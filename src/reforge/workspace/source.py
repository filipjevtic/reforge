"""Resolve a task's source codebase into a local directory.

Supports three source types: a local path shipped with the task, a git repo
pinned to a commit, and a tarball. Returns the resolved ref (a commit SHA for
git sources) so it can be recorded in run provenance.
"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path

from reforge.spec.models import SourceType, TaskSpec
from reforge.utils.errors import SourceError


def resolve_source(spec: TaskSpec, dest: Path) -> str | None:
    """Materialize the codebase into ``dest`` (created fresh). Return the ref."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    source = spec.source
    if source.type is SourceType.local:
        _resolve_local(spec, dest)
        return None
    if source.type is SourceType.git:
        return _resolve_git(spec, dest)
    if source.type is SourceType.tarball:
        _resolve_tarball(spec, dest)
        return None
    raise SourceError(f"unsupported source type: {source.type}")  # pragma: no cover


def _apply_subdir(root: Path, subdir: str) -> Path:
    if not subdir:
        return root
    target = root / subdir
    if not target.is_dir():
        raise SourceError(f"source.subdir not found: {subdir}")
    return target


def _copy_tree(src: Path, dest: Path) -> None:
    for child in src.iterdir():
        target = dest / child.name
        if child.is_dir():
            shutil.copytree(child, target, symlinks=True)
        else:
            shutil.copy2(child, target)


def _resolve_local(spec: TaskSpec, dest: Path) -> None:
    assert spec.source.path is not None
    src_root = (spec.task_dir / spec.source.path).resolve()
    if not src_root.is_dir():
        raise SourceError(f"source.path is not a directory: {src_root}")
    _copy_tree(_apply_subdir(src_root, spec.source.subdir), dest)
    return None


def _resolve_git(spec: TaskSpec, dest: Path) -> str:
    repo, ref = spec.source.repo, spec.source.ref
    assert repo is not None and ref is not None
    try:
        subprocess.run(
            ["git", "clone", "--no-checkout", repo, str(dest)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", str(dest), "checkout", "--detach", ref],
            check=True,
            capture_output=True,
            text=True,
        )
        resolved = subprocess.run(
            ["git", "-C", str(dest), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise SourceError(f"git source failed: {exc.stderr or exc}") from exc

    if spec.source.subdir:
        sub = _apply_subdir(dest, spec.source.subdir)
        _flatten_subdir(sub, dest)
    return resolved


def _resolve_tarball(spec: TaskSpec, dest: Path) -> None:
    assert spec.source.archive is not None
    archive = (spec.task_dir / spec.source.archive).resolve()
    if not archive.is_file():
        raise SourceError(f"source.archive not found: {archive}")
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")
    if spec.source.subdir:
        _flatten_subdir(_apply_subdir(dest, spec.source.subdir), dest)
    return None


def _flatten_subdir(subdir: Path, dest: Path) -> None:
    """Move the contents of ``subdir`` up to ``dest`` and drop everything else."""
    staging = dest.parent / (dest.name + ".subdir")
    shutil.move(str(subdir), str(staging))
    shutil.rmtree(dest)
    shutil.move(str(staging), str(dest))
