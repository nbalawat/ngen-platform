"""Observability middleware for NGEN platform services.

Provides three composable FastAPI middleware components:

1. CorrelationIDMiddleware — propagates or generates X-Request-ID / trace_id
   for every request, making it available to loggers and response headers.

2. RequestMetricsMiddleware — tracks request count, latency, and status codes
   in an in-memory metrics store, exposed via /metrics endpoint.

3. TraceContext — asyncio context variable for propagating trace info across
   async boundaries without thread-local hacks.

All middleware is zero-dependency beyond FastAPI/Starlette (no OpenTelemetry
or Prometheus SDK required). Production deployments can scrape the /metrics
endpoint or replace with vendor SDKs.
"""

from __future__ import annotations

import contextvars
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trace Context (async-safe context variable)
# ---------------------------------------------------------------------------

# Context variable holding the current request's trace info
_trace_ctx: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar(
    "ngen_trace_ctx", default={}
)


def get_trace_context() -> dict[str, str]:
    """Get the current trace context (request_id, tenant_id, etc.)."""
    return dict(_trace_ctx.get())


def set_trace_context(ctx: dict[str, str]) -> None:
    """Set trace context for the current async task."""
    _trace_ctx.set(ctx)


def get_request_id() -> str | None:
    """Get the current request ID from trace context."""
    return _trace_ctx.get().get("request_id")


# ---------------------------------------------------------------------------
# Correlation ID Middleware
# ---------------------------------------------------------------------------

HEADER_REQUEST_ID = "X-Request-ID"
HEADER_TRACE_ID = "X-Trace-ID"
HEADER_TENANT_ID = "X-Tenant-ID"


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Extracts or generates a request ID and propagates it.

    - Reads X-Request-ID header from inbound request (or generates one)
    - Sets it in the trace context (available to all async code)
    - Adds it to the response headers
    - Injects it into the logging context via a filter
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Extract or generate request ID
        request_id = (
            request.headers.get(HEADER_REQUEST_ID)
            or request.headers.get(HEADER_TRACE_ID)
            or str(uuid.uuid4())
        )
        tenant_id = request.headers.get(HEADER_TENANT_ID, "")

        # Set trace context for downstream code
        ctx = {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "method": request.method,
            "path": request.url.path,
        }
        set_trace_context(ctx)

        # Store on request.state for handler access
        request.state.request_id = request_id
        request.state.tenant_id = tenant_id

        response = await call_next(request)

        # Add to response headers
        response.headers[HEADER_REQUEST_ID] = request_id
        if tenant_id:
            response.headers[HEADER_TENANT_ID] = tenant_id

        return response


# ---------------------------------------------------------------------------
# Trace-aware logging filter
# ---------------------------------------------------------------------------


