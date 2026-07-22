"""Presentation-neutral command option and execution boundaries."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from grab2md.cli.runtime import build_header_config, build_header_manager
from grab2md.markdown.batch_processor import BatchResult
from grab2md.markdown.content_extractor import ContentMode, validate_content_request
from grab2md.markdown.crawler import CrawlResult
from grab2md.utils.crawl_policy import validate_crawl_policy
from grab2md.utils.parser import is_url
from grab2md.utils.state_manager import StateManager


class Browser(str, Enum):
    CHROME = "chrome"
    FIREFOX = "firefox"


class CommandUsageError(ValueError):
    """A command option combination or source set is invalid."""


COMMAND_ERRORS = (OSError, RuntimeError, ValueError)


@dataclass(frozen=True)
class CommandFailure:
    """Presentation-neutral classification of one command boundary failure."""

    message: str
    exit_code: int


def classify_command_failure(label: str, error: Exception) -> CommandFailure:
    """Give every network command the same usage/runtime failure semantics."""
    if isinstance(error, CommandUsageError):
        return CommandFailure(f"{label} options are invalid: {error}", 2)
    return CommandFailure(f"{label} failed: {error}", 1)


@dataclass(frozen=True)
class ConvertCommandOptions:
    sources: list[str]
    content_mode: ContentMode
    selector: Optional[str]
    output: Optional[Path]
    no_cookies: bool
    browser_cookies: bool
    browser: Optional[Browser]
    cookie_path: Optional[Path]
    cookie_json: Optional[Path]
    headers_file: Optional[Path]
    storage_state: Optional[Path]
    local: bool
    enhanced_headers: bool
    user_agent_contact: Optional[str]
    insecure: bool
    allow_private_network: bool
    download_images: bool
    images_dir: str
    include_metadata: bool
    render_js: bool
    fancy: bool

    def conversion_arguments(self) -> dict[str, Any]:
        return {
            "content_mode": self.content_mode,
            "selector": self.selector,
            "output": self.output,
            "no_cookies": self.no_cookies,
            "browser_cookies": self.browser_cookies,
            "browser": self.browser,
            "cookie_path": self.cookie_path,
            "cookie_json": self.cookie_json,
            "headers_file": self.headers_file,
            "storage_state": self.storage_state,
            "local": self.local,
            "download_images": self.download_images,
            "images_dir": self.images_dir,
            "enhanced_headers": self.enhanced_headers,
            "user_agent_contact": self.user_agent_contact,
            "insecure": self.insecure,
            "include_metadata": self.include_metadata,
            "render_js": self.render_js,
            "allow_private_network": self.allow_private_network,
        }


def prepare_convert_options(
    options: ConvertCommandOptions,
) -> None:
    """Validate one conversion request without mutating persistent settings."""
    validate_content_request(options.content_mode, options.selector)
    if options.output is not None and len(options.sources) > 1:
        raise CommandUsageError(
            "--output accepts exactly one source; omit it for multiple sources"
        )
    if options.cookie_path is not None and not options.browser_cookies:
        raise CommandUsageError("--cookie-path requires --browser-cookies")
    if options.cookie_path is not None and options.cookie_json is not None:
        raise CommandUsageError("--cookie-path and --cookie-json cannot be combined")
    if options.no_cookies and (
        options.browser_cookies
        or options.cookie_path is not None
        or options.cookie_json is not None
    ):
        raise CommandUsageError("--no-cookies cannot be combined with cookie inputs")


@dataclass(frozen=True)
class BatchCommandOptions:
    input_patterns: list[str]
    output_dir: Path
    content_mode: ContentMode
    selector: Optional[str]
    include_metadata: bool
    enhanced_headers: bool
    user_agent_contact: Optional[str]
    flatten_output: bool
    flatten_all: bool
    hierarchical: bool
    visualize: bool
    report: Optional[Path]
    insecure: bool
    allow_private_network: bool
    quiet: bool


@dataclass(frozen=True)
class BatchExecution:
    result: BatchResult
    expanded_files: tuple[str, ...]
    unmatched_patterns: tuple[str, ...]


def expand_input_patterns(patterns: list[str]) -> tuple[list[str], list[str]]:
    expanded: list[str] = []
    unmatched: list[str] = []
    for pattern in patterns:
        matches = glob.glob(os.path.expanduser(pattern))
        if matches:
            expanded.extend(matches)
        else:
            unmatched.append(pattern)
    return expanded, unmatched


def execute_batch(
    options: BatchCommandOptions,
    *,
    processor: Callable[..., BatchResult],
    config: dict[str, Any],
    progress_callback: Optional[Callable[..., None]] = None,
) -> BatchExecution:
    """Validate, resolve inputs, construct headers, and execute one batch."""
    validate_content_request(options.content_mode, options.selector)
    if options.flatten_output and options.flatten_all:
        raise CommandUsageError("Cannot use --flatten and --flatten-all together")
    if (options.flatten_output or options.flatten_all) and options.hierarchical:
        raise CommandUsageError(
            "Cannot use --hierarchical with --flatten or --flatten-all"
        )
    expanded, unmatched = expand_input_patterns(options.input_patterns)
    if not expanded:
        raise CommandUsageError("No input files found to process")
    options.output_dir.mkdir(parents=True, exist_ok=True)
    result = processor(
        expanded,
        options.output_dir,
        content_mode=options.content_mode,
        selector=options.selector,
        progress_callback=progress_callback,
        flatten_output=options.flatten_output,
        flatten_all=options.flatten_all,
        hierarchical_domains=options.hierarchical,
        verify_ssl=not options.insecure,
        include_metadata=options.include_metadata,
        allow_private_network=options.allow_private_network,
        header_manager=build_header_manager(
            config,
            enhanced_headers=options.enhanced_headers,
            user_agent_contact=options.user_agent_contact,
        ),
    )
    return BatchExecution(result, tuple(expanded), tuple(unmatched))


@dataclass(frozen=True)
class CrawlCommandOptions:
    start_urls: list[str]
    output_dir: Path
    follow_option: str
    max_depth: int
    max_pages: int
    delay: float
    respect_robots: bool
    rate_limit: Optional[int]
    enhanced_headers: bool
    user_agent_contact: Optional[str]
    insecure: bool
    allow_private_network: bool
    polite: bool
    show_progress: bool
    content_mode: ContentMode
    selector: Optional[str]
    include_metadata: bool
    flatten_output: bool
    hierarchical: bool
    visualize: bool
    quiet: bool


@dataclass
class CrawlExecution:
    results: list[tuple[str, CrawlResult]] = field(default_factory=list)
    invalid_urls: list[str] = field(default_factory=list)
    url_mapping: dict[str, str] = field(default_factory=dict)

    @property
    def failed_count(self) -> int:
        return len(self.invalid_urls) + sum(
            not result.success for _, result in self.results
        )

    @property
    def processed_start_count(self) -> int:
        return sum(result.success for _, result in self.results)

    @property
    def processed_page_count(self) -> int:
        return sum(result.processed_count for _, result in self.results)


def execute_crawls(
    options: CrawlCommandOptions,
    *,
    crawler: Callable[..., CrawlResult],
    config: dict[str, Any],
    progress_callback: Optional[Callable[..., None]] = None,
    state_factory: Callable[[], StateManager] = StateManager,
) -> CrawlExecution:
    """Validate and execute starting URLs without owning presentation."""
    validate_content_request(options.content_mode, options.selector)
    try:
        validate_crawl_policy(
            follow_option=options.follow_option,
            max_depth=options.max_depth,
            max_pages=options.max_pages,
            delay=options.delay,
            rate_limit=options.rate_limit,
        )
    except ValueError as error:
        raise CommandUsageError(str(error)) from error
    options.output_dir.mkdir(parents=True, exist_ok=True)
    header_config = build_header_config(
        config,
        enhanced_headers=options.enhanced_headers,
        user_agent_contact=options.user_agent_contact,
    )
    execution = CrawlExecution()
    for start_url in options.start_urls:
        if not is_url(start_url):
            execution.invalid_urls.append(start_url)
            continue
        state_manager = state_factory()
        with state_manager.signal_handling():
            result = crawler(
                start_url,
                options.output_dir,
                follow_option=options.follow_option,
                max_depth=options.max_depth,
                max_pages=options.max_pages,
                delay=options.delay,
                respect_robots=options.respect_robots,
                rate_limit=options.rate_limit,
                header_config=header_config,
                polite_mode=options.polite,
                show_progress=options.show_progress,
                content_mode=options.content_mode,
                selector=options.selector,
                include_metadata=options.include_metadata,
                progress_callback=progress_callback,
                flatten_output=options.flatten_output,
                hierarchical_domains=options.hierarchical,
                verify_ssl=not options.insecure,
                allow_private_network=options.allow_private_network,
                state_manager=state_manager,
            )
        execution.results.append((start_url, result))
        execution.url_mapping.update(result.url_mapping)
    return execution
