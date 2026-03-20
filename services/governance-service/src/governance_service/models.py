"""Domain models for the governance service.

Policies define guardrails that govern agent behavior. Each policy has a type
(content_filter, cost_limit, tool_restriction, rate_limit) and a rule set.
Policies are scoped to tenants (namespace) and can be attached to agents via
the CRD action_guards field.

Violations are records of policy breaches detected during evaluation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PolicyType(StrEnum):
    """Types of governance policies."""

    CONTENT_FILTER = "content_filter"
    COST_LIMIT = "cost_limit"
    TOOL_RESTRICTION = "tool_restriction"
    RATE_LIMIT = "rate_limit"


class PolicyAction(StrEnum):
    """Action to take when a policy is violated."""

    BLOCK = "block"
    WARN = "warn"
    LOG = "log"
    ESCALATE = "escalate"


class Severity(StrEnum):
    """Severity of a policy violation."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Policy rule schemas (type-specific)
# ---------------------------------------------------------------------------


class ContentFilterRule(BaseModel):
    """Rule for content-based filtering."""

    blocked_patterns: list[str] = Field(default_factory=list)
    blocked_topics: list[str] = Field(default_factory=list)
    max_output_length: int | None = None
    require_citations: bool = False


class CostLimitRule(BaseModel):
    """Rule for cost/budget governance."""

    max_cost_per_request: float | None = None
    max_tokens_per_request: int | None = None
    daily_budget: float | None = None
    alert_threshold: float = 0.8


class ToolRestrictionRule(BaseModel):
    """Rule for tool access control."""

    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[str] = Field(default_factory=list)
    require_approval: list[str] = Field(default_factory=list)


class RateLimitRule(BaseModel):
    """Rule for rate limiting."""

    max_requests_per_minute: int | None = None
    max_requests_per_hour: int | None = None
    max_concurrent: int | None = None


# ---------------------------------------------------------------------------
# Policy model
# ---------------------------------------------------------------------------


class PolicyCreate(BaseModel):
    """Request body for creating a policy."""

    name: str = Field(..., min_length=3, max_length=100)
    description: str = ""
    policy_type: PolicyType
    namespace: str = Field(default="default", min_length=1)
    action: PolicyAction = PolicyAction.BLOCK
    severity: Severity = Severity.MEDIUM
    rules: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class Policy(BaseModel):
    """A governance policy."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    policy_type: PolicyType
    namespace: str = "default"
    action: PolicyAction = PolicyAction.BLOCK
    severity: Severity = Severity.MEDIUM
    rules: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyUpdate(BaseModel):
    """Request body for updating a policy."""

    description: str | None = None
    action: PolicyAction | None = None
    severity: Severity | None = None
    rules: dict[str, Any] | None = None
    enabled: bool | None = None


# ---------------------------------------------------------------------------
# Evaluation request/response
# ---------------------------------------------------------------------------


class EvalContext(BaseModel):
    """Context for policy evaluation."""

    namespace: str = "default"
    agent_name: str | None = None
    tool_name: str | None = None
    content: str | None = None
    token_count: int | None = None
    estimated_cost: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Violation(BaseModel):
    """A policy violation detected during evaluation."""

    policy_id: str
    policy_name: str
    policy_type: PolicyType
    action: PolicyAction
    severity: Severity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class EvalResult(BaseModel):
    """Result of evaluating context against all applicable policies."""

    allowed: bool
    violations: list[Violation] = Field(default_factory=list)
    warnings: list[Violation] = Field(default_factory=list)
    evaluated_policies: int = 0
