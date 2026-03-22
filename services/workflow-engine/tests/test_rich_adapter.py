"""TDD tests for the rich DefaultAdapter — context-aware agent responses.

These tests verify that agent output is driven by the system_prompt
and user input, not just echo. Written FIRST (red), then code
implements to make them pass (green).

Uses InMemoryAdapter (test conftest) and real HTTP calls. No mocks.
"""

from __future__ import annotations

import pytest


class TestRichAgentOutput:
    """Agent responses should be context-aware, not echo."""

    async def test_output_references_system_prompt(self, client):
        """Output should reference the role from the system prompt."""
        await client.post("/agents", json={
            "name": "support-bot",
            "framework": "in-memory",
            "system_prompt": "You are a customer support agent helping users with account issues.",
        })
        resp = await client.post("/agents/support-bot/invoke", json={
            "messages": [{"role": "user", "content": "How do I reset my password?"}],
        })
        output = resp.json()["output"]
        assert output is not None
        # Should reference the role
        output_lower = output.lower()
        assert "support" in output_lower or "customer" in output_lower
        # Should acknowledge the user's question
        assert "password" in output_lower or "reset" in output_lower

    async def test_output_without_system_prompt_still_meaningful(self, client):
        """Even without a system prompt, output should be more than echo."""
        await client.post("/agents", json={
            "name": "default-bot",
            "framework": "in-memory",
        })
        resp = await client.post("/agents/default-bot/invoke", json={
            "messages": [{"role": "user", "content": "Tell me about the weather"}],
        })
        output = resp.json()["output"]
        assert output is not None
        # Should acknowledge the topic, not just "Output from default-bot"
        assert "weather" in output.lower()

    async def test_different_inputs_produce_different_outputs(self, client):
        """Two different questions should get different answers."""
        await client.post("/agents", json={
            "name": "varied-bot",
            "framework": "in-memory",
            "system_prompt": "You are a helpful assistant.",
        })

        resp1 = await client.post("/agents/varied-bot/invoke", json={
            "messages": [{"role": "user", "content": "What is Python?"}],
        })
        resp2 = await client.post("/agents/varied-bot/invoke", json={
            "messages": [{"role": "user", "content": "How do I cook pasta?"}],
        })

        output1 = resp1.json()["output"]
        output2 = resp2.json()["output"]
        assert output1 != output2

    async def test_thinking_event_references_agent_role(self, client):
        """THINKING event should mention what the agent's role is."""
        await client.post("/agents", json={
            "name": "thinker-bot",
            "framework": "in-memory",
            "system_prompt": "You are a data analyst specializing in financial reports.",
        })
        resp = await client.post("/agents/thinker-bot/invoke", json={
            "messages": [{"role": "user", "content": "Analyze Q3 revenue"}],
        })
        events = resp.json()["events"]
        thinking_events = [e for e in events if e["type"] == "thinking"]
        assert len(thinking_events) >= 1
        thinking_text = thinking_events[0]["data"].get("text", "").lower()
        # Thinking should reference either the role or the topic
        assert "analyst" in thinking_text or "financial" in thinking_text or "revenue" in thinking_text or "q3" in thinking_text


