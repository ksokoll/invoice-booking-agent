"""Shared test doubles used across the unit test suite."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.results import ToolResult
    from app.services.llm.client_protocol import LLMResponse


class FakeLLMClient:
    """LLM test double that returns a preconfigured sequence of responses.

    Records every list of ToolResults passed to continue_with_results so
    tests can verify the payloads the Coordinator sends back to the LLM.
    """

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = iter(responses)
        self.received_tool_results: list[list[ToolResult]] = []

    def start(
        self,
        system_prompt: str,
        task: str,
        tool_schemas: list[dict],
    ) -> LLMResponse:
        return next(self._responses)

    def continue_with_results(self, tool_results: list[ToolResult]) -> LLMResponse:
        self.received_tool_results.append(list(tool_results))
        return next(self._responses)
