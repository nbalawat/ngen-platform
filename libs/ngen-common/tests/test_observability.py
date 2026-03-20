"""Tests for observability middleware — correlation IDs, metrics, trace context.

Uses real FastAPI apps with ASGI transport. No mocks.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI, Request

from ngen_common.observability import (
    CorrelationIDMiddleware,
    MetricsStore,
    RequestMetricsMiddleware,
    RequestMetric,
    TraceContextFilter,
    add_observability,
    get_request_id,
    get_trace_context,
    reset_metrics_store,
    set_trace_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(store: MetricsStore | None = None) -> FastAPI:
    """Create a test FastAPI app with observability middleware."""
    app = FastAPI()
    actual_store = add_observability(app, service_name="test-svc", metrics_store=store)

    @app.get("/hello")
    async def hello():
        return {"message": "world"}

    @app.get("/trace")
    async def trace(request: Request):
        """Return trace context visible to the handler."""
        ctx = get_trace_context()
        return {
            "request_id": ctx.get("request_id", ""),
            "tenant_id": ctx.get("tenant_id", ""),
            "state_request_id": getattr(request.state, "request_id", ""),
        }

    @app.get("/error")
    async def error():
        raise ValueError("test error")

    @app.get("/items/{item_id}")
    async def get_item(item_id: str):
        return {"id": item_id}

    @app.exception_handler(ValueError)
    async def handle_value_error(request, exc):
        from starlette.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=500)

    return app


async def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Trace Context unit tests
# ---------------------------------------------------------------------------


class TestTraceContext:
    """Tests for trace context variable management."""

    def test_default_empty(self):
        ctx = get_trace_context()
        assert ctx == {} or isinstance(ctx, dict)

    def test_set_and_get(self):
        set_trace_context({"request_id": "abc-123", "tenant_id": "t1"})
        ctx = get_trace_context()
        assert ctx["request_id"] == "abc-123"
        assert ctx["tenant_id"] == "t1"
        # Cleanup
        set_trace_context({})

    def test_get_request_id(self):
        set_trace_context({"request_id": "req-456"})
        assert get_request_id() == "req-456"
        set_trace_context({})

    def test_get_request_id_none_when_empty(self):
        set_trace_context({})
        assert get_request_id() is None

    async def test_context_isolated_per_task(self):
        """Context variables are isolated per async task."""
        results = {}

        async def task(name: str, req_id: str):
            set_trace_context({"request_id": req_id})
            await asyncio.sleep(0.01)
            results[name] = get_request_id()

        await asyncio.gather(
            task("a", "id-a"),
            task("b", "id-b"),
        )
        assert results["a"] == "id-a"
        assert results["b"] == "id-b"


# ---------------------------------------------------------------------------
# CorrelationIDMiddleware tests
# ---------------------------------------------------------------------------


class TestCorrelationIDMiddleware:
    """Tests for request ID propagation."""

    async def test_generates_request_id(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/hello")
        assert resp.status_code == 200
        req_id = resp.headers.get("X-Request-ID")
        assert req_id is not None
        assert len(req_id) > 0

    async def test_propagates_provided_request_id(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/hello", headers={"X-Request-ID": "custom-123"})
        assert resp.headers["X-Request-ID"] == "custom-123"

    async def test_propagates_trace_id_header(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/hello", headers={"X-Trace-ID": "trace-456"})
        assert resp.headers["X-Request-ID"] == "trace-456"

    async def test_request_id_prefers_x_request_id(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get(
            "/hello",
            headers={"X-Request-ID": "req-1", "X-Trace-ID": "trace-2"},
        )
        assert resp.headers["X-Request-ID"] == "req-1"

    async def test_tenant_id_propagated(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get(
            "/hello", headers={"X-Tenant-ID": "acme-corp"}
        )
        assert resp.headers["X-Tenant-ID"] == "acme-corp"

    async def test_trace_context_in_handler(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get(
            "/trace",
            headers={"X-Request-ID": "ctx-789", "X-Tenant-ID": "my-tenant"},
        )
        data = resp.json()
        assert data["request_id"] == "ctx-789"
        assert data["tenant_id"] == "my-tenant"
        assert data["state_request_id"] == "ctx-789"

    async def test_unique_ids_for_concurrent_requests(self):
        app = _make_app()
        client = await _client(app)
        responses = await asyncio.gather(
            client.get("/hello"),
            client.get("/hello"),
            client.get("/hello"),
        )
        ids = [r.headers["X-Request-ID"] for r in responses]
        assert len(set(ids)) == 3  # All unique


# ---------------------------------------------------------------------------
# RequestMetric unit tests
# ---------------------------------------------------------------------------


class TestRequestMetric:
    """Tests for the RequestMetric data class."""

    def test_record_basic(self):
        m = RequestMetric(method="GET", path="/test")
        m.record(200, 15.0)
        assert m.total_requests == 1
        assert m.total_errors == 0
        assert m.avg_latency_ms == 15.0
        assert m.min_latency_ms == 15.0
        assert m.max_latency_ms == 15.0

    def test_record_multiple(self):
        m = RequestMetric(method="GET", path="/test")
        m.record(200, 10.0)
        m.record(200, 20.0)
        m.record(500, 30.0)
        assert m.total_requests == 3
        assert m.total_errors == 1
        assert m.avg_latency_ms == 20.0
        assert m.min_latency_ms == 10.0
        assert m.max_latency_ms == 30.0

    def test_status_counts(self):
        m = RequestMetric(method="POST", path="/api")
        m.record(200, 5.0)
        m.record(201, 5.0)
        m.record(200, 5.0)
        m.record(400, 5.0)
        assert m.status_counts[200] == 2
        assert m.status_counts[201] == 1
        assert m.status_counts[400] == 1

    def test_avg_latency_zero_requests(self):
        m = RequestMetric(method="GET", path="/")
        assert m.avg_latency_ms == 0.0


# ---------------------------------------------------------------------------
# MetricsStore tests
# ---------------------------------------------------------------------------


class TestMetricsStore:
    """Tests for the in-memory metrics store."""

    def test_record_and_get_all(self):
        store = MetricsStore()
        store.record("GET", "/hello", 200, 10.0)
        store.record("GET", "/hello", 200, 20.0)
        store.record("POST", "/data", 201, 5.0)

        metrics = store.get_all()
        assert len(metrics) == 2

        hello = next(m for m in metrics if m["path"] == "/hello")
        assert hello["total_requests"] == 2
        assert hello["avg_latency_ms"] == 15.0

    def test_get_summary(self):
        store = MetricsStore()
        store.record("GET", "/a", 200, 10.0)
        store.record("GET", "/b", 500, 20.0)

        summary = store.get_summary()
        assert summary["total_requests"] == 2
        assert summary["total_errors"] == 1
        assert summary["error_rate"] == 0.5
        assert summary["routes"] == 2
        assert summary["uptime_seconds"] >= 0

    def test_reset(self):
        store = MetricsStore()
        store.record("GET", "/a", 200, 10.0)
        store.reset()
        assert store.get_all() == []
        assert store.get_summary()["total_requests"] == 0


# ---------------------------------------------------------------------------
# RequestMetricsMiddleware integration tests
# ---------------------------------------------------------------------------


class TestRequestMetricsMiddleware:
    """Integration tests for metrics middleware with real HTTP calls."""

    async def test_records_successful_request(self):
        store = MetricsStore()
        app = _make_app(store)
        client = await _client(app)

        await client.get("/hello")
        metrics = store.get_all()
        assert len(metrics) >= 1
        hello = next((m for m in metrics if m["path"] == "/hello"), None)
        assert hello is not None
        assert hello["total_requests"] == 1
        assert hello["status_counts"].get(200) == 1

    async def test_records_error_request(self):
        store = MetricsStore()
        app = _make_app(store)
        client = await _client(app)

        await client.get("/error")
        metrics = store.get_all()
        error_metric = next((m for m in metrics if m["path"] == "/error"), None)
        assert error_metric is not None
        assert error_metric["total_errors"] == 1
        assert error_metric["status_counts"].get(500) == 1

    async def test_server_timing_header(self):
        store = MetricsStore()
        app = _make_app(store)
        client = await _client(app)

        resp = await client.get("/hello")
        timing = resp.headers.get("Server-Timing")
        assert timing is not None
        assert timing.startswith("total;dur=")

    async def test_path_normalization(self):
        store = MetricsStore()
        app = _make_app(store)
        client = await _client(app)

        await client.get("/items/550e8400-e29b-41d4-a716-446655440000")
        await client.get("/items/12345678-abcd-efgh-ijkl-mnopqrstuvwx")

        metrics = store.get_all()
        # Both should be normalized to /items/{id}
        item_metrics = [m for m in metrics if "items" in m["path"]]
        assert len(item_metrics) == 1
        assert item_metrics[0]["total_requests"] == 2

    async def test_metrics_endpoint(self):
        store = MetricsStore()
        app = _make_app(store)
        client = await _client(app)

        # Make some requests first
        await client.get("/hello")
        await client.get("/hello")

        # Now check /metrics
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "routes" in data
        assert data["summary"]["total_requests"] >= 2

    async def test_multiple_routes_tracked(self):
        store = MetricsStore()
        app = _make_app(store)
        client = await _client(app)

        await client.get("/hello")
        await client.get("/trace")
        await client.get("/hello")

        summary = store.get_summary()
        assert summary["total_requests"] >= 3
        assert summary["routes"] >= 2


# ---------------------------------------------------------------------------
# TraceContextFilter tests
# ---------------------------------------------------------------------------


class TestTraceContextFilter:
    """Tests for the logging filter that injects trace context."""

    def test_injects_request_id(self):
        import logging

        f = TraceContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        set_trace_context({"request_id": "filter-test-123"})
        f.filter(record)
        assert record.request_id == "filter-test-123"  # type: ignore
        set_trace_context({})

    def test_empty_context_gives_empty_strings(self):
        import logging

        f = TraceContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        set_trace_context({})
        f.filter(record)
        assert record.request_id == ""  # type: ignore


# ---------------------------------------------------------------------------
# add_observability integration
# ---------------------------------------------------------------------------


class TestAddObservability:
    """Tests for the combined observability setup helper."""

    async def test_full_stack(self):
        """Verify all middleware works together end-to-end."""
        store = MetricsStore()
        app = _make_app(store)
        client = await _client(app)

        # Request with full headers
        resp = await client.get(
            "/trace",
            headers={"X-Request-ID": "e2e-test", "X-Tenant-ID": "acme"},
        )
        assert resp.status_code == 200

        # Correlation ID propagated
        assert resp.headers["X-Request-ID"] == "e2e-test"
        assert resp.headers["X-Tenant-ID"] == "acme"

        # Trace context visible in handler
        data = resp.json()
        assert data["request_id"] == "e2e-test"

        # Metrics recorded
        assert store.get_summary()["total_requests"] >= 1

        # Server timing present
        assert "Server-Timing" in resp.headers
