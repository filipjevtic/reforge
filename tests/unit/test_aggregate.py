"""Tests for leaderboard aggregation."""

from __future__ import annotations

from reforge.report.aggregate import build_leaderboard
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
