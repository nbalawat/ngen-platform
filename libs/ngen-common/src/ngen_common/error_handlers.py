"""Unified error handling for NGEN platform FastAPI services.

Provides exception handlers that convert NgenError subclasses and common
Python exceptions into consistent JSON error responses. Every service that
calls `add_error_handlers(app)` will return the same error shape:

    {
        "error": "ERROR_CODE",
        "message": "Human-readable description",
        "details": { ... },
        "request_id": "abc-123"   // from trace context if available
    }

This ensures API consumers get predictable error responses regardless of
which service they hit.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from ngen_common.errors import (
    NgenError,
    NotFoundError,
    ConflictError,
    ValidationError,
    PolicyViolationError,
    RateLimitError,
    ServiceUnavailableError,
)

logger = logging.getLogger(__name__)


def _get_request_id(request: Request) -> str:
    """Extract request ID from request state or headers."""
    # Try request.state first (set by CorrelationIDMiddleware)
    req_id = getattr(getattr(request, "state", None), "request_id", None)
    if req_id:
        return req_id
    # Fall back to header
    return request.headers.get("X-Request-ID", "")


def _build_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str = "",
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a standardized JSON error response."""
    body: dict[str, Any] = {
        "error": error_code,
        "message": message,
    }
    if details:
        body["details"] = details
    if request_id:
        body["request_id"] = request_id

    return JSONResponse(
        status_code=status_code,
        content=body,
        headers=headers,
    )


async def _handle_ngen_error(request: Request, exc: NgenError) -> JSONResponse:
    """Handle any NgenError subclass."""
    request_id = _get_request_id(request)

    # Log at appropriate level based on status code
    if exc.status_code >= 500:
        logger.error(
            "NgenError %s: %s [request_id=%s]",
            exc.code, exc.message, request_id,
            exc_info=True,
        )
    elif exc.status_code >= 400:
        logger.warning(
            "NgenError %s: %s [request_id=%s]",
            exc.code, exc.message, request_id,
        )

    headers = {}
    # Add Retry-After for rate limit errors
    if isinstance(exc, RateLimitError):
        retry_after = exc.details.get("retry_after_seconds")
        if retry_after:
            headers["Retry-After"] = str(retry_after)

    return _build_error_response(
        status_code=exc.status_code,
        error_code=exc.code,
        message=exc.message,
        details=exc.details if exc.details else None,
        request_id=request_id,
        headers=headers or None,
    )


async def _handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
    """Handle ValueError as a 400 Bad Request."""
    request_id = _get_request_id(request)
    logger.warning("ValueError: %s [request_id=%s]", str(exc), request_id)
    return _build_error_response(
        status_code=400,
        error_code="VALIDATION_ERROR",
        message=str(exc),
        request_id=request_id,
    )


async def _handle_key_error(request: Request, exc: KeyError) -> JSONResponse:
    """Handle KeyError as a 400 Bad Request (missing field)."""
    request_id = _get_request_id(request)
    logger.warning("KeyError: %s [request_id=%s]", str(exc), request_id)
    return _build_error_response(
        status_code=400,
        error_code="VALIDATION_ERROR",
        message=f"Missing required field: {exc}",
        request_id=request_id,
    )


async def _handle_permission_error(
    request: Request, exc: PermissionError
) -> JSONResponse:
    """Handle PermissionError as a 403 Forbidden."""
    request_id = _get_request_id(request)
    logger.warning("PermissionError: %s [request_id=%s]", str(exc), request_id)
    return _build_error_response(
        status_code=403,
        error_code="FORBIDDEN",
        message=str(exc) or "Permission denied",
        request_id=request_id,
    )


async def _handle_not_implemented(
    request: Request, exc: NotImplementedError
) -> JSONResponse:
    """Handle NotImplementedError as a 501 Not Implemented."""
    request_id = _get_request_id(request)
    return _build_error_response(
        status_code=501,
        error_code="NOT_IMPLEMENTED",
        message=str(exc) or "This feature is not yet implemented",
        request_id=request_id,
    )


def add_error_handlers(app) -> None:
    """Register all standard error handlers on a FastAPI app.

    Should be called during app setup, typically alongside
    add_observability() and add_auth().

    Handles:
    - All NgenError subclasses (NotFoundError, ConflictError, etc.)
    - ValueError → 400
    - KeyError → 400
    - PermissionError → 403
    - NotImplementedError → 501

    Note: A generic Exception catch-all is NOT registered because
    Starlette's ASGI stack does not reliably route non-HTTP exceptions
    through app-level handlers. Unhandled exceptions are logged by
    Uvicorn and result in a 500 Internal Server Error.

    Example:
        app = FastAPI()
        add_error_handlers(app)
        add_observability(app, service_name="my-service")
    """
    # NgenError and all subclasses
    app.add_exception_handler(NgenError, _handle_ngen_error)

    # Common Python exceptions mapped to HTTP status codes
    app.add_exception_handler(ValueError, _handle_value_error)
    app.add_exception_handler(KeyError, _handle_key_error)
    app.add_exception_handler(PermissionError, _handle_permission_error)
    app.add_exception_handler(NotImplementedError, _handle_not_implemented)
