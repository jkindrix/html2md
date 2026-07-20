"""Regression checks for the project's declared license grant."""

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]


def test_complete_mit_grant_matches_project_attribution():
    license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")

    assert license_text.startswith("MIT License\n\n")
    assert "Copyright (c) 2025-2026 Justin Kindrix" in license_text
    assert "Permission is hereby granted, free of charge" in license_text
    assert "The above copyright notice and this permission notice" in license_text
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in license_text
    assert "OUT OF OR IN CONNECTION WITH THE SOFTWARE" in license_text


def test_package_metadata_and_readmes_point_to_mit_grant():
    metadata = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    root_readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    extension_readme = (PROJECT_ROOT / "extension" / "README.md").read_text(
        encoding="utf-8"
    )

    assert metadata["project"]["license"] == "MIT"
    assert "grab2md/blob/main/LICENSE" in root_readme
    assert "[MIT License](../LICENSE)" in extension_readme
    urls = metadata["project"]["urls"]
    assert set(urls) == {"Repository", "Issues", "Changelog", "Documentation"}
    assert all(
        value.startswith("https://github.com/jkindrix/grab2md")
        for value in urls.values()
    )
    assert (
        "Programming Language :: Python :: 3.13"
        in metadata["project"]["classifiers"]
    )
    assert "](./" not in root_readme


def test_vendored_turndown_notice_preserves_license_and_provenance():
    extension_root = PROJECT_ROOT / "extension"
    derivative = (extension_root / "turndown.js").read_text(encoding="utf-8")
    notice = (extension_root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert "Derived from Turndown v7.1.1" in derivative
    assert "Copyright (c) 2017 Dom Christie" in derivative
    assert "see THIRD_PARTY_NOTICES.md" in derivative
    assert "https://github.com/mixmark-io/turndown/tree/v7.1.1" in notice
    assert "Copyright (c) 2017 Dom Christie" in notice
    assert "Permission is hereby granted, free of charge" in notice
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in notice
    assert "Local modifications: GRAB2MD-specific" in notice
