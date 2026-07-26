"""A generic bring-your-own-agent adapter.

Runs an arbitrary shell command inside the container. The task instruction and
model are exposed as environment variables, so you can wire up any agent that has
a CLI without writing Python. This is the escape hatch that keeps reforge honest
about being model-agnostic.

Configure it per run with ``--config`` (JSON), e.g.::

    reforge run --task t --adapter command \\
      --config '{"command": "my-agent --model $REFORGE_MODEL \\"$REFORGE_INSTRUCTION\\""}'
"""

from __future__ import annotations

import dataclasses

from reforge.adapters.base import AdapterInput, AdapterResult, AgentAdapter
from reforge.adapters.process import run_cli
from reforge.utils.errors import AdapterError


class CommandAdapter(AgentAdapter):
    name = "command"
    version = "1.0.0"

    def validate(self, input: AdapterInput) -> None:
        if not input.config.get("command"):
            raise AdapterError(
                "command adapter requires config.command, a shell command to run in the container"
            )

    def run(self, input: AdapterInput) -> AdapterResult:
        command = str(input.config["command"])
        env = dict(input.env)
        env["REFORGE_INSTRUCTION"] = input.instruction
        env["REFORGE_MODEL"] = input.model or ""
        env["REFORGE_WORKSPACE"] = input.workspace_path

        merged = dataclasses.replace(input, env=env)
        return run_cli(merged, ["sh", "-c", command], metadata={"command": command})
