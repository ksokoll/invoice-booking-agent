"""Observability layer: structured logs, traces, and metrics.

Public API:
    configure_observability(): one-call setup for all three pillars
    get_logger(name): structlog logger
    get_tracer(name): OpenTelemetry tracer
    record_*(...): metric recording functions
    new_correlation_id(), set_correlation_id(), get_correlation_id()
"""

from app.services.observability.correlation import (
    get_correlation_id,
    new_correlation_id,
    set_correlation_id,
)
from app.services.observability.logging import (
    add_correlation_id_processor,
    configure_logging,
    get_logger,
)
from app.services.observability.metrics import (
    record_iteration,
    record_llm_tokens,
    record_run_finished,
    record_run_started,
    record_tool_call,
    record_verification_failure,
)
from app.services.observability.tracing import (
    configure_tracing,
    get_tracer,
)


def configure_observability() -> None:
    """One-call setup for all three observability pillars. Idempotent."""
    configure_logging()
    configure_tracing()


__all__ = [
    "add_correlation_id_processor",
    "configure_observability",
    "get_correlation_id",
    "get_logger",
    "get_tracer",
    "new_correlation_id",
    "record_iteration",
    "record_llm_tokens",
    "record_run_finished",
    "record_run_started",
    "record_tool_call",
    "record_verification_failure",
    "set_correlation_id",
]
