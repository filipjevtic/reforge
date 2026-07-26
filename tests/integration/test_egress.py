"""Egress allowlist end to end (requires Docker).

Hermetic: an upstream HTTP server runs on the default bridge, and a task container
confined to the egress proxy may reach it only when its IP is allowlisted. No real
internet is used.
"""

from __future__ import annotations

import time

import pytest

from reforge.runtime.docker_runtime import DockerRuntime
from reforge.runtime.limits import ResourceLimits

pytestmark = pytest.mark.docker


def _bridge_ip(container) -> str:  # type: ignore[no-untyped-def]
    """The container's IP on the default bridge, waiting briefly for assignment."""
    for _ in range(20):
        container.reload()
        net = container.attrs["NetworkSettings"]
        ip = net.get("IPAddress") or net.get("Networks", {}).get("bridge", {}).get("IPAddress", "")
        if ip:
            return str(ip)
        time.sleep(0.25)
    return ""


@pytest.fixture(scope="module")
def runtime() -> DockerRuntime:
    rt = DockerRuntime()
    if not rt.is_available():
        pytest.skip("Docker daemon not available")
    return rt


def _get(container, url: str) -> int:  # type: ignore[no-untyped-def]
    """Exit code of a proxied urllib GET from inside the task container."""
    code = f"import urllib.request\nurllib.request.urlopen('{url}', timeout=15).read()\n"
    return container.exec(["python", "-c", code]).exit_code


def test_allowlist_permits_only_listed_hosts(runtime: DockerRuntime) -> None:
    client = runtime._get_client()
    upstream = client.containers.run(
        "python:3.12-slim",
        ["python", "-m", "http.server", "80"],
        detach=True,
        tty=False,
    )
    task = None
    try:
        ip = _bridge_ip(upstream)
        assert ip, "upstream did not get a bridge IP"

        # Allowlist the upstream IP only. A different address must be blocked.
        limits = ResourceLimits(network="bridge")
        task = runtime.run_container(
            image="python:3.12-slim",
            workdir="/tmp",
            limits=limits,
            egress_hosts=[ip],
        )
        # Give the proxy a moment to bind.
        task.exec(["sh", "-c", "sleep 2"])

        assert _get(task, f"http://{ip}/") == 0  # allowlisted -> reaches upstream
        assert _get(task, "http://10.255.255.1/") != 0  # not allowlisted -> proxy 403
    finally:
        if task is not None:
            task.stop()
        upstream.remove(force=True)
