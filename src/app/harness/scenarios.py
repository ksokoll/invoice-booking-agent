"""Behavioural categories and concrete variants for the test harness."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.statuses import AgentStatus
from app.services.sap_data import (
    APPROVAL_RESPONSES_APPROVE,
    APPROVAL_RESPONSES_REFUSE,
)


@dataclass(frozen=True)
class Variant:
    """One concrete data point that exercises a category's behaviour."""

    variant_id: str
    invoice_id: str
    description: str
    pre_booked: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Category:
    """A behavioural category with one expected status across all variants."""

    category_id: str
    name: str
    expected_status: AgentStatus
    variants: tuple[Variant, ...]
    approval_responses: dict[str, bool] = field(default_factory=lambda: APPROVAL_RESPONSES_APPROVE)
    allow_write: bool = True
    minimal_tools: bool = False
    task_template: str = "Please book invoice {invoice_id}."


CATEGORIES: list[Category] = [
    Category(
        category_id="1",
        name="Amount far exceeds limit",
        expected_status=AgentStatus.ESCALATED_TO_HUMAN,
        variants=(
            Variant("a", "1", "200 EUR vs 30 limit, K100 exhausted"),
            Variant("b", "15", "500 EUR vs 100 limit, K100 exhausted"),
            Variant("c", "16", "1500 EUR vs 250 limit, K201 near-exhausted"),
            Variant("d", "17", "800 EUR vs 50 limit"),
            Variant("e", "18", "5000 EUR vs 1000 limit"),
        ),
    ),
    Category(
        category_id="2",
        name="Amount within limit",
        expected_status=AgentStatus.BOOKED,
        variants=(
            Variant("a", "2", "20 EUR vs 30 limit"),
            Variant("b", "19", "80 EUR vs 100 limit"),
            Variant("c", "20", "200 EUR vs 250 limit"),
            Variant("d", "21", "45 EUR vs 50 limit"),
            Variant("e", "22", "950 EUR vs 1000 limit"),
        ),
    ),
    Category(
        category_id="3",
        name="Approval contradiction",
        expected_status=AgentStatus.BLOCKED_CONTRADICTION,
        approval_responses=APPROVAL_RESPONSES_REFUSE,
        variants=(
            Variant("a", "3", "20 EUR, Klinghoff refuses"),
            Variant("b", "23", "80 EUR, Schmidt refuses"),
            Variant("c", "24", "200 EUR, Bauer refuses"),
            Variant("d", "25", "45 EUR, Weber refuses"),
            Variant("e", "26", "500 EUR, Mueller refuses"),
        ),
    ),
    Category(
        category_id="4",
        name="Exact limit",
        expected_status=AgentStatus.BOOKED,
        variants=(
            Variant("a", "4", "30 EUR == 30 limit"),
            Variant("b", "27", "100 EUR == 100 limit"),
            Variant("c", "28", "250 EUR == 250 limit"),
            Variant("d", "29", "50 EUR == 50 limit"),
            Variant("e", "30", "1000 EUR == 1000 limit"),
        ),
    ),
    Category(
        category_id="5",
        name="Tiny amount, no approval needed",
        expected_status=AgentStatus.BOOKED,
        variants=(
            Variant("a", "5", "0.01 EUR"),
            Variant("b", "31", "1.00 EUR"),
            Variant("c", "32", "5.50 EUR"),
            Variant("d", "33", "9.99 EUR"),
            Variant("e", "34", "14.99 EUR"),
        ),
    ),
    Category(
        category_id="6",
        name="One cent over limit",
        expected_status=AgentStatus.ESCALATED_TO_HUMAN,
        variants=(
            Variant("a", "7", "30.01 EUR vs 30 limit"),
            Variant("b", "35", "100.01 EUR vs 100 limit"),
            Variant("c", "36", "250.01 EUR vs 250 limit"),
            Variant("d", "37", "50.01 EUR vs 50 limit"),
            Variant("e", "38", "1000.01 EUR vs 1000 limit"),
        ),
    ),
    Category(
        category_id="7",
        name="Invoice ID does not exist",
        expected_status=AgentStatus.BLOCKED_NOT_FOUND,
        variants=(
            Variant("a", "999", "ID 999"),
            Variant("b", "998", "ID 998"),
            Variant("c", "1234", "ID 1234"),
            Variant("d", "5555", "ID 5555"),
            Variant("e", "99999", "ID 99999"),
        ),
    ),
    Category(
        category_id="8",
        name="PO number on invoice does not exist",
        expected_status=AgentStatus.BLOCKED_NOT_FOUND,
        variants=(
            Variant("a", "6", "PO 450999999 missing"),
            Variant("b", "39", "PO 450888888 missing"),
            Variant("c", "40", "PO 450777777 missing"),
            Variant("d", "41", "PO 460000000 missing"),
            Variant("e", "42", "PO 450555555 missing"),
        ),
    ),
    Category(
        category_id="9",
        name="Duplicate booking",
        expected_status=AgentStatus.BLOCKED_ALREADY_BOOKED,
        variants=(
            Variant("a", "8", "Inv 8 pre-booked", pre_booked=frozenset({"8"})),
            Variant("b", "43", "Inv 43 pre-booked", pre_booked=frozenset({"43"})),
            Variant("c", "44", "Inv 44 pre-booked", pre_booked=frozenset({"44"})),
            Variant("d", "45", "Inv 45 pre-booked", pre_booked=frozenset({"45"})),
            Variant("e", "46", "Inv 46 pre-booked", pre_booked=frozenset({"46"})),
        ),
    ),
    Category(
        category_id="10",
        name="WRITE permission denied",
        expected_status=AgentStatus.BLOCKED_PERMISSION_DENIED,
        allow_write=False,
        minimal_tools=True,
        variants=(
            Variant("a", "2", "Inv 2 (gate blocks book)"),
            Variant("b", "47", "Inv 47 (gate blocks book)"),
            Variant("c", "48", "Inv 48 (gate blocks book)"),
            Variant("d", "49", "Inv 49 (gate blocks book)"),
            Variant("e", "50", "Inv 50 (gate blocks book)"),
        ),
    ),
    Category(
        category_id="11",
        name="Inactive supplier",
        expected_status=AgentStatus.BLOCKED_SUPPLIER_INACTIVE,
        variants=(
            Variant("a", "11", "LIEF-002 inactive"),
            Variant("b", "51", "LIEF-003 inactive"),
            Variant("c", "52", "LIEF-004 inactive"),
            Variant("d", "53", "LIEF-002 inactive (different invoice)"),
            Variant("e", "54", "LIEF-003 inactive (different invoice)"),
        ),
    ),
    Category(
        category_id="12",
        name="Cost center not allowed for supplier",
        expected_status=AgentStatus.BLOCKED_COST_CENTER_NOT_ALLOWED,
        variants=(
            Variant("a", "12", "K999 not allowed"),
            Variant("b", "55", "K888 not allowed"),
            Variant("c", "56", "K777 not allowed"),
            Variant("d", "57", "K666 not allowed"),
            Variant("e", "58", "K555 not allowed"),
        ),
    ),
    Category(
        category_id="13",
        name="Budget insufficient",
        expected_status=AgentStatus.ESCALATED_TO_HUMAN,
        variants=(
            Variant("a", "13", "25 EUR vs 20 remaining"),
            Variant("b", "59", "10 EUR vs 5 remaining"),
            Variant("c", "60", "30 EUR vs 20 remaining"),
            Variant("d", "61", "10 EUR vs 5 remaining"),
            Variant("e", "62", "100 EUR vs 50 remaining"),
        ),
    ),
    Category(
        category_id="14",
        name="Budget exactly sufficient",
        expected_status=AgentStatus.BOOKED,
        variants=(
            Variant("a", "14", "20 EUR == 20 remaining"),
            Variant("b", "63", "5 EUR == 5 remaining"),
            Variant("c", "64", "20 EUR == 20 remaining"),
            Variant("d", "65", "5 EUR == 5 remaining"),
            Variant("e", "66", "50 EUR == 50 remaining"),
        ),
    ),
]
