"""Mock SAP data for the invoice booking agent.

This module simulates the external SAP system that the agent reads
from. In production, these dicts would be replaced by real SAP
adapters returning the same shapes.

All data is read-only across scenario runs. The only mutable state
is booked_invoices, which is created fresh per scenario.
"""

from __future__ import annotations

from app.core.entities import BudgetRecord, Invoice, PORecord, SupplierRule

# ---------------------------------------------------------------------------
# Invoice factory
# ---------------------------------------------------------------------------


def _inv(
    invoice_id: str,
    amount: float,
    po_number: str = "450123456",
    cost_center: str = "K100",
    supplier_id: str = "LIEF-001",
    contact_person: str = "Uwe Klinghoff",
) -> Invoice:
    """Build an Invoice for the mock data dict."""
    return Invoice(
        id=invoice_id,
        net_amount_eur=amount,
        po_number=po_number,
        contact_person=contact_person,
        supplier_id=supplier_id,
        cost_center=cost_center,
    )


# ---------------------------------------------------------------------------
# PO Records
# ---------------------------------------------------------------------------

PO_RECORDS: dict[str, PORecord] = {
    "450123456": PORecord(
        po_number="450123456", limit_eur=30.0, responsible_person="Uwe Klinghoff"
    ),
    "450200000": PORecord(
        po_number="450200000", limit_eur=100.0, responsible_person="Anna Schmidt"
    ),
    "450300000": PORecord(po_number="450300000", limit_eur=250.0, responsible_person="Klaus Bauer"),
    "450400000": PORecord(po_number="450400000", limit_eur=50.0, responsible_person="Maria Weber"),
    "450500000": PORecord(
        po_number="450500000", limit_eur=1000.0, responsible_person="Thomas Mueller"
    ),
}


# ---------------------------------------------------------------------------
# Budget Records
# ---------------------------------------------------------------------------

BUDGET_RECORDS: dict[str, BudgetRecord] = {
    "K100": BudgetRecord(
        cost_center="K100", period="2026-Q2", total_budget_eur=500.0, consumed_eur=480.0
    ),
    "K200": BudgetRecord(
        cost_center="K200", period="2026-Q2", total_budget_eur=500.0, consumed_eur=0.0
    ),
    "K201": BudgetRecord(
        cost_center="K201", period="2026-Q2", total_budget_eur=100.0, consumed_eur=95.0
    ),
    "K202": BudgetRecord(
        cost_center="K202", period="2026-Q2", total_budget_eur=200.0, consumed_eur=180.0
    ),
    "K203": BudgetRecord(
        cost_center="K203", period="2026-Q2", total_budget_eur=50.0, consumed_eur=45.0
    ),
    "K204": BudgetRecord(
        cost_center="K204", period="2026-Q2", total_budget_eur=1000.0, consumed_eur=950.0
    ),
    "K300": BudgetRecord(
        cost_center="K300", period="2026-Q2", total_budget_eur=1000.0, consumed_eur=0.0
    ),
    "K400": BudgetRecord(
        cost_center="K400", period="2026-Q2", total_budget_eur=100.0, consumed_eur=0.0
    ),
    "K500": BudgetRecord(
        cost_center="K500", period="2026-Q2", total_budget_eur=1000.0, consumed_eur=0.0
    ),
}


# ---------------------------------------------------------------------------
# Supplier Rules
# ---------------------------------------------------------------------------

