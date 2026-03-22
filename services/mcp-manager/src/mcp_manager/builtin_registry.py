"""Built-in handler registry for platform-provided tools.

Maps (server_name, tool_name) to async Python handler functions,
enabling tools to run as local functions instead of remote MCP servers.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Handler signature: async (arguments: dict) -> dict with MCP content format
BuiltinHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class BuiltinHandlerRegistry:
    """Registry mapping (server_name, tool_name) to local handler functions."""

    def __init__(self) -> None:
        self._handlers: dict[str, BuiltinHandler] = {}

    def register(
        self, server_name: str, tool_name: str, handler: BuiltinHandler
    ) -> None:
        key = f"{server_name}/{tool_name}"
        self._handlers[key] = handler
        logger.info("Registered built-in handler: %s", key)

    def get(
        self, server_name: str, tool_name: str
    ) -> BuiltinHandler | None:
        return self._handlers.get(f"{server_name}/{tool_name}")

    def has(self, server_name: str, tool_name: str) -> bool:
        return f"{server_name}/{tool_name}" in self._handlers

    @property
    def registered_tools(self) -> list[str]:
        return list(self._handlers.keys())
