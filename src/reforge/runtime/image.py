"""Image tagging and build caching.

The tag for a task image is derived from the Dockerfile contents plus build args,
so identical environments reuse one image and edits invalidate it. Builds are
serialized per tag with a lock, so parallel task runs never build the same image
twice at once.
"""

from __future__ import annotations

import threading
from pathlib import Path

from reforge.runtime.base import ContainerRuntime
from reforge.spec.models import TaskSpec
from reforge.utils.errors import SpecError
from reforge.utils.hashing import hash_text, short

_build_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_digest_cache: dict[str, str] = {}


def image_tag(spec: TaskSpec) -> str:
    """Deterministic image tag for a task's environment."""
    dockerfile_path = spec.task_dir / spec.environment.dockerfile
    if not dockerfile_path.is_file():
        raise SpecError(f"Dockerfile not found: {dockerfile_path}")
    payload = dockerfile_path.read_text(encoding="utf-8") + repr(
        sorted(spec.environment.build_args.items())
    )
    return f"reforge/{spec.id}:{short(hash_text(payload))}"


def _lock_for(tag: str) -> threading.Lock:
    with _locks_guard:
        return _build_locks.setdefault(tag, threading.Lock())


def build_task_image(
    runtime: ContainerRuntime, spec: TaskSpec, *, no_cache: bool = False
) -> tuple[str, str]:
    """Build (or reuse) the image for a task. Returns ``(tag, digest)``."""
    tag = image_tag(spec)
    with _lock_for(tag):
        if not no_cache and tag in _digest_cache:
            return tag, _digest_cache[tag]
        digest = runtime.build_image(
            context_dir=spec.task_dir,
            dockerfile=spec.environment.dockerfile,
            tag=tag,
            build_args=spec.environment.build_args,
        )
        _digest_cache[tag] = digest
        return tag, digest


def _reset_cache_for_tests() -> None:
    _digest_cache.clear()


# Re-exported for callers that only need the location.
__all__ = ["Path", "build_task_image", "image_tag"]
