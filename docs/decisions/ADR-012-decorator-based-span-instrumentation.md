# ADR-012: Decorator-Based Span Instrumentation

Status: Accepted
Date: 2026-04-24
Deciders: Kevin Sokoll

## Context

ADR-011 introduced the three-pillar observability stack and
accepted that the Coordinator now carries around 200 lines of
instrumentation code interleaved with business logic. The cost
was accepted as a one-time price for production-grade
observability.

In practice the `with tracer.start_as_current_span(...)` blocks at
the top of `Coordinator.run` and `Coordinator._execute_tool_call`
add one extra level of indentation and two extra lines per method
that duplicate information already present in the signature: the
span name is a static string, and the attributes `invoice_id` and
`correlation_id` come directly from parameters. A separate
discussion with a senior software engineer confirmed that for
greenfield code in 2026, senior Python practice is to reserve
manual `with` blocks for dynamic span logic and to use a
decorator for structural spans whose boundary coincides with a
method boundary.

The question is not whether to instrument but how to split the
instrumentation code between the structural case (span boundary
equals method boundary) and the dynamic case (span boundary is
inside a loop or the attributes only become known at runtime).

## Decision

Adopt a three-level instrumentation model:

1. **Decorator-based spans** for methods whose span boundary
   equals the method boundary and whose attributes are derivable
   statically from the parameter list. These are annotated with
   `@traced("span.name", attributes_from_args=(...))`.
2. **Manual `with` blocks** for spans whose boundary lies inside
   a loop, or whose attributes are only known after some
   computation inside the method (for example the iteration
   counter, the resolved status, the verification rule that
   failed).
3. **Business events** for semantic moments inside an existing
   span. These are not their own spans; they are either
   `span.add_event(...)` calls or structured log lines.

The decorator lives in
`src/app/services/observability/decorators.py` and depends only
on `opentelemetry`, `inspect`, and `functools`. It extracts
attribute values via `inspect.signature` and `sig.bind`, and only
attaches values whose runtime type is primitive
(`str`, `int`, `float`, `bool`). Non-primitive values are
skipped silently so the decorator can be applied to methods that
also take dicts or dataclasses as parameters.

`Coordinator.run` and `Coordinator._execute_tool_call` are
converted to the decorator style. The iteration loop inside
`run`, the pre- and post-execute verification spans inside
`_execute_tool_call`, and all dynamic attribute assignments
(`status`, `outcome`, `rule`) remain as manual code because they
are dynamic by nature.

## Rationale

- Separation of concerns on the method level: the structural
  shape of the span tree is declared at the method header, while
  the dynamic parts of the span (result-dependent attributes)
  stay explicit in the body.
- The Coordinator's methods lose one level of indentation each
  and the duplicate "span name plus static attribute" boilerplate
  at the top of each method. The business logic becomes the first
  readable line of the method body.
- The decorator itself is small (around 40 lines) and has one
  responsibility. It is unit-tested in isolation.
- The chosen approach does not replace `OpenTelemetry` auto-
  instrumentation. We still control the span names and decide
  which methods are worth a span. That trade-off is important for
  an LLM agent where span cardinality is a real cost.
- The `set_attribute` API remains the same for both styles. A
  reader who knows how to set an attribute inside a `with` block
  already knows how to set one inside a decorated method: call
  `trace.get_current_span().set_attribute(...)` in the body.

## Alternatives Considered

- **Full-auto instrumentation.** Using something like
  `opentelemetry.instrumentation.auto_instrumentation` that
  decorates every call. Rejected because it is too magic for an
  LLM-driven agent where we want to control span cardinality and
  because no OpenTelemetry auto-instrumentor targets our
  hand-written `Coordinator` class.
- **Leave everything as manual `with` blocks (status quo).**
  Rejected because the cost of the boilerplate keeps rising as
  more Coordinator methods are added, while the benefit of
  manual blocks for structural spans is zero.
- **Class-level decorator that instruments every method
  automatically.** Rejected because we do not want every helper
  (`_compress_tool_result`, `_summarise_for_llm`,
  `_update_state`) to produce its own span. Only the structural
  methods belong in the tree.

## Consequences

Positive:
- The Coordinator's `run` and `_execute_tool_call` methods are
  shorter and more readable. The span name is declared once, at
  the method header, where the reader first looks.
- The decorator is reusable for any future structural span on
  any class.
- The three-level model is simple enough to hold in one's head:
  structural equals decorator, dynamic equals `with`, semantic
  equals event.

Negative:
- One new local abstraction (`@traced`) that future contributors
  need to learn. Small learning curve but still a curve.
- Attribute extraction via `inspect.signature` adds a small
  reflection cost per call. For a method that runs a handful of
  times per invoice this is negligible; for a hot loop it would
  not be.

Neutral:
- The `set_attribute` API is unchanged; both styles use it.
- ADR-011 still stands. This is a refinement of how the
  instrumentation is expressed, not of what is instrumented.
