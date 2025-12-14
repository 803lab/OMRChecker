"""Generate ID sheet images and templates."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .template_io import save_template
from .template_model import CustomLabelGroup, FieldBlock, PageSettings, TemplateModel
from .project_model import Project


@dataclass
class IdSheetParams:
    """User-configurable parameters for an ID sheet."""

    num_digits: int
    page_width: int
    page_height: int
    margin_left: int
    margin_top: int
    bubble_radius: int
    labels_gap: int
    bubbles_gap: int
    marker_gap: int = 6
    marker_ratio: int = 17
    include_class: bool = False
    class_digits: int = 0


@dataclass
class GeneratedSheet:
    """Paths to generated artifacts."""

    image_path: Path
    template_path: Path
    config_path: Optional[Path]
    project_path: Optional[Path]


def _draw_markers(draw: ImageDraw.ImageDraw, width: int, height: int, size: int) -> None:
    draw.rectangle([0, 0, size, size], fill="black")
    draw.rectangle([width - size, 0, width - 1, size], fill="black")
    draw.rectangle([0, height - size, size, height - 1], fill="black")
    draw.rectangle([width - size, height - size, width - 1, height - 1], fill="black")


def _draw_markers_box(
    draw: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int, size: int
) -> None:
    """Draw four markers around a bounding box."""
    draw.rectangle([x0, y0, x0 + size, y0 + size], fill="black")
    draw.rectangle([x1 - size, y0, x1 - 1, y0 + size], fill="black")
    draw.rectangle([x0, y1 - size, x0 + size, y1 - 1], fill="black")
    draw.rectangle([x1 - size, y1 - size, x1 - 1, y1 - 1], fill="black")


def _default_marker_source_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "samples" / "sample1" / "omr_marker.jpg"


def _load_default_marker_image() -> Image.Image:
    src = _default_marker_source_path()
    if src.exists():
        return Image.open(src).convert("RGB")
    raise FileNotFoundError(f"Default marker not found: {src}")


def _ensure_marker_file(marker_path: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    src = _default_marker_source_path()
    if not src.exists():
        raise FileNotFoundError(f"Default marker not found: {src}")
    shutil.copyfile(src, marker_path)


def generate_id_sheet(
    params: IdSheetParams, output_dir: Path, base_name: str = "student_id"
) -> GeneratedSheet:
    """
    Generate a printable ID answer sheet and its template/config JSON files.
    """
    # Treat output_dir as project root and create standard structure.
    project_root = output_dir
    config_dir = project_root / "config"
    input_dir = project_root / "input"
    output_root = project_root / "output"
    config_dir.mkdir(parents=True, exist_ok=True)
    input_dir.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    image_path = config_dir / "sheet.png"
    template_path = config_dir / "template.json"
    config_path = config_dir / "config.json"
    marker_path = config_dir / "omr_marker.jpg"

    _ensure_marker_file(marker_path)

    image, labels, class_labels, _label_start_x, _label_start_y, marker_w, marker_h = render_sheet_image(params)
    image.save(image_path)

    gap = max(0, int(params.marker_gap))
    total_columns = params.num_digits + (params.class_digits if params.include_class else 0)
    extra_class_gap = params.labels_gap if (params.include_class and params.class_digits > 0) else 0
    region_width = max(
        0,
        (total_columns - 1) * params.labels_gap + extra_class_gap + 2 * params.bubble_radius,
    )
    region_height = max(0, 9 * params.bubbles_gap + 2 * params.bubble_radius)
    warped_page_width = int(round(region_width + 2 * gap + marker_w))
    warped_page_height = int(round(region_height + 2 * gap + marker_h))
    origin_x = float(marker_w // 2 + gap + params.bubble_radius)
    origin_y = float(marker_h // 2 + gap + params.bubble_radius)
    effective_marker_ratio = max(2, int(round(params.page_width / max(1, marker_w))))

    template = TemplateModel(
        page=PageSettings(width=warped_page_width, height=warped_page_height),
        bubble_dimensions=(params.bubble_radius * 2, params.bubble_radius * 2),
        pre_processors=[
            {"name": "CropPage", "options": {"morphKernel": [10, 10], "onFail": "skip"}},
            {
                "name": "CropOnMarkers",
                "options": {
                    "relativePath": marker_path.name,
                    "sheetToMarkerWidthRatio": effective_marker_ratio,
                    "searchMode": "global",
                },
            },
        ],
        field_blocks=[
            FieldBlock(
                id="StudentID",
                field_type="INT",
                labels=labels,
                origin_x=origin_x,
                origin_y=origin_y,
                labels_gap=float(params.labels_gap),
                bubbles_gap=float(params.bubbles_gap),
            )
        ],
        custom_labels=[
            CustomLabelGroup(name="StudentID", component_labels=list(labels))
        ],
        output_columns=["StudentID"],
    )
    if class_labels:
        template.field_blocks.append(
            FieldBlock(
                id="Class",
                field_type="INT",
                labels=class_labels,
                origin_x=float(origin_x + params.num_digits * params.labels_gap + params.labels_gap),
                origin_y=origin_y,
                labels_gap=float(params.labels_gap),
                bubbles_gap=float(params.bubbles_gap),
            )
        )
        template.custom_labels.append(
            CustomLabelGroup(name="Class", component_labels=list(class_labels))
        )
        template.output_columns.append("Class")
    save_template(template, template_path)

    config = {
        "dimensions": {
            "display_width": params.page_width,
            "display_height": params.page_height,
            "processing_width": params.page_width,
            "processing_height": params.page_height,
        },
        "outputs": {
            "show_image_level": 0
        },
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    # Create project file for convenience
    omr_root = Path(__file__).resolve().parents[2]
    project = Project(
        name=base_name,
        omrchecker_root=omr_root,
        template_path=template_path,
        config_path=config_path,
        evaluation_path=None,
        input_dir=input_dir,
        output_dir=output_root,
    )
    project_path = project_root / f"{base_name}.omrproj"
    project.save(project_path)

    return GeneratedSheet(
        image_path=image_path,
        template_path=template_path,
        config_path=config_path,
        project_path=project_path,
    )


def render_sheet_image(
    params: IdSheetParams,
) -> tuple[Image.Image, list[str], list[str], int, int, int, int]:
    """Render the ID sheet to a Pillow image and return metadata."""
    image = Image.new("RGB", (params.page_width, params.page_height), "white")
    draw = ImageDraw.Draw(image)

    font = ImageFont.load_default()
    gap = max(0, int(params.marker_gap))

    total_columns = params.num_digits + (params.class_digits if params.include_class else 0)
    extra_class_gap = params.labels_gap if (params.include_class and params.class_digits > 0) else 0
    region_width = max(
        0,
        (total_columns - 1) * params.labels_gap + extra_class_gap + 2 * params.bubble_radius,
    )
    region_height = max(0, 9 * params.bubbles_gap + 2 * params.bubble_radius)

    # Only keep left/top "margin": it locates the bubble-region's top-left corner.
    max_x0 = max(0, params.page_width - region_width)
    max_y0 = max(0, params.page_height - region_height)
    desired_x0 = max(0, min(max_x0, int(params.margin_left)))
    desired_y0 = max(0, min(max_y0, int(params.margin_top)))

    # Compute marker size so that markers can fit around the region at the desired position.
    marker_ratio = max(2, int(params.marker_ratio))
    marker_target_width = max(24, int(round(params.page_width / marker_ratio)))
    left_space = desired_x0
    top_space = desired_y0
    right_space = params.page_width - (desired_x0 + region_width)
    bottom_space = params.page_height - (desired_y0 + region_height)
    horiz_fit = max(0, int(min(left_space - gap, right_space - gap)))
    vert_fit = max(0, int(min(top_space - gap, bottom_space - gap)))

    base_marker = _load_default_marker_image()
    base_w, base_h = base_marker.size

    # Fit by width first, then correct if height doesn't fit.
    candidate_w = max(12, min(marker_target_width, horiz_fit))
    candidate_h = int(round(candidate_w * (base_h / base_w))) if base_w else candidate_w
    if candidate_h > vert_fit and vert_fit > 0:
        candidate_h = max(12, min(candidate_h, vert_fit))
        candidate_w = int(round(candidate_h * (base_w / base_h))) if base_h else candidate_h

    marker_w = max(12, int(candidate_w))
    marker_h = max(12, int(candidate_h))

    # Keep marker dimensions even so marker centers are integer pixels.
    if marker_w % 2 == 1:
        marker_w -= 1
    if marker_h % 2 == 1:
        marker_h -= 1
    marker_w = max(12, marker_w)
    marker_h = max(12, marker_h)

    # Clamp region so that all four markers stay inside the page.
    border = 1
    min_x0 = gap + marker_w + border
    min_y0 = gap + marker_h + border
    max_x0_fit = params.page_width - region_width - gap - marker_w - border
    max_y0_fit = params.page_height - region_height - gap - marker_h - border
    if max_x0_fit < min_x0:
        region_x0 = max(0, min(max_x0, desired_x0))
    else:
        region_x0 = max(min_x0, min(max_x0_fit, desired_x0))
    if max_y0_fit < min_y0:
        region_y0 = max(0, min(max_y0, desired_y0))
    else:
        region_y0 = max(min_y0, min(max_y0_fit, desired_y0))

    marker = base_marker.resize((marker_w, marker_h)).convert("RGB")

    label_start_x = int(round(region_x0 + params.bubble_radius))
    label_start_y = int(round(region_y0 + params.bubble_radius))

    labels: list[str] = []
    class_labels: list[str] = []
    for col in range(params.num_digits):
        label = f"sid{col + 1}"
        labels.append(label)
        column_x = label_start_x + col * params.labels_gap
        for digit in range(10):
            center_y = label_start_y + digit * params.bubbles_gap
            bbox = [
                column_x - params.bubble_radius,
                center_y - params.bubble_radius,
                column_x + params.bubble_radius,
                center_y + params.bubble_radius,
            ]
            draw.ellipse(bbox, outline="black", width=2)
            text = str(digit)
            bbox_text = draw.textbbox((0, 0), text, font=font)
            text_w, text_h = bbox_text[2] - bbox_text[0], bbox_text[3] - bbox_text[1]
            draw.text(
                (column_x + params.bubble_radius + 4, center_y - text_h / 2),
                text,
                fill="black",
                font=font,
            )

    if params.include_class and params.class_digits > 0:
        class_start_x = label_start_x + params.num_digits * params.labels_gap + params.labels_gap
        for col in range(params.class_digits):
            label = f"class{col + 1}"
            class_labels.append(label)
            column_x = class_start_x + col * params.labels_gap
            for digit in range(10):
                center_y = label_start_y + digit * params.bubbles_gap
                bbox = [
                    column_x - params.bubble_radius,
                    center_y - params.bubble_radius,
                    column_x + params.bubble_radius,
                    center_y + params.bubble_radius,
                ]
                draw.ellipse(bbox, outline="black", width=2)
                text = str(digit)
                bbox_text = draw.textbbox((0, 0), text, font=font)
                text_w, text_h = bbox_text[2] - bbox_text[0], bbox_text[3] - bbox_text[1]
                draw.text(
                    (column_x + params.bubble_radius + 4, center_y - text_h / 2),
                    text,
                    fill="black",
                    font=font,
                )

    # Place markers around the bubble region (fill region's four corners).
    if total_columns > 0:
        region_x1 = region_x0 + region_width
        region_y1 = region_y0 + region_height

        positions = [
            (int(round(region_x0 - gap - marker_w)), int(round(region_y0 - gap - marker_h))),
            (int(round(region_x1 + gap)), int(round(region_y0 - gap - marker_h))),
            (int(round(region_x0 - gap - marker_w)), int(round(region_y1 + gap))),
            (int(round(region_x1 + gap)), int(round(region_y1 + gap))),
        ]

        for x, y in positions:
            image.paste(marker, (x, y))

    return image, labels, class_labels, label_start_x, label_start_y, marker_w, marker_h
