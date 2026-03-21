"""Agent lifecycle manager — manages standalone agent instances.

Provides CRUD operations for agent instances that exist outside of
workflow runs. Agents can be created from AgentCRD YAML, listed,
inspected, and torn down. Each agent is managed through the
AgentExecutor and can be invoked directly.

This complements the WorkflowEngine which creates agents ephemerally
per-run. The AgentManager creates persistent agents that survive
across requests.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ngen_framework_core.crd import parse_crd
from ngen_framework_core.executor import AgentExecutor
from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    ModelRef,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AgentCreateRequest(BaseModel):
    """Request body for creating a standalone agent."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    framework: str = "default"
    model: str = "default"
    system_prompt: str = "You are a helpful agent."
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentCreateFromCRD(BaseModel):
    """Request body for creating an agent from CRD YAML."""

    agent_yaml: str = Field(..., description="Raw YAML string of an AgentCRD")


class AgentInvokeRequest(BaseModel):
    """Request body for invoking a standalone agent."""

    messages: list[dict[str, str]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class AgentInfo(BaseModel):
    """Information about a managed agent."""

    name: str
    description: str = ""
    framework: str = ""
    model: str = ""
    status: str = "running"
    created_at: float = 0.0
    invocation_count: int = 0


class AgentInvokeResponse(BaseModel):
    """Response from an agent invocation."""

    agent_name: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    output: str | None = None


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------


@dataclass
class ManagedAgent:
    """Internal state of a managed agent."""

    name: str
    description: str = ""
    framework: str = ""
    model: str = ""
    status: str = "running"
    created_at: float = field(default_factory=time.time)
    invocation_count: int = 0


class AgentRegistry:
    """Tracks managed agent instances."""

    def __init__(self) -> None:
        self._agents: dict[str, ManagedAgent] = {}

    def register(self, agent: ManagedAgent) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> ManagedAgent | None:
        return self._agents.get(name)

    def list(self) -> list[ManagedAgent]:
        return list(self._agents.values())

    def remove(self, name: str) -> bool:
        return self._agents.pop(name, None) is not None

    def increment_invocations(self, name: str) -> None:
        agent = self._agents.get(name)
        if agent:
            agent.invocation_count += 1


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


agent_router = APIRouter(prefix="/agents", tags=["agents"])


def _get_executor(request: Request) -> AgentExecutor:
    return request.app.state.executor


def _get_registry(request: Request) -> AgentRegistry:
    registry = getattr(request.app.state, "agent_registry", None)
    if registry is None:
        registry = AgentRegistry()
        request.app.state.agent_registry = registry
    return registry


def _publish_agent_event(
    request: Request, subject: str, data: dict,
) -> None:
    """Fire-and-forget agent lifecycle event publishing."""
    bus = getattr(request.app.state, "event_bus", None)
    if bus is None:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(bus.publish(subject, data, source="workflow-engine"))
    except RuntimeError:
        pass


@agent_router.post("", status_code=201, response_model=AgentInfo)
async def create_agent(body: AgentCreateRequest, request: Request) -> AgentInfo:
    """Create a standalone managed agent."""
    executor = _get_executor(request)
    registry = _get_registry(request)

    if registry.get(body.name) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Agent '{body.name}' already exists",
        )

    spec = AgentSpec(
        name=body.name,
        description=body.description,
        framework=body.framework,
        model=ModelRef(name=body.model),
        system_prompt=body.system_prompt,
        metadata=body.metadata,
    )

    await executor.create(spec)

    managed = ManagedAgent(
        name=body.name,
        description=body.description,
        framework=body.framework,
        model=body.model,
    )
    registry.register(managed)

    from ngen_common.events import Subjects
    _publish_agent_event(request, Subjects.LIFECYCLE_AGENT_CREATED, {
        "name": body.name,
        "framework": body.framework,
        "model": body.model,
    })

    return AgentInfo(
        name=managed.name,
        description=managed.description,
        framework=managed.framework,
        model=managed.model,
        created_at=managed.created_at,
    )


@agent_router.get("", response_model=list[AgentInfo])
async def list_agents(request: Request) -> list[AgentInfo]:
    """List all managed agents."""
    registry = _get_registry(request)
    return [
        AgentInfo(
            name=a.name,
            description=a.description,
            framework=a.framework,
            model=a.model,
            status=a.status,
            created_at=a.created_at,
            invocation_count=a.invocation_count,
        )
        for a in registry.list()
    ]


@agent_router.get("/{agent_name}", response_model=AgentInfo)
async def get_agent(agent_name: str, request: Request) -> AgentInfo:
    """Get details of a managed agent."""
    registry = _get_registry(request)
    agent = registry.get(agent_name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return AgentInfo(
        name=agent.name,
        description=agent.description,
        framework=agent.framework,
        model=agent.model,
        status=agent.status,
        created_at=agent.created_at,
        invocation_count=agent.invocation_count,
    )


@agent_router.post("/{agent_name}/invoke", response_model=AgentInvokeResponse)
async def invoke_agent(
    agent_name: str, body: AgentInvokeRequest, request: Request,
) -> AgentInvokeResponse:
    """Invoke a managed agent and return its events."""
    executor = _get_executor(request)
    registry = _get_registry(request)

    agent = registry.get(agent_name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    agent_input = AgentInput(
        messages=body.messages or [{"role": "user", "content": "Hello"}],
        context=body.context,
        session_id=body.session_id,
    )

    events: list[dict[str, Any]] = []
    output_text = ""

    try:
        async for event in executor.execute(agent_name, agent_input):
            events.append({
                "type": event.type.value,
                "data": event.data,
                "agent_name": event.agent_name,
            })
            if event.type == AgentEventType.TEXT_DELTA:
                output_text += event.data.get("text", "")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed: {exc}",
        )

    registry.increment_invocations(agent_name)

    return AgentInvokeResponse(
        agent_name=agent_name,
        events=events,
        output=output_text or None,
    )


@agent_router.delete("/{agent_name}", status_code=204)
async def delete_agent(agent_name: str, request: Request) -> None:
    """Tear down and remove a managed agent."""
    executor = _get_executor(request)
    registry = _get_registry(request)

    agent = registry.get(agent_name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    try:
        await executor.teardown(agent_name)
    except Exception:
        logger.warning("Error tearing down agent '%s'", agent_name, exc_info=True)

    registry.remove(agent_name)

    from ngen_common.events import Subjects
    _publish_agent_event(request, Subjects.LIFECYCLE_AGENT_DELETED, {
        "name": agent_name,
    })
