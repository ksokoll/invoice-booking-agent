"""ConsultProcurementTool: consult the Procurement team about PO/budget issues."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from app.core.failures import VerificationFailure
from app.services.permission_gate import PermissionLevel
from app.services.tool_base import DefaultTool

if TYPE_CHECKING:
    from app.core.workflow_state import WorkflowState

# Per-invoice consultation budget. Once reached, further consultations
# are refused as a hard failure and the agent must escalate.
_MAX_CONSULTATIONS_PER_INVOICE = 3


class ConsultProcurementTool(DefaultTool):
    """Sends a question to the Procurement team and returns their response."""

    name = "consult_procurement"
    description = "Consult the Procurement team about a PO or budget issue."
    permission_level = PermissionLevel.READ

    anthropic_schema: ClassVar[dict[str, Any]] = {
        "name": "consult_procurement",
        "description": (
            "Send a question to the Procurement team about a PO or budget "
            "issue and return their response.\n\n"
            "PRECONDITION (HARD REQUIREMENT):\n"
            "- You may ONLY call this tool AFTER a previous tool result "
            "  in this conversation contained verification_failed=true. "
            "  No exceptions.\n"
            "- The verification_failed result must relate to a budget or "
            "  PO limit issue (rule = 'budget_sufficient' or "
            "  'limit_not_exceeded'). For other failures Procurement cannot "
            "  help.\n"
            "- If you have not yet seen a verification_failed tool result, "
            "  do NOT call this tool. Continue the standard workflow "
            "  (get_invoice_data, get_supplier_rules, get_po_limit, "
            "  get_budget, request_approval, book_invoice) until either "
            "  the booking succeeds or a real failure is reported.\n\n"
            "USAGE RULES:\n"
            "- The question must clearly state the invoice ID, the failure "
            "  rule, the actual values from SAP, and what you need from "
            "  Procurement.\n"
            "- After Procurement responds, you MUST re-call the SAP read tool "
            "  that originally failed (get_budget for budget issues, "
            "  get_po_limit for limit issues). Re-verification against SAP "
            "  is mandatory. Never trust the Procurement response in isolation.\n\n"
            "FORBIDDEN:\n"
            "- DO NOT consult Procurement based on a problem you predicted or "
            "  assumed. Only consult in response to an actual "
            "  verification_failed tool result.\n"
            "- DO NOT consult Procurement to ask whether a booking is allowed "
            "  before trying it. Try the booking first.\n"
            "- DO NOT consult Procurement for hard failures like not_found, "
            "  already_booked, supplier_inactive, or cost_center_not_allowed.\n"
            "- DO NOT consult Procurement more than 3 times per invoice. "
            "  Escalate to human instead.\n"
            "- DO NOT trust Procurement claims without re-verifying. SAP is "
            "  the source of truth.\n\n"
            "OUTPUT USAGE:\n"
            "- The response from Procurement is a natural-language string. "
            "  Treat it as a hypothesis about what Procurement did or refused "
            "  to do, and verify against SAP."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {
                    "type": "string",
                    "description": "The invoice you are consulting about.",
                },
                "topic": {
                    "type": "string",
                    "description": ("Short machine-readable topic. One of: 'budget', 'po_limit'."),
                },
                "question": {
                    "type": "string",
                    "description": (
                        "Natural-language question to Procurement. Must "
                        "include the invoice ID, the relevant SAP "
                        "values, and what action you are asking for."
                    ),
                },
            },
            "required": ["invoice_id", "topic", "question"],
        },
    }

    def __init__(self, responses: dict[str, list[str]]) -> None:
        self._responses = responses
        self._call_index: dict[str, int] = {}

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        invoice_id = params["invoice_id"]
        responses = self._responses.get(invoice_id, [])
        index = self._call_index.get(invoice_id, 0)
        if index < len(responses):
            response_text = responses[index]
            self._call_index[invoice_id] = index + 1
        else:
            response_text = (
                "Procurement: I cannot contribute anything more to this "
                "request. Please escalate to a human."
            )
        return {
            "invoice_id": invoice_id,
            "response": response_text,
        }

    def verify_before(
        self,
        params: dict[str, Any],
        state: WorkflowState,
        invoice_id: str,
    ) -> VerificationFailure | None:
        if state.consultations_used >= _MAX_CONSULTATIONS_PER_INVOICE:
            return VerificationFailure(
                rule="consultation_limit_exceeded",
                reason=(
                    f"Maximum {_MAX_CONSULTATIONS_PER_INVOICE} consultations "
                    f"per invoice reached for invoice {invoice_id}. "
                    f"Escalate to human instead."
                ),
                consultable=False,
            )
        return None

    def update_state(
        self,
        result: dict[str, Any],
        state: WorkflowState,
    ) -> None:
        state.consultations_used += 1
