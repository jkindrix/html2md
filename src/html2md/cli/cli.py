"""
CLI for html2md using Typer and Rich for a beautiful user experience.
"""

import glob
import json
import logging
import os
import platform
import sys
import time
from copy import deepcopy
from enum import Enum
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

from html2md.config.loader import (
    CONFIG_FILE,
    DEFAULT_CONFIG,
    get_backup_manager,
    load_config,
    save_config,
)
from html2md.config.schema import ConfigValidationError, default_at_path, parse_cli_value
from html2md.cookies.session_manager import get_session, apply_browser_cookies
from html2md.markdown.batch_processor import process_markdown_links
from html2md.markdown.converter import html_to_markdown, local_html_to_markdown
from html2md.markdown.crawler import crawl_website
from html2md.network.header_manager import HeaderConfig
from html2md.utils.logger import setup_logging
from html2md.utils.parser import is_url
from html2md.utils.state_manager import StateManager

# Create a custom theme with enhanced colors
html2md_theme = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "command": "bold magenta",
        "url": "underline blue",
        "filename": "bold cyan",
        "directory": "bold blue",
        "count": "bold yellow",
        "header": "bold white on blue",
        "subheader": "bold cyan",
    }
)

# Configure logger to use a file instead of stdout
logger = setup_logging(console_output=False)

# Create Rich console with the custom theme
console = Console(theme=html2md_theme)

# Define system information
SYSTEM_INFO = {
    "system": platform.system(),
    "release": platform.release(),
    "version": platform.version(),
    "python": platform.python_version(),
}

# Define emojis for different statuses
STATUS_EMOJI = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "processing": "🔄",
    "download": "📥",
    "upload": "📤",
    "config": "⚙️",
    "markdown": "📝",
    "html": "🌐",
    "batch": "📚",
    "convert": "🔄",
    "crawl": "🕸️",
    "file": "📄",
    "directory": "📁",
    "link": "🔗",
    "queued": "⏳",
    "visited": "👁️",
}

# Create Typer app
app = typer.Typer(
    help="Convert HTML content from URLs or local files to Markdown with beautiful output.",
    add_completion=False,
)


def get_cli_default(command: str, option: str, default_value=None):
    """Get CLI default value from config or use provided default."""
    config = load_config()
    cli_defaults = config.get("cli_defaults", {})
    command_defaults = cli_defaults.get(command, {})
    return command_defaults.get(option, default_value)

# Create config subcommand app
config_app = typer.Typer(
    help="Manage html2md configuration settings.",
    add_completion=False,
)

# Create state management subcommand app
state_app = typer.Typer(
    help="Manage crawl state and resume interrupted crawls.",
    add_completion=False,
)


# Create a custom class for rich progress display with estimated time
class EnhancedProgress(Progress):
    """Enhanced progress display with custom styling and additional columns."""

    def __init__(self):
        super().__init__(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}[/bold blue]"),
            BarColumn(bar_width=40, style="cyan", complete_style="green"),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
        )


def show_welcome_banner():
    """Display a beautiful welcome banner with system information."""
    title = Text("HTML2MD", style="bold white on blue")
    subtitle = Text("Convert HTML to Markdown with Style", style="italic cyan")

    # Create version information
    version_info = Table.grid(padding=(0, 1))
    version_info.add_row("Version:", "0.1.0")
    version_info.add_row("Python:", SYSTEM_INFO["python"])
    version_info.add_row("System:", f"{SYSTEM_INFO['system']} {SYSTEM_INFO['release']}")

    # Create a help hint
    help_text = Text("\nUse --help with any command for more information", style="dim")

    # Combine all elements
    banner_content = Group(title, subtitle, Text(), version_info, help_text)
    banner = Panel(
        banner_content,
        border_style="blue",
        padding=(1, 2),
        title="Welcome to HTML2MD",
        subtitle="https://github.com/jkindrix/html2md",
    )

    console.print(banner)


def display_directory_tree(path, max_depth=3):
    """Display a directory structure as a rich tree."""
    root = Tree(f"📁 {path}", style="bold blue")

    def add_directory(tree, path, depth=0):
        if depth >= max_depth:
            tree.add("...")
            return

        for item in sorted(os.listdir(path)):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                branch = tree.add(f"📁 {item}", style="bold blue")
                if depth < max_depth - 1:
                    add_directory(branch, item_path, depth + 1)
            else:
                icon = "📄"
                if item.endswith(".md"):
                    icon = "📝"
                elif item.endswith(".html"):
                    icon = "🌐"
                tree.add(f"{icon} {item}", style="green")

    try:
        add_directory(root, path)
        return root
    except Exception as e:
        return Text(f"Error displaying directory tree: {str(e)}", style="bold red")


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
    EDGE = "edge"
    SAFARI = "safari"


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


