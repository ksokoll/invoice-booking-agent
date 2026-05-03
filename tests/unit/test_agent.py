"""Unit tests for the invoice booking agent.

All tests run without an API key. The LLM is never called.
Tests are named after the behaviour being verified.

Test coverage:
    - Permission gate blocks WRITE when not allowed
    - Permission gate passes READ always
    - Verification catches limit exceeded
    - Verification catches approval contradiction
    - Verification passes valid cases
    - Tool routing: correct tool selected by name
    - InvoiceTool returns not-found for unknown invoice
    - POTool returns not-found for unknown PO
    - BookingTool records invoice in booked set
"""

from __future__ import annotations

import pytest

from app.approval.approval_tool import ApprovalTool
from app.approval.consult_procurement_tool import ConsultProcurementTool
from app.booking.booking_tool import BookingTool
from app.booking.escalate_to_human_tool import EscalateToHumanTool
from app.core.entities import BudgetRecord, Invoice, PORecord, SupplierRule
from app.core.results import CoordinatorResult
from app.core.results import ToolCall as TC
from app.core.statuses import AgentStatus
from app.intake.invoice_tool import InvoiceTool
from app.intake.supplier_rules_tool import SupplierRulesTool
from app.pipeline import Coordinator
from app.services.llm.client_protocol import LLMResponse
from app.services.permission_gate import PermissionDeniedError, PermissionGate, PermissionLevel
from app.verification.budget_tool import BudgetTool
from app.verification.po_tool import POTool
from app.verification.rules import (
    check_approval_consistent,
    check_approval_required,
    check_budget_sufficient,
    check_cost_center_allowed,
    check_limit_not_exceeded,
    check_not_already_booked,
    check_not_found,
    check_supplier_active,
)

# ---------------------------------------------------------------------------
# Permission Gate
# ---------------------------------------------------------------------------


class TestPermissionGate:
    def test_read_is_always_approved(self) -> None:
        gate = PermissionGate(allow_write=False)
        gate.check("get_invoice_data", PermissionLevel.READ)  # must not raise

    def test_write_is_approved_when_allowed(self) -> None:
        gate = PermissionGate(allow_write=True)
        gate.check("book_invoice", PermissionLevel.WRITE)  # must not raise

    def test_write_is_blocked_when_not_allowed(self) -> None:
        gate = PermissionGate(allow_write=False)
        with pytest.raises(PermissionDeniedError):
            gate.check("book_invoice", PermissionLevel.WRITE)

    def test_blocked_error_message_contains_tool_name(self) -> None:
        gate = PermissionGate(allow_write=False)
        with pytest.raises(PermissionDeniedError, match="book_invoice"):
            gate.check("book_invoice", PermissionLevel.WRITE)


# ---------------------------------------------------------------------------
# Verification — limit check
# ---------------------------------------------------------------------------


class TestLimitVerification:
    def test_blocks_when_amount_exceeds_limit(self) -> None:
        failure = check_limit_not_exceeded(
            amount_eur=200.0,
            limit_eur=30.0,
            invoice_id="1",
            po_number="450123456",
        )
        assert failure is not None
        assert failure.rule == "limit_not_exceeded"

    def test_passes_when_amount_equals_limit(self) -> None:
        failure = check_limit_not_exceeded(
            amount_eur=30.0,
            limit_eur=30.0,
            invoice_id="1",
            po_number="450123456",
        )
        assert failure is None

    def test_passes_when_amount_below_limit(self) -> None:
        failure = check_limit_not_exceeded(
            amount_eur=20.0,
            limit_eur=30.0,
            invoice_id="2",
            po_number="450123456",
        )
        assert failure is None

    def test_failure_message_contains_both_amounts(self) -> None:
        failure = check_limit_not_exceeded(
            amount_eur=200.0,
            limit_eur=30.0,
            invoice_id="1",
            po_number="450123456",
        )
        assert failure is not None
        assert "200" in failure.reason
        assert "30" in failure.reason


# ---------------------------------------------------------------------------
# Verification — approval contradiction
# ---------------------------------------------------------------------------


