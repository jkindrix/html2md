"""Crawl-state CLI command group."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from html2md.markdown.crawler import crawl_website
from html2md.utils.state_manager import StateManager


console = Console()
state_app = typer.Typer(
    help="Manage crawl state and resume interrupted crawls.",
    add_completion=False,
)


@state_app.command(name="list")
def list_states():
    """List all resumable crawl states."""
    crawls = StateManager().list_resumable_crawls()
    if not crawls:
        console.print("[yellow]No resumable crawls found.[/yellow]")
        return

    table = Table(title="Resumable Crawls", show_header=True, header_style="bold blue")
    for label, style in (
        ("ID", "cyan"),
        ("URL", "green"),
        ("Created", "yellow"),
        ("Last Checkpoint", "yellow"),
        ("Progress", "magenta"),
    ):
        table.add_column(label, style=style)
    for crawl in crawls:
        progress = f"{crawl['urls_processed']}/{crawl['urls_processed'] + crawl['urls_queued']}"
        table.add_row(
            crawl["crawl_id"][:8],
            crawl["start_url"],
            crawl["created_at"][:19],
            crawl["last_checkpoint"][:19],
            progress,
        )
    console.print(table)


@state_app.command(name="resume")
def resume_crawl(
    crawl_id: str = typer.Argument(..., help="ID of the crawl to resume"),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir", "-o", help="Override output directory"
    ),
):
    """Resume an interrupted crawl."""
    state_manager = StateManager()
    crawl_state = state_manager.load_state(crawl_id)
    if not crawl_state:
        console.print(f"[red]Crawl {crawl_id} not found.[/red]")
        raise typer.Exit(1)
    if output_dir:
        crawl_state.output_dir = output_dir

    console.print(f"[green]Resuming crawl {crawl_id}[/green]")
    try:
        resume_options = dict(crawl_state.config)
        for explicit_option in (
            "start_url",
            "output_dir",
            "state_manager",
            "resume_crawl_id",
            "scope_url",
        ):
            resume_options.pop(explicit_option, None)
        with state_manager.signal_handling():
            result = crawl_website(
                start_url=crawl_state.start_url,
                output_dir=crawl_state.output_dir,
                state_manager=state_manager,
                resume_crawl_id=crawl_id,
                **resume_options,
            )
        if not result.success:
            console.print(f"[red]Crawl resume failed: {result.error}[/red]")
            raise typer.Exit(1)
        console.print("[green]✓ Crawl resumed successfully![/green]")
        console.print(
            f"[blue]Final count:[/blue] {result.processed_count} URLs processed"
        )
    except typer.Exit:
        raise
    except Exception as error:
        console.print(f"[red]Error resuming crawl: {error}[/red]")
        raise typer.Exit(1) from error


@state_app.command(name="clean")
def clean_states(
    days: int = typer.Option(
        30, "--days", "-d", help="Remove states older than N days"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Clean up old crawl states."""
    if not force and not Confirm.ask(f"Remove crawl states older than {days} days?"):
        console.print("[yellow]Cancelled.[/yellow]")
        return
    cleaned = StateManager().clean_old_states(days)
    console.print(f"[green]Cleaned {cleaned} old state files.[/green]")


@state_app.command(name="export")
def export_state(
    crawl_id: str = typer.Argument(..., help="ID of the crawl to export"),
    output_file: Path = typer.Argument(..., help="Output file for exported state"),
):
    """Export a crawl state to a file."""
    try:
        StateManager().export_state(crawl_id, output_file)
        console.print(f"[green]✓ State exported to {output_file}[/green]")
    except Exception as error:
        console.print(f"[red]Error exporting state: {error}[/red]")


@state_app.command(name="import")
def import_state(input_file: Path = typer.Argument(..., help="State file to import")):
    """Import a crawl state from a file."""
    try:
        crawl_id = StateManager().import_state(input_file)
        console.print(f"[green]✓ State imported with ID: {crawl_id}[/green]")
    except Exception as error:
        console.print(f"[red]Error importing state: {error}[/red]")


@state_app.command(name="info")
def show_state_info(
    crawl_id: str = typer.Argument(..., help="ID of the crawl to show info for")
):
    """Show detailed information about a crawl state."""
    crawl_state = StateManager().load_state(crawl_id)
    if not crawl_state:
        console.print(f"[red]Crawl {crawl_id} not found.[/red]")
        return

    table = Table(title=f"Crawl State: {crawl_id}", show_header=False)
    table.add_column("Property", style="cyan", width=20)
    table.add_column("Value", style="green")
    for label, value in (
        ("ID", crawl_state.crawl_id),
        ("Start URL", crawl_state.start_url),
        ("Output Dir", crawl_state.output_dir),
        ("Created", crawl_state.created_at),
        ("Last Checkpoint", crawl_state.last_checkpoint),
        ("URLs Processed", crawl_state.statistics.urls_processed),
        ("URLs Failed", crawl_state.statistics.urls_failed),
        ("URLs Queued", len(crawl_state.urls_queued)),
        ("Checkpoints", len(crawl_state.checkpoints)),
    ):
        table.add_row(label, str(value))
    console.print(table)
