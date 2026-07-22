# Changelog

All notable changes are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and intends to use
[Semantic Versioning](https://semver.org/) once public releases begin.

Versions through `0.3.0` were developed under the former `html2md` identity.
Versions `0.4.0` and `0.4.1` were used only for TestPyPI release rehearsals.
The pending first public `0.4.2` alpha uses `grab2md` consistently.

## [Unreleased]

### Added

- Added hosted Bandit enforcement, immutable GitHub Action pins with weekly
  update automation, and macOS/Windows package-contract jobs.
- Added presentation-neutral command runtimes, typed batch-input and crawl-run
  contexts, focused browser/presenter/platform tests, and an exact-wheel release
  smoke rehearsal.
- Added complete package metadata plus contribution, security-reporting, and
  alpha support policies.
- Added an enforced Poetry requirement-export drift gate and reusable crawl
  state ID prefixes.
- Added a manually authorized OIDC publishing workflow that retrieves the exact
  distributions retained by a successful protected-main CI run, verifies their
  identity, and publishes with PEP 740 attestations through protected TestPyPI
  and PyPI environments.

### Changed

- Audited user-facing documentation, CLI help, release status, and production
  comments against the current implementation; direct conversion is now
  consistently presented as `grab2md SOURCE...`, while `convert` is identified
  only as its hidden compatibility and persisted-configuration namespace.
- Added an enforced documentation consistency check for version alignment,
  primary command presentation, and valid repository-relative Markdown links.
- Renamed the distribution, executable, import package, extension, repository,
  runtime identity, and local storage namespaces from `html2md`/`html2md-cli`
  to `grab2md` before the first public release.
- Made `grab2md SOURCE` the primary single-page form while retaining the hidden
  `grab2md convert SOURCE` pre-release compatibility alias.
- Declared the pre-1.0 distribution CLI-only: internal Python modules remain
  importable but are not a supported compatibility surface; only version
  metadata is exported from the package root.
- Centralized streaming image acquisition on the guarded pinned HTTP transport,
  decomposed the large CLI/batch/crawl coordinators, and made terminal batch and
  crawl states explicit.
- Centralized redirect archive identity and canonical-metadata finalization
  across batch and crawl, unified command-failure classification, and made
  `--no-progress` suppress crawler callbacks as documented.
- Shared the browser-cookie database copy/connection lifecycle while retaining
  format-specific Chrome and Firefox semantics, then separated browser paths,
  private database handling, and the two format implementations behind the
  cookie-source adapters; modernized rate-limiter annotations.
- Consolidated document-base and responsive-image reference parsing, removed
  dead conversion/archive/request surfaces, and kept `Retry-After` parsing in
  the sequential request scheduler as the single policy implementation.
- Limited automatic Chrome cookie extraction to supported Windows DPAPI keys;
  macOS Keychain, Linux keyring, and app-bound v20 formats now fail closed with
  portable-export guidance.
- Made `--cookie-path` a one-shot conversion input instead of silently writing
  it into global configuration, and made Firefox honor install-selected and
  explicitly default profiles.
- Removed dead batch path/filename helpers and their non-production tests.
- Ratcheted the production coverage floor from 75% to 85% and added a stricter
  mypy pass over untyped production function bodies.
- Moved diagnostic logs from the installed package tree to conventional
  per-user platform locations while preserving `GRAB2MD_LOG_PATH`, and unified
  every project logger under one always-redacting `grab2md.*` namespace.
- Renamed the extension's remaining first-party `Html2Md*` controller and
  utility identifiers to `Grab2Md*`.
- Snapshot browser cookie databases through SQLite's backup API so committed
  records still resident in a WAL file are included consistently.
- Restored strict utility-layer dependency direction, centralized dotted config
  traversal, and derive CLI option help from the canonical defaults and schema.
- Updated Ruff and Poetry to their current verified releases, migrated package
  metadata to PEP 621, and added weekly Python and pre-commit update automation.
- Made every package-description link absolute and added a build gate that
  rejects relative links before publishing to a package index.
- Refreshed the locked Python/tooling baseline after the first automated scan
  and made coverage.py's subprocess patch explicit for pytest-cov 7.
- Made `--max-pages` a cumulative attempt budget, made `--rate-limit` a literal
  no-burst maximum, and gave `--polite` a documented one-second delay floor.
- Defined `--rate-limit` explicitly as an independent hard maximum for each
  destination origin instead of implying an aggregate crawl-wide ceiling.
- Kept page-authored canonical URLs as document metadata without treating them
  as archive identities; only requested and redirect-final URLs can suppress a
  duplicate conversion.
- Made the source-install path independent of Poetry while retaining Poetry
  2.4.1 as the pinned contributor and release toolchain.

### Fixed

- Fixed deterministic HTTP HTML decoding when no charset is declared, including
  HTTP/BOM/meta precedence and explicit invalid-encoding failures across
  single-page, batch, and crawl acquisition.
- Removed the extension's undeclared startup control, made fenced-code behavior
  honor its setting, and removed redundant inert link controls.
- Made crawl frontier identity fragment-free while preserving distinct query
  resources, and checkpointed discovered links with the page success transition.
- Preserved caller-owned directory permissions during state export and closed
  HTTP sessions when browser-cookie extraction fails.
- Prevented redirected Windows CLI output from crashing on decorative Unicode,
  and converted local `file:` image URLs with the host platform's path rules.
- Switched popup extraction to the documented `chrome.scripting` `func` key,
  escaped authored Markdown punctuation, and made table conversion unconditional
  instead of exposing an inert setting.
- Made crawl persistence/counting terminal only after successful link discovery,
  isolated malformed Firefox cookie rows, and guaranteed popup conversion errors
  restore terminal error and spinner state.
- Preserved authored indentation, repeated whitespace, blank lines, and long
  backtick runs in extension code blocks, and serialized popup conversions with
  one terminal cleanup path.
- Replaced the crawler's optimizer-strippable response invariant with an
  explicit failure and made generic config updates use the same typed schema as
  command-default updates.
- Rejected multiple conversion sources sharing one output file, confined state
  IDs to their storage root while printing reusable full IDs, and validated
  every archive identity before committing Markdown bytes.
- Treated hostile or malformed document canonical links as absent and refreshed
  committed runtime/development requirement exports from the lock.
- Persisted cumulative page-attempt and per-URL retry counts in crawl-state
  schema 1.1 so resumes cannot reset either `--max-pages` or the retry ceiling;
  version 1.0 and unversioned states migrate conservatively.
- Rejected invalid crawl regular expressions and non-positive or negative crawl
  budgets as usage errors before creating output or making network requests.
- Escaped authored Markdown punctuation and preserved line boundaries inside
  extension table cells.
- Removed an unused legacy configuration file from wheel and source artifacts
  and enforced a package-data allowlist in hosted CI.

### Security

- Restored inert DOM parsing for extension conversion so hostile HTML cannot
  trigger passive resource loads, script/custom-element execution, or
  navigation in the privileged popup.
- Process inert extension input as a parsed document body so page-controlled
  closing tags cannot terminate an internal wrapper and omit trailing content.
- Made asynchronous extension clipboard/download failures terminal instead of
  overwriting them with generic success.
- Corrected Windows Chrome Local State key decoding and made unsupported cookie
  encryption variants fail before decryption.
- Refreshed vulnerable development-tool dependencies and added a hosted audit
  of the complete locked development environment alongside the runtime audit.
- Applied private-file checks to exported cookie JSON, blocked non-public IPv4
  destinations embedded in the well-known NAT64 prefix, rejected HTTPS-to-HTTP
  redirects, and made incompatible Requests pinning adapters fail closed.
- Blocked non-public IPv4 destinations embedded in deprecated IPv4-compatible
  IPv6 addresses and made redirect credential-header removal case-insensitive.
- Fsynced parent directories after atomic JSON replacement so successful state
  and configuration renames have a durable directory entry on POSIX.
- Made current and rotated diagnostic logs owner-only, rejected non-regular log
  targets, and structurally redacted URL userinfo, OAuth/presigned credential
  parameters, bearer/header values, and complete multi-value cookie headers.
- Anchored POSIX image finalization to a validated no-follow destination
  directory handle so concurrent directory substitution cannot redirect the
  atomic write outside its selected output directory.
- Redacted complete Basic, Digest, proxy-authorization, and quoted header values
  and excluded cookie secrets from generated record representations.
- Added a 50 MiB aggregate decoded-transfer budget to optional Chromium
  rendering and directory-fd-anchored POSIX Markdown artifact replacement.

## [0.3.0] - 2026-07-17

Sixth source alpha, establishing shared typed acquisition and conversion
contracts across the Python single, batch, and crawl workflows, plus common
semantic fixtures for the extension's independent conversion engine.

### Added

- Added typed acquired-page and converted-document contracts with consistent
  requested, final, canonical, media, status, and failure information.
- Added a collision-resistant archive planner and manifest, structural link and
  asset rewriting, and atomic artifact persistence.
- Added an injected sequential crawl engine with explicit frontier, scope,
  robots, scheduling, page-pipeline, artifact, checkpoint, and event boundaries.
- Added explicit browser-render policy for allowed origins, readiness,
  timeouts, request budgets, blocked resource types, and credential handling.
- Added versioned crawl-state migrations and shared generic-conversion fixtures
  across the Python and extension implementations.

### Changed

- Single, batch, and crawl conversion now compose the same page and asset
  pipeline; partial and total batch failures have typed results and nonzero exit
  status.
- Crawl pages, redirects, robots requests, and assets now share one sequential
  politeness scheduler and one guarded transport observation boundary.
- Cookie discovery, exported-cookie parsing, replay policy, and HTTP-session
  construction are separate adapters with explicit capability and failure
  contracts.
- Generated requests use an honest `html2md/<version>` identity with optional
  contact information instead of imitating a browser.
- The extension now separates conversion and settings controllers from popup UI
  coordination while retaining standalone operation.

### Removed

- Removed unused concurrency machinery and its configuration surface.
- Removed fabricated referers, browser impersonation, and conditional-request
  settings that lacked a cache-backed implementation.

### Security

- Invalid or unavailable credential sources fail explicitly rather than
  silently degrading to unauthenticated requests.
- Rendered cross-origin requests strip credentials and caller-specific headers;
  every authorized render origin is validated and pinned.
- Browser cookies retain host, domain, path, secure, and expiry policy through
  the centralized replay boundary.

## [0.2.0] - 2026-07-17

Fifth source alpha, replacing implicit and site-specific cleanup with explicit,
generic authentication and content-selection contracts.

### Added

- Added generic owner-private request-header input for authenticated static and
  rendered conversion, plus owner-private Playwright storage-state input for
  rendered conversion.
- Added explicit `full`, `main`, and CSS-selector content modes across convert,
  batch, and crawl. Full-document conversion is the lossless default; inferred
  main-content failure is explicit rather than a silent fallback.

### Changed

- Main-content mode now selects one substantial semantic region when available
  and otherwise uses a confidence-gated readability extractor before the
  existing HTML-to-Markdown pipeline.
- The Chrome extension now preserves the complete document in full-page mode,
  preserves the exact selected fragment in selection mode, and uses packaged
  Mozilla Readability 0.6.0 only when article mode is explicitly selected.

### Removed

- Removed the unreachable provider-specific OAuth flow, token storage, and its
  runtime dependencies; login and credential acquisition remain outside the
  converter.
- Removed domain/footer/heading-based Markdown truncation from all Python
  conversion paths.
- Removed the bundled site-rule map, domain-rule configuration commands, and
  obsolete encoding analysis. Content customization is now a caller-owned CSS
  selector with no packaged per-site behavior.

### Security

- Browser database cookies retain and enforce host, domain, path, secure, and
  expiry scope across redirects instead of being flattened by name.
- Header and browser storage-state authentication inputs require owner-private
  files on POSIX systems and remain within the guarded static or pinned browser
  transport boundaries.

## [0.1.3] - 2026-07-17

Fourth source alpha, narrowing the supported product to generic HTML-to-Markdown
conversion before publication.

### Changed

- Extracted shared CLI presentation and conversion services and raised the
  enforced production coverage floor to 75%.
- Simplified the core and extension conversion paths by removing specialized
  capture, parsing, and page-cleaning behavior.

## [0.1.2] - 2026-07-16

Third alpha release, extending the guarded outbound-network boundary to every
direct fetch path before public package publication.

### Added

- Added `--allow-private-network` as an explicit opt-in for trusted internal and
  local-development destinations.

### Security

- Extended destination validation and numeric-address pinning from image
  downloads to static conversion, batch, crawl, robots, and test OAuth
  requests; every redirect is handled manually and revalidated.
- Pinned Chromium's source hostname through its resolver, failed all other DNS,
  and blocked cross-origin browser redirects rather than permitting a separate
  resolution race.
- Added 10 MiB static page/crawl and 1 MiB robots response limits.
- Corrected crawl hostname/subdomain boundaries, established discovery scope
  from the final starting URL, applied scope before robots lookups, and checked
  redirect destinations against scope and robots before fetching them.
- Removed session credentials and non-safe custom headers from cross-origin
  page and image redirect hops.

## [0.1.1] - 2026-07-16

Second alpha release, closing the remote-image DNS-rebinding residual found
during independent post-remediation verification.

### Changed

- Refreshed the production coverage baseline to 67.18%, raised the enforced
  floor from 59% to 65%, and clarified that 75% is a post-alpha target.
- Made hosted checks portable across colored terminals and ensured extension
  runtime tests use the explicitly provisioned Chromium build.

### Security

- Closed the remote-image DNS-rebinding window by connecting each request and
  redirect only to its validated public address while preserving HTTP and TLS
  hostname identity; guarded image requests now bypass proxies that could
  independently re-resolve the destination.

## [0.1.0] - 2026-07-16

First alpha release after the stabilization and integrity remediation cycle.

### Added

- End-to-end CLI coverage for local, URL, batch, crawl, state, interruption,
  compression, HTTP failure, robots, and path-safety boundaries.
- Required Python 3.11–3.13 CI, production coverage, static quality, wheel,
  extension, security, and dependency-audit gates.
- Metadata-backed `--version` support and a non-mutating deployment dry run.
- Optional `--metadata` YAML front matter for convert, batch, and crawl output.
- An isolated `render` extra and `convert --render-js` mode for pages whose DOM
  requires JavaScript, with required Chromium end-to-end CI coverage.

### Changed

- The planned distribution name is `html2md-cli`; the command and import
  package remain `html2md`.
- Crawl fetching, persistence, politeness, link rewriting, configuration,
  conversion orchestration, and extension behavior were stabilized and tested.
- Runtime dependencies now contain only direct requirements with compatible
  bounds and an audited lockfile.
- Remote relative links and images resolve against the final response URL and
  valid HTML base element while local-file references remain relative.
- The historical enterprise/distributed roadmap is superseded by an accepted
  measured-need, benchmark, architecture, resource, and security gate.

### Security

- Credential and cookie logging is redacted; private temporary files and token
  storage use restrictive permissions.
- Image acquisition rejects private-network targets, unsafe redirects, active
  formats, oversized files, and output-root escapes.
- The extension uses least-privilege permissions and exposes only tested modes.

[Unreleased]: https://github.com/jkindrix/grab2md/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/jkindrix/grab2md/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/jkindrix/grab2md/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/jkindrix/grab2md/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/jkindrix/grab2md/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/jkindrix/grab2md/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/jkindrix/grab2md/releases/tag/v0.1.0
