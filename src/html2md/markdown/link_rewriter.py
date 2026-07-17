"""Structurally rewrite successfully archived web links to local paths."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit

from html2md.markdown.archive import ArtifactManifest, ArtifactStore
from html2md.markdown.markdown_links import scan_inline_links

OutputPath = str | os.PathLike
ProgressCallback = Callable[[str, Optional[str], Optional[str]], None]


def _manifest(value) -> ArtifactManifest:
    return (
        value
        if isinstance(value, ArtifactManifest)
        else ArtifactManifest.from_mapping(value)
    )


def rewrite_links(content, archive, source_file):
    """Rewrite mapped inline links while preserving surrounding Markdown bytes."""
    manifest = _manifest(archive)
    source_dir = Path(source_file).resolve().parent
    replacements: list[tuple[int, int, str]] = []
    for link in scan_inline_links(content):
        parts = urlsplit(link.destination)
        if parts.scheme.casefold() not in {"http", "https"}:
            continue
        without_fragment = urlunsplit(parts._replace(fragment=""))
        record = manifest.resolve(without_fragment)
        preserve_query = False
        if record is None and parts.query:
            without_query = urlunsplit(parts._replace(query="", fragment=""))
            record = manifest.resolve(without_query)
            preserve_query = record is not None
        if record is None:
            continue
        destination = os.path.relpath(record.output_path, source_dir).replace(
            os.sep, "/"
        )
        if preserve_query:
            destination += f"?{parts.query}"
        if parts.fragment:
            destination += f"#{parts.fragment}"
        replacements.append((link.start, link.end, destination))

    rewritten = content
    for start, end, destination in reversed(replacements):
        rewritten = rewritten[:start] + destination + rewritten[end:]
    return rewritten


def rewrite_archived_files(
    archive: ArtifactManifest | Mapping[str, OutputPath],
    update_progress: ProgressCallback,
) -> int:
    """Rewrite each unique durable artifact, isolating per-file failures."""
    manifest = _manifest(archive)
    records = manifest.records
    update_progress(f"Rewriting links between {len(records)} files...", None, None)
    updated_count = 0
    for index, record in enumerate(records, start=1):
        path = record.output_path
        update_progress(
            f"Updating links in file {index}/{len(records)}: {path}",
            record.requested_url,
            "updating",
        )
        try:
            content = path.read_text(encoding="utf-8")
            ArtifactStore.write_text(path, rewrite_links(content, manifest, path))
            update_progress(
                f"Updated links in file: {path}", record.requested_url, "updated"
            )
            updated_count += 1
        except (OSError, UnicodeError) as error:
            update_progress(
                f"Error updating links in file {path}: {error}",
                record.requested_url,
                "error",
            )
    return updated_count
