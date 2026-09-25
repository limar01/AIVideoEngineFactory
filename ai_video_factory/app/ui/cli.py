"""CLI Dashboard - Typer-based MVP UI for the AI Video Factory.

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
    aivf vault create-account     # Add account to vault
    aivf vault list-accounts      # List vault accounts
    aivf vault open-login --id    # Login with Google OAuth
    aivf vault mark-logged-in     # Mark account logged in
    aivf vault remove-account     # Remove account from vault
    aivf vault status             # Show vault status
    aivf pipeline generate-story  # Generate story
    aivf pipeline compile-prompts # Compile prompts
    aivf pipeline run-pipeline    # Run full pipeline
    aivf pipeline login-snapgen   # Open browser for login
    aivf pipeline wizard          # Interactive wizard
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

from app.core.config import get_settings

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
vault_app = typer.Typer(name="vault", help="Account vault - browser profile management")
pipeline_app = typer.Typer(name="pipeline", help="Standalone pipeline commands (no API server needed)")

app.add_typer(project_app, name="project")
app.add_typer(queue_app, name="queue")
app.add_typer(account_app, name="account")
app.add_typer(provider_app, name="provider")
app.add_typer(vault_app, name="vault")
app.add_typer(pipeline_app, name="pipeline")

console = Console()


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------


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

    # Projects
    def create_project(self, name, niche, topic, duration, description):
        return self._post("/api/projects", {
            "name": name, "niche": niche, "topic": topic,
            "target_seconds": duration, "description": description,
        })

    def list_projects(self):
        return self._get("/api/projects")

    def project_status(self, project_id):
        return self._get(f"/api/projects/{project_id}")

    def start_project(self, project_id):
        return self._post(f"/api/projects/{project_id}/start")

    def pause_project(self, project_id):
        return self._post(f"/api/projects/{project_id}/pause")

    def resume_project(self, project_id):
        return self._post(f"/api/projects/{project_id}/resume")

    def cancel_project(self, project_id):
        return self._post(f"/api/projects/{project_id}/cancel")

    # Queue
    def list_jobs(self, status=None, limit=50):
        params = {"limit": limit}
        if status:
            params["status"] = status
        return self._get("/api/queue/jobs", params=params)

    def get_job(self, job_id):
        return self._get(f"/api/queue/jobs/{job_id}")

    def retry_job(self, job_id):
        return self._post(f"/api/queue/jobs/{job_id}/retry")

    def skip_scene(self, job_id):
        return self._post(f"/api/queue/jobs/{job_id}/skip")

    # Accounts
    def list_accounts(self):
        return self._get("/api/accounts")

    def get_account(self, account_id):
        return self._get(f"/api/accounts/{account_id}")

    # Provider
    def get_provider_status(self):
        return self._get("/api/provider/status")

    def get_capabilities(self):
        return self._get("/api/provider/capabilities")

    def get_quota(self):
        return self._get("/api/provider/quota")

    def health_check(self):
        return self._get("/api/provider/health")


def get_client(api_url: str = "http://localhost:8890") -> APIClient:
    return APIClient(base_url=api_url)


# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------


@project_app.command("create")
def project_create(
    name: str = typer.Option(..., "--name", "-n", help="Project name"),
    niche: str = typer.Option("horror", "--niche", help="Niche key"),
    topic: str = typer.Option(..., "--topic", "-t", help="Story topic"),
    duration: int = typer.Option(600, "--duration", "-d", help="Target duration in seconds"),
    description: str = typer.Option("", "--description", "-D", help="Optional description"),
    api_url: str = typer.Option("http://localhost:8890", "--api-url", "-u"),
):
    """Create a new video generation project."""
    client = get_client(api_url)
    try:
        result = client.create_project(name, niche, topic, duration, description)
        console.print(Panel(
            f"[green]Project created successfully![/green]\n\n"
            f"  ID: {result['id']}\n"
            f"  Name: {result['name']}\n"
            f"  Status: {result['status']}\n"
            f"  Created: {result['created_at']}",
            title="New Project",
        ))
        console.print(f"\nTo start generation: [cyan]aivf project start {result['id']}[/cyan]")
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")
    except Exception as e:
        console.print(f"[red]Error connecting to API: {e}[/red]")
        console.print("[yellow]Make sure the API server is running: aivf serve[/yellow]")


# ---------------------------------------------------------------------------
# Vault commands
# ---------------------------------------------------------------------------


@vault_app.command("create-account")
def vault_create_account(
    label: str = typer.Option(..., "--label", "-l", help="Human-readable account label"),
):
    """Create a new account slot in the vault."""
    from app.providers.vault import AccountVault
    vault = AccountVault()
    account = vault.create_account(label=label)
    console.print(Panel(
        f"[green]Account created:[/green]\n\n"
        f"  ID: [cyan]{account.id}[/cyan]\n"
        f"  Label: {label}\n"
        f"  Profile: {account.profile_dir}\n"
        f"  Status: [yellow]needs_login[/yellow]\n\n"
        f"Next: [cyan]aivf vault open-login --id {account.id}[/cyan]",
        title="Account Created",
    ))


@vault_app.command("list-accounts")
def vault_list_accounts():
    """List all accounts in the vault."""
    from app.providers.vault import AccountVault
    vault = AccountVault()
    accounts = vault.list_accounts()

    if not accounts:
        console.print("[dim]No accounts in vault. Create one with: aivf vault create-account[/dim]")
        return

    table = Table(title="Account Vault")
    table.add_column("ID", style="cyan")
    table.add_column("Label", style="white")
    table.add_column("Profile", style="dim")
    table.add_column("Status", style="yellow")
    table.add_column("Created", style="dim")

    for acc in accounts:
        status_style = {
            "needs_login": "red",
            "authenticated": "green",
            "expired": "yellow",
            "blocked": "red",
        }.get(acc["login_status"], "white")

        table.add_row(
            acc["id"],
            acc["label"],
            acc["profile_dir"],
            f"[{status_style}]{acc['login_status']}[/{status_style}]",
            acc["created_at"][:10],
        )

    console.print(table)
    console.print(
        f"\n[dim]Total: {len(accounts)} accounts | "
        f"Authenticated: {vault.authenticated_count()}[/dim]"
    )


@vault_app.command("open-login")
def vault_open_login(
    account_id: str = typer.Option(..., "--id", "-i", help="Account ID to open login browser for"),
    visible: bool = typer.Option(True, "--visible/--headless", help="Show browser window"),
):
    """Open a browser for manual Google OAuth login to an account."""
    from app.providers.vault import AccountVault
    vault = AccountVault()
    try:
        account = vault.get_account(account_id)
        if account is None:
            console.print(f"[red]Account not found: {account_id}[/red]")
            return

        console.print(Panel(
            f"[cyan]Opening browser for account: {account.label}[/cyan]\n\n"
            f"  ID: {account_id}\n"
            f"  Profile: {account.profile_dir}\n\n"
            f"[yellow]LOGIN INSTRUCTIONS:[/yellow]\n"
            f"  1. Go to https://snapgen.ai\n"
            f"  2. Click Login, then Sign in with Google\n"
            f"  3. Complete Google OAuth flow\n"
            f"  4. Close the browser when done\n\n"
            f"Then run: [cyan]aivf vault mark-logged-in --id {account_id}[/cyan]",
            title="SnapGen Login",
            border_style="yellow",
        ))

        session = vault.open_login_browser(account_id, visible=visible)
        console.print(
            f"[green]Browser opened for {account_id}[/green] - "
            f"login with Google, then close window and mark as logged in."
        )
    except Exception as exc:
        console.print(f"[red]Error opening login browser: {exc}[/red]")


@vault_app.command("mark-logged-in")
def vault_mark_logged_in(
    account_id: str = typer.Option(..., "--id", "-i", help="Account ID to mark as logged in"),
):
    """Mark an account as authenticated after manual login."""
    from app.providers.vault import AccountVault
    vault = AccountVault()
    try:
        account = vault.mark_logged_in(account_id)
        console.print(Panel(
            f"[green]Account marked as logged in:[/green]\n\n"
            f"  ID: [cyan]{account.id}[/cyan]\n"
            f"  Label: {account.label}\n"
            f"  Profile: {account.profile_dir}\n"
            f"  Status: [green]authenticated[/green]\n\n"
            f"The browser profile is saved. Future sessions will auto-login.",
            title="Logged In",
            border_style="green",
        ))
    except Exception as exc:
        console.print(f"[red]Error marking account as logged in: {exc}[/red]")


@vault_app.command("remove-account")
def vault_remove_account(
    account_id: str = typer.Option(..., "--id", "-i", help="Account ID to remove"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove an account and its browser profile."""
    if not yes:
        confirm = typer.confirm(
            f"Remove account {account_id} and delete its profile?",
        )
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            return

    from app.providers.vault import AccountVault
    vault = AccountVault()
    try:
        removed = vault.remove_account(account_id)
        if removed:
            console.print(f"[green]Account {account_id} removed.[/green]")
        else:
            console.print(f"[red]Account not found: {account_id}[/red]")
    except Exception as exc:
        console.print(f"[red]Error removing account: {exc}[/red]")


