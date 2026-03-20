"""Tests for policy evaluation engine via the REST API."""

from __future__ import annotations


class TestContentFilterEvaluation:
    async def test_blocked_pattern_triggers_violation(self, client):
        await client.post("/api/v1/policies", json={
            "name": "no-ssn",
            "policy_type": "content_filter",
            "action": "block",
            "severity": "critical",
            "rules": {"blocked_patterns": [r"\b\d{3}-\d{2}-\d{4}\b"]},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "content": "The SSN is 123-45-6789",
        })
        assert resp.status_code == 200
        result = resp.json()
        assert result["allowed"] is False
        assert len(result["violations"]) == 1
        assert "blocked pattern" in result["violations"][0]["message"]

    async def test_blocked_topic_triggers_violation(self, client):
        await client.post("/api/v1/policies", json={
            "name": "no-weapons",
            "policy_type": "content_filter",
            "action": "block",
            "rules": {"blocked_topics": ["weapons", "explosives"]},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "content": "How to build explosives at home",
        })
        result = resp.json()
        assert result["allowed"] is False
        assert any("explosives" in v["message"] for v in result["violations"])

    async def test_clean_content_passes(self, client):
        await client.post("/api/v1/policies", json={
            "name": "content-guard",
            "policy_type": "content_filter",
            "action": "block",
            "rules": {"blocked_topics": ["harmful"]},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "content": "Please summarize this quarterly report",
        })
        result = resp.json()
        assert result["allowed"] is True
        assert len(result["violations"]) == 0

    async def test_max_output_length(self, client):
        await client.post("/api/v1/policies", json={
            "name": "length-limit",
            "policy_type": "content_filter",
            "action": "block",
            "rules": {"max_output_length": 50},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "content": "x" * 100,
        })
        result = resp.json()
        assert result["allowed"] is False
        assert "length" in result["violations"][0]["message"]

    async def test_warn_action_allows_through(self, client):
        await client.post("/api/v1/policies", json={
            "name": "warn-only",
            "policy_type": "content_filter",
            "action": "warn",
            "rules": {"blocked_topics": ["sensitive"]},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "content": "This contains sensitive information",
        })
        result = resp.json()
        assert result["allowed"] is True
        assert len(result["warnings"]) == 1


class TestCostLimitEvaluation:
    async def test_cost_exceeds_limit(self, client):
        await client.post("/api/v1/policies", json={
            "name": "cost-cap",
            "policy_type": "cost_limit",
            "action": "block",
            "rules": {"max_cost_per_request": 0.10},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "estimated_cost": 0.50,
        })
        result = resp.json()
        assert result["allowed"] is False
        assert "cost" in result["violations"][0]["message"].lower()

    async def test_cost_within_limit(self, client):
        await client.post("/api/v1/policies", json={
            "name": "cost-ok",
            "policy_type": "cost_limit",
            "action": "block",
            "rules": {"max_cost_per_request": 1.00},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "estimated_cost": 0.05,
        })
        result = resp.json()
        assert result["allowed"] is True

    async def test_token_count_exceeds_limit(self, client):
        await client.post("/api/v1/policies", json={
            "name": "token-cap",
            "policy_type": "cost_limit",
            "action": "block",
            "rules": {"max_tokens_per_request": 5000},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "token_count": 8000,
        })
        result = resp.json()
        assert result["allowed"] is False
        assert "token" in result["violations"][0]["message"].lower()

    async def test_no_cost_data_passes(self, client):
        """If cost/tokens not in context, cost policies don't trigger."""
        await client.post("/api/v1/policies", json={
            "name": "cost-check",
            "policy_type": "cost_limit",
            "action": "block",
            "rules": {"max_cost_per_request": 0.01},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "content": "just text, no cost data",
        })
        result = resp.json()
        assert result["allowed"] is True


