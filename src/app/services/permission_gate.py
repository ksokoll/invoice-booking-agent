"""Permission system for the tool layer.

The gate is a separate architectural layer between the coordinator's
routing decision and actual tool execution. This means the permission
model can be changed without touching any tool implementation.

Design decision: READ is always auto-approved. WRITE requires explicit
approval from the gate.
"""

from __future__ import annotations

from enum import Enum, auto


class PermissionLevel(Enum):
    """Escalating risk levels for tool operations.

    READ:  No side effects. Always auto-approved.
    WRITE: Persists state. Requires gate approval.
    """

    READ = auto()
    WRITE = auto()


class PermissionDeniedError(Exception):
    """Raised when a tool call is blocked by the permission gate."""


class PermissionGate:
    """Evaluates whether a tool is allowed to execute.

    Args:
        allow_write: If True, WRITE-level tools are approved automatically.
    """

    def __init__(self, allow_write: bool = True) -> None:
        """Initialize the gate with a write-permission policy.

        Args:
            allow_write: If True, WRITE-level tools are approved
                automatically. Defaults to True for development and
                harness convenience. A production deployment should
                set this to False explicitly and enable WRITE only
                for authenticated or authorized contexts.
        """
        self._allow_write = allow_write

    def check(self, tool_name: str, level: PermissionLevel) -> None:
        """Verify that a tool is permitted to execute.

        Args:
            tool_name: Name of the tool requesting execution.
            level: The permission level declared by that tool.

        Raises:
            PermissionDeniedError: If the gate blocks the operation.
        """
        if level == PermissionLevel.READ:
            return

        if level == PermissionLevel.WRITE and not self._allow_write:
            raise PermissionDeniedError(
                f"Tool '{tool_name}' requires WRITE permission, which is not"
                " granted in this context."
            )
