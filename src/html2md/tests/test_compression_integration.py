"""Deterministic integration tests for advertised HTTP compression support."""

import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import zlib

import brotli
import pytest
import requests

from html2md.markdown.converter import html_to_markdown
from html2md.network.header_manager import HeaderManager


HTML = b"<!DOCTYPE html><html><body><h1>Compression Test</h1></body></html>"


class CompressionHandler(BaseHTTPRequestHandler):
    """Serve the same HTML using the encoding named by the request path."""

    def do_GET(self):
        encoding = self.path.lstrip("/")
        compressors = {
            "identity": lambda content: content,
            "gzip": gzip.compress,
            "deflate": zlib.compress,
            "br": brotli.compress,
        }
        body = compressors[encoding](HTML)

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if encoding != "identity":
            self.send_header("Content-Encoding", encoding)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Keep test output quiet."""


@pytest.fixture
def compression_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), CompressionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate", "br"])
def test_advertised_compression_is_decoded(compression_server, encoding):
    url = f"{compression_server}/{encoding}"
    headers = HeaderManager().get_headers(url)

    result = html_to_markdown(
        url,
        session=requests.Session(),
        headers=headers,
        allow_private_network=True,
    )

    assert result is not None
    assert "# Compression Test" in result
    if encoding != "identity":
        assert encoding in headers["Accept-Encoding"]
