"""Shared runtime construction for CLI commands."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from grab2md.network.header_manager import HeaderConfig
from grab2md.network.header_manager import HeaderManager


def build_header_config(
    config: Mapping[str, Any],
    *,
    enhanced_headers: bool,
    user_agent_contact: str | None,
) -> HeaderConfig:
    """Build one header identity for direct conversion, batch, and crawl."""
    header_settings = config.get("headers", {})
    contact_email = user_agent_contact if "@" in (user_agent_contact or "") else None
    contact_url = (
        user_agent_contact
        if user_agent_contact and "@" not in user_agent_contact
        else None
    )

    return HeaderConfig(
        use_enhanced_user_agent=enhanced_headers,
        contact_email=contact_email,
        contact_url=contact_url,
        user_agent_name=header_settings.get("user_agent_name", "grab2md"),
        enable_compression=header_settings.get("enable_compression", True),
        compression_methods=header_settings.get(
            "compression_methods", "gzip, deflate, br"
        ),
        respect_caching=header_settings.get("respect_caching", True),
        include_accept_language=header_settings.get("include_accept_language", True),
        preferred_language=header_settings.get("preferred_language", "en-US,en;q=0.9"),
        custom_headers=header_settings.get("custom_headers", {}),
    )


def build_header_manager(
    config: Mapping[str, Any],
    *,
    enhanced_headers: bool,
    user_agent_contact: str | None,
) -> HeaderManager:
    """Construct the shared header policy as a ready-to-use manager."""
    return HeaderManager(
        build_header_config(
            config,
            enhanced_headers=enhanced_headers,
            user_agent_contact=user_agent_contact,
        )
    )
