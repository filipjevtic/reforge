"""Scorer interface and the context handed to each scorer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from reforge.runtime.base import ContainerHandle
from reforge.spec.models import TaskSpec


@dataclass
class TaskScoringContext:
    """Inputs available to every scorer after the agent has run."""

    spec: TaskSpec
    container: ContainerHandle
    diff: str  # unified diff the agent produced (may be empty)
    workspace_path: str


@dataclass
class ScorerResult:
    """A normalized sub-score plus a boolean view and scorer-specific detail."""

    key: str
    score: float  # normalized to [0, 1]
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)


class Scorer(ABC):
    key: str = ""

    @abstractmethod
    def score(self, ctx: TaskScoringContext) -> ScorerResult:
        """Compute this scorer's contribution for one task."""
