# html2md

A command-line utility for converting HTML content to Markdown.

## Features

- Convert HTML from URLs to Markdown
- Convert HTML from local files to Markdown
- Support for cookie-based authentication
- Domain-specific content trimming
- Batch processing of markdown files containing links
- Modular output with preserved link structure
- Beautiful modern UI with progress indicators

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/html2md.git
cd html2md

# Install with Poetry
poetry install

# Or install with pip
pip install .
```

## Usage

html2md comes in two flavors:

1. `html2md` - The classic CLI interface
2. `html2md-modern` - A beautiful modern UI with progress bars and rich formatting

### Basic Usage

Convert a single URL to Markdown:

```bash
# Classic interface
html2md convert https://example.com

# Modern interface
html2md-modern convert https://example.com
```

Convert a local HTML file to Markdown:

```bash
# Classic interface
html2md convert path/to/local/file.html

# Modern interface
html2md-modern convert path/to/local/file.html
```

Save the output to a file:

```bash
# Classic interface
html2md convert https://example.com --output result.md

# Modern interface
html2md-modern convert https://example.com --output result.md
```

### Batch Processing

Process markdown files containing links and create a modular output structure:

```bash
# Classic interface
html2md batch path/to/link-collection.md --output-dir docs

# Modern interface with beautiful progress bars
html2md-modern batch path/to/link-collection.md --output-dir docs
```

Process multiple files at once:

```bash
html2md-modern batch file1.md file2.md --output-dir docs
```

Use glob patterns to process multiple files:

```bash
html2md-modern batch "docs/*.md" --output-dir output
```

## Command Line Options

### Global Options

- `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}`: Set logging level (default: INFO)

### Convert Command Options

- `--trim/--no-trim`: Enable/disable trimming based on domain-specific rules
- `--output FILE, -o FILE`: Specify output file to save converted markdown
- `--no-cookies`: Disable loading cookies from the browser
- `--local`: Force treating sources as local files even if they look like URLs

### Batch Command Options

- `--output-dir DIR, -o DIR`: Directory to save the output files and folders (default: "output")
- `--trim/--no-trim`: Enable/disable trimming based on domain-specific rules

## Modern UI Features

The modern UI (`html2md-modern`) includes these enhancements:

- Beautiful colored output with syntax highlighting
- Progress spinners and bars for long-running operations
- Detailed status updates during batch processing
- Summary tables showing results of operations
- File and directory counts for batch operations
- Rich formatting for better readability
- Silent logging (logs go to files, not the console)

## Examples

### Converting a URL with Authentication

If you need to access a site that requires authentication, html2md can use your browser cookies:

```bash
html2md-modern convert https://private-site.com/protected-page
```

### Batch Processing Documentation Links

Create a structured documentation site from a collection of markdown links with a beautiful progress display:

```bash
html2md-modern batch incomplete-docs/*.txt --output-dir documentation
```

This will:
1. Extract all URLs from the provided markdown files
2. Convert each URL's HTML content to markdown
3. Save the files in a structured directory layout
4. Update links between files to maintain correct references

All with beautiful progress indicators and detailed status updates!

## License

MIT
