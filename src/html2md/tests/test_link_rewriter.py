"""Regression tests for local link rewriting and success-only mappings."""

from pathlib import Path
from unittest.mock import patch

from html2md.markdown.batch_processor import process_markdown_links
from html2md.markdown.crawler import crawl_website
from html2md.markdown.link_rewriter import rewrite_archived_files, rewrite_links
from html2md.network.request_handler import FetchResult
from html2md.utils.state_manager import StateManager


def test_rewrite_links_is_relative_to_each_source_and_preserves_url_parts(tmp_path):
    root = tmp_path / "output"
    source = root / "example.com" / "guide" / "current.md"
    mapping = {
        "https://example.com/sibling": root / "example.com" / "guide" / "sibling.md",
        "https://example.com/home": root / "example.com" / "index.md",
        "https://example.com/deep": root / "example.com" / "guide" / "deep" / "page.md",
        "https://example.com/search?view=full": root / "example.com" / "query.md",
    }
    content = """[Sibling](https://example.com/sibling)
[Parent](https://example.com/home)
[Nested](https://example.com/deep)
[Fragment](https://example.com/sibling#details)
[Exact query](https://example.com/search?view=full)
[Fallback query](https://example.com/sibling?view=compact#top)
[With title](https://example.com/home "Home")
[External](https://outside.example/page)
![Mapped image](https://example.com/sibling)
"""

    rewritten = rewrite_links(content, mapping, source)

    assert "[Sibling](sibling.md)" in rewritten
    assert "[Parent](../index.md)" in rewritten
    assert "[Nested](deep/page.md)" in rewritten
    assert "[Fragment](sibling.md#details)" in rewritten
    assert "[Exact query](../query.md)" in rewritten
    assert "[Fallback query](sibling.md?view=compact#top)" in rewritten
    assert '[With title](../index.md "Home")' in rewritten
    assert "[External](https://outside.example/page)" in rewritten
    assert "![Mapped image](https://example.com/sibling)" in rewritten


def test_rewrite_archived_files_updates_all_files_and_reports_progress(tmp_path):
    first = tmp_path / "first.md"
    second = tmp_path / "nested" / "second.md"
    second.parent.mkdir()
    first.write_text("[Second](https://example.com/second)", encoding="utf-8")
    second.write_text("[First](https://example.com/first)", encoding="utf-8")
    mapping = {
        "https://example.com/first": first,
        "https://example.com/second": second,
    }
    progress = []

    updated = rewrite_archived_files(
        mapping, lambda message, url, status: progress.append((message, url, status))
    )

    assert updated == 2
    assert first.read_text(encoding="utf-8") == "[Second](nested/second.md)"
    assert second.read_text(encoding="utf-8") == "[First](../first.md)"
    assert [event[2] for event in progress].count("updated") == 2


def test_rewrite_archived_files_isolates_missing_file_failure(tmp_path):
    missing = tmp_path / "missing.md"
    existing = tmp_path / "existing.md"
    existing.write_text("[Missing](https://example.com/missing)", encoding="utf-8")
    mapping = {
        "https://example.com/missing": missing,
        "https://example.com/existing": existing,
    }
    progress = []

    updated = rewrite_archived_files(
        mapping, lambda message, url, status: progress.append((message, url, status))
    )

    assert updated == 1
    assert any(status == "error" for _, _, status in progress)


def test_batch_mapping_and_rewrites_exclude_failed_outputs(tmp_path):
    source = tmp_path / "links.md"
    source.write_text("fixture", encoding="utf-8")
    good = "https://example.com/good"
    failed = "https://example.com/failed"

    with (
        patch(
            "html2md.markdown.batch_processor.get_urls_from_file",
            return_value=[good, failed],
        ),
        patch(
            "html2md.markdown.batch_processor.html_to_markdown",
            side_effect=[f"[Failed]({failed})", None],
        ),
    ):
        result = process_markdown_links([source], tmp_path / "output")

    assert result.processed_count == 1
    assert result.failed_count == 1
    assert result.success is False
    assert result.items[1].error == "Conversion returned no Markdown content"
    assert set(result.url_mapping) == {good}
    archived_file = next(iter(result.url_mapping.values()))
    assert failed in Path(archived_file).read_text(encoding="utf-8")
    assert not list((tmp_path / "output").rglob("*failed*.md"))


def test_crawl_mapping_and_rewrites_exclude_failed_outputs(tmp_path):
    start = "https://example.com/start"
    failed = "https://example.com/failed"
    first_html = f'<html><body><a href="{failed}">Failed</a></body></html>'
    second_html = "<html><body>conversion fails</body></html>"
    responses = [
        FetchResult(start, start, status_code=200, body=first_html),
        FetchResult(failed, failed, status_code=200, body=second_html),
    ]
    manager = StateManager(state_dir=tmp_path / "states")

    with (
        patch("html2md.markdown.crawler.fetch_html", side_effect=responses),
        patch(
            "html2md.markdown.crawler.html_content_to_markdown",
            side_effect=[f"[Failed]({failed})", None],
        ),
    ):
        result = crawl_website(
            start,
            tmp_path / "output",
            max_pages=2,
            max_depth=1,
            respect_robots=False,
            state_manager=manager,
        )

    assert result.processed_count == 1
    assert result.failed_count == 1
    assert set(result.url_mapping) == {start}
    archived_file = next(iter(result.url_mapping.values()))
    assert failed in Path(archived_file).read_text(encoding="utf-8")
    assert failed not in manager.current_state.urls_visited
    assert failed in manager.current_state.urls_failed
