"""ngen-common — shared utilities for the NGEN platform."""

from ngen_common.errors import (
    ConflictError,
    NgenError,
    NotFoundError,
    PolicyViolationError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
)
from ngen_common.health import (
    DependencyHealth,
    HealthCheck,
    HealthChecker,
    HealthResponse,
    HealthStatus,
)
from ngen_common.logging import JSONFormatter, get_logger, setup_logging
from ngen_common.config import DatabaseConfig, ServiceConfig, ServiceURLs
from ngen_common.observability import (
    CorrelationIDMiddleware,
    MetricsStore,
    RequestMetricsMiddleware,
    TraceContextFilter,
    add_observability,
    get_metrics_store,
    get_request_id,
    get_trace_context,
    reset_metrics_store,
    set_trace_context,
)
from ngen_common.error_handlers import add_error_handlers
from ngen_common.events import (
    Event,
    EventBus,
    InMemoryEventBus,
    NATSEventBus,
    Subjects,
    add_event_bus,
    publish_audit_event,
    publish_cost_event,
)
from ngen_common.auth import (
    APIKeyStore,
    AuthConfig,
    AuthIdentity,
    AuthMiddleware,
    AuthMode,
    JWTError,
    JWTValidator,
    add_auth,
    create_jwt,
    require_role,
    require_scope,
)

__all__ = [
    # errors
    "NgenError",
    "NotFoundError",
    "ConflictError",
    "ValidationError",
    "PolicyViolationError",
    "RateLimitError",
    "ServiceUnavailableError",
    # health
    "HealthStatus",
    "DependencyHealth",
    "HealthResponse",
    "HealthCheck",
    "HealthChecker",
    # logging
    "JSONFormatter",
    "setup_logging",
    "get_logger",
    # config
    "ServiceConfig",
    "DatabaseConfig",
    "ServiceURLs",
    # observability
    "CorrelationIDMiddleware",
    "RequestMetricsMiddleware",
    "MetricsStore",
    "TraceContextFilter",
    "add_observability",
    "get_metrics_store",
    "reset_metrics_store",
    "get_trace_context",
    "set_trace_context",
    "get_request_id",
    # auth
    "APIKeyStore",
    "AuthConfig",
    "AuthIdentity",
    "AuthMiddleware",
    "AuthMode",
    "JWTError",
    "JWTValidator",
    "add_auth",
    "create_jwt",
    "require_role",
    "require_scope",
    # error handlers
    "add_error_handlers",
    # events
    "Event",
    "EventBus",
    "InMemoryEventBus",
    "NATSEventBus",
    "Subjects",
    "publish_cost_event",
    "publish_audit_event",
    "add_event_bus",
]
