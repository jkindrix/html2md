# html2md

A command-line utility for converting HTML content to Markdown.

> [!WARNING]
> This repository is an **alpha-stage, pre-1.0 project under active stabilization**. URL conversion, crawling, state resume, and several Chrome extension modes have known release-blocking defects. It is not currently recommended for unattended or production use. See [Project status](#project-status) before relying on it.

## Project status

The current development version is **0.1.0 (alpha)**. Feature work is temporarily frozen while the primary fetch, convert, crawl, persistence, and extension paths are repaired and covered by end-to-end tests.

- No stable package or extension release has been declared.
- Python 3.11 is the current verified development baseline.
- Python 3.12 and 3.13 are compatibility targets, not supported claims, until the CI matrix is implemented.
- Passing unit tests do not currently imply that every documented workflow works end to end.
- The current measured status and known blockers are maintained in [`INTEGRITY_REVIEW.md`](./INTEGRITY_REVIEW.md).

### Security boundaries

- Generated crawl and batch paths are resolved beneath the selected output root; encoded traversal segments and symlink escapes are rejected or sanitized.
- Browser cookie databases are copied only into unpredictable, owner-private temporary directories and removed after success, failure, or an interrupt.
- Configuration, OAuth token, and crawl-state files are atomically replaced with `0600` files inside `0700` directories on POSIX systems.
- Windows does not implement POSIX mode bits; private files rely on the current account's directory ACLs and Python's exclusive temporary-file creation.
- Diagnostic logging redacts credential-bearing headers and token-like values. Response bodies and cookie values are intentionally omitted even at debug level.

## Features

- Convert HTML from URLs to Markdown
- Convert HTML from local files to Markdown
- Support for cookie-based authentication
- Domain-specific content trimming
- Batch processing of markdown files containing links
- Recursive website crawling with link following
- Modular output with preserved link structure
- Beautiful UI with progress indicators
- Chrome extension for instant web page conversion

## Installation

### Prerequisites

- Python 3.11 (current verified development baseline)
- pip or Poetry package manager

### Install with Poetry (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/html2md.git
cd html2md

# Install dependencies and project
poetry install

# Activate the virtual environment
poetry shell
```

### Install with pip

```bash
# Clone the repository
git clone https://github.com/yourusername/html2md.git
cd html2md

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install the project in development mode
pip install -e .
```

### Development Installation

For development with testing and linting tools:

```bash
# With Poetry
poetry install --with dev

# With pip
pip install -r requirements-dev.txt
```

### Canonical development verification

The Poetry workflow is the canonical clean-checkout verification path during stabilization. Run these commands from the repository root:

```bash
# Resolve exactly the committed dependency graph and install all development tools
poetry install --with dev --sync

# Validate project and lock metadata
poetry check

# Run the committed product test suites
poetry run pytest src/html2md/tests tests/config

# Measure production-package coverage with the same suite
poetry run pytest src/html2md/tests tests/config --cov=html2md --cov-report=term-missing

# Static quality baselines (currently expected to expose tracked remediation work)
poetry run ruff check src tests
poetry run black --check src tests
poetry run mypy src/html2md
```

Record the commit, Python version, Poetry version, and exact command whenever publishing a result. A check is not considered green merely because unrelated files or failing suites were omitted. CI enforcement is tracked separately and has not yet been delivered.

## Usage

html2md features a beautiful UI with progress bars and rich formatting

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
- `--browser-cookies`: Use cookies from the local browser to authenticate with websites
- `--browser {chrome,firefox,edge,safari}`: Specify which browser to extract cookies from (default: chrome)
- `--cookie-path PATH`: Path to browser cookies database file (helps with Windows/WSL)
- `--cookie-json PATH`: Path to JSON file with exported cookies (from browser developer tools)
- `--local`: Force treating sources as local files even if they look like URLs
- `--enhanced-headers/--basic-headers`: Use enhanced headers with User-Agent identification and compression support (default: enhanced)
- `--user-agent-contact EMAIL_OR_URL`: Contact email or URL to include in User-Agent header for crawler identification
- `--simulate-browser`: Use browser-like headers instead of identifying as html2md crawler
- `--insecure, --no-verify-ssl`: Disable SSL certificate verification. Only use with hosts you trust (e.g. internal servers with self-signed certificates)

### Batch Command Options

- `--output-dir DIR, -o DIR`: Directory to save the output files and folders (default: "output")
- `--trim/--no-trim`: Enable/disable trimming based on domain-specific rules
- `--flatten`: Output files directly to domain directories (e.g., 'docs.github.com/')
- `--visualize`: Display a visual representation of the output directory structure
- `--report FILE`: Generate a detailed Markdown report of the process
- `--quiet`: Reduce output verbosity, showing only essential information
- `--insecure, --no-verify-ssl`: Disable SSL certificate verification. Only use with hosts you trust (e.g. internal servers with self-signed certificates)

### Crawl Command Options

- `--output-dir DIR, -o DIR`: Directory to save the output files and folders (default: "output")
- `--follow`: How to follow links. Options: 'domain-only', 'host-only', 'subdomain', or a regex pattern (default: domain-only)
- `--max-depth`: Maximum link depth to follow (default: 3)
- `--max-pages`: Maximum number of pages to crawl (default: 100)
- `--trim/--no-trim`: Enable/disable trimming based on domain-specific rules
- `--flatten`: Output files directly to domain directories (e.g., 'docs.github.com/')
- `--enhanced-headers/--basic-headers`: Use enhanced headers with User-Agent identification and compression support (default: enhanced)
- `--user-agent-contact EMAIL_OR_URL`: Contact email or URL to include in User-Agent header for crawler identification
- `--simulate-browser`: Use browser-like headers instead of identifying as html2md crawler
- `--insecure, --no-verify-ssl`: Disable SSL certificate verification. Only use with hosts you trust (e.g. internal servers with self-signed certificates)

## UI Features

The UI includes these enhancements:

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
# Use cookies from your default Chrome browser
html2md convert https://private-site.com/protected-page --browser-cookies

# Use cookies from Firefox instead
html2md convert https://private-site.com/protected-page --browser-cookies --browser firefox

# Use cookies from Microsoft Edge
html2md convert https://private-site.com/protected-page --browser-cookies --browser edge

# Specify path to cookies database (useful in WSL)
html2md convert https://private-site.com/protected-page --browser-cookies --cookie-path "/path/to/cookies/database"

# Use exported cookies JSON file (most reliable method)
# 1. In Chrome/Firefox, open DevTools (F12)
# 2. Go to Application/Storage tab, then Cookies
# 3. Right-click and Export as JSON
# 4. Save the file and use it with html2md:
html2md convert https://private-site.com/protected-page --browser-cookies --cookie-json "cookies.json"
```

### Customizing HTTP Headers

html2md provides flexible header customization for different use cases:

```bash
# Use enhanced headers with proper crawler identification (default)
html2md convert https://example.com --enhanced-headers

# Include contact information in User-Agent for responsible crawling
html2md convert https://example.com --user-agent-contact "admin@example.com"

# Use browser-like headers to avoid crawler detection
html2md convert https://example.com --simulate-browser

# Combine browser simulation with authentication
html2md convert https://example.com --simulate-browser --browser-cookies

# Use basic headers (minimal User-Agent)
html2md convert https://example.com --basic-headers
```

**Header Modes:**
- **Enhanced headers** (default): Identifies as html2md crawler, includes compression support, conditional requests, and optional contact info
- **Browser simulation**: Mimics a real browser to bypass basic crawler detection
- **Basic headers**: Simple User-Agent only, for minimal footprint

### Internal Servers with Self-Signed Certificates

Internal or development servers often present certificates that fail
verification (self-signed, or issued for a different hostname). By default
html2md refuses to connect and reports the certificate error. When you trust
the host and cannot fix its certificate, skip verification explicitly:

```bash
# Skip SSL certificate verification (curl-style flag)
html2md convert https://internal-server.example/docs.html --insecure

# Equivalent long form; also available on crawl and batch
html2md crawl https://internal-server.example --no-verify-ssl
```

**Warning:** Disabling verification exposes the connection to
man-in-the-middle attacks. Only use these flags for hosts you control or
trust, and prefer fixing the server's certificate when possible.

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

### Recursive Website Crawling

Recursively crawl a website, converting each page to markdown:

```bash
html2md crawl https://docs.example.com/ --output-dir documentation
```

Crawl a website but only follow links to the same domain:

```bash
html2md crawl https://docs.example.com/ --follow domain-only
```

Crawl a website including its subdomains:

```bash
html2md crawl https://docs.example.com/ --follow subdomain
```

Crawl with a custom regex pattern to follow only specific links:

```bash
html2md crawl https://docs.example.com/ --follow "^https://docs\.example\.com/api/.*"
```

Set crawling limits for depth and number of pages:

```bash
html2md crawl https://docs.example.com/ --max-depth 5 --max-pages 500
```

Crawl with various options combined:

```bash
html2md crawl https://docs.example.com/ --follow subdomain --max-depth 4 --max-pages 200 --output-dir docs --flatten
```

This will:
1. Recursively crawl the website starting from the URL
2. Follow links according to the specified pattern
3. Convert each page to markdown up to the specified depth and page limit
4. Save files in a structured directory layout
5. Rewrite all links between pages to maintain working references
6. Provide beautiful visuals and detailed status updates throughout

## Chrome Extension

HTML2MD comes with a Chrome extension for instant conversion of web pages to Markdown:

- Convert any web page with one click
- Multiple conversion modes (full page, selection, main article)
- Copy to clipboard, download or preview in the extension
- Dark mode support and customizable settings
- Context menu integration and keyboard shortcuts

Check out the [extension directory](./extension) for installation instructions.

## Known Limitations

### Concurrent Configuration Access

Concurrent modifications to the configuration file from multiple `html2md` processes are not supported and may result in the "last-write-wins" scenario, where one change may be silently overwritten.

**What this means:**
- If you run two `html2md config set` commands simultaneously from different terminals, one change may be lost
- Single-process operations (normal usage) are fully protected with thread-safety locks
- Atomic write operations prevent file corruption even in concurrent scenarios

**Recommendation:**
- Avoid running multiple `html2md config` commands at the exact same time
- For automated scripts, ensure config operations happen sequentially

## License

MIT
