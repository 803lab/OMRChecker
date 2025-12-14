"""Project model used by the GUI application."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Project:
    """Encapsulates user project settings."""

    name: str
    omrchecker_root: Path
    template_path: Path
    config_path: Optional[Path]
    evaluation_path: Optional[Path]
    input_dir: Path
    output_dir: Path

    @classmethod
    def load(cls, path: Path) -> "Project":
        """Load a project definition from a JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        """Build a Project from a dictionary."""
        return cls(
            name=data.get("name", "Untitled Project"),
            omrchecker_root=Path(data["omrchecker_root"]),
            template_path=Path(data["template_path"]),
            config_path=Path(data["config_path"]) if data.get("config_path") else None,
            evaluation_path=Path(data["evaluation_path"])
            if data.get("evaluation_path")
            else None,
            input_dir=Path(data["input_dir"]),
            output_dir=Path(data["output_dir"]),
        )

    def to_dict(self) -> dict:
        """Serialize the project to a JSON-friendly dict."""
        return {
            "name": self.name,
            "omrchecker_root": str(self.omrchecker_root),
            "template_path": str(self.template_path),
            "config_path": str(self.config_path) if self.config_path else None,
            "evaluation_path": (
                str(self.evaluation_path) if self.evaluation_path else None
            ),
            "input_dir": str(self.input_dir),
            "output_dir": str(self.output_dir),
        }

    def save(self, path: Path) -> None:
        """Persist the project definition to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
