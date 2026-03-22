"""MCP transport layer — dispatches tool calls to MCP servers.

Supports the Streamable HTTP transport (the primary MCP transport for
remote servers). SSE and STDIO transports are recognized but not yet
implemented.

The transport sends a JSON-RPC 2.0 ``tools/call`` request to the server's
endpoint and returns the result content.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

import httpx

from mcp_manager.builtin_registry import BuiltinHandlerRegistry
from mcp_manager.models import AuthConfig, AuthType, Server, TransportType

logger = logging.getLogger(__name__)


class MCPTransportError(Exception):
    """Raised when an MCP transport operation fails."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MCPTransport:
    """Dispatches tool calls to MCP servers via their registered transport.

    Currently supports:
    - ``streamable-http``: JSON-RPC 2.0 over HTTP POST
    - ``sse``: Server-Sent Events (planned)
    - ``stdio``: Standard I/O subprocess (planned)
    """

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
        builtin_registry: BuiltinHandlerRegistry | None = None,
    ) -> None:
        self._client = client
        self._timeout = timeout
        self._owns_client = False
        self._builtin_registry = builtin_registry

    async def invoke(
        self,
        server: Server,
        tool_name: str,
        arguments: dict[str, Any],
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Invoke a tool on an MCP server.

        Returns the result dict from the JSON-RPC response.
        Raises MCPTransportError on failure.
        """
        if server.transport == TransportType.BUILTIN:
            return await self._invoke_builtin(server, tool_name, arguments, namespace)
        elif server.transport in (TransportType.STREAMABLE_HTTP, TransportType.SSE):
            return await self._invoke_http(server, tool_name, arguments)
        else:
            raise MCPTransportError(
                f"Transport '{server.transport}' not supported for remote invocation"
            )

    async def _invoke_builtin(
        self,
        server: Server,
        tool_name: str,
        arguments: dict[str, Any],
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Dispatch to a built-in handler function."""
        if self._builtin_registry is None:
            raise MCPTransportError(
                f"No built-in handler registry configured for server '{server.name}'"
            )

        handler = self._builtin_registry.get(server.name, tool_name)
        if handler is None:
            raise MCPTransportError(
                f"No built-in handler registered for '{server.name}/{tool_name}'"
            )

        try:
            # Inject namespace for tenant scoping
            arguments_with_ns = {**arguments, "_namespace": namespace}
            result = await handler(arguments_with_ns)
            # Ensure result is in MCP content format
            if isinstance(result, dict) and "content" in result:
                texts = []
                for block in result["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block.get("text", ""))
                if texts:
                    return {"content": result["content"], "text": "\n".join(texts)}
                return result
            # Wrap plain text result
            if isinstance(result, str):
                return {
                    "content": [{"type": "text", "text": result}],
                    "text": result,
                }
            return result
        except MCPTransportError:
            raise
        except Exception as exc:
            raise MCPTransportError(
                f"Built-in handler error for '{server.name}/{tool_name}': {exc}"
            ) from exc

    async def _invoke_http(
        self,
        server: Server,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a JSON-RPC tools/call request over HTTP."""
        client = self._client
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout)
            should_close = True

        # Build JSON-RPC 2.0 request
        request_id = uuid4().hex[:12]
        jsonrpc_body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        # Build headers
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._apply_auth(headers, server.auth)

        try:
            resp = await client.post(
                server.endpoint,
                json=jsonrpc_body,
                headers=headers,
            )

            if resp.status_code >= 400:
                raise MCPTransportError(
                    f"MCP server returned {resp.status_code}: {resp.text}",
                    status_code=resp.status_code,
                )

            data = resp.json()

            # Handle JSON-RPC error response
            if "error" in data:
                err = data["error"]
                msg = err.get("message", str(err))
                code = err.get("code", -1)
                raise MCPTransportError(
                    f"MCP server error ({code}): {msg}"
                )

            # Extract result — JSON-RPC result field
            result = data.get("result", {})

            # MCP tools/call returns {content: [...]} — extract content
            if isinstance(result, dict) and "content" in result:
                content_blocks = result["content"]
                # Flatten text content blocks for convenience
                texts = []
                for block in content_blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block.get("text", ""))
                if texts:
                    return {"content": content_blocks, "text": "\n".join(texts)}
                return {"content": content_blocks}

            return result

        except httpx.TimeoutException as exc:
            raise MCPTransportError(
                f"Timeout invoking tool '{tool_name}' on '{server.name}': {exc}"
            ) from exc
        except httpx.ConnectError as exc:
            raise MCPTransportError(
                f"Connection failed to MCP server '{server.name}' at {server.endpoint}: {exc}"
            ) from exc
        except MCPTransportError:
            raise
        except Exception as exc:
            raise MCPTransportError(
                f"Unexpected error invoking '{tool_name}': {exc}"
            ) from exc
        finally:
            if should_close:
                await client.aclose()

    @staticmethod
    def _apply_auth(headers: dict[str, str], auth: AuthConfig) -> None:
        """Apply authentication headers based on server auth config."""
        if auth.type == AuthType.API_KEY:
            # API key can be in secret_ref or config
            key = auth.secret_ref or auth.config.get("api_key", "")
            if key:
                headers["Authorization"] = f"Bearer {key}"
        elif auth.type == AuthType.OAUTH2:
            token = auth.config.get("access_token", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
