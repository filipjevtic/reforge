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


def test_gate_fails_closed_without_tests_result() -> None:
    # tiny-task requires pass_to_pass; a run that produced no tests result cannot
    # certify the absence of a regression, so the score is gated to zero rather
    # than composed from the remaining scorers.
    spec = load_task(TINY_TASK)
    spec = spec.model_copy(
        update={"scoring": spec.scoring.model_copy(update={"weights": {"judge": 1.0}})}
    )
    result = compose(spec, {"judge": ScorerResult(key="judge", score=1.0, passed=True, detail={})})
    assert result.gated is True
    assert result.final_score == 0.0
    assert result.resolved is False


def test_weights_normalized_over_active_scorers() -> None:
    # A spec whose weights include judge, but only tests ran -> tests gets full weight.
    spec = load_task(TINY_TASK)
    spec = spec.model_copy(
        update={
            "scoring": spec.scoring.model_copy(update={"weights": {"tests": 0.5, "judge": 0.5}})
        }
    )
    result = compose(spec, {"tests": _tests_result(0.6, True, False)})
    assert result.weights_used == {"tests": 1.0}
    assert result.final_score == 0.6


def test_extra_scorer_key_composes() -> None:
    # An arbitrary (plugin) scorer key with a weight is composed like any other.
    spec = load_task(TINY_TASK)
    spec = spec.model_copy(
        update={
            "scoring": spec.scoring.model_copy(update={"weights": {"tests": 0.5, "security": 0.5}})
        }
    )
    results = {
        "tests": _tests_result(1.0, True, True),
        "security": ScorerResult(key="security", score=0.4, passed=True, detail={}),
    }
    result = compose(spec, results)
    assert result.final_score == round(0.5 * 1.0 + 0.5 * 0.4, 4)
