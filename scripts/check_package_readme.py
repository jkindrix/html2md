#!/usr/bin/env python3
"""Reject Markdown links that will break in a package-index description."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(\s*(?P<target><[^>]+>|[^\s)]+)")
REFERENCE_LINK = re.compile(
    r"^[ \t]*\[[^\]]+\]:[ \t]*(?P<target><[^>]+>|\S+)", re.MULTILINE
)
PORTABLE_SCHEMES = frozenset({"http", "https", "mailto"})


def _target_value(match: re.Match[str]) -> str:
    return match.group("target").strip("<>")


def nonportable_links(markdown: str) -> list[tuple[int, str]]:
    """Return package-index-incompatible Markdown link targets."""
    findings: list[tuple[int, str]] = []
    matches = [*INLINE_LINK.finditer(markdown), *REFERENCE_LINK.finditer(markdown)]
    for match in sorted(matches, key=lambda candidate: candidate.start()):
        target = _target_value(match)
        if (
            target.startswith("#")
            or urlsplit(target).scheme.lower() in PORTABLE_SCHEMES
        ):
            continue
        line_number = markdown.count("\n", 0, match.start()) + 1
        findings.append((line_number, target))
    return findings


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: check_package_readme.py README.md", file=sys.stderr)
        return 2

    path = Path(args[0])
    findings = nonportable_links(path.read_text(encoding="utf-8"))
    for line_number, target in findings:
        print(
            f"{path}:{line_number}: package description link must be absolute: {target}",
            file=sys.stderr,
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
