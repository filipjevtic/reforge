"""Tests for LLM message translation and cost accounting."""

from __future__ import annotations

from reforge.llm.client import ToolCall, _to_anthropic_messages, _to_openai_messages
from reforge.llm.cost import compute_cost, price_for


def test_cost_known_model() -> None:
    cost = compute_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert cost == 3.0 + 15.0


def test_cost_unknown_model_is_none() -> None:
    assert compute_cost("mystery-model", 1000, 1000) is None
    assert price_for("mystery-model").known is False


def test_anthropic_tool_result_shape() -> None:
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "using tool",
            "tool_calls": [ToolCall(id="t1", name="read_file", arguments={"path": "a"})],
        },
        {"role": "tool", "tool_call_id": "t1", "content": "file body"},
    ]
    out = _to_anthropic_messages(messages)
    assert out[1]["content"][0]["type"] == "text"
    assert out[1]["content"][1]["type"] == "tool_use"
    assert out[2]["content"][0]["type"] == "tool_result"
    assert out[2]["content"][0]["tool_use_id"] == "t1"


def test_openai_tool_call_shape() -> None:
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [ToolCall(id="t1", name="run", arguments={"command": "ls"})],
        },
        {"role": "tool", "tool_call_id": "t1", "content": "out"},
    ]
    out = _to_openai_messages("sys", messages)
    assert out[0] == {"role": "system", "content": "sys"}
    assert out[1]["tool_calls"][0]["function"]["name"] == "run"
    assert out[2]["role"] == "tool" and out[2]["tool_call_id"] == "t1"
