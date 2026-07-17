"""Destination-validated HTTP transport for untrusted web content."""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, MutableMapping, Optional, cast
from urllib.parse import urljoin, urlsplit

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter


DEFAULT_MAX_BODY_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_REDIRECTS = 5
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
SAFE_CROSS_ORIGIN_HEADERS = {
    "accept",
    "accept-encoding",
    "accept-language",
    "cache-control",
    "dnt",
    "pragma",
    "upgrade-insecure-requests",
    "user-agent",
}


class UnsafeNetworkTarget(requests.RequestException):
    """Raised when a URL violates the outbound destination policy."""


class ResponseTooLarge(requests.RequestException):
    """Raised when a remote response exceeds its configured byte limit."""


class _PinnedAddressAdapter(HTTPAdapter):
    """Connect to one validated address while preserving HTTP/TLS identity."""

    def __init__(self, address: str):
        self.address = address
        super().__init__(pool_connections=1, pool_maxsize=1, max_retries=0)

    def get_connection_with_tls_context(
        self,
        request: Any,
        verify: Any,
        proxies: Optional[Mapping[str, str]] = None,
        cert: Any = None,
    ) -> Any:
        del proxies
        host_params, typed_pool_kwargs = self.build_connection_pool_key_attributes(
            request, verify, cert
        )
        pool_kwargs: Dict[str, Any] = dict(typed_pool_kwargs)
        expected_hostname = str(host_params["host"])
        host_params["host"] = self.address
        if host_params["scheme"] == "https":
            pool_kwargs["assert_hostname"] = expected_hostname
            pool_kwargs["server_hostname"] = expected_hostname
        return self.poolmanager.connection_from_host(
            **host_params, pool_kwargs=pool_kwargs
        )

    def add_headers(self, request: Any, **kwargs: Any) -> None:
        super().add_headers(request, **kwargs)
        parsed = urlsplit(request.url)
        request.headers["Host"] = parsed.netloc


Origin = tuple[str, str, int]


@dataclass
class DestinationPolicy:
    """Resolve each origin once and retain only authorized numeric addresses."""

    allow_private: bool = False
    _pins: MutableMapping[Origin, tuple[str, ...]] = field(default_factory=dict)

    @staticmethod
    def _origin(url: str) -> Origin:
        parsed = urlsplit(url)
        scheme = parsed.scheme.casefold()
        if scheme not in {"http", "https"} or not parsed.hostname:
            raise UnsafeNetworkTarget("Only HTTP(S) network URLs are allowed")
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeNetworkTarget(
                "Network URLs containing credentials are not allowed"
            )
        raw_hostname = parsed.hostname
        try:
            ipaddress.ip_address(raw_hostname.split("%", 1)[0])
            hostname = raw_hostname.casefold()
        except ValueError:
            try:
                hostname = raw_hostname.encode("idna").decode("ascii").casefold()
            except UnicodeError as error:
                raise UnsafeNetworkTarget(
                    "Network URL contains an invalid host"
                ) from error
            if len(hostname) > 253 or any(
                not label
                or len(label) > 63
                or re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) is None
                for label in hostname.rstrip(".").split(".")
            ):
                raise UnsafeNetworkTarget("Network URL contains an invalid host")
        try:
            port = parsed.port or (443 if scheme == "https" else 80)
        except ValueError as error:
            raise UnsafeNetworkTarget("Network URL contains an invalid port") from error
        return scheme, hostname, port

    def addresses_for(self, url: str) -> tuple[str, ...]:
        """Return stable validated addresses for the URL origin."""
        origin = self._origin(url)
        cached = self._pins.get(origin)
        if cached is not None:
            return cached

        _, hostname, port = origin
        try:
            records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as error:
            raise UnsafeNetworkTarget(
                f"Network host cannot be resolved: {hostname}"
            ) from error
        if not records:
            raise UnsafeNetworkTarget(f"Network host has no addresses: {hostname}")

        addresses: list[str] = []
        for record in records:
            raw_address = str(record[4][0]).split("%", 1)[0]
            try:
                address = ipaddress.ip_address(raw_address)
            except ValueError as error:
                raise UnsafeNetworkTarget(
                    f"Invalid resolved network address: {raw_address}"
                ) from error
            if not self.allow_private and not address.is_global:
                raise UnsafeNetworkTarget(
                    f"Network host resolves to a non-public address: {raw_address}; "
                    "use --allow-private-network only for destinations you trust"
                )
            normalized = str(address)
            if normalized not in addresses:
                addresses.append(normalized)

        pinned = tuple(addresses)
        self._pins[origin] = pinned
        return pinned


def _clone_direct_session(source: Session) -> Session:
    """Copy request identity into a session that cannot delegate DNS to a proxy."""
    direct = requests.Session()
    direct.headers.clear()
    direct.headers.update(getattr(source, "headers", {}))
    source_cookies = getattr(source, "cookies", None)
    if source_cookies is not None:
        direct.cookies.update(source_cookies)
    direct.auth = getattr(source, "auth", None)
    direct.verify = getattr(source, "verify", True)
    direct.cert = getattr(source, "cert", None)
    source_params = cast(Mapping[str, Any], getattr(source, "params", {}))
    direct.params = dict(source_params)
    direct.trust_env = False
    direct.proxies.clear()
    return direct


