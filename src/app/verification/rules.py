"""Verification engine for the coordinator loop.

This module contains the Skeptical Execution logic: after each tool
output the coordinator runs explicit domain checks before proceeding.
These checks are deterministic Python code, NOT LLM calls.

Verification rules implemented:
    check_limit_not_exceeded    -- invoice amount must not exceed PO limit
    check_approval_consistent   -- approval response must not contradict known data
    check_not_found             -- tool returned found=False
    check_not_already_booked    -- invoice must not be booked already
    check_approval_required     -- amount above threshold requires prior approval
    check_supplier_active       -- supplier must be active
    check_cost_center_allowed   -- cost center must be in supplier's allowed list
    check_budget_sufficient     -- remaining cost center budget must cover the invoice
"""

from __future__ import annotations

from typing import Any

from app.core.failures import VerificationFailure

# Invoices above this amount require explicit approval before booking.
# This is a business rule, not an LLM decision.
APPROVAL_THRESHOLD_EUR: float = 15.0

# Keywords that indicate an approver is refusing an invoice based on
# their authority limit. Derived empirically from gpt-4o-mini mock
# responses during Round 5.5. If new refusal patterns emerge in the
# harness, extend this set with the new tokens.
_LIMIT_REFUSAL_KEYWORDS: frozenset[str] = frozenset(
    {"exceeds", "responsibility", "limit", "exceeded"}
)


def check_limit_not_exceeded(
    amount_eur: float,
    limit_eur: float,
    invoice_id: str,
    po_number: str,
) -> VerificationFailure | None:
    """Verify that the invoice amount does not exceed the PO limit."""
    if amount_eur > limit_eur:
        return VerificationFailure(
            rule="limit_not_exceeded",
            reason=(
                f"Invoice {invoice_id} amount {amount_eur:.2f} EUR exceeds "
                f"PO {po_number} limit of {limit_eur:.2f} EUR. "
                "Booking blocked."
            ),
        )
    return None


def check_approval_consistent(
    approved: bool,
    stated_reason: str,
    expected_limit_eur: float,
    actual_amount_eur: float,
    recipient: str,
) -> VerificationFailure | None:
    """Detect contradictions between an approval response and known data.

    The approval tool returns `approved` plus a free-text `reason`.
    This check flags the case where the approver refuses with a
    limit-based justification ("exceeds my responsibility",
    "over my limit") but the recorded limit for that approver in
    fact covers the invoice amount. The mismatch usually means the
    approver was called with the wrong recipient or that their SAP
    record is out of date; both cases are unsafe to proceed on.

    The refusal is detected via keyword matching against
    `_LIMIT_REFUSAL_KEYWORDS`, a small heuristic derived empirically
    from mock-approver responses during Round 5.5. If a new refusal
    phrase appears in the harness that is not caught here, extend
    that set rather than broadening the check.

    Args:
        approved: The boolean approval flag returned by the tool.
        stated_reason: The free-text justification the approver
            gave. Matched case-insensitively against the refusal
            keywords.
        expected_limit_eur: The approver's authoritative limit,
            taken from the prior `get_po_limit` call. The invoice
            amount is compared against this limit.
        actual_amount_eur: The authoritative invoice amount, taken
            from the prior `get_invoice_data` call.
        recipient: The person the approval was requested from.
            Surfaced in the failure reason for the log trail.

    Returns:
        `None` when the response is internally consistent, or a
        `VerificationFailure` with rule `approval_consistent` when
        the approver refused with a limit claim that contradicts the
        recorded limit.
    """
    reason_claims_limit = any(kw in stated_reason.lower() for kw in _LIMIT_REFUSAL_KEYWORDS)

    if not approved and reason_claims_limit and actual_amount_eur <= expected_limit_eur:
        return VerificationFailure(
            rule="approval_consistent",
            reason=(
                f"{recipient} refused citing limit, but our records show "
                f"{actual_amount_eur:.2f} EUR is within their limit of "
                f"{expected_limit_eur:.2f} EUR. "
                "This is a contradiction, escalating for manual review."
            ),
        )
    return None