@vault_app.command("status")
def vault_status():
    """Show vault status summary."""
    from app.providers.vault import AccountVault
    vault = AccountVault()
    accounts = vault.list_accounts()

    table = Table(title="Vault Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Total accounts", str(len(accounts)))
    table.add_row("Authenticated", str(vault.authenticated_count()))
    table.add_row("Needs login", str(len([a for a in accounts if a["login_status"] == "needs_login"])))
    table.add_row("Expired", str(len([a for a in accounts if a["login_status"] == "expired"])))

    console.print(table)

    if accounts:
        console.print("\n[bold]Accounts:[/bold]")
        for acc in accounts:
            status_icon = {
                "needs_login": "[red]O[/red]",
                "authenticated": "[green]●[/green]",
                "expired": "[yellow]◐[/yellow]",
                "blocked": "[red]✗[/red]",
            }.get(acc["login_status"], "?")
            console.print(
                f"  {status_icon} {acc['id']} - {acc['label']} "
                f"({acc['login_status']})"
            )


# ---------------------------------------------------------------------------
# Pipeline commands
# ---------------------------------------------------------------------------


@pipeline_app.command("generate-story")
def pipeline_generate_story(
    topic: str = typer.Option(..., "--topic", "-t", help="Story topic / premise"),
    niche: str = typer.Option("pinoy_drama", "--niche", help="Niche key (e.g. pinoy_drama, horror)"),
    duration: int = typer.Option(396, "--duration", "-d", help="Target video duration in seconds"),
    output: str = typer.Option("story.json", "--output", "-o", help="Output file path"),
):
    """Generate a story from a topic and niche."""
    from app.story.engine import get_story_engine
    from app.story.models import save_story

    engine = get_story_engine(niche)
    story = engine.generate_story(topic, niche, duration)
    save_story(story, output)
    console.print(Panel(
        f"[green]Story generated:[/green]\n\n"
        f"  Topic: {topic}\n"
        f"  Niche: {niche}\n"
        f"  Duration: {duration}s\n"
        f"  Scenes: {story.total_scenes}\n"
        f"  Acts: {len(story.acts)}\n"
        f"  Saved: {output}",
        title="Story Generated",
    ))


