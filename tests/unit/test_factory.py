"""Tests for runtime backend selection."""

from __future__ import annotations

import pytest

from reforge.runtime.docker_runtime import DockerRuntime
from reforge.runtime.factory import _podman_socket, make_runtime
from reforge.utils.errors import ConfigError


def test_docker_runtime_default() -> None:
    rt = make_runtime("docker")
    assert isinstance(rt, DockerRuntime)
    assert rt._base_url is None


def test_podman_runtime_labeled() -> None:
    rt = make_runtime("podman")
    assert isinstance(rt, DockerRuntime)
    assert rt._label == "podman"


def test_unknown_runtime_raises() -> None:
    with pytest.raises(ConfigError):
        make_runtime("containerd")


def test_podman_socket_respects_docker_host(monkeypatch) -> None:
    monkeypatch.setenv("DOCKER_HOST", "unix:///custom.sock")
    assert _podman_socket() is None


def test_podman_socket_default(monkeypatch) -> None:
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    socket = _podman_socket()
    assert socket is not None and socket.startswith("unix://") and "podman.sock" in socket
