"""Integration tests: governance service — policy CRUD and evaluation.

Tests the full governance lifecycle: create policies, evaluate inputs
against them, verify block/warn/log/escalate actions.
"""

from __future__ import annotations

import uuid

import httpx
import pytest


# ---------------------------------------------------------------------------
# Policy CRUD
# ---------------------------------------------------------------------------


class TestGovernancePolicyCRUD:
    """Full policy lifecycle in the governance service."""

    async def test_create_content_filter_policy(self, http: httpx.AsyncClient, governance_url):
        name = f"content-filter-{uuid.uuid4().hex[:8]}"
        resp = await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": name,
                "namespace": "integration-test",
                "policy_type": "content_filter",
                "action": "block",
                "rules": {"blocked_patterns": ["password", "secret", "api_key"]},
            },
        )
        assert resp.status_code == 201, f"Create policy failed: {resp.text}"
        data = resp.json()
        assert data["name"] == name
        assert data["policy_type"] == "content_filter"
        assert data["enabled"] is True

    async def test_list_policies(self, http: httpx.AsyncClient, governance_url):
        resp = await http.get(f"{governance_url}/api/v1/policies")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_list_policies_by_namespace(self, http: httpx.AsyncClient, governance_url):
        ns = f"ns-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": f"ns-policy-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "policy_type": "content_filter",
                "action": "warn",
                "rules": {"blocked_patterns": ["test"]},
            },
        )
        resp = await http.get(f"{governance_url}/api/v1/policies?namespace={ns}")
        assert resp.status_code == 200
        policies = resp.json()
        assert all(p["namespace"] == ns for p in policies)

    async def test_get_policy_by_id(self, http: httpx.AsyncClient, governance_url):
        name = f"get-policy-{uuid.uuid4().hex[:8]}"
        create = await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": name,
                "namespace": "default",
                "policy_type": "cost_limit",
                "action": "warn",
                "rules": {"max_cost_per_request": 1.0},
            },
        )
        policy_id = create.json()["id"]

        resp = await http.get(f"{governance_url}/api/v1/policies/{policy_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == name

    async def test_update_policy(self, http: httpx.AsyncClient, governance_url):
        name = f"update-policy-{uuid.uuid4().hex[:8]}"
        create = await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": name,
                "namespace": "default",
                "policy_type": "content_filter",
                "action": "warn",
                "rules": {"blocked_patterns": ["old"]},
            },
        )
        policy_id = create.json()["id"]

        resp = await http.patch(
            f"{governance_url}/api/v1/policies/{policy_id}",
            json={
                "action": "block",
                "rules": {"blocked_patterns": ["old", "new"]},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["action"] == "block"

    async def test_delete_policy(self, http: httpx.AsyncClient, governance_url):
        name = f"del-policy-{uuid.uuid4().hex[:8]}"
        create = await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": name,
                "namespace": "default",
                "policy_type": "content_filter",
                "action": "log",
                "rules": {"blocked_patterns": ["tmp"]},
            },
        )
        policy_id = create.json()["id"]

        resp = await http.delete(f"{governance_url}/api/v1/policies/{policy_id}")
        assert resp.status_code == 204

        get_resp = await http.get(f"{governance_url}/api/v1/policies/{policy_id}")
        assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Policy Evaluation
# ---------------------------------------------------------------------------


