"""Firefox profile selection and cookie extraction."""

from __future__ import annotations

import configparser
import sqlite3
from datetime import datetime
from pathlib import Path

from grab2md.cookies.browser_paths import get_browser_cookie_path
from grab2md.cookies.database import copied_cookie_connection
from grab2md.cookies.errors import CookieSourceError
from grab2md.cookies.replay import (
    CookieRecord,
    cookie_domain_matches,
    normalize_hostname,
)
from grab2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger(__name__)


def _resolve_firefox_profile_path(
    firefox_root: Path,
    section: configparser.SectionProxy,
    option: str,
) -> Path | None:
    raw_path = (section.get(option, fallback="") or "").strip()
    if not raw_path:
        return None
    candidate = Path(raw_path).expanduser()
    if section.name.casefold().startswith("profile"):
        relative = section.getboolean("IsRelative", fallback=True)
    else:
        relative = not candidate.is_absolute()
    return firefox_root / candidate if relative else candidate


def find_firefox_profile(firefox_root: Path) -> Path | None:
    """Resolve Firefox's install-selected or explicitly default profile."""
    parsed: list[tuple[configparser.ConfigParser, bool]] = []
    for ini_path in (firefox_root / "profiles.ini", firefox_root / "installs.ini"):
        if not ini_path.exists():
            continue
        parser = configparser.ConfigParser(interpolation=None)
        try:
            with ini_path.open("r", encoding="utf-8") as ini_file:
                parser.read_file(ini_file)
        except (OSError, configparser.Error, UnicodeError) as error:
            raise CookieSourceError(
                f"Could not parse Firefox profile configuration {ini_path}: {error}"
            ) from error
        parsed.append((parser, ini_path.name == "installs.ini"))

    install_defaults: list[Path] = []
    profile_defaults: list[Path] = []
    profile_fallbacks: list[Path] = []
    for parser, install_file in parsed:
        for section_name in parser.sections():
            section = parser[section_name]
            if install_file or section_name.casefold().startswith("install"):
                candidate = _resolve_firefox_profile_path(
                    firefox_root, section, "Default"
                )
                if candidate is not None:
                    install_defaults.append(candidate)
            elif section_name.casefold().startswith("profile"):
                candidate = _resolve_firefox_profile_path(firefox_root, section, "Path")
                if candidate is None:
                    continue
                profile_fallbacks.append(candidate)
                if section.getboolean("Default", fallback=False):
                    profile_defaults.append(candidate)

    for candidate in install_defaults + profile_defaults + profile_fallbacks:
        if candidate.is_dir():
            return candidate
    return None


def get_firefox_cookies(
    domain: str, *, cookie_path: str | Path | None = None
) -> list[CookieRecord]:
    """Retrieve applicable Firefox cookies for one hostname."""
    cookie_records: list[CookieRecord] = []
    target_hostname = normalize_hostname(domain)
    if not target_hostname:
        raise CookieSourceError("Firefox cookie extraction requires a valid hostname")
    resolved_path = get_browser_cookie_path("firefox", cookie_path)
    if not resolved_path or not resolved_path.exists():
        raise CookieSourceError(
            f"Firefox profile directory not found at {resolved_path}"
        )

    profile_dir = resolved_path.parent if resolved_path.is_file() else None
    cookies_db = resolved_path if resolved_path.is_file() else None
    if resolved_path.is_dir():
        firefox_root = (
            resolved_path.parent if resolved_path.name == "Profiles" else resolved_path
        )
        profile_dir = find_firefox_profile(firefox_root)

    if not profile_dir and resolved_path.is_dir():
        profiles = [
            path
            for path in resolved_path.iterdir()
            if path.is_dir() and path.name.endswith(".default")
        ]
        if len(profiles) == 1:
            profile_dir = profiles[0]
        else:
            profile_dir = next(
                (
                    path
                    for path in resolved_path.iterdir()
                    if path.is_dir() and ".default" in path.name
                ),
                None,
            )

    if not profile_dir or not profile_dir.exists():
        raise CookieSourceError("Could not find a valid Firefox profile")
    cookies_db = cookies_db or profile_dir / "cookies.sqlite"
    if not cookies_db.exists():
        raise CookieSourceError(f"Firefox cookies database not found at {cookies_db}")

    try:
        with copied_cookie_connection(cookies_db) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT name, value, host, expiry, path, isSecure, isHttpOnly
                  FROM moz_cookies
                 WHERE host = ?
                    OR (
                        substr(host, 1, 1) = '.'
                        AND (
                            ltrim(host, '.') = ?
                            OR ? LIKE '%.' || ltrim(host, '.')
                        )
                    )
                """,
                (target_hostname, target_hostname, target_hostname),
            )
            now = int(datetime.now().timestamp())
            for (
                name,
                value,
                host,
                expiry,
                path,
                is_secure,
                is_httponly,
            ) in cursor.fetchall():
                try:
                    host_only = not str(host).startswith(".")
                    if not cookie_domain_matches(
                        target_hostname, host, host_only=host_only
                    ):
                        continue
                    expiry_value = int(expiry) if expiry else 0
                    if expiry_value and expiry_value < now:
                        continue
                    cookie_records.append(
                        CookieRecord(
                            name=str(name),
                            value=str(value),
                            domain=str(host),
                            path=str(path or "/"),
                            expires=expiry_value or None,
                            secure=bool(is_secure),
                            http_only=bool(is_httponly),
                            host_only=host_only,
                        )
                    )
                except (TypeError, ValueError, OverflowError) as error:
                    logger.warning("Skipping malformed Firefox cookie row: %s", error)
    except sqlite3.OperationalError as error:
        logger.error("Error querying Firefox cookies: %s", error)
        raise CookieSourceError(f"Could not query Firefox cookies: {error}") from error
    except Exception as error:
        logger.error("Error reading Firefox cookies: %s", error)
        if isinstance(error, CookieSourceError):
            raise
        raise CookieSourceError(f"Could not read Firefox cookies: {error}") from error

    logger.info("Retrieved %s cookies for domain %s", len(cookie_records), domain)
    return cookie_records
