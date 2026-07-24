"""Run one task end to end: prepare, build, agent, capture, verify, score.

This mirrors SWE-bench's per-instance lifecycle. The important ordering rule: the
agent's diff is captured *before* the verifier and held-out tests are injected, so
an agent can never see or modify the tests it is graded against.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from reforge import __version__
from reforge.adapters.base import AdapterInput
from reforge.adapters.registry import load_adapter
from reforge.report.models import Provenance, SubScore, TaskResult, TokenCounts
from reforge.runner.run_context import RunContext
from reforge.runtime.base import ContainerHandle, ContainerRuntime
from reforge.runtime.image import build_task_image
from reforge.runtime.limits import ResourceLimits
from reforge.scoring.base import TaskScoringContext
from reforge.scoring.compose import compose
from reforge.scoring.tests import VERIFIER_DIR_IN_CONTAINER, TestScorer
from reforge.spec.models import TaskSpec
from reforge.utils.errors import ReforgeError
from reforge.utils.logging import get_logger

log = get_logger("runner.task")

_GOLD_PATCH_REL = "gold/solution.patch"


def run_task(
    spec: TaskSpec,
    ctx: RunContext,
    runtime: ContainerRuntime,
    *,
    network_override: str | None = None,
    no_cache: bool = False,
    adapter_config: dict[str, object] | None = None,
    judge_limiter: object | None = None,
) -> TaskResult:
    """Execute a single task and return its result. Never raises for task-level
    failures are captured in the returned :class:`TaskResult`."""
    task_out = ctx.task_dir(spec.id)
    tlog = log.bind(task=spec.id, adapter=ctx.adapter)
    started = time.monotonic()

    result = TaskResult(
        task_id=spec.id,
        category=spec.category.value,
        adapter=ctx.adapter,
        model=ctx.model,
    )

    container = None
    workspace_tmp = Path(tempfile.mkdtemp(prefix=f"reforge-{spec.id}-"))
    try:
        from reforge.workspace import prepare_workspace

        source_ref = prepare_workspace(spec, workspace_tmp / "src")
        tlog.info("workspace_prepared", ref=source_ref)

        image_tag, image_digest = build_task_image(runtime, spec, no_cache=no_cache)

        limits = ResourceLimits.from_spec(spec.resources, network_override)
        container = runtime.run_container(
            image=image_tag, workdir=spec.environment.workdir, limits=limits
        )

        # Place the source into the container and snapshot a base commit.
        container.exec(["mkdir", "-p", spec.environment.workdir])
        container.copy_in(workspace_tmp / "src", spec.environment.workdir)
        listing = container.exec(
            ["sh", "-c", "find . -maxdepth 3 -not -path './.git/*' | sort | head -40"],
            workdir=spec.environment.workdir,
        )
        tlog.info("workspace_listing", files=listing.output.replace("\n", " "))
        base_sha = _snapshot_base(container, spec.environment.workdir)

        # Run the agent.
        adapter = load_adapter(ctx.adapter)
        trace_path = task_out / "agent_trace.log"
        adapter_input = AdapterInput(
            instruction=spec.instruction,
            workspace_path=spec.environment.workdir,
            container=container,
            trace_path=trace_path,
            model=ctx.model,
            config={**_adapter_config(spec), **(adapter_config or {})},
            env={},
            logger=tlog,
            timeout_s=spec.resources.agent_timeout_s,
        )
        adapter.validate(adapter_input)
        agent_result = adapter.run(adapter_input)
        result.agent_success = agent_result.success
        result.tokens = TokenCounts(
            input=agent_result.token_usage.input_tokens,
            output=agent_result.token_usage.output_tokens,
            total=agent_result.token_usage.total(),
        )
        result.cost_usd = agent_result.cost_usd

        # Capture the diff BEFORE any test material touches the container.
        diff = _capture_diff(container, spec.environment.workdir, base_sha)
        (task_out / "prediction.patch").write_text(diff, encoding="utf-8")

        # Inject the verifier and run the scorers.
        _inject_verifier(container, spec)
        scoring_ctx = TaskScoringContext(
            spec=spec,
            container=container,
            diff=diff,
            workspace_path=spec.environment.workdir,
        )
        subscores = {}
        test_result = TestScorer().score(scoring_ctx)
        subscores[test_result.key] = test_result

        weights = spec.scoring.weights
        if weights.dependency_coverage > 0 and not spec.dependency_coverage.is_empty():
            from reforge.scoring.dependency import DependencyScorer

            subscores["dependency_coverage"] = DependencyScorer().score(scoring_ctx)

        judge_model_used = None
        if weights.judge > 0 and not ctx.no_judge and not spec.rubric.is_empty():
            judge = _make_judge(ctx, judge_limiter, tlog)
            if judge is not None:
                judge_result = judge.score(scoring_ctx)
                subscores["judge"] = judge_result
                judge_model_used = judge_result.detail.get("judge_model")

        score = compose(spec, subscores)
        result.resolved = score.resolved
        result.final_score = score.final_score
        result.gated = score.gated
        result.weights_used = score.weights_used
        result.scores = {
            k: SubScore(score=v.score, passed=v.passed, detail=v.detail)
            for k, v in score.subscores.items()
        }
        result.provenance = Provenance(
            tool_version=__version__,
            adapter=ctx.adapter,
            adapter_version=adapter.version,
            model=ctx.model,
            image_tag=image_tag,
            image_digest=image_digest,
            source_ref=source_ref,
            judge_model=judge_model_used,
        )
        result.artifacts = {
            "patch": "prediction.patch",
            "trace": "agent_trace.log",
        }
        tlog.info("task_done", resolved=result.resolved, score=result.final_score)

    except ReforgeError as exc:
        result.error = str(exc)
        tlog.error("task_failed", error=str(exc))
    finally:
        result.duration_s = round(time.monotonic() - started, 2)
        if container is not None:
            container.stop()
        _cleanup(workspace_tmp)

    (task_out / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result


DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"


def _make_judge(ctx: RunContext, limiter: object | None, tlog: object):  # type: ignore[no-untyped-def]
    """Build a judge scorer, or return None if credentials/SDK are unavailable."""
    from reforge.llm.client import make_client
    from reforge.llm.ratelimit import RateLimiter
    from reforge.scoring.judge import JudgeScorer
    from reforge.utils.errors import ReforgeError

    model = ctx.judge_model or DEFAULT_JUDGE_MODEL
    try:
        client = make_client(model)
    except ReforgeError as exc:
        tlog.warning("judge_disabled", reason=str(exc))  # type: ignore[attr-defined]
        return None
    samples = int(ctx.judge_samples)
    rl = limiter if isinstance(limiter, RateLimiter) else None
    return JudgeScorer(client, samples=samples, limiter=rl)


def _adapter_config(spec: TaskSpec) -> dict[str, object]:
    config: dict[str, object] = {}
    gold = spec.task_dir / _GOLD_PATCH_REL
    if gold.is_file():
        config["gold_patch_path"] = str(gold)
    return config


def _snapshot_base(container: ContainerHandle, workdir: str) -> str:
    script = (
        "git init -q && "
        "git config user.email reforge@local && "
        "git config user.name reforge && "
        "git add -A -f && "
        'git commit -q -m "reforge base" --allow-empty && '
        "git rev-parse HEAD"
    )
    res = container.exec(["sh", "-c", script], workdir=workdir)
    if not res.ok:
        raise ReforgeError(f"failed to snapshot base commit: {res.output}")
    return res.output.strip().splitlines()[-1]


def _capture_diff(container: ContainerHandle, workdir: str, base_sha: str) -> str:
    script = (
        f"git add -A -f && git diff --cached {base_sha} > /tmp/reforge.diff; cat /tmp/reforge.diff"
    )
    res = container.exec(["sh", "-c", script], workdir=workdir)
    return res.output


def _inject_verifier(container: ContainerHandle, spec: TaskSpec) -> None:
    verifier_dir = spec.task_dir / "verifier"
    if not verifier_dir.is_dir():
        raise ReforgeError(f"task has no verifier/ directory: {verifier_dir}")
    container.exec(["mkdir", "-p", VERIFIER_DIR_IN_CONTAINER])
    container.copy_in(verifier_dir, VERIFIER_DIR_IN_CONTAINER)


def _cleanup(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
