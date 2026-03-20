"""NGEN Framework Core - Protocol classes and CRD models for the multi-agent platform.

Component type model (RAPIDS methodology):
- Tool: Deterministic function, stateless, no LLM
- Skill: LLM-powered, single-shot, reasoning trace + confidence
- Agent: Autonomous, multi-turn, stateful, event stream contract
"""

from ngen_framework_core.crd import (
    AgentCRD,
    MCPServerCRD,
    MemoryCRD,
    ModelCRD,
    SkillCRD,
    ToolCRD,
    WorkflowCRD,
    parse_crd,
    parse_crd_file,
    validate_crd,
)
from ngen_framework_core.executor import AgentExecutor, ToolExecutor
from ngen_framework_core.memory_interceptor import MemoryInterceptor
from ngen_framework_core.memory_manager import DefaultMemoryManager
from ngen_framework_core.memory_registry import MemoryRegistry
from ngen_framework_core.memory_store import InMemoryMemoryStore, RedisMemoryStore
from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
    AgentSpec,
    ComponentType,
    CostConfig,
    EscalationConfig,
    EvalConfig,
    EventInterceptor,
    FrameworkAdapter,
    GuardrailRef,
    MCPServerRef,
    MemoryConfig,
    MemoryEntry,
    MemoryPolicy,
    MemoryScope,
    MemoryStore,
    MemoryType,
    ModelRef,
    SkillSpec,
    StateSnapshot,
    ToolComponentSpec,
    ToolSpec,
    WorkflowSpec,
)
from ngen_framework_core.registry import (
    AdapterRegistry,
    ComponentRegistry,
    get_adapter,
    get_registry,
    reset_registry,
)
from ngen_framework_core.state_store import (
    InMemoryStateStore,
    RedisStateStore,
    StateStore,
)

__all__ = [
    "AdapterRegistry",
    "AgentCRD",
    "AgentEvent",
    "AgentEventType",
    "AgentExecutor",
    "AgentInput",
    "AgentSpec",
    "ComponentRegistry",
    "ComponentType",
    "CostConfig",
    "DefaultMemoryManager",
    "EscalationConfig",
    "EvalConfig",
    "EventInterceptor",
    "FrameworkAdapter",
    "GuardrailRef",
    "InMemoryMemoryStore",
    "InMemoryStateStore",
    "MCPServerCRD",
    "MCPServerRef",
    "MemoryConfig",
    "MemoryCRD",
    "MemoryEntry",
    "MemoryInterceptor",
    "MemoryPolicy",
    "MemoryRegistry",
    "MemoryScope",
    "MemoryStore",
    "MemoryType",
    "ModelCRD",
    "ModelRef",
    "RedisMemoryStore",
    "RedisStateStore",
    "SkillCRD",
    "SkillSpec",
    "StateSnapshot",
    "StateStore",
    "ToolCRD",
    "ToolComponentSpec",
    "ToolExecutor",
    "ToolSpec",
    "WorkflowCRD",
    "WorkflowSpec",
    "get_adapter",
    "get_registry",
    "parse_crd",
    "parse_crd_file",
    "reset_registry",
    "validate_crd",
]
