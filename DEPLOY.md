# Deployment Guide for html2md

This guide explains how to deploy and install the `html2md` tool after making changes.

## Automated Deployment

An automated deployment script is provided to simplify the process:

```bash
./deploy.sh
```

This script will:
1. Run all tests to ensure everything works correctly
2. Build the package using Poetry
3. Install the package globally using pipx
4. Verify the installation by checking command availability

## Manual Deployment

If you prefer to deploy manually, follow these steps:

### 1. Run tests

```bash
python -m pytest
```

### 2. Build the package with Poetry

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
html2md --help
html2md --help
```

## Usage after Deployment

After deployment, you can use `html2md` from anywhere:

```bash
# Convert a single URL
html2md convert https://example.com --output example.md

# Process a batch of URLs from a file
html2md batch urls.txt --output-dir docs

# Process batch URLs and output directly to domain-named directories
html2md batch urls.txt --output-dir docs --flatten
```

For the classic interface:

```bash
html2md convert https://example.com --output example.md
```

## Troubleshooting

If you encounter any issues:

- Check that Poetry and pipx are installed and up to date
- Ensure all development dependencies are installed: `poetry install`
- Try uninstalling before reinstalling: `pipx uninstall html2md`
