#!/usr/bin/env python3
"""
SVN冲突递归解决脚本 - 增强版
确保能正确处理所有子目录
"""

import json
import locale
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import xml.etree.ElementTree as ET
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.dont_write_bytecode = True

_SVN_EXE: Path | None = None


def _config_path() -> Path:
    """
    配置文件路径：放到用户目录下，文件名为 .safesvnconf
    """
    return (Path.home() / ".safesvnconf").resolve()


def _legacy_config_path() -> Path:
    """
    兼容旧版本配置文件位置（%LOCALAPPDATA%\\SafesvnResolver\\config.json）。
    """
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / "AppData" / "Local"
    return (root / "SafesvnResolver" / "config.json").resolve()


def _load_config() -> dict:
    p = _config_path()
    try:
        if not p.exists():
            # 兼容迁移：新配置不存在时，尝试读取旧配置并迁移到新位置
            legacy = _legacy_config_path()
            if legacy.exists():
                cfg = json.loads(legacy.read_text(encoding="utf-8"))
                try:
                    _save_config(cfg)
                except Exception:
                    pass
                return cfg if isinstance(cfg, dict) else {}
            return {}
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(cfg: dict) -> None:
    p = _config_path()
    # 用户目录下的单文件：不需要创建目录，但保留写入前的目录存在性检查
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _set_svn_exe(path: Path | str | None) -> None:
    global _SVN_EXE
    _SVN_EXE = Path(path).resolve() if path else None


def _candidate_svn_paths() -> list[Path]:
    """
    常见 SVN 客户端安装路径候选（Windows）。
    """
    candidates: list[Path] = []
    # TortoiseSVN
    candidates += [
        Path(r"C:\Program Files\TortoiseSVN\bin\svn.exe"),
        Path(r"C:\Program Files (x86)\TortoiseSVN\bin\svn.exe"),
    ]
    # SlikSVN
    candidates += [
        Path(r"C:\Program Files\SlikSvn\bin\svn.exe"),
        Path(r"C:\Program Files (x86)\SlikSvn\bin\svn.exe"),
    ]
    # CollabNet / VisualSVN / 其他发行版（路径各异，给几个常见兜底）
    candidates += [
        Path(r"C:\Program Files\CollabNet Subversion Client\svn.exe"),
        Path(r"C:\Program Files (x86)\CollabNet Subversion Client\svn.exe"),
        Path(r"C:\Program Files\Subversion\bin\svn.exe"),
        Path(r"C:\Program Files (x86)\Subversion\bin\svn.exe"),
        Path(r"C:\Program Files\VisualSVN Server\bin\svn.exe"),
        Path(r"C:\Program Files (x86)\VisualSVN Server\bin\svn.exe"),
    ]
    return candidates


def _resolve_svn_exe() -> Path | None:
    """
    解析可用的 svn.exe 路径：
    1) 配置文件里保存的路径
    2) PATH 上的 svn
    3) 常见安装路径
    """
    cfg = _load_config()
    cfg_path = cfg.get("svn_exe")
    if cfg_path:
        p = Path(cfg_path)
        if p.exists() and p.is_file():
            return p.resolve()

    which = shutil.which("svn")
    if which:
        p = Path(which)
        if p.exists():
            return p.resolve()

    for p in _candidate_svn_paths():
        if p.exists() and p.is_file():
            return p.resolve()

    return None


def get_svn_exe_or_none() -> Path | None:
    global _SVN_EXE
    if _SVN_EXE is not None and _SVN_EXE.exists():
        return _SVN_EXE
    resolved = _resolve_svn_exe()
    if resolved is not None:
        _set_svn_exe(resolved)
        return resolved
    return None


def ensure_svn_exe_or_raise() -> Path:
    svn_exe = get_svn_exe_or_none()
    if svn_exe is None:
        raise FileNotFoundError(
            "未找到 svn 可执行文件（svn.exe）。\n"
            "解决办法：\n"
            "1) 安装 TortoiseSVN / SlikSVN 等客户端；或\n"
            "2) 将 svn.exe 所在目录加入 PATH；或\n"
            "3) 在本工具里手动选择 svn.exe 路径。"
        )
    return svn_exe


