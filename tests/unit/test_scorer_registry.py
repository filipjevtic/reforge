"""Tests for entry-point scorer discovery."""

from __future__ import annotations

from reforge.scoring import registry
from reforge.scoring.base import Scorer, ScorerResult, TaskScoringContext


class _SecurityScorer(Scorer):
    key = "security"

    def score(self, ctx: TaskScoringContext) -> ScorerResult:
        return ScorerResult(key=self.key, score=1.0, passed=True)


class _ClobberTests(Scorer):
    key = "tests"

    def score(self, ctx: TaskScoringContext) -> ScorerResult:  # pragma: no cover
        return ScorerResult(key=self.key, score=0.0, passed=False)


class _FakeEP:
    def __init__(self, name, obj):
        self.name = name
        self.value = f"fake:{name}"
        self._obj = obj

    def load(self):
        return self._obj


def test_load_extra_scorers_skips_builtin_keys(monkeypatch) -> None:
    eps = [_FakeEP("security", _SecurityScorer), _FakeEP("tests", _ClobberTests)]
    monkeypatch.setattr(registry, "entry_points", lambda group: eps)
    loaded = registry.load_extra_scorers()
    keys = [s.key for s in loaded]
    assert "security" in keys
    assert "tests" not in keys  # built-in keys can't be clobbered by a plugin
