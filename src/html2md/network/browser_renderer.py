"""Isolated optional browser rendering for JavaScript-dependent pages."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, cast
from urllib.parse import urlsplit

from html2md.network.safe_http import (
    SAFE_CROSS_ORIGIN_HEADERS,
    DestinationPolicy,
    UnsafeNetworkTarget,
)


class RenderingUnavailable(RuntimeError):
    """Raised when the optional browser runtime is not installed."""


class RenderError(RuntimeError):
    """Raised when a browser render violates policy or cannot complete."""


@dataclass(frozen=True)
class RenderedPage:
    """Rendered HTML and the browser's final document URL."""

    html: str
    final_url: str


@dataclass
class BrowserRequestPolicy:
    """Validate, pin, and authorize each explicit browser origin."""

    source_url: str
    allow_private_network: bool = False
    additional_origins: Iterable[str] = field(default_factory=tuple)
    allowed_origins: set[tuple[str, str, Optional[int]]] = field(default_factory=set)
    pinned_hosts: dict[str, str] = field(default_factory=dict)
    pinned_address: str = field(init=False)

    def __post_init__(self) -> None:
        policy = DestinationPolicy(allow_private=self.allow_private_network)
        source_origin = self._authorize(self.source_url, policy)
        self.pinned_address = self.pinned_hosts[source_origin[1]]
        for url in self.additional_origins:
            self._authorize(url, policy)

    def _authorize(
        self, url: str, policy: DestinationPolicy
    ) -> tuple[str, str, Optional[int]]:
        origin = self._origin(url)
        if origin is None:
            raise RenderError(f"Invalid browser render origin: {url}")
        try:
            addresses = policy.addresses_for(url)
        except UnsafeNetworkTarget as error:
            raise RenderError(str(error)) from error
        address = addresses[0]
        existing = self.pinned_hosts.get(origin[1])
        if existing is not None and existing != address:
            raise RenderError(f"Conflicting validated addresses for {origin[1]}")
        self.pinned_hosts[origin[1]] = address
        self.allowed_origins.add(origin)
        return origin

    @staticmethod
    def _origin(url: str) -> Optional[tuple[str, str, Optional[int]]]:
        try:
            scheme, hostname, port = DestinationPolicy._origin(url)
        except UnsafeNetworkTarget:
            return None
        return scheme, hostname, port

    def permits(self, url: str, *, navigation: bool) -> bool:
        """Return whether a browser request is inside the render boundary."""
        scheme = urlsplit(url).scheme.casefold()
        if scheme == "about":
            return not navigation and url.casefold() == "about:blank"
        if scheme == "data":
            return not navigation
        if scheme == "blob":
            return not navigation and self._origin(url[5:]) in self.allowed_origins
        origin = self._origin(url)
        if origin is None:
            return False
        parsed = urlsplit(url)
        if parsed.username is not None or parsed.password is not None:
            return False
        return origin in self.allowed_origins

    def headers_for(
        self,
        url: str,
        browser_headers: Mapping[str, str],
        supplied_headers: Mapping[str, str],
    ) -> dict[str, str]:
        """Apply caller headers only where their credential context is valid."""
        headers = dict(browser_headers)
        origin = self._origin(url)
        source_origin = self._origin(self.source_url)
        if origin == source_origin:
            headers.update(supplied_headers)
            return headers
        sensitive = {"authorization", "cookie", "proxy-authorization"}
        headers = {
            name: value
            for name, value in headers.items()
            if name.casefold() not in sensitive
        }
        headers.update(
            {
                name: value
                for name, value in supplied_headers.items()
                if name.casefold() in SAFE_CROSS_ORIGIN_HEADERS
            }
        )
        return headers

    def host_resolver_rules(self) -> str:
        """Map the source hostname to its validated IP and fail all other DNS."""
        origin = self._origin(self.source_url)
        if origin is None:  # guarded by __post_init__
            raise RenderError("Browser rendering requires an HTTP(S) URL")
        rules = []
        for hostname, address in sorted(self.pinned_hosts.items()):
            rendered_hostname = f"[{hostname}]" if ":" in hostname else hostname
            rendered_address = f"[{address}]" if ":" in address else address
            rules.append(f"MAP {rendered_hostname} {rendered_address}")
        return ", ".join([*rules, "MAP * ~NOTFOUND"])


