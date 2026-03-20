"""Health check utilities for NGEN platform services.

Provides standard health/readiness endpoint helpers and dependency
checking patterns used across all services.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class DependencyHealth:
    """Health status of a single dependency."""

    name: str
    status: HealthStatus
    latency_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthResponse:
    """Aggregated health response for a service."""

    service: str
    status: HealthStatus
    version: str = "0.1.0"
    uptime_seconds: float = 0.0
    dependencies: list[DependencyHealth] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status.value,
            "service": self.service,
            "version": self.version,
            "uptime_seconds": round(self.uptime_seconds, 2),
        }
        if self.dependencies:
            result["dependencies"] = [
                {
                    "name": d.name,
                    "status": d.status.value,
                    **({"latency_ms": round(d.latency_ms, 2)} if d.latency_ms is not None else {}),
                    **({"details": d.details} if d.details else {}),
                }
                for d in self.dependencies
            ]
        return result


# Type alias for async health check functions
HealthCheck = Callable[[], Awaitable[DependencyHealth]]


class HealthChecker:
    """Runs health checks against registered dependencies.

    Usage:
        checker = HealthChecker("workflow-engine", version="0.2.0")
        checker.register("postgres", check_postgres)
        checker.register("redis", check_redis)

        response = await checker.check()
    """

    def __init__(self, service_name: str, version: str = "0.1.0") -> None:
        self.service_name = service_name
        self.version = version
        self._checks: dict[str, HealthCheck] = {}
        self._start_time = time.monotonic()

    def register(self, name: str, check: HealthCheck) -> None:
        """Register a dependency health check."""
        self._checks[name] = check

    async def check(self) -> HealthResponse:
        """Run all registered health checks and return aggregated result."""
        dependencies: list[DependencyHealth] = []

        for name, check_fn in self._checks.items():
            start = time.monotonic()
            try:
                dep = await check_fn()
                if dep.latency_ms is None:
                    dep.latency_ms = (time.monotonic() - start) * 1000
                dependencies.append(dep)
            except Exception as exc:
                dependencies.append(
                    DependencyHealth(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        latency_ms=(time.monotonic() - start) * 1000,
                        details={"error": str(exc)},
                    )
                )

        # Determine overall status
        if any(d.status == HealthStatus.UNHEALTHY for d in dependencies):
            overall = HealthStatus.UNHEALTHY
        elif any(d.status == HealthStatus.DEGRADED for d in dependencies):
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return HealthResponse(
            service=self.service_name,
            status=overall,
            version=self.version,
            uptime_seconds=time.monotonic() - self._start_time,
            dependencies=dependencies,
        )

    async def is_ready(self) -> bool:
        """Quick readiness check — returns False if any dependency is unhealthy."""
        response = await self.check()
        return response.status != HealthStatus.UNHEALTHY
