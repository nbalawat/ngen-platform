"""Response strategies for the mock LLM provider."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from ngen_mock_llm.models import (
    ChatCompletionRequest,
    ChatMessage,
    FunctionCall,
    ToolCall,
)


class ResponseStrategy(ABC):
    """Base class for mock LLM response strategies."""

    @abstractmethod
    def generate(self, request: ChatCompletionRequest) -> ChatMessage:
        """Generate a response message for the given request."""


class CannedStrategy(ResponseStrategy):
    """Returns a fixed response regardless of input."""

    def __init__(self, response: str = "This is a mock response.") -> None:
        self._response = response

    def generate(self, request: ChatCompletionRequest) -> ChatMessage:
        return ChatMessage(role="assistant", content=self._response)


class EchoStrategy(ResponseStrategy):
    """Echoes back the last user message."""

    def __init__(self, prefix: str = "Echo: ") -> None:
        self._prefix = prefix

    def generate(self, request: ChatCompletionRequest) -> ChatMessage:
        last_user_msg = ""
        for msg in reversed(request.messages):
            if msg.role == "user" and msg.content:
                last_user_msg = msg.content
                break
        return ChatMessage(
            role="assistant",
            content=f"{self._prefix}{last_user_msg}",
        )


class ToolCallStrategy(ResponseStrategy):
    """Generates a tool call response for testing tool use flows."""

    def __init__(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> None:
        self._tool_name = tool_name
        self._arguments = arguments or {}

    def generate(self, request: ChatCompletionRequest) -> ChatMessage:
        return ChatMessage(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(
                    function=FunctionCall(
                        name=self._tool_name,
                        arguments=json.dumps(self._arguments),
                    ),
                )
            ],
        )
