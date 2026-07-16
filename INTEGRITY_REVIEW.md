# HTML2MD Project Status and Integrity Record

**Status date:** 2026-07-16

**Development version:** 0.1.0 (alpha)

## Purpose

This document records measured project status. It replaces the previous self-assessment, which claimed production readiness, 95%+ coverage, complete concurrency, and comprehensive end-to-end testing without reproducible evidence.

The earlier assessment was inaccurate and must not be used as release evidence. Current claims should be supported by an exact command, environment, commit, and retained output or CI result.

## Release posture

HTML2MD is a pre-1.0 project undergoing stabilization. It is not ready for a stable package release, Chrome Web Store submission, unattended crawling, or production use.

Feature expansion is frozen while the project repairs and verifies its primary workflows:

1. local HTML conversion;
2. URL conversion;
3. batch conversion;
4. website crawling;
5. interruption and state resume; and
6. supported Chrome extension modes.

## Verified strengths

- Configuration writes use temporary files, `fsync`, and atomic replacement.
- Configuration backup and corruption-recovery behavior has substantive tests.
- Local-file conversion works for representative headings, emphasis, links, tables, and code blocks.
- The CLI exposes a broad and discoverable option surface.
- Rate limiting, circuit breaking, configurable headers, and robots handling provide useful design foundations, although their crawler integration is incomplete.

## Confirmed release blockers

- Brotli is advertised without a guaranteed decoder, so Brotli responses can be emitted as binary text.
- Crawl state cannot serialize `Path` values supplied by the CLI.
- The CLI and crawler use inconsistent result shapes.
- Crawl resume calls a local helper before it is defined.
- Failed commands can return exit code 0 and report success.
- Crawled pages are fetched twice, and real response status/headers do not reach politeness controls.
- Signal handlers checkpoint without reliably terminating.
- URL-derived output paths are not fully contained beneath the selected output root.
- Debug logging can expose cookie and session-token values.
- Unsupported Chrome extension URL/batch/element modes and the duplicate service worker have been removed. The retained popup surface has unpacked-Chromium regression coverage.
- The project now carries its declared MIT grant and the required Turndown third-party notice.

## Test and quality status

The canonical commands are documented in `README.md`. Results are meaningful only when their scope and environment are stated.

The following baseline was produced from a clean prospective tree based on commit `4992c8a`, with only the H2M-002 through H2M-005 batch applied:

- **Environment:** Python 3.11.2; Poetry 1.8.3
- **Install:** `poetry install --with dev --sync` completed from the regenerated lockfile in a new virtual environment.
- **Metadata:** `poetry check` passed.
- **Import/help smoke test:** package version `0.1.0` imported; `html2md --help` exited 0 without stderr after initial default-config creation.
- **Tests:** `poetry run pytest src/html2md/tests tests/config` produced **139 passed, 2 failed, 11 skipped, and 26 warnings**.
- **Coverage:** the documented production-package command reported **45% total coverage** (5,461 statements; 2,983 missed).
- **Ruff:** **99 errors**, 84 reported as automatically fixable.
- **Black:** **34 files** would be reformatted; 18 would remain unchanged.
- **Mypy:** **37 errors in 9 files** across 46 checked source files.

Historical baseline observations at that commit:

- The recovered configuration suite has **58 passing tests**.
- The recovered state suites have **18 passing and 2 failing tests**. One failure confirms the crawl-resume production defect; the other exposes state import/listing isolation behavior.
- The broader committed suite is not green.
- Meaningful CLI and Chrome extension end-to-end coverage is absent.
- Four legacy core test modules are empty and require replacement or removal.

Current remediation evidence for H2M-030 through H2M-032 supersedes those test-health observations:

- `poetry run pytest src/html2md/tests tests/config` passes with **308 passed and 1 external dependency warning**. The unused async stack and its skipped/warning-producing tests have been removed.
- The previously failing state modules pass both alone and in the canonical suite: **22 passed**.
- Converter, cookie-loader, request-handler, and trimmer modules now contain behavior and error-path tests; no core placeholder test remains empty.
- Ten real subprocess tests cover local and URL conversion, batch, crawl, state listing/resume, gzip, redirects, HTTP 404/429/500 failures, robots denial, output traversal containment, and failure exit behavior. Signal interruption/resume subprocess coverage is maintained separately in the committed signal suite.
- Production-only statement coverage is **63.24%** (4,328 statements; 1,591 missed), with an enforced 59% non-regression floor and a documented 75% stabilization target. Package-internal tests are excluded from the denominator.
- CI definitions now run the locked suite and coverage gate on Python 3.11–3.13 and build/smoke-test the wheel. Ruff, Black, and mypy remain explicitly non-blocking debt reports pending H2M-052–054, so H2M-033 is not yet complete.
- Extension static regressions cover HTML salvage, unsupported control removal, packaged scripts, unique controls, least privilege, and preservation of user-authored product words and fenced code. An unpacked-Chromium suite covers popup startup/settings, full-page/article/selection extraction, conversion, preview, clipboard, download, granted API permissions, and denied host access.
- Chrome extension runtime coverage remains absent and is tracked by H2M-046.

Coverage evidence is reproducible through the documented production-package command; future claims must retain the same denominator or explicitly explain a change.

## Supported environment

- Python 3.11 is the current verified development baseline.
- Python 3.12 and 3.13 are CI matrix targets; they become supported claims only after the hosted matrix produces green evidence.
- Poetry and the committed lockfile define the canonical development installation.

## Evidence and update policy

A status claim may be added or changed only when it includes:

1. the commit under test;
2. Python and Poetry/tool versions;
3. the exact command;
4. pass/fail counts or relevant output; and
5. known exclusions, skips, warnings, or environment constraints.

Historical success language should not be preserved as current fact. When evidence changes, update this record in the same work group that produced the change.

## Exit criteria for a stable release

A stable release requires, at minimum:

- a fresh clone installing without regenerating the lockfile;
- green CI on every declared Python version;
- passing end-to-end tests for all advertised CLI and extension workflows;
- stable, tested failure exit codes and no false success reporting;
- no known credential disclosure, unrestricted private-host downloads, or output-root escape;
- complete project and third-party license notices;
- clean install tests for wheel and source distributions; and
- user documentation that describes only delivered, verified behavior.

Until these conditions are met, HTML2MD remains alpha software.
