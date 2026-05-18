"""Unit tests for BookingTool."""

from __future__ import annotations

from app.booking.booking_tool import BookingTool


class TestBookingTool:
    def test_records_invoice_in_booked_set(self) -> None:
        booked: set[str] = set()
        tool = BookingTool(booked_invoices=booked)
        result = tool.execute({"invoice_id": "2", "po_number": "450123456", "amount_eur": 20.0})
        assert result["booked"] is True
        assert "2" in booked

    def test_booking_result_contains_all_fields(self) -> None:
        tool = BookingTool(booked_invoices=set())
        result = tool.execute({"invoice_id": "2", "po_number": "450123456", "amount_eur": 20.0})
        assert result["invoice_id"] == "2"
        assert result["po_number"] == "450123456"
        assert result["amount_eur"] == 20.0
