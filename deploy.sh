#!/usr/bin/env bash
set -euo pipefail

dry_run=false
if [[ "${1:-}" == "--dry-run" ]]; then
    dry_run=true
elif [[ $# -gt 0 ]]; then
    echo "Usage: $0 [--dry-run]" >&2
    exit 2
fi

if [[ ! -f pyproject.toml ]]; then
    echo "Error: run this script from the project root." >&2
    exit 1
fi

echo "Running release gates..."
poetry check
poetry run ruff check src/html2md tests/config
poetry run black --check src/html2md tests/config
poetry run mypy src/html2md tests/config
poetry run pytest src/html2md/tests tests/config

echo "Building distributions..."
rm -rf dist
poetry build
expected_version="$(poetry version --short)"

if [[ "$dry_run" == true ]]; then
    smoke_dir="$(mktemp -d)"
    trap 'rm -rf "$smoke_dir"' EXIT
    python -m venv "$smoke_dir/venv"
    "$smoke_dir/venv/bin/python" -m pip install --quiet dist/*.whl
    html2md_command="$smoke_dir/venv/bin/html2md"
    python_command="$smoke_dir/venv/bin/python"
else
    command -v pipx >/dev/null || {
        echo "Error: pipx is required for deployment." >&2
        exit 1
    }
    pipx install . --force
    html2md_command="$(command -v html2md)"
    python_command="python"
fi

installed_version="$($html2md_command --version)"
module_version="$($python_command -m html2md --version)"
if [[ "$installed_version" != "$expected_version" || "$module_version" != "$expected_version" ]]; then
    echo "Version mismatch: expected $expected_version, command=$installed_version, module=$module_version" >&2
    exit 1
fi

echo "Deployment verification complete: html2md $expected_version"
