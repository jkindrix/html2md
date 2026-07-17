"""
CLI for html2md using Typer and Rich for a beautiful user experience.
"""

import glob
import logging
import os
import platform
import sys
import time
from enum import Enum
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)
from rich.table import Table
from rich.text import Text

from html2md.config.loader import load_config, save_config
from html2md.markdown.batch_processor import BatchResult, process_markdown_links
from html2md.markdown.content_extractor import (
    ContentExtractionError,
    ContentMode,
    validate_content_request,
)
from html2md.markdown.crawler import crawl_website
from html2md.cli.runtime import build_header_config, build_header_manager
from html2md.cli.state_commands import state_app
from html2md import __version__
from html2md.cli.conversion_presenter import (
    process_single_quiet,
    process_single_with_progress,
)
from html2md.cli.config_commands import config_app
from html2md.cli.presentation import (
    HTML2MD_THEME,
    STATUS_EMOJI,
    EnhancedProgress,
    display_directory_tree,
    show_welcome_banner,
)
from html2md.utils.logger import setup_logging
from html2md.utils.parser import is_url
from html2md.utils.state_manager import StateManager

# Configure logger to use a file instead of stdout
logger = setup_logging(console_output=False)

# Create Rich console with the custom theme
console = Console(theme=HTML2MD_THEME)

# Create Typer app
app = typer.Typer(
    help="Convert HTML content from URLs or local files to Markdown with beautiful output.",
    add_completion=False,
)


def get_cli_default(command: str, option: str, default_value=None):
    """Return a Click-compatible factory that reads config at invocation time."""

    def resolve_default():
        config = load_config()
        cli_defaults = config.get("cli_defaults", {})
        command_defaults = cli_defaults.get(command, {})
        return command_defaults.get(option, default_value)

    return resolve_default


# Add config app as a subcommand
app.add_typer(config_app, name="config")

# Add state app as a subcommand
app.add_typer(state_app, name="state")


