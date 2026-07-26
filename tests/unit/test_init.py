"""Test the init scaffolder produces a validatable task."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from reforge.cli import app
from reforge.spec import load_task, validate_task

runner = CliRunner()


def test_init_scaffold_validates(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", "my-task", "--dir", str(tmp_path), "--category", "devops"])
    assert result.exit_code == 0, result.output

    task_dir = tmp_path / "my-task"
    for rel in ("task.yaml", "Dockerfile", "verifier/run_tests.sh", "gold/solution.patch"):
        assert (task_dir / rel).is_file()

    spec = load_task(task_dir)
    assert spec.category == "devops"
    assert validate_task(spec) == []


def test_init_refuses_existing(tmp_path: Path) -> None:
    (tmp_path / "taken").mkdir()
    result = runner.invoke(app, ["init", "taken", "--dir", str(tmp_path)])
    assert result.exit_code != 0
