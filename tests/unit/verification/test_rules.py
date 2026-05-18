"""Unit tests for pure verification rule functions."""

from __future__ import annotations

from app.verification.rules import (
    check_approval_consistent,
    check_approval_required,
    check_budget_sufficient,
    check_cost_center_allowed,
    check_limit_not_exceeded,
    check_not_already_booked,
    check_not_found,
    check_supplier_active,
)

# ---------------------------------------------------------------------------
# Verification — limit check
# ---------------------------------------------------------------------------


class TestLimitVerification:
    def test_blocks_when_amount_exceeds_limit(self) -> None:
        failure = check_limit_not_exceeded(
            amount_eur=200.0,
            limit_eur=30.0,
            invoice_id="1",
            po_number="450123456",
        )
        assert failure is not None
        assert failure.rule == "limit_not_exceeded"

    def test_passes_when_amount_equals_limit(self) -> None:
        failure = check_limit_not_exceeded(
            amount_eur=30.0,
            limit_eur=30.0,
            invoice_id="1",
            po_number="450123456",
        )
        assert failure is None

    def test_passes_when_amount_below_limit(self) -> None:
        failure = check_limit_not_exceeded(
            amount_eur=20.0,
            limit_eur=30.0,
            invoice_id="2",
            po_number="450123456",
        )
        assert failure is None

    def test_failure_message_contains_both_amounts(self) -> None:
        failure = check_limit_not_exceeded(
            amount_eur=200.0,
            limit_eur=30.0,
            invoice_id="1",
            po_number="450123456",
        )
        assert failure is not None
        assert "200" in failure.reason
        assert "30" in failure.reason


# ---------------------------------------------------------------------------
# Verification — approval contradiction
# ---------------------------------------------------------------------------


class TestApprovalVerification:
    def test_detects_contradiction_when_refusal_contradicts_known_limit(self) -> None:
        failure = check_approval_consistent(
            approved=False,
            stated_reason="The approval amount exceeds my responsibility.",
            expected_limit_eur=30.0,
            actual_amount_eur=25.0,
            recipient="Uwe Klinghoff",
        )
        assert failure is not None
        assert failure.rule == "approval_consistent"

    def test_passes_when_refusal_is_legitimate(self) -> None:
        # Amount really does exceed the limit — refusal is valid.
        failure = check_approval_consistent(
            approved=False,
            stated_reason="The approval amount exceeds my responsibility.",
            expected_limit_eur=30.0,
            actual_amount_eur=200.0,
            recipient="Uwe Klinghoff",
        )
        assert failure is None

    def test_passes_on_genuine_approval(self) -> None:
        failure = check_approval_consistent(
            approved=True,
            stated_reason="Approved by Uwe Klinghoff.",
            expected_limit_eur=30.0,
            actual_amount_eur=25.0,
            recipient="Uwe Klinghoff",
        )
        assert failure is None

    def test_contradiction_message_contains_recipient(self) -> None:
        failure = check_approval_consistent(
            approved=False,
            stated_reason="exceeds",
            expected_limit_eur=30.0,
            actual_amount_eur=25.0,
            recipient="Uwe Klinghoff",
        )
        assert failure is not None
        assert "Uwe Klinghoff" in failure.reason


# ---------------------------------------------------------------------------
# Verification rules — not_found, duplicate booking, approval required
# ---------------------------------------------------------------------------


class TestNotFoundVerification:
    def test_detects_invoice_not_found(self) -> None:
        failure = check_not_found("get_invoice_data", {"found": False, "invoice_id": "999"})
        assert failure is not None
        assert failure.rule == "not_found"

    def test_passes_when_found(self) -> None:
        failure = check_not_found("get_invoice_data", {"found": True, "invoice_id": "1"})
        assert failure is None


class TestDuplicateBookingVerification:
    def test_blocks_already_booked_invoice(self) -> None:
        failure = check_not_already_booked("1", booked_invoices={"1", "2"})
        assert failure is not None
        assert failure.rule == "not_already_booked"

    def test_passes_for_new_invoice(self) -> None:
        failure = check_not_already_booked("3", booked_invoices={"1", "2"})
        assert failure is None


class TestApprovalRequiredVerification:
    def test_blocks_booking_above_threshold_without_approval(self) -> None:
        failure = check_approval_required("1", amount_eur=20.0, approval_received=False)
        assert failure is not None
        assert failure.rule == "approval_required"

    def test_passes_above_threshold_with_approval(self) -> None:
        failure = check_approval_required("1", amount_eur=20.0, approval_received=True)
        assert failure is None

    def test_passes_below_threshold_without_approval(self) -> None:
        failure = check_approval_required("1", amount_eur=10.0, approval_received=False)
        assert failure is None


# ---------------------------------------------------------------------------
# Rule Set 1: SupplierRules
# ---------------------------------------------------------------------------


class TestSupplierRulesVerification:
    def test_blocks_inactive_supplier(self) -> None:
        failure = check_supplier_active("LIEF-002", active=False)
        assert failure is not None
        assert failure.rule == "supplier_active"

    def test_passes_active_supplier(self) -> None:
        failure = check_supplier_active("LIEF-001", active=True)
        assert failure is None

    def test_blocks_disallowed_cost_center(self) -> None:
        failure = check_cost_center_allowed("K300", ["K100", "K200"], "1")
        assert failure is not None
        assert failure.rule == "cost_center_allowed"

    def test_passes_allowed_cost_center(self) -> None:
        failure = check_cost_center_allowed("K100", ["K100", "K200"], "1")
        assert failure is None

    def test_passes_when_all_cost_centers_allowed(self) -> None:
        failure = check_cost_center_allowed("K999", [], "1")
        assert failure is None


# ---------------------------------------------------------------------------
# Rule Set 2: BudgetRules
# ---------------------------------------------------------------------------


class TestBudgetRulesVerification:
    def test_blocks_when_budget_insufficient(self) -> None:
        failure = check_budget_sufficient(
            amount_eur=25.0,
            remaining_budget_eur=20.0,
            cost_center="K100",
            invoice_id="13",
        )
        assert failure is not None
        assert failure.rule == "budget_sufficient"

    def test_passes_when_budget_sufficient(self) -> None:
        failure = check_budget_sufficient(
            amount_eur=10.0,
            remaining_budget_eur=20.0,
            cost_center="K100",
            invoice_id="13",
        )
        assert failure is None

    def test_passes_when_budget_exactly_covers_amount(self) -> None:
        failure = check_budget_sufficient(
            amount_eur=20.0,
            remaining_budget_eur=20.0,
            cost_center="K100",
            invoice_id="14",
        )
        assert failure is None
