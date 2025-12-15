# OMRChecker 桌面 GUI 使用指南

本仓库在原有 OMRChecker 引擎基础上提供了一个桌面端 GUI（PySide6），用于创建/管理项目、可视化编辑模板、批量识别并导出 CSV；同时仍支持命令行（CLI）方式运行。

![示例输出](docs/assets/colored_output.jpg)

快速定位：
- [快速开始（推荐）](#quickstart)
- [项目结构（GUI/CLI 通用）](#project-structure)
- [GUI 使用说明](#gui-guide)
- [CLI 用法（无 GUI）](#cli-guide)
- [配置文件速览](#configs)
- [常见问题（FAQ）](#faq)

<a id="quickstart"></a>
## 快速开始（推荐）

### 运行环境

- Python：`3.12+`（见 `.python-version` 与 `pyproject.toml`）
- 平台：Windows/macOS/Linux 均可（示例命令以 PowerShell 为主）

### 安装依赖

方式 A：使用 `uv`（仓库已包含 `uv.lock`）

```powershell
uv sync
```

方式 B：使用 `pip`（建议虚拟环境）

```powershell
python -m venv .venv
# Windows:
.\.venv\Scripts\python -m pip install -r requirements.txt
# macOS/Linux:
./.venv/bin/python -m pip install -r requirements.txt
```

### 启动 GUI

在仓库根目录执行任意一种方式即可：

```powershell
python main.py
```

```powershell
python -m omr_gui.app
```

```powershell
uv run python main.py
```

### 3 分钟体验样例（samples/test）

1. 启动 GUI：`python main.py`
2. 菜单 `File -> New Project`，选择 `samples/test`（或先复制一份该目录再选择，避免覆盖样例文件）
3. 点击 `Run OMR`，完成后在 `Results` 标签页查看 CSV

<a id="project-structure"></a>
## 项目结构（GUI/CLI 通用）

GUI 默认围绕“项目目录”组织文件，建议采用如下结构：

```text
<项目目录>/
  config/
    template.json
    config.json          # 可选（不提供则使用默认参数）
    evaluation.json      # 可选（用于评分/解析答案）
    omr_marker.jpg       # 可选（使用 CropOnMarkers 时需要）
  input/                 # 放置待识别图片（png/jpg/jpeg，可含子目录）
  output/                # 识别输出（CSV、标注图等）
  *.omrproj              # GUI 项目文件（JSON）
```

提示：仓库内置了可直接体验的样例目录 `samples/test/`，结构完整（含 `config/` 与 `input/`）。

<a id="gui-guide"></a>
## GUI 使用说明

### 1) 新建/打开项目（.omrproj）

- 新建：菜单 `File -> New Project`，选择一个项目目录；GUI 会自动创建 `config/ input/ output/` 并生成 `<项目名>.omrproj`。
- 打开：菜单 `File -> Open Project`，选择已有 `.omrproj`。
- `.omrproj` 本质是 JSON，保存的是“绝对路径”；拷贝到其他机器后如果路径失效，建议在新机器上重新 `New Project` 生成。

### 2) 运行识别与查看结果

- `Run OMR`：对 `input/` 中的图片批量识别，并实时输出日志。
- `View Latest Results`：加载 `output/` 下最新生成的 CSV 并以表格展示。

说明：GUI 会通过环境变量将 `template.json/config.json/evaluation.json` 传给引擎（分别对应 `OMR_TEMPLATE_PATH/OMR_CONFIG_PATH/OMR_EVALUATION_PATH`），无需把配置文件拷贝到 `input/`。

### 3) 模板可视化编辑器（Template Editor）

入口：菜单 `Tools -> Open Template Editor`。

- 在画布上绘制/移动/缩放区域块（Field Block）。
- 编辑块属性：题型（INT/MCQ4/MCQ5/BOOLEAN）、标签、起点坐标、`labelsGap`、`bubblesGap` 等。
- 支持加载背景图用于对齐；保存后写回引擎兼容的 `template.json`。

### 4) 学号答题卡生成器（ID Sheet Generator）

入口：菜单 `Tools -> Open ID Sheet Generator`。

- 生成内容：答题卡 PNG、`template.json`、`config.json`，并自动准备 `omr_marker.jpg`（用于定位/裁切）。
- 输出目录会按“项目结构”组织（`config/ input/ output/`），生成后可直接作为一个项目目录使用。

<a id="cli-guide"></a>
## CLI 用法（无 GUI）

CLI 适合批处理/集成流水线。以下命令在仓库根目录执行：

```powershell
python main.py --cli -i .\inputs -o .\outputs
```

常用参数：

- `-i/--inputDir`：输入目录（默认 `inputs`，支持多个目录：`-i dir1 dir2`）
- `-o/--outputDir`：输出目录（默认 `outputs`）
- `-a/--autoAlign`：实验性自动对齐（也可在 `config.json` 的 `alignment_params.auto_align` 配置）
- `-l/--setLayout`：布局调试模式（用于反复调整模板）

高级：直接指定配置文件路径（GUI 同样使用这一机制）

```powershell
$env:OMR_TEMPLATE_PATH="C:\\path\\to\\template.json"
$env:OMR_CONFIG_PATH="C:\\path\\to\\config.json"
$env:OMR_EVALUATION_PATH="C:\\path\\to\\evaluation.json"
python main.py --cli -i .\\input -o .\\output
```

<a id="configs"></a>
## 配置文件速览

<details>
<summary><b>template.json（模板/版式）</b></summary>

- `pageDimensions`：处理时将整页 resize 到的尺寸 `[width, height]`
- `bubbleDimensions`：单个气泡区域大小 `[width, height]`
- `preProcessors`：预处理链（如 `CropPage`、`CropOnMarkers`、`FeatureBasedAlignment`）
- `fieldBlocks`：字段块集合（每块包含 `origin`、`labelsGap`、`bubblesGap`、`fieldLabels`、`fieldType` 等）
- `customLabels` / `outputColumns`：输出列的组合与顺序控制

</details>

<details>
<summary><b>config.json（运行参数）</b></summary>

- `dimensions.processing_*`：内部处理分辨率（影响速度/精度）
- `outputs.show_image_level`：调试可视化级别（越大显示越多、速度越慢）
- `alignment_params.auto_align`：是否启用自动对齐

</details>

<details>
<summary><b>evaluation.json（评分/答案解析，可选）</b></summary>

- 支持从 CSV 读取答案（见样例 `samples/answer-key/using-csv/`）
- `marking_schemes` 可定义对/错/空的计分规则

</details>

<a id="faq"></a>
## 常见问题（FAQ）

- GUI 无法启动：确认在仓库根目录运行，或使用 `python -m omr_gui.app`；并检查是否已安装 `PySide6`（`pip install -r requirements.txt`）。
- 找不到输出 CSV：确认 `input/` 中存在 `png/jpg/jpeg` 图片；查看 GUI 日志或 CLI 输出中的报错信息。
- 识别偏移/裁切不稳：优先在模板中启用 `CropOnMarkers` 并确保 `omr_marker.jpg` 可用；其次再考虑开启 `autoAlign`。

## 更多资料

- 英文版项目介绍与更完整的背景说明：`README.md`
- 示例与样例配置：`samples/`

## 开发与贡献

- 引擎代码：`src/`；GUI 代码：`omr_gui/`
- 运行测试：`pytest`
- 贡献指南：`CONTRIBUTING.md`