@pipeline_app.command("compile-prompts")
def pipeline_compile_prompts(
    story_path: str = typer.Option("story.json", "--story", "-s", help="Story JSON file"),
    output: str = typer.Option("prompts.json", "--output", "-o", help="Output file path"),
    provider: str = typer.Option("snapgen-pool", "--provider", "-p", help="Provider key"),
):
    """Compile prompts for a story."""
    from app.story.models import load_story
    from app.providers.registry import create_provider
    from app.prompts.compiler import SnapGenPromptAdapter, PromptCompiler

    story = load_story(story_path)
    provider_obj = create_provider(provider)
    adapter = SnapGenPromptAdapter()
    compiler = PromptCompiler(provider="snapgen", adapter=adapter)
    prompts = compiler.compile(story.all_scenes)

    import json

    with open(output, "w") as f:
        json.dump([{
            "scene_id": p.scene_id,
            "scene_number": p.scene_number,
            "provider": p.provider,
            "prompt_text": p.prompt_text,
            "version": p.version,
            "metadata": p.metadata,
            "created_at": p.created_at,
        } for p in prompts], f, indent=2)

    console.print(Panel(
        f"[green]Prompts compiled:[/green]\n\n"
        f"  Scenes: {len(prompts)}\n"
        f"  Provider: {provider}\n"
        f"  Saved: {output}",
        title="Prompts Compiled",
    ))