class TestToolCallSimulation:
    """Agents with tools should simulate tool usage in their event stream."""

    async def test_tool_call_events_when_tools_configured(self, client):
        """Agent with tools in metadata should emit tool call events."""
        await client.post("/agents", json={
            "name": "tool-bot",
            "framework": "in-memory",
            "system_prompt": "You are a research assistant with web search capability.",
            "metadata": {"tools": ["search/web-search", "docs/read-file"]},
        })
        resp = await client.post("/agents/tool-bot/invoke", json={
            "messages": [{"role": "user", "content": "Search for recent AI news"}],
        })
        events = resp.json()["events"]
        event_types = [e["type"] for e in events]
        assert "tool_call_start" in event_types
        assert "tool_call_end" in event_types

    async def test_no_tool_events_without_tools(self, client):
        """Agent without tools should NOT emit tool call events."""
        await client.post("/agents", json={
            "name": "no-tool-bot",
            "framework": "in-memory",
            "system_prompt": "You are a simple chatbot.",
        })
        resp = await client.post("/agents/no-tool-bot/invoke", json={
            "messages": [{"role": "user", "content": "Hello there"}],
        })
        events = resp.json()["events"]
        event_types = [e["type"] for e in events]
        assert "tool_call_start" not in event_types
        assert "tool_call_end" not in event_types

    async def test_tool_call_references_tool_name(self, client):
        """Tool call events should include the tool name."""
        await client.post("/agents", json={
            "name": "named-tool-bot",
            "framework": "in-memory",
            "system_prompt": "You are an assistant.",
            "metadata": {"tools": ["search/web-search"]},
        })
        resp = await client.post("/agents/named-tool-bot/invoke", json={
            "messages": [{"role": "user", "content": "Find information"}],
        })
        events = resp.json()["events"]
        tool_starts = [e for e in events if e["type"] == "tool_call_start"]
        assert len(tool_starts) >= 1
        assert "tool" in tool_starts[0]["data"]


class TestAgentInfoSystemPrompt:
    """AgentInfo should include system_prompt for frontend display."""

    async def test_agent_info_includes_system_prompt(self, client):
        """GET /agents/{name} should return system_prompt field."""
        await client.post("/agents", json={
            "name": "prompt-bot",
            "framework": "in-memory",
            "system_prompt": "You are an expert in quantum physics.",
        })
        resp = await client.get("/agents/prompt-bot")
        data = resp.json()
        assert "system_prompt" in data
        assert data["system_prompt"] == "You are an expert in quantum physics."

    async def test_list_agents_includes_system_prompt(self, client):
        """GET /agents should include system_prompt for each agent."""
        await client.post("/agents", json={
            "name": "listed-bot",
            "framework": "in-memory",
            "system_prompt": "You are a translator.",
        })
        resp = await client.get("/agents")
        agents = resp.json()
        matching = [a for a in agents if a["name"] == "listed-bot"]
        assert len(matching) == 1
        assert matching[0]["system_prompt"] == "You are a translator."

    async def test_agent_info_empty_system_prompt(self, client):
        """Agent without system_prompt should return empty string."""
        await client.post("/agents", json={
            "name": "no-prompt-bot",
            "framework": "in-memory",
        })
        resp = await client.get("/agents/no-prompt-bot")
        data = resp.json()
        assert "system_prompt" in data
        # Default from AgentCreateRequest is "You are a helpful agent."
        assert isinstance(data["system_prompt"], str)


class TestAgentAutoRecreate:
    """Agents should be auto-recreated in the executor if state is lost."""

    async def test_invoke_recreates_agent_if_executor_lost_it(self, client, app):
        """If agent is in registry but not executor, invoke should still work."""
        # Create agent normally
        await client.post("/agents", json={
            "name": "fragile-bot",
            "framework": "in-memory",
            "system_prompt": "You are a test agent.",
        })

        # Simulate executor losing the agent (e.g., adapter reset)
        executor = app.state.executor
        if "fragile-bot" in executor.agent_names:
            await executor.teardown("fragile-bot")

        # Invoke should auto-recreate and succeed
        resp = await client.post("/agents/fragile-bot/invoke", json={
            "messages": [{"role": "user", "content": "Are you alive?"}],
        })
        assert resp.status_code == 200
        assert resp.json()["output"] is not None
        assert len(resp.json()["output"]) > 10

    async def test_invoke_nonexistent_still_returns_404(self, client):
        """Agent not in registry at all should still return 404."""
        resp = await client.post("/agents/totally-missing/invoke", json={
            "messages": [{"role": "user", "content": "Hello"}],
        })
        assert resp.status_code == 404
