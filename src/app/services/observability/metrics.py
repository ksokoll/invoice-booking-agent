"""Prometheus metric definitions for the invoice agent.

Six metrics, one purpose per metric:

    coordinator_runs_total          Counter, labels: status
    coordinator_run_duration_seconds  Histogram, no labels
    coordinator_iterations_per_run    Histogram, no labels
    tool_calls_total                Counter, labels: tool_name, outcome
    verification_failures_total     Counter, labels: rule, consultable
    llm_tokens_used_total           Counter, labels: provider, model

A scraping endpoint is NOT included; metrics live in the
in-process registry only.
"""

from __future__ import annotations

import time

from prometheus_client import Counter, Histogram

_runs_total = Counter(
    "coordinator_runs_total",
    "Number of Coordinator runs that reached a terminal state",
    labelnames=("status",),
)

_run_duration = Histogram(
    "coordinator_run_duration_seconds",
    "End-to-end duration of a Coordinator run",
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0),
)

_iterations_per_run = Histogram(
    "coordinator_iterations_per_run",
    "Number of iterations a Coordinator run took",
    buckets=(1, 2, 3, 5, 7, 10),
)

_tool_calls_total = Counter(
    "tool_calls_total",
    "Total tool invocations by name and outcome",
    labelnames=("tool_name", "outcome"),
)

_verification_failures_total = Counter(
    "verification_failures_total",
    "Total verification failures by rule and consultability",
    labelnames=("rule", "consultable"),
)

_llm_tokens_total = Counter(
    "llm_tokens_used_total",
    "Total LLM tokens consumed",
    labelnames=("provider", "model"),
)


_run_start_time: float | None = None


def record_run_started() -> None:
    """Mark the start of a Coordinator run for duration tracking."""
    global _run_start_time
    _run_start_time = time.monotonic()


def record_run_finished(status: str) -> None:
    """Mark the end of a Coordinator run."""
    global _run_start_time
    _runs_total.labels(status=status).inc()
    if _run_start_time is not None:
        _run_duration.observe(time.monotonic() - _run_start_time)
        _run_start_time = None


def record_iteration(count: int) -> None:
    """Record how many iterations one run took."""
    _iterations_per_run.observe(count)


def record_tool_call(tool_name: str, outcome: str) -> None:
    """Record one tool invocation."""
    _tool_calls_total.labels(tool_name=tool_name, outcome=outcome).inc()


def record_verification_failure(rule: str, consultable: bool) -> None:
    """Record one verification rule failure."""
    _verification_failures_total.labels(
        rule=rule,
        consultable="true" if consultable else "false",
    ).inc()


def record_llm_tokens(provider: str, model: str, tokens: int) -> None:
    """Record token usage from an LLM call."""
    _llm_tokens_total.labels(provider=provider, model=model).inc(tokens)
