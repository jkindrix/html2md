"""
Robots.txt parser for respecting website crawling policies.

This module provides functionality to:
- Fetch and parse robots.txt files
- Check if URLs are allowed to be crawled
- Extract crawl-delay directives
- Cache robots.txt content for efficiency
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from html2md.network.safe_http import DestinationPolicy, guarded_request

logger = logging.getLogger("html2md")


@dataclass(frozen=True)
class RobotsFetchResult:
    """robots.txt response data needed to apply RFC 9309 failure policy."""

    content: Optional[str]
    status_code: Optional[int]


class RobotsChecker:
    """
    A robots.txt parser that respects website crawling policies.

    Features:
    - Caches robots.txt content to avoid repeated fetches
    - Supports crawl-delay directives
    - Handles various edge cases (missing robots.txt, malformed content)
    - Serializes cache/session access for concurrent callers
    """

    def __init__(
        self,
        user_agent: str = "html2md",
        session: Optional[requests.Session] = None,
        network_policy: Optional[DestinationPolicy] = None,
        allow_private_network: bool = False,
    ):
        """
        Initialize the robots checker.

        Args:
            user_agent: The user agent string to use when checking rules
            session: Optional requests session for connection pooling
        """
        self.user_agent = user_agent
        self._product_token = user_agent.split()[0].split("/", 1)[0].lower()
        self.session = session or requests.Session()
        self.network_policy = network_policy or DestinationPolicy(
            allow_private=allow_private_network
        )
        self._cache: Dict[str, Tuple[RobotFileParser, Optional[float], float]] = {}
        self._cache_duration = 3600  # Cache robots.txt for 1 hour
        self._lock = threading.RLock()

    def _get_robots_url(self, url: str) -> str:
        """Get the robots.txt URL for a given URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def _fetch_robots_txt(self, robots_url: str) -> RobotsFetchResult:
        """
        Fetch robots.txt content from a URL.

        Returns:
            Content and HTTP status, or no status for a network failure.
        """
        try:
            response = guarded_request(
                self.session,
                "GET",
                robots_url,
                policy=self.network_policy,
                timeout=10,
                max_body_bytes=1024 * 1024,
                headers={"User-Agent": self.user_agent},
            )
            if 200 <= response.status_code < 300:
                return RobotsFetchResult(response.text, response.status_code)
            if 400 <= response.status_code < 500:
                logger.debug(
                    f"robots.txt unavailable at {robots_url}: HTTP {response.status_code}"
                )
                return RobotsFetchResult("", response.status_code)
            else:
                logger.warning(
                    f"Failed to fetch robots.txt from {robots_url}: HTTP {response.status_code}"
                )
                return RobotsFetchResult(None, response.status_code)
        except requests.RequestException as e:
            logger.warning(f"Error fetching robots.txt from {robots_url}: {e}")
            return RobotsFetchResult(None, None)

    def _parse_crawl_delay(self, content: str) -> Optional[float]:
        """
        Extract crawl-delay directive from robots.txt content.

        Args:
            content: The robots.txt content

        Returns:
            Crawl delay in seconds, or None if not specified
        """
        if not content:
            return None

        # Group consecutive User-agent fields and apply the product-token group
        # in preference to the wildcard group.
        groups: list[tuple[list[str], list[tuple[str, str]]]] = []
        agents: list[str] = []
        directives: list[tuple[str, str]] = []
        seen_directive = False

        def finish_group():
            if agents:
                groups.append((list(agents), list(directives)))

        for raw_line in content.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.lower()
            if field == "user-agent":
                if seen_directive:
                    finish_group()
                    agents.clear()
                    directives.clear()
                    seen_directive = False
                agents.append(value.lower())
            elif agents:
                seen_directive = True
                directives.append((field, value))
        finish_group()

        def delay_for(agent_name):
            for group_agents, group_directives in groups:
                if agent_name not in group_agents:
                    continue
                for field, value in group_directives:
                    if field == "crawl-delay":
                        try:
                            return float(value)
                        except ValueError:
                            logger.warning("Invalid crawl-delay value: %s", value)
            return None

        specific_delay = delay_for(self._product_token)
        return specific_delay if specific_delay is not None else delay_for("*")

    def _get_cached_or_fetch(self, url: str) -> Tuple[RobotFileParser, Optional[float]]:
        """
        Get robots.txt parser from cache or fetch if needed.

        Returns:
            Tuple of (RobotFileParser, crawl_delay)
        """
        robots_url = self._get_robots_url(url)
        with self._lock:
            if robots_url in self._cache:
                parser, crawl_delay, cached_time = self._cache[robots_url]
                if time.time() - cached_time < self._cache_duration:
                    return parser, crawl_delay

            fetch_result = self._fetch_robots_txt(robots_url)
            content = fetch_result.content

            parser = RobotFileParser()
            parser.set_url(robots_url)

            if (
                fetch_result.status_code is not None
                and 400 <= fetch_result.status_code < 500
            ):
                # RFC 9309: an unavailable robots.txt permits access.
                setattr(parser, "allow_all", True)
            elif content is not None:
                parser.parse(content.split("\n"))
            else:
                # RFC 9309: unreachable or 5xx robots.txt is temporarily unavailable;
                # crawlers must assume complete disallow.
                setattr(parser, "disallow_all", True)

            crawl_delay = self._parse_crawl_delay(content) if content else None
            self._cache[robots_url] = (parser, crawl_delay, time.time())
            return parser, crawl_delay

    def can_fetch(self, url: str) -> bool:
        """
        Check if a URL can be fetched according to robots.txt.

        Args:
            url: The URL to check

        Returns:
            True if the URL can be fetched, False otherwise
        """
        try:
            parser, _ = self._get_cached_or_fetch(url)
            return parser.can_fetch(self._product_token, url)
        except Exception as e:
            logger.error(f"Error checking robots.txt for {url}: {e}")
            return False

    def get_crawl_delay(self, url: str) -> Optional[float]:
        """
        Get the crawl-delay for a given URL from robots.txt.

        Args:
            url: The URL to check

        Returns:
            Crawl delay in seconds, or None if not specified
        """
        try:
            _, crawl_delay = self._get_cached_or_fetch(url)
            return crawl_delay
        except Exception as e:
            logger.error(f"Error getting crawl-delay for {url}: {e}")
            return None

    def filter_urls(self, urls: list) -> list:
        """
        Filter a list of URLs to only include those allowed by robots.txt.

        Args:
            urls: List of URLs to filter

        Returns:
            List of allowed URLs
        """
        allowed_urls = []
        for url in urls:
            if self.can_fetch(url):
                allowed_urls.append(url)
            else:
                logger.info(f"URL disallowed by robots.txt: {url}")
        return allowed_urls

    def clear_cache(self):
        """Clear the robots.txt cache."""
        with self._lock:
            self._cache.clear()
