"""Pydantic models for a reforge task specification.

A task lives in a directory. ``task.yaml`` is parsed into :class:`TaskSpec`; the
Dockerfile, verifier scripts, and gold solution sit beside it as real files. One
unified schema covers both task categories. A ``category`` field plus which
blocks the author fills in is what distinguishes a replication task from a
new-feature task.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# Suggested categories; `category` is free-form so any domain (cloud-infra,
# devops, ai-dev, app-feature, ...) is first-class without a code change.
SUGGESTED_CATEGORIES = ("replication", "new_feature")


class SourceType(StrEnum):
    git = "git"
    local = "local"
    tarball = "tarball"


class TestFramework(StrEnum):
    pytest = "pytest"
    jest = "jest"
    gotest = "gotest"
    junit = "junit"
    custom = "custom"


class NetworkMode(StrEnum):
    none = "none"
    bridge = "bridge"


class Source(_Model):
    """Where the codebase-under-test comes from."""

    type: SourceType
    repo: str | None = Field(default=None, description="Git URL when type=git.")
    ref: str | None = Field(default=None, description="Commit SHA (pin for reproducibility).")
    path: str | None = Field(default=None, description="Path when type=local (task-dir relative).")
    archive: str | None = Field(default=None, description="Tarball path when type=tarball.")
    subdir: str = Field(default="", description="Treat this subdirectory as the workspace root.")
    strip_git: bool = Field(default=True, description="Remove .git before the agent runs.")

    @model_validator(mode="after")
    def _check_fields_for_type(self) -> Source:
        if self.type is SourceType.git and not self.repo:
            raise ValueError("source.repo is required when type=git")
        if self.type is SourceType.git and not self.ref:
            raise ValueError("source.ref (commit SHA) is required when type=git")
        if self.type is SourceType.local and not self.path:
            raise ValueError("source.path is required when type=local")
        if self.type is SourceType.tarball and not self.archive:
            raise ValueError("source.archive is required when type=tarball")
        return self


class Environment(_Model):
    """The container image the task runs in."""

    dockerfile: str = Field(default="Dockerfile", description="Path relative to the task dir.")
    build_args: dict[str, str] = Field(default_factory=dict)
    workdir: str = Field(default="/workspace")


class Context(_Model):
    """What the agent may see. Hidden paths are removed before the agent runs."""

    visible_paths: list[str] = Field(default_factory=lambda: ["**"])
    hidden_paths: list[str] = Field(default_factory=list)


class ExpectedFile(_Model):
    path: str
    must_exist: bool = True


class ExpectedArtifacts(_Model):
    files: list[ExpectedFile] = Field(default_factory=list)


class Verification(_Model):
    """Deterministic test verification (SWE-bench FAIL_TO_PASS / PASS_TO_PASS)."""

    entrypoint: str = Field(description="Script in verifier/ the harness execs to run tests.")
    framework: TestFramework = TestFramework.pytest
    fail_to_pass: list[str] = Field(
        default_factory=list,
        description="Tests that must go from failing to passing (the work got done).",
    )
    pass_to_pass: list[str] = Field(
        default_factory=list,
        description="Tests that must stay green (no regressions).",
    )
    timeout_s: int = Field(default=900, gt=0)


class RequiredDeps(_Model):
    """Ground-truth dependencies a correct solution must wire up."""

    services: list[str] = Field(default_factory=list)
    config_refs: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)


class Detector(_Model):
    """How to detect what the agent actually wired up, scoped by a glob."""

    type: str = Field(description="Detector name, e.g. python_imports or env_refs.")
    scope: str = Field(default="**", description="Glob limiting which files to inspect.")


class DependencyCoverage(_Model):
    required: RequiredDeps = Field(default_factory=RequiredDeps)
    detectors: list[Detector] = Field(default_factory=list)

    def is_empty(self) -> bool:
        req = self.required
        return not (req.services or req.config_refs or req.imports)


class RubricCriterion(_Model):
    id: str
    weight: float = Field(gt=0)
    prompt: str
    scale: tuple[int, int] = Field(default=(0, 5))

    @model_validator(mode="after")
    def _check_scale(self) -> RubricCriterion:
        lo, hi = self.scale
        if hi <= lo:
            raise ValueError(f"rubric criterion '{self.id}': scale max must exceed min")
        return self


class Rubric(_Model):
    criteria: list[RubricCriterion] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.criteria


DEFAULT_WEIGHTS = {"tests": 0.5, "dependency_coverage": 0.25, "judge": 0.25}


class ScoringGate(_Model):
    require_pass_to_pass: bool = True


class Scoring(_Model):
    # Keys are scorer names ("tests", "dependency_coverage", "judge", or any
    # registered scorer). Same YAML shape as before, now open to plugin scorers.
    weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    gate: ScoringGate = Field(default_factory=ScoringGate)

    @model_validator(mode="after")
    def _check_weights(self) -> Scoring:
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("scoring.weights values must be >= 0")
        if sum(self.weights.values()) <= 0:
            raise ValueError("scoring.weights must sum to a positive number")
        return self


class Resources(_Model):
    """Isolation and resource limits applied to the task container."""

    cpus: float = Field(default=2.0, gt=0)
    memory: str = Field(default="4g")
    pids: int = Field(default=512, gt=0)
    network: NetworkMode = NetworkMode.none
    agent_timeout_s: int = Field(default=1800, gt=0)
    disk_quota: str | None = None


class TaskSpec(_Model):
    """A single benchmark task, parsed from ``task.yaml``."""

    schema_version: int = SCHEMA_VERSION
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    category: str = Field(
        min_length=1,
        description="Free-form domain label, e.g. replication, devops, cloud-infra.",
    )
    tags: list[str] = Field(default_factory=list, description="Cross-cutting labels for filtering.")
    title: str
    description: str = ""

    source: Source
    environment: Environment = Field(default_factory=Environment)
    instruction: str
    context: Context = Field(default_factory=Context)
    expected_artifacts: ExpectedArtifacts = Field(default_factory=ExpectedArtifacts)
    verification: Verification
    dependency_coverage: DependencyCoverage = Field(default_factory=DependencyCoverage)
    rubric: Rubric = Field(default_factory=Rubric)
    scoring: Scoring = Field(default_factory=Scoring)
    resources: Resources = Field(default_factory=Resources)

    # Populated by the loader; not part of task.yaml.
    task_dir: Path = Field(default=Path("."), exclude=True)

    @model_validator(mode="after")
    def _check_schema_version(self) -> TaskSpec:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version {self.schema_version}; "
                f"this build understands version {SCHEMA_VERSION}"
            )
        return self

    def with_dir(self, task_dir: Path) -> TaskSpec:
        """Return a copy that knows where it was loaded from."""
        return self.model_copy(update={"task_dir": task_dir})
