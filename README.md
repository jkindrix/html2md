# grab2md

`grab2md` converts local HTML, web pages, link collections, and crawlable sites
to Markdown. It includes a Python CLI and an unpacked Chrome extension.

> [!IMPORTANT]
> This is an alpha-stage, pre-1.0 project. The primary workflows are covered by
> end-to-end tests, but no stable package or extension release has been
> published. Review the limitations and security boundaries before using it on
> sensitive or unattended workloads.

## Status and support

- Unpublished development version: `0.4.0`
- Latest historical source tag: `v0.3.0` (before the `grab2md` rename)
- Tested Python versions: 3.11, 3.12, and 3.13
- Planned PyPI distribution: `grab2md`
- Installed command and Python import: `grab2md`
- Required gates: tests and production coverage, Ruff, Black, mypy, requirement
  export consistency, wheel smoke, extension runtime tests, Bandit, and
  dependency audit
- No PyPI, Web Store, or stable API compatibility promise yet

The primary tested paths are local conversion, URL conversion, batch link
processing, sequential crawling, interruption/resume, configuration recovery,
and the extension's full-page/article/selection conversion modes.

## Installation

No PyPI release has been declared. Install from source during stabilization:

```bash
git clone https://github.com/jkindrix/grab2md.git
cd grab2md
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install .
grab2md --help
```

Contributors running the complete development and release gates need Poetry
2.4.1 and Node.js; see [CONTRIBUTING.md](CONTRIBUTING.md) for that pinned
toolchain and its canonical commands.

JavaScript rendering is an isolated optional installation:

```bash
python -m pip install "grab2md[render]"
python -m playwright install chromium
grab2md https://example.com/app --render-js
```