class TestGovernanceEvaluation:
    """Test policy evaluation against real content."""

    async def test_content_filter_blocks(self, http: httpx.AsyncClient, governance_url):
        """Content filter should block input containing prohibited patterns."""
        ns = f"eval-block-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": f"block-policy-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "policy_type": "content_filter",
                "action": "block",
                "rules": {"blocked_patterns": ["confidential", "top_secret"]},
            },
        )

        resp = await http.post(
            f"{governance_url}/api/v1/evaluate",
            json={
                "namespace": ns,
                "content": "This document is confidential and should not be shared.",
                "agent_name": "test-agent",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is False
        assert len(data["violations"]) > 0
        assert any(v["action"] == "block" for v in data["violations"])

    async def test_content_filter_allows_clean_input(self, http: httpx.AsyncClient, governance_url):
        """Clean input should pass content filter evaluation."""
        ns = f"eval-allow-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": f"allow-policy-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "policy_type": "content_filter",
                "action": "block",
                "rules": {"blocked_patterns": ["forbidden_word"]},
            },
        )

        resp = await http.post(
            f"{governance_url}/api/v1/evaluate",
            json={
                "namespace": ns,
                "content": "This is a perfectly normal message about the weather.",
                "agent_name": "test-agent",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True
        assert len(data["violations"]) == 0

    async def test_content_filter_warns(self, http: httpx.AsyncClient, governance_url):
        """Warn action should flag but still allow the input."""
        ns = f"eval-warn-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": f"warn-policy-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "policy_type": "content_filter",
                "action": "warn",
                "rules": {"blocked_patterns": ["caution"]},
            },
        )

        resp = await http.post(
            f"{governance_url}/api/v1/evaluate",
            json={
                "namespace": ns,
                "content": "Please exercise caution with this data.",
                "agent_name": "test-agent",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True  # warn doesn't block
        assert len(data["warnings"]) > 0
        assert data["warnings"][0]["action"] == "warn"

    async def test_cost_limit_evaluation(self, http: httpx.AsyncClient, governance_url):
        """Cost limit should block when estimated cost exceeds threshold."""
        ns = f"eval-cost-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": f"cost-policy-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "policy_type": "cost_limit",
                "action": "block",
                "rules": {"max_cost_per_request": 0.01},
            },
        )

        resp = await http.post(
            f"{governance_url}/api/v1/evaluate",
            json={
                "namespace": ns,
                "content": "Generate a long essay",
                "agent_name": "test-agent",
                "estimated_cost": 5.00,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is False

    async def test_tool_restriction(self, http: httpx.AsyncClient, governance_url):
        """Tool restriction should block disallowed tools."""
        ns = f"eval-tool-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": f"tool-policy-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "policy_type": "tool_restriction",
                "action": "block",
                "rules": {"allowed_tools": ["search", "calculator"]},
            },
        )

        resp = await http.post(
            f"{governance_url}/api/v1/evaluate",
            json={
                "namespace": ns,
                "content": "Use the database tool",
                "agent_name": "test-agent",
                "tool_name": "database_admin",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is False

    async def test_namespace_isolation(self, http: httpx.AsyncClient, governance_url):
        """Policies in one namespace should not affect another."""
        ns_a = f"ns-a-{uuid.uuid4().hex[:8]}"
        ns_b = f"ns-b-{uuid.uuid4().hex[:8]}"

        # Create blocking policy in ns_a only
        await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": f"isolated-{uuid.uuid4().hex[:8]}",
                "namespace": ns_a,
                "policy_type": "content_filter",
                "action": "block",
                "rules": {"blocked_patterns": ["danger"]},
            },
        )

        # Evaluate in ns_a — should block
        resp_a = await http.post(
            f"{governance_url}/api/v1/evaluate",
            json={"namespace": ns_a, "content": "danger zone", "agent_name": "a"},
        )
        assert resp_a.json()["allowed"] is False

        # Evaluate same input in ns_b — should pass (no policies)
        resp_b = await http.post(
            f"{governance_url}/api/v1/evaluate",
            json={"namespace": ns_b, "content": "danger zone", "agent_name": "b"},
        )
        assert resp_b.json()["allowed"] is True

    async def test_disabled_policy_skipped(self, http: httpx.AsyncClient, governance_url):
        """Disabled policies should not be evaluated."""
        ns = f"eval-disabled-{uuid.uuid4().hex[:8]}"
        await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": f"disabled-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "policy_type": "content_filter",
                "action": "block",
                "rules": {"blocked_patterns": ["block_me"]},
                "enabled": False,
            },
        )

        resp = await http.post(
            f"{governance_url}/api/v1/evaluate",
            json={"namespace": ns, "content": "block_me please", "agent_name": "a"},
        )
        assert resp.json()["allowed"] is True

    async def test_multiple_policies_all_evaluated(self, http: httpx.AsyncClient, governance_url):
        """Multiple policies in the same namespace should all be checked."""
        ns = f"eval-multi-{uuid.uuid4().hex[:8]}"

        # Policy 1: warn on "caution"
        await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": f"multi-1-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "policy_type": "content_filter",
                "action": "warn",
                "rules": {"blocked_patterns": ["caution"]},
            },
        )
        # Policy 2: block on "forbidden"
        await http.post(
            f"{governance_url}/api/v1/policies",
            json={
                "name": f"multi-2-{uuid.uuid4().hex[:8]}",
                "namespace": ns,
                "policy_type": "content_filter",
                "action": "block",
                "rules": {"blocked_patterns": ["forbidden"]},
            },
        )

        # Input triggers both
        resp = await http.post(
            f"{governance_url}/api/v1/evaluate",
            json={
                "namespace": ns,
                "content": "Exercise caution, this is forbidden content.",
                "agent_name": "a",
            },
        )
        data = resp.json()
        assert data["allowed"] is False  # block wins
        # violations has blocks, warnings has warns
        assert len(data["violations"]) >= 1
        assert len(data["warnings"]) >= 1
