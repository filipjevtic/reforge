"""Run a set of tasks and write the run report.

Concurrency is a bounded thread pool: each task spends most of its wall-clock
blocked on ``container.exec`` and (later) API calls, so threads are the simplest
model that keeps N containers busy. Image builds are serialized elsewhere so
parallel tasks never build the same image twice.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from reforge import __version__
from reforge.report.aggregate import build_leaderboard, build_task_stats
from reforge.report.models import RunReport, TaskResult
from reforge.runner.run_context import RunContext
from reforge.runner.task_runner import run_task
from reforge.runtime.base import ContainerRuntime
from reforge.spec.models import TaskSpec
from reforge.utils.errors import redact_secrets
from reforge.utils.logging import get_logger

log = get_logger("runner.orchestrator")


def run_dataset(
    specs: list[TaskSpec],
    ctx: RunContext,
    runtime: ContainerRuntime,
    *,
    dataset_name: str,
    concurrency: int = 1,
    network_override: str | None = None,
    no_cache: bool = False,
    adapter_config: dict[str, object] | None = None,
    progress: bool = False,
    repeats: int = 1,
    max_cost_usd: float | None = None,
    requested_env: dict[str, str] | None = None,
) -> RunReport:
    _write_run_json(ctx, dataset_name, specs)

    results: list[TaskResult] = []
    concurrency = max(1, concurrency)
    repeats = max(1, repeats)

    # One shared limiter so judge calls across parallel tasks don't burst.
    from reforge.llm.ratelimit import RateLimiter

    judge_limiter = RateLimiter(calls_per_minute=60.0)

    # (spec, attempt) is the unit of work; repeats add attempts per task.
    work = [(spec, attempt) for attempt in range(repeats) for spec in specs]

    def _run(item: tuple[TaskSpec, int]) -> TaskResult:
        spec, attempt = item
        try:
            return run_task(
                spec,
                ctx,
                runtime,
                network_override=network_override,
                no_cache=no_cache,
                adapter_config=adapter_config,
                judge_limiter=judge_limiter,
                requested_env=requested_env,
                attempt=attempt,
            )
        except Exception as exc:  # run_task shouldn't raise, but never let it abort the run
            message = redact_secrets(f"unexpected: {exc}")
            log.error("task_crashed", task=spec.id, error=message)
            return TaskResult(
                task_id=spec.id,
                category=spec.category,
                tags=list(spec.tags),
                adapter=ctx.adapter,
                model=ctx.model,
                error=message,
            )

    spent = 0.0
    exhausted = False

    def _over_budget() -> bool:
        return max_cost_usd is not None and spent >= max_cost_usd

    tracker = _Progress(len(work), enabled=progress)
    with tracker:
        if concurrency == 1:
            for item in work:
                if _over_budget():
                    exhausted = True
                    break
                result = _run(item)
                results.append(result)
                spent += result.cost_usd or 0.0
                tracker.advance(result)
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {pool.submit(_run, item): item for item in work}
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
                    spent += result.cost_usd or 0.0
                    tracker.advance(result)
                    if _over_budget():
                        exhausted = True
                        for pending in futures:
                            pending.cancel()

    if exhausted:
        log.warning("budget_exhausted", spent=round(spent, 4), budget=max_cost_usd)

    results.sort(key=lambda r: r.task_id)
    report = RunReport(
        run_id=ctx.run_id,
        tool_version=__version__,
        dataset=dataset_name,
        adapter=ctx.adapter,
        model=ctx.model,
        repeats=repeats,
        budget_usd=max_cost_usd,
        total_cost_usd=round(spent, 4),
        budget_exhausted=exhausted,
        results=results,
        leaderboard=build_leaderboard(results),
        task_stats=build_task_stats(results),
    )
    ctx.report_json.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    log.info("run_complete", run_id=ctx.run_id, results=len(results), cost=round(spent, 4))
    return report


class _Progress:
    """A thin rich progress bar that no-ops when disabled or output isn't a tty."""

    def __init__(self, total: int, *, enabled: bool) -> None:
        self._enabled = enabled
        self._total = total
        self._progress: Any = None
        self._task_id: Any = None
        self._done = 0
        self._resolved = 0

    def __enter__(self) -> _Progress:
        if self._enabled:
            from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn

            self._progress = Progress(
                TextColumn("[bold]running[/bold]"),
                BarColumn(),
                MofNCompleteColumn(),
                TextColumn("{task.fields[status]}"),
            )
            self._progress.start()
            self._task_id = self._progress.add_task("run", total=self._total, status="")
        return self

    def advance(self, result: TaskResult) -> None:
        self._done += 1
        if result.resolved:
            self._resolved += 1
        if self._progress is not None:
            self._progress.update(
                self._task_id,
                advance=1,
                status=f"[green]{self._resolved} resolved[/green]",
            )

    def __exit__(self, *exc: object) -> None:
        if self._progress is not None:
            self._progress.stop()


def _write_run_json(ctx: RunContext, dataset_name: str, specs: list[TaskSpec]) -> None:
    import json

    payload = {
        "run_id": ctx.run_id,
        "tool_version": __version__,
        "dataset": dataset_name,
        "adapter": ctx.adapter,
        "model": ctx.model,
        "no_judge": ctx.no_judge,
        "judge_model": ctx.judge_model,
        "task_ids": [s.id for s in specs],
    }
    ctx.run_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
