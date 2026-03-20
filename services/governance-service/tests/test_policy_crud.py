"""Tests for governance policy CRUD operations."""

from __future__ import annotations


class TestPolicyCreate:
    async def test_create_content_filter(self, client):
        resp = await client.post("/api/v1/policies", json={
            "name": "no-pii-output",
            "description": "Block PII in agent outputs",
            "policy_type": "content_filter",
            "namespace": "acme-corp",
            "action": "block",
            "severity": "high",
            "rules": {
                "blocked_patterns": [r"\b\d{3}-\d{2}-\d{4}\b", r"\b\d{16}\b"],
                "blocked_topics": ["social security"],
            },
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "no-pii-output"
        assert data["policy_type"] == "content_filter"
        assert data["namespace"] == "acme-corp"
        assert data["enabled"] is True
        assert "id" in data

    async def test_create_cost_limit(self, client):
        resp = await client.post("/api/v1/policies", json={
            "name": "budget-cap",
            "policy_type": "cost_limit",
            "rules": {
                "max_cost_per_request": 0.50,
                "max_tokens_per_request": 10000,
                "daily_budget": 100.0,
            },
        })
        assert resp.status_code == 201
        assert resp.json()["policy_type"] == "cost_limit"

    async def test_create_tool_restriction(self, client):
        resp = await client.post("/api/v1/policies", json={
            "name": "safe-tools-only",
            "policy_type": "tool_restriction",
            "action": "block",
            "rules": {
                "blocked_tools": ["shell-exec", "file-delete"],
                "require_approval": ["database-write"],
            },
        })
        assert resp.status_code == 201

    async def test_create_rate_limit(self, client):
        resp = await client.post("/api/v1/policies", json={
            "name": "api-throttle",
            "policy_type": "rate_limit",
            "action": "block",
            "rules": {
                "max_requests_per_minute": 60,
                "max_requests_per_hour": 1000,
            },
        })
        assert resp.status_code == 201

    async def test_duplicate_name_returns_409(self, client):
        body = {
            "name": "unique-policy",
            "policy_type": "content_filter",
            "namespace": "default",
            "rules": {},
        }
        resp1 = await client.post("/api/v1/policies", json=body)
        assert resp1.status_code == 201
        resp2 = await client.post("/api/v1/policies", json=body)
        assert resp2.status_code == 409

    async def test_duplicate_name_different_namespace_ok(self, client):
        body = {
            "name": "shared-name",
            "policy_type": "content_filter",
            "rules": {},
        }
        resp1 = await client.post("/api/v1/policies", json={**body, "namespace": "ns-a"})
        assert resp1.status_code == 201
        resp2 = await client.post("/api/v1/policies", json={**body, "namespace": "ns-b"})
        assert resp2.status_code == 201


class TestPolicyRead:
    async def test_list_empty(self, client):
        resp = await client.get("/api/v1/policies")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_namespace_filter(self, client):
        for i, ns in enumerate(["alpha", "beta", "alpha"]):
            await client.post("/api/v1/policies", json={
                "name": f"policy-{ns}-{i}",
                "policy_type": "content_filter",
                "namespace": ns,
                "rules": {},
            })
        resp = await client.get("/api/v1/policies?namespace=alpha")
        assert resp.status_code == 200
        policies = resp.json()
        assert len(policies) == 2
        assert all(p["namespace"] == "alpha" for p in policies)

    async def test_list_with_type_filter(self, client):
        await client.post("/api/v1/policies", json={
            "name": "cf-policy",
            "policy_type": "content_filter",
            "rules": {},
        })
        await client.post("/api/v1/policies", json={
            "name": "cl-policy",
            "policy_type": "cost_limit",
            "rules": {},
        })
        resp = await client.get("/api/v1/policies?type=cost_limit")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["policy_type"] == "cost_limit"

    async def test_get_by_id(self, client):
        created = (await client.post("/api/v1/policies", json={
            "name": "get-test",
            "policy_type": "content_filter",
            "rules": {},
        })).json()
        resp = await client.get(f"/api/v1/policies/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-test"

    async def test_get_not_found(self, client):
        resp = await client.get("/api/v1/policies/nonexistent-id")
        assert resp.status_code == 404

    async def test_get_by_name(self, client):
        await client.post("/api/v1/policies", json={
            "name": "named-policy",
            "policy_type": "cost_limit",
            "namespace": "test-ns",
            "rules": {},
        })
        resp = await client.get("/api/v1/policies/by-name/named-policy?namespace=test-ns")
        assert resp.status_code == 200
        assert resp.json()["name"] == "named-policy"

    async def test_get_by_name_not_found(self, client):
        resp = await client.get("/api/v1/policies/by-name/nope")
        assert resp.status_code == 404


class TestPolicyUpdate:
    async def test_update_fields(self, client):
        created = (await client.post("/api/v1/policies", json={
            "name": "updatable",
            "policy_type": "content_filter",
            "action": "warn",
            "rules": {"blocked_topics": ["pii"]},
        })).json()

        resp = await client.patch(f"/api/v1/policies/{created['id']}", json={
            "action": "block",
            "severity": "critical",
            "rules": {"blocked_topics": ["pii", "secrets"]},
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["action"] == "block"
        assert updated["severity"] == "critical"
        assert "secrets" in updated["rules"]["blocked_topics"]

    async def test_disable_policy(self, client):
        created = (await client.post("/api/v1/policies", json={
            "name": "toggle-me",
            "policy_type": "content_filter",
            "rules": {},
        })).json()
        resp = await client.patch(f"/api/v1/policies/{created['id']}", json={
            "enabled": False,
        })
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_update_not_found(self, client):
        resp = await client.patch("/api/v1/policies/bad-id", json={"action": "log"})
        assert resp.status_code == 404


class TestPolicyDelete:
    async def test_delete(self, client):
        created = (await client.post("/api/v1/policies", json={
            "name": "delete-me",
            "policy_type": "content_filter",
            "rules": {},
        })).json()
        resp = await client.delete(f"/api/v1/policies/{created['id']}")
        assert resp.status_code == 204

        get_resp = await client.get(f"/api/v1/policies/{created['id']}")
        assert get_resp.status_code == 404

    async def test_delete_not_found(self, client):
        resp = await client.delete("/api/v1/policies/bad-id")
        assert resp.status_code == 404