def render_html(
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    verify_ssl: bool = True,
    timeout_ms: int = 30_000,
    settle_ms: int = 500,
    max_html_bytes: int = 10 * 1024 * 1024,
    executable_path: Optional[str] = None,
    allow_private_network: bool = False,
    storage_state: Optional[Mapping[str, Any]] = None,
    allowed_origins: Iterable[str] = (),
    wait_until: str = "domcontentloaded",
    wait_for_selector: Optional[str] = None,
    max_requests: int = 250,
    blocked_resource_types: Iterable[str] = ("font", "image", "media"),
) -> RenderedPage:
    """Render one URL in a fresh non-persistent Chromium context."""
    readiness_modes = {"commit", "domcontentloaded", "load", "networkidle"}
    if (
        timeout_ms <= 0
        or not 0 <= settle_ms <= 5_000
        or max_html_bytes <= 0
        or max_requests <= 0
        or wait_until not in readiness_modes
        or wait_for_selector == ""
    ):
        raise ValueError("Invalid browser rendering resource limit")
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RenderingUnavailable(
            "JavaScript rendering requires 'html2md-cli[render]' and a Chromium "
            "runtime installed with 'python -m playwright install chromium'."
        ) from error

    policy = BrowserRequestPolicy(
        url,
        allow_private_network=allow_private_network,
        additional_origins=allowed_origins,
    )
    supplied_headers = dict(headers or {})
    user_agent = supplied_headers.get("User-Agent")
    browser_managed_headers = {
        "accept-encoding",
        "connection",
        "content-length",
        "cookie",
        "host",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "user-agent",
    }
    safe_headers = {
        key: value
        for key, value in supplied_headers.items()
        if key.casefold() not in browser_managed_headers
    }

    try:
        with sync_playwright() as playwright:
            executable_path = executable_path or os.getenv(
                "HTML2MD_CHROMIUM_EXECUTABLE"
            )
            browser = playwright.chromium.launch(
                headless=True,
                executable_path=executable_path,
                args=[
                    f"--host-resolver-rules={policy.host_resolver_rules()}",
                    "--no-proxy-server",
                ],
            )
            try:
                context = browser.new_context(
                    accept_downloads=False,
                    ignore_https_errors=not verify_ssl,
                    service_workers="block",
                    user_agent=user_agent,
                    storage_state=cast(
                        Any, dict(storage_state) if storage_state else None
                    ),
                )
                context.set_default_timeout(timeout_ms)
                context.set_default_navigation_timeout(timeout_ms)

                request_count = 0
                request_limit_exceeded = False
                blocked_types = set(blocked_resource_types)

                def handle_route(route) -> None:
                    nonlocal request_count, request_limit_exceeded
                    request = route.request
                    request_count += 1
                    if request_count > max_requests:
                        request_limit_exceeded = True
                        route.abort()
                        return
                    if request.resource_type in blocked_types:
                        route.abort()
                        return
                    if policy.permits(
                        request.url, navigation=request.is_navigation_request()
                    ):
                        route.continue_(
                            headers=policy.headers_for(
                                request.url, request.headers, safe_headers
                            )
                        )
                    else:
                        route.abort()

                context.route("**/*", handle_route)
                page = context.new_page()
                response = page.goto(url, wait_until=cast(Any, wait_until))
                if response is not None and response.status >= 400:
                    raise RenderError(f"Rendered page returned HTTP {response.status}")
                if wait_for_selector:
                    page.wait_for_selector(wait_for_selector, state="attached")
                if settle_ms:
                    page.wait_for_timeout(settle_ms)
                if request_limit_exceeded:
                    raise RenderError(
                        f"Browser rendering exceeded the {max_requests}-request limit"
                    )
                html = page.content()
                if len(html.encode("utf-8")) > max_html_bytes:
                    raise RenderError("Rendered HTML exceeds the 10 MiB limit")
                return RenderedPage(html=html, final_url=page.url)
            finally:
                browser.close()
    except PlaywrightTimeoutError as error:
        raise RenderError(
            f"Browser rendering timed out after {timeout_ms} ms"
        ) from error
    except PlaywrightError as error:
        raise RenderError(f"Browser rendering failed: {error}") from error
