"""Thread-isolated log capture for parallel harness runs.

Bridges structlog events into per-thread buffers so the harness
can attach each run's log to its report row. In production mode
the normal structlog renderer handles output; in harness mode
this bridge additionally appends each event to the current
thread's buffer.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import structlog

from app.services.observability import add_correlation_id_processor

if TYPE_CHECKING:
    from collections.abc import MutableMapping


class ThreadIsolatedBufferHandler(logging.Handler):
    """Captures log records into per-thread buffers.

    Each worker thread that runs a variant emits log records
    through the standard logger. This handler routes each record
    to a buffer keyed by the emitting thread's ID.

    Thread safety: the buffer dict is guarded by a lock.
    """

    def __init__(self) -> None:
        super().__init__()
        self._buffers: dict[int, list[str]] = {}
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """Append the formatted record to the emitting thread's buffer."""
        try:
            msg = self.format(record)
        except Exception:
            self.handleError(record)
            return
        thread_id = record.thread
        if thread_id is None:
            return
        with self._lock:
            self._buffers.setdefault(thread_id, []).append(msg)

    def start_capture(self) -> int:
        """Begin a fresh capture for the current thread."""
        thread_id = threading.get_ident()
        with self._lock:
            self._buffers[thread_id] = []
        return thread_id

    def pop_capture(self, thread_id: int) -> list[str]:
        """Return and remove the captured records for one thread."""
        with self._lock:
            return self._buffers.pop(thread_id, [])


class StructlogCaptureProcessor:
    """structlog processor that copies events into per-thread buffers.

    Each event is rendered as a one-line string and appended to
    the current thread's capture buffer if that thread has an
    active capture.
    """

    def __init__(self, handler: ThreadIsolatedBufferHandler) -> None:
        self._handler = handler

    def __call__(
        self,
        logger: object,
        method_name: str,
        event_dict: MutableMapping[str, Any],
    ) -> MutableMapping[str, Any]:
        thread_id = threading.get_ident()
        if thread_id in self._handler._buffers:
            line = " ".join(f"{k}={v}" for k, v in event_dict.items())
            with self._handler._lock:
                self._handler._buffers[thread_id].append(line)
        return event_dict


def configure_capture_logging() -> ThreadIsolatedBufferHandler:
    """Install a thread-isolated buffer handler bridged into structlog.

    Reconfigures structlog's processor pipeline to include the
    capture processor. In harness mode this overrides the default
    configuration from configure_observability().
    """
    handler = ThreadIsolatedBufferHandler()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id_processor,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            StructlogCaptureProcessor(handler),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.ReturnLoggerFactory(),
    )

    return handler
