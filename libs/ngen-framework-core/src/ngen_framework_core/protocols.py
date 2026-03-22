"""Core protocol classes defining the platform's abstraction layer.

These protocols define the contract between the platform and framework adapters.
Every framework adapter (LangGraph, ADK, CrewAI, Claude Agent SDK, etc.) must
implement the FrameworkAdapter protocol.

Component type model (RAPIDS methodology):
- Tool: Deterministic function, stateless, no LLM
- Skill: LLM-powered, single-shot, reasoning trace + confidence
- Agent: Autonomous, multi-turn, stateful, event stream contract
"""

from __future__ import annotations

import enum
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Component type taxonomy (RAPIDS)
# ---------------------------------------------------------------------------


class ComponentType(enum.Enum):
    """Three escalating autonomy levels for platform components."""

    TOOL = "tool"
    SKILL = "skill"
    AGENT = "agent"

# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelRef:
    """Reference to a model registered in the model registry."""

    name: str
    fallback: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPServerRef:
    """Reference to an MCP server in the MCP registry."""

    name: str
    version: str | None = None


@dataclass(frozen=True)
class GuardrailRef:
    """Reference to a guardrail in the governance service."""

    name: str
    config: dict[str, Any] = field(default_factory=dict)


class MemoryType(enum.Enum):
    """Seven memory types for agent memory systems.

    Each type serves a distinct purpose in the agent's cognitive architecture:
    - CONVERSATIONAL: Chat history for context continuity (structured/SQL)
    - KNOWLEDGE_BASE: Documents and facts retrieved by similarity (vector)
    - WORKFLOW: Past tool execution patterns (vector)
    - TOOLBOX: Available tools with semantic search (vector)
    - ENTITY: Extracted people, places, concepts (vector)
    - SUMMARY: Compressed conversation summaries (vector)
    - TOOL_LOG: Raw tool-call inputs, outputs, status for audit (structured/SQL)
    """

    CONVERSATIONAL = "conversational"
    KNOWLEDGE_BASE = "knowledge_base"
    WORKFLOW = "workflow"
    TOOLBOX = "toolbox"
    ENTITY = "entity"
    SUMMARY = "summary"
    TOOL_LOG = "tool_log"


@dataclass(frozen=True)
class MemoryScope:
    """Namespace isolation key for multi-tenant memory.

    Every memory operation is scoped by (org, team, project, agent) to guarantee
    zero cross-tenant data leakage. Thread ID provides sub-agent isolation for
    conversational and tool-log memory.
    """

    org_id: str
    team_id: str
    project_id: str
    agent_name: str
    thread_id: str | None = None

    def to_prefix(self) -> str:
        """Return colon-joined key prefix for storage backends."""
        base = f"ngen:mem:{self.org_id}:{self.team_id}:{self.project_id}:{self.agent_name}"
        return f"{base}:{self.thread_id}" if self.thread_id else base


@dataclass
class MemoryEntry:
    """Individual memory record with metadata, TTL, and scope."""

    id: str
    memory_type: MemoryType
    scope: MemoryScope
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    role: str | None = None  # "user"/"assistant" for conversational
    embedding: list[float] | None = None
    created_at: float = 0.0
    ttl_seconds: int | None = None
    summary_id: str | None = None  # links summarized entries to their summary
    size_bytes: int = 0
    token_estimate: int = 0


@dataclass(frozen=True)
class MemoryPolicy:
    """Retention and lifecycle policy for memory entries."""

    max_entries: int | None = None
    ttl_seconds: int | None = None
    summarization_threshold: int | None = None  # auto-summarize after N msgs
    retention_days: int | None = None


@dataclass(frozen=True)
class MemoryConfig:
    """Configuration for agent memory systems.

    Backward compatible: original fields remain. New fields support the
    full 7-type memory architecture with policies and embedding config.
    """

    short_term: bool = True
    long_term: bool = False
    vector_store: str | None = None
    ttl_seconds: int | None = None
    # --- Memory subsystem fields ---
    memory_types: list[MemoryType] = field(default_factory=list)
    policy: MemoryPolicy = field(default_factory=MemoryPolicy)
    embedding_model: str | None = None
    context_budget_tokens: int = 4000


