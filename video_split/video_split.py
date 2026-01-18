from __future__ import annotations

import argparse
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.dont_write_bytecode = True


@dataclass(frozen=True)
class Tools:
    ffmpeg: str
    ffprobe: str


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _require_success(result: subprocess.CompletedProcess[str], *, cmd: list[str]) -> None:
    if result.returncode == 0:
        return

    cmd_str = " ".join(cmd)
    stderr = (result.stderr or "").strip()
    if stderr:
        raise RuntimeError(f"Command failed ({result.returncode}): {cmd_str}\n{stderr}")
    raise RuntimeError(f"Command failed ({result.returncode}): {cmd_str}")


def _probe_duration_seconds(in_path: Path, *, tools: Tools) -> float:
    cmd = [
        tools.ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nk=1:nw=1",
        str(in_path),
    ]
    result = _run(cmd)
    _require_success(result, cmd=cmd)

    raw = (result.stdout or "").strip()
    try:
        duration = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"ffprobe returned invalid duration: {raw!r}") from exc

    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(f"Invalid duration from ffprobe: {duration!r}")
    return duration


def _parse_duration_to_seconds(raw: str) -> float:
    raw = raw.strip()
    if not raw:
        raise ValueError("duration is empty")

    # Accept seconds as a number: "10", "2.5"
    if ":" not in raw:
        seconds = float(raw)
        if seconds <= 0:
            raise ValueError("duration must be > 0")
        return seconds

    # Accept timecode: "HH:MM:SS" or "HH:MM:SS.mmm"
    parts = raw.split(":")
    if len(parts) != 3:
        raise ValueError("duration timecode must be HH:MM:SS(.ms)")

    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise ValueError("duration must be > 0")
    return total


def _segment_format_from_suffix(suffix: str) -> str | None:
    ext = suffix.lower().lstrip(".")
    if not ext:
        return None

    mapping = {
        "mp4": "mp4",
        "m4v": "mp4",
        "mov": "mov",
        "mkv": "matroska",
        "webm": "webm",
        "avi": "avi",
        "flv": "flv",
        "ts": "mpegts",
        "m2ts": "mpegts",
        "mts": "mpegts",
    }
    return mapping.get(ext) or ext


def _ffmpeg_segment_cmd_base(
    in_path: Path,
    *,
    tools: Tools,
    segment_format: str | None,
    start_number: int,
) -> list[str]:
    cmd = [
        tools.ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(in_path),
        "-map",
        "0",
        "-c",
        "copy",
        "-f",
        "segment",
        "-reset_timestamps",
        "1",
    ]

    if segment_format:
        cmd += ["-segment_format", segment_format]
        if segment_format in {"mp4", "mov"}:
            cmd += ["-segment_format_options", "movflags=+faststart"]

    cmd += ["-segment_start_number", str(start_number)]
    return cmd


def _ffmpeg_copy_cmd(in_path: Path, *, out_path: Path, tools: Tools) -> list[str]:
    return [
        tools.ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(in_path),
        "-map",
        "0",
        "-c",
        "copy",
        str(out_path),
    ]


def _ffmpeg_copy_single(in_path: Path, *, out_path: Path, tools: Tools) -> None:
    cmd = _ffmpeg_copy_cmd(in_path, out_path=out_path, tools=tools)
    result = _run(cmd)
    _require_success(result, cmd=cmd)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="video_split.py",
        description="Split a video into multiple parts by count or by duration (requires ffmpeg/ffprobe).",
    )

    p.add_argument(
        "inputs",
        nargs="*",
        help="Input video file paths (you can pass multiple).",
    )
    p.add_argument(
        "--in",
        dest="in_paths",
        action="append",
        help="Input video file path (can repeat; same as positional inputs).",
    )

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--count", type=int, help="Split into N parts (exactly N outputs).")
    mode.add_argument(
        "--duration",
        help='Split by segment duration, e.g. "10" (seconds) or "00:00:10" (HH:MM:SS).',
    )

    p.add_argument(
        "--output-dir",
        help=(
            "Output directory. Default: for single input -> <input_dir>/<input_stem>_split; "
            "for multiple inputs -> <first_input_dir>/video_split_out"
        ),
    )
    p.add_argument(
        "--digits",
        type=int,
        default=3,
        help="Prefix digits for numbering. Default: 3 (001, 002, ...).",
    )
    p.add_argument(
        "--startIndex",
        "--start-number",
        dest="start_index",
        type=int,
        default=1,
        help=(
            "Start index for numbering, e.g. 17 -> 017_... (alias: --start-number). "
            "When multiple inputs are provided, numbering will continue across files. Default: 1."
        ),
    )

    p.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable name/path.")
    p.add_argument("--ffprobe", default="ffprobe", help="ffprobe executable name/path.")
    p.add_argument("--dry-run", action="store_true", help="Print the ffmpeg command, do not run.")

    return p


def _resolve_existing_file(path_raw: str) -> Path:
    path = Path(path_raw).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(str(path))
    return path


def _default_output_dir(in_paths: list[Path]) -> Path:
    if len(in_paths) == 1:
        in_path = in_paths[0]
        return in_path.parent / f"{in_path.stem}_split"
    # Multiple inputs: default to a single shared output folder so numbering can be continuous.
    return in_paths[0].parent / "video_split_out"


