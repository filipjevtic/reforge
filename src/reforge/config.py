"""Project configuration and defaults.

Run defaults can live in a `reforge.toml` (or a `[tool.reforge]` table in
`pyproject.toml`) in the working directory, so a team sets adapter/model/judge/etc.
once instead of repeating flags. CLI flags always override the file; the file
overrides the built-in defaults.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def load_project_config(start: Path | None = None) -> dict[str, Any]:
    """Read run defaults from reforge.toml or pyproject's [tool.reforge]."""
    root = start or Path.cwd()

    toml_path = root / "reforge.toml"
    if toml_path.is_file():
        return tomllib.loads(toml_path.read_text(encoding="utf-8"))

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        tool = data.get("tool", {}).get("reforge")
        if isinstance(tool, dict):
            return tool

    return {}
