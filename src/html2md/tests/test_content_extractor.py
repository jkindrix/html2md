"""Content-selection contracts independent of fetching and presentation."""

from pathlib import Path

import pytest

from html2md.markdown.content_extractor import (
    ContentExtractionError,
    ContentMode,
    extract_content_html,
    validate_content_request,
)

FIXTURES = Path(__file__).parents[3] / "tests" / "fixtures" / "extraction"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["article.html", "documentation.html"])
def test_main_mode_prefers_one_semantic_region_without_page_furniture(name):
    extracted = extract_content_html(_fixture(name), mode=ContentMode.MAIN)

    assert "SHOULD NOT SURVIVE MAIN MODE" not in extracted
    assert "References are legitimate" in extracted or "license section" in extracted
    assert "<table>" in extracted
    assert "<code" in extracted


def test_main_mode_uses_readability_for_a_generic_article():
    extracted = extract_content_html(
        _fixture("generic-article.html"), mode=ContentMode.MAIN
    )

    assert "Generic Container Story" in extracted
    assert "evidence link" in extracted
    assert "MASTHEAD" not in extracted
    assert "FOOTER" not in extracted


def test_main_mode_fails_honestly_on_an_ambiguous_page():
    with pytest.raises(ContentExtractionError, match="No confident"):
        extract_content_html(_fixture("ambiguous.html"), mode=ContentMode.MAIN)


def test_full_mode_returns_input_byte_for_byte():
    html = _fixture("article.html")
    assert extract_content_html(html) == html


def test_selector_mode_supports_multiple_matches_and_rejects_no_match():
    html = "<div><p class='keep'>one</p><p>drop</p><p class='keep'>two</p></div>"

    extracted = extract_content_html(html, mode=ContentMode.SELECTOR, selector="p.keep")
    assert "one" in extracted and "two" in extracted and "drop" not in extracted

    with pytest.raises(ContentExtractionError, match="matched no content"):
        extract_content_html(html, mode=ContentMode.SELECTOR, selector="article")


def test_content_request_rejects_invalid_mode_selector_combinations():
    with pytest.raises(ContentExtractionError, match="requires --selector"):
        validate_content_request(ContentMode.SELECTOR, None)
    with pytest.raises(ContentExtractionError, match="--content selector"):
        validate_content_request(ContentMode.MAIN, ".article")
    with pytest.raises(ContentExtractionError, match="Invalid CSS selector"):
        extract_content_html("<main>body</main>", mode="selector", selector="[")
