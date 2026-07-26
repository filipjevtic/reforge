"""Adapter for the Claude Code CLI.

Runs `claude` in headless mode inside the task container. The container image must
have the `claude` CLI installed and the task must allow network access, since the
CLI calls the API from inside the container. The host's ANTHROPIC_API_KEY is
forwarded in.
"""

from __future__ import annotations

import dataclasses
import os

from reforge.adapters.base import AdapterInput, AdapterResult, AgentAdapter
from reforge.adapters.process import require_binary, run_cli
from reforge.utils.errors import AdapterError


class ClaudeCodeAdapter(AgentAdapter):
    name = "claude-code"
    version = "1.0.0"

    def validate(self, input: AdapterInput) -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise AdapterError("claude-code needs ANTHROPIC_API_KEY in the environment")
        require_binary(input, "claude")

    def run(self, input: AdapterInput) -> AdapterResult:
        env = dict(input.env)
        env["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY", "")
        env["REFORGE_INSTRUCTION"] = input.instruction

        # Wrap in sh so the values expand from the environment and quoting is safe;
        # never interpolate instruction/model into the command string directly.
        shell_cmd = 'claude -p "$REFORGE_INSTRUCTION" --dangerously-skip-permissions'
        if input.model:
            env["REFORGE_MODEL"] = input.model
            shell_cmd += ' --model "$REFORGE_MODEL"'

        merged = dataclasses.replace(input, env=env)
        return run_cli(merged, ["sh", "-c", shell_cmd], metadata={"model": input.model or ""})
