# html2md

`html2md` converts local HTML, web pages, link collections, and crawlable sites
to Markdown. It includes a Python CLI and an unpacked Chrome extension.

> [!IMPORTANT]
> This is an alpha-stage, pre-1.0 project. The primary workflows are covered by
> end-to-end tests, but no stable package or extension release has been
> published. Review the limitations and security boundaries before using it on
> sensitive or unattended workloads.

## Status and support

- Development version: `0.2.0`
- Source alpha release: `v0.2.0`
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

- `--content full|main|selector` for explicit content selection (full is the
  lossless default), with `--selector` required by selector mode;
- `--output/-o` to write a file instead of stdout;
- `--browser-cookies` or `--cookie-json` for authenticated pages;
- `--headers-file` for an owner-only JSON object of target request headers;
- `--storage-state` with `--render-js` for owner-only Playwright session state;
- `--enhanced-headers/--basic-headers` and `--user-agent-contact` for an honest,
  versioned request identity;
- `--download-images` with a configurable `--images-dir`;
- `--allow-private-network` only for explicitly trusted intranet, loopback, or
  development destinations;
- `--insecure` only for trusted hosts with invalid certificates; and
- `--fancy` for decorated progress output.

Automatic browser database extraction is implemented for Chrome and Firefox.
Exported cookie JSON is the most
portable explicit authentication path. Password submission is not supported.

### Batch output

Batch mode supports preserved paths, flattened domain output, a single flat
directory, hierarchical domain folders, optional visualization, quiet output,
and a Markdown report. Only successfully written files enter the local-link
mapping; failed URLs remain remote links.

### Crawl policy

Crawls are intentionally sequential. Available controls include:

- `--follow` (`domain-only` for the same host and port, `host-only` for the
  exact hostname, `subdomain` for that hostname and dot-delimited descendants,
  or an explicit regular expression);
- `--max-depth`, `--max-pages`, and jittered `--delay`;
- `--respect-robots/--ignore-robots`;
- requests-per-minute `--rate-limit` with adaptive delay and a circuit breaker;
- `--polite` for a more conservative delay policy;
- content selection, progress, output layout, visualization, and quiet-mode switches.

`Ctrl+C` or termination checkpoints the active crawl and then preserves normal
signal behavior. Deferred URLs remain queued instead of being silently lost.

## Configuration and state

Configuration is stored beneath the user's platform-appropriate `.html2md`
directory. Writes are validated, atomic, backed up, and recoverable. Run:

```bash
html2md config show
html2md config path
html2md config show-options
html2md config set-cli-default convert content_mode main
html2md config set-cli-default crawl max_pages 250
html2md config backup
html2md config list-backups
```

CLI defaults are typed and loaded at invocation time. Optional values accept
`null`; invalid updates fail without replacing the existing file. Concurrent
configuration changes from separate processes use last-write-wins semantics,
so serialize configuration commands in automation.

CSS selectors are caller-owned generic inputs; html2md does not ship or
silently apply per-site extraction profiles. A selector can be supplied for one
run or configured as a CLI default together with `content_mode=selector`.

Crawl state supports `list`, `resume`, `clean`, `export`, `import`, and `info`.
State files use restrictive permissions on POSIX systems.

## Chrome extension

Load `extension/` as an unpacked Manifest V3 extension in Chrome or Chromium.
The supported workflow operates on the active tab and provides:

- full-page, main-article, and current-selection conversion;
- preview, clipboard copy, and Markdown download;
- theme and conversion settings; and
- packaged Mozilla Readability extraction only when article mode is selected.

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
- Configuration and crawl states are atomically replaced using
  `0600` files in `0700` directories on POSIX systems.
- Diagnostic logs redact credential-bearing headers, cookie values, and
  token-like data.
- Target authentication accepts scoped browser cookies, an owner-only JSON
  header file, or an owner-only Playwright storage-state file for rendered
  conversion. Login flows remain outside html2md, and authentication files are
  rejected when group- or world-readable on POSIX systems.
- Remote pages, crawl targets, robots files, and images
  allow only HTTP(S), resolve each origin once, connect only to validated
  numeric addresses, and manually revalidate redirects. Private, loopback,
  link-local, and metadata destinations are blocked by default. Guarded traffic
  bypasses configured and environment proxies because proxy-side DNS would
  defeat address pinning.
- Static page/crawl responses are capped at 10 MiB and robots files at 1 MiB.
  Image acquisition additionally verifies MIME type and file signature, rejects
  active SVG, and enforces 10 MiB per-image and 50 MiB per-conversion limits.
- `--allow-private-network` explicitly relaxes destination classification for
  trusted internal or development targets; DNS pinning, redirect validation,
  URL validation, response limits, and TLS verification remain active.
- Local image copying is restricted to regular files beneath the source HTML
  directory; parent traversal and symlink escapes are rejected.
- `--insecure` disables TLS verification and should be used only for hosts you
  control. It exposes the connection to interception but does not authorize
  private-network access.

See [`docs/network-security.md`](./docs/network-security.md) for the complete
outbound request contract and maintainer integration rule.

Windows relies on the current account's directory ACLs because POSIX mode bits
are unavailable there.

## Output contract

Remote relative links and image references are resolved against the final URL
and the document's valid `<base>` element. `--metadata` adds deterministic YAML
front matter for available title, author/date, canonical URL, description, and
language fields. Local references remain relative. See
[`docs/output-contract.md`](./docs/output-contract.md) for the exact contract.

## Known limitations

- Conversion uses `markdownify`. Full-document mode deliberately preserves
  authored boilerplate; opt-in main-content mode uses substantial semantic
  regions and a confidence-gated readability fallback, whose quality varies by
  document. The measured decision is recorded in
  [`ADR 0002`](./docs/adr/0002-select-main-content-extraction.md).
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
