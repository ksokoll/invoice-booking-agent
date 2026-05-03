"""Agent terminal status enumeration.

Every Coordinator run ends in exactly one AgentStatus value. The
status is the canonical signal for the test harness, the report
writer, and the eventual human-facing API.
"""

from enum import Enum


class AgentStatus(Enum):
    """Terminal status of an invoice booking attempt."""

    BOOKED = "booked"
    BLOCKED_LIMIT_EXCEEDED = "blocked_limit_exceeded"
    BLOCKED_CONTRADICTION = "blocked_contradiction"
    BLOCKED_PERMISSION_DENIED = "blocked_permission_denied"
    BLOCKED_NOT_FOUND = "blocked_not_found"
    BLOCKED_ALREADY_BOOKED = "blocked_already_booked"
    BLOCKED_MAX_ITERATIONS = "blocked_max_iterations"
    BLOCKED_SUPPLIER_INACTIVE = "blocked_supplier_inactive"
    BLOCKED_COST_CENTER_NOT_ALLOWED = "blocked_cost_center_not_allowed"
    BLOCKED_BUDGET_INSUFFICIENT = "blocked_budget_insufficient"
    BLOCKED_MISSING_INVOICE_STATE = "blocked_missing_invoice_state"
    BLOCKED_AMOUNT_TAMPERING = "blocked_amount_tampering"
    BLOCKED_APPROVAL_MISSING = "blocked_approval_missing"
    BLOCKED_AGENT_ABANDONED = "blocked_agent_abandoned"
    BLOCKED_MISSING_PO_DATA = "blocked_missing_po_data"
    ESCALATED_TO_HUMAN = "escalated_to_human"
