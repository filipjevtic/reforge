"""reforge command-line interface."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import typer
from rich.console import Console

from reforge import __version__
from reforge.utils.errors import ReforgeError
from reforge.utils.logging import configure

if TYPE_CHECKING:
    from reforge.spec.models import TaskSpec

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Benchmark how well AI coding agents replicate and extend your own codebase.",
)
list_app = typer.Typer(no_args_is_help=True, help="List installed plugins.")
app.add_typer(list_app, name="list")

console = Console()
err_console = Console(stderr=True)

_TASK_TEMPLATE = """schema_version: 1
id: {id}
category: {category}
tags: []
title: "TODO: one-line title"
instruction: |
  TODO: describe what the agent must do.

source:
  type: local
  path: src
  strip_git: true

environment:
  dockerfile: Dockerfile
  workdir: /workspace

verification:
  entrypoint: verifier/run_tests.sh
  framework: pytest
  fail_to_pass:
    - "test_todo.py::test_todo"
  pass_to_pass: []
  timeout_s: 300

scoring:
  weights: {{ tests: 1.0 }}

resources:
  cpus: 1
  memory: "1g"
  network: none
"""

_DOCKERFILE_TEMPLATE = """FROM python:3.12-slim

RUN apt-get update \\
    && apt-get install -y --no-install-recommends git \\
    && rm -rf /var/lib/apt/lists/* \\
    && pip install --no-cache-dir pytest==8.2.2

WORKDIR /workspace
"""

_RUN_TESTS_TEMPLATE = """#!/bin/sh
set -e
cd /verifier/tests
PYTHONPATH=/workspace pytest \\
  --junitxml="${REFORGE_REPORT:-/tmp/reforge_report}" -o junit_family=xunit2
"""


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"reforge {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    verbose: int = typer.Option(0, "-v", "--verbose", count=True, help="Increase log verbosity."),
    json_logs: bool = typer.Option(False, "--json-logs", help="Emit logs as JSON."),
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    level = {0: "warning", 1: "info"}.get(verbose, "debug")
    configure(level=level, json_logs=json_logs)


def _fail(message: str) -> NoReturn:
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code=1)


@app.command()
def init(
    task_id: str = typer.Argument(..., help="Task id (lowercase, dashes)."),
    category: str = typer.Option("new_feature", "--category", help="Task category label."),
    directory: Path = typer.Option(Path("tasks"), "--dir", help="Where to create the task dir."),
) -> None:
    """Scaffold a new task directory you can fill in."""
    task_dir = directory / task_id
    if task_dir.exists():
        _fail(f"{task_dir} already exists")
    (task_dir / "src").mkdir(parents=True)
    (task_dir / "verifier" / "tests").mkdir(parents=True)
    (task_dir / "gold").mkdir(parents=True)

    (task_dir / "task.yaml").write_text(_TASK_TEMPLATE.format(id=task_id, category=category))
    (task_dir / "Dockerfile").write_text(_DOCKERFILE_TEMPLATE)
    (task_dir / "verifier" / "run_tests.sh").write_text(_RUN_TESTS_TEMPLATE)
    (task_dir / "gold" / "solution.patch").write_text(
        "# TODO: git diff of the reference solution\n"
    )
    (task_dir / "src" / ".gitkeep").write_text("")

    console.print(f"[green]scaffolded[/green] {task_dir}")
    console.print("Next: add source under src/, write the verifier and gold/solution.patch, then")
    console.print(f"  reforge validate {task_dir} && reforge verify-gold {task_dir}")


@app.command()
def validate(
    path: Path = typer.Argument(..., help="A task directory (or dataset dir with --dataset)."),
    dataset: bool = typer.Option(False, "--dataset", help="Treat PATH as a dataset of tasks."),
) -> None:
    """Validate task specifications without running anything."""
    from reforge.spec import load_dataset_dir, load_task, validate_task

    try:
        specs = load_dataset_dir(path) if dataset else [load_task(path)]
    except ReforgeError as exc:
        _fail(str(exc))
        return

    ok = True
    for spec in specs:
        problems = validate_task(spec)
        if problems:
            ok = False
            console.print(f"[red]✗[/red] {spec.id}")
            for problem in problems:
                console.print(f"    - {problem}")
        else:
            console.print(f"[green]✓[/green] {spec.id}")

    if not ok:
        raise typer.Exit(code=1)


@app.command("verify-gold")
def verify_gold(
    task_dir: Path = typer.Argument(..., help="Task directory to self-verify."),
) -> None:
    """Apply the gold solution and assert the task resolves. The self-consistency
    check every task must pass."""
    from reforge.runner.run_context import make_run_context
    from reforge.runner.task_runner import run_task
    from reforge.runtime.docker_runtime import DockerRuntime
    from reforge.spec import load_task

    try:
        spec = load_task(task_dir)
        runtime = DockerRuntime()
        if not runtime.is_available():
            _fail("Docker is not available; verify-gold needs a running daemon.")
        ctx = make_run_context(
            run_id=f"verify-gold-{spec.id}",
            output_root=Path("runs"),
            adapter="gold",
            model=None,
        )
        result = run_task(spec, ctx, runtime)
    except ReforgeError as exc:
        _fail(str(exc))
        return

    if result.error:
        _fail(f"gold verification errored: {result.error}")
    if result.resolved:
        console.print(f"[green]✓ gold solution resolves[/green] {spec.id}")
    else:
        _fail(
            f"gold solution did NOT resolve {spec.id} "
            f"(score={result.final_score}). See runs/{ctx.run_id}/tasks/{spec.id}/."
        )


@app.command()
def run(
    adapter: str | None = typer.Option(None, "--adapter", "-a", help="Agent adapter name."),
    dataset: str | None = typer.Option(
        None, "--dataset", help="Dataset directory, or hf:owner/repo for a HuggingFace dataset."
    ),
    task: Path | None = typer.Option(None, "--task", help="A single task directory."),
    model: str | None = typer.Option(None, "--model", "-m", help="Model id for the adapter."),
    run_id: str | None = typer.Option(None, "--run-id", help="Name for this run."),
    concurrency: int | None = typer.Option(None, "--concurrency", "-j", help="Parallel workers."),
    runtime_name: str | None = typer.Option(
        None, "--runtime", help="Container runtime: docker|podman."
    ),
    network: str | None = typer.Option(None, "--network", help="Override container network."),
    output: Path | None = typer.Option(None, "--output", help="Where run dirs are written."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Rebuild images from scratch."),
    config: str | None = typer.Option(None, "--config", help="Adapter config as a JSON object."),
    no_judge: bool = typer.Option(False, "--no-judge", help="Skip the LLM judge (deterministic)."),
    judge_model: str | None = typer.Option(None, "--judge-model", help="Model id for the judge."),
    judge_samples: int = typer.Option(1, "--judge-samples", help="Judge samples; median is taken."),
    repeats: int = typer.Option(1, "--repeats", help="Run each task N times for variance."),
    max_cost_usd: float | None = typer.Option(
        None, "--max-cost-usd", help="Stop launching tasks once spend reaches this budget."
    ),
    fail_under: float | None = typer.Option(
        None, "--fail-under", help="Exit non-zero if the resolved rate is below this (0..1)."
    ),
    category: str | None = typer.Option(
        None, "--category", help="Only run tasks in this category."
    ),
    tag: list[str] = typer.Option(None, "--tag", help="Only run tasks having all these tags."),
    env_passthrough: list[str] = typer.Option(
        None,
        "--env-passthrough",
        help="Forward this host env var into tasks that allowlist it (repeatable).",
    ),
    fmt: str = typer.Option("table", "--format", help="Report format: table|markdown|json."),
) -> None:
    """Run an adapter against a task or dataset and score the results."""
    from reforge.config import load_project_config
    from reforge.dataset import resolve_dataset_source
    from reforge.report.render import render_json, render_markdown, render_table
    from reforge.runner.orchestrator import run_dataset
    from reforge.runner.run_context import make_run_context
    from reforge.runtime.factory import make_runtime
    from reforge.spec import load_dataset_dir, load_task

    if bool(dataset) == bool(task):
        _fail("provide exactly one of --dataset or --task")

    # Flags override reforge.toml, which overrides built-in defaults.
    cfg = load_project_config()
    adapter = adapter or cfg.get("adapter")
    if not adapter:
        _fail("provide --adapter (or set adapter in reforge.toml)")
    model = model or cfg.get("model")
    judge_model = judge_model or cfg.get("judge_model")
    runtime_name = runtime_name or cfg.get("runtime", "docker")
    network = network or cfg.get("network")
    concurrency = concurrency if concurrency is not None else int(cfg.get("concurrency", 1))
    output = output or Path(cfg.get("output", "runs"))
    max_cost_usd = max_cost_usd if max_cost_usd is not None else cfg.get("max_cost_usd")
    fail_under = fail_under if fail_under is not None else cfg.get("fail_under")

    adapter_config = _parse_config(config)
    requested_env = {k: os.environ[k] for k in (env_passthrough or []) if k in os.environ}

    try:
        if dataset:
            specs = load_dataset_dir(resolve_dataset_source(dataset))
            dataset_name = dataset
        else:
            specs = [load_task(task)]  # type: ignore[arg-type]
            dataset_name = str(task)

        specs = _filter_specs(specs, category, tag)
        if not specs:
            _fail("no tasks matched the given --category/--tag filters")

        runtime = make_runtime(runtime_name)
        if not runtime.is_available():
            _fail(f"{runtime_name} is not available; run needs a running daemon.")

        resolved_run_id = run_id or _default_run_id(adapter)
        ctx = make_run_context(
            run_id=resolved_run_id,
            output_root=output,
            adapter=adapter,
            model=model,
            no_judge=no_judge,
            judge_model=judge_model,
            judge_samples=judge_samples,
        )
        report = run_dataset(
            specs,
            ctx,
            runtime,
            dataset_name=dataset_name,
            concurrency=concurrency,
            network_override=network,
            no_cache=no_cache,
            adapter_config=adapter_config,
            progress=(fmt == "table"),
            repeats=repeats,
            max_cost_usd=max_cost_usd,
            requested_env=requested_env,
        )
    except ReforgeError as exc:
        _fail(str(exc))
        return

    if fmt == "json":
        console.print_json(render_json(report))
    elif fmt == "markdown":
        console.print(render_markdown(report))
    else:
        render_table(report, console)
    console.print(f"\nrun written to [bold]{ctx.run_dir}[/bold]")

    if fail_under is not None:
        total = len(report.results)
        rate = sum(1 for r in report.results if r.resolved) / total if total else 0.0
        if rate < fail_under:
            err_console.print(
                f"[red]resolved rate {rate:.0%} is below --fail-under {fail_under:.0%}[/red]"
            )
        raise typer.Exit(code=0 if rate >= fail_under else 2)


@app.command()
def report(
    run_dir: Path = typer.Argument(..., help="A run directory containing report.json."),
    compare: list[Path] = typer.Option(
        None, "--compare", help="Other run dirs to combine into one leaderboard."
    ),
    fmt: str = typer.Option("table", "--format", help="Report format: table|markdown|json."),
) -> None:
    """Render a run report, or compare several runs on one leaderboard."""
    from reforge.report.aggregate import build_leaderboard, build_task_stats
    from reforge.report.models import RunReport
    from reforge.report.render import render_comparison, render_json, render_markdown, render_table

    parsed = _load_report(run_dir)

    if compare:
        reports = [parsed, *(_load_report(d) for d in compare)]
        combined = [r for rep in reports for r in rep.results]
        merged = RunReport(
            run_id="+".join(r.run_id for r in reports),
            tool_version=parsed.tool_version,
            dataset=parsed.dataset,
            adapter="(multiple)",
            repeats=max((rep.repeats for rep in reports), default=1),
            results=combined,
            leaderboard=build_leaderboard(combined),
            task_stats=build_task_stats(combined),
        )
        if fmt == "json":
            console.print_json(render_json(merged))
        else:
            render_comparison(merged, console)
        return

    # Re-aggregate from the stored results so confidence intervals and pass@k are
    # present even for a report.json produced before those fields existed.
    parsed.leaderboard = build_leaderboard(parsed.results)
    parsed.task_stats = build_task_stats(parsed.results)
    if fmt == "json":
        console.print_json(render_json(parsed))
    elif fmt == "markdown":
        console.print(render_markdown(parsed))
    else:
        render_table(parsed, console)


def _load_report(run_dir: Path):  # type: ignore[no-untyped-def]
    from reforge.report.models import RunReport

    report_file = run_dir / "report.json"
    if not report_file.is_file():
        _fail(f"no report.json in {run_dir}")
    return RunReport.model_validate_json(report_file.read_text(encoding="utf-8"))


@app.command()
def schema(
    output: Path | None = typer.Option(None, "--output", help="Write JSON Schema to a file."),
) -> None:
    """Print (or write) the task JSON Schema."""
    from reforge.spec.schema import dump_task_json_schema

    text = dump_task_json_schema()
    if output:
        output.write_text(text + "\n", encoding="utf-8")
        console.print(f"wrote schema to {output}")
    else:
        console.print_json(text)


@app.command("adapter-check")
def adapter_check(
    adapter: str = typer.Option(..., "--adapter", "-a", help="Adapter to preflight."),
    model: str | None = typer.Option(None, "--model", "-m", help="Model id for the adapter."),
    config: str | None = typer.Option(None, "--config", help="Adapter config as a JSON object."),
) -> None:
    """Preflight an adapter's credentials/config without running a task.

    Resolves the adapter and runs its validate() against a lightweight input, so
    you catch a missing API key or unknown model before spending a full run.
    """
    from reforge.adapters.base import AdapterInput
    from reforge.adapters.registry import load_adapter

    try:
        instance = load_adapter(adapter)
        probe = AdapterInput(
            instruction="preflight",
            workspace_path="/workspace",
            container=_NullContainer(),  # type: ignore[arg-type]
            trace_path=Path("/dev/null"),
            model=model,
            config=_parse_config(config),
        )
        instance.validate(probe)
    except ReforgeError as exc:
        _fail(str(exc))
        return
    console.print(f"[green]✓ {adapter} looks ready[/green] (v{instance.version})")


@list_app.command("adapters")
def list_adapters() -> None:
    """List installed agent adapters."""
    from reforge.adapters.registry import available_adapters

    adapters = available_adapters()
    if not adapters:
        console.print("no adapters installed")
        return
    for name, target in sorted(adapters.items()):
        console.print(f"[bold]{name}[/bold]  [dim]{target}[/dim]")


@list_app.command("detectors")
def list_detectors() -> None:
    """List dependency-coverage detectors (built-in + entry-point plugins)."""
    from reforge.scoring.dependency import available_detectors

    for name in available_detectors():
        console.print(f"[bold]{name}[/bold]")


@list_app.command("scorers")
def list_scorers() -> None:
    """List scorers: the built-in three plus any entry-point plugins."""
    from reforge.scoring.registry import BUILTIN_KEYS, available_scorers

    for name in sorted(BUILTIN_KEYS):
        console.print(f"[bold]{name}[/bold]  [dim](built-in)[/dim]")
    for name, target in sorted(available_scorers().items()):
        console.print(f"[bold]{name}[/bold]  [dim]{target}[/dim]")


class _NullContainer:
    """A stand-in container for adapter-check.

    There is no real container during preflight, so container-side probes (such as
    an adapter's binary check) succeed here. adapter-check verifies host-side
    prerequisites like API keys and model; whether a CLI is present in the task
    image is confirmed when a real run builds it.
    """

    @property
    def id(self) -> str:
        return "null"

    def exec(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        from reforge.runtime.base import ExecResult

        return ExecResult(exit_code=0, output="", timed_out=False)

    def copy_in(self, *args: object, **kwargs: object) -> None:
        return None

    def read_file(self, *args: object, **kwargs: object) -> bytes:
        return b""

    def stop(self) -> None:
        return None


def _filter_specs(
    specs: list[TaskSpec], category: str | None, tags: list[str] | None
) -> list[TaskSpec]:
    """Keep specs matching the category and having all requested tags."""
    if category:
        specs = [s for s in specs if s.category == category]
    if tags:
        wanted = set(tags)
        specs = [s for s in specs if wanted <= set(s.tags)]
    return specs


def _parse_config(config: str | None) -> dict[str, object]:
    if not config:
        return {}
    try:
        parsed = json.loads(config)
    except json.JSONDecodeError as exc:
        _fail(f"--config is not valid JSON: {exc}")
        return {}
    if not isinstance(parsed, dict):
        _fail("--config must be a JSON object")
        return {}
    return parsed


def _default_run_id(adapter: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{adapter}-{stamp}"


def main() -> None:  # pragma: no cover - console entry indirection
    try:
        app()
    except ReforgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
