"""GUI for the ID sheet generator."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import ImageDraw
from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from omr_gui.core.id_sheet_generator import (
    GeneratedSheet,
    IdSheetParams,
    generate_id_sheet,
    render_sheet_image,
)


class IdSheetGeneratorWindow(QMainWindow):
    """Window to configure and generate ID sheets."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ID Sheet Generator")
        self._build_ui()

    def _build_ui(self) -> None:
        self.num_digits = QSpinBox()
        self.num_digits.setRange(1, 20)
        self.num_digits.setValue(10)

        self.page_width = QSpinBox()
        self.page_width.setRange(500, 5000)
        self.page_width.setValue(1654)
        self.page_height = QSpinBox()
        self.page_height.setRange(500, 5000)
        self.page_height.setValue(2339)

        self.margin_left = QSpinBox()
        self.margin_left.setRange(0, 1000)
        self.margin_left.setValue(60)
        self.margin_top = QSpinBox()
        self.margin_top.setRange(0, 1000)
        self.margin_top.setValue(60)

        self.bubble_radius = QSpinBox()
        self.bubble_radius.setRange(5, 100)
        self.bubble_radius.setValue(14)
        self.labels_gap = QSpinBox()
        self.labels_gap.setRange(10, 400)
        self.labels_gap.setValue(52)
        self.bubbles_gap = QSpinBox()
        self.bubbles_gap.setRange(10, 400)
        self.bubbles_gap.setValue(42)
        self.marker_gap = QSpinBox()
        self.marker_gap.setRange(0, 400)
        self.marker_gap.setValue(6)
        self.show_template_overlay = QCheckBox("Show template overlay")

        self.include_class = QCheckBox("Include Class Field")
        self.class_digits = QSpinBox()
        self.class_digits.setRange(1, 10)
        self.class_digits.setValue(2)
        self.class_digits.setEnabled(False)
        self.include_class.stateChanged.connect(
            lambda state: self.class_digits.setEnabled(bool(state))
        )

        self.output_dir = QLineEdit(str(Path.cwd()))
        browse_output = QPushButton("Browse")
        browse_output.clicked.connect(self._browse_output_dir)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_dir)
        output_row.addWidget(browse_output)
        output_container = QWidget()
        output_container.setLayout(output_row)

        self.base_name = QLineEdit("student_id")

        form = QFormLayout()
        form.addRow("Number of digits", self.num_digits)
        form.addRow("Page width", self.page_width)
        form.addRow("Page height", self.page_height)
        form.addRow("Margin left", self.margin_left)
        form.addRow("Margin top", self.margin_top)
        form.addRow("Bubble radius", self.bubble_radius)
        form.addRow("Labels gap", self.labels_gap)
        form.addRow("Bubbles gap", self.bubbles_gap)
        form.addRow("Marker gap", self.marker_gap)
        form.addRow(self.show_template_overlay)
        form.addRow(self.include_class, self.class_digits)
        form.addRow("Output directory", output_container)
        form.addRow("Base name", self.base_name)

        generate_btn = QPushButton("Generate")
        generate_btn.clicked.connect(self._generate)

        # Preview area
        self.preview_label = QLabel("Preview will appear here.")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setWidget(self.preview_label)
        self.preview_scroll = preview_scroll

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addLayout(form)
        left_layout.addWidget(generate_btn)
        left_layout.addStretch()

        splitter = QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(preview_scroll)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(splitter)

        self.setCentralWidget(container)

        # Live preview on parameter changes
        for spin in (
            self.num_digits,
            self.page_width,
            self.page_height,
            self.margin_left,
            self.margin_top,
            self.bubble_radius,
            self.labels_gap,
            self.bubbles_gap,
            self.marker_gap,
            self.class_digits,
        ):
            spin.valueChanged.connect(self._update_preview)
        self.show_template_overlay.stateChanged.connect(self._update_preview)
        self.include_class.stateChanged.connect(self._update_preview)
        self.base_name.textChanged.connect(self._update_preview)
        # refresh on scroll area resize
        original_resize = self.preview_scroll.resizeEvent

        def resize_event(event):
            self._update_preview()
            original_resize(event)

        self.preview_scroll.resizeEvent = resize_event  # type: ignore[assignment]

        self._update_preview()

    def _browse_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_dir.setText(directory)
            self._update_preview()

    def _generate(self) -> None:
        params = IdSheetParams(
            num_digits=self.num_digits.value(),
            page_width=self.page_width.value(),
            page_height=self.page_height.value(),
            margin_left=self.margin_left.value(),
            margin_top=self.margin_top.value(),
            bubble_radius=self.bubble_radius.value(),
            labels_gap=self.labels_gap.value(),
            bubbles_gap=self.bubbles_gap.value(),
            marker_gap=self.marker_gap.value(),
            include_class=self.include_class.isChecked(),
            class_digits=self.class_digits.value(),
        )
        output_dir = Path(self.output_dir.text())
        base_name = self.base_name.text() or "student_id"
        try:
            sheet: GeneratedSheet = generate_id_sheet(params, output_dir, base_name=base_name)
        except Exception as exc:  # pragma: no cover - GUI runtime
            QMessageBox.critical(self, "Error", f"Failed to generate sheet: {exc}")
            return

        QMessageBox.information(
            self,
            "Generated",
            f"Project: {sheet.project_path}\nImage: {sheet.image_path}\nTemplate: {sheet.template_path}\nConfig: {sheet.config_path}",
        )
        self._update_preview()

    def _show_preview(self, image_path: Path) -> None:
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self.preview_label.setText(f"Failed to load preview: {image_path}")
            return
        # scale to fit scroll area width while keeping aspect ratio
        vw = self.preview_scroll.viewport().width() if self.preview_scroll else self.preview_label.width()
        vh = self.preview_scroll.viewport().height() if self.preview_scroll else self.preview_label.height()
        if vw <= 0:
            vw = 400
        if vh <= 0:
            vh = 400
        scaled = pixmap.scaled(vw, vh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        self.preview_label.setText("")

    def _update_preview(self) -> None:
        params = IdSheetParams(
            num_digits=self.num_digits.value(),
            page_width=self.page_width.value(),
            page_height=self.page_height.value(),
            margin_left=self.margin_left.value(),
            margin_top=self.margin_top.value(),
            bubble_radius=self.bubble_radius.value(),
            labels_gap=self.labels_gap.value(),
            bubbles_gap=self.bubbles_gap.value(),
            marker_gap=self.marker_gap.value(),
            include_class=self.include_class.isChecked(),
            class_digits=self.class_digits.value(),
        )
        try:
            (
                image,
                _labels,
                _class_labels,
                label_start_x,
                label_start_y,
                marker_w,
                marker_h,
            ) = render_sheet_image(params)
        except Exception as exc:  # pragma: no cover
            self.preview_label.setText(f"Preview error: {exc}")
            self.preview_label.setPixmap(QPixmap())
            return

        if self.show_template_overlay.isChecked():
            bubble_radius = params.bubble_radius
            gap = max(0, int(params.marker_gap))
            total_columns = params.num_digits + (params.class_digits if params.include_class else 0)
            extra_class_gap = params.labels_gap if (params.include_class and params.class_digits > 0) else 0
            region_width = max(
                0,
                (total_columns - 1) * params.labels_gap + extra_class_gap + 2 * bubble_radius,
            )
            region_height = max(0, 9 * params.bubbles_gap + 2 * bubble_radius)

            region_x0 = int(round(label_start_x - bubble_radius))
            region_y0 = int(round(label_start_y - bubble_radius))
            left_cx = int(round(region_x0 - gap - marker_w // 2))
            top_cy = int(round(region_y0 - gap - marker_h // 2))
            warped_w = int(round(region_width + 2 * gap + marker_w))
            warped_h = int(round(region_height + 2 * gap + marker_h))

            warped = image.crop((left_cx, top_cy, left_cx + warped_w, top_cy + warped_h)).convert(
                "RGBA"
            )
            draw = ImageDraw.Draw(warped, "RGBA")

            origin_x = marker_w // 2 + gap + bubble_radius
            origin_y = marker_h // 2 + gap + bubble_radius

            rect_x0 = origin_x - bubble_radius
            rect_y0 = origin_y - bubble_radius
            rect_x1 = rect_x0 + region_width
            rect_y1 = rect_y0 + region_height
            draw.rectangle([rect_x0, rect_y0, rect_x1, rect_y1], outline=(0, 128, 255, 200), width=2)

            def draw_int_columns(start_x: int, num_cols: int) -> None:
                for col in range(num_cols):
                    cx = start_x + col * params.labels_gap
                    for digit in range(10):
                        cy = origin_y + digit * params.bubbles_gap
                        draw.ellipse(
                            [cx - bubble_radius, cy - bubble_radius, cx + bubble_radius, cy + bubble_radius],
                            outline=(255, 0, 0, 200),
                            width=2,
                        )

            draw_int_columns(origin_x, params.num_digits)
            if params.include_class and params.class_digits > 0:
                class_start_x = origin_x + params.num_digits * params.labels_gap + params.labels_gap
                draw_int_columns(class_start_x, params.class_digits)

            image = warped.convert("RGB")

        qt_image = ImageQt(image)
        pixmap = QPixmap.fromImage(qt_image)
        vw = self.preview_scroll.viewport().width() if self.preview_scroll else self.preview_label.width()
        vh = self.preview_scroll.viewport().height() if self.preview_scroll else self.preview_label.height()
        if vw <= 0:
            vw = 400
        if vh <= 0:
            vh = 400
        scaled = pixmap.scaled(vw, vh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        self.preview_label.setText("")
