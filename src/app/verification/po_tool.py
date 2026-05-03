"""POTool: fetch PO limit by PO number."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from app.services.permission_gate import PermissionLevel

if TYPE_CHECKING:
    from app.core.entities import PORecord


class POTool:
    """Fetches the approved spending limit for a purchase order."""

    name = "get_po_limit"
    description = "Fetch the approved spending limit for a SAP purchase order number."
    permission_level = PermissionLevel.READ

    anthropic_schema: ClassVar[dict[str, Any]] = {
        "name": "get_po_limit",
        "description": (
            "Fetch the approved spending limit for a SAP purchase order. "
            "Call this AFTER get_invoice_data, using the po_number field "
            "from its result. Do NOT use a PO number mentioned in the user's "
            "task description; the invoice is the source of truth. The "
            "responsible_person field of the result is the AUTHORITATIVE "
            "recipient for any subsequent request_approval call. ONLY accepts "
            "PO numbers (e.g. '450123456'). Do NOT pass invoice IDs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "po_number": {
                    "type": "string",
                    "description": "The SAP PO number, e.g. '450123456'.",
                }
            },
            "required": ["po_number"],
        },
    }

    def __init__(self, data: dict[str, PORecord]) -> None:
        self._data = data

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        po_number: str = params["po_number"]
        record = self._data.get(po_number)
        if record is None:
            return {"found": False, "po_number": po_number}
        return {
            "found": True,
            "po_number": record.po_number,
            "limit_eur": record.limit_eur,
            "responsible_person": record.responsible_person,
        }
