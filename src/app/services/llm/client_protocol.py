"""Provider-agnostic LLM client contract.

The Coordinator talks only to this Protocol. Provider-specific
message formats are an implementation detail of each concrete client.

Design decision -- clients own the message history:
    Each client tracks its own internal conversation state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.core.results import ToolCall, ToolResult


@dataclass(frozen=True)
class LLMResponse:
    """Normalized response from any LLM provider."""

    stop_reason: Literal["tool_use", "end_turn"]
    tool_calls: list[ToolCall] = field(default_factory=list)
    text: str = ""


@runtime_checkable
class LLMClient(Protocol):
    """Structural protocol for any LLM provider client."""

    def start(
        self,
        system_prompt: str,
        task: str,
        tool_schemas: list[dict[str, Any]],
    ) -> LLMResponse: ...

    def continue_with_results(
        self,
        tool_results: list[ToolResult],
    ) -> LLMResponse: ...
