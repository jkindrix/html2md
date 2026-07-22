"""
CLI for grab2md using Typer and Rich for a beautiful user experience.
"""

import logging
import os
import platform
import sys
import time
from enum import Enum
from pathlib import Path
from typing import List, Literal, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)
from typer._click.core import Context as TyperContext
from typer.core import TyperGroup

from grab2md.config.loader import load_config
from grab2md.markdown.batch_processor import process_markdown_links
from grab2md.markdown.content_extractor import (
    ContentExtractionError,
    ContentMode,
    validate_content_request,
)
from grab2md.markdown.crawler import crawl_website
from grab2md.cli.state_commands import state_app
from grab2md import __version__
from grab2md.cli.conversion_presenter import (
    process_single_quiet,
    process_single_with_progress,
)
from grab2md.cli.command_runtime import (
    BatchCommandOptions,
    Browser,
    COMMAND_ERRORS,
    ConvertCommandOptions,
    CrawlCommandOptions,
    classify_command_failure,
    execute_batch,
    execute_crawls,
    prepare_convert_options,
)
from grab2md.cli.config_commands import config_app
from grab2md.cli.presentation import (
    GRAB2MD_THEME,
    EnhancedProgress,
    display_directory_tree,
    show_welcome_banner,
)
from grab2md.utils.logger import setup_logging

# Configure logger to use a file instead of stdout
logger = setup_logging(console_output=False)

# Create Rich console with the custom theme
console = Console(theme=GRAB2MD_THEME)


_COMMANDS = frozenset({"batch", "config", "convert", "crawl", "state"})
_ROOT_VALUE_OPTIONS = frozenset({"--debug-log", "--log-level"})
_ROOT_FLAG_OPTIONS = frozenset({"--banner"})
_ROOT_TERMINAL_OPTIONS = frozenset({"--help", "-h", "--version"})


def route_default_source(args: list[str]) -> list[str]:
    """Insert the hidden conversion command when the input starts with a source."""
    if not args:
        return args

    command_index = 0
    while command_index < len(args):
        argument = args[command_index]
        if argument in _ROOT_TERMINAL_OPTIONS:
            return args
        if argument in _ROOT_FLAG_OPTIONS:
            command_index += 1
            continue
        if argument in _ROOT_VALUE_OPTIONS:
            if command_index + 1 >= len(args):
                return args
            command_index += 2
            continue
        if any(argument.startswith(f"{option}=") for option in _ROOT_VALUE_OPTIONS):
            command_index += 1
            continue
        break

    if command_index >= len(args) or args[command_index] in _COMMANDS:
        return args
    return [*args[:command_index], "convert", *args[command_index:]]


class DefaultSourceGroup(TyperGroup):
    """Treat an unrecognized first operand as a conversion source."""

    def parse_args(self, ctx: TyperContext, args: list[str]) -> list[str]:
        return super().parse_args(ctx, route_default_source(args))


# Create Typer app
app = typer.Typer(
    cls=DefaultSourceGroup,
    help=(
        "Convert HTTP(S) URLs or local HTML files to Markdown. Use batch, "
        "crawl, config, or state for alternate workflows."
    ),
    epilog=(
        "Examples: grab2md https://example.com -o page.md | "
        "grab2md page.html -o page.md | grab2md crawl https://docs.example.com"
    ),
    no_args_is_help=True,
    subcommand_metavar="[SOURCE ...] | COMMAND [ARGS]...",
    add_completion=False,
)


def fail_command(label: str, error: Exception) -> None:
    """Render a consistently classified command failure and exit."""
    failure = classify_command_failure(label, error)
    console.print(f"[bold red]{failure.message}[/bold red]")
    raise typer.Exit(failure.exit_code) from error


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


def set_log_level(level: LogLevel, debug_log: Optional[Path] = None) -> None:
    """Set the logging level and optionally enable debug logging to a file."""
    global logger

    # If debug log is specified, reconfigure the logger
    if debug_log:
        from grab2md.utils.logger import setup_logging

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


