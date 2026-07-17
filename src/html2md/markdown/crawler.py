import logging
import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from html2md.cookies.session_manager import get_session
from html2md.markdown.archive import (
    ArtifactManifest,
    ArtifactStore,
    OutputPlanner,
)
from html2md.markdown.content_extractor import ContentMode, validate_content_request
from html2md.markdown.crawl_engine import (
    CrawlCheckpointStore,
    CrawlFrontier,
    CrawlOptions,
    CrawlScope,
    SequentialCrawlEngine,
)
from html2md.markdown.pipeline import PagePipeline
from html2md.network.request_handler import fetch_html
from html2md.network.robots_parser import RobotsChecker
from html2md.network.header_manager import HeaderManager, HeaderConfig
from html2md.network.request_scheduler import SequentialRequestScheduler
from html2md.network.safe_http import DestinationPolicy
from html2md.utils.state_manager import StateManager

# Setup logger
logger = logging.getLogger("html2md")


@dataclass(frozen=True)
class CrawlResult:
    """Stable result contract for every crawl outcome."""

    processed_count: int = 0
    url_mapping: Dict[str, str] = field(default_factory=dict)
    crawl_id: Optional[str] = None
    success: bool = True
    failed_count: int = 0
    error: Optional[str] = None


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
    # State management parameters
    state_manager=None,
    resume_crawl_id=None,
    enable_checkpoints=True,
    checkpoint_interval=300,
    checkpoint_page_count=100,
):
    """
    Crawl a website starting from a URL and convert each page to markdown.

    Args:
        start_url (str): Starting URL to crawl
        output_dir (str): Directory to save the output files
        follow_option (str, optional): How to follow links:
            - "domain-only": Follow links to the same domain
            - "host-only": Follow links to the same host (excluding subdomains)
            - "subdomain": Follow links to the same domain and its subdomains
            - Any other string is treated as a regex pattern to match URLs
        max_depth (int, optional): Maximum link depth to follow. Defaults to 3.
        max_pages (int, optional): Maximum number of pages to crawl. Defaults to 100.
        delay (float, optional): Delay between requests in seconds. Random jitter of ±30% will be added. Defaults to 0.0.
        respect_robots (bool, optional): Whether to respect robots.txt rules. Defaults to True.
        rate_limit (int, optional): Requests per minute limit. If None, no rate limiting is applied. Defaults to None.
        content_mode: Full document, inferred main content, or explicit selector.
        selector: CSS selector required by selector mode.
        progress_callback (callable, optional): Function to call with progress updates
        flatten_output (bool, optional): If True, creates output directories directly
                                       named after domain. Defaults to False.
        hierarchical_domains (bool, optional): If True, creates hierarchical domain structure
                                              (e.g., com/jetbrains/www). Defaults to False.
        download_images (bool, optional): Whether to download images from pages.
        images_dir (str, optional): Directory name for images (default: "images").
        verify_ssl (bool, optional): Whether to verify SSL certificates. Defaults to True.
            Set to False only for trusted hosts with invalid/self-signed certificates.
        include_metadata (bool, optional): Prepend YAML front matter to each output.
        state_manager (StateManager, optional): State manager for persistence. If None, creates new one.
        resume_crawl_id (str, optional): ID of crawl to resume. If None, starts new crawl.
        enable_checkpoints (bool, optional): Whether to enable checkpointing. Defaults to True.
        checkpoint_interval (int, optional): Checkpoint interval in seconds. Defaults to 300.
        checkpoint_page_count (int, optional): Checkpoint after this many pages. Defaults to 100.

    Returns:
        CrawlResult: Typed result for successful and unsuccessful outcomes.
    """
    content_mode = validate_content_request(content_mode, selector)

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Initialize state manager
    if state_manager is None:
        state_manager = StateManager()

    # Configure checkpoint settings
    if enable_checkpoints:
        state_manager.checkpoint_interval = checkpoint_interval
        state_manager.checkpoint_page_count = checkpoint_page_count

    # Helper function to update progress. It must exist before resume handling.
    def update_progress(message, url=None, status=None):
        logger.info(message)
        if progress_callback:
            progress_callback(message, url, status)

    # Initialize crawl state
    crawl_state = None
    if resume_crawl_id:
        # Resume existing crawl
        crawl_state = state_manager.load_state(resume_crawl_id)
        if crawl_state:
            # Restore state
            start_url = crawl_state.start_url
            output_dir = crawl_state.output_dir
            url_to_file_mapping = crawl_state.urls_visited.copy()
            visited_urls = set(crawl_state.urls_visited.keys()) | set(
                crawl_state.urls_failed.keys()
            )
            queue = list(crawl_state.urls_queued)
            processed_urls_count = len(crawl_state.urls_visited)
        else:
            update_progress(
                f"Could not resume crawl {resume_crawl_id}, starting new crawl",
                start_url,
                "warning",
            )

    crawl_scope_url = (
        str(crawl_state.config.get("scope_url", start_url))
        if crawl_state
        else start_url
    )

    # Create new crawl state if not resuming
    if not crawl_state:
        crawl_config = {
            "follow_option": follow_option,
            "max_depth": max_depth,
            "max_pages": max_pages,
            "delay": delay,
            "respect_robots": respect_robots,
            "rate_limit": rate_limit,
            "content_mode": content_mode.value,
            "selector": selector,
            "flatten_output": flatten_output,
            "hierarchical_domains": hierarchical_domains,
            "download_images": download_images,
            "images_dir": images_dir,
            "verify_ssl": verify_ssl,
            "include_metadata": include_metadata,
            "allow_private_network": allow_private_network,
            "polite_mode": polite_mode,
            "enable_checkpoints": enable_checkpoints,
            "checkpoint_interval": checkpoint_interval,
            "checkpoint_page_count": checkpoint_page_count,
            "scope_url": start_url,
        }
        crawl_state = state_manager.create_new_state(
            start_url, output_dir, crawl_config
        )
        url_to_file_mapping = {}
        visited_urls = set()
        queue = [(start_url, 0)]  # (url, depth)
        processed_urls_count = 0

        # Initialize queue in state
        state_manager.add_urls_to_queue([(start_url, 0)])

    frontier = CrawlFrontier(queue, terminal_urls=visited_urls)

    # Now update progress for resume case
    if resume_crawl_id and crawl_state:
        update_progress(f"Resuming crawl {resume_crawl_id}", start_url, "info")

    # Create session for requests (shared by robots checks, page fetches, and image downloads)
    session = get_session(verify_ssl=verify_ssl)
    network_policy = DestinationPolicy(allow_private=allow_private_network)
    scheduler = SequentialRequestScheduler(
        requests_per_minute=rate_limit,
        minimum_delay=delay,
        polite=polite_mode,
    )
    manifest = ArtifactManifest.from_mapping(url_to_file_mapping)
    output_planner = OutputPlanner(
        output_dir,
        flatten_domain=flatten_output,
        hierarchical_domains=hierarchical_domains,
    )
    page_pipeline = PagePipeline()

    # Initialize header manager
    header_manager = HeaderManager(header_config or HeaderConfig())

    if rate_limit and rate_limit > 0:
        update_progress(
            f"Rate limiting enabled: {rate_limit} requests/minute", start_url, "info"
        )
    if polite_mode:
        update_progress(
            "Polite mode enabled: slower sequential request policy",
            start_url,
            "info",
        )

    # Initialize robots.txt checker if enabled
    robots_checker = None
    robots_delay = None
    if respect_robots:
        initial_headers = header_manager.get_headers(start_url)
        robots_checker = RobotsChecker(
            user_agent=initial_headers["User-Agent"],
            session=session,
            network_policy=network_policy,
            scheduler=scheduler,
        )

        # Check if start URL is allowed
        if not robots_checker.can_fetch(start_url):
            update_progress(
                f"Starting URL is disallowed by robots.txt: {start_url}",
                start_url,
                "blocked",
            )
            session.close()
            return CrawlResult(
                crawl_id=crawl_state.crawl_id if crawl_state else None,
                success=False,
                error=f"Starting URL is disallowed by robots.txt: {start_url}",
            )

        # Get crawl-delay from robots.txt
        robots_delay = robots_checker.get_crawl_delay(start_url)
        if robots_delay:
            update_progress(
                f"robots.txt specifies crawl-delay: {robots_delay}s", start_url, "info"
            )
            # Use the larger of user-specified delay or robots.txt delay
            if robots_delay > delay:
                delay = robots_delay
                scheduler.minimum_delay = max(scheduler.minimum_delay, robots_delay)
                update_progress(
                    f"Using robots.txt crawl-delay: {delay}s", start_url, "info"
                )

    checkpoint_store = CrawlCheckpointStore(state_manager, enabled=enable_checkpoints)
    engine = SequentialCrawlEngine(
        frontier=frontier,
        scope=CrawlScope(crawl_scope_url, follow_option),
        robots=robots_checker,
        scheduler=scheduler,
        page_pipeline=page_pipeline,
        artifact_store=ArtifactStore,
        checkpoint_store=checkpoint_store,
        event_sink=update_progress,
        session=session,
        network_policy=network_policy,
        header_manager=header_manager,
        manifest=manifest,
        output_planner=output_planner,
        url_mapping=url_to_file_mapping,
        fetch_page=fetch_html,
        options=CrawlOptions(
            max_depth=max_depth,
            max_pages=max_pages,
            content_mode=content_mode,
            selector=selector,
            download_images=download_images,
            images_dir=images_dir,
            include_metadata=include_metadata,
            allow_private_network=allow_private_network,
        ),
        initial_processed=processed_urls_count,
    )
    try:
        run = engine.run()
    finally:
        session.close()
    processed_urls_count = run.processed_count
    failed_urls_count = run.failed_count

    for domain, domain_stats in scheduler.get_all_stats().items():
        if domain_stats.total_requests > 0:
            update_progress(
                f"Request stats for {domain}: {domain_stats.total_requests} requests, "
                f"{domain_stats.successful_requests} successful, "
                f"{domain_stats.failed_requests} failed",
                start_url,
                "stats",
            )

    update_progress(
        f"Completed crawling. Processed {processed_urls_count} pages, "
        f"visited {run.terminal_count} URLs."
    )

    # Save final checkpoint
    if enable_checkpoints and crawl_state:
        state_manager.save_checkpoint("completion", "Crawl completed successfully")

    success = processed_urls_count > 0 and failed_urls_count == 0
    if failed_urls_count:
        error = f"Crawl completed with {failed_urls_count} failed URLs"
    elif not processed_urls_count:
        error = "Crawl completed without producing any pages"
    else:
        error = None

    return CrawlResult(
        processed_count=processed_urls_count,
        url_mapping=url_to_file_mapping,
        crawl_id=crawl_state.crawl_id if crawl_state else None,
        success=success,
        failed_count=failed_urls_count,
        error=error,
    )