def process_single_with_progress(
    source: str,
    trim: bool,
    output: Optional[Path],
    no_cookies: bool,
    browser_cookies: bool,
    browser: Optional[Browser],
    cookie_path: Optional[Path] = None,
    cookie_json: Optional[Path] = None,
    local: bool = False,
    download_images: bool = False,
    images_dir: str = "images",
    enhanced_headers: bool = True,
    user_agent_contact: Optional[str] = None,
    simulate_browser: bool = False,
    insecure: bool = False,
    progress: Progress = None,
    task_id: TaskID = None,
) -> bool:
    """Process a single URL or file with progress tracking."""
    progress.update(task_id, description=f"Processing {source}")

    if is_url(source, local):
        # Process as URL
        # Build header configuration from CLI options and config
        config = load_config()
        header_settings = config.get("headers", {})
        
        header_config = HeaderConfig(
            use_enhanced_user_agent=enhanced_headers,
            contact_email=user_agent_contact if "@" in (user_agent_contact or "") else None,
            contact_url=user_agent_contact if user_agent_contact and "@" not in user_agent_contact else None,
            user_agent_name=header_settings.get("user_agent_name", "html2md"),
            user_agent_version=header_settings.get("user_agent_version", "1.0"),
            enable_compression=header_settings.get("enable_compression", True),
            compression_methods=header_settings.get("compression_methods", "gzip, deflate, br"),
            enable_conditional_requests=header_settings.get("enable_conditional_requests", True),
            simulate_browser=simulate_browser,
            browser_type=header_settings.get("browser_type", "chrome"),
            respect_caching=header_settings.get("respect_caching", True),
            include_accept_language=header_settings.get("include_accept_language", True),
            preferred_language=header_settings.get("preferred_language", "en-US,en;q=0.9"),
            custom_headers=header_settings.get("custom_headers", {})
        )
        
        from html2md.network.header_manager import HeaderManager
        header_manager = HeaderManager(header_config)
        headers = header_manager.get_headers(source)
        logger.info(f"Processing URL: {source}")

        try:
            # Subtasks for fetching and converting
            progress.update(task_id, description=f"Fetching content from {source}")

            # Create a new session
            session = None
            
            # Determine session type based on flags
            if not no_cookies:
                session = get_session(verify_ssl=not insecure)

                # If browser cookies flag is set, apply browser cookies to session
                if browser_cookies and session:
                    # Store browser preference in config or use specified one
                    config = load_config()
                    if browser:
                        config.setdefault('browser', {})['preferred'] = browser

                    progress.update(task_id, description=f"Extracting browser cookies for {source}")
                    
                    # Apply browser cookies to session - use JSON file if provided
                    if cookie_json:
                        progress.update(task_id, description=f"Loading cookies from JSON file for {source}")
                        session = apply_browser_cookies(session, source, cookie_json)
                        progress.update(task_id, description=f"Using cookies from JSON file for {source}")
                        logger.info(f"Using cookies from JSON file for {source}")
                    else:
                        # Otherwise use browser extraction
                        session = apply_browser_cookies(session, source)
                        browser_name = browser or config.get('browser', {}).get('preferred', 'chrome')
                        progress.update(task_id, description=f"Using cookies from {browser_name} browser for {source}")
                        logger.info(f"Using cookies from {browser_name} browser for {source}")

            # Determine output directory for images if needed
            output_dir = None
            if download_images and output:
                output_dir = os.path.dirname(os.path.abspath(output))
            elif download_images:
                # If no output file specified but downloading images, use current directory
                output_dir = os.getcwd()

            # Process URL with session and headers
            markdown_result = html_to_markdown(
                source, session=session, headers=headers, trim=trim,
                download_images=download_images, output_dir=output_dir, images_dir=images_dir,
                verify_ssl=not insecure
            )

            progress.update(task_id, description=f"Converting {source} to markdown")

            if markdown_result:
                if output:
                    # Save to file
                    progress.update(task_id, description=f"Saving to {output}")
                    with open(output, "w", encoding="utf-8") as f:
                        f.write(markdown_result)
                    # Show more information about what happened
                    progress.stop()
                    console.print(
                        f"[bold green]✓[/bold green] Downloaded and converted [bold]{source}[/bold]"
                    )
                    console.print(
                        f"[bold green]✓[/bold green] Saved output to [bold]{output}[/bold]"
                    )
                    progress.start()
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
                    "\n[blue]Authentication tips:[/blue]"
                )
                console.print("• Try using --browser-cookies to use your browser's cookies")
                console.print("• Use --browser firefox (or chrome, edge) to specify which browser's cookies to use")
                console.print("• Try using the --no-cookies flag if default cookies are causing issues")
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

            # Determine output directory for images if needed
            output_dir = None
            if download_images and output:
                output_dir = os.path.dirname(os.path.abspath(output))
            elif download_images:
                # If no output file specified but downloading images, use file's directory
                output_dir = os.path.dirname(file_path)

            # Process local file
            markdown_result = local_html_to_markdown(file_path, trim=trim,
                                                    download_images=download_images,
                                                    output_dir=output_dir,
                                                    images_dir=images_dir,
                                                    verify_ssl=not insecure)

            progress.update(task_id, description=f"Converting {file_path} to markdown")

            if markdown_result:
                if output:
                    # Save to file
                    progress.update(task_id, description=f"Saving to {output}")
                    with open(output, "w", encoding="utf-8") as f:
                        f.write(markdown_result)
                    # Show more information about what happened
                    progress.stop()
                    console.print(
                        f"[bold green]✓[/bold green] Converted local file [bold]{file_path}[/bold]"
                    )
                    console.print(
                        f"[bold green]✓[/bold green] Saved output to [bold]{output}[/bold]"
                    )
                    progress.start()
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


