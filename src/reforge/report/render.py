"""Render a run report as a rich table, Markdown, or JSON."""

from __future__ import annotations

import json

from rich.console import Console
from rich.table import Table

from reforge.report.models import LeaderboardRow, RunReport
from reforge.report.stats import two_proportion_pvalue

#: Version of the shareable leaderboard export format (``render_leaderboard_json``).
LEADERBOARD_SCHEMA = "reforge-leaderboard/v1"


def render_json(report: RunReport) -> str:
    return report.model_dump_json(indent=2)


def render_leaderboard_json(report: RunReport) -> str:
    """A stable, shareable leaderboard-only export (rows plus a small envelope)."""
    payload = {
        "schema": LEADERBOARD_SCHEMA,
        "tool_version": report.tool_version,
        "dataset": report.dataset,
        "rows": [row.model_dump() for row in report.leaderboard],
    }
    return json.dumps(payload, indent=2)


def _fmt_rate_ci(row: LeaderboardRow) -> str:
    """e.g. ``67% [39-86%]`` when a CI is present, else just the rate."""
    rate = f"{row.resolved_rate:.0%}"
    if row.resolved_rate_ci is None:
        return rate
    lo, hi = row.resolved_rate_ci
    return f"{rate} [{lo:.0%}-{hi:.0%}]"


