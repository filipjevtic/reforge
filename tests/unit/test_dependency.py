"""Tests for the dependency-coverage scorer and its detectors."""

from __future__ import annotations

from reforge.scoring.base import TaskScoringContext
from reforge.scoring.dependency import (
    DependencyScorer,
    detect_env_refs,
    detect_python_imports,
    detect_service_deps,
)
from reforge.spec.models import (
    DependencyCoverage,
    Detector,
    RequiredDeps,
    Source,
    TaskSpec,
    Verification,
)
from tests.unit.fakes import FakeFsContainer


def test_python_imports_detector() -> None:
    found = detect_python_imports({"a.py": "import os\nfrom app.db import session\n"})
    assert "os" in found
    assert "app.db" in found
    assert "app.db.session" in found


def test_env_refs_detector() -> None:
    found = detect_env_refs({"a.py": 'os.environ["DATABASE_URL"]\nx = os.getenv("REDIS_URL")\n'})
    assert "DATABASE_URL" in found
    assert "REDIS_URL" in found


def test_service_deps_detector() -> None:
    compose = "services:\n  postgres:\n    image: postgres:16\n  redis:\n    image: redis:7\n"
    found = detect_service_deps({"docker-compose.yml": compose})
    assert "postgres" in found
    assert "redis" in found


def _spec_with_deps(required: RequiredDeps, detectors: list[Detector]) -> TaskSpec:
    return TaskSpec(
        id="dep",
        category="replication",
        title="t",
        instruction="do",
        source=Source(type="local", path="src"),
        verification=Verification(entrypoint="verifier/run_tests.sh", fail_to_pass=["a::b"]),
        dependency_coverage=DependencyCoverage(required=required, detectors=detectors),
    )


def test_scorer_reports_missed() -> None:
    spec = _spec_with_deps(
        RequiredDeps(config_refs=["DATABASE_URL", "REDIS_URL", "AWS_REGION"]),
        [Detector(type="env_refs", scope="**")],
    )
    container = FakeFsContainer(
        {"app/config.py": 'os.environ["DATABASE_URL"]\nos.environ["REDIS_URL"]\n'}
    )
    ctx = TaskScoringContext(spec=spec, container=container, diff="", workspace_path="/workspace")
    result = DependencyScorer().score(ctx)
    assert result.passed is False
    assert result.detail["missed"] == ["AWS_REGION"]
    assert result.score == round(2 / 3, 4)


def test_scorer_full_coverage() -> None:
    spec = _spec_with_deps(
        RequiredDeps(services=["postgres"]),
        [Detector(type="service_deps", scope="**")],
    )
    container = FakeFsContainer(
        {"docker-compose.yml": "services:\n  postgres:\n    image: postgres:16\n"}
    )
    ctx = TaskScoringContext(spec=spec, container=container, diff="", workspace_path="/workspace")
    result = DependencyScorer().score(ctx)
    assert result.passed is True
    assert result.score == 1.0