class LogLevel(str, Enum):
    """Log levels for the application."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Browser(str, Enum):
    """Supported browsers for cookie extraction."""

    CHROME = "chrome"
    FIREFOX = "firefox"


def set_log_level(level: LogLevel, debug_log: Optional[Path] = None) -> None:
    """Set the logging level and optionally enable debug logging to a file."""
    global logger

    # If debug log is specified, reconfigure the logger
    if debug_log:
        from html2md.utils.logger import setup_logging

        logger = setup_logging(console_output=True, debug_file=str(debug_log))
        logger.info(f"Debug logs will be written to: {debug_log}")

    # Set the log level
    logger.setLevel(getattr(logging, level))


def validate_content_options(mode: ContentMode, selector: Optional[str]) -> None:
    """Turn content-contract mistakes into concise CLI failures."""
    try:
        validate_content_request(mode, selector)
    except ContentExtractionError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise typer.Exit(1) from error


@app.command(name="convert")
def convert_command(
    sources: List[str] = typer.Argument(
        ..., help="URLs or local HTML files to convert."
    ),
    content_mode: ContentMode = typer.Option(
        get_cli_default("convert", "content_mode", ContentMode.FULL.value),
        "--content",
        help="Select full document, inferred main content, or an explicit selector.",
    ),
    selector: Optional[str] = typer.Option(
        get_cli_default("convert", "selector", None),
        "--selector",
        help="CSS selector used only with '--content selector'.",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file to save converted markdown."
    ),
    no_cookies: bool = typer.Option(
        get_cli_default("convert", "no_cookies", False),
        "--no-cookies/--cookies",
        help="Disable loading cookies from the browser.",
    ),
    browser_cookies: bool = typer.Option(
        get_cli_default("convert", "browser_cookies", False),
        "--browser-cookies/--no-browser-cookies",
        help="Use cookies from the local browser to authenticate with websites.",
    ),
    browser: Optional[Browser] = typer.Option(
        get_cli_default("convert", "browser", None),
        "--browser",
        help="Specify which browser to extract cookies from (default: chrome).",
    ),
    cookie_path: Optional[Path] = typer.Option(
        None,
        "--cookie-path",
        help="Path to browser cookies database file (helps with Windows/WSL).",
    ),
    cookie_json: Optional[Path] = typer.Option(
        None,
        "--cookie-json",
        help="Path to JSON file with exported cookies (from browser developer tools).",
    ),
    headers_file: Optional[Path] = typer.Option(
        None,
        "--headers-file",
        help="Owner-only JSON file of request headers for the target site.",
    ),
    storage_state: Optional[Path] = typer.Option(
        None,
        "--storage-state",
        help="Owner-only Playwright storage-state JSON; requires --render-js.",
    ),
    local: bool = typer.Option(
        get_cli_default("convert", "local", False),
        "--local/--auto-detect",
        help="Force treating sources as local files even if they look like URLs.",
    ),
    enhanced_headers: bool = typer.Option(
        get_cli_default("convert", "enhanced_headers", True),
        "--enhanced-headers/--basic-headers",
        help="Use enhanced headers with User-Agent identification and compression support.",
    ),
    user_agent_contact: Optional[str] = typer.Option(
        get_cli_default("convert", "user_agent_contact", None),
        "--user-agent-contact",
        help="Contact email or URL to include in User-Agent header (e.g., 'admin@example.com').",
    ),
    simulate_browser: bool = typer.Option(
        get_cli_default("convert", "simulate_browser", False),
        "--simulate-browser/--identify-crawler",
        help="Use browser-like headers instead of identifying as html2md crawler.",
    ),
    insecure: bool = typer.Option(
        get_cli_default("convert", "insecure", False),
        "--insecure/--secure",
        "--no-verify-ssl",
        help="Disable SSL certificate verification. Only use with hosts you trust "
        "(e.g. internal servers with self-signed certificates).",
    ),
    allow_private_network: bool = typer.Option(
        get_cli_default("convert", "allow_private_network", False),
        "--allow-private-network/--public-network-only",
        help="Allow explicitly trusted private, loopback, or link-local destinations.",
    ),
    download_images: bool = typer.Option(
        get_cli_default("convert", "download_images", False),
        "--download-images/--no-download-images",
        help="Download images from the webpage and store them locally.",
    ),
    images_dir: str = typer.Option(
        get_cli_default("convert", "images_dir", "images"),
        "--images-dir",
        help="Directory name for storing downloaded images.",
    ),
    include_metadata: bool = typer.Option(
        get_cli_default("convert", "metadata", False),
        "--metadata/--no-metadata",
        help="Prepend title, author/date, canonical URL, and page metadata as YAML front matter.",
    ),
    render_js: bool = typer.Option(
        get_cli_default("convert", "render_js", False),
        "--render-js/--static",
        help="Render JavaScript in an isolated optional Chromium context.",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", help="Set logging level."
    ),
    debug_log: Optional[Path] = typer.Option(
        None, "--debug-log", help="Write debug logs to specified file."
    ),
    fancy: bool = typer.Option(
        get_cli_default("convert", "fancy", False),
        "--fancy/--plain",
        help="Enable fancy output with progress bars and decorations.",
    ),
):
    """Convert HTML content from URLs or local files to Markdown."""
    set_log_level(log_level, debug_log)
    validate_content_options(content_mode, selector)

    # Handle config updates for cookie path
    if cookie_path:
        config = load_config()
        config.setdefault("browser", {}).setdefault("custom_path", {})
        if browser:
            config["browser"]["custom_path"][browser] = str(cookie_path)
        else:
            pref_browser = config.get("browser", {}).get("preferred", "chrome")
            config["browser"]["custom_path"][pref_browser] = str(cookie_path)
        save_config(config)

    if fancy:
        # Fancy mode with progress bars and decorations
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
                    source=source,
                    content_mode=content_mode,
                    selector=selector,
                    output=output,
                    no_cookies=no_cookies,
                    browser_cookies=browser_cookies,
                    browser=browser,
                    cookie_path=cookie_path,
                    cookie_json=cookie_json,
                    headers_file=headers_file,
                    storage_state=storage_state,
                    local=local,
                    download_images=download_images,
                    images_dir=images_dir,
                    enhanced_headers=enhanced_headers,
                    user_agent_contact=user_agent_contact,
                    simulate_browser=simulate_browser,
                    insecure=insecure,
                    include_metadata=include_metadata,
                    render_js=render_js,
                    allow_private_network=allow_private_network,
                    progress=progress,
                    task_id=task_id,
                    console=console,
                ):
                    successes += 1
                progress.update(task_id, completed=1)

        # Show summary
        if len(sources) > 1:
            console.print(
                f"\n✨ [bold green]Completed {successes}/{len(sources)} conversions[/bold green]"
            )

        if successes < len(sources):
            raise typer.Exit(1)
    else:
        # Quiet mode - just output the content
        successes = 0
        for source in sources:
            if process_single_quiet(
                source=source,
                content_mode=content_mode,
                selector=selector,
                output=output,
                no_cookies=no_cookies,
                browser_cookies=browser_cookies,
                browser=browser,
                cookie_path=cookie_path,
                cookie_json=cookie_json,
                headers_file=headers_file,
                storage_state=storage_state,
                local=local,
                download_images=download_images,
                images_dir=images_dir,
                enhanced_headers=enhanced_headers,
                user_agent_contact=user_agent_contact,
                simulate_browser=simulate_browser,
                insecure=insecure,
                include_metadata=include_metadata,
                render_js=render_js,
                allow_private_network=allow_private_network,
            ):
                successes += 1

        if successes < len(sources):
            raise typer.Exit(1)


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
    content_mode: ContentMode = typer.Option(
        get_cli_default("batch", "content_mode", ContentMode.FULL.value),
        "--content",
        help="Select full document, inferred main content, or an explicit selector.",
    ),
    selector: Optional[str] = typer.Option(
        get_cli_default("batch", "selector", None),
        "--selector",
        help="CSS selector used only with '--content selector'.",
    ),
    include_metadata: bool = typer.Option(
        get_cli_default("batch", "metadata", False),
        "--metadata/--no-metadata",
        help="Prepend title, author/date, canonical URL, and page metadata as YAML front matter.",
    ),
    enhanced_headers: bool = typer.Option(
        get_cli_default("batch", "enhanced_headers", True),
        "--enhanced-headers/--basic-headers",
        help="Use an identified html2md user agent and compression support.",
    ),
    user_agent_contact: Optional[str] = typer.Option(
        get_cli_default("batch", "user_agent_contact", None),
        "--user-agent-contact",
        help="Contact email or URL to include in the crawler user agent.",
    ),
    simulate_browser: bool = typer.Option(
        get_cli_default("batch", "simulate_browser", False),
        "--simulate-browser/--identify-crawler",
        help="Use the configured browser-like request identity.",
    ),
    flatten_output: bool = typer.Option(
        get_cli_default("batch", "flatten", False),
        "--flatten/--preserve-paths",
        help="Output files directly to domain directories (e.g., 'docs.github.com/')",
    ),
    flatten_all: bool = typer.Option(
        get_cli_default("batch", "flatten_all", False),
        "--flatten-all/--no-flatten-all",
        help="Output all files to a single directory, ignoring domain structure",
    ),
    hierarchical: bool = typer.Option(
        get_cli_default("batch", "hierarchical", False),
        "--hierarchical/--flat-domains",
        help="Create hierarchical domain folders (e.g., com/jetbrains/www)",
    ),
    visualize: bool = typer.Option(
        get_cli_default("batch", "visualize", False),
        "--visualize/--no-visualize",
        help="Display a visual representation of the output directory structure.",
    ),
    report: Optional[Path] = typer.Option(
        None,
        "--report",
        help="Generate a detailed Markdown report of the process.",
    ),
    insecure: bool = typer.Option(
        get_cli_default("batch", "insecure", False),
        "--insecure/--secure",
        "--no-verify-ssl",
        help="Disable SSL certificate verification. Only use with hosts you trust "
        "(e.g. internal servers with self-signed certificates).",
    ),
    allow_private_network: bool = typer.Option(
        get_cli_default("batch", "allow_private_network", False),
        "--allow-private-network/--public-network-only",
        help="Allow explicitly trusted private, loopback, or link-local destinations.",
    ),
    quiet: bool = typer.Option(
        get_cli_default("batch", "quiet", False),
        "--quiet/--progress-output",
        help="Reduce output verbosity, showing only essential information.",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", help="Set logging level."
    ),
    debug_log: Optional[Path] = typer.Option(
        None, "--debug-log", help="Write debug logs to specified file."
    ),
):
    """Process markdown files with links and create modular output."""
    set_log_level(log_level, debug_log)
    validate_content_options(content_mode, selector)

    # Validate flatten options
    if flatten_output and flatten_all:
        console.print(
            "[bold red]Error:[/bold red] Cannot use both --flatten and --flatten-all options together."
        )
        raise typer.Exit(1)
    if (flatten_output or flatten_all) and hierarchical:
        console.print(
            "[bold red]Error:[/bold red] Cannot use --hierarchical with --flatten or --flatten-all options."
        )
        raise typer.Exit(1)

    # Start time for processing report
    start_time = time.time()

    # Display header without the layout
    if not quiet:
        # Create header with styled title and stats
        header_text = Text()
        header_text.append("📚 ", style="bold")
        header_text.append("HTML2MD BATCH PROCESSOR", style="bold magenta")
        header_text.append(
            " - Convert URLs to structured Markdown", style="italic cyan"
        )

        console.print(
            Panel(
                header_text,
                border_style="magenta",
                padding=(1, 2),
            )
        )
    else:
        # Display minimal header in quiet mode
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

    # Process files with enhanced live progress
    console.print("\n[bold]Starting batch processing...[/bold]")

    # Initialize variables to track results
    batch_result = BatchResult()

    with EnhancedProgress() as progress:
        task = progress.add_task("Extracting URLs...", total=None)

        try:
            # Create a custom wrapper function to update progress with more user feedback
            def progress_callback(message, url=None, status=None):
                # Update the progress bar
                progress.update(task, description=message)

                # For certain informational messages, also print them
                if status in ["info", "warning"]:
                    # Pause the progress display temporarily
                    progress.stop()

                    if status == "warning":
                        console.print(f"[yellow]⚠ {message}[/yellow]")
                    elif "URLs to process" in message:
                        console.print("[blue]Finding URLs in file:[/blue]")
                    elif message.startswith("  "):  # This is a URL in the list
                        # Extract just the URL, not the index
                        url_part = (
                            message.split(". ", 1)[1] if ". " in message else message
                        )
                        console.print(f"  [dim]{url_part.strip()}[/dim]")
                    else:
                        console.print(f"[blue]ℹ[/blue] {message}")

                    # Resume the progress display
                    progress.start()

            config = load_config()
            header_manager = build_header_manager(
                config,
                enhanced_headers=enhanced_headers,
                user_agent_contact=user_agent_contact,
                simulate_browser=simulate_browser,
            )

            batch_result = process_markdown_links(
                expanded_files,
                output_dir,
                content_mode=content_mode,
                selector=selector,
                progress_callback=progress_callback,
                flatten_output=flatten_output,
                flatten_all=flatten_all,
                hierarchical_domains=hierarchical,
                verify_ssl=not insecure,
                include_metadata=include_metadata,
                allow_private_network=allow_private_network,
                header_manager=header_manager,
            )
            processed_count = batch_result.processed_count
            url_to_file_mapping = batch_result.url_mapping

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

    # Show summary of processing results with more detail
    console.print(
        f"\n✨ [bold green]Successfully processed {processed_count} URLs[/bold green]"
    )

    # Generate summary information
    processing_time = time.time() - start_time
    created_files = []

    # Use the url_to_file_mapping from the batch processor to get actual created files
    for url, file_path in url_to_file_mapping.items():
        rel_path = os.path.relpath(file_path, output_dir)
        created_files.append((file_path, rel_path))

    # Count output files
    file_count = len(created_files)

    dir_count = 0
    for root, dirs, files in os.walk(output_dir):
        dir_count += len(dirs)

    # Display the results based on the visualization mode
    if visualize and not quiet and file_count > 0:
        # Create an enhanced visual display of results
        results_layout = Layout()
        results_layout.split_column(
            Layout(name="summary", size=4),
            Layout(name="files", ratio=1),
            Layout(name="directory", ratio=2 if dir_count > 0 else 0),
        )

        # Summary panel with statistics and timing
        summary_table = Table.grid(padding=1)
        summary_table.add_column(style="bold blue")
        summary_table.add_column(style="green")

        summary_table.add_row(
            "Total URLs Processed:", f"[count]{processed_count}[/count]"
        )
        summary_table.add_row("Files Created:", f"[count]{file_count}[/count]")
        summary_table.add_row("Directories Created:", f"[count]{dir_count}[/count]")
        summary_table.add_row(
            "Processing Time:", f"[count]{processing_time:.2f}[/count] seconds"
        )

        summary_panel = Panel(
            summary_table,
            title="Processing Summary",
            border_style="green",
            padding=(1, 2),
        )
        results_layout["summary"].update(summary_panel)

        # Files list in a scrollable panel (show sample if many files)
        if file_count > 0:
            files_content = Text()
            max_files_to_show = min(10, file_count)

            for i, (_, rel_path) in enumerate(created_files[:max_files_to_show]):
                files_content.append(f"{STATUS_EMOJI['success']} ", style="green")
                files_content.append(rel_path, style="filename")
                files_content.append("\n")

            if file_count > max_files_to_show:
                files_content.append(
                    f"\n... and {file_count - max_files_to_show} more files",
                    style="dim",
                )

            files_panel = Panel(
                files_content,
                title=f"Files Created ({file_count} total)",
                border_style="blue",
                padding=(1, 2),
            )
            results_layout["files"].update(files_panel)

        # Directory tree visualization
        if dir_count > 0:
            tree = display_directory_tree(output_dir)
            dir_panel = Panel(
                tree,
                title="Directory Structure",
                border_style="cyan",
                padding=(1, 2),
            )
            results_layout["directory"].update(dir_panel)

        console.print("\n")
        console.print(results_layout)

    else:
        # Standard output for non-visual mode
        if not quiet:
            console.print("\n[bold blue]Files created:[/bold blue]")

            # Just show first few files with count
            max_files_to_show = min(5, file_count)
            for _, rel_path in created_files[:max_files_to_show]:
                console.print(f"[green]✓[/green] [bold]{rel_path}[/bold]")

            if file_count > max_files_to_show:
                console.print(f"... and {file_count - max_files_to_show} more files")

            console.print(
                f"\n[bold green]Total files created: {file_count}[/bold green]"
            )

            # Show simple output directory structure
            console.print("\n[bold blue]Output directory structure:[/bold blue]")

            # Create a table to show the structure
            table = Table(show_header=True)
            table.add_column("Type", style="cyan")
            table.add_column("Count", style="green")

            table.add_row("Directories", str(dir_count))
            table.add_row("Files", str(file_count))

            console.print(table)

    # Generate report if requested
    if report is not None:
        report_content = f"""# HTML2MD Batch Processing Report

