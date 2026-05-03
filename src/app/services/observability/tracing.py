"""OpenTelemetry tracing setup.

Provides a tracer that the Coordinator and tools can use to
create spans. Spans nest hierarchically:

    coordinator.run                          (root)
        coordinator.iteration                (per LLM round-trip)
            tool.execute                     (per tool call)
                verification.check           (per verification rule)

In this round we do not export spans anywhere; they live in
the in-memory tracer provider.
"""

from __future__ import annotations

from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

_INITIALIZED = False


def configure_tracing() -> None:
    """Configure the global TracerProvider.

    Idempotent: calling twice is a no-op.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    resource = Resource.create(
        {
            "service.name": "invoice-agent",
            "service.version": "1.0.0",
        }
    )
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    _INITIALIZED = True


def get_tracer(name: str) -> Any:
    """Return a tracer bound to the given name."""
    return trace.get_tracer(name)
