"""Data models for OMR templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Literal

FieldType = Literal["INT", "MCQ4", "MCQ5", "BOOLEAN"]


@dataclass
class PageSettings:
    """Page dimensions for a template."""

    width: int
    height: int


@dataclass
class FieldBlock:
    """Represents a single OMR field block."""

    id: str
    field_type: FieldType
    labels: List[str]
    origin_x: float
    origin_y: float
    labels_gap: float
    bubbles_gap: float


@dataclass
class CustomLabelGroup:
    """Groups labels into a logical column."""

    name: str
    component_labels: List[str]


@dataclass
class TemplateModel:
    """Complete template definition."""

    page: PageSettings
    bubble_dimensions: tuple[int, int] | None = None
    pre_processors: List[dict[str, Any]] = field(default_factory=list)
    field_blocks: List[FieldBlock] = field(default_factory=list)
    custom_labels: List[CustomLabelGroup] = field(default_factory=list)
    output_columns: List[str] = field(default_factory=list)
