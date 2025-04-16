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
- Chrome extension for instant web page conversion

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

html2md features a beautiful modern UI with progress bars and rich formatting

### Basic Usage

Convert a single URL to Markdown:

```bash
html2md convert https://example.com
```

Convert a local HTML file to Markdown:

```bash
html2md convert path/to/local/file.html
```

Save the output to a file:

```bash
html2md convert https://example.com --output result.md
```

### Batch Processing

Process markdown files containing links and create a modular output structure:

```bash
html2md batch path/to/link-collection.md --output-dir docs
```

Process multiple files at once:

```bash
html2md batch file1.md file2.md --output-dir docs
```

Use glob patterns to process multiple files:

```bash
html2md batch "docs/*.md" --output-dir output
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
- `--flatten`: Output files directly to domain directories (e.g., 'docs.github.com/')
- `--visualize`: Display a visual representation of the output directory structure
- `--report FILE`: Generate a detailed Markdown report of the process
- `--quiet`: Reduce output verbosity, showing only essential information

## UI Features

The modern UI includes these enhancements:

- Beautiful colored output with adaptive theme and syntax highlighting
- Progress spinners and bars with time estimates for long-running operations
- Detailed status updates with rich emoji indicators during batch processing
- Interactive directory tree visualization in `--visualize` mode
- Summary tables and panels showing detailed operation results
- File and directory counts with intelligent display limits
- Rich formatting with semantic styling for better readability
- Terminal capability detection for optimal rendering in any environment
- Detailed error handling with debug mode support
- Silent logging (logs go to files, not the console)

## Configuration Management

html2md includes configuration management as subcommands:

```bash
html2md config [command]
```

### Available Configuration Commands

- `config show`: Display the current configuration
- `config path`: Show the path to the configuration file
- `config set`: Set a configuration value
- `config get`: Get a configuration value
- `config delete`: Delete a configuration value
- `config add-domain`: Interactive wizard to add domain-specific configuration
- `config list-domains`: List all configured domains with their settings
- `config reset`: Reset the configuration to default values

### Example: Adding Domain-Specific Trimming Rules

```bash
# Add domain-specific rules interactively
html2md config add-domain

# List all configured domains
html2md config list-domains

# Set a specific configuration value
html2md config set domains.example.com.footer_marker "Copyright"
```

## Examples

### Converting a URL with Authentication

If you need to access a site that requires authentication, html2md can use your browser cookies:

```bash
html2md convert https://private-site.com/protected-page
```

### Batch Processing Documentation Links

Create a structured documentation site from a collection of markdown links with a beautiful progress display:

```bash
html2md batch incomplete-docs/*.txt --output-dir documentation
```

For a simpler output structure, use the flatten option:

```bash
html2md batch urls.txt --output-dir documentation --flatten
```

For a rich visual display of the results:

```bash
html2md batch urls.txt --output-dir documentation --visualize
```

Or generate a markdown report file along with the output:

```bash
html2md batch urls.txt --output-dir documentation --report processing-report.md
```

This will:
1. Extract all URLs from the provided files (including plain URL lists)
2. Convert each URL's HTML content to markdown
3. Save the files in a structured directory layout
4. Update links between files to maintain correct references
5. Provide beautiful visuals and detailed status updates throughout

All with intuitive progress indicators and intelligent terminal adaptations!

## Chrome Extension

HTML2MD comes with a Chrome extension for instant conversion of web pages to Markdown:

- Convert any web page with one click
- Multiple conversion modes (full page, selection, main article)
- Copy to clipboard, download or preview in the extension
- Dark mode support and customizable settings
- Context menu integration and keyboard shortcuts

Check out the [extension directory](./extension) for installation instructions.

## License

MIT
