"""Discover third-party scorers via the ``reforge.scorers`` entry-point group.

A plugin scorer is any :class:`~reforge.scoring.base.Scorer` subclass that takes a
``TaskScoringContext`` and returns a ``ScorerResult``. The three built-in scorers
(tests, dependency_coverage, judge) are handled directly in the task runner because
they need special construction; this registry is only for additional, context-only
scorers. A task opts in by giving the scorer's key a weight > 0.
"""

from __future__ import annotations

from importlib.metadata import entry_points

from reforge.scoring.base import Scorer

ENTRY_POINT_GROUP = "reforge.scorers"
BUILTIN_KEYS = {"tests", "dependency_coverage", "judge"}


def available_scorers() -> dict[str, str]:
    return {ep.name: ep.value for ep in entry_points(group=ENTRY_POINT_GROUP)}


def load_extra_scorers() -> list[Scorer]:
    """Instantiate every registered scorer whose key doesn't collide with a built-in."""
    scorers: list[Scorer] = []
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        cls = ep.load()
        if not (isinstance(cls, type) and issubclass(cls, Scorer)):
            continue
        instance = cls()
        if not instance.key:
            instance.key = ep.name
        if instance.key in BUILTIN_KEYS:
            continue
        scorers.append(instance)
    return scorers