class TestApprovalVerification:
    def test_detects_contradiction_when_refusal_contradicts_known_limit(self) -> None:
        failure = check_approval_consistent(
            approved=False,
            stated_reason="The approval amount exceeds my responsibility.",
            expected_limit_eur=30.0,
            actual_amount_eur=25.0,
            recipient="Uwe Klinghoff",
        )
        assert failure is not None
        assert failure.rule == "approval_consistent"

    def test_passes_when_refusal_is_legitimate(self) -> None:
        # Amount really does exceed the limit — refusal is valid.
        failure = check_approval_consistent(
            approved=False,
            stated_reason="The approval amount exceeds my responsibility.",
            expected_limit_eur=30.0,
            actual_amount_eur=200.0,
            recipient="Uwe Klinghoff",
        )
        assert failure is None

    def test_passes_on_genuine_approval(self) -> None:
        failure = check_approval_consistent(
            approved=True,
            stated_reason="Approved by Uwe Klinghoff.",
            expected_limit_eur=30.0,
            actual_amount_eur=25.0,
            recipient="Uwe Klinghoff",
        )
        assert failure is None

    def test_contradiction_message_contains_recipient(self) -> None:
        failure = check_approval_consistent(
            approved=False,
            stated_reason="exceeds",
            expected_limit_eur=30.0,
            actual_amount_eur=25.0,
            recipient="Uwe Klinghoff",
        )
        assert failure is not None
        assert "Uwe Klinghoff" in failure.reason


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


class TestInvoiceTool:
    def _make_tool(self) -> InvoiceTool:
        return InvoiceTool(
            data={
                "1": Invoice(
                    id="1",
                    net_amount_eur=200.0,
                    po_number="450123456",
                    contact_person="Uwe Klinghoff",
                    supplier_id="LIEF-001",
                    cost_center="K100",
                )
            }
        )

    def test_returns_invoice_data_for_known_id(self) -> None:
        tool = self._make_tool()
        result = tool.execute({"invoice_id": "1"})
        assert result["found"] is True
        assert result["net_amount_eur"] == 200.0
        assert result["po_number"] == "450123456"

    def test_returns_not_found_for_unknown_id(self) -> None:
        tool = self._make_tool()
        result = tool.execute({"invoice_id": "999"})
        assert result["found"] is False

    def test_does_not_return_po_number_as_invoice(self) -> None:
        # Regression: CrewAI agent passed PO number as invoice ID.
        tool = self._make_tool()
        result = tool.execute({"invoice_id": "450123456"})
        assert result["found"] is False


class TestPOTool:
    def _make_tool(self) -> POTool:
        return POTool(
            data={
                "450123456": PORecord(
                    po_number="450123456",
                    limit_eur=30.0,
                    responsible_person="Uwe Klinghoff",
                )
            }
        )

    def test_returns_po_limit_for_known_number(self) -> None:
        tool = self._make_tool()
        result = tool.execute({"po_number": "450123456"})
        assert result["found"] is True
        assert result["limit_eur"] == 30.0

    def test_returns_not_found_for_unknown_po(self) -> None:
        tool = self._make_tool()
        result = tool.execute({"po_number": "000000000"})
        assert result["found"] is False


class TestBookingTool:
    def test_records_invoice_in_booked_set(self) -> None:
        booked: set[str] = set()
        tool = BookingTool(booked_invoices=booked)
        result = tool.execute({"invoice_id": "2", "po_number": "450123456", "amount_eur": 20.0})
        assert result["booked"] is True
        assert "2" in booked

    def test_booking_result_contains_all_fields(self) -> None:
        tool = BookingTool(booked_invoices=set())
        result = tool.execute({"invoice_id": "2", "po_number": "450123456", "amount_eur": 20.0})
        assert result["invoice_id"] == "2"
        assert result["po_number"] == "450123456"
        assert result["amount_eur"] == 20.0


# ---------------------------------------------------------------------------
# New verification rules
# ---------------------------------------------------------------------------


class TestNotFoundVerification:
    def test_detects_invoice_not_found(self) -> None:
        failure = check_not_found("get_invoice_data", {"found": False, "invoice_id": "999"})
        assert failure is not None
        assert failure.rule == "not_found"

    def test_passes_when_found(self) -> None:
        failure = check_not_found("get_invoice_data", {"found": True, "invoice_id": "1"})
        assert failure is None


class TestDuplicateBookingVerification:
    def test_blocks_already_booked_invoice(self) -> None:
        failure = check_not_already_booked("1", booked_invoices={"1", "2"})
        assert failure is not None
        assert failure.rule == "not_already_booked"

    def test_passes_for_new_invoice(self) -> None:
        failure = check_not_already_booked("3", booked_invoices={"1", "2"})
        assert failure is None


class TestApprovalRequiredVerification:
    def test_blocks_booking_above_threshold_without_approval(self) -> None:
        failure = check_approval_required("1", amount_eur=20.0, approval_received=False)
        assert failure is not None
        assert failure.rule == "approval_required"

    def test_passes_above_threshold_with_approval(self) -> None:
        failure = check_approval_required("1", amount_eur=20.0, approval_received=True)
        assert failure is None

    def test_passes_below_threshold_without_approval(self) -> None:
        failure = check_approval_required("1", amount_eur=10.0, approval_received=False)
        assert failure is None


