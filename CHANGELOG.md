# Changelog

All notable changes are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and intends to use
[Semantic Versioning](https://semver.org/) once public releases begin.

## [Unreleased]

## [0.3.0] - 2026-07-17

Sixth source alpha, establishing one explicit acquisition, conversion, archive,
and persistence pipeline across single, batch, crawl, and extension workflows.

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

[Unreleased]: https://github.com/jkindrix/html2md/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/jkindrix/html2md/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/jkindrix/html2md/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/jkindrix/html2md/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/jkindrix/html2md/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/jkindrix/html2md/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/jkindrix/html2md/releases/tag/v0.1.0
