"""Statistics that turn raw leaderboard numbers into a defensible decision.

Everything here is a pure function over counts, so it is trivial to unit-test and
carries no dependency beyond the standard library. The report layer uses these to
attach confidence intervals, pass@k, a significance note, and a cost/quality
frontier to the leaderboard.
"""

from __future__ import annotations

import math


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (default 95%).

    Preferred over the normal approximation because it stays inside [0, 1] and is
    still sensible at the extremes (0% and 100%) and for small n, which is exactly
    where a benchmark with few tasks lives.
    """
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / denom
    lo = max(0.0, center - margin)
    hi = min(1.0, center + margin)
    return (round(lo, 4), round(hi, 4))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased pass@k estimator (Chen et al., HumanEval).

    With ``n`` samples of which ``c`` passed, the probability that a random subset
    of ``k`` contains at least one pass is ``1 - C(n-c, k) / C(n, k)``. This is the
    standard estimator and avoids the bias of ``(c/n)**k``-style shortcuts.
    """
    if k <= 0 or n <= 0:
        return 0.0
    if c <= 0:
        return 0.0
    if k > n:
        k = n
    if n - c < k:
        return 1.0  # too few failures to fill a k-subset without a pass
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def two_proportion_pvalue(s1: int, n1: int, s2: int, n2: int) -> float:
    """Two-sided p-value for H0: two resolved rates are equal (pooled z-test).

    A large-sample approximation; with few tasks the Wilson intervals are the more
    reliable read. Returned rounded, clamped to [0, 1].
    """
    if n1 <= 0 or n2 <= 0:
        return 1.0
    p1, p2 = s1 / n1, s2 / n2
    pool = (s1 + s2) / (n1 + n2)
    se = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = abs(p1 - p2) / se
    # Two-sided p = 2 * (1 - Phi(z)); Phi via the error function.
    p = 2 * (1 - _phi(z))
    return round(max(0.0, min(1.0, p)), 4)


def _phi(x: float) -> float:
    """Standard-normal CDF."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def pareto_frontier(points: list[tuple[float, float]]) -> list[bool]:
    """Mark each ``(cost, quality)`` point that is not dominated by another.

    Lower cost is better and higher quality is better. A point is dominated when
    some other point is at least as cheap and at least as good, and strictly better
    on at least one axis. Ties (identical cost and quality) both stay on the
    frontier.
    """
    flags: list[bool] = []
    for i, (ci, qi) in enumerate(points):
        dominated = False
        for j, (cj, qj) in enumerate(points):
            if i == j:
                continue
            if cj <= ci and qj >= qi and (cj < ci or qj > qi):
                dominated = True
                break
        flags.append(not dominated)
    return flags
