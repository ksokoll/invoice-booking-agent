"""ApprovalTool: send approval request, return mock response."""

from __future__ import annotations

from typing import Any, ClassVar

from app.services.permission_gate import PermissionLevel


class ApprovalTool:
    """Sends an approval request and returns a simulated response."""

    name = "request_approval"
    description = "Send an approval request to a person and return their response."
    permission_level = PermissionLevel.READ

    anthropic_schema: ClassVar[dict[str, Any]] = {
        "name": "request_approval",
        "description": (
            "Send an approval request for an invoice and return the "
            "approver's response. Call this when the invoice amount "
            "exceeds the approval_threshold_eur returned by "
            "get_supplier_rules.\n\n"
            "PRECONDITION (HARD REQUIREMENT):\n"
            "- get_po_limit MUST have been called successfully before "
            "  this tool. The recipient is determined automatically "
            "  by the system from get_po_limit.responsible_person. "
            "  You do not select the recipient.\n\n"
            "USAGE RULES:\n"
            "- Pass the invoice_id and amount_eur from the current "
            "  invoice. The system will fill in the recipient.\n\n"
            "FORBIDDEN:\n"
            "- DO NOT attempt to specify a recipient. The recipient "
            "  parameter does not exist in this tool's interface. "
            "  The system handles it for you."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {
                    "type": "string",
                    "description": "The invoice ID being submitted for approval.",
                },
                "amount_eur": {
                    "type": "number",
                    "description": "The invoice net amount in EUR.",
                },
            },
            "required": ["invoice_id", "amount_eur"],
        },
    }

    def __init__(self, approval_responses: dict[str, bool]) -> None:
        self._responses = approval_responses

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        recipient: str = params["recipient"]
        approved = self._responses.get(recipient, False)
        reason = (
            f"Approved by {recipient}."
            if approved
            else f"{recipient}: The approval amount exceeds my responsibility."
        )
        return {
            "recipient": recipient,
            "approved": approved,
            "reason": reason,
        }
