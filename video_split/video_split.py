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


def _build_output_paths(
    in_path: Path,
    *,
    output_dir: Path | None,
    digits: int,
) -> tuple[Path, str]:
    if output_dir is None:
        output_dir = in_path.parent / f"{in_path.stem}_split"

    suffix = in_path.suffix or ".mp4"
    output_template = str(output_dir / f"%0{digits}d_{in_path.stem}{suffix}")
    output_single = output_dir / f"{1:0{digits}d}_{in_path.stem}{suffix}"
    return output_single, output_template


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
        "input",
        nargs="?",
        help="Input video file path (also supports --in).",
    )
    p.add_argument(
        "--in",
        dest="in_path",
        help="Input video file path (same as positional input).",
    )

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--count", type=int, help="Split into N parts (exactly N outputs).")
    mode.add_argument(
        "--duration",
        help='Split by segment duration, e.g. "10" (seconds) or "00:00:10" (HH:MM:SS).',
    )

    p.add_argument(
        "--output-dir",
        help="Output directory. Default: <input_dir>/<input_stem>_split",
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
        help="Start index for numbering, e.g. 17 -> 017_... (alias: --start-number). Default: 1.",
    )

    p.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable name/path.")
    p.add_argument("--ffprobe", default="ffprobe", help="ffprobe executable name/path.")
    p.add_argument("--dry-run", action="store_true", help="Print the ffmpeg command, do not run.")

    return p


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    in_raw = (args.in_path or args.input or "").strip()
    if not in_raw:
        parser.error("Missing input video path. Provide positional input or --in.")
        return 2

    in_path = Path(in_raw).expanduser().resolve()
    if not in_path.exists() or not in_path.is_file():
        sys.stderr.write(f"ERROR: input not found: {in_path}\n")
        return 1

    if args.digits <= 0:
        sys.stderr.write("ERROR: --digits must be > 0\n")
        return 1
    if args.start_index <= 0:
        sys.stderr.write("ERROR: --startIndex must be > 0\n")
        return 1

    tools = Tools(ffmpeg=args.ffmpeg, ffprobe=args.ffprobe)
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None

    out_single, out_template = _build_output_paths(in_path, output_dir=output_dir, digits=args.digits)
    segment_format = _segment_format_from_suffix(in_path.suffix)

    # Note: PTools UI typically passes args via Arg1..Arg3; keep prints concise and deterministic.
    try:
        out_single.parent.mkdir(parents=True, exist_ok=True)

        if args.count is not None:
            if args.count <= 0:
                raise ValueError("--count must be > 0")

            if args.count == 1:
                cmd = _ffmpeg_copy_cmd(in_path, out_path=out_single, tools=tools)
                if args.dry_run:
                    sys.stdout.write(" ".join(cmd) + "\n")
                    return 0
                _ffmpeg_copy_single(in_path, out_path=out_single, tools=tools)
                sys.stdout.write(f"OK: {out_single}\n")
                return 0

            duration = _probe_duration_seconds(in_path, tools=tools)
            cut_times = [duration * i / args.count for i in range(1, args.count)]
            cut_times = [t for t in cut_times if 0 < t < duration]

            cmd = _ffmpeg_segment_cmd_base(
                in_path,
                tools=tools,
                segment_format=segment_format,
                start_number=args.start_index,
            )
            cmd += ["-segment_times", ",".join(f"{t:.3f}" for t in cut_times)]
            cmd.append(out_template)

            if args.dry_run:
                sys.stdout.write(" ".join(cmd) + "\n")
                return 0

            result = _run(cmd)
            _require_success(result, cmd=cmd)

            sys.stdout.write(f"OK: {out_single.parent}\n")
            return 0

        if args.duration is not None:
            seconds = _parse_duration_to_seconds(args.duration)

            cmd = _ffmpeg_segment_cmd_base(
                in_path,
                tools=tools,
                segment_format=segment_format,
                start_number=args.start_index,
            )
            cmd += ["-segment_time", f"{seconds:.3f}"]
            cmd.append(out_template)

            if args.dry_run:
                sys.stdout.write(" ".join(cmd) + "\n")
                return 0

            result = _run(cmd)
            _require_success(result, cmd=cmd)
            sys.stdout.write(f"OK: {out_single.parent}\n")
            return 0

        parser.error("Internal error: no split mode selected.")
        return 2
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

