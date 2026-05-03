"""Structured logging via structlog.

Two modes:
    - Production (OBSERVABILITY_FORMAT=json): JSON output, one
      line per event, suitable for Loki / Datadog / Elastic.
    - Development (default): colored human-readable output via
      structlog's ConsoleRenderer.

Every log event automatically includes:
    - timestamp (ISO 8601, UTC)
    - level
    - event (the message)
    - correlation_id (from contextvars, see correlation.py)
    - any custom fields passed to the logger
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, Any

import structlog

from app.services.observability.correlation import get_correlation_id

if TYPE_CHECKING:
    from collections.abc import MutableMapping


def add_correlation_id_processor(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """structlog processor: inject the current correlation ID.

    Public processor used by both the production logging
    configuration and the harness capture configuration. Reads
    the correlation ID from the contextvar and adds it to the
    event_dict under the key 'correlation_id'. If no correlation
    ID is set, the field is omitted (not set to empty string).

    Args:
        logger: The bound logger (unused, required by structlog).
        method_name: The log method name (unused, required by structlog).
        event_dict: The event dictionary being processed.

    Returns:
        The event_dict, possibly with a 'correlation_id' field added.
    """
    cid = get_correlation_id()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_logging() -> None:
    """Configure structlog for the current process.

    Reads OBSERVABILITY_FORMAT from the environment. If set to
    'json', uses the JSONRenderer. Otherwise uses ConsoleRenderer
    with colors. Idempotent.
    """
    use_json = os.environ.get("OBSERVABILITY_FORMAT", "").lower() == "json"

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        add_correlation_id_processor,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if use_json:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """Return a structlog logger bound to the given name."""
    return structlog.get_logger(name)
