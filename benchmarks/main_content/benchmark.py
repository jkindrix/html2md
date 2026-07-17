#!/usr/bin/env python3
"""Compare raw conversion with optional main-content extractors."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from bs4 import BeautifulSoup
from markdownify import markdownify

FIXTURES = Path(__file__).with_name("fixtures.json")


@dataclass(frozen=True)
class Engine:
    name: str
    convert: Callable[[str], str]


def _semantic_region(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    articles = [
        element
        for element in soup.find_all("article")
        if len(element.get_text(" ", strip=True)) >= 200
    ]
    if len(articles) == 1:
        return str(articles[0])
    mains = soup.find_all("main")
    return str(mains[0]) if len(mains) == 1 else None


def _enough_fallback_content(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return len(soup.get_text(" ", strip=True)) >= 300 and len(soup.find_all("p")) >= 2


def _engines() -> list[Engine]:
    engines = [
        Engine("raw", lambda html: markdownify(html, heading_style="ATX")),
    ]
    try:
        from readability import Document

        def semantic_readability(html: str) -> str:
            extracted = _semantic_region(html) or Document(html).summary()
            if not _semantic_region(html) and not _enough_fallback_content(extracted):
                return ""
            return markdownify(extracted, heading_style="ATX")

        engines.append(
            Engine(
                "readability",
                lambda html: markdownify(Document(html).summary(), heading_style="ATX"),
            )
        )
        engines.append(Engine("semantic+readability", semantic_readability))
    except ImportError:
        pass

    try:
        from trafilatura import extract

        def semantic_trafilatura(html: str) -> str:
            semantic = _semantic_region(html)
            if semantic:
                return markdownify(semantic, heading_style="ATX")
            extracted = (
                extract(
                    html,
                    output_format="markdown",
                    include_comments=False,
                    include_images=True,
                    include_links=True,
                    include_tables=True,
                )
                or ""
            )
            return extracted if len(extracted) >= 300 else ""

        engines.append(
            Engine(
                "trafilatura",
                lambda html: extract(
                    html,
                    output_format="markdown",
                    include_comments=False,
                    include_images=True,
                    include_links=True,
                    include_tables=True,
                )
                or "",
            )
        )
        engines.append(Engine("semantic+trafilatura", semantic_trafilatura))
    except ImportError:
        pass
    return engines


def _ratio(matches: int, total: int) -> str:
    return f"{matches / total:.0%}" if total else "-"


def main() -> None:
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    print(
        "fixture\tengine\trequired_recall\tboilerplate_rejection\t"
        "honest_disposition\tcharacters"
    )
    for fixture in fixtures:
        html = (FIXTURES.parent / fixture["file"]).read_text(encoding="utf-8")
        for engine in _engines():
            output = engine.convert(html)
            retained = sum(marker in output for marker in fixture["required"])
            rejected = sum(marker not in output for marker in fixture["boilerplate"])
            expected_empty = fixture.get("expected_empty", False)
            honest = expected_empty == (not output.strip())
            print(
                f"{fixture['name']}\t{engine.name}\t"
                f"{_ratio(retained, len(fixture['required']))}\t"
                f"{_ratio(rejected, len(fixture['boilerplate']))}\t"
                f"{'yes' if honest else 'no'}\t{len(output)}"
            )


if __name__ == "__main__":
    main()
