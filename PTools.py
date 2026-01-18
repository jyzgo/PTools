from __future__ import annotations

import shlex
import subprocess
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

sys.dont_write_bytecode = True


@dataclass(frozen=True)
class ScriptItem:
    display_name: str
    path: Path
    kind: str  # "py" | "bat"


def _is_ignored_dir(dir_name: str) -> bool:
    ignored = {
        "__pycache__",
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "dist",
        "build",
    }
    return dir_name in ignored


def _display_name_from_relative_path(relative: Path, *, suffix: str) -> str:
    relative_str = relative.as_posix()
    if suffix and relative_str.lower().endswith(suffix.lower()):
        return relative_str[: -len(suffix)]
    return relative_str


def _list_scripts_recursive(*, scripts_dir: Path, self_path: Path) -> list[ScriptItem]:
    scripts: list[ScriptItem] = []

    root_stub = (scripts_dir / "PTools.py").resolve()

    patterns: list[tuple[str, str]] = [
        ("*.py", "py"),
        ("*.bat", "bat"),
    ]

    for pattern, kind in patterns:
        for file_path in scripts_dir.rglob(pattern):
            if not file_path.is_file():
                continue

            resolved = file_path.resolve()
            if resolved == self_path:
                continue
            if resolved == root_stub:
                continue

            if kind == "py" and file_path.name == "__init__.py":
                continue

            if file_path.name.startswith("_"):
                continue

            if any(_is_ignored_dir(part) for part in file_path.parts):
                continue

            try:
                relative = file_path.relative_to(scripts_dir)
            except ValueError:
                # 防御：理论上不会发生（rglob 来源于 scripts_dir）
                relative = Path(file_path.name)

            display_name = _display_name_from_relative_path(relative, suffix=file_path.suffix)
            scripts.append(ScriptItem(display_name=display_name, path=file_path, kind=kind))

    scripts.sort(key=lambda item: item.display_name.lower())
    return scripts


