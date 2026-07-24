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
        input.container.copy_in(patch_path, "/tmp")
        # put_archive lands the file at /tmp/<name>; normalize to a stable path.
        input.container.exec(["mv", f"/tmp/{patch_path.name}", _CONTAINER_PATCH_PATH])

        git_res = input.container.exec(
            ["git", "apply", "--whitespace=nowarn", "-v", _CONTAINER_PATCH_PATH],
            workdir=input.workspace_path,
        )
        outputs = [f"$ git apply -v (exit {git_res.exit_code})\n{git_res.output}"]
        result = git_res
        if not git_res.ok:
            # Fall back to patch(1) for diffs git refuses (e.g. no a/ b/ prefixes).
            patch_res = input.container.exec(
                ["sh", "-c", f"patch -p1 < {_CONTAINER_PATCH_PATH}"],
                workdir=input.workspace_path,
            )
            outputs.append(f"$ patch -p1 (exit {patch_res.exit_code})\n{patch_res.output}")
            result = patch_res

        input.trace_path.write_text("\n".join(outputs), encoding="utf-8")

        if not result.ok:
            raise AdapterError(
                f"gold patch did not apply (git apply exit {git_res.exit_code}): "
                f"{git_res.output.strip()[:600]}"
            )
        return AdapterResult(
            success=True, trace_path=input.trace_path, exit_code=result.exit_code
        )