def _next_start_index_from_dir(output_dir: Path, *, digits: int, fallback: int) -> int:
    """
    Determine next start index by scanning output_dir for files like:
      ^\\d+_...
    and returning (max + 1). If none found, return fallback.
    """
    max_index = 0

    if not output_dir.exists() or not output_dir.is_dir():
        return fallback

    for p in output_dir.iterdir():
        if not p.is_file():
            continue
        name = p.name
        underscore_pos = name.find("_")
        if underscore_pos <= 0:
            continue
        head = name[:underscore_pos]
        if not head.isdigit():
            continue
        if len(head) < digits:
            # Be conservative: keep current digits setting as a minimum width.
            # (This should not happen for files produced by this tool.)
            continue
        idx = int(head, 10)
        if idx > max_index:
            max_index = idx

    return (max_index + 1) if max_index > 0 else fallback


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    raw_inputs: list[str] = []
    if args.in_paths:
        raw_inputs.extend(args.in_paths)
    if args.inputs:
        raw_inputs.extend(args.inputs)

    raw_inputs = [s.strip() for s in raw_inputs if str(s).strip()]
    if not raw_inputs:
        parser.error("Missing input video path(s). Provide positional inputs or one/more --in.")
        return 2

    if args.digits <= 0:
        sys.stderr.write("ERROR: --digits must be > 0\n")
        return 1
    if args.start_index <= 0:
        sys.stderr.write("ERROR: --startIndex must be > 0\n")
        return 1

    tools = Tools(ffmpeg=args.ffmpeg, ffprobe=args.ffprobe)
    try:
        in_paths = [_resolve_existing_file(p) for p in raw_inputs]
    except FileNotFoundError as exc:
        sys.stderr.write(f"ERROR: input not found: {exc}\n")
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else _default_output_dir(in_paths)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Note: PTools UI typically passes args via Arg1..Arg3; keep prints concise and deterministic.
    try:
        current_start = args.start_index

        for in_path in in_paths:
            suffix = in_path.suffix or ".mp4"
            out_template = str(output_dir / f"%0{args.digits}d_{in_path.stem}{suffix}")
            out_single = output_dir / f"{current_start:0{args.digits}d}_{in_path.stem}{suffix}"
            segment_format = _segment_format_from_suffix(in_path.suffix)

            if args.count is not None:
                if args.count <= 0:
                    raise ValueError("--count must be > 0")

                if args.count == 1:
                    cmd = _ffmpeg_copy_cmd(in_path, out_path=out_single, tools=tools)
                    if args.dry_run:
                        sys.stdout.write(" ".join(cmd) + "\n")
                    else:
                        _ffmpeg_copy_single(in_path, out_path=out_single, tools=tools)
                    current_start = _next_start_index_from_dir(output_dir, digits=args.digits, fallback=current_start + 1)
                    continue

                duration = _probe_duration_seconds(in_path, tools=tools)
                cut_times = [duration * i / args.count for i in range(1, args.count)]
                cut_times = [t for t in cut_times if 0 < t < duration]

                cmd = _ffmpeg_segment_cmd_base(
                    in_path,
                    tools=tools,
                    segment_format=segment_format,
                    start_number=current_start,
                )
                cmd += ["-segment_times", ",".join(f"{t:.3f}" for t in cut_times)]
                cmd.append(out_template)

                if args.dry_run:
                    sys.stdout.write(" ".join(cmd) + "\n")
                else:
                    result = _run(cmd)
                    _require_success(result, cmd=cmd)

                current_start = _next_start_index_from_dir(
                    output_dir,
                    digits=args.digits,
                    fallback=current_start + args.count,
                )
                continue

            if args.duration is not None:
                seconds = _parse_duration_to_seconds(args.duration)
                cmd = _ffmpeg_segment_cmd_base(
                    in_path,
                    tools=tools,
                    segment_format=segment_format,
                    start_number=current_start,
                )
                cmd += ["-segment_time", f"{seconds:.3f}"]
                cmd.append(out_template)

                if args.dry_run:
                    sys.stdout.write(" ".join(cmd) + "\n")
                    current_start = _next_start_index_from_dir(
                        output_dir,
                        digits=args.digits,
                        fallback=current_start + 1,
                    )
                    continue
                else:
                    result = _run(cmd)
                    _require_success(result, cmd=cmd)

                # Conservative fallback if the directory scan doesn't find anything new.
                duration = _probe_duration_seconds(in_path, tools=tools)
                expected_segments = max(1, int(math.ceil(duration / seconds)))
                current_start = _next_start_index_from_dir(
                    output_dir,
                    digits=args.digits,
                    fallback=current_start + expected_segments,
                )
                continue

            parser.error("Internal error: no split mode selected.")
            return 2

        if args.dry_run:
            return 0

        sys.stdout.write(f"OK: {output_dir}\n")
        return 0
    except FileNotFoundError as exc:
        # Typically ffmpeg/ffprobe missing.
        sys.stderr.write(
            "ERROR: required tool not found. Please install ffmpeg and ensure ffmpeg/ffprobe are in PATH.\n"
            f"Details: {exc}\n"
        )
        return 1
    except Exception as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

