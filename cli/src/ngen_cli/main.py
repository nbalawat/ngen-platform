"""NGEN Platform CLI — main entry point."""

from __future__ import annotations

import click

from ngen_cli.commands.health import health
from ngen_cli.commands.mcp import mcp
from ngen_cli.commands.model import model
from ngen_cli.commands.policy import policy
from ngen_cli.commands.workflow import workflow


@click.group()
@click.option(
    "--workflow-url",
    envvar="NGEN_WORKFLOW_URL",
    default="http://localhost:8003",
    help="Workflow Engine URL.",
)
@click.option(
    "--registry-url",
    envvar="NGEN_REGISTRY_URL",
    default="http://localhost:8002",
    help="Model Registry URL.",
)
@click.option(
    "--gateway-url",
    envvar="NGEN_GATEWAY_URL",
    default="http://localhost:8001",
    help="Model Gateway URL.",
)
@click.option(
    "--governance-url",
    envvar="NGEN_GOVERNANCE_URL",
    default="http://localhost:8004",
    help="Governance Service URL.",
)
@click.option(
    "--mcp-url",
    envvar="NGEN_MCP_URL",
    default="http://localhost:8005",
    help="MCP Manager URL.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    workflow_url: str,
    registry_url: str,
    gateway_url: str,
    governance_url: str,
    mcp_url: str,
) -> None:
    """NGEN Platform CLI — manage workflows, models, policies, MCP servers, and services."""
    ctx.ensure_object(dict)
    ctx.obj["workflow_url"] = workflow_url
    ctx.obj["registry_url"] = registry_url
    ctx.obj["gateway_url"] = gateway_url
    ctx.obj["governance_url"] = governance_url
    ctx.obj["mcp_url"] = mcp_url


cli.add_command(workflow)
cli.add_command(model)
cli.add_command(policy)
cli.add_command(mcp)
cli.add_command(health)
