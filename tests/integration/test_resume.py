"""Resume skips already-scored tasks (requires Docker)."""

from __future__ import annotations

from pathlib import Path

import pytest

from reforge.report.models import TaskResult
from reforge.runner.orchestrator import run_dataset
from reforge.runner.run_context import make_run_context
from reforge.runtime.docker_runtime import DockerRuntime
from reforge.spec import load_task

pytestmark = pytest.mark.docker

TINY_TASK = Path(__file__).parent.parent / "fixtures" / "tiny-task"


@pytest.fixture(scope="module")
def runtime() -> DockerRuntime:
    rt = DockerRuntime()
    if not rt.is_available():
        pytest.skip("Docker daemon not available")
    return rt


def test_resume_loads_prior_result_instead_of_rerunning(
    runtime: DockerRuntime, tmp_path: Path
) -> None:
    ctx = make_run_context(run_id="it-resume", output_root=tmp_path, adapter="gold", model=None)
    spec = load_task(TINY_TASK)

    first = run_dataset([spec], ctx, runtime, dataset_name="d")
    assert first.results[0].resolved is True

    # Poison the stored result with a sentinel score. If resume re-runs the task,
    # gold would score 1.0; if it loads from disk, we see the sentinel.
    result_path = ctx.result_file(spec.id, 0)
    poisoned = TaskResult.model_validate_json(result_path.read_text(encoding="utf-8"))
    poisoned.final_score = 0.4242
    result_path.write_text(poisoned.model_dump_json(), encoding="utf-8")

    resumed = run_dataset([spec], ctx, runtime, dataset_name="d", resume=True)
    assert resumed.results[0].final_score == 0.4242  # loaded, not re-run
