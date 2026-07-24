"""A small provider-agnostic chat client with tool-use support.

Two backends: Anthropic (default for ``claude-*`` models) and any
OpenAI-compatible endpoint (OpenAI, plus Gemini, Kimi/Moonshot, and others via a
``base_url``). The API-backed agent and the LLM judge both talk to this interface
so the rest of the code never imports a vendor SDK directly.

The normalized message list uses these shapes:

* ``{"role": "user"|"assistant", "content": str}``
* ``{"role": "assistant", "tool_calls": [ToolCall, ...]}``
* ``{"role": "tool", "tool_call_id": str, "content": str}``
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from reforge.utils.errors import AdapterError


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for the arguments object


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AssistantTurn:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    stop_reason: str | None = None


class LLMClient(ABC):
    """Minimal chat interface used by the agent and the judge."""

    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
    def chat(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AssistantTurn: ...


class AnthropicClient(LLMClient):
    def __init__(self, model: str, api_key: str | None = None) -> None:
        super().__init__(model)
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise AdapterError(
                "the anthropic package is required; install reforge with the [judge] extra"
            ) from exc
        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def chat(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AssistantTurn:
        payload = _to_anthropic_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "system": system,
            "messages": payload,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ]
        resp = self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
                )

        return AssistantTurn(
            text="".join(text_parts) or None,
            tool_calls=tool_calls,
            usage=LLMUsage(resp.usage.input_tokens, resp.usage.output_tokens),
            stop_reason=resp.stop_reason,
        )


class OpenAIClient(LLMClient):
    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None) -> None:
        super().__init__(model)
        try:
            import openai
        except ImportError as exc:  # pragma: no cover
            raise AdapterError(
                "the openai package is required; install reforge with the [judge] extra"
            ) from exc
        self._client = openai.OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url or os.environ.get("REFORGE_OPENAI_BASE_URL"),
        )

    def chat(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AssistantTurn:
        payload = _to_openai_messages(system, messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": payload,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        resp = self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        tool_calls = [
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=json.loads(tc.function.arguments or "{}"),
            )
            for tc in (choice.message.tool_calls or [])
        ]
        usage = resp.usage
        return AssistantTurn(
            text=choice.message.content,
            tool_calls=tool_calls,
            usage=LLMUsage(
                usage.prompt_tokens if usage else 0,
                usage.completion_tokens if usage else 0,
            ),
            stop_reason=choice.finish_reason,
        )


def make_client(
    model: str,
    *,
    provider: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LLMClient:
    """Pick a backend by explicit provider or by the model name."""
    resolved = provider or ("anthropic" if model.startswith("claude") else "openai")
    if resolved == "anthropic":
        return AnthropicClient(model, api_key=api_key)
    if resolved == "openai":
        return OpenAIClient(model, api_key=api_key, base_url=base_url)
    raise AdapterError(f"unknown LLM provider: {resolved}")


def _to_anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg["role"]
        if role == "tool":
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg["tool_call_id"],
                            "content": msg["content"],
                        }
                    ],
                }
            )
        elif role == "assistant" and msg.get("tool_calls"):
            content: list[dict[str, Any]] = []
            if msg.get("content"):
                content.append({"type": "text", "text": msg["content"]})
            for tc in msg["tool_calls"]:
                content.append(
                    {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                )
            out.append({"role": "assistant", "content": content})
        else:
            out.append({"role": role, "content": msg["content"]})
    return out


def _to_openai_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for msg in messages:
        role = msg["role"]
        if role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": msg["content"],
                }
            )
        elif role == "assistant" and msg.get("tool_calls"):
            out.append(
                {
                    "role": "assistant",
                    "content": msg.get("content") or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in msg["tool_calls"]
                    ],
                }
            )
        else:
            out.append({"role": role, "content": msg["content"]})
    return out
