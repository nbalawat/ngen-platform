"""Tests for ngen_common.health — health check utilities."""

from __future__ import annotations

import pytest

from ngen_common.health import (
    DependencyHealth,
    HealthChecker,
    HealthResponse,
    HealthStatus,
)


class TestHealthStatus:
    def test_values(self) -> None:
        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.UNHEALTHY == "unhealthy"


class TestDependencyHealth:
    def test_basic(self) -> None:
        dep = DependencyHealth(name="postgres", status=HealthStatus.HEALTHY, latency_ms=2.5)
        assert dep.name == "postgres"
        assert dep.latency_ms == 2.5


class TestHealthResponse:
    def test_to_dict_minimal(self) -> None:
        resp = HealthResponse(service="svc", status=HealthStatus.HEALTHY)
        d = resp.to_dict()
        assert d["status"] == "healthy"
        assert d["service"] == "svc"
        assert "dependencies" not in d

    def test_to_dict_with_dependencies(self) -> None:
        resp = HealthResponse(
            service="svc",
            status=HealthStatus.DEGRADED,
            dependencies=[
                DependencyHealth(name="db", status=HealthStatus.HEALTHY, latency_ms=1.234),
                DependencyHealth(name="cache", status=HealthStatus.DEGRADED, details={"msg": "slow"}),
            ],
        )
        d = resp.to_dict()
        assert d["status"] == "degraded"
        assert len(d["dependencies"]) == 2
        assert d["dependencies"][0]["latency_ms"] == 1.23
        assert d["dependencies"][1]["details"] == {"msg": "slow"}


class TestHealthChecker:
    @pytest.mark.asyncio
    async def test_all_healthy(self) -> None:
        checker = HealthChecker("test-svc")

        async def ok_check() -> DependencyHealth:
            return DependencyHealth(name="db", status=HealthStatus.HEALTHY)

        checker.register("db", ok_check)
        result = await checker.check()
        assert result.status == HealthStatus.HEALTHY
        assert len(result.dependencies) == 1
        assert result.uptime_seconds > 0

    @pytest.mark.asyncio
    async def test_degraded_when_one_degraded(self) -> None:
        checker = HealthChecker("test-svc")

        async def healthy() -> DependencyHealth:
            return DependencyHealth(name="db", status=HealthStatus.HEALTHY)

        async def degraded() -> DependencyHealth:
            return DependencyHealth(name="cache", status=HealthStatus.DEGRADED)

        checker.register("db", healthy)
        checker.register("cache", degraded)
        result = await checker.check()
        assert result.status == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_unhealthy_when_one_unhealthy(self) -> None:
        checker = HealthChecker("test-svc")

        async def healthy() -> DependencyHealth:
            return DependencyHealth(name="db", status=HealthStatus.HEALTHY)

        async def dead() -> DependencyHealth:
            return DependencyHealth(name="cache", status=HealthStatus.UNHEALTHY)

        checker.register("db", healthy)
        checker.register("cache", dead)
        result = await checker.check()
        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_exception_becomes_unhealthy(self) -> None:
        checker = HealthChecker("test-svc")

        async def explode() -> DependencyHealth:
            raise ConnectionError("connection refused")

        checker.register("db", explode)
        result = await checker.check()
        assert result.status == HealthStatus.UNHEALTHY
        assert result.dependencies[0].details["error"] == "connection refused"
        assert result.dependencies[0].latency_ms is not None

    @pytest.mark.asyncio
    async def test_is_ready_true(self) -> None:
        checker = HealthChecker("svc")

        async def ok() -> DependencyHealth:
            return DependencyHealth(name="x", status=HealthStatus.HEALTHY)

        checker.register("x", ok)
        assert await checker.is_ready() is True

    @pytest.mark.asyncio
    async def test_is_ready_false_when_unhealthy(self) -> None:
        checker = HealthChecker("svc")

        async def bad() -> DependencyHealth:
            raise RuntimeError("down")

        checker.register("x", bad)
        assert await checker.is_ready() is False

    @pytest.mark.asyncio
    async def test_no_dependencies(self) -> None:
        checker = HealthChecker("svc")
        result = await checker.check()
        assert result.status == HealthStatus.HEALTHY
        assert result.dependencies == []

    @pytest.mark.asyncio
    async def test_measures_latency(self) -> None:
        checker = HealthChecker("svc")

        async def slow() -> DependencyHealth:
            import asyncio
            await asyncio.sleep(0.01)
            return DependencyHealth(name="slow-db", status=HealthStatus.HEALTHY)

        checker.register("slow-db", slow)
        result = await checker.check()
        assert result.dependencies[0].latency_ms >= 5  # At least ~10ms

    @pytest.mark.asyncio
    async def test_version(self) -> None:
        checker = HealthChecker("svc", version="1.2.3")
        result = await checker.check()
        assert result.version == "1.2.3"
