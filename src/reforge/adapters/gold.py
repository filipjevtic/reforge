"""The gold adapter: applies the task's reference solution.

This is how ``reforge verify-gold`` and the self-consistency tests exercise the
full pipeline without any LLM. If a task is authored correctly, running the gold
adapter must make it resolve. The runner passes the host path to the gold patch
through ``config["gold_patch_path"]``.
"""

from __future__ import annotations

from pathlib import Path

from reforge.adapters.base import AdapterInput, AdapterResult, AgentAdapter
from reforge.utils.errors import AdapterError

_CONTAINER_PATCH_PATH = "/tmp/reforge_gold.patch"


class GoldAdapter(AgentAdapter):
    name = "gold"
    version = "1.0.0"

    def validate(self, input: AdapterInput) -> None:
        patch_path = input.config.get("gold_patch_path")
        if not patch_path or not Path(patch_path).is_file():
            raise AdapterError(
                "gold adapter requires config.gold_patch_path pointing to an existing patch file"
            )

    def run(self, input: AdapterInput) -> AdapterResult:
        patch_path = Path(input.config["gold_patch_path"])
        patch_text = patch_path.read_text(encoding="utf-8")
        input.container.copy_in(patch_path, "/tmp")
        # put_archive lands the file at /tmp/<name>; normalize to a stable path.
        input.container.exec(["mv", f"/tmp/{patch_path.name}", _CONTAINER_PATCH_PATH])

        # Pre-create parent directories of every target file. git apply usually
        # creates leading dirs itself, but doing it explicitly makes application
        # robust across Docker storage backends where a put_archive'd directory
        # is not yet writable in the way git apply expects.
        for parent in _target_parents(patch_text):
            input.container.exec(["mkdir", "-p", parent], workdir=input.workspace_path)

        result = input.container.exec(
            ["git", "apply", "--whitespace=nowarn", _CONTAINER_PATCH_PATH],
            workdir=input.workspace_path,
        )
        input.trace_path.write_text(
            f"$ git apply (exit {result.exit_code})\n{result.output}", encoding="utf-8"
        )

        if not result.ok:
            debug = input.container.exec(
                ["sh", "-c", "ls -la . && echo '--' && git status --porcelain"],
                workdir=input.workspace_path,
            )
            raise AdapterError(
                f"gold patch did not apply (git apply exit {result.exit_code}): "
                f"{result.output.strip()[:400]} :: workspace: {debug.output.strip()[:400]}"
            )
        return AdapterResult(success=True, trace_path=input.trace_path, exit_code=result.exit_code)


def _target_parents(patch_text: str) -> list[str]:
    """Parent directories of files the patch creates or modifies (from +++ lines)."""
    parents: list[str] = []
    for line in patch_text.splitlines():
        if line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            if "/" in path:
                parents.append(path.rsplit("/", 1)[0])
    return sorted(set(parents))
