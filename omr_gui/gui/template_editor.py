"""Template visual editor for OMR templates."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, QSizeF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRubberBand,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from omr_gui.core import template_io
from omr_gui.core.template_model import (
    CustomLabelGroup,
    FieldBlock,
    FieldType,
    PageSettings,
    TemplateModel,
)


class TemplateGraphicsView(QGraphicsView):
    """Graphics view with support for drawing rectangles (Ctrl+Drag)."""

    rect_drawn = Signal(QRectF)

    def __init__(self, scene: QGraphicsScene, parent: Optional[QWidget] = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self._dragging = False
        self._drag_start = QPointF()
        self._rubber_band = QRubberBand(QRubberBand.Rectangle, self)

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.LeftButton
            and event.modifiers() & Qt.ControlModifier
            and not self.itemAt(event.pos())
        ):
            self._dragging = True
            self._drag_start = event.position()
            self._rubber_band.setGeometry(QRect(self._drag_start.toPoint(), QSize()))
            self._rubber_band.show()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            rect = QRect(self._drag_start.toPoint(), event.position().toPoint()).normalized()
            self._rubber_band.setGeometry(rect)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._rubber_band.hide()
            end_pos = event.position()
            if (end_pos - self._drag_start).manhattanLength() > 10:
                scene_start = self.mapToScene(self._drag_start.toPoint())
                scene_end = self.mapToScene(end_pos.toPoint())
                rect = QRectF(scene_start, scene_end).normalized()
                self.rect_drawn.emit(rect)
            self._dragging = False
        else:
            super().mouseReleaseEvent(event)


class FieldBlockItem(QGraphicsRectItem):
    """Graphics item representing a field block."""

    def __init__(
        self,
        block_id: str,
        rect: QRectF,
        on_geometry_change,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        super().__init__(rect, parent)
        self.block_id = block_id
        self.on_geometry_change = on_geometry_change
        self._resizing = False
        self._handle_size = 12
        self.setBrush(QColor(80, 140, 255, 60))
        self.setPen(QPen(QColor(40, 90, 180), 2, Qt.DashLine))
        self.setFlags(
            QGraphicsRectItem.ItemIsMovable
            | QGraphicsRectItem.ItemIsSelectable
            | QGraphicsRectItem.ItemSendsGeometryChanges
            | QGraphicsRectItem.ItemIsFocusable
        )
        self.setAcceptHoverEvents(True)

    def _hit_resize_handle(self, pos: QPointF) -> bool:
        rect = self.rect()
        handle_rect = QRectF(
            rect.bottomRight() - QPointF(self._handle_size, self._handle_size),
            QSizeF(self._handle_size, self._handle_size),
        )
        return handle_rect.contains(pos)

    def hoverMoveEvent(self, event):
        if self._hit_resize_handle(event.pos()):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._hit_resize_handle(event.pos()):
            self._resizing = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            new_rect = QRectF(QPointF(0, 0), event.pos()).normalized()
            new_rect.setWidth(max(10, new_rect.width()))
            new_rect.setHeight(max(10, new_rect.height()))
            self.setRect(new_rect)
            if self.on_geometry_change:
                self.on_geometry_change(self)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            if self.on_geometry_change:
                self.on_geometry_change(self)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if (
            change == QGraphicsItem.ItemPositionHasChanged
            or change == QGraphicsItem.ItemTransformHasChanged
        ):
            if self.on_geometry_change:
                self.on_geometry_change(self)
        return super().itemChange(change, value)


class TemplateEditorWindow(QMainWindow):
    """Main window for the template editor."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Template Editor")
        self.model = TemplateModel(page=PageSettings(width=1654, height=2339))
        self.current_template_path: Optional[Path] = None
        self.background_item: Optional[QGraphicsPixmapItem] = None
        self.block_items: Dict[str, FieldBlockItem] = {}
        self._selected_block_id: Optional[str] = None
        self._scale_x = 1.0
        self._scale_y = 1.0

        self._build_ui()
        self._setup_menu()
        self._refresh_scene()

    # UI setup helpers -----------------------------------------------------
    def _build_ui(self) -> None:
        self.scene = QGraphicsScene(self)
        self.view = TemplateGraphicsView(self.scene, self)
        self.view.rect_drawn.connect(self._on_rect_drawn)

        self.block_id_label = QLabel("-")
        self.field_type_combo = QComboBox()
        self.field_type_combo.addItems(["INT", "MCQ4", "MCQ5", "BOOLEAN"])
        self.label_prefix_input = QLineEdit()
        self.label_count_input = QSpinBox()
        self.label_count_input.setRange(1, 200)
        self.origin_x_input = QDoubleSpinBox()
        self.origin_x_input.setRange(0, 10000)
        self.origin_y_input = QDoubleSpinBox()
        self.origin_y_input.setRange(0, 10000)
        self.labels_gap_input = QDoubleSpinBox()
        self.labels_gap_input.setRange(0, 1000)
        self.labels_gap_input.setValue(40)
        self.bubbles_gap_input = QDoubleSpinBox()
        self.bubbles_gap_input.setRange(0, 1000)
        self.bubbles_gap_input.setValue(30)

        apply_button = QPushButton("Apply Block Changes")
        apply_button.clicked.connect(self._apply_block_changes)
        regen_button = QPushButton("Regenerate Labels")
        regen_button.clicked.connect(self._regenerate_labels)
        delete_button = QPushButton("Delete Selected Block")
        delete_button.clicked.connect(self._delete_selected_block)

        block_form = QWidget()
        block_layout = QFormLayout(block_form)
        block_layout.addRow("Block ID", self.block_id_label)
        block_layout.addRow("Field Type", self.field_type_combo)
        block_layout.addRow("Label Prefix", self.label_prefix_input)
        block_layout.addRow("Label Count", self.label_count_input)
        block_layout.addRow("Origin X", self.origin_x_input)
        block_layout.addRow("Origin Y", self.origin_y_input)
        block_layout.addRow("Labels Gap", self.labels_gap_input)
        block_layout.addRow("Bubbles Gap", self.bubbles_gap_input)
        block_layout.addRow(regen_button)
        block_layout.addRow(apply_button)
        block_layout.addRow(delete_button)

        # Custom labels tab
        self.group_list = QListWidget()
        self.group_list.currentItemChanged.connect(self._on_group_selected)
        self.label_memberships = QListWidget()
        self.label_memberships.itemChanged.connect(self._on_label_membership_changed)
        add_group_btn = QPushButton("Add Group")
        add_group_btn.clicked.connect(self._add_group)
        remove_group_btn = QPushButton("Remove Group")
        remove_group_btn.clicked.connect(self._remove_group)

        custom_layout = QVBoxLayout()
        custom_layout.addWidget(QLabel("Custom Label Groups"))
        custom_layout.addWidget(self.group_list)
        btn_row = QHBoxLayout()
        btn_row.addWidget(add_group_btn)
        btn_row.addWidget(remove_group_btn)
        custom_layout.addLayout(btn_row)
        custom_layout.addWidget(QLabel("Labels in Group"))
        custom_layout.addWidget(self.label_memberships)
        custom_widget = QWidget()
        custom_widget.setLayout(custom_layout)

        tabs = QTabWidget()
        tabs.addTab(block_form, "Block Properties")
        tabs.addTab(custom_widget, "Custom Labels")

        splitter = QSplitter(self)
        splitter.addWidget(self.view)
        splitter.addWidget(tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.addWidget(splitter)

        bottom_bar = QHBoxLayout()
        info_label = QLabel(
            "Ctrl+Drag on the canvas to draw a new block. Select a block to edit."
        )
        bottom_bar.addWidget(info_label)
        main_layout.addLayout(bottom_bar)

        self.setCentralWidget(central)

        self.scene.selectionChanged.connect(self._on_selection_changed)

    def _setup_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        open_action = QAction("Open Template", self)
        open_action.triggered.connect(self._open_template_dialog)
        save_action = QAction("Save", self)
        save_action.triggered.connect(self._save_template)
        save_as_action = QAction("Save As", self)
        save_as_action.triggered.connect(self._save_template_as)
        load_bg_action = QAction("Load Background Image", self)
        load_bg_action.triggered.connect(self._load_background_image)

        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(load_bg_action)

        edit_menu = self.menuBar().addMenu("Edit")
        add_block_action = QAction("Add Block", self)
        add_block_action.triggered.connect(self._add_default_block)
        delete_block_action = QAction("Delete Block", self)
        delete_block_action.triggered.connect(self._delete_selected_block)
        edit_menu.addAction(add_block_action)
        edit_menu.addAction(delete_block_action)

    # Model/scene sync -----------------------------------------------------
    def _refresh_scene(self) -> None:
        self.scene.clear()
        self.block_items.clear()
        if self.background_item:
            self.background_item = None
        self._scale_x = 1.0
        self._scale_y = 1.0

        if self.current_template_path:
            self.setWindowTitle(f"Template Editor - {self.current_template_path}")
        else:
            self.setWindowTitle("Template Editor")

        # Update scene rect to page size
        self.scene.setSceneRect(
            QRectF(0, 0, float(self.model.page.width), float(self.model.page.height))
        )

        for block in self.model.field_blocks:
            self._add_block_item(block)
        self._refresh_groups_ui()

    def _add_block_item(self, block: FieldBlock) -> FieldBlockItem:
        width = self._block_width(block)
        height = self._block_height(block)
        scene_pos = self._model_to_scene_point(block.origin_x, block.origin_y)
        item = FieldBlockItem(
            block_id=block.id,
            rect=QRectF(0, 0, width, height),
            on_geometry_change=self._on_item_geometry_changed,
        )
        item.setPos(scene_pos)
        self.scene.addItem(item)
        self.block_items[block.id] = item
        return item

    def _block_width(self, block: FieldBlock) -> float:
        columns = max(1, len(block.labels))
        gap = block.labels_gap if block.labels_gap > 0 else 40
        return columns * gap

    def _block_height(self, block: FieldBlock) -> float:
        rows = self._rows_for_block(block)
        gap = block.bubbles_gap if block.bubbles_gap > 0 else 30
        return rows * gap

    def _rows_for_block(self, block: FieldBlock) -> int:
        if block.field_type == "INT":
            return 10
        if block.field_type == "MCQ4":
            return 4
        if block.field_type == "MCQ5":
            return 5
        if block.field_type == "BOOLEAN":
            return 2
        return max(1, len(block.labels))

    def _model_to_scene_point(self, x: float, y: float) -> QPointF:
        return QPointF(x * self._scale_x, y * self._scale_y)

    def _scene_to_model_point(self, point: QPointF) -> QPointF:
        scale_x = self._scale_x if self._scale_x else 1.0
        scale_y = self._scale_y if self._scale_y else 1.0
        return QPointF(point.x() / scale_x, point.y() / scale_y)

    def _update_item_from_block(self, block: FieldBlock) -> None:
        item = self.block_items.get(block.id)
        if not item:
            return
        item.setPos(self._model_to_scene_point(block.origin_x, block.origin_y))
        item.setRect(QRectF(0, 0, self._block_width(block), self._block_height(block)))

    def _on_item_geometry_changed(self, item: FieldBlockItem) -> None:
        block = self._get_block_by_id(item.block_id)
        if not block:
            return
        model_pos = self._scene_to_model_point(item.scenePos())
        block.origin_x = float(model_pos.x())
        block.origin_y = float(model_pos.y())
        block.labels_gap = float(item.rect().width() / max(1, len(block.labels)))
        rows = max(1, self._rows_for_block(block))
        block.bubbles_gap = float(item.rect().height() / rows)
        if self._selected_block_id == block.id:
            self._populate_block_form(block)

    def _get_block_by_id(self, block_id: str) -> Optional[FieldBlock]:
        for block in self.model.field_blocks:
            if block.id == block_id:
                return block
        return None

    # Slots ---------------------------------------------------------------
    def _on_rect_drawn(self, rect: QRectF) -> None:
        model_pos = self._scene_to_model_point(rect.topLeft())
        width = rect.width() / (self._scale_x if self._scale_x else 1.0)
        height = rect.height() / (self._scale_y if self._scale_y else 1.0)
        block_id = f"Block_{len(self.model.field_blocks) + 1}"
        block = FieldBlock(
            id=block_id,
            field_type="INT",
            labels=[f"{block_id}_1"],
            origin_x=float(model_pos.x()),
            origin_y=float(model_pos.y()),
            labels_gap=width,
            bubbles_gap=height / 10 if height > 0 else 30,
        )
        self.model.field_blocks.append(block)
        self._add_block_item(block)
        self._select_block(block.id)
        self._refresh_groups_ui()

    def _add_default_block(self) -> None:
        rect = QRectF(50, 50, 200, 200)
        self._on_rect_drawn(rect)

    def _on_selection_changed(self) -> None:
        items = self.scene.selectedItems()
        if not items:
            self._selected_block_id = None
            self._populate_block_form(None)
            return
        item = items[0]
        if isinstance(item, FieldBlockItem):
            self._selected_block_id = item.block_id
            block = self._get_block_by_id(item.block_id)
            self._populate_block_form(block)

    def _populate_block_form(self, block: Optional[FieldBlock]) -> None:
        if not block:
            self.block_id_label.setText("-")
            return
        self.block_id_label.setText(block.id)
        self.field_type_combo.setCurrentText(block.field_type)
        self.origin_x_input.setValue(block.origin_x)
        self.origin_y_input.setValue(block.origin_y)
        self.labels_gap_input.setValue(block.labels_gap)
        self.bubbles_gap_input.setValue(block.bubbles_gap)
        if block.labels:
            prefix = "".join([c for c in block.labels[0] if not c.isdigit()])
            self.label_prefix_input.setText(prefix)
            self.label_count_input.setValue(len(block.labels))

    def _apply_block_changes(self) -> None:
        if not self._selected_block_id:
            return
        block = self._get_block_by_id(self._selected_block_id)
        if not block:
            return
        block.field_type = self.field_type_combo.currentText()  # type: ignore[assignment]
        block.origin_x = self.origin_x_input.value()
        block.origin_y = self.origin_y_input.value()
        block.labels_gap = self.labels_gap_input.value()
        block.bubbles_gap = self.bubbles_gap_input.value()
        if self.label_prefix_input.text():
            prefix = self.label_prefix_input.text()
            count = self.label_count_input.value()
            block.labels = [f"{prefix}{i+1}" for i in range(count)]
        self._update_item_from_block(block)
        self._refresh_groups_ui()

    def _regenerate_labels(self) -> None:
        if not self._selected_block_id:
            return
        block = self._get_block_by_id(self._selected_block_id)
        if not block:
            return
        prefix = self.label_prefix_input.text() or "field"
        count = self.label_count_input.value()
        block.labels = [f"{prefix}{i+1}" for i in range(count)]
        self._update_item_from_block(block)
        self._refresh_groups_ui()

    def _delete_selected_block(self) -> None:
        if not self._selected_block_id:
            return
        block = self._get_block_by_id(self._selected_block_id)
        if not block:
            return
        self.model.field_blocks.remove(block)
        item = self.block_items.pop(block.id, None)
        if item:
            self.scene.removeItem(item)
        self._selected_block_id = None
        self._populate_block_form(None)
        self._refresh_groups_ui()

    # Group UI ------------------------------------------------------------
    def _collect_all_labels(self) -> list[str]:
        labels: list[str] = []
        for block in self.model.field_blocks:
            labels.extend(block.labels)
        return labels

    def _refresh_groups_ui(self) -> None:
        self.group_list.blockSignals(True)
        self.group_list.clear()
        for group in self.model.custom_labels:
            self.group_list.addItem(group.name)
        self.group_list.blockSignals(False)
        if self.model.custom_labels:
            self.group_list.setCurrentRow(0)
        else:
            self.label_memberships.clear()

    def _on_group_selected(
        self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]
    ) -> None:
        if not current:
            self.label_memberships.clear()
            return
        group = self._get_group_by_name(current.text())
        if not group:
            return
        self._populate_label_memberships(group)

    def _populate_label_memberships(self, group: CustomLabelGroup) -> None:
        self.label_memberships.blockSignals(True)
        self.label_memberships.clear()
        all_labels = self._collect_all_labels()
        for label in all_labels:
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if label in group.component_labels else Qt.Unchecked
            )
            self.label_memberships.addItem(item)
        self.label_memberships.blockSignals(False)

    def _on_label_membership_changed(self, item: QListWidgetItem) -> None:
        group_item = self.group_list.currentItem()
        if not group_item:
            return
        group = self._get_group_by_name(group_item.text())
        if not group:
            return
        label = item.text()
        if item.checkState() == Qt.Checked:
            if label not in group.component_labels:
                group.component_labels.append(label)
        else:
            if label in group.component_labels:
                group.component_labels.remove(label)
        self.model.output_columns = [g.name for g in self.model.custom_labels]

    def _add_group(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Group", "Group name:")
        if not ok or not name:
            return
        if self._get_group_by_name(name):
            QMessageBox.warning(self, "Duplicate Name", "Group name already exists.")
            return
        group = CustomLabelGroup(name=name, component_labels=[])
        self.model.custom_labels.append(group)
        self._refresh_groups_ui()

    def _remove_group(self) -> None:
        current = self.group_list.currentItem()
        if not current:
            return
        group = self._get_group_by_name(current.text())
        if not group:
            return
        self.model.custom_labels.remove(group)
        self._refresh_groups_ui()
        self.model.output_columns = [g.name for g in self.model.custom_labels]

    def _get_group_by_name(self, name: str) -> Optional[CustomLabelGroup]:
        for group in self.model.custom_labels:
            if group.name == name:
                return group
        return None

    # Template load/save ---------------------------------------------------
    def load_template(self, path: Path) -> None:
        """Load a template and display it."""
        self.model = template_io.load_template(path)
        self.current_template_path = path
        self._refresh_scene()

    def _open_template_dialog(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Template", "", "Template JSON (*.json)"
        )
        if file_path:
            self.load_template(Path(file_path))

    def _save_template(self) -> None:
        if not self.current_template_path:
            self._save_template_as()
            return
        template_io.save_template(self.model, self.current_template_path)
        QMessageBox.information(self, "Template Saved", "Template saved successfully.")

    def _save_template_as(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Template As", "", "Template JSON (*.json)"
        )
        if file_path:
            self.current_template_path = Path(file_path)
            self._save_template()

    # Background image ----------------------------------------------------
    def _load_background_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Background Image", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if not file_path:
            return
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Error", "Failed to load image.")
            return
        self.scene.clear()
        self.block_items.clear()
        self.background_item = self.scene.addPixmap(pixmap)
        self._scale_x = pixmap.width() / self.model.page.width
        self._scale_y = pixmap.height() / self.model.page.height
        for block in self.model.field_blocks:
            self._add_block_item(block)

    # Utilities -----------------------------------------------------------
    def _get_output_columns(self) -> list[str]:
        if self.model.output_columns:
            return self.model.output_columns
        return [g.name for g in self.model.custom_labels]
