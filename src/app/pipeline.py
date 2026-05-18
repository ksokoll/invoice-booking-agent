"""Coordinator: the main agent loop for invoice booking.

Architecture:
    The coordinator depends only on the LLMClient Protocol.
    It never imports anthropic or openai directly.

    Loop per iteration:
        1. LLMClient.start() or continue_with_results() -> LLMResponse
        2. stop_reason == 'end_turn' -> extract final status, exit
        3. stop_reason == 'tool_use' -> for each ToolCall:
               a. PermissionGate.check()
               b. Tool.execute()
               c. VerificationEngine checks (not_found, limit, approval, duplicate)
               d. If verification fails -> route based on consultability
        4. Collect ToolResults -> LLMClient.continue_with_results()
        5. Repeat until terminal state or max_iterations
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from opentelemetry import trace

from app.core.failures import VerificationFailure
from app.core.results import CoordinatorResult, ToolCall, ToolResult
from app.core.statuses import AgentStatus
from app.core.workflow_state import WorkflowState
from app.prompts import SYSTEM_PROMPT
from app.services.observability import (
    get_logger,
    get_tracer,
    new_correlation_id,
    record_iteration,
    record_run_finished,
    record_run_started,
    record_tool_call,
    record_verification_failure,
    set_correlation_id,
)
from app.services.observability.decorators import traced
from app.services.permission_gate import PermissionDeniedError, PermissionGate
from app.verification.rules import (
    APPROVAL_THRESHOLD_EUR,
    check_approval_consistent,
    check_approval_required,
    check_budget_sufficient,
    check_cost_center_allowed,
    check_limit_not_exceeded,
    check_not_already_booked,
    check_not_found,
    check_supplier_active,
)

if TYPE_CHECKING:
    from app.services.llm.client_protocol import LLMClient
    from app.services.tool_base import Tool

logger = get_logger(__name__)
tracer = get_tracer(__name__)

_MAX_ITERATIONS = 10
# Consultation budget per invoice. Lifecycle-separated from the
# per-failure consultable flag on VerificationFailure (classification
# vs enforcement; see ADR-006).
_MAX_CONSULTATIONS_PER_INVOICE = 3


class Coordinator:
    """Runs the invoice booking agent loop against any LLM provider.

    Args:
        client: Any object satisfying the LLMClient Protocol.
        tools: List of Tool instances available to the agent.
        gate: PermissionGate that approves or blocks tool execution.
        booked_invoices: Shared set of already-booked invoice IDs.
                         Injected so the duplicate check sees the same state
                         as BookingTool.
    """

    def __init__(
        self,
        client: LLMClient,
        tools: list[Tool],
        gate: PermissionGate,
        booked_invoices: set[str] | None = None,
    ) -> None:
        self._client = client
        self._registry: dict[str, Tool] = {t.name: t for t in tools}
        self._gate = gate
        self._tool_schemas = [t.anthropic_schema for t in tools]
        self._booked_invoices = booked_invoices or set()
        self._system_prompt = SYSTEM_PROMPT.prompt

    @traced("coordinator.run", attributes_from_args=("invoice_id",))
    def run(self, invoice_id: str, task: str) -> CoordinatorResult:
        """Execute the full booking flow for one invoice."""
        cid = new_correlation_id()
        set_correlation_id(cid)

        state = WorkflowState()
        record_run_started()

        run_span = trace.get_current_span()
        run_span.set_attribute("correlation_id", cid)

        logger.info(
            "coordinator.run.start",
            invoice_id=invoice_id,
            task=task,
        )

        # Initial LLM call: no tool results yet, so we use start() instead of
        # continue_with_results(). Tracing is covered by the parent
        # coordinator.run span. The single-turn protocol is documented in ADR-003.
        response = self._client.start(
            system_prompt=self._system_prompt,
            task=task,
            tool_schemas=self._tool_schemas,
        )
        logger.info(
            "coordinator.initial_call",
            stop_reason=response.stop_reason,
            tool_calls_count=len(response.tool_calls),
        )

        for iteration in range(_MAX_ITERATIONS):
            with tracer.start_as_current_span("coordinator.iteration") as iter_span:
                iter_span.set_attribute("iteration", iteration + 1)
                iter_span.set_attribute("stop_reason", response.stop_reason)

                logger.info(
                    "coordinator.iteration",
                    iteration=iteration + 1,
                    stop_reason=response.stop_reason,
                )

                if response.stop_reason == "end_turn":
                    status = (
                        AgentStatus.BOOKED
                        if state.booked
                        else AgentStatus.BLOCKED_AGENT_ABANDONED
                    )
                    result = CoordinatorResult(
                        status=status,
                        message=response.text,
                        invoice_id=invoice_id,
                    )
                    run_span.set_attribute("status", status.value)
                    record_run_finished(status.value)
                    record_iteration(iteration + 1)
                    return result

                tool_results: list[ToolResult] = []

                for tool_call in response.tool_calls:
                    outcome = self._execute_tool_call(tool_call, state, invoice_id)
                    if isinstance(outcome, CoordinatorResult):
                        run_span.set_attribute("status", outcome.status.value)
                        record_run_finished(outcome.status.value)
                        record_iteration(iteration + 1)
                        return outcome
                    tool_results.append(outcome)

                response = self._client.continue_with_results(tool_results)

        result = CoordinatorResult(
            status=AgentStatus.BLOCKED_MAX_ITERATIONS,
            message=f"Agent reached maximum iterations ({_MAX_ITERATIONS}) without completing.",
            invoice_id=invoice_id,
        )
        run_span.set_attribute("status", result.status.value)
        record_run_finished(result.status.value)
        record_iteration(_MAX_ITERATIONS)
        return result

    @traced("tool.execute", attributes_from_args=("invoice_id",))
    def _execute_tool_call(
        self,
        tool_call: ToolCall,
        state: WorkflowState,
        invoice_id: str,
    ) -> ToolResult | CoordinatorResult:
        """Run one tool call through the gate, execute, and verify.

        The method consults the tool registry, enforces the permission
        gate, runs pre-execute verification, invokes the tool itself,
        runs post-execute verification, updates accumulated state, and
        records metrics and logs along the way.

        Args:
            tool_call: The LLM-issued tool call to execute.
            state: Mutable accumulated state for the current run. Keys
                written by earlier tools (for example
                `invoice_amount_eur` from `get_invoice_data`) are read
                here, and this method may add further keys via
                `_update_state`.
            invoice_id: The invoice being booked. Flows into span
                attributes and failure messages.

        Returns:
            A `ToolResult` if the tool executed successfully (this is
            the normal case; the result is handed back to the LLM in
            the next iteration). A `CoordinatorResult` when execution
            terminates the run early: on permission denial, on a
            non-consultable verification failure, or on an explicit
            escalation from the `escalate_to_human` tool.
        """
        span = trace.get_current_span()
        span.set_attribute("tool_name", tool_call.name)

        logger.info(
            "tool.execute",
            tool_name=tool_call.name,
            params=tool_call.params,
        )

        tool = self._registry.get(tool_call.name)
        if tool is None:
            record_tool_call(tool_call.name, "unknown")
            return ToolResult(
                tool_call_id=tool_call.id,
                content=json.dumps({"error": f"Unknown tool: {tool_call.name}"}),
            )

        # --- Permission Gate ---
        try:
            self._gate.check(tool_call.name, tool.permission_level)
        except PermissionDeniedError as exc:
            span.set_attribute("outcome", "permission_denied")
            record_tool_call(tool_call.name, "permission_denied")
            return CoordinatorResult(
                status=AgentStatus.BLOCKED_PERMISSION_DENIED,
                message=str(exc),
                invoice_id=invoice_id,
            )

        # --- Pre-Execute Verification ---
        # Dispatch in two layers during the lifecycle migration: the tool's
        # own verify_before fires first; if it returns None we fall back to
        # the Coordinator's legacy branches for tools not yet migrated.
        with tracer.start_as_current_span("verification.pre_execute") as verif_span:
            verif_span.set_attribute("tool_name", tool_call.name)
            pre_failure = tool.verify_before(
                tool_call.params, state, invoice_id
            ) or self._pre_execute_verify(tool_call, state, invoice_id)
            if pre_failure is not None:
                verif_span.set_attribute("rule", pre_failure.rule)
                verif_span.set_attribute("outcome", "failed")
                record_verification_failure(
                    rule=pre_failure.rule,
                    consultable=pre_failure.consultable,
                )
                return self._route_failure(pre_failure, tool_call, invoice_id)

        # --- Tool Execution ---
        raw_result = tool.execute(tool_call.params)
        logger.info(
            "tool.result",
            tool_name=tool_call.name,
            result=raw_result,
        )

        # --- Escalation hook ---
        if tool_call.name == "escalate_to_human":
            span.set_attribute("outcome", "escalated")
            record_tool_call(tool_call.name, "escalated")
            return CoordinatorResult(
                status=AgentStatus.ESCALATED_TO_HUMAN,
                message=raw_result["handoff_message"],
                invoice_id=invoice_id,
            )

        # --- Post-Execute Verification ---
        # Same two-layer dispatch as for pre-execute.
        with tracer.start_as_current_span("verification.post_execute") as verif_span:
            verif_span.set_attribute("tool_name", tool_call.name)
            post_failure = tool.verify_after(
                tool_call.params, raw_result, state, invoice_id
            ) or self._post_execute_verify(tool_call, raw_result, state, invoice_id)
            if post_failure is not None:
                verif_span.set_attribute("rule", post_failure.rule)
                verif_span.set_attribute("outcome", "failed")
                record_verification_failure(
                    rule=post_failure.rule,
                    consultable=post_failure.consultable,
                )
                return self._route_failure(post_failure, tool_call, invoice_id)

        # --- Increment consultation counter ---
        if tool_call.name == "consult_procurement":
            state.consultations_used += 1

        # State update: tool-side first (no-op for non-migrated tools), then
        # Coordinator's legacy branches for the tools still living here.
        tool.update_state(raw_result, state)
        self._update_state(tool_call.name, raw_result, state)
        span.set_attribute("outcome", "ok")
        record_tool_call(tool_call.name, "ok")

        # Compression: identity check distinguishes migrated tools (which
        # return a new dict) from non-migrated tools (DefaultTool returns
        # the raw_result reference unchanged).
        compressed = tool.compress_result(raw_result, state)
        if compressed is raw_result:
            content = self._compress_tool_result(tool_call.name, raw_result, state)
        else:
            content = json.dumps(compressed)
        return ToolResult(tool_call_id=tool_call.id, content=content)

    # Tools still compressed via the legacy Coordinator path. Entries are
    # removed as each tool implements compress_result in its own class.
    _COMPRESSIBLE_TOOLS: frozenset[str] = frozenset(
        {
            "get_supplier_rules",
            "get_po_limit",
            "get_budget",
        }
    )

    def _compress_tool_result(
        self,
        tool_name: str,
        raw_result: dict[str, Any],
        state: WorkflowState,
    ) -> str:
        """Return the LLM-facing payload for a tool result.

        Read-tool results can be bulky (full invoice records,
        supplier rules, PO limits). Sending them verbatim back into
        the LLM context wastes tokens and tends to confuse the
        model, because the same fields reappear on every iteration.
        The Coordinator already materialises the relevant fields
        into `state`, so the LLM does not need to see the raw
        payload a second time.

        For tools in `_COMPRESSIBLE_TOOLS` whose lookup succeeded
        (`found` is truthy), this method replaces the full payload
        with a small pointer object that names the tool, marks the
        data as materialised in state, and embeds a short summary of
        the key fields from state. All other tool results (write
        tools, not-found lookups, and any tool not in
        `_COMPRESSIBLE_TOOLS`) pass through unchanged.

        Args:
            tool_name: The tool whose result is being compressed.
            raw_result: The tool's full result dict.
            state: The accumulated state for this run, used to pull
                the fields that go into the summary.

        Returns:
            A JSON string that the Coordinator places on the outgoing
            `ToolResult`. Either the pointer object (for compressed
            read-tool results) or a direct dump of `raw_result`.
        """
        if tool_name not in self._COMPRESSIBLE_TOOLS:
            return json.dumps(raw_result)

        if not raw_result.get("found", True):
            return json.dumps(raw_result)

        pointer = {
            "status": "materialised_in_state",
            "tool": tool_name,
            "summary": self._summarise_for_llm(tool_name, state),
        }
        return json.dumps(pointer)

    def _summarise_for_llm(
        self,
        tool_name: str,
        state: WorkflowState,
    ) -> dict[str, Any]:
        """Build a short summary of the materialised state for one tool."""
        # get_invoice_data moved to InvoiceTool.compress_result.
        if tool_name == "get_supplier_rules":
            return {
                "approval_threshold_eur": state.supplier_approval_threshold_eur,
            }
        if tool_name == "get_po_limit":
            return {"limit_eur": state.po_limit_eur}
        if tool_name == "get_budget":
            return {"remaining_eur": state.budget_remaining_eur}
        return {}

    _STATUS_MAP: ClassVar[dict[str, AgentStatus]] = {
        "not_found": AgentStatus.BLOCKED_NOT_FOUND,
        "not_already_booked": AgentStatus.BLOCKED_ALREADY_BOOKED,
        "approval_consistent": AgentStatus.BLOCKED_CONTRADICTION,
        "limit_not_exceeded": AgentStatus.BLOCKED_LIMIT_EXCEEDED,
        "supplier_active": AgentStatus.BLOCKED_SUPPLIER_INACTIVE,
        "cost_center_allowed": AgentStatus.BLOCKED_COST_CENTER_NOT_ALLOWED,
        "budget_sufficient": AgentStatus.BLOCKED_BUDGET_INSUFFICIENT,
        "missing_invoice_state": AgentStatus.BLOCKED_MISSING_INVOICE_STATE,
        "amount_tampering": AgentStatus.BLOCKED_AMOUNT_TAMPERING,
        "approval_required": AgentStatus.BLOCKED_APPROVAL_MISSING,
        "missing_po_data": AgentStatus.BLOCKED_MISSING_PO_DATA,
        "consultation_limit_exceeded": AgentStatus.BLOCKED_AGENT_ABANDONED,
    }

    def _failure_to_result(
        self,
        failure: VerificationFailure,
        invoice_id: str,
    ) -> CoordinatorResult:
        """Convert a VerificationFailure to a CoordinatorResult.

        Raises:
            KeyError: If failure.rule is not in _STATUS_MAP. This
                indicates a programming error: a new verification rule
                was added without updating the status mapping.
        """
        return CoordinatorResult(
            status=self._STATUS_MAP[failure.rule],
            message=failure.reason,
            invoice_id=invoice_id,
        )

    def _route_failure(
        self,
        failure: VerificationFailure,
        tool_call: ToolCall,
        invoice_id: str,
    ) -> ToolResult | CoordinatorResult:
        """Route a verification failure based on its consultability.

        Each `VerificationFailure` carries a `consultable` flag (see
        ADR-006) that partitions rules into two classes. Consultable
        failures are returned to the LLM as a tool-error payload so
        the agent can call `consult_procurement` and potentially
        recover; the run continues. Hard failures terminate the run
        with a mapped `CoordinatorResult` status and never reach the
        LLM again.

        Args:
            failure: The `VerificationFailure` produced by either
                the pre-execute or the post-execute verify step.
            tool_call: The tool call whose execution triggered the
                failure. Needed so the `ToolResult` returned for
                consultable failures can be correlated with the
                original call id.
            invoice_id: The invoice being booked. Surfaced in the
                terminal `CoordinatorResult` when the failure is
                hard.

        Returns:
            A `ToolResult` carrying a consultable-failure payload
            when the rule is consultable, or a terminal
            `CoordinatorResult` when the rule is hard.
        """
        if failure.consultable:
            payload = {
                "verification_failed": True,
                "rule": failure.rule,
                "reason": failure.reason,
                "consultable": True,
                "guidance": (
                    "This failure may be resolvable by consulting the "
                    "Procurement team. You may call consult_procurement to ask, "
                    "but you must re-verify against SAP afterwards. If "
                    "consultation does not help, call escalate_to_human."
                ),
            }
            return ToolResult(
                tool_call_id=tool_call.id,
                content=json.dumps(payload),
            )
        return self._failure_to_result(failure, invoice_id)

    def _pre_execute_verify(
        self,
        tool_call: ToolCall,
        state: WorkflowState,
        invoice_id: str,
    ) -> Any:
        """Run checks that must fire before the tool executes.

        Pre-execute checks guard against three categories:

        1. Budgeted resources: `consult_procurement` has a per-
           invoice limit (`_MAX_CONSULTATIONS_PER_INVOICE`). Once
           reached, further consultations are refused as a hard
           failure so the agent must escalate.
        2. Coordinator-managed parameters: `request_approval` needs
           a recipient. The recipient is deterministic from the
           prior `get_po_limit` call (see ADR-005). If that call
           has not been made, the tool call is refused; otherwise
           the recipient is injected into the tool call params.
        3. Confused-deputy guards on `book_invoice`: the invoice
           amount must have been fetched (no booking on phantom
           state), the LLM-supplied amount must match the recorded
           amount (no tampering), and the invoice must not already
           be booked; above the approval threshold, approval must
           have been recorded.

        Args:
            tool_call: The tool call about to execute. The method
                may mutate its `params` dict for the
                Coordinator-managed-parameter case.
            state: Accumulated state for this run. Used for every
                check above.
            invoice_id: The invoice being booked; surfaced in
                failure reasons.

        Returns:
            `None` when the tool call is allowed to proceed. A
            `VerificationFailure` when a guard fires; the rule name
            identifies which guard.
        """
        if tool_call.name == "consult_procurement":
            used = state.consultations_used
            if used >= _MAX_CONSULTATIONS_PER_INVOICE:
                return VerificationFailure(
                    rule="consultation_limit_exceeded",
                    reason=(
                        f"Maximum {_MAX_CONSULTATIONS_PER_INVOICE} consultations "
                        f"per invoice reached for invoice {invoice_id}. "
                        f"Escalate to human instead."
                    ),
                    consultable=False,
                )
            return None

        if tool_call.name == "request_approval":
            state_recipient = state.po_responsible_person
            if state_recipient is None:
                return VerificationFailure(
                    rule="missing_po_data",
                    reason=(
                        f"Cannot request approval for invoice {invoice_id}: "
                        f"get_po_limit has not been called yet, so the "
                        f"authoritative recipient is unknown. The agent "
                        f"must call get_po_limit before request_approval."
                    ),
                    consultable=False,
                )
            # Coordinator-managed parameter injection per ADR-005:
            # the recipient is determined by the system from authoritative
            # state, never by the LLM. ToolCall.params is the documented
            # extension point for this injection (mutable dict on a frozen
            # dataclass).
            tool_call.params["recipient"] = state_recipient
            return None

        # Early Exit if "book invoice" wasn't chosen
        if tool_call.name != "book_invoice":
            return None

        params = tool_call.params

        state_amount = state.invoice_amount_eur
        if state_amount is None:
            return VerificationFailure(
                rule="missing_invoice_state",
                reason=(
                    f"Cannot book invoice {invoice_id}: invoice data was never "
                    f"fetched. The agent must call get_invoice_data before "
                    f"book_invoice."
                ),
                consultable=False,
            )

        params_amount = params.get("amount_eur")
        if params_amount is not None and abs(params_amount - state_amount) > 0.001:
            return VerificationFailure(
                rule="amount_tampering",
                reason=(
                    f"Invoice {invoice_id}: book_invoice was called with "
                    f"amount_eur={params_amount} but the authoritative amount "
                    f"from get_invoice_data is {state_amount}. Refusing to book."
                ),
                consultable=False,
            )

        authoritative_amount = state_amount

        failure = check_not_already_booked(
            invoice_id=invoice_id,
            booked_invoices=self._booked_invoices,
        )
        if failure:
            return failure

        failure = check_approval_required(
            invoice_id=invoice_id,
            amount_eur=authoritative_amount,
            approval_received=bool(state.approvals_received),
            threshold_eur=(
                state.supplier_approval_threshold_eur
                if state.supplier_approval_threshold_eur is not None
                else APPROVAL_THRESHOLD_EUR
            ),
        )
        if failure:
            return failure

        return None

    def _post_execute_verify(
        self,
        tool_call: ToolCall,
        result: dict[str, Any],
        state: WorkflowState,
        invoice_id: str,
    ) -> Any:
        """Run checks that require the tool result.

        Post-execute checks apply the pure verification rules from
        `app.verification.rules` to the combination of the tool
        result and the accumulated state. The checks are ordered:

        1. `not_found` for the four SAP lookup tools.
        2. `limit_not_exceeded` whenever both amount and limit are
           known; the check fires from either direction depending on
           which of `get_po_limit` and `get_invoice_data` was
           called first.
        3. Supplier rules: `supplier_active` and, when the invoice
           cost center is already known, `cost_center_allowed`.
        4. `budget_sufficient` when both amount and budget are
           known.
        5. `approval_consistent` on `request_approval` results.
           This check also records the recipient in
           `state.approvals_received` when the approval was
           granted, so the subsequent `approval_required` check on
           `book_invoice` can see it.

        Args:
            tool_call: The tool call that just executed.
            result: The raw result dict returned by the tool.
            state: Accumulated state; read for cross-tool
                invariants and updated with the approval list when
                appropriate.
            invoice_id: The invoice being booked; surfaced in
                failure reasons.

        Returns:
            `None` when every applicable check passed. The first
            `VerificationFailure` encountered otherwise.
        """
        tool_name = tool_call.name
        params = tool_call.params

        # 1. Not-found check (still here for tools not yet migrated to the
        # per-tool lifecycle; migrated tools handle this in verify_after).
        if tool_name in (
            "get_po_limit",
            "get_supplier_rules",
            "get_budget",
        ):
            failure = check_not_found(tool_name, result)
            if failure:
                return failure

        # 2. Limit check (still here for get_po_limit, which has not yet
        # been migrated; get_invoice_data's branch moved into InvoiceTool).
        if (
            tool_name == "get_po_limit"
            and result.get("found")
            and state.invoice_amount_eur is not None
        ):
            failure = check_limit_not_exceeded(
                amount_eur=state.invoice_amount_eur,
                limit_eur=result["limit_eur"],
                invoice_id=state.invoice_id if state.invoice_id is not None else invoice_id,
                po_number=result["po_number"],
            )
            if failure:
                return failure

        # 3. Supplier-rules checks.
        if tool_name == "get_supplier_rules" and result.get("found"):
            failure = check_supplier_active(
                supplier_id=result["supplier_id"],
                active=result["active"],
            )
            if failure:
                return failure
            if state.invoice_cost_center is not None:
                failure = check_cost_center_allowed(
                    cost_center=state.invoice_cost_center,
                    allowed_cost_centers=result["allowed_cost_centers"],
                    invoice_id=invoice_id,
                )
                if failure:
                    return failure

        # 4. Budget check.
        if (
            tool_name == "get_budget"
            and result.get("found")
            and state.invoice_amount_eur is not None
        ):
            failure = check_budget_sufficient(
                amount_eur=state.invoice_amount_eur,
                remaining_budget_eur=result["remaining_eur"],
                cost_center=result["cost_center"],
                invoice_id=invoice_id,
            )
            if failure:
                return failure

        # 5. Approval contradiction check.
        if tool_name == "request_approval":
            if state.invoice_amount_eur is not None and state.po_limit_eur is not None:
                failure = check_approval_consistent(
                    approved=result["approved"],
                    stated_reason=result["reason"],
                    expected_limit_eur=state.po_limit_eur,
                    actual_amount_eur=state.invoice_amount_eur,
                    recipient=params["recipient"],
                )
                if failure:
                    return failure
            if result.get("approved"):
                state.approvals_received.append(params["recipient"])

        return None

    def _update_state(
        self,
        tool_name: str,
        result: dict[str, Any],
        state: WorkflowState,
    ) -> None:
        """Update accumulated state after a successful tool call.

        Each successful read tool contributes a known set of fields
        to `state`. Subsequent verification checks and the
        `_summarise_for_llm` helper read from those fields, so the
        contract is stable per tool:

        - `get_invoice_data` (found): writes `invoice_id`,
          `invoice_amount_eur`, `invoice_po_number`,
          `invoice_contact_person`, `invoice_supplier_id`,
          `invoice_cost_center`.
        - `get_supplier_rules` (found): writes
          `supplier_approval_threshold_eur`.
        - `get_budget` (found): writes `budget_remaining_eur`.
        - `get_po_limit` (found): writes `po_limit_eur` and
          `po_responsible_person`. The latter is the Coordinator-
          managed recipient for `request_approval` (see ADR-005).
        - `book_invoice` (booked): writes `booked=True`, which
          determines the terminal status in `run`.

        Args:
            tool_name: The tool whose result is being folded into
                state.
            result: The tool's raw result dict.
            state: The mutable WorkflowState for this run.
        """
        # get_invoice_data moved to InvoiceTool.update_state.

        if tool_name == "get_supplier_rules" and result.get("found"):
            state.supplier_approval_threshold_eur = result["approval_threshold_eur"]

        if tool_name == "get_budget" and result.get("found"):
            state.budget_remaining_eur = result["remaining_eur"]

        if tool_name == "get_po_limit" and result.get("found"):
            state.po_limit_eur = result["limit_eur"]
            state.po_responsible_person = result["responsible_person"]

        if tool_name == "book_invoice" and result.get("booked"):
            state.booked = True
