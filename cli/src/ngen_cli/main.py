"""NGEN Platform CLI — main entry point."""

from __future__ import annotations

import click

from ngen_cli.commands.health import health
from ngen_cli.commands.model import model
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
@click.pass_context
def cli(
    ctx: click.Context,
    workflow_url: str,
    registry_url: str,
    gateway_url: str,
) -> None:
    """NGEN Platform CLI — manage workflows, models, and services."""
    ctx.ensure_object(dict)
    ctx.obj["workflow_url"] = workflow_url
    ctx.obj["registry_url"] = registry_url
    ctx.obj["gateway_url"] = gateway_url


cli.add_command(workflow)
cli.add_command(model)
cli.add_command(health)
