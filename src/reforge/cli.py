"""reforge command-line interface."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

from reforge import __version__
from reforge.utils.errors import ReforgeError
from reforge.utils.logging import configure

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Benchmark how well AI coding agents replicate and extend your own codebase.",
)
list_app = typer.Typer(no_args_is_help=True, help="List installed plugins.")
app.add_typer(list_app, name="list")

console = Console()
err_console = Console(stderr=True)


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


def _fail(message: str) -> None:
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code=1)


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
    keep_container: bool = typer.Option(False, "--keep-container", help="reserved"),
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
    adapter: str = typer.Option(..., "--adapter", "-a", help="Agent adapter name."),
    dataset: Path | None = typer.Option(None, "--dataset", help="Dataset directory."),
    task: Path | None = typer.Option(None, "--task", help="A single task directory."),
    model: str | None = typer.Option(None, "--model", "-m", help="Model id for the adapter."),
    run_id: str | None = typer.Option(None, "--run-id", help="Name for this run."),
    concurrency: int = typer.Option(1, "--concurrency", "-j", help="Parallel task workers."),
    network: str | None = typer.Option(None, "--network", help="Override container network."),
    output: Path = typer.Option(Path("runs"), "--output", help="Where run dirs are written."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Rebuild images from scratch."),
    fmt: str = typer.Option("table", "--format", help="Report format: table|markdown|json."),
) -> None:
    """Run an adapter against a task or dataset and score the results."""
    from reforge.report.render import render_json, render_markdown, render_table
    from reforge.runner.orchestrator import run_dataset
    from reforge.runner.run_context import make_run_context
    from reforge.runtime.docker_runtime import DockerRuntime
    from reforge.spec import load_dataset_dir, load_task

    if bool(dataset) == bool(task):
        _fail("provide exactly one of --dataset or --task")

    try:
        if dataset:
            specs = load_dataset_dir(dataset)
            dataset_name = str(dataset)
        else:
            specs = [load_task(task)]  # type: ignore[arg-type]
            dataset_name = str(task)

        runtime = DockerRuntime()
        if not runtime.is_available():
            _fail("Docker is not available; run needs a running daemon.")

        resolved_run_id = run_id or _default_run_id(adapter)
        ctx = make_run_context(
            run_id=resolved_run_id, output_root=output, adapter=adapter, model=model
        )
        report = run_dataset(
            specs,
            ctx,
            runtime,
            dataset_name=dataset_name,
            concurrency=concurrency,
            network_override=network,
            no_cache=no_cache,
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


@app.command()
def report(
    run_dir: Path = typer.Argument(..., help="A run directory containing report.json."),
    fmt: str = typer.Option("table", "--format", help="Report format: table|markdown|json."),
) -> None:
    """Render a previously written run report."""
    from reforge.report.models import RunReport
    from reforge.report.render import render_json, render_markdown, render_table

    report_file = run_dir / "report.json"
    if not report_file.is_file():
        _fail(f"no report.json in {run_dir}")
    parsed = RunReport.model_validate_json(report_file.read_text(encoding="utf-8"))

    if fmt == "json":
        console.print_json(render_json(parsed))
    elif fmt == "markdown":
        console.print(render_markdown(parsed))
    else:
        render_table(parsed, console)


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


# Small helper kept for potential programmatic use / tests.
def _dump(obj: object) -> str:
    return json.dumps(obj, indent=2)
