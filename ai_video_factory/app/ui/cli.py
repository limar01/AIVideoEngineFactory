"""CLI Dashboard — Typer-based MVP UI for the AI Video Factory.

Per ADR-0003: MVP CLI drives the REST API.
Full React dashboard is deferred.

Usage:
    aivf init                     # Initialize database + config
    aivf serve                    # Start API server
    aivf project create [opts]    # Create a new project
    aivf project start <id>       # Begin pipeline
    aivf project list             # List projects
    aivf project status <id>      # Show project status
    aivf project pause <id>       # Pause project
    aivf project resume <id>      # Resume project
    aivf queue list [opts]        # List queue items
    aivf queue stats [opts]       # Show queue statistics
    aivf queue retry <id>         # Retry a failed job
    aivf queue skip <id>          # Skip a scene
    aivf account add [opts]       # Add an authorized account
    aivf account list             # List accounts
    aivf provider status          # Check provider status
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="AI Video Factory",
    help="Modular free-tier AI video generation pipeline.",
    add_completion=False,
)

project_app = typer.Typer(name="project", help="Project management")
queue_app = typer.Typer(name="queue", help="Queue and job management")
account_app = typer.Typer(name="account", help="Account management")
provider_app = typer.Typer(name="provider", help="Provider management")

app.add_typer(project_app, name="project")
app.add_typer(queue_app, name="queue")
app.add_typer(account_app, name="account")
app.add_typer(provider_app, name="provider")

console = Console()


# --------------------------------------------------------------------------- #
# API Client
# --------------------------------------------------------------------------- #

class APIClient:
    """Thin HTTP client wrapping the REST API."""

    def __init__(self, base_url: str = "http://localhost:8890"):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self.client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict | None = None) -> dict:
        resp = self.client.post(path, data=data or {})
        resp.raise_for_status()
        return resp.json()

    # -- Project API --

    def create_project(self, name: str, niche: str, topic: str, target_seconds: int,
                       description: str | None = None) -> dict:
        return self._post("/api/v1/projects", {
            "name": name, "niche": niche, "topic": topic,
            "target_seconds": target_seconds, "description": description,
        })

    def list_projects(self) -> list[dict]:
        return self._get("/api/v1/projects")

    def get_project(self, project_id: str) -> dict:
        return self._get(f"/api/v1/projects/{project_id}")

    def start_project(self, project_id: str) -> dict:
        return self._post(f"/api/v1/projects/{project_id}/start")

    def pause_project(self, project_id: str) -> dict:
        return self._post(f"/api/v1/projects/{project_id}/pause")

    def resume_project(self, project_id: str) -> dict:
        return self._post(f"/api/v1/projects/{project_id}/resume")

    def project_status(self, project_id: str) -> dict:
        return self._get(f"/api/v1/projects/{project_id}/status")

    # -- Queue API --

    def queue_list(self, project_id: str | None = None) -> list[dict]:
        params = {"project_id": project_id} if project_id else None
        return self._get("/api/v1/queue", params)

    def queue_stats(self, project_id: str | None = None) -> dict:
        params = {"project_id": project_id} if project_id else None
        return self._get("/api/v1/queue/stats", params)

    def retry_job(self, job_id: str) -> dict:
        return self._post(f"/api/v1/queue/retry/{job_id}")

    def skip_job(self, job_id: str) -> dict:
        return self._post(f"/api/v1/queue/skip/{job_id}")

    # -- Provider API --

    def provider_status(self) -> dict:
        return self._get("/api/v1/provider/status")

    def provider_test(self) -> dict:
        return self._post("/api/v1/provider/test-connection")


def get_client(api_url: str = "http://localhost:8890") -> APIClient:
    return APIClient(api_url)


# --------------------------------------------------------------------------- #
# Serve / Init commands (top-level)
# --------------------------------------------------------------------------- #

@app.command()
def init(
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u", help="API URL"),
):
    """Initialize database and configuration."""
    from app.core.database import get_engine, init_db, run_migrations

    # Ensure config dir exists
    from app.core.config import CONFIG_DIR
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize database
    engine = get_engine()
    try:
        applied = run_migrations()
        console.print(f"[green]Migrations applied: {len(applied)}[/green]")
        for m in applied:
            console.print(f"  ✓ {m}")
    except Exception:
        init_db(engine)
        console.print("[green]Database initialized (schema created)[/green]")

    # Bootstrap encryption key
    from app.core.security import ensure_encryption_key
    try:
        ensure_encryption_key()
        console.print("[green]Encryption key configured[/green]")
    except Exception as e:
        console.print(f"[yellow]Warning: encryption key setup: {e}[/yellow]")

    from app.core.config import get_settings
    settings = get_settings()
    console.print(f"[green]AI Video Factory initialized[/green]")
    console.print(f"  Database: {settings.database_path}")
    console.print(f"  Projects: {settings.projects_dir}")
    console.print(f"  API: http://{settings.api_host}:{settings.api_port}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h"),
    port: int = typer.Option(8890, "--port", "-p"),
    reload: bool = typer.Option(False, "--reload", "-r"),
):
    """Start the API server."""
    import uvicorn
    console.print(f"[cyan]Starting AI Video Factory API on {host}:{port}[/cyan]")
    uvicorn.run(
        "app.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# --------------------------------------------------------------------------- #
# Project commands
# --------------------------------------------------------------------------- #

@project_app.command("create")
def project_create(
    name: str = typer.Option(..., "--name", "-n", help="Project name"),
    niche: str = typer.Option("horror", "--niche", help="Niche (horror, comedy, etc.)"),
    topic: str = typer.Option(..., "--topic", "-t", help="Topic for the story"),
    duration: int = typer.Option(600, "--duration", "-d", help="Target duration in seconds"),
    description: str = typer.Option(None, "--desc", help="Project description"),
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """Create a new video project."""
    client = get_client(api_url)
    try:
        result = client.create_project(name, niche, topic, duration, description)
        console.print(Panel(
            f"[green]Project created successfully![/green]\n\n"
            f"  ID: {result['id']}\n"
            f"  Name: {result['name']}\n"
            f"  Status: {result['status']}\n"
            f"  Created: {result['created_at']}",
            title="New Project"
        ))
        console.print(f"\nTo start generation: [cyan]aivf project start {result['id']}[/cyan]")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


@project_app.command("list")
def project_list(
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """List all projects."""
    client = get_client(api_url)
    try:
        projects = client.list_projects()
        if not projects:
            console.print("[dim]No projects found. Create one with: aivf project create[/dim]")
            return

        table = Table(title="AI Video Factory Projects")
        table.add_column("ID", style="cyan", overflow="fold")
        table.add_column("Name", style="white")
        table.add_column("Status", style="yellow")
        table.add_column("Niche", style="magenta")
        table.add_column("Topic", style="white")
        table.add_column("Duration", style="green")
        table.add_column("Started", style="dim")
        table.add_column("Completed", style="dim")

        for p in projects:
            table.add_row(
                p["id"][:8], p["name"], p["status"], p["niche"],
                p["topic"], f"{p['target_seconds']}s",
                p.get("started_at") or "-",
                p.get("completed_at") or "-",
            )
        console.print(table)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


@project_app.command("start")
def project_start(
    project_id: str = typer.Argument(..., help="Project ID to start"),
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """Start the generation pipeline for a project."""
    client = get_client(api_url)
    try:
        result = client.start_project(project_id)
        console.print(Panel(
            f"Project {project_id} is now [yellow]{result['status']}[/yellow]\n\n"
            f"The pipeline will:\n"
            f"  1. Generate story, character bible, visual bible\n"
            f"  2. Create scenes and compile prompts\n"
            f"  3. Queue generation jobs\n"
            f"  4. Submit to provider, download, validate\n"
            f"  5. Assemble final video with FFmpeg\n\n"
            f"Watch progress: [cyan]aivf project status {project_id}[/cyan]",
            title="Pipeline Started"
        ))
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


@project_app.command("status")
def project_status(
    project_id: str = typer.Argument(..., help="Project ID"),
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """Show project status and progress."""
    client = get_client(api_url)
    try:
        status = client.project_status(project_id)

        table = Table(title=f"Project: {status['name']}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Status", status["status"])
        table.add_row("Total Scenes", str(status["total_scenes"]))
        table.add_row("Valid Clips", str(status["valid_clips"]))
        table.add_row("Started", status.get("started_at") or "-")
        table.add_row("Completed", status.get("completed_at") or "-")

        console.print(table)

        # State breakdown
        if status.get("by_state"):
            state_table = Table(title="Scene States")
            state_table.add_column("State", style="yellow")
            state_table.add_column("Count", style="white", justify="right")
            for state, count in sorted(status["by_state"].items()):
                color = "green" if count > 0 or state == "VALID" else "dim"
                state_table.add_row(state, f"[{color}]{count}[/{color}]")
            console.print(state_table)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


@project_app.command("pause")
def project_pause(
    project_id: str = typer.Argument(..., help="Project ID to pause"),
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """Pause a running project."""
    client = get_client(api_url)
    try:
        result = client.pause_project(project_id)
        console.print(f"[yellow]Project {project_id} paused[/yellow]. "
                       f"Resume with: [cyan]aivf project resume {project_id}[/cyan]")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


@project_app.command("resume")
def project_resume(
    project_id: str = typer.Argument(..., help="Project ID to resume"),
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """Resume a paused project."""
    client = get_client(api_url)
    try:
        result = client.resume_project(project_id)
        console.print(f"[green]Project {project_id} resumed[/green]. "
                       f"Monitor with: [cyan]aivf project status {project_id}[/cyan]")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


# --------------------------------------------------------------------------- #
# Queue commands
# --------------------------------------------------------------------------- #

@queue_app.command("list")
def queue_list(
    project_id: str = typer.Option(None, "--project", "-p", help="Filter by project ID"),
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """List generation jobs in the queue."""
    client = get_client(api_url)
    try:
        jobs = client.queue_list(project_id)
        if not jobs:
            console.print("[dim]Queue is empty.[/dim]")
            return

        table = Table(title="Generation Queue")
        table.add_column("Job ID", style="cyan")
        table.add_column("State", style="yellow")
        table.add_column("Retries", style="white", justify="right")
        table.add_column("Max", style="dim", justify="right")
        table.add_column("Error", style="red")

        for j in jobs:
            state_color = {
                "VALID": "green",
                "FAILED": "red",
                "QUOTA_WAIT": "yellow",
                "BLOCKED": "yellow",
                "SUBMITTED": "cyan",
                "GENERATING": "blue",
                "PENDING": "dim",
                "READY": "green",
            }.get(j["state"], "white")
            table.add_row(
                j["job_id"][:8],
                f"[{state_color}]{j['state']}[/{state_color}]",
                str(j["retry_count"]),
                str(j["max_retries"]),
                j.get("error_reason") or "",
            )
        console.print(table)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


@queue_app.command("stats")
def queue_stats(
    project_id: str = typer.Option(None, "--project", "-p", help="Filter by project ID"),
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """Show queue statistics."""
    client = get_client(api_url)
    try:
        stats = client.queue_stats(project_id)
        table = Table(title="Queue Statistics")
        table.add_column("State", style="yellow")
        table.add_column("Count", style="white", justify="right")
        for state, count in sorted(stats.items()):
            table.add_row(state, str(count))
        console.print(table)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


@queue_app.command("retry")
def queue_retry(
    job_id: str = typer.Argument(..., help="Job ID to retry"),
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """Retry a failed job (auto-repair enabled)."""
    client = get_client(api_url)
    try:
        result = client.retry_job(job_id)
        console.print(f"[green]Job retried[/green]\n"
                       f"  Old job: {result['old_job_id']}\n"
                       f"  New job: {result['new_job_id']}\n"
                       f"  New prompt version: {result['new_prompt_version']}")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


@queue_app.command("skip")
def queue_skip(
    job_id: str = typer.Argument(..., help="Job ID to skip"),
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """Skip a non-critical scene."""
    client = get_client(api_url)
    try:
        result = client.skip_job(job_id)
        console.print(f"[yellow]Job {job_id} skipped[/yellow] "
                       f"(state: {result['state']})")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


# --------------------------------------------------------------------------- #
# Account commands
# --------------------------------------------------------------------------- #

@account_app.command("add")
def account_add(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name (e.g. snapgen)"),
    label: str = typer.Option(None, "--label", "-l", help="Account label"),
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """Add a new authorized provider account."""
    console.print(f"[yellow]To authorize a {provider} account, you need to:[/yellow]")
    console.print(f"  1. Log in to {provider} in your browser")
    console.print(f"  2. The system will capture your session via CDP auth")
    console.print(f"  3. Or manually enter credentials (encrypted at rest)")
    console.print(f"\n[cyan]Use the web dashboard at http://localhost:8890/auth[/cyan]")
    console.print(f"[dim]Or set VAF_API_KEY for API access[/dim]")


@account_app.command("list")
def account_list(
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """List provider accounts."""
    client = get_client(api_url)
    try:
        # Use provider status endpoint
        status = client.provider_status()
        console.print(f"[cyan]Provider: {status['provider']}[/cyan]")
        console.print(f"  Session valid: {status['session_valid']}")
        quota = status.get("quota", {})
        if quota:
            console.print(f"  Quota: {quota}")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


# --------------------------------------------------------------------------- #
# Provider commands
# --------------------------------------------------------------------------- #

@provider_app.command("status")
def provider_status(
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """Check provider status."""
    client = get_client(api_url)
    try:
        status = client.provider_status()
        table = Table(title="Provider Status")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Provider", status["provider"])
        table.add_row("Session Valid", str(status["session_valid"]))
        quota = status.get("quota")
        if quota:
            for k, v in quota.items():
                table.add_row(f"Quota: {k}", str(v))
        console.print(table)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


@provider_app.command("test")
def provider_test(
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """Test provider connection."""
    client = get_client(api_url)
    try:
        result = client.provider_test()
        if result.get("connected"):
            console.print(f"[green]✓ Connected to {result['provider']}[/green]")
        else:
            console.print("[red]✗ Connection failed[/red]")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")


# Alias the main app for the entry point
main = app


if __name__ == "__main__":
    app()
