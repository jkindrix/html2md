import logging
import os
import time
import random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, Optional

from html2md.cookies.session_manager import get_session
from html2md.markdown.converter import html_content_to_markdown
from html2md.markdown.link_rewriter import rewrite_links
from html2md.markdown.batch_processor import create_directory_structure
from html2md.network.request_handler import fetch_html
from html2md.network.robots_parser import RobotsChecker
from html2md.network.rate_limiter import GlobalRateLimiter, RateLimitConfig
from html2md.network.header_manager import HeaderManager, HeaderConfig
from html2md.network.concurrent_limiter import ConcurrentLimiter, ConcurrentConfig
from html2md.utils.state_manager import StateManager
from html2md.utils.parser import (
    extract_links_from_html,
    generate_safe_filename,
    should_follow_link,
)
from html2md.utils.path_safety import contained_output_file

# Setup logger
logger = logging.getLogger("html2md")
MAX_RATE_LIMIT_RETRIES = 2


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
    concurrent_config=None,
    polite_mode=False,
    show_progress=True,
    trim=True,
    progress_callback=None,
    flatten_output=False,
    hierarchical_domains=False,
    download_images=False,
    images_dir="images",
    verify_ssl=True,
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
        trim (bool, optional): Whether to trim the markdown. Defaults to True.
        progress_callback (callable, optional): Function to call with progress updates
        flatten_output (bool, optional): If True, creates output directories directly
                                       named after domain. Defaults to False.
        hierarchical_domains (bool, optional): If True, creates hierarchical domain structure
                                              (e.g., com/jetbrains/www). Defaults to False.
        download_images (bool, optional): Whether to download images from pages.
        images_dir (str, optional): Directory name for images (default: "images").
        verify_ssl (bool, optional): Whether to verify SSL certificates. Defaults to True.
            Set to False only for trusted hosts with invalid/self-signed certificates.
        state_manager (StateManager, optional): State manager for persistence. If None, creates new one.
        resume_crawl_id (str, optional): ID of crawl to resume. If None, starts new crawl.
        enable_checkpoints (bool, optional): Whether to enable checkpointing. Defaults to True.
        checkpoint_interval (int, optional): Checkpoint interval in seconds. Defaults to 300.
        checkpoint_page_count (int, optional): Checkpoint after this many pages. Defaults to 100.

    Returns:
        CrawlResult: Typed result for successful and unsuccessful outcomes.
    """
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
            visited_urls = set(crawl_state.urls_visited.keys()) | set(crawl_state.urls_failed.keys())
            queue = deque(crawl_state.urls_queued)
            processed_urls_count = len(crawl_state.urls_visited)
        else:
            update_progress(f"Could not resume crawl {resume_crawl_id}, starting new crawl", start_url, "warning")
    
    # Create new crawl state if not resuming
    if not crawl_state:
        crawl_config = {
            "follow_option": follow_option,
            "max_depth": max_depth,
            "max_pages": max_pages,
            "delay": delay,
            "respect_robots": respect_robots,
            "rate_limit": rate_limit,
            "trim": trim,
            "flatten_output": flatten_output,
            "hierarchical_domains": hierarchical_domains,
            "download_images": download_images,
            "images_dir": images_dir,
            "verify_ssl": verify_ssl,
            "polite_mode": polite_mode,
            "enable_checkpoints": enable_checkpoints,
            "checkpoint_interval": checkpoint_interval,
            "checkpoint_page_count": checkpoint_page_count
        }
        crawl_state = state_manager.create_new_state(start_url, output_dir, crawl_config)
        url_to_file_mapping = {}
        visited_urls = set()
        queue = deque([(start_url, 0)])  # (url, depth)
        processed_urls_count = 0
        
        # Initialize queue in state
        state_manager.add_urls_to_queue([(start_url, 0)])

    failed_urls_count = 0
    retryable_attempts = defaultdict(int)
    queued_urls = {item[0] for item in queue}
    in_flight_urls = set()

    def enqueue_url(url, depth):
        """Queue nonterminal work exactly once."""
        if url in visited_urls or url in queued_urls or url in in_flight_urls:
            return False
        queue.append((url, depth))
        queued_urls.add(url)
        if enable_checkpoints:
            state_manager.current_state.urls_queued = list(queue)
        return True

    # Now update progress for resume case
    if resume_crawl_id and crawl_state:
        update_progress(f"Resuming crawl {resume_crawl_id}", start_url, "info")

    # Create session for requests (shared by robots checks, page fetches, and image downloads)
    session = get_session(verify_ssl=verify_ssl)
    
    # Initialize header manager
    header_manager = HeaderManager(header_config or HeaderConfig())
    
    # Initialize rate limiter if enabled
    rate_limiter = None
    if rate_limit and rate_limit > 0:
        config = RateLimitConfig(requests_per_minute=rate_limit)
        rate_limiter = GlobalRateLimiter(config)
        update_progress(f"Rate limiting enabled: {rate_limit} requests/minute", start_url, "info")
    
    # Initialize concurrent limiter
    concurrent_limiter = None
    if concurrent_config or polite_mode:
        # Build concurrent config
        if not concurrent_config:
            concurrent_config = ConcurrentConfig()
        
        # Apply polite mode
        if polite_mode:
            concurrent_config.polite_mode = True
            concurrent_config.polite_delay_multiplier = 2.0
            update_progress("Polite mode enabled: slower sequential request policy", start_url, "info")
        
        concurrent_limiter = ConcurrentLimiter(concurrent_config)
    else:
        # Default concurrent limiter
        concurrent_limiter = ConcurrentLimiter()
    
    # Initialize robots.txt checker if enabled
    robots_checker = None
    robots_delay = None
    if respect_robots:
        initial_headers = header_manager.get_headers(start_url)
        robots_checker = RobotsChecker(user_agent=initial_headers["User-Agent"], session=session)
        
        # Check if start URL is allowed
        if not robots_checker.can_fetch(start_url):
            update_progress(f"Starting URL is disallowed by robots.txt: {start_url}", start_url, "blocked")
            return CrawlResult(
                crawl_id=crawl_state.crawl_id if crawl_state else None,
                success=False,
                error=f"Starting URL is disallowed by robots.txt: {start_url}",
            )
        
        # Get crawl-delay from robots.txt
        robots_delay = robots_checker.get_crawl_delay(start_url)
        if robots_delay:
            update_progress(f"robots.txt specifies crawl-delay: {robots_delay}s", start_url, "info")
            # Use the larger of user-specified delay or robots.txt delay
            if robots_delay > delay:
                delay = robots_delay
                update_progress(f"Using robots.txt crawl-delay: {delay}s", start_url, "info")

    # Process URLs breadth-first up to max_depth
    while queue and processed_urls_count < max_pages:
        url, depth = queue.popleft()
        queued_urls.discard(url)

        # Skip if already visited
        if url in visited_urls:
            continue

        # Keep the active URL in persisted state until it reaches a terminal
        # outcome so a signal checkpoint can resume it.
        if enable_checkpoints:
            state_manager.current_state.urls_queued = [(url, depth), *queue]
        
        # Check robots.txt for this URL
        if robots_checker and not robots_checker.can_fetch(url):
            update_progress(f"URL disallowed by robots.txt: {url}", url, "blocked")
            visited_urls.add(url)
            if enable_checkpoints:
                state_manager.current_state.urls_queued = list(queue)
            continue

        # Process the URL
        update_progress(
            f"Processing URL {processed_urls_count+1}/{max_pages} (depth {depth}/{max_depth}): {url}",
            url,
            "processing",
        )

        slot_acquired = False
        request_start_time = None
        request_recorded = False
        try:
            # Check concurrent limits and backoff
            if not concurrent_limiter.acquire_slot(url):
                # Check if we need to wait for backoff
                wait_time = concurrent_limiter.should_wait(url)
                if wait_time:
                    update_progress(
                        f"Domain backoff, waiting {wait_time:.1f}s for {url}", 
                        url, 
                        "backoff"
                    )
                    # Skip this URL and continue with others
                    enqueue_url(url, depth)
                    continue
                else:
                    update_progress(f"Concurrent limit reached, queueing {url}", url, "queued")
                    enqueue_url(url, depth)
                    continue
            slot_acquired = True
            in_flight_urls.add(url)
            
            # Check rate limit before making request
            if rate_limiter:
                can_proceed, suggested_delay = rate_limiter.can_make_request(url)
                if not can_proceed:
                    update_progress(
                        f"Rate limited, waiting {suggested_delay:.1f}s for {url}", 
                        url, 
                        "rate_limited"
                    )
                    time.sleep(suggested_delay)
                    # Re-check after waiting
                    can_proceed, _ = rate_limiter.can_make_request(url)
                    if not can_proceed:
                        update_progress(f"Rate limit still exceeded; queueing {url}", url, "queued")
                        concurrent_limiter.release_slot(url)
                        slot_acquired = False
                        in_flight_urls.discard(url)
                        enqueue_url(url, depth)
                        continue
                elif suggested_delay > 0:
                    update_progress(
                        f"Adaptive rate limit delay: {suggested_delay:.1f}s for {url}",
                        url,
                        "rate_limited",
                    )
                    time.sleep(suggested_delay)
            
            # Record request start for rate limiting
            request_start_time = time.time()
            if rate_limiter:
                rate_limiter.record_request_start(url)
            
            # Fetch HTML content
            update_progress(f"Fetching content from {url}", url, "fetching")
            headers = header_manager.get_headers(url)
            fetch_result = fetch_html(url, session, headers)
            
            # Record request completion
            request_success = fetch_result.success
            if rate_limiter:
                rate_limiter.record_request_end(
                    url,
                    request_start_time,
                    request_success,
                    response_time=fetch_result.elapsed,
                )
                request_recorded = True
            
            # Release concurrent slot
            concurrent_limiter.release_slot(
                url,
                success=request_success,
                status_code=fetch_result.status_code,
                retry_after=fetch_result.retry_after,
            )
            slot_acquired = False

            if (
                fetch_result.status_code == 429
                and retryable_attempts[url] < MAX_RATE_LIMIT_RETRIES
            ):
                retryable_attempts[url] += 1
                update_progress(
                    f"Server rate limited {url}; queueing retry "
                    f"{retryable_attempts[url]}/{MAX_RATE_LIMIT_RETRIES}",
                    url,
                    "queued",
                )
                in_flight_urls.discard(url)
                enqueue_url(url, depth)
                if enable_checkpoints:
                    state_manager.current_state.urls_queued = list(queue)
                continue

            # The URL is terminal only after it succeeds or exhausts retry policy.
            in_flight_urls.discard(url)
            visited_urls.add(url)

            if not fetch_result.success or not fetch_result.body:
                error_message = fetch_result.error or "Failed to fetch content"
                update_progress(f"Failed to fetch content from {url}: {error_message}", url, "failed")
                failed_urls_count += 1
                if enable_checkpoints:
                    state_manager.current_state.urls_queued = list(queue)
                    state_manager.update_progress(
                        url, False, error_message=error_message
                    )
                continue

            html_content = fetch_result.body

            # Create directory structure for the URL
            url_dir = create_directory_structure(
                output_dir, url, flatten_domain=flatten_output, 
                hierarchical_domains=hierarchical_domains
            )

            # Generate a safe filename for the URL
            safe_filename = generate_safe_filename(url)
            output_file = str(contained_output_file(output_dir, url_dir, safe_filename))

            # Convert HTML to markdown
            markdown_content = html_content_to_markdown(
                html_content, fetch_result.final_url, session=session, trim=trim,
                download_images=download_images, output_dir=url_dir, images_dir=images_dir
            )

            if markdown_content:
                # Save to file
                update_progress(f"Saving markdown to {output_file}", url, "saving")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(markdown_content)

                # Only durable output files are eligible for local rewriting.
                url_to_file_mapping[url] = output_file
                update_progress(f"Saved markdown to: {output_file}", url, "saved")
                processed_urls_count += 1
                
                # Update state manager with successful processing
                if enable_checkpoints:
                    state_manager.current_state.urls_queued = list(queue)
                    state_manager.update_progress(url, True, output_file)
                
                # Apply delay with jitter if configured
                if delay > 0 and processed_urls_count < max_pages:
                    # Calculate jitter: ±30% of the base delay
                    jitter = delay * 0.3
                    actual_delay = delay + random.uniform(-jitter, jitter)
                    actual_delay = max(0.1, actual_delay)  # Ensure minimum 0.1s delay
                    
                    update_progress(
                        f"Waiting {actual_delay:.1f}s before next request...", 
                        url, 
                        "delaying"
                    )
                    time.sleep(actual_delay)

                # Extract links if we haven't reached max depth
                if depth < max_depth:
                    links = extract_links_from_html(html_content, url)
                    update_progress(
                        f"Found {len(links)} links on {url}", url, "extracting_links"
                    )

                    # Filter links according to follow_option and robots.txt
                    allowed_links = links
                    if robots_checker:
                        allowed_links = robots_checker.filter_urls(links)
                        if len(allowed_links) < len(links):
                            update_progress(
                                f"Filtered {len(links) - len(allowed_links)} links due to robots.txt",
                                url,
                                "filtered"
                            )
                    
                    for link in allowed_links:
                        if link not in visited_urls and should_follow_link(
                            link, start_url, follow_option
                        ):
                            if enqueue_url(link, depth + 1):
                                update_progress(
                                    f"Queued link (depth {depth+1}): {link}", link, "queued"
                                )

            else:
                update_progress(f"Failed to convert HTML from {url}", url, "failed")
                failed_urls_count += 1
                if enable_checkpoints:
                    state_manager.current_state.urls_queued = list(queue)
                    state_manager.update_progress(
                        url, False, error_message="Failed to convert HTML"
                    )

        except Exception as e:
            in_flight_urls.discard(url)
            visited_urls.add(url)
            failed_urls_count += 1
            # Record failed request for rate limiting
            if rate_limiter and request_start_time is not None and not request_recorded:
                rate_limiter.record_request_end(url, request_start_time, False)
            # Release concurrent slot on error
            if slot_acquired:
                concurrent_limiter.release_slot(url, success=False)
            update_progress(f"Error processing URL {url}: {str(e)}", url, "error")
            
            # Update state manager with failed processing
            if enable_checkpoints:
                state_manager.current_state.urls_queued = list(queue)
                state_manager.update_progress(url, False, error_message=str(e))

    # Rewrite links in all files to point to local files
    if processed_urls_count > 0:
        update_progress(f"Rewriting links between {len(url_to_file_mapping)} files...")

        for i, (url, output_file) in enumerate(url_to_file_mapping.items()):
            update_progress(
                f"Updating links in file {i+1}/{len(url_to_file_mapping)}: {output_file}",
                url,
                "updating",
            )

            try:
                # Read the file content
                with open(output_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # Rewrite links
                updated_content = rewrite_links(
                    content, url_to_file_mapping, output_file
                )

                # Save updated content
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(updated_content)

                update_progress(f"Updated links in file: {output_file}", url, "updated")

            except Exception as e:
                update_progress(
                    f"Error updating links in file {output_file}: {str(e)}",
                    url,
                    "error",
                )

    # Report statistics
    if rate_limiter:
        stats = rate_limiter.get_all_stats()
        for domain, domain_stats in stats.items():
            if domain_stats.total_requests > 0:
                update_progress(
                    f"Rate limit stats for {domain}: {domain_stats.total_requests} requests, "
                    f"{domain_stats.successful_requests} successful, {domain_stats.failed_requests} failed, "
                    f"{domain_stats.blocked_requests} rate-limited, circuit: {domain_stats.circuit_state.value}",
                    start_url,
                    "stats"
                )
    
    # Report concurrent limiter statistics
    concurrent_stats = concurrent_limiter.get_progress()
    if concurrent_stats['total_completed'] > 0:
        update_progress(
            f"Concurrent stats: {concurrent_stats['total_completed']} completed, "
            f"{concurrent_stats['total_errors']} errors, "
            f"{concurrent_stats['requests_per_second']:.2f} req/s",
            start_url,
            "stats"
        )
        
        # Report per-domain concurrent stats
        domain_stats = concurrent_limiter.get_all_domain_stats()
        for domain, stats in domain_stats.items():
            if stats['total_requests'] > 0:
                update_progress(
                    f"Domain {domain}: {stats['total_requests']} requests, "
                    f"{stats['total_errors']} errors ({stats['error_rate']:.1f}%), "
                    f"backoff: {'yes' if stats['in_backoff'] else 'no'}",
                    start_url,
                    "stats"
                )

    update_progress(
        f"Completed crawling. Processed {processed_urls_count} pages, visited {len(visited_urls)} URLs."
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
