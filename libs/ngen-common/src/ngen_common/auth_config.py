"""Shared auth configuration factory for NGEN services.

Reads ``AUTH_JWT_SECRET`` from environment. When set, enables JWT
authentication. When empty, auth is disabled (development mode).

Usage in any service's ``create_app()``::

    from ngen_common.auth_config import make_auth_config
    from ngen_common.auth import add_auth

    config = make_auth_config()
    add_auth(app, config)
"""

from __future__ import annotations

import os

from ngen_common.auth import AuthConfig, AuthMode


def make_auth_config() -> AuthConfig:
    """Build an AuthConfig from environment variables.

    Environment variables:
    - ``AUTH_JWT_SECRET`` — JWT signing secret. Empty = auth disabled.
    - ``AUTH_JWT_ISSUER`` — Optional JWT issuer claim.
    - ``AUTH_JWT_AUDIENCE`` — Optional JWT audience claim.
    """
    secret = os.environ.get("AUTH_JWT_SECRET", "")
    if not secret:
        return AuthConfig(mode=AuthMode.NONE)

    return AuthConfig(
        mode=AuthMode.JWT,
        jwt_secret=secret,
        jwt_issuer=os.environ.get("AUTH_JWT_ISSUER"),
        jwt_audience=os.environ.get("AUTH_JWT_AUDIENCE"),
        exclude_paths=["/health", "/metrics", "/docs", "/openapi.json", "/redoc"],
    )
