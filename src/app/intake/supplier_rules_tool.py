"""SupplierRulesTool: fetch booking rules for a supplier."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from app.core.verification_rules import (
    check_cost_center_allowed,
    check_not_found,
    check_supplier_active,
)
from app.services.permission_gate import PermissionLevel
from app.services.tool_base import DefaultTool

if TYPE_CHECKING:
    from app.core.entities import SupplierRule
    from app.core.failures import VerificationFailure
    from app.core.workflow_state import WorkflowState


class SupplierRulesTool(DefaultTool):
    """Fetches booking rules for a specific supplier."""

    name = "get_supplier_rules"
    description = "Fetch the booking rules for a specific supplier by supplier ID."
    permission_level = PermissionLevel.READ

    anthropic_schema: ClassVar[dict[str, Any]] = {
        "name": "get_supplier_rules",
        "description": (
            "Fetch booking rules for a specific supplier. Call this AFTER "
            "get_invoice_data, using the supplier_id field from its result. "
            "Returns active flag, approval_threshold_eur, allowed_cost_centers, "
            "and document requirements. The approval_threshold_eur from this "
            "tool is what determines whether request_approval is needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "supplier_id": {
                    "type": "string",
                    "description": "The supplier ID, e.g. 'LIEF-001'.",
                }
            },
            "required": ["supplier_id"],
        },
    }

    def __init__(self, data: dict[str, SupplierRule]) -> None:
        self._data = data

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        supplier_id: str = params["supplier_id"]
        rule = self._data.get(supplier_id)
        if rule is None:
            return {"found": False, "supplier_id": supplier_id}
        return {
            "found": True,
            "supplier_id": rule.supplier_id,
            "name": rule.name,
            "active": rule.active,
            "approval_threshold_eur": rule.approval_threshold_eur,
            "allowed_cost_centers": rule.allowed_cost_centers,
            "requires_supporting_document": rule.requires_supporting_document,
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
        if not result.get("found"):
            return None
        failure = check_supplier_active(
            supplier_id=result["supplier_id"],
            active=result["active"],
        )
        if failure is not None:
            return failure
        if state.invoice_cost_center is not None:
            return check_cost_center_allowed(
                cost_center=state.invoice_cost_center,
                allowed_cost_centers=result["allowed_cost_centers"],
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
        state.supplier_approval_threshold_eur = result["approval_threshold_eur"]

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
            "summary": {"approval_threshold_eur": state.supplier_approval_threshold_eur},
        }
