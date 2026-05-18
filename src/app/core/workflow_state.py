"""Runtime state for one Coordinator.run() invocation.

WorkflowState replaces the ad-hoc dict[str, Any] that used to be
passed around the Coordinator. Each field corresponds to information
that one tool produces and a later tool or verification step consumes.

All fields are Optional with None defaults except:
- consultations_used: int counter, starts at 0
- approvals_received: list[str] accumulating recipients, starts empty
- booked: bool flag, starts False

The dataclass is mutable. Coordinator methods that previously wrote
to state["key"] now write to state.key directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkflowState:
    # Invoice data, written by get_invoice_data (found case)
    invoice_id: str | None = None
    invoice_amount_eur: float | None = None
    invoice_po_number: str | None = None
    invoice_contact_person: str | None = None
    invoice_supplier_id: str | None = None
    invoice_cost_center: str | None = None

    # PO data, written by get_po_limit (found case)
    po_limit_eur: float | None = None
    po_responsible_person: str | None = None

    # Supplier data, written by get_supplier_rules (found case)
    supplier_approval_threshold_eur: float | None = None

    # Budget data, written by get_budget (found case)
    budget_remaining_eur: float | None = None

    # Consultation budget counter, incremented by consult_procurement
    consultations_used: int = 0

    # Approval recipients, appended by request_approval (approved case)
    approvals_received: list[str] = field(default_factory=list)

    # Booking flag, set by book_invoice (booked case)
    booked: bool = False
