"""End-to-end resilience checks (require Docker).

Two things that only matter once real agents run: an adapter that throws must fail
just its task (not the run), and the api-agent's in-container tool loop must
actually edit files in a real container and resolve a task. The latter uses a fake
LLM client so it runs without any API key; only the provider HTTP call is left
unexercised here (see the key-gated live smoke test).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from reforge.adapters.base import AdapterInput, AdapterResult, AgentAdapter
from reforge.llm.client import AssistantTurn, LLMUsage, ToolCall
from reforge.runner.run_context import make_run_context
from reforge.runner.task_runner import run_task
from reforge.runtime.docker_runtime import DockerRuntime
from reforge.spec import load_task

pytestmark = pytest.mark.docker

TINY_TASK = Path(__file__).parent.parent / "fixtures" / "tiny-task"

FIXED_CALC = (
    '"""tiny calc module"""\ndef add(a, b):\n    return a + b\ndef existing():\n    return "ok"\n'
)


@pytest.fixture(scope="module")
def runtime() -> DockerRuntime:
    rt = DockerRuntime()
    if not rt.is_available():
        pytest.skip("Docker daemon not available")
    return rt


class _CrashingAdapter(AgentAdapter):
    name = "crashing"
    version = "0.0.0"

    def run(self, input: AdapterInput) -> AdapterResult:
        raise RuntimeError("simulated provider 500")


def test_adapter_exception_fails_only_the_task(runtime, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("reforge.runner.task_runner.load_adapter", lambda name: _CrashingAdapter())
    spec = load_task(TINY_TASK)
    ctx = make_run_context(run_id="it-crash", output_root=tmp_path, adapter="crashing", model=None)
    # Must NOT raise; the failure is captured in the result.
    result = run_task(spec, ctx, runtime)
    assert result.resolved is False
    assert result.error is not None
    assert "simulated provider 500" in result.error


class _ScriptedClient:
    def __init__(self) -> None:
        self.model = "claude-sonnet-4-6"
        self._turns = [
            AssistantTurn(
                text="writing the fix",
                tool_calls=[
                    ToolCall(
                        id="1",
                        name="write_file",
                        arguments={"path": "calc.py", "content": FIXED_CALC},
                    )
                ],
                usage=LLMUsage(100, 20),
            ),
            AssistantTurn(
                text="done",
                tool_calls=[ToolCall(id="2", name="finish", arguments={"summary": "ok"})],
                usage=LLMUsage(30, 5),
            ),
        ]
        self._i = 0

    def chat(self, **kwargs) -> AssistantTurn:
        turn = self._turns[self._i]
        self._i += 1
        return turn


def test_api_agent_tool_loop_resolves_in_container(runtime, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("reforge.adapters.api_agent.make_client", lambda *a, **k: _ScriptedClient())
    spec = load_task(TINY_TASK)
    ctx = make_run_context(
        run_id="it-apiagent", output_root=tmp_path, adapter="api-agent", model="claude-sonnet-4-6"
    )
    result = run_task(spec, ctx, runtime)
    assert result.error is None, result.error
    assert result.resolved is True
    assert result.tokens.total == 155


def test_env_reaches_container_exec(runtime) -> None:
    """Env forwarded to run_container is visible to exec'd commands (creds path)."""
    from reforge.runtime.limits import ResourceLimits

    container = runtime.run_container(
        image="python:3.12-slim",
        workdir="/",
        limits=ResourceLimits(cpus=1, memory="512m", pids=128, network="none"),
        env={"REFORGE_TEST_ENV": "sekret"},
    )
    try:
        result = container.exec(["printenv", "REFORGE_TEST_ENV"])
        assert result.output.strip() == "sekret"
    finally:
        container.stop()


ANALYTICS_TASK = Path(__file__).parent.parent.parent / "tasks" / "newfeature-analytics"


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="live smoke test needs ANTHROPIC_API_KEY",
)
def test_live_api_agent_and_judge(runtime, tmp_path) -> None:
    """Exercise the real provider SDK path: api-agent solving a task and the judge
    scoring it. Runs only when a key is present (locally or via a CI secret)."""
    model = os.environ.get("REFORGE_TEST_MODEL", "claude-sonnet-4-6")
    spec = load_task(ANALYTICS_TASK)
    ctx = make_run_context(run_id="it-live", output_root=tmp_path, adapter="api-agent", model=model)
    result = run_task(spec, ctx, runtime)
    # We don't require the model to solve it; the whole real pipeline must complete
    # and produce scores (tests + judge) with real token accounting.
    assert result.error is None, result.error
    assert "tests" in result.scores
    assert "judge" in result.scores
    assert result.tokens.total > 0
