"""Deterministic static-versus-rendered browser fixture."""

from __future__ import annotations

import os
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from unittest.mock import patch

from html2md.markdown.converter import html_to_markdown
from html2md.network.auth_inputs import load_storage_state
from html2md.network.browser_renderer import render_html


class JavaScriptFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/authenticated":
            authenticated = (
                "session=secret" in self.headers.get("Cookie", "")
                and self.headers.get("X-Tenant") == "docs"
            )
            body = (
                b"<html><body><h1>Authenticated</h1></body></html>"
                if authenticated
                else b"<html><body><h1>Guest</h1></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b"""<!doctype html><html><body>
        <h1>Fixture</h1><div id="app">Static placeholder</div>
        <script>
        document.querySelector('#app').innerHTML =
          '<h2>Rendered content</h2><p>Created by JavaScript.</p>';
        </script></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def test_static_and_browser_modes_have_deterministic_distinct_output():
    if os.getenv("HTML2MD_RUN_RENDER_E2E") != "1":
        pytest.skip("set HTML2MD_RUN_RENDER_E2E=1 with the render extra and Chromium")

    server = ThreadingHTTPServer(("127.0.0.1", 0), JavaScriptFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/fixture"
    try:
        static = html_to_markdown(url, trim=False, allow_private_network=True)
        rendered = html_to_markdown(
            url, trim=False, render_js=True, allow_private_network=True
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert static is not None and rendered is not None
    assert "Static placeholder" in static
    assert "Created by JavaScript" not in static
    assert "## Rendered content" in rendered
    assert "Created by JavaScript" in rendered
    assert "Static placeholder" not in rendered


def test_browser_connects_to_the_single_python_validated_address():
    if os.getenv("HTML2MD_RUN_RENDER_E2E") != "1":
        pytest.skip("set HTML2MD_RUN_RENDER_E2E=1 with the render extra and Chromium")

    server = ThreadingHTTPServer(("127.0.0.1", 0), JavaScriptFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://rebind.invalid:{server.server_port}/fixture"
    records = [(2, 1, 6, "", ("127.0.0.1", server.server_port))]
    try:
        with patch("socket.getaddrinfo", return_value=records) as dns:
            rendered = render_html(url, allow_private_network=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    dns.assert_called_once()
    assert rendered.final_url == url
    assert "Rendered content" in rendered.html


def test_browser_storage_state_authenticates_the_isolated_context(tmp_path):
    if os.getenv("HTML2MD_RUN_RENDER_E2E") != "1":
        pytest.skip("set HTML2MD_RUN_RENDER_E2E=1 with the render extra and Chromium")

    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "session",
                        "value": "secret",
                        "domain": "127.0.0.1",
                        "path": "/",
                        "expires": -1,
                        "httpOnly": True,
                        "secure": False,
                        "sameSite": "Lax",
                    }
                ],
                "origins": [],
            }
        ),
        encoding="utf-8",
    )
    if os.name == "posix":
        state.chmod(0o600)
    server = ThreadingHTTPServer(("127.0.0.1", 0), JavaScriptFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/authenticated"
    try:
        guest = render_html(url, allow_private_network=True)
        authenticated = render_html(
            url,
            allow_private_network=True,
            headers={"X-Tenant": "docs"},
            storage_state=load_storage_state(state),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert "Guest" in guest.html
    assert "Authenticated" in authenticated.html