def process_single_quiet(
    source: str,
    trim: bool,
    output: Optional[Path],
    no_cookies: bool,
    browser_cookies: bool,
    browser: Optional[Browser],
    cookie_path: Optional[Path] = None,
    cookie_json: Optional[Path] = None,
    local: bool = False,
    download_images: bool = False,
    images_dir: str = "images",
    enhanced_headers: bool = True,
    user_agent_contact: Optional[str] = None,
    simulate_browser: bool = False,
    insecure: bool = False,
) -> bool:
    """Process a single URL or file in quiet mode (just output content)."""
    if is_url(source, local):
        # Process as URL
        # Build header configuration from CLI options and config
        config = load_config()
        header_settings = config.get("headers", {})
        
        header_config = HeaderConfig(
            use_enhanced_user_agent=enhanced_headers,
            contact_email=user_agent_contact if "@" in (user_agent_contact or "") else None,
            contact_url=user_agent_contact if user_agent_contact and "@" not in user_agent_contact else None,
            user_agent_name=header_settings.get("user_agent_name", "html2md"),
            user_agent_version=header_settings.get("user_agent_version", "1.0"),
            enable_compression=header_settings.get("enable_compression", True),
            compression_methods=header_settings.get("compression_methods", "gzip, deflate, br"),
            enable_conditional_requests=header_settings.get("enable_conditional_requests", True),
            simulate_browser=simulate_browser,
            browser_type=header_settings.get("browser_type", "chrome"),
            respect_caching=header_settings.get("respect_caching", True),
            include_accept_language=header_settings.get("include_accept_language", True),
            preferred_language=header_settings.get("preferred_language", "en-US,en;q=0.9"),
            custom_headers=header_settings.get("custom_headers", {})
        )
        
        from html2md.network.header_manager import HeaderManager
        header_manager = HeaderManager(header_config)
        headers = header_manager.get_headers(source)
        logger.info(f"Processing URL: {source}")

        try:
            # Create a new session
            session = None
            
            # Determine session type based on flags
            if not no_cookies:
                session = get_session(verify_ssl=not insecure)

                # If browser cookies flag is set, apply browser cookies to session
                if browser_cookies and session:
                    # Store browser preference in config or use specified one
                    config = load_config()
                    if browser:
                        config.setdefault('browser', {})['preferred'] = browser

                    # Apply browser cookies to session - use JSON file if provided
                    if cookie_json:
                        session = apply_browser_cookies(session, source, cookie_json)
                        logger.info(f"Using cookies from JSON file for {source}")
                    else:
                        # Otherwise use browser extraction
                        session = apply_browser_cookies(session, source)
                        browser_name = browser or config.get('browser', {}).get('preferred', 'chrome')
                        logger.info(f"Using cookies from {browser_name} browser for {source}")

            # Determine output directory for images if needed
            output_dir = None
            if download_images and output:
                output_dir = os.path.dirname(os.path.abspath(output))
            elif download_images:
                output_dir = os.getcwd()

            # Process URL with session and headers
            markdown_result = html_to_markdown(
                source, session=session, headers=headers, trim=trim,
                download_images=download_images, output_dir=output_dir, images_dir=images_dir,
                verify_ssl=not insecure
            )

            if markdown_result:
                if output:
                    # Save to file silently
                    with open(output, "w", encoding="utf-8") as f:
                        f.write(markdown_result)
                    logger.info(f"Successfully processed URL: {source}")
                else:
                    # Print to console without decoration
                    print(markdown_result)
                    logger.info(f"Successfully processed URL: {source}")
                return True
            else:
                print(f"Error: Unable to retrieve content from {source}", file=sys.stderr)
                return False
        except Exception as e:
            logger.error(f"Failed to process URL {source}: {e}")
            print(f"Error processing {source}: {str(e)}", file=sys.stderr)
            return False
    else:
        # Process as local file
        logger.info(f"Processing local file: {source}")

        try:
            # Expand to absolute path if needed
            file_path = os.path.abspath(os.path.expanduser(source))

            # Determine output directory for images if needed
            output_dir = None
            if download_images and output:
                output_dir = os.path.dirname(os.path.abspath(output))
            elif download_images:
                output_dir = os.path.dirname(file_path)

            # Process local file
            markdown_result = local_html_to_markdown(file_path, trim=trim,
                                                    download_images=download_images,
                                                    output_dir=output_dir,
                                                    images_dir=images_dir,
                                                    verify_ssl=not insecure)

            if markdown_result:
                if output:
                    # Save to file silently
                    with open(output, "w", encoding="utf-8") as f:
                        f.write(markdown_result)
                    logger.info(f"Successfully processed local file: {file_path}")
                else:
                    # Print to console without decoration
                    print(markdown_result)
                    logger.info(f"Successfully processed local file: {file_path}")
                return True
            else:
                print(f"Error: Unable to convert local file {file_path}", file=sys.stderr)
                return False
        except Exception as e:
            logger.error(f"Failed to process local file {source}: {e}")
            print(f"Error processing {source}: {str(e)}", file=sys.stderr)
            return False

    return False


