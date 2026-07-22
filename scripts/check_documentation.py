#!/usr/bin/env python3
"""Verify current documentation metadata and repository-relative links."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(\s*(?P<target><[^>]+>|[^\s)]+)")
REFERENCE_LINK = re.compile(
    r"^[ \t]*\[[^\]]+\]:[ \t]*(?P<target><[^>]+>|\S+)", re.MULTILINE
)
REMOTE_SCHEMES = frozenset({"http", "https", "mailto"})
README_VERSION = re.compile(
    r"^- Development/release-candidate version: `(?P<version>[^`]+)`$",
    re.MULTILINE,
)
PENDING_VERSION = re.compile(
    r"pending first public `(?P<version>[^`]+)` alpha", re.IGNORECASE
)


def _target_value(match: re.Match[str]) -> str:
    return match.group("target").strip("<>")


def documentation_files(root: Path) -> list[Path]:
    """Return maintained Markdown files whose local links must resolve."""
    paths = [*root.glob("*.md"), *(root / "docs").rglob("*.md")]
    paths.extend((root / "extension").glob("*.md"))
    return sorted(path for path in paths if path.is_file())


def broken_local_links(root: Path, path: Path) -> list[tuple[int, str]]:
    """Return repository-relative Markdown links whose targets do not exist."""
    markdown = path.read_text(encoding="utf-8")
    matches = [*INLINE_LINK.finditer(markdown), *REFERENCE_LINK.finditer(markdown)]
    findings: list[tuple[int, str]] = []
    for match in sorted(matches, key=lambda candidate: candidate.start()):
        target = _target_value(match)
        parsed = urlsplit(target)
        if target.startswith("#") or parsed.scheme.lower() in REMOTE_SCHEMES:
            continue
        relative = unquote(parsed.path)
        if not relative:
            continue
        destination = (path.parent / relative).resolve()
        try:
            destination.relative_to(root.resolve())
        except ValueError:
            exists = False
        else:
            exists = destination.exists()
        if not exists:
            line_number = markdown.count("\n", 0, match.start()) + 1
            findings.append((line_number, target))
    return findings


def contract_findings(root: Path) -> list[str]:
    """Return drift between release metadata and current public documentation."""
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = str(pyproject["project"]["version"])
    manifest = json.loads(
        (root / "extension" / "manifest.json").read_text(encoding="utf-8")
    )
    manifest_version = str(manifest["version"])
    readme = (root / "README.md").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    findings: list[str] = []

    readme_match = README_VERSION.search(readme)
    readme_version = readme_match.group("version") if readme_match else None
    pending_match = PENDING_VERSION.search(changelog)
    pending_version = pending_match.group("version") if pending_match else None
    versions = {
        "pyproject.toml project version": project_version,
        "extension/manifest.json version": manifest_version,
        "README development version": readme_version,
        "CHANGELOG pending-public version": pending_version,
    }
    for label, version in versions.items():
        if version != project_version:
            findings.append(
                f"{label} is {version or 'missing'}, expected {project_version}"
            )

    command_section = readme.partition("## Commands")[2].partition("## ")[0]
    if "| `grab2md SOURCE...` |" not in command_section:
        findings.append("README command table must present `grab2md SOURCE...`")
    if "| `convert` |" in command_section:
        findings.append("README command table must not present hidden `convert`")
    if "hidden compatibility alias `grab2md convert SOURCE`" not in readme:
        findings.append(
            "README must identify `convert` as a hidden compatibility alias"
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 1:
        print("usage: check_documentation.py [REPOSITORY_ROOT]", file=sys.stderr)
        return 2

    root = Path(args[0] if args else ".").resolve()
    findings = contract_findings(root)
    for path in documentation_files(root):
        for line_number, target in broken_local_links(root, path):
            relative_path = path.relative_to(root)
            findings.append(
                f"{relative_path}:{line_number}: local Markdown link does not exist: "
                f"{target}"
            )

    for finding in findings:
        print(finding, file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
