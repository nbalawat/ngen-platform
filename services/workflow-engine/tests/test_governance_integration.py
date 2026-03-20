"""End-to-end tests for governance integration in the workflow engine.

These tests wire the governance policy engine directly into the workflow
engine and verify that policies are enforced during workflow execution.
No mocks — real governance engine, real workflow engine, real ASGI transport.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from governance_service.engine import PolicyEngine
from governance_service.models import PolicyCreate
from governance_service.repository import PolicyRepository

from ngen_framework_core.executor import AgentExecutor
from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    StateSnapshot,
)
from ngen_framework_core.registry import AdapterRegistry

from workflow_engine.app import create_app
from workflow_engine.governance import GovernanceGuard

# ---------------------------------------------------------------------------
# InMemoryAdapter (same as conftest — avoids import issues)
# ---------------------------------------------------------------------------


class InMemoryAdapter:
    def __init__(self) -> None:
        self._agents: dict[str, AgentSpec] = {}

    @property
    def name(self) -> str:
        return "in-memory"

    async def create_agent(self, spec: AgentSpec) -> str:
        self._agents[spec.name] = spec
        return spec.name

    async def execute(self, agent: str, input: AgentInput) -> AsyncIterator[AgentEvent]:
        spec = self._agents.get(agent)
        agent_name = spec.name if spec else agent
        yield AgentEvent(type=AgentEventType.THINKING, data={"text": f"Agent '{agent_name}' thinking..."}, agent_name=agent_name, timestamp=time.time())
        yield AgentEvent(type=AgentEventType.TEXT_DELTA, data={"text": f"Output from {agent_name}"}, agent_name=agent_name, timestamp=time.time())
        yield AgentEvent(type=AgentEventType.DONE, data={}, agent_name=agent_name, timestamp=time.time())

    async def checkpoint(self, agent: str) -> StateSnapshot:
        return StateSnapshot(agent_name=agent, state={})

    async def restore(self, agent: str, snapshot: StateSnapshot) -> None:
        pass

    async def teardown(self, agent: str) -> None:
        self._agents.pop(agent, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEQUENTIAL_WORKFLOW = """
apiVersion: ngen.io/v1
kind: Workflow
metadata:
  name: governed-workflow
  namespace: test-ns
spec:
  topology: sequential
  agents:
    - ref: researcher
    - ref: writer