class TraceContextFilter(logging.Filter):
    """Logging filter that injects trace context fields into log records.

    Use with JSONFormatter to get request_id, tenant_id, etc. in every log line.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = _trace_ctx.get()
        record.request_id = ctx.get("request_id", "")  # type: ignore[attr-defined]
        record.tenant_id = ctx.get("tenant_id", "")  # type: ignore[attr-defined]
        return True


# ---------------------------------------------------------------------------
# Request Metrics
# ---------------------------------------------------------------------------


@dataclass
class RequestMetric:
    """Aggregated metrics for a specific route."""

    method: str
    path: str
    total_requests: int = 0
    total_errors: int = 0
    total_latency_ms: float = 0.0
    status_counts: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    def record(self, status_code: int, latency_ms: float) -> None:
        """Record a single request."""
        self.total_requests += 1
        self.total_latency_ms += latency_ms
        self.status_counts[status_code] += 1
        if status_code >= 500:
            self.total_errors += 1
        if latency_ms < self.min_latency_ms:
            self.min_latency_ms = latency_ms
        if latency_ms > self.max_latency_ms:
            self.max_latency_ms = latency_ms


class MetricsStore:
    """In-memory metrics store for request telemetry.

    Stores per-route aggregated metrics. Thread-safe for single-threaded
    async (asyncio event loop).
    """

    def __init__(self) -> None:
        self._metrics: dict[str, RequestMetric] = {}
        self._start_time: float = time.time()

    def record(self, method: str, path: str, status_code: int, latency_ms: float) -> None:
        """Record a request metric."""
        key = f"{method} {path}"
        if key not in self._metrics:
            self._metrics[key] = RequestMetric(method=method, path=path)
        self._metrics[key].record(status_code, latency_ms)

    def get_all(self) -> list[dict[str, Any]]:
        """Return all metrics as a list of dicts."""
        return [
            {
                "method": m.method,
                "path": m.path,
                "total_requests": m.total_requests,
                "total_errors": m.total_errors,
                "avg_latency_ms": round(m.avg_latency_ms, 2),
                "min_latency_ms": round(m.min_latency_ms, 2) if m.min_latency_ms != float("inf") else 0,
                "max_latency_ms": round(m.max_latency_ms, 2),
                "status_counts": dict(m.status_counts),
            }
            for m in self._metrics.values()
        ]

    def get_summary(self) -> dict[str, Any]:
        """Return a summary of all metrics."""
        total_requests = sum(m.total_requests for m in self._metrics.values())
        total_errors = sum(m.total_errors for m in self._metrics.values())
        return {
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": round(total_errors / max(total_requests, 1), 4),
            "routes": len(self._metrics),
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._metrics.clear()
        self._start_time = time.time()


# Singleton store — shared across middleware and metrics endpoint
_default_store = MetricsStore()


def get_metrics_store() -> MetricsStore:
    """Get the default metrics store singleton."""
    return _default_store


def reset_metrics_store() -> None:
    """Reset the default metrics store (for testing)."""
    global _default_store
    _default_store = MetricsStore()


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that records request latency and status codes.

    Metrics are stored in a MetricsStore and can be queried via the
    /metrics endpoint or get_metrics_store().
    """

    def __init__(self, app, store: MetricsStore | None = None, **kwargs) -> None:
        super().__init__(app, **kwargs)
        self._store = store or get_metrics_store()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        latency_ms = (time.monotonic() - start) * 1000

        # Normalize path to avoid cardinality explosion
        path = self._normalize_path(request.url.path)
        self._store.record(request.method, path, response.status_code, latency_ms)

        # Add server timing header
        response.headers["Server-Timing"] = f"total;dur={latency_ms:.1f}"

        return response

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Replace path parameters with placeholders to limit cardinality.

        e.g., /api/v1/runs/abc-123 → /api/v1/runs/{id}
        """
        parts = path.strip("/").split("/")
        normalized = []
        for part in parts:
            # Heuristic: UUID-like or numeric segments are path params
            if len(part) > 8 and "-" in part:
                normalized.append("{id}")
            elif part.isdigit():
                normalized.append("{id}")
            else:
                normalized.append(part)
        return "/" + "/".join(normalized) if normalized else "/"


# ---------------------------------------------------------------------------
# FastAPI integration helpers
# ---------------------------------------------------------------------------


def add_observability(
    app,
    service_name: str = "unknown",
    metrics_store: MetricsStore | None = None,
) -> MetricsStore:
    """Add all observability middleware to a FastAPI app.

    Adds:
    - CorrelationIDMiddleware (request ID propagation)
    - RequestMetricsMiddleware (latency + status tracking)
    - /metrics endpoint

    Args:
        app: FastAPI application instance.
        service_name: Name of the service for logging.
        metrics_store: Optional custom MetricsStore (for testing).

    Returns:
        The MetricsStore being used (for direct access in tests).
    """
    store = metrics_store or get_metrics_store()

    # Add middleware (order matters — outermost first)
    app.add_middleware(RequestMetricsMiddleware, store=store)
    app.add_middleware(CorrelationIDMiddleware)

    # Add metrics endpoint
    @app.get("/metrics")
    async def metrics_endpoint():
        return {
            "summary": store.get_summary(),
            "routes": store.get_all(),
        }

    return store
