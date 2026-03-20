"""CRD (Custom Resource Definition) models for declarative platform resources.

All platform resources (Agents, Workflows, MCPServers, Models) are defined as
YAML manifests following Kubernetes CRD patterns. These Pydantic models parse
and validate the YAML.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Common CRD structures
# ---------------------------------------------------------------------------

API_VERSION = "ngen.io/v1"
SUPPORTED_API_VERSIONS = {"ngen.io/v1", "ngen.io/v1beta1", "ngen.io/v1alpha1"}


class CRDMetadata(BaseModel):
    """Metadata common to all CRD resources."""

    name: str = Field(..., min_length=1, max_length=253, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    namespace: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class ScalingSpec(BaseModel):
    """Auto-scaling configuration."""

    min_replicas: int = Field(default=1, ge=0, alias="minReplicas")
    max_replicas: int = Field(default=10, ge=1, alias="maxReplicas")

    model_config = {"populate_by_name": True}


class ObservabilitySpec(BaseModel):
    """Observability configuration for a resource."""

    tracing: bool = True
    cost_tracking: bool = Field(default=True, alias="costTracking")
    custom_metrics: list[str] = Field(default_factory=list, alias="customMetrics")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Agent CRD
# ---------------------------------------------------------------------------


class AgentToolRef(BaseModel):
    """Tool reference within an Agent spec."""

    name: str
    mcp_server: str | None = Field(default=None, alias="mcpServer")
    handler: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class AgentModelRef(BaseModel):
    """Model reference within an Agent spec."""

    name: str
    fallback: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class FrameworkType(StrEnum):
    """Supported agent framework types."""

    LANGGRAPH = "langgraph"
    CLAUDE_AGENT_SDK = "claude-agent-sdk"
    CREWAI = "crewai"
    ADK = "adk"
    MS_AGENT_FRAMEWORK = "ms-agent-framework"


class DecisionLoopSpec(BaseModel):
    """Decision loop configuration for agents (RAPIDS)."""

    max_turns: int = Field(default=25, alias="maxTurns")
    exit_conditions: list[str] = Field(default_factory=list, alias="exitConditions")

    model_config = {"populate_by_name": True}


class StateSpec(BaseModel):
    """State persistence configuration for agents (RAPIDS)."""

    persistence: str = "memory"  # "memory", "redis", "postgres"
    ttl_seconds: int | None = Field(default=None, alias="ttlSeconds")

    model_config = {"populate_by_name": True}


class ActionGuard(BaseModel):
    """Per-tool guardrail (RAPIDS action_guards)."""

    tool: str
    policy: str
    config: dict[str, Any] = Field(default_factory=dict)


class EscalationSpecCRD(BaseModel):
    """Escalation configuration for agents (RAPIDS)."""

    target: str | None = None
    conditions: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=3600, alias="timeoutSeconds")

    model_config = {"populate_by_name": True}


class EvalSpecCRD(BaseModel):
    """Multi-dimensional evaluation configuration (RAPIDS)."""

    dimensions: list[str] = Field(default_factory=list)
    threshold: float = 0.8
    dataset_ref: str | None = Field(default=None, alias="datasetRef")

    model_config = {"populate_by_name": True}


class CostSpecCRD(BaseModel):
    """Cost/budget governance for agents (RAPIDS)."""

    max_cost_per_invocation: float | None = Field(default=None, alias="maxCostPerInvocation")
    daily_budget: float | None = Field(default=None, alias="dailyBudget")
    alert_threshold: float = Field(default=0.8, alias="alertThreshold")

    model_config = {"populate_by_name": True}


class AgentSpecCRD(BaseModel):
    """Spec section of the Agent CRD.

    Enriched with RAPIDS fields for capabilities, decision loop, state,
    action guards, escalation, eval, cost, and labels.
    """

    framework: FrameworkType
    model: AgentModelRef
    system_prompt: str = Field(alias="systemPrompt")
    tools: list[AgentToolRef] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)
    scaling: ScalingSpec = Field(default_factory=ScalingSpec)
    observability: ObservabilitySpec = Field(default_factory=ObservabilitySpec)
    memory: dict[str, Any] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    # --- RAPIDS enrichments ---
    capabilities: list[str] = Field(default_factory=list)
    decision_loop: DecisionLoopSpec = Field(default_factory=DecisionLoopSpec, alias="decisionLoop")
    state: StateSpec = Field(default_factory=StateSpec)
    action_guards: list[ActionGuard] = Field(default_factory=list, alias="actionGuards")
    escalation: EscalationSpecCRD = Field(default_factory=EscalationSpecCRD)
    eval: EvalSpecCRD = Field(default_factory=EvalSpecCRD)
    cost: CostSpecCRD = Field(default_factory=CostSpecCRD)
    labels: dict[str, str] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class AgentCRD(BaseModel):
    """Agent Custom Resource Definition.

    Example:
        apiVersion: ngen.io/v1
        kind: Agent
        metadata:
          name: support-bot
          namespace: acme-corp
        spec:
          framework: langgraph
          model:
            name: claude-opus-4-6
          systemPrompt: "You are a support agent..."
          tools:
            - name: search-kb
              mcpServer: knowledge-base
    """

    api_version: str = Field(alias="apiVersion")
    kind: Literal["Agent"]
    metadata: CRDMetadata
    spec: AgentSpecCRD

    model_config = {"populate_by_name": True}

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, v: str) -> str:
        if v not in SUPPORTED_API_VERSIONS:
            raise ValueError(f"Unsupported apiVersion '{v}'. Supported: {SUPPORTED_API_VERSIONS}")
        return v


# ---------------------------------------------------------------------------
# Workflow CRD
# ---------------------------------------------------------------------------


class TopologyType(StrEnum):
    """Supported workflow topology types."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    GRAPH = "graph"
    HIERARCHICAL = "hierarchical"


