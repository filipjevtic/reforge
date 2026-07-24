"""Prepare a resolved workspace before the agent sees it.

Strips git history when requested and removes any paths the task wants hidden
from the agent. The verifier and gold solution are never placed here; they are
injected into the container only after the agent's diff is captured.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from reforge.spec.models import TaskSpec
from reforge.workspace.source import resolve_source


def prepare_workspace(spec: TaskSpec, dest: Path) -> str | None:
    """Resolve the source into ``dest`` and apply strip_git / hidden_paths.

    Returns the resolved source ref (SHA for git sources), for provenance.
    """
    ref = resolve_source(spec, dest)

    if spec.source.strip_git:
        git_dir = dest / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir)

    for pattern in spec.context.hidden_paths:
        for match in dest.glob(pattern):
            if match.is_dir():
                shutil.rmtree(match, ignore_errors=True)
            elif match.exists():
                match.unlink()

    return ref
