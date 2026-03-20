"""Model commands — list, get, register, delete."""

from __future__ import annotations

import asyncio
import json
import sys

import click

from ngen_cli.client import NgenClient
from ngen_cli.output import (
    console,
    print_error,
    print_json,
    print_models_table,
    print_success,
)


def _make_client(ctx: click.Context) -> NgenClient:
    return NgenClient(
        workflow_url=ctx.obj["workflow_url"],
        registry_url=ctx.obj["registry_url"],
        gateway_url=ctx.obj["gateway_url"],
    )


@click.group()
def model() -> None:
    """Manage registered models."""


@model.command("list")
@click.option("--provider", "-p", help="Filter by provider.")
@click.option("--json-output", "-j", "as_json", is_flag=True, help="Output raw JSON.")
@click.pass_context
def list_models(ctx: click.Context, provider: str | None, as_json: bool) -> None:
    """List registered models."""
    client = _make_client(ctx)
    models = asyncio.run(client.list_models(provider))
    if as_json:
        print_json(models)
    elif not models:
        console.print("[dim]No models registered.[/dim]")
    else:
        print_models_table(models)


@model.command()
@click.argument("model_id")
@click.option("--json-output", "-j", "as_json", is_flag=True, help="Output raw JSON.")
@click.pass_context
def get(ctx: click.Context, model_id: str, as_json: bool) -> None:
    """Get a model by ID or name."""
    client = _make_client(ctx)
    try:
        result = asyncio.run(client.get_model(model_id))
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)
    if as_json:
        print_json(result)
    else:
        print_json(result)


@model.command()
@click.option("--name", "-n", required=True, help="Model name.")
@click.option("--provider", "-p", required=True, help="Provider (anthropic, openai, ollama).")
@click.option("--model-id", "-m", "model_id_str", required=True, help="Provider model ID.")
@click.option("--capability", "-c", multiple=True, help="Capability (chat, embedding, code, vision).")
@click.option("--json-output", "-j", "as_json", is_flag=True, help="Output raw JSON.")
@click.pass_context
def register(
    ctx: click.Context,
    name: str,
    provider: str,
    model_id_str: str,
    capability: tuple[str, ...],
    as_json: bool,
) -> None:
    """Register a new model."""
    client = _make_client(ctx)
    data = {
        "name": name,
        "provider": provider,
        "model_id": model_id_str,
        "capabilities": list(capability) if capability else ["chat"],
    }
    try:
        result = asyncio.run(client.register_model(data))
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)
    if as_json:
        print_json(result)
    else:
        print_success(f"Model '{name}' registered (id: {result.get('id', '?')}).")


@model.command()
@click.argument("model_id")
@click.pass_context
def delete(ctx: click.Context, model_id: str) -> None:
    """Delete a model by UUID."""
    client = _make_client(ctx)
    try:
        asyncio.run(client.delete_model(model_id))
        print_success(f"Model {model_id} deleted.")
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)
