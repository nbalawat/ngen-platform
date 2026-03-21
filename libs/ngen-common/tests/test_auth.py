"""Tests for auth middleware — API keys, JWT, authorization.

Uses real FastAPI apps with ASGI transport. No mocks.
"""

from __future__ import annotations

import time

import httpx
import pytest
from fastapi import FastAPI, Request

from ngen_common.auth import (
    APIKeyStore,
    AuthConfig,
    AuthIdentity,
    AuthMiddleware,
    AuthMode,
    JWTError,
    JWTValidator,
    add_auth,
    create_jwt,
    require_role,
    require_scope,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SECRET = "test-secret-key-for-ngen-platform"


def _make_app(config: AuthConfig) -> FastAPI:
    """Create a test FastAPI app with auth middleware."""
    app = FastAPI()
    add_auth(app, config)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/protected")
    async def protected(request: Request):
        identity: AuthIdentity | None = getattr(request.state, "identity", None)
        if identity is None:
            return {"authenticated": False}
        return {
            "authenticated": True,
            "subject": identity.subject,
            "tenant_id": identity.tenant_id,
            "roles": identity.roles,
            "scopes": identity.scopes,
        }

    @app.get("/admin")
    async def admin(request: Request):
        identity = getattr(request.state, "identity", None)
        if not require_role(identity, "admin"):
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"error": "FORBIDDEN", "message": "Admin role required"},
            )
        return {"admin": True}

    return app


async def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# APIKeyStore tests
# ---------------------------------------------------------------------------


class TestAPIKeyStore:
    """Tests for the in-memory API key store."""

    def test_register_and_validate(self):
        store = APIKeyStore()
        store.register("sk-test-123", subject="user-1", tenant_id="acme")
        identity = store.validate("sk-test-123")
        assert identity is not None
        assert identity.subject == "user-1"
        assert identity.tenant_id == "acme"

    def test_validate_wrong_key(self):
        store = APIKeyStore()
        store.register("sk-test-123", subject="user-1")
        assert store.validate("sk-wrong") is None

    def test_validate_empty_store(self):
        store = APIKeyStore()
        assert store.validate("any-key") is None

    def test_revoke(self):
        store = APIKeyStore()
        store.register("sk-test-123", subject="user-1")
        assert store.revoke("sk-test-123") is True
        assert store.validate("sk-test-123") is None

    def test_revoke_nonexistent(self):
        store = APIKeyStore()
        assert store.revoke("nonexistent") is False

    def test_count(self):
        store = APIKeyStore()
        assert store.count == 0
        store.register("key-1", subject="u1")
        store.register("key-2", subject="u2")
        assert store.count == 2

    def test_roles_and_scopes(self):
        store = APIKeyStore()
        store.register(
            "sk-admin",
            subject="admin-user",
            roles=["admin", "operator"],
            scopes=["read", "write", "delete"],
        )
        identity = store.validate("sk-admin")
        assert identity is not None
        assert "admin" in identity.roles
        assert "write" in identity.scopes

    def test_key_hashed_internally(self):
        """Keys are stored as hashes, not plaintext."""
        store = APIKeyStore()
        store.register("secret-key", subject="u1")
        # The raw key should not appear in the internal dict keys
        assert "secret-key" not in store._keys


# ---------------------------------------------------------------------------
# JWT tests
# ---------------------------------------------------------------------------


