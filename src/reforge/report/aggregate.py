"""Aggregate per-task results into a leaderboard."""

from __future__ import annotations

import statistics

from reforge.report.models import LeaderboardRow, TaskResult, TaskStat
from reforge.report.stats import pareto_frontier, pass_at_k, wilson_interval


def build_task_stats(results: list[TaskResult]) -> list[TaskStat]:
    """Aggregate results by task id, capturing score variance across repeats."""
    groups: dict[str, list[TaskResult]] = {}
    for r in results:
        groups.setdefault(r.task_id, []).append(r)

    stats: list[TaskStat] = []
    for task_id, rs in sorted(groups.items()):
        scores = [r.final_score for r in rs]
        resolved = sum(1 for r in rs if r.resolved)
        stats.append(
            TaskStat(
                task_id=task_id,
                category=rs[0].category,
                runs=len(rs),
                resolved=resolved,
                resolved_rate=round(resolved / len(rs), 4),
                mean_final_score=round(statistics.fmean(scores), 4),
                stdev_final_score=round(statistics.pstdev(scores), 4) if len(scores) > 1 else 0.0,
            )
        )
    return stats


def build_leaderboard(results: list[TaskResult]) -> list[LeaderboardRow]:
    """Group results by (adapter, model) and summarize each group."""
    groups: dict[tuple[str, str | None], list[TaskResult]] = {}
    for r in results:
        groups.setdefault((r.adapter, r.model), []).append(r)

    rows = [_summarize(adapter, model, rs) for (adapter, model), rs in groups.items()]
    rows.sort(key=lambda row: (row.resolved_rate, row.mean_final_score), reverse=True)

    # Pareto frontier is a cross-row property, so mark it once the rows exist.
    if len(rows) > 1:
        flags = pareto_frontier([(row.mean_cost_usd or 0.0, row.resolved_rate) for row in rows])
        for row, on_frontier in zip(rows, flags, strict=True):
            row.on_frontier = on_frontier
    return rows


def _summarize(adapter: str, model: str | None, rs: list[TaskResult]) -> LeaderboardRow:
    n = len(rs)
    resolved = sum(1 for r in rs if r.resolved)
    mean_final = sum(r.final_score for r in rs) / n if n else 0.0

    by_category: dict[str, dict[str, float]] = {}
    for category in {r.category for r in rs}:
        cat_rs = [r for r in rs if r.category == category]
        cat_resolved = sum(1 for r in cat_rs if r.resolved)
        by_category[category] = {
            "tasks": float(len(cat_rs)),
            "resolved_rate": round(cat_resolved / len(cat_rs), 4) if cat_rs else 0.0,
            "mean_final_score": round(sum(r.final_score for r in cat_rs) / len(cat_rs), 4)
            if cat_rs
            else 0.0,
        }

    dep_scores = [
        r.scores["dependency_coverage"].score for r in rs if "dependency_coverage" in r.scores
    ]
    mean_dep = round(sum(dep_scores) / len(dep_scores), 4) if dep_scores else None

    total_cost = round(sum(r.cost_usd or 0.0 for r in rs), 4)

    return LeaderboardRow(
        adapter=adapter,
        model=model,
        tasks=n,
        resolved=resolved,
        resolved_rate=round(resolved / n, 4) if n else 0.0,
        mean_final_score=round(mean_final, 4),
        by_category=by_category,
        mean_dep_coverage=mean_dep,
        total_cost_usd=total_cost,
        mean_duration_s=round(sum(r.duration_s for r in rs) / n, 2) if n else 0.0,
        resolved_rate_ci=wilson_interval(resolved, n) if n else None,
        pass_at_k=_pass_at_k_over_tasks(rs),
        mean_cost_usd=round(total_cost / n, 6) if n else None,
    )


def _pass_at_k_over_tasks(rs: list[TaskResult]) -> dict[int, float]:
    """pass@k averaged over tasks, for k in 1..max repeats. Empty unless repeated.

    Each task contributes ``pass_at_k(n_attempts, n_resolved, k)``; the row value is
    the mean across tasks. Only meaningful when at least one task was run more than
    once, so an unrepeated run returns ``{}``.
    """
    by_task: dict[str, list[TaskResult]] = {}
    for r in rs:
        by_task.setdefault(r.task_id, []).append(r)
    max_n = max((len(v) for v in by_task.values()), default=0)
    if max_n <= 1:
        return {}
    out: dict[int, float] = {}
    for k in range(1, max_n + 1):
        per_task = [pass_at_k(len(v), sum(1 for r in v if r.resolved), k) for v in by_task.values()]
        out[k] = round(sum(per_task) / len(per_task), 4) if per_task else 0.0
    return out
