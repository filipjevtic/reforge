"""Unit tests for the resume load/skip logic."""

from __future__ import annotations

from pathlib import Path

from reforge.report.models import TaskResult
from reforge.runner.orchestrator import _load_completed
from reforge.runner.run_context import make_run_context


def _ctx(tmp_path: Path):  # type: ignore[no-untyped-def]
    return make_run_context(run_id="r", output_root=tmp_path, adapter="gold", model=None)


def _write(ctx, task_id: str, attempt: int, result: TaskResult) -> None:  # type: ignore[no-untyped-def]
    d = ctx.task_dir(task_id, attempt)
    (d / "result.json").write_text(result.model_dump_json(), encoding="utf-8")


def test_load_completed_returns_scored_result(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _write(ctx, "a", 0, TaskResult(task_id="a", category="c", adapter="gold", resolved=True))
    loaded = _load_completed(ctx, "a", 0)
    assert loaded is not None
    assert loaded.resolved is True


def test_load_completed_missing_returns_none(tmp_path: Path) -> None:
    assert _load_completed(_ctx(tmp_path), "nope", 0) is None


def test_load_completed_errored_is_retried(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _write(ctx, "a", 0, TaskResult(task_id="a", category="c", adapter="gold", error="boom"))
    # An errored result is treated as unfinished so resume re-runs it.
    assert _load_completed(ctx, "a", 0) is None


def test_result_file_does_not_create_dir(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    path = ctx.result_file("ghost", 0)
    assert not path.parent.exists()  # checking must not litter empty task dirs
