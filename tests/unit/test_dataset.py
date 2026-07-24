"""Tests for dataset source resolution (local + hf:)."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from reforge.dataset import resolve_dataset_source
from reforge.utils.errors import ConfigError


def test_local_source_is_a_path() -> None:
    assert resolve_dataset_source("./tasks") == Path("./tasks")


def test_hf_source_calls_snapshot_download(monkeypatch, tmp_path: Path) -> None:
    calls = {}

    def fake_snapshot_download(repo_id: str, repo_type: str, revision=None) -> str:
        calls["repo_id"] = repo_id
        calls["repo_type"] = repo_type
        calls["revision"] = revision
        return str(tmp_path)

    fake_module = types.ModuleType("huggingface_hub")
    fake_module.snapshot_download = fake_snapshot_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_module)

    result = resolve_dataset_source("hf:acme/reforge-tasks@v1")
    assert result == tmp_path
    assert calls == {"repo_id": "acme/reforge-tasks", "repo_type": "dataset", "revision": "v1"}


def test_hf_source_without_revision(monkeypatch, tmp_path: Path) -> None:
    def fake_snapshot_download(repo_id: str, repo_type: str, revision=None) -> str:
        assert revision is None
        return str(tmp_path)

    fake_module = types.ModuleType("huggingface_hub")
    fake_module.snapshot_download = fake_snapshot_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_module)

    assert resolve_dataset_source("hf:acme/reforge-tasks") == tmp_path


def test_hf_missing_package_raises(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    with pytest.raises(ConfigError):
        resolve_dataset_source("hf:acme/reforge-tasks")


def test_hf_empty_repo_raises(monkeypatch, tmp_path: Path) -> None:
    fake_module = types.ModuleType("huggingface_hub")
    fake_module.snapshot_download = lambda **k: str(tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_module)
    with pytest.raises(ConfigError):
        resolve_dataset_source("hf:")
