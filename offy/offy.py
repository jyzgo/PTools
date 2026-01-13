#!/usr/bin/env python3
"""
Git 离线同步工具
- export(): 从当前分支导出未推送的提交为 .patch 文件（用于离线机器）
- import_patches(): 应用 patches/ 目录下的所有 .patch 文件（用于在线机器）
"""

import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

PATCH_DIR = Path("patches")
PATCH_PATTERN = "patch*.txt"  # 文件名必须以 patch 开头，扩展名为 .txt


def run_git(args, check=True):
    """运行 git 命令并返回 stdout"""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=Path.cwd(),
    )
    if check and result.returncode != 0:
        print(f"❌ Git error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def get_current_branch():
    """获取当前分支名"""
    return run_git(["branch", "--show-current"])


def export():
    """导出未推送的提交为 patch 文件"""
    branch = get_current_branch()
    if not branch:
        print("❌ 不在任何 Git 分支上！", file=sys.stderr)
        sys.exit(1)

    # 获取远程跟踪分支（如 origin/main）
    remote_ref = f"origin/{branch}"

    # 检查远程分支是否存在
    try:
        run_git(["rev-parse", "--verify", remote_ref], check=True)
        base_commit = remote_ref
    except SystemExit:
        # 如果远程分支不存在（比如新仓库），从初始提交开始
        print(f"⚠️ 远程分支 {remote_ref} 不存在，将导出全部提交")
        base_commit = run_git(["rev-list", "--max-parents=0", "HEAD"])  # 初始提交

    # 计算本地独有的提交
    try:
        commits = run_git(["log", "--oneline", f"{base_commit}..HEAD"])
    except Exception:
        commits = ""

    if not commits:
        print("✅ 没有新的提交需要导出。")
        return

    print("即将导出的提交：")
    print(commits)

    # 创建 patches 目录
    PATCH_DIR.mkdir(exist_ok=True)

    # 清空旧的 patch*.txt 文件（可选，避免混淆）
    for f in PATCH_DIR.glob(PATCH_PATTERN):
        f.unlink()

    # 生成 patch 文件到临时目录
    temp_dir = PATCH_DIR / "temp"
    temp_dir.mkdir(exist_ok=True)

    cmd = ["format-patch", "-o", str(temp_dir), f"{base_commit}..HEAD"]
    result = subprocess.run(
        ["git"] + cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        print(f"❌ 导出失败: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    # 将生成的 .patch 文件重命名为 patch*.txt
    temp_patches = list(temp_dir.glob("*.patch"))
    renamed_count = 0
    for temp_patch in sorted(temp_patches):
        # 提取序号，例如 0001-xxx.patch -> patch0001.txt
        new_name = f"patch{temp_patch.stem.split('-')[0]}.txt"
        new_path = PATCH_DIR / new_name
        temp_patch.rename(new_path)
        renamed_count += 1
        print(f"  ✓ {new_name}")

    # 删除临时目录
    temp_dir.rmdir()

    print(f"\n✅ 成功导出 {renamed_count} 个补丁到 {PATCH_DIR}/")


def import_patches():
    """应用 patches/ 目录下的所有 patch*.txt 文件"""
    if not PATCH_DIR.exists():
        print(f"❌ 目录 {PATCH_DIR}/ 不存在，请先放入 {PATCH_PATTERN} 文件", file=sys.stderr)
        sys.exit(1)

    patch_files = sorted(PATCH_DIR.glob(PATCH_PATTERN))
    if not patch_files:
        print(f"✅ {PATCH_DIR}/ 中没有 {PATCH_PATTERN} 文件", file=sys.stderr)
        return

    # 检查是否有未完成的 git am 操作，如果有就清理
    rebase_dir = Path(".git/rebase-apply")
    if rebase_dir.exists():
        print("⚠️ 检测到未完成的 git am 操作，正在清理...")
        subprocess.run(["git", "am", "--abort"], capture_output=True)
        print("✅ 已清理")

    print(f"发现 {len(patch_files)} 个补丁，准备应用...")
    for patch in patch_files:
        print(f"📦 应用 {patch.name} ...")
        result = subprocess.run(
            ["git", "am", str(patch)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            print(f"❌ 应用失败: {result.stderr}", file=sys.stderr)
            print("💡 尝试修复冲突后运行: git am --continue")
            sys.exit(1)

    print(f"\n✅ 所有 {len(patch_files)} 个补丁已成功应用！")
    print("现在你可以运行 `git push` 推送到远程。")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("export", "import"):
        print("用法:")
        print(f"  python {Path(__file__).name} export   # 在离线机器上导出改动")
        print(f"  python {Path(__file__).name} import   # 在在线机器上导入改动")
        sys.exit(1)

    action = sys.argv[1]
    if action == "export":
        export()
    elif action == "import":
        import_patches()


if __name__ == "__main__":
    main()

