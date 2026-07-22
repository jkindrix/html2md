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
poetry check --lock
python scripts/check_requirement_exports.py
python scripts/check_documentation.py
python scripts/check_package_readme.py README.md
poetry run ruff check src/grab2md tests/config tests/scripts scripts/check_documentation.py scripts/check_package_readme.py
poetry run black --check src/grab2md tests/config tests/scripts scripts/check_documentation.py scripts/check_package_readme.py
poetry run mypy src/grab2md tests/config tests/scripts scripts/check_documentation.py scripts/check_package_readme.py
poetry run mypy --check-untyped-defs --exclude 'src/grab2md/tests/' src/grab2md
poetry run pytest src/grab2md/tests tests/config tests/scripts

echo "Building distributions..."
rm -rf dist
poetry build
expected_version="$(poetry version --short)"
poetry run twine check dist/*

if [[ "$dry_run" == true ]]; then
    poetry run python scripts/release_smoke.py dist/*.whl \
        --expected-version "$expected_version"
    smoke_dir="$(mktemp -d)"
    trap 'rm -rf "$smoke_dir"' EXIT
    python -m venv "$smoke_dir/venv"
    "$smoke_dir/venv/bin/python" -m pip install --quiet dist/*.whl
    grab2md_command="$smoke_dir/venv/bin/grab2md"
    python_command="$smoke_dir/venv/bin/python"
else
    command -v pipx >/dev/null || {
        echo "Error: pipx is required for deployment." >&2
        exit 1
    }
    pipx install . --force
    grab2md_command="$(command -v grab2md)"
    python_command="python"
fi

installed_version="$($grab2md_command --version)"
module_version="$($python_command -m grab2md --version)"
if [[ "$installed_version" != "$expected_version" || "$module_version" != "$expected_version" ]]; then
    echo "Version mismatch: expected $expected_version, command=$installed_version, module=$module_version" >&2
    exit 1
fi

echo "Deployment verification complete: grab2md $expected_version"
