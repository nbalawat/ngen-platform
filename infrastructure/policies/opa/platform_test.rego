package ngen.platform_test

import data.ngen.platform
import future.keywords.in

# ──────────────────────────────────────────────────────────────────
# Cost governance tests
# ──────────────────────────────────────────────────────────────────

test_allow_within_cost_limit {
    platform.allow with input as {
        "estimated_cost": 0.05,
        "policy": {"max_cost_per_request": 1.00},
    }
}

test_deny_exceeds_cost_limit {
    not platform.allow with input as {
        "estimated_cost": 2.00,
        "policy": {"max_cost_per_request": 1.00},
    }
}

test_deny_exceeds_token_limit {
    not platform.allow with input as {
        "token_count": 50000,
        "policy": {"max_tokens_per_request": 10000},
    }
}

test_warn_daily_spend_threshold {
    count(platform.warn) > 0 with input as {
        "daily_spend": 85.0,
        "policy": {
            "daily_budget": 100.0,
            "alert_threshold": 0.8,
        },
    }
}

# ──────────────────────────────────────────────────────────────────
# Content filtering tests
# ──────────────────────────────────────────────────────────────────

test_deny_blocked_pattern {
    not platform.allow with input as {
        "content": "SSN: 123-45-6789",
        "policy": {"blocked_patterns": ["\\d{3}-\\d{2}-\\d{4}"]},
    }
}

test_deny_blocked_topic {
    not platform.allow with input as {
        "content": "Tell me about weapons manufacturing",
        "policy": {"blocked_topics": ["weapons"]},
    }
}

test_allow_clean_content {
    platform.allow with input as {
        "content": "What is the weather today?",
        "policy": {"blocked_patterns": [], "blocked_topics": []},
    }
}

# ──────────────────────────────────────────────────────────────────
# Tool restriction tests
# ──────────────────────────────────────────────────────────────────

test_deny_blocked_tool {
    not platform.allow with input as {
        "tool_name": "delete_database",
        "policy": {"blocked_tools": ["delete_database", "drop_table"]},
    }
}

test_allow_unblocked_tool {
    platform.allow with input as {
        "tool_name": "search",
        "policy": {"blocked_tools": ["delete_database"]},
    }
}

test_escalate_approval_required {
    count(platform.escalate) > 0 with input as {
        "tool_name": "send_email",
        "policy": {"require_approval": ["send_email"]},
    }
}

# ──────────────────────────────────────────────────────────────────
# Tenant isolation tests
# ──────────────────────────────────────────────────────────────────

test_deny_cross_tenant {
    not platform.allow with input as {
        "request_tenant": "acme",
        "resource_tenant": "globex",
    }
}

test_allow_same_tenant {
    platform.allow with input as {
        "request_tenant": "acme",
        "resource_tenant": "acme",
    }
}
