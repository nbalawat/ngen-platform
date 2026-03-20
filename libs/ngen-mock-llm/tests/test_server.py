"""Tests for the mock LLM server."""

from __future__ import annotations

import httpx
import pytest

from ngen_mock_llm import (
    CannedStrategy,
    EchoStrategy,
    ToolCallStrategy,
    create_mock_llm_app,
)


async def test_health(client: httpx.AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


async def test_list_models(client: httpx.AsyncClient):
    resp = await client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert len(data["data"]) == 2
    ids = {m["id"] for m in data["data"]}
    assert "mock-model" in ids


class TestChatCompletions:
    async def test_default_canned_response(
        self, client: httpx.AsyncClient
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "user", "content": "Hello"}
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert data["model"] == "mock-model"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["finish_reason"] == "stop"
        assert (
            data["choices"][0]["message"]["content"]
            == "This is a mock response."
        )

    async def test_usage_tokens_present(
        self, client: httpx.AsyncClient
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "user", "content": "Hello world"}
                ],
            },
        )
        data = resp.json()
        usage = data["usage"]
        assert usage["prompt_tokens"] > 0
        assert usage["completion_tokens"] > 0
        assert (
            usage["total_tokens"]
            == usage["prompt_tokens"] + usage["completion_tokens"]
        )

    async def test_response_id_format(
        self, client: httpx.AsyncClient
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "user", "content": "Hi"}
                ],
            },
        )
        data = resp.json()
        assert data["id"].startswith("chatcmpl-")

    async def test_model_echoed_back(
        self, client: httpx.AsyncClient
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "my-custom-model",
                "messages": [
                    {"role": "user", "content": "Hi"}
                ],
            },
        )
        assert resp.json()["model"] == "my-custom-model"


class TestEchoStrategy:
    @pytest.fixture()
    async def echo_client(self):
        app = create_mock_llm_app(strategy=EchoStrategy())
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            yield ac

    async def test_echoes_last_user_message(
        self, echo_client: httpx.AsyncClient
    ):
        resp = await echo_client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "user", "content": "What is 2+2?"},
                ],
            },
        )
        content = resp.json()["choices"][0]["message"]["content"]
        assert content == "Echo: What is 2+2?"

    async def test_echoes_last_in_multi_turn(
        self, echo_client: httpx.AsyncClient
    ):
        resp = await echo_client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "user", "content": "First"},
                    {"role": "assistant", "content": "Reply"},
                    {"role": "user", "content": "Second"},
                ],
            },
        )
        content = resp.json()["choices"][0]["message"]["content"]
        assert content == "Echo: Second"

    async def test_custom_prefix(self):
        app = create_mock_llm_app(
            strategy=EchoStrategy(prefix="[BOT] ")
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            resp = await ac.post(
                "/v1/chat/completions",
                json={
                    "model": "mock-model",
                    "messages": [
                        {"role": "user", "content": "Hi"}
                    ],
                },
            )
        content = resp.json()["choices"][0]["message"]["content"]
        assert content == "[BOT] Hi"


class TestToolCallStrategy:
    @pytest.fixture()
    async def tool_client(self):
        app = create_mock_llm_app(
            strategy=ToolCallStrategy(
                tool_name="get_weather",
                arguments={"location": "Paris"},
            )
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            yield ac

    async def test_returns_tool_call(
        self, tool_client: httpx.AsyncClient
    ):
        resp = await tool_client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "user", "content": "Weather?"}
                ],
            },
        )
        data = resp.json()
        assert data["choices"][0]["finish_reason"] == "tool_calls"
        msg = data["choices"][0]["message"]
        assert msg["content"] is None
        assert len(msg["tool_calls"]) == 1
        tc = msg["tool_calls"][0]
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "get_weather"
        assert '"Paris"' in tc["function"]["arguments"]

    async def test_tool_call_has_id(
        self, tool_client: httpx.AsyncClient
    ):
        resp = await tool_client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "user", "content": "Weather?"}
                ],
            },
        )
        tc = resp.json()["choices"][0]["message"]["tool_calls"][0]
        assert tc["id"].startswith("call_")


class TestStrategySwap:
    async def test_swap_strategy_at_runtime(
        self, mock_llm_app, client: httpx.AsyncClient
    ):
        # Default canned response
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "m",
                "messages": [
                    {"role": "user", "content": "Hi"}
                ],
            },
        )
        assert (
            resp.json()["choices"][0]["message"]["content"]
            == "This is a mock response."
        )

        # Swap to echo
        mock_llm_app.state.strategy = EchoStrategy()
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "m",
                "messages": [
                    {"role": "user", "content": "Hi"}
                ],
            },
        )
        assert (
            resp.json()["choices"][0]["message"]["content"]
            == "Echo: Hi"
        )
