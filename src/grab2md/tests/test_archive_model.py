"""Archive identity, planning, manifest, and structural rewriting tests."""

from unittest.mock import Mock, call, patch

import pytest

from grab2md.markdown.archive import (
    ArtifactManifest,
    ArtifactRecord,
    OutputPlanner,
    canonical_url_identity,
)
from grab2md.markdown.batch_processor import process_markdown_links
from grab2md.markdown.archiving import ArchiveCoordinator
from grab2md.markdown.document import DocumentMetadata
from grab2md.markdown.link_rewriter import rewrite_links
from grab2md.markdown.pipeline import AcquiredPage, ConvertedDocument
from grab2md.utils.parser import extract_links_from_html, extract_urls_from_markdown


def test_url_identity_normalizes_origin_and_excludes_fragments():
    assert (
        canonical_url_identity("HTTPS://Example.COM:443/docs/page?view=full#part")
        == "https://example.com/docs/page?view=full"
    )
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


def test_manifest_resolves_only_requested_and_redirect_identities(tmp_path):
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
    assert manifest.resolve("https://example.com/guide") is None


def test_archive_coordinator_reuses_final_identity_without_reconversion(tmp_path):
    manifest = ArtifactManifest()
    store = Mock()
    archiver = ArchiveCoordinator(
        manifest=manifest,
        planner=OutputPlanner(tmp_path),
        write_text=store.write_text,
    )
    first_page = AcquiredPage(
        "https://example.com/old",
        "https://example.com/current",
        "<h1>Current</h1>",
        200,
        {},
        "text/html",
        "utf-8",
    )
    document = ConvertedDocument(
        first_page,
        "# Current",
        first_page.html,
        DocumentMetadata(canonical_url="https://example.com/guide"),
    )
    convert = Mock(return_value=document)

    first = archiver.archive(first_page.requested_url, first_page, convert)
    second_convert = Mock()
    second_page = AcquiredPage(
        "https://example.com/another",
        first_page.final_url,
        first_page.html,
        200,
        {},
        "text/html",
        "utf-8",
    )
    second = archiver.archive(second_page.requested_url, second_page, second_convert)

    assert first.reused is False
    assert second.reused is True
    assert second.output_path == first.output_path
    convert.assert_called_once_with(first.output_path)
    second_convert.assert_not_called()
    store.write_text.assert_called_once_with(first.output_path, "# Current")
    assert manifest.resolve(second_page.requested_url) is manifest.resolve(
        first_page.final_url
    )


def test_archive_coordinator_validates_acquisition_identities_before_writing(tmp_path):
    manifest = ArtifactManifest()
    store = Mock()
    archiver = ArchiveCoordinator(
        manifest=manifest,
        planner=OutputPlanner(tmp_path),
        write_text=store.write_text,
    )
    page = AcquiredPage(
        "https://example.com/requested",
        "javascript:alert(1)",
        "<h1>Final</h1>",
        200,
        {},
        "text/html",
        "utf-8",
    )
    document = ConvertedDocument(
        page,
        "# Final",
        page.html,
        DocumentMetadata(canonical_url="https://example.com/metadata-only"),
    )

    with pytest.raises(ValueError, match=r"HTTP\(S\) URL"):
        archiver.archive(page.requested_url, page, lambda _output: document)

    store.write_text.assert_not_called()
    assert not list(tmp_path.rglob("*.md"))
    assert manifest.records == ()


def test_authored_canonical_cannot_suppress_a_distinct_page(tmp_path):
    manifest = ArtifactManifest()
    store = Mock()
    archiver = ArchiveCoordinator(
        manifest=manifest,
        planner=OutputPlanner(tmp_path),
        write_text=store.write_text,
    )
    first_url = "https://example.com/first"
    second_url = "https://example.com/second"
    first_page = AcquiredPage(
        first_url,
        first_url,
        '<link rel="canonical" href="/second"><h1>First</h1>',
        200,
        {},
        "text/html",
        "utf-8",
    )
    second_page = AcquiredPage(
        second_url,
        second_url,
        "<h1>Second</h1>",
        200,
        {},
        "text/html",
        "utf-8",
    )
    first_document = ConvertedDocument(
        first_page,
        "# First",
        first_page.html,
        DocumentMetadata(canonical_url=second_url),
    )
    second_document = ConvertedDocument(
        second_page,
        "# Second",
        second_page.html,
        DocumentMetadata(canonical_url=second_url),
    )
    first_convert = Mock(return_value=first_document)
    second_convert = Mock(return_value=second_document)

    first = archiver.archive(first_url, first_page, first_convert)
    second = archiver.archive(second_url, second_page, second_convert)

    assert first.reused is False
    assert second.reused is False
    assert first.output_path != second.output_path
    assert len(manifest.records) == 2
    assert manifest.resolve(second_url) is manifest.records[1]
    first_convert.assert_called_once_with(first.output_path)
    second_convert.assert_called_once_with(second.output_path)
    assert store.write_text.call_args_list == [
        call(first.output_path, "# First"),
        call(second.output_path, "# Second"),
    ]


def test_authored_canonical_cannot_discard_the_declaring_page(tmp_path):
    manifest = ArtifactManifest()
    store = Mock()
    archiver = ArchiveCoordinator(
        manifest=manifest,
        planner=OutputPlanner(tmp_path),
        write_text=store.write_text,
    )
    target_url = "https://example.com/target"
    declaring_url = "https://example.com/declaring"
    target_page = AcquiredPage(
        target_url,
        target_url,
        "<h1>Target</h1>",
        200,
        {},
        "text/html",
        "utf-8",
    )
    declaring_page = AcquiredPage(
        declaring_url,
        declaring_url,
        '<link rel="canonical" href="/target"><h1>Declaring</h1>',
        200,
        {},
        "text/html",
        "utf-8",
    )

    target = archiver.archive(
        target_url,
        target_page,
        Mock(
            return_value=ConvertedDocument(
                target_page,
                "# Target",
                target_page.html,
                DocumentMetadata(canonical_url=target_url),
            )
        ),
    )
    declaring_convert = Mock(
        return_value=ConvertedDocument(
            declaring_page,
            "# Declaring",
            declaring_page.html,
            DocumentMetadata(canonical_url=target_url),
        )
    )
    declaring = archiver.archive(declaring_url, declaring_page, declaring_convert)

    assert target.reused is False
    assert declaring.reused is False
    assert target.output_path != declaring.output_path
    assert len(manifest.records) == 2
    declaring_convert.assert_called_once_with(declaring.output_path)
    store.write_text.assert_any_call(declaring.output_path, "# Declaring")


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
    markdown = '[API](https://example.com/functions/run(value) "API")'
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

    with patch("grab2md.markdown.batch_processor.acquire_http_page", side_effect=pages):
        result = process_markdown_links(
            [source], tmp_path / "output", page_pipeline=pipeline
        )

    assert result.success is True
    assert result.processed_count == 2
    assert len(set(result.url_mapping.values())) == 1
    assert result.manifest is not None
    assert len(result.manifest.records) == 1
    pipeline.convert.assert_called_once()
