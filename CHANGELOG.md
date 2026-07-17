# Changelog

All notable changes are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and intends to use
[Semantic Versioning](https://semver.org/) once public releases begin.

## [Unreleased]

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

### Removed

- Removed the unreachable provider-specific OAuth flow, token storage, and its
  runtime dependencies; login and credential acquisition remain outside the
  converter.
- Removed domain/footer/heading-based Markdown truncation from all Python
  conversion paths.

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

[Unreleased]: https://github.com/jkindrix/html2md/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/jkindrix/html2md/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/jkindrix/html2md/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/jkindrix/html2md/releases/tag/v0.1.0
