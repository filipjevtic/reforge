"""End-to-end harness tests (require Docker).

These are the keystone checks: the gold solution must resolve the task, and the
noop adapter must not. Together they prove the harness measures real work rather
than rubber-stamping every run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reforge.runner.run_context import make_run_context
from reforge.runner.task_runner import run_task
from reforge.runtime.docker_runtime import DockerRuntime
from reforge.spec import load_task

pytestmark = pytest.mark.docker

TINY_TASK = Path(__file__).parent.parent / "fixtures" / "tiny-task"


@pytest.fixture(scope="module")
def runtime() -> DockerRuntime:
    rt = DockerRuntime()
    if not rt.is_available():
        pytest.skip("Docker daemon not available")
    return rt


def test_gold_resolves(runtime: DockerRuntime, tmp_path: Path) -> None:
    spec = load_task(TINY_TASK)
    ctx = make_run_context(run_id="it-gold", output_root=tmp_path, adapter="gold", model=None)
    result = run_task(spec, ctx, runtime)
    assert result.error is None, result.error
    assert result.resolved is True
    assert result.final_score == 1.0
    assert result.scores["tests"].detail["pass_to_pass_ok"] is True


def test_noop_does_not_resolve(runtime: DockerRuntime, tmp_path: Path) -> None:
    spec = load_task(TINY_TASK)
    ctx = make_run_context(run_id="it-noop", output_root=tmp_path, adapter="noop", model=None)
    result = run_task(spec, ctx, runtime)
    assert result.error is None, result.error
    assert result.resolved is False
    assert result.scores["tests"].detail["f2p_passed"] == 0


def test_command_adapter_resolves(runtime: DockerRuntime, tmp_path: Path) -> None:
    """The generic BYO command adapter should resolve the task end to end."""
    spec = load_task(TINY_TASK)
    ctx = make_run_context(run_id="it-command", output_root=tmp_path, adapter="command", model=None)
    # Implement add() by replacing its body; sed avoids fragile shell quoting.
    fix = "sed -i 's/raise NotImplementedError/return a + b/' calc.py"
    result = run_task(spec, ctx, runtime, adapter_config={"command": fix})
    assert result.error is None, result.error
    assert result.resolved is True


REPLICATION_TASK = Path(__file__).parent.parent.parent / "tasks" / "replication-staging-env"


def test_dependency_scorer_reports_misses(runtime: DockerRuntime, tmp_path: Path) -> None:
    """noop on the replication task should miss every declared dependency."""
    spec = load_task(REPLICATION_TASK)
    ctx = make_run_context(run_id="it-dep", output_root=tmp_path, adapter="noop", model=None)
    result = run_task(spec, ctx, runtime)
    assert result.error is None, result.error
    assert result.resolved is False
    dep = result.scores["dependency_coverage"].detail
    # nothing was created, so all required deps are missed
    assert set(dep["missed"]) == set(dep["required"])
