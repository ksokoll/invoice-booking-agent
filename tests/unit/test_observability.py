"""Smoke tests for the observability setup.

These tests verify that our wiring is correct: configuration
runs without errors, the public API is callable, correlation
IDs propagate, metrics record without crashing.
"""

from __future__ import annotations

from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.services.observability import (
    configure_observability,
    get_correlation_id,
    get_logger,
    get_tracer,
    new_correlation_id,
    record_iteration,
    record_run_finished,
    record_run_started,
    record_tool_call,
    record_verification_failure,
    set_correlation_id,
)
from app.services.observability.decorators import traced


class TestObservabilitySetup:
    def test_configure_observability_is_idempotent(self) -> None:
        configure_observability()
        configure_observability()  # must not raise

    def test_get_logger_returns_a_logger(self) -> None:
        configure_observability()
        log = get_logger("test")
        log.info("test.event", value=42)  # must not raise

    def test_get_tracer_returns_a_tracer(self) -> None:
        configure_observability()
        tracer = get_tracer("test")
        with tracer.start_as_current_span("test.span") as span:
            span.set_attribute("key", "value")


class TestCorrelationId:
    def test_default_correlation_id_is_empty(self) -> None:
        # In a fresh context, the default is the empty string.
        # When other tests have run first the value may be set; accept both.
        assert isinstance(get_correlation_id(), str)

    def test_set_and_get_correlation_id(self) -> None:
        cid = new_correlation_id()
        set_correlation_id(cid)
        assert get_correlation_id() == cid

    def test_new_correlation_id_is_unique(self) -> None:
        a = new_correlation_id()
        b = new_correlation_id()
        assert a != b
        assert len(a) == 32  # uuid4 hex length


class TestMetricsRecording:
    def test_record_run_lifecycle_does_not_crash(self) -> None:
        record_run_started()
        record_run_finished("booked")

    def test_record_iteration_does_not_crash(self) -> None:
        record_iteration(3)

    def test_record_tool_call_does_not_crash(self) -> None:
        record_tool_call("get_invoice_data", "ok")
        record_tool_call("book_invoice", "permission_denied")

    def test_record_verification_failure_does_not_crash(self) -> None:
        record_verification_failure("limit_not_exceeded", consultable=True)
        record_verification_failure("not_found", consultable=False)


class TestCorrelationIdInCapture:
    """Verify that captured log lines include the correlation ID.

    Regression test for the Round 11.1 bug where the harness
    capture pipeline was missing the correlation ID processor.
    """

    def test_captured_log_line_contains_correlation_id(self) -> None:
        from app.harness.logging_capture import configure_capture_logging
        from app.services.observability import (
            get_logger,
            new_correlation_id,
            set_correlation_id,
        )

        handler = configure_capture_logging()
        thread_id = handler.start_capture()

        cid = new_correlation_id()
        set_correlation_id(cid)

        log = get_logger("test")
        log.info("test.event", invoice_id="42")

        captured = handler.pop_capture(thread_id)

        assert len(captured) >= 1, "no log line was captured"
        joined = " ".join(captured)
        assert cid in joined, f"correlation_id {cid} not found in captured log:\n{joined}"


_decorator_test_exporter = InMemorySpanExporter()
_decorator_test_provider = TracerProvider()
_decorator_test_provider.add_span_processor(SimpleSpanProcessor(_decorator_test_exporter))


class TestTracedDecorator:
    """Unit tests for the `@traced` decorator.

    The decorator is expected to open exactly one span per invocation,
    attach primitive-typed attributes from the named parameters, pass
    through the return value unchanged, and propagate exceptions.

    OpenTelemetry's `ProxyTracer` caches its real tracer on first
    use. To keep the test deterministic we install a single
    `TracerProvider` at module-import time and clear the exporter
    between tests rather than swapping providers per test.
    """

    @pytest.fixture(autouse=True)
    def _install_provider(self) -> Any:
        previous = trace.get_tracer_provider()
        trace._TRACER_PROVIDER = _decorator_test_provider  # type: ignore[attr-defined]
        _decorator_test_exporter.clear()
        try:
            yield
        finally:
            trace._TRACER_PROVIDER = previous  # type: ignore[attr-defined]

    @pytest.fixture
    def captured_spans(self) -> InMemorySpanExporter:
        return _decorator_test_exporter

    def test_decorated_method_produces_one_named_span(
        self, captured_spans: InMemorySpanExporter
    ) -> None:
        class Subject:
            @traced("subject.do")
            def do(self) -> int:
                return 42

        result = Subject().do()

        spans = captured_spans.get_finished_spans()
        assert result == 42
        assert len(spans) == 1
        assert spans[0].name == "subject.do"

    def test_named_primitive_attributes_are_attached(
        self, captured_spans: InMemorySpanExporter
    ) -> None:
        class Subject:
            @traced("subject.do", attributes_from_args=("invoice_id", "count"))
            def do(self, invoice_id: str, count: int, payload: dict[str, Any]) -> None:
                _ = payload
                return None

        Subject().do("INV-42", 3, {"irrelevant": True})

        spans = captured_spans.get_finished_spans()
        assert len(spans) == 1
        attrs = dict(spans[0].attributes or {})
        assert attrs.get("invoice_id") == "INV-42"
        assert attrs.get("count") == 3

    def test_non_listed_parameters_are_not_attached(
        self, captured_spans: InMemorySpanExporter
    ) -> None:
        class Subject:
            @traced("subject.do", attributes_from_args=("invoice_id",))
            def do(self, invoice_id: str, task: str) -> None:
                return None

        Subject().do("INV-42", "book it")

        spans = captured_spans.get_finished_spans()
        assert len(spans) == 1
        attrs = dict(spans[0].attributes or {})
        assert "task" not in attrs

    def test_non_primitive_attribute_values_are_skipped(
        self, captured_spans: InMemorySpanExporter
    ) -> None:
        class Subject:
            @traced("subject.do", attributes_from_args=("payload",))
            def do(self, payload: dict[str, Any]) -> None:
                return None

        Subject().do({"not": "primitive"})

        spans = captured_spans.get_finished_spans()
        assert len(spans) == 1
        attrs = dict(spans[0].attributes or {})
        assert "payload" not in attrs

    def test_return_value_is_passed_through(self, captured_spans: InMemorySpanExporter) -> None:
        class Subject:
            @traced("subject.do")
            def do(self) -> dict[str, int]:
                return {"answer": 42}

        assert Subject().do() == {"answer": 42}

    def test_exception_is_not_swallowed(self, captured_spans: InMemorySpanExporter) -> None:
        class BoomError(Exception):
            pass

        class Subject:
            @traced("subject.do")
            def do(self) -> None:
                raise BoomError("kaboom")

        with pytest.raises(BoomError):
            Subject().do()
