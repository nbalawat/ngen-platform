"""Shared fixtures for workflow-engine tests."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import httpx
import pytest
import yaml

from ngen_framework_core.crd import (
    CRDMetadata,
    TopologyType,
    WorkflowAgentRef,
    WorkflowCRD,
    WorkflowEdge,
    WorkflowSpecCRD,
    HumanInTheLoopSpec,
)
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
from workflow_engine.config import Settings
from workflow_engine.engine import WorkflowEngine


# ---------------------------------------------------------------------------
# InMemoryAdapter — real FrameworkAdapter for testing (no mocks!)
# ---------------------------------------------------------------------------


class InMemoryAdapter:
    """A real FrameworkAdapter that produces context-aware events.

    Delegates to DefaultAdapter's rich response logic but registers
    with name "in-memory" for test fixtures.
    """

    def __init__(self) -> None:
        from workflow_engine.default_adapter import DefaultAdapter
        self._delegate = DefaultAdapter()

    @property
    def name(self) -> str:
        return "in-memory"

    async def create_agent(self, spec: AgentSpec) -> str:
        return await self._delegate.create_agent(spec)

    async def execute(
        self, agent: str, input: AgentInput
    ) -> AsyncIterator[AgentEvent]:
        async for event in self._delegate.execute(agent, input):
            yield event

    async def checkpoint(self, agent: str) -> StateSnapshot:
        return await self._delegate.checkpoint(agent)

    async def restore(self, agent: str, snapshot: StateSnapshot) -> None:
        await self._delegate.restore(agent, snapshot)

    async def teardown(self, agent: str) -> None:
        await self._delegate.teardown(agent)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def adapter() -> InMemoryAdapter:
    return InMemoryAdapter()


@pytest.fixture()
def registry(adapter: InMemoryAdapter) -> AdapterRegistry:
    reg = AdapterRegistry()
    reg.register(adapter)
    return reg


@pytest.fixture()
def executor(registry: AdapterRegistry) -> AgentExecutor:
    return AgentExecutor(registry=registry)


@pytest.fixture()
def engine(executor: AgentExecutor) -> WorkflowEngine:
    return WorkflowEngine(executor=executor, default_framework="in-memory")


@pytest.fixture()
def settings() -> Settings:
    return Settings()


@pytest.fixture()
def app(executor: AgentExecutor, settings: Settings):
    return create_app(executor=executor, settings=settings, default_framework="in-memory")


@pytest.fixture()
async def client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://workflow-engine"
    ) as ac:
        yield ac


@pytest.fixture()
def make_crd():
    """Fixture that returns the make_workflow_crd factory."""
    return make_workflow_crd


@pytest.fixture()
def crd_to_yaml():
    """Fixture that returns the workflow_crd_to_yaml helper."""
    return workflow_crd_to_yaml


def make_workflow_crd(
    name: str = "test-workflow",
    agents: list[str] | None = None,
    topology: TopologyType = TopologyType.SEQUENTIAL,
    edges: list[dict[str, str]] | None = None,
    hitl_gate: str | None = None,
) -> WorkflowCRD:
    """Factory to create WorkflowCRD objects for testing."""
    agent_refs = [
        WorkflowAgentRef(ref=a) for a in (agents or ["agent-a", "agent-b"])
    ]
    workflow_edges = []
    if edges:
        workflow_edges = [
            WorkflowEdge.model_validate(e) for e in edges
        ]

    hitl = None
    if hitl_gate:
        hitl = HumanInTheLoopSpec(approval_gate=hitl_gate)

    return WorkflowCRD(
        apiVersion="ngen.io/v1",
        kind="Workflow",
        metadata=CRDMetadata(name=name),
        spec=WorkflowSpecCRD(
            agents=agent_refs,
            topology=topology,
            edges=workflow_edges,
            human_in_the_loop=hitl,
        ),
    )


def workflow_crd_to_yaml(crd: WorkflowCRD) -> str:
    """Convert a WorkflowCRD to YAML string for API tests."""
    data = {
        "apiVersion": "ngen.io/v1",
        "kind": "Workflow",
        "metadata": {"name": crd.metadata.name},
        "spec": {
            "agents": [{"ref": a.ref} for a in crd.spec.agents],
            "topology": crd.spec.topology.value,
        },
    }
    if crd.spec.edges:
        data["spec"]["edges"] = [
            {"from": e.source, "to": e.target, **({"condition": e.condition} if e.condition else {})}
            for e in crd.spec.edges
        ]
    if crd.spec.human_in_the_loop:
        data["spec"]["humanInTheLoop"] = {
            "approvalGate": crd.spec.human_in_the_loop.approval_gate,
        }
    return yaml.dump(data)
