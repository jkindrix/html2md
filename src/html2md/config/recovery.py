"""
Configuration error recovery handler.

This module provides intelligent, context-aware recovery from configuration
file errors. It adapts its behavior based on execution context (interactive
terminal vs automated script) and provides user-friendly recovery options.
"""

import json
import logging
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict

from rich.console import Console
from rich.prompt import Confirm, Prompt

logger = logging.getLogger(__name__)
console = Console()


class RecoveryAction(Enum):
    """Available recovery actions for corrupt configuration."""

    USE_DEFAULTS = "defaults"
    RESTORE_BACKUP = "backup"
    EXIT = "exit"
    MANUAL_FIX = "manual"


class ConfigRecoveryHandler:
    """
    Handles configuration file recovery scenarios with context awareness.

    This class manages recovery from configuration errors (JSON parsing failures,
    missing files) and adapts its behavior based on execution context:

    **Interactive Mode (TTY):**
    - Presents user with clear options via Rich prompts
    - Allows restoration from backup
    - Requires confirmation for destructive actions
    - Provides option to exit and manually fix

    **Non-Interactive Mode (CI/CD, scripts):**
    - Automatically attempts backup restoration
    - Falls back to default config in memory only
    - Never blocks on user input
    - Never overwrites config file without explicit command

    The handler follows the principle: User data is more valuable than
    application's ability to run once.
    """

    def __init__(
        self,
        config_file: Path,
        backup_manager,
        default_config: Dict[str, Any]
    ):
        """
        Initialize recovery handler.

        Args:
            config_file: Path to the configuration file
            backup_manager: ConfigBackupManager instance for backup operations
            default_config: Default configuration dictionary to use as fallback
        """
        self.config_file = config_file
        self.backup_manager = backup_manager
        self.default_config = default_config
        self.is_interactive = sys.stdin.isatty() and sys.stdout.isatty()

    def handle_corrupt_config(self, error: Exception) -> Dict[str, Any]:
        """
        Handle corrupt configuration file with context-aware recovery.

        This is the main entry point for recovery. It:
        1. Saves the corrupt config for debugging
        2. Logs the error with full details
        3. Determines appropriate recovery action based on context
        4. Executes recovery and returns resulting config

        Args:
            error: The exception that occurred during config loading
                  (JSONDecodeError, FileNotFoundError, etc.)

        Returns:
            Configuration dictionary to use (recovered, default, or restored)

        Raises:
            SystemExit: If user chooses to exit or manual fix in interactive mode

        Example:
            >>> handler = ConfigRecoveryHandler(config_file, backup_mgr, defaults)
            >>> try:
            ...     config = json.load(config_file)
            ... except json.JSONDecodeError as e:
            ...     config = handler.handle_corrupt_config(e)
        """
        # Save corrupted config for user debugging
        corrupt_path = self.backup_manager.save_corrupted_config()

        # Log error with context
        logger.error(
            f"Configuration file corrupt: {type(error).__name__}: {error}"
        )
        logger.error(f"Config file location: {self.config_file}")

        if corrupt_path:
            logger.info(f"Corrupt config saved to: {corrupt_path}")

        # Determine recovery action based on context
        if self.is_interactive:
            action = self._prompt_user_recovery()
        else:
            action = self._non_interactive_recovery()

        # Execute recovery action
        return self._execute_recovery(action)

    def _prompt_user_recovery(self) -> RecoveryAction:
        """
        Prompt user for recovery action in interactive mode.

        Presents a clear, user-friendly interface with:
        - List of available backups (if any)
        - Recovery options with explanations
        - Confirmation for destructive actions

        Returns:
            Selected recovery action

        Example output:
            ⚠️  Configuration File Corrupt
            File: /home/user/.config/html2md/config.json

            Found 3 backup(s)
              1. 20251029_143100
              2. 20251029_143045
              3. 20251029_143022

            Recovery Options:
              R) Restore most recent backup
              D) Use default configuration (will lose custom settings)
              M) Exit and manually fix config file
              Q) Quit

            Choose recovery action [m]:
        """
        console.print("\n[bold red]⚠️  Configuration File Corrupt[/bold red]")
        console.print(f"File: [cyan]{self.config_file}[/cyan]")
        console.print()

        # Check for available backups
        backups = self.backup_manager.list_backups()

        # Build options list
        options = []
        valid_choices = []

        if backups:
            console.print(f"[green]Found {len(backups)} backup(s)[/green]")
            for i, backup in enumerate(backups[:3], 1):
                # Extract timestamp from filename: config.20251029_143100.reason.json
                parts = backup.stem.split('.')
                if len(parts) >= 2:
                    timestamp = parts[1]
                    console.print(f"  {i}. {timestamp}")
            console.print()
            options.append("R) Restore most recent backup")
            valid_choices.append('r')

        options.extend([
            "D) Use default configuration (will lose custom settings)",
            "M) Exit and manually fix config file",
            "Q) Quit"
        ])
        valid_choices.extend(['d', 'm', 'q'])

        # Display options
        console.print("[bold]Recovery Options:[/bold]")
        for option in options:
            console.print(f"  {option}")
        console.print()

        # Get user choice
        while True:
            choice = Prompt.ask(
                "Choose recovery action",
                choices=valid_choices,
                default='m',
                show_choices=False
            ).lower()

            if choice == 'r' and backups:
                return RecoveryAction.RESTORE_BACKUP
            elif choice == 'd':
                # Confirm destructive action
                console.print()
                if Confirm.ask(
                    "[yellow]⚠️  This will reset all custom settings. Continue?[/yellow]",
                    default=False
                ):
                    return RecoveryAction.USE_DEFAULTS
                else:
                    console.print("[dim]Cancelled. Choose another option.[/dim]\n")
                    # Loop back to prompt
            elif choice == 'm':
                return RecoveryAction.MANUAL_FIX
            elif choice == 'q':
                return RecoveryAction.EXIT

    def _non_interactive_recovery(self) -> RecoveryAction:
        """
        Determine recovery action in non-interactive mode (CI/CD, scripts).

        Strategy:
        1. Check for available backups
        2. If backups exist, attempt automatic restoration
        3. If no backups or restoration fails, use defaults IN MEMORY ONLY
        4. Never write to disk without explicit user command

        Returns:
            Recovery action (RESTORE_BACKUP or USE_DEFAULTS)

        Note:
            This method NEVER blocks or requires user input.
            It logs all decisions for audit trail.
        """
        logger.info("Running in non-interactive mode (no TTY)")

        backups = self.backup_manager.list_backups()

        if backups:
            logger.info(
                f"Found {len(backups)} backup(s), attempting automatic restoration"
            )
            return RecoveryAction.RESTORE_BACKUP
        else:
            logger.warning(
                "No backups available, will use default config in memory only"
            )
            logger.warning(
                "Config file NOT overwritten - fix manually or use 'config reset'"
            )
            return RecoveryAction.USE_DEFAULTS

    def _execute_recovery(self, action: RecoveryAction) -> Dict[str, Any]:
        """
        Execute the selected recovery action.

        Args:
            action: Recovery action to execute

        Returns:
            Configuration dictionary to use

        Raises:
            SystemExit: If action is EXIT or MANUAL_FIX
        """
        if action == RecoveryAction.RESTORE_BACKUP:
            return self._execute_restore_backup()

        elif action == RecoveryAction.USE_DEFAULTS:
            return self._execute_use_defaults()

        elif action == RecoveryAction.MANUAL_FIX:
            console.print(
                f"\n[cyan]Please fix the config file:[/cyan] {self.config_file}"
            )
            console.print(
                "[dim]The corrupt version was saved with .corrupt extension[/dim]"
            )
            logger.info("User chose to manually fix config file, exiting")
            sys.exit(1)

        elif action == RecoveryAction.EXIT:
            console.print("[yellow]Exiting without changes[/yellow]")
            logger.info("User chose to exit without recovery")
            sys.exit(0)

    def _execute_restore_backup(self) -> Dict[str, Any]:
        """
        Execute backup restoration recovery action.

        Attempts to restore from the most recent backup. If restoration
        succeeds, loads and returns the restored config. If it fails,
        falls back to using defaults.

        Returns:
            Configuration dictionary (restored or default)
        """
        backups = self.backup_manager.list_backups()

        if not backups:
            logger.error("No backups available for restoration")
            if self.is_interactive:
                console.print("[red]No backups found, using defaults instead[/red]")
            return self._execute_use_defaults()

        # Attempt restoration
        most_recent_backup = backups[0]
        logger.info(f"Attempting to restore from: {most_recent_backup}")

        if self.backup_manager.restore_backup(most_recent_backup):
            # Restoration succeeded, load the restored config
            if self.is_interactive:
                console.print("[green]✓ Config restored from backup[/green]")
            logger.info("Successfully restored config from backup")

            # Load and return restored config
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load restored config: {e}")
                if self.is_interactive:
                    console.print(
                        "[red]Restored config is invalid, using defaults[/red]"
                    )
                return self._execute_use_defaults()
        else:
            # Restoration failed
            logger.error("Backup restoration failed")
            if self.is_interactive:
                console.print("[red]Backup restoration failed, using defaults[/red]")
            return self._execute_use_defaults()

    def _execute_use_defaults(self) -> Dict[str, Any]:
        """
        Execute use-defaults recovery action.

        CRITICAL BEHAVIOR:
        - In NON-INTERACTIVE mode: Returns defaults IN MEMORY ONLY,
          does NOT write to disk
        - In INTERACTIVE mode: Creates backup, then writes defaults to disk

        This ensures automated scripts never accidentally overwrite user
        config, while interactive users get a clean slate if they explicitly
        confirm.

        Returns:
            Default configuration dictionary
        """
        if self.is_interactive:
            # Interactive: User explicitly confirmed, so write to disk
            logger.info("Writing default config to disk (user confirmed)")

            # Create backup of corrupt file before overwriting
            self.backup_manager.create_backup(reason="pre-reset")

            # Write defaults atomically
            from html2md.config.writer import atomic_write_json
            atomic_write_json(self.config_file, self.default_config, private=True)

            console.print("[yellow]Configuration reset to defaults[/yellow]")
            console.print(
                f"[dim]Backup created in: {self.backup_manager.backup_dir}[/dim]"
            )
        else:
            # Non-interactive: DO NOT write to disk
            logger.warning("Using default config IN MEMORY ONLY (non-interactive)")
            logger.warning(
                f"Config file preserved at: {self.config_file}"
            )
            logger.warning(
                "To permanently reset, run: html2md config reset"
            )

        return self.default_config.copy()
