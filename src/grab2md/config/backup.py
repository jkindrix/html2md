"""
Configuration backup management.

This module provides comprehensive backup functionality for configuration files,
including timestamped backups, automatic cleanup, corruption preservation, and
restore capabilities.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from grab2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger(__name__)


class ConfigBackupManager:
    """
    Manages configuration file backups with versioning and cleanup.

    This class provides:
    - Timestamped backup creation with reason tracking
    - Automatic cleanup of old backups (rolling window)
    - Corruption preservation for debugging
    - Restore from backup with validation
    - Backup listing and management

    Backups are stored in a dedicated subdirectory with the naming convention:
    config.{timestamp}.{reason}.json

    Example:
        config.20251029_143022.pre-save.json
        config.20251029_143045.manual.json
        config.20251029_143100.pre-reset.json
    """

    def __init__(self, config_file: Path, max_backups: int = 5):
        """
        Initialize backup manager.

        Args:
            config_file: Path to the configuration file to manage
            max_backups: Maximum number of backups to retain (default: 5)

        Raises:
            ValueError: If max_backups is less than 1
        """
        if max_backups < 1:
            raise ValueError(f"max_backups must be >= 1, got {max_backups}")

        self.config_file = config_file
        self.max_backups = max_backups
        self.backup_dir = config_file.parent / "backups"

    def create_backup(self, reason: str = "manual") -> Optional[Path]:
        """
        Create a timestamped backup of the configuration file.

        The backup file is named with timestamp and reason for auditing:
        config.{YYYYMMDD_HHMMSS}.{reason}.json

        After creating the backup, old backups are automatically cleaned up
        to maintain the max_backups limit.

        Args:
            reason: Reason for creating backup (e.g., "pre-save", "pre-reset",
                   "manual", "corruption"). Used in filename for auditing.

        Returns:
            Path to created backup file, or None if source file doesn't exist

        Example:
            >>> manager = ConfigBackupManager(Path("config.json"))
            >>> backup = manager.create_backup(reason="pre-reset")
            >>> print(backup)
            PosixPath('/home/user/.config/grab2md/backups/config.20251029_143022.pre-reset.json')
        """
        if not self.config_file.exists():
            logger.warning(f"Cannot backup: {self.config_file} does not exist")
            return None

        # Create backup directory if needed
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"config.{timestamp}.{reason}.json"
        backup_path = self.backup_dir / backup_name

        # Copy file with metadata preservation
        try:
            shutil.copy2(self.config_file, backup_path)
            logger.info(f"Created backup: {backup_path}")

            # Cleanup old backups
            self._cleanup_old_backups()

            return backup_path

        except OSError as e:
            logger.error(f"Failed to create backup: {e}")
            return None

    def save_corrupted_config(self) -> Optional[Path]:
        """
        Save corrupted configuration file for debugging.

        When a config file fails to parse, this preserves the corrupt
        state for user inspection and debugging. Only the most recent
        corrupt file is kept (overwrites previous .corrupt file).

        Returns:
            Path to saved corrupt file, or None if save failed

        Example:
            >>> manager = ConfigBackupManager(Path("config.json"))
            >>> corrupt_path = manager.save_corrupted_config()
            >>> print(corrupt_path)
            PosixPath('/home/user/.config/grab2md/config.json.corrupt')
        """
        if not self.config_file.exists():
            logger.warning(
                f"Cannot save corrupt config: {self.config_file} does not exist"
            )
            return None

        corrupt_path = self.config_file.with_suffix(".json.corrupt")

        try:
            # Overwrite any existing .corrupt file (only keep most recent)
            shutil.copy2(self.config_file, corrupt_path)
            logger.warning(f"Saved corrupt config to: {corrupt_path}")
            return corrupt_path

        except OSError as e:
            logger.error(f"Failed to save corrupt config: {e}")
            return None

    def list_backups(self) -> List[Path]:
        """
        List all available backups, sorted by timestamp (newest first).

        Returns:
            List of backup file paths, sorted newest to oldest

        Example:
            >>> manager = ConfigBackupManager(Path("config.json"))
            >>> backups = manager.list_backups()
            >>> for backup in backups:
            ...     print(backup.name)
            config.20251029_143100.pre-reset.json
            config.20251029_143045.manual.json
            config.20251029_143022.pre-save.json
        """
        if not self.backup_dir.exists():
            return []

        backups = sorted(
            self.backup_dir.glob("config.*.json"),
            key=lambda p: p.name,  # Sort by filename (contains timestamp)
            reverse=True,
        )
        return backups

    def restore_backup(self, backup_path: Path) -> bool:
        """
        Restore configuration from a backup file.

        This validates that the backup file contains valid JSON before
        attempting to restore it. The restoration overwrites the current
        config file.

        Args:
            backup_path: Path to backup file to restore

        Returns:
            True if restore succeeded, False otherwise

        Example:
            >>> manager = ConfigBackupManager(Path("config.json"))
            >>> backups = manager.list_backups()
            >>> success = manager.restore_backup(backups[0])
            >>> if success:
            ...     print("Config restored!")
        """
        if not backup_path.exists():
            logger.error(f"Backup not found: {backup_path}")
            return False

        try:
            # Validate backup contains valid JSON
            with open(backup_path, "r", encoding="utf-8") as f:
                json.load(f)

            # Copy backup to config location (with metadata)
            shutil.copy2(backup_path, self.config_file)
            logger.info(f"Restored config from: {backup_path}")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Backup file is corrupt: {e}")
            return False
        except OSError as e:
            logger.error(f"Failed to restore backup: {e}")
            return False

    def _cleanup_old_backups(self) -> None:
        """
        Remove old backups beyond the max_backups limit.

        This is called automatically after creating a backup to maintain
        the rolling window of backups. Only removes excess backups beyond
        the configured limit.

        Logs warnings for any backups that fail to delete.
        """
        backups = self.list_backups()

        # Remove backups beyond max_backups limit
        for old_backup in backups[self.max_backups :]:
            try:
                old_backup.unlink()
                logger.debug(f"Removed old backup: {old_backup}")
            except OSError as e:
                logger.warning(f"Failed to remove old backup {old_backup}: {e}")
