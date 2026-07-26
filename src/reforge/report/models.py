"""Serializable result models for a single task and a whole run."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SubScore(BaseModel):
    score: float
    passed: bool
    detail: dict[str, Any] = Field(default_factory=dict)


class TokenCounts(BaseModel):
    input: int = 0
    output: int = 0
    total: int = 0


class Provenance(BaseModel):
    tool_version: str
    adapter: str
    adapter_version: str = ""
    model: str | None = None
    image_tag: str | None = None
    image_digest: str | None = None
    source_ref: str | None = None
    judge_model: str | None = None


class TaskResult(BaseModel):
    task_id: str
    category: str
    tags: list[str] = Field(default_factory=list)
    adapter: str
    model: str | None = None

    resolved: bool = False
    final_score: float = 0.0
    gated: bool = False
    scores: dict[str, SubScore] = Field(default_factory=dict)
    weights_used: dict[str, float] = Field(default_factory=dict)

    agent_success: bool = False
    error: str | None = None
    cost_usd: float | None = None
    tokens: TokenCounts = Field(default_factory=TokenCounts)
    duration_s: float = 0.0

    artifacts: dict[str, str] = Field(default_factory=dict)
    provenance: Provenance | None = None


class LeaderboardRow(BaseModel):
    adapter: str
    model: str | None = None
    tasks: int = 0
    resolved: int = 0
    resolved_rate: float = 0.0
    mean_final_score: float = 0.0
    by_category: dict[str, dict[str, float]] = Field(default_factory=dict)
    mean_dep_coverage: float | None = None
    total_cost_usd: float = 0.0
    mean_duration_s: float = 0.0


class TaskStat(BaseModel):
    """Per-task aggregation across repeated runs (variance signal)."""

    task_id: str
    category: str
    runs: int = 0
    resolved: int = 0
    resolved_rate: float = 0.0
    mean_final_score: float = 0.0
    stdev_final_score: float = 0.0


class RunReport(BaseModel):
    run_id: str
    tool_version: str
    dataset: str
    adapter: str
    model: str | None = None
    repeats: int = 1
    budget_usd: float | None = None
    total_cost_usd: float = 0.0
    budget_exhausted: bool = False
    results: list[TaskResult] = Field(default_factory=list)
    leaderboard: list[LeaderboardRow] = Field(default_factory=list)
    task_stats: list[TaskStat] = Field(default_factory=list)
