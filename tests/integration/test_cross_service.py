"""Integration tests: cross-service workflows.

Tests that span multiple services, verifying they work together
end-to-end in the Docker Compose environment.
"""

from __future__ import annotations

import textwrap
import uuid

import httpx
import pytest


def _make_workflow_yaml(name: str, topology: str = "sequential", agents: list[str] | None = None) -> str:
    """Build a valid WorkflowCRD YAML string."""
    if agents is None:
        agents = ["mock-agent"]
    agent_lines = "\n".join(f"  - ref: {a}" for a in agents)
    return (
        f"apiVersion: ngen.io/v1\n"
        f"kind: Workflow\n"
        f"metadata:\n"
        f"  name: {name}\n"
        f"  namespace: integration-test\n"
        f"spec:\n"
        f"  topology: {topology}\n"
        f"  agents:\n"
        f"{agent_lines}\n"
    )


# ---------------------------------------------------------------------------
# Model Registry → Gateway flow
# ---------------------------------------------------------------------------


class TestRegistryToGateway:
    """Verify models registered in the registry are usable through the gateway."""

    async def test_gateway_lists_models(self, http: httpx.AsyncClient, gateway_url):
        """Gateway should have auto-registered mock models."""
        resp = await http.get(f"{gateway_url}/v1/models")
        assert resp.status_code == 200
        models = resp.json()["data"]
        model_ids = [m["id"] for m in models]
        assert "mock-model" in model_ids, f"mock-model not found in gateway. Available: {model_ids}"


# ---------------------------------------------------------------------------
# Governance → evaluation across namespaces
# ---------------------------------------------------------------------------


class TestGovernanceCrossNamespace:
    """Test governance policies don't leak across namespaces."""

    async def test_full_governance_lifecycle(self, http: httpx.AsyncClient, governance_url):
        """Create policy → evaluate (blocked) → delete policy → evaluate (allowed)."""
        ns = f"lifecycle-{uuid.uuid4().hex[:8]}"

        # Create blocking policy
        create = await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": f"lifecycle-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "policy_type": "content_filter",
                "action": "block",
                "rules": {"blocked_patterns": ["restricted"]},
            },
        )
        assert create.status_code == 201
        policy_id = create.json()["id"]

        # Evaluate — should block
        eval1 = await http.post(
            f"{governance_url}/api/v1/evaluate",
            json={"namespace": ns, "content": "This is restricted data", "agent_name": "a"},
        )
        assert eval1.json()["allowed"] is False

        # Delete policy
        del_resp = await http.delete(f"{governance_url}/api/v1/policies/{policy_id}")
        assert del_resp.status_code == 204

        # Evaluate again — should pass
        eval2 = await http.post(
            f"{governance_url}/api/v1/evaluate",
            json={"namespace": ns, "content": "This is restricted data", "agent_name": "a"},
        )
        assert eval2.json()["allowed"] is True


# ---------------------------------------------------------------------------
# MCP → tool catalog consistency
# ---------------------------------------------------------------------------


class TestMCPCatalogConsistency:
    """Verify tool catalog stays consistent through server lifecycle."""

    async def test_tools_appear_after_server_registration(self, http: httpx.AsyncClient, mcp_url):
        """Registering a server with tools should make them searchable."""
        ns = f"catalog-{uuid.uuid4().hex[:8]}"
        unique_tool = f"unique_tool_{uuid.uuid4().hex[:8]}"

        await http.post(
            f"{mcp_url}/api/v1/servers",
            json={
                "name": f"catalog-server-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "endpoint": "http://catalog.example.com/mcp",
                "transport": "stdio",
                "tools": [
                    {
                        "name": unique_tool,
                        "description": "A uniquely named tool for search testing",
                        "parameters": [],
                        "tags": ["catalog-test"],
                    },
                ],
            },
        )

        # Search for the unique tool
        search = await http.get(f"{mcp_url}/api/v1/tools/search?q={unique_tool}")
        assert search.status_code == 200
        tools = search.json()
        assert any(t["name"] == unique_tool for t in tools), \
            f"Tool {unique_tool} not found in search results"

    async def test_tools_removed_when_server_deleted(self, http: httpx.AsyncClient, mcp_url):
        """Deleting a server should remove its tools from the catalog."""
        ns = f"del-catalog-{uuid.uuid4().hex[:8]}"
        tool_name = f"ephemeral_tool_{uuid.uuid4().hex[:8]}"

        create = await http.post(
            f"{mcp_url}/api/v1/servers",
            json={
                "name": f"ephemeral-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "endpoint": "http://ephemeral.example.com/mcp",
                "transport": "stdio",
                "tools": [
                    {
                        "name": tool_name,
                        "description": "Will be deleted",
                        "parameters": [],
                    },
                ],
            },
        )
        server_id = create.json()["id"]

        # Verify tool exists
        search1 = await http.get(f"{mcp_url}/api/v1/tools/search?q={tool_name}")
        assert any(t["name"] == tool_name for t in search1.json())

        # Delete server
        await http.delete(f"{mcp_url}/api/v1/servers/{server_id}")

        # Verify tool gone
        search2 = await http.get(f"{mcp_url}/api/v1/tools/search?q={tool_name}")
        assert not any(t["name"] == tool_name for t in search2.json())


