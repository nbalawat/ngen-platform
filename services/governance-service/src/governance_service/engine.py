"""Policy evaluation engine.

Evaluates an EvalContext against all applicable policies in a namespace.
Each policy type has a dedicated evaluator that checks the context against
the policy's rules and produces violations if rules are breached.
"""

from __future__ import annotations

import re

from governance_service.models import (
    ContentFilterRule,
    CostLimitRule,
    EvalContext,
    EvalResult,
    Policy,
    PolicyAction,
    PolicyType,
    RateLimitRule,
    ToolRestrictionRule,
    Violation,
)
from governance_service.repository import PolicyRepository


class PolicyEngine:
    """Evaluates contexts against governance policies."""

    def __init__(self, repository: PolicyRepository) -> None:
        self._repo = repository

    def evaluate(self, context: EvalContext) -> EvalResult:
        """Evaluate context against all enabled policies in the namespace."""
        policies = self._repo.list(
            namespace=context.namespace, enabled_only=True
        )

        violations: list[Violation] = []
        warnings: list[Violation] = []

        for policy in policies:
            policy_violations = self._evaluate_policy(policy, context)
            for v in policy_violations:
                if v.action in (PolicyAction.BLOCK, PolicyAction.ESCALATE):
                    violations.append(v)
                else:
                    warnings.append(v)

        blocked = any(
            v.action in (PolicyAction.BLOCK, PolicyAction.ESCALATE)
            for v in violations
        )

        return EvalResult(
            allowed=not blocked,
            violations=violations,
            warnings=warnings,
            evaluated_policies=len(policies),
        )

    def _evaluate_policy(
        self, policy: Policy, context: EvalContext
    ) -> list[Violation]:
        """Dispatch evaluation to the appropriate type-specific evaluator."""
        evaluators = {
            PolicyType.CONTENT_FILTER: self._eval_content_filter,
            PolicyType.COST_LIMIT: self._eval_cost_limit,
            PolicyType.TOOL_RESTRICTION: self._eval_tool_restriction,
            PolicyType.RATE_LIMIT: self._eval_rate_limit,
        }
        evaluator = evaluators.get(policy.policy_type)
        if evaluator is None:
            return []
        return evaluator(policy, context)

    def _eval_content_filter(
        self, policy: Policy, context: EvalContext
    ) -> list[Violation]:
        rule = ContentFilterRule(**policy.rules)
        violations: list[Violation] = []
        content = context.content or ""

        for pattern in rule.blocked_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                violations.append(
                    Violation(
                        policy_id=policy.id,
                        policy_name=policy.name,
                        policy_type=policy.policy_type,
                        action=policy.action,
                        severity=policy.severity,
                        message=f"Content matches blocked pattern: {pattern}",
                        details={"pattern": pattern},
                    )
                )

        for topic in rule.blocked_topics:
            if topic.lower() in content.lower():
                violations.append(
                    Violation(
                        policy_id=policy.id,
                        policy_name=policy.name,
                        policy_type=policy.policy_type,
                        action=policy.action,
                        severity=policy.severity,
                        message=f"Content contains blocked topic: {topic}",
                        details={"topic": topic},
                    )
                )

        if rule.max_output_length and len(content) > rule.max_output_length:
            violations.append(
                Violation(
                    policy_id=policy.id,
                    policy_name=policy.name,
                    policy_type=policy.policy_type,
                    action=policy.action,
                    severity=policy.severity,
                    message=(
                        f"Content length {len(content)} exceeds max "
                        f"{rule.max_output_length}"
                    ),
                    details={
                        "length": len(content),
                        "max": rule.max_output_length,
                    },
                )
            )

        return violations

    def _eval_cost_limit(
        self, policy: Policy, context: EvalContext
    ) -> list[Violation]:
        rule = CostLimitRule(**policy.rules)
        violations: list[Violation] = []

        if (
            rule.max_cost_per_request is not None
            and context.estimated_cost is not None
            and context.estimated_cost > rule.max_cost_per_request
        ):
            violations.append(
                Violation(
                    policy_id=policy.id,
                    policy_name=policy.name,
                    policy_type=policy.policy_type,
                    action=policy.action,
                    severity=policy.severity,
                    message=(
                        f"Estimated cost ${context.estimated_cost:.4f} exceeds "
                        f"limit ${rule.max_cost_per_request:.4f}"
                    ),
                    details={
                        "estimated_cost": context.estimated_cost,
                        "limit": rule.max_cost_per_request,
                    },
                )
            )

        if (
            rule.max_tokens_per_request is not None
            and context.token_count is not None
            and context.token_count > rule.max_tokens_per_request
        ):
            violations.append(
                Violation(
                    policy_id=policy.id,
                    policy_name=policy.name,
                    policy_type=policy.policy_type,
                    action=policy.action,
                    severity=policy.severity,
                    message=(
                        f"Token count {context.token_count} exceeds "
                        f"limit {rule.max_tokens_per_request}"
                    ),
                    details={
                        "token_count": context.token_count,
                        "limit": rule.max_tokens_per_request,
                    },
                )
            )

        return violations

    def _eval_tool_restriction(
        self, policy: Policy, context: EvalContext
    ) -> list[Violation]:
        rule = ToolRestrictionRule(**policy.rules)
        violations: list[Violation] = []
        tool = context.tool_name

        if tool is None:
            return []

        if rule.blocked_tools and tool in rule.blocked_tools:
            violations.append(
                Violation(
                    policy_id=policy.id,
                    policy_name=policy.name,
                    policy_type=policy.policy_type,
                    action=policy.action,
                    severity=policy.severity,
                    message=f"Tool '{tool}' is blocked by policy",
                    details={"tool": tool},
                )
            )

        if rule.allowed_tools and tool not in rule.allowed_tools:
            violations.append(
                Violation(
                    policy_id=policy.id,
                    policy_name=policy.name,
                    policy_type=policy.policy_type,
                    action=policy.action,
                    severity=policy.severity,
                    message=f"Tool '{tool}' is not in allowed list",
                    details={"tool": tool, "allowed": rule.allowed_tools},
                )
            )

        if rule.require_approval and tool in rule.require_approval:
            violations.append(
                Violation(
                    policy_id=policy.id,
                    policy_name=policy.name,
                    policy_type=policy.policy_type,
                    action=PolicyAction.ESCALATE,
                    severity=policy.severity,
                    message=f"Tool '{tool}' requires human approval",
                    details={"tool": tool},
                )
            )

        return violations

    def _eval_rate_limit(
        self, policy: Policy, context: EvalContext
    ) -> list[Violation]:
        """Rate limit evaluation.

        Actual rate tracking requires a stateful counter (Redis, etc.).
        This evaluator checks if rate limit metadata is present in the context
        and validates against the policy rules.
        """
        rule = RateLimitRule(**policy.rules)
        violations: list[Violation] = []
        meta = context.metadata

        current_rpm = meta.get("requests_per_minute")
        if (
            rule.max_requests_per_minute is not None
            and current_rpm is not None
            and current_rpm >= rule.max_requests_per_minute
        ):
            violations.append(
                Violation(
                    policy_id=policy.id,
                    policy_name=policy.name,
                    policy_type=policy.policy_type,
                    action=policy.action,
                    severity=policy.severity,
                    message=(
                        f"Rate {current_rpm} RPM exceeds limit "
                        f"{rule.max_requests_per_minute} RPM"
                    ),
                    details={
                        "current": current_rpm,
                        "limit": rule.max_requests_per_minute,
                    },
                )
            )

        current_rph = meta.get("requests_per_hour")
        if (
            rule.max_requests_per_hour is not None
            and current_rph is not None
            and current_rph >= rule.max_requests_per_hour
        ):
            violations.append(
                Violation(
                    policy_id=policy.id,
                    policy_name=policy.name,
                    policy_type=policy.policy_type,
                    action=policy.action,
                    severity=policy.severity,
                    message=(
                        f"Rate {current_rph} RPH exceeds limit "
                        f"{rule.max_requests_per_hour} RPH"
                    ),
                    details={
                        "current": current_rph,
                        "limit": rule.max_requests_per_hour,
                    },
                )
            )

        return violations
