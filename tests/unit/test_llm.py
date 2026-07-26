"""Tests for LLM message translation and cost accounting."""

from __future__ import annotations

import pytest

from reforge.llm.client import (
    ToolCall,
    _is_retryable,
    _to_anthropic_messages,
    _to_openai_messages,
    call_with_retries,
)
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


class _Status(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"http {status_code}")
        self.status_code = status_code


def test_is_retryable() -> None:
    assert _is_retryable(_Status(429)) is True
    assert _is_retryable(_Status(503)) is True
    assert _is_retryable(_Status(400)) is False
    assert _is_retryable(Exception("connection reset")) is True
    assert _is_retryable(Exception("invalid api key")) is False
    # A bare client-side timeout is NOT retried: the request may have been billed.
    assert _is_retryable(Exception("request timed out")) is False


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _Status(429)
        return "ok"

    result = call_with_retries(flaky, retries=3, base_delay=0.01, sleep=slept.append)
    assert result == "ok"
    assert calls["n"] == 3
    assert len(slept) == 2  # slept before each of the two retries


def test_non_retryable_raises_immediately() -> None:
    calls = {"n": 0}

    def bad() -> str:
        calls["n"] += 1
        raise _Status(400)

    with pytest.raises(_Status):
        call_with_retries(bad, retries=3, base_delay=0.01, sleep=lambda _: None)
    assert calls["n"] == 1


def test_retries_exhausted_reraises() -> None:
    with pytest.raises(_Status):
        call_with_retries(
            lambda: (_ for _ in ()).throw(_Status(503)),
            retries=2,
            base_delay=0.01,
            sleep=lambda _: None,
        )


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
