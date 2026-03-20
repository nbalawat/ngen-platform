"""Configuration utilities for NGEN platform services.

Provides a base settings class with common patterns: env-var loading,
debug mode, service identity, and port configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServiceConfig:
    """Base configuration for any NGEN service.

    Values are loaded from environment variables with an optional prefix.
    Subclass and add fields for service-specific settings.
    """

    service_name: str = "unknown"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    namespace: str = "default"

    @classmethod
    def from_env(cls, prefix: str = "NGEN_", **overrides: Any) -> "ServiceConfig":
        """Create a config from environment variables.

        Reads:
          {prefix}SERVICE_NAME, {prefix}PORT, {prefix}DEBUG,
          {prefix}LOG_LEVEL, {prefix}NAMESPACE

        Any keyword argument overrides the environment value.
        """
        def _env(key: str, default: str) -> str:
            return os.environ.get(f"{prefix}{key}", default)

        return cls(
            service_name=overrides.get("service_name", _env("SERVICE_NAME", cls.service_name)),
            port=int(overrides.get("port", _env("PORT", str(cls.port)))),
            debug=overrides.get("debug", _env("DEBUG", str(cls.debug)).lower() in ("true", "1", "yes")),
            log_level=overrides.get("log_level", _env("LOG_LEVEL", cls.log_level)),
            namespace=overrides.get("namespace", _env("NAMESPACE", cls.namespace)),
        )


@dataclass
class DatabaseConfig:
    """Database connection configuration."""

    url: str = "sqlite+aiosqlite:///./ngen.db"
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False

    @classmethod
    def from_env(cls, prefix: str = "NGEN_", **overrides: Any) -> "DatabaseConfig":
        def _env(key: str, default: str) -> str:
            return os.environ.get(f"{prefix}{key}", default)

        return cls(
            url=overrides.get("url", _env("DATABASE_URL", cls.url)),
            pool_size=int(overrides.get("pool_size", _env("DB_POOL_SIZE", str(cls.pool_size)))),
            max_overflow=int(overrides.get("max_overflow", _env("DB_MAX_OVERFLOW", str(cls.max_overflow)))),
            echo=overrides.get("echo", _env("DB_ECHO", str(cls.echo)).lower() in ("true", "1", "yes")),
        )


@dataclass
class ServiceURLs:
    """URLs for inter-service communication."""

    workflow_engine: str = "http://localhost:8003"
    model_gateway: str = "http://localhost:8002"
    model_registry: str = "http://localhost:8001"
    tenant_service: str = "http://localhost:8000"
    governance: str = "http://localhost:8004"
    mcp_manager: str = "http://localhost:8005"

    @classmethod
    def from_env(cls, **overrides: Any) -> "ServiceURLs":
        return cls(
            workflow_engine=overrides.get("workflow_engine", os.environ.get("NGEN_WORKFLOW_URL", cls.workflow_engine)),
            model_gateway=overrides.get("model_gateway", os.environ.get("NGEN_GATEWAY_URL", cls.model_gateway)),
            model_registry=overrides.get("model_registry", os.environ.get("NGEN_REGISTRY_URL", cls.model_registry)),
            tenant_service=overrides.get("tenant_service", os.environ.get("NGEN_TENANT_URL", cls.tenant_service)),
            governance=overrides.get("governance", os.environ.get("NGEN_GOVERNANCE_URL", cls.governance)),
            mcp_manager=overrides.get("mcp_manager", os.environ.get("NGEN_MCP_URL", cls.mcp_manager)),
        )
