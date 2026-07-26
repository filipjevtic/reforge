"""Semantic validation beyond what the schema can express.

The pydantic models guarantee shape. This module checks the things that need the
filesystem: that the Dockerfile exists, the verifier entrypoint is present, the
gold solution is there, and that a task which asks for scoring actually supplies
the inputs those scorers need.
"""

from __future__ import annotations

from reforge.spec.models import TaskSpec

GOLD_PATCH = "gold/solution.patch"


def validate_task(spec: TaskSpec) -> list[str]:
    """Return a list of human-readable problems. Empty list means valid."""
    problems: list[str] = []
    task_dir = spec.task_dir

    dockerfile = task_dir / spec.environment.dockerfile
    if not dockerfile.is_file():
        problems.append(f"environment.dockerfile not found: {dockerfile}")

    entrypoint = task_dir / spec.verification.entrypoint
    if not entrypoint.is_file():
        problems.append(f"verification.entrypoint not found: {entrypoint}")

    if not (task_dir / GOLD_PATCH).is_file():
        problems.append(f"missing gold solution: {task_dir / GOLD_PATCH}")

    if spec.source.type.value == "local" and spec.source.path:
        source_path = task_dir / spec.source.path
        if not source_path.exists():
            problems.append(f"source.path not found: {source_path}")

    if not spec.verification.fail_to_pass:
        problems.append("verification.fail_to_pass is empty; nothing proves the task was done")

    # Guard against weights that reference a scorer the task never configured.
    weights = spec.scoring.weights
    if weights.get("dependency_coverage", 0) > 0 and spec.dependency_coverage.is_empty():
        problems.append(
            "scoring.weights.dependency_coverage > 0 but dependency_coverage.required is empty"
        )
    if weights.get("judge", 0) > 0 and spec.rubric.is_empty():
        problems.append("scoring.weights.judge > 0 but rubric.criteria is empty")

    # An egress allowlist does nothing without a network; catch the silent no-op.
    if spec.environment.allowed_hosts and spec.resources.network.value == "none":
        problems.append(
            "environment.allowed_hosts is set but resources.network is 'none'; "
            "set a network (e.g. bridge) for the allowlist to take effect"
        )

    return problems