class WorkflowAgentRef(BaseModel):
    """Agent reference within a Workflow spec."""

    ref: str
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    """Edge in a graph topology workflow."""

    source: str = Field(alias="from")
    target: str = Field(alias="to")
    condition: str | None = None

    model_config = {"populate_by_name": True}


class HumanInTheLoopSpec(BaseModel):
    """Human-in-the-loop configuration."""

    approval_gate: str | None = Field(default=None, alias="approvalGate")
    timeout_seconds: int = Field(default=3600, alias="timeoutSeconds")
    escalation: str | None = None

    model_config = {"populate_by_name": True}


class WorkflowSpecCRD(BaseModel):
    """Spec section of the Workflow CRD."""

    agents: list[WorkflowAgentRef]
    topology: TopologyType
    edges: list[WorkflowEdge] = Field(default_factory=list)
    human_in_the_loop: HumanInTheLoopSpec | None = Field(default=None, alias="humanInTheLoop")
    state_schema: dict[str, Any] = Field(default_factory=dict, alias="stateSchema")
    observability: ObservabilitySpec = Field(default_factory=ObservabilitySpec)

    model_config = {"populate_by_name": True}


class WorkflowCRD(BaseModel):
    """Workflow Custom Resource Definition."""

    api_version: str = Field(alias="apiVersion")
    kind: Literal["Workflow"]
    metadata: CRDMetadata
    spec: WorkflowSpecCRD

    model_config = {"populate_by_name": True}

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, v: str) -> str:
        if v not in SUPPORTED_API_VERSIONS:
            raise ValueError(f"Unsupported apiVersion '{v}'. Supported: {SUPPORTED_API_VERSIONS}")
        return v


# ---------------------------------------------------------------------------
# MCPServer CRD
# ---------------------------------------------------------------------------


