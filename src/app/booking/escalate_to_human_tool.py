"""EscalateToHumanTool: hand off to a human AP clerk."""

from __future__ import annotations

from typing import Any, ClassVar

from app.services.permission_gate import PermissionLevel


class EscalateToHumanTool:
    """Hands the invoice off to a human AP clerk for manual review."""

    name = "escalate_to_human"
    description = "Escalate the invoice to a human AP clerk for manual review."
    permission_level = PermissionLevel.READ

    anthropic_schema: ClassVar[dict[str, Any]] = {
        "name": "escalate_to_human",
        "description": (
            "Escalate this invoice to a human AP clerk for manual "
            "review. Call this tool when one of the following is true:\n\n"
            "USAGE RULES:\n"
            "- A consultable verification failure occurred and you have "
            "  already consulted Procurement without resolution.\n"
            "- A consultable verification failure occurred and you "
            "  cannot identify a relevant correspondent to consult.\n"
            "- You have insufficient information to proceed and no tool "
            "  can give you that information.\n"
            "- Your consultation budget for this invoice is exhausted.\n\n"
            "FORBIDDEN:\n"
            "- DO NOT call this tool for a hard verification failure "
            "  (not_found, already_booked, permission_denied, "
            "  amount_tampering). Those terminate "
            "  the run on their own.\n"
            "- DO NOT call this tool to ask the human a clarifying "
            "  question. Escalation is a hand-off, not a dialogue.\n\n"
            "OUTPUT:\n"
            "- The handoff_message must be a clear, structured summary "
            "  of what you tried, what failed, what you consulted, and "
            "  what you recommend the human do next.\n"
            "- After calling this tool, the run terminates with status "
            "  ESCALATED_TO_HUMAN."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {
                    "type": "string",
                    "description": "The invoice being escalated.",
                },
                "reason_code": {
                    "type": "string",
                    "description": (
                        "Short machine-readable reason. Use one of: "
                        "'budget_unresolved', 'limit_unresolved', "
                        "'consultation_exhausted', 'insufficient_information'."
                    ),
                },
                "handoff_message": {
                    "type": "string",
                    "description": (
                        "Structured natural-language handoff for the "
                        "human AP clerk. Must include: what was attempted, "
                        "what failed, what was consulted, what is "
                        "recommended."
                    ),
                },
            },
            "required": ["invoice_id", "reason_code", "handoff_message"],
        },
    }

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "escalated": True,
            "invoice_id": params["invoice_id"],
            "reason_code": params["reason_code"],
            "handoff_message": params["handoff_message"],
        }
