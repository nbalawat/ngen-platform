"""Output formatting helpers for the NGEN CLI."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()
err_console = Console(stderr=True)


def print_json(data: Any) -> None:
    """Pretty-print JSON data."""
    console.print_json(json.dumps(data, default=str))


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    err_console.print(f"[bold red]Error:[/bold red] {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]{message}[/bold green]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]{message}[/bold yellow]")


def print_runs_table(runs: list[dict[str, Any]]) -> None:
    """Print workflow runs as a table."""
    table = Table(title="Workflow Runs")
    table.add_column("Run ID", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")
    table.add_column("Events", justify="right")
    table.add_column("Error")

    for run in runs:
        status = run.get("status", "unknown")
        style = {
            "completed": "green",
            "running": "yellow",
            "pending": "dim",
            "failed": "red",
            "cancelled": "dim red",
            "waiting_approval": "bold yellow",
        }.get(status, "")

        table.add_row(
            run.get("run_id", "?"),
            f"[{style}]{status}[/{style}]",
            str(len(run.get("events", []))),
            run.get("error") or "",
        )

    console.print(table)


def print_models_table(models: list[dict[str, Any]]) -> None:
    """Print models as a table."""
    table = Table(title="Registered Models")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Name", style="cyan")
    table.add_column("Provider", style="bold")
    table.add_column("Capabilities")

    for model in models:
        caps = ", ".join(model.get("capabilities", []))
        table.add_row(
            model.get("id", "?"),
            model.get("name", "?"),
            model.get("provider", "?"),
            caps,
        )

    console.print(table)


def print_health_table(results: dict[str, dict[str, Any] | str]) -> None:
    """Print health check results as a table."""
    table = Table(title="Service Health")
    table.add_column("Service", style="cyan")
    table.add_column("URL", style="dim")
    table.add_column("Status", style="bold")

    for name, result in results.items():
        if isinstance(result, dict):
            status_val = result.get("status", "unknown")
            style = "green" if status_val in ("ok", "healthy") else "yellow"
            table.add_row(name, "", f"[{style}]{status_val}[/{style}]")
        else:
            table.add_row(name, "", f"[red]{result}[/red]")

    console.print(table)


def print_sse_event(event_type: str | None, data: dict[str, Any] | None) -> None:
    """Print a streamed SSE event in a human-friendly format."""
    if event_type == "thinking":
        text = (data or {}).get("data", {}).get("text", "")
        console.print(f"  [dim]{text}[/dim]")
    elif event_type == "text_delta":
        text = (data or {}).get("data", {}).get("text", "")
        console.print(f"  {text}")
    elif event_type == "waiting_approval":
        run_id = (data or {}).get("run_id", "?")
        gate = (data or {}).get("gate", "?")
        console.print(
            f"\n[bold yellow]Approval required[/bold yellow] "
            f"(run: {run_id}, gate: {gate})"
        )
        console.print(
            f"  Run: [cyan]ngen workflow approve {run_id}[/cyan]"
        )
    elif event_type == "done":
        status = (data or {}).get("status", "?")
        run_id = (data or {}).get("run_id", "?")
        style = "green" if status == "completed" else "red"
        console.print(
            f"\n[bold {style}]Workflow {status}[/bold {style}] "
            f"(run: {run_id})"
        )
    elif event_type == "error":
        error = (data or {}).get("error", "unknown error")
        console.print(f"\n[bold red]Error:[/bold red] {error}")
    elif event_type == "keepalive":
        pass  # Silent
    else:
        agent = (data or {}).get("agent_name", "")
        prefix = f"[dim]{agent}[/dim] " if agent else ""
        console.print(f"  {prefix}[dim]{event_type}[/dim]")
