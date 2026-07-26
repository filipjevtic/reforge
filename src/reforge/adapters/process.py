"""Helpers for adapters that drive an external agent by running a CLI.

Most agent adapters do the same thing: run one command inside the container,
stream its output to the trace file, and report whether it exited cleanly. This
module captures that shape so a CLI-backed adapter is a few lines.
"""

from __future__ import annotations

from reforge.adapters.base import AdapterInput, AdapterResult
from reforge.utils.errors import AdapterError


def require_binary(input: AdapterInput, binary: str) -> None:
    """Raise AdapterError if ``binary`` is not on PATH inside the container."""
    check = input.container.exec(["sh", "-c", f"command -v {binary} >/dev/null 2>&1"])
    if not check.ok:
        raise AdapterError(
            f"'{binary}' is not installed in the task image. "
            f"Add it to the task Dockerfile to use this adapter."
        )


def run_cli(
    input: AdapterInput,
    cmd: list[str],
    *,
    metadata: dict[str, object] | None = None,
) -> AdapterResult:
    """Run ``cmd`` in the container, stream to the trace, and wrap the result."""
    result = input.container.exec(
        cmd,
        workdir=input.workspace_path,
        env=input.env,
        timeout_s=input.timeout_s,
        stream_to=input.trace_path,
    )
    return AdapterResult(
        success=result.ok,
        trace_path=input.trace_path,
        exit_code=result.exit_code,
        metadata=metadata or {},
        error=None if result.ok else _describe_failure(result.exit_code, result.timed_out),
    )


def _describe_failure(exit_code: int, timed_out: bool) -> str:
    if timed_out:
        return "agent timed out"
    return f"agent exited with code {exit_code}"
