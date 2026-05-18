"""Integration-style unit tests for the Coordinator orchestration logic.

Each test exercises the real Coordinator.run() against a FakeLLMClient
that returns a preconfigured response sequence and against real Tool
implementations.
"""

from __future__ import annotations

import json

from app.approval.approval_tool import ApprovalTool
from app.approval.consult_procurement_tool import ConsultProcurementTool
from app.booking.booking_tool import BookingTool
from app.booking.escalate_to_human_tool import EscalateToHumanTool
from app.core.entities import BudgetRecord, Invoice, PORecord
from app.core.results import ToolCall as TC
from app.core.statuses import AgentStatus
from app.intake.invoice_tool import InvoiceTool
from app.pipeline import Coordinator
from app.services.llm.client_protocol import LLMResponse
from app.services.permission_gate import PermissionGate
from app.verification.budget_tool import BudgetTool
from app.verification.po_tool import POTool
from tests.unit._doubles import FakeLLMClient

# ---------------------------------------------------------------------------
# Fix 2: PermissionDeniedError exits the coordinator loop immediately
# ---------------------------------------------------------------------------


class TestPermissionGateExitsImmediately:
    def test_should_return_permission_denied_when_gate_blocks_book_invoice(self) -> None:
        # Given a coordinator with WRITE permission disabled and an LLM that
        # immediately requests book_invoice
        booked: set[str] = set()
        invoice = Invoice(
            id="2",
            net_amount_eur=20.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        fake_llm = FakeLLMClient(
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
                                "amount_eur": 20.0,
                            },
                        )
                    ],
                ),
            ]
        )
        coordinator = Coordinator(
            client=fake_llm,
            tools=[InvoiceTool(data={"2": invoice}), BookingTool(booked_invoices=booked)],
            gate=PermissionGate(allow_write=False),
            booked_invoices=booked,
        )

        # When the agent attempts the write
        result = coordinator.run(invoice_id="2", task="Book invoice 2")

        # Then the run terminates with permission-denied and the LLM is never
        # re-prompted (FakeLLMClient was given only one response; a second
        # turn would raise StopIteration)
        assert result.status == AgentStatus.BLOCKED_PERMISSION_DENIED
        assert fake_llm.received_tool_results == []


# ---------------------------------------------------------------------------
# Fix 1: Confused-deputy guard in _pre_execute_verify
# ---------------------------------------------------------------------------


class TestConfusedDeputyOnBookInvoice:
    """Verify that the book_invoice guard uses fetched state, not LLM params."""

    def test_should_block_booking_when_amount_differs_from_fetched_state(self) -> None:
        # Given a fake LLM that first fetches the invoice (real amount 200)
        # and then asks to book it with a tampered amount of 10
        invoice = Invoice(
            id="2",
            net_amount_eur=200.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        booked: set[str] = set()
        fake_llm = FakeLLMClient(
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
                        TC(
                            id="t2",
                            name="book_invoice",
                            params={
                                "invoice_id": "2",
                                "po_number": "450123456",
                                "amount_eur": 10.0,
                            },
                        ),
                    ],
                ),
            ]
        )
        coordinator = Coordinator(
            client=fake_llm,
            tools=[InvoiceTool(data={"2": invoice}), BookingTool(booked_invoices=booked)],
            gate=PermissionGate(allow_write=True),
            booked_invoices=booked,
        )

        # When the agent attempts to book with the tampered amount
        result = coordinator.run(invoice_id="2", task="Book invoice 2")

        # Then booking is blocked as tampering and the invoice is not booked
        assert result.status == AgentStatus.BLOCKED_AMOUNT_TAMPERING
        assert "2" not in booked

    def test_should_block_booking_when_invoice_was_never_fetched(self) -> None:
        # Given a fake LLM that jumps straight to book_invoice without
        # calling get_invoice_data first
        invoice = Invoice(
            id="2",
            net_amount_eur=200.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        booked: set[str] = set()
        fake_llm = FakeLLMClient(
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
                                "amount_eur": 20.0,
                            },
                        ),
                    ],
                ),
            ]
        )
        coordinator = Coordinator(
            client=fake_llm,
            tools=[InvoiceTool(data={"2": invoice}), BookingTool(booked_invoices=booked)],
            gate=PermissionGate(allow_write=True),
            booked_invoices=booked,
        )

        # When the agent attempts to book without prior fetch
        result = coordinator.run(invoice_id="2", task="Book invoice 2")

        # Then booking is blocked for missing invoice state
        assert result.status == AgentStatus.BLOCKED_MISSING_INVOICE_STATE
        assert "2" not in booked


# ---------------------------------------------------------------------------
# Fix 2: approval_required maps to BLOCKED_APPROVAL_MISSING, not LIMIT_EXCEEDED
# ---------------------------------------------------------------------------


