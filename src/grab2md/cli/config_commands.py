"""Configuration-management command group for the grab2md CLI."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table

from grab2md.config.loader import (
    CONFIG_FILE,
    DEFAULT_CONFIG,
    get_backup_manager,
    load_config,
    save_config,
)
from grab2md.config.path_access import (
    ConfigPathError,
    delete_at_path,
    get_at_path,
    set_at_path,
    split_config_path,
)
from grab2md.config.schema import (
    ConfigValidationError,
    cli_option_rows,
    default_at_path,
    parse_config_value,
    parse_cli_value,
)

console = Console()
config_app = typer.Typer(
    help="Manage grab2md configuration settings.",
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
        ..., help="Config path (e.g., 'cli_defaults.convert.content_mode')"
    ),
    value: str = typer.Argument(..., help="Value to set"),
):
    """Set a configuration value at the specified path."""
    config = load_config()

    try:
        components = split_config_path(path)
        parsed_value = parse_config_value(DEFAULT_CONFIG, components, value)
        set_at_path(config, components, parsed_value)
    except (ConfigPathError, ConfigValidationError) as error:
        console.print(f"[bold red]Error:[/bold red] {error}")
        raise typer.Exit(1)

    # Save the updated config
    try:
        save_config(config)
    except ConfigValidationError as error:
        console.print(f"[bold red]Error:[/bold red] {error}")
        raise typer.Exit(1)

    console.print(f"[bold green]Updated:[/bold green] {path} = {value}")


@config_app.command(name="get")
def get_config_value(
    path: str = typer.Argument(
        ..., help="Config path (e.g., 'cli_defaults.convert.content_mode')"
    ),
):
    """Get a configuration value at the specified path."""
    config = load_config()

    try:
        current = get_at_path(config, split_config_path(path))
    except ConfigPathError as error:
        console.print(f"[bold red]Error:[/bold red] {error}")
        return

    # Display the value
    json_str = json.dumps(current, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai")

    console.print(f"[bold blue]{path}:[/bold blue]")
    console.print(syntax)


@config_app.command(name="delete")
def delete_config_value(
    path: str = typer.Argument(
        ..., help="Config path to delete (e.g., 'headers.custom_headers')"
    ),
):
    """Delete a configuration value at the specified path."""
    config = load_config()

    try:
        components = split_config_path(path)
        deleted_value = get_at_path(config, components)
    except ConfigPathError as error:
        console.print(f"[bold red]Error:[/bold red] {error}")
        return

    if Confirm.ask(f"Are you sure you want to delete '{path}'?"):
        delete_at_path(config, components)

        # Save the updated config
        save_config(config)

        console.print(f"[bold green]Deleted:[/bold green] {path}")
        console.print("[dim]Previous value was:[/dim]")
        json_str = json.dumps(deleted_value, indent=2)
        syntax = Syntax(json_str, "json", theme="monokai")
        console.print(syntax)


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
    command: str = typer.Argument(
        ...,
        help=("Defaults namespace (convert for direct conversion, batch, or crawl)"),
    ),
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
    invocation = "grab2md SOURCE" if command == "convert" else f"grab2md {command}"
    console.print(
        f"\n[bold blue]Tip:[/bold blue] This will be the default value for "
        f"--{option.replace('_', '-')} when using '{invocation}'"
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
        title = (
            "Direct Conversion Defaults (`convert` namespace)"
            if command == "convert"
            else f"{command.capitalize()} Command Defaults"
        )
        table = Table(title=title)
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
            "[bold cyan]GRAB2MD Configuration Options[/bold cyan]", border_style="cyan"
        )
    )

    # CLI Defaults Section
    console.print("\n[bold yellow]CLI Defaults[/bold yellow]")
    console.print("Configure default values for command-line options\n")

    for command, options in cli_option_rows(DEFAULT_CONFIG).items():
        title = (
            "Direct Conversion Options (`convert` namespace)"
            if command == "convert"
            else f"{command.capitalize()} Command Options"
        )
        table = Table(title=title, title_style="bold blue")
        table.add_column("Option", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Description", style="white")

        for option, opt_type, description in options:
            table.add_row(option, opt_type, description)

        console.print(table)
        console.print()

    # Browser Configuration Section
    console.print("[bold yellow]Browser Configuration[/bold yellow]")
    console.print("Configure browser cookie extraction settings\n")

    browser_table = Table(title="Browser Options")
    browser_table.add_column("Setting", style="cyan")
    browser_table.add_column("Description", style="white")

    browser_table.add_row("preferred", "Default browser (chrome/firefox)")
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
            "grab2md config set-cli-default convert browser_cookies true",
        ),
        (
            "Enable hierarchical folders",
            "grab2md config set-cli-default batch hierarchical true",
        ),
        ("Set max crawl pages", "grab2md config set-cli-default crawl max_pages 500"),
        (
            "Use a generic selector",
            "grab2md config set-cli-default convert content_mode selector && "
            "grab2md config set-cli-default convert selector 'main article'",
        ),
        ("Set config value directly", "grab2md config set browser.preferred firefox"),
        ("View current config", "grab2md config show"),
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
