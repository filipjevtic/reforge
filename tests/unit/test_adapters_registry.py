"""Tests for adapter discovery and the no-LLM reference adapters."""

from __future__ import annotations

from pathlib import Path

import pytest

from reforge.adapters.base import AdapterInput
from reforge.adapters.registry import available_adapters, load_adapter
from reforge.utils.errors import AdapterError


def test_builtin_adapters_are_registered() -> None:
    names = available_adapters()
    assert "noop" in names
    assert "gold" in names


def test_load_unknown_adapter_raises() -> None:
    with pytest.raises(AdapterError):
        load_adapter("does-not-exist")


def test_noop_adapter_makes_no_changes(tmp_path: Path) -> None:
    adapter = load_adapter("noop")
    trace = tmp_path / "trace.log"
    result = adapter.run(
        AdapterInput(
            instruction="do nothing",
            workspace_path="/workspace",
            container=None,  # type: ignore[arg-type]  # noop never touches it
            trace_path=trace,
        )
    )
    assert result.success is True
    assert trace.exists()


def test_gold_adapter_validate_requires_patch(tmp_path: Path) -> None:
    adapter = load_adapter("gold")
    with pytest.raises(AdapterError):
        adapter.validate(
            AdapterInput(
                instruction="",
                workspace_path="/workspace",
                container=None,  # type: ignore[arg-type]
                trace_path=tmp_path / "t.log",
                config={},
            )
        )