class MCPSourceSpec(BaseModel):
    """Source specification for an MCP server."""

    type: str  # "openapi", "database", "custom"
    url: str | None = None
    schema_ref: str | None = Field(default=None, alias="schemaRef")
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class MCPAuthSpec(BaseModel):
    """Authentication specification for an MCP server."""

    type: str  # "oauth2", "api-key", "none"
    secret_ref: str | None = Field(default=None, alias="secretRef")
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class MCPServerSpecCRD(BaseModel):
    """Spec section of the MCPServer CRD."""

    source: MCPSourceSpec
    auth: MCPAuthSpec = Field(default_factory=lambda: MCPAuthSpec(type="none"))
    scaling: ScalingSpec = Field(default_factory=ScalingSpec)
    transport: str = "streamable-http"
    health_check_path: str = Field(default="/health", alias="healthCheckPath")

    model_config = {"populate_by_name": True}


class MCPServerCRD(BaseModel):
    """MCPServer Custom Resource Definition."""

    api_version: str = Field(alias="apiVersion")
    kind: Literal["MCPServer"]
    metadata: CRDMetadata
    spec: MCPServerSpecCRD

    model_config = {"populate_by_name": True}

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, v: str) -> str:
        if v not in SUPPORTED_API_VERSIONS:
            raise ValueError(f"Unsupported apiVersion '{v}'. Supported: {SUPPORTED_API_VERSIONS}")
        return v


# ---------------------------------------------------------------------------
# Model CRD
# ---------------------------------------------------------------------------


class ModelSpecCRD(BaseModel):
    """Spec section of the Model CRD."""

    provider: str  # "anthropic", "openai", "azure", "bedrock", etc.
    endpoint: str
    capabilities: list[str] = Field(default_factory=list)
    cost_per_m_token: dict[str, float] = Field(default_factory=dict, alias="costPerMToken")
    context_window: int | None = Field(default=None, alias="contextWindow")
    max_output_tokens: int | None = Field(default=None, alias="maxOutputTokens")
    parameters: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class ModelCRD(BaseModel):
    """Model Custom Resource Definition."""

    api_version: str = Field(alias="apiVersion")
    kind: Literal["Model"]
    metadata: CRDMetadata
    spec: ModelSpecCRD

    model_config = {"populate_by_name": True}

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, v: str) -> str:
        if v not in SUPPORTED_API_VERSIONS:
            raise ValueError(f"Unsupported apiVersion '{v}'. Supported: {SUPPORTED_API_VERSIONS}")
        return v


# ---------------------------------------------------------------------------
# Tool CRD (RAPIDS component type: Tool)
# ---------------------------------------------------------------------------


class ToolSpecCRD(BaseModel):
    """Spec section of the Tool CRD.

    Tools are deterministic, stateless functions with no LLM involvement.
    """

    handler: str  # Python dotted path or MCP server reference
    input_schema: dict[str, Any] = Field(default_factory=dict, alias="inputSchema")
    output_schema: dict[str, Any] = Field(default_factory=dict, alias="outputSchema")
    timeout_ms: int = Field(default=30_000, alias="timeoutMs")
    idempotent: bool = False
    health_check: str | None = Field(default=None, alias="healthCheck")
    mcp_server: str | None = Field(default=None, alias="mcpServer")

    model_config = {"populate_by_name": True}


class ToolCRD(BaseModel):
    """Tool Custom Resource Definition (RAPIDS component type: Tool).

    Example:
        apiVersion: ngen.io/v1
        kind: Tool
        metadata:
          name: search-kb
          namespace: acme-corp
        spec:
          handler: tools.search.search_knowledge_base
          inputSchema:
            type: object
            properties:
              query: {type: string}
          timeoutMs: 5000
          idempotent: true
    """

    api_version: str = Field(alias="apiVersion")
    kind: Literal["Tool"]
    metadata: CRDMetadata
    spec: ToolSpecCRD

    model_config = {"populate_by_name": True}

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, v: str) -> str:
        if v not in SUPPORTED_API_VERSIONS:
            raise ValueError(f"Unsupported apiVersion '{v}'. Supported: {SUPPORTED_API_VERSIONS}")
        return v