@pipeline_app.command("run-pipeline")
def pipeline_run_pipeline(
    topic: str = typer.Option(..., "--topic", "-t", help="Story topic / premise"),
    niche: str = typer.Option("pinoy_drama", "--niche", help="Niche key"),
    duration: int = typer.Option(396, "--duration", "-d", help="Target video duration in seconds"),
    clip: float = typer.Option(6.0, "--clip", "-c", help="Clip duration in seconds"),
    provider: str = typer.Option("snapgen-pool", "--provider", "-p", help="Provider key (e.g. snapgen-pool, mock)"),
    output: str = typer.Option("output", "--output-dir", "-o", help="Output directory"),
):
    """Run the full video generation pipeline."""
    from app.story.engine import get_story_engine
    from app.providers.registry import create_provider
    from app.prompts.compiler import SnapGenPromptAdapter, PromptCompiler
    from app.assembly import VideoAssembler, AssemblyInput

    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel(
        f"[cyan]Pipeline starting...[/cyan]\n"
        f"Topic: {topic} | Niche: {niche} | Duration: {duration}s | Clip: {clip}s | Provider: {provider}",
        title="AI Video Factory",
    ))

    # Step 1: Generate story
    console.print("\n[step 1/5] Generating story...")
    engine = get_story_engine(niche)
    story = engine.generate_story(topic, niche, duration)
    story_path = output_dir / "story.json"
    story_path.write_text(story.model_dump_json())
    console.print(f"[green]Story: {story.total_scenes} scenes, {len(story.acts)} acts[/green]")

    # Step 2: Compile prompts
    console.print("\n[step 2/5] Compiling prompts...")
    provider_instance = create_provider(provider)
    adapter = SnapGenPromptAdapter()
    compiler = PromptCompiler(adapter=adapter)
    prompts = compiler.compile(story.all_scenes, story=story)
    prompts_path = output_dir / "prompts.json"
    import json
    prompts_list = prompts if isinstance(prompts, list) else [prompts]
    with open(str(prompts_path), "w") as f:
        json.dump([{
            "scene_id": p.scene_id,
            "scene_number": p.scene_number,
            "provider": p.provider,
            "prompt_text": p.prompt_text,
            "version": p.version,
            "metadata": p.metadata,
            "created_at": p.created_at,
        } for p in prompts_list], f, indent=2)
    console.print(f"[green]Prompts: {len(prompts_list)} prompts compiled[/green]")

    # Step 3-5: Submit, poll, download
    console.print(f"\n[step 3/5] Submitting to {provider}...")
    console.print(f"[yellow]NOTE: This will use real SnapGen quota if provider is not 'mock'.[/yellow]")
    console.print(f"  {len(prompts_list)} clips x {clip}s = {len(prompts_list) * clip}s total")

    clip_dir = output_dir / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for i, prompt in enumerate(prompts_list):
        console.print(f"  [{i+1}/{len(prompts_list)}] Generating clip {prompt.scene_number}...")
        try:
            metadata = dict(prompt.metadata)
            metadata["target_clip_seconds"] = clip
            result = provider_instance.submit_generation(prompt.text, metadata)
            if result.success:
                clip_path = clip_dir / f"clip_{prompt.scene_number:03d}.mp4"
                if hasattr(provider_instance, 'download_result'):
                    data = provider_instance.download_result(result.result_id)
                    clip_path.write_bytes(data)
                elif hasattr(provider_instance, '_save_clip'):
                    provider_instance._save_clip(result.result_id, str(clip_path))
                else:
                    console.print(f"[yellow]  No download method for {provider}[/yellow]")
                status = "completed"
            else:
                status = "failed"
                console.print(f"  [red]  Failed: {result.error_code or result.error_message}[/red]")
            results.append({"status": status, "scene_number": prompt.scene_number})
        except Exception as exc:
            results.append({"status": "error", "scene_number": prompt.scene_number, "error": str(exc)})
            console.print(f"  [red]  Error: {exc}[/red]")

    completed = sum(1 for r in results if r.get("status") in ("completed", "success"))
    failed = sum(1 for r in results if r.get("status") in ("failed", "error"))
    console.print(f"\n[green]Pipeline complete: {completed} succeeded, {failed} failed[/green]")

    # Assemble
    if completed > 0:
        console.print("\n[step 5/5] Assembling final video...")
        clip_paths = sorted(clip_dir.glob("*.mp4"))
        if not clip_paths:
            console.print("[yellow]No clips found for assembly.[/yellow]")
        else:
            from app.assembly import AssemblyConfig
            assembler = VideoAssembler(
                config=AssemblyConfig(
                    output_dir=str(output_dir / "final"),
                    target_resolution=(1080, 1920),  # 9:16 vertical for FB Reels
                    crossfade_duration=0.0,           # hard cuts for continuous shot
                )
            )
            input_data = AssemblyInput(clips=clip_paths)
            result = assembler.assemble(input_data)
            if result.success and result.output_path:
                console.print(f"[green]Final video:[/green] [cyan]{result.output_path}[/cyan]")
                console.print(f"[dim]Duration: {result.duration_seconds:.1f}s | Size: {result.file_size_bytes/1024:.0f} KB[/dim]")
            else:
                console.print(f"[red]Assembly failed: {result.error_message}[/red]")


