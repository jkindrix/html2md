import logging
import os
from logging.handlers import RotatingFileHandler

from pythonjsonlogger import jsonlogger

# Allow environment variables to override default settings
DEFAULT_LOG_DIR = os.path.join(os.path.dirname(__file__), "../../logs")
DEFAULT_LOG_FILE = os.path.join(DEFAULT_LOG_DIR, "html2md.log")

LOG_FILE = os.getenv("HTML2MD_LOG_PATH", DEFAULT_LOG_FILE)
LOG_LEVEL = os.getenv("HTML2MD_LOG_LEVEL", "INFO").upper()
ENABLE_JSON_LOGGING = os.getenv("HTML2MD_JSON_LOGGING", "false").lower() == "true"


def setup_logging(console_output=True):
    """
    Configure logging for the application with both file and console handlers.

    Args:
        console_output (bool): Whether to output logs to the console. Defaults to True.

    - Ensures the logs directory exists before creating log files.
    - Supports log rotation (5MB per file, keeping 3 backups).
    - Reads log level from an environment variable.
    - Supports optional JSON logging.
    """

    # Ensure the logs directory exists
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("html2md")

    # Prevent duplicate handlers if `setup_logging()` is called multiple times
    if logger.hasHandlers():
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

    # Set logging level dynamically based on environment variable
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Console handler (if enabled)
    if console_output:
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        if ENABLE_JSON_LOGGING:
            console_formatter = jsonlogger.JsonFormatter(
                "%(asctime)s %(name)s %(levelname)s %(message)s"
            )

        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # File handler with log rotation
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger
