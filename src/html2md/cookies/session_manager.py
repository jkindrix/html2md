import requests
import logging
from html2md.config.loader import load_config

logger = logging.getLogger("session_manager")

# Load configuration
config = load_config()

# Global session object
session = requests.Session()

# Default headers (override from config if available)
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}


def configure_session():
    """Initialize the session with appropriate headers and settings."""
    global session

    # Load custom headers from config
    custom_headers = config.get("default_headers", {})
    session.headers.update(DEFAULT_HEADERS)
    session.headers.update(custom_headers)

    logger.info("Session initialized with headers: %s", session.headers)


def reset_session():
    """Reset the global session if it becomes invalid."""
    global session
    session.close()
    session = requests.Session()
    configure_session()
    logger.info("Session has been reset.")


# Initial session configuration
configure_session()
