# ADR-011: Observability as an Architecture Characteristic

Status: Accepted
Date: 2026-04-12
Deciders: Kevin Sokoll

## Context

The invoice agent went through ten patch rounds focused on
correctness, structure, and tests. The result is a system that
works in development and passes its tests. What it does not
have is the operational layer that any production deployment
in a regulated environment (banking, insurance, public sector)
would require: structured logs, distributed traces, and
metrics, all correlated by a request identifier.

The question is not whether to add observability. It is which
of the modern standards to follow and how deeply to instrument
without over-engineering the demo.

## Decision

Adopt the modern three-pillar observability model with one
cross-cutting addition:

1. Structured logs via `structlog`. JSON output for production,
   colored human-readable output for development. The choice is
   made via the `OBSERVABILITY_FORMAT` environment variable.
2. Distributed tracing via OpenTelemetry. Spans nest
   hierarchically: `coordinator.run` is the root, with child
   spans for each iteration, each tool call, and each
   verification check.
3. Metrics via `prometheus_client`. Six metrics covering the
   four golden signals (Rate, Errors, Duration, Saturation does
   not apply for a batch agent) plus three agent-specific
   signals (iterations per run, verification failures, LLM
   tokens).
4. Correlation IDs via `contextvars.ContextVar`. The Coordinator
   generates a fresh ID at the start of every run and binds it
   to the context. structlog reads it via a processor;
   OpenTelemetry attaches it as a span attribute.

All three pillars live under `src/app/services/observability/`
as separate submodules following the 1:1:1 rule from
`ml_engineering.md`.

## Rationale

- Observability is explicitly listed as an Architecture
  Characteristic for ML systems in `architecture.md` Rule #15:
  "Can you see what the model predicts, on what inputs, in real
  time?" An LLM-driven agent without observability fails this
  question.
- The three-pillar model (logs, metrics, traces) is the industry
  standard in 2026. Following it makes the resulting skill
  transferable to any banking, insurance, or regulated
  environment that uses the same vocabulary.
- `structlog`, OpenTelemetry, and `prometheus_client` are the
  Python ecosystem's mainstream choices. Each has multi-year
  stability and broad vendor support. None of them locks in to a
  specific backend.
- Correlation IDs via `contextvars` are the modern Python
  pattern for cross-component request identity. They avoid
  polluting every function signature with a `correlation_id`
  parameter.
- Spans nest hierarchically because the Coordinator's execution
  naturally forms a tree (run -> iteration -> tool call ->
  verification). A flat span list would discard this structure
  and lose the per-tool latency breakdown which is the main
  value of tracing for debugging.
- Six metrics is the right size: enough to cover the important
  questions (how many runs, how long, how many tools, how many
  failures, how many tokens), few enough to reason about and to
  keep cardinality under 100.

## Alternatives Considered

| Dimension | No observability | Logs only | Three pillars (chosen) | Honeycomb wide events |
|---|---|---|---|---|
| Production-ready debugging | Impossible | Partial | Yes | Yes |
| Latency analysis per component | Impossible | Impossible | Yes (spans) | Yes (events) |
| Industry-standard vocabulary | None | Partial | Full | Niche |
| Skill transfer to other roles | None | Limited | High | Limited |
| Implementation effort for the demo | Zero | Low | Medium | Medium |
| Correlation ID propagation | None | Manual | Automatic via contextvars | Automatic |

The "logs only" alternative was rejected because logs without
spans cannot answer "where did the time go?". The wide-events
approach from Honeycomb is conceptually elegant but is not yet
the industry standard, so adopting it would mean a less
transferable skill set. The chosen three-pillar approach matches
what every senior production engineer expects to see in 2026.

## Consequences

Positive:
- Every Coordinator run is fully traceable via correlation ID
- Latency bottlenecks are visible at the per-tool and
  per-verification level
- Operational metrics (token cost, failure rate by rule) are
  measurable and graphable
- The skill set is transferable to any modern Python service in
  a regulated environment

Negative:
- Three new dependencies (`structlog`, `opentelemetry-sdk`,
  `prometheus-client`). Each is small and stable, but each is
  another thing to keep updated.
- Adds approximately 200 lines of instrumentation code in
  `pipeline.py`. The business logic is now interleaved with
  observability calls.
- The current implementation does not export metrics or spans to
  any backend. A reviewer asking "where do the metrics go?" gets
  the answer "into the in-process registry; in production you
  would add an OTLP exporter and a Prometheus scrape endpoint,
  both are 10 lines of code".

Neutral:
- The `OBSERVABILITY_FORMAT` environment variable adds one
  configuration knob
- The architecture fitness function for verification purity (see
  ADR-007) is unchanged because verification rules remain pure.
  They are called from the Coordinator, which owns the
  observability calls.
- The smoke tests under `tests/unit/test_observability.py` catch
  wiring errors; they do not test structlog or OpenTelemetry
  themselves.
