"""
Enhanced HTTP header management for respectful web crawling.

This module provides:
- Configurable User-Agent strings with contact information
- Accept-Encoding for compression support
- If-Modified-Since for conditional requests
- Centralized header configuration and management
- Professional crawling headers that identify the tool
"""

import logging
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from urllib.parse import urlparse

logger = logging.getLogger("html2md")


@dataclass
class HeaderConfig:
    """Configuration for enhanced HTTP headers."""

    # User-Agent configuration
    use_enhanced_user_agent: bool = True
    contact_email: Optional[str] = None
    contact_url: Optional[str] = None
    user_agent_name: str = "html2md"
    user_agent_version: str = "1.0"

    # Compression support
    enable_compression: bool = True
    compression_methods: str = "gzip, deflate, br"

    # Conditional requests
    enable_conditional_requests: bool = True

    # Browser simulation headers
    simulate_browser: bool = False
    browser_type: str = "chrome"  # "chrome", "firefox", "safari"

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
        self._last_modified_cache: Dict[str, str] = {}

    def get_headers(
        self, url: str, last_modified: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Get complete HTTP headers for a request.

        Args:
            url: Target URL for the request
            last_modified: Optional last-modified timestamp for conditional requests

        Returns:
            Dictionary of HTTP headers
        """
        headers = self._get_base_headers().copy()

        # Add URL-specific headers
        domain = urlparse(url).netloc
        if domain:
            headers["Referer"] = f"https://{domain}/"

        # Add conditional request headers
        if self.config.enable_conditional_requests:
            if last_modified:
                headers["If-Modified-Since"] = last_modified
                self._last_modified_cache[url] = last_modified
            elif url in self._last_modified_cache:
                headers["If-Modified-Since"] = self._last_modified_cache[url]

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

        # Browser simulation headers
        if self.config.simulate_browser:
            headers.update(self._get_browser_simulation_headers())

        return headers

    def _build_user_agent(self) -> str:
        """Build an enhanced User-Agent string."""
        if not self.config.use_enhanced_user_agent:
            # Fallback to browser simulation
            return self._get_browser_user_agent()

        # Build professional crawler User-Agent
        ua_parts = [f"{self.config.user_agent_name}/{self.config.user_agent_version}"]

        # Add system information
        system_info = (
            f"({platform.system()} {platform.release()}; {platform.machine()})"
        )
        ua_parts.append(system_info)

        # Add Python version
        python_version = f"Python/{platform.python_version()}"
        ua_parts.append(python_version)

        # Build base User-Agent
        user_agent = " ".join(ua_parts)

        # Add contact information if provided
        contact_parts = []
        if self.config.contact_email:
            contact_parts.append(f"Contact: {self.config.contact_email}")
        if self.config.contact_url:
            contact_parts.append(f"Info: {self.config.contact_url}")

        if contact_parts:
            contact_string = "; ".join(contact_parts)
            user_agent += f" (+{contact_string})"

        return user_agent

    def _get_browser_user_agent(self) -> str:
        """Get a browser-like User-Agent string."""
        browser_agents = {
            "chrome": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "firefox": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
            "safari": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
        }
        return browser_agents.get(self.config.browser_type, browser_agents["chrome"])

    def _get_browser_simulation_headers(self) -> Dict[str, str]:
        """Get headers that simulate a real browser."""
        if self.config.browser_type == "chrome":
            return {
                "Sec-CH-UA": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
        elif self.config.browser_type == "firefox":
            return {
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
            }
        return {}

    def update_last_modified(self, url: str, last_modified: str) -> None:
        """
        Update the last-modified timestamp for a URL.

        Args:
            url: The URL that was requested
            last_modified: Last-Modified header value from the response
        """
        if self.config.enable_conditional_requests and last_modified:
            self._last_modified_cache[url] = last_modified
            logger.debug(f"Updated last-modified for {url}: {last_modified}")

    def get_last_modified(self, url: str) -> Optional[str]:
        """
        Get the cached last-modified timestamp for a URL.

        Args:
            url: The URL to check

        Returns:
            Last-Modified timestamp or None
        """
        return self._last_modified_cache.get(url)

    def clear_cache(self) -> None:
        """Clear all cached headers and last-modified timestamps."""
        self._cached_base_headers = None
        self._last_modified_cache.clear()
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
            "conditional_requests": self.config.enable_conditional_requests,
            "browser_simulation": self.config.simulate_browser,
            "browser_type": self.config.browser_type,
            "custom_headers_count": len(self.config.custom_headers),
            "cached_last_modified_count": len(self._last_modified_cache),
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