# ---------------------------------------------------------------------------
# Skill CRD (RAPIDS component type: Skill)
# ---------------------------------------------------------------------------


class SkillSpecCRD(BaseModel):
    """Spec section of the Skill CRD.

    Skills are LLM-powered, single-shot components that add reasoning trace,
    confidence scoring, and evaluation endpoints.
    """

    model: AgentModelRef
    system_prompt: str = Field(alias="systemPrompt")
    tools: list[AgentToolRef] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)
    output_schema: dict[str, Any] = Field(default_factory=dict, alias="outputSchema")
    eval: EvalSpecCRD = Field(default_factory=EvalSpecCRD)
    cost: CostSpecCRD = Field(default_factory=CostSpecCRD)
    scaling: ScalingSpec = Field(default_factory=ScalingSpec)
    observability: ObservabilitySpec = Field(default_factory=ObservabilitySpec)

    model_config = {"populate_by_name": True}


class SkillCRD(BaseModel):
    """Skill Custom Resource Definition (RAPIDS component type: Skill).

    Example:
        apiVersion: ngen.io/v1
        kind: Skill
        metadata:
          name: summarizer
          namespace: acme-corp
        spec:
          model:
            name: claude-sonnet-4-6
          systemPrompt: "Summarize the provided text concisely."
          outputSchema:
            type: object
            properties:
              summary: {type: string}
              confidence: {type: number}
    """

    api_version: str = Field(alias="apiVersion")
    kind: Literal["Skill"]
    metadata: CRDMetadata
    spec: SkillSpecCRD

    model_config = {"populate_by_name": True}

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, v: str) -> str:
        if v not in SUPPORTED_API_VERSIONS:
            raise ValueError(f"Unsupported apiVersion '{v}'. Supported: {SUPPORTED_API_VERSIONS}")
        return v


# ---------------------------------------------------------------------------
# Memory CRD
# ---------------------------------------------------------------------------


class MemoryPolicyCRD(BaseModel):
    """Retention and lifecycle policy for memory entries (CRD representation)."""

    max_entries: int | None = Field(default=None, alias="maxEntries")
    ttl_seconds: int | None = Field(default=None, alias="ttlSeconds")
    summarization_threshold: int | None = Field(
        default=None, alias="summarizationThreshold"
    )
    retention_days: int | None = Field(default=None, alias="retentionDays")

    model_config = {"populate_by_name": True}


class MemoryTypeConfigCRD(BaseModel):
    """Per-memory-type configuration within a MemoryCRD spec."""

    type: str  # MemoryType value (e.g., "conversational", "knowledge_base")
    enabled: bool = True
    backend: str | None = None  # override default: "redis", "pgvector", etc.
    policy: MemoryPolicyCRD = Field(default_factory=MemoryPolicyCRD)

    model_config = {"populate_by_name": True}


class MemorySpecCRD(BaseModel):
    """Spec for the Memory CRD — declarative memory configuration."""

    memory_types: list[MemoryTypeConfigCRD] = Field(
        default_factory=list, alias="memoryTypes"
    )
    embedding_model: str | None = Field(default=None, alias="embeddingModel")
    context_budget_tokens: int = Field(default=4000, alias="contextBudgetTokens")
    default_backend: str = Field(default="redis", alias="defaultBackend")
    default_policy: MemoryPolicyCRD = Field(
        default_factory=MemoryPolicyCRD, alias="defaultPolicy"
    )

    model_config = {"populate_by_name": True}


