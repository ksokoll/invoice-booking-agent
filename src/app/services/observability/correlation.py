"""Correlation ID context propagation.

Every Coordinator run gets a unique correlation ID. The ID is
stored in a contextvar so that any code path running on the
same thread (or async context) can read it without explicit
parameter passing.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def new_correlation_id() -> str:
    """Generate a fresh correlation ID."""
    return uuid.uuid4().hex


def set_correlation_id(value: str) -> None:
    """Bind a correlation ID to the current context."""
    _correlation_id.set(value)


def get_correlation_id() -> str:
    """Return the current context's correlation ID, or empty string."""
    return _correlation_id.get()
