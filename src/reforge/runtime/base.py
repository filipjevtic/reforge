"""Runtime abstraction: build images, run containers, exec commands, copy files.

Agent adapters and the task runner talk to these interfaces, never to Docker
directly. That keeps adapters portable and leaves room for a future rootless or
Podman backend without touching the rest of the code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from reforge.runtime.limits import ResourceLimits


@dataclass
class ExecResult:
    """Outcome of a command run inside a container."""

    exit_code: int
    output: str  # combined stdout+stderr, captured (may be truncated by caller)
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class ContainerHandle(ABC):
    """A running container. Adapters drive their agent through this interface."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Short container id, for logging."""

    @abstractmethod
    def exec(
        self,
        cmd: list[str],
        *,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
        timeout_s: int | None = None,
        stream_to: IO[str] | Path | None = None,
    ) -> ExecResult:
        """Run ``cmd`` inside the container.

        If ``stream_to`` is given, combined output is written there as it is
        produced (a file path is opened for the duration). On ``timeout_s`` the
        process is killed and ``ExecResult.timed_out`` is set.
        """

    @abstractmethod
    def copy_in(self, src: Path, dest_dir: str) -> None:
        """Copy a host file or directory tree to ``dest_dir`` in the container."""

    @abstractmethod
    def read_file(self, path: str) -> bytes:
        """Read a single file from the container."""

    @abstractmethod
    def stop(self) -> None:
        """Stop and remove the container. Idempotent."""


class ContainerRuntime(ABC):
    """Factory for images and containers."""

    @abstractmethod
    def is_available(self) -> bool:
        """True if the backend (e.g. the Docker daemon) can be reached."""

    @abstractmethod
    def build_image(
        self,
        *,
        context_dir: Path,
        dockerfile: str,
        tag: str,
        build_args: dict[str, str] | None = None,
    ) -> str:
        """Build an image and return its digest (``sha256:...``)."""

    @abstractmethod
    def run_container(
        self,
        *,
        image: str,
        workdir: str,
        limits: ResourceLimits,
        env: dict[str, str] | None = None,
    ) -> ContainerHandle:
        """Start a long-lived container (sleeps) and return a handle to it."""
