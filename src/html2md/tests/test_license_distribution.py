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
    metadata = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    root_readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    extension_readme = (PROJECT_ROOT / "extension" / "README.md").read_text(
        encoding="utf-8"
    )

    assert metadata["tool"]["poetry"]["license"] == "MIT"
    assert "[MIT License](./LICENSE)" in root_readme
    assert "[MIT License](../LICENSE)" in extension_readme
