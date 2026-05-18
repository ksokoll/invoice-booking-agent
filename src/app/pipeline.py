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
from typing import TYPE_CHECKING, ClassVar

from opentelemetry import trace

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

if TYPE_CHECKING:
    from app.core.failures import VerificationFailure
    from app.services.llm.client_protocol import LLMClient
    from app.services.tool_base import Tool

logger = get_logger(__name__)
tracer = get_tracer(__name__)

_MAX_ITERATIONS = 10


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
            state: Mutable accumulated state for the current run.
                Fields written by earlier tools (for example
                `invoice_amount_eur` from `get_invoice_data`) are
                read here, and the tool's own `update_state` may
                add further fields.
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

        # --- Pre-Execute Verification (delegated to the tool) ---
        with tracer.start_as_current_span("verification.pre_execute") as verif_span:
            verif_span.set_attribute("tool_name", tool_call.name)
            pre_failure = tool.verify_before(tool_call.params, state, invoice_id)
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
        # The terminal-status decision for escalate_to_human is a genuine
        # Coordinator concern (flow control), not a per-tool concern. It
        # stays here intentionally and is the only tool name the
        # Coordinator still knows by string.
        if tool_call.name == "escalate_to_human":
            span.set_attribute("outcome", "escalated")
            record_tool_call(tool_call.name, "escalated")
            return CoordinatorResult(
                status=AgentStatus.ESCALATED_TO_HUMAN,
                message=raw_result["handoff_message"],
                invoice_id=invoice_id,
            )

        # --- Post-Execute Verification (delegated to the tool) ---
        with tracer.start_as_current_span("verification.post_execute") as verif_span:
            verif_span.set_attribute("tool_name", tool_call.name)
            post_failure = tool.verify_after(tool_call.params, raw_result, state, invoice_id)
            if post_failure is not None:
                verif_span.set_attribute("rule", post_failure.rule)
                verif_span.set_attribute("outcome", "failed")
                record_verification_failure(
                    rule=post_failure.rule,
                    consultable=post_failure.consultable,
                )
                return self._route_failure(post_failure, tool_call, invoice_id)

        tool.update_state(raw_result, state)
        span.set_attribute("outcome", "ok")
        record_tool_call(tool_call.name, "ok")

        return ToolResult(
            tool_call_id=tool_call.id,
            content=json.dumps(tool.compress_result(raw_result, state)),
        )

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

