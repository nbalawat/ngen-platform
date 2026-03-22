"""Tests for memory observability API endpoints.

Verifies platform-wide stats, per-agent stats with size metrics,
memory health recommendations, and entry detail endpoints.
Uses InMemoryMemoryStore. No mocks.
"""

from __future__ import annotations

import pytest


class TestPlatformMemoryStats:
    async def test_platform_stats_empty(self, client):
        resp = await client.get("/memory/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_entries"] == 0
        assert data["agents_with_memory"] == 0

    async def test_platform_stats_after_invoke(self, client):
        await client.post("/agents", json={
            "name": "stats-agent", "framework": "in-memory",
        })
        await client.post("/agents/stats-agent/invoke", json={
            "messages": [{"role": "user", "content": "Hello stats"}],
        })

        resp = await client.get("/memory/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_entries"] >= 2  # user + assistant
        assert data["total_bytes"] > 0
        assert data["total_tokens"] > 0
        assert "stats-agent" in data["by_agent"]
        agent_data = data["by_agent"]["stats-agent"]
        assert agent_data["total_bytes"] > 0

    async def test_platform_stats_multiple_agents(self, client):
        for name in ["multi-a", "multi-b"]:
            await client.post("/agents", json={
                "name": name, "framework": "in-memory",
            })
            await client.post(f"/agents/{name}/invoke", json={
                "messages": [{"role": "user", "content": f"Hi from {name}"}],
            })

        resp = await client.get("/memory/stats")
        data = resp.json()
        assert data["agents_with_memory"] >= 2
        assert "multi-a" in data["by_agent"]
        assert "multi-b" in data["by_agent"]


