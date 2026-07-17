"""Minimal structural scanner for inline Markdown links."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarkdownLink:
    destination: str
    start: int
    end: int


def scan_inline_links(content: str) -> list[MarkdownLink]:
    """Locate non-image inline-link destinations outside fenced code blocks."""
    links: list[MarkdownLink] = []
    offset = 0
    fenced = False
    fence_marker = ""
    for line in content.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = stripped[:3]
        if marker in {"```", "~~~"}:
            if not fenced:
                fenced = True
                fence_marker = marker
            elif marker == fence_marker:
                fenced = False
            offset += len(line)
            continue
        if not fenced:
            links.extend(_scan_line(line, offset))
        offset += len(line)
    return links


def _scan_line(line: str, offset: int) -> list[MarkdownLink]:
    links: list[MarkdownLink] = []
    index = 0
    while index < len(line):
        if line[index] != "[" or (index > 0 and line[index - 1] in {"!", "\\"}):
            index += 1
            continue
        close_label = _balanced_close(line, index, "[", "]")
        if close_label is None:
            index += 1
            continue
        cursor = close_label + 1
        while cursor < len(line) and line[cursor] in " \t":
            cursor += 1
        if cursor >= len(line) or line[cursor] != "(":
            index = close_label + 1
            continue
        cursor += 1
        while cursor < len(line) and line[cursor] in " \t":
            cursor += 1
        if cursor < len(line) and line[cursor] == "<":
            start = cursor + 1
            end = _unescaped(line, ">", start)
        else:
            start = cursor
            end = _destination_end(line, start)
        if end is not None and end > start:
            destination = line[start:end]
            links.append(MarkdownLink(destination, offset + start, offset + end))
            index = end + 1
        else:
            index = close_label + 1
    return links


def _balanced_close(text: str, start: int, opening: str, closing: str) -> int | None:
    depth = 0
    for index in range(start, len(text)):
        if index > 0 and text[index - 1] == "\\":
            continue
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def _unescaped(text: str, wanted: str, start: int) -> int | None:
    for index in range(start, len(text)):
        if text[index] == wanted and (index == 0 or text[index - 1] != "\\"):
            return index
    return None


def _destination_end(text: str, start: int) -> int | None:
    depth = 0
    for index in range(start, len(text)):
        character = text[index]
        if index > start and text[index - 1] == "\\":
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                return index
            depth -= 1
        elif character in " \t" and depth == 0:
            return index
    return None
