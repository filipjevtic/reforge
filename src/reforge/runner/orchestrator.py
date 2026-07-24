"""Run a set of tasks and write the run report.

Concurrency is a bounded thread pool: each task spends most of its wall-clock
blocked on ``container.exec`` and (later) API calls, so threads are the simplest
model that keeps N containers busy. Image builds are serialized elsewhere so
parallel tasks never build the same image twice.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from reforge import __version__
from reforge.report.aggregate import build_leaderboard
from reforge.report.models import RunReport, TaskResult
from reforge.runner.run_context import RunContext
from reforge.runner.task_runner import run_task
from reforge.runtime.base import ContainerRuntime
from reforge.spec.models import TaskSpec
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
) -> RunReport:
    _write_run_json(ctx, dataset_name, specs)

    results: list[TaskResult] = []
    concurrency = max(1, concurrency)

    if concurrency == 1:
        for spec in specs:
            results.append(
                run_task(spec, ctx, runtime, network_override=network_override, no_cache=no_cache)
            )
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(
                    run_task,
                    spec,
                    ctx,
                    runtime,
                    network_override=network_override,
                    no_cache=no_cache,
                ): spec
                for spec in specs
            }
            for future in as_completed(futures):
                results.append(future.result())

    results.sort(key=lambda r: r.task_id)
    report = RunReport(
        run_id=ctx.run_id,
        tool_version=__version__,
        dataset=dataset_name,
        adapter=ctx.adapter,
        model=ctx.model,
        results=results,
        leaderboard=build_leaderboard(results),
    )
    ctx.report_json.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    log.info("run_complete", run_id=ctx.run_id, tasks=len(results))
    return report


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
