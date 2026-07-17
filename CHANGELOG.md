# Changelog

All notable changes are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and intends to use
[Semantic Versioning](https://semver.org/) once public releases begin.

## [Unreleased]

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

[Unreleased]: https://github.com/jkindrix/html2md/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jkindrix/html2md/releases/tag/v0.1.0
