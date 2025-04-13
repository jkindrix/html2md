"""
Modern CLI for html2md using Typer and Rich for a beautiful user experience.
"""

import glob
import logging
import os
from enum import Enum
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn
from rich.table import Table

from html2md.cookies.session_manager import get_session
from html2md.markdown.batch_processor import build_headers, process_markdown_links
from html2md.markdown.converter import html_to_markdown, local_html_to_markdown
from html2md.utils.logger import setup_logging
from html2md.utils.parser import is_url

# Configure logger to use a file instead of stdout
logger = setup_logging(console_output=False)

# Create Rich console for beautiful output
console = Console()

# Create Typer app
app = typer.Typer(
    help="Convert HTML content from URLs or local files to Markdown with beautiful output.",
    add_completion=False,
)


class LogLevel(str, Enum):
    """Log levels for the application."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def set_log_level(level: LogLevel) -> None:
    """Set the logging level."""
    logger.setLevel(getattr(logging, level))


def process_single_with_progress(
    source: str,
    trim: bool,
    output: Optional[Path],
    no_cookies: bool,
    local: bool,
    progress: Progress,
    task_id: TaskID,
) -> bool:
    """Process a single URL or file with progress tracking."""
    progress.update(task_id, description=f"Processing {source}")

    if is_url(source, local):
        # Process as URL
        headers = build_headers(source)
        logger.info(f"Processing URL: {source}")

        try:
            # Subtasks for fetching and converting
            progress.update(task_id, description=f"Fetching content from {source}")

            # Create a new session for each URL if cookies are not disabled
            session = get_session() if not no_cookies else None

            # Process URL with session and headers
            markdown_result = html_to_markdown(
                source, session=session, headers=headers, trim=trim
            )

            progress.update(task_id, description=f"Converting {source} to markdown")

            if markdown_result:
                if output:
                    # Save to file
                    progress.update(task_id, description=f"Saving to {output}")
                    with open(output, "w", encoding="utf-8") as f:
                        f.write(markdown_result)
                    logger.info(f"Successfully processed URL: {source}")
                else:
                    # Print to console
                    progress.stop()
                    console.print(Panel.fit(f"# URL: {source}", title="Source"))
                    console.print(markdown_result)
                    progress.start()
                    logger.info(f"Successfully processed URL: {source}")

                progress.update(task_id, description=f"✅ Completed {source}")
                return True
        except Exception as e:
            logger.error(f"Failed to process URL {source}: {e}")
            progress.update(task_id, description=f"❌ Failed {source} ({str(e)})")
            return False
    else:
        # Process as local file
        logger.info(f"Processing local file: {source}")

        try:
            # Expand to absolute path if needed
            file_path = os.path.abspath(os.path.expanduser(source))
            progress.update(task_id, description=f"Reading local file {file_path}")

            # Process local file
            markdown_result = local_html_to_markdown(file_path, trim=trim)

            progress.update(task_id, description=f"Converting {file_path} to markdown")

            if markdown_result:
                if output:
                    # Save to file
                    progress.update(task_id, description=f"Saving to {output}")
                    with open(output, "w", encoding="utf-8") as f:
                        f.write(markdown_result)
                    logger.info(f"Successfully processed local file: {file_path}")
                else:
                    # Print to console
                    progress.stop()
                    console.print(Panel.fit(f"# File: {file_path}", title="Source"))
                    console.print(markdown_result)
                    progress.start()
                    logger.info(f"Successfully processed local file: {file_path}")

                progress.update(task_id, description=f"✅ Completed {file_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to process local file {source}: {e}")
            progress.update(task_id, description=f"❌ Failed {source} ({str(e)})")
            return False

    return False


@app.command(name="convert")
def convert_command(
    sources: List[str] = typer.Argument(
        ..., help="URLs or local HTML files to convert."
    ),
    trim: bool = typer.Option(
        True,
        "--trim/--no-trim",
        help="Enable/disable trimming based on domain-specific rules.",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file to save converted markdown."
    ),
    no_cookies: bool = typer.Option(
        False, "--no-cookies", help="Disable loading cookies from the browser."
    ),
    local: bool = typer.Option(
        False,
        "--local",
        help="Force treating sources as local files even if they look like URLs.",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.INFO, "--log-level", help="Set logging level."
    ),
):
    """Convert HTML content from URLs or local files to Markdown."""
    set_log_level(log_level)

    # Display a beautiful header
    console.print(
        Panel.fit(
            "🌐 [bold cyan]html2md[/bold cyan] - HTML to Markdown Converter",
            border_style="cyan",
        )
    )

    # Create a progress display
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}[/bold blue]"),
        BarColumn(),
        TextColumn("[bold]{task.completed}/{task.total}[/bold]"),
        console=console,
    ) as progress:
        # Create a task for each source
        tasks = {
            source: progress.add_task(f"Queued: {source}", total=1)
            for source in sources
        }

        # Process each source
        successes = 0
        for source in sources:
            task_id = tasks[source]
            if process_single_with_progress(
                source, trim, output, no_cookies, local, progress, task_id
            ):
                successes += 1
            progress.update(task_id, completed=1)

    # Show summary
    if len(sources) > 1:
        console.print(
            f"\n✨ [bold green]Completed {successes}/{len(sources)} conversions[/bold green]"
        )


@app.command(name="batch")
def batch_command(
    input_files: List[str] = typer.Argument(
        ..., help="Markdown files containing links to process."
    ),
    output_dir: Path = typer.Option(
        "output",
        "--output-dir",
        "-o",
        help="Directory to save output files and folders.",
    ),
    trim: bool = typer.Option(
        True,
        "--trim/--no-trim",
        help="Enable/disable trimming based on domain-specific rules.",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.INFO, "--log-level", help="Set logging level."
    ),
):
    """Process markdown files with links and create modular output."""
    set_log_level(log_level)

    # Display a beautiful header
    console.print(
        Panel.fit(
            "📚 [bold magenta]html2md batch[/bold magenta] - Markdown Link Processor",
            border_style="magenta",
        )
    )

    # Expand glob patterns
    expanded_files = []
    with console.status("[bold blue]Finding markdown files..."):
        for pattern in input_files:
            matches = glob.glob(os.path.expanduser(pattern))
            if matches:
                expanded_files.extend(matches)
                console.print(
                    f"[green]✓[/green] Found {len(matches)} files matching [bold]{pattern}[/bold]"
                )
            else:
                console.print(
                    f"[yellow]⚠[/yellow] No files found matching [bold]{pattern}[/bold]"
                )

    if not expanded_files:
        console.print("[bold red]❌ No input files found to process.[/bold red]")
        raise typer.Exit(1)

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    console.print(f"[bold blue]Output directory:[/bold blue] {output_dir}")

    # Process files with live progress
    console.print("\n[bold]Starting batch processing...[/bold]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold purple]{task.description}[/bold purple]"),
        BarColumn(),
        TextColumn("[bold]{task.completed}[/bold]"),
        console=console,
    ) as progress:
        task = progress.add_task("Extracting URLs...", total=None)

        try:
            # Create a custom wrapper function to update progress
            def progress_callback(message, url=None, status=None):
                progress.update(task, description=message)

            # Process the files with callback for updates
            processed_count = process_markdown_links(
                expanded_files,
                output_dir,
                trim=trim,
                progress_callback=progress_callback,
            )

            # Set completed state
            progress.update(
                task, description=f"✅ Completed processing {processed_count} URLs"
            )

        except Exception as e:
            logger.error(f"Error during batch processing: {e}")
            progress.update(task, description=f"❌ Error: {str(e)}")
            console.print(
                f"[bold red]Error during batch processing: {str(e)}[/bold red]"
            )
            raise typer.Exit(1)

    # Show summary of processing results
    console.print(
        f"\n✨ [bold green]Successfully processed {processed_count} URLs[/bold green]"
    )

    # Show output directory structure
    console.print("\n[bold blue]Output directory structure:[/bold blue]")

    # Count output files and directories
    file_count = 0
    dir_count = 0

    for root, dirs, files in os.walk(output_dir):
        dir_count += len(dirs)
        file_count += len(files)

    # Create a table to show the structure
    table = Table(show_header=True)
    table.add_column("Type", style="cyan")
    table.add_column("Count", style="green")

    table.add_row("Directories", str(dir_count))
    table.add_row("Files", str(file_count))

    console.print(table)

    console.print(
        f"\n[bold green]Batch processing complete! Output saved to {output_dir}[/bold green]"
    )


@app.callback()
def main(
    log_level: LogLevel = typer.Option(
        LogLevel.INFO, "--log-level", help="Set logging level."
    ),
):
    """Main entry point for the application."""
    set_log_level(log_level)


def entry_point():
    """Entry point for the CLI."""
    app()
