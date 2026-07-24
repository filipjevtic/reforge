"""Aggregate per-task results into a leaderboard."""

from __future__ import annotations

from reforge.report.models import LeaderboardRow, TaskResult


def build_leaderboard(results: list[TaskResult]) -> list[LeaderboardRow]:
    """Group results by (adapter, model) and summarize each group."""
    groups: dict[tuple[str, str | None], list[TaskResult]] = {}
    for r in results:
        groups.setdefault((r.adapter, r.model), []).append(r)

    rows = [_summarize(adapter, model, rs) for (adapter, model), rs in groups.items()]
    rows.sort(key=lambda row: (row.resolved_rate, row.mean_final_score), reverse=True)
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

    return LeaderboardRow(
        adapter=adapter,
        model=model,
        tasks=n,
        resolved=resolved,
        resolved_rate=round(resolved / n, 4) if n else 0.0,
        mean_final_score=round(mean_final, 4),
        by_category=by_category,
        mean_dep_coverage=mean_dep,
        total_cost_usd=round(sum(r.cost_usd or 0.0 for r in rs), 4),
        mean_duration_s=round(sum(r.duration_s for r in rs) / n, 2) if n else 0.0,
    )