SUPPLIER_RULES: dict[str, SupplierRule] = {
    "LIEF-001": SupplierRule(
        supplier_id="LIEF-001",
        name="Uwe Klinghoff GmbH",
        active=True,
        approval_threshold_eur=15.0,
        allowed_cost_centers=(
            "K100",
            "K200",
            "K201",
            "K202",
            "K203",
            "K204",
            "K300",
            "K400",
            "K500",
        ),
        requires_supporting_document=False,
    ),
    "LIEF-002": SupplierRule(
        supplier_id="LIEF-002",
        name="Inactive Supplier AG",
        active=False,
        approval_threshold_eur=0.0,
        allowed_cost_centers=(),
        requires_supporting_document=False,
    ),
    "LIEF-003": SupplierRule(
        supplier_id="LIEF-003",
        name="Obsolete Supplier GmbH",
        active=False,
        approval_threshold_eur=0.0,
        allowed_cost_centers=(),
        requires_supporting_document=False,
    ),
    "LIEF-004": SupplierRule(
        supplier_id="LIEF-004",
        name="Cancelled Supplier AG",
        active=False,
        approval_threshold_eur=0.0,
        allowed_cost_centers=(),
        requires_supporting_document=False,
    ),
}


# ---------------------------------------------------------------------------
# Approval responses
# ---------------------------------------------------------------------------

APPROVAL_RESPONSES_APPROVE: dict[str, bool] = {
    "Uwe Klinghoff": True,
    "Anna Schmidt": True,
    "Klaus Bauer": True,
    "Maria Weber": True,
    "Thomas Mueller": True,
}

APPROVAL_RESPONSES_REFUSE: dict[str, bool] = {
    "Uwe Klinghoff": False,
    "Anna Schmidt": False,
    "Klaus Bauer": False,
    "Maria Weber": False,
    "Thomas Mueller": False,
}


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

INVOICES: dict[str, Invoice] = {
    # Existing Round 5.4 invoices (variant "a" of each category)
    "1": _inv("1", 200.0, "450123456", "K100"),
    "2": _inv("2", 20.0, "450123456", "K100"),
    "3": _inv("3", 20.0, "450123456", "K300"),
    "4": _inv("4", 30.0, "450123456", "K300"),
    "5": _inv("5", 0.01, "450123456", "K100"),
    "6": _inv("6", 15.0, "450999999", "K100"),
    "7": _inv("7", 30.01, "450123456", "K100"),
    "8": _inv("8", 20.0, "450123456", "K100"),
    "11": _inv("11", 10.0, "450123456", "K100", supplier_id="LIEF-002"),
    "12": _inv("12", 10.0, "450123456", "K999"),
    "13": _inv("13", 25.0, "450123456", "K100"),
    "14": _inv("14", 20.0, "450123456", "K100"),
    # Category 1: Amount far exceeds limit
    "15": _inv("15", 500.0, "450200000", "K100"),
    "16": _inv("16", 1500.0, "450300000", "K201"),
    "17": _inv("17", 800.0, "450400000", "K202"),
    "18": _inv("18", 5000.0, "450500000", "K204"),
    # Category 2: Amount within limit
    "19": _inv("19", 80.0, "450200000", "K200"),
    "20": _inv("20", 200.0, "450300000", "K500"),
    "21": _inv("21", 45.0, "450400000", "K200"),
    "22": _inv("22", 950.0, "450500000", "K500"),
    # Category 3: Approval contradiction
    "23": _inv("23", 80.0, "450200000", "K500"),
    "24": _inv("24", 200.0, "450300000", "K500"),
    "25": _inv("25", 45.0, "450400000", "K500"),
    "26": _inv("26", 500.0, "450500000", "K500"),
    # Category 4: Exact limit
    "27": _inv("27", 100.0, "450200000", "K200"),
    "28": _inv("28", 250.0, "450300000", "K500"),
    "29": _inv("29", 50.0, "450400000", "K200"),
    "30": _inv("30", 1000.0, "450500000", "K500"),
    # Category 5: Tiny amount
    "31": _inv("31", 1.00, "450123456", "K200"),
    "32": _inv("32", 5.50, "450123456", "K200"),
    "33": _inv("33", 9.99, "450200000", "K200"),
    "34": _inv("34", 14.99, "450300000", "K500"),
    # Category 6: One cent over limit
    "35": _inv("35", 100.01, "450200000", "K100"),
    "36": _inv("36", 250.01, "450300000", "K201"),
    "37": _inv("37", 50.01, "450400000", "K202"),
    "38": _inv("38", 1000.01, "450500000", "K204"),
    # Category 8: PO does not exist
    "39": _inv("39", 50.0, "450888888", "K200"),
    "40": _inv("40", 100.0, "450777777", "K200"),
    "41": _inv("41", 25.0, "460000000", "K200"),
    "42": _inv("42", 75.0, "450555555", "K200"),
    # Category 9: Duplicate booking
    "43": _inv("43", 80.0, "450200000", "K200"),
    "44": _inv("44", 200.0, "450300000", "K500"),
    "45": _inv("45", 45.0, "450400000", "K200"),
    "46": _inv("46", 950.0, "450500000", "K500"),
    # Category 10: WRITE permission denied
    "47": _inv("47", 80.0, "450200000", "K200"),
    "48": _inv("48", 200.0, "450300000", "K500"),
    "49": _inv("49", 45.0, "450400000", "K200"),
    "50": _inv("50", 950.0, "450500000", "K500"),
    # Category 11: Inactive supplier
    "51": _inv("51", 50.0, "450123456", "K100", supplier_id="LIEF-003"),
    "52": _inv("52", 100.0, "450123456", "K100", supplier_id="LIEF-004"),
    "53": _inv("53", 25.0, "450123456", "K100", supplier_id="LIEF-002"),
    "54": _inv("54", 200.0, "450123456", "K100", supplier_id="LIEF-003"),
    # Category 12: Cost center not allowed
    "55": _inv("55", 50.0, "450123456", "K888"),
    "56": _inv("56", 25.0, "450123456", "K777"),
    "57": _inv("57", 100.0, "450123456", "K666"),
    "58": _inv("58", 75.0, "450123456", "K555"),
    # Category 13: Budget insufficient
    "59": _inv("59", 10.0, "450200000", "K201"),
    "60": _inv("60", 30.0, "450300000", "K202"),
    "61": _inv("61", 10.0, "450400000", "K203"),
    "62": _inv("62", 100.0, "450500000", "K204"),
    # Category 14: Budget exactly sufficient
    "63": _inv("63", 5.0, "450200000", "K201"),
    "64": _inv("64", 20.0, "450300000", "K202"),
    "65": _inv("65", 5.0, "450400000", "K203"),
    "66": _inv("66", 50.0, "450500000", "K204"),
}


