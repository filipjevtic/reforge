"""Typed exception hierarchy for reforge.

Every failure the tool raises on purpose inherits from :class:`ReforgeError`, so
the CLI can catch one type, print a clean message, and exit non-zero without a
traceback. Unexpected exceptions still bubble up as tracebacks.
"""

from __future__ import annotations

import re

# API-key shapes and bearer tokens that must never land in persisted run artifacts.
_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{16,}")
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._-]{16,}")


def redact_secrets(text: str) -> str:
    """Mask anything that looks like a provider API key or bearer token.

    Provider SDK errors can echo request details; this scrubs them before an error
    string is written to a run's result.json.
    """
    return _SECRET_RE.sub("[redacted]", _BEARER_RE.sub(r"\1[redacted]", text))


class ReforgeError(Exception):
    """Base class for all errors raised deliberately by reforge."""


class SpecError(ReforgeError):
    """A task specification is missing, malformed, or semantically invalid."""


class SourceError(ReforgeError):
    """The codebase-under-test could not be resolved or prepared."""


class RuntimeBackendError(ReforgeError):
    """The container runtime (Docker) failed or is unavailable."""


class AdapterError(ReforgeError):
    """An agent adapter could not be resolved, validated, or run."""


class ScoringError(ReforgeError):
    """A scorer could not produce a result."""


class ConfigError(ReforgeError):
    """Invalid configuration or CLI arguments."""