def render_markdown(report: RunReport) -> str:
    lines = [
        f"# reforge run `{report.run_id}`",
        "",
        f"- Dataset: `{report.dataset}`",
        f"- Tool version: `{report.tool_version}`",
        "",
        "## Leaderboard",
        "",
        "| Adapter | Model | Tasks | Resolved | Resolved rate (95% CI) | Mean score | Cost (USD) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report.leaderboard:
        lines.append(
            f"| {row.adapter} | {row.model or '-'} | {row.tasks} | {row.resolved} "
            f"| {_fmt_rate_ci(row)} | {row.mean_final_score:.3f} | {row.total_cost_usd:.2f} |"
        )
    cq = [r for r in report.leaderboard if r.mean_cost_usd is not None]
    if len(cq) > 1 and not all(r.mean_cost_usd == 0 for r in cq):
        lines += [
            "",
            "## Cost vs quality",
            "",
            "| Model | $/task | Resolved rate | Mean score | Pareto |",
            "| --- | ---: | ---: | ---: | :---: |",
        ]
        for cr in sorted(cq, key=lambda row: row.mean_cost_usd or 0.0):
            mark = "frontier" if cr.on_frontier else "dominated"
            lines.append(
                f"| {cr.model or cr.adapter} | {cr.mean_cost_usd or 0.0:.4f} "
                f"| {cr.resolved_rate:.0%} | {cr.mean_final_score:.3f} | {mark} |"
            )
    lines += [
        "",
        "## Tasks",
        "",
        "| Task | Category | Resolved | Score |",
        "| --- | --- | :---: | ---: |",
    ]
    for r in report.results:
        mark = "✅" if r.resolved else "❌"
        lines.append(f"| {r.task_id} | {r.category} | {mark} | {r.final_score:.3f} |")
    return "\n".join(lines) + "\n"


def render_table(report: RunReport, console: Console | None = None) -> None:
    console = console or Console()

    board = Table(title=f"reforge run {report.run_id} leaderboard")
    for col in ("Adapter", "Model", "Tasks", "Resolved", "Rate (95% CI)", "Mean score", "Cost $"):
        board.add_column(col, justify="right" if col not in ("Adapter", "Model") else "left")
    for row in report.leaderboard:
        board.add_row(
            row.adapter,
            row.model or "-",
            str(row.tasks),
            str(row.resolved),
            _fmt_rate_ci(row),
            f"{row.mean_final_score:.3f}",
            f"{row.total_cost_usd:.2f}",
        )
    console.print(board)

    tasks = Table(title="tasks")
    for col in ("Task", "Category", "Resolved", "Score", "Duration s"):
        tasks.add_column(col, justify="left" if col in ("Task", "Category") else "right")
    for r in report.results:
        tasks.add_row(
            r.task_id,
            r.category,
            "[green]yes[/green]" if r.resolved else "[red]no[/red]",
            f"{r.final_score:.3f}",
            f"{r.duration_s:.1f}",
        )
    console.print(tasks)

    if report.repeats > 1:
        variance = Table(title=f"variance over {report.repeats} repeats")
        for col in ("Task", "Runs", "Resolved rate", "Mean score", "Std dev"):
            variance.add_column(col, justify="left" if col == "Task" else "right")
        for s in report.task_stats:
            variance.add_row(
                s.task_id,
                str(s.runs),
                f"{s.resolved_rate:.0%}",
                f"{s.mean_final_score:.3f}",
                f"{s.stdev_final_score:.3f}",
            )
        console.print(variance)
        render_pass_at_k(report, console)

    if report.budget_usd is not None or report.total_cost_usd:
        note = f"total cost: ${report.total_cost_usd:.4f}"
        if report.budget_usd is not None:
            note += f" / budget ${report.budget_usd:.2f}"
        if report.budget_exhausted:
            note += " [red](budget exhausted; some tasks skipped)[/red]"
        console.print(note)


def render_comparison(report: RunReport, console: Console | None = None) -> None:
    """Render a leaderboard that combines several runs (for cross-model compare)."""
    console = console or Console()
    board = Table(title="reforge comparison leaderboard")
    cols = ("Adapter", "Model", "Tasks", "Resolved", "Rate (95% CI)", "Mean score", "Dep cov")
    for col in cols:
        board.add_column(col, justify="left" if col in ("Adapter", "Model") else "right")
    for row in report.leaderboard:
        board.add_row(
            row.adapter,
            row.model or "-",
            str(row.tasks),
            str(row.resolved),
            _fmt_rate_ci(row),
            f"{row.mean_final_score:.3f}",
            "-" if row.mean_dep_coverage is None else f"{row.mean_dep_coverage:.2f}",
        )
    console.print(board)
    _render_significance(report, console)
    render_cost_quality(report, console)
    render_pass_at_k(report, console)


def _render_significance(report: RunReport, console: Console) -> None:
    """One-line note on whether the leader's resolved rate beats the runner-up."""
    board = report.leaderboard
    if len(board) < 2:
        return
    top, nxt = board[0], board[1]
    p = two_proportion_pvalue(top.resolved, top.tasks, nxt.resolved, nxt.tasks)
    delta = (top.resolved_rate - nxt.resolved_rate) * 100
    verdict = "significant" if p < 0.05 else "not significant at p<0.05"
    console.print(
        f"top {top.model or top.adapter} vs {nxt.model or nxt.adapter}: "
        f"delta resolved = {delta:+.0f}pp, p = {p:.3f} "
        f"({verdict}; two-proportion z, large-sample)"
    )


def render_cost_quality(report: RunReport, console: Console | None = None) -> None:
    """Cost vs quality table sorted by cost, with Pareto-frontier membership."""
    console = console or Console()
    rows = [r for r in report.leaderboard if r.mean_cost_usd is not None]
    if len(rows) < 2 or all(r.mean_cost_usd == 0 for r in rows):
        return  # nothing to compare on cost
    rows = sorted(rows, key=lambda r: r.mean_cost_usd or 0.0)
    table = Table(title="cost vs quality")
    for col in ("Model", "$/task", "Resolved (CI)", "Mean score", "Pareto"):
        table.add_column(col, justify="left" if col == "Model" else "right")
    for r in rows:
        mark = "[green]on frontier[/green]" if r.on_frontier else "[dim]dominated[/dim]"
        table.add_row(
            r.model or r.adapter,
            f"{r.mean_cost_usd or 0.0:.4f}",
            _fmt_rate_ci(r),
            f"{r.mean_final_score:.3f}",
            mark,
        )
    console.print(table)


def render_pass_at_k(report: RunReport, console: Console | None = None) -> None:
    """pass@k table, shown only when repeated runs make it meaningful."""
    console = console or Console()
    rows = [r for r in report.leaderboard if r.pass_at_k]
    if not rows:
        return
    ks = sorted({k for r in rows for k in r.pass_at_k})
    table = Table(title="pass@k")
    table.add_column("Model", justify="left")
    for k in ks:
        table.add_column(f"pass@{k}", justify="right")
    for r in rows:
        table.add_row(
            r.model or r.adapter,
            *[f"{r.pass_at_k.get(k, 0.0):.2f}" for k in ks],
        )
    console.print(table)
