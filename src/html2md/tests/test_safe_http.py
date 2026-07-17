"""Adversarial tests for the shared outbound HTTP boundary."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import pytest
import requests

from html2md.network.safe_http import (
    DestinationPolicy,
    PinnedHttpClient,
    ResponseTooLarge,
    UnsafeNetworkTarget,
    _PinnedAddressAdapter,
    guarded_request,
)
from html2md.network.chatgpt_handler import extract_conversation_id, is_chatgpt_url


PUBLIC_DNS = [(2, 1, 6, "", ("93.184.216.34", 443))]


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fe80::1"],
)
def test_default_policy_rejects_every_non_public_address(address):
    family = 10 if ":" in address else 2
    with patch(
        "html2md.network.safe_http.socket.getaddrinfo",
        return_value=[(family, 1, 6, "", (address, 443))],
    ):
        with pytest.raises(UnsafeNetworkTarget, match="non-public"):
            DestinationPolicy().addresses_for("https://target.example/path")


def test_private_destinations_require_explicit_authorization():
    records = [(2, 1, 6, "", ("127.0.0.1", 8080))]
    with patch("html2md.network.safe_http.socket.getaddrinfo", return_value=records):
        addresses = DestinationPolicy(allow_private=True).addresses_for(
            "http://localhost:8080/path"
        )
    assert addresses == ("127.0.0.1",)


def test_policy_resolves_an_origin_once_and_reuses_its_pin():
    dns = MagicMock(return_value=PUBLIC_DNS)
    policy = DestinationPolicy()
    with patch("html2md.network.safe_http.socket.getaddrinfo", dns):
        first = policy.addresses_for("https://example.com/one")
        second = policy.addresses_for("https://example.com/two")
    assert first == second == ("93.184.216.34",)
    dns.assert_called_once()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:secret@example.com/",
        "https://bad_host.example/",
        "https://example.com:invalid/",
        "https://evil.example,MAP * 127.0.0.1/",
    ],
)
def test_policy_rejects_malformed_or_credential_bearing_urls(url):
    with pytest.raises(UnsafeNetworkTarget):
        DestinationPolicy().addresses_for(url)


def test_transport_connects_only_to_the_validated_numeric_address(monkeypatch):
    dns = MagicMock(return_value=[(2, 1, 6, "", ("93.184.216.34", 80))])
    connect = MagicMock(side_effect=OSError("stop after socket target inspection"))
    monkeypatch.setattr("socket.getaddrinfo", dns)
    monkeypatch.setattr("urllib3.util.connection.create_connection", connect)
    monkeypatch.setenv("HTTP_PROXY", "http://environment-proxy.invalid:8080")

    session = requests.Session()
    session.proxies = {"http": "http://session-proxy.invalid:8080"}
    with PinnedHttpClient(session, DestinationPolicy()) as client:
        with pytest.raises(requests.ConnectionError):
            client.request("GET", "http://target.example/page")

    dns.assert_called_once()
    assert connect.call_count == 1
    assert connect.call_args.args[0] == ("93.184.216.34", 80)


def test_redirect_is_revalidated_before_the_second_request():
    redirect = requests.Response()
    redirect.status_code = 302
    redirect.url = "https://public.example/start"
    redirect.headers["Location"] = "http://169.254.169.254/latest/meta-data"
    redirect.raw = MagicMock()

    def dns(hostname, port, **_kwargs):
        address = "93.184.216.34" if hostname == "public.example" else hostname
        return [(2, 1, 6, "", (address, port))]

    with patch("html2md.network.safe_http.socket.getaddrinfo", side_effect=dns):
        with PinnedHttpClient(requests.Session(), DestinationPolicy()) as client:
            client.session.request = MagicMock(return_value=redirect)
            with pytest.raises(UnsafeNetworkTarget, match="non-public"):
                client.request("GET", "https://public.example/start")
            client.session.request.assert_called_once()


def test_redirect_callback_runs_before_the_second_request():
    redirect = requests.Response()
    redirect.status_code = 302
    redirect.url = "https://one.example/start"
    redirect.headers["Location"] = "https://two.example/final"
    redirect.raw = MagicMock()
    validator = MagicMock(side_effect=UnsafeNetworkTarget("robots denied"))

    with patch("html2md.network.safe_http.socket.getaddrinfo", return_value=PUBLIC_DNS):
        with PinnedHttpClient(requests.Session(), DestinationPolicy()) as client:
            client.session.request = MagicMock(return_value=redirect)
            with pytest.raises(UnsafeNetworkTarget, match="robots denied"):
                client.request(
                    "GET",
                    "https://one.example/start",
                    redirect_validator=validator,
                )

    validator.assert_called_once_with(
        "https://one.example/start", "https://two.example/final"
    )
    client.session.request.assert_called_once()


def test_cross_origin_redirect_strips_explicit_credentials():
    redirect = requests.Response()
    redirect.status_code = 302
    redirect.url = "https://one.example/start"
    redirect.headers["Location"] = "https://two.example/final"
    redirect.raw = MagicMock()
    final = requests.Response()
    final.status_code = 200
    final.url = "https://two.example/final"
    final.raw = MagicMock()

    with patch("html2md.network.safe_http.socket.getaddrinfo", return_value=PUBLIC_DNS):
        source = requests.Session()
        source.headers.update(
            {"Authorization": "session secret", "X-API-Key": "also secret"}
        )
        with PinnedHttpClient(source, DestinationPolicy()) as client:
            client.session.request = MagicMock(side_effect=[redirect, final])
            client.request(
                "GET",
                "https://one.example/start",
                headers={
                    "Authorization": "Bearer secret",
                    "Cookie": "token=secret",
                    "X-Custom-Secret": "secret",
                    "Accept": "text/html",
                },
            )

    second_headers = client.session.request.call_args_list[1].kwargs["headers"]
    assert "Authorization" not in second_headers
    assert "Cookie" not in second_headers
    assert "X-Custom-Secret" not in second_headers
    assert second_headers["Accept"] == "text/html"
    assert "Authorization" not in client.session.headers
    assert "X-API-Key" not in client.session.headers


def test_cross_origin_redirect_never_replays_a_request_body():
    redirect = requests.Response()
    redirect.status_code = 307
    redirect.url = "https://one.example/start"
    redirect.headers["Location"] = "https://two.example/final"
    redirect.raw = MagicMock()

    with patch("html2md.network.safe_http.socket.getaddrinfo", return_value=PUBLIC_DNS):
        with PinnedHttpClient(requests.Session(), DestinationPolicy()) as client:
            client.session.request = MagicMock(return_value=redirect)
            with pytest.raises(UnsafeNetworkTarget, match="request body"):
                client.request("POST", "https://one.example/start", data="sensitive")
            client.session.request.assert_called_once()


class _BodyHandler(BaseHTTPRequestHandler):
    body = b"x" * 64

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *_args):
        return


def test_buffered_response_limit_covers_private_opt_in_traffic():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _BodyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/body"
    try:
        with pytest.raises(ResponseTooLarge, match="exceeds 32 bytes"):
            guarded_request(
                requests.Session(),
                "GET",
                url,
                policy=DestinationPolicy(allow_private=True),
                max_body_bytes=32,
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_https_adapter_preserves_host_sni_and_certificate_identity():
    adapter = _PinnedAddressAdapter("93.184.216.34")
    adapter.poolmanager = MagicMock()
    request = requests.Request("GET", "https://assets.example.test:8443/page").prepare()

    adapter.get_connection_with_tls_context(request, verify=True)
    adapter.add_headers(request)

    call = adapter.poolmanager.connection_from_host.call_args
    assert call.kwargs["host"] == "93.184.216.34"
    assert call.kwargs["pool_kwargs"]["server_hostname"] == "assets.example.test"
    assert call.kwargs["pool_kwargs"]["assert_hostname"] == "assets.example.test"
    assert request.headers["Host"] == "assets.example.test:8443"


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/?next=chatgpt.com/c/secret",
        "https://chatgpt.com.evil.example/c/secret",
        "https://chatgpt.com@evil.example/c/secret",
        "http://chatgpt.com/c/secret",
    ],
)
def test_chatgpt_special_handling_requires_exact_https_origin(url):
    assert is_chatgpt_url(url) is False
    assert extract_conversation_id(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://chatgpt.com/c/conversation-id",
        "https://chat.openai.com/share/conversation-id",
    ],
)
def test_chatgpt_special_handling_accepts_supported_exact_origins(url):
    assert is_chatgpt_url(url) is True
    assert extract_conversation_id(url) == "conversation-id"
