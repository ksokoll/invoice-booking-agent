"""Tool Protocol for the invoice booking agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.services.permission_gate import PermissionLevel


@runtime_checkable
class Tool(Protocol):
    """Structural protocol for all tool implementations."""

    name: str
    description: str
    permission_level: PermissionLevel
    anthropic_schema: ClassVar[dict[str, Any]]  # protocol declares class-level schema

    def execute(self, params: dict[str, Any]) -> dict[str, Any]: ...
