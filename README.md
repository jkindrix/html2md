# html2md

`html2md` converts local HTML, web pages, link collections, and crawlable sites
to Markdown. It includes a Python CLI and an unpacked Chrome extension.

> [!IMPORTANT]
> This is an alpha-stage, pre-1.0 project. The primary workflows are covered by
> end-to-end tests, but no stable package or extension release has been
> published. Review the limitations and security boundaries before using it on
> sensitive or unattended workloads.

## Status and support

- Development version: `0.1.0`
- Source alpha release: `v0.1.0`
- Tested Python versions: 3.11, 3.12, and 3.13
- Planned PyPI distribution: `html2md-cli`
- Installed command and Python import: `html2md`
- Required gates: tests and production coverage, Ruff, Black, mypy, wheel smoke,
  extension runtime tests, Bandit, and dependency audit
- No PyPI, Web Store, or stable API compatibility promise yet

The primary tested paths are local conversion, URL conversion, batch link
processing, sequential crawling, interruption/resume, configuration recovery,
and the extension's full-page/article/selection conversion modes.

## Installation

No PyPI release has been declared. Install from source during stabilization:

```bash
git clone https://github.com/jkindrix/html2md.git
cd html2md
poetry install --with dev --sync
poetry run html2md --help
```

JavaScript rendering is an isolated optional installation:

```bash
python -m pip install "html2md-cli[render]"
python -m playwright install chromium
html2md convert https://example.com/app --render-js
```

See [`docs/browser-rendering.md`](./docs/browser-rendering.md) for its resource,
network, and authentication boundaries.

For an isolated non-development installation from a local checkout:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install .
html2md --version
```

The distribution name differs because `html2md` is already occupied on PyPI.
The `html2md-cli` name must be checked again immediately before publication.

## Quick start

Convert a URL or local HTML file:

```bash
html2md convert https://example.com --output example.md
html2md convert page.html --output page.md
```

Process Markdown files or plain URL lists and rewrite links between successful
local outputs:

```bash
html2md batch links.md urls.txt --output-dir documentation
```

Crawl sequentially with robots.txt enabled by default:

```bash
html2md crawl https://docs.example.com \
  --output-dir documentation \
  --max-depth 3 \
  --max-pages 100 \
  --rate-limit 30
