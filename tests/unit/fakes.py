"""Lightweight fakes for unit-testing adapters without Docker."""

from __future__ import annotations

from pathlib import Path
from typing import IO

from reforge.runtime.base import ContainerHandle, ExecResult


class FakeContainer(ContainerHandle):
    """Records exec calls and returns scripted results.

    ``responses`` maps a substring of the joined command to an ExecResult; the
    first matching entry wins. Anything unmatched returns exit 0 with no output.
    """

    def __init__(self, responses: dict[str, ExecResult] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.responses = responses or {}

    @property
    def id(self) -> str:
        return "fake"

    def exec(
        self,
        cmd: list[str],
        *,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
        timeout_s: int | None = None,
        stream_to: IO[str] | Path | None = None,
    ) -> ExecResult:
        self.calls.append(cmd)
        joined = " ".join(cmd)
        for needle, result in self.responses.items():
            if needle in joined:
                return result
        return ExecResult(exit_code=0, output="", timed_out=False)

    def copy_in(self, src: Path, dest_dir: str) -> None:
        return None

    def read_file(self, path: str) -> bytes:
        return b""

    def stop(self) -> None:
        return None
