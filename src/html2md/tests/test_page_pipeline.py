"""Contract tests for shared page acquisition and conversion boundaries."""

from unittest.mock import Mock, patch

import pytest
import requests

from html2md.markdown.pipeline import (
    AcquisitionFailure,
    AcquiredPage,
    PageConverter,
    acquire_http_page,
    acquire_local_page,
    acquire_rendered_page,
)
from html2md.network.browser_renderer import RenderedPage


def _response(
    *,
    body="<h1>Page</h1>",
    url="https://example.com/final",
    content_type="text/html; charset=iso-8859-1",
    status=200,
):
    response = Mock(
        text=body,
        url=url,
        status_code=status,
        headers={"Content-Type": content_type},
        encoding="iso-8859-1",
    )
    response.raise_for_status.return_value = None
    return response


def test_static_acquisition_preserves_requested_and_final_representation_metadata():
    session = requests.Session()
    with patch(
        "html2md.markdown.pipeline.guarded_request", return_value=_response()
    ) as request:
        page = acquire_http_page(
            "https://example.com/start",
            session=session,
            headers={"User-Agent": "fixture"},
        )

    assert page.requested_url == "https://example.com/start"
    assert page.final_url == "https://example.com/final"
    assert page.status_code == 200
    assert page.media_type == "text/html"
    assert page.charset == "iso-8859-1"
    assert page.is_remote is True
    assert request.call_args.kwargs["headers"] == {"User-Agent": "fixture"}


def test_static_acquisition_rejects_non_html_and_preserves_status_failures():
    session = requests.Session()
    with patch(
        "html2md.markdown.pipeline.guarded_request",
        return_value=_response(content_type="application/pdf"),
    ):
        with pytest.raises(AcquisitionFailure, match="Expected HTML"):
            acquire_http_page("https://example.com/file", session=session)

    response = _response(status=404)
    response.raise_for_status.side_effect = requests.HTTPError(
        "not found", response=response
    )
    with patch("html2md.markdown.pipeline.guarded_request", return_value=response):
        with pytest.raises(AcquisitionFailure) as raised:
            acquire_http_page("https://example.com/missing", session=session)
    assert raised.value.status_code == 404


def test_local_and_rendered_acquisition_share_the_page_contract(tmp_path):
    source = tmp_path / "page.html"
    source.write_text("<h1>Local</h1>", encoding="utf-8")

    local = acquire_local_page(source)
    with patch(
        "html2md.markdown.pipeline.render_html",
        return_value=RenderedPage("<h1>Rendered</h1>", "https://example.com/final"),
    ):
        rendered = acquire_rendered_page("https://example.com/start")

    assert local.source_path == source.resolve()
    assert local.final_url == source.resolve().as_uri()
    assert local.charset == "utf-8"
    assert rendered.rendered is True
    assert rendered.final_url == "https://example.com/final"


def test_page_converter_is_pure_and_returns_selected_html_and_metadata():
    page = AcquiredPage(
        requested_url="https://example.com/start",
        final_url="https://example.com/final",
        html="<html><head><title>Guide</title></head><body><h1>Page</h1></body></html>",
        status_code=200,
        headers={"Content-Type": "text/html"},
        media_type="text/html",
        charset="utf-8",
    )

    document = PageConverter().convert(page, include_metadata=True)

    assert document.page is page
    assert "# Page" in document.markdown
    assert 'title: "Guide"' in document.markdown
    assert "<h1>Page</h1>" in document.selected_html
    assert document.metadata.canonical_url == "https://example.com/final"
