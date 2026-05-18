"""Unit tests for InvoiceTool."""

from __future__ import annotations

from app.core.entities import Invoice
from app.intake.invoice_tool import InvoiceTool


class TestInvoiceTool:
    def _make_tool(self) -> InvoiceTool:
        return InvoiceTool(
            data={
                "1": Invoice(
                    id="1",
                    net_amount_eur=200.0,
                    po_number="450123456",
                    contact_person="Uwe Klinghoff",
                    supplier_id="LIEF-001",
                    cost_center="K100",
                )
            }
        )

    def test_returns_invoice_data_for_known_id(self) -> None:
        tool = self._make_tool()
        result = tool.execute({"invoice_id": "1"})
        assert result["found"] is True
        assert result["net_amount_eur"] == 200.0
        assert result["po_number"] == "450123456"

    def test_returns_not_found_for_unknown_id(self) -> None:
        tool = self._make_tool()
        result = tool.execute({"invoice_id": "999"})
        assert result["found"] is False

    def test_does_not_return_po_number_as_invoice(self) -> None:
        # Regression: CrewAI agent passed PO number as invoice ID.
        tool = self._make_tool()
        result = tool.execute({"invoice_id": "450123456"})
        assert result["found"] is False
