"""Load and parse task specifications from disk."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from reforge.spec.models import TaskSpec
from reforge.utils.errors import SpecError

TASK_FILE = "task.yaml"


def load_task(task_dir: str | Path) -> TaskSpec:
    """Load a single task from its directory.

    ``task_dir`` must contain ``task.yaml``. The returned spec remembers its
    directory so downstream code can resolve the Dockerfile, verifier, and gold
    paths relative to it.
    """
    task_dir = Path(task_dir).resolve()
    task_file = task_dir / TASK_FILE
    if not task_file.is_file():
        raise SpecError(f"no {TASK_FILE} found in {task_dir}")

    try:
        raw = yaml.safe_load(task_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecError(f"{task_file}: invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise SpecError(f"{task_file}: expected a mapping at the top level")

    try:
        spec = TaskSpec.model_validate(raw)
    except ValidationError as exc:
        raise SpecError(f"{task_file}: {_format_validation_error(exc)}") from exc

    return spec.with_dir(task_dir)


def load_dataset_dir(dataset_dir: str | Path) -> list[TaskSpec]:
    """Load every task directory directly under ``dataset_dir``.

    A directory is a task if it contains ``task.yaml``. Results are sorted by id
    so runs are deterministic.
    """
    dataset_dir = Path(dataset_dir).resolve()
    if not dataset_dir.is_dir():
        raise SpecError(f"dataset directory not found: {dataset_dir}")

    tasks = [
        load_task(child) for child in sorted(dataset_dir.iterdir()) if (child / TASK_FILE).is_file()
    ]
    if not tasks:
        raise SpecError(f"no tasks (directories with {TASK_FILE}) found in {dataset_dir}")

    _check_unique_ids(tasks)
    return tasks


def _check_unique_ids(tasks: list[TaskSpec]) -> None:
    seen: dict[str, Path] = {}
    for task in tasks:
        if task.id in seen:
            raise SpecError(f"duplicate task id '{task.id}' in {task.task_dir} and {seen[task.id]}")
        seen[task.id] = task.task_dir


def _format_validation_error(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "(root)"
        lines.append(f"{loc}: {err['msg']}")
    return "; ".join(lines)
