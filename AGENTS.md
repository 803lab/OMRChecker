### Agent Spec: OMR GUI + Template Editor + ID Sheet Generator

Goal

Implement a modular Python desktop application that provides:

1. A GUI to manage OMR projects and run the existing OMRChecker engine (already available as a separate repo).
2. A visual template editor that lets users define OMR answer sheet regions directly on top of an image and export OMRChecker-compatible `template.json`.
3. An ID sheet generator: given the number of student ID digits, generate a printable answer sheet (image/PDF) and its corresponding `template.json`.

OMRChecker itself must not be modified: treat it as an external dependency.


#### 1. Tech stack and constraints

* Language: Python 3.10+
* GUI toolkit: PySide6
* Layout / graphics:

  * Use `QMainWindow`, `QDockWidget`, `QGraphicsView/QGraphicsScene` where appropriate.
* Drawing printable sheets:

  * Use Pillow or reportlab. You may assume Pillow first (PNG output).
* External engine:

  * OMRChecker is available in `external/OMRChecker`.
  * Always call it via `subprocess` from a wrapper class.

Code quality:

* Follow PEP 8.
* Organize code into modules as described in the directory structure.
* Add type hints and minimal docstrings to public methods.
* Avoid global state.

---

#### 2. Project model

Create a `Project` class in `core/project_model.py`:

```python
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class Project:
    name: str
    omrchecker_root: Path
    template_path: Path
    config_path: Optional[Path]
    evaluation_path: Optional[Path]
    input_dir: Path
    output_dir: Path

    @classmethod
    def load(cls, path: Path) -> "Project": ...
    def save(self, path: Path) -> None: ...
```

Project files are stored as JSON with the above fields (convert Paths to strings).

GUI must allow:

* Create new project.
* Open existing project file (`*.omrproj`).
* Edit project settings.

---

#### 3. OMR runner wrapper

In `core/omr_runner.py` implement:

```python
import subprocess
from pathlib import Path
from typing import List

class OmrRunner:
    def __init__(self, omrchecker_root: Path) -> None: ...

    def run(self,
            input_dir: Path,
            template_path: Path | None = None,
            config_path: Path | None = None,
            evaluation_path: Path | None = None,
            log_callback=None) -> Path:
        """
        Run OMRChecker on the given input_dir.
        If log_callback is provided, call it(line: str) for each line of stdout/stderr.
        Return the path to the latest CSV generated in OMRChecker's outputs directory.
        """

    def list_output_csvs(self) -> List[Path]:
        """Return all CSV files currently in the OMRChecker outputs directory."""
```

`run` should:

* Use `subprocess.Popen` with `cwd=omrchecker_root`.
* Build the appropriate command (at minimum: `["python", "main.py", "-i", str(input_dir)]`).
* Stream stdout/stderr line by line to `log_callback` if provided.
* After completion, scan the outputs directory for CSV files and return the most recently modified one.

---

#### 4. Template model & JSON IO

In `core/template_model.py` define data classes:

```python
from dataclasses import dataclass, field
from typing import List, Literal, Optional

FieldType = Literal["INT", "MCQ4", "MCQ5", "BOOLEAN"]

@dataclass
class PageSettings:
    width: int
    height: int

@dataclass
class FieldBlock:
    id: str
    field_type: FieldType
    labels: List[str]
    origin_x: float
    origin_y: float
    labels_gap: float
    bubbles_gap: float

@dataclass
class CustomLabelGroup:
    name: str
    component_labels: List[str]

@dataclass
class TemplateModel:
    page: PageSettings
    field_blocks: List[FieldBlock] = field(default_factory=list)
    custom_labels: List[CustomLabelGroup] = field(default_factory=list)
    output_columns: List[str] = field(default_factory=list)
```

In `core/template_io.py` implement:

* `load_template(path: Path) -> TemplateModel`
* `save_template(model: TemplateModel, path: Path) -> None`

Mapping rules:

* Map OMRChecker `pageDimensions` to `PageSettings`.
* Map OMRChecker `fieldBlocks` to `FieldBlock` list.
* Map `customLabels` to `CustomLabelGroup`.
* Map `outputColumns` to `output_columns`.

You do NOT need to handle every possible OMRChecker field type; support an `INT` type (for digit columns) and MCQ4/MCQ5 is enough initially.

---

