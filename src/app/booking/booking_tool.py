"""BookingTool: execute the final invoice booking."""

from __future__ import annotations

from typing import Any, ClassVar

from app.services.permission_gate import PermissionLevel


class BookingTool:
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
