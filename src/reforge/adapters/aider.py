"""Adapter for the aider CLI.

Runs aider non-interactively inside the task container. The image must have
`aider` installed and the task must allow network access. Whichever provider key
aider needs (OpenAI or Anthropic) is forwarded from the host if present.
"""

from __future__ import annotations

import os

from reforge.adapters.base import AdapterInput, AdapterResult, AgentAdapter
from reforge.adapters.process import require_binary, run_cli
from reforge.utils.errors import AdapterError

_FORWARDED_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY")


class AiderAdapter(AgentAdapter):
    name = "aider"
    version = "1.0.0"

    def validate(self, input: AdapterInput) -> None:
        if not any(os.environ.get(k) for k in _FORWARDED_KEYS):
            raise AdapterError(
                "aider needs one of " + ", ".join(_FORWARDED_KEYS) + " in the environment"
            )
        require_binary(input, "aider")

    def run(self, input: AdapterInput) -> AdapterResult:
        env = dict(input.env)
        for key in _FORWARDED_KEYS:
            if os.environ.get(key):
                env[key] = os.environ[key]
        env["REFORGE_INSTRUCTION"] = input.instruction

        shell_cmd = 'aider --yes --no-auto-commits --message "$REFORGE_INSTRUCTION"'
        if input.model:
            shell_cmd += f" --model {input.model}"

        merged = AdapterInput(
            instruction=input.instruction,
            workspace_path=input.workspace_path,
            container=input.container,
            trace_path=input.trace_path,
            model=input.model,
            config=input.config,
            env=env,
            logger=input.logger,
            timeout_s=input.timeout_s,
        )
        return run_cli(merged, ["sh", "-c", shell_cmd], metadata={"model": input.model or ""})
