"""Tests for CLI governance policy commands against real governance service."""

from __future__ import annotations

import pytest


class TestPolicyCRUD:
    async def test_create_policy(self, governance_client):
        resp = await governance_client.post(
            "/api/v1/policies",
            json={
                "name": "test-filter",
                "policy_type": "content_filter",
                "namespace": "default",
                "action": "block",
                "severity": "high",
                "rules": {"blocked_patterns": ["secret"]},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-filter"
        assert data["policy_type"] == "content_filter"
        assert data["id"]

    async def test_list_policies(self, governance_client):
        # Create two policies
        await governance_client.post(
            "/api/v1/policies",
            json={
                "name": "policy-a",
                "policy_type": "content_filter",
                "action": "block",
                "rules": {"blocked_patterns": ["bad"]},
            },
        )
        await governance_client.post(
            "/api/v1/policies",
            json={
                "name": "policy-b",
                "policy_type": "cost_limit",
                "action": "warn",
                "rules": {"max_cost": 10.0},
            },
        )
        resp = await governance_client.get("/api/v1/policies")
        assert resp.status_code == 200
        policies = resp.json()
        assert len(policies) >= 2
        names = {p["name"] for p in policies}
        assert "policy-a" in names
        assert "policy-b" in names

    async def test_get_policy_by_id(self, governance_client):
        create_resp = await governance_client.post(
            "/api/v1/policies",
            json={
                "name": "get-test",
                "policy_type": "rate_limit",
                "action": "block",
                "rules": {"max_requests_per_minute": 100},
            },
        )
        policy_id = create_resp.json()["id"]

        resp = await governance_client.get(f"/api/v1/policies/{policy_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-test"

    async def test_delete_policy(self, governance_client):
        create_resp = await governance_client.post(
            "/api/v1/policies",
            json={
                "name": "delete-me",
                "policy_type": "content_filter",
                "action": "log",
                "rules": {"blocked_patterns": ["x"]},
            },
        )
        policy_id = create_resp.json()["id"]

        delete_resp = await governance_client.delete(f"/api/v1/policies/{policy_id}")
        assert delete_resp.status_code == 204

        get_resp = await governance_client.get(f"/api/v1/policies/{policy_id}")
        assert get_resp.status_code == 404

    async def test_list_by_namespace(self, governance_client):
        await governance_client.post(
            "/api/v1/policies",
            json={
                "name": "ns-alpha",
                "policy_type": "content_filter",
                "namespace": "alpha",
                "action": "block",
                "rules": {"blocked_patterns": ["x"]},
            },
        )
        await governance_client.post(
            "/api/v1/policies",
            json={
                "name": "ns-beta",
                "policy_type": "content_filter",
                "namespace": "beta",
                "action": "block",
                "rules": {"blocked_patterns": ["y"]},
            },
        )

        resp = await governance_client.get("/api/v1/policies", params={"namespace": "alpha"})
        assert resp.status_code == 200
        policies = resp.json()
        assert all(p["namespace"] == "alpha" for p in policies)


class TestPolicyEvaluation:
    async def test_evaluate_blocked(self, governance_client):
        await governance_client.post(
            "/api/v1/policies",
            json={
                "name": "block-secrets",
                "policy_type": "content_filter",
                "action": "block",
                "severity": "critical",
                "rules": {"blocked_patterns": ["password"]},
            },
        )

        resp = await governance_client.post(
            "/api/v1/evaluate",
            json={
                "content": "my password is 1234",
                "namespace": "default",
            },
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["allowed"] is False
        assert len(result["violations"]) >= 1

    async def test_evaluate_allowed(self, governance_client):
        await governance_client.post(
            "/api/v1/policies",
            json={
                "name": "harmless-filter",
                "policy_type": "content_filter",
                "action": "block",
                "rules": {"blocked_patterns": ["toxic"]},
            },
        )

        resp = await governance_client.post(
            "/api/v1/evaluate",
            json={
                "content": "hello world",
                "namespace": "default",
            },
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["allowed"] is True

    async def test_evaluate_with_cost_limit(self, governance_client):
        await governance_client.post(
            "/api/v1/policies",
            json={
                "name": "cost-guard",
                "policy_type": "cost_limit",
                "action": "block",
                "rules": {"max_cost_per_request": 5.0},
            },
        )

        resp = await governance_client.post(
            "/api/v1/evaluate",
            json={
                "estimated_cost": 10.0,
                "namespace": "default",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False

    async def test_evaluate_warn_action(self, governance_client):
        await governance_client.post(
            "/api/v1/policies",
            json={
                "name": "warn-filter",
                "policy_type": "content_filter",
                "action": "warn",
                "rules": {"blocked_patterns": ["caution"]},
            },
        )

        resp = await governance_client.post(
            "/api/v1/evaluate",
            json={
                "content": "exercise caution",
                "namespace": "default",
            },
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["allowed"] is True
        assert len(result["warnings"]) >= 1