class TestApprovalMissingStatus:
    def test_should_yield_approval_missing_when_booking_above_threshold_without_approval(
        self,
    ) -> None:
        # Given an invoice above the approval threshold and a fake LLM that
        # fetches it, then books it with the correct amount (no tampering)
        # but never requests approval
        invoice = Invoice(
            id="2",
            net_amount_eur=200.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        booked: set[str] = set()
        fake_llm = FakeLLMClient(
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
                        TC(
                            id="t2",
                            name="book_invoice",
                            params={
                                "invoice_id": "2",
                                "po_number": "450123456",
                                "amount_eur": 200.0,
                            },
                        ),
                    ],
                ),
            ]
        )
        coordinator = Coordinator(
            client=fake_llm,
            tools=[InvoiceTool(data={"2": invoice}), BookingTool(booked_invoices=booked)],
            gate=PermissionGate(allow_write=True),
            booked_invoices=booked,
        )

        # When the agent attempts the booking
        result = coordinator.run(invoice_id="2", task="Book invoice 2")

        # Then the status is BLOCKED_APPROVAL_MISSING, not BLOCKED_LIMIT_EXCEEDED
        # (limit was never fetched), and the invoice is not booked
        assert result.status == AgentStatus.BLOCKED_APPROVAL_MISSING
        assert "2" not in booked


# ---------------------------------------------------------------------------
# Fix 2: Context Compression
# ---------------------------------------------------------------------------


