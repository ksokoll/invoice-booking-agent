"""Unit tests for POTool."""

from __future__ import annotations

from app.core.entities import PORecord
from app.verification.po_tool import POTool


class TestPOTool:
    def _make_tool(self) -> POTool:
        return POTool(
            data={
                "450123456": PORecord(
                    po_number="450123456",
                    limit_eur=30.0,
                    responsible_person="Uwe Klinghoff",
                )
            }
        )

    def test_returns_po_limit_for_known_number(self) -> None:
        tool = self._make_tool()
        result = tool.execute({"po_number": "450123456"})
        assert result["found"] is True
        assert result["limit_eur"] == 30.0

    def test_returns_not_found_for_unknown_po(self) -> None:
        tool = self._make_tool()
        result = tool.execute({"po_number": "000000000"})
        assert result["found"] is False
