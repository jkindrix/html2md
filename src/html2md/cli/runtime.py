"""Shared runtime construction for CLI commands."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from html2md.network.header_manager import HeaderConfig


def build_header_config(
    config: Mapping[str, Any],
    *,
    enhanced_headers: bool,
    user_agent_contact: str | None,
    simulate_browser: bool,
) -> HeaderConfig:
    """Build one deliberate header identity for convert, batch, and crawl."""
    header_settings = config.get("headers", {})
    contact_email = user_agent_contact if "@" in (user_agent_contact or "") else None
    contact_url = (
        user_agent_contact if user_agent_contact and "@" not in user_agent_contact else None
    )

    return HeaderConfig(
        use_enhanced_user_agent=enhanced_headers,
        contact_email=contact_email,
        contact_url=contact_url,
        user_agent_name=header_settings.get("user_agent_name", "html2md"),
        user_agent_version=header_settings.get("user_agent_version", "1.0"),
        enable_compression=header_settings.get("enable_compression", True),
        compression_methods=header_settings.get("compression_methods", "gzip, deflate, br"),
        enable_conditional_requests=header_settings.get("enable_conditional_requests", True),
        simulate_browser=simulate_browser,
        browser_type=header_settings.get("browser_type", "chrome"),
        respect_caching=header_settings.get("respect_caching", True),
        include_accept_language=header_settings.get("include_accept_language", True),
        preferred_language=header_settings.get("preferred_language", "en-US,en;q=0.9"),
        custom_headers=header_settings.get("custom_headers", {}),
    )
