## Goal
把指定目录（默认工程根目录）下的所有 Python 脚本（含子文件夹）以“工具入口”展示在 `PTools` 界面中，并支持一键调用运行。

## Constraints / Principles
- 最小化改动，沿用现有 Tkinter UI（`ptools/PTools.py`）。
- 默认扫描工程根目录（`C:\Tools\pythonTools`）下的所有 `*.py`（递归）。
- 需要过滤无意义目录/文件（如 `__pycache__`、虚拟环境等）。
- 运行脚本使用当前 Python 解释器（`sys.executable`），并允许传参（保留现有 Arg1~Arg3）。

## Phases
### Phase 1 — Baseline understanding [complete]
- [x] 确认入口文件与 UI 文件关系
- [x] 确认当前脚本扫描策略与运行方式

### Phase 2 — Script discovery (recursive) [complete]
- [x] 递归发现 `scripts_dir` 下的 `*.py`
- [x] 排除自身入口、`__init__.py`、下划线开头、常见无关目录
- [x] 在 UI 中用相对路径展示（避免重名冲突）

### Phase 3 — Invocation UX [complete]
- [x] 选择脚本后可运行
- [x] 运行时在界面显示命令/状态

### Phase 4 — Verify [pending]
- [ ] 本机运行无异常（至少能列出脚本并能启动）

## Errors Encountered
| Error | Attempt | Resolution |
|---|---:|---|
| (none) |  |  |

# PTools 实现计划

## 目标
- 在本工程内新增 `PTools.py`：运行后打开 GUI 主界面。
- 主界面包含：
  - 顶部地址栏（用户粘贴路径）
  - 第二行若干参数输入框，最右侧 `Run` 按钮
  - 底部多排“图标”（以脚本名显示）用于选择同级 `.py` 脚本
  - 支持 `Tab` 在输入框间切换，支持回车执行
- 启动时遍历与 `PTools.py` 同级的 Python 脚本并展示为按钮网格。

## 方案与关键决策
- GUI 框架：使用标准库 `tkinter`（零依赖、跨平台）。
- 执行方式：`sys.executable script.py <path?> <args...>`，使用 `shlex.split` 支持参数中引号。
- 脚本发现：扫描同级目录 `*.py`，排除 `PTools.py`、`__init__.py`、以下划线开头脚本。

## 阶段
### Phase 1 - 工程现状确认（complete）
- 确认目录可读、是否已有脚本

### Phase 2 - GUI 与脚本发现（complete）
- 编写 `PTools.py`：布局、脚本按钮网格、选择高亮、刷新

### Phase 3 - 执行与交互（complete）
- Run / 回车触发执行
- Tab 默认行为验证

### Phase 4 - 本地运行验证与收尾（in_progress）
- 已做：`py_compile` 语法校验、脚本扫描函数冒烟测试
- 待做：在带图形界面的环境实际运行 `python PTools.py`（验证窗口、Tab 切换、回车运行）

## Errors Encountered
| Error | Attempt | Resolution |
|------|---------|------------|
| 目录工具列举超时/空结果 | 1 | 改用 PowerShell `Get-ChildItem` 验证目录为空 |
| PowerShell 复杂引号/括号导致命令解析失败 | 1 | 改为直接运行 `python -c "..."` 进行冒烟测试 |

---

# 工程结构调整计划：每个功能一个文件夹（2026-01-13）

## 目标
- 让每个“功能脚本”有独立文件夹承载实现代码，便于扩展与维护。
- 保持原有使用方式不变：仍可在根目录运行 `python PTools.py` / `python SafesvnResolver.py` / `python offy.py`。

## 方案与关键决策
- 采用“根目录入口脚本 + features/<功能>/ 实现”结构。
- 入口脚本只负责转发调用，避免破坏 `PTools` 的“扫描同级脚本”逻辑。

## 阶段
### Phase A - 功能识别（complete）
- 识别现有功能入口：`PTools.py`、`SafesvnResolver.py`、`offy.py`。

### Phase B - 迁移实现到功能文件夹（complete）
- 新增：`features/ptools/PTools.py`
- 新增：`features/safesvn_resolver/SafesvnResolver.py`
- 新增：`features/offy/offy.py`

### Phase C - 根目录入口脚本薄封装（complete）
- `PTools.py`：转发到 `features.ptools.PTools.main(scripts_dir=<工程根>)`
- `SafesvnResolver.py`：保持 `--cli/-c` 行为不变
- `offy.py`：保持原 CLI 参数行为不变

### Phase D - 校验与收尾（complete）
- `python -m py_compile` 对全部入口与模块通过


