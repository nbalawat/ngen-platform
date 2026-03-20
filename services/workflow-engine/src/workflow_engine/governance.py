"""Governance integration for the Workflow Engine.

Provides a GovernanceGuard that evaluates agent events against governance
policies. When a policy violation is detected, it emits GUARDRAIL_TRIGGER
events and optionally blocks the agent from proceeding.

The guard can work in two modes:
1. Inline — uses the governance engine directly (no HTTP, for co-located deployments)
2. Remote — calls the governance REST API (for distributed deployments)

This module implements the inline mode using the EventInterceptor protocol.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ngen_framework_core.protocols import (
    AgentEvent,
    AgentEventType,
    AgentInput,
)

logger = logging.getLogger(__name__)


class GovernanceGuard:
    """Evaluates governance policies during workflow execution.

    Checks:
    - Pre-execution: content filters on input, tool restrictions, cost limits
    - Post-event: content filters on agent output, cost checkpoints

    Uses the governance engine directly (inline mode).
    """

    def __init__(
        self,
        engine: Any | None = None,
        namespace: str = "default",
    ) -> None:
        self._engine = engine
        self._namespace = namespace
        self._violations: list[dict[str, Any]] = []

    @property
    def violations(self) -> list[dict[str, Any]]:
        return list(self._violations)

    def set_namespace(self, namespace: str) -> None:
        self._namespace = namespace

    async def check_input(
        self,
        agent_name: str,
        agent_input: AgentInput,
    ) -> list[AgentEvent]:
        """Check governance policies before agent execution.

        Returns a list of GUARDRAIL_TRIGGER events for any violations.
        If any violation has action=block, the caller should skip execution.
        """
        if self._engine is None:
            return []

        # Extract content from input messages
        content_parts = [
            msg.get("content", "") for msg in agent_input.messages
        ]
        content = " ".join(content_parts)

        from governance_service.models import EvalContext

        ctx = EvalContext(
            namespace=self._namespace,
            agent_name=agent_name,
            content=content,
            metadata=agent_input.context,
        )

        result = self._engine.evaluate(ctx)
        events: list[AgentEvent] = []

        for violation in result.violations:
            v_data = {
                "policy_name": violation.policy_name,
                "policy_type": violation.policy_type,
                "action": violation.action,
                "severity": violation.severity,
                "message": violation.message,
                "phase": "pre_execution",
                "agent_name": agent_name,
            }
            self._violations.append(v_data)
            events.append(AgentEvent(
                type=AgentEventType.GUARDRAIL_TRIGGER,
                data=v_data,
                agent_name=agent_name,
                timestamp=time.time(),
            ))

        for warning in result.warnings:
            w_data = {
                "policy_name": warning.policy_name,
                "policy_type": warning.policy_type,
                "action": warning.action,
                "severity": warning.severity,
                "message": warning.message,
                "phase": "pre_execution",
                "agent_name": agent_name,
            }
            events.append(AgentEvent(
                type=AgentEventType.GUARDRAIL_TRIGGER,
                data=w_data,
                agent_name=agent_name,
                timestamp=time.time(),
            ))

        return events

    async def check_tool(
        self,
        agent_name: str,
        tool_name: str,
    ) -> list[AgentEvent]:
        """Check if a tool is allowed by governance policies."""
        if self._engine is None:
            return []

        from governance_service.models import EvalContext

        ctx = EvalContext(
            namespace=self._namespace,
            agent_name=agent_name,
            tool_name=tool_name,
        )

        result = self._engine.evaluate(ctx)
        events: list[AgentEvent] = []

        for violation in result.violations:
            v_data = {
                "policy_name": violation.policy_name,
                "policy_type": violation.policy_type,
                "action": violation.action,
                "severity": violation.severity,
                "message": violation.message,
                "phase": "tool_check",
                "agent_name": agent_name,
                "tool_name": tool_name,
            }
            self._violations.append(v_data)
            events.append(AgentEvent(
                type=AgentEventType.GUARDRAIL_TRIGGER,
                data=v_data,
                agent_name=agent_name,
                timestamp=time.time(),
            ))

        return events

    async def check_output(
        self,
        agent_name: str,
        content: str,
        estimated_cost: float | None = None,
        token_count: int | None = None,
    ) -> list[AgentEvent]:
        """Check governance policies on agent output."""
        if self._engine is None:
            return []

        from governance_service.models import EvalContext

        ctx = EvalContext(
            namespace=self._namespace,
            agent_name=agent_name,
            content=content,
            estimated_cost=estimated_cost,
            token_count=token_count,
        )

        result = self._engine.evaluate(ctx)
        events: list[AgentEvent] = []

        for violation in result.violations:
            v_data = {
                "policy_name": violation.policy_name,
                "policy_type": violation.policy_type,
                "action": violation.action,
                "severity": violation.severity,
                "message": violation.message,
                "phase": "post_execution",
                "agent_name": agent_name,
            }
            self._violations.append(v_data)
            events.append(AgentEvent(
                type=AgentEventType.GUARDRAIL_TRIGGER,
                data=v_data,
                agent_name=agent_name,
                timestamp=time.time(),
            ))

        for warning in result.warnings:
            w_data = {
                "policy_name": warning.policy_name,
                "policy_type": warning.policy_type,
                "action": warning.action,
                "severity": warning.severity,
                "message": warning.message,
                "phase": "post_execution",
                "agent_name": agent_name,
            }
            events.append(AgentEvent(
                type=AgentEventType.GUARDRAIL_TRIGGER,
                data=w_data,
                agent_name=agent_name,
                timestamp=time.time(),
            ))

        return events

    def is_blocked(self) -> bool:
        """Check if any violation requires blocking."""
        return any(v.get("action") == "block" for v in self._violations)

    def reset(self) -> None:
        """Clear accumulated violations."""
        self._violations = []