class PinnedHttpClient:
    """Issue requests only to addresses authorized by a destination policy."""

    def __init__(self, session: Session, policy: DestinationPolicy):
        self.source = session
        self.policy = policy
        self.session = _clone_direct_session(session)

    def __enter__(self) -> "PinnedHttpClient":
        return self

    def __exit__(self, *_args: object) -> None:
        source_cookies = getattr(self.source, "cookies", None)
        if source_cookies is not None:
            source_cookies.update(self.session.cookies)
        self.session.close()

    def _mount(self, address: str) -> None:
        for prefix in ("http://", "https://"):
            previous = self.session.adapters.get(prefix)
            if previous is not None:
                previous.close()
            self.session.mount(prefix, _PinnedAddressAdapter(address))

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        data: Any = None,
        timeout: float = 30,
        stream: bool = False,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        redirect_validator: Optional[Callable[[str, str], None]] = None,
    ) -> Response:
        """Request a URL, manually validating and pinning each redirect hop."""
        if max_redirects < 0:
            raise ValueError("max_redirects cannot be negative")

        current_url = url
        current_method = method.upper()
        current_data = data
        current_headers = dict(headers or {})
        history: list[Response] = []

        for redirect_count in range(max_redirects + 1):
            addresses = self.policy.addresses_for(current_url)
            response: Optional[Response] = None
            last_error: Optional[requests.RequestException] = None
            for address in addresses:
                self._mount(address)
                try:
                    response = self.session.request(
                        current_method,
                        current_url,
                        headers=current_headers,
                        data=current_data,
                        timeout=timeout,
                        stream=stream,
                        allow_redirects=False,
                    )
                    break
                except (requests.ConnectionError, requests.Timeout) as error:
                    last_error = error
            if response is None:
                if last_error is not None:
                    raise last_error
                raise UnsafeNetworkTarget("Network host has no usable address")

            response.history = list(history)
            if response.status_code not in REDIRECT_STATUSES:
                return response

            location = response.headers.get("Location")
            if not location:
                response.close()
                raise requests.TooManyRedirects("Redirect response has no Location")
            if redirect_count == max_redirects:
                response.close()
                raise requests.TooManyRedirects("Redirect limit exceeded")

            next_url = urljoin(current_url, location)
            # Validate before releasing the current hop so unsafe redirects fail closed.
            self.policy.addresses_for(next_url)
            if redirect_validator is not None:
                redirect_validator(current_url, next_url)
            cross_origin = DestinationPolicy._origin(
                current_url
            ) != DestinationPolicy._origin(next_url)
            if cross_origin and current_method not in {"GET", "HEAD"}:
                response.close()
                raise UnsafeNetworkTarget(
                    "Cross-origin redirect cannot replay a request body"
                )
            history.append(response)
            response.close()

            if response.status_code == 303 and current_method != "HEAD":
                current_method = "GET"
            elif response.status_code == 302 and current_method != "HEAD":
                current_method = "GET"
            elif response.status_code == 301 and current_method == "POST":
                current_method = "GET"
            if current_method == "GET":
                current_data = None
                for name in ("Content-Length", "Content-Type", "Transfer-Encoding"):
                    current_headers.pop(name, None)

            current_headers.pop("Cookie", None)
            self.session.headers.pop("Cookie", None)
            if cross_origin:
                current_headers = {
                    name: value
                    for name, value in current_headers.items()
                    if name.casefold() in SAFE_CROSS_ORIGIN_HEADERS
                }
                self.session.headers = requests.structures.CaseInsensitiveDict(
                    {
                        name: value
                        for name, value in self.session.headers.items()
                        if name.casefold() in SAFE_CROSS_ORIGIN_HEADERS
                    }
                )
            if self.session.should_strip_auth(current_url, next_url):
                current_headers.pop("Authorization", None)
                self.session.headers.pop("Authorization", None)
                self.session.auth = None
            current_url = next_url

        raise requests.TooManyRedirects("Redirect limit exceeded")


def guarded_request(
    session: Session,
    method: str,
    url: str,
    *,
    policy: Optional[DestinationPolicy] = None,
    headers: Optional[Mapping[str, str]] = None,
    data: Any = None,
    timeout: float = 30,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    redirect_validator: Optional[Callable[[str, str], None]] = None,
) -> Response:
    """Return a fully buffered response obtained through the guarded transport."""
    if max_body_bytes <= 0:
        raise ValueError("max_body_bytes must be positive")
    active_policy = policy or DestinationPolicy()
    with PinnedHttpClient(session, active_policy) as client:
        response = client.request(
            method,
            url,
            headers=headers,
            data=data,
            timeout=timeout,
            stream=True,
            max_redirects=max_redirects,
            redirect_validator=redirect_validator,
        )
        try:
            declared_length = response.headers.get("Content-Length")
            if declared_length is not None:
                try:
                    if int(declared_length) > max_body_bytes:
                        raise ResponseTooLarge(
                            f"Remote response exceeds {max_body_bytes} bytes"
                        )
                except ValueError:
                    pass

            chunks: list[bytes] = []
            byte_count = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                byte_count += len(chunk)
                if byte_count > max_body_bytes:
                    raise ResponseTooLarge(
                        f"Remote response exceeds {max_body_bytes} bytes"
                    )
                chunks.append(chunk)
            response._content = b"".join(chunks)
            setattr(response, "_content_consumed", True)
            return response
        finally:
            response.close()
