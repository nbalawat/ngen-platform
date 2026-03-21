package ngen.platform

# NGEN Platform OPA Policies
# Enforces platform-wide governance rules for multi-agent systems.
# Evaluated by the governance-service or as an admission controller.

import future.keywords.in
import future.keywords.if
import future.keywords.contains

# ──────────────────────────────────────────────────────────────────
# Cost governance
# ──────────────────────────────────────────────────────────────────

# Deny requests that exceed per-request cost limit
deny contains msg if {
    input.estimated_cost > input.policy.max_cost_per_request
    msg := sprintf("Estimated cost $%.4f exceeds limit $%.4f", [input.estimated_cost, input.policy.max_cost_per_request])
}

# Deny requests that exceed token limit
deny contains msg if {
    input.token_count > input.policy.max_tokens_per_request
    msg := sprintf("Token count %d exceeds limit %d", [input.token_count, input.policy.max_tokens_per_request])
}

# Warn when daily spend crosses alert threshold
warn contains msg if {
    input.daily_spend >= input.policy.daily_budget * input.policy.alert_threshold
    msg := sprintf("Daily spend $%.4f has reached %.0f%% of budget $%.2f", [
        input.daily_spend,
        input.policy.alert_threshold * 100,
        input.policy.daily_budget,
    ])
}

# ──────────────────────────────────────────────────────────────────
# Content filtering
# ──────────────────────────────────────────────────────────────────

# Deny content matching blocked patterns
deny contains msg if {
    some pattern in input.policy.blocked_patterns
    regex.match(pattern, input.content)
    msg := sprintf("Content matches blocked pattern: %s", [pattern])
}

# Deny content containing blocked topics
deny contains msg if {
    some topic in input.policy.blocked_topics
    contains(lower(input.content), lower(topic))
    msg := sprintf("Content contains blocked topic: %s", [topic])
}

# Deny content exceeding max length
deny contains msg if {
    input.policy.max_output_length > 0
    count(input.content) > input.policy.max_output_length
    msg := sprintf("Content length %d exceeds max %d", [count(input.content), input.policy.max_output_length])
}

# ──────────────────────────────────────────────────────────────────
# Tool restrictions
# ──────────────────────────────────────────────────────────────────

# Deny blocked tools
deny contains msg if {
    input.tool_name in input.policy.blocked_tools
    msg := sprintf("Tool '%s' is blocked by policy", [input.tool_name])
}

# Deny tools not in allowed list (when allowlist is defined)
deny contains msg if {
    count(input.policy.allowed_tools) > 0
    not input.tool_name in input.policy.allowed_tools
    msg := sprintf("Tool '%s' is not in the allowed list", [input.tool_name])
}

# Escalate tools requiring human approval
escalate contains msg if {
    input.tool_name in input.policy.require_approval
    msg := sprintf("Tool '%s' requires human approval", [input.tool_name])
}

# ──────────────────────────────────────────────────────────────────
# Rate limiting
# ──────────────────────────────────────────────────────────────────

deny contains msg if {
    input.requests_per_minute >= input.policy.max_requests_per_minute
    msg := sprintf("Rate %d RPM exceeds limit %d RPM", [input.requests_per_minute, input.policy.max_requests_per_minute])
}

deny contains msg if {
    input.requests_per_hour >= input.policy.max_requests_per_hour
    msg := sprintf("Rate %d RPH exceeds limit %d RPH", [input.requests_per_hour, input.policy.max_requests_per_hour])
}

# ──────────────────────────────────────────────────────────────────
# Tenant isolation
# ──────────────────────────────────────────────────────────────────

# Deny cross-tenant access
deny contains msg if {
    input.request_tenant != input.resource_tenant
    msg := sprintf("Cross-tenant access denied: tenant '%s' cannot access resources of tenant '%s'", [input.request_tenant, input.resource_tenant])
}

# ──────────────────────────────────────────────────────────────────
# Agent governance
# ──────────────────────────────────────────────────────────────────

# Deny agent creation beyond tenant limit
deny contains msg if {
    input.current_agent_count >= input.policy.max_agents
    msg := sprintf("Agent limit reached: %d/%d agents", [input.current_agent_count, input.policy.max_agents])
}

# Require system prompt for all agents
deny contains msg if {
    input.agent_spec.system_prompt == ""
    msg := "Agents must have a non-empty system prompt"
}

# ──────────────────────────────────────────────────────────────────
# Decision helpers
# ──────────────────────────────────────────────────────────────────

# Final decision: allowed if no deny rules triggered
default allow := true

allow := false if {
    count(deny) > 0
}
