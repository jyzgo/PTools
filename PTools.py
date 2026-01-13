from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

from ptools.PTools import main as _main


def main() -> int:
    # 默认扫描“脚本入口文件所在目录”（工程根目录）下的所有 .py（含子文件夹）。
    return _main(scripts_dir=Path(__file__).resolve().parent)


if __name__ == "__main__":
    raise SystemExit(main())