"""


def _make_app(policies: list[dict[str, Any]] | None = None):
    """Create a workflow app with governance guard and optional policies."""
    repo = PolicyRepository()
    engine = PolicyEngine(repo)
    guard = GovernanceGuard(engine=engine, namespace="test-ns")

    if policies:
        for p in policies:
            repo.create(PolicyCreate(**p))

    # Set up real adapter + executor
    adapter = InMemoryAdapter()
    registry = AdapterRegistry()
    registry.register(adapter)
    executor = AgentExecutor(registry=registry)

    return create_app(
        executor=executor,
        default_framework="in-memory",
        governance_guard=guard,
    ), repo, engine


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGovernanceBlocksInput:
    """Test that governance can block workflow execution based on input content."""

    async def test_blocked_content_prevents_execution(self):
        app, _, _ = _make_app(policies=[
            {
                "name": "no-harmful-content",
                "policy_type": "content_filter",
                "namespace": "test-ns",
                "action": "block",
                "severity": "critical",
                "rules": {"blocked_topics": ["hack", "exploit"]},
            },
        ])

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wf") as client:
            resp = await client.post("/workflows/run", json={
                "workflow_yaml": SEQUENTIAL_WORKFLOW,
                "input_data": {"query": "How to hack a system"},
            })
            assert resp.status_code == 200
            data = resp.json()

            # Should have guardrail trigger events
            guardrail_events = [
                e for e in data["events"]
                if e["type"] == "guardrail_trigger"
            ]
            assert len(guardrail_events) > 0
            assert guardrail_events[0]["data"]["action"] == "block"
            assert guardrail_events[0]["data"]["phase"] == "pre_execution"

            # Should have an error event about governance blocking
            error_events = [e for e in data["events"] if e["type"] == "error"]
            assert any("governance" in e["data"].get("error", "").lower() for e in error_events)

            # Run should be failed
            assert data["status"] == "failed"

    async def test_clean_content_passes_through(self):
        app, _, _ = _make_app(policies=[
            {
                "name": "content-guard",
                "policy_type": "content_filter",
                "namespace": "test-ns",
                "action": "block",
                "rules": {"blocked_topics": ["harmful"]},
            },
        ])

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wf") as client:
            resp = await client.post("/workflows/run", json={
                "workflow_yaml": SEQUENTIAL_WORKFLOW,
                "input_data": {"query": "Summarize Q4 revenue"},
            })
            data = resp.json()
            assert data["status"] == "completed"

            # No guardrail triggers
            guardrail_events = [
                e for e in data["events"]
                if e["type"] == "guardrail_trigger"
            ]
            assert len(guardrail_events) == 0


class TestGovernanceWarnings:
    """Test that warn-level policies allow execution but emit events."""

    async def test_warn_policy_allows_but_emits_events(self):
        app, _, _ = _make_app(policies=[
            {
                "name": "caution-flag",
                "policy_type": "content_filter",
                "namespace": "test-ns",
                "action": "warn",
                "severity": "low",
                "rules": {"blocked_topics": ["sensitive"]},
            },
        ])

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wf") as client:
            resp = await client.post("/workflows/run", json={
                "workflow_yaml": SEQUENTIAL_WORKFLOW,
                "input_data": {"query": "Handle sensitive data"},
            })
            data = resp.json()

            # Should complete successfully
            assert data["status"] == "completed"

            # But should have warning guardrail events
            guardrail_events = [
                e for e in data["events"]
                if e["type"] == "guardrail_trigger"
            ]
            assert len(guardrail_events) > 0
            assert guardrail_events[0]["data"]["action"] == "warn"


class TestGovernanceCostLimits:
    """Test cost limit enforcement during execution."""

    async def test_cost_limit_on_input(self):
        app, _, _ = _make_app(policies=[
            {
                "name": "cost-cap",
                "policy_type": "cost_limit",
                "namespace": "test-ns",
                "action": "block",
                "rules": {"max_tokens_per_request": 10},
            },
        ])

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wf") as client:
            # Cost limit policies won't trigger on input because token_count
            # isn't in the input context — they're designed for runtime checks
            resp = await client.post("/workflows/run", json={
                "workflow_yaml": SEQUENTIAL_WORKFLOW,
                "input_data": {"query": "Short query"},
            })
            data = resp.json()
            # Should complete because token_count not provided in input context
            assert data["status"] == "completed"


class TestGovernanceOutputFiltering:
    """Test that governance checks agent output content."""

    async def test_output_content_filter(self):
        app, _, _ = _make_app(policies=[
            {
                "name": "output-filter",
                "policy_type": "content_filter",
                "namespace": "test-ns",
                "action": "warn",
                "rules": {"blocked_patterns": [r"Output from"]},
            },
        ])

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wf") as client:
            resp = await client.post("/workflows/run", json={
                "workflow_yaml": SEQUENTIAL_WORKFLOW,
                "input_data": {"query": "Test output filtering"},
            })
            data = resp.json()

            # Output from InMemoryAdapter contains "Processed:" which matches pattern
            guardrail_events = [
                e for e in data["events"]
                if e["type"] == "guardrail_trigger"
                and e["data"].get("phase") == "post_execution"
            ]
            # Should have output-phase guardrail triggers
            assert len(guardrail_events) > 0


class TestGovernanceNamespaceIsolation:
    """Test that policies only apply in their namespace."""

    async def test_different_namespace_not_enforced(self):
        app, _, _ = _make_app(policies=[
            {
                "name": "ns-specific",
                "policy_type": "content_filter",
                "namespace": "other-ns",
                "action": "block",
                "rules": {"blocked_topics": ["everything"]},
            },
        ])

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wf") as client:
            resp = await client.post("/workflows/run", json={
                "workflow_yaml": SEQUENTIAL_WORKFLOW,
                "input_data": {"query": "everything is fine"},
            })
            data = resp.json()

            # Policy is in "other-ns" but workflow is in "test-ns" — no enforcement
            assert data["status"] == "completed"
            guardrail_events = [
                e for e in data["events"]
                if e["type"] == "guardrail_trigger"
            ]
            assert len(guardrail_events) == 0


class TestGovernanceDisabledPolicies:
    """Test that disabled policies are not enforced."""

    async def test_disabled_policy_skipped(self):
        app, repo, _ = _make_app(policies=[
            {
                "name": "disabled-policy",
                "policy_type": "content_filter",
                "namespace": "test-ns",
                "action": "block",
                "rules": {"blocked_topics": ["everything"]},
                "enabled": False,
            },
        ])

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wf") as client:
            resp = await client.post("/workflows/run", json={
                "workflow_yaml": SEQUENTIAL_WORKFLOW,
                "input_data": {"query": "everything works"},
            })
            data = resp.json()
            assert data["status"] == "completed"


class TestNoGovernance:
    """Test that workflows work fine without governance configured."""

    async def test_no_guard_configured(self):
        adapter = InMemoryAdapter()
        registry = AdapterRegistry()
        registry.register(adapter)
        executor = AgentExecutor(registry=registry)
        app = create_app(executor=executor, default_framework="in-memory")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wf") as client:
            resp = await client.post("/workflows/run", json={
                "workflow_yaml": SEQUENTIAL_WORKFLOW,
                "input_data": {"query": "Normal query"},
            })
            data = resp.json()
            assert data["status"] == "completed"


class TestMultiplePolicies:
    """Test enforcement of multiple policies simultaneously."""

    async def test_multiple_policies_all_enforced(self):
        app, _, _ = _make_app(policies=[
            {
                "name": "content-guard",
                "policy_type": "content_filter",
                "namespace": "test-ns",
                "action": "block",
                "severity": "high",
                "rules": {"blocked_topics": ["forbidden"]},
            },
            {
                "name": "cost-guard",
                "policy_type": "cost_limit",
                "namespace": "test-ns",
                "action": "warn",
                "rules": {"max_cost_per_request": 0.01},
            },
        ])

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wf") as client:
            resp = await client.post("/workflows/run", json={
                "workflow_yaml": SEQUENTIAL_WORKFLOW,
                "input_data": {"query": "forbidden content here"},
            })
            data = resp.json()

            # Content filter should block
            assert data["status"] == "failed"
            guardrail_events = [
                e for e in data["events"]
                if e["type"] == "guardrail_trigger"
            ]
            assert any(e["data"]["policy_name"] == "content-guard" for e in guardrail_events)


class TestGovernanceSSEStream:
    """Test that governance events appear in SSE streams."""

    async def test_guardrail_events_in_sse_stream(self):
        app, _, _ = _make_app(policies=[
            {
                "name": "stream-guard",
                "policy_type": "content_filter",
                "namespace": "test-ns",
                "action": "warn",
                "rules": {"blocked_topics": ["caution"]},
            },
        ])

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://wf") as client:
            events = []
            async with client.stream("POST", "/workflows/run/stream", json={
                "workflow_yaml": SEQUENTIAL_WORKFLOW,
                "input_data": {"query": "exercise caution please"},
            }) as resp:
                current_event = None
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("event: "):
                        current_event = line[7:]
                    elif line.startswith("data: "):
                        data = json.loads(line[6:])
                        events.append({"event": current_event, "data": data})
                        current_event = None

            # Should have guardrail_trigger events in the stream
            guardrail_sse = [e for e in events if e["event"] == "guardrail_trigger"]
            assert len(guardrail_sse) > 0

            # Should also complete successfully (warn, not block)
            done_events = [
                e for e in events
                if e["event"] == "done" and e["data"].get("run_id")
            ]
            assert len(done_events) == 1
            assert done_events[0]["data"]["status"] == "completed"