def check_not_found(
    tool_name: str,
    result: dict[str, Any],
) -> VerificationFailure | None:
    """Verify that a lookup tool returned a record.

    SAP lookup tools set `found: False` on their result dict when no
    matching record exists. This check turns that flag into a
    verification failure so the Coordinator stops rather than
    letting the LLM continue on phantom data.

    The failure message tries to include the identifier that was not
    found. The lookup tools expose one of `invoice_id`,
    `po_number`, or `supplier_id` on the not-found payload; the
    first present value is used. If none is set (for example when a
    tool ever returns a not-found payload with no identifier at
    all), the message falls back to the literal string `unknown` so
    the log line remains parseable.

    Args:
        tool_name: Name of the tool whose result is being checked.
            Surfaced in the failure reason so the log trail shows
            which lookup came up empty.
        result: The tool's raw result dict. Must carry a `found` key
            with a bool value; missing `found` is treated as
            `True` (backwards-compatible default for tools that
            always find a record).

    Returns:
        `None` when the result was found. A `VerificationFailure`
        with rule `not_found` when the lookup returned no record.
    """
    if not result.get("found", True):
        identifier = (
            result.get("invoice_id")
            or result.get("po_number")
            or result.get("supplier_id")
            or "unknown"
        )
        return VerificationFailure(
            rule="not_found",
            reason=(
                f"Tool '{tool_name}' could not find record '{identifier}'. "
                "Booking blocked until data is resolved."
            ),
        )
    return None


def check_not_already_booked(
    invoice_id: str,
    booked_invoices: set[str],
) -> VerificationFailure | None:
    """Verify the invoice has not already been booked."""
    if invoice_id in booked_invoices:
        return VerificationFailure(
            rule="not_already_booked",
            reason=(f"Invoice {invoice_id} has already been booked. Duplicate booking blocked."),
        )
    return None


def check_approval_required(
    invoice_id: str,
    amount_eur: float,
    approval_received: bool,
    threshold_eur: float = APPROVAL_THRESHOLD_EUR,
) -> VerificationFailure | None:
    """Block booking if the amount requires approval that has not been received."""
    if amount_eur > threshold_eur and not approval_received:
        return VerificationFailure(
            rule="approval_required",
            reason=(
                f"Invoice {invoice_id} amount {amount_eur:.2f} EUR exceeds "
                f"approval threshold of {threshold_eur:.2f} EUR. "
                "Explicit approval required before booking."
            ),
        )
    return None


def check_budget_sufficient(
    amount_eur: float,
    remaining_budget_eur: float,
    cost_center: str,
    invoice_id: str,
) -> VerificationFailure | None:
    """Block booking if the cost center budget is insufficient."""
    if amount_eur > remaining_budget_eur:
        return VerificationFailure(
            rule="budget_sufficient",
            reason=(
                f"Invoice {invoice_id} amount {amount_eur:.2f} EUR exceeds "
                f"remaining budget of {remaining_budget_eur:.2f} EUR "
                f"for cost center '{cost_center}'. Booking blocked."
            ),
        )
    return None


def check_supplier_active(
    supplier_id: str,
    active: bool,
) -> VerificationFailure | None:
    """Block booking if the supplier is inactive."""
    if not active:
        return VerificationFailure(
            rule="supplier_active",
            reason=(f"Supplier {supplier_id} is inactive. Booking blocked."),
        )
    return None


def check_cost_center_allowed(
    cost_center: str,
    allowed_cost_centers: tuple[str, ...],
    invoice_id: str,
) -> VerificationFailure | None:
    """Block booking if the cost center is not permitted for this supplier."""
    if allowed_cost_centers and cost_center not in allowed_cost_centers:
        return VerificationFailure(
            rule="cost_center_allowed",
            reason=(
                f"Cost center '{cost_center}' is not in the allowed list for this supplier "
                f"on invoice {invoice_id}. Allowed: {allowed_cost_centers}. Booking blocked."
            ),
        )
    return None
