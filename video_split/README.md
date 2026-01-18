## video_split

输入一个视频文件路径，把它按 **份数** 或 **时长** 切割成多个小文件，输出文件名前缀自动加 `001_002_...`。

### 前置依赖

- 需要已安装 `ffmpeg`（同时包含 `ffprobe`），并确保命令行可直接运行：
  - `ffmpeg -version`
  - `ffprobe -version`

### 用法

#### 按份数切割（精确输出 N 份）

```bash
python video_split.py "D:\path\to\input.mp4" --count 5
```

默认输出目录：`<输入文件所在目录>\<输入文件名>_split\`

输出示例：

- `001_input.mp4`
- `002_input.mp4`
- ...

#### 按时长切割（每段固定时长，最后一段可能更短）

```bash
python video_split.py "D:\path\to\input.mp4" --duration 10
python video_split.py "D:\path\to\input.mp4" --duration 00:00:10
```

#### 指定起始编号（例如从 017 开始）

```bash
python video_split.py "D:\path\to\input.mp4" --count 5 --startIndex 017
```

#### 指定输出目录

```bash
python video_split.py "D:\path\to\input.mp4" --count 3 --output-dir "D:\out\clips"
```

#### 在 PTools GUI 里使用（推荐）

- **Path**：填视频路径
- **Arg1**：填 `--count 5` 或 `--duration 10`
- **Arg2**：可填 `--startIndex 017`（可选）
- 然后点 Run

### 注意事项

- 默认使用 `-c copy` 直接切割（速度快、不重新编码）；但如果你发现切点处画面/音频异常，可能是因为非关键帧切割导致，可考虑后续加“重编码模式”（若你需要我可以补上）。

