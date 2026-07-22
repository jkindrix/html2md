"""Deliberately sequential crawl orchestration over injected collaborators."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, MutableMapping, Optional

import requests

from grab2md.markdown.archive import (
    ArtifactManifest,
    ArtifactStore,
    OutputPlanner,
    canonical_url_identity,
)
from grab2md.markdown.archiving import ArchiveCoordinator
from grab2md.markdown.content_extractor import ContentMode
from grab2md.markdown.link_rewriter import rewrite_archived_files
from grab2md.markdown.pipeline import AcquiredPage, PagePipeline, acquired_http_page
from grab2md.network.header_manager import HeaderManager
from grab2md.network.request_handler import FetchResult
from grab2md.network.request_scheduler import SequentialRequestScheduler
from grab2md.network.robots_parser import RobotsChecker
from grab2md.network.safe_http import DestinationPolicy, UnsafeNetworkTarget
from grab2md.utils.parser import extract_links_from_html, should_follow_link
from grab2md.utils.crawl_policy import FollowRule, compile_follow_option
from grab2md.utils.state_manager import StateManager

MAX_RATE_LIMIT_RETRIES = 2
ProgressSink = Callable[[str, Optional[str], Optional[str]], None]
FetchPage = Callable[..., FetchResult]


@dataclass(frozen=True)
class FrontierItem:
    url: str
    depth: int


class CrawlFrontier:
    """Breadth-first work queue with explicit queued, active, and terminal states."""

    def __init__(
        self,
        items: Iterable[tuple[str, int]],
        *,
        terminal_urls: Iterable[str] = (),
        retry_attempts: Mapping[str, int] | None = None,
    ) -> None:
        self._queue: deque[FrontierItem] = deque()
        self._queued: set[str] = set()
        self._active: set[str] = set()
        self._terminal = {canonical_url_identity(url) for url in terminal_urls}
        self._retryable_attempts: dict[str, int] = defaultdict(int)
        for url, count in (retry_attempts or {}).items():
            identity = canonical_url_identity(url)
            self._retryable_attempts[identity] = max(
                self._retryable_attempts[identity], count
            )
        for url, depth in items:
            self.enqueue(url, depth)

    def __bool__(self) -> bool:
        return bool(self._queue)

    @property
    def terminal_count(self) -> int:
        return len(self._terminal)

    @property
    def retry_attempts(self) -> dict[str, int]:
        return dict(self._retryable_attempts)

    def pop(self) -> Optional[FrontierItem]:
        while self._queue:
            item = self._queue.popleft()
            identity = canonical_url_identity(item.url)
            self._queued.discard(identity)
            if identity not in self._terminal:
                self._active.add(identity)
                return item
        return None

    def enqueue(self, url: str, depth: int) -> bool:
        identity = canonical_url_identity(url)
        if (
            identity in self._terminal
            or identity in self._queued
            or identity in self._active
        ):
            return False
        self._queue.append(FrontierItem(url, depth))
        self._queued.add(identity)
        return True

    def retry(self, item: FrontierItem) -> int:
        identity = canonical_url_identity(item.url)
        self._retryable_attempts[identity] += 1
        self._active.discard(identity)
        self.enqueue(item.url, item.depth)
        return self._retryable_attempts[identity]

    def can_retry(self, url: str) -> bool:
        return (
            self._retryable_attempts[canonical_url_identity(url)]
            < MAX_RATE_LIMIT_RETRIES
        )

    def finish(self, url: str) -> None:
        identity = canonical_url_identity(url)
        self._active.discard(identity)
        self._terminal.add(identity)
        self._retryable_attempts.pop(identity, None)

    def snapshot(self, active: Optional[FrontierItem] = None) -> list[tuple[str, int]]:
        queued = [(item.url, item.depth) for item in self._queue]
        return ([(active.url, active.depth)] if active else []) + queued


@dataclass
class CrawlScope:
    root_url: str
    follow_option: str
    _follow_rule: FollowRule = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._follow_rule = compile_follow_option(self.follow_option)

    def allows(self, url: str) -> bool:
        return should_follow_link(url, self.root_url, self._follow_rule)


class CrawlCheckpointStore:
    """Adapter isolating crawl orchestration from the state-manager schema."""

    def __init__(self, state_manager: StateManager, *, enabled: bool) -> None:
        self.state_manager = state_manager
        self.enabled = enabled

    def sync(
        self,
        frontier: CrawlFrontier,
        active: Optional[FrontierItem] = None,
        *,
        attempted_count: int | None = None,
    ) -> None:
        state = self.state_manager.current_state
        if self.enabled and state is not None:
            state.urls_queued = frontier.snapshot(active)
            state.retry_attempts = frontier.retry_attempts
            if attempted_count is not None:
                state.attempted_count = attempted_count

    def succeeded(self, url: str, output_file: str, frontier: CrawlFrontier) -> None:
        if self.enabled:
            self.sync(frontier)
            self.state_manager.update_progress(url, True, output_file)

    def failed(self, url: str, error: str, frontier: CrawlFrontier) -> None:
        if self.enabled:
            self.sync(frontier)
            self.state_manager.update_progress(url, False, error_message=error)

    def set_scope(self, scope_url: str) -> None:
        if self.enabled and self.state_manager.current_state is not None:
            self.state_manager.current_state.config["scope_url"] = scope_url


@dataclass(frozen=True)
class CrawlOptions:
    max_depth: int
    max_pages: int
    content_mode: ContentMode
    selector: Optional[str]
    download_images: bool
    images_dir: str
    include_metadata: bool
    allow_private_network: bool


@dataclass(frozen=True)
class CrawlRun:
    processed_count: int
    failed_count: int
    terminal_count: int
    attempted_count: int


class SequentialCrawlEngine:
    """Coordinate crawl policy without implementing any collaborator's work."""

    def __init__(
        self,
        *,
        frontier: CrawlFrontier,
        scope: CrawlScope,
        robots: RobotsChecker | None,
        scheduler: SequentialRequestScheduler,
        page_pipeline: PagePipeline,
        artifact_store: type[ArtifactStore],
        checkpoint_store: CrawlCheckpointStore,
        event_sink: ProgressSink,
        session: requests.Session,
        network_policy: DestinationPolicy,
        header_manager: HeaderManager,
        manifest: ArtifactManifest,
        output_planner: OutputPlanner,
        url_mapping: MutableMapping[str, str],
        fetch_page: FetchPage,
        options: CrawlOptions,
        initial_processed: int = 0,
        initial_attempted: int = 0,
    ) -> None:
        self.frontier = frontier
        self.scope = scope
        self.robots = robots
        self.scheduler = scheduler
        self.page_pipeline = page_pipeline
        self.checkpoints = checkpoint_store
        self.emit = event_sink
        self.session = session
        self.network_policy = network_policy
        self.header_manager = header_manager
        self.manifest = manifest
        self.archiver = ArchiveCoordinator(
            manifest=manifest,
            planner=output_planner,
            write_text=artifact_store.write_text,
        )
        self.url_mapping = url_mapping
        self.fetch_page = fetch_page
        self.options = options
        self.processed_count = initial_processed
        self.failed_count = 0
        # Terminal URLs were already attempted in a previous resumable run.
        # Count every new dequeue, including failures and explicit retries, so
        # max_pages is a hard page-attempt budget instead of a success target.
        self.attempted_count = max(initial_attempted, frontier.terminal_count)

    def _redirect_validator(self, item: FrontierItem) -> Callable[[str, str], None]:
        starting_navigation = item.url == self.scope.root_url and item.depth == 0

        def validate(_source_url: str, target_url: str) -> None:
            if not starting_navigation and not self.scope.allows(target_url):
                raise UnsafeNetworkTarget(
                    f"Crawl redirect leaves the configured scope: {target_url}"
                )
            if self.robots and not self.robots.can_fetch(target_url):
                raise UnsafeNetworkTarget(
                    f"Crawl redirect is disallowed by robots.txt: {target_url}"
                )

        return validate

    def _fetch(self, item: FrontierItem) -> FetchResult:
        self.emit(f"Fetching content from {item.url}", item.url, "fetching")
        return self.fetch_page(
            item.url,
            self.session,
            self.header_manager.get_headers(item.url),
            network_policy=self.network_policy,
            redirect_validator=self._redirect_validator(item),
            request_scheduler=self.scheduler,
        )

    @staticmethod
    def _acquired_page(item: FrontierItem, result: FetchResult) -> AcquiredPage:
        if result.status_code is None:
            raise RuntimeError("Successful fetch result is missing an HTTP status")
        content = result.content
        if content is None:
            content = (result.body or "").encode("utf-8")
        return acquired_http_page(
            requested_url=item.url,
            final_url=result.final_url,
            status_code=result.status_code,
            headers=result.headers,
            content=content,
        )

    def _persist(self, item: FrontierItem, page: AcquiredPage) -> str:
        def convert(output_path):
            return self.page_pipeline.convert(
                page,
                content_mode=self.options.content_mode,
                selector=self.options.selector,
                download_images=self.options.download_images,
                output_dir=output_path.parent,
                images_dir=self.options.images_dir,
                include_metadata=self.options.include_metadata,
                session=self.session,
                allow_private_network=self.options.allow_private_network,
                request_scheduler=self.scheduler,
            )

        return str(self.archiver.archive(item.url, page, convert).output_path)

    def _discover(self, item: FrontierItem, page: AcquiredPage) -> list[str]:
        """Return allowed links without mutating the frontier."""
        if item.depth >= self.options.max_depth:
            return []
        links = extract_links_from_html(page.html, page.final_url)
        self.emit(
            f"Found {len(links)} links on {item.url}",
            item.url,
            "extracting_links",
        )
        allowed = [link for link in links if self.scope.allows(link)]
        if self.robots:
            scoped_count = len(allowed)
            allowed = self.robots.filter_urls(allowed)
            if len(allowed) < scoped_count:
                self.emit(
                    f"Filtered {scoped_count - len(allowed)} links due to robots.txt",
                    item.url,
                    "filtered",
                )
        return allowed

    def _enqueue_discovered(self, item: FrontierItem, links: Iterable[str]) -> None:
        """Commit already-parsed discovery results to the frontier."""
        for link in links:
            if self.frontier.enqueue(link, item.depth + 1):
                self.emit(
                    f"Queued link (depth {item.depth + 1}): {link}",
                    link,
                    "queued",
                )

    def _process(self, item: FrontierItem) -> None:
        if self.robots and not self.robots.can_fetch(item.url):
            self.emit(f"URL disallowed by robots.txt: {item.url}", item.url, "blocked")
            self.frontier.finish(item.url)
            self.checkpoints.sync(self.frontier)
            return

        self.emit(
            f"Processing page attempt {self.attempted_count}/{self.options.max_pages} "
            f"(depth {item.depth}/{self.options.max_depth}): {item.url}",
            item.url,
            "processing",
        )
        result = self._fetch(item)
        if result.status_code == 429 and self.frontier.can_retry(item.url):
            attempt = self.frontier.retry(item)
            self.emit(
                f"Server rate limited {item.url}; queueing retry "
                f"{attempt}/{MAX_RATE_LIMIT_RETRIES}",
                item.url,
                "queued",
            )
            self.checkpoints.sync(self.frontier)
            return

        if not result.success:
            error = result.error or "Failed to fetch content"
            self.emit(
                f"Failed to fetch content from {item.url}: {error}",
                item.url,
                "failed",
            )
            self.frontier.finish(item.url)
            self.failed_count += 1
            self.checkpoints.failed(item.url, error, self.frontier)
            return

        if item.depth == 0 and item.url == self.scope.root_url:
            self.scope.root_url = result.final_url

        page = self._acquired_page(item, result)
        discovered = self._discover(item, page)
        output_file = self._persist(item, page)
        self._enqueue_discovered(item, discovered)
        self.frontier.finish(item.url)
        self.url_mapping[item.url] = output_file
        self.emit(f"Saved markdown to: {output_file}", item.url, "saved")
        self.processed_count += 1
        if item.depth == 0:
            self.checkpoints.set_scope(self.scope.root_url)
        self.checkpoints.succeeded(item.url, output_file, self.frontier)

    def run(self) -> CrawlRun:
        while self.frontier and self.attempted_count < self.options.max_pages:
            item = self.frontier.pop()
            if item is None:
                break
            self.attempted_count += 1
            self.checkpoints.sync(
                self.frontier, item, attempted_count=self.attempted_count
            )
            try:
                self._process(item)
            except Exception as error:
                self.frontier.finish(item.url)
                self.failed_count += 1
                self.emit(
                    f"Error processing URL {item.url}: {error}", item.url, "error"
                )
                self.checkpoints.failed(item.url, str(error), self.frontier)

        if self.processed_count > 0:
            rewrite_archived_files(self.manifest, self.emit)
        return CrawlRun(
            self.processed_count,
            self.failed_count,
            self.frontier.terminal_count,
            self.attempted_count,
        )
