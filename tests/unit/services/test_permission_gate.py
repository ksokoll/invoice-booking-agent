"""Unit tests for PermissionGate."""

from __future__ import annotations

import pytest

from app.services.permission_gate import PermissionDeniedError, PermissionGate, PermissionLevel


class TestPermissionGate:
    def test_read_is_always_approved(self) -> None:
        gate = PermissionGate(allow_write=False)
        gate.check("get_invoice_data", PermissionLevel.READ)  # must not raise

    def test_write_is_approved_when_allowed(self) -> None:
        gate = PermissionGate(allow_write=True)
        gate.check("book_invoice", PermissionLevel.WRITE)  # must not raise

    def test_write_is_blocked_when_not_allowed(self) -> None:
        gate = PermissionGate(allow_write=False)
        with pytest.raises(PermissionDeniedError):
            gate.check("book_invoice", PermissionLevel.WRITE)

    def test_blocked_error_message_contains_tool_name(self) -> None:
        gate = PermissionGate(allow_write=False)
        with pytest.raises(PermissionDeniedError, match="book_invoice"):
            gate.check("book_invoice", PermissionLevel.WRITE)
