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


class FakeFsContainer(ContainerHandle):
    """A container backed by an in-memory file tree.

    Supports the two commands the dependency scorer issues: ``find . -type f`` and
    ``cat <path>``. Paths in ``files`` are workspace-relative (no leading ./).
    """

    def __init__(self, files: dict[str, str]) -> None:
        self.files = files

    @property
    def id(self) -> str:
        return "fakefs"

    def exec(
        self,
        cmd: list[str],
        *,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
        timeout_s: int | None = None,
        stream_to: IO[str] | Path | None = None,
    ) -> ExecResult:
        joined = " ".join(cmd)
        if "find . -type f" in joined:
            listing = "\n".join(f"./{p}" for p in sorted(self.files))
            return ExecResult(exit_code=0, output=listing, timed_out=False)
        if cmd[0] == "cat":
            path = cmd[1]
            if path in self.files:
                return ExecResult(exit_code=0, output=self.files[path], timed_out=False)
            return ExecResult(exit_code=1, output="", timed_out=False)
        return ExecResult(exit_code=0, output="", timed_out=False)

    def copy_in(self, src: Path, dest_dir: str) -> None:
        return None

    def read_file(self, path: str) -> bytes:
        return b""

    def stop(self) -> None:
        return None
