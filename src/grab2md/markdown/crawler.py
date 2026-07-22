"""Crawl lifecycle assembly over the deliberately sequential engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import requests

from grab2md.cookies.session_manager import get_session
from grab2md.markdown.archive import ArtifactManifest, ArtifactStore, OutputPlanner
from grab2md.markdown.content_extractor import ContentMode, validate_content_request
from grab2md.markdown.crawl_engine import (
    CrawlCheckpointStore,
    CrawlFrontier,
    CrawlOptions,
    CrawlScope,
    SequentialCrawlEngine,
)
from grab2md.markdown.pipeline import PagePipeline
from grab2md.network.header_manager import HeaderConfig, HeaderManager
from grab2md.network.request_handler import fetch_html
from grab2md.network.request_scheduler import SequentialRequestScheduler
from grab2md.network.robots_parser import RobotsChecker
from grab2md.network.safe_http import DestinationPolicy
from grab2md.utils.crawl_policy import validate_crawl_policy
from grab2md.utils.redaction import get_redacting_logger
from grab2md.utils.state_manager import StateManager
from grab2md.utils.state_schema import CrawlState

logger = get_redacting_logger(__name__)

ProgressCallback = Callable[[str, Optional[str], Optional[str]], None]


@dataclass(frozen=True)
class CrawlResult:
    """Stable result contract for every crawl outcome."""

    processed_count: int = 0
    url_mapping: dict[str, str] = field(default_factory=dict)
    crawl_id: Optional[str] = None
    success: bool = True
    failed_count: int = 0
    error: Optional[str] = None


@dataclass(frozen=True)
class CrawlRequest:
    start_url: str
    output_dir: Path
    follow_option: str = "domain-only"
    max_depth: int = 3
    max_pages: int = 100
    delay: float = 0.0
    respect_robots: bool = True
    rate_limit: Optional[int] = None
    header_config: Optional[HeaderConfig] = None
    polite_mode: bool = False
    show_progress: bool = True
    content_mode: ContentMode = ContentMode.FULL
    selector: Optional[str] = None
    progress_callback: Optional[ProgressCallback] = None
    flatten_output: bool = False
    hierarchical_domains: bool = False
    download_images: bool = False
    images_dir: str = "images"
    verify_ssl: bool = True
    include_metadata: bool = False
    allow_private_network: bool = False
    resume_crawl_id: Optional[str] = None
    enable_checkpoints: bool = True
    checkpoint_interval: int = 300
    checkpoint_page_count: int = 100


@dataclass
class CrawlRunContext:
    """New and resumed state normalized for one engine run."""

    state: CrawlState
    start_url: str
    scope_url: str
    output_dir: Path
    url_mapping: dict[str, str]
    terminal_urls: set[str]
    queue: list[tuple[str, int]]
    initial_processed: int
    initial_attempted: int
    retry_attempts: dict[str, int]


@dataclass
class CrawlRuntime:
    engine: SequentialCrawlEngine
    session: requests.Session
    scheduler: SequentialRequestScheduler


def _progress_sink(callback: Optional[ProgressCallback]) -> ProgressCallback:
    def emit(
        message: str, url: Optional[str] = None, status: Optional[str] = None
    ) -> None:
        logger.info(message)
        if callback:
            callback(message, url, status)

    return emit


def _crawl_config(request: CrawlRequest) -> dict[str, object]:
    return {
        "follow_option": request.follow_option,
        "max_depth": request.max_depth,
        "max_pages": request.max_pages,
        "delay": request.delay,
        "respect_robots": request.respect_robots,
        "rate_limit": request.rate_limit,
        "content_mode": request.content_mode.value,
        "selector": request.selector,
        "flatten_output": request.flatten_output,
        "hierarchical_domains": request.hierarchical_domains,
        "download_images": request.download_images,
        "images_dir": request.images_dir,
        "verify_ssl": request.verify_ssl,
        "include_metadata": request.include_metadata,
        "allow_private_network": request.allow_private_network,
        "polite_mode": request.polite_mode,
        "enable_checkpoints": request.enable_checkpoints,
        "checkpoint_interval": request.checkpoint_interval,
        "checkpoint_page_count": request.checkpoint_page_count,
        "scope_url": request.start_url,
    }


def initialize_crawl_context(
    request: CrawlRequest,
    state_manager: StateManager,
    emit: ProgressCallback,
) -> CrawlRunContext:
    """Normalize a new or resumed crawl behind one typed context."""
    if request.enable_checkpoints:
        state_manager.checkpoint_interval = request.checkpoint_interval
        state_manager.checkpoint_page_count = request.checkpoint_page_count

    state = (
        state_manager.load_state(request.resume_crawl_id)
        if request.resume_crawl_id
        else None
    )
    if state is None:
        if request.resume_crawl_id:
            emit(
                f"Could not resume crawl {request.resume_crawl_id}, starting new crawl",
                request.start_url,
                "warning",
            )
        state = state_manager.create_new_state(
            request.start_url, str(request.output_dir), _crawl_config(request)
        )
        state_manager.add_urls_to_queue([(request.start_url, 0)])
        return CrawlRunContext(
            state=state,
            start_url=request.start_url,
            scope_url=request.start_url,
            output_dir=request.output_dir,
            url_mapping={},
            terminal_urls=set(),
            queue=[(request.start_url, 0)],
            initial_processed=0,
            initial_attempted=0,
            retry_attempts={},
        )

    emit(f"Resuming crawl {request.resume_crawl_id}", state.start_url, "info")
    return CrawlRunContext(
        state=state,
        start_url=state.start_url,
        scope_url=str(state.config.get("scope_url", state.start_url)),
        output_dir=Path(state.output_dir),
        url_mapping=state.urls_visited.copy(),
        terminal_urls=set(state.urls_visited) | set(state.urls_failed),
        queue=list(state.urls_queued),
        initial_processed=len(state.urls_visited),
        initial_attempted=state.attempted_count,
        retry_attempts=state.retry_attempts.copy(),
    )


def _configure_robots(
    request: CrawlRequest,
    context: CrawlRunContext,
    *,
    session: requests.Session,
    policy: DestinationPolicy,
    scheduler: SequentialRequestScheduler,
    headers: HeaderManager,
    emit: ProgressCallback,
) -> tuple[RobotsChecker | None, str | None]:
    if not request.respect_robots:
        return None, None
    checker = RobotsChecker(
        user_agent=headers.get_headers(context.start_url)["User-Agent"],
        session=session,
        network_policy=policy,
        scheduler=scheduler,
    )
    if not checker.can_fetch(context.start_url):
        error = f"Starting URL is disallowed by robots.txt: {context.start_url}"
        emit(error, context.start_url, "blocked")
        return checker, error
    robots_delay = checker.get_crawl_delay(context.start_url)
    if robots_delay:
        emit(
            f"robots.txt specifies crawl-delay: {robots_delay}s",
            context.start_url,
            "info",
        )
        if robots_delay > scheduler.minimum_delay:
            scheduler.minimum_delay = robots_delay
            emit(
                f"Using robots.txt crawl-delay: {robots_delay}s",
                context.start_url,
                "info",
            )
    return checker, None


def build_crawl_runtime(
    request: CrawlRequest,
    context: CrawlRunContext,
    state_manager: StateManager,
    emit: ProgressCallback,
) -> tuple[CrawlRuntime | None, str | None]:
    """Construct transport, policy, persistence, and engine collaborators."""
    session = get_session(verify_ssl=request.verify_ssl)
    policy = DestinationPolicy(allow_private=request.allow_private_network)
    scheduler = SequentialRequestScheduler(
        requests_per_minute=request.rate_limit,
        minimum_delay=request.delay,
        polite=request.polite_mode,
    )
    headers = HeaderManager(request.header_config or HeaderConfig())
    robots, startup_error = _configure_robots(
        request,
        context,
        session=session,
        policy=policy,
        scheduler=scheduler,
        headers=headers,
        emit=emit,
    )
    if startup_error:
        session.close()
        return None, startup_error

    if request.rate_limit and request.rate_limit > 0:
        emit(
            "Rate limiting enabled: "
            f"{request.rate_limit} requests/minute per destination origin",
            context.start_url,
            "info",
        )
    if request.polite_mode:
        emit(
            "Polite mode enabled: slower sequential request policy",
            context.start_url,
            "info",
        )

    engine = SequentialCrawlEngine(
        frontier=CrawlFrontier(
            context.queue,
            terminal_urls=context.terminal_urls,
            retry_attempts=context.retry_attempts,
        ),
        scope=CrawlScope(context.scope_url, request.follow_option),
        robots=robots,
        scheduler=scheduler,
        page_pipeline=PagePipeline(),
        artifact_store=ArtifactStore,
        checkpoint_store=CrawlCheckpointStore(
            state_manager, enabled=request.enable_checkpoints
        ),
        event_sink=emit,
        session=session,
        network_policy=policy,
        header_manager=headers,
        manifest=ArtifactManifest.from_mapping(context.url_mapping),
        output_planner=OutputPlanner(
            context.output_dir,
            flatten_domain=request.flatten_output,
            hierarchical_domains=request.hierarchical_domains,
        ),
        url_mapping=context.url_mapping,
        fetch_page=fetch_html,
        options=CrawlOptions(
            max_depth=request.max_depth,
            max_pages=request.max_pages,
            content_mode=request.content_mode,
            selector=request.selector,
            download_images=request.download_images,
            images_dir=request.images_dir,
            include_metadata=request.include_metadata,
            allow_private_network=request.allow_private_network,
        ),
        initial_processed=context.initial_processed,
        initial_attempted=context.initial_attempted,
    )
    return CrawlRuntime(engine, session, scheduler), None


def _terminal_result(
    context: CrawlRunContext,
    processed_count: int,
    failed_count: int,
) -> CrawlResult:
    success = processed_count > 0 and failed_count == 0
    if failed_count:
        error = f"Crawl completed with {failed_count} failed URLs"
    elif not processed_count:
        error = "Crawl completed without producing any pages"
    else:
        error = None
    return CrawlResult(
        processed_count=processed_count,
        url_mapping=context.url_mapping,
        crawl_id=context.state.crawl_id,
        success=success,
        failed_count=failed_count,
        error=error,
    )


def run_crawl(request: CrawlRequest, state_manager: StateManager) -> CrawlResult:
    """Coordinate one crawl lifecycle with typed initialization and termination."""
    validate_crawl_policy(
        follow_option=request.follow_option,
        max_depth=request.max_depth,
        max_pages=request.max_pages,
        delay=request.delay,
        rate_limit=request.rate_limit,
    )
    callback = request.progress_callback if request.show_progress else None
    emit = _progress_sink(callback)
    context = initialize_crawl_context(request, state_manager, emit)
    context.output_dir.mkdir(parents=True, exist_ok=True)
    runtime, startup_error = build_crawl_runtime(request, context, state_manager, emit)
    if runtime is None:
        if request.enable_checkpoints:
            state_manager.save_checkpoint("completion", startup_error)
        return CrawlResult(
            crawl_id=context.state.crawl_id,
            success=False,
            error=startup_error,
        )

    try:
        engine_run = runtime.engine.run()
    finally:
        runtime.session.close()

    for domain, stats in runtime.scheduler.get_all_stats().items():
        if stats.total_requests > 0:
            emit(
                f"Request stats for {domain}: {stats.total_requests} requests, "
                f"{stats.successful_requests} successful, {stats.failed_requests} failed",
                context.start_url,
                "stats",
            )
    result = _terminal_result(
        context, engine_run.processed_count, engine_run.failed_count
    )
    emit(
        f"Completed crawling. Processed {result.processed_count} pages, "
        f"visited {engine_run.terminal_count} URLs, "
        f"failed {result.failed_count}.",
        None,
        None,
    )
    if request.enable_checkpoints:
        state_manager.save_checkpoint(
            "completion", result.error or "Crawl completed successfully"
        )
    return result


def crawl_website(
    start_url,
    output_dir,
    follow_option="domain-only",
    max_depth=3,
    max_pages=100,
    delay=0.0,
    respect_robots=True,
    rate_limit=None,
    header_config=None,
    polite_mode=False,
    show_progress=True,
    content_mode=ContentMode.FULL,
    selector=None,
    progress_callback=None,
    flatten_output=False,
    hierarchical_domains=False,
    download_images=False,
    images_dir="images",
    verify_ssl=True,
    include_metadata=False,
    allow_private_network=False,
    state_manager=None,
    resume_crawl_id=None,
    enable_checkpoints=True,
    checkpoint_interval=300,
    checkpoint_page_count=100,
):
    """Crawl a website and return its stable aggregate result."""
    selected_mode = validate_content_request(content_mode, selector)
    validate_crawl_policy(
        follow_option=follow_option,
        max_depth=max_depth,
        max_pages=max_pages,
        delay=delay,
        rate_limit=rate_limit,
    )
    request = CrawlRequest(
        start_url=start_url,
        output_dir=Path(output_dir),
        follow_option=follow_option,
        max_depth=max_depth,
        max_pages=max_pages,
        delay=delay,
        respect_robots=respect_robots,
        rate_limit=rate_limit,
        header_config=header_config,
        polite_mode=polite_mode,
        show_progress=show_progress,
        content_mode=selected_mode,
        selector=selector,
        progress_callback=progress_callback,
        flatten_output=flatten_output,
        hierarchical_domains=hierarchical_domains,
        download_images=download_images,
        images_dir=images_dir,
        verify_ssl=verify_ssl,
        include_metadata=include_metadata,
        allow_private_network=allow_private_network,
        resume_crawl_id=resume_crawl_id,
        enable_checkpoints=enable_checkpoints,
        checkpoint_interval=checkpoint_interval,
        checkpoint_page_count=checkpoint_page_count,
    )
    return run_crawl(request, state_manager or StateManager())
