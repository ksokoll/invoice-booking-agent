"""BudgetTool: fetch remaining budget for a cost center."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from app.core.verification_rules import check_budget_sufficient, check_not_found
from app.services.permission_gate import PermissionLevel
from app.services.tool_base import DefaultTool

if TYPE_CHECKING:
    from app.core.entities import BudgetRecord
    from app.core.failures import VerificationFailure
    from app.core.workflow_state import WorkflowState


class BudgetTool(DefaultTool):
    """Fetches the remaining budget for a cost center."""

    name = "get_budget"
    description = "Fetch the remaining budget for a cost center in the current period."
    permission_level = PermissionLevel.READ

    anthropic_schema: ClassVar[dict[str, Any]] = {
        "name": "get_budget",
        "description": (
            "Fetch the remaining budget for a cost center in the current "
            "period. Call this AFTER get_invoice_data, using the cost_center "
            "field from its result. The remaining_eur field of the result "
            "must cover the invoice net_amount_eur, otherwise the booking "
            "will be blocked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cost_center": {
                    "type": "string",
                    "description": "The cost center identifier, e.g. 'K100'.",
                }
            },
            "required": ["cost_center"],
        },
    }

    def __init__(self, data: dict[str, BudgetRecord]) -> None:
        self._data = data

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        cost_center: str = params["cost_center"]
        record = self._data.get(cost_center)
        if record is None:
            return {"found": False, "cost_center": cost_center}
        return {
            "found": True,
            "cost_center": record.cost_center,
            "period": record.period,
            "total_budget_eur": record.total_budget_eur,
            "consumed_eur": record.consumed_eur,
            "remaining_eur": record.remaining_eur,
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
        if result.get("found") and state.invoice_amount_eur is not None:
            return check_budget_sufficient(
                amount_eur=state.invoice_amount_eur,
                remaining_budget_eur=result["remaining_eur"],
                cost_center=result["cost_center"],
                invoice_id=invoice_id,
            )
        return None

    def update_state(
        self,
        result: dict[str, Any],
        state: WorkflowState,
    ) -> None:
        if not result.get("found"):
            return
        state.budget_remaining_eur = result["remaining_eur"]

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
            "summary": {"remaining_eur": state.budget_remaining_eur},
        }
