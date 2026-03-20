"""Tests for provider implementations — translation logic and provider dispatch."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from model_gateway.providers.anthropic import (
    AnthropicProvider,
    anthropic_to_openai,
    openai_to_anthropic,
)
from model_gateway.providers.base import ProviderRegistry
from model_gateway.providers.openai_compat import OpenAICompatProvider


# ---------------------------------------------------------------------------
# OpenAI → Anthropic translation
# ---------------------------------------------------------------------------


class TestOpenAIToAnthropic:
    def test_basic_user_message(self) -> None:
        body = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1024,
        }
        result = openai_to_anthropic(body)

        assert result["model"] == "claude-sonnet-4-6"
        assert result["max_tokens"] == 1024
        assert len(result["messages"]) == 1
        assert result["messages"][0] == {"role": "user", "content": "Hello"}
        assert "system" not in result

    def test_system_message_extracted(self) -> None:
        body = {
            "model": "claude-opus-4-6",
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hi"},
            ],
        }
        result = openai_to_anthropic(body)

        assert result["system"] == "You are helpful."
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "user"

    def test_multi_turn_conversation(self) -> None:
        body = {
            "model": "claude-sonnet-4-6",
            "messages": [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "What is 2+2?"},
                {"role": "assistant", "content": "4"},
                {"role": "user", "content": "And 3+3?"},
            ],
        }
        result = openai_to_anthropic(body)

        assert result["system"] == "Be concise."
        assert len(result["messages"]) == 3
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"
        assert result["messages"][2]["role"] == "user"

    def test_temperature_mapped(self) -> None:
        body = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Hi"}],
            "temperature": 0.7,
        }
        result = openai_to_anthropic(body)
        assert result["temperature"] == 0.7

    def test_top_p_mapped(self) -> None:
        body = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Hi"}],
            "top_p": 0.9,
        }
        result = openai_to_anthropic(body)
        assert result["top_p"] == 0.9

    def test_stop_string(self) -> None:
        body = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Hi"}],
            "stop": "END",
        }
        result = openai_to_anthropic(body)
        assert result["stop_sequences"] == ["END"]

    def test_stop_list(self) -> None:
        body = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Hi"}],
            "stop": ["END", "STOP"],
        }
        result = openai_to_anthropic(body)
        assert result["stop_sequences"] == ["END", "STOP"]

    def test_stream_flag_not_forwarded(self) -> None:
        """Stream is not part of the Anthropic Messages API — handled by the SDK."""
        body = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        }
        result = openai_to_anthropic(body)
        assert "stream" not in result

    def test_default_max_tokens(self) -> None:
        body = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Hi"}],
        }
        result = openai_to_anthropic(body)
        assert result["max_tokens"] == 4096


# ---------------------------------------------------------------------------
# Anthropic → OpenAI translation
# ---------------------------------------------------------------------------


class TestAnthropicToOpenAI:
    def test_basic_text_response(self) -> None:
        anthropic_resp = {
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello there!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        result = anthropic_to_openai(anthropic_resp, "claude-sonnet-4-6")

        assert result["object"] == "chat.completion"
        assert result["model"] == "claude-sonnet-4-6"
        assert result["choices"][0]["message"]["content"] == "Hello there!"
        assert result["choices"][0]["finish_reason"] == "stop"
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["completion_tokens"] == 5
        assert result["usage"]["total_tokens"] == 15

    def test_multiple_text_blocks(self) -> None:
        anthropic_resp = {
            "content": [
                {"type": "text", "text": "Part 1."},
                {"type": "text", "text": "Part 2."},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 10},
        }
        result = anthropic_to_openai(anthropic_resp, "claude-opus-4-6")
        assert result["choices"][0]["message"]["content"] == "Part 1.\nPart 2."

    def test_max_tokens_stop_reason(self) -> None:
        anthropic_resp = {
            "content": [{"type": "text", "text": "Truncated..."}],
            "stop_reason": "max_tokens",
            "usage": {"input_tokens": 10, "output_tokens": 100},
        }
        result = anthropic_to_openai(anthropic_resp, "claude-sonnet-4-6")
        assert result["choices"][0]["finish_reason"] == "length"

    def test_tool_use_stop_reason(self) -> None:
        anthropic_resp = {
            "content": [{"type": "text", "text": ""}],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
        result = anthropic_to_openai(anthropic_resp, "claude-sonnet-4-6")
        assert result["choices"][0]["finish_reason"] == "tool_calls"

    def test_empty_content(self) -> None:
        anthropic_resp = {
            "content": [],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 0},
        }
        result = anthropic_to_openai(anthropic_resp, "claude-sonnet-4-6")
        assert result["choices"][0]["message"]["content"] == ""

    def test_id_generated(self) -> None:
        anthropic_resp = {
            "content": [{"type": "text", "text": "Hi"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        result = anthropic_to_openai(anthropic_resp, "claude-sonnet-4-6")
        assert result["id"].startswith("chatcmpl-")
        assert result["created"] > 0


# ---------------------------------------------------------------------------
# ProviderRegistry
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    def test_register_and_get(self) -> None:
        registry = ProviderRegistry()
        provider = OpenAICompatProvider()
        registry.register("mock", provider)
        assert registry.get("mock") is provider

    def test_get_missing_returns_none(self) -> None:
        registry = ProviderRegistry()
        assert registry.get("nonexistent") is None

    def test_list_providers(self) -> None:
        registry = ProviderRegistry()
        registry.register("mock", OpenAICompatProvider())
        registry.register("anthropic", AnthropicProvider())
        assert sorted(registry.list_providers()) == ["anthropic", "mock"]


# ---------------------------------------------------------------------------
# AnthropicProvider integration (with fake upstream)
# ---------------------------------------------------------------------------


class TestAnthropicProviderWithFakeUpstream:
    """Test AnthropicProvider using a fake Anthropic API response.

    Injects a custom httpx.AsyncClient into the provider so the SDK
    sends requests through the fake ASGI transport instead of the network.
    """

    @pytest.fixture()
    def fake_anthropic_response(self) -> dict[str, Any]:
        return {
            "id": "msg_test123",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Paris is the capital of France."}],
            "model": "claude-sonnet-4-6",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 15, "output_tokens": 8},
        }

    @pytest.fixture()
    def fake_upstream_transport(self, fake_anthropic_response):
        """ASGI app that mimics the Anthropic /v1/messages endpoint."""
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def messages_endpoint(request):
            assert request.headers.get("x-api-key") == "test-key"
            body = await request.json()
            assert "messages" in body
            assert "model" in body
            return JSONResponse(fake_anthropic_response)

        app = Starlette(routes=[Route("/v1/messages", messages_endpoint, methods=["POST"])])
        return httpx.ASGITransport(app=app)

    async def test_chat_completion_translates_correctly(
        self, fake_upstream_transport, fake_anthropic_response
    ) -> None:
        # Inject the fake transport into the SDK via http_client
        fake_http = httpx.AsyncClient(transport=fake_upstream_transport)
        provider = AnthropicProvider(http_client=fake_http)
        try:
            result = await provider.chat_completion(
                client=fake_http,  # unused by SDK path, but required by interface
                upstream_url="http://fake-anthropic",
                body={
                    "model": "claude-sonnet-4-6",
                    "messages": [
                        {"role": "system", "content": "Be helpful."},
                        {"role": "user", "content": "What is the capital of France?"},
                    ],
                    "max_tokens": 1024,
                },
                api_key="test-key",
            )
        finally:
            await fake_http.aclose()

        # Response should be in OpenAI format
        assert result["object"] == "chat.completion"
        assert result["choices"][0]["message"]["content"] == "Paris is the capital of France."
        assert result["usage"]["prompt_tokens"] == 15
        assert result["usage"]["completion_tokens"] == 8

    async def test_chat_completion_requires_api_key(self) -> None:
        provider = AnthropicProvider()
        async with httpx.AsyncClient() as client:
            with pytest.raises(ValueError, match="API key is required"):
                await provider.chat_completion(
                    client=client,
                    upstream_url="http://fake",
                    body={"model": "claude-sonnet-4-6", "messages": []},
                    api_key=None,
                )

    async def test_native_request_passthrough(
        self, fake_upstream_transport, fake_anthropic_response
    ) -> None:
        fake_http = httpx.AsyncClient(transport=fake_upstream_transport)
        provider = AnthropicProvider(http_client=fake_http)
        try:
            result = await provider.native_request(
                client=fake_http,
                upstream_url="http://fake-anthropic",
                body={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                api_key="test-key",
            )
        finally:
            await fake_http.aclose()

        # Should return raw Anthropic response as dict
        assert result["type"] == "message"
        assert result["content"][0]["text"] == "Paris is the capital of France."

    async def test_native_request_requires_api_key(self) -> None:
        provider = AnthropicProvider()
        async with httpx.AsyncClient() as client:
            with pytest.raises(ValueError, match="API key is required"):
                await provider.native_request(
                    client=client,
                    upstream_url="http://fake",
                    body={"model": "claude-sonnet-4-6", "messages": []},
                    api_key=None,
                )


# ---------------------------------------------------------------------------
# OpenAICompatProvider integration
# ---------------------------------------------------------------------------


class TestOpenAICompatProvider:
    async def test_chat_completion_forwards_request(self) -> None:
        """OpenAI-compatible provider forwards to /v1/chat/completions."""
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        expected_response = {
            "id": "chatcmpl-test",
            "choices": [{"message": {"role": "assistant", "content": "Hi!"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }

        async def completions(request):
            return JSONResponse(expected_response)

        app = Starlette(routes=[Route("/v1/chat/completions", completions, methods=["POST"])])
        transport = httpx.ASGITransport(app=app)

        provider = OpenAICompatProvider()
        async with httpx.AsyncClient(transport=transport) as client:
            result = await provider.chat_completion(
                client=client,
                upstream_url="http://fake-ollama",
                body={"model": "llama3.2", "messages": [{"role": "user", "content": "Hi"}]},
            )

        assert result["choices"][0]["message"]["content"] == "Hi!"

    async def test_auth_header_sent_when_api_key_provided(self) -> None:
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def completions(request):
            assert request.headers.get("authorization") == "Bearer my-key"
            return JSONResponse({"choices": [], "usage": {}})

        app = Starlette(routes=[Route("/v1/chat/completions", completions, methods=["POST"])])
        transport = httpx.ASGITransport(app=app)

        provider = OpenAICompatProvider()
        async with httpx.AsyncClient(transport=transport) as client:
            await provider.chat_completion(
                client=client,
                upstream_url="http://fake",
                body={"model": "test", "messages": []},
                api_key="my-key",
            )
