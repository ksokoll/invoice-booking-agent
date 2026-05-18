"""SupplierRulesTool: fetch booking rules for a supplier."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from app.services.permission_gate import PermissionLevel
from app.services.tool_base import DefaultTool

if TYPE_CHECKING:
    from app.core.entities import SupplierRule


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