```

Inspect and resume crawl state:

```bash
html2md state list
html2md state info CRAWL_ID
html2md state resume CRAWL_ID
```

Run `html2md COMMAND --help` for the complete, configuration-aware option list.

## Commands

| Command | Purpose |
|---|---|
| `convert` | Convert one or more URLs or local HTML files. |
| `batch` | Extract links from input files, convert them, and rewrite successful local links. |
| `crawl` | Recursively fetch and convert pages using a sequential, robots-aware policy. |
| `config` | Inspect, validate, back up, restore, and change configuration. |
| `state` | List, inspect, export, import, clean, and resume crawl state. |

Global options include `--log-level` (default `WARNING`), `--debug-log`,
`--banner`, and metadata-backed `--version`.

### Conversion

Useful options include:

- `--trim/--no-trim` for domain-specific trimming rules;
- `--output/-o` to write a file instead of stdout;
- `--browser-cookies` or `--cookie-json` for authenticated pages;
- `--enhanced-headers/--basic-headers`, `--user-agent-contact`, and
  `--simulate-browser` for request identity;
- `--download-images` with a configurable `--images-dir`;
- `--insecure` only for trusted hosts with invalid certificates; and
- `--fancy` for decorated progress output.

Automatic browser database extraction is implemented for Chrome and Firefox.
Edge and Safari are accepted configuration values but do not currently have a
complete extraction backend on every platform. Exported cookie JSON is the most
portable explicit authentication path. Password submission is not supported.

### Batch output

Batch mode supports preserved paths, flattened domain output, a single flat
directory, hierarchical domain folders, optional visualization, quiet output,
and a Markdown report. Only successfully written files enter the local-link
mapping; failed URLs remain remote links.

### Crawl policy

Crawls are intentionally sequential. Available controls include:

- `--follow` (`domain-only`, `host-only`, `subdomain`, or a regular expression);
- `--max-depth`, `--max-pages`, and jittered `--delay`;
- `--respect-robots/--ignore-robots`;
- requests-per-minute `--rate-limit` with adaptive delay and a circuit breaker;
- `--polite` for a more conservative delay policy;
- progress, trimming, output layout, visualization, and quiet-mode switches.

`Ctrl+C` or termination checkpoints the active crawl and then preserves normal
signal behavior. Deferred URLs remain queued instead of being silently lost.

## Configuration and state

Configuration is stored beneath the user's platform-appropriate `.html2md`
directory. Writes are validated, atomic, backed up, and recoverable. Run:

```bash
html2md config show
html2md config path
html2md config show-options
html2md config add-domain --domain example.com
html2md config set-cli-default crawl max_pages 250
html2md config backup
html2md config list-backups
```

CLI defaults are typed and loaded at invocation time. Optional values accept
`null`; invalid updates fail without replacing the existing file. Concurrent
configuration changes from separate processes use last-write-wins semantics,
so serialize configuration commands in automation.

Crawl state supports `list`, `resume`, `clean`, `export`, `import`, and `info`.
State and token files use restrictive permissions on POSIX systems.

## Chrome extension

Load `extension/` as an unpacked Manifest V3 extension in Chrome or Chromium.
The supported workflow operates on the active tab and provides:

- full-page, main-article, and current-selection conversion;
- preview, clipboard copy, and Markdown download;
- theme and conversion settings; and
- structural cleanup that preserves user-authored text and fenced code.

The extension uses `activeTab`, `scripting`, `storage`, `downloads`, and
`clipboardWrite`; it does not request persistent access to every site. URL-list,
batch, native CLI integration, background service-worker conversion, context
menus, and keyboard shortcuts are not supported.

See [`extension/README.md`](./extension/README.md) for installation and testing.

## Security boundaries

- Crawl and batch outputs are contained beneath the selected output root;
  traversal and symlink escapes are rejected or sanitized.
- Browser cookie databases are copied into unpredictable owner-private
  temporary directories and removed after success, failure, or interruption.
- Configuration, OAuth tokens, and crawl states are atomically replaced using
  `0600` files in `0700` directories on POSIX systems.
- Diagnostic logs redact credential-bearing headers, cookie values, and
  token-like data.
- Remote image downloads allow only HTTP(S), reject private-network and unsafe
  redirect targets, verify MIME type and file signature, reject active SVG, and
  enforce 10 MiB per-image and 50 MiB per-conversion limits.
- Local image copying is restricted to regular files beneath the source HTML
  directory; parent traversal and symlink escapes are rejected.
- `--insecure` disables TLS verification and should be used only for hosts you
  control. It exposes the connection to interception.

Windows relies on the current account's directory ACLs because POSIX mode bits
are unavailable there.

## Output contract

Remote relative links and image references are resolved against the final URL
and the document's valid `<base>` element. `--metadata` adds deterministic YAML
front matter for available title, author/date, canonical URL, description, and
language fields. Local references remain relative. See
[`docs/output-contract.md`](./docs/output-contract.md) for the exact contract.

## Known limitations

- Conversion uses `markdownify` and optional per-domain trimming; it does not
  provide general main-content extraction or boilerplate removal. The measured
  extractor decision is documented in
  [`docs/main-content-benchmark.md`](./docs/main-content-benchmark.md).
- JavaScript rendering is opt-in for `convert`; batch and crawl remain static.
- Metadata extraction intentionally uses declared HTML/meta fields rather than
  text inference or executable structured data.
- Crawling is sequential; removed concurrency options are not advertised.
- Browser cookie decryption varies across browser and operating-system versions.
- The extension must be installed unpacked; no Web Store release exists.

## Development

Run the canonical local gates from a clean checkout:

```bash
poetry install --with dev --sync
poetry check
poetry run pre-commit run --all-files
poetry run pre-commit run --all-files --hook-stage pre-push
node --test extension/tests/*.test.js
node extension/tests/chromium-smoke.js
./deploy.sh --dry-run
```

Coverage uses the production package as its denominator and enforces the floor
documented in [`docs/coverage.md`](./docs/coverage.md).

## Project documentation

- [`CHANGELOG.md`](./CHANGELOG.md): user-visible changes and changelog policy
- [`docs/releasing.md`](./docs/releasing.md): reproducible release checklist
- [`docs/deployment.md`](./docs/deployment.md): local deployment details
- [`docs/configuration-example.md`](./docs/configuration-example.md): configuration example
- [`docs/adr/0001-defer-scale-out-crawling.md`](./docs/adr/0001-defer-scale-out-crawling.md): scale-out architecture gate
- [`docs/internal/`](./docs/internal/README.md): historical planning and review records

## License

Copyright (c) 2025-2026 Justin Kindrix. Distributed under the
[MIT License](./LICENSE).