# ---------------------------------------------------------------------------
# Multi-tenant isolation
# ---------------------------------------------------------------------------


class TestMultiTenantIsolation:
    """Verify tenant isolation across services."""

    async def test_gateway_tracks_tenants_independently(self, http: httpx.AsyncClient, gateway_url):
        """Each tenant's usage should be tracked separately."""
        tenant_a = f"tenant-a-{uuid.uuid4().hex[:8]}"
        tenant_b = f"tenant-b-{uuid.uuid4().hex[:8]}"

        # Tenant A makes 2 requests
        for _ in range(2):
            await http.post(
                f"{gateway_url}/v1/chat/completions",
                json={"model": "mock-model", "messages": [{"role": "user", "content": "hi"}]},
                headers={"x-tenant-id": tenant_a},
            )

        # Tenant B makes 1 request
        await http.post(
            f"{gateway_url}/v1/chat/completions",
            json={"model": "mock-model", "messages": [{"role": "user", "content": "hi"}]},
            headers={"x-tenant-id": tenant_b},
        )

        usage_a = (await http.get(f"{gateway_url}/v1/usage/{tenant_a}")).json()
        usage_b = (await http.get(f"{gateway_url}/v1/usage/{tenant_b}")).json()

        assert usage_a["request_count"] == 2
        assert usage_b["request_count"] == 1

    async def test_tenant_service_org_isolation(self, http: httpx.AsyncClient, tenant_url):
        """Different organizations should not see each other's teams."""
        suffix = uuid.uuid4().hex[:8]

        # Create two orgs
        org1 = (await http.post(
            f"{tenant_url}/api/v1/orgs",
            json={
                "name": f"iso-org-1-{suffix}",
                "slug": f"iso-org-1-{suffix}",
                "contact_email": f"iso1-{suffix}@example.com",
            },
        )).json()
        org2 = (await http.post(
            f"{tenant_url}/api/v1/orgs",
            json={
                "name": f"iso-org-2-{suffix}",
                "slug": f"iso-org-2-{suffix}",
                "contact_email": f"iso2-{suffix}@example.com",
            },
        )).json()

        # Create a team in org1
        team_slug = f"team-{suffix}"
        await http.post(
            f"{tenant_url}/api/v1/orgs/{org1['id']}/teams",
            json={"name": f"team-{suffix}", "slug": team_slug},
        )

        # List teams in org2 — should NOT include org1's team
        teams2 = (await http.get(f"{tenant_url}/api/v1/orgs/{org2['id']}/teams")).json()
        assert not any(t["slug"] == team_slug for t in teams2)


# ---------------------------------------------------------------------------
# End-to-end: Full platform flow
# ---------------------------------------------------------------------------


class TestEndToEndFlow:
    """Full platform flow spanning multiple services."""

    async def test_gateway_chat_completion(self, http: httpx.AsyncClient, gateway_url):
        """Verify gateway can proxy chat completions to mock-llm."""
        resp = await http.post(
            f"{gateway_url}/v1/chat/completions",
            json={
                "model": "mock-model",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "What is the capital of France?"},
                ],
            },
            headers={"x-tenant-id": "e2e-test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["choices"]) > 0
        assert data["choices"][0]["message"]["content"]  # non-empty response

    async def test_governance_then_workflow(self, http: httpx.AsyncClient, governance_url, engine_url):
        """Create governance policy, then run a workflow — both services must work."""
        ns = f"e2e-{uuid.uuid4().hex[:8]}"

        # Create a policy
        await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": f"e2e-policy-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "policy_type": "content_filter",
                "action": "warn",
                "rules": {"blocked_patterns": ["test"]},
            },
        )

        # Verify policy evaluates
        eval_resp = await http.post(
            f"{governance_url}/api/v1/evaluate",
            json={"namespace": ns, "content": "test content", "agent_name": "a"},
        )
        assert eval_resp.status_code == 200
        assert eval_resp.json()["allowed"] is True  # warn doesn't block

        # Run a workflow
        wf_name = f"e2e-wf-{uuid.uuid4().hex[:8]}"
        run_resp = await http.post(
            f"{engine_url}/workflows/run",
            json={
                "workflow_yaml": _make_workflow_yaml(wf_name),
                "input_data": {"message": "End to end test"},
            },
        )
        assert run_resp.status_code == 200
        data = run_resp.json()
        assert "run_id" in data
