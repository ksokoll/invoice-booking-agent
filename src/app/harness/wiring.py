"""Coordinator wiring for the test harness."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from app.approval.approval_tool import ApprovalTool
from app.approval.consult_procurement_tool import ConsultProcurementTool
from app.booking.booking_tool import BookingTool
from app.booking.escalate_to_human_tool import EscalateToHumanTool
from app.intake.invoice_tool import InvoiceTool
from app.intake.supplier_rules_tool import SupplierRulesTool
from app.pipeline import Coordinator
from app.services.permission_gate import PermissionGate
from app.services.sap_data import (
    BUDGET_RECORDS,
    INVOICES,
    PO_RECORDS,
    PROCUREMENT_RESPONSES,
    SUPPLIER_RULES,
)
from app.verification.budget_tool import BudgetTool
from app.verification.po_tool import POTool

if TYPE_CHECKING:
    from app.harness.scenarios import Category, Variant
    from app.services.llm.client_protocol import LLMClient
    from app.services.tool_base import Tool


def build_llm_client() -> LLMClient:
    """Instantiate the configured LLM provider client."""
    provider = os.environ.get("PROVIDER", "openai").lower()

    if provider == "anthropic":
        from app.services.llm.anthropic_client import AnthropicClient

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set.")
        return AnthropicClient(api_key=api_key)

    if provider == "openai":
        from app.services.llm.openai_client import OpenAIClient

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set.")
        return OpenAIClient(api_key=api_key)

    raise ValueError(f"Unknown provider '{provider}'. Choose 'anthropic' or 'openai'.")


def build_coordinator_for_variant(
    category: Category,
    variant: Variant,
) -> Coordinator:
    """Build a fresh Coordinator for one (category, variant) pair.

    Each variant gets its own booked_invoices set, its own gate,
    its own LLMClient instance, and its own tool list. No shared
    mutable state across variants.
    """
    booked_invoices: set[str] = set(variant.pre_booked)
    gate = PermissionGate(allow_write=category.allow_write)
    client = build_llm_client()

    tools: list[Tool] = [
        InvoiceTool(data=INVOICES),
        SupplierRulesTool(data=SUPPLIER_RULES),
        BudgetTool(data=BUDGET_RECORDS),
        POTool(data=PO_RECORDS),
        ApprovalTool(approval_responses=category.approval_responses),
        BookingTool(booked_invoices=booked_invoices),
    ]

    if not category.minimal_tools:
        tools.append(ConsultProcurementTool(responses=PROCUREMENT_RESPONSES))
        tools.append(EscalateToHumanTool())

    return Coordinator(
        client=client,
        tools=tools,
        gate=gate,
        booked_invoices=booked_invoices,
    )
