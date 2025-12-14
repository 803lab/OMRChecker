"""Wrapper around the OMRChecker CLI."""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
from typing import List, Optional


class OmrRunner:
    """Runs the external OMRChecker process."""

    def __init__(self, omrchecker_root: Path) -> None:
        self.omrchecker_root = Path(omrchecker_root)
        self.outputs_dir = self.omrchecker_root / "outputs"

    def _latest_output_csv(self) -> Optional[Path]:
        files = self.list_output_csvs()
        if not files:
            return None
        return max(files, key=lambda f: f.stat().st_mtime)

    def run(
        self,
        input_dir: Path,
        template_path: Path | None = None,
        config_path: Path | None = None,
        evaluation_path: Path | None = None,
        log_callback=None,
    ) -> Path:
        """
        Run OMRChecker on the given input_dir.
        If log_callback is provided, call it(line: str) for each line of stdout/stderr.
        Return the path to the latest CSV generated in OMRChecker's outputs directory.
        """

        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        python_exec = sys.executable or "python"
        cmd = [python_exec, "main.py", "-i", str(input_dir), "-o", str(self.outputs_dir)]

        # Optional arguments are reserved for future versions of OMRChecker.
        # We still propagate them via environment variables for potential consumers.
        env = None
        if any([template_path, config_path, evaluation_path]):
            env = {**os.environ}
            if template_path:
                env["OMR_TEMPLATE_PATH"] = str(template_path)
            if config_path:
                env["OMR_CONFIG_PATH"] = str(config_path)
            if evaluation_path:
                env["OMR_EVALUATION_PATH"] = str(evaluation_path)

        process = subprocess.Popen(
            cmd,
            cwd=self.omrchecker_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )

        assert process.stdout is not None
        for line in process.stdout:
            if log_callback:
                log_callback(line.rstrip("\n"))

        process.wait()
        if process.returncode != 0:
            raise RuntimeError(f"OMRChecker exited with code {process.returncode}")

        latest_csv = self._latest_output_csv()
        if not latest_csv:
            raise FileNotFoundError("No CSV outputs were found after running OMRChecker")
        return latest_csv

    def list_output_csvs(self) -> List[Path]:
        """Return all CSV files currently in the OMRChecker outputs directory."""
        if not self.outputs_dir.exists():
            return []
        return list(self.outputs_dir.rglob("*.csv"))
