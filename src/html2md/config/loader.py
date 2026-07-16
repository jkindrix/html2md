import json
import os
import sys
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from html2md.utils.logger import setup_logging

logger = setup_logging()

# Default Configuration
DEFAULT_CONFIG = {
    "domains": {},
    "domain_limits": {
        # Example domain-specific rate limits
        # "github.com": {
        #     "max_concurrent": 2,
        #     "requests_per_minute": 30,
        #     "backoff_multiplier": 2.0
        # }
    },
    "concurrent": {
        "max_concurrent_per_domain": 2,
        "max_total_concurrent": 10,
        "connection_timeout": 30,
        "backoff_strategy": "exponential",  # none, linear, exponential, fibonacci
        "initial_backoff": 1.0,
        "max_backoff": 300.0,
        "backoff_multiplier": 2.0,
        "error_threshold": 3,
        "respect_retry_after": True,
        "polite_concurrent_limit": 1,
        "polite_delay_multiplier": 2.0
    },
    "logging": {"level": "WARNING"},
    "oauth": {"CLIENT_ID": "", "CLIENT_SECRET": ""},
    "browser": {"preferred": "chrome"},
    "headers": {
        "enhanced_user_agent": True,
        "contact_email": None,
        "contact_url": None,
        "user_agent_name": "html2md",
        "user_agent_version": "1.0",
        "enable_compression": True,
        "compression_methods": "gzip, deflate, br",
        "enable_conditional_requests": True,
        "simulate_browser": False,
        "browser_type": "chrome",
        "respect_caching": True,
        "include_accept_language": True,
        "preferred_language": "en-US,en;q=0.9",
        "custom_headers": {}
    },
    "cli_defaults": {
        "batch": {
            "hierarchical": False,
            "flatten": False,
            "flatten_all": False,
            "trim": True,
            "visualize": False,
            "quiet": False
        },
        "crawl": {
            "hierarchical": False,
            "flatten": False,
            "follow": "domain-only",
            "max_depth": 3,
            "max_pages": 100,
            "delay": 0.0,
            "respect_robots": True,
            "rate_limit": None,
            "enhanced_headers": True,
            "user_agent_contact": None,
            "simulate_browser": False,
            "polite": False,
            "max_concurrent": None,
            "show_progress": True,
            "trim": True,
            "visualize": False,
            "quiet": False
        },
        "convert": {
            "browser_cookies": False,
            "no_cookies": False,
            "browser": None,
            "enhanced_headers": True,
            "user_agent_contact": None,
            "simulate_browser": False,
            "trim": True,
            "download_images": False,
            "images_dir": "images",
            "fancy": False,
            "local": False
        }
    }
}


# Determine the correct config path based on OS
def get_config_path():
    """Return the appropriate configuration file path for the user's OS."""
    if sys.platform == "win32":
        config_dir = (
            Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / "html2md"
        )
    elif sys.platform == "darwin":  # macOS
        config_dir = Path.home() / "Library" / "Application Support" / "html2md"
    else:  # Assume Linux/Unix
        config_dir = (
            Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "html2md"
        )

    config_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    return config_dir / "config.json"


# Allow external configuration path override
CONFIG_FILE = Path(os.getenv("HTML2MD_CONFIG_PATH", get_config_path()))
CONFIG_PATH = CONFIG_FILE  # Alias for external use

# Set the token file location according to best practice
CONFIG_DIR = CONFIG_FILE.parent
TOKENS_FILE = CONFIG_DIR / "tokens.json"

_cached_config = None  # Cached configuration

# Thread-safety lock for config operations
_config_lock = threading.Lock()

# Lazy-loaded singleton instances (imported on first use to avoid circular deps)
_backup_manager = None
_recovery_handler = None


def get_backup_manager():
    """
    Get or create singleton backup manager instance.

    Returns:
        ConfigBackupManager: Singleton backup manager
    """
    global _backup_manager
    if _backup_manager is None:
        from html2md.config.backup import ConfigBackupManager
        _backup_manager = ConfigBackupManager(CONFIG_FILE, max_backups=5)
    return _backup_manager


def get_recovery_handler():
    """
    Get or create singleton recovery handler instance.

    Returns:
        ConfigRecoveryHandler: Singleton recovery handler
    """
    global _recovery_handler
    if _recovery_handler is None:
        from html2md.config.recovery import ConfigRecoveryHandler
        _recovery_handler = ConfigRecoveryHandler(
            CONFIG_FILE,
            get_backup_manager(),
            DEFAULT_CONFIG
        )
    return _recovery_handler


