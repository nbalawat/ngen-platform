"""Tests for platform-shared agents — visible to all tenants, protected from deletion."""

from __future__ import annotations

import pytest

from workflow_engine.agent_manager import (
    AgentRegistry,
    ManagedAgent,
    PLATFORM_TENANT,
    seed_platform_agents,
)


class TestAgentRegistryPlatformFallthrough:
    def test_tenant_gets_own_agent(self):
        reg = AgentRegistry()
        reg.register(ManagedAgent(name="my-bot", source="tenant"), "tenant-a")
        assert reg.get("my-bot", "tenant-a") is not None
        assert reg.get("my-bot", "tenant-a").source == "tenant"

    def test_tenant_falls_through_to_platform(self):
        reg = AgentRegistry()
        reg.register(ManagedAgent(name="shared-bot", source="platform"), PLATFORM_TENANT)
        # Tenant B doesn't have shared-bot, but platform does
        agent = reg.get("shared-bot", "tenant-b")
        assert agent is not None
        assert agent.source == "platform"

    def test_tenant_agent_overrides_platform(self):
        reg = AgentRegistry()
        reg.register(ManagedAgent(name="bot", source="platform"), PLATFORM_TENANT)
        reg.register(ManagedAgent(name="bot", source="tenant"), "tenant-a")
        # Tenant A gets their own version
        agent = reg.get("bot", "tenant-a")
        assert agent.source == "tenant"

    def test_missing_agent_returns_none(self):
        reg = AgentRegistry()
        assert reg.get("nonexistent", "tenant-a") is None

    def test_list_includes_platform_agents(self):
        reg = AgentRegistry()
        reg.register(ManagedAgent(name="platform-bot", source="platform"), PLATFORM_TENANT)
        reg.register(ManagedAgent(name="my-bot", source="tenant"), "tenant-a")
        agents = reg.list("tenant-a")
        names = {a.name for a in agents}
        assert "platform-bot" in names
        assert "my-bot" in names

    def test_list_deduplicates_overridden_platform_agents(self):
        reg = AgentRegistry()
        reg.register(ManagedAgent(name="bot", source="platform"), PLATFORM_TENANT)
        reg.register(ManagedAgent(name="bot", source="tenant"), "tenant-a")
        agents = reg.list("tenant-a")
        bot_agents = [a for a in agents if a.name == "bot"]
        assert len(bot_agents) == 1
        assert bot_agents[0].source == "tenant"

    def test_platform_list_only_shows_platform(self):
        reg = AgentRegistry()
        reg.register(ManagedAgent(name="p-bot", source="platform"), PLATFORM_TENANT)
        reg.register(ManagedAgent(name="t-bot", source="tenant"), "tenant-a")
        agents = reg.list(PLATFORM_TENANT)
        names = {a.name for a in agents}
        assert "p-bot" in names
        assert "t-bot" not in names

    def test_is_platform_agent(self):
        reg = AgentRegistry()
        reg.register(ManagedAgent(name="p-bot", source="platform"), PLATFORM_TENANT)
        assert reg.is_platform_agent("p-bot")
        assert not reg.is_platform_agent("unknown")

    def test_increment_invocations_platform(self):
        reg = AgentRegistry()
        reg.register(ManagedAgent(name="shared", source="platform"), PLATFORM_TENANT)
        reg.increment_invocations("shared", "tenant-a")
        assert reg.get("shared", PLATFORM_TENANT).invocation_count == 1

    def test_tenant_isolation(self):
        reg = AgentRegistry()
        reg.register(ManagedAgent(name="secret", source="tenant"), "tenant-a")
        assert reg.get("secret", "tenant-b") is None  # No fallthrough to other tenants


class TestPlatformAgentProtection:
    async def test_delete_platform_agent_returns_403(self, client):
        """Attempting to delete a platform agent should return 403."""
        # Seed platform agents
        resp = await client.get("/agents")
        agents = resp.json()
        platform_agents = [a for a in agents if a.get("source") == "platform"]
        if not platform_agents:
            pytest.skip("No platform agents seeded in test app")

        name = platform_agents[0]["name"]
        resp = await client.delete(f"/agents/{name}")
        assert resp.status_code == 403
        assert "platform-provided" in resp.json()["detail"]

    async def test_create_with_platform_name_returns_409(self, client):
        """Creating an agent with a platform agent's name should return 409."""
        resp = await client.get("/agents")
        agents = resp.json()
        platform_agents = [a for a in agents if a.get("source") == "platform"]
        if not platform_agents:
            pytest.skip("No platform agents seeded in test app")

        name = platform_agents[0]["name"]
        resp = await client.post("/agents", json={
            "name": name,
            "framework": "in-memory",
            "system_prompt": "override attempt",
        })
        assert resp.status_code == 409
        assert "platform-provided" in resp.json()["detail"]

    async def test_platform_agents_appear_in_list(self, client):
        """Platform agents should appear in tenant agent list."""
        resp = await client.get("/agents")
        agents = resp.json()
        platform_agents = [a for a in agents if a.get("source") == "platform"]
        if not platform_agents:
            pytest.skip("No platform agents seeded in test app")
        sources = {a.get("source") for a in agents}
        assert "platform" in sources

    async def test_platform_agent_invocable(self, client):
        """Tenants should be able to invoke platform agents."""
        resp = await client.get("/agents")
        agents = resp.json()
        platform_agents = [a for a in agents if a.get("source") == "platform"]
        if not platform_agents:
            pytest.skip("No platform agents seeded in test app")

        name = platform_agents[0]["name"]
        resp = await client.post(f"/agents/{name}/invoke", json={
            "messages": [{"role": "user", "content": "Hello"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["output"] is not None


class TestSeedPlatformAgents:
    @pytest.mark.asyncio
    async def test_seed_creates_agents(self):
        from ngen_framework_core.executor import AgentExecutor
        from ngen_framework_core.registry import AdapterRegistry
        from workflow_engine.default_adapter import DefaultAdapter

        registry_adapter = AdapterRegistry()
        registry_adapter.register(DefaultAdapter())
        executor = AgentExecutor(registry=registry_adapter)

        agent_registry = AgentRegistry()
        count = await seed_platform_agents(agent_registry, executor)
        assert count >= 6

        # Verify all are platform-sourced
        agents = agent_registry.list(PLATFORM_TENANT)
        for a in agents:
            assert a.source == "platform"

        # Verify specific agents exist
        names = {a.name for a in agents}
        assert "research-analyst" in names
        assert "customer-support" in names
        assert "document-processor" in names

    @pytest.mark.asyncio
    async def test_seed_is_idempotent(self):
        from ngen_framework_core.executor import AgentExecutor
        from ngen_framework_core.registry import AdapterRegistry
        from workflow_engine.default_adapter import DefaultAdapter

        registry_adapter = AdapterRegistry()
        registry_adapter.register(DefaultAdapter())
        executor = AgentExecutor(registry=registry_adapter)

        agent_registry = AgentRegistry()
        count1 = await seed_platform_agents(agent_registry, executor)
        count2 = await seed_platform_agents(agent_registry, executor)
        assert count1 >= 6
        assert count2 == 0  # Already seeded
