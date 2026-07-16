import logging
import os
from logging.handlers import RotatingFileHandler

try:
    from pythonjsonlogger import jsonlogger
    HAS_JSON_LOGGER = True
except ImportError:
    HAS_JSON_LOGGER = False

# Allow environment variables to override default settings
DEFAULT_LOG_DIR = os.path.join(os.path.dirname(__file__), "../../logs")
DEFAULT_LOG_FILE = os.path.join(DEFAULT_LOG_DIR, "html2md.log")

LOG_FILE = os.getenv("HTML2MD_LOG_PATH", DEFAULT_LOG_FILE)
LOG_LEVEL = os.getenv("HTML2MD_LOG_LEVEL", "WARNING").upper()
ENABLE_JSON_LOGGING = os.getenv("HTML2MD_JSON_LOGGING", "false").lower() == "true" and HAS_JSON_LOGGER


def setup_logging(console_output=True, debug_file=None):
    """
    Configure logging for the application with both file and console handlers.

    Args:
        console_output (bool): Whether to output logs to the console. Defaults to True.
        debug_file (str, optional): Optional path to a debug log file. All logs will be
                                   written to this file at DEBUG level regardless of the
                                   global log level.

    - Ensures the logs directory exists before creating log files.
    - Supports log rotation (5MB per file, keeping 3 backups).
    - Reads log level from an environment variable.
    - Supports optional JSON logging.
    - Can write debug logs to a separate file when debug_file is provided.
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
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.WARNING))

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
    else:
        # Even with console output disabled (the CLI default, keeping stdout
        # clean for piped markdown), genuine errors must never be silent:
        # surface ERROR and above on stderr.
        error_handler = logging.StreamHandler()
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(error_handler)

    # File handler with log rotation
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Optional dedicated debug log file
    if debug_file:
        # Create parent directory if needed
        debug_dir = os.path.dirname(debug_file)
        if debug_dir and not os.path.exists(debug_dir):
            os.makedirs(debug_dir, exist_ok=True)
            
        # Create a file handler that captures everything at DEBUG level
        debug_handler = logging.FileHandler(debug_file, mode='w')  # 'w' to overwrite each time
        debug_handler.setLevel(logging.DEBUG)  # Force DEBUG level for this handler
        debug_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        debug_handler.setFormatter(debug_formatter)
        logger.addHandler(debug_handler)
        logger.debug(f"Debug logging enabled to: {debug_file}")

    return logger
