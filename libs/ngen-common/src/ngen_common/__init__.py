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
]
