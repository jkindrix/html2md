"""
Modern CLI for html2md using Typer and Rich for a beautiful user experience.
"""

import glob
import json
import logging
import os
from enum import Enum
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

from html2md.config.loader import (
    CONFIG_FILE,
    DEFAULT_CONFIG,
    load_config,
)
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

# Create config subcommand app
config_app = typer.Typer(
    help="Manage html2md configuration settings.",
    add_completion=False,
)

# Add config app as a subcommand
app.add_typer(config_app, name="config")


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
            else:
                # Handle empty result case
                progress.stop()
                console.print(
                    Panel(
                        f"[bold red]Unable to retrieve content from:[/bold red] {source}",
                        title="Error",
                        border_style="red",
                    )
                )
                console.print("[yellow]Possible causes:[/yellow]")
                console.print("• The website may require authentication")
                console.print("• The website may be blocking automated requests")
                console.print("• There may be network connectivity issues")
                console.print("• The website may be returning an empty response")
                console.print(
                    "\n[blue]Try using the --no-cookies flag if you're having login issues[/blue]"
                )
                progress.start()
                progress.update(
                    task_id, description=f"❌ Failed to retrieve content from {source}"
                )
                return False
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


# Configuration management commands
@config_app.command(name="show")
def show_config():
    """Display the current configuration."""
    config = load_config()
    config_path = CONFIG_FILE

    # Display config path
    console.print(f"[bold blue]Configuration file:[/bold blue] {config_path}")

    # Display config as syntax-highlighted JSON
    json_str = json.dumps(config, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)

    console.print(Panel(syntax, title="Current Configuration", border_style="green"))


@config_app.command(name="path")
def show_config_path():
    """Show the path to the configuration file."""
    console.print(f"[bold green]Configuration file:[/bold green] {CONFIG_FILE}")


@config_app.command(name="set")
def set_config_value(
    path: str = typer.Argument(
        ..., help="Config path (e.g., 'domains.example.com.footer_marker')"
    ),
    value: str = typer.Argument(..., help="Value to set"),
):
    """Set a configuration value at the specified path."""
    config = load_config()

    # Split the path into components
    components = path.split(".")

    # Navigate to the destination
    current = config
    for i, component in enumerate(components[:-1]):
        if component not in current:
            # Create missing dictionaries along the path
            current[component] = {}
        elif not isinstance(current[component], dict):
            console.print(
                f"[bold red]Error:[/bold red] '{'.'.join(components[:i+1])}' is not a dictionary"
            )
            return
        current = current[component]

    # Set the value (convert to appropriate type if possible)
    last_component = components[-1]
    try:
        # Try to parse as JSON
        parsed_value = json.loads(value)
        current[last_component] = parsed_value
    except json.JSONDecodeError:
        # If not valid JSON, use as string
        current[last_component] = value

    # Save the updated config
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

    console.print(f"[bold green]Updated:[/bold green] {path} = {value}")

    if components[0] == "domains":
        console.print(
            "\n[bold blue]Tip:[/bold blue] You've updated domain-specific trimming rules."
        )
        console.print(
            "These rules determine how HTML content is trimmed when converted to markdown."
        )


