"""Result and call DTOs for the Coordinator interface.

These types are the contract between the Coordinator and its
callers. ToolCall and ToolResult are also used by the LLM client
protocol.
"""

from dataclasses import dataclass
from typing import Any

from app.core.statuses import AgentStatus


@dataclass(frozen=True)
class ToolCall:
    """A single tool invocation as requested by the LLM."""

    id: str
    name: str
    params: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """The result of executing one ToolCall."""

    tool_call_id: str
    content: str


@dataclass(frozen=True)
class CoordinatorResult:
    """Terminal output of one Coordinator run."""

    status: AgentStatus
    message: str
    invoice_id: str