@app.command(name="convert")
def convert_command(
    sources: List[str] = typer.Argument(
        ..., help="URLs or local HTML files to convert."
    ),
    trim: bool = typer.Option(
        get_cli_default("convert", "trim", True),
        "--trim/--no-trim",
        help="Enable/disable trimming based on domain-specific rules.",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file to save converted markdown."
    ),
    no_cookies: bool = typer.Option(
        get_cli_default("convert", "no_cookies", False), "--no-cookies", help="Disable loading cookies from the browser."
    ),
    browser_cookies: bool = typer.Option(
        get_cli_default("convert", "browser_cookies", False), "--browser-cookies", help="Use cookies from the local browser to authenticate with websites."
    ),
    browser: Optional[Browser] = typer.Option(
        get_cli_default("convert", "browser", None), "--browser", help="Specify which browser to extract cookies from (default: chrome)."
    ),
    cookie_path: Optional[Path] = typer.Option(
        None, "--cookie-path", help="Path to browser cookies database file (helps with Windows/WSL)."
    ),
    cookie_json: Optional[Path] = typer.Option(
        None, "--cookie-json", help="Path to JSON file with exported cookies (from browser developer tools)."
    ),
    local: bool = typer.Option(
        get_cli_default("convert", "local", False),
        "--local",
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
        "--simulate-browser",
        help="Use browser-like headers instead of identifying as html2md crawler.",
    ),
    insecure: bool = typer.Option(
        get_cli_default("convert", "insecure", False),
        "--insecure",
        "--no-verify-ssl",
        help="Disable SSL certificate verification. Only use with hosts you trust "
        "(e.g. internal servers with self-signed certificates).",
    ),
    download_images: bool = typer.Option(
        get_cli_default("convert", "download_images", False),
        "--download-images",
        help="Download images from the webpage and store them locally.",
    ),
    images_dir: str = typer.Option(
        get_cli_default("convert", "images_dir", "images"),
        "--images-dir",
        help="Directory name for storing downloaded images.",
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", help="Set logging level."
    ),
    debug_log: Optional[Path] = typer.Option(
        None, "--debug-log", help="Write debug logs to specified file."
    ),
    fancy: bool = typer.Option(
        get_cli_default("convert", "fancy", False), "--fancy", help="Enable fancy output with progress bars and decorations."
    ),
):
    """Convert HTML content from URLs or local files to Markdown."""
    set_log_level(log_level, debug_log)

    # Handle config updates for cookie path
    if cookie_path:
        config = load_config()
        config.setdefault('browser', {}).setdefault('custom_path', {})
        if browser:
            config['browser']['custom_path'][browser] = str(cookie_path)
        else:
            pref_browser = config.get('browser', {}).get('preferred', 'chrome')
            config['browser']['custom_path'][pref_browser] = str(cookie_path)
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
                    trim=trim, 
                    output=output, 
                    no_cookies=no_cookies, 
                    browser_cookies=browser_cookies, 
                    browser=browser,
                    cookie_path=cookie_path,
                    cookie_json=cookie_json,
                    local=local,
                    download_images=download_images,
                    images_dir=images_dir,
                    enhanced_headers=enhanced_headers,
                    user_agent_contact=user_agent_contact,
                    simulate_browser=simulate_browser,
                    insecure=insecure,
                    progress=progress,
                    task_id=task_id
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
                trim=trim,
                output=output,
                no_cookies=no_cookies,
                browser_cookies=browser_cookies,
                browser=browser,
                cookie_path=cookie_path,
                cookie_json=cookie_json,
                local=local,
                download_images=download_images,
                images_dir=images_dir,
                enhanced_headers=enhanced_headers,
                user_agent_contact=user_agent_contact,
                simulate_browser=simulate_browser,
                insecure=insecure,
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
    trim: bool = typer.Option(
        get_cli_default("batch", "trim", True),
        "--trim/--no-trim",
        help="Enable/disable trimming based on domain-specific rules.",
    ),
    flatten_output: bool = typer.Option(
        get_cli_default("batch", "flatten", False),
        "--flatten",
        help="Output files directly to domain directories (e.g., 'docs.github.com/')",
    ),
    flatten_all: bool = typer.Option(
        get_cli_default("batch", "flatten_all", False),
        "--flatten-all",
        help="Output all files to a single directory, ignoring domain structure",
    ),
    hierarchical: bool = typer.Option(
        get_cli_default("batch", "hierarchical", False),
        "--hierarchical",
        help="Create hierarchical domain folders (e.g., com/jetbrains/www)",
    ),
    visualize: bool = typer.Option(
        get_cli_default("batch", "visualize", False),
        "--visualize",
        help="Display a visual representation of the output directory structure.",
    ),
    report: Optional[Path] = typer.Option(
        None,
        "--report",
        help="Generate a detailed Markdown report of the process.",
    ),
    insecure: bool = typer.Option(
        get_cli_default("batch", "insecure", False),
        "--insecure",
        "--no-verify-ssl",
        help="Disable SSL certificate verification. Only use with hosts you trust "
        "(e.g. internal servers with self-signed certificates).",
    ),
    quiet: bool = typer.Option(
        get_cli_default("batch", "quiet", False),
        "--quiet",
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

    # Validate flatten options
    if flatten_output and flatten_all:
        console.print("[bold red]Error:[/bold red] Cannot use both --flatten and --flatten-all options together.")
        raise typer.Exit(1)
    if (flatten_output or flatten_all) and hierarchical:
        console.print("[bold red]Error:[/bold red] Cannot use --hierarchical with --flatten or --flatten-all options.")
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
    processed_count = 0
    url_to_file_mapping = {}

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

            # Process the files with callback for updates
            processed_count, url_to_file_mapping = process_markdown_links(
                expanded_files,
                output_dir,
                trim=trim,
                progress_callback=progress_callback,
                flatten_output=flatten_output,
                flatten_all=flatten_all,
                hierarchical_domains=hierarchical,
                verify_ssl=not insecure,
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
  - Trim: {trim}
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

    # Final success message
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
        get_cli_default("crawl", "max_depth", 3), "--max-depth", help="Maximum link depth to follow."
    ),
    max_pages: int = typer.Option(
        get_cli_default("crawl", "max_pages", 100), "--max-pages", help="Maximum number of pages to crawl."
    ),
    delay: float = typer.Option(
        get_cli_default("crawl", "delay", 0.0), 
        "--delay", 
        help="Delay between requests in seconds (e.g., 1.5). A random jitter of ±30% will be added."
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
        "--simulate-browser",
        help="Use browser-like headers instead of identifying as html2md crawler.",
    ),
    insecure: bool = typer.Option(
        get_cli_default("crawl", "insecure", False),
        "--insecure",
        "--no-verify-ssl",
        help="Disable SSL certificate verification. Only use with hosts you trust "
        "(e.g. internal servers with self-signed certificates).",
    ),
    polite: bool = typer.Option(
        get_cli_default("crawl", "polite", False),
        "--polite",
        help="Enable conservative sequential crawling with slower adaptive delays.",
    ),
    show_progress: bool = typer.Option(
        get_cli_default("crawl", "show_progress", True),
        "--progress/--no-progress",
        help="Show crawling progress and statistics.",
    ),
    trim: bool = typer.Option(
        get_cli_default("crawl", "trim", True),
        "--trim/--no-trim",
        help="Enable/disable trimming based on domain-specific rules.",
    ),
    flatten_output: bool = typer.Option(
        get_cli_default("crawl", "flatten", False),
        "--flatten",
        help="Output files directly to domain directories (e.g., 'docs.github.com/')",
    ),
    hierarchical: bool = typer.Option(
        get_cli_default("crawl", "hierarchical", False),
        "--hierarchical",
        help="Create hierarchical domain folders (e.g., com/jetbrains/www)",
    ),
    visualize: bool = typer.Option(
        get_cli_default("crawl", "visualize", False),
        "--visualize",
        help="Display a visual representation of the output directory structure.",
    ),
    quiet: bool = typer.Option(
        get_cli_default("crawl", "quiet", False),
        "--quiet",
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
        console.print(f"[bold]Respect robots.txt:[/bold] {'Yes' if respect_robots else 'No'}")
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
                header_settings = config.get("headers", {})
                
                header_config = HeaderConfig(
                    use_enhanced_user_agent=enhanced_headers,
                    contact_email=user_agent_contact if "@" in (user_agent_contact or "") else None,
                    contact_url=user_agent_contact if user_agent_contact and "@" not in user_agent_contact else None,
                    user_agent_name=header_settings.get("user_agent_name", "html2md"),
                    user_agent_version=header_settings.get("user_agent_version", "1.0"),
                    enable_compression=header_settings.get("enable_compression", True),
                    compression_methods=header_settings.get("compression_methods", "gzip, deflate, br"),
                    enable_conditional_requests=header_settings.get("enable_conditional_requests", True),
                    simulate_browser=simulate_browser,
                    browser_type=header_settings.get("browser_type", "chrome"),
                    respect_caching=header_settings.get("respect_caching", True),
                    include_accept_language=header_settings.get("include_accept_language", True),
                    preferred_language=header_settings.get("preferred_language", "en-US,en;q=0.9"),
                    custom_headers=header_settings.get("custom_headers", {})
                )
                
                # Build concurrent configuration from CLI options and config
                from html2md.network.concurrent_limiter import ConcurrentConfig, BackoffStrategy
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
                    backoff_multiplier=concurrent_settings.get("backoff_multiplier", 2.0),
                    error_threshold_for_backoff=concurrent_settings.get("error_threshold", 3),
                    retry_after_respect=concurrent_settings.get("respect_retry_after", True),
                    polite_delay_multiplier=concurrent_settings.get("polite_delay_multiplier", 2.0)
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
                        trim=trim,
                        progress_callback=progress_callback,
                        flatten_output=flatten_output,
                        hierarchical_domains=hierarchical,
                        verify_ssl=not insecure,
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


@app.callback()
def main(
    log_level: LogLevel = typer.Option(
        LogLevel.WARNING, "--log-level", help="Set logging level."
    ),
    debug_log: Optional[Path] = typer.Option(
        None, "--debug-log", help="Write debug logs to specified file."
    ),
    banner: bool = typer.Option(
        False, "--banner", help="Display the welcome banner."
    ),
):
    """Main entry point for the application."""
    set_log_level(log_level, debug_log)

    # Show welcome banner if explicitly requested
    if banner:
        show_welcome_banner()


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


# State management commands
@state_app.command(name="list")
def list_states():
    """List all resumable crawl states."""
    state_manager = StateManager()
    crawls = state_manager.list_resumable_crawls()
    
    if not crawls:
        console.print("[yellow]No resumable crawls found.[/yellow]")
        return
    
    table = Table(title="Resumable Crawls", show_header=True, header_style="bold blue")
    table.add_column("ID", style="cyan", width=8)
    table.add_column("URL", style="green")
    table.add_column("Created", style="yellow")
    table.add_column("Last Checkpoint", style="yellow")
    table.add_column("Progress", style="magenta")
    
    for crawl in crawls:
        progress = f"{crawl['urls_processed']}/{crawl['urls_processed'] + crawl['urls_queued']}"
        table.add_row(
            crawl['crawl_id'][:8],
            crawl['start_url'],
            crawl['created_at'][:19],
            crawl['last_checkpoint'][:19],
            progress
        )
    
    console.print(table)


@state_app.command(name="resume")
def resume_crawl(
    crawl_id: str = typer.Argument(..., help="ID of the crawl to resume"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", "-o", help="Override output directory")
):
    """Resume an interrupted crawl."""
    state_manager = StateManager()
    crawl_state = state_manager.load_state(crawl_id)
    
    if not crawl_state:
        console.print(f"[red]Crawl {crawl_id} not found.[/red]")
        raise typer.Exit(1)
    
    # Use provided output dir or original
    if output_dir:
        crawl_state.output_dir = output_dir
    
    console.print(f"[green]Resuming crawl {crawl_id}[/green]")
    console.print(f"[blue]URL:[/blue] {crawl_state.start_url}")
    console.print(f"[blue]Output:[/blue] {crawl_state.output_dir}")
    console.print(f"[blue]Progress:[/blue] {crawl_state.statistics.urls_processed} URLs processed")
    
    # Resume the crawl
    try:
        resume_options = dict(crawl_state.config)
        for explicit_option in (
            "start_url",
            "output_dir",
            "state_manager",
            "resume_crawl_id",
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
        console.print(f"[blue]Final count:[/blue] {result.processed_count} URLs processed")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error resuming crawl: {e}[/red]")
        raise typer.Exit(1)


@state_app.command(name="clean")
def clean_states(
    days: int = typer.Option(30, "--days", "-d", help="Remove states older than N days"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation")
):
    """Clean up old crawl states."""
    state_manager = StateManager()
    
    if not force:
        confirm = Confirm.ask(f"Remove crawl states older than {days} days?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            return
    
    cleaned = state_manager.clean_old_states(days)
    console.print(f"[green]Cleaned {cleaned} old state files.[/green]")


@state_app.command(name="export")
def export_state(
    crawl_id: str = typer.Argument(..., help="ID of the crawl to export"),
    output_file: Path = typer.Argument(..., help="Output file for exported state")
):
    """Export a crawl state to a file."""
    state_manager = StateManager()
    
    try:
        state_manager.export_state(crawl_id, output_file)
        console.print(f"[green]✓ State exported to {output_file}[/green]")
    except Exception as e:
        console.print(f"[red]Error exporting state: {e}[/red]")


@state_app.command(name="import")
def import_state(
    input_file: Path = typer.Argument(..., help="State file to import")
):
    """Import a crawl state from a file."""
    state_manager = StateManager()
    
    try:
        new_crawl_id = state_manager.import_state(input_file)
        console.print(f"[green]✓ State imported with ID: {new_crawl_id}[/green]")
    except Exception as e:
        console.print(f"[red]Error importing state: {e}[/red]")


@state_app.command(name="info")
def show_state_info(
    crawl_id: str = typer.Argument(..., help="ID of the crawl to show info for")
):
    """Show detailed information about a crawl state."""
    state_manager = StateManager()
    crawl_state = state_manager.load_state(crawl_id)
    
    if not crawl_state:
        console.print(f"[red]Crawl {crawl_id} not found.[/red]")
        return
    
    # Create info table
    info_table = Table(title=f"Crawl State: {crawl_id}", show_header=False)
    info_table.add_column("Property", style="cyan", width=20)
    info_table.add_column("Value", style="green")
    
    info_table.add_row("ID", crawl_state.crawl_id)
    info_table.add_row("Start URL", crawl_state.start_url)
    info_table.add_row("Output Dir", crawl_state.output_dir)
    info_table.add_row("Created", crawl_state.created_at)
    info_table.add_row("Last Checkpoint", crawl_state.last_checkpoint)
    info_table.add_row("URLs Processed", str(crawl_state.statistics.urls_processed))
    info_table.add_row("URLs Failed", str(crawl_state.statistics.urls_failed))
    info_table.add_row("URLs Queued", str(len(crawl_state.urls_queued)))
    info_table.add_row("Checkpoints", str(len(crawl_state.checkpoints)))
    
    console.print(info_table)
    
    # Show recent checkpoints
    if crawl_state.checkpoints:
        console.print("\n[bold blue]Recent Checkpoints:[/bold blue]")
        checkpoint_table = Table(show_header=True, header_style="bold blue")
        checkpoint_table.add_column("Time", style="yellow")
        checkpoint_table.add_column("Trigger", style="cyan")
        checkpoint_table.add_column("Message", style="green")
        
        for checkpoint in crawl_state.checkpoints[-5:]:  # Last 5 checkpoints
            checkpoint_table.add_row(
                checkpoint.timestamp[:19],
                checkpoint.trigger,
                checkpoint.message or "No message"
            )
        
        console.print(checkpoint_table)


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
    try:
        save_config(config)
    except ConfigValidationError as error:
        console.print(f"[bold red]Error:[/bold red] {error}")
        raise typer.Exit(1)

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
        save_config(config)

        console.print(f"[bold green]Deleted:[/bold green] {path}")
        console.print("[dim]Previous value was:[/dim]")
        json_str = json.dumps(deleted_value, indent=2)
        syntax = Syntax(json_str, "json", theme="monokai")
        console.print(syntax)


@config_app.command(name="add-domain")
def add_domain_config(
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain name (e.g., example.com). If not provided, runs in interactive mode."),
    quick: bool = typer.Option(False, "--quick", "-q", help="Quick mode: add domain with default settings without prompts")
):
    """Add domain-specific configuration. Use --domain to specify domain directly, or run interactively."""
    config = load_config()

    # Domain name
    if domain is None:
        domain = Prompt.ask("[bold blue]Enter domain name[/bold blue] (e.g., example.com)")

    # Check if domain already exists
    if domain in config.get("domains", {}):
        if quick:
            console.print(f"[yellow]Domain '{domain}' already exists. Use interactive mode to update it.[/yellow]")
            return
        elif not Confirm.ask(
            f"Domain '{domain}' already exists. Do you want to update it?"
        ):
            return

    # Initialize domain config if it doesn't exist
    if "domains" not in config:
        config["domains"] = {}
    if domain not in config["domains"]:
        config["domains"][domain] = {}

    # In quick mode, just add the domain with empty config
    if quick:
        # Save the config
        save_config(config)
        console.print(f"[bold green]✓[/bold green] Domain '{domain}' added with default settings")
        return

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
    save_config(config)

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
        "[bold red]Warning:[/bold red] This will reset all settings to default values. Continue?",
        default=False
    ):
        console.print("[yellow]Reset cancelled[/yellow]")
        return

    # Create backup before reset
    backup_manager = get_backup_manager()
    backup_path = backup_manager.create_backup(reason="manual-reset")

    if backup_path:
        console.print(f"[dim]Backup created: {backup_path}[/dim]")

    # Write default config using safe save
    save_config(DEFAULT_CONFIG)

    console.print("[bold green]Configuration reset to default values.[/bold green]")
    if backup_path:
        console.print(f"[dim]Previous config backed up to: {backup_path}[/dim]")

    # Show the reset config
    json_str = json.dumps(DEFAULT_CONFIG, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)

    console.print(Panel(syntax, title="Default Configuration", border_style="yellow"))


@config_app.command(name="set-cli-default")
def set_cli_default(
    command: str = typer.Argument(..., help="Command name (convert, batch, crawl)"),
    option: str = typer.Argument(..., help="Option name (e.g., browser_cookies, hierarchical)"),
    value: Optional[str] = typer.Argument(None, help="Typed value to set; use null for optional values"),
    reset: bool = typer.Option(False, "--reset", help="Reset this option to its built-in default"),
):
    """Set a default value for a CLI option."""
    config = load_config()
    
    # Ensure cli_defaults exists
    if "cli_defaults" not in config:
        config["cli_defaults"] = deepcopy(DEFAULT_CONFIG["cli_defaults"])
    
    # Validate command
    if command not in config["cli_defaults"]:
        console.print(f"[bold red]Error:[/bold red] Unknown command '{command}'. Valid commands: convert, batch, crawl")
        raise typer.Exit(1)
    
    # Validate option exists in the command defaults
    if option not in config["cli_defaults"][command]:
        valid_options = ", ".join(config["cli_defaults"][command].keys())
        console.print(f"[bold red]Error:[/bold red] Unknown option '{option}' for command '{command}'.")
        console.print(f"Valid options: {valid_options}")
        raise typer.Exit(1)
    
    config_path = ("cli_defaults", command, option)
    try:
        if reset:
            if value is not None:
                raise ConfigValidationError(["value cannot be combined with --reset"])
            parsed_value = default_at_path(DEFAULT_CONFIG, config_path)
        else:
            if value is None:
                raise ConfigValidationError(["a value or --reset is required"])
            parsed_value = parse_cli_value(DEFAULT_CONFIG, config_path, value)
    except ConfigValidationError as error:
        console.print(f"[bold red]Error:[/bold red] {error}")
        raise typer.Exit(1)
    
    # Set the value
    config["cli_defaults"][command][option] = parsed_value
    
    # Save the updated config
    save_config(config)
    
    console.print(f"[bold green]Updated:[/bold green] {command}.{option} = {parsed_value}")
    console.print(f"\n[bold blue]Tip:[/bold blue] This will be the default value for --{option.replace('_', '-')} when using 'html2md {command}'")


@config_app.command(name="list-cli-defaults")
def list_cli_defaults():
    """List all CLI default settings."""
    config = load_config()
    cli_defaults = config.get("cli_defaults", {})
    
    if not cli_defaults:
        console.print("[yellow]No CLI defaults configured yet.[/yellow]")
        return
    
    # Create a table for each command
    for command, options in cli_defaults.items():
        table = Table(title=f"{command.capitalize()} Command Defaults")
        table.add_column("Option", style="cyan")
        table.add_column("Default Value", style="green")
        table.add_column("CLI Flag", style="magenta")
        
        for option, value in options.items():
            cli_flag = f"--{option.replace('_', '-')}"
            table.add_row(option, str(value), cli_flag)
        
        console.print(table)
        console.print()  # Add spacing between tables


@config_app.command(name="show-options")
def show_config_options():
    """Show all available configuration options with descriptions."""
    console.print(Panel.fit("[bold cyan]HTML2MD Configuration Options[/bold cyan]", border_style="cyan"))
    
    # CLI Defaults Section
    console.print("\n[bold yellow]CLI Defaults[/bold yellow]")
    console.print("Configure default values for command-line options\n")
    
    cli_options = {
        "convert": {
            "browser_cookies": ("bool", "Use cookies from browser automatically"),
            "no_cookies": ("bool", "Disable cookie loading by default"),
            "browser": ("str", "Default browser for cookie extraction (chrome/firefox/edge/safari)"),
            "trim": ("bool", "Enable/disable content trimming"),
            "download_images": ("bool", "Download images from pages"),
            "images_dir": ("str", "Directory name for downloaded images"),
            "fancy": ("bool", "Enable fancy output with progress bars"),
            "local": ("bool", "Treat sources as local files by default")
        },
        "batch": {
            "hierarchical": ("bool", "Create hierarchical domain folders (com/example/www)"),
            "flatten": ("bool", "Output files directly to domain directories"),
            "flatten_all": ("bool", "Output all files to single directory"),
            "trim": ("bool", "Enable/disable content trimming"),
            "visualize": ("bool", "Show visual directory structure"),
            "quiet": ("bool", "Reduce output verbosity")
        },
        "crawl": {
            "hierarchical": ("bool", "Create hierarchical domain folders"),
            "flatten": ("bool", "Output files directly to domain directories"),
            "follow": ("str", "Link following strategy (domain-only/host-only/subdomain/regex)"),
            "max_depth": ("int", "Maximum crawl depth"),
            "max_pages": ("int", "Maximum pages to crawl"),
            "delay": ("float", "Delay between requests in seconds (with ±30% jitter)"),
            "respect_robots": ("bool", "Respect robots.txt rules and crawl-delay"),
            "rate_limit": ("int", "Maximum requests per minute with circuit breaker"),
            "trim": ("bool", "Enable/disable content trimming"),
            "visualize": ("bool", "Show visual directory structure"),
            "quiet": ("bool", "Reduce output verbosity")
        }
    }
    
    for command, options in cli_options.items():
        table = Table(title=f"{command.capitalize()} Command Options", title_style="bold blue")
        table.add_column("Option", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Description", style="white")
        
        for option, (opt_type, description) in options.items():
            table.add_row(option, opt_type, description)
        
        console.print(table)
        console.print()
    
    # Domain Configuration Section
    console.print("[bold yellow]Domain-Specific Trimming[/bold yellow]")
    console.print("Configure content trimming rules per domain\n")
    
    domain_table = Table(title="Domain Configuration Options")
    domain_table.add_column("Setting", style="cyan")
    domain_table.add_column("Description", style="white")
    
    domain_table.add_row("footer_marker", "Text that marks where to trim content")
    domain_table.add_row("path_rules", "Path-specific trimming rules")
    domain_table.add_row("path_rules.*.h1_occurrence", "Which h1 heading to keep (e.g., 2 = second h1)")
    domain_table.add_row("path_rules.*.footer_marker", "Path-specific footer marker")
    
    console.print(domain_table)
    console.print()
    
    # Browser Configuration Section
    console.print("[bold yellow]Browser Configuration[/bold yellow]")
    console.print("Configure browser cookie extraction settings\n")
    
    browser_table = Table(title="Browser Options")
    browser_table.add_column("Setting", style="cyan")
    browser_table.add_column("Description", style="white")
    
    browser_table.add_row("preferred", "Default browser (chrome/firefox/edge/safari)")
    browser_table.add_row("custom_path.<browser>", "Custom path to browser cookie database")
    
    console.print(browser_table)
    console.print()
    
    # Examples
    console.print("[bold yellow]Examples[/bold yellow]\n")
    
    examples = [
        ("Set browser cookies as default", "html2md config set-cli-default convert browser_cookies true"),
        ("Enable hierarchical folders", "html2md config set-cli-default batch hierarchical true"),
        ("Set max crawl pages", "html2md config set-cli-default crawl max_pages 500"),
        ("Add domain trimming rule", "html2md config add-domain --domain example.com"),
        ("Set config value directly", "html2md config set browser.preferred firefox"),
        ("View current config", "html2md config show"),
    ]
    
    for desc, cmd in examples:
        console.print(f"[bold blue]{desc}:[/bold blue]")
        console.print(f"  [dim]$[/dim] {cmd}\n")


@config_app.command(name="backup")
def backup_config_command():
    """Create a manual backup of the current configuration."""
    backup_manager = get_backup_manager()
    backup_path = backup_manager.create_backup(reason="manual")

    if backup_path:
        console.print(f"[green]✓ Backup created:[/green] {backup_path}")
    else:
        console.print("[red]Failed to create backup[/red]")
        raise typer.Exit(1)


@config_app.command(name="list-backups")
def list_backups_command():
    """List all available configuration backups."""
    backup_manager = get_backup_manager()
    backups = backup_manager.list_backups()

    if not backups:
        console.print("[yellow]No backups found[/yellow]")
        return

    table = Table(title="Configuration Backups", border_style="cyan")
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Time", style="cyan", no_wrap=True)
    table.add_column("Reason", style="green")
    table.add_column("Size", style="yellow", justify="right")
    table.add_column("Path", style="dim")

    for backup in backups:
        # Parse filename: config.20251029_143022.manual.json
        parts = backup.stem.split('.')
        if len(parts) >= 3:
            timestamp = parts[1]
            reason = parts[2] if len(parts) > 2 else "unknown"

            # Format for display: YYYYMMDD_HHMMSS
            if len(timestamp) >= 15 and '_' in timestamp:
                date_part = timestamp[:8]  # YYYYMMDD
                time_part = timestamp[9:]  # HHMMSS

                # Format: YYYY-MM-DD
                date_str = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
                # Format: HH:MM:SS
                time_str = f"{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"

                size = backup.stat().st_size
                size_str = f"{size:,}"

                table.add_row(date_str, time_str, reason, size_str, str(backup))

    console.print(table)


@config_app.command(name="restore")
def restore_config_command(
    backup_file: Optional[Path] = typer.Argument(
        None,
        help="Path to backup file (or omit to restore most recent)"
    )
):
    """Restore configuration from a backup file."""
    backup_manager = get_backup_manager()

    # Determine which backup to restore
    if backup_file is None:
        backups = backup_manager.list_backups()
        if not backups:
            console.print("[red]No backups available to restore[/red]")
            raise typer.Exit(1)
        backup_file = backups[0]
        console.print(f"[cyan]Restoring most recent backup:[/cyan] {backup_file.name}")

    # Confirm restore
    if not Confirm.ask(
        f"[yellow]⚠️  Restore config from {backup_file.name}?[/yellow]",
        default=False
    ):
        console.print("[yellow]Restore cancelled[/yellow]")
        return

    # Create backup of current config before restoring
    current_backup = backup_manager.create_backup(reason="pre-restore")

    # Restore
    if backup_manager.restore_backup(backup_file):
        console.print("[green]✓ Configuration restored successfully[/green]")
        if current_backup:
            console.print(f"[dim]Previous config backed up to: {current_backup.name}[/dim]")
    else:
        console.print("[red]Failed to restore backup[/red]")
        raise typer.Exit(1)


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
    console = Console(theme=html2md_theme, color_system=color_system)

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
