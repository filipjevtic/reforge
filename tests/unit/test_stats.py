"""Tests for the decision-grade statistics helpers."""

from __future__ import annotations

from reforge.report.stats import (
    pareto_frontier,
    pass_at_k,
    two_proportion_pvalue,
    wilson_interval,
)


def test_wilson_known_value() -> None:
    lo, hi = wilson_interval(8, 10)
    # Classic 8/10 Wilson 95% interval is roughly [0.49, 0.94].
    assert 0.48 <= lo <= 0.50
    assert 0.93 <= hi <= 0.95


def test_wilson_extremes_stay_in_range() -> None:
    lo, _ = wilson_interval(0, 5)
    assert lo == 0.0
    _, hi = wilson_interval(5, 5)
    assert hi == 1.0


def test_wilson_zero_n() -> None:
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_pass_at_k() -> None:
    assert pass_at_k(5, 2, 1) == 0.4  # 2 of 5 pass -> pass@1 == c/n
    assert pass_at_k(5, 0, 3) == 0.0  # nothing passed
    assert pass_at_k(5, 1, 5) == 1.0  # any k==n subset includes the one pass
    # With one pass among five, pass@1 is 1/5; pass@4 must contain it more often.
    assert pass_at_k(5, 1, 4) > pass_at_k(5, 1, 1)


def test_two_proportion_pvalue() -> None:
    assert two_proportion_pvalue(100, 100, 0, 100) < 0.001  # clearly different
    assert two_proportion_pvalue(50, 100, 50, 100) == 1.0  # identical
    assert two_proportion_pvalue(0, 0, 1, 1) == 1.0  # empty sample -> no signal


def test_pareto_frontier() -> None:
    # (cost, quality): B is strictly dominated by A (cheaper and better).
    a = (1.0, 0.9)
    b = (2.0, 0.5)
    c = (3.0, 0.95)  # pricier but best quality -> on frontier
    flags = pareto_frontier([a, b, c])
    assert flags == [True, False, True]


def test_pareto_ties_both_kept() -> None:
    flags = pareto_frontier([(1.0, 0.8), (1.0, 0.8)])
    assert flags == [True, True]
