"""Standard error types for NGEN platform services.

All services should use these error types for consistent error handling
and HTTP response formatting across the platform.
"""

from __future__ import annotations

from typing import Any


class NgenError(Exception):
    """Base exception for all NGEN platform errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


class NotFoundError(NgenError):
    """Resource not found."""

    def __init__(
        self,
        resource: str,
        identifier: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=f"{resource} '{identifier}' not found",
            code="NOT_FOUND",
            status_code=404,
            details=details or {"resource": resource, "identifier": identifier},
        )


class ConflictError(NgenError):
    """Resource already exists or state conflict."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=409,
            details=details,
        )


class ValidationError(NgenError):
    """Request validation failed."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=400,
            details=details,
        )


class PolicyViolationError(NgenError):
    """Governance policy violation."""

    def __init__(
        self,
        policy_name: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="POLICY_VIOLATION",
            status_code=403,
            details=details or {"policy": policy_name},
        )


class RateLimitError(NgenError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        d = details or {}
        if retry_after:
            d["retry_after_seconds"] = retry_after
        super().__init__(
            message=message,
            code="RATE_LIMITED",
            status_code=429,
            details=d,
        )


class ServiceUnavailableError(NgenError):
    """Upstream service unavailable."""

    def __init__(
        self,
        service: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message or f"Service '{service}' is unavailable",
            code="SERVICE_UNAVAILABLE",
            status_code=503,
            details=details or {"service": service},
        )
