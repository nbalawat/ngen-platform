"""Tests for agent memory integration — conversation persistence.

Verifies that agent invoke persists user/assistant messages to memory
and that memory endpoints return conversation history.
Uses InMemoryMemoryStore. No mocks.
"""

from __future__ import annotations

import pytest


class TestAgentMemoryPersistence:
    async def test_invoke_persists_user_message(self, client):
        await client.post("/agents", json={
            "name": "mem-agent", "framework": "in-memory",
        })
        await client.post("/agents/mem-agent/invoke", json={
            "messages": [{"role": "user", "content": "Hello from test"}],
        })

        resp = await client.get("/agents/mem-agent/memory?memory_type=conversational")
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) >= 1
        contents = [e["content"] for e in entries]
        assert any("Hello from test" in c for c in contents)

    async def test_invoke_persists_assistant_response(self, client):
        await client.post("/agents", json={
            "name": "resp-agent", "framework": "in-memory",
        })
        resp = await client.post("/agents/resp-agent/invoke", json={
            "messages": [{"role": "user", "content": "Hi"}],
        })
        output = resp.json()["output"]
        assert output is not None

        mem_resp = await client.get("/agents/resp-agent/memory?memory_type=conversational")
        entries = mem_resp.json()
        roles = [e["role"] for e in entries]
        assert "user" in roles
        assert "assistant" in roles

    async def test_multiple_invocations_accumulate(self, client):
        await client.post("/agents", json={
            "name": "multi-agent", "framework": "in-memory",
        })

        for msg in ["First message", "Second message", "Third message"]:
            await client.post("/agents/multi-agent/invoke", json={
                "messages": [{"role": "user", "content": msg}],
            })

        resp = await client.get("/agents/multi-agent/memory?memory_type=conversational")
        entries = resp.json()
        # 3 user messages + 3 assistant responses = 6 entries
        assert len(entries) >= 6

    async def test_context_window_endpoint(self, client):
        await client.post("/agents", json={
            "name": "ctx-agent", "framework": "in-memory",
        })
        await client.post("/agents/ctx-agent/invoke", json={
            "messages": [{"role": "user", "content": "Build context"}],
        })

        resp = await client.get("/agents/ctx-agent/memory/context?query=test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "ctx-agent"
        assert isinstance(data["context"], str)


class TestMemoryEndpointValidation:
    async def test_memory_nonexistent_agent(self, client):
        resp = await client.get("/agents/nonexistent/memory")
        assert resp.status_code == 404

    async def test_context_nonexistent_agent(self, client):
        resp = await client.get("/agents/nonexistent/memory/context")
        assert resp.status_code == 404

    async def test_invalid_memory_type(self, client):
        await client.post("/agents", json={
            "name": "invalid-type-agent", "framework": "in-memory",
        })
        resp = await client.get("/agents/invalid-type-agent/memory?memory_type=bogus")
        assert resp.status_code == 400
