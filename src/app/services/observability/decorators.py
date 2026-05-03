"""Decorator-based span instrumentation for structural tracing.

ADR-012 documents the three-level instrumentation model that this
module supports. Level 1 is decorator-based and used here. Levels 2
and 3 (manual `with` blocks and `span.add_event` calls) remain as
they were.

A `@traced` decorator wraps a method so its call boundary becomes a
span boundary. Named parameters listed in `attributes_from_args` are
extracted via `inspect.signature` and set as span attributes when
their runtime value is a primitive type.

Only primitive types (`str`, `int`, `float`, `bool`) are attached as
attributes. Complex types (dicts, lists, dataclasses) are silently
skipped because OpenTelemetry's attribute API does not accept them.

The decorator preserves the wrapped function's signature and
docstring via `functools.wraps`.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from opentelemetry import trace

_tracer = trace.get_tracer(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def traced(
    span_name: str,
    attributes_from_args: tuple[str, ...] = (),
) -> Callable[[F], F]:
    """Wrap a method so its body runs inside a new span.

    The decorator opens a span with the given name, extracts the
    requested parameter values from the bound call arguments, and
    attaches them as span attributes. Only primitive values are
    attached; non-primitive values are skipped silently so that the
    decorator can be applied to methods whose signatures include
    dicts, dataclasses, or other complex types without breaking.

    Args:
        span_name: The OpenTelemetry span name. Follows dotted
            naming like "coordinator.run" or "tool.execute".
        attributes_from_args: Tuple of parameter names (including
            `self`-bound instance parameters but excluding `self`
            itself) whose runtime values should be set as span
            attributes when primitive.

    Returns:
        A decorator that wraps the given callable. The wrapped
        callable preserves the original signature, docstring, and
        return value, and does not swallow exceptions.
    """

    def decorator(func: F) -> F:
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with _tracer.start_as_current_span(span_name) as span:
                if attributes_from_args:
                    bound = signature.bind(*args, **kwargs)
                    bound.apply_defaults()
                    for name in attributes_from_args:
                        if name not in bound.arguments:
                            continue
                        value = bound.arguments[name]
                        if isinstance(value, bool | int | float | str):
                            span.set_attribute(name, value)
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
