"""ApprovalTool: send approval request, return mock response."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from app.core.failures import VerificationFailure
from app.services.permission_gate import PermissionLevel
from app.services.tool_base import DefaultTool
from app.verification.rules import check_approval_consistent

if TYPE_CHECKING:
    from app.core.workflow_state import WorkflowState


class ApprovalTool(DefaultTool):
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

    def verify_before(
        self,
        params: dict[str, Any],
        state: WorkflowState,
        invoice_id: str,
    ) -> VerificationFailure | None:
        state_recipient = state.po_responsible_person
        if state_recipient is None:
            return VerificationFailure(
                rule="missing_po_data",
                reason=(
                    f"Cannot request approval for invoice {invoice_id}: "
                    f"get_po_limit has not been called yet, so the "
                    f"authoritative recipient is unknown. The agent "
                    f"must call get_po_limit before request_approval."
                ),
                consultable=False,
            )
        # Coordinator-managed parameter injection per ADR-005: the recipient
        # is determined by the system from authoritative state, never by
        # the LLM. ToolCall.params is the documented extension point for
        # this injection (mutable dict on a frozen dataclass).
        params["recipient"] = state_recipient
        return None

    def verify_after(
        self,
        params: dict[str, Any],
        result: dict[str, Any],
        state: WorkflowState,
        invoice_id: str,
    ) -> VerificationFailure | None:
        # Option A (per CLAUDE.md): the approvals_received append is kept
        # co-located with the contradiction check because both depend on
        # the same params["recipient"], which verify_before just injected.
        if state.invoice_amount_eur is not None and state.po_limit_eur is not None:
            failure = check_approval_consistent(
                approved=result["approved"],
                stated_reason=result["reason"],
                expected_limit_eur=state.po_limit_eur,
                actual_amount_eur=state.invoice_amount_eur,
                recipient=params["recipient"],
            )
            if failure is not None:
                return failure
        if result.get("approved"):
            state.approvals_received.append(params["recipient"])
        return None
