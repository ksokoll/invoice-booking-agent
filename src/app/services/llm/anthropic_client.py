"""Anthropic implementation of the LLMClient Protocol."""

from __future__ import annotations

from typing import Any

import anthropic

from app.core.results import ToolCall, ToolResult
from app.services.llm.client_protocol import LLMResponse


class AnthropicClient:
    """LLMClient implementation backed by the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 1024,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._messages: list[dict[str, Any]] = []
        self._system_prompt: str = ""
        self._tool_schemas: list[dict[str, Any]] = []

    def start(
        self, system_prompt: str, task: str, tool_schemas: list[dict[str, Any]]
    ) -> LLMResponse:
        self._system_prompt = system_prompt
        self._tool_schemas = tool_schemas
        self._messages = [{"role": "user", "content": task}]
        return self._call()

    def continue_with_results(self, tool_results: list[ToolResult]) -> LLMResponse:
        anthropic_results = [
            {"type": "tool_result", "tool_use_id": tr.tool_call_id, "content": tr.content}
            for tr in tool_results
        ]
        self._messages.append({"role": "user", "content": anthropic_results})
        return self._call()

    def _call(self) -> LLMResponse:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=self._system_prompt,
            tools=self._tool_schemas,  # type: ignore[arg-type]
            messages=self._messages,  # type: ignore[arg-type]
        )
        self._messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "end_turn":
            text = next(
                (b.text for b in response.content if hasattr(b, "type") and b.type == "text"), ""
            )
            return LLMResponse(stop_reason="end_turn", text=text)
        tool_calls = [
            ToolCall(id=b.id, name=b.name, params=b.input)
            for b in response.content
            if hasattr(b, "type") and b.type == "tool_use"
        ]
        return LLMResponse(stop_reason="tool_use", tool_calls=tool_calls)