# ---------------------------------------------------------------------------
# Fix 2: PermissionDeniedError exits the coordinator loop immediately
# ---------------------------------------------------------------------------


class TestPermissionGateExitsImmediately:
    def test_coordinator_exits_on_first_permission_denial(self) -> None:
        """Coordinator must return BLOCKED_PERMISSION_DENIED without calling
        continue_with_results when the gate blocks book_invoice.

        The mock LLM immediately requests book_invoice. With allow_write=False,
        the gate raises PermissionDeniedError. The coordinator must return a
        CoordinatorResult immediately — it must NOT call continue_with_results.
        """

        continue_called: list[bool] = []

        class MockClient:
            def start(self, *_, **__):
                return LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(
                            id="t1",
                            name="book_invoice",
                            params={
                                "invoice_id": "2",
                                "po_number": "450123456",
                                "amount_eur": 20.0,
                            },
                        )
                    ],
                )

            def continue_with_results(self, *_, **__):
                continue_called.append(True)
                return LLMResponse(stop_reason="end_turn", text="done")

        booked: set[str] = set()
        invoice = Invoice(
            id="2",
            net_amount_eur=20.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        tools = [
            InvoiceTool(data={"2": invoice}),
            BookingTool(booked_invoices=booked),
        ]

        coordinator = Coordinator(
            client=MockClient(),
            tools=tools,
            gate=PermissionGate(allow_write=False),  # WRITE blocked
            booked_invoices=booked,
        )

        result = coordinator.run(invoice_id="2", task="Book invoice 2")

        assert result.status == AgentStatus.BLOCKED_PERMISSION_DENIED
        assert continue_called == [], "continue_with_results must not be called"


# ---------------------------------------------------------------------------
# Rule Set 1: SupplierRules
# ---------------------------------------------------------------------------


class TestSupplierRulesVerification:
    def test_blocks_inactive_supplier(self) -> None:
        failure = check_supplier_active("LIEF-002", active=False)
        assert failure is not None
        assert failure.rule == "supplier_active"

    def test_passes_active_supplier(self) -> None:
        failure = check_supplier_active("LIEF-001", active=True)
        assert failure is None

    def test_blocks_disallowed_cost_center(self) -> None:
        failure = check_cost_center_allowed("K300", ["K100", "K200"], "1")
        assert failure is not None
        assert failure.rule == "cost_center_allowed"

    def test_passes_allowed_cost_center(self) -> None:
        failure = check_cost_center_allowed("K100", ["K100", "K200"], "1")
        assert failure is None

    def test_passes_when_all_cost_centers_allowed(self) -> None:
        failure = check_cost_center_allowed("K999", [], "1")
        assert failure is None


# ---------------------------------------------------------------------------
# Rule Set 2: BudgetRules
# ---------------------------------------------------------------------------


class TestBudgetRulesVerification:
    def test_blocks_when_budget_insufficient(self) -> None:
        failure = check_budget_sufficient(
            amount_eur=25.0,
            remaining_budget_eur=20.0,
            cost_center="K100",
            invoice_id="13",
        )
        assert failure is not None
        assert failure.rule == "budget_sufficient"

    def test_passes_when_budget_sufficient(self) -> None:
        failure = check_budget_sufficient(
            amount_eur=10.0,
            remaining_budget_eur=20.0,
            cost_center="K100",
            invoice_id="13",
        )
        assert failure is None

    def test_passes_when_budget_exactly_covers_amount(self) -> None:
        failure = check_budget_sufficient(
            amount_eur=20.0,
            remaining_budget_eur=20.0,
            cost_center="K100",
            invoice_id="14",
        )
        assert failure is None


# ---------------------------------------------------------------------------
# Fix 1: Confused-deputy guard in _pre_execute_verify
# ---------------------------------------------------------------------------


class TestConfusedDeputyOnBookInvoice:
    """Verify that _pre_execute_verify uses state amount, not LLM params."""

    def _make_coordinator(
        self,
        mock_responses: list,
        initial_state: dict,
    ):  # type: ignore[return]
        """Build a Coordinator whose run() pre-populates state."""

        responses = iter(mock_responses)

        class MockClient:
            def start(self, *_, **__):
                return next(responses)

            def continue_with_results(self, *_, **__):
                return next(responses)

        booked: set[str] = set()
        invoice = Invoice(
            id="2",
            net_amount_eur=200.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        tools = [
            InvoiceTool(data={"2": invoice}),
            BookingTool(booked_invoices=booked),
        ]

        captured_booked = booked

        class CoordinatorWithPreState(Coordinator):
            def run(self, invoice_id, task):
                state = dict(initial_state)
                response = self._client.start(system_prompt="", task=task, tool_schemas=[])
                for tool_call in response.tool_calls:
                    outcome = self._execute_tool_call(tool_call, state, invoice_id)
                    if isinstance(outcome, CoordinatorResult):
                        return outcome
                return CoordinatorResult(
                    status=AgentStatus.BLOCKED_MAX_ITERATIONS,
                    message="",
                    invoice_id=invoice_id,
                )

        coordinator = CoordinatorWithPreState(
            client=MockClient(),
            tools=tools,
            gate=PermissionGate(allow_write=True),
            booked_invoices=captured_booked,
        )
        coordinator._booked_ref = captured_booked
        return coordinator

    def test_book_invoice_with_tampered_amount_is_blocked(self) -> None:

        # State says 200.0 EUR; LLM tries to book with 10.0 to bypass checks.
        responses = [
            LLMResponse(
                stop_reason="tool_use",
                tool_calls=[
                    TC(
                        id="t1",
                        name="book_invoice",
                        params={"invoice_id": "2", "po_number": "450123456", "amount_eur": 10.0},
                    )
                ],
            ),
        ]
        coordinator = self._make_coordinator(
            mock_responses=responses,
            initial_state={"invoice_amount_eur": 200.0},
        )

        result = coordinator.run(invoice_id="2", task="Book invoice 2")

        assert result.status == AgentStatus.BLOCKED_AMOUNT_TAMPERING
        assert "2" not in coordinator._booked_ref

    def test_book_invoice_without_prior_invoice_fetch_is_blocked(self) -> None:

        # Empty state: get_invoice_data was never called.
        responses = [
            LLMResponse(
                stop_reason="tool_use",
                tool_calls=[
                    TC(
                        id="t1",
                        name="book_invoice",
                        params={"invoice_id": "2", "po_number": "450123456", "amount_eur": 20.0},
                    )
                ],
            ),
        ]
        coordinator = self._make_coordinator(
            mock_responses=responses,
            initial_state={},
        )

        result = coordinator.run(invoice_id="2", task="Book invoice 2")

        assert result.status == AgentStatus.BLOCKED_MISSING_INVOICE_STATE
        assert "2" not in coordinator._booked_ref


# ---------------------------------------------------------------------------
# Fix 2: approval_required maps to BLOCKED_APPROVAL_MISSING, not LIMIT_EXCEEDED
# ---------------------------------------------------------------------------


class TestApprovalMissingStatus:
    def test_missing_approval_yields_approval_missing_status(self) -> None:
        """book_invoice above threshold without approval must yield BLOCKED_APPROVAL_MISSING.

        Arrange: state has invoice_amount_eur=200.0, supplier threshold=15.0,
        no approvals_received. LLM drives straight to book_invoice with the
        correct amount (no tampering).
        Assert: result.status == BLOCKED_APPROVAL_MISSING (not BLOCKED_LIMIT_EXCEEDED).
        """

        responses = iter(
            [
                LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(
                            id="t1",
                            name="book_invoice",
                            params={
                                "invoice_id": "2",
                                "po_number": "450123456",
                                "amount_eur": 200.0,
                            },
                        )
                    ],
                ),
            ]
        )

        class MockClient:
            def start(self, *_, **__):
                return next(responses)

            def continue_with_results(self, *_, **__):
                return next(responses)

        booked: set[str] = set()
        invoice = Invoice(
            id="2",
            net_amount_eur=200.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        tools = [
            InvoiceTool(data={"2": invoice}),
            BookingTool(booked_invoices=booked),
        ]

        class CoordinatorWithPreState(Coordinator):
            def run(self, invoice_id, task):
                state = {
                    "invoice_amount_eur": 200.0,
                    "supplier_approval_threshold_eur": 15.0,
                    # No approvals_received — approval is missing.
                }
                response = self._client.start(system_prompt="", task=task, tool_schemas=[])
                for tool_call in response.tool_calls:
                    outcome = self._execute_tool_call(tool_call, state, invoice_id)
                    if isinstance(outcome, CoordinatorResult):
                        return outcome
                return CoordinatorResult(
                    status=AgentStatus.BLOCKED_MAX_ITERATIONS,
                    message="",
                    invoice_id=invoice_id,
                )

        coordinator = CoordinatorWithPreState(
            client=MockClient(),
            tools=tools,
            gate=PermissionGate(allow_write=True),
            booked_invoices=booked,
        )

        result = coordinator.run(invoice_id="2", task="Book invoice 2")

        assert result.status == AgentStatus.BLOCKED_APPROVAL_MISSING
        assert "2" not in booked


# ---------------------------------------------------------------------------
# Fix 2: Context Compression
# ---------------------------------------------------------------------------


class TestContextCompression:
    """Verify that compressible tool results are replaced with state pointers."""

    def _build_coordinator_and_capture(self, responses: list, invoice):
        """Return (coordinator, captured_contents) where captured_contents
        is a list that will be populated with every ToolResult.content string
        passed to continue_with_results.
        """

        captured: list[str] = []
        response_iter = iter(responses)

        class MockClient:
            def start(self, *_, **__):
                return next(response_iter)

            def continue_with_results(self, tool_results, **__):
                for tr in tool_results:
                    captured.append(tr.content)
                return next(response_iter)

        booked: set[str] = set()
        po = PORecord(po_number="450123456", limit_eur=30.0, responsible_person="Uwe Klinghoff")
        supplier = SupplierRule(
            supplier_id="LIEF-001",
            name="Test",
            active=True,
            approval_threshold_eur=15.0,
            allowed_cost_centers=("K100",),
            requires_supporting_document=False,
        )
        budget = BudgetRecord(
            cost_center="K100", period="2026-Q2", total_budget_eur=500.0, consumed_eur=0.0
        )

        tools = [
            InvoiceTool(data={invoice.id: invoice}),
            POTool(data={"450123456": po}),
            SupplierRulesTool(data={"LIEF-001": supplier}),
            BudgetTool(data={"K100": budget}),
            BookingTool(booked_invoices=booked),
        ]

        coordinator = Coordinator(
            client=MockClient(),
            tools=tools,
            gate=PermissionGate(allow_write=True),
            booked_invoices=booked,
        )
        return coordinator, captured

    def test_get_invoice_data_result_is_compressed_after_state_update(
        self,
    ) -> None:
        import json

        invoice = Invoice(
            id="2",
            net_amount_eur=20.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )

        responses = [
            LLMResponse(
                stop_reason="tool_use",
                tool_calls=[
                    TC(id="t1", name="get_invoice_data", params={"invoice_id": "2"}),
                ],
            ),
            LLMResponse(stop_reason="end_turn", text="done"),
        ]

        coordinator, captured = self._build_coordinator_and_capture(responses, invoice)
        coordinator.run(invoice_id="2", task="Book invoice 2")

        assert len(captured) == 1
        payload = json.loads(captured[0])
        assert payload.get("status") == "materialised_in_state"
        assert payload.get("tool") == "get_invoice_data"
        summary = payload.get("summary", {})
        assert summary.get("amount_eur") == 20.0
        assert summary.get("invoice_id") == "2"

    def test_book_invoice_result_is_not_compressed(self) -> None:
        import json

        invoice = Invoice(
            id="2",
            net_amount_eur=10.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )

        # State is pre-populated via the real tool sequence so book_invoice passes.
        responses = [
            LLMResponse(
                stop_reason="tool_use",
                tool_calls=[
                    TC(id="t1", name="get_invoice_data", params={"invoice_id": "2"}),
                ],
            ),
            LLMResponse(
                stop_reason="tool_use",
                tool_calls=[
                    TC(
                        id="t2",
                        name="book_invoice",
                        params={"invoice_id": "2", "po_number": "450123456", "amount_eur": 10.0},
                    ),
                ],
            ),
            LLMResponse(stop_reason="end_turn", text="booked"),
        ]

        coordinator, captured = self._build_coordinator_and_capture(responses, invoice)
        coordinator.run(invoice_id="2", task="Book invoice 2")

        # captured[0] = compressed get_invoice_data result
        # captured[1] = book_invoice result (must NOT be compressed)
        assert len(captured) >= 2
        book_payload = json.loads(captured[1])
        assert "materialised_in_state" not in str(book_payload)
        assert book_payload.get("booked") is True

    def test_not_found_result_is_not_compressed(self) -> None:
        import json

        invoice = Invoice(
            id="999",
            net_amount_eur=20.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )

        responses = [
            LLMResponse(
                stop_reason="tool_use",
                tool_calls=[
                    TC(id="t1", name="get_invoice_data", params={"invoice_id": "999"}),
                ],
            ),
            LLMResponse(stop_reason="end_turn", text="not found"),
        ]

        coordinator, _captured = self._build_coordinator_and_capture(responses, invoice)
        coordinator.run(invoice_id="999", task="Book invoice 999")

        # The run stops at check_not_found (returns CoordinatorResult), so
        # continue_with_results is never called. The not_found payload would
        # have been the full result. Verify directly via _compress_tool_result.
        not_found_result = {"found": False, "invoice_id": "999"}
        state: dict = {}
        compressed = coordinator._compress_tool_result("get_invoice_data", not_found_result, state)
        payload = json.loads(compressed)
        assert payload.get("found") is False
        assert "materialised_in_state" not in str(payload)


# ---------------------------------------------------------------------------
# Agent abandonment fallback
# ---------------------------------------------------------------------------


class TestAgentAbandonment:
    """Verify that end_turn without booking returns BLOCKED_AGENT_ABANDONED."""

    def test_end_turn_without_booking_returns_abandoned(self) -> None:

        class MockClient:
            def start(self, *_, **__):
                return LLMResponse(
                    stop_reason="end_turn",
                    text="I cannot proceed without more information.",
                )

            def continue_with_results(self, *_, **__):  # pragma: no cover
                raise AssertionError("continue_with_results must not be called")

        coordinator = Coordinator(
            client=MockClient(),
            tools=[],
            gate=PermissionGate(allow_write=True),
        )
        result = coordinator.run(invoice_id="42", task="Book invoice 42")

        assert result.status == AgentStatus.BLOCKED_AGENT_ABANDONED
        assert result.invoice_id == "42"
        assert "cannot proceed" in result.message


# ---------------------------------------------------------------------------
# Recipient injection
# ---------------------------------------------------------------------------


class TestRecipientInjection:
    """Verify the Coordinator injects the recipient from state into
    request_approval params before execution."""

    def _build_coordinator(self, responses: list):

        invoice = Invoice(
            id="2",
            net_amount_eur=20.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        po_record = PORecord(
            po_number="450123456", limit_eur=30.0, responsible_person="Uwe Klinghoff"
        )

        response_iter = iter(responses)

        class MockClient:
            def start(self, *_, **__):
                return next(response_iter)

            def continue_with_results(self, *_, **__):
                return next(response_iter)

        tools = [
            InvoiceTool(data={"2": invoice}),
            POTool(data={"450123456": po_record}),
            ApprovalTool(approval_responses={"Uwe Klinghoff": True}),
            BookingTool(booked_invoices=set()),
        ]
        return Coordinator(
            client=MockClient(),
            tools=tools,
            gate=PermissionGate(allow_write=True),
        )

    def test_request_approval_without_prior_po_limit_is_blocked(self) -> None:

        responses = [
            # Jump straight to request_approval without calling get_po_limit first.
            # No recipient in params -- the LLM never sees that field.
            LLMResponse(
                stop_reason="tool_use",
                tool_calls=[
                    TC(
                        id="t1",
                        name="request_approval",
                        params={"invoice_id": "2", "amount_eur": 20.0},
                    ),
                ],
            ),
        ]

        coordinator = self._build_coordinator(responses)
        result = coordinator.run(invoice_id="2", task="Book invoice 2")

        assert result.status == AgentStatus.BLOCKED_MISSING_PO_DATA
        assert "get_po_limit" in result.message

    def test_request_approval_injects_recipient_from_state(self) -> None:

        # Track the recipient that ApprovalTool.execute actually receives.
        received_recipients: list[str] = []

        invoice = Invoice(
            id="2",
            net_amount_eur=20.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        po_record = PORecord(
            po_number="450123456", limit_eur=30.0, responsible_person="Uwe Klinghoff"
        )

        # Subclass ApprovalTool to capture the recipient it receives
        class CapturingApprovalTool(ApprovalTool):
            def execute(self, params):
                received_recipients.append(params.get("recipient", "MISSING"))
                return super().execute(params)

        response_iter = iter(
            [
                LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(id="t1", name="get_invoice_data", params={"invoice_id": "2"}),
                    ],
                ),
                LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(id="t2", name="get_po_limit", params={"po_number": "450123456"}),
                    ],
                ),
                # LLM does NOT supply recipient -- only invoice_id and amount_eur
                LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(
                            id="t3",
                            name="request_approval",
                            params={"invoice_id": "2", "amount_eur": 20.0},
                        ),
                    ],
                ),
                LLMResponse(stop_reason="end_turn", text="approval obtained"),
            ]
        )

        class MockClient:
            def start(self, *_, **__):
                return next(response_iter)

            def continue_with_results(self, *_, **__):
                return next(response_iter)

        coordinator = Coordinator(
            client=MockClient(),
            tools=[
                InvoiceTool(data={"2": invoice}),
                POTool(data={"450123456": po_record}),
                CapturingApprovalTool(approval_responses={"Uwe Klinghoff": True}),
                BookingTool(booked_invoices=set()),
            ],
            gate=PermissionGate(allow_write=True),
        )
        coordinator.run(invoice_id="2", task="Book invoice 2")

        assert received_recipients == ["Uwe Klinghoff"]

    def test_injected_recipient_matches_get_po_limit_result(self) -> None:

        # End-to-end: get_po_limit -> request_approval -> end_turn.
        # The recipient passed to ApprovalTool must match responsible_person.
        responses = [
            LLMResponse(
                stop_reason="tool_use",
                tool_calls=[
                    TC(id="t1", name="get_invoice_data", params={"invoice_id": "2"}),
                ],
            ),
            LLMResponse(
                stop_reason="tool_use",
                tool_calls=[
                    TC(id="t2", name="get_po_limit", params={"po_number": "450123456"}),
                ],
            ),
            # No recipient in params
            LLMResponse(
                stop_reason="tool_use",
                tool_calls=[
                    TC(
                        id="t3",
                        name="request_approval",
                        params={"invoice_id": "2", "amount_eur": 20.0},
                    ),
                ],
            ),
            LLMResponse(stop_reason="end_turn", text="approval obtained"),
        ]

        coordinator = self._build_coordinator(responses)
        result = coordinator.run(invoice_id="2", task="Book invoice 2")

        # Should NOT be blocked -- recipient was injected correctly
        assert result.status != AgentStatus.BLOCKED_MISSING_PO_DATA
        # The run ended at end_turn without booking, so it is abandoned (not a failure)
        assert result.status == AgentStatus.BLOCKED_AGENT_ABANDONED


