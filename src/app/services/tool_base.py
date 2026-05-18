"""Tool Protocol and DefaultTool base for the invoice booking agent.

Each Tool is self-contained: it knows how to execute itself, which
preconditions to verify, which postconditions to check, which fields
of the WorkflowState it contributes to, and how to compress its
result for the LLM. The Coordinator only dispatches; it does not
encode per-tool semantics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.core.failures import VerificationFailure
    from app.core.workflow_state import WorkflowState
    from app.services.permission_gate import PermissionLevel


@runtime_checkable
class Tool(Protocol):
    """Structural protocol for all tool implementations.

    Lifecycle (called by the Coordinator in this order):
        1. verify_before(params, state, invoice_id)
        2. execute(params)
        3. verify_after(params, result, state, invoice_id)
        4. update_state(result, state)
        5. compress_result(result, state) -> dict for the LLM

    Concrete tools inherit from `DefaultTool` for no-op defaults and
    override only the lifecycle methods that apply to them.
    """

    name: str
    description: str
    permission_level: PermissionLevel
    anthropic_schema: ClassVar[dict[str, Any]]

    def execute(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def verify_before(
        self,
        params: dict[str, Any],
        state: WorkflowState,
        invoice_id: str,
    ) -> VerificationFailure | None: ...

    def verify_after(
        self,
        params: dict[str, Any],
        result: dict[str, Any],
        state: WorkflowState,
        invoice_id: str,
    ) -> VerificationFailure | None: ...

    def update_state(
        self,
        result: dict[str, Any],
        state: WorkflowState,
    ) -> None: ...

    def compress_result(
        self,
        result: dict[str, Any],
        state: WorkflowState,
    ) -> dict[str, Any]: ...


class DefaultTool:
    """Base class providing no-op lifecycle defaults.

    Concrete tools inherit from this class and override only the
    lifecycle methods that apply to them. The defaults preserve the
    raw tool result unchanged, perform no verification, and make no
    state contribution.
    """

    def verify_before(
        self,
        params: dict[str, Any],
        state: WorkflowState,
        invoice_id: str,
    ) -> VerificationFailure | None:
        return None

    def verify_after(
        self,
        params: dict[str, Any],
        result: dict[str, Any],
        state: WorkflowState,
        invoice_id: str,
    ) -> VerificationFailure | None:
        return None

    def update_state(
        self,
        result: dict[str, Any],
        state: WorkflowState,
    ) -> None:
        return None

    def compress_result(
        self,
        result: dict[str, Any],
        state: WorkflowState,
    ) -> dict[str, Any]:
        return result