@dataclass(frozen=True)
class ToolSpec:
    """Declares a tool an agent can use.

    Tools can be backed by an MCP server or a local handler function reference.
    """

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    mcp_server: MCPServerRef | None = None
    handler: str | None = None  # Python dotted path to handler function


@dataclass(frozen=True)
class ToolComponentSpec:
    """Declares a standalone platform tool (RAPIDS component type: Tool).

    Tools are deterministic, stateless functions with no LLM involvement.
    Runtime contract: execute(), health(), schema().
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    handler: str | None = None  # Python dotted path to handler function
    mcp_server: MCPServerRef | None = None
    timeout_ms: int = 30_000
    idempotent: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalConfig:
    """Evaluation configuration for skills and agents."""

    dimensions: list[str] = field(default_factory=list)  # e.g., ["accuracy", "latency", "cost"]
    threshold: float = 0.8
    dataset_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CostConfig:
    """Budget limits for skills and agents."""

    max_cost_per_invocation: float | None = None
    daily_budget: float | None = None
    alert_threshold: float = 0.8  # fraction of budget that triggers alert


@dataclass(frozen=True)
class EscalationConfig:
    """Escalation rules for agents."""

    target: str | None = None  # agent or human to escalate to
    conditions: list[str] = field(default_factory=list)
    timeout_seconds: int = 3600


@dataclass(frozen=True)
class SkillSpec:
    """Declares a platform skill (RAPIDS component type: Skill).

    Skills are LLM-powered, single-shot components that add reasoning trace,
    confidence scoring, and evaluation endpoints.
    """

    name: str
    description: str
    model: ModelRef
    system_prompt: str
    tools: list[ToolSpec] = field(default_factory=list)
    guardrails: list[GuardrailRef] = field(default_factory=list)
    output_schema: dict[str, Any] = field(default_factory=dict)
    eval_config: EvalConfig = field(default_factory=EvalConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentSpec:
    """Declares an agent's identity, capabilities, and configuration.

    This is the primary input to a FrameworkAdapter. The adapter translates
    this spec into the framework-specific agent representation.

    Enriched with RAPIDS fields for capabilities, decision loop control,
    state management, escalation, evaluation, and cost governance.
    """

    name: str
    description: str
    framework: str  # e.g., "langgraph", "claude-agent-sdk", "crewai", "adk"
    model: ModelRef
    system_prompt: str
    tools: list[ToolSpec] = field(default_factory=list)
    guardrails: list[GuardrailRef] = field(default_factory=list)
    memory_config: MemoryConfig = field(default_factory=MemoryConfig)
    metadata: dict[str, Any] = field(default_factory=dict)
    # --- RAPIDS enrichments ---
    capabilities: list[str] = field(default_factory=list)
    decision_loop: dict[str, Any] = field(default_factory=dict)  # max_turns, exit_conditions
    state: dict[str, Any] = field(default_factory=dict)  # persistence, ttl
    escalation: EscalationConfig = field(default_factory=EscalationConfig)
    eval_config: EvalConfig = field(default_factory=EvalConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowSpec:
    """Declares a multi-agent workflow."""

    name: str
    description: str
    agents: list[str]  # Agent names (refs)
    topology: str  # "sequential", "parallel", "graph", "hierarchical"
    edges: list[dict[str, str]] = field(default_factory=list)
    state_schema: dict[str, Any] = field(default_factory=dict)
    human_in_the_loop: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent execution types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentInput:
    """Input to an agent invocation."""

    messages: list[dict[str, Any]]
    context: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None


class AgentEventType(enum.Enum):
    """Types of events emitted during agent execution.

    The event stream is the governance layer — every event is a checkpoint
    for validation, audit, and halting (RAPIDS principle).
    """

    TEXT_DELTA = "text_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    THINKING = "thinking"
    ERROR = "error"
    DONE = "done"
    STATE_CHECKPOINT = "state_checkpoint"
    # --- RAPIDS event types ---
    RESPONSE = "response"  # Final response from skill/agent
    ESCALATION = "escalation"  # Agent escalating to human or another agent
    GUARDRAIL_TRIGGER = "guardrail_trigger"  # Guardrail activated
    COST_CHECKPOINT = "cost_checkpoint"  # Cost tracking event
    # --- Memory subsystem events ---
    MEMORY_WRITE = "memory_write"  # Memory entry persisted
    MEMORY_EXPIRE = "memory_expire"  # Memory entries expired/cleaned
    MEMORY_SUMMARIZE = "memory_summarize"  # Conversation summarized


@dataclass
class AgentEvent:
    """Event emitted during agent execution (streaming)."""

    type: AgentEventType
    data: dict[str, Any] = field(default_factory=dict)
    agent_name: str | None = None
    timestamp: float | None = None


@dataclass
class StateSnapshot:
    """Serializable snapshot of agent state for checkpointing."""

    agent_name: str
    state: dict[str, Any]
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Framework Adapter protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class FrameworkAdapter(Protocol):
    """Protocol that every framework adapter must implement.

    Each adapter (LangGraph, ADK, CrewAI, Claude Agent SDK, etc.) translates
    the platform's AgentSpec into framework-specific constructs and handles
    execution, checkpointing, and lifecycle management.
    """

    @property
    def name(self) -> str:
        """Unique name of this adapter (e.g., 'langgraph', 'claude-agent-sdk')."""
        ...

    async def create_agent(self, spec: AgentSpec) -> Any:
        """Create a framework-specific agent from the platform AgentSpec."""
        ...

    async def execute(
        self,
        agent: Any,
        input: AgentInput,
    ) -> AsyncIterator[AgentEvent]:
        """Execute the agent and yield streaming events."""
        ...

    async def checkpoint(self, agent: Any) -> StateSnapshot:
        """Capture the current state of the agent for persistence."""
        ...

    async def restore(self, agent: Any, snapshot: StateSnapshot) -> None:
        """Restore agent state from a snapshot."""
        ...

    async def teardown(self, agent: Any) -> None:
        """Clean up resources associated with the agent."""
        ...


# ---------------------------------------------------------------------------
# Event interceptor protocol (RAPIDS governance layer)
# ---------------------------------------------------------------------------


@runtime_checkable
class EventInterceptor(Protocol):
    """Protocol for event stream interceptors.

    Interceptors sit between the agent runtime and the consumer of events.
    The platform controls which interceptors are active; teams control the
    agent implementation. This is the governance hook point.

    Returning None halts the event stream (e.g., policy violation).
    Returning a (possibly modified) event allows it to continue.
    """

    async def intercept(self, event: AgentEvent) -> AgentEvent | None:
        """Process an event. Return None to halt, or the event to continue."""
        ...


# ---------------------------------------------------------------------------
# Memory store protocol (multi-tenant memory subsystem)
# ---------------------------------------------------------------------------


@runtime_checkable
class MemoryStore(Protocol):
    """Protocol for persistent memory storage backends.

    All operations are scoped by MemoryScope to enforce multi-tenant isolation.
    Implementations include InMemoryMemoryStore (testing), RedisMemoryStore
    (production structured data), and vendor-specific vector stores via adapters.
    """

    async def write(self, entry: MemoryEntry) -> str:
        """Persist a memory entry. Returns the entry ID."""
        ...

    async def read(
        self,
        scope: MemoryScope,
        memory_type: MemoryType,
        limit: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> list[MemoryEntry]:
        """Read entries by scope and type (recency-ordered)."""
        ...

    async def search(
        self,
        scope: MemoryScope,
        memory_type: MemoryType,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Semantic similarity search using embeddings."""
        ...

    async def update(
        self,
        entry_id: str,
        scope: MemoryScope,
        updates: dict[str, Any],
    ) -> bool:
        """Update fields on an existing entry. Returns True if found."""
        ...

    async def delete(self, entry_id: str, scope: MemoryScope) -> bool:
        """Delete a single entry. Returns True if found."""
        ...

    async def delete_by_scope(
        self,
        scope: MemoryScope,
        memory_type: MemoryType | None = None,
    ) -> int:
        """Delete all entries for a scope (optionally filtered by type). Returns count."""
        ...

    async def expire(self, scope: MemoryScope, before_timestamp: float) -> int:
        """Delete entries older than the given timestamp. Returns count."""
        ...

    async def count(self, scope: MemoryScope, memory_type: MemoryType) -> int:
        """Count entries for a scope and type."""
        ...

    async def stats(self, scope: MemoryScope) -> dict[str, Any]:
        """Return per-type stats for a scope.

        Returns ``{memory_type_value: {"count": int, "size_bytes": int, "token_estimate": int}}``
        for every type that has entries under *scope*.
        """
        ...
