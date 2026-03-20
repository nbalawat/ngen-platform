"""Tests for the NGEN SDK governance client.

Validates the SDK can create, list, evaluate, and manage policies
through the real governance service.
"""

from __future__ import annotations


class TestGovernanceSDK:
    async def test_create_and_list_policies(self, governance_client):
        client = governance_client
        policy = await client.governance.create_policy({
            "name": "sdk-test-policy",
            "policy_type": "content_filter",
            "namespace": "sdk-ns",
            "rules": {"blocked_topics": ["forbidden"]},
        })
        assert policy["name"] == "sdk-test-policy"
        assert policy["id"]

        policies = await client.governance.list_policies(namespace="sdk-ns")
        assert len(policies) == 1

    async def test_get_policy(self, governance_client):
        client = governance_client
        created = await client.governance.create_policy({
            "name": "get-test-policy",
            "policy_type": "cost_limit",
            "rules": {"max_cost_per_request": 1.0},
        })
        policy = await client.governance.get_policy(created["id"])
        assert policy["name"] == "get-test-policy"

    async def test_update_policy(self, governance_client):
        client = governance_client
        created = await client.governance.create_policy({
            "name": "update-test",
            "policy_type": "content_filter",
            "action": "warn",
            "rules": {},
        })
        updated = await client.governance.update_policy(
            created["id"], {"action": "block"}
        )
        assert updated["action"] == "block"

    async def test_delete_policy(self, governance_client):
        client = governance_client
        created = await client.governance.create_policy({
            "name": "delete-test",
            "policy_type": "content_filter",
            "rules": {},
        })
        await client.governance.delete_policy(created["id"])
        policies = await client.governance.list_policies()
        assert len(policies) == 0

    async def test_evaluate_blocked(self, governance_client):
        client = governance_client
        await client.governance.create_policy({
            "name": "blocker",
            "policy_type": "content_filter",
            "action": "block",
            "rules": {"blocked_topics": ["secret"]},
        })
        result = await client.governance.evaluate({
            "content": "This is a secret document",
        })
        assert result["allowed"] is False
        assert len(result["violations"]) == 1

    async def test_evaluate_allowed(self, governance_client):
        client = governance_client
        await client.governance.create_policy({
            "name": "harmless",
            "policy_type": "content_filter",
            "action": "block",
            "rules": {"blocked_topics": ["danger"]},
        })
        result = await client.governance.evaluate({
            "content": "Please summarize this report",
        })
        assert result["allowed"] is True
