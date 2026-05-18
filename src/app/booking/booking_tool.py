"""BookingTool: execute the final invoice booking."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from app.core.failures import VerificationFailure
from app.services.permission_gate import PermissionLevel
from app.services.tool_base import DefaultTool
from app.verification.rules import (
    APPROVAL_THRESHOLD_EUR,
    check_approval_required,
    check_not_already_booked,
)

if TYPE_CHECKING:
    from app.core.workflow_state import WorkflowState


class BookingTool(DefaultTool):
    """Executes the final invoice booking. WRITE-level tool."""

    name = "book_invoice"
    description = "Execute the final booking of an invoice in the accounting system."
    permission_level = PermissionLevel.WRITE

    anthropic_schema: ClassVar[dict[str, Any]] = {
        "name": "book_invoice",
        "description": (
            "Execute the final booking of an invoice. This tool has irreversible "
            "side effects. Refuse to call this tool unless ALL of the following "
            "have already been called successfully in the current conversation: "
            "(1) get_invoice_data, "
            "(2) get_supplier_rules, "
            "(3) get_po_limit, "
            "(4) get_budget. "
            "If the invoice amount exceeds the approval_threshold_eur from "
            "get_supplier_rules, you MUST also have called request_approval "
            "and received approved=true before calling book_invoice. "
            "The amount_eur parameter MUST exactly match the net_amount_eur "
            "returned by get_invoice_data. Never substitute or round the amount. "
            "The po_number parameter MUST exactly match the po_number returned "
            "by get_invoice_data. Never use a PO number from the user's task "
            "description, only from the invoice itself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {
                    "type": "string",
                    "description": (
                        "The invoice ID to book. Must match the invoice_id "
                        "field of get_invoice_data."
                    ),
                },
                "po_number": {
                    "type": "string",
                    "description": (
                        "The PO number, copied verbatim from the po_number "
                        "field of get_invoice_data. Not from the user's "
                        "task description."
                    ),
                },
                "amount_eur": {
                    "type": "number",
                    "description": (
                        "The net amount in EUR, copied verbatim from the "
                        "net_amount_eur field of get_invoice_data."
                    ),
                },
            },
            "required": ["invoice_id", "po_number", "amount_eur"],
        },
    }

    def __init__(self, booked_invoices: set[str]) -> None:
        self._booked = booked_invoices

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        invoice_id: str = params["invoice_id"]
        self._booked.add(invoice_id)
        return {
            "booked": True,
            "invoice_id": invoice_id,
            "po_number": params["po_number"],
            "amount_eur": params["amount_eur"],
            "message": f"Invoice {invoice_id} successfully booked.",
        }

    def verify_before(
        self,
        params: dict[str, Any],
        state: WorkflowState,
        invoice_id: str,
    ) -> VerificationFailure | None:
        # Confused-deputy guard: the authoritative amount must come from
        # the prior get_invoice_data call, not from the LLM-supplied params.
        state_amount = state.invoice_amount_eur
        if state_amount is None:
            return VerificationFailure(
                rule="missing_invoice_state",
                reason=(
                    f"Cannot book invoice {invoice_id}: invoice data was never "
                    f"fetched. The agent must call get_invoice_data before "
                    f"book_invoice."
                ),
                consultable=False,
            )

        params_amount = params.get("amount_eur")
        if params_amount is not None and abs(params_amount - state_amount) > 0.001:
            return VerificationFailure(
                rule="amount_tampering",
                reason=(
                    f"Invoice {invoice_id}: book_invoice was called with "
                    f"amount_eur={params_amount} but the authoritative amount "
                    f"from get_invoice_data is {state_amount}. Refusing to book."
                ),
                consultable=False,
            )

        failure = check_not_already_booked(
            invoice_id=invoice_id,
            booked_invoices=self._booked,
        )
        if failure is not None:
            return failure

        return check_approval_required(
            invoice_id=invoice_id,
            amount_eur=state_amount,
            approval_received=bool(state.approvals_received),
            threshold_eur=(
                state.supplier_approval_threshold_eur
                if state.supplier_approval_threshold_eur is not None
                else APPROVAL_THRESHOLD_EUR
            ),
        )

    def update_state(
        self,
        result: dict[str, Any],
        state: WorkflowState,
    ) -> None:
        if result.get("booked"):
            state.booked = True