def _split_args(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    return shlex.split(raw, posix=(not sys.platform.startswith("win")))


class PToolsApp:
    def __init__(self, root: tk.Tk, scripts_dir: Path) -> None:
        self._root = root
        self._scripts_dir = scripts_dir
        self._self_path = Path(__file__).resolve()

        self._selected_script: ScriptItem | None = None
        self._script_buttons_by_path: dict[Path, ttk.Button] = {}

        self._path_var = tk.StringVar()
        self._arg_vars = [tk.StringVar() for _ in range(3)]
        self._status_var = tk.StringVar(value="Ready")

        self._style = ttk.Style(self._root)
        self._style.configure("Script.TButton", padding=(10, 8))
        self._style.configure("SelectedScript.TButton", padding=(10, 8), relief="sunken")

        self._build_ui()
        self.refresh_scripts()

        self._root.bind("<Return>", self._on_return_key, add=True)

    def _build_ui(self) -> None:
        self._root.title("PTools")
        self._root.minsize(900, 520)

        container = ttk.Frame(self._root, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        self._root.rowconfigure(0, weight=1)
        self._root.columnconfigure(0, weight=1)

        container.columnconfigure(0, weight=1)

        top_row = ttk.Frame(container)
        top_row.grid(row=0, column=0, sticky="ew")
        top_row.columnconfigure(1, weight=1)

        ttk.Label(top_row, text="Path:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._path_entry = ttk.Entry(top_row, textvariable=self._path_var)
        self._path_entry.grid(row=0, column=1, sticky="ew")

        args_row = ttk.Frame(container)
        args_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        for col in range(3):
            args_row.columnconfigure(col, weight=1)
        args_row.columnconfigure(3, weight=0)

        self._arg_entries: list[ttk.Entry] = []
        for idx, var in enumerate(self._arg_vars, start=1):
            cell = ttk.Frame(args_row)
            cell.grid(row=0, column=idx - 1, sticky="ew", padx=(0 if idx == 1 else 8, 0))
            cell.columnconfigure(1, weight=1)

            ttk.Label(cell, text=f"Arg{idx}:").grid(row=0, column=0, sticky="w", padx=(0, 6))
            entry = ttk.Entry(cell, textvariable=var)
            entry.grid(row=0, column=1, sticky="ew")
            self._arg_entries.append(entry)

        self._run_button = ttk.Button(args_row, text="Run", command=self.run_selected_script)
        self._run_button.grid(row=0, column=3, sticky="e", padx=(12, 0))

        ttk.Separator(container).grid(row=2, column=0, sticky="ew", pady=12)

        scripts_label_row = ttk.Frame(container)
        scripts_label_row.grid(row=3, column=0, sticky="ew")
        scripts_label_row.columnconfigure(0, weight=1)
        ttk.Label(scripts_label_row, text="Scripts:").grid(row=0, column=0, sticky="w")
        ttk.Button(scripts_label_row, text="Refresh", command=self.refresh_scripts).grid(
            row=0,
            column=1,
            sticky="e",
        )

        scripts_area = ttk.Frame(container)
        scripts_area.grid(row=4, column=0, sticky="nsew")
        container.rowconfigure(4, weight=1)
        scripts_area.rowconfigure(0, weight=1)
        scripts_area.columnconfigure(0, weight=1)

        self._scripts_canvas = tk.Canvas(scripts_area, highlightthickness=0)
        self._scripts_canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(scripts_area, orient="vertical", command=self._scripts_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._scripts_canvas.configure(yscrollcommand=scrollbar.set)

        self._scripts_frame = ttk.Frame(self._scripts_canvas, padding=(0, 0, 4, 0))
        self._scripts_window_id = self._scripts_canvas.create_window(
            (0, 0),
            window=self._scripts_frame,
            anchor="nw",
        )

        self._scripts_frame.bind("<Configure>", self._on_scripts_frame_configure, add=True)
        self._scripts_canvas.bind("<Configure>", self._on_canvas_configure, add=True)

        status_row = ttk.Frame(container)
        status_row.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        status_row.columnconfigure(0, weight=1)
        ttk.Label(status_row, textvariable=self._status_var).grid(row=0, column=0, sticky="w")

        self._path_entry.focus_set()

    def _on_scripts_frame_configure(self, _event: tk.Event) -> None:
        self._scripts_canvas.configure(scrollregion=self._scripts_canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._scripts_canvas.itemconfigure(self._scripts_window_id, width=event.width)

    def _on_return_key(self, _event: tk.Event) -> None:
        self.run_selected_script()

    def refresh_scripts(self) -> None:
        scripts = _list_scripts_recursive(scripts_dir=self._scripts_dir, self_path=self._self_path)

        for child in self._scripts_frame.winfo_children():
            child.destroy()

        self._script_buttons_by_path.clear()
        self._selected_script = None

        max_columns = 6
        for col in range(max_columns):
            self._scripts_frame.columnconfigure(col, weight=1, uniform="scripts")

        if not scripts:
            empty = ttk.Label(
                self._scripts_frame,
                text="No scripts found under scripts_dir. Put .py/.bat files under the folder, then click Refresh.",
                foreground="#666666",
            )
            empty.grid(row=0, column=0, sticky="w")
            self._status_var.set("Ready (no scripts found)")
            return

        for idx, item in enumerate(scripts):
            row = idx // max_columns
            col = idx % max_columns

            button = ttk.Button(
                self._scripts_frame,
                text=item.display_name,
                style="Script.TButton",
                command=lambda it=item: self.select_script(it),
            )
            button.grid(row=row, column=col, sticky="ew", padx=6, pady=6)
            self._script_buttons_by_path[item.path] = button

        self.select_script(scripts[0])

    def select_script(self, item: ScriptItem) -> None:
        self._selected_script = item

        for path, button in self._script_buttons_by_path.items():
            style = "SelectedScript.TButton" if path == item.path else "Script.TButton"
            button.configure(style=style)

        self._status_var.set(f"Selected: {item.display_name}")

    def _build_command(self, item: ScriptItem) -> list[str]:
        if item.kind == "py":
            cmd: list[str] = [sys.executable, str(item.path)]
        elif item.kind == "bat":
            cmd = ["cmd.exe", "/c", str(item.path)]
        else:
            raise ValueError(f"Unsupported script type: {item.kind}")

        raw_path = self._path_var.get().strip()
        if raw_path:
            cmd.append(raw_path)

        for var in self._arg_vars:
            cmd.extend(_split_args(var.get()))

        return cmd

    def run_selected_script(self) -> None:
        item = self._selected_script
        if item is None:
            self._status_var.set("Please select a script first.")
            return

        try:
            cmd = self._build_command(item)
        except ValueError as exc:
            self._status_var.set(f"Invalid args: {exc}")
            return

        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = subprocess.CREATE_NEW_CONSOLE

        try:
            subprocess.Popen(cmd, cwd=str(item.path.parent), creationflags=creationflags)
        except OSError as exc:
            self._status_var.set(f"Failed to run: {exc}")
            return

        self._status_var.set(f"Running: {' '.join(cmd)}")


def main(*, scripts_dir: Path | None = None) -> int:
    scripts_dir = scripts_dir or Path(__file__).resolve().parent

    root = tk.Tk()
    PToolsApp(root, scripts_dir=scripts_dir)
    root.mainloop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

