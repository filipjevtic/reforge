"""Structured logging setup built on structlog.

The CLI calls :func:`configure` once. Everything else asks for a logger with
:func:`get_logger`. Human runs get colored console output; ``--json-logs`` (or a
non-tty) gets line-delimited JSON that is easy to grep and archive next to a run.
"""

from __future__ import annotations

import logging
import sys

import structlog

_configured = False


def configure(level: str = "info", json_logs: bool = False) -> None:
    """Configure structlog + stdlib logging. Safe to call more than once."""
    global _configured

    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=log_level)

    renderer: structlog.types.Processor
    renderer = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger, configuring with defaults on first use."""
    if not _configured:
        configure()
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
