"""Tests for the mock LLM data models."""

from __future__ import annotations

from ngen_mock_llm.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    FunctionCall,
    ToolCall,
    Usage,
)


class TestChatMessage:
    def test_simple_user_message(self):
        msg = ChatMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_calls is None

    def test_assistant_with_tool_calls(self):
        msg = ChatMessage(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(
                    function=FunctionCall(
                        name="search", arguments='{"q": "test"}'
                    )
                )
            ],
        )
        assert msg.content is None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].function.name == "search"

    def test_tool_result_message(self):
        msg = ChatMessage(
            role="tool",
            content="result data",
            tool_call_id="call_abc",
        )
        assert msg.tool_call_id == "call_abc"


class TestToolCall:
    def test_auto_generated_id(self):
        tc = ToolCall(
            function=FunctionCall(name="f", arguments="{}")
        )
        assert tc.id.startswith("call_")
        assert tc.type == "function"

    def test_explicit_id(self):
        tc = ToolCall(
            id="call_custom",
            function=FunctionCall(name="f", arguments="{}"),
        )
        assert tc.id == "call_custom"


class TestChatCompletionRequest:
    def test_minimal_request(self):
        req = ChatCompletionRequest(
            model="gpt-4",
            messages=[ChatMessage(role="user", content="Hi")],
        )
        assert req.model == "gpt-4"
        assert req.temperature == 1.0
        assert req.stream is False
        assert req.tools is None

    def test_request_with_tools(self):
        req = ChatCompletionRequest(
            model="gpt-4",
            messages=[ChatMessage(role="user", content="Hi")],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "parameters": {},
                    },
                }
            ],
        )
        assert len(req.tools) == 1


class TestChatCompletionResponse:
    def test_auto_generated_fields(self):
        resp = ChatCompletionResponse(
            model="mock",
            choices=[
                Choice(
                    message=ChatMessage(
                        role="assistant", content="Hi"
                    )
                )
            ],
            usage=Usage(
                prompt_tokens=5,
                completion_tokens=3,
                total_tokens=8,
            ),
        )
        assert resp.id.startswith("chatcmpl-")
        assert resp.object == "chat.completion"
        assert resp.created > 0
        assert resp.choices[0].finish_reason == "stop"
