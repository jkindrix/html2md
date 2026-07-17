"""Behavior tests for the core HTML conversion paths."""

from unittest.mock import Mock

import requests
import pytest

from html2md.markdown.converter import (
    html_content_to_markdown,
    html_to_markdown,
    local_html_to_markdown,
)


@pytest.fixture(autouse=True)
def route_mock_sessions_through_conversion_boundary(monkeypatch):
    from html2md.markdown import converter

    original = converter.guarded_request

    def request(session, method, url, **kwargs):
        if isinstance(session, Mock):
            return session.get(
                url,
                headers=kwargs.get("headers"),
                timeout=kwargs.get("timeout"),
            )
        return original(session, method, url, **kwargs)

    monkeypatch.setattr(converter, "guarded_request", request)


def test_html_content_conversion_preserves_core_markdown_structures():
    html = """
    <h1>Guide</h1><p>An <strong>important</strong> <a href="/topic">topic</a>.</p>
    <table><tr><th>Name</th><th>Value</th></tr><tr><td>one</td><td>1</td></tr></table>
    """

    markdown = html_content_to_markdown(html, "https://example.com/docs")

    assert markdown is not None
    assert "# Guide" in markdown
    assert "**important**" in markdown
    assert "[topic](https://example.com/topic)" in markdown
    assert "| Name | Value |" in markdown
    assert "| one | 1 |" in markdown


def test_html_content_conversion_preserves_ordinary_words_and_code():
    html = """
    <article>
      <h1>Model Notes</h1>
      <p>Search, model, API, and assistant are ordinary authored words.</p>
      <pre><code class="language-text">model Search API</code></pre>
    </article>
    """

    markdown = html_content_to_markdown(html, "https://example.com/notes")

    assert markdown is not None
    assert "Search, model, API, and assistant are ordinary authored words." in markdown
    assert "model Search API" in markdown


def test_full_conversion_preserves_legitimate_navigation_footer_and_sections():
    html = """
    <nav>Documentation navigation</nav>
    <main><h1>Guide</h1><h2>References</h2><p>Reference entry.</p>
    <h2>License</h2><p>License terms.</p>
    <section class="comments"><h2>Comments</h2><p>Reader response.</p></section></main>
    <footer>Authored footer note</footer>
    """

    markdown = html_content_to_markdown(html, "https://example.com/guide")

    assert markdown is not None
    for authored_text in (
        "Documentation navigation",
        "## References",
        "Reference entry.",
        "## License",
        "License terms.",
        "## Comments",
        "Reader response.",
        "Authored footer note",
    ):
        assert authored_text in markdown


def test_empty_html_is_a_conversion_failure():
    assert html_content_to_markdown("  ", "https://example.com") is None


def test_url_conversion_passes_headers_without_mutating_session():
    response = Mock(
        text="<h1>Fetched</h1><p>body</p>",
        encoding="utf-8",
        status_code=200,
        headers={"Content-Type": "text/html"},
    )
    response.raise_for_status.return_value = None
    session = Mock()
    session.get.return_value = response
    headers = {"Referer": "https://example.com/source"}

    result = html_to_markdown(
        "https://example.com/page", session=session, headers=headers
    )

    assert result is not None and "# Fetched" in result
    session.get.assert_called_once_with(
        "https://example.com/page", headers=headers, timeout=30
    )
    assert headers == {"Referer": "https://example.com/source"}


def test_url_conversion_uses_final_response_url_for_relative_references():
    response = Mock(
        text='<a href="next">Next</a>',
        encoding="utf-8",
        status_code=200,
        headers={"Content-Type": "text/html"},
        url="https://example.com/redirected/page",
    )
    response.raise_for_status.return_value = None
    session = Mock()
    session.get.return_value = response

    result = html_to_markdown("https://example.com/start", session=session)

    assert result is not None
    assert "[Next](https://example.com/redirected/next)" in result


def test_url_timeout_returns_failure():
    session = Mock()
    session.get.side_effect = requests.Timeout("fixture timeout")

    assert html_to_markdown("https://example.com", session=session) is None


def test_local_conversion_handles_success_missing_and_empty_files(tmp_path):
    html_file = tmp_path / "page.html"
    html_file.write_text("<h1>Local</h1><p>body</p>", encoding="utf-8")
    empty_file = tmp_path / "empty.html"
    empty_file.write_text("", encoding="utf-8")

    converted = local_html_to_markdown(html_file)

    assert converted is not None and "# Local" in converted
    assert local_html_to_markdown(tmp_path / "missing.html") is None
    assert local_html_to_markdown(empty_file) is None
