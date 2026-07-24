"""Typed exception hierarchy for reforge.

Every failure the tool raises on purpose inherits from :class:`ReforgeError`, so
the CLI can catch one type, print a clean message, and exit non-zero without a
traceback. Unexpected exceptions still bubble up as tracebacks.
"""

from __future__ import annotations


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
