"""Tests for the API-backed agent loop, driven by a fake LLM client."""

from __future__ import annotations

import base64
from pathlib import Path

from reforge.adapters.api_agent import ApiAgentAdapter
from reforge.adapters.base import AdapterInput
from reforge.llm.client import AssistantTurn, LLMUsage, ToolCall
from tests.unit.fakes import FakeContainer


class FakeClient:
    def __init__(self, turns: list[AssistantTurn]) -> None:
        self._turns = turns
        self.model = "claude-sonnet-4-6"
        self.calls = 0

    def chat(self, **kwargs: object) -> AssistantTurn:
        turn = self._turns[self.calls]
        self.calls += 1
        return turn


def test_agent_writes_file_then_finishes(tmp_path: Path, monkeypatch) -> None:
    turns = [
        AssistantTurn(
            text="writing the fix",
            tool_calls=[
                ToolCall(
                    id="1", name="write_file", arguments={"path": "calc.py", "content": "x=1\n"}
                )
            ],
            usage=LLMUsage(100, 20),
        ),
        AssistantTurn(
            text="done",
            tool_calls=[ToolCall(id="2", name="finish", arguments={"summary": "ok"})],
            usage=LLMUsage(50, 10),
        ),
    ]
    fake_client = FakeClient(turns)
    monkeypatch.setattr("reforge.adapters.api_agent.make_client", lambda *a, **k: fake_client)

    container = FakeContainer()
    adapter = ApiAgentAdapter()
    result = adapter.run(
        AdapterInput(
            instruction="fix calc",
            workspace_path="/workspace",
            container=container,
            trace_path=tmp_path / "trace.log",
            model="claude-sonnet-4-6",
        )
    )

    assert result.success is True
    assert result.metadata["finished"] is True
    assert result.token_usage.input_tokens == 150
    assert result.token_usage.output_tokens == 30
    # Cost is computed from the pricing table for a known model.
    assert result.cost_usd is not None and result.cost_usd > 0

    # The write went through as a base64 decode into the target path.
    wrote = [c for c in container.calls if any("base64 -d" in part for part in c)]
    assert wrote, "expected a write_file exec"
    encoded = base64.b64encode(b"x=1\n").decode()
    assert any(encoded in part for part in wrote[0])


def test_agent_validate_requires_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    adapter = ApiAgentAdapter()
    import pytest

    from reforge.utils.errors import AdapterError

    with pytest.raises(AdapterError):
        adapter.validate(
            AdapterInput(
                instruction="x",
                workspace_path="/workspace",
                container=FakeContainer(),
                trace_path=tmp_path / "t.log",
                model="claude-sonnet-4-6",
            )
        )
