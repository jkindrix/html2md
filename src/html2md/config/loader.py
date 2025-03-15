import json
import os
from html2md.utils.logger import setup_logging

logger = setup_logging()

# Default Configuration
DEFAULT_CONFIG = {"domains": {}, "logging": {"level": "INFO"}}

# Allow external configuration path override
CONFIG_FILE = os.getenv("HTML2MD_CONFIG_PATH") or os.path.join(
    os.path.dirname(__file__), "config.json"
)

_cached_config = None  # Cached configuration


def validate_config(config_data):
    """Ensure the loaded config contains required keys, falling back if necessary."""
    if not isinstance(config_data, dict):
        logger.error("Invalid config format: Expected a JSON object.")
        return DEFAULT_CONFIG

    # Ensure required sections exist
    if "domains" not in config_data:
        logger.warning("Missing 'domains' section in config. Using default.")
        config_data["domains"] = {}

    if "logging" not in config_data or "level" not in config_data["logging"]:
        logger.warning(
            "Missing logging level in config. Using default logging level INFO."
        )
        config_data["logging"] = {"level": "INFO"}

    return config_data


def load_config(force_reload=False):
    """Load configuration from a JSON file, ensuring safe error handling."""
    global _cached_config

    if _cached_config is not None and not force_reload:
        return _cached_config  # Use cached config

    if not os.path.exists(CONFIG_FILE):
        logger.warning(
            f"Configuration file not found: {CONFIG_FILE}. Using default configuration."
        )
        _cached_config = DEFAULT_CONFIG
        return _cached_config

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            _cached_config = validate_config(config_data)
            logger.info(f"Loaded configuration from: {CONFIG_FILE}")
            return _cached_config
    except json.JSONDecodeError as e:
        logger.error(
            f"Invalid JSON in {CONFIG_FILE}: {e}. Using default configuration."
        )
    except Exception as e:
        logger.error(
            f"Unexpected error loading config from {CONFIG_FILE}: {e}. Using default configuration."
        )

    _cached_config = DEFAULT_CONFIG
    return _cached_config
