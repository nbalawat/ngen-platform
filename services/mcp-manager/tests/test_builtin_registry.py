"""Tests for built-in handler registry and transport dispatch."""

from __future__ import annotations

import pytest

from mcp_manager.builtin_registry import BuiltinHandlerRegistry
from mcp_manager.models import Server, TransportType
from mcp_manager.transport import MCPTransport, MCPTransportError


class TestBuiltinHandlerRegistry:
    def test_register_and_retrieve(self):
        registry = BuiltinHandlerRegistry()

        async def handler(args):
            return {"content": [{"type": "text", "text": "ok"}]}

        registry.register("my-server", "my-tool", handler)
        assert registry.get("my-server", "my-tool") is handler
        assert registry.has("my-server", "my-tool")

    def test_missing_handler_returns_none(self):
        registry = BuiltinHandlerRegistry()
        assert registry.get("unknown", "unknown") is None
        assert not registry.has("unknown", "unknown")

    @pytest.mark.asyncio
    async def test_handler_invocation_returns_mcp_format(self):
        registry = BuiltinHandlerRegistry()

        async def handler(args):
            return {"content": [{"type": "text", "text": f"Hello {args.get('name', 'world')}"}]}

        registry.register("test-server", "greet", handler)
        h = registry.get("test-server", "greet")
        result = await h({"name": "NGEN"})
        assert result["content"][0]["text"] == "Hello NGEN"

    def test_registered_tools_list(self):
        registry = BuiltinHandlerRegistry()

        async def h(args):
            return {}

        registry.register("s1", "t1", h)
        registry.register("s1", "t2", h)
        registry.register("s2", "t1", h)
        assert sorted(registry.registered_tools) == ["s1/t1", "s1/t2", "s2/t1"]


class TestBuiltinTransportDispatch:
    @pytest.mark.asyncio
    async def test_builtin_transport_dispatches_to_handler(self):
        registry = BuiltinHandlerRegistry()

        async def handler(args):
            return {"content": [{"type": "text", "text": f"Result: {args.get('q')}"}]}

        registry.register("test-server", "test-tool", handler)

        transport = MCPTransport(builtin_registry=registry)
        server = Server(
            name="test-server",
            endpoint="builtin://test-server",
            transport=TransportType.BUILTIN,
        )

        result = await transport.invoke(server, "test-tool", {"q": "hello"})
        assert "text" in result
        assert "Result: hello" in result["text"]

    @pytest.mark.asyncio
    async def test_builtin_transport_unknown_tool_raises(self):
        registry = BuiltinHandlerRegistry()
        transport = MCPTransport(builtin_registry=registry)
        server = Server(
            name="test-server",
            endpoint="builtin://test-server",
            transport=TransportType.BUILTIN,
        )

        with pytest.raises(MCPTransportError, match="No built-in handler"):
            await transport.invoke(server, "nonexistent", {})

    @pytest.mark.asyncio
    async def test_builtin_no_registry_raises(self):
        transport = MCPTransport()  # no registry
        server = Server(
            name="test-server",
            endpoint="builtin://test-server",
            transport=TransportType.BUILTIN,
        )

        with pytest.raises(MCPTransportError, match="No built-in handler registry"):
            await transport.invoke(server, "test-tool", {})

    @pytest.mark.asyncio
    async def test_builtin_handler_error_wrapped(self):
        registry = BuiltinHandlerRegistry()

        async def bad_handler(args):
            raise ValueError("something broke")

        registry.register("bad-server", "bad-tool", bad_handler)
        transport = MCPTransport(builtin_registry=registry)
        server = Server(
            name="bad-server",
            endpoint="builtin://bad-server",
            transport=TransportType.BUILTIN,
        )

        with pytest.raises(MCPTransportError, match="something broke"):
            await transport.invoke(server, "bad-tool", {})
