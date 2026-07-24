"""Tests for resource-limit translation to docker kwargs."""

from __future__ import annotations

from reforge.runtime.limits import ResourceLimits
from reforge.spec.models import Resources


def test_from_spec_and_override() -> None:
    limits = ResourceLimits.from_spec(Resources(), network_override="bridge")
    assert limits.network == "bridge"


def test_docker_kwargs_hardening() -> None:
    kwargs = ResourceLimits(cpus=2.0, memory="4g", pids=512, network="none").to_docker_kwargs()
    assert kwargs["nano_cpus"] == 2_000_000_000
    assert kwargs["mem_limit"] == "4g"
    assert kwargs["pids_limit"] == 512
    assert kwargs["network_mode"] == "none"
    assert kwargs["cap_drop"] == ["ALL"]
    assert "no-new-privileges" in kwargs["security_opt"]
