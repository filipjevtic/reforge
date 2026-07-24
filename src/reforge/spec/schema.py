"""Export the task schema as JSON Schema for editor autocompletion and docs."""

from __future__ import annotations

import json
from typing import Any

from reforge.spec.models import TaskSpec


def task_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for a ``task.yaml`` document."""
    return TaskSpec.model_json_schema()


def dump_task_json_schema(indent: int = 2) -> str:
    """Return the task JSON Schema as a formatted string."""
    return json.dumps(task_json_schema(), indent=indent, sort_keys=True)