# ---------------------------------------------------------------------------
# Consultation flow
# ---------------------------------------------------------------------------


class TestConsultationFlow:
    """Verify routing of consultable vs hard failures, consultation budget,
    and escalation terminal state."""

    def _make_coordinator(self, responses: list, extra_tools: list | None = None):

        invoice = Invoice(
            id="13",
            net_amount_eur=25.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        po_record = PORecord(
            po_number="450123456", limit_eur=30.0, responsible_person="Uwe Klinghoff"
        )
        budget = BudgetRecord(
            cost_center="K100", period="2026-Q2", total_budget_eur=500.0, consumed_eur=480.0
        )

        response_iter = iter(responses)

        class MockClient:
            def start(self, *_, **__):
                return next(response_iter)

            def continue_with_results(self, *_, **__):
                return next(response_iter)

        tools = [
            InvoiceTool(data={"13": invoice}),
            POTool(data={"450123456": po_record}),
            BudgetTool(data={"K100": budget}),
            ConsultProcurementTool(responses={"13": ["Procurement cannot help."]}),
            EscalateToHumanTool(),
        ]
        if extra_tools:
            tools.extend(extra_tools)

        return Coordinator(
            client=MockClient(),
            tools=tools,
            gate=PermissionGate(allow_write=True),
        )

    def test_consultable_failure_returns_tool_result_not_termination(self) -> None:
        import json

        # Simulate: agent fetches invoice, then budget; budget check fails (25 > 20 remaining).
        # The coordinator must NOT terminate; it must return a ToolResult with
        # verification_failed=true back to the LLM.
        invoice = Invoice(
            id="13",
            net_amount_eur=25.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        budget = BudgetRecord(
            cost_center="K100", period="2026-Q2", total_budget_eur=500.0, consumed_eur=480.0
        )

        budget_tool_result_holder: list[str] = []

        class StepClient:
            def __init__(self):
                self._step = 0

            def start(self, *_, **__):
                return LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(id="t1", name="get_invoice_data", params={"invoice_id": "13"}),
                    ],
                )

            def continue_with_results(self, tool_results, **__):
                self._step += 1
                for tr in tool_results:
                    budget_tool_result_holder.append(tr.content)
                if self._step == 1:
                    # After invoice fetch, request budget check
                    return LLMResponse(
                        stop_reason="tool_use",
                        tool_calls=[
                            TC(id="t2", name="get_budget", params={"cost_center": "K100"}),
                        ],
                    )
                # After budget check (which should be a consultable failure ToolResult), end
                return LLMResponse(stop_reason="end_turn", text="escalating")

        tools = [
            InvoiceTool(data={"13": invoice}),
            BudgetTool(data={"K100": budget}),
            ConsultProcurementTool(responses={}),
            EscalateToHumanTool(),
        ]

        coordinator = Coordinator(
            client=StepClient(),
            tools=tools,
            gate=PermissionGate(allow_write=True),
        )
        coordinator.run(invoice_id="13", task="Book invoice 13")

        # The second element in budget_tool_result_holder is the budget check result.
        # It must be a consultable failure payload, not a hard termination.
        assert len(budget_tool_result_holder) >= 2
        budget_payload = json.loads(budget_tool_result_holder[1])
        assert budget_payload.get("verification_failed") is True
        assert budget_payload.get("consultable") is True
        assert budget_payload.get("rule") == "budget_sufficient"

    def test_hard_failure_terminates_immediately(self) -> None:

        # Agent tries to fetch an invoice that does not exist: not_found is hard.
        responses = [
            LLMResponse(
                stop_reason="tool_use",
                tool_calls=[
                    TC(id="t1", name="get_invoice_data", params={"invoice_id": "999"}),
                ],
            ),
            # This response should never be reached because the hard failure
            # terminates the run before continue_with_results is called.
            LLMResponse(stop_reason="end_turn", text="should not reach here"),
        ]

        coordinator = self._make_coordinator(responses)
        result = coordinator.run(invoice_id="999", task="Book invoice 999")

        assert result.status == AgentStatus.BLOCKED_NOT_FOUND

    def test_consult_procurement_increments_consultation_counter(self) -> None:

        state_holder: list[dict] = []

        class StepClient:
            def start(self, *_, **__):
                return LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(
                            id="t1",
                            name="consult_procurement",
                            params={
                                "invoice_id": "13",
                                "topic": "budget",
                                "question": "Can you increase the budget?",
                            },
                        ),
                    ],
                )

            def continue_with_results(self, *_, **__):
                return LLMResponse(stop_reason="end_turn", text="done")

        coordinator = Coordinator(
            client=StepClient(),
            tools=[
                ConsultProcurementTool(responses={"13": ["Procurement: No."]}),
                EscalateToHumanTool(),
            ],
            gate=PermissionGate(allow_write=True),
        )

        # Patch run to capture state after execution
        original_run = coordinator.run

        def patched_run(invoice_id, task):
            # Run normally but capture state via a hook on _execute_tool_call
            original_execute = coordinator._execute_tool_call

            def capturing_execute(tool_call, state, inv_id):
                result = original_execute(tool_call, state, inv_id)
                state_holder.append(dict(state))
                return result

            coordinator._execute_tool_call = capturing_execute
            return original_run(invoice_id=invoice_id, task=task)

        patched_run(invoice_id="13", task="Book invoice 13")

        # After one successful consult_procurement call, consultations_used should be 1
        assert any(s.get("consultations_used") == 1 for s in state_holder)

    def test_fourth_consultation_attempt_is_blocked(self) -> None:

        class MockClient:
            def start(self, *_, **__):
                return LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(
                            id="t1",
                            name="consult_procurement",
                            params={
                                "invoice_id": "13",
                                "topic": "budget",
                                "question": "One more time?",
                            },
                        ),
                    ],
                )

            def continue_with_results(self, *_, **__):
                return LLMResponse(stop_reason="end_turn", text="done")

        coordinator = Coordinator(
            client=MockClient(),
            tools=[
                ConsultProcurementTool(responses={}),
                EscalateToHumanTool(),
            ],
            gate=PermissionGate(allow_write=True),
        )

        # Pre-seed state by monkey-patching _execute_tool_call to inject consultations_used=3
        original_run = coordinator.run

        def run_with_seeded_state(invoice_id, task):
            original_execute = coordinator._execute_tool_call

            first_call = [True]

            def seeded_execute(tool_call, state, inv_id):
                if first_call[0]:
                    state["consultations_used"] = 3
                    first_call[0] = False
                return original_execute(tool_call, state, inv_id)

            coordinator._execute_tool_call = seeded_execute
            return original_run(invoice_id=invoice_id, task=task)

        result = run_with_seeded_state(invoice_id="13", task="Book invoice 13")

        assert result.status == AgentStatus.BLOCKED_AGENT_ABANDONED
        assert "Maximum" in result.message

    def test_escalate_to_human_terminates_with_correct_status(self) -> None:

        handoff = "Invoice 13: budget K100 exhausted, Procurement refused. Recommend manual review."

        class MockClient:
            def start(self, *_, **__):
                return LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(
                            id="t1",
                            name="escalate_to_human",
                            params={
                                "invoice_id": "13",
                                "reason_code": "budget_unresolved",
                                "handoff_message": handoff,
                            },
                        ),
                    ],
                )

            def continue_with_results(self, *_, **__):  # pragma: no cover
                raise AssertionError("must not be called after escalation")

        coordinator = Coordinator(
            client=MockClient(),
            tools=[EscalateToHumanTool()],
            gate=PermissionGate(allow_write=True),
        )
        result = coordinator.run(invoice_id="13", task="Book invoice 13")

        assert result.status == AgentStatus.ESCALATED_TO_HUMAN
        assert result.message == handoff
        assert result.invoice_id == "13"
