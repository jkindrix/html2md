"""Archive identity, planning, manifest, and structural rewriting tests."""

from pathlib import Path
from unittest.mock import Mock, patch

from html2md.markdown.archive import (
    ArtifactManifest,
    ArtifactRecord,
    OutputPlanner,
    canonical_url_identity,
)
from html2md.markdown.batch_processor import process_markdown_links
from html2md.markdown.document import DocumentMetadata
from html2md.markdown.link_rewriter import rewrite_links
from html2md.markdown.pipeline import AcquiredPage, ConvertedDocument
from html2md.utils.parser import extract_links_from_html, extract_urls_from_markdown


def test_url_identity_normalizes_origin_and_excludes_fragments():
    assert canonical_url_identity(
        "HTTPS://Example.COM:443/docs/page?view=full#part"
    ) == "https://example.com/docs/page?view=full"
    assert canonical_url_identity("http://example.com:80") == "http://example.com/"


def test_output_planner_is_readable_stable_and_collision_resistant(tmp_path):
    planner = OutputPlanner(tmp_path)
    common = "x" * 140

    first = planner.plan(f"https://example.com/docs/{common}-one")
    second = planner.plan(f"https://example.com/docs/{common}-two")

    assert first != second
    assert first.parent == second.parent == tmp_path / "example.com" / "docs"
    assert first.name.endswith(".md")
    assert len(first.name) < 90
    assert planner.plan(f"https://example.com/docs/{common}-one#section") == first


def test_manifest_resolves_requested_redirect_and_canonical_aliases(tmp_path):
    record = ArtifactRecord(
        "https://example.com/start",
        "https://www.example.com/final",
        "https://example.com/guide",
        tmp_path / "guide.md",
    )
    manifest = ArtifactManifest()
    manifest.register(record)

    assert manifest.resolve("https://example.com/start#top") is record
    assert manifest.resolve("https://www.example.com/final") is record
    assert manifest.resolve("https://example.com/guide") is record


def test_structural_rewriter_handles_parentheses_titles_and_fenced_code(tmp_path):
    target = tmp_path / "archive" / "guide.md"
    source = tmp_path / "index.md"
    manifest = ArtifactManifest()
    manifest.register(
        ArtifactRecord(
            "https://example.com/guides/(current)",
            "https://example.com/guides/(current)",
            None,
            target,
        )
    )
    content = """[Guide](https://example.com/guides/(current) "Current guide")
![Image](https://example.com/guides/(current))
```
[Code](https://example.com/guides/(current))
```
"""

    rewritten = rewrite_links(content, manifest, source)

    assert '[Guide](archive/guide.md "Current guide")' in rewritten
    assert "![Image](https://example.com/guides/(current))" in rewritten
    assert "[Code](https://example.com/guides/(current))" in rewritten


def test_structural_discovery_honors_markdown_parentheses_and_html_base():
    markdown = "[API](https://example.com/functions/run(value) \"API\")"
    html = '<base href="/docs/v2/"><A HREF=chapter.html>Chapter</A>'

    assert extract_urls_from_markdown(markdown) == [
        "https://example.com/functions/run(value)"
    ]
    assert extract_links_from_html(html, "https://example.com/start") == [
        "https://example.com/docs/v2/chapter.html"
    ]


def test_batch_manifest_reuses_two_requested_urls_with_one_final_identity(tmp_path):
    source = tmp_path / "links.md"
    first = "https://example.com/old-one"
    second = "https://example.com/old-two"
    final = "https://example.com/current"
    source.write_text(f"[One]({first})\n[Two]({second})", encoding="utf-8")
    pages = [
        AcquiredPage(url, final, "<h1>Current</h1>", 200, {}, "text/html", "utf-8")
        for url in (first, second)
    ]
    pipeline = Mock()
    pipeline.convert.return_value = ConvertedDocument(
        pages[0], "# Current", pages[0].html, DocumentMetadata(canonical_url=final)
    )

    with patch(
        "html2md.markdown.batch_processor.acquire_http_page", side_effect=pages
    ):
        result = process_markdown_links(
            [source], tmp_path / "output", page_pipeline=pipeline
        )

    assert result.success is True
    assert result.processed_count == 2
    assert len(set(result.url_mapping.values())) == 1
    assert result.manifest is not None
    assert len(result.manifest.records) == 1
    pipeline.convert.assert_called_once()
