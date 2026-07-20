"""Browser cookie-store path discovery."""

from __future__ import annotations

import sys
from pathlib import Path

from grab2md.config.loader import load_config
from grab2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger(__name__)


def _default_browser_cookie_path(
    platform: str, home: Path, browser: str
) -> Path | None:
    """Return the documented browser path without probing or configuration."""
    if platform == "win32":
        roots = {
            "chrome": home
            / "AppData/Local/Google/Chrome/User Data/Default/Network/Cookies",
            "firefox": home / "AppData/Roaming/Mozilla/Firefox/Profiles",
            "edge": home
            / "AppData/Local/Microsoft/Edge/User Data/Default/Network/Cookies",
        }
        return roots.get(browser)
    if platform == "darwin":
        roots = {
            "chrome": home
            / "Library/Application Support/Google/Chrome/Default/Cookies",
            "firefox": home / "Library/Application Support/Firefox/Profiles",
            "safari": home / "Library/Cookies/Cookies.binarycookies",
        }
        return roots.get(browser)
    if platform.startswith("linux"):
        roots = {
            "chrome": home / ".config/google-chrome/Default/Cookies",
            "firefox": home / ".mozilla/firefox",
            "edge": home / ".config/microsoft-edge/Default/Cookies",
        }
        return roots.get(browser)
    return None


def _normalized_cookie_path(raw_path: str | Path) -> Path:
    """Normalize an explicit/configured browser path, including WSL syntax."""
    custom_path_str = str(raw_path)
    if (
        sys.platform.startswith("linux")
        and not custom_path_str.startswith("/")
        and len(custom_path_str) >= 3
        and custom_path_str[1:3] in {":\\", ":/"}
    ):
        drive = custom_path_str[0].lower()
        path_without_drive = custom_path_str[3:]
        path_with_slashes = path_without_drive.replace("\\", "/")
        return Path(f"/mnt/{drive}/{path_with_slashes}")
    return Path(custom_path_str).expanduser()


def get_browser_cookie_path(
    browser: str | None = None, custom_path: str | Path | None = None
) -> Path | None:
    """Return the configured or conventional browser cookie path."""
    config = load_config()
    browser_config = config.get("browser", {})
    preferred_browser = browser or browser_config.get("preferred", "chrome")

    if custom_path is not None:
        normalized = _normalized_cookie_path(custom_path)
        logger.info(
            "Using one-shot cookie path for %s: %s",
            preferred_browser,
            normalized,
        )
        return normalized

    custom_paths = browser_config.get("custom_path", {})
    if preferred_browser in custom_paths and custom_paths[preferred_browser]:
        custom_path = _normalized_cookie_path(custom_paths[preferred_browser])
        if custom_path.exists():
            logger.info(
                "Using custom cookie path for %s: %s",
                preferred_browser,
                custom_path,
            )
            return custom_path
        logger.warning(
            "Custom cookie path for %s not found: %s",
            preferred_browser,
            custom_path,
        )

    default_path = _default_browser_cookie_path(
        sys.platform, Path.home(), preferred_browser
    )
    if default_path is not None:
        return default_path

    logger.warning(
        "Unsupported browser %r or platform %r",
        preferred_browser,
        sys.platform,
    )
    return None
