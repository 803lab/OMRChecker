"""Utilities to load and save OMR template JSON files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, List

from .template_model import (
    CustomLabelGroup,
    FieldBlock,
    FieldType,
    PageSettings,
    TemplateModel,
)

FIELD_TYPE_FROM_OMR = {
    "QTYPE_INT": "INT",
    "QTYPE_MCQ4": "MCQ4",
    "QTYPE_MCQ5": "MCQ5",
    "QTYPE_BOOL": "BOOLEAN",
    "QTYPE_BOOLEAN": "BOOLEAN",
}

FIELD_TYPE_TO_OMR = {
    "INT": "QTYPE_INT",
    "MCQ4": "QTYPE_MCQ4",
    "MCQ5": "QTYPE_MCQ5",
    "BOOLEAN": "QTYPE_BOOL",
}


def _expand_labels(labels: Iterable[str]) -> List[str]:
    expanded: List[str] = []
    for label in labels:
        match = re.match(r"([a-zA-Z_]+)(\d+)\.\.(\d+)", label)
        if match:
            prefix, start, end = match.groups()
            start_idx = int(start)
            end_idx = int(end)
            step = 1 if end_idx >= start_idx else -1
            for idx in range(start_idx, end_idx + step, step):
                expanded.append(f"{prefix}{idx}")
        else:
            expanded.append(label)
    return expanded


def _map_field_type_from_omr(raw_type: str | None) -> FieldType:
    if raw_type is None:
        return "INT"
    return FIELD_TYPE_FROM_OMR.get(raw_type, "INT")  # type: ignore[return-value]


def _map_field_type_to_omr(field_type: FieldType) -> str:
    return FIELD_TYPE_TO_OMR.get(field_type, "QTYPE_INT")


def load_template(path: Path) -> TemplateModel:
    """Load a template.json file into a TemplateModel."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    page_dimensions = raw.get("pageDimensions") or raw.get("page_dimensions") or [0, 0]
    page = PageSettings(width=int(page_dimensions[0]), height=int(page_dimensions[1]))
    bubble_dims = raw.get("bubbleDimensions")
    bubble_dimensions_tuple = (
        (int(bubble_dims[0]), int(bubble_dims[1])) if bubble_dims else None
    )
    model = TemplateModel(page=page, bubble_dimensions=bubble_dimensions_tuple)
    model.pre_processors = list(raw.get("preProcessors", []) or [])

    for block_id, block_data in raw.get("fieldBlocks", {}).items():
        origin = block_data.get("origin", [0, 0])
        labels_raw = block_data.get("fieldLabels", [])
        labels = _expand_labels(labels_raw)
        model.field_blocks.append(
            FieldBlock(
                id=block_id,
                field_type=_map_field_type_from_omr(block_data.get("fieldType")),
                labels=labels,
                origin_x=float(origin[0]),
                origin_y=float(origin[1]),
                labels_gap=float(block_data.get("labelsGap", 0)),
                bubbles_gap=float(block_data.get("bubblesGap", 0)),
            )
        )

    custom_labels = raw.get("customLabels", {}) or {}
    for name, components in custom_labels.items():
        expanded = _expand_labels(components)
        model.custom_labels.append(
            CustomLabelGroup(name=name, component_labels=expanded)
        )

    output_columns = raw.get("outputColumns", [])
    model.output_columns = list(output_columns)

    return model


def save_template(model: TemplateModel, path: Path) -> None:
    """Write a TemplateModel to a JSON file."""
    data: dict = {
        "pageDimensions": [model.page.width, model.page.height],
        "preProcessors": list(model.pre_processors or []),
        "fieldBlocks": {},
    }

    for block in model.field_blocks:
        data["fieldBlocks"][block.id] = {
            "fieldType": _map_field_type_to_omr(block.field_type),
            "fieldLabels": block.labels,
            # OMRChecker schema expects integer origins.
            "origin": [int(round(block.origin_x)), int(round(block.origin_y))],
            "labelsGap": block.labels_gap,
            "bubblesGap": block.bubbles_gap,
        }

    if model.custom_labels:
        data["customLabels"] = {
            group.name: group.component_labels for group in model.custom_labels
        }
    if model.output_columns:
        data["outputColumns"] = model.output_columns
    if model.bubble_dimensions:
        data["bubbleDimensions"] = [model.bubble_dimensions[0], model.bubble_dimensions[1]]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