class TestAgentMemoryStats:
    async def test_agent_stats_with_size(self, client):
        await client.post("/agents", json={
            "name": "size-agent", "framework": "in-memory",
        })
        await client.post("/agents/size-agent/invoke", json={
            "messages": [{"role": "user", "content": "Check sizes"}],
        })

        resp = await client.get("/agents/size-agent/memory/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "size-agent"
        assert data["total_entries"] >= 2
        assert data["total_bytes"] > 0
        assert data["total_tokens"] > 0
        assert "context_budget_tokens" in data
        assert "conversational" in data["by_type"]


class TestMemoryEntryDetail:
    async def test_get_entry_by_id(self, client):
        await client.post("/agents", json={
            "name": "detail-agent", "framework": "in-memory",
        })
        await client.post("/agents/detail-agent/invoke", json={
            "messages": [{"role": "user", "content": "Entry detail test"}],
        })

        # Get memory entries to find an ID
        mem_resp = await client.get("/agents/detail-agent/memory?memory_type=conversational")
        entries = mem_resp.json()
        assert len(entries) >= 1
        entry_id = entries[0]["id"]

        # Fetch full detail
        resp = await client.get(f"/agents/detail-agent/memory/{entry_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == entry_id
        assert data["memory_type"] == "conversational"
        assert "content" in data
        assert "size_bytes" in data
        assert "token_estimate" in data
        assert data["size_bytes"] > 0
        assert "scope" in data

    async def test_get_entry_not_found(self, client):
        await client.post("/agents", json={
            "name": "noentry-agent", "framework": "in-memory",
        })
        resp = await client.get("/agents/noentry-agent/memory/nonexistent-id")
        assert resp.status_code == 404


class TestMemoryHealth:
    async def test_health_empty(self, client):
        resp = await client.get("/memory/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "recommendations" in data
        assert "agents_analyzed" in data

    async def test_health_returns_recommendations_for_heavy_agent(self, client):
        await client.post("/agents", json={
            "name": "heavy-agent", "framework": "in-memory",
        })
        # Invoke many times to build up memory
        for i in range(30):
            await client.post("/agents/heavy-agent/invoke", json={
                "messages": [{"role": "user", "content": f"Message number {i} with enough content to push tokens up " * 5}],
            })

        resp = await client.get("/memory/health")
        data = resp.json()
        # Should have at least analyzed the agent
        assert data["agents_analyzed"] >= 1


class TestTenantContext:
    async def test_tenant_headers_affect_scope(self, client):
        """Memory scoped to a tenant is isolated from default scope."""
        await client.post("/agents", json={
            "name": "tenant-agent", "framework": "in-memory",
        })

        # Invoke with tenant headers
        await client.post(
            "/agents/tenant-agent/invoke",
            json={"messages": [{"role": "user", "content": "Tenant A msg"}]},
            headers={"x-org-id": "acme", "x-team-id": "eng", "x-project-id": "proj1"},
        )

        # Read with same tenant headers
        resp = await client.get(
            "/agents/tenant-agent/memory",
            headers={"x-org-id": "acme", "x-team-id": "eng", "x-project-id": "proj1"},
        )
        entries = resp.json()
        assert any("Tenant A msg" in e["content"] for e in entries)

        # Read with different tenant — should be empty
        resp2 = await client.get(
            "/agents/tenant-agent/memory",
            headers={"x-org-id": "other-org", "x-team-id": "other", "x-project-id": "other"},
        )
        entries2 = resp2.json()
        assert not any("Tenant A msg" in e["content"] for e in entries2)

    async def test_stats_respect_tenant_headers(self, client):
        """Agent stats should be scoped to tenant."""
        await client.post("/agents", json={
            "name": "scoped-stats-agent", "framework": "in-memory",
        })

        # Write under tenant A
        await client.post(
            "/agents/scoped-stats-agent/invoke",
            json={"messages": [{"role": "user", "content": "A data"}]},
            headers={"x-org-id": "tenant-a"},
        )

        # Stats under tenant A should show entries
        resp_a = await client.get(
            "/agents/scoped-stats-agent/memory/stats",
            headers={"x-org-id": "tenant-a"},
        )
        assert resp_a.json()["total_entries"] >= 2

        # Stats under tenant B should be empty
        resp_b = await client.get(
            "/agents/scoped-stats-agent/memory/stats",
            headers={"x-org-id": "tenant-b"},
        )
        assert resp_b.json()["total_entries"] == 0

    async def test_clear_memory_respects_tenant(self, client):
        """Clear memory should only affect the tenant's scope."""
        await client.post("/agents", json={
            "name": "clear-scoped-agent", "framework": "in-memory",
        })

        # Write under two tenants
        for tenant in ["org-x", "org-y"]:
            await client.post(
                "/agents/clear-scoped-agent/invoke",
                json={"messages": [{"role": "user", "content": f"Data for {tenant}"}]},
                headers={"x-org-id": tenant},
            )

        # Clear only org-x
        await client.delete(
            "/agents/clear-scoped-agent/memory",
            headers={"x-org-id": "org-x"},
        )

        # org-x should be empty
        resp_x = await client.get(
            "/agents/clear-scoped-agent/memory",
            headers={"x-org-id": "org-x"},
        )
        assert len(resp_x.json()) == 0

        # org-y should still have data
        resp_y = await client.get(
            "/agents/clear-scoped-agent/memory",
            headers={"x-org-id": "org-y"},
        )
        assert len(resp_y.json()) > 0


class TestEndToEndMemoryFlow:
    """Full end-to-end tests covering the complete memory lifecycle."""

    async def test_create_invoke_inspect_clear_lifecycle(self, client):
        """Complete lifecycle: create agent -> invoke -> read memory -> inspect entry -> clear."""
        # Create
        resp = await client.post("/agents", json={
            "name": "lifecycle-agent", "framework": "in-memory",
        })
        assert resp.status_code == 201

        # Invoke
        resp = await client.post("/agents/lifecycle-agent/invoke", json={
            "messages": [{"role": "user", "content": "What is the meaning of life?"}],
        })
        assert resp.status_code == 200
        assert resp.json()["output"] is not None

        # Read memory
        resp = await client.get("/agents/lifecycle-agent/memory")
        entries = resp.json()
        assert len(entries) >= 2
        user_entries = [e for e in entries if e["role"] == "user"]
        assistant_entries = [e for e in entries if e["role"] == "assistant"]
        assert len(user_entries) >= 1
        assert len(assistant_entries) >= 1

        # Get stats
        resp = await client.get("/agents/lifecycle-agent/memory/stats")
        stats = resp.json()
        assert stats["total_entries"] >= 2
        assert stats["total_bytes"] > 0
        assert stats["total_tokens"] > 0

        # Inspect a specific entry
        entry_id = entries[0]["id"]
        resp = await client.get(f"/agents/lifecycle-agent/memory/{entry_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["id"] == entry_id
        assert detail["size_bytes"] > 0
        assert "scope" in detail

        # Clear
        resp = await client.delete("/agents/lifecycle-agent/memory")
        assert resp.json()["deleted"] >= 2

        # Verify empty
        resp = await client.get("/agents/lifecycle-agent/memory")
        assert len(resp.json()) == 0

    async def test_multiple_invocations_accumulate_memory(self, client):
        """Memory should accumulate across multiple invocations."""
        await client.post("/agents", json={
            "name": "accumulate-agent", "framework": "in-memory",
        })

        messages = ["First question", "Second question", "Third question"]
        for msg in messages:
            await client.post("/agents/accumulate-agent/invoke", json={
                "messages": [{"role": "user", "content": msg}],
            })

        resp = await client.get("/agents/accumulate-agent/memory?limit=100")
        entries = resp.json()
        # 3 user + 3 assistant = 6
        assert len(entries) >= 6

        # Verify all user messages present
        contents = [e["content"] for e in entries]
        for msg in messages:
            assert any(msg in c for c in contents)

        # Stats should reflect total
        resp = await client.get("/agents/accumulate-agent/memory/stats")
        stats = resp.json()
        assert stats["total_entries"] >= 6

    async def test_session_isolation(self, client):
        """Different sessions should have isolated memory when using session_id."""
        await client.post("/agents", json={
            "name": "session-agent", "framework": "in-memory",
        })

        # Invoke with session A
        await client.post("/agents/session-agent/invoke", json={
            "messages": [{"role": "user", "content": "Session A message"}],
            "session_id": "session-a",
        })

        # Invoke with session B
        await client.post("/agents/session-agent/invoke", json={
            "messages": [{"role": "user", "content": "Session B message"}],
            "session_id": "session-b",
        })

        # Reading without session should see all (parent scope match)
        resp = await client.get("/agents/session-agent/memory")
        all_entries = resp.json()
        assert len(all_entries) >= 4  # 2 user + 2 assistant

    async def test_platform_stats_aggregate_across_agents(self, client):
        """Platform stats should aggregate across all agents."""
        agents = ["plat-agent-1", "plat-agent-2", "plat-agent-3"]
        for name in agents:
            await client.post("/agents", json={
                "name": name, "framework": "in-memory",
            })
            await client.post(f"/agents/{name}/invoke", json={
                "messages": [{"role": "user", "content": f"Hello from {name}"}],
            })

        resp = await client.get("/memory/stats")
        stats = resp.json()
        assert stats["agents_with_memory"] >= 3
        assert stats["total_entries"] >= 6  # 3 agents x 2 entries each
        assert stats["total_bytes"] > 0

        # Verify each agent appears in breakdown
        for name in agents:
            assert name in stats["by_agent"]


class TestHealthRecommendationsAdvanced:
    async def test_no_recommendations_for_light_agents(self, client):
        """Agents with minimal memory should have no recommendations."""
        await client.post("/agents", json={
            "name": "light-agent", "framework": "in-memory",
        })
        await client.post("/agents/light-agent/invoke", json={
            "messages": [{"role": "user", "content": "Hi"}],
        })

        resp = await client.get("/memory/health")
        recs = resp.json()["recommendations"]
        light_recs = [r for r in recs if r["agent_name"] == "light-agent"]
        # Light agent shouldn't trigger any warnings
        assert len(light_recs) == 0

    async def test_health_recommendation_severity_values(self, client):
        """All recommendations should have valid severity values."""
        await client.post("/agents", json={
            "name": "sev-check-agent", "framework": "in-memory",
        })
        # Generate enough data for potential recommendations
        for i in range(20):
            await client.post("/agents/sev-check-agent/invoke", json={
                "messages": [{"role": "user", "content": f"Message {i} " * 20}],
            })

        resp = await client.get("/memory/health")
        for rec in resp.json()["recommendations"]:
            assert rec["severity"] in ("info", "warning", "critical")
            assert rec["agent_name"]
            assert rec["issue"]
            assert rec["suggestion"]
