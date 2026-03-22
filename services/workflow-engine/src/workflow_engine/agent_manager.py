"""Agent lifecycle manager — manages standalone agent instances.

Provides CRUD operations for agent instances that exist outside of
workflow runs. Agents can be created from AgentCRD YAML, listed,
inspected, and torn down. Each agent is managed through the
AgentExecutor and can be invoked directly.

Includes integrated memory support via MemoryInterceptor — agent
conversations are automatically persisted to the memory subsystem.
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
from ngen_framework_core.memory_interceptor import MemoryInterceptor
from ngen_framework_core.memory_manager import DefaultMemoryManager
from ngen_framework_core.memory_store import InMemoryMemoryStore
from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    MemoryScope,
    MemoryType,
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
    system_prompt: str = ""
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
    system_prompt: str = ""
    status: str = "running"
    created_at: float = field(default_factory=time.time)
    invocation_count: int = 0


class AgentRegistry:
    """Tracks managed agent instances, scoped by tenant.

    Agents are keyed by ``{tenant_id}:{agent_name}`` to prevent
    cross-tenant name collisions and ensure complete isolation.
    """

    def __init__(self) -> None:
        self._agents: dict[str, ManagedAgent] = {}

    @staticmethod
    def _key(tenant_id: str, name: str) -> str:
        return f"{tenant_id}:{name}"

    def register(self, agent: ManagedAgent, tenant_id: str = "default") -> None:
        self._agents[self._key(tenant_id, agent.name)] = agent

    def get(self, name: str, tenant_id: str = "default") -> ManagedAgent | None:
        return self._agents.get(self._key(tenant_id, name))

    def list(self, tenant_id: str = "default") -> list[ManagedAgent]:
        prefix = f"{tenant_id}:"
        return [a for k, a in self._agents.items() if k.startswith(prefix)]

    def remove(self, name: str, tenant_id: str = "default") -> bool:
        return self._agents.pop(self._key(tenant_id, name), None) is not None

    def increment_invocations(self, name: str, tenant_id: str = "default") -> None:
        agent = self._agents.get(self._key(tenant_id, name))
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


def _publish_memory_event(
    request: Request,
    subject: str,
    agent_name: str,
    memory_type: str,
    size_bytes: int = 0,
    token_estimate: int = 0,
    entry_count: int = 1,
) -> None:
    """Fire-and-forget memory event publishing."""
    bus = getattr(request.app.state, "event_bus", None)
    if bus is None:
        return
    org_id, _, _ = _extract_tenant(request)
    try:
        from ngen_common.events import publish_memory_event
        loop = asyncio.get_running_loop()
        loop.create_task(publish_memory_event(
            bus,
            subject=subject,
            tenant_id=org_id,
            agent_name=agent_name,
            memory_type=memory_type,
            size_bytes=size_bytes,
            token_estimate=token_estimate,
            entry_count=entry_count,
        ))
    except RuntimeError:
        pass


@agent_router.post("", status_code=201, response_model=AgentInfo)
async def create_agent(body: AgentCreateRequest, request: Request) -> AgentInfo:
    """Create a standalone managed agent, scoped to the caller's tenant."""
    executor = _get_executor(request)
    registry = _get_registry(request)
    tenant_id = _get_tenant_id(request)

    if registry.get(body.name, tenant_id) is not None:
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
        system_prompt=body.system_prompt,
    )
    registry.register(managed, tenant_id)

    from ngen_common.events import Subjects
    _publish_agent_event(request, Subjects.LIFECYCLE_AGENT_CREATED, {
        "name": body.name,
        "framework": body.framework,
        "model": body.model,
    })

    # Write tool specs to TOOLBOX memory
    tools = body.metadata.get("tools", [])
    if tools:
        mgr = _get_memory_manager(request, body.name)
        tools_text = "Available tools for this agent:\n" + "\n".join(
            f"- {t}" for t in tools
        )
        await mgr.write_memory(
            MemoryType.TOOLBOX,
            tools_text,
            metadata={"tools": tools},
        )

    return AgentInfo(
        name=managed.name,
        description=managed.description,
        framework=managed.framework,
        model=managed.model,
        system_prompt=managed.system_prompt,
        created_at=managed.created_at,
    )


