"""The agent adapter contract.

An adapter's one job is to drive its agent to modify files under
``input.workspace_path`` inside the container. It never scores anything and it
does not need to report the diff; the harness captures it uniformly with
git after ``run`` returns. This keeps every adapter, from a one-line CLI wrapper
to a full agent, on equal footing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import structlog

    from reforge.runtime.base import ContainerHandle


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class AdapterInput:
    """Everything an adapter needs to run one task."""

    instruction: str
    workspace_path: str
    container: ContainerHandle
    trace_path: Path
    model: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    logger: structlog.stdlib.BoundLogger | None = None
    timeout_s: int = 1800


@dataclass
class AdapterResult:
    """What an adapter reports back. Success means *it ran*, not *it solved it*."""

    success: bool
    trace_path: Path
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    cost_usd: float | None = None
    exit_code: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class AgentAdapter(ABC):
    """Base class every adapter implements."""

    #: Registry key, e.g. ``"claude-code"``. Set on the subclass.
    name: str = ""
    #: Adapter version, recorded in run provenance.
    version: str = "0.0.0"

    def validate(self, input: AdapterInput) -> None:  # noqa: B027 (intentional no-op default)
        """Fail fast before a run: check API keys, model support, binaries.

        Default is a no-op. Adapters that need credentials or an installed CLI
        should override and raise :class:`~reforge.utils.errors.AdapterError`.
        """

    @abstractmethod
    def run(self, input: AdapterInput) -> AdapterResult:
        """Drive the agent to modify files under ``input.workspace_path``."""
