"""Policy commands — create, list, get, delete, evaluate."""

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
def policy() -> None:
    """Manage governance policies."""


@policy.command("create")
@click.option("--name", required=True, help="Policy name.")
@click.option("--type", "policy_type", required=True, type=click.Choice(["content_filter", "cost_limit", "tool_restriction", "rate_limit"]))
@click.option("--namespace", default="default", help="Namespace for the policy.")
@click.option("--action", default="block", type=click.Choice(["block", "warn", "log", "escalate"]))
@click.option("--severity", default="medium", type=click.Choice(["low", "medium", "high", "critical"]))
@click.option("--rules", default="{}", help="JSON string of policy rules.")
@click.pass_context
def create(ctx: click.Context, name: str, policy_type: str, namespace: str, action: str, severity: str, rules: str) -> None:
    """Create a governance policy."""
    client = _make_client(ctx)
    try:
        rules_dict = json.loads(rules)
    except json.JSONDecodeError as e:
        print_error(f"Invalid rules JSON: {e}")
        sys.exit(1)

    result = asyncio.run(client.create_policy({
        "name": name,
        "policy_type": policy_type,
        "namespace": namespace,
        "action": action,
        "severity": severity,
        "rules": rules_dict,
    }))
    print_success(f"Policy '{name}' created: {result['id']}")


@policy.command("list")
@click.option("--namespace", default=None, help="Filter by namespace.")
@click.pass_context
def list_policies(ctx: click.Context, namespace: str | None) -> None:
    """List governance policies."""
    client = _make_client(ctx)
    policies = asyncio.run(client.list_policies(namespace=namespace))
    if not policies:
        console.print("[dim]No policies found.[/dim]")
        return
    print_json(policies)


@policy.command("get")
@click.argument("policy_id")
@click.pass_context
def get(ctx: click.Context, policy_id: str) -> None:
    """Get a policy by ID."""
    client = _make_client(ctx)
    result = asyncio.run(client.get_policy(policy_id))
    print_json(result)


@policy.command("delete")
@click.argument("policy_id")
@click.pass_context
def delete(ctx: click.Context, policy_id: str) -> None:
    """Delete a policy by ID."""
    client = _make_client(ctx)
    asyncio.run(client.delete_policy(policy_id))
    print_success(f"Policy '{policy_id}' deleted.")


@policy.command("evaluate")
@click.option("--content", default=None, help="Content to evaluate.")
@click.option("--tool-name", default=None, help="Tool name to check.")
@click.option("--namespace", default="default", help="Namespace context.")
@click.option("--cost", default=None, type=float, help="Estimated cost.")
@click.pass_context
def evaluate(ctx: click.Context, content: str | None, tool_name: str | None, namespace: str, cost: float | None) -> None:
    """Evaluate content/tool against governance policies."""
    client = _make_client(ctx)
    context: dict = {"namespace": namespace}
    if content:
        context["content"] = content
    if tool_name:
        context["tool_name"] = tool_name
    if cost is not None:
        context["estimated_cost"] = cost

    result = asyncio.run(client.evaluate_policy(context))

    if result["allowed"]:
        print_success(f"✓ Allowed ({result['evaluated_policies']} policies checked)")
    else:
        print_error(f"✗ Blocked ({len(result['violations'])} violations)")

    if result.get("violations"):
        console.print("\n[bold red]Violations:[/bold red]")
        for v in result["violations"]:
            console.print(f"  • [{v['severity']}] {v['message']}")

    if result.get("warnings"):
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for w in result["warnings"]:
            console.print(f"  • [{w['severity']}] {w['message']}")