See [`docs/browser-rendering.md`](https://github.com/jkindrix/grab2md/blob/main/docs/browser-rendering.md) for its resource,
network, and authentication boundaries.

The `grab2md` name had no registered PyPI project when checked on 2026-07-19,
but availability is not a reservation and must be checked again immediately
before publication.

## Quick start

Convert a URL or local HTML file:

```bash
grab2md https://example.com --output example.md
grab2md page.html --output page.md
```

The earlier explicit form, `grab2md convert SOURCE`, remains accepted for
pre-release scripts, but direct sources are the primary interface.

Process Markdown files or plain URL lists and rewrite links between successful
local outputs:

```bash
grab2md batch links.md urls.txt --output-dir documentation
```

Crawl sequentially with robots.txt enabled by default:

```bash
grab2md crawl https://docs.example.com \
  --output-dir documentation \
  --max-depth 3 \
  --max-pages 100 \
  --rate-limit 30
```

Inspect and resume crawl state:

```bash
grab2md state list
grab2md state info CRAWL_ID
grab2md state resume CRAWL_ID
```

Run `grab2md COMMAND --help` for the complete, configuration-aware option list.

## Commands

| Command | Purpose |
|---|---|
| `convert` | Convert one or more URLs or local HTML files. |
| `batch` | Extract links from input files, convert them, and rewrite successful local links. |
| `crawl` | Recursively fetch and convert pages using a sequential, robots-aware policy. |
| `config` | Inspect, validate, back up, restore, and change configuration. |
| `state` | List, inspect, export, import, clean, and resume crawl state. |

### Python API support

The supported pre-1.0 interface is the `grab2md` command (and equivalent
`python -m grab2md` entry point). The installed Python modules are internal and
may change between alpha releases; importing conversion, crawler, cookie, or
transport implementation modules is not a supported compatibility contract.
`grab2md.__version__` is exposed for metadata inspection only. A library API
will be considered separately if real use cases establish the required result,
exception, and compatibility contract.

Global options include `--log-level` (default `WARNING`), `--debug-log`,
`--banner`, and metadata-backed `--version`.

### Conversion

Useful options include:

- `--content full|main|selector` for explicit content selection (full is the
  lossless default), with `--selector` required by selector mode;
- `--output/-o` to write one source to a file instead of stdout (multiple
  sources cannot share one output path);
- `--cookie-json` for an owner-only portable cookie export on every platform;
- `--browser-cookies` for compatible Firefox databases or the narrow legacy
  Windows Chrome DPAPI path, optionally with a one-shot `--cookie-path` that
  does not modify global configuration;
- `--headers-file` for an owner-only JSON object of target request headers;
- `--storage-state` with `--render-js` for owner-only Playwright session state;
- `--enhanced-headers/--basic-headers` and `--user-agent-contact` for an honest,
  versioned request identity;
- `--download-images` with a configurable `--images-dir`;
- `--allow-private-network` only for explicitly trusted intranet, loopback, or
  development destinations;
- `--insecure` only for trusted hosts with invalid certificates; and
- `--fancy` for decorated progress output.

Automatic Firefox database extraction is supported on Windows, macOS, and
Linux for recognized profile/database schemas. Current Chrome normally uses
app-bound (`v20`) encryption, so direct database extraction is generally
unavailable and fails closed with export guidance. Only legacy Windows
DPAPI-backed Chrome keys are supported; Chrome Keychain/keyring retrieval is
not implemented on macOS or Linux. Exported, owner-private cookie JSON is the
primary portable authentication path on every platform. Password submission is
not supported.

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
- `--max-depth`, a cumulative per-start `--max-pages` page-attempt budget that
  includes failures and explicit retries, and jittered `--delay`;
- `--respect-robots/--ignore-robots`;
- hard-maximum requests-per-minute `--rate-limit` for each destination origin
  (host and port), with adaptive slowing and a circuit breaker;
- `--polite` for at least one second between sequential requests and twice any
  larger explicit delay;
- content selection, progress, output layout, visualization, and quiet-mode switches.

`Ctrl+C` or termination checkpoints the active crawl and then preserves normal
signal behavior. Deferred URLs remain queued instead of being silently lost.

## Configuration and state

Configuration is stored in the `grab2md` directory beneath the platform config
root (`$XDG_CONFIG_HOME` or `~/.config` on Linux, `Application Support` on
macOS, and `%APPDATA%` on Windows). Writes are validated, atomic, backed up,
and recoverable. `GRAB2MD_CONFIG_PATH` overrides the complete file path. Run:

```bash
grab2md config show
grab2md config path
grab2md config show-options
grab2md config set-cli-default convert content_mode main
grab2md config set-cli-default crawl max_pages 250
grab2md config backup
grab2md config list-backups
```

CLI defaults are typed and loaded at invocation time. Optional values accept
`null`; invalid updates fail without replacing the existing file. Concurrent
configuration changes from separate processes use last-write-wins semantics,
so serialize configuration commands in automation.

CSS selectors are caller-owned generic inputs; grab2md does not ship or
silently apply per-site extraction profiles. A selector can be supplied for one
run or configured as a CLI default together with `content_mode=selector`.

Crawl state supports `list`, `resume`, `clean`, `export`, `import`, and `info`.
State files use restrictive permissions on POSIX systems. `state list` prints
complete reusable IDs; other state commands also accept an unambiguous prefix
of at least eight characters. Identifiers and resolved state paths are confined
to the configured state directory.

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

See [`extension/README.md`](https://github.com/jkindrix/grab2md/blob/main/extension/README.md) for installation and testing.

## Security boundaries

- Crawl and batch outputs are contained beneath the selected output root;
  traversal and symlink escapes are rejected or sanitized.
- Browser cookie databases are copied into unpredictable owner-private
  temporary directories and removed after success, failure, or interruption.
- Configuration and crawl states are atomically replaced using
  `0600` files in `0700` directories on POSIX systems.
- Project-owned diagnostic logs are owner-only on POSIX systems and redact URL
  userinfo, credential-bearing headers, complete cookie values, and recognized
  credential query/fragment fields before emission. The rotating log defaults
  to the platform's per-user application-log/state directory; set
  `GRAB2MD_LOG_PATH` to choose an explicit file. Embedding applications remain
  responsible for handlers they attach to third-party or root loggers.
- Target authentication accepts scoped browser cookies, an owner-only JSON
  cookie export, header file, or Playwright storage-state file for rendered
  conversion. Login flows remain outside grab2md, and authentication files are
  rejected when group- or world-readable or when the supplied final path is a
  symlink on POSIX systems. Resolution of caller-owned ancestor directories
  remains an operating-system/filesystem trust boundary.
- Remote pages, crawl targets, robots files, and images
  allow only HTTP(S), resolve each origin once, connect only to validated
  numeric addresses, and manually revalidate redirects. Private, loopback,
  link-local, metadata, IPv4-mapped, 6to4, IPv4-compatible, and well-known
  NAT64 encodings of non-public IPv4 destinations are blocked by default.
  HTTPS redirects cannot downgrade to HTTP. Guarded traffic
  bypasses configured and environment proxies because proxy-side DNS would
  defeat address pinning.
- Static page/crawl responses are capped at 10 MiB and robots files at 1 MiB.
  Image acquisition additionally verifies MIME type and file signature, rejects
  every SVG image, and enforces 10 MiB per-image and 50 MiB per-conversion limits.
- `--allow-private-network` explicitly relaxes destination classification for
  trusted internal or development targets; DNS pinning, redirect validation,
  URL validation, response limits, and TLS verification remain active.
- Local image copying is restricted to regular files beneath the source HTML
  directory; parent traversal and symlink escapes are rejected.
- `--insecure` disables TLS verification and should be used only for hosts you
  control. It exposes the connection to interception but does not authorize
  private-network access.

See [`docs/network-security.md`](https://github.com/jkindrix/grab2md/blob/main/docs/network-security.md) for the complete
outbound request contract and maintainer integration rule.

Windows relies on the current account's directory ACLs because POSIX mode bits
are unavailable there.

## Output contract

Remote relative links and image references are resolved against the final URL
and the document's valid `<base>` element. `--metadata` adds deterministic YAML
front matter for available title, author/date, canonical URL, description, and
language fields. Local references remain relative. See
[`docs/output-contract.md`](https://github.com/jkindrix/grab2md/blob/main/docs/output-contract.md) for the exact contract.

## Known limitations

- Conversion uses `markdownify`. Full-document mode deliberately preserves
  authored boilerplate; opt-in main-content mode uses substantial semantic
  regions and a confidence-gated readability fallback, whose quality varies by
  document. The measured decision is recorded in
  [`ADR 0002`](https://github.com/jkindrix/grab2md/blob/main/docs/adr/0002-select-main-content-extraction.md).
- JavaScript rendering is opt-in for `convert`; batch and crawl remain static.
- Metadata extraction intentionally uses declared HTML/meta fields rather than
  text inference or executable structured data.
- Crawling is sequential; removed concurrency options are not advertised.
- Browser cookie support is deliberately bounded: Firefox database schemas can
  change, while current Chrome's app-bound (`v20`) cookies are not available to
  automatic extraction. The Chrome database path is limited to legacy Windows
  DPAPI-backed keys and excludes macOS Keychain and Linux keyring formats. Use
  an owner-private cookie JSON export as the primary portable path.
- The extension must be installed unpacked; no Web Store release exists.

## Development

Run the canonical local gates from a clean checkout:

```bash
poetry sync --with dev
poetry check
poetry run pre-commit run --all-files
poetry run pre-commit run --all-files --hook-stage pre-push
node --test extension/tests/*.test.js
node extension/tests/chromium-smoke.js
./deploy.sh --dry-run
```

Coverage uses the production package as its denominator and enforces the floor
documented in [`docs/coverage.md`](https://github.com/jkindrix/grab2md/blob/main/docs/coverage.md).

## Project documentation

- [`CHANGELOG.md`](https://github.com/jkindrix/grab2md/blob/main/CHANGELOG.md): user-visible changes and changelog policy
- [`CONTRIBUTING.md`](https://github.com/jkindrix/grab2md/blob/main/CONTRIBUTING.md): development setup and contribution gates
- [`SECURITY.md`](https://github.com/jkindrix/grab2md/blob/main/SECURITY.md): private vulnerability-reporting route
- [`SUPPORT.md`](https://github.com/jkindrix/grab2md/blob/main/SUPPORT.md): alpha support and compatibility policy
- [`docs/releasing.md`](https://github.com/jkindrix/grab2md/blob/main/docs/releasing.md): reproducible release checklist
- [`docs/deployment.md`](https://github.com/jkindrix/grab2md/blob/main/docs/deployment.md): local deployment details
- [`docs/configuration-example.md`](https://github.com/jkindrix/grab2md/blob/main/docs/configuration-example.md): configuration example
- [`docs/adr/0001-defer-scale-out-crawling.md`](https://github.com/jkindrix/grab2md/blob/main/docs/adr/0001-defer-scale-out-crawling.md): scale-out architecture gate
- [`docs/internal/`](https://github.com/jkindrix/grab2md/tree/main/docs/internal): historical planning and review records

## License

Copyright (c) 2025-2026 Justin Kindrix. Distributed under the
[MIT License](https://github.com/jkindrix/grab2md/blob/main/LICENSE).
