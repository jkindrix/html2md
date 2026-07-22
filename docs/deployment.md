# Local deployment guide for grab2md

This guide explains how to build and install `grab2md` locally after making
changes. Neither path publishes a package or creates a release.

## Automated Deployment

An automated deployment script is provided to simplify the process:

```bash
./deploy.sh
```

Validate the complete release path without changing the global environment:

```bash
./deploy.sh --dry-run
```

This script will:

1. Run metadata, requirement-export, lint, format, type, and test gates
2. Build the package using Poetry
3. Install the package globally using pipx (or into a temporary environment in
   dry-run mode)
4. Verify command, module, and package-metadata versions agree

## Manual Deployment

The distribution is named `grab2md`; it installs the `grab2md` command and
the `grab2md` Python package. TestPyPI already contains the staging-only `0.4.0`
and `0.4.1` rehearsals. Before production publication, verify the production
PyPI project state and matching Trusted Publisher again; a pending publisher,
local build, or pipx installation does not reserve the registry name.

If you prefer to deploy manually, follow these steps:

### 1. Run tests

```bash
poetry run pytest src/grab2md/tests tests/config tests/scripts \
  --cov=grab2md --cov-report=term-missing:skip-covered
```

### 2. Build the package with Poetry 2.4.1

```bash
poetry build
```

### 3. Install globally with pipx

```bash
pipx install . --force
```

### 4. Verify installation

The following commands should now be available:

```bash
grab2md --help
grab2md --version
python -m grab2md --version
```

## Usage after Deployment

After deployment, you can use `grab2md` from anywhere:

```bash
# Convert a single URL
grab2md https://example.com --output example.md

# Process a batch of URLs from a file
grab2md batch urls.txt --output-dir docs

# Process batch URLs and output directly to domain-named directories
grab2md batch urls.txt --output-dir docs --flatten
```

## Troubleshooting

If you encounter any issues:

- Check that Poetry 2.4.1 and pipx are installed
- Ensure all locked development dependencies are installed:
  `poetry sync --with dev`
- Try uninstalling before reinstalling: `pipx uninstall grab2md`
