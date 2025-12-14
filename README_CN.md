# OMR GUI 使用说明

本项目在原有 OMRChecker 引擎外增加了一个桌面 GUI，便于创建项目、运行识别、编辑模板以及生成学号答题卡。依赖 Python 3.10+ 与 PySide6、Pillow（已写入 requirements）。

## 安装

1. 进入仓库根目录：
   ```powershell
   cd C:\Users\13395\Documents\Code\Project\OMRChecker
   ```
2. 安装依赖（建议在虚拟环境中）：
   ```powershell
   .\.venv\Scripts\python -m pip install -r requirements.txt
   ```

## 启动 GUI

从仓库根目录运行：
```powershell
.\.venv\Scripts\python -m omr_gui.app
```
或使用 uv：
```powershell
uv run -m omr_gui.app
```

> 若从其它目录启动，请先设置 `PYTHONPATH` 指向仓库根：
> ```powershell
> $env:PYTHONPATH="C:\Users\13395\Documents\Code\Project\OMRChecker"
> .\.venv\Scripts\python -m omr_gui.app
> ```

## 主窗口（项目管理与运行）

- 推荐项目结构：  
  ```
  <项目根>/
    config/
      template.json
      config.json
      evaluation.json   # 可选
    input/
    output/
  ```
- 只需选择 “Project Root” 即可自动填入 input/output/config 路径；仍可手动调整。
- “Run OMR”：调用 OMRChecker 处理 input 目录，并在日志页实时显示 stdout/stderr。运行前会把 config/template/evaluation 拷贝到 input 目录，方便 OMRChecker 自动识别。完成后自动加载最新 CSV。
- “View Latest Results”：从 output 目录选择最新 CSV 并在表格页展示。
- 菜单 File：新建/打开/保存项目（保存为 `.omrproj`）。
- Tools：打开模板编辑器、学号答题卡生成器。

## 模板可视化编辑器

打开方式：主窗口 Tools -> Open Template Editor。

功能：
- Ctrl+拖拽在画布上绘制新块；块可拖动、右下角缩放。
- 右侧“Block Properties”编辑字段：类型（INT/MCQ4/MCQ5/BOOLEAN）、标签前缀+数量、原点坐标、labels_gap、bubbles_gap。
- “Custom Labels”页：新增/删除组合列，并勾选成员标签；输出列会随组合列更新。
- 菜单 File：Open Template / Save / Save As；可加载背景图方便对齐。
- Save 会写回 OMRChecker 兼容的 template.json。

## 学号答题卡生成器

打开方式：主窗口 Tools -> Open ID Sheet Generator。

步骤：
1. 设置学号位数、页面宽高、边距、气泡半径、行距/列距；可勾选“Include Class Field”并设置班级位数。
2. 选择输出目录与文件前缀（Base name）。
3. 点击 Generate，生成：
   - PNG 答题卡
   - 对应 template.json
   - 默认 config.json（尺寸与页面匹配）

生成后弹窗显示路径，可再用模板编辑器打开校验。

## 典型流程

1. 用 ID 生成器生成学号卡（得到 PNG/模板/config）。
2. 在项目中填写这些路径，指定输入扫描目录和输出目录。
3. 运行 “Run OMR”，查看日志与结果表格。
4. 如需调整模板，打开模板编辑器修改后保存，再次运行。

## 常见问题

- `ModuleNotFoundError: omr_gui`：请在仓库根目录运行，或设置 `PYTHONPATH`。
- `ImportError: PySide6`：未安装依赖，请执行 `pip install -r requirements.txt`。
- 无 CSV 输出：检查输入目录是否有图片，或查看日志中的 OMRChecker 错误信息。***
