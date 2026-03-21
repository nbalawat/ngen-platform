"""CORS middleware helper for NGEN services.

Adds permissive CORS headers for portal access.
Reads ``CORS_ORIGINS`` from environment (comma-separated).
Defaults to ``http://localhost:3000`` for development.
"""

from __future__ import annotations

import os


def add_cors(app: object) -> None:
    """Add CORS middleware to a FastAPI app.

    Reads ``CORS_ORIGINS`` env var (comma-separated origins).
    Defaults to allowing localhost:3000 (portal dev server).
    """
    from starlette.middleware.cors import CORSMiddleware

    origins_str = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
    origins = [o.strip() for o in origins_str.split(",") if o.strip()]

    app.add_middleware(  # type: ignore[attr-defined]
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
