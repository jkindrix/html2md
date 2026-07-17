"""
HTTP identity management for respectful web crawling.

This module provides:
- Configurable User-Agent strings with contact information
- Accept-Encoding for compression support
- Centralized header configuration and management
- Honest crawler headers that identify the installed tool version
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from html2md import __version__

logger = logging.getLogger("html2md")


@dataclass
class HeaderConfig:
    """Configuration for enhanced HTTP headers."""

    # User-Agent configuration
    use_enhanced_user_agent: bool = True
    contact_email: Optional[str] = None
    contact_url: Optional[str] = None
    user_agent_name: str = "html2md"

    # Compression support
    enable_compression: bool = True
    compression_methods: str = "gzip, deflate, br"

    # Additional professional headers
    respect_caching: bool = True
    include_accept_language: bool = True
    preferred_language: str = "en-US,en;q=0.9"

    # Custom headers
    custom_headers: Dict[str, str] = field(default_factory=dict)


class HeaderManager:
    """Centralized HTTP header management."""

    def __init__(self, config: Optional[HeaderConfig] = None):
        self.config = config or HeaderConfig()
        self._cached_base_headers: Optional[Dict[str, str]] = None

    def get_headers(self, url: str) -> Dict[str, str]:
        """
        Get complete HTTP headers for a request.

        Args:
            url: Target URL for the request
        Returns:
            Dictionary of HTTP headers
        """
        headers = self._get_base_headers().copy()

        # Add custom headers (highest priority)
        headers.update(self.config.custom_headers)

        logger.debug(
            f"Generated headers for {url}: User-Agent={headers.get('User-Agent', 'None')[:50]}..."
        )
        return headers

    def _get_base_headers(self) -> Dict[str, str]:
        """Get base headers that apply to all requests."""
        if self._cached_base_headers is None:
            self._cached_base_headers = self._build_base_headers()
        return self._cached_base_headers.copy()

    def _build_base_headers(self) -> Dict[str, str]:
        """Build the base set of HTTP headers."""
        headers = {}

        # User-Agent header
        headers["User-Agent"] = self._build_user_agent()

        # Accept headers
        headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        )

        # Compression support
        if self.config.enable_compression:
            headers["Accept-Encoding"] = self.config.compression_methods

        # Language preferences
        if self.config.include_accept_language:
            headers["Accept-Language"] = self.config.preferred_language

        # Connection management
        headers["Connection"] = "keep-alive"

        # Caching behavior
        if self.config.respect_caching:
            headers["Cache-Control"] = "max-age=0"
        else:
            headers["Cache-Control"] = "no-cache"

        return headers

    def _build_user_agent(self) -> str:
        """Build an enhanced User-Agent string."""
        user_agent = f"{self.config.user_agent_name}/{__version__}"

        # Add contact information if provided
        contact_parts = []
        if self.config.contact_email:
            contact_parts.append(f"Contact: {self.config.contact_email}")
        if self.config.contact_url:
            contact_parts.append(f"Info: {self.config.contact_url}")

        if contact_parts and self.config.use_enhanced_user_agent:
            contact_string = "; ".join(contact_parts)
            user_agent += f" (+{contact_string})"

        return user_agent

    def clear_cache(self) -> None:
        """Clear cached base headers."""
        self._cached_base_headers = None
        logger.debug("Cleared header manager cache")

    def update_config(self, config: HeaderConfig) -> None:
        """
        Update the header configuration.

        Args:
            config: New header configuration
        """
        self.config = config
        self.clear_cache()
        logger.info("Updated header configuration")

    def get_config_summary(self) -> Dict[str, Any]:
        """Get a summary of the current configuration."""
        return {
            "enhanced_user_agent": self.config.use_enhanced_user_agent,
            "contact_email": self.config.contact_email,
            "contact_url": self.config.contact_url,
            "compression_enabled": self.config.enable_compression,
            "custom_headers_count": len(self.config.custom_headers),
        }


def format_http_date(timestamp: Optional[float] = None) -> str:
    """
    Format a timestamp as an HTTP date string.

    Args:
        timestamp: Unix timestamp (defaults to current time)

    Returns:
        HTTP date string (RFC 7231 format)
    """
    if timestamp is None:
        timestamp = time.time()

    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def parse_http_date(date_string: str) -> Optional[float]:
    """
    Parse an HTTP date string to a Unix timestamp.

    Args:
        date_string: HTTP date string

    Returns:
        Unix timestamp or None if parsing fails
    """
    formats = [
        "%a, %d %b %Y %H:%M:%S GMT",  # RFC 7231
        "%A, %d-%b-%y %H:%M:%S GMT",  # RFC 850
        "%a %b %d %H:%M:%S %Y",  # ANSI C asctime()
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_string, fmt)
            dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue

    logger.warning(f"Could not parse HTTP date: {date_string}")
    return None
