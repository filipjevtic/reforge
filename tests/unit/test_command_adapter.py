"""Tests for the generic command adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from reforge.adapters.base import AdapterInput
from reforge.adapters.registry import load_adapter
from reforge.utils.errors import AdapterError
from tests.unit.fakes import FakeContainer


def _input(tmp_path: Path, container: FakeContainer, config: dict) -> AdapterInput:
    return AdapterInput(
        instruction="do the thing",
        workspace_path="/workspace",
        container=container,
        trace_path=tmp_path / "trace.log",
        model="some-model",
        config=config,
    )


def test_command_requires_command(tmp_path: Path) -> None:
    adapter = load_adapter("command")
    with pytest.raises(AdapterError):
        adapter.validate(_input(tmp_path, FakeContainer(), {}))


def test_command_runs_and_exposes_env(tmp_path: Path) -> None:
    adapter = load_adapter("command")
    container = FakeContainer()
    result = adapter.run(_input(tmp_path, container, {"command": "echo hi"}))
    assert result.success is True
    # The command is run through sh -c.
    assert container.calls[-1][:2] == ["sh", "-c"]
    assert "echo hi" in container.calls[-1][2]