def validate_config(config_data):
    """
    Ensure the loaded config contains required keys and valid types.

    This function:
    - Merges user config with defaults
    - Validates types match expected schema
    - Reverts invalid values to defaults with warnings

    Args:
        config_data: User configuration dictionary to validate

    Returns:
        Validated and merged configuration dictionary
    """
    if not isinstance(config_data, dict):
        logger.error("Invalid config format: Expected a JSON object.")
        return deepcopy(DEFAULT_CONFIG)

    # Start with a copy of default config and merge user config
    merged_config = deepcopy(DEFAULT_CONFIG)

    # Deep merge user config into default config
    def deep_merge(default_dict, user_dict):
        """Recursively merge user config into default config."""
        for key, value in user_dict.items():
            if key in default_dict and isinstance(default_dict[key], dict) and isinstance(value, dict):
                deep_merge(default_dict[key], value)
            else:
                default_dict[key] = value

    deep_merge(merged_config, config_data)

    # Validate types match defaults
    def validate_types(user_dict, default_dict, path=""):
        """
        Recursively validate that user config values match expected types.

        On type mismatch, logs a warning and reverts to default value.

        Args:
            user_dict: User configuration dictionary (modified in-place)
            default_dict: Default configuration with expected types
            path: Current path in config tree (for error messages)
        """
        for key, default_value in default_dict.items():
            if key in user_dict:
                user_value = user_dict[key]

                # Check if types match
                if type(user_value) is not type(default_value):
                    config_path = f"{path}.{key}" if path else key
                    logger.warning(
                        f"Config type mismatch at '{config_path}': "
                        f"expected {type(default_value).__name__}, "
                        f"got {type(user_value).__name__}. Using default value."
                    )
                    user_dict[key] = default_value

                # Recursively validate nested dictionaries
                elif isinstance(default_value, dict) and isinstance(user_value, dict):
                    validate_types(
                        user_value,
                        default_value,
                        f"{path}.{key}" if path else key
                    )

    validate_types(merged_config, DEFAULT_CONFIG)

    return merged_config


def ensure_config_exists():
    """Ensure configuration file exists, creating with defaults if missing."""
    if not CONFIG_FILE.exists():
        logger.warning(
            f"Configuration file not found: {CONFIG_FILE}. Creating with defaults."
        )
        # Use atomic write to ensure even initial creation is safe
        from html2md.config.writer import atomic_write_json
        atomic_write_json(CONFIG_FILE, DEFAULT_CONFIG, private=True)
        return True
    return False


def save_config(config_data: Dict[str, Any]) -> None:
    """
    Save configuration to file with atomic write and backup.

    This is the centralized write path for all configuration modifications.
    It ensures data safety through:
    - Thread-safe locking (prevents concurrent save/load races)
    - Pre-save backup creation (if file exists)
    - Validation before saving
    - Atomic write operation (no partial writes)
    - Graceful disk-full error handling
    - Cache invalidation (write-through)

    Args:
        config_data: Configuration dictionary to save

    Raises:
        OSError: If write operation fails (except disk full)
        TypeError: If data cannot be serialized to JSON
        typer.Exit: On disk full error

    Example:
        >>> config = load_config()
        >>> config['domains']['example.com'] = {'footer_marker': 'Copyright'}
        >>> save_config(config)
    """
    global _cached_config

    # Thread-safe: Entire save operation is atomic with respect to other config ops
    with _config_lock:
        # Validate before saving
        validated_config = validate_config(config_data)

        # Create backup before overwriting (if file exists)
        if CONFIG_FILE.exists():
            backup_manager = get_backup_manager()
            backup_manager.create_backup(reason="pre-save")

        # Atomic write using our safe writer with disk-full error handling
        try:
            from html2md.config.writer import atomic_write_json
            atomic_write_json(CONFIG_FILE, validated_config, indent=4, private=True)
        except OSError as e:
            # Handle disk full error gracefully
            if e.errno == 28:  # errno.ENOSPC - No space left on device
                logger.critical(f"Disk full: Cannot save configuration to {CONFIG_FILE}")
                # Import here to avoid circular dependency issues
                from rich.console import Console
                console = Console()
                console.print(
                    "[bold red]Error: Disk is full. Configuration could not be saved.[/bold red]"
                )
                console.print(
                    "[yellow]Free up disk space and try the operation again.[/yellow]"
                )
                # Exit with error code in CLI context
                import typer
                raise typer.Exit(1)
            else:
                # Re-raise other OSErrors
                raise

        # Invalidate cache (write-through pattern)
        _cached_config = validated_config

        logger.info(f"Saved configuration to: {CONFIG_FILE}")


def load_config(force_reload=False):
    """
    Load configuration from a JSON file with robust error recovery.

    This function:
    - Thread-safe: Protected by lock to prevent races with save operations
    - Returns cached config if available (unless force_reload=True)
    - Creates default config file if missing
    - Validates loaded config against defaults
    - Uses recovery handler for corruption/errors (never silently overwrites)

    Args:
        force_reload: If True, bypass cache and reload from disk

    Returns:
        Configuration dictionary (validated and merged with defaults)

    Example:
        >>> config = load_config()
        >>> print(config['domains'])
        {}
    """
    global _cached_config

    # Thread-safe: Entire load operation is atomic with respect to save operations
    with _config_lock:
        if _cached_config is not None and not force_reload:
            return _cached_config  # Use cached config

        ensure_config_exists()
        _cached_config = deepcopy(DEFAULT_CONFIG) if not CONFIG_FILE.exists() else None

        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                config_data = json.load(f)
                _cached_config = validate_config(config_data)
                logger.info(f"Loaded configuration from: {CONFIG_FILE}")
                return _cached_config

        except (json.JSONDecodeError, FileNotFoundError) as e:
            # Use recovery handler instead of immediate overwrite
            # This respects user data and provides context-aware recovery
            recovery_handler = get_recovery_handler()
            _cached_config = recovery_handler.handle_corrupt_config(e)
            return _cached_config
