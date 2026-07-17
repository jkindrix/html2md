from unittest.mock import MagicMock, patch

import pytest
import requests

from html2md.markdown.converter import local_html_to_markdown
from html2md.network.image_downloader import (
    ImageDownloader,
    UnsafeImageSource,
    _PinnedAddressAdapter,
    _PinnedExchange,
)


PNG = b"\x89PNG\r\n\x1a\n" + b"safe-image-data"
JPEG = b"\xff\xd8\xff" + b"safe-image-data"
PUBLIC_DNS = [(2, 1, 6, "", ("93.184.216.34", 443))]


class FakeResponse:
    def __init__(self, status=200, headers=None, chunks=None):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks or []
        self.closed = False

    def iter_content(self, chunk_size=8192):
        del chunk_size
        yield from self._chunks

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def route_fake_sessions_through_the_pinned_boundary(monkeypatch):
    original = ImageDownloader._send_to_address

    def send(downloader, url, address, **_kwargs):
        if isinstance(downloader.session, FakeSession):
            response = downloader.session.get(
                url,
                timeout=downloader.timeout,
                stream=True,
                allow_redirects=False,
                pinned_address=address,
            )
            return _PinnedExchange(response=response, session=None)
        return original(downloader, url, address)

    monkeypatch.setattr(ImageDownloader, "_send_to_address", send)


def public_dns(*args, **kwargs):
    del args, kwargs
    return PUBLIC_DNS


@pytest.mark.parametrize(
    "url",
    [
        "data:image/png;base64,AAAA",
        "ftp://example.com/image.png",
        "javascript:alert(1)",
        "https://user:secret@example.com/image.png",
    ],
)
def test_remote_policy_rejects_unsafe_schemes_and_credentials(tmp_path, url):
    downloader = ImageDownloader(session=FakeSession())

    with patch("html2md.network.safe_http.socket.getaddrinfo", public_dns):
        assert downloader.download_image(url, tmp_path) is None


@pytest.mark.parametrize(
    "resolved_address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "0.0.0.0",
    ],
)
def test_remote_policy_blocks_non_public_and_metadata_destinations(
    tmp_path, resolved_address
):
    family = 10 if ":" in resolved_address else 2

    def private_dns(*args, **kwargs):
        del args, kwargs
        return [(family, 1, 6, "", (resolved_address, 443))]

    session = FakeSession(
        FakeResponse(headers={"Content-Type": "image/png"}, chunks=[PNG])
    )
    downloader = ImageDownloader(session=session)
    with patch("html2md.network.safe_http.socket.getaddrinfo", private_dns):
        assert (
            downloader.download_image("https://metadata.test/image.png", tmp_path)
            is None
        )

    assert session.calls == []


def test_redirect_target_is_resolved_and_revalidated(tmp_path):
    redirect = FakeResponse(
        302, {"Location": "http://169.254.169.254/latest/meta-data"}
    )
    session = FakeSession(redirect)
    downloader = ImageDownloader(session=session)

    def selective_dns(hostname, *args, **kwargs):
        del args, kwargs
        address = "93.184.216.34" if hostname == "example.com" else "169.254.169.254"
        return [(2, 1, 6, "", (address, 80))]

    with patch("html2md.network.safe_http.socket.getaddrinfo", selective_dns):
        assert downloader.download_image("https://example.com/image", tmp_path) is None

    assert redirect.closed
    assert len(session.calls) == 1


def test_safe_redirect_is_followed_without_requests_automatic_redirects(tmp_path):
    redirect = FakeResponse(302, {"Location": "https://cdn.example.com/final"})
    image = FakeResponse(200, {"Content-Type": "image/png"}, [PNG])
    session = FakeSession(redirect, image)
    downloader = ImageDownloader(session=session)

    with patch("html2md.network.safe_http.socket.getaddrinfo", public_dns):
        result = downloader.download_image("https://example.com/image", tmp_path)

    assert result is not None
    assert result.read_bytes() == PNG
    assert [call[0] for call in session.calls] == [
        "https://example.com/image",
        "https://cdn.example.com/final",
    ]
    assert all(call[1]["allow_redirects"] is False for call in session.calls)
    assert all(call[1]["pinned_address"] == "93.184.216.34" for call in session.calls)
    assert redirect.closed and image.closed


