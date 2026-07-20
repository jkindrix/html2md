"""Compatibility facade for cookie sources and HTTP session replay."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import requests

from grab2md.cookies.browser_paths import get_browser_cookie_path
from grab2md.cookies.chrome import (
    decrypt_chrome_cookie,
    get_chrome_cookies,
    get_chrome_encryption_key,
)
from grab2md.cookies.errors import CookieSourceError
from grab2md.cookies.export import load_cookies_from_json
from grab2md.cookies.firefox import get_firefox_cookies
from grab2md.cookies.http_session import (
    disable_ssl_verification,
    get_session,
    reset_session,
)
from grab2md.cookies.replay import (
    CookieRecord,
    apply_cookie_records,
    target_hostname,
)
from grab2md.cookies.sources import CookieSource
from grab2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger(__name__)

__all__ = [
    "CookieRecord",
    "CookieSourceError",
    "apply_browser_cookies",
    "decrypt_chrome_cookie",
    "disable_ssl_verification",
    "get_browser_cookie_path",
    "get_chrome_cookies",
    "get_chrome_encryption_key",
    "get_domain_cookies",
    "get_firefox_cookies",
    "get_session",
    "load_cookies_from_json",
    "reset_session",
]


def get_domain_cookies(
    url: str,
    browser: str | None = None,
    cookie_path: Path | None = None,
) -> list[CookieRecord]:
    """Load records through the selected browser-source adapter."""
    if not target_hostname(url):
        logger.warning("Cannot extract cookies for a URL without a valid hostname")
        return []
    from grab2md.cookies.sources import browser_cookie_source

    return cast(
        list[CookieRecord], browser_cookie_source(browser, cookie_path).load(url)
    )


def apply_browser_cookies(
    session: requests.Session,
    url: str,
    cookie_json: str | Path | None = None,
    browser: str | None = None,
    cookie_path: str | Path | None = None,
) -> requests.Session:
    """Load one explicit cookie source and replay applicable records safely."""
    url_domain = target_hostname(url)
    if not url_domain:
        raise ValueError("Cannot apply cookies to a URL without a valid hostname")
    logger.debug("Setting cookies for domain: %s", url_domain)

    source: CookieSource
    if cookie_json:
        from grab2md.cookies.sources import ExportedCookieSource

        source = ExportedCookieSource(Path(cookie_json))
    else:
        from grab2md.cookies.sources import browser_cookie_source

        source = browser_cookie_source(
            browser, Path(cookie_path) if cookie_path is not None else None
        )
    cookies = source.load(url)

    if not cookies:
        raise CookieSourceError(
            f"No applicable cookies were found for {url_domain} in {source.name}"
        )

    session = apply_cookie_records(session, url, cookies)
    logger.debug("Applied %s cookies to session", len(session.cookies.get_dict()))
    logger.info("Applied cookies to session for %s", url)
    return session
