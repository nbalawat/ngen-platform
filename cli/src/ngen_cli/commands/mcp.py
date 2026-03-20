"""MCP commands — register servers, list tools, search, invoke."""

from __future__ import annotations

import asyncio
import json
import sys

import click

from ngen_cli.client import NgenClient
from ngen_cli.output import console, print_error, print_json, print_success


def _make_client(ctx: click.Context) -> NgenClient:
    return NgenClient(
        workflow_url=ctx.obj["workflow_url"],
        registry_url=ctx.obj["registry_url"],
        gateway_url=ctx.obj["gateway_url"],
        governance_url=ctx.obj.get("governance_url", "http://localhost:8004"),
        mcp_url=ctx.obj.get("mcp_url", "http://localhost:8005"),
    )


@click.group()
def mcp() -> None:
    """Manage MCP servers and tools."""


@mcp.command("register")
@click.option("--name", required=True, help="Server name.")
@click.option("--endpoint", required=True, help="Server endpoint URL.")
@click.option("--namespace", default="default", help="Namespace.")
@click.option("--transport", default="streamable-http", type=click.Choice(["streamable-http", "sse", "stdio"]))
@click.option("--tools-json", default="[]", help="JSON array of tool definitions.")
@click.pass_context
def register(ctx: click.Context, name: str, endpoint: str, namespace: str, transport: str, tools_json: str) -> None:
    """Register an MCP server."""
    client = _make_client(ctx)
    try:
        tools = json.loads(tools_json)
    except json.JSONDecodeError as e:
        print_error(f"Invalid tools JSON: {e}")
        sys.exit(1)

    result = asyncio.run(client.register_server({
        "name": name,
        "endpoint": endpoint,
        "namespace": namespace,
        "transport": transport,
        "tools": tools,
    }))
    print_success(f"Server '{name}' registered: {result['id']}")


@mcp.command("servers")
@click.option("--namespace", default=None, help="Filter by namespace.")
@click.pass_context
def list_servers(ctx: click.Context, namespace: str | None) -> None:
    """List registered MCP servers."""
    client = _make_client(ctx)
    servers = asyncio.run(client.list_servers(namespace=namespace))
    if not servers:
        console.print("[dim]No servers registered.[/dim]")
        return
    print_json(servers)


@mcp.command("tools")
@click.option("--server", "server_name", default=None, help="Filter by server name.")
@click.option("--tag", default=None, help="Filter by tag.")
@click.pass_context
def list_tools(ctx: click.Context, server_name: str | None, tag: str | None) -> None:
    """List available tools."""
    client = _make_client(ctx)
    tools = asyncio.run(client.list_tools(server_name=server_name, tag=tag))
    if not tools:
        console.print("[dim]No tools found.[/dim]")
        return
    print_json(tools)


@mcp.command("search")
@click.argument("query")
@click.pass_context
def search(ctx: click.Context, query: str) -> None:
    """Search tools by keyword."""
    client = _make_client(ctx)
    results = asyncio.run(client.search_tools(query))
    if not results:
        console.print("[dim]No tools match query.[/dim]")
        return
    print_json(results)


@mcp.command("invoke")
@click.argument("server_name")
@click.argument("tool_name")
@click.option("--args", "arguments", default="{}", help="JSON arguments.")
@click.option("--namespace", default="default", help="Namespace.")
@click.pass_context
def invoke(ctx: click.Context, server_name: str, tool_name: str, arguments: str, namespace: str) -> None:
    """Invoke a tool on an MCP server."""
    client = _make_client(ctx)
    try:
        args = json.loads(arguments)
    except json.JSONDecodeError as e:
        print_error(f"Invalid arguments JSON: {e}")
        sys.exit(1)

    result = asyncio.run(client.invoke_tool(server_name, tool_name, args, namespace))
    print_json(result)
