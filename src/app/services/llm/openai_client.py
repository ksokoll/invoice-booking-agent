"""OpenAI implementation of the LLMClient Protocol."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.core.results import ToolCall, ToolResult
from app.services.llm.client_protocol import LLMResponse


class OpenAIClient:
    """LLMClient implementation backed by the OpenAI Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 1024,
    ) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._messages: list[dict[str, Any]] = []
        self._system_prompt: str = ""
        self._tool_schemas: list[dict[str, Any]] = []

    def start(
        self, system_prompt: str, task: str, tool_schemas: list[dict[str, Any]]
    ) -> LLMResponse:
        self._system_prompt = system_prompt
        self._tool_schemas = [self._convert_schema(s) for s in tool_schemas]
        self._messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]
        return self._call()

    def continue_with_results(self, tool_results: list[ToolResult]) -> LLMResponse:
        for tr in tool_results:
            self._messages.append(
                {"role": "tool", "tool_call_id": tr.tool_call_id, "content": tr.content}
            )
        return self._call()

    def _call(self) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            tools=self._tool_schemas,  # type: ignore[arg-type]
            messages=self._messages,  # type: ignore[arg-type]
        )
        message = response.choices[0].message
        self._messages.append(message.model_dump(exclude_unset=False))
        if not message.tool_calls:
            return LLMResponse(stop_reason="end_turn", text=message.content or "")
        tool_calls = [
            ToolCall(
                id=tc.id,
                name=tc.function.name,  # type: ignore[union-attr]  # only function tools used
                params=json.loads(tc.function.arguments),  # type: ignore[union-attr]  # only function tools used
            )
            for tc in message.tool_calls
        ]
        return LLMResponse(stop_reason="tool_use", tool_calls=tool_calls)

    @staticmethod
    def _convert_schema(anthropic_schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": anthropic_schema["name"],
                "description": anthropic_schema["description"],
                "parameters": anthropic_schema["input_schema"],
            },
        }
