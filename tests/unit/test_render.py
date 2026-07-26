"""Smoke tests for the decision-grade render helpers."""

from __future__ import annotations

import json

from rich.console import Console

from reforge.report.aggregate import build_leaderboard
from reforge.report.models import RunReport, TaskResult
from reforge.report.render import (
    LEADERBOARD_SCHEMA,
    render_cost_quality,
    render_leaderboard_json,
    render_markdown,
    render_pass_at_k,
)


def _r(task: str, model: str, resolved: bool, cost: float) -> TaskResult:
    return TaskResult(
        task_id=task,
        category="new_feature",
        adapter="api-agent",
        model=model,
        resolved=resolved,
        final_score=1.0 if resolved else 0.0,
        cost_usd=cost,
    )


def _report(results: list[TaskResult], repeats: int = 1) -> RunReport:
    return RunReport(
        run_id="t",
        tool_version="0",
        dataset="d",
        adapter="(multiple)",
        repeats=repeats,
        results=results,
        leaderboard=build_leaderboard(results),
    )


def test_cost_quality_and_markdown_render() -> None:
    results = [
        _r("a", "cheap", True, 0.01),
        _r("b", "cheap", True, 0.01),
        _r("a", "pricey", False, 1.0),
        _r("b", "pricey", False, 1.0),
    ]
    report = _report(results)
    # Should not raise, and markdown should mention the frontier section.
    render_cost_quality(report, Console(file=open("/dev/null", "w")))  # noqa: SIM115
    md = render_markdown(report)
    assert "Cost vs quality" in md
    assert "dominated" in md


def test_leaderboard_json_export() -> None:
    report = _report([_r("a", "m", True, 0.0)])
    payload = json.loads(render_leaderboard_json(report))
    assert payload["schema"] == LEADERBOARD_SCHEMA
    assert payload["rows"][0]["model"] == "m"
    assert payload["rows"][0]["resolved_rate"] == 1.0


def test_pass_at_k_render_smoke() -> None:
    results = [
        _r("a", "m", True, 0.0),
        _r("a", "m", False, 0.0),
    ]
    report = _report(results, repeats=2)
    render_pass_at_k(report, Console(file=open("/dev/null", "w")))  # noqa: SIM115
