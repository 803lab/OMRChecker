"""Main window for the OMR GUI application."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from omr_gui.core.omr_runner import OmrRunner
from omr_gui.core.project_model import Project
from omr_gui.core.result_parser import parse_omr_csv
from omr_gui.gui.id_sheet_generator import IdSheetGeneratorWindow
from omr_gui.gui.template_editor import TemplateEditorWindow


class PathSelector(QWidget):
    """Line edit with a browse button."""

    def __init__(self, label: str, select_file: bool) -> None:
        super().__init__()
        self.select_file = select_file
        self.label_text = label
        self.line_edit = QLineEdit()
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse)

        layout = QHBoxLayout(self)
        layout.addWidget(self.line_edit)
        layout.addWidget(browse_btn)
        layout.setContentsMargins(0, 0, 0, 0)

    def _browse(self) -> None:
        if self.select_file:
            file_path, _ = QFileDialog.getOpenFileName(self, f"Select {self.label_text}")
            if file_path:
                self.line_edit.setText(file_path)
        else:
            directory = QFileDialog.getExistingDirectory(self, f"Select {self.label_text}")
            if directory:
                self.line_edit.setText(directory)

    def path(self) -> Path:
        return Path(self.line_edit.text()) if self.line_edit.text() else Path()

    def set_path(self, path: Path) -> None:
        self.line_edit.setText(str(path))


class OmrRunWorker(QThread):
    """Worker thread to run OMRChecker and stream logs."""

    log_line = Signal(str)
    finished = Signal(Path)
    failed = Signal(str)

    def __init__(
        self,
        runner: OmrRunner,
        input_dir: Path,
        template_path: Optional[Path],
        config_path: Optional[Path],
        evaluation_path: Optional[Path],
    ) -> None:
        super().__init__()
        self.setTerminationEnabled(True)
        self.runner = runner
        self.input_dir = input_dir
        self.template_path = template_path
        self.config_path = config_path
        self.evaluation_path = evaluation_path

    def run(self) -> None:
        try:
            latest_csv = self.runner.run(
                input_dir=self.input_dir,
                template_path=self.template_path,
                config_path=self.config_path,
                evaluation_path=self.evaluation_path,
                log_callback=self.log_line.emit,
            )
            self.finished.emit(latest_csv)
        except Exception as exc:  # pragma: no cover - GUI runtime
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    """Main GUI window wrapping OMRChecker."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OMR GUI")
        self.current_project_path: Optional[Path] = None
        self.runner: Optional[OmrRunner] = None
        self.run_worker: Optional[OmrRunWorker] = None
        self.project_root: Optional[Path] = None

        self._build_ui()
        self._setup_menu()

    # UI construction -----------------------------------------------------
    def _build_ui(self) -> None:
        self.name_input = QLineEdit("New Project")
        # Internal selectors (hidden)
        self.project_root_input = PathSelector("Project Root", select_file=False)
        self.omr_root_input = PathSelector("OMRChecker Root", select_file=False)
        self.omr_root_input.setVisible(False)
        self.omr_root_input.set_path(self._default_omr_root())
        self.template_input = PathSelector("Template JSON", select_file=True)
        self.config_input = PathSelector("Config JSON", select_file=True)
        self.evaluation_input = PathSelector("Evaluation JSON", select_file=True)
        self.input_dir_input = PathSelector("Input Directory", select_file=False)
        self.output_dir_input = PathSelector("Output Directory", select_file=False)

        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.addRow("Project Name", self.name_input)
        # Hide all path selectors; show only summary.
        for selector in (
            self.project_root_input,
            self.template_input,
            self.config_input,
            self.evaluation_input,
            self.input_dir_input,
            self.output_dir_input,
        ):
            selector.setVisible(False)

        self.paths_summary = QLabel("")
        self.paths_summary.setWordWrap(True)
        form_layout.addRow("Paths", self.paths_summary)

        run_button = QPushButton("Run OMR")
        run_button.clicked.connect(self._run_omr)
        view_results_button = QPushButton("View Latest Results")
        view_results_button.clicked.connect(self._view_latest_results)

        tools_layout = QHBoxLayout()
        template_editor_btn = QPushButton("Open Template Editor")
        template_editor_btn.clicked.connect(self._open_template_editor)
        id_sheet_btn = QPushButton("Open ID Sheet Generator")
        id_sheet_btn.clicked.connect(self._open_id_sheet_generator)
        tools_layout.addWidget(template_editor_btn)
        tools_layout.addWidget(id_sheet_btn)

        run_layout = QHBoxLayout()
        run_layout.addWidget(run_button)
        run_layout.addWidget(view_results_button)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)

        self.results_table = QTableView()
        self.results_table.horizontalHeader().setStretchLastSection(True)

        tabs = QTabWidget()
        tabs.addTab(self.log_output, "Log")
        tabs.addTab(self.results_table, "Results")

        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.addWidget(form_widget)
        main_layout.addLayout(run_layout)
        main_layout.addLayout(tools_layout)
        main_layout.addWidget(tabs)

        self.setCentralWidget(central)

        # Auto-fill paths when project root changes
        self.project_root_input.line_edit.textChanged.connect(self._on_project_root_changed)

    def _setup_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        new_action = QAction("New Project", self)
        new_action.triggered.connect(self._new_project)
        open_action = QAction("Open Project", self)
        open_action.triggered.connect(self._open_project)
        save_action = QAction("Save Project", self)
        save_action.triggered.connect(self._save_project)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        tools_menu = self.menuBar().addMenu("Tools")
        te_action = QAction("Open Template Editor", self)
        te_action.triggered.connect(self._open_template_editor)
        id_action = QAction("Open ID Sheet Generator", self)
        id_action.triggered.connect(self._open_id_sheet_generator)
        tools_menu.addAction(te_action)
        tools_menu.addAction(id_action)

    # Project helpers -----------------------------------------------------
    def _build_runner(self, project: Project) -> OmrRunner:
        runner = OmrRunner(project.omrchecker_root)
        runner.outputs_dir = project.output_dir
        return runner

    def _gather_project(self) -> Project:
        project_root = self.project_root_input.path()
        if project_root and project_root.exists():
            self._auto_fill_from_project_root(project_root)
        project_root = self.project_root_input.path()
        if not project_root:
            raise RuntimeError("Please create or open a project first.")
        template_path, config_path, evaluation_path, input_dir, output_dir = (
            self._paths_from_root(project_root)
        )
        return Project(
            name=self.name_input.text() or "Untitled",
            omrchecker_root=self.omr_root_input.path() or self._default_omr_root(),
            template_path=template_path,
            config_path=config_path,
            evaluation_path=evaluation_path,
            input_dir=input_dir,
            output_dir=output_dir,
        )

    def _populate_project_fields(self, project: Project) -> None:
        self.name_input.setText(project.name)
        inferred_root = self._infer_project_root(project)
        if inferred_root:
            self.project_root_input.set_path(inferred_root)
            self.project_root = inferred_root
        self.omr_root_input.set_path(project.omrchecker_root)
        self.template_input.set_path(project.template_path)
        if project.config_path:
            self.config_input.set_path(project.config_path)
        else:
            self.config_input.line_edit.clear()
        if project.evaluation_path:
            self.evaluation_input.set_path(project.evaluation_path)
        else:
            self.evaluation_input.line_edit.clear()
        self.input_dir_input.set_path(project.input_dir)
        self.output_dir_input.set_path(project.output_dir)
        self._update_paths_summary()

    def _new_project(self) -> None:
        self.current_project_path = None
        chosen_dir = QFileDialog.getExistingDirectory(
            self, "Choose Project Folder", str(Path.cwd())
        )
        if not chosen_dir:
            return
        default_root = Path(chosen_dir)
        default_root.mkdir(parents=True, exist_ok=True)
        for sub in ("config", "input", "output"):
            (default_root / sub).mkdir(parents=True, exist_ok=True)
        template_path, config_path, evaluation_path, input_dir, output_dir = (
            self._paths_from_root(default_root)
        )
        project_name = default_root.name or "New Project"
        project = Project(
            name=project_name,
            omrchecker_root=self._default_omr_root(),
            template_path=template_path,
            config_path=config_path,
            evaluation_path=evaluation_path,
            input_dir=input_dir,
            output_dir=output_dir,
        )
        self.project_root_input.set_path(default_root)
        self._populate_project_fields(project)
        # Auto-create project file inside chosen directory.
        project_file = default_root / f"{project_name}.omrproj"
        project.save(project_file)
        self.current_project_path = project_file
        self.runner = self._build_runner(project)
        self.log_output.clear()
        self.log_output.appendPlainText(f"Project created at {project_file}")

    def _open_project(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "OMR Project (*.omrproj)"
        )
        if not file_path:
            return
        project = Project.load(Path(file_path))
        self.current_project_path = Path(file_path)
        self._populate_project_fields(project)
        self.runner = self._build_runner(project)
        self.log_output.appendPlainText(f"Loaded project from {file_path}")

    def _save_project(self) -> None:
        project = self._gather_project()
        if not self.current_project_path:
            suggested = (
                project.template_path.parent.parent / f"{project.name}.omrproj"
                if self.project_root_input.path()
                else Path.cwd() / f"{project.name}.omrproj"
            )
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Project", str(suggested), "OMR Project (*.omrproj)"
            )
            if not file_path:
                return
            self.current_project_path = Path(file_path)
        project.save(self.current_project_path)
        QMessageBox.information(self, "Saved", "Project saved successfully.")
        self.runner = self._build_runner(project)

    # Actions -------------------------------------------------------------
    def _run_omr(self) -> None:
        if self.run_worker and self.run_worker.isRunning():
            QMessageBox.warning(self, "Busy", "OMR is already running.")
            return
        try:
            project = self._gather_project()
        except Exception as exc:
            QMessageBox.warning(self, "Project Required", str(exc))
            return
        if not project.omrchecker_root.exists():
            QMessageBox.warning(self, "Invalid Path", "OMRChecker root does not exist.")
            return
        self.runner = self._build_runner(project)
        self._prepare_project_files(project)
        self.log_output.appendPlainText("Starting OMRChecker...")
        self.run_worker = OmrRunWorker(
            runner=self.runner,
            input_dir=project.input_dir,
            template_path=project.template_path,
            config_path=project.config_path,
            evaluation_path=project.evaluation_path,
        )
        self.run_worker.log_line.connect(self._append_log)
        self.run_worker.finished.connect(self._on_run_finished)
        self.run_worker.failed.connect(self._on_run_failed)
        self.run_worker.start()

    def _append_log(self, line: str) -> None:
        self.log_output.appendPlainText(line)

    def _on_run_finished(self, csv_path: Path) -> None:
        self.log_output.appendPlainText(f"Run complete. Latest CSV: {csv_path}")
        self._load_results(csv_path)

    def _on_run_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Run Failed", message)
        self.log_output.appendPlainText(f"Run failed: {message}")

    def _view_latest_results(self) -> None:
        if not self.runner:
            QMessageBox.warning(self, "No Runner", "Please configure a project first.")
            return
        csv_files = self.runner.list_output_csvs()
        if not csv_files:
            QMessageBox.information(self, "No Results", "No CSV outputs found.")
            return
        latest = max(csv_files, key=lambda f: f.stat().st_mtime)
        self._load_results(latest)

    def _load_results(self, csv_path: Path) -> None:
        df = pd.read_csv(csv_path)
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(list(df.columns))
        for _, row in df.iterrows():
            items = [QStandardItem(str(value)) for value in row]
            model.appendRow(items)
        self.results_table.setModel(model)
        self.results_table.resizeColumnsToContents()
        # Keep parsed records handy for potential downstream use
        _ = parse_omr_csv(csv_path)

    def _open_template_editor(self) -> None:
        editor = TemplateEditorWindow(self)
        template_path = self.template_input.path()
        if template_path.exists():
            editor.load_template(template_path)
        editor.show()

    def _open_id_sheet_generator(self) -> None:
        generator = IdSheetGeneratorWindow(self)
        generator.show()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Ensure background threads are stopped before closing."""
        if self.run_worker and self.run_worker.isRunning():
            self.log_output.appendPlainText("Waiting for OMR run to stop...")
            self.run_worker.requestInterruption()
            self.run_worker.wait(5000)
            if self.run_worker.isRunning():
                self.log_output.appendPlainText("Force-stopping OMR thread.")
                self.run_worker.terminate()
                self.run_worker.wait(1000)
        super().closeEvent(event)

    # Project root helpers -----------------------------------------------
    def _on_project_root_changed(self) -> None:
        root = self.project_root_input.path()
        if root and root.exists():
            self._auto_fill_from_project_root(root)
        self.omr_root_input.set_path(self._default_omr_root())
        self._update_paths_summary()

    def _auto_fill_from_project_root(self, root: Path) -> None:
        self.project_root = root
        config_dir = root / "config"
        input_dir = root / "input"
        output_dir = root / "output"
        self.input_dir_input.set_path(input_dir)
        self.output_dir_input.set_path(output_dir)
        template_path = config_dir / "template.json"
        config_path = config_dir / "config.json"
        evaluation_path = config_dir / "evaluation.json"
        self.template_input.set_path(template_path)
        if config_path.exists():
            self.config_input.set_path(config_path)
        else:
            self.config_input.line_edit.clear()
        if evaluation_path.exists():
            self.evaluation_input.set_path(evaluation_path)
        else:
            self.evaluation_input.line_edit.clear()

    def _infer_project_root(self, project: Project) -> Optional[Path]:
        candidates = []
        if project.template_path.name == "template.json" and project.template_path.parent.name.lower() == "config":
            candidates.append(project.template_path.parent.parent)
        if project.input_dir.name.lower() in ["input", "inputs"]:
            candidates.append(project.input_dir.parent)
        if project.output_dir.name.lower() in ["output", "outputs"]:
            candidates.append(project.output_dir.parent)
        for root in candidates:
            if root.exists():
                return root
        return None

    def _paths_from_root(self, root: Path | None) -> tuple[Path, Optional[Path], Optional[Path], Path, Path]:
        base = root if root else Path.cwd()
        config_dir = base / "config"
        input_dir = base / "input"
        output_dir = base / "output"
        template_path = config_dir / "template.json"
        config_path = config_dir / "config.json"
        evaluation_path = config_dir / "evaluation.json"
        return (
            template_path,
            config_path if config_path.exists() else None,
            evaluation_path if evaluation_path.exists() else None,
            input_dir,
            output_dir,
        )

    def _prepare_project_files(self, project: Project) -> None:
        """Ensure expected structure and link config/template into input dir."""
        project.input_dir.mkdir(parents=True, exist_ok=True)
        project.output_dir.mkdir(parents=True, exist_ok=True)

    def _update_paths_summary(self) -> None:
        root = self.project_root_input.path()
        template_path, config_path, evaluation_path, input_dir, output_dir = (
            self._paths_from_root(root)
        )
        summary_lines = [
            f"Template: {template_path}",
            f"Config: {config_path or 'not found'}",
            f"Evaluation: {evaluation_path or 'not set'}",
            f"Input: {input_dir}",
            f"Output: {output_dir}",
        ]
        self.paths_summary.setText("\n".join(summary_lines))

    def _default_omr_root(self) -> Path:
        """Default OMRChecker root is the repository root (one level above omr_gui)."""
        return Path(__file__).resolve().parents[2]
