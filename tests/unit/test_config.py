"""Tests for project config loading (reforge.toml / pyproject [tool.reforge])."""

from __future__ import annotations

from pathlib import Path

from reforge.config import load_project_config


def test_reforge_toml_wins(tmp_path: Path) -> None:
    (tmp_path / "reforge.toml").write_text(
        'adapter = "api-agent"\nconcurrency = 4\n', encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text('[tool.reforge]\nadapter = "gold"\n', encoding="utf-8")
    cfg = load_project_config(tmp_path)
    assert cfg["adapter"] == "api-agent"
    assert cfg["concurrency"] == 4


def test_pyproject_fallback(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.reforge]\nmodel = "claude-sonnet-4-6"\nfail_under = 0.8\n', encoding="utf-8"
    )
    cfg = load_project_config(tmp_path)
    assert cfg["model"] == "claude-sonnet-4-6"
    assert cfg["fail_under"] == 0.8


def test_no_config_is_empty(tmp_path: Path) -> None:
    assert load_project_config(tmp_path) == {}