class MemoryCRD(BaseModel):
    """CRD for declarative memory configuration (kind: Memory).

    Tenants specify which memory types they need, backend preferences,
    retention policies, and embedding model. The platform handles all
    underlying plumbing — storage provisioning, namespace isolation,
    lifecycle management, and context retrieval.

    Example YAML::

        apiVersion: ngen.io/v1
        kind: Memory
        metadata:
          name: support-bot-memory
          namespace: acme-corp
        spec:
          embeddingModel: sentence-transformers/paraphrase-mpnet-base-v2
          contextBudgetTokens: 8000
          defaultBackend: redis
          defaultPolicy:
            ttlSeconds: 86400
            summarizationThreshold: 50
          memoryTypes:
            - type: conversational
              policy:
                ttlSeconds: 3600
            - type: knowledge_base
              backend: pgvector
            - type: summary
            - type: tool_log
              policy:
                retentionDays: 30
    """

    api_version: str = Field(alias="apiVersion")
    kind: Literal["Memory"]
    metadata: CRDMetadata
    spec: MemorySpecCRD

    model_config = {"populate_by_name": True}

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, v: str) -> str:
        if v not in SUPPORTED_API_VERSIONS:
            raise ValueError(
                f"Unsupported apiVersion '{v}'. Supported: {SUPPORTED_API_VERSIONS}"
            )
        return v


# ---------------------------------------------------------------------------
# CRD type mapping and parsing utilities
# ---------------------------------------------------------------------------

CRDType = AgentCRD | WorkflowCRD | MCPServerCRD | ModelCRD | ToolCRD | SkillCRD | MemoryCRD

_CRD_KIND_MAP: dict[str, type[CRDType]] = {
    "Agent": AgentCRD,
    "Workflow": WorkflowCRD,
    "MCPServer": MCPServerCRD,
    "Model": ModelCRD,
    "Tool": ToolCRD,
    "Skill": SkillCRD,
    "Memory": MemoryCRD,
}


def parse_crd(data: dict[str, Any]) -> CRDType:
    """Parse a CRD from a dictionary (e.g., loaded from YAML).

    Args:
        data: Dictionary representation of the CRD.

    Returns:
        The appropriate CRD model instance.

    Raises:
        ValueError: If the kind is unknown or the data is invalid.
    """
    kind = data.get("kind")
    if kind is None:
        raise ValueError("CRD must have a 'kind' field")

    crd_class = _CRD_KIND_MAP.get(kind)
    if crd_class is None:
        raise ValueError(f"Unknown CRD kind '{kind}'. Supported: {list(_CRD_KIND_MAP.keys())}")

    return crd_class.model_validate(data)


def parse_crd_file(path: str | Path) -> list[CRDType]:
    """Parse one or more CRDs from a YAML file (supports multi-document YAML).

    Args:
        path: Path to the YAML file.

    Returns:
        List of parsed CRD model instances.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If any document is invalid.
    """
    path = Path(path)
    content = path.read_text()
    documents = list(yaml.safe_load_all(content))
    results: list[CRDType] = []
    for doc in documents:
        if doc is not None:
            results.append(parse_crd(doc))
    return results


def validate_crd(data: dict[str, Any]) -> list[str]:
    """Validate a CRD dictionary and return a list of errors (empty if valid).

    Args:
        data: Dictionary representation of the CRD.

    Returns:
        List of validation error messages. Empty list means valid.
    """
    errors: list[str] = []

    kind = data.get("kind")
    if kind is None:
        errors.append("Missing required field: 'kind'")
        return errors

    api_version = data.get("apiVersion")
    if api_version is None:
        errors.append("Missing required field: 'apiVersion'")

    if api_version and api_version not in SUPPORTED_API_VERSIONS:
        errors.append(
            f"Unsupported apiVersion '{api_version}'. Supported: {SUPPORTED_API_VERSIONS}"
        )

    crd_class = _CRD_KIND_MAP.get(kind)
    if crd_class is None:
        errors.append(f"Unknown kind '{kind}'. Supported: {list(_CRD_KIND_MAP.keys())}")
        return errors

    try:
        crd_class.model_validate(data)
    except Exception as e:
        errors.append(str(e))

    return errors
