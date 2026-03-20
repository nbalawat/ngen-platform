"""Workflow commands — run, list, get, approve, cancel."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click
import yaml

from ngen_cli.client import NgenClient
from ngen_cli.output import (
    console,
    print_error,
    print_json,
    print_runs_table,
    print_sse_event,
    print_success,
)


def _make_client(ctx: click.Context) -> NgenClient:
    return NgenClient(
        workflow_url=ctx.obj["workflow_url"],
        registry_url=ctx.obj["registry_url"],
        gateway_url=ctx.obj["gateway_url"],
    )


@click.group()
def workflow() -> None:
    """Manage workflow runs."""


@workflow.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--input", "-i", "input_json",
    help="Input data as JSON string.",
)
@click.option(
    "--input-file", "-f",
    type=click.Path(exists=True, path_type=Path),
    help="Input data from a JSON file.",
)
@click.option("--stream/--no-stream", default=True, help="Stream events in real time.")
@click.option("--session-id", "-s", help="Session ID for workflow run.")
@click.option("--json-output", "-j", "as_json", is_flag=True, help="Output raw JSON.")
@click.pass_context
def run(
    ctx: click.Context,
    file: Path,
    input_json: str | None,
    input_file: Path | None,
    stream: bool,
    session_id: str | None,
    as_json: bool,
) -> None:
    """Run a workflow from a YAML file.

    FILE is the path to a WorkflowCRD YAML file.
    """
    workflow_yaml = file.read_text()

    # Validate it's valid YAML
    try:
        parsed = yaml.safe_load(workflow_yaml)
        if not isinstance(parsed, dict) or parsed.get("kind") != "Workflow":
            print_error(f"Expected kind 'Workflow' in {file}")
            sys.exit(1)
    except yaml.YAMLError as exc:
        print_error(f"Invalid YAML in {file}: {exc}")
        sys.exit(1)

    # Parse input data
    input_data: dict[str, Any] = {}
    if input_file:
        input_data = json.loads(input_file.read_text())
    elif input_json:
        input_data = json.loads(input_json)

    client = _make_client(ctx)

    if stream and not as_json:
        asyncio.run(_stream_run(client, workflow_yaml, input_data, session_id))
    else:
        result = asyncio.run(
            client.run_workflow(workflow_yaml, input_data, session_id)
        )
        if as_json:
            print_json(result)
        else:
            status = result.get("status", "unknown")
            run_id = result.get("run_id", "?")
            style = "green" if status == "completed" else "red"
            console.print(
                f"[bold {style}]Workflow {status}[/bold {style}] "
                f"(run: {run_id})"
            )
            if result.get("error"):
                print_error(result["error"])


async def _stream_run(
    client: NgenClient,
    workflow_yaml: str,
    input_data: dict[str, Any],
    session_id: str | None,
) -> None:
    """Stream workflow events with rich output."""
    console.print("[bold]Starting workflow...[/bold]\n")
    current_event: str | None = None

    async for line in client.stream_workflow(workflow_yaml, input_data, session_id):
        line = line.strip()
        if not line:
            continue
        if line.startswith(":"):
            print_sse_event("keepalive", None)
            continue
        if line.startswith("event: "):
            current_event = line[len("event: "):]
        elif line.startswith("data: "):
            data = json.loads(line[len("data: "):])
            print_sse_event(current_event, data)
            current_event = None


@workflow.command("list")
@click.option("--status", "-s", help="Filter by status.")
@click.option("--json-output", "-j", "as_json", is_flag=True, help="Output raw JSON.")
@click.pass_context
def list_runs(ctx: click.Context, status: str | None, as_json: bool) -> None:
    """List workflow runs."""
    client = _make_client(ctx)
    runs = asyncio.run(client.list_runs(status))
    if as_json:
        print_json(runs)
    elif not runs:
        console.print("[dim]No workflow runs found.[/dim]")
    else:
        print_runs_table(runs)


@workflow.command()
@click.argument("run_id")
@click.option("--json-output", "-j", "as_json", is_flag=True, help="Output raw JSON.")
@click.pass_context
def get(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """Get details of a workflow run."""
    client = _make_client(ctx)
    try:
        result = asyncio.run(client.get_run(run_id))
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)
    if as_json:
        print_json(result)
    else:
        print_json(result)


@workflow.command()
@click.argument("run_id")
@click.pass_context
def approve(ctx: click.Context, run_id: str) -> None:
    """Approve a workflow run waiting at an HITL gate."""
    client = _make_client(ctx)
    try:
        result = asyncio.run(client.approve_run(run_id))
        print_success(f"Run {result['run_id']} approved.")
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)


@workflow.command()
@click.argument("run_id")
@click.pass_context
def cancel(ctx: click.Context, run_id: str) -> None:
    """Cancel a running workflow."""
    client = _make_client(ctx)
    try:
        result = asyncio.run(client.cancel_run(run_id))
        print_success(f"Run {result['run_id']} cancelled.")
    except Exception as exc:
        print_error(str(exc))
        sys.exit(1)
