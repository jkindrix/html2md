import json
import os
import sys
from pathlib import Path
from copy import deepcopy
from html2md.utils.logger import setup_logging

logger = setup_logging()

# Default Configuration
DEFAULT_CONFIG = {"domains": {}, "logging": {"level": "INFO"}}

# Determine the correct config path based on OS
def get_config_path():
    """Return the appropriate configuration file path for the user's OS."""
    if sys.platform == "win32":
        config_dir = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / "html2md"
    elif sys.platform == "darwin":  # macOS
        config_dir = Path.home() / "Library" / "Application Support" / "html2md"
    else:  # Assume Linux/Unix
        config_dir = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "html2md"

    config_dir.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    return config_dir / "config.json"

# Allow external configuration path override
CONFIG_FILE = Path(os.getenv("HTML2MD_CONFIG_PATH", get_config_path()))

_cached_config = None  # Cached configuration


def validate_config(config_data):
    """Ensure the loaded config contains required keys, falling back if necessary."""
    if not isinstance(config_data, dict):
        logger.error("Invalid config format: Expected a JSON object.")
        return deepcopy(DEFAULT_CONFIG)

    # Ensure required sections exist
    if "domains" not in config_data:
        logger.warning("Missing 'domains' section in config. Using default.")
        config_data["domains"] = {}

    if "logging" not in config_data or "level" not in config_data["logging"]:
        logger.warning("Missing logging level in config. Using default logging level INFO.")
        config_data["logging"] = {"level": "INFO"}

    return config_data


def load_config(force_reload=False):
    """Load configuration from a JSON file, creating it if missing."""
    global _cached_config

    if _cached_config is not None and not force_reload:
        return _cached_config  # Use cached config

    if not CONFIG_FILE.exists():
        logger.warning(f"Configuration file not found: {CONFIG_FILE}. Creating with defaults.")
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=4), encoding="utf-8")
        _cached_config = deepcopy(DEFAULT_CONFIG)
        return _cached_config

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            config_data = json.load(f)
            _cached_config = validate_config(config_data)
            logger.info(f"Loaded configuration from: {CONFIG_FILE}")
            return _cached_config
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"Invalid or missing config ({CONFIG_FILE}): {e}. Resetting to defaults.")
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=4), encoding="utf-8")

    _cached_config = deepcopy(DEFAULT_CONFIG)
    return _cached_config
