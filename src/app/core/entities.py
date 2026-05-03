"""Read-only domain entities for the invoice booking domain.

These dataclasses represent the canonical shape of business
objects as they flow through the verification rules. They are
output by tools and consumed by the Coordinator and verification
module.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Invoice:
    """An invoice to be processed and booked."""

    id: str
    net_amount_eur: float
    po_number: str
    contact_person: str
    supplier_id: str
    cost_center: str


@dataclass(frozen=True)
class SupplierRule:
    """Booking rules for a specific supplier."""

    supplier_id: str
    name: str
    active: bool
    approval_threshold_eur: float
    allowed_cost_centers: tuple[str, ...]
    requires_supporting_document: bool


@dataclass(frozen=True)
class PORecord:
    """A purchase order record with an approved spending limit."""

    po_number: str
    limit_eur: float
    responsible_person: str


@dataclass(frozen=True)
class BudgetRecord:
    """Budget for a cost center in a given period."""

    cost_center: str
    period: str
    total_budget_eur: float
    consumed_eur: float

    @property
    def remaining_eur(self) -> float:
        """Remaining budget in EUR."""
        return self.total_budget_eur - self.consumed_eur