## Summary
- **Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}
- **Total URLs Processed:** {processed_count}
- **Files Created:** {file_count}
- **Directories Created:** {dir_count}
- **Processing Time:** {processing_time:.2f} seconds
- **Output Directory:** {output_dir}
- **Options Used:**
  - Content: {content_mode.value}{f" ({selector})" if selector else ""}
  - Flatten Output: {flatten_output}

## Files Created
"""
        # Add list of all files created
        for _, rel_path in created_files:
            report_content += f"- {rel_path}\n"

        # Save report
        with open(report, "w") as f:
            f.write(report_content)
        console.print(
            f"\n[success]Report saved to: [filename]{report}[/filename][/success]"
        )

    if not batch_result.success:
        detail = batch_result.error or (
            f"{batch_result.failed_count} URL(s) failed; "
            f"{batch_result.processed_count} succeeded"
        )
        console.print(f"\n[bold red]Batch processing failed: {detail}[/bold red]")
        raise typer.Exit(1)

    console.print(
        f"\n[success]Batch processing complete! Output saved to [directory]{output_dir}[/directory][/success]"
    )


@app.command(name="crawl")
def crawl_command(
    start_urls: List[str] = typer.Argument(..., help="Starting URLs to crawl."),
    output_dir: Path = typer.Option(
        "output",
        "--output-dir",
        "-o",
        help="Directory to save output files and folders.",
    ),
    follow_option: str = typer.Option(
        get_cli_default("crawl", "follow", "domain-only"),
        "--follow",
        help="How to follow links. Options: 'domain-only', 'host-only', 'subdomain', or a regex pattern.",
    ),
    max_depth: int = typer.Option(
        get_cli_default("crawl", "max_depth", 3),
        "--max-depth",
        help="Maximum link depth to follow.",
    ),
    max_pages: int = typer.Option(
        get_cli_default("crawl", "max_pages", 100),
        "--max-pages",
        help="Maximum number of pages to crawl.",
    ),
    delay: float = typer.Option(
        get_cli_default("crawl", "delay", 0.0),
        "--delay",
        help="Delay between requests in seconds (e.g., 1.5). A random jitter of ±30% will be added.",
    ),
    respect_robots: bool = typer.Option(
        get_cli_default("crawl", "respect_robots", True),
        "--respect-robots/--ignore-robots",
        help="Respect robots.txt rules and crawl-delay directives.",
    ),
    rate_limit: Optional[int] = typer.Option(
        get_cli_default("crawl", "rate_limit", None),
        "--rate-limit",
        help="Maximum requests per minute (e.g., 30). Includes circuit breaker and adaptive limiting.",
    ),
    enhanced_headers: bool = typer.Option(
        get_cli_default("crawl", "enhanced_headers", True),
        "--enhanced-headers/--basic-headers",
        help="Use enhanced headers with User-Agent identification and compression support.",
    ),
    user_agent_contact: Optional[str] = typer.Option(
        get_cli_default("crawl", "user_agent_contact", None),
        "--user-agent-contact",
        help="Contact email or URL to include in User-Agent header (e.g., 'admin@example.com').",
    ),
    simulate_browser: bool = typer.Option(
        get_cli_default("crawl", "simulate_browser", False),
        "--simulate-browser/--identify-crawler",
        help="Use browser-like headers instead of identifying as html2md crawler.",
    ),
    insecure: bool = typer.Option(
        get_cli_default("crawl", "insecure", False),
        "--insecure/--secure",
        "--no-verify-ssl",
        help="Disable SSL certificate verification. Only use with hosts you trust "
        "(e.g. internal servers with self-signed certificates).",
    ),
    allow_private_network: bool = typer.Option(
        get_cli_default("crawl", "allow_private_network", False),
        "--allow-private-network/--public-network-only",
        help="Allow explicitly trusted private, loopback, or link-local destinations.",
    ),
    polite: bool = typer.Option(
        get_cli_default("crawl", "polite", False),
        "--polite/--standard-policy",
        help="Enable conservative sequential crawling with slower adaptive delays.",
    ),
    show_progress: bool = typer.Option(
        get_cli_default("crawl", "show_progress", True),
        "--progress/--no-progress",
        help="Show crawling progress and statistics.",
    ),
    content_mode: ContentMode = typer.Option(
        get_cli_default("crawl", "content_mode", ContentMode.FULL.value),
        "--content",
        help="Select full document, inferred main content, or an explicit selector.",
    ),
    selector: Optional[str] = typer.Option(
        get_cli_default("crawl", "selector", None),
        "--selector",
        help="CSS selector used only with '--content selector'.",
    ),
    include_metadata: bool = typer.Option(
        get_cli_default("crawl", "metadata", False),
        "--metadata/--no-metadata",
        help="Prepend title, author/date, canonical URL, and page metadata as YAML front matter.",
    ),
    flatten_output: bool = typer.Option(
        get_cli_default("crawl", "flatten", False),
        "--flatten/--preserve-paths",
        help="Output files directly to domain directories (e.g., 'docs.github.com/')",
    ),
    hierarchical: bool = typer.Option(
        get_cli_default("crawl", "hierarchical", False),
        "--hierarchical/--flat-domains",
        help="Create hierarchical domain folders (e.g., com/jetbrains/www)",
    ),
    visualize: bool = typer.Option(
        get_cli_default("crawl", "visualize", False),
        "--visualize/--no-visualize",
        help="Display a visual representation of the output directory structure.",
    ),
    quiet: bool = typer.Option(
        get_cli_default("crawl", "quiet", False),
        "--quiet/--progress-output",
        help="Reduce output verbosity, showing only essential information.",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", help="Set logging level."
    ),
    debug_log: Optional[Path] = typer.Option(
        None, "--debug-log", help="Write debug logs to specified file."
    ),
):
    """Recursively crawl websites from starting URLs and convert to markdown."""
    set_log_level(log_level, debug_log)
    validate_content_options(content_mode, selector)

    # Start time for processing report
    start_time = time.time()

    # Display header without the layout
    if not quiet:
        # Create header with styled title and stats
        header_text = Text()
        header_text.append("🕸️ ", style="bold")
        header_text.append("HTML2MD WEBSITE CRAWLER", style="bold blue")
        header_text.append(
            " - Recursively convert websites to Markdown", style="italic cyan"
        )

        console.print(
            Panel(
                header_text,
                border_style="blue",
                padding=(1, 2),
            )
        )
    else:
        # Display minimal header in quiet mode
        console.print(
            Panel.fit(
                "🕸️ [bold blue]html2md crawl[/bold blue] - Website Crawler",
                border_style="blue",
            )
        )

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    console.print(f"[bold blue]Output directory:[/bold blue] {output_dir}")

    # Set up progress display for crawling
    processed_total = 0
    failed_total = 0
    total_urls_processed = 0
    url_to_file_mappings = {}

    for start_url in start_urls:
        if not is_url(start_url):
            console.print(f"[bold red]❌ Invalid URL: {start_url}[/bold red]")
            failed_total += 1
            continue

        console.print(f"\n[bold blue]Starting crawl from:[/bold blue] {start_url}")
        console.print(f"[bold]Follow option:[/bold] {follow_option}")
        console.print(f"[bold]Maximum depth:[/bold] {max_depth}")
        console.print(f"[bold]Maximum pages:[/bold] {max_pages}")
        if delay > 0:
            console.print(f"[bold]Request delay:[/bold] {delay}s (±30% jitter)")
        console.print(
            f"[bold]Respect robots.txt:[/bold] {'Yes' if respect_robots else 'No'}"
        )
        if rate_limit:
            console.print(f"[bold]Rate limit:[/bold] {rate_limit} requests/minute")

        with EnhancedProgress() as progress:
            task = progress.add_task(f"Crawling {start_url}...", total=None)

            # Create a custom wrapper function to update progress with more user feedback
            def progress_callback(message, url=None, status=None):
                # Update the progress bar
                progress.update(task, description=message)

                # For certain messages, also print them
                if (
                    url
                    and status
                    in ["queued", "processing", "failed", "saved", "extracting_links"]
                    and not quiet
                ):
                    # Pause the progress display temporarily
                    progress.stop()

                    if status == "queued":
                        console.print(
                            f"  {STATUS_EMOJI['queued']} [dim]Queued: {url}[/dim]"
                        )
                    elif status == "processing":
                        console.print(
                            f"  {STATUS_EMOJI['processing']} Processing: {url}"
                        )
                    elif status == "failed":
                        console.print(
                            f"  {STATUS_EMOJI['error']} [red]Failed: {url}[/red]"
                        )
                    elif status == "saved":
                        console.print(
                            f"  {STATUS_EMOJI['success']} [green]Saved: {url}[/green]"
                        )
                    elif status == "extracting_links":
                        message_parts = message.split(": ", 1)
                        if len(message_parts) > 1:
                            console.print(
                                f"  {STATUS_EMOJI['link']} {message_parts[1]}"
                            )

                    # Resume the progress display
                    progress.start()

            try:
                # Build header configuration from CLI options and config
                config = load_config()
                header_config = build_header_config(
                    config,
                    enhanced_headers=enhanced_headers,
                    user_agent_contact=user_agent_contact,
                    simulate_browser=simulate_browser,
                )

                # Build concurrent configuration from CLI options and config
                from html2md.network.concurrent_limiter import (
                    ConcurrentConfig,
                    BackoffStrategy,
                )

                concurrent_settings = config.get("concurrent", {})

                # Parse backoff strategy
                backoff_str = concurrent_settings.get("backoff_strategy", "exponential")
                backoff_strategy = BackoffStrategy.EXPONENTIAL
                if backoff_str == "none":
                    backoff_strategy = BackoffStrategy.NONE
                elif backoff_str == "linear":
                    backoff_strategy = BackoffStrategy.LINEAR
                elif backoff_str == "fibonacci":
                    backoff_strategy = BackoffStrategy.FIBONACCI

                concurrent_config = ConcurrentConfig(
                    backoff_strategy=backoff_strategy,
                    initial_backoff=concurrent_settings.get("initial_backoff", 1.0),
                    max_backoff=concurrent_settings.get("max_backoff", 300.0),
                    backoff_multiplier=concurrent_settings.get(
                        "backoff_multiplier", 2.0
                    ),
                    error_threshold_for_backoff=concurrent_settings.get(
                        "error_threshold", 3
                    ),
                    retry_after_respect=concurrent_settings.get(
                        "respect_retry_after", True
                    ),
                    polite_delay_multiplier=concurrent_settings.get(
                        "polite_delay_multiplier", 2.0
                    ),
                )

                # Signal handling is explicit and scoped to active crawl work.
                state_manager = StateManager()
                with state_manager.signal_handling():
                    result = crawl_website(
                        start_url,
                        output_dir,
                        follow_option=follow_option,
                        max_depth=max_depth,
                        max_pages=max_pages,
                        delay=delay,
                        respect_robots=respect_robots,
                        rate_limit=rate_limit,
                        header_config=header_config,
                        concurrent_config=concurrent_config,
                        polite_mode=polite,
                        show_progress=show_progress,
                        content_mode=content_mode,
                        selector=selector,
                        include_metadata=include_metadata,
                        progress_callback=progress_callback,
                        flatten_output=flatten_output,
                        hierarchical_domains=hierarchical,
                        verify_ssl=not insecure,
                        allow_private_network=allow_private_network,
                        state_manager=state_manager,
                    )

                if not result.success:
                    failed_total += 1
                    progress.update(task, description=f"❌ {result.error}")
                    console.print(f"[bold red]Crawl failed: {result.error}[/bold red]")
                    continue

                # Update totals
                processed_total += 1
                total_urls_processed += result.processed_count
                url_to_file_mappings.update(result.url_mapping)

                # Set completed state
                progress.update(
                    task,
                    description=f"✅ Completed crawling {start_url} - Processed {result.processed_count} pages",
                )

            except Exception as e:
                failed_total += 1
                logger.error(f"Error during recursive crawling of {start_url}: {e}")
                progress.update(task, description=f"❌ Error: {str(e)}")
                console.print(
                    f"[bold red]Error during crawling {start_url}: {str(e)}[/bold red]"
                )

    # Show summary of processing results with more detail
    if processed_total > 0:
        msg = f"\n✨ [bold green]Successfully processed {total_urls_processed} pages"
        msg += f" from {processed_total}/{len(start_urls)} URLs[/bold green]"
        console.print(msg)

        # Generate summary information
        processing_time = time.time() - start_time
        file_count = len(url_to_file_mappings)

        dir_count = 0
        for root, dirs, files in os.walk(output_dir):
            dir_count += len(dirs)

        # Display the results based on the visualization mode
        if visualize and not quiet and file_count > 0:
            # Create an enhanced visual display of results
            results_layout = Layout()
            results_layout.split_column(
                Layout(name="summary", size=4),
                Layout(name="files", ratio=1),
                Layout(name="directory", ratio=2 if dir_count > 0 else 0),
            )

            # Summary panel with statistics and timing
            summary_table = Table.grid(padding=1)
            summary_table.add_column(style="bold blue")
            summary_table.add_column(style="green")

            summary_table.add_row(
                "Total URLs Crawled:", f"[count]{total_urls_processed}[/count]"
            )
            summary_table.add_row("Files Created:", f"[count]{file_count}[/count]")
            summary_table.add_row("Directories Created:", f"[count]{dir_count}[/count]")
            summary_table.add_row(
                "Processing Time:", f"[count]{processing_time:.2f}[/count] seconds"
            )

            summary_panel = Panel(
                summary_table,
                title="Crawling Summary",
                border_style="green",
                padding=(1, 2),
            )
            results_layout["summary"].update(summary_panel)

            # Files list in a scrollable panel (show sample if many files)
            if file_count > 0:
                files_content = Text()
                max_files_to_show = min(10, file_count)

                for i, (url, path) in enumerate(
                    list(url_to_file_mappings.items())[:max_files_to_show]
                ):
                    files_content.append(f"{STATUS_EMOJI['success']} ", style="green")
                    rel_path = os.path.relpath(path, output_dir)
                    files_content.append(rel_path, style="filename")
                    files_content.append("\n")

                if file_count > max_files_to_show:
                    files_content.append(
                        f"\n... and {file_count - max_files_to_show} more files",
                        style="dim",
                    )

                files_panel = Panel(
                    files_content,
                    title=f"Files Created ({file_count} total)",
                    border_style="blue",
                    padding=(1, 2),
                )
                results_layout["files"].update(files_panel)

            # Directory tree visualization
            if dir_count > 0:
                tree = display_directory_tree(output_dir)
                dir_panel = Panel(
                    tree,
                    title="Directory Structure",
                    border_style="cyan",
                    padding=(1, 2),
                )
                results_layout["directory"].update(dir_panel)

            console.print("\n")
            console.print(results_layout)

        else:
            # Standard output for non-visual mode
            if not quiet:
                console.print("\n[bold blue]Files created:[/bold blue]")

                # Just show first few files with count
                max_files_to_show = min(5, file_count)
                for i, (url, path) in enumerate(
                    list(url_to_file_mappings.items())[:max_files_to_show]
                ):
                    rel_path = os.path.relpath(path, output_dir)
                    console.print(f"[green]✓[/green] [bold]{rel_path}[/bold]")

                if file_count > max_files_to_show:
                    console.print(
                        f"... and {file_count - max_files_to_show} more files"
                    )

                console.print(
                    f"\n[bold green]Total files created: {file_count}[/bold green]"
                )

    if failed_total:
        console.print(
            f"\n[bold red]Crawling failed for {failed_total}/{len(start_urls)} starting URLs.[/bold red]"
        )
        raise typer.Exit(1)

    console.print(
        f"\n[success]Website crawling complete! Output saved to [directory]{output_dir}[/directory][/success]"
    )


def version_callback(value: bool) -> None:
    """Print distribution metadata before command validation."""
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", help="Set logging level."
    ),
    debug_log: Optional[Path] = typer.Option(
        None, "--debug-log", help="Write debug logs to specified file."
    ),
    banner: bool = typer.Option(False, "--banner", help="Display the welcome banner."),
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the installed html2md version and exit.",
        is_eager=True,
        callback=version_callback,
    ),
):
    """Main entry point for the application."""
    del version
    set_log_level(log_level, debug_log)

    # Show welcome banner if explicitly requested
    if banner:
        show_welcome_banner(console)


def detect_color_support():
    """Detect if the terminal supports colors and how many."""
    # Check if NO_COLOR environment variable is set (respecting no-color.org standard)
    if os.environ.get("NO_COLOR") is not None:
        return 0

    # Check for common CI environments that often have color support
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return 256

    # Use platform detection
    if platform.system() == "Windows":
        # Check for Windows Terminal or ConEmu which have good color support
        if os.environ.get("WT_SESSION") or os.environ.get("ConEmuANSI") == "ON":
            return 256
        # Check for terminals that support 16 colors
        if os.environ.get("TERM") in ["xterm", "xterm-color"]:
            return 16
        # Default minimal windows cmd.exe (unless ANSICON or similar is installed)
        if os.environ.get("ANSICON"):
            return 16
        return 0

    # Most modern Unix terminals support at least 16 colors, many support 256
    if os.environ.get("TERM") in ["xterm-256color", "screen-256color"]:
        return 256
    if os.environ.get("COLORTERM") in ["truecolor", "24bit"]:
        return 16777216  # 24-bit color

    # Default to 16 colors for most terminals
    return 16


def entry_point():
    """Entry point for the CLI."""
    # Configure color detection
    color_system = "auto"
    color_level = detect_color_support()

    if color_level == 0:
        color_system = None
    elif color_level == 16:
        color_system = "standard"
    elif color_level == 256:
        color_system = "256"
    elif color_level >= 16777216:
        color_system = "truecolor"

    # Update console with detected color system
    global console
    console = Console(theme=HTML2MD_THEME, color_system=color_system)

    # Run the app
    try:
        app()
    except Exception as e:
        console.print(f"[error]Error: {str(e)}[/error]")
        if os.environ.get("HTML2MD_DEBUG"):
            console.print_exception(show_locals=True)
        else:
            console.print(
                "[dim]Run with HTML2MD_DEBUG=1 for detailed error information[/dim]"
            )
        sys.exit(1)
