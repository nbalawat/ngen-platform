"""Tests for ngen_common.errors — standard error hierarchy."""

from __future__ import annotations

import pytest

from ngen_common.errors import (
    ConflictError,
    NgenError,
    NotFoundError,
    PolicyViolationError,
    RateLimitError,
    ServiceUnavailableError,
    ValidationError,
)


class TestNgenError:
    def test_defaults(self) -> None:
        err = NgenError("boom")
        assert str(err) == "boom"
        assert err.message == "boom"
        assert err.code == "INTERNAL_ERROR"
        assert err.status_code == 500
        assert err.details == {}

    def test_custom_fields(self) -> None:
        err = NgenError("oops", code="CUSTOM", status_code=418, details={"k": "v"})
        assert err.code == "CUSTOM"
        assert err.status_code == 418
        assert err.details == {"k": "v"}

    def test_to_dict(self) -> None:
        err = NgenError("msg", code="C", details={"x": 1})
        d = err.to_dict()
        assert d == {"error": "C", "message": "msg", "details": {"x": 1}}

    def test_is_exception(self) -> None:
        with pytest.raises(NgenError):
            raise NgenError("test")


class TestNotFoundError:
    def test_message_format(self) -> None:
        err = NotFoundError("Workflow", "wf-123")
        assert err.message == "Workflow 'wf-123' not found"
        assert err.code == "NOT_FOUND"
        assert err.status_code == 404
        assert err.details == {"resource": "Workflow", "identifier": "wf-123"}

    def test_custom_details(self) -> None:
        err = NotFoundError("Agent", "a1", details={"extra": True})
        assert err.details == {"extra": True}

    def test_inherits_ngen_error(self) -> None:
        err = NotFoundError("X", "1")
        assert isinstance(err, NgenError)


class TestConflictError:
    def test_basic(self) -> None:
        err = ConflictError("already exists")
        assert err.status_code == 409
        assert err.code == "CONFLICT"
        assert err.message == "already exists"


class TestValidationError:
    def test_basic(self) -> None:
        err = ValidationError("bad field", details={"field": "name"})
        assert err.status_code == 400
        assert err.code == "VALIDATION_ERROR"
        assert err.details == {"field": "name"}


class TestPolicyViolationError:
    def test_basic(self) -> None:
        err = PolicyViolationError("content_filter", "blocked content")
        assert err.status_code == 403
        assert err.code == "POLICY_VIOLATION"
        assert err.details == {"policy": "content_filter"}

    def test_custom_details(self) -> None:
        err = PolicyViolationError("rate_limit", "too fast", details={"limit": 100})
        assert err.details == {"limit": 100}


class TestRateLimitError:
    def test_defaults(self) -> None:
        err = RateLimitError()
        assert err.status_code == 429
        assert err.code == "RATE_LIMITED"
        assert err.message == "Rate limit exceeded"
        assert err.details == {}

    def test_retry_after(self) -> None:
        err = RateLimitError(retry_after=30)
        assert err.details == {"retry_after_seconds": 30}

    def test_custom_message(self) -> None:
        err = RateLimitError(message="slow down", retry_after=10, details={"bucket": "api"})
        assert err.message == "slow down"
        assert err.details == {"bucket": "api", "retry_after_seconds": 10}


class TestServiceUnavailableError:
    def test_default_message(self) -> None:
        err = ServiceUnavailableError("postgres")
        assert err.status_code == 503
        assert err.message == "Service 'postgres' is unavailable"
        assert err.details == {"service": "postgres"}

    def test_custom_message(self) -> None:
        err = ServiceUnavailableError("redis", message="connection refused")
        assert err.message == "connection refused"