@app.command(name="convert", hidden=True)
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
        help=(
            "Use a compatible Firefox database or legacy Windows Chrome "
            "DPAPI database; current Chrome v20 cookies require --cookie-json."
        ),
    ),
    browser: Optional[Browser] = typer.Option(
        get_cli_default("convert", "browser", None),
        "--browser",
        help="Specify which browser to extract cookies from (default: chrome).",
    ),
    cookie_path: Optional[Path] = typer.Option(
        None,
        "--cookie-path",
        help="One-shot browser cookie database path; does not change configuration.",
    ),
    cookie_json: Optional[Path] = typer.Option(
        None,
        "--cookie-json",
        help="Primary portable path to an owner-only browser cookie JSON export.",
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
    options = ConvertCommandOptions(
        sources=sources,
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
        enhanced_headers=enhanced_headers,
        user_agent_contact=user_agent_contact,
        insecure=insecure,
        allow_private_network=allow_private_network,
        download_images=download_images,
        images_dir=images_dir,
        include_metadata=include_metadata,
        render_js=render_js,
        fancy=fancy,
    )
    try:
        prepare_convert_options(options)
    except COMMAND_ERRORS as error:
        fail_command("Conversion", error)
    arguments = options.conversion_arguments()
    successes = 0
    if fancy:
        console.print(
            Panel.fit(
                "🌐 [bold cyan]grab2md[/bold cyan] - HTML to Markdown Converter",
                border_style="cyan",
            )
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}[/bold blue]"),
            BarColumn(),
            TextColumn("[bold]{task.completed}/{task.total}[/bold]"),
            console=console,
        ) as progress:
            tasks = {
                source: progress.add_task(f"Queued: {source}", total=1)
                for source in sources
            }
            for source in sources:
                task_id = tasks[source]
                if process_single_with_progress(
                    source=source,
                    **arguments,
                    progress=progress,
                    task_id=task_id,
                    console=console,
                ):
                    successes += 1
                progress.update(task_id, completed=1)
        if len(sources) > 1:
            console.print(
                f"\n✨ [bold green]Completed {successes}/{len(sources)} conversions[/bold green]"
            )
    else:
        for source in sources:
            if process_single_quiet(source=source, **arguments):
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
        help="Use an identified grab2md user agent and compression support.",
    ),
    user_agent_contact: Optional[str] = typer.Option(
        get_cli_default("batch", "user_agent_contact", None),
        "--user-agent-contact",
        help="Contact email or URL to include in the crawler user agent.",
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
    options = BatchCommandOptions(
        input_patterns=input_files,
        output_dir=output_dir,
        content_mode=content_mode,
        selector=selector,
        include_metadata=include_metadata,
        enhanced_headers=enhanced_headers,
        user_agent_contact=user_agent_contact,
        flatten_output=flatten_output,
        flatten_all=flatten_all,
        hierarchical=hierarchical,
        visualize=visualize,
        report=report,
        insecure=insecure,
        allow_private_network=allow_private_network,
        quiet=quiet,
    )
    started = time.time()
    console.print(
        Panel.fit(
            "📚 [bold magenta]grab2md batch[/bold magenta] - Markdown Link Processor",
            border_style="magenta",
        )
    )
    try:
        with EnhancedProgress() as progress:
            task = progress.add_task("Extracting URLs...", total=None)

            def on_progress(message, _url=None, status=None):
                progress.update(task, description=message)
                if status in {"warning", "error"}:
                    progress.stop()
                    console.print(f"[yellow]⚠ {message}[/yellow]")
                    progress.start()

            execution = execute_batch(
                options,
                processor=process_markdown_links,
                config=load_config(),
                progress_callback=on_progress,
            )
            progress.update(
                task,
                description=(
                    f"✅ Completed processing {execution.result.processed_count} URLs"
                ),
            )
    except COMMAND_ERRORS as error:
        fail_command("Batch processing", error)

    for pattern in execution.unmatched_patterns:
        console.print(f"[yellow]⚠ No files found matching {pattern}[/yellow]")
    result = execution.result
    created_files = [
        os.path.relpath(path, output_dir) for path in result.url_mapping.values()
    ]
    console.print(
        f"\n✨ [bold green]Successfully processed {result.processed_count} URLs[/bold green]"
    )
    if not quiet:
        for relative_path in created_files[:10]:
            console.print(f"[green]✓[/green] [bold]{relative_path}[/bold]")
        if visualize and created_files:
            console.print(display_directory_tree(output_dir))
    if report is not None:
        elapsed = time.time() - started
        report_lines = [
            "# GRAB2MD Batch Processing Report",
            "",
            "## Summary",
            f"- **Total URLs Processed:** {result.processed_count}",
            f"- **Failed URLs:** {result.failed_count}",
            f"- **Processing Time:** {elapsed:.2f} seconds",
            f"- **Output Directory:** {output_dir}",
            "",
            "## Files Created",
            *(f"- {path}" for path in created_files),
            "",
        ]
        report.write_text("\n".join(report_lines), encoding="utf-8")
        console.print(f"[success]Report saved to: {report}[/success]")
    if not result.success:
        detail = result.error or (
            f"{result.failed_count} URL(s) failed; {result.processed_count} succeeded"
        )
        console.print(f"[bold red]Batch processing failed: {detail}[/bold red]")
        raise typer.Exit(1)
    console.print(
        f"\n[success]Batch processing complete! Output saved to {output_dir}[/success]"
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
        help=(
            "Maximum page attempts per starting URL, including failures and "
            "explicit retries."
        ),
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
        help=(
            "Hard maximum requests per minute for each destination origin "
            "(e.g., 30), plus adaptive slowing."
        ),
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
        help="Use at least one second between sequential requests and double larger delays.",
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
    options = CrawlCommandOptions(
        start_urls=start_urls,
        output_dir=output_dir,
        follow_option=follow_option,
        max_depth=max_depth,
        max_pages=max_pages,
        delay=delay,
        respect_robots=respect_robots,
        rate_limit=rate_limit,
        enhanced_headers=enhanced_headers,
        user_agent_contact=user_agent_contact,
        insecure=insecure,
        allow_private_network=allow_private_network,
        polite=polite,
        show_progress=show_progress,
        content_mode=content_mode,
        selector=selector,
        include_metadata=include_metadata,
        flatten_output=flatten_output,
        hierarchical=hierarchical,
        visualize=visualize,
        quiet=quiet,
    )
    console.print(
        Panel.fit(
            "🕸️ [bold blue]grab2md crawl[/bold blue] - Website Crawler",
            border_style="blue",
        )
    )

    def on_progress(message, url=None, status=None):
        if quiet or status not in {
            "queued",
            "processing",
            "failed",
            "error",
            "saved",
            "blocked",
        }:
            return
        label = f" ({url})" if url else ""
        console.print(f"{message}{label}")

    try:
        execution = execute_crawls(
            options,
            crawler=crawl_website,
            config=load_config(),
            progress_callback=on_progress,
        )
    except COMMAND_ERRORS as error:
        fail_command("Crawling", error)

    for invalid_url in execution.invalid_urls:
        console.print(f"[bold red]❌ Invalid URL: {invalid_url}[/bold red]")
    for start_url, result in execution.results:
        if result.success:
            console.print(
                f"[green]✓[/green] {start_url}: {result.processed_count} pages"
            )
        else:
            console.print(f"[bold red]Crawl failed: {result.error}[/bold red]")
    if execution.processed_start_count:
        console.print(
            f"\n✨ [bold green]Successfully processed "
            f"{execution.processed_page_count} pages from "
            f"{execution.processed_start_count}/{len(start_urls)} URLs[/bold green]"
        )
    if visualize and not quiet and execution.url_mapping:
        console.print(display_directory_tree(output_dir))
    if execution.failed_count:
        console.print(
            f"[bold red]Crawling failed for {execution.failed_count}/"
            f"{len(start_urls)} starting URLs.[/bold red]"
        )
        raise typer.Exit(1)
    console.print(
        f"\n[success]Website crawling complete! Output saved to {output_dir}[/success]"
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
        help="Show the installed grab2md version and exit.",
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


def detect_color_support() -> int:
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


def entry_point() -> None:
    """Entry point for the CLI."""
    # Redirected Windows streams may use a legacy code page that cannot encode
    # Rich's decorative Unicode. Preserve command execution and replace only
    # unsupported presentation glyphs instead of crashing before work begins.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="replace")

    # Configure color detection
    color_system: Literal["auto", "standard", "256", "truecolor", "windows"] | None = (
        "auto"
    )
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
    console = Console(theme=GRAB2MD_THEME, color_system=color_system)

    # Run the app
    try:
        app()
    except Exception as e:
        console.print(f"[error]Error: {str(e)}[/error]")
        if os.environ.get("GRAB2MD_DEBUG"):
            console.print_exception(show_locals=True)
        else:
            console.print(
                "[dim]Run with GRAB2MD_DEBUG=1 for detailed error information[/dim]"
            )
        sys.exit(1)
