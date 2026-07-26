"""A minimal but real API-backed coding agent.

Drives any model reachable through :mod:`reforge.llm.client` (Anthropic or any
OpenAI-compatible endpoint, which covers Gemini, Kimi, and friends) around a small
tool loop: list, read, write, and run commands inside the task container. It edits
files in place, so the harness captures its diff the same way it does for every
other adapter.

This is deliberately simple. It exists so the tool works out of the box against a
raw model API, and so frontier and non-frontier models can be compared on the same
scaffold. It is not trying to be a state-of-the-art agent.
"""

from __future__ import annotations

import base64
import json
import os
import shlex
from typing import Any

from reforge.adapters.base import AdapterInput, AdapterResult, AgentAdapter, TokenUsage
from reforge.llm.client import LLMClient, ToolSpec, make_client
from reforge.llm.cost import compute_cost
from reforge.utils.errors import AdapterError

_SYSTEM = """You are a software engineer working inside a repository at {workspace}.
Complete the task by editing files with the provided tools. Work incrementally:
inspect the code first, make focused changes, and use run() to check your work.
When the task is done, call finish(). Keep changes minimal and idiomatic to the
surrounding code. Do not ask questions; make reasonable decisions and proceed."""

_TOOLS = [
    ToolSpec(
        name="list_dir",
        description="List files under a directory (relative to the workspace).",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "default": "."}},
        },
    ),
    ToolSpec(
        name="read_file",
        description="Read a file's contents (relative to the workspace).",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ),
    ToolSpec(
        name="write_file",
        description="Write (create or overwrite) a file with the given contents.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    ),
    ToolSpec(
        name="run",
        description="Run a shell command in the workspace and return its output.",
        parameters={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    ),
    ToolSpec(
        name="finish",
        description="Declare the task complete.",
        parameters={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
        },
    ),
]


class ApiAgentAdapter(AgentAdapter):
    name = "api-agent"
    version = "1.0.0"

    def validate(self, input: AdapterInput) -> None:
        if not input.model:
            raise AdapterError("api-agent requires --model")
        provider = input.config.get("provider")
        is_anthropic = provider == "anthropic" or (
            provider is None and input.model.startswith("claude")
        )
        key_var = "ANTHROPIC_API_KEY" if is_anthropic else "OPENAI_API_KEY"
        if not os.environ.get(key_var):
            raise AdapterError(f"api-agent needs {key_var} in the environment")

    def run(self, input: AdapterInput) -> AdapterResult:
        assert input.model is not None
        client = make_client(
            input.model,
            provider=input.config.get("provider"),
            base_url=input.config.get("base_url"),
        )
        max_steps = int(input.config.get("max_steps", 30))
        usage = TokenUsage()

        with input.trace_path.open("w", encoding="utf-8") as trace:
            return self._loop(input, client, max_steps, usage, trace)

    def _loop(
        self,
        input: AdapterInput,
        client: LLMClient,
        max_steps: int,
        usage: TokenUsage,
        trace: Any,
    ) -> AdapterResult:
        system = _SYSTEM.format(workspace=input.workspace_path)
        messages: list[dict[str, Any]] = [{"role": "user", "content": input.instruction}]
        finished = False
        steps = 0

        for step in range(max_steps):
            steps = step + 1
            turn = client.chat(system=system, messages=messages, tools=_TOOLS, temperature=0.0)
            usage.input_tokens += turn.usage.input_tokens
            usage.output_tokens += turn.usage.output_tokens
            if turn.text:
                trace.write(f"\n[assistant] {turn.text}\n")

            if not turn.tool_calls:
                break

            messages.append(
                {"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls}
            )
            for call in turn.tool_calls:
                if call.name == "finish":
                    finished = True
                    result_text = "ok"
                else:
                    result_text = self._exec_tool(input, call.name, call.arguments, trace)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result_text})
            if finished:
                break

        cost = compute_cost(input.model, usage.input_tokens, usage.output_tokens)
        return AdapterResult(
            success=True,
            trace_path=input.trace_path,
            token_usage=usage,
            cost_usd=cost,
            metadata={"model": input.model, "steps": steps, "finished": finished},
        )

    def _exec_tool(self, input: AdapterInput, name: str, args: dict[str, Any], trace: Any) -> str:
        ws = input.workspace_path
        container = input.container
        trace.write(f"\n[tool] {name} {json.dumps(args)}\n")

        if name == "list_dir":
            path = args.get("path", ".")
            res = container.exec(["sh", "-c", f"ls -la {shlex.quote(path)}"], workdir=ws)
            return _clip(res.output)
        if name == "read_file":
            path = args.get("path")
            if not path:
                return "error: read_file requires a 'path' argument"
            res = container.exec(["cat", path], workdir=ws)
            return _clip(res.output)
        if name == "write_file":
            path = args.get("path")
            content = args.get("content")
            if not path or content is None:
                return "error: write_file requires 'path' and 'content' arguments"
            encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
            script = (
                f'mkdir -p "$(dirname {shlex.quote(path)})" && '
                f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(path)}"
            )
            res = container.exec(["sh", "-c", script], workdir=ws)
            return "written" if res.ok else _clip(res.output)
        if name == "run":
            command = args.get("command")
            if not command:
                return "error: run requires a 'command' argument"
            res = container.exec(
                ["sh", "-c", command], workdir=ws, timeout_s=min(300, input.timeout_s)
            )
            return _clip(f"exit={res.exit_code}\n{res.output}")
        return f"unknown tool: {name}"


def _clip(text: str, limit: int = 8000) -> str:
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"