@pipeline_app.command("wizard")
def pipeline_wizard():
    """Interactive wizard to configure and run a pipeline."""
    from rich.prompt import Prompt, Confirm, IntPrompt

    console.print(Panel(
        "[cyan]AI Video Factory - Pipeline Wizard[/cyan]\n\n"
        "Walk through each step to configure your video generation.",
        title="Wizard",
    ))

    # Step 1: Topic
    topic = Prompt.ask("Enter story topic / premise", default="Pinoy drama short")
    console.print(f"[green]Topic:[/green] {topic}")

    # Step 2: Niche
    niches = ["pinoy_drama", "horror", "romance", "comedy", "action"]
    console.print(f"\nNiches available: {niches}")
    niche = Prompt.ask("Select niche", choices=niches, default="pinoy_drama")
    console.print(f"[green]Niche:[/green] {niche}")

    # Step 3: Duration
    duration = IntPrompt.ask("Target video duration (seconds)", default=396)
    console.print(f"[green]Duration:[/green] {duration}s")

    # Step 4: Clip length
    clip = IntPrompt.ask("Clip duration (seconds)", default=6)
    console.print(f"[green]Clip:[/green] {clip}s")

    # Step 5: Provider
    providers = ["mock", "snapgen-pool"]
    provider = Prompt.ask("Select provider", choices=providers, default="mock")
    console.print(f"[green]Provider:[/green] {provider}")

    if provider == "snapgen-pool":
        from app.providers.vault import AccountVault
        vault = AccountVault()
        auth_count = vault.authenticated_count()
        if auth_count == 0:
            console.print("[red]No authenticated accounts in vault.[/red]")
            console.print("Create accounts: [cyan]aivf vault create-account --label user1[/cyan]")
            console.print("Then login: [cyan]aivf vault open-login --id <id>[/cyan]")
            if not Confirm.ask("Continue with 0 authenticated accounts? (generations will fail)"):
                raise typer.Exit(0)

    # Step 6: Output dir
    output = Prompt.ask("Output directory", default="output")
    console.print(f"[green]Output:[/green] {output}")

    # Confirm
    console.print()
    console.print(Panel(
        f"[cyan]Summary:[/cyan]\n"
        f"Topic: {topic}\n"
        f"Niche: {niche}\n"
        f"Duration: {duration}s\n"
        f"Clip: {clip}s\n"
        f"Provider: {provider}\n"
        f"Output: {output}",
    ))
    if not Confirm.ask("Run pipeline?"):
        console.print("[yellow]Cancelled.[/yellow]")
        raise typer.Exit(0)

    # Run
    console.print("\n[yellow]Starting pipeline...[/yellow]")
    import subprocess
    import shlex

    cmd = [
        typer.main.get_command().info.name or "aivf",
        "pipeline", "run-pipeline",
        "--topic", topic,
        "--niche", niche,
        "--duration", str(duration),
        "--clip", str(clip),
        "--provider", provider,
        "--output-dir", output,
    ]
    console.print(f"[dim]{' '.join(shlex.quote(a) for a in cmd)}[/dim]")
    result = subprocess.run(cmd)
    raise typer.Exit(result.returncode)


@pipeline_app.command("login-snapgen")
def pipeline_login_snapgen(
    headless: bool = typer.Option(False, "--headless", "-H", help="Run browser in headless mode"),
):
    """Open a Chromium browser for manual SnapGen login."""
    from app.providers.browser_session import BrowserSession

    session = BrowserSession(
        headless=False,
        user_data_dir=Path.home() / ".snapgen-browser-profile",
    )
    try:
        session.launch()
        session.navigate("https://snapgen.ai/app/video-gen")
        console.print(Panel(
            f"[cyan]Browser opened for SnapGen login[/cyan]\n\n"
            f"  URL: https://snapgen.ai/app/video-gen\n"
            f"  Login: Click [bold]Login[/bold], then [bold]Sign in with Google[/bold]\n"
            f"  Close this window when done.\n\n"
            f"Credentials saved to: [dim]{session._user_data_dir}[/dim]",
            title="SnapGen Login",
            border_style="yellow",
        ))
        console.print("[yellow]Press Enter to close the browser...[/yellow]")
        input()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


@app.command()
def main() -> None:
    """Entry point for `aivf` CLI (also callable programmatically)."""
    app()


if __name__ == "__main__":
    main()
