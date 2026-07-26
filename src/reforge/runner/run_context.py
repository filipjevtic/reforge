"""Run directory layout and per-run context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunContext:
    """Identifiers and paths shared across every task in a run."""

    run_id: str
    run_dir: Path
    adapter: str
    model: str | None
    no_judge: bool = False
    judge_model: str | None = None
    judge_samples: int = 1

    def _task_path(self, task_id: str, attempt: int = 0) -> Path:
        path = self.run_dir / "tasks" / task_id
        if attempt > 0:
            path = path / f"run-{attempt}"
        return path

    def task_dir(self, task_id: str, attempt: int = 0) -> Path:
        path = self._task_path(task_id, attempt)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def result_file(self, task_id: str, attempt: int = 0) -> Path:
        """Path to a task's result.json without creating the directory (for resume)."""
        return self._task_path(task_id, attempt) / "result.json"

    @property
    def run_json(self) -> Path:
        return self.run_dir / "run.json"

    @property
    def report_json(self) -> Path:
        return self.run_dir / "report.json"


def make_run_context(
    *,
    run_id: str,
    output_root: Path,
    adapter: str,
    model: str | None,
    no_judge: bool = False,
    judge_model: str | None = None,
    judge_samples: int = 1,
) -> RunContext:
    run_dir = output_root / run_id
    (run_dir / "tasks").mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        adapter=adapter,
        model=model,
        no_judge=no_judge,
        judge_model=judge_model,
        judge_samples=judge_samples,
    )
