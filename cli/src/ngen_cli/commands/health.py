"""Health command — check service availability."""

from __future__ import annotations

import asyncio

import click

from ngen_cli.client import NgenClient
from ngen_cli.output import print_health_table


def _make_client(ctx: click.Context) -> NgenClient:
    return NgenClient(
        workflow_url=ctx.obj["workflow_url"],
        registry_url=ctx.obj["registry_url"],
        gateway_url=ctx.obj["gateway_url"],
    )


@click.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    """Check health of all NGEN platform services."""
    client = _make_client(ctx)
    results = asyncio.run(_check_all(client))
    print_health_table(results)


async def _check_all(client: NgenClient) -> dict[str, dict | str]:
    """Check all services concurrently."""
    services = {
        "workflow-engine": client.workflow_url,
        "model-registry": client.registry_url,
        "model-gateway": client.gateway_url,
    }

    results: dict[str, dict | str] = {}
    for name, url in services.items():
        try:
            results[name] = await client.check_health(url)
        except Exception as exc:
            results[name] = f"unreachable ({exc.__class__.__name__})"

    return results
