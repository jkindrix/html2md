import json
import os
import sys
from copy import deepcopy
from pathlib import Path

from html2md.utils.logger import setup_logging

logger = setup_logging()

# Default Configuration
DEFAULT_CONFIG = {
    "domains": {},
    "logging": {"level": "INFO"},
    "oauth": {"CLIENT_ID": "", "CLIENT_SECRET": ""},
    "browser": {"preferred": "chrome"},
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

# Set the token file location according to best practice
CONFIG_DIR = CONFIG_FILE.parent
TOKENS_FILE = CONFIG_DIR / "tokens.json"

_cached_config = None  # Cached configuration


def validate_config(config_data):
    """Ensure the loaded config contains required keys, falling back if necessary."""
    if not isinstance(config_data, dict):
        logger.error("Invalid config format: Expected a JSON object.")
        return deepcopy(DEFAULT_CONFIG)

    # Define required sections with default values
    required_defaults = {
        "domains": {},
        "logging": {"level": "INFO"},
        "oauth": {"CLIENT_ID": "", "CLIENT_SECRET": ""},
        "browser": {"preferred": "chrome"},
    }

    # Ensure each required section exists
    for key, default_value in required_defaults.items():
        if key not in config_data:
            logger.warning(f"Missing '{key}' section in config. Using default.")
            config_data[key] = deepcopy(default_value)
        elif isinstance(default_value, dict):
            # Ensure nested keys exist for dictionary-type defaults
            for sub_key, sub_default in default_value.items():
                if sub_key not in config_data[key]:
                    logger.warning(
                        f"Missing '{sub_key}' in '{key}'. Using default: {sub_default}"
                    )
                    config_data[key][sub_key] = sub_default

    return config_data


def load_config(force_reload=False):
    """Load configuration from a JSON file, creating it if missing."""
    global _cached_config

    if _cached_config is not None and not force_reload:
        return _cached_config  # Use cached config

    if not CONFIG_FILE.exists():
        logger.warning(
            f"Configuration file not found: {CONFIG_FILE}. Creating with defaults."
        )
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
        logger.error(
            f"Invalid or missing config ({CONFIG_FILE}): {e}. Resetting to defaults."
        )
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=4), encoding="utf-8")

    _cached_config = deepcopy(DEFAULT_CONFIG)
    return _cached_config
