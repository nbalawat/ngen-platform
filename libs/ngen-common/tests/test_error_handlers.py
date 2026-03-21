"""Tests for unified error handling middleware.

Uses real FastAPI apps with ASGI transport. No mocks.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request

from ngen_common.error_handlers import add_error_handlers, _build_error_response
from ngen_common.errors import (
    ConflictError,
    NgenError,
    NotFoundError,
    PolicyViolationError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
)
from ngen_common.observability import add_observability


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(with_observability: bool = False) -> FastAPI:
    """Create a test app with error handlers registered."""
    app = FastAPI()
    add_error_handlers(app)
    if with_observability:
        add_observability(app, service_name="test-svc")

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/not-found")
    async def not_found():
        raise NotFoundError("Workflow", "wf-123")

    @app.get("/conflict")
    async def conflict():
        raise ConflictError("Agent 'analyzer' already exists")

    @app.get("/validation")
    async def validation():
        raise ValidationError(
            "Invalid topology type",
            details={"field": "topology", "allowed": ["sequential", "parallel"]},
        )

    @app.get("/policy-violation")
    async def policy_violation():
        raise PolicyViolationError(
            "content-filter-prod",
            "Content contains prohibited terms",
            details={"policy": "content-filter-prod", "matched": ["restricted"]},
        )

    @app.get("/rate-limit")
    async def rate_limit():
        raise RateLimitError(
            "Too many requests",
            retry_after=30,
        )

    @app.get("/service-unavailable")
    async def service_unavailable():
        raise ServiceUnavailableError("model-gateway")

    @app.get("/generic-ngen-error")
    async def generic_ngen():
        raise NgenError("Something broke", code="CUSTOM_ERROR", status_code=422)

    @app.get("/value-error")
    async def value_error():
        raise ValueError("model_id is required")

    @app.get("/key-error")
    async def key_error():
        raise KeyError("namespace")

    @app.get("/permission-error")
    async def perm_error():
        raise PermissionError("Cannot delete admin tenant")

    @app.get("/not-implemented")
    async def not_impl():
        raise NotImplementedError("Streaming not supported for this adapter")

    return app


async def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# NgenError subclass tests
# ---------------------------------------------------------------------------


class TestNgenErrorHandlers:
    """Tests for NgenError subclass → JSON response mapping."""

    async def test_not_found_error(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/not-found")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "NOT_FOUND"
        assert "wf-123" in data["message"]
        assert data["details"]["resource"] == "Workflow"
        assert data["details"]["identifier"] == "wf-123"

    async def test_conflict_error(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/conflict")
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "CONFLICT"
        assert "already exists" in data["message"]

    async def test_validation_error(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/validation")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "VALIDATION_ERROR"
        assert data["details"]["field"] == "topology"

    async def test_policy_violation_error(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/policy-violation")
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"] == "POLICY_VIOLATION"
        assert "prohibited" in data["message"]
        assert data["details"]["policy"] == "content-filter-prod"

    async def test_rate_limit_error(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/rate-limit")
        assert resp.status_code == 429
        data = resp.json()
        assert data["error"] == "RATE_LIMITED"
        assert resp.headers.get("Retry-After") == "30"
        assert data["details"]["retry_after_seconds"] == 30

    async def test_service_unavailable_error(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/service-unavailable")
        assert resp.status_code == 503
        data = resp.json()
        assert data["error"] == "SERVICE_UNAVAILABLE"
        assert "model-gateway" in data["message"]

    async def test_generic_ngen_error(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/generic-ngen-error")
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"] == "CUSTOM_ERROR"
        assert data["message"] == "Something broke"


# ---------------------------------------------------------------------------
# Python exception mapping tests
# ---------------------------------------------------------------------------


class TestPythonExceptionHandlers:
    """Tests for standard Python exceptions → HTTP status mapping."""

    async def test_value_error_becomes_400(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/value-error")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "VALIDATION_ERROR"
        assert "model_id" in data["message"]

    async def test_key_error_becomes_400(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/key-error")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "VALIDATION_ERROR"
        assert "namespace" in data["message"]

    async def test_permission_error_becomes_403(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/permission-error")
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"] == "FORBIDDEN"

    async def test_not_implemented_becomes_501(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/not-implemented")
        assert resp.status_code == 501
        data = resp.json()
        assert data["error"] == "NOT_IMPLEMENTED"
        assert "Streaming" in data["message"]



# ---------------------------------------------------------------------------
# Response format consistency tests
# ---------------------------------------------------------------------------


class TestResponseFormat:
    """Tests ensuring all error responses follow the same shape."""

    async def test_all_errors_have_error_and_message_fields(self):
        app = _make_app()
        client = await _client(app)

        error_paths = [
            "/not-found", "/conflict", "/validation", "/policy-violation",
            "/rate-limit", "/service-unavailable", "/value-error",
            "/key-error", "/permission-error", "/not-implemented",
        ]
        for path in error_paths:
            resp = await client.get(path)
            data = resp.json()
            assert "error" in data, f"{path} missing 'error' field"
            assert "message" in data, f"{path} missing 'message' field"
            assert isinstance(data["error"], str), f"{path} 'error' not a string"
            assert isinstance(data["message"], str), f"{path} 'message' not a string"

    async def test_healthy_endpoint_unaffected(self):
        app = _make_app()
        client = await _client(app)
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}


# ---------------------------------------------------------------------------
# Request ID propagation tests
# ---------------------------------------------------------------------------


class TestRequestIDInErrors:
    """Tests that request ID appears in error responses when observability is active."""

    async def test_request_id_included_in_error(self):
        app = _make_app(with_observability=True)
        client = await _client(app)

        resp = await client.get(
            "/not-found",
            headers={"X-Request-ID": "err-trace-789"},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data.get("request_id") == "err-trace-789"

    async def test_no_request_id_when_no_observability(self):
        app = _make_app(with_observability=False)
        client = await _client(app)

        resp = await client.get("/not-found")
        data = resp.json()
        # request_id should be absent or empty
        assert data.get("request_id", "") == ""


# ---------------------------------------------------------------------------
# _build_error_response unit tests
# ---------------------------------------------------------------------------


class TestBuildErrorResponse:
    """Unit tests for the response builder helper."""

    def test_minimal_response(self):
        resp = _build_error_response(400, "BAD_REQUEST", "bad input")
        assert resp.status_code == 400
        # Body is bytes, decode it
        import json
        body = json.loads(resp.body)
        assert body["error"] == "BAD_REQUEST"
        assert body["message"] == "bad input"
        assert "details" not in body
        assert "request_id" not in body

    def test_full_response(self):
        resp = _build_error_response(
            422, "CUSTOM", "msg",
            details={"field": "x"},
            request_id="req-1",
            headers={"X-Custom": "val"},
        )
        assert resp.status_code == 422
        import json
        body = json.loads(resp.body)
        assert body["details"]["field"] == "x"
        assert body["request_id"] == "req-1"
        assert resp.headers.get("X-Custom") == "val"