#### 5. Template visual editor GUI

In `gui/template_editor.py`:

* Implement a `TemplateEditorWindow(QMainWindow)` that allows:

  * Loading a background sheet image.
  * Loading an existing `template.json` into a `TemplateModel`.
  * Displaying all `FieldBlock` objects as resizable rectangles on top of the image using `QGraphicsView/QGraphicsScene`.
  * Selecting a field block to edit its properties in a side panel (`QWidget` with form fields):

    * field type (combo box)
    * label prefix + count (to regenerate `labels` list)
    * origin_x / origin_y (either numeric or updated from the rectangle position)
    * labels_gap / bubbles_gap
  * Adding a new field block by drawing a rectangle with the mouse.
  * Removing selected field blocks.
  * Managing `CustomLabelGroup` entries:

    * UI list showing groups;
    * For each group, UI to select which labels belong to it (multi-select list).

Important:

* Implement conversion functions between scene coordinates and template model coordinates based on `PageSettings`.
* Ensure Save / Save As functions write a valid OMRChecker-compatible `template.json` using `template_io.save_template`.

---

#### 6. ID sheet generator core logic

In `core/id_sheet_generator.py`:

Define:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class IdSheetParams:
    num_digits: int
    page_width: int     # in pixels or logical units
    page_height: int
    margin_left: int
    margin_top: int
    margin_right: int
    margin_bottom: int
    bubble_radius: int
    labels_gap: int
    bubbles_gap: int
    include_class: bool = False
    class_digits: int = 0

@dataclass
class GeneratedSheet:
    image_path: Path
    template_path: Path
    config_path: Optional[Path]

def generate_id_sheet(params: IdSheetParams,
                      output_dir: Path,
                      base_name: str = "student_id") -> GeneratedSheet:
    """
    Generate a printable ID answer sheet and its template.json.
    1. Render a blank sheet image with markers and ID bubbles.
    2. Build a TemplateModel with:
       - INT field blocks for each ID digit (labels sid1..sidN)
       - custom label group "StudentID" combining those labels.
    3. Save the image as PNG (base_name.png).
    4. Save template.json and a default config.json.
    """
```

Rendering logic:

* Use Pillow:

  * Create a blank white image of size `(page_width, page_height)`.
  * Draw four solid black rectangles at the corners as markers.
  * For each digit i in `[0, num_digits)`:

    * Compute column x position (starting from `margin_left` + i * `labels_gap`).
    * For each digit value d in `[0..9]`, compute bubble center y position (starting from `margin_top`, increment by `bubbles_gap`).
    * Draw a circle and the digit label next to it.
* Mirror the same coordinates into `FieldBlock.origin_x`, `origin_y`, `labels_gap`, `bubbles_gap` so that OMRChecker can use them.

TemplateModel construction:

* For ID digits:

  * For i in `[0..num_digits)`:

    * create labels like `sid{i+1}`.
  * Create one `FieldBlock` with `field_type="INT"` and `labels=["sid1", ..., f"sid{num_digits}"]`, with appropriate `origin_x`, `origin_y`, `labels_gap`, `bubbles_gap`.
* Create `CustomLabelGroup`:

  * name = `"StudentID"`, `component_labels=["sid1", ..., f"sid{num_digits}"]`.
* Set `output_columns` at least to `["StudentID"]`.

Config:

* Write a simple `config.json` that matches the generated `page_width`/`page_height` and gives reasonable `processing_width`/`processing_height`.

---

#### 7. Main window GUI

In `gui/main_window.py`:

Implement `MainWindow(QMainWindow)` with:

* Menu bar entries:

  * File:

    * New Project
    * Open Project
    * Save Project
    * Exit
  * Tools:

    * Open Template Editor
    * Open ID Sheet Generator
  * Run:

    * Run OMR
    * View Latest Results

* Central widgets:

  * A form showing current project properties (paths, template, config).
  * Buttons to browse/select directories / JSON files.
  * A tab to show:

    * Log output (multi-line text)
    * Results table (QTableView) bound to parsed CSV records

The main window orchestrates:

* Loading/saving `Project` objects.
* Constructing an `OmrRunner` instance with `project.omrchecker_root`.
* Calling `OmrRunner.run` when the user clicks "Run OMR".
* Updating the UI after a run (e.g., auto-loading the latest CSV and showing it in the table).

---
