"""InvoiceTool: fetch invoice details by ID."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from app.core.verification_rules import check_limit_not_exceeded, check_not_found
from app.services.permission_gate import PermissionLevel
from app.services.tool_base import DefaultTool

if TYPE_CHECKING:
    from app.core.entities import Invoice
    from app.core.failures import VerificationFailure
    from app.core.workflow_state import WorkflowState


class InvoiceTool(DefaultTool):
    """Fetches invoice details from the invoice system."""

    name = "get_invoice_data"
    description = "Fetch invoice details (amount, PO number, contact) by invoice ID."
    permission_level = PermissionLevel.READ

    anthropic_schema: ClassVar[dict[str, Any]] = {
        "name": "get_invoice_data",
        "description": (
            "Fetch invoice details from the invoice system. This is ALWAYS "
            "the first tool you call when processing an invoice. The result "
            "contains net_amount_eur, po_number, supplier_id, cost_center, "
            "and contact_person, all of which are the AUTHORITATIVE source "
            "for any subsequent tool call. ONLY accepts invoice IDs (e.g. "
            "'1', '42'). Do NOT pass PO numbers to this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {
                    "type": "string",
                    "description": "The invoice ID, e.g. '1'. Not a PO number.",
                }
            },
            "required": ["invoice_id"],
        },
    }

    def __init__(self, data: dict[str, Invoice]) -> None:
        self._data = data

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        invoice_id: str = params["invoice_id"]
        invoice = self._data.get(invoice_id)
        if invoice is None:
            return {"found": False, "invoice_id": invoice_id}
        return {
            "found": True,
            "invoice_id": invoice.id,
            "net_amount_eur": invoice.net_amount_eur,
            "po_number": invoice.po_number,
            "contact_person": invoice.contact_person,
            "supplier_id": invoice.supplier_id,
            "cost_center": invoice.cost_center,
        }

    def verify_after(
        self,
        params: dict[str, Any],
        result: dict[str, Any],
        state: WorkflowState,
        invoice_id: str,
    ) -> VerificationFailure | None:
        failure = check_not_found(self.name, result)
        if failure is not None:
            return failure
        if result.get("found") and state.po_limit_eur is not None:
            return check_limit_not_exceeded(
                amount_eur=result["net_amount_eur"],
                limit_eur=state.po_limit_eur,
                invoice_id=result["invoice_id"],
                po_number=result["po_number"],
            )
        return None

    def update_state(
        self,
        result: dict[str, Any],
        state: WorkflowState,
    ) -> None:
        if not result.get("found"):
            return
        state.invoice_id = result["invoice_id"]
        state.invoice_amount_eur = result["net_amount_eur"]
        state.invoice_po_number = result["po_number"]
        state.invoice_contact_person = result.get("contact_person", "")
        state.invoice_supplier_id = result.get("supplier_id", "")
        state.invoice_cost_center = result.get("cost_center", "")

    def compress_result(
        self,
        result: dict[str, Any],
        state: WorkflowState,
    ) -> dict[str, Any]:
        if not result.get("found", True):
            return result
        return {
            "status": "materialised_in_state",
            "tool": self.name,
            "summary": {
                "invoice_id": state.invoice_id,
                "amount_eur": state.invoice_amount_eur,
                "po_number": state.invoice_po_number,
                "supplier_id": state.invoice_supplier_id,
                "cost_center": state.invoice_cost_center,
            },
        }
