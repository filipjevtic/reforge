"""Docker implementation of the container runtime, built on docker-py.

Design choices worth knowing:

* Command timeouts are enforced with the in-container ``timeout`` binary (present
  in both coreutils and busybox) rather than by killing the container. That keeps
  the container alive after an agent times out, so we can still capture whatever
  diff it produced. Exit code 124 means the wrapped command was killed.
* Containers run as ``sleep infinity`` and we ``exec`` into them, mirroring how
  SWE-bench and terminal-bench drive a persistent task environment.
"""

from __future__ import annotations

import io
import tarfile
from contextlib import nullcontext
from pathlib import Path
from typing import IO, TYPE_CHECKING

from reforge.runtime.base import ContainerHandle, ContainerRuntime, ExecResult
from reforge.runtime.limits import ResourceLimits
from reforge.utils.errors import RuntimeBackendError
from reforge.utils.logging import get_logger

if TYPE_CHECKING:
    from docker import DockerClient
    from docker.models.containers import Container

log = get_logger("runtime.docker")

# Cap captured output per exec so a runaway agent cannot exhaust memory.
_MAX_CAPTURE_BYTES = 8 * 1024 * 1024


class DockerContainerHandle(ContainerHandle):
    def __init__(self, client: DockerClient, container: Container) -> None:
        self._client = client
        self._container = container
        self._stopped = False

    @property
    def id(self) -> str:
        return str(self._container.short_id)

    def exec(
        self,
        cmd: list[str],
        *,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
        timeout_s: int | None = None,
        stream_to: IO[str] | Path | None = None,
    ) -> ExecResult:
        final_cmd = list(cmd)
        if timeout_s is not None:
            # SIGTERM at the deadline, SIGKILL 10s later if it ignores that.
            final_cmd = ["timeout", "-k", "10", "-s", "TERM", str(timeout_s), *final_cmd]

        api = self._client.api
        try:
            exec_id = api.exec_create(
                self._container.id,
                final_cmd,
                workdir=workdir,
                environment=env or {},
            )["Id"]
            stream = api.exec_start(exec_id, stream=True)
        except Exception as exc:  # docker.errors.APIError and friends
            raise RuntimeBackendError(f"exec failed to start: {exc}") from exc

        captured = bytearray()
        sink_ctx = (
            open(stream_to, "w", encoding="utf-8")  # noqa: SIM115 (closed by contextmanager)
            if isinstance(stream_to, Path)
            else nullcontext(stream_to)
        )
        with sink_ctx as sink:
            for chunk in stream:
                if len(captured) < _MAX_CAPTURE_BYTES:
                    captured.extend(chunk)
                if sink is not None:
                    sink.write(chunk.decode("utf-8", errors="replace"))

        info = api.exec_inspect(exec_id)
        exit_code = info.get("ExitCode")
        exit_code = 0 if exit_code is None else int(exit_code)
        timed_out = timeout_s is not None and exit_code in (124, 137)
        return ExecResult(
            exit_code=exit_code,
            output=captured.decode("utf-8", errors="replace"),
            timed_out=timed_out,
        )

    def copy_in(self, src: Path, dest_dir: str) -> None:
        src = Path(src)
        if not src.exists():
            raise RuntimeBackendError(f"copy_in source does not exist: {src}")

        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            if src.is_dir():
                for child in sorted(src.rglob("*")):
                    tar.add(child, arcname=child.relative_to(src).as_posix())
            else:
                tar.add(src, arcname=src.name)
        buffer.seek(0)

        try:
            self._container.put_archive(dest_dir, buffer.getvalue())
        except Exception as exc:
            raise RuntimeBackendError(f"copy_in failed: {exc}") from exc

    def read_file(self, path: str) -> bytes:
        try:
            stream, _ = self._container.get_archive(path)
        except Exception as exc:
            raise RuntimeBackendError(f"read_file failed for {path}: {exc}") from exc

        raw = io.BytesIO(b"".join(stream))
        with tarfile.open(fileobj=raw, mode="r") as tar:
            member = tar.next()
            if member is None:
                raise RuntimeBackendError(f"read_file: empty archive for {path}")
            extracted = tar.extractfile(member)
            if extracted is None:
                raise RuntimeBackendError(f"read_file: {path} is not a regular file")
            return extracted.read()

    def stop(self) -> None:
        if self._stopped:
            return
        try:
            self._container.remove(force=True)
        except Exception as exc:  # best effort; log and move on
            log.warning("container_remove_failed", container=self.id, error=str(exc))
        finally:
            self._stopped = True


class DockerRuntime(ContainerRuntime):
    def __init__(self) -> None:
        self._client: DockerClient | None = None

    def _get_client(self) -> DockerClient:
        if self._client is None:
            try:
                import docker

                self._client = docker.from_env()
            except Exception as exc:
                raise RuntimeBackendError(
                    "could not connect to Docker; is the daemon running?"
                ) from exc
        return self._client

    def is_available(self) -> bool:
        try:
            self._get_client().ping()
            return True
        except Exception:
            return False

    def build_image(
        self,
        *,
        context_dir: Path,
        dockerfile: str,
        tag: str,
        build_args: dict[str, str] | None = None,
    ) -> str:
        client = self._get_client()
        log.info("image_build_start", tag=tag, dockerfile=dockerfile)
        try:
            image, logs = client.images.build(
                path=str(context_dir),
                dockerfile=dockerfile,
                tag=tag,
                buildargs=build_args or {},
                rm=True,
                forcerm=True,
                pull=False,
            )
        except Exception as exc:
            raise RuntimeBackendError(f"image build failed for {tag}: {exc}") from exc

        for entry in logs:
            line = entry.get("stream", "").rstrip() if isinstance(entry, dict) else ""
            if line:
                log.debug("image_build_log", line=line)

        log.info("image_build_done", tag=tag, digest=image.id)
        return str(image.id)

    def run_container(
        self,
        *,
        image: str,
        workdir: str,
        limits: ResourceLimits,
        env: dict[str, str] | None = None,
    ) -> ContainerHandle:
        client = self._get_client()
        try:
            container = client.containers.run(
                image,
                command=["sleep", "infinity"],
                detach=True,
                working_dir=workdir,
                environment=env or {},
                tty=False,
                **limits.to_docker_kwargs(),
            )
        except Exception as exc:
            raise RuntimeBackendError(f"failed to start container from {image}: {exc}") from exc

        log.info("container_started", container=container.short_id, image=image)
        return DockerContainerHandle(client, container)
