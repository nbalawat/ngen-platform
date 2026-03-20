"""Server-Sent Events formatting utilities."""

from __future__ import annotations

import json
from typing import Any


def format_sse(event_type: str, data: dict[str, Any]) -> str:
    """Format a single SSE message.

    Returns a string in the format::

        event: {event_type}
        data: {json}

    with a trailing blank line to delimit the message.
    """
    json_str = json.dumps(data, default=str)
    return f"event: {event_type}\ndata: {json_str}\n\n"


def format_keepalive() -> str:
    """Return an SSE comment line that keeps the connection alive.

    SSE clients ignore lines starting with ``:``, but proxies and load
    balancers see activity and keep the connection open.
    """
    return ": keepalive\n\n"