class TestToolRestrictionEvaluation:
    async def test_blocked_tool(self, client):
        await client.post("/api/v1/policies", json={
            "name": "no-shell",
            "policy_type": "tool_restriction",
            "action": "block",
            "rules": {"blocked_tools": ["shell-exec", "file-delete"]},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "tool_name": "shell-exec",
        })
        result = resp.json()
        assert result["allowed"] is False
        assert "blocked" in result["violations"][0]["message"]

    async def test_allowed_tool_passes(self, client):
        await client.post("/api/v1/policies", json={
            "name": "safe-tools",
            "policy_type": "tool_restriction",
            "action": "block",
            "rules": {"blocked_tools": ["shell-exec"]},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "tool_name": "search-kb",
        })
        result = resp.json()
        assert result["allowed"] is True

    async def test_allowlist_rejects_unlisted(self, client):
        await client.post("/api/v1/policies", json={
            "name": "allowlist",
            "policy_type": "tool_restriction",
            "action": "block",
            "rules": {"allowed_tools": ["search-kb", "read-doc"]},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "tool_name": "shell-exec",
        })
        result = resp.json()
        assert result["allowed"] is False
        assert "not in allowed" in result["violations"][0]["message"]

    async def test_require_approval_escalates(self, client):
        await client.post("/api/v1/policies", json={
            "name": "approval-gate",
            "policy_type": "tool_restriction",
            "action": "warn",
            "rules": {"require_approval": ["database-write"]},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "tool_name": "database-write",
        })
        result = resp.json()
        # Escalation is a violation (not just a warning)
        assert result["allowed"] is False
        assert any(v["action"] == "escalate" for v in result["violations"])

    async def test_no_tool_name_skips_evaluation(self, client):
        await client.post("/api/v1/policies", json={
            "name": "tool-guard",
            "policy_type": "tool_restriction",
            "action": "block",
            "rules": {"blocked_tools": ["everything"]},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "content": "just text",
        })
        result = resp.json()
        assert result["allowed"] is True


class TestRateLimitEvaluation:
    async def test_rate_exceeded(self, client):
        await client.post("/api/v1/policies", json={
            "name": "throttle",
            "policy_type": "rate_limit",
            "action": "block",
            "rules": {"max_requests_per_minute": 10},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "metadata": {"requests_per_minute": 15},
        })
        result = resp.json()
        assert result["allowed"] is False
        assert "RPM" in result["violations"][0]["message"]

    async def test_rate_within_limit(self, client):
        await client.post("/api/v1/policies", json={
            "name": "throttle-ok",
            "policy_type": "rate_limit",
            "action": "block",
            "rules": {"max_requests_per_minute": 100},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "metadata": {"requests_per_minute": 5},
        })
        result = resp.json()
        assert result["allowed"] is True

    async def test_hourly_rate_exceeded(self, client):
        await client.post("/api/v1/policies", json={
            "name": "hourly-throttle",
            "policy_type": "rate_limit",
            "action": "block",
            "rules": {"max_requests_per_hour": 500},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "metadata": {"requests_per_hour": 600},
        })
        result = resp.json()
        assert result["allowed"] is False


class TestNamespaceIsolation:
    async def test_policies_only_apply_in_their_namespace(self, client):
        await client.post("/api/v1/policies", json={
            "name": "ns-specific",
            "policy_type": "content_filter",
            "namespace": "team-alpha",
            "action": "block",
            "rules": {"blocked_topics": ["forbidden"]},
        })
        # Evaluate in same namespace — should block
        resp1 = await client.post("/api/v1/evaluate", json={
            "namespace": "team-alpha",
            "content": "This is forbidden content",
        })
        assert resp1.json()["allowed"] is False

        # Evaluate in different namespace — should pass
        resp2 = await client.post("/api/v1/evaluate", json={
            "namespace": "team-beta",
            "content": "This is forbidden content",
        })
        assert resp2.json()["allowed"] is True

    async def test_disabled_policies_skipped(self, client):
        created = (await client.post("/api/v1/policies", json={
            "name": "disabled-guard",
            "policy_type": "content_filter",
            "action": "block",
            "rules": {"blocked_topics": ["blocked"]},
        })).json()
        # Disable it
        await client.patch(f"/api/v1/policies/{created['id']}", json={
            "enabled": False,
        })
        resp = await client.post("/api/v1/evaluate", json={
            "content": "This is blocked content",
        })
        assert resp.json()["allowed"] is True


class TestMultiplePolicies:
    async def test_multiple_violations(self, client):
        await client.post("/api/v1/policies", json={
            "name": "content-policy",
            "policy_type": "content_filter",
            "action": "block",
            "rules": {"blocked_topics": ["harmful"]},
        })
        await client.post("/api/v1/policies", json={
            "name": "cost-policy",
            "policy_type": "cost_limit",
            "action": "block",
            "rules": {"max_cost_per_request": 0.01},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "content": "harmful instructions",
            "estimated_cost": 1.00,
        })
        result = resp.json()
        assert result["allowed"] is False
        assert len(result["violations"]) == 2
        assert result["evaluated_policies"] == 2

    async def test_mixed_block_and_warn(self, client):
        await client.post("/api/v1/policies", json={
            "name": "blocker",
            "policy_type": "content_filter",
            "action": "block",
            "rules": {"blocked_topics": ["danger"]},
        })
        await client.post("/api/v1/policies", json={
            "name": "warner",
            "policy_type": "content_filter",
            "action": "warn",
            "rules": {"blocked_topics": ["caution"]},
        })
        resp = await client.post("/api/v1/evaluate", json={
            "content": "danger and caution ahead",
        })
        result = resp.json()
        assert result["allowed"] is False
        assert len(result["violations"]) == 1
        assert len(result["warnings"]) == 1