@agent_router.get("", response_model=list[AgentInfo])
async def list_agents(request: Request, search: str = "") -> list[AgentInfo]:
    """List managed agents for the caller's tenant. Optionally filter by search."""
    registry = _get_registry(request)
    tenant_id = _get_tenant_id(request)
    agents = registry.list(tenant_id)
    if search:
        q = search.lower()
        agents = [a for a in agents if q in a.name.lower() or q in a.description.lower()]
    return [
        AgentInfo(
            name=a.name,
            description=a.description,
            framework=a.framework,
            model=a.model,
            system_prompt=a.system_prompt,
            status=a.status,
            created_at=a.created_at,
            invocation_count=a.invocation_count,
        )
        for a in agents
    ]


@agent_router.get("/{agent_name}", response_model=AgentInfo)
async def get_agent(agent_name: str, request: Request) -> AgentInfo:
    """Get details of a managed agent, scoped to caller's tenant."""
    registry = _get_registry(request)
    tenant_id = _get_tenant_id(request)
    agent = registry.get(agent_name, tenant_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return AgentInfo(
        name=agent.name,
        description=agent.description,
        framework=agent.framework,
        model=agent.model,
        system_prompt=agent.system_prompt,
        status=agent.status,
        created_at=agent.created_at,
        invocation_count=agent.invocation_count,
    )


@agent_router.post("/{agent_name}/invoke", response_model=AgentInvokeResponse)
async def invoke_agent(
    agent_name: str, body: AgentInvokeRequest, request: Request,
) -> AgentInvokeResponse:
    """Invoke a managed agent, scoped to caller's tenant."""
    executor = _get_executor(request)
    registry = _get_registry(request)
    tenant_id = _get_tenant_id(request)

    agent = registry.get(agent_name, tenant_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    # Auto-recreate agent in executor if it was lost (e.g., server restart, adapter mismatch)
    if agent_name not in executor.agent_names:
        spec = AgentSpec(
            name=agent.name,
            description=agent.description,
            framework=agent.framework or "default",
            model=ModelRef(name=agent.model or "default"),
            system_prompt=agent.system_prompt,
        )
        try:
            await executor.create(spec)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize agent '{agent_name}': {exc}",
            )

    agent_input = AgentInput(
        messages=body.messages or [{"role": "user", "content": "Hello"}],
        context=body.context,
        session_id=body.session_id,
    )

    # Set up memory for conversation persistence
    manager = _get_memory_manager(request, agent_name, body.session_id)
    from ngen_common.events import Subjects

    # Set up interceptor for automatic event→memory mapping
    async def _on_intercept(mem_type: str, size_bytes: int, token_estimate: int) -> None:
        _publish_memory_event(
            request, Subjects.MEMORY_WRITTEN, agent_name,
            mem_type, size_bytes=size_bytes, token_estimate=token_estimate,
        )

    interceptor = MemoryInterceptor(
        manager=manager,
        event_callback=_on_intercept,
    )

    # Persist user messages to memory
    for msg in (body.messages or []):
        if isinstance(msg, dict) and msg.get("content"):
            content = msg["content"]
            await manager.write_memory(
                MemoryType.CONVERSATIONAL,
                content,
                role=msg.get("role", "user"),
            )
            _publish_memory_event(
                request, Subjects.MEMORY_WRITTEN, agent_name,
                MemoryType.CONVERSATIONAL.value,
                size_bytes=len(content.encode("utf-8")),
                token_estimate=len(content) // 4,
            )

    events: list[dict[str, Any]] = []
    output_text = ""

    try:
        async for event in executor.execute(agent_name, agent_input):
            # Intercept events → auto-writes TOOL_LOG, WORKFLOW, etc.
            event = await interceptor.intercept(event)

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

    # Persist agent response to memory
    if output_text:
        await manager.write_memory(
            MemoryType.CONVERSATIONAL,
            output_text,
            role="assistant",
        )
        _publish_memory_event(
            request, Subjects.MEMORY_WRITTEN, agent_name,
            MemoryType.CONVERSATIONAL.value,
            size_bytes=len(output_text.encode("utf-8")),
            token_estimate=len(output_text) // 4,
        )

    # --- Background async tasks (fire-and-forget) ---
    loop = asyncio.get_running_loop()

    # Entity extraction from the response
    if output_text and len(output_text) > 50:
        loop.create_task(_extract_entities(manager, output_text))

    # Auto-summarization when threshold reached
    stats = await manager.get_stats()
    conv_count = stats.get("by_type", {}).get(
        MemoryType.CONVERSATIONAL.value, {}
    ).get("count", 0)
    if conv_count >= 20:
        thread_id = body.session_id or "default"
        loop.create_task(manager.summarize_and_compact(thread_id=thread_id))

    registry.increment_invocations(agent_name, tenant_id)

    return AgentInvokeResponse(
        agent_name=agent_name,
        events=events,
        output=output_text or None,
    )


@agent_router.delete("/{agent_name}", status_code=204)
async def delete_agent(agent_name: str, request: Request) -> None:
    """Tear down and remove a managed agent, scoped to caller's tenant."""
    executor = _get_executor(request)
    registry = _get_registry(request)
    tenant_id = _get_tenant_id(request)

    agent = registry.get(agent_name, tenant_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    try:
        await executor.teardown(agent_name)
    except Exception:
        logger.warning("Error tearing down agent '%s'", agent_name, exc_info=True)

    registry.remove(agent_name, tenant_id)

    from ngen_common.events import Subjects
    _publish_agent_event(request, Subjects.LIFECYCLE_AGENT_DELETED, {
        "name": agent_name,
    })


# ---------------------------------------------------------------------------
# Memory endpoints
# ---------------------------------------------------------------------------


def _get_memory_store(request: Request) -> InMemoryMemoryStore:
    """Get or create the shared memory store."""
    store = getattr(request.app.state, "memory_store", None)
    if store is None:
        store = InMemoryMemoryStore()
        request.app.state.memory_store = store
    return store


def _get_tenant_id(request: Request) -> str:
    """Extract tenant ID from JWT identity, header, or default."""
    identity = getattr(request.state, "identity", None)
    if identity and hasattr(identity, "tenant_id") and identity.tenant_id:
        return identity.tenant_id
    return request.headers.get("x-tenant-id", "default")


def _extract_tenant(request: Request) -> tuple[str, str, str]:
    """Extract tenant context from JWT identity, headers, or defaults."""
    tenant_id = _get_tenant_id(request)
    org_id = request.headers.get("x-org-id", tenant_id)
    team_id = request.headers.get("x-team-id", "default")
    project_id = request.headers.get("x-project-id", "default")
    return org_id, team_id, project_id


async def _summarize_fn(text: str) -> str:
    """Summarize text via LLM. Used as the memory manager's summarize callback."""
    from workflow_engine.default_adapter import _call_llm

    result = await _call_llm(
        system_prompt=(
            "You are a memory compaction assistant. Summarize the following conversation "
            "concisely, preserving key facts, decisions, action items, and any important "
            "context. Be brief but thorough."
        ),
        user_msg=text,
    )
    return result or text[:500]


async def _extract_entities(manager: DefaultMemoryManager, text: str) -> None:
    """Extract named entities from text and write to ENTITY memory (fire-and-forget)."""
    try:
        from workflow_engine.default_adapter import _call_llm

        entities_text = await _call_llm(
            system_prompt=(
                "Extract all named entities from the following text. "
                "Group them by type: People, Organizations, Technologies, "
                "Locations, Dates, Concepts. Return as a concise bullet list. "
                "If there are no entities, respond with 'No entities found.'"
            ),
            user_msg=text,
        )
        if entities_text and "no entities" not in entities_text.lower():
            await manager.write_memory(
                MemoryType.ENTITY,
                entities_text,
                metadata={"source": "auto_extraction"},
            )
    except Exception:
        logger.debug("Entity extraction failed (non-critical)", exc_info=True)


def _get_memory_manager(
    request: Request, agent_name: str, session_id: str | None = None,
) -> DefaultMemoryManager:
    """Create a MemoryManager scoped to an agent and tenant."""
    from ngen_framework_core.protocols import MemoryPolicy

    store = _get_memory_store(request)
    org_id, team_id, project_id = _extract_tenant(request)
    scope = MemoryScope(
        org_id=org_id,
        team_id=team_id,
        project_id=project_id,
        agent_name=agent_name,
        thread_id=session_id,
    )
    return DefaultMemoryManager(
        scope=scope,
        store=store,
        summarize_fn=_summarize_fn,
        policy=MemoryPolicy(summarization_threshold=20),
    )


@agent_router.get("/{agent_name}/memory")
async def get_agent_memory(
    agent_name: str,
    request: Request,
    memory_type: str = "conversational",
    limit: int = 20,
) -> list[dict]:
    """Retrieve memory entries for an agent."""
    registry = _get_registry(request)
    if registry.get(agent_name) is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    try:
        mem_type = MemoryType(memory_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid memory type: {memory_type}. Valid: {[t.value for t in MemoryType]}",
        )

    manager = _get_memory_manager(request, agent_name)
    entries = await manager.read_memory(mem_type, limit=limit)
    return [
        {
            "id": e.id,
            "memory_type": e.memory_type.value,
            "content": e.content,
            "role": e.role,
            "metadata": e.metadata,
            "created_at": e.created_at,
            "size_bytes": e.size_bytes,
            "token_estimate": e.token_estimate,
        }
        for e in entries
    ]


@agent_router.get("/{agent_name}/memory/context")
async def get_agent_context_window(
    agent_name: str,
    request: Request,
    query: str = "",
) -> dict:
    """Build a context window from the agent's memory."""
    registry = _get_registry(request)
    if registry.get(agent_name) is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    manager = _get_memory_manager(request, agent_name)
    context = await manager.build_context_window(query or None)
    return {"context": context, "agent_name": agent_name}


@agent_router.get("/{agent_name}/memory/stats")
async def get_agent_memory_stats(
    agent_name: str,
    request: Request,
) -> dict:
    """Get memory statistics for an agent."""
    registry = _get_registry(request)
    if registry.get(agent_name) is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    manager = _get_memory_manager(request, agent_name)
    stats = await manager.get_stats()
    return {
        "agent_name": agent_name,
        "total_entries": stats["total_entries"],
        "by_type": stats["by_type"],
        "total_bytes": stats["total_bytes"],
        "total_tokens": stats["total_tokens"],
        "context_budget_tokens": stats["context_budget_tokens"],
    }


@agent_router.delete("/{agent_name}/memory")
async def clear_agent_memory(
    agent_name: str,
    request: Request,
    memory_type: str | None = None,
) -> dict:
    """Clear memory for an agent. Optionally filter by memory type."""
    registry = _get_registry(request)
    if registry.get(agent_name) is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    store = _get_memory_store(request)
    org_id, team_id, project_id = _extract_tenant(request)
    scope = MemoryScope(
        org_id=org_id,
        team_id=team_id,
        project_id=project_id,
        agent_name=agent_name,
    )

    if memory_type:
        try:
            mem_type = MemoryType(memory_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid memory type: {memory_type}")
        deleted = await store.delete_by_scope(scope, mem_type)
    else:
        deleted = await store.delete_by_scope(scope)

    if deleted > 0:
        from ngen_common.events import Subjects
        _publish_memory_event(
            request,
            Subjects.MEMORY_DELETED,
            agent_name,
            memory_type or "all",
            entry_count=deleted,
        )

    return {"agent_name": agent_name, "deleted": deleted}


# ---------------------------------------------------------------------------
# Platform-wide memory stats
# ---------------------------------------------------------------------------

memory_router = APIRouter(prefix="/memory", tags=["memory"])


@memory_router.get("/stats")
async def get_platform_memory_stats(
    request: Request,
    org_id: str | None = None,
) -> dict:
    """Get platform-wide memory statistics across all agents.

    Optionally filter by org_id for tenant-level breakdown.
    """
    store = _get_memory_store(request)
    registry = _get_registry(request)

    req_org, req_team, req_project = _extract_tenant(request)

    by_agent: dict[str, dict] = {}
    by_type: dict[str, int] = {}
    total_entries = 0
    total_bytes = 0

    for agent in registry.list():
        agent_name = agent.name
        scope = MemoryScope(
            org_id=org_id or req_org,
            team_id=req_team,
            project_id=req_project,
            agent_name=agent_name,
        )
        agent_stats = await store.stats(scope)

        if agent_stats:
            agent_entries = sum(v["count"] for v in agent_stats.values())
            agent_bytes = sum(v["size_bytes"] for v in agent_stats.values())
            agent_tokens = sum(v["token_estimate"] for v in agent_stats.values())
            by_agent[agent_name] = {
                "total_entries": agent_entries,
                "total_bytes": agent_bytes,
                "total_tokens": agent_tokens,
                "by_type": agent_stats,
            }
            total_entries += agent_entries
            total_bytes += agent_bytes
            for mt, vals in agent_stats.items():
                by_type[mt] = by_type.get(mt, 0) + vals["count"]

    total_tokens = sum(a["total_tokens"] for a in by_agent.values())

    return {
        "total_entries": total_entries,
        "total_bytes": total_bytes,
        "total_tokens": total_tokens,
        "agents_with_memory": len(by_agent),
        "by_agent": by_agent,
        "by_type": by_type,
    }


@memory_router.get("/health")
async def get_memory_health(request: Request) -> dict:
    """Analyze agent memory and return health recommendations."""
    store = _get_memory_store(request)
    registry = _get_registry(request)
    req_org, req_team, req_project = _extract_tenant(request)

    recommendations: list[dict] = []

    for agent in registry.list():
        scope = MemoryScope(
            org_id=req_org,
            team_id=req_team,
            project_id=req_project,
            agent_name=agent.name,
        )
        agent_stats = await store.stats(scope)
        if not agent_stats:
            continue

        total_entries = sum(v["count"] for v in agent_stats.values())
        total_tokens = sum(v["token_estimate"] for v in agent_stats.values())

        # Check: high token usage relative to default budget
        if total_tokens > 4000:
            recommendations.append({
                "agent_name": agent.name,
                "issue": "memory_exceeds_budget",
                "severity": "warning",
                "detail": f"Memory tokens ({total_tokens}) exceed default context budget (4000)",
                "suggestion": "Enable summarization or increase context_budget_tokens",
            })

        # Check: high conversational entries without summaries
        conv_count = agent_stats.get("conversational", {}).get("count", 0)
        summary_count = agent_stats.get("summary", {}).get("count", 0)
        if conv_count > 50 and summary_count == 0:
            recommendations.append({
                "agent_name": agent.name,
                "issue": "no_summarization",
                "severity": "warning",
                "detail": f"{conv_count} conversational entries with no summaries",
                "suggestion": "Configure a summarize_fn to compress old conversations",
            })

        # Check: tool_log dominating memory
        tool_log_count = agent_stats.get("tool_log", {}).get("count", 0)
        if total_entries > 10 and tool_log_count / total_entries > 0.8:
            recommendations.append({
                "agent_name": agent.name,
                "issue": "tool_log_dominant",
                "severity": "info",
                "detail": f"Tool logs are {tool_log_count}/{total_entries} entries ({tool_log_count * 100 // total_entries}%)",
                "suggestion": "Consider setting a TTL on tool_log entries or reducing logging verbosity",
            })

    return {
        "recommendations": recommendations,
        "agents_analyzed": len(registry.list()),
    }


@agent_router.get("/{agent_name}/memory/{entry_id}")
async def get_memory_entry(
    agent_name: str,
    entry_id: str,
    request: Request,
) -> dict:
    """Get full details of a specific memory entry."""
    registry = _get_registry(request)
    if registry.get(agent_name) is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    store = _get_memory_store(request)
    org_id, team_id, project_id = _extract_tenant(request)
    scope = MemoryScope(
        org_id=org_id,
        team_id=team_id,
        project_id=project_id,
        agent_name=agent_name,
    )

    # Search across all memory types for this entry ID
    for mem_type in MemoryType:
        entries = await store.read(scope, mem_type, limit=10000)
        for entry in entries:
            if entry.id == entry_id:
                return {
                    "id": entry.id,
                    "memory_type": entry.memory_type.value,
                    "content": entry.content,
                    "role": entry.role,
                    "metadata": entry.metadata,
                    "created_at": entry.created_at,
                    "size_bytes": entry.size_bytes,
                    "token_estimate": entry.token_estimate,
                    "ttl_seconds": entry.ttl_seconds,
                    "summary_id": entry.summary_id,
                    "scope": {
                        "org_id": entry.scope.org_id,
                        "team_id": entry.scope.team_id,
                        "project_id": entry.scope.project_id,
                        "agent_name": entry.scope.agent_name,
                        "thread_id": entry.scope.thread_id,
                    },
                }

    raise HTTPException(status_code=404, detail=f"Memory entry '{entry_id}' not found")
