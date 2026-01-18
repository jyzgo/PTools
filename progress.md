## Session log
### 2026-01-13
- 识别到两个 `PTools.py`：根目录入口与 `ptools/` 下的 Tkinter UI 实现。
- 下一步：改为递归发现脚本并在界面展示与调用。
- 已完成：递归扫描展示 + 修复入口导入 + 运行时 cwd 改为脚本目录。
- 已完成：递归扫描同时支持 `.bat`，运行时自动用 `cmd.exe /c` 执行。

# Progress / 进展记录

## 2026-01-10
- 创建：`task_plan.md`、`findings.md`、`progress.md`
- 确认：工程目录当前为空
- 新增：`PTools.py`（tkinter GUI：路径栏 + 参数栏 + Run + 脚本按钮网格 + Refresh）
- 校验：`python -m py_compile PTools.py` 通过
- 冒烟：`_list_sibling_scripts()` 在空目录返回 0（符合预期）
- 优化：扫描到脚本时默认自动选中第一个

## 2026-01-13
- 结构调整：为每个功能创建独立文件夹 `features/<功能>/`
- 新增：
  - `features/ptools/PTools.py`
  - `features/safesvn_resolver/SafesvnResolver.py`
  - `features/offy/offy.py`
  - `features/__init__.py` 及各子包 `__init__.py`
- 根目录脚本改为入口薄封装：`PTools.py` / `SafesvnResolver.py` / `offy.py`
- 校验：`python -m py_compile` 对全部入口与模块通过

## 2026-01-17
- 计划：新增视频切割工具 `video_split/`（按份数或时长切割，输出前缀 `001_002_...`）。
- 已完成：更新 `task_plan.md/findings.md/progress.md` 写入本次目标与约束。
- 已完成：新增 `video_split/video_split.py` 与 `video_split/README.md`
- 已完成：冒烟 `python video_split/video_split.py --help`、`python -m py_compile video_split/video_split.py`
