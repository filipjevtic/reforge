"""Discover agent adapters through the ``reforge.adapters`` entry-point group.

Built-in adapters and third-party ones (``pip install reforge-adapter-foo``) are
found the same way, so ``reforge list adapters`` shows everything installed.
"""

from __future__ import annotations

from importlib.metadata import entry_points

from reforge.adapters.base import AgentAdapter
from reforge.utils.errors import AdapterError

ENTRY_POINT_GROUP = "reforge.adapters"


def available_adapters() -> dict[str, str]:
    """Map adapter name -> entry-point target string, for every installed adapter."""
    return {ep.name: ep.value for ep in entry_points(group=ENTRY_POINT_GROUP)}


def load_adapter(name: str) -> AgentAdapter:
    """Instantiate an adapter by name."""
    eps = {ep.name: ep for ep in entry_points(group=ENTRY_POINT_GROUP)}
    ep = eps.get(name)
    if ep is None:
        known = ", ".join(sorted(eps)) or "(none installed)"
        raise AdapterError(f"unknown adapter '{name}'. Available: {known}")

    try:
        cls = ep.load()
    except Exception as exc:
        raise AdapterError(f"failed to load adapter '{name}': {exc}") from exc

    if not (isinstance(cls, type) and issubclass(cls, AgentAdapter)):
        raise AdapterError(f"adapter '{name}' does not point to an AgentAdapter subclass")

    instance = cls()
    if not instance.name:
        instance.name = name
    return instance
