"""Render a run report as a rich table, Markdown, or JSON."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from reforge.report.models import RunReport


def render_json(report: RunReport) -> str:
    return report.model_dump_json(indent=2)


def render_markdown(report: RunReport) -> str:
    lines = [
        f"# reforge run `{report.run_id}`",
        "",
        f"- Dataset: `{report.dataset}`",
        f"- Tool version: `{report.tool_version}`",
        "",
        "## Leaderboard",
        "",
        "| Adapter | Model | Tasks | Resolved | Resolved rate | Mean score | Cost (USD) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report.leaderboard:
        lines.append(
            f"| {row.adapter} | {row.model or '-'} | {row.tasks} | {row.resolved} "
            f"| {row.resolved_rate:.0%} | {row.mean_final_score:.3f} | {row.total_cost_usd:.2f} |"
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
    for col in ("Adapter", "Model", "Tasks", "Resolved", "Rate", "Mean score", "Cost $"):
        board.add_column(col, justify="right" if col not in ("Adapter", "Model") else "left")
    for row in report.leaderboard:
        board.add_row(
            row.adapter,
            row.model or "-",
            str(row.tasks),
            str(row.resolved),
            f"{row.resolved_rate:.0%}",
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
    for col in ("Adapter", "Model", "Tasks", "Resolved", "Rate", "Mean score", "Dep cov", "Cost $"):
        board.add_column(col, justify="left" if col in ("Adapter", "Model") else "right")
    for row in report.leaderboard:
        board.add_row(
            row.adapter,
            row.model or "-",
            str(row.tasks),
            str(row.resolved),
            f"{row.resolved_rate:.0%}",
            f"{row.mean_final_score:.3f}",
            "-" if row.mean_dep_coverage is None else f"{row.mean_dep_coverage:.2f}",
            f"{row.total_cost_usd:.2f}",
        )
    console.print(board)
