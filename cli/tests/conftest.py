"""Shared fixtures for CLI tests.

Spins up real in-process FastAPI services (workflow-engine, model-registry)
behind httpx ASGI transports so the CLI client talks to real backends.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from ngen_framework_core.executor import AgentExecutor
from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    StateSnapshot,
)
from ngen_framework_core.registry import AdapterRegistry

from model_registry.app import create_app as create_registry_app
from workflow_engine.app import create_app as create_workflow_app
from workflow_engine.config import Settings

from ngen_cli.client import NgenClient


# ---------------------------------------------------------------------------
# InMemoryAdapter — same as workflow-engine tests
# ---------------------------------------------------------------------------


class InMemoryAdapter:
    """Real FrameworkAdapter that produces deterministic events."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentSpec] = {}
        self._states: dict[str, dict[str, Any]] = {}

    @property
    def name(self) -> str:
        return "in-memory"

    async def create_agent(self, spec: AgentSpec) -> str:
        self._agents[spec.name] = spec
        self._states[spec.name] = {}
        return spec.name

    async def execute(
        self, agent: str, input: AgentInput
    ) -> AsyncIterator[AgentEvent]:
        spec = self._agents.get(agent)
        agent_name = spec.name if spec else agent

        yield AgentEvent(
            type=AgentEventType.THINKING,
            data={"text": f"Agent '{agent_name}' is thinking..."},
            agent_name=agent_name,
            timestamp=time.time(),
        )
        yield AgentEvent(
            type=AgentEventType.TEXT_DELTA,
            data={"text": f"Output from {agent_name}"},
            agent_name=agent_name,
            timestamp=time.time(),
        )
        yield AgentEvent(
            type=AgentEventType.DONE,
            data={},
            agent_name=agent_name,
            timestamp=time.time(),
        )

    async def checkpoint(self, agent: str) -> StateSnapshot:
        return StateSnapshot(agent_name=agent, state=dict(self._states.get(agent, {})))

    async def restore(self, agent: str, snapshot: StateSnapshot) -> None:
        self._states[agent] = dict(snapshot.state)

    async def teardown(self, agent: str) -> None:
        self._agents.pop(agent, None)
        self._states.pop(agent, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workflow_app():
    """Create a real workflow-engine FastAPI app with in-memory adapter."""
    adapter = InMemoryAdapter()
    registry = AdapterRegistry()
    registry.register(adapter)
    executor = AgentExecutor(registry=registry)
    return create_workflow_app(
        executor=executor,
        settings=Settings(),
        default_framework="in-memory",
    )


@pytest.fixture()
def registry_app():
    """Create a real model-registry FastAPI app with a fresh repository."""
    import model_registry.routes as registry_routes
    # Reset the singleton so each test gets a clean repo
    registry_routes._repository = None
    return create_registry_app()


@pytest.fixture()
def ngen_client(workflow_app, registry_app) -> NgenClient:
    """Create an NgenClient wired to in-process ASGI apps.

    Monkeypatches httpx.AsyncClient so the CLI client talks to real
    backends without needing actual network servers.
    """
    # We create a patched NgenClient that overrides the HTTP calls
    # to route through ASGI transports
    client = NgenClient(
        workflow_url="http://workflow-engine",
        registry_url="http://model-registry",
        gateway_url="http://model-gateway",
    )
    client._workflow_app = workflow_app
    client._registry_app = registry_app
    return client


@pytest.fixture()
async def workflow_client(workflow_app) -> AsyncIterator[httpx.AsyncClient]:
    """Direct httpx client for the workflow engine."""
    transport = httpx.ASGITransport(app=workflow_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://workflow-engine"
    ) as client:
        yield client


@pytest.fixture()
async def registry_client(registry_app) -> AsyncIterator[httpx.AsyncClient]:
    """Direct httpx client for the model registry."""
    transport = httpx.ASGITransport(app=registry_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://model-registry"
    ) as client:
        yield client
