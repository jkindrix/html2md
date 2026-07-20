"""Strict parsing for caller-supplied browser cookie exports."""

from __future__ import annotations

from grab2md.cookies.errors import CookieSourceError
from grab2md.cookies.replay import CookieRecord, target_hostname
from grab2md.utils.private_json import load_private_json
from grab2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger(__name__)


def load_cookies_from_json(json_file, url=None) -> list[CookieRecord]:
    """Load scoped records from a browser developer-tools export."""
    cookies: list[CookieRecord] = []
    try:
        cookie_data = load_private_json(json_file, description="Cookie export")

        hostname = target_hostname(url) if url else ""
        if isinstance(cookie_data, list):
            for cookie in cookie_data:
                if not isinstance(cookie, dict) or not {
                    "name",
                    "value",
                }.issubset(cookie):
                    continue
                cookie_domain = str(cookie.get("domain", hostname))
                record = CookieRecord(
                    name=str(cookie["name"]),
                    value=str(cookie["value"]),
                    domain=cookie_domain,
                    path=str(cookie.get("path", "/") or "/"),
                    expires=(
                        int(cookie["expirationDate"])
                        if cookie.get("expirationDate") is not None
                        else None
                    ),
                    secure=bool(cookie.get("secure", False)),
                    http_only=bool(cookie.get("httpOnly", False)),
                    same_site=(
                        str(cookie["sameSite"])
                        if cookie.get("sameSite") is not None
                        else None
                    ),
                    host_only=bool(
                        cookie.get("hostOnly", not cookie_domain.startswith("."))
                    ),
                )
                if not hostname or record.applies_to(hostname):
                    cookies.append(record)
        elif isinstance(cookie_data, dict):
            if not hostname:
                raise ValueError(
                    "A target URL is required for an unscoped cookie mapping"
                )
            cookies.extend(
                CookieRecord(str(name), str(value), hostname, host_only=True)
                for name, value in cookie_data.items()
            )
        else:
            raise ValueError("Cookie export must be a JSON object or array")
    except Exception as error:
        logger.error("Error loading cookies from JSON file: %s", error)
        if isinstance(error, CookieSourceError):
            raise
        raise CookieSourceError(f"Could not load cookie export: {error}") from error

    logger.info("Loaded %s cookies from JSON file: %s", len(cookies), json_file)
    return cookies