class TestContextCompression:
    """Verify that compressible tool results are replaced with state pointers."""

    def test_should_compress_get_invoice_data_result_into_state_pointer(self) -> None:
        # Given a fake LLM that fetches an invoice, then ends the turn
        invoice = Invoice(
            id="2",
            net_amount_eur=20.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        fake_llm = FakeLLMClient(
            [
                LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(id="t1", name="get_invoice_data", params={"invoice_id": "2"}),
                    ],
                ),
                LLMResponse(stop_reason="end_turn", text="done"),
            ]
        )
        coordinator = Coordinator(
            client=fake_llm,
            tools=[InvoiceTool(data={"2": invoice})],
            gate=PermissionGate(allow_write=True),
        )

        # When the agent runs
        coordinator.run(invoice_id="2", task="Book invoice 2")

        # Then the tool result sent back to the LLM is a state pointer that
        # summarises the materialised state, not the full invoice payload
        assert len(fake_llm.received_tool_results) == 1
        payload = json.loads(fake_llm.received_tool_results[0][0].content)
        assert payload["status"] == "materialised_in_state"
        assert payload["tool"] == "get_invoice_data"
        assert payload["summary"]["amount_eur"] == 20.0
        assert payload["summary"]["invoice_id"] == "2"

    def test_should_not_compress_book_invoice_result(self) -> None:
        # Given a fake LLM that fetches an invoice (amount below approval
        # threshold) and then books it
        invoice = Invoice(
            id="2",
            net_amount_eur=10.0,
            po_number="450123456",
            contact_person="Uwe Klinghoff",
            supplier_id="LIEF-001",
            cost_center="K100",
        )
        booked: set[str] = set()
        fake_llm = FakeLLMClient(
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
                        TC(
                            id="t2",
                            name="book_invoice",
                            params={
                                "invoice_id": "2",
                                "po_number": "450123456",
                                "amount_eur": 10.0,
                            },
                        ),
                    ],
                ),
                LLMResponse(stop_reason="end_turn", text="booked"),
            ]
        )
        coordinator = Coordinator(
            client=fake_llm,
            tools=[InvoiceTool(data={"2": invoice}), BookingTool(booked_invoices=booked)],
            gate=PermissionGate(allow_write=True),
            booked_invoices=booked,
        )

        # When the agent runs the full sequence
        coordinator.run(invoice_id="2", task="Book invoice 2")

        # Then the book_invoice tool result is sent verbatim to the LLM
        # (not replaced by a compression pointer)
        assert len(fake_llm.received_tool_results) >= 2
        book_payload = json.loads(fake_llm.received_tool_results[1][0].content)
        assert "materialised_in_state" not in str(book_payload)
        assert book_payload["booked"] is True

    # REFACTOR-BLOCKER: The "not_found" pass-through branch in
    # _compress_tool_result is unreachable via the public API: every
    # compressible tool (the four SAP lookups) is run through
    # _post_execute_verify, which converts found=False into a hard
    # VerificationFailure that terminates the run before the tool result
    # is ever sent back to the LLM. Asserting on this branch from the
    # outside would require either changing production code or calling
    # the private method directly, both of which are out of scope.
    # DESIGN-SMELL: _compress_tool_result has a defensive branch that
    # cannot be exercised through coordinator.run(). It should either
    # be removed or _post_execute_verify's not-found routing should be
    # made consultable. The original test directly invoked the private
    # method; that test has been removed as part of this refactor.


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

    def test_should_send_consultable_failure_back_to_llm_instead_of_terminating(self) -> None:
        # Given an invoice for 25 EUR and a budget with only 20 EUR remaining,
        # and a fake LLM that fetches the invoice, then the budget, then ends
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
        fake_llm = FakeLLMClient(
            [
                LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(id="t1", name="get_invoice_data", params={"invoice_id": "13"}),
                    ],
                ),
                LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(id="t2", name="get_budget", params={"cost_center": "K100"}),
                    ],
                ),
                LLMResponse(stop_reason="end_turn", text="giving up"),
            ]
        )
        coordinator = Coordinator(
            client=fake_llm,
            tools=[InvoiceTool(data={"13": invoice}), BudgetTool(data={"K100": budget})],
            gate=PermissionGate(allow_write=True),
        )

        # When the agent runs
        result = coordinator.run(invoice_id="13", task="Book invoice 13")

        # Then the budget failure is sent back to the LLM as a consultable
        # tool result (not as a terminal CoordinatorResult), and the run
        # only stops on the subsequent end_turn
        assert result.status == AgentStatus.BLOCKED_AGENT_ABANDONED
        assert len(fake_llm.received_tool_results) == 2
        budget_payload = json.loads(fake_llm.received_tool_results[1][0].content)
        assert budget_payload["verification_failed"] is True
        assert budget_payload["consultable"] is True
        assert budget_payload["rule"] == "budget_sufficient"

    def test_should_terminate_immediately_on_hard_failure(self) -> None:
        # Given a fake LLM that fetches a non-existent invoice
        fake_llm = FakeLLMClient(
            [
                LLMResponse(
                    stop_reason="tool_use",
                    tool_calls=[
                        TC(id="t1", name="get_invoice_data", params={"invoice_id": "999"}),
                    ],
                ),
            ]
        )
        coordinator = Coordinator(
            client=fake_llm,
            tools=[InvoiceTool(data={})],
            gate=PermissionGate(allow_write=True),
        )

        # When the agent runs
        result = coordinator.run(invoice_id="999", task="Book invoice 999")

        # Then the run terminates with BLOCKED_NOT_FOUND without re-prompting
        # the LLM (FakeLLMClient was given only one response)
        assert result.status == AgentStatus.BLOCKED_NOT_FOUND
        assert fake_llm.received_tool_results == []

    def test_should_block_fourth_consultation_after_budget_is_exhausted(self) -> None:
        # Given a fake LLM that calls consult_procurement four times in a row
        consult_call = TC(
            id="t",
            name="consult_procurement",
            params={
                "invoice_id": "13",
                "topic": "budget",
                "question": "Can you help?",
            },
        )
        consult_response = LLMResponse(stop_reason="tool_use", tool_calls=[consult_call])
        fake_llm = FakeLLMClient(
            [
                consult_response,
                consult_response,
                consult_response,
                consult_response,
            ]
        )
        coordinator = Coordinator(
            client=fake_llm,
            tools=[ConsultProcurementTool(responses={"13": ["Procurement: No."]})],
            gate=PermissionGate(allow_write=True),
        )

        # When the agent attempts a fourth consultation
        result = coordinator.run(invoice_id="13", task="Book invoice 13")

        # Then the run is abandoned with the consultation-limit message and
        # only the first three consultations were sent back to the LLM
        assert result.status == AgentStatus.BLOCKED_AGENT_ABANDONED
        assert "Maximum" in result.message
        assert len(fake_llm.received_tool_results) == 3

    def test_should_terminate_with_escalated_status_on_escalate_to_human(self) -> None:
        # Given a fake LLM that calls escalate_to_human with a handoff message
        handoff = "Invoice 13: budget K100 exhausted, Procurement refused. Recommend manual review."
        fake_llm = FakeLLMClient(
            [
                LLMResponse(
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
                ),
            ]
        )
        coordinator = Coordinator(
            client=fake_llm,
            tools=[EscalateToHumanTool()],
            gate=PermissionGate(allow_write=True),
        )

        # When the agent runs
        result = coordinator.run(invoice_id="13", task="Book invoice 13")

        # Then the run terminates with ESCALATED_TO_HUMAN, carrying the
        # handoff message verbatim, and the LLM is never re-prompted
        assert result.status == AgentStatus.ESCALATED_TO_HUMAN
        assert result.message == handoff
        assert result.invoice_id == "13"
        assert fake_llm.received_tool_results == []
