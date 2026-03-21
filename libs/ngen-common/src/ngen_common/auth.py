"""Authentication and authorization middleware for NGEN platform services.

Supports two authentication modes:
1. **API Key** — Simple bearer token or X-API-Key header validation
2. **JWT** — JSON Web Token validation with claims extraction (tenant, roles, scopes)

Both modes are zero-dependency (uses stdlib only — no PyJWT needed) by implementing
a minimal JWT decoder for HS256. Production deployments can swap in RS256/JWKS
by subclassing JWTValidator.

Usage:
    from ngen_common.auth import AuthMiddleware, AuthConfig

    config = AuthConfig(
        mode="jwt",
        jwt_secret="my-secret",
        exclude_paths=["/health", "/metrics"],
    )
    add_auth(app, config)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


# ---------------------------------------------------------------------------
# Auth Identity — the result of successful authentication
# ---------------------------------------------------------------------------


@dataclass
class AuthIdentity:
    """Represents an authenticated caller."""

    subject: str  # user ID or API key name
    tenant_id: str = ""
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    claims: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# API Key store
# ---------------------------------------------------------------------------


class APIKeyStore:
    """In-memory API key registry.

    Maps API key strings to identity metadata. In production, this would
    be backed by a database or secrets manager.
    """

    def __init__(self) -> None:
        self._keys: dict[str, AuthIdentity] = {}

    def register(
        self,
        key: str,
        subject: str = "",
        tenant_id: str = "",
        roles: list[str] | None = None,
        scopes: list[str] | None = None,
    ) -> None:
        """Register an API key with associated identity."""
        # Store hash of key for security
        key_hash = self._hash(key)
        self._keys[key_hash] = AuthIdentity(
            subject=subject or f"apikey:{key[:8]}...",
            tenant_id=tenant_id,
            roles=roles or [],
            scopes=scopes or [],
        )

    def validate(self, key: str) -> AuthIdentity | None:
        """Validate an API key and return the identity, or None."""
        key_hash = self._hash(key)
        return self._keys.get(key_hash)

    def revoke(self, key: str) -> bool:
        """Revoke an API key. Returns True if it existed."""
        key_hash = self._hash(key)
        if key_hash in self._keys:
            del self._keys[key_hash]
            return True
        return False

    @property
    def count(self) -> int:
        return len(self._keys)

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Minimal JWT decoder (HS256 only — no external deps)
# ---------------------------------------------------------------------------


def _b64url_decode(data: str) -> bytes:
    """Decode base64url without padding."""
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def _b64url_encode(data: bytes) -> str:
    """Encode bytes to base64url without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class JWTError(Exception):
    """JWT validation error."""

    pass