@config_app.command(name="get")
def get_config_value(
    path: str = typer.Argument(
        ..., help="Config path (e.g., 'domains.example.com.footer_marker')"
    ),
):
    """Get a configuration value at the specified path."""
    config = load_config()

    # Split the path into components
    components = path.split(".")

    # Navigate to the destination
    current = config
    for i, component in enumerate(components):
        if component not in current:
            console.print(
                f"[bold red]Error:[/bold red] Path '{path}' not found in configuration"
            )
            return
        elif i < len(components) - 1 and not isinstance(current[component], dict):
            console.print(
                f"[bold red]Error:[/bold red] '{'.'.join(components[:i+1])}' is not a dictionary"
            )
            return
        current = current[component]

    # Display the value
    json_str = json.dumps(current, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai")

    console.print(f"[bold blue]{path}:[/bold blue]")
    console.print(syntax)


@config_app.command(name="delete")
def delete_config_value(
    path: str = typer.Argument(
        ..., help="Config path to delete (e.g., 'domains.example.com')"
    ),
):
    """Delete a configuration value at the specified path."""
    config = load_config()

    # Split the path into components
    components = path.split(".")

    # Navigate to the parent
    current = config
    for i, component in enumerate(components[:-1]):
        if component not in current:
            console.print(
                f"[bold red]Error:[/bold red] Path '{path}' not found in configuration"
            )
            return
        elif not isinstance(current[component], dict):
            console.print(
                f"[bold red]Error:[/bold red] '{'.'.join(components[:i+1])}' is not a dictionary"
            )
            return
        current = current[component]

    # Delete the value
    last_component = components[-1]
    if last_component not in current:
        console.print(
            f"[bold red]Error:[/bold red] Path '{path}' not found in configuration"
        )
        return

    if Confirm.ask(f"Are you sure you want to delete '{path}'?"):
        deleted_value = current[last_component]
        del current[last_component]

        # Save the updated config
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

        console.print(f"[bold green]Deleted:[/bold green] {path}")
        console.print("[dim]Previous value was:[/dim]")
        json_str = json.dumps(deleted_value, indent=2)
        syntax = Syntax(json_str, "json", theme="monokai")
        console.print(syntax)


@config_app.command(name="add-domain")
def add_domain_config():
    """Interactive wizard to add domain-specific configuration."""
    config = load_config()

    # Domain name
    domain = Prompt.ask("[bold blue]Enter domain name[/bold blue] (e.g., example.com)")

    # Check if domain already exists
    if domain in config.get("domains", {}):
        if not Confirm.ask(
            f"Domain '{domain}' already exists. Do you want to update it?"
        ):
            return

    # Initialize domain config if it doesn't exist
    if "domains" not in config:
        config["domains"] = {}
    if domain not in config["domains"]:
        config["domains"][domain] = {}

    # Ask for footer marker
    if Confirm.ask(
        "Do you want to set a footer marker? (text that indicates where to trim content)"
    ):
        footer_marker = Prompt.ask("[bold blue]Enter footer marker text[/bold blue]")
        config["domains"][domain]["footer_marker"] = footer_marker

    # Ask for path-specific rules
    if Confirm.ask("Do you want to add path-specific rules?"):
        while True:
            path = Prompt.ask("[bold blue]Enter URL path[/bold blue] (e.g., /docs)")

            h1_occurrence = Prompt.ask(
                "[bold blue]Enter h1 occurrence to keep[/bold blue] (e.g., 2 means keep the 2nd h1 heading)",
                default="1",
            )

            path_footer = Prompt.ask(
                "[bold blue]Enter path-specific footer marker[/bold blue]", default=""
            )

            # Initialize path rules if they don't exist
            if "path_rules" not in config["domains"][domain]:
                config["domains"][domain]["path_rules"] = {}

            # Add path rule
            config["domains"][domain]["path_rules"][path] = {
                "h1_occurrence": int(h1_occurrence)
            }

            if path_footer:
                config["domains"][domain]["path_rules"][path][
                    "footer_marker"
                ] = path_footer

            if not Confirm.ask("Add another path rule?"):
                break

    # Save the config
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

    # Show the updated domain config
    domain_config = config["domains"][domain]
    json_str = json.dumps({domain: domain_config}, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai")

    console.print("\n[bold green]Domain configuration added:[/bold green]")
    console.print(syntax)
    console.print(
        "\n[bold blue]Tip:[/bold blue] This configuration will be used when converting HTML from this domain."
    )


@config_app.command(name="list-domains")
def list_domains():
    """List all configured domains with their settings."""
    config = load_config()

    if "domains" not in config or not config["domains"]:
        console.print("[yellow]No domains configured yet.[/yellow]")
        console.print(
            "Use [bold]html2md config add-domain[/bold] to add domain configurations."
        )
        return

    # Create a table
    table = Table(title="Configured Domains")
    table.add_column("Domain", style="cyan")
    table.add_column("Footer Marker", style="green")
    table.add_column("Path Rules", style="magenta")

    # Add rows for each domain
    for domain, settings in config["domains"].items():
        footer = settings.get("footer_marker", "")

        path_rules_count = len(settings.get("path_rules", {}))
        path_rules = f"{path_rules_count} path rule(s)" if path_rules_count > 0 else ""

        table.add_row(domain, footer, path_rules)

    console.print(table)


@config_app.command(name="reset")
def reset_config():
    """Reset the configuration to default values."""
    if not Confirm.ask(
        "[bold red]Warning:[/bold red] This will reset all settings to default values. Continue?"
    ):
        return

    # Write default config
    CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")

    console.print("[bold green]Configuration reset to default values.[/bold green]")

    # Show the reset config
    json_str = json.dumps(DEFAULT_CONFIG, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)

    console.print(Panel(syntax, title="Default Configuration", border_style="yellow"))


def entry_point():
    """Entry point for the CLI."""
    app()
