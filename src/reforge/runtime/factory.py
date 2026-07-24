"""Select a container runtime backend by name.

``docker`` uses the local Docker daemon. ``podman`` reuses the same, well-tested
docker-py code path pointed at Podman's Docker-compatible API socket: Podman
exposes an API that docker-py speaks, so this is the tested runtime talking to a
different daemon rather than a separate, unverified backend. Set ``DOCKER_HOST``
to override the socket for either.
"""

from __future__ import annotations

import os

from reforge.runtime.base import ContainerRuntime
from reforge.runtime.docker_runtime import DockerRuntime
from reforge.utils.errors import ConfigError


def make_runtime(name: str = "docker") -> ContainerRuntime:
    name = name.lower()
    if name == "docker":
        return DockerRuntime()
    if name == "podman":
        return DockerRuntime(base_url=_podman_socket(), label="podman")
    raise ConfigError(f"unknown runtime '{name}'; expected 'docker' or 'podman'")


def _podman_socket() -> str | None:
    """Resolve the Podman API socket.

    Prefer an explicit DOCKER_HOST; otherwise use the rootless per-user socket,
    falling back to the system socket. Returning None lets docker-py read the
    environment itself.
    """
    if os.environ.get("DOCKER_HOST"):
        return None
    uid = os.getuid() if hasattr(os, "getuid") else None
    if uid:
        rootless = f"/run/user/{uid}/podman/podman.sock"
        if os.path.exists(rootless):
            return f"unix://{rootless}"
    return "unix:///run/podman/podman.sock"