def test_transport_connects_to_validated_address_without_second_dns(
    tmp_path, monkeypatch
):
    dns = MagicMock(return_value=PUBLIC_DNS)
    connect = MagicMock(side_effect=OSError("connection stopped for inspection"))
    monkeypatch.setattr("socket.getaddrinfo", dns)
    monkeypatch.setattr("urllib3.util.connection.create_connection", connect)

    session = requests.Session()
    session.proxies = {"http": "http://proxy.invalid:8080"}
    monkeypatch.setenv("HTTP_PROXY", "http://environment-proxy.invalid:8080")
    downloader = ImageDownloader(session=session)

    assert (
        downloader.download_image("http://images.example.test/image.png", tmp_path)
        is None
    )

    assert dns.call_count == 1
    assert connect.call_count == 1
    assert connect.call_args.args[0] == ("93.184.216.34", 80)


def test_transport_attempts_only_validated_public_addresses(tmp_path, monkeypatch):
    public_addresses = [
        (2, 1, 6, "", ("93.184.216.34", 80)),
        (2, 1, 6, "", ("93.184.216.35", 80)),
    ]
    connect = MagicMock(side_effect=OSError("connection stopped for inspection"))
    monkeypatch.setattr("socket.getaddrinfo", MagicMock(return_value=public_addresses))
    monkeypatch.setattr("urllib3.util.connection.create_connection", connect)

    assert (
        ImageDownloader(session=requests.Session()).download_image(
            "http://images.example.test/image.png", tmp_path
        )
        is None
    )

    assert [call.args[0][0] for call in connect.call_args_list] == [
        "93.184.216.34",
        "93.184.216.35",
    ]


def test_https_pin_preserves_host_header_sni_and_certificate_hostname():
    adapter = _PinnedAddressAdapter("93.184.216.34")
    adapter.poolmanager = MagicMock()
    request = requests.Request(
        "GET", "https://assets.example.test:8443/image.png"
    ).prepare()

    adapter.get_connection_with_tls_context(request, verify=True)
    adapter.add_headers(request)

    call = adapter.poolmanager.connection_from_host.call_args
    assert call.kwargs["host"] == "93.184.216.34"
    assert call.kwargs["port"] == 8443
    assert call.kwargs["scheme"] == "https"
    assert call.kwargs["pool_kwargs"]["server_hostname"] == "assets.example.test"
    assert call.kwargs["pool_kwargs"]["assert_hostname"] == "assets.example.test"
    assert request.headers["Host"] == "assets.example.test:8443"


def test_cross_origin_image_hop_drops_session_secrets():
    source = requests.Session()
    source.headers.update(
        {
            "Authorization": "Bearer secret",
            "X-API-Key": "secret",
            "Accept": "image/png",
        }
    )
    source.auth = ("user", "secret")
    downloader = ImageDownloader(session=source)

    direct = downloader._direct_session("93.184.216.34", retain_credentials=False)
    try:
        assert "Authorization" not in direct.headers
        assert "X-API-Key" not in direct.headers
        assert direct.headers["Accept"] == "image/png"
        assert direct.auth is None
    finally:
        direct.close()


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("", PNG),
        ("text/html", PNG),
        ("image/png", b"<html>not an image</html>"),
        ("image/jpeg", PNG),
        ("image/svg+xml", b"<svg><script>alert(1)</script></svg>"),
    ],
)
def test_mime_header_and_file_signature_must_be_supported_and_match(
    tmp_path, content_type, body
):
    response = FakeResponse(200, {"Content-Type": content_type}, [body])
    downloader = ImageDownloader(session=FakeSession(response))

    with patch("html2md.network.safe_http.socket.getaddrinfo", public_dns):
        assert downloader.download_image("https://example.com/image", tmp_path) is None

    assert not list(tmp_path.rglob("*.png"))
    assert not list(tmp_path.glob(".html2md-image-*"))


