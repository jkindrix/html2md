"""Isolated optional browser rendering for JavaScript-dependent pages."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional
from urllib.parse import urlsplit

from html2md.network.safe_http import DestinationPolicy, UnsafeNetworkTarget


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
    """Permit traffic only to the explicitly pinned source origin."""

    source_url: str
    allow_private_network: bool = False
    allowed_origins: set[tuple[str, str, Optional[int]]] = field(default_factory=set)
    pinned_address: str = field(init=False)

    def __post_init__(self) -> None:
        origin = self._origin(self.source_url)
        if origin is None:
            raise RenderError("Browser rendering requires an HTTP(S) URL")
        try:
            addresses = DestinationPolicy(
                allow_private=self.allow_private_network
            ).addresses_for(self.source_url)
        except UnsafeNetworkTarget as error:
            raise RenderError(str(error)) from error
        self.pinned_address = addresses[0]
        self.allowed_origins.add(origin)

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
        if scheme in {"about", "blob", "data"}:
            return True
        origin = self._origin(url)
        if origin is None:
            return False
        parsed = urlsplit(url)
        if parsed.username is not None or parsed.password is not None:
            return False
        del navigation
        return origin in self.allowed_origins

    def host_resolver_rules(self) -> str:
        """Map the source hostname to its validated IP and fail all other DNS."""
        origin = self._origin(self.source_url)
        if origin is None:  # guarded by __post_init__
            raise RenderError("Browser rendering requires an HTTP(S) URL")
        address = self.pinned_address
        hostname = origin[1]
        if ":" in hostname:
            hostname = f"[{hostname}]"
        if ":" in address:
            address = f"[{address}]"
        return f"MAP {hostname} {address}, MAP * ~NOTFOUND"


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
) -> RenderedPage:
    """Render one URL in a fresh non-persistent Chromium context."""
    if timeout_ms <= 0 or not 0 <= settle_ms <= 5_000 or max_html_bytes <= 0:
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

    policy = BrowserRequestPolicy(url, allow_private_network=allow_private_network)
    supplied_headers = dict(headers or {})
    user_agent = supplied_headers.get("User-Agent")
    safe_headers = {
        key: value
        for key, value in supplied_headers.items()
        if key.casefold() in {"accept-language", "dnt"}
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
                    extra_http_headers=safe_headers,
                    user_agent=user_agent,
                )
                context.set_default_timeout(timeout_ms)
                context.set_default_navigation_timeout(timeout_ms)

                def handle_route(route) -> None:
                    request = route.request
                    if request.resource_type in {"font", "image", "media"}:
                        route.abort()
                        return
                    if policy.permits(
                        request.url, navigation=request.is_navigation_request()
                    ):
                        route.continue_()
                    else:
                        route.abort()

                context.route("**/*", handle_route)
                page = context.new_page()
                response = page.goto(url, wait_until="domcontentloaded")
                if response is not None and response.status >= 400:
                    raise RenderError(f"Rendered page returned HTTP {response.status}")
                if settle_ms:
                    page.wait_for_timeout(settle_ms)
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
