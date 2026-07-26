"""Combine scorer results into one task score.

Weights come from the task's ``scoring.weights`` block and are normalized over
whichever scorers actually ran (so ``--no-judge`` reweights the rest instead of
leaving a gap). A pass_to_pass regression is disqualifying: it zeroes the final
score while leaving the sub-scores visible for debugging.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from reforge.scoring.base import ScorerResult
from reforge.spec.models import TaskSpec


@dataclass
class TaskScore:
    final_score: float
    resolved: bool
    weights_used: dict[str, float] = field(default_factory=dict)
    subscores: dict[str, ScorerResult] = field(default_factory=dict)
    gated: bool = False  # True if a regression zeroed the score


def compose(spec: TaskSpec, results: dict[str, ScorerResult]) -> TaskScore:
    weights_cfg = spec.scoring.weights

    active = {k: weights_cfg[k] for k in results if weights_cfg.get(k, 0) > 0}
    total_weight = sum(active.values())
    weights_used = {k: w / total_weight for k, w in active.items()} if total_weight > 0 else {}

    final = sum(results[k].score * w for k, w in weights_used.items())

    tests_result = results.get("tests")
    resolved = tests_result.passed if tests_result is not None else False

    # The regression gate fails closed: if the task requires pass_to_pass but no
    # usable tests result exists (or the flag is absent), we cannot certify the
    # absence of a regression, so the score is gated to zero.
    gated = False
    if spec.scoring.gate.require_pass_to_pass:
        p2p_ok = tests_result.detail.get("pass_to_pass_ok", False) if tests_result else False
        if not p2p_ok:
            final = 0.0
            gated = True

    return TaskScore(
        final_score=round(final, 4),
        resolved=resolved,
        weights_used=weights_used,
        subscores=results,
        gated=gated,
    )