def test_content_length_and_streaming_enforce_per_file_limit(tmp_path):
    stated = FakeResponse(
        200,
        {"Content-Type": "image/png", "Content-Length": "100"},
        [PNG],
    )
    streamed = FakeResponse(200, {"Content-Type": "image/png"}, [PNG[:8], b"x" * 20])

    with patch("html2md.network.safe_http.socket.getaddrinfo", public_dns):
        assert (
            ImageDownloader(
                session=FakeSession(stated), max_file_bytes=32
            ).download_image("https://example.com/stated", tmp_path)
            is None
        )
        assert (
            ImageDownloader(
                session=FakeSession(streamed), max_file_bytes=16
            ).download_image("https://example.com/streamed", tmp_path)
            is None
        )

    assert not list(tmp_path.glob(".html2md-image-*"))


def test_aggregate_limit_applies_across_images(tmp_path):
    first = FakeResponse(200, {"Content-Type": "image/png"}, [PNG])
    second = FakeResponse(200, {"Content-Type": "image/jpeg"}, [JPEG])
    downloader = ImageDownloader(
        session=FakeSession(first, second),
        max_file_bytes=100,
        max_total_bytes=len(PNG) + len(JPEG) - 1,
    )

    with patch("html2md.network.safe_http.socket.getaddrinfo", public_dns):
        first_path = downloader.download_image("https://example.com/first", tmp_path)
        second_path = downloader.download_image("https://example.com/second", tmp_path)

    assert first_path is not None
    assert second_path is None
    assert downloader.total_downloaded_bytes == len(PNG)


def test_output_images_directory_cannot_escape_root(tmp_path):
    response = FakeResponse(200, {"Content-Type": "image/png"}, [PNG])
    downloader = ImageDownloader(session=FakeSession(response), images_dir="../escaped")

    with patch("html2md.network.safe_http.socket.getaddrinfo", public_dns):
        assert (
            downloader.download_image("https://example.com/image.png", tmp_path) is None
        )

    assert not (tmp_path.parent / "escaped").exists()


def test_local_conversion_copies_contained_image_and_rewrites_markdown(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "photo.png").write_bytes(PNG)
    html_file = source_dir / "page.html"
    html_file.write_text('<img src="photo.png" alt="Photo">', encoding="utf-8")
    output_dir = tmp_path / "output"

    markdown = local_html_to_markdown(
        html_file,
        download_images=True,
        output_dir=output_dir,
    )

    assert markdown is not None
    assert "![Photo](images/photo.png)" in markdown
    assert (output_dir / "images" / "photo.png").read_bytes() == PNG


def test_local_copy_rejects_parent_traversal_and_symlink_escape(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG)
    symlink = source_dir / "linked.png"
    symlink.symlink_to(outside)
    downloader = ImageDownloader(local_root=source_dir)

    traversal = f"{source_dir.as_uri()}/%2e%2e/outside.png"
    assert downloader.download_image(traversal, tmp_path / "output") is None
    assert downloader.download_image(symlink.as_uri(), tmp_path / "output") is None


def test_file_urls_are_disabled_without_an_explicit_local_root(tmp_path):
    source = tmp_path / "image.png"
    source.write_bytes(PNG)

    assert (
        ImageDownloader().download_image(source.as_uri(), tmp_path / "output") is None
    )


def test_exact_rewrite_does_not_replace_an_unrelated_same_basename():
    downloader = ImageDownloader()
    markdown = "![one](https://one.test/logo.png) ![two](https://two.test/logo.png)"

    rewritten = downloader.rewrite_image_urls(
        markdown, {"https://one.test/logo.png": "images/logo.png"}
    )

    assert rewritten == "![one](images/logo.png) ![two](https://two.test/logo.png)"


def test_direct_remote_validation_rejects_invalid_port():
    with pytest.raises(UnsafeImageSource, match="invalid port"):
        ImageDownloader._validate_remote_url("https://example.com:invalid/image.png")
