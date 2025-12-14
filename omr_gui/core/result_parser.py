"""Helpers to parse OMRChecker CSV outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


@dataclass
class OmrRecord:
    """Single row extracted from an OMR result CSV."""

    image_name: str
    student_id: str
    class_code: str
    raw_row: Dict[str, Any]


def parse_omr_csv(
    csv_path: Path,
    student_id_column: str = "StudentID",
    class_column: str = "Class",
) -> List[OmrRecord]:
    """Parse a CSV file into a list of OmrRecord objects."""
    df = pd.read_csv(csv_path)
    records: List[OmrRecord] = []
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        image_name = str(
            row_dict.get("image_name") or row_dict.get("image") or ""
        ).strip()
        student_id = str(row_dict.get(student_id_column, "") or "").strip()
        class_code = str(row_dict.get(class_column, "") or "").strip()
        records.append(
            OmrRecord(
                image_name=image_name,
                student_id=student_id,
                class_code=class_code,
                raw_row=row_dict,
            )
        )
    return records
