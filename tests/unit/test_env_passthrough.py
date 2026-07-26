"""Tests for credentialed-task env passthrough (allowlist intersection)."""

from __future__ import annotations

from reforge.runner.task_runner import _resolve_task_env
from reforge.spec.models import Environment, Source, TaskSpec, Verification


class _FakeLog:
    def __init__(self) -> None:
        self.warnings: list[dict] = []

    def warning(self, event: str, **kw: object) -> None:
        self.warnings.append({"event": event, **kw})


def _spec(allowed: list[str]) -> TaskSpec:
    return TaskSpec(
        id="t",
        category="cloud-infra",
        title="t",
        instruction="do",
        source=Source(type="local", path="src"),
        environment=Environment(allowed_env=allowed),
        verification=Verification(entrypoint="verifier/run_tests.sh", fail_to_pass=["a::b"]),
    )


def test_only_allowlisted_keys_forwarded() -> None:
    log = _FakeLog()
    env = _resolve_task_env(
        _spec(["AWS_REGION"]),
        {"AWS_REGION": "us-east-1", "SECRET_TOKEN": "nope"},
        log,
    )
    assert env == {"AWS_REGION": "us-east-1"}
    assert log.warnings and log.warnings[0]["keys"] == ["AWS_REGION"]


def test_nothing_forwarded_without_allowlist() -> None:
    assert _resolve_task_env(_spec([]), {"AWS_REGION": "us-east-1"}, _FakeLog()) == {}


def test_no_requested_env_is_empty() -> None:
    assert _resolve_task_env(_spec(["AWS_REGION"]), None, _FakeLog()) == {}
