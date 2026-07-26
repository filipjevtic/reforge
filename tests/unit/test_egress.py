"""Unit tests for the egress allowlist matcher and validation."""

from __future__ import annotations

from reforge.runtime.egress import egress_allowed
from reforge.spec.models import Environment, Resources, Source, TaskSpec, Verification
from reforge.spec.validate import validate_task


def test_egress_exact_and_subdomain() -> None:
    allowed = {"pypi.org", "githubusercontent.com"}
    assert egress_allowed("pypi.org", allowed)
    assert egress_allowed("files.pypi.org", allowed)  # subdomain
    assert egress_allowed("raw.githubusercontent.com", allowed)
    assert egress_allowed("PyPI.org:443", allowed)  # case + port stripped


def test_egress_denies_others() -> None:
    allowed = {"pypi.org"}
    assert not egress_allowed("evil.com", allowed)
    assert not egress_allowed("notpypi.org", allowed)  # not a real subdomain
    assert not egress_allowed("", allowed)


def _spec(tmp_path, allowed_hosts, network):  # type: ignore[no-untyped-def]
    return TaskSpec(
        id="t",
        category="c",
        title="t",
        instruction="do",
        source=Source(type="local", path="src"),
        verification=Verification(entrypoint="verifier/run_tests.sh", fail_to_pass=["a::b"]),
        environment=Environment(allowed_hosts=allowed_hosts),
        resources=Resources(network=network),
    ).with_dir(tmp_path)


def test_validate_flags_allowlist_without_network(tmp_path) -> None:  # type: ignore[no-untyped-def]
    problems = validate_task(_spec(tmp_path, ["pypi.org"], "none"))
    assert any("allowed_hosts" in p for p in problems)


def test_validate_ok_with_network(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # (other problems like missing files may exist; just assert the egress one does not)
    problems = validate_task(_spec(tmp_path, ["pypi.org"], "bridge"))
    assert not any("allowed_hosts" in p for p in problems)