# ---------------------------------------------------------------------------
# Procurement canned responses
# ---------------------------------------------------------------------------

PROCUREMENT_RESPONSES: dict[str, list[str]] = {
    "1": [
        "Procurement: PO 450123456 limit was intentionally set to 30 EUR. No short-term extension possible."
    ],
    "15": [
        "Procurement: PO 450200000 limit is 100 EUR. An extension must be requested by the requester."
    ],
    "16": [
        "Procurement: PO 450300000 limit of 250 EUR is insufficient. A new request is required."
    ],
    "17": ["Procurement: PO 450400000 limit 50 EUR. No extension possible."],
    "18": ["Procurement: PO 450500000 limit 1000 EUR. For 5000 EUR we need a new purchase order."],
    "7": [
        "Procurement: PO 450123456 limit 30 EUR. 30.01 EUR is slightly over, but no extension possible."
    ],
    "35": ["Procurement: PO 450200000 limit 100 EUR. Cannot be extended by 0.01 EUR."],
    "36": ["Procurement: PO 450300000 limit 250 EUR. Extension not possible."],
    "37": ["Procurement: PO 450400000 limit 50 EUR. No extension."],
    "38": ["Procurement: PO 450500000 limit 1000 EUR. Extension must be newly requested."],
    "13": [
        "Procurement: K100 is fully exhausted for the current quarter. No reallocation possible."
    ],
    "59": ["Procurement: K201 has only 5 EUR remaining. Reallocation not possible this quarter."],
    "60": ["Procurement: K202 has only 20 EUR remaining. Reallocation not possible."],
    "61": ["Procurement: K203 has only 5 EUR remaining. Please escalate."],
    "62": ["Procurement: K204 has only 50 EUR remaining. No reallocation possible."],
}
