"""Configuration-management command group for the html2md CLI."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

from html2md.config.loader import (
    CONFIG_FILE,
    DEFAULT_CONFIG,
    get_backup_manager,
    load_config,
    save_config,
)
from html2md.config.schema import (
    ConfigValidationError,
    default_at_path,
    parse_cli_value,
)

console = Console()
config_app = typer.Typer(
    help="Manage html2md configuration settings.",
    add_completion=False,
)


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
    domain: Optional[str] = typer.Option(
        None,
        "--domain",
        "-d",
        help="Domain name (e.g., example.com). If not provided, runs in interactive mode.",
    ),
    quick: bool = typer.Option(
        False,
        "--quick",
        "-q",
        help="Quick mode: add domain with default settings without prompts",
    ),
):
    """Add domain-specific configuration. Use --domain to specify domain directly, or run interactively."""
    config = load_config()

    # Domain name
    if domain is None:
        domain = Prompt.ask(
            "[bold blue]Enter domain name[/bold blue] (e.g., example.com)"
        )

    # Check if domain already exists
    if domain in config.get("domains", {}):
        if quick:
            console.print(
                f"[yellow]Domain '{domain}' already exists. Use interactive mode to update it.[/yellow]"
            )
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
        console.print(
            f"[bold green]✓[/bold green] Domain '{domain}' added with default settings"
        )
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
        default=False,
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
    option: str = typer.Argument(
        ..., help="Option name (e.g., browser_cookies, hierarchical)"
    ),
    value: Optional[str] = typer.Argument(
        None, help="Typed value to set; use null for optional values"
    ),
    reset: bool = typer.Option(
        False, "--reset", help="Reset this option to its built-in default"
    ),
):
    """Set a default value for a CLI option."""
    config = load_config()

    # Ensure cli_defaults exists
    if "cli_defaults" not in config:
        config["cli_defaults"] = deepcopy(DEFAULT_CONFIG["cli_defaults"])

    # Validate command
    if command not in config["cli_defaults"]:
        console.print(
            f"[bold red]Error:[/bold red] Unknown command '{command}'. Valid commands: convert, batch, crawl"
        )
        raise typer.Exit(1)

    # Validate option exists in the command defaults
    if option not in config["cli_defaults"][command]:
        valid_options = ", ".join(config["cli_defaults"][command].keys())
        console.print(
            f"[bold red]Error:[/bold red] Unknown option '{option}' for command '{command}'."
        )
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

    console.print(
        f"[bold green]Updated:[/bold green] {command}.{option} = {parsed_value}"
    )
    console.print(
        f"\n[bold blue]Tip:[/bold blue] This will be the default value for --{option.replace('_', '-')} when using 'html2md {command}'"
    )


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
    console.print(
        Panel.fit(
            "[bold cyan]HTML2MD Configuration Options[/bold cyan]", border_style="cyan"
        )
    )

    # CLI Defaults Section
    console.print("\n[bold yellow]CLI Defaults[/bold yellow]")
    console.print("Configure default values for command-line options\n")

    cli_options = {
        "convert": {
            "browser_cookies": ("bool", "Use cookies from browser automatically"),
            "no_cookies": ("bool", "Disable cookie loading by default"),
            "browser": (
                "str",
                "Default browser for cookie extraction (chrome/firefox/edge/safari)",
            ),
            "content_mode": ("str", "Content mode (full/main/selector)"),
            "selector": ("str", "CSS selector for selector content mode"),
            "download_images": ("bool", "Download images from pages"),
            "images_dir": ("str", "Directory name for downloaded images"),
            "metadata": ("bool", "Prepend YAML document metadata"),
            "render_js": ("bool", "Render JavaScript with optional Chromium"),
            "fancy": ("bool", "Enable fancy output with progress bars"),
            "local": ("bool", "Treat sources as local files by default"),
        },
        "batch": {
            "hierarchical": (
                "bool",
                "Create hierarchical domain folders (com/example/www)",
            ),
            "flatten": ("bool", "Output files directly to domain directories"),
            "flatten_all": ("bool", "Output all files to single directory"),
            "content_mode": ("str", "Content mode (full/main/selector)"),
            "selector": ("str", "CSS selector for selector content mode"),
            "metadata": ("bool", "Prepend YAML document metadata"),
            "visualize": ("bool", "Show visual directory structure"),
            "quiet": ("bool", "Reduce output verbosity"),
        },
        "crawl": {
            "hierarchical": ("bool", "Create hierarchical domain folders"),
            "flatten": ("bool", "Output files directly to domain directories"),
            "follow": (
                "str",
                "Link following strategy (domain-only/host-only/subdomain/regex)",
            ),
            "max_depth": ("int", "Maximum crawl depth"),
            "max_pages": ("int", "Maximum pages to crawl"),
            "delay": ("float", "Delay between requests in seconds (with ±30% jitter)"),
            "respect_robots": ("bool", "Respect robots.txt rules and crawl-delay"),
            "rate_limit": ("int", "Maximum requests per minute with circuit breaker"),
            "content_mode": ("str", "Content mode (full/main/selector)"),
            "selector": ("str", "CSS selector for selector content mode"),
            "metadata": ("bool", "Prepend YAML document metadata"),
            "visualize": ("bool", "Show visual directory structure"),
            "quiet": ("bool", "Reduce output verbosity"),
        },
    }

    for command, options in cli_options.items():
        table = Table(
            title=f"{command.capitalize()} Command Options", title_style="bold blue"
        )
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
    domain_table.add_row(
        "path_rules.*.h1_occurrence", "Which h1 heading to keep (e.g., 2 = second h1)"
    )
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
    browser_table.add_row(
        "custom_path.<browser>", "Custom path to browser cookie database"
    )

    console.print(browser_table)
    console.print()

    # Examples
    console.print("[bold yellow]Examples[/bold yellow]\n")

    examples = [
        (
            "Set browser cookies as default",
            "html2md config set-cli-default convert browser_cookies true",
        ),
        (
            "Enable hierarchical folders",
            "html2md config set-cli-default batch hierarchical true",
        ),
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
        parts = backup.stem.split(".")
        if len(parts) >= 3:
            timestamp = parts[1]
            reason = parts[2] if len(parts) > 2 else "unknown"

            # Format for display: YYYYMMDD_HHMMSS
            if len(timestamp) >= 15 and "_" in timestamp:
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
        None, help="Path to backup file (or omit to restore most recent)"
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
        f"[yellow]⚠️  Restore config from {backup_file.name}?[/yellow]", default=False
    ):
        console.print("[yellow]Restore cancelled[/yellow]")
        return

    # Create backup of current config before restoring
    current_backup = backup_manager.create_backup(reason="pre-restore")

    # Restore
    if backup_manager.restore_backup(backup_file):
        console.print("[green]✓ Configuration restored successfully[/green]")
        if current_backup:
            console.print(
                f"[dim]Previous config backed up to: {current_backup.name}[/dim]"
            )
    else:
        console.print("[red]Failed to restore backup[/red]")
        raise typer.Exit(1)