def ensure_svn_exe_gui(parent: tk.Tk | None = None) -> bool:
    """
    GUI 场景：确保 svn.exe 可用；不可用则弹窗引导用户选择，并保存到配置。
    返回 True 表示可用，False 表示用户取消/仍不可用。
    """
    try:
        ensure_svn_exe_or_raise()
        return True
    except FileNotFoundError as e:
        ok = messagebox.askokcancel(
            "未检测到 svn.exe",
            f"{e}\n\n是否现在手动选择 svn.exe？",
            parent=parent,
        )
        if not ok:
            return False

        exe_path = filedialog.askopenfilename(
            parent=parent,
            title="请选择 svn.exe",
            filetypes=[("svn.exe", "svn.exe"), ("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if not exe_path:
            return False

        p = Path(exe_path)
        if not p.exists() or not p.is_file():
            messagebox.showerror("路径无效", "选择的文件不存在或不是文件。", parent=parent)
            return False

        # 简单校验文件名（不强制，避免某些发行版命名差异）
        if p.name.lower() != "svn.exe":
            ok2 = messagebox.askokcancel(
                "确认选择",
                f"你选择的文件名不是 svn.exe：\n\n{p}\n\n仍然继续使用它吗？",
                parent=parent,
            )
            if not ok2:
                return False

        _set_svn_exe(p)
        cfg = _load_config()
        cfg["svn_exe"] = str(p)
        try:
            _save_config(cfg)
        except Exception:
            # 保存失败不影响使用（只是下次还会提示）
            pass

        return True


def _run_svn(args, cwd: Path, timeout: float | None = None):
    """
    统一执行 svn 命令：自动使用系统首选编码并容错解码，避免 Windows 下 UTF-8 解码失败。
    """
    svn_exe = ensure_svn_exe_or_raise()
    encoding = locale.getpreferredencoding(False) or "utf-8"
    return subprocess.run(
        [str(svn_exe), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding=encoding,
        errors="replace",
        timeout=timeout,
    )


def _parse_svn_status_xml(xml_text: str, root: Path):
    """
    解析 `svn status --xml` 输出，返回冲突文件的绝对 Path 列表。
    """
    conflicts = []
    tree = ET.fromstring(xml_text)
    for entry in tree.findall(".//entry"):
        rel_path = entry.get("path")
        if not rel_path:
            continue
        wc_status = entry.find("wc-status")
        if wc_status is None:
            continue

        item = (wc_status.get("item") or "").lower()
        tree_conflicted = (wc_status.get("tree-conflicted") or "").lower() == "true"

        if item == "conflicted" or tree_conflicted:
            conflicts.append((root / rel_path).resolve())
    return conflicts


def _parse_svn_status_text(text: str, root: Path):
    """
    兜底：解析 `svn status` 的文本输出（尽量按固定列格式取路径）。
    """
    conflicts = []
    for line in text.splitlines():
        if not line:
            continue
        # `svn status` 前 7 列是状态列，之后是路径；冲突项第一列为 'C'
        # 例: "C       path/to/file" 或 "C  +    path/to/file"
        m = re.match(r"^C.{6}\s+(.*)$", line)
        if m:
            rel = m.group(1).strip()
        else:
            # 兼容非常规格式
            parts = line.split(maxsplit=1)
            if len(parts) != 2 or parts[0] != "C":
                continue
            rel = parts[1].strip()

        if rel:
            conflicts.append((root / rel).resolve())
    return conflicts


def ensure_svn_root_or_exit():
    """
    确保当前工作目录位于 SVN 工作副本内（并尽量切到最近的包含 .svn 的目录）。
    """
    if not (Path(".") / ".svn").exists():
        for parent in Path(".").absolute().parents:
            if (parent / ".svn").exists():
                print(f"当前目录不是SVN根目录，切换到: {parent}")
                os.chdir(parent)
                break
        else:
            print("错误: 当前目录及其父目录都不是SVN工作副本")
            sys.exit(1)


def find_nearest_svn_root(start: Path | str = ".") -> Path | None:
    """
    从 start 开始向上查找最近的 SVN 工作副本根目录（包含 .svn 的目录）。
    找不到返回 None。
    """
    p = Path(start).resolve()
    if (p / ".svn").exists():
        return p
    for parent in p.parents:
        if (parent / ".svn").exists():
            return parent
    return None


def run_svn_update(root: Path):
    """
    执行 `svn update`，返回 (returncode, stdout, stderr)
    """
    result = _run_svn(["update"], cwd=root)
    return result.returncode, result.stdout or "", result.stderr or ""


def svn_update_output_has_conflict(stdout: str, stderr: str) -> bool:
    """
    基于 `svn update` 的输出快速判断“很可能出现冲突/需要人工处理”。

    说明：
    - `svn update` 通常会以单字母状态输出每个路径（U/G/A/D/C...），其中 C 常表示冲突。
    - 不同 SVN 客户端/语言环境输出略有差异，因此这里做多条件兜底匹配。
    - 该判断用于“是否需要进一步跑 svn status 全量扫描”的性能优化；最终以 status 扫描为准。
    """
    text = f"{stdout}\n{stderr}".strip()
    if not text:
        return False

    # 常见：行首 "C " 表示冲突
    if re.search(r"(?m)^[ \t]*C[ \t]", text):
        return True

    # 一些版本会输出类似 "Summary of conflicts:" / "conflict" / "conflicted"
    if re.search(r"(?i)\bconflict(ed|ing)?\b", text):
        return True

    # 树冲突有时会出现 "Tree conflict" 字样
    if re.search(r"(?i)\btree\s+conflict\b", text):
        return True

    return False


def find_svn_working_copies(base: Path | str, *, ignore_dirnames=None):
    """
    在 base 下递归查找 SVN 工作副本根目录（以存在 .svn 目录为准）。

    - 会跳过一些常见的大目录（可通过 ignore_dirnames 追加/覆盖）。
    - 支持“嵌套的独立工作副本”（例如某些目录是单独 checkout/externals 形成的工作副本）。
    - 为了性能：当发现某个目录本身是工作副本根目录时，默认不再深入它的子目录；
      但如果这个目录就是 base（扫描起点），则仍会继续向下查找其它嵌套工作副本。
    """
    base = Path(base).resolve()
    ignore = set(ignore_dirnames or [])
    ignore |= {
        ".git",
        ".svn",
        "__pycache__",
        ".vs",
        ".idea",
        # 下面这些目录在本工程里通常非常大且一般不含嵌套 SVN 工作副本；如你确实需要扫描它们，可从这里移除
        "client",
        "Libs",
        "config",
        "dist",
        "build",
        "Library",
        "Temp",
        "Obj",
        "Build",
        "Builds",
        "Logs",
        "UserSettings",
        "node_modules",
    }

    roots: list[Path] = []
    seen: set[Path] = set()

    for dirpath, dirnames, _filenames in os.walk(str(base), topdown=True):
        # 剪枝：避免进入明显不需要的目录
        dirnames[:] = [d for d in dirnames if d not in ignore]

        p = Path(dirpath)
        svn_dir = p / ".svn"
        if svn_dir.is_dir():
            # 额外做一点“看起来像 SVN 元数据”的校验，避免误把普通名为 .svn 的目录当做工作副本
            if not ((svn_dir / "wc.db").exists() or (svn_dir / "entries").exists()):
                continue

            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                roots.append(rp)

            # 找到工作副本根后：为了性能通常不再深入该目录
            # 但如果当前目录就是扫描起点 base，则继续往下找嵌套工作副本（否则会漏）
            if rp != base:
                dirnames[:] = []

    roots.sort(key=lambda x: str(x).lower())
    return roots


def resolve_conflicts_paths(paths):
    """
    对给定路径列表执行 resolve。不同冲突类型可接受策略不同，这里做多策略兜底。
    返回 (success_count, total, failures[(path, stderr)])
    """
    root = Path(".").resolve()
    accept_candidates = [
        "theirs-full",
        "theirs-conflict",
        "working",
    ]

    success = 0
    failures = []

    for cf in paths:
        last = None
        ok = False
        for accept in accept_candidates:
            result = _run_svn(["resolve", "--accept", accept, str(cf)], cwd=root)
            last = result
            if result.returncode == 0:
                ok = True
                break
        if ok:
            success += 1
        else:
            err = ((last.stderr if last else "") or "").strip()
            failures.append((cf, err))

    return success, len(list(paths)), failures


def resolve_conflicts_grouped(items):
    """
    对多个 SVN 工作副本中的冲突路径执行 resolve。

    items: Iterable[(wc_root: Path, conflict_path: Path)]
    返回 (success_count, total, failures[(path, stderr)])
    """
    accept_candidates = [
        "theirs-full",
        "theirs-conflict",
        "working",
    ]

    success = 0
    failures = []

    # 分组：wc_root -> [paths...]
    grouped: dict[Path, list[Path]] = {}
    for wc_root, cf in items:
        wc_root = Path(wc_root).resolve()
        cf = Path(cf).resolve()
        grouped.setdefault(wc_root, []).append(cf)

    for wc_root, paths in grouped.items():
        for cf in paths:
            last = None
            ok = False
            for accept in accept_candidates:
                result = _run_svn(["resolve", "--accept", accept, str(cf)], cwd=wc_root)
                last = result
                if result.returncode == 0:
                    ok = True
                    break
            if ok:
                success += 1
            else:
                err = ((last.stderr if last else "") or "").strip()
                failures.append((cf, err))

    total = sum(len(v) for v in grouped.values())
    return success, total, failures


def find_all_svn_conflicts_recursive(root_dir="."):
    """
    递归查找所有SVN冲突文件
    使用多种方法确保不遗漏
    """
    root = Path(root_dir).resolve()
    conflict_files = []
    method1_ok = False

    # 方法1: 使用 svn status --xml（递归、机器可读，最稳）
    print("方法1: 使用 svn status --xml 递归扫描...")
    try:
        # XML 输出通常声明为 UTF-8；这里直接按 bytes 捕获并用 UTF-8 解码，避免系统编码导致乱码/解析失败
        svn_exe = ensure_svn_exe_or_raise()
        result = subprocess.run(
            [str(svn_exe), "status", "--xml", "--depth", "infinity"],
            cwd=str(root),
            capture_output=True,
        )

        if result.returncode == 0:
            xml_text = (result.stdout or b"").decode("utf-8", errors="replace")
            for filepath in _parse_svn_status_xml(xml_text, root):
                if filepath not in conflict_files:
                    conflict_files.append(filepath)
                    try:
                        rel = filepath.relative_to(root)
                    except Exception:
                        rel = filepath
                    print(f"  [方法1] 发现冲突: {rel}")
            # 只要 XML 成功解析并执行完，就认为扫描可靠；不再进入方法2（避免全仓库二次扫描卡死）
            method1_ok = True
        else:
            err = (result.stderr or "").strip()
            if err:
                print(f"  方法1返回非0: {err}")
    except Exception as e:
        print(f"  方法1失败: {e}")

    if method1_ok:
        # 去重并返回（即使为空，也表示已可靠扫描完）
        unique_files = []
        seen = set()
        for f in conflict_files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)
        print(f"[SCAN] {time.strftime('%H:%M:%S')} 方法1完成：冲突 {len(unique_files)} 个（已跳过方法2兜底）")
        return unique_files

    # 方法2: 兜底使用文本格式（递归）
    print("\n方法2: 使用 svn status 文本输出兜底扫描...")
    try:
        # 兜底扫描可能非常慢（Unity 工程文件量巨大），加超时避免长时间卡住
        result = _run_svn(["status", "--depth", "infinity"], cwd=root, timeout=60)
        if result.returncode == 0:
            for filepath in _parse_svn_status_text(result.stdout, root):
                if filepath not in conflict_files:
                    conflict_files.append(filepath)
                    try:
                        rel = filepath.relative_to(root)
                    except Exception:
                        rel = filepath
                    print(f"  [方法2] 发现冲突: {rel}")
        else:
            err = (result.stderr or "").strip()
            if err:
                print(f"  方法2返回非0: {err}")
    except subprocess.TimeoutExpired:
        print("  方法2超时：跳过文本兜底扫描（可尝试仅使用方法1结果）")
    except Exception as e:
        print(f"  方法2失败: {e}")

    # 去重并返回
    unique_files = []
    seen = set()
    for f in conflict_files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)
    print(f"[SCAN] {time.strftime('%H:%M:%S')} 扫描完成：冲突 {len(unique_files)} 个（方法2兜底已执行/尝试）")
    return unique_files


class SafesvnResolverApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        # base_root：用于“拉取全部svn库”时的递归扫描起点
        self.base_root = Path(".").resolve()
        # svn_root：用于“扫描冲突/解决冲突”的 SVN 工作副本根目录（运行时动态确定）
        self.svn_root = self.base_root

        self._busy = False
        self._paths_by_index = []
        self._wc_root_by_index = []
        self._wc_roots = []
        self._resolve_visible = False

        self.root.title("Safe SVN Resolver")
        self.root.geometry("980x640")

        self._build_ui()
        self._bring_to_front()
        self._log(f"当前目录: {self.base_root}")
        # 启动时先尝试解析 svn.exe（不强制，避免用户只是想先打开窗口看看）
        svn_exe = get_svn_exe_or_none()
        if svn_exe is not None:
            self._log(f"svn.exe: {svn_exe}")
        else:
            self._log("svn.exe: （未检测到，点击按钮时会提示选择/安装）")
        svn_root = find_nearest_svn_root(self.base_root)
        if svn_root is not None:
            self.svn_root = svn_root
            self._log(f"SVN 根目录: {self.svn_root}")
        else:
            self._log("SVN 根目录: （未检测到，扫描冲突需在 SVN 工作副本内运行）")

    def _build_ui(self):
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill="both", expand=True)

        top = ttk.Frame(frm)
        top.pack(fill="x")

        self.btn_scan = ttk.Button(top, text="1. 立即扫描冲突", command=self.on_scan)
        self.btn_scan.pack(side="left")

        self.btn_update_all = ttk.Button(top, text="拉取全部svn库", command=self.on_update_all)
        self.btn_update_all.pack(side="left", padx=(14, 0))

        self.btn_resolve = ttk.Button(
            top,
            text="3. 一键解决冲突（使用他人版本）",
            command=self.on_resolve_all,
            state="disabled",
        )
        # 扫描结束且发现冲突时再显示
        # self.btn_resolve.pack(side="left", padx=(14, 0))

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(top, textvariable=self.status_var).pack(side="right")

        mid = ttk.Frame(frm)
        mid.pack(fill="both", expand=True, pady=(10, 0))

        ttk.Label(mid, text="冲突文件列表（双击可在 Explorer 中定位）：").pack(anchor="w")

        list_frame = ttk.Frame(mid)
        list_frame.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE)
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", self.on_open_in_explorer)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        ttk.Label(frm, text="日志：").pack(anchor="w", pady=(10, 0))
        self.txt_log = tk.Text(frm, height=10, wrap="word")
        self.txt_log.pack(fill="both", expand=False)
        self.txt_log.configure(state="disabled")

    def _set_busy(self, busy: bool, status: str | None = None):
        self._busy = busy
        if status is not None:
            self.status_var.set(status)
        self.btn_scan.configure(state=("disabled" if busy else "normal"))
        self.btn_update_all.configure(state=("disabled" if busy else "normal"))
        if self._resolve_visible:
            self.btn_resolve.configure(state=("disabled" if busy or not self._paths_by_index else "normal"))

    def _bring_to_front(self):
        """
        尽量把窗口提到前台（Windows 下有时会在后台打开导致“看不见”）。
        """
        try:
            self.root.update_idletasks()
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            # 临时置顶再还原，避免一直 topmost
            self.root.attributes("-topmost", True)
            self.root.after(300, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

    def _log(self, msg: str):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", msg.rstrip() + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _set_conflict_list(self, paths):
        self.listbox.delete(0, "end")
        self._paths_by_index = []
        self._wc_root_by_index = []
        for item in paths:
            wc_root = None
            p = item
            if isinstance(item, tuple) and len(item) == 2:
                wc_root, p = item
            p = Path(p).resolve()
            wc_root = Path(wc_root).resolve() if wc_root is not None else self.svn_root

            try:
                wc_rel = str(wc_root.relative_to(self.base_root))
            except Exception:
                wc_rel = str(wc_root)

            try:
                rel = str(p.relative_to(wc_root))
            except Exception:
                rel = str(p)

            display = f"{wc_rel} :: {rel}"
            self.listbox.insert("end", display)
            self._paths_by_index.append(p)
            self._wc_root_by_index.append(wc_root)
        if self._resolve_visible and not self._busy:
            self.btn_resolve.configure(state=("normal" if self._paths_by_index else "disabled"))

    def _start_scan_all(self, wc_roots=None, *, reason: str = ""):
        if self._busy:
            return
        if not ensure_svn_exe_gui(self.root):
            return

        self._set_busy(True, "扫描中...")
        if reason:
            self._log(f"[SCAN-ALL] {reason}")
        self._log(f"[SCAN-ALL] 扫描起点: {self.base_root}")

        def worker():
            wcs = list(wc_roots) if wc_roots is not None else find_svn_working_copies(self.base_root)
            # 保存给“解决冲突/复扫”使用
            self._wc_roots = [Path(x).resolve() for x in wcs]

            items = []
            for i, wc in enumerate(self._wc_roots, 1):
                self.root.after(0, lambda i=i, wc=wc: self.status_var.set(f"扫描 {i}/{len(self._wc_roots)}: {wc}"))
                conflicts = find_all_svn_conflicts_recursive(str(wc))
                for cf in conflicts:
                    items.append((wc, Path(cf).resolve()))
            self.root.after(0, lambda: self._on_scan_all_done(items))

        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_all_done(self, items):
        self._set_busy(False, "就绪")
        self._set_conflict_list(items)
        if not items:
            self._log("[OK] 未发现冲突（所有SVN库）")
            if self._resolve_visible:
                try:
                    self.btn_resolve.pack_forget()
                except Exception:
                    pass
                self._resolve_visible = False
        else:
            self._log(f"发现 {len(items)} 个冲突文件（所有SVN库）")
            if not self._resolve_visible:
                self.btn_resolve.pack(side="left", padx=(14, 0))
                self._resolve_visible = True
            self.btn_resolve.configure(state=("normal" if self._paths_by_index else "disabled"))
            self._bring_to_front()

    def on_open_in_explorer(self, _evt=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._paths_by_index):
            return
        target = self._paths_by_index[idx]
        # Explorer 选中文件
        subprocess.run(["explorer", "/select,", str(target)], shell=False)

    def on_scan(self):
        self._start_scan_all(reason="手动扫描冲突（所有SVN库）")

    def on_update_all(self):
        if self._busy:
            return
        if not ensure_svn_exe_gui(self.root):
            return

        ok = messagebox.askokcancel(
            "拉取全部svn库",
            f"将在以下目录下递归查找 SVN 工作副本，并逐个执行 svn update：\n\n{self.base_root}\n\n是否继续？",
        )
        if not ok:
            return

        self._set_busy(True, "查找SVN库...")
        self._log(f"[UPDATE-ALL] 扫描 SVN 工作副本: {self.base_root}")

        def ui_log(msg: str):
            self.root.after(0, lambda: self._log(msg))

        def ui_status(msg: str):
            self.root.after(0, lambda: self.status_var.set(msg))

        def worker():
            wcs = find_svn_working_copies(self.base_root)
            ui_log(f"[UPDATE-ALL] 找到 {len(wcs)} 个 SVN 工作副本根目录")
            ui_log("[UPDATE-ALL] 将更新以下目录（工作副本根目录）：")
            display_paths = []
            for wc in wcs:
                try:
                    display_paths.append(str(wc.relative_to(self.base_root)))
                except Exception:
                    display_paths.append(str(wc))
            for dp in display_paths[:200]:
                ui_log(f"  - {dp}")
            if len(display_paths) > 200:
                ui_log(f"  ... 还有 {len(display_paths) - 200} 个未展开")

            results = []
            conflict_hint_roots: list[Path] = []
            for i, wc in enumerate(wcs, 1):
                ui_status(f"更新 {i}/{len(wcs)}: {wc}")
                ui_log(f"[UPDATE-ALL] svn update: {wc}")
                rc, out, err = run_svn_update(wc)
                results.append((wc, rc, out, err))
                if out.strip():
                    ui_log(out.rstrip())
                if err.strip():
                    ui_log("[stderr] " + err.rstrip())
                if rc != 0 or svn_update_output_has_conflict(out, err):
                    conflict_hint_roots.append(Path(wc).resolve())

            self.root.after(0, lambda: self._on_update_all_done(results, conflict_hint_roots))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_all_done(self, results, conflict_hint_roots=None):
        self._set_busy(False, "就绪")
        if not results:
            self._log("[UPDATE-ALL] 未找到任何 SVN 工作副本（或已取消/无结果）")
            messagebox.showinfo("完成", "未找到任何 SVN 工作副本。")
            return

        ok_cnt = sum(1 for _wc, rc, _out, _err in results if rc == 0)
        fail = [(wc, rc) for wc, rc, _out, _err in results if rc != 0]

        self._log(f"[UPDATE-ALL] 完成：成功 {ok_cnt}/{len(results)}")
        self._log("[UPDATE-ALL] 实际更新过的目录（工作副本根目录）：")
        for wc, rc, _out, _err in results:
            try:
                dp = str(wc.relative_to(self.base_root))
            except Exception:
                dp = str(wc)
            tag = "OK" if rc == 0 else f"FAIL(rc={rc})"
            self._log(f"  - [{tag}] {dp}")
        if fail:
            self._log("[UPDATE-ALL] 失败列表：")
            for wc, rc in fail[:20]:
                self._log(f"  - rc={rc}: {wc}")
            if len(fail) > 20:
                self._log(f"  ... 还有 {len(fail) - 20} 个未显示")
            messagebox.showwarning(
                "完成（有失败）",
                f"成功 {ok_cnt}/{len(results)}，有 {len(fail)} 个目录更新失败，请看日志。",
            )
        else:
            messagebox.showinfo("完成", f"已完成全部更新：{ok_cnt}/{len(results)}")

        # 拉取完成后：优化——仅对“update 输出提示冲突/更新失败”的库做自动冲突扫描
        hinted = [Path(x).resolve() for x in (conflict_hint_roots or [])]
        hinted = list(dict.fromkeys(hinted))  # 去重保序
        if hinted:
            self._log(f"[SCAN-ALL] update 输出提示需要扫描的库：{len(hinted)} 个")
            for wc in hinted[:200]:
                try:
                    dp = str(wc.relative_to(self.base_root))
                except Exception:
                    dp = str(wc)
                self._log(f"  - {dp}")
            if len(hinted) > 200:
                self._log(f"  ... 还有 {len(hinted) - 200} 个未展开")
            self._start_scan_all(hinted, reason="拉取完成后自动扫描冲突（仅扫描 update 提示的库）")
        else:
            self._log("[SCAN-ALL] update 输出未提示冲突/失败：已跳过自动扫描（可手动点击“立即扫描冲突”确认）")
            self._set_conflict_list([])
            if self._resolve_visible:
                try:
                    self.btn_resolve.pack_forget()
                except Exception:
                    pass
                self._resolve_visible = False

    def on_resolve_all(self):
        if self._busy:
            return
        if not ensure_svn_exe_gui(self.root):
            return
        if not self._paths_by_index:
            messagebox.showinfo("无冲突", "当前列表为空：请先点击“1. 立即扫描冲突”。")
            return

        ok = messagebox.askokcancel(
            "一键解决冲突",
            f"将对列表中的 {len(self._paths_by_index)} 个冲突执行自动解决。\n\n"
            "策略：theirs-full → theirs-conflict → working\n\n"
            "是否继续？",
        )
        if not ok:
            return

        self._set_busy(True, "解决冲突中...")
        self._log("开始一键解决冲突（所有SVN库，使用他人版本）...")
        items = list(zip(self._wc_root_by_index, self._paths_by_index))
        wc_roots = list(self._wc_roots) if self._wc_roots else list({wc for wc, _p in items})

        def worker():
            success, total, failures = resolve_conflicts_grouped(items)
            # 解决后：对所有库复扫
            remain_items = []
            for wc in wc_roots:
                remain = find_all_svn_conflicts_recursive(str(wc))
                for cf in remain:
                    remain_items.append((wc, Path(cf).resolve()))
            self.root.after(
                0,
                lambda: self._on_resolve_all_done(success, total, failures, remain_items),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_resolve_all_done(self, success, total, failures, remain_items):
        self._set_busy(False, "就绪")
        self._log(f"一键 resolve 完成：成功 {success}/{total}")
        if failures:
            self._log("以下路径 resolve 失败：")
            for p, e in failures[:20]:
                self._log(f"  - {p}: {e}")
            if len(failures) > 20:
                self._log(f"  ... 还有 {len(failures) - 20} 条未显示")

        self._set_conflict_list(remain_items)
        if remain_items:
            self.status_var.set("仍有冲突，需要人工处理")
            messagebox.showwarning("仍有冲突", f"自动处理后仍剩余 {len(remain_items)} 个冲突，请人工处理。")
        else:
            self.status_var.set("冲突已解决")
            messagebox.showinfo("完成", "冲突已全部解决（未检测到剩余冲突）。")


def cli_main():
    ensure_svn_root_or_exit()
    try:
        ensure_svn_exe_or_raise()
    except FileNotFoundError as e:
        print(str(e))
        return False

    print("开始递归扫描SVN冲突文件...")
    print(f"根目录: {Path('.').resolve()}")
    print("-" * 50)

    conflicts = find_all_svn_conflicts_recursive()

    if not conflicts:
        print("[OK] 未发现任何冲突文件")
        return True

    print(f"\n总计发现 {len(conflicts)} 个冲突文件:")
    for i, cf in enumerate(conflicts, 1):
        print(f"  {i:3d}. {cf}")

    # 询问解决
    response = input("\n是否解决所有冲突? (y/N): ").strip().lower()
    if response not in ("y", "yes"):
        print("操作已取消")
        return False

    # 解决冲突
    success = 0
    for cf in conflicts:
        try:
            display = os.path.relpath(str(cf), str(Path(".").resolve()))
        except Exception:
            display = str(cf)
        print(f"解决: {display}...", end=" ")
        try:
            # 不同类型冲突可接受的策略不同（例如属性冲突/树冲突无法用 theirs-full）
            accept_candidates = [
                "theirs-full",  # 文本冲突：直接接受对方版本
                "theirs-conflict",  # 属性/部分冲突：接受对方冲突块
                "working",  # 树冲突等：标记为已处理（通常需你先手动调整到想要的状态）
            ]

            last_result = None
            used_accept = None
            for accept in accept_candidates:
                result = _run_svn(["resolve", "--accept", accept, str(cf)], cwd=Path(".").resolve())
                last_result = result
                if result.returncode == 0:
                    used_accept = accept
                    break

            if used_accept is not None:
                print(f"[OK] 成功 ({used_accept})")
                success += 1
            else:
                print("[FAIL] 失败")
                err = ((last_result.stderr if last_result else "") or "").strip()
                if err:
                    print(f"  错误: {err}")
        except Exception as e:
            print(f"[ERROR] 异常: {e}")

    print(f"\n解决完成! 成功: {success}/{len(conflicts)}")
    return success == len(conflicts)


def gui_main():
    print(f"[GUI] {time.strftime('%H:%M:%S')} 启动 GUI...（如无窗口弹出，请确认未使用 --cli）")
    root = tk.Tk()
    _app = SafesvnResolverApp(root)
    root.mainloop()


if __name__ == "__main__":
    # 默认启动 GUI；如需原命令行行为：python SafesvnResolver.py --cli
    if any(a in ("--cli", "-c") for a in sys.argv[1:]):
        cli_main()
    else:
        gui_main()

