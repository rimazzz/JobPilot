"""Structured logging setup built on :mod:`structlog`.

Call :func:`configure_logging` once at process start-up. Application code then
uses :func:`get_logger` to obtain a bound logger. Context (such as the run's
``thread_id`` and the active ``agent``) is attached via context vars so it
appears on every log line without threading it through call signatures.
"""

from __future__ import annotations

import logging
import sys

import structlog

_CONFIGURED = False


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    """Configure structlog (and the stdlib root logger) for the process.

    Args:
        level: Minimum log level, e.g. ``"INFO"`` or ``"DEBUG"``.
        fmt: ``"json"`` for machine-readable output or ``"console"`` for
            human-friendly, coloured output during local development.
    """
    global _CONFIGURED

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Keep noisy third-party libraries at WARNING unless we're debugging.
    logging.basicConfig(level=log_level, format="%(message)s", stream=sys.stderr, force=True)
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(max(log_level, logging.WARNING))

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor
    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger, configuring logging on first use."""
    if not _CONFIGURED:
        configure_logging()
    return structlog.get_logger(name)


def bind_context(**kwargs: object) -> None:
    """Bind key/value pairs to the current context (thread-local/async-safe)."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Remove all context vars bound to the current context."""
    structlog.contextvars.clear_contextvars()