class TestJWTValidator:
    """Tests for the minimal HS256 JWT implementation."""

    def test_create_and_validate(self):
        token = create_jwt(SECRET, subject="user-1")
        validator = JWTValidator(SECRET)
        claims = validator.validate(token)
        assert claims["sub"] == "user-1"

    def test_claims_roundtrip(self):
        token = create_jwt(
            SECRET,
            subject="user-1",
            tenant_id="acme",
            roles=["admin"],
            scopes=["read", "write"],
            issuer="ngen",
            audience="api",
        )
        validator = JWTValidator(SECRET, issuer="ngen", audience="api")
        claims = validator.validate(token)
        assert claims["sub"] == "user-1"
        assert claims["tenant_id"] == "acme"
        assert claims["roles"] == ["admin"]
        assert claims["scope"] == "read write"
        assert claims["iss"] == "ngen"
        assert claims["aud"] == "api"

    def test_wrong_secret_rejected(self):
        token = create_jwt(SECRET, subject="user-1")
        validator = JWTValidator("wrong-secret")
        with pytest.raises(JWTError, match="Invalid JWT signature"):
            validator.validate(token)

    def test_expired_token(self):
        token = create_jwt(SECRET, subject="user-1", expires_in=-100)
        validator = JWTValidator(SECRET)
        with pytest.raises(JWTError, match="expired"):
            validator.validate(token)

    def test_clock_skew_tolerance(self):
        """Tokens within clock skew window should still be valid."""
        token = create_jwt(SECRET, subject="user-1", expires_in=-10)
        validator = JWTValidator(SECRET, clock_skew_seconds=30)
        claims = validator.validate(token)
        assert claims["sub"] == "user-1"

    def test_invalid_format(self):
        validator = JWTValidator(SECRET)
        with pytest.raises(JWTError, match="expected 3 parts"):
            validator.validate("not.a.valid.jwt.token")

    def test_wrong_issuer(self):
        token = create_jwt(SECRET, subject="user-1", issuer="other")
        validator = JWTValidator(SECRET, issuer="ngen")
        with pytest.raises(JWTError, match="Invalid issuer"):
            validator.validate(token)

    def test_wrong_audience(self):
        token = create_jwt(SECRET, subject="user-1", audience="other")
        validator = JWTValidator(SECRET, audience="ngen-api")
        with pytest.raises(JWTError, match="Invalid audience"):
            validator.validate(token)

    def test_to_identity(self):
        token = create_jwt(
            SECRET,
            subject="user-1",
            tenant_id="acme",
            roles=["admin"],
            scopes=["read", "write"],
        )
        validator = JWTValidator(SECRET)
        claims = validator.validate(token)
        identity = validator.to_identity(claims)
        assert identity.subject == "user-1"
        assert identity.tenant_id == "acme"
        assert identity.roles == ["admin"]
        assert "read" in identity.scopes
        assert "write" in identity.scopes

    def test_extra_claims(self):
        token = create_jwt(
            SECRET, subject="user-1",
            extra_claims={"custom_field": "hello"},
        )
        validator = JWTValidator(SECRET)
        claims = validator.validate(token)
        assert claims["custom_field"] == "hello"


# ---------------------------------------------------------------------------
# Auth Middleware — API Key mode
# ---------------------------------------------------------------------------


