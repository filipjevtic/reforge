"""Tests for leaderboard aggregation."""

from __future__ import annotations

from reforge.report.aggregate import build_leaderboard, build_task_stats
from reforge.report.models import SubScore, TaskResult


def _result(task_id: str, category: str, resolved: bool, score: float) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        category=category,
        adapter="noop",
        model="m1",
        resolved=resolved,
        final_score=score,
        scores={"tests": SubScore(score=score, passed=resolved)},
        duration_s=1.0,
    )


def test_leaderboard_summarizes_group() -> None:
    results = [
        _result("a", "new_feature", True, 1.0),
        _result("b", "new_feature", False, 0.0),
        _result("c", "replication", True, 0.5),
    ]
    board = build_leaderboard(results)
    assert len(board) == 1
    row = board[0]
    assert row.tasks == 3
    assert row.resolved == 2
    assert row.resolved_rate == round(2 / 3, 4)
    assert "new_feature" in row.by_category
    assert row.by_category["new_feature"]["resolved_rate"] == 0.5


def test_leaderboard_splits_by_adapter_model() -> None:
    results = [
        _result("a", "new_feature", True, 1.0),
    ]
    results.append(
        TaskResult(
            task_id="b",
            category="new_feature",
            adapter="gold",
            model="m2",
            resolved=True,
            final_score=1.0,
        )
    )
    board = build_leaderboard(results)
    assert len(board) == 2


def test_task_stats_variance() -> None:
    # Same task run three times with differing scores -> non-zero stdev.
    results = [
        _result("a", "new_feature", True, 1.0),
        _result("a", "new_feature", False, 0.0),
        _result("a", "new_feature", True, 1.0),
    ]
    stats = build_task_stats(results)
    assert len(stats) == 1
    s = stats[0]
    assert s.runs == 3
    assert s.resolved == 2
    assert s.resolved_rate == round(2 / 3, 4)
    assert s.mean_final_score == round(2 / 3, 4)
    assert s.stdev_final_score > 0.0


def test_task_stats_single_run_zero_variance() -> None:
    stats = build_task_stats([_result("a", "new_feature", True, 1.0)])
    assert stats[0].stdev_final_score == 0.0


def test_leaderboard_has_ci_and_no_pass_at_k_without_repeats() -> None:
    results = [
        _result("a", "new_feature", True, 1.0),
        _result("b", "new_feature", False, 0.0),
        _result("c", "replication", True, 0.5),
    ]
    row = build_leaderboard(results)[0]
    assert row.resolved_rate_ci is not None
    lo, hi = row.resolved_rate_ci
    assert lo < row.resolved_rate < hi
    assert row.pass_at_k == {}  # no repeats


def test_leaderboard_pass_at_k_with_repeats() -> None:
    # One task run 3x, resolved twice -> pass@1 == 2/3, pass@3 == 1.0.
    results = [
        _result("a", "new_feature", True, 1.0),
        _result("a", "new_feature", False, 0.0),
        _result("a", "new_feature", True, 1.0),
    ]
    row = build_leaderboard(results)[0]
    assert row.pass_at_k[1] == round(2 / 3, 4)
    assert row.pass_at_k[3] == 1.0


def _priced(task_id: str, adapter: str, model: str, resolved: bool, cost: float) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        category="new_feature",
        adapter=adapter,
        model=model,
        resolved=resolved,
        final_score=1.0 if resolved else 0.0,
        cost_usd=cost,
    )


def test_pareto_flags_dominated_model() -> None:
    # cheap+good model dominates an expensive+worse one.
    results = [
        _priced("a", "x", "cheap-good", True, 0.01),
        _priced("b", "x", "cheap-good", True, 0.01),
        _priced("a", "y", "pricey-bad", False, 1.00),
        _priced("b", "y", "pricey-bad", False, 1.00),
    ]
    rows = {r.model: r for r in build_leaderboard(results)}
    assert rows["cheap-good"].on_frontier is True
    assert rows["pricey-bad"].on_frontier is False
    assert rows["cheap-good"].mean_cost_usd == 0.01