class JWTValidator:
    """Validates HS256 JWTs using a shared secret.

    Checks:
    - Signature validity (HMAC-SHA256)
    - Expiration (exp claim)
    - Not-before (nbf claim)
    - Issuer (iss claim, if configured)
    - Audience (aud claim, if configured)
    """

    def __init__(
        self,
        secret: str,
        issuer: str | None = None,
        audience: str | None = None,
        clock_skew_seconds: int = 30,
    ) -> None:
        self._secret = secret.encode()
        self._issuer = issuer
        self._audience = audience
        self._clock_skew = clock_skew_seconds

    def validate(self, token: str) -> dict[str, Any]:
        """Validate a JWT and return its claims.

        Raises JWTError if validation fails.
        """
        parts = token.split(".")
        if len(parts) != 3:
            raise JWTError("Invalid JWT format: expected 3 parts")

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        actual_sig = _b64url_decode(signature_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise JWTError("Invalid JWT signature")

        # Decode header
        try:
            header = json.loads(_b64url_decode(header_b64))
        except (json.JSONDecodeError, Exception) as e:
            raise JWTError(f"Invalid JWT header: {e}")

        if header.get("alg") != "HS256":
            raise JWTError(f"Unsupported algorithm: {header.get('alg')}")

        # Decode payload
        try:
            claims = json.loads(_b64url_decode(payload_b64))
        except (json.JSONDecodeError, Exception) as e:
            raise JWTError(f"Invalid JWT payload: {e}")

        now = time.time()

        # Check expiration
        if "exp" in claims:
            if now > claims["exp"] + self._clock_skew:
                raise JWTError("JWT has expired")

        # Check not-before
        if "nbf" in claims:
            if now < claims["nbf"] - self._clock_skew:
                raise JWTError("JWT is not yet valid")

        # Check issuer
        if self._issuer and claims.get("iss") != self._issuer:
            raise JWTError(f"Invalid issuer: expected {self._issuer}")

        # Check audience
        if self._audience:
            aud = claims.get("aud", "")
            if isinstance(aud, list):
                if self._audience not in aud:
                    raise JWTError(f"Invalid audience: {self._audience} not in {aud}")
            elif aud != self._audience:
                raise JWTError(f"Invalid audience: expected {self._audience}")

        return claims

    def to_identity(self, claims: dict[str, Any]) -> AuthIdentity:
        """Convert JWT claims to an AuthIdentity."""
        return AuthIdentity(
            subject=claims.get("sub", ""),
            tenant_id=claims.get("tenant_id", claims.get("tid", "")),
            roles=claims.get("roles", []),
            scopes=claims.get("scope", "").split() if isinstance(claims.get("scope"), str) else claims.get("scopes", []),
            claims=claims,
        )


def create_jwt(
    secret: str,
    subject: str,
    tenant_id: str = "",
    roles: list[str] | None = None,
    scopes: list[str] | None = None,
    expires_in: int = 3600,
    issuer: str | None = None,
    audience: str | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create an HS256 JWT. Useful for testing.

    Args:
        secret: Signing secret.
        subject: The 'sub' claim.
        tenant_id: Tenant identifier.
        roles: List of roles.
        scopes: List of scopes (space-separated in 'scope' claim).
        expires_in: Seconds until expiry.
        issuer: Optional 'iss' claim.
        audience: Optional 'aud' claim.
        extra_claims: Additional claims to include.

    Returns:
        Encoded JWT string.
    """
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_in,
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if roles:
        payload["roles"] = roles
    if scopes:
        payload["scope"] = " ".join(scopes)
    if issuer:
        payload["iss"] = issuer
    if audience:
        payload["aud"] = audience
    if extra_claims:
        payload.update(extra_claims)

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())

    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


# ---------------------------------------------------------------------------
# Auth Configuration
# ---------------------------------------------------------------------------


class AuthMode(str, Enum):
    """Authentication mode."""

    API_KEY = "api_key"
    JWT = "jwt"
    NONE = "none"  # No auth (dev mode)


@dataclass
class AuthConfig:
    """Configuration for auth middleware."""

    mode: AuthMode = AuthMode.NONE
    # API key settings
    api_key_store: APIKeyStore | None = None
    # JWT settings
    jwt_secret: str = ""
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    # Paths excluded from auth (e.g., health checks)
    exclude_paths: list[str] = field(
        default_factory=lambda: ["/health", "/metrics", "/docs", "/openapi.json"]
    )


# ---------------------------------------------------------------------------
# Auth Middleware
# ---------------------------------------------------------------------------

HEADER_AUTHORIZATION = "Authorization"
HEADER_API_KEY = "X-API-Key"


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware supporting API keys and JWT tokens.

    Extracts credentials from:
    - Authorization: Bearer <token> header (JWT or API key)
    - X-API-Key: <key> header (API key only)

    Sets request.state.identity with the authenticated AuthIdentity.
    """

    def __init__(self, app, config: AuthConfig, **kwargs) -> None:
        super().__init__(app, **kwargs)
        self._config = config
        self._jwt_validator: JWTValidator | None = None
        if config.mode == AuthMode.JWT and config.jwt_secret:
            self._jwt_validator = JWTValidator(
                secret=config.jwt_secret,
                issuer=config.jwt_issuer,
                audience=config.jwt_audience,
            )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip auth for excluded paths
        if self._is_excluded(request.url.path):
            request.state.identity = None
            return await call_next(request)

        # No auth mode — pass through
        if self._config.mode == AuthMode.NONE:
            request.state.identity = None
            return await call_next(request)

        # Try to authenticate
        identity = self._authenticate(request)
        if identity is None:
            return JSONResponse(
                status_code=401,
                content={"error": "UNAUTHORIZED", "message": "Authentication required"},
            )

        request.state.identity = identity
        return await call_next(request)

    def _is_excluded(self, path: str) -> bool:
        """Check if a path is excluded from auth."""
        for excluded in self._config.exclude_paths:
            if path == excluded or path.startswith(excluded + "/"):
                return True
        return False

    def _authenticate(self, request: Request) -> AuthIdentity | None:
        """Try to authenticate the request."""
        # Try Authorization header
        auth_header = request.headers.get(HEADER_AUTHORIZATION, "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if self._config.mode == AuthMode.JWT:
                return self._validate_jwt(token)
            elif self._config.mode == AuthMode.API_KEY:
                return self._validate_api_key(token)

        # Try X-API-Key header
        api_key = request.headers.get(HEADER_API_KEY, "")
        if api_key and self._config.mode == AuthMode.API_KEY:
            return self._validate_api_key(api_key)

        return None

    def _validate_jwt(self, token: str) -> AuthIdentity | None:
        """Validate a JWT token."""
        if not self._jwt_validator:
            return None
        try:
            claims = self._jwt_validator.validate(token)
            return self._jwt_validator.to_identity(claims)
        except JWTError:
            return None

    def _validate_api_key(self, key: str) -> AuthIdentity | None:
        """Validate an API key."""
        if not self._config.api_key_store:
            return None
        return self._config.api_key_store.validate(key)


# ---------------------------------------------------------------------------
# Scope-based authorization helper
# ---------------------------------------------------------------------------


def require_scope(identity: AuthIdentity | None, scope: str) -> bool:
    """Check if identity has a required scope.

    Returns True if authorized, False otherwise.
    """
    if identity is None:
        return False
    return scope in identity.scopes


def require_role(identity: AuthIdentity | None, role: str) -> bool:
    """Check if identity has a required role."""
    if identity is None:
        return False
    return role in identity.roles


# ---------------------------------------------------------------------------
# FastAPI integration
# ---------------------------------------------------------------------------


def add_auth(app, config: AuthConfig) -> None:
    """Add authentication middleware to a FastAPI app.

    Args:
        app: FastAPI application instance.
        config: Authentication configuration.
    """
    if config.mode != AuthMode.NONE:
        app.add_middleware(AuthMiddleware, config=config)