class TestAuthMiddlewareAPIKey:
    """Integration tests for API key authentication."""

    async def test_valid_api_key_bearer(self):
        store = APIKeyStore()
        store.register("sk-test-key", subject="user-1", tenant_id="acme")
        config = AuthConfig(mode=AuthMode.API_KEY, api_key_store=store)
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get(
            "/protected",
            headers={"Authorization": "Bearer sk-test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["authenticated"] is True
        assert data["subject"] == "user-1"
        assert data["tenant_id"] == "acme"

    async def test_valid_api_key_header(self):
        store = APIKeyStore()
        store.register("sk-test-key", subject="user-1")
        config = AuthConfig(mode=AuthMode.API_KEY, api_key_store=store)
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get(
            "/protected",
            headers={"X-API-Key": "sk-test-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is True

    async def test_invalid_api_key(self):
        store = APIKeyStore()
        store.register("sk-valid", subject="user-1")
        config = AuthConfig(mode=AuthMode.API_KEY, api_key_store=store)
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get(
            "/protected",
            headers={"Authorization": "Bearer sk-invalid"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "UNAUTHORIZED"

    async def test_missing_credentials(self):
        store = APIKeyStore()
        store.register("sk-valid", subject="user-1")
        config = AuthConfig(mode=AuthMode.API_KEY, api_key_store=store)
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get("/protected")
        assert resp.status_code == 401

    async def test_health_excluded(self):
        store = APIKeyStore()
        config = AuthConfig(mode=AuthMode.API_KEY, api_key_store=store)
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


# ---------------------------------------------------------------------------
# Auth Middleware — JWT mode
# ---------------------------------------------------------------------------


class TestAuthMiddlewareJWT:
    """Integration tests for JWT authentication."""

    async def test_valid_jwt(self):
        token = create_jwt(SECRET, subject="user-1", tenant_id="acme", roles=["admin"])
        config = AuthConfig(mode=AuthMode.JWT, jwt_secret=SECRET)
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["authenticated"] is True
        assert data["subject"] == "user-1"
        assert data["tenant_id"] == "acme"
        assert "admin" in data["roles"]

    async def test_expired_jwt_rejected(self):
        token = create_jwt(SECRET, subject="user-1", expires_in=-100)
        config = AuthConfig(mode=AuthMode.JWT, jwt_secret=SECRET)
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    async def test_wrong_secret_rejected(self):
        token = create_jwt("other-secret", subject="user-1")
        config = AuthConfig(mode=AuthMode.JWT, jwt_secret=SECRET)
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    async def test_no_token_rejected(self):
        config = AuthConfig(mode=AuthMode.JWT, jwt_secret=SECRET)
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get("/protected")
        assert resp.status_code == 401

    async def test_health_excluded(self):
        config = AuthConfig(mode=AuthMode.JWT, jwt_secret=SECRET)
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_jwt_with_issuer_audience(self):
        token = create_jwt(
            SECRET, subject="user-1", issuer="ngen", audience="api"
        )
        config = AuthConfig(
            mode=AuthMode.JWT, jwt_secret=SECRET,
            jwt_issuer="ngen", jwt_audience="api",
        )
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is True

    async def test_jwt_wrong_issuer_rejected(self):
        token = create_jwt(SECRET, subject="user-1", issuer="other")
        config = AuthConfig(
            mode=AuthMode.JWT, jwt_secret=SECRET, jwt_issuer="ngen"
        )
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Auth Mode NONE
# ---------------------------------------------------------------------------


class TestAuthModeNone:
    """Tests for no-auth mode (development)."""

    async def test_no_auth_passes_through(self):
        config = AuthConfig(mode=AuthMode.NONE)
        app = _make_app(config)
        client = await _client(app)

        resp = await client.get("/protected")
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is False


# ---------------------------------------------------------------------------
# Authorization helpers
# ---------------------------------------------------------------------------


class TestAuthorization:
    """Tests for scope and role checking."""

    def test_require_scope_granted(self):
        identity = AuthIdentity(subject="u1", scopes=["read", "write"])
        assert require_scope(identity, "read") is True

    def test_require_scope_denied(self):
        identity = AuthIdentity(subject="u1", scopes=["read"])
        assert require_scope(identity, "delete") is False

    def test_require_scope_none_identity(self):
        assert require_scope(None, "read") is False

    def test_require_role_granted(self):
        identity = AuthIdentity(subject="u1", roles=["admin", "operator"])
        assert require_role(identity, "admin") is True

    def test_require_role_denied(self):
        identity = AuthIdentity(subject="u1", roles=["viewer"])
        assert require_role(identity, "admin") is False

    def test_require_role_none_identity(self):
        assert require_role(None, "admin") is False

    async def test_role_based_endpoint(self):
        """Test that role-based authorization works end-to-end."""
        store = APIKeyStore()
        store.register("admin-key", subject="admin", roles=["admin"])
        store.register("viewer-key", subject="viewer", roles=["viewer"])
        config = AuthConfig(mode=AuthMode.API_KEY, api_key_store=store)
        app = _make_app(config)
        client = await _client(app)

        # Admin can access
        resp = await client.get("/admin", headers={"X-API-Key": "admin-key"})
        assert resp.status_code == 200
        assert resp.json()["admin"] is True

        # Viewer is forbidden
        resp = await client.get("/admin", headers={"X-API-Key": "viewer-key"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Path exclusion tests
# ---------------------------------------------------------------------------


class TestPathExclusion:
    """Tests for path exclusion from auth."""

    async def test_custom_excluded_paths(self):
        config = AuthConfig(
            mode=AuthMode.JWT,
            jwt_secret=SECRET,
            exclude_paths=["/health", "/metrics", "/public"],
        )
        app = FastAPI()
        add_auth(app, config)

        @app.get("/public")
        async def public():
            return {"public": True}

        @app.get("/private")
        async def private():
            return {"private": True}

        client = await _client(app)

        # Public is accessible
        resp = await client.get("/public")
        assert resp.status_code == 200

        # Private requires auth
        resp = await client.get("/private")
        assert resp.status_code == 401

    async def test_subpath_excluded(self):
        config = AuthConfig(
            mode=AuthMode.JWT,
            jwt_secret=SECRET,
            exclude_paths=["/api/v1/public"],
        )
        app = FastAPI()
        add_auth(app, config)

        @app.get("/api/v1/public/data")
        async def public_data():
            return {"data": True}

        client = await _client(app)
        resp = await client.get("/api/v1/public/data")
        assert resp.status_code == 200
