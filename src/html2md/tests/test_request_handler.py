"""Tests for the crawler's structured HTTP response contract."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

import requests
import pytest

from html2md.network.request_handler import FetchResult, fetch_html


@pytest.fixture(autouse=True)
def route_mock_sessions_through_contract_boundary(monkeypatch):
    from html2md.network import request_handler

    original = request_handler.guarded_request

    def request(session, method, url, **kwargs):
        if isinstance(session, Mock):
            return session.request(
                method,
                url,
                headers=kwargs.get("headers"),
                data=kwargs.get("data"),
                timeout=kwargs.get("timeout"),
            )
        return original(session, method, url, **kwargs)

    monkeypatch.setattr(request_handler, "guarded_request", request)


class ContractHandler(BaseHTTPRequestHandler):
    counts: dict[str, int] = {}

    def do_GET(self):
        self.counts[self.path] = self.counts.get(self.path, 0) + 1
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
            return
        if self.path == "/limited":
            self.send_response(429)
            self.send_header("Retry-After", "7")
            self.end_headers()
            return
        if self.path == "/flaky" and self.counts[self.path] == 1:
            self.send_response(503)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body>ok</body></html>")

    def log_message(self, format, *args):
        pass


def start_contract_server():
    ContractHandler.counts = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), ContractHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def response(status, body="", url="https://example.com/final", headers=None):
    return Mock(status_code=status, text=body, url=url, headers=headers or {})


def test_fetch_result_preserves_redirect_target_status_and_headers():
    session = Mock()
    session.request.return_value = response(
        200,
        "<html>ok</html>",
        headers={"Content-Type": "text/html"},
    )

    result = fetch_html("https://example.com/start", session, {"Referer": "source"})

    assert isinstance(result, FetchResult)
    assert result.success is True
    assert result.final_url == "https://example.com/final"
    assert result.status_code == 200
    assert result.headers["Content-Type"] == "text/html"
    session.request.assert_called_once_with(
        "GET",
        "https://example.com/start",
        headers={"Referer": "source"},
        data=None,
        timeout=10,
    )


def test_server_error_retries_then_returns_real_success():
    session = Mock()
    session.request.side_effect = [response(503), response(200, "ok")]

    with patch("html2md.network.request_handler.time.sleep") as sleep:
        result = fetch_html("https://example.com", session, {}, max_retries=3)

    assert result.success is True
    assert result.status_code == 200
    assert result.attempts == 2
    sleep.assert_called_once_with(1)


def test_client_error_is_not_retried():
    session = Mock()
    session.request.return_value = response(404, "missing")

    result = fetch_html("https://example.com/missing", session, {}, max_retries=3)

    assert result.success is False
    assert result.status_code == 404
    assert result.attempts == 1
    session.request.assert_called_once()


def test_retry_after_is_exposed_to_domain_policy():
    result = FetchResult(
        requested_url="https://example.com",
        final_url="https://example.com",
        status_code=429,
        headers={"Retry-After": "7"},
        error="HTTP 429",
    )

    assert result.retry_after == 7


def test_connection_failure_returns_structured_error_without_final_sleep():
    session = Mock()
    session.request.side_effect = requests.ConnectionError("offline")

    with patch("html2md.network.request_handler.time.sleep") as sleep:
        result = fetch_html("https://example.com", session, {}, max_retries=2)

    assert result.success is False
    assert result.status_code is None
    assert "ConnectionError" in result.error
    assert result.attempts == 2
    sleep.assert_called_once_with(1)


def test_local_server_redirect_reports_final_url_and_success():
    server, base_url = start_contract_server()
    try:
        result = fetch_html(
            f"{base_url}/redirect",
            requests.Session(),
            {},
            allow_private_network=True,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result.success is True
    assert result.status_code == 200
    assert result.final_url == f"{base_url}/ok"
    assert ContractHandler.counts == {"/redirect": 1, "/ok": 1}


def test_local_server_429_preserves_retry_after_without_hidden_retry():
    server, base_url = start_contract_server()
    try:
        result = fetch_html(
            f"{base_url}/limited",
            requests.Session(),
            {},
            allow_private_network=True,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result.status_code == 429
    assert result.retry_after == 7
    assert ContractHandler.counts["/limited"] == 1


def test_local_server_5xx_retries_and_recovers():
    server, base_url = start_contract_server()
    try:
        with patch("html2md.network.request_handler.time.sleep"):
            result = fetch_html(
                f"{base_url}/flaky",
                requests.Session(),
                {},
                allow_private_network=True,
            )
    finally:
        server.shutdown()
        server.server_close()

    assert result.success is True
    assert result.status_code == 200
    assert result.attempts == 2
    assert ContractHandler.counts["/flaky"] == 2
