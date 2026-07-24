"""Tests for score composition and gating."""

from __future__ import annotations

from reforge.scoring.base import ScorerResult
from reforge.scoring.compose import compose
from reforge.spec import load_task
from tests.unit.test_spec import TINY_TASK


def _tests_result(score: float, p2p_ok: bool, passed: bool) -> ScorerResult:
    return ScorerResult(
        key="tests",
        score=score,
        passed=passed,
        detail={"pass_to_pass_ok": p2p_ok},
    )


def test_tests_only_resolved() -> None:
    spec = load_task(TINY_TASK)
    result = compose(spec, {"tests": _tests_result(1.0, True, True)})
    assert result.resolved is True
    assert result.final_score == 1.0
    assert result.gated is False


def test_regression_gates_to_zero() -> None:
    spec = load_task(TINY_TASK)
    result = compose(spec, {"tests": _tests_result(1.0, False, False)})
    assert result.final_score == 0.0
    assert result.gated is True


def test_weights_normalized_over_active_scorers() -> None:
    # A spec whose weights include judge, but only tests ran -> tests gets full weight.
    spec = load_task(TINY_TASK)
    spec = spec.model_copy(
        update={
            "scoring": spec.scoring.model_copy(
                update={
                    "weights": spec.scoring.weights.model_copy(
                        update={"tests": 0.5, "dependency_coverage": 0.0, "judge": 0.5}
                    )
                }
            )
        }
    )
    result = compose(spec, {"tests": _tests_result(0.6, True, False)})
    assert result.weights_used == {"tests": 1.0}
    assert result.final_score == 0.6
