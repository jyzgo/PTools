## Key findings
- `C:\Tools\pythonTools\PTools.py` 是入口转发脚本，当前引用 `features.ptools.PTools`（需要核对是否真实存在）。
- 实际 Tkinter UI 实现在 `C:\Tools\pythonTools\ptools\PTools.py`。
- 当前脚本发现逻辑：只扫描 `scripts_dir` 的同级 `*.py`（非递归）。
- 当前运行逻辑：Windows 下默认 `CREATE_NEW_CONSOLE` 直接 `Popen` 启动，不在界面捕获输出。

## Changes made (this session)
- 根目录入口 `PTools.py` 已改为导入 `ptools.PTools`（不再依赖不存在的 `features.*`）。
- 新增 `ptools/__init__.py` 使其可被正常 import。
- `ptools/PTools.py` 的脚本发现逻辑改为递归扫描 `scripts_dir`（`rglob("*.py")`），并过滤常见无关目录。
- 脚本展示名称改为相对路径（无后缀），避免不同目录重名脚本冲突。
- 运行脚本时的 `cwd` 改为脚本所在目录（`item.path.parent`），更符合工具脚本常见用法。
- 已支持 `*.bat`：扫描时会同时发现 `.py/.bat`，运行 `.bat` 时使用 `cmd.exe /c <script> ...`。

# Findings / 发现

## 2026-01-10
- `C:\Tools\pythonTools` 当前目录为空（未发现任何文件）。
- 因此 `PTools.py` 初次运行时脚本按钮区可能为空；后续同级新增脚本后应能自动出现（并提供刷新能力更友好）。
- `PTools.py` 的执行策略：`python <script.py> [Path] [Args...]`，其中 `Path` 来自顶部地址栏（非必填），`Args` 来自参数框（支持引号分割）。

## 2026-01-13
- 为满足“每个功能一个文件夹”，采用 `features/<功能名>/` 承载实现代码；根目录保留同名入口脚本以保证兼容性。
- `PTools` 仍按“根目录同级 .py”发现脚本，因此入口脚本继续放在根目录，功能实现下沉到 `features/`。

