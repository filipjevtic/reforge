"""Tests for source resolution and workspace preparation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from reforge.spec.models import Source, TaskSpec, Verification
from reforge.utils.errors import SourceError
from reforge.workspace import prepare_workspace


def _spec(source: Source, hidden: list[str] | None = None) -> TaskSpec:
    from reforge.spec.models import Context

    return TaskSpec(
        id="t",
        category="new_feature",
        title="t",
        instruction="do",
        source=source,
        verification=Verification(entrypoint="verifier/run_tests.sh", fail_to_pass=["a::b"]),
        context=Context(hidden_paths=hidden or []),
    )


def test_local_source_copies_and_strips_git(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "keep.py").write_text("x = 1\n")
    (src / ".git").mkdir()
    (src / ".git" / "HEAD").write_text("ref: refs/heads/main\n")

    task_dir = tmp_path / "task"
    task_dir.mkdir()

    spec = _spec(Source(type="local", path="../src", strip_git=True)).with_dir(task_dir)
    dest = tmp_path / "ws"
    ref = prepare_workspace(spec, dest)

    assert ref is None
    assert (dest / "keep.py").exists()
    assert not (dest / ".git").exists()


def test_hidden_paths_removed(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "keep.py").write_text("x = 1\n")
    (src / "secret.txt").write_text("hidden\n")
    task_dir = tmp_path / "task"
    task_dir.mkdir()

    spec = _spec(Source(type="local", path="../src"), hidden=["secret.txt"]).with_dir(task_dir)
    dest = tmp_path / "ws"
    prepare_workspace(spec, dest)

    assert (dest / "keep.py").exists()
    assert not (dest / "secret.txt").exists()


def test_subdir_traversal_rejected(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "keep.py").write_text("x = 1\n")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret.txt").write_text("nope\n")

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    spec = _spec(Source(type="local", path="../src", subdir="../outside")).with_dir(task_dir)
    with pytest.raises(SourceError, match="escapes"):
        prepare_workspace(spec, tmp_path / "ws")


def test_git_transport_helper_rejected(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    spec = _spec(Source(type="git", repo="ext::sh -c touch&/tmp/pwned", ref="HEAD")).with_dir(
        task_dir
    )
    with pytest.raises(SourceError, match="transport helper"):
        prepare_workspace(spec, tmp_path / "ws")


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_source_pins_to_sha(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *a: subprocess.run(a, cwd=repo, check=True, capture_output=True)  # noqa: E731
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@t")
    run("git", "config", "user.name", "t")
    (repo / "app.py").write_text("print('hi')\n")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "init")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    spec = _spec(Source(type="git", repo=str(repo), ref=sha, strip_git=True)).with_dir(task_dir)
    dest = tmp_path / "ws"
    ref = prepare_workspace(spec, dest)

    assert ref == sha
    assert (dest / "app.py").exists()
    assert not (dest / ".git").exists()
