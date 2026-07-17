"""Deliberately sequential crawl orchestration over injected collaborators."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable, Iterable, MutableMapping, Optional

from html2md.markdown.archive import (
    ArtifactManifest,
    ArtifactRecord,
    ArtifactStore,
    OutputPlanner,
)
from html2md.markdown.content_extractor import ContentMode
from html2md.markdown.link_rewriter import rewrite_archived_files
from html2md.markdown.pipeline import AcquiredPage, PagePipeline
from html2md.network.request_handler import FetchResult
from html2md.network.safe_http import UnsafeNetworkTarget
from html2md.utils.parser import extract_links_from_html, should_follow_link


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
    ) -> None:
        self._queue = deque(FrontierItem(url, depth) for url, depth in items)
        self._queued = {item.url for item in self._queue}
        self._active: set[str] = set()
        self._terminal = set(terminal_urls)
        self._retryable_attempts: dict[str, int] = defaultdict(int)

    def __bool__(self) -> bool:
        return bool(self._queue)

    @property
    def terminal_count(self) -> int:
        return len(self._terminal)

    def pop(self) -> Optional[FrontierItem]:
        while self._queue:
            item = self._queue.popleft()
            self._queued.discard(item.url)
            if item.url not in self._terminal:
                self._active.add(item.url)
                return item
        return None

    def enqueue(self, url: str, depth: int) -> bool:
        if url in self._terminal or url in self._queued or url in self._active:
            return False
        self._queue.append(FrontierItem(url, depth))
        self._queued.add(url)
        return True

    def retry(self, item: FrontierItem) -> int:
        self._retryable_attempts[item.url] += 1
        self._active.discard(item.url)
        self.enqueue(item.url, item.depth)
        return self._retryable_attempts[item.url]

    def can_retry(self, url: str) -> bool:
        return self._retryable_attempts[url] < MAX_RATE_LIMIT_RETRIES

    def finish(self, url: str) -> None:
        self._active.discard(url)
        self._terminal.add(url)

    def snapshot(self, active: Optional[FrontierItem] = None) -> list[tuple[str, int]]:
        queued = [(item.url, item.depth) for item in self._queue]
        return ([(active.url, active.depth)] if active else []) + queued


@dataclass
class CrawlScope:
    root_url: str
    follow_option: str

    def allows(self, url: str) -> bool:
        return should_follow_link(url, self.root_url, self.follow_option)


class CrawlCheckpointStore:
    """Adapter isolating crawl orchestration from the state-manager schema."""

    def __init__(self, state_manager: Any, *, enabled: bool) -> None:
        self.state_manager = state_manager
        self.enabled = enabled

    def sync(self, frontier: CrawlFrontier, active: Optional[FrontierItem] = None) -> None:
        if self.enabled:
            self.state_manager.current_state.urls_queued = frontier.snapshot(active)

    def succeeded(self, url: str, output_file: str, frontier: CrawlFrontier) -> None:
        if self.enabled:
            self.sync(frontier)
            self.state_manager.update_progress(url, True, output_file)

    def failed(self, url: str, error: str, frontier: CrawlFrontier) -> None:
        if self.enabled:
            self.sync(frontier)
            self.state_manager.update_progress(url, False, error_message=error)

    def set_scope(self, scope_url: str) -> None:
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


class SequentialCrawlEngine:
    """Coordinate crawl policy without implementing any collaborator's work."""

    def __init__(
        self,
        *,
        frontier: CrawlFrontier,
        scope: CrawlScope,
        robots: Any,
        scheduler: Any,
        page_pipeline: PagePipeline,
        artifact_store: Any,
        checkpoint_store: CrawlCheckpointStore,
        event_sink: ProgressSink,
        session: Any,
        network_policy: Any,
        header_manager: Any,
        manifest: ArtifactManifest,
        output_planner: OutputPlanner,
        url_mapping: MutableMapping[str, str],
        fetch_page: FetchPage,
        options: CrawlOptions,
        initial_processed: int = 0,
    ) -> None:
        self.frontier = frontier
        self.scope = scope
        self.robots = robots
        self.scheduler = scheduler
        self.page_pipeline = page_pipeline
        self.artifact_store = artifact_store
        self.checkpoints = checkpoint_store
        self.emit = event_sink
        self.session = session
        self.network_policy = network_policy
        self.header_manager = header_manager
        self.manifest = manifest
        self.output_planner = output_planner
        self.url_mapping = url_mapping
        self.fetch_page = fetch_page
        self.options = options
        self.processed_count = initial_processed
        self.failed_count = 0

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

    def _persist(self, item: FrontierItem, result: FetchResult) -> str:
        existing = self.manifest.resolve(result.final_url)
        if existing is not None:
            self.manifest.register_alias(item.url, existing)
            return str(existing.output_path)

        output_path = self.output_planner.plan(result.final_url)
        page = AcquiredPage(
            requested_url=item.url,
            final_url=result.final_url,
            html=result.body or "",
            status_code=result.status_code,
            headers=result.headers,
            media_type="text/html",
            charset="utf-8",
        )
        document = self.page_pipeline.convert(
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
        canonical_url = document.metadata.canonical_url
        canonical_record = (
            self.manifest.resolve(canonical_url) if canonical_url else None
        )
        if canonical_record is not None:
            self.manifest.register_alias(item.url, canonical_record)
            self.manifest.register_alias(result.final_url, canonical_record)
            return str(canonical_record.output_path)

        self.artifact_store.write_text(output_path, document.markdown)
        self.manifest.register(
            ArtifactRecord(item.url, result.final_url, canonical_url, output_path)
        )
        return str(output_path)

    def _discover(self, item: FrontierItem, result: FetchResult) -> None:
        if item.depth >= self.options.max_depth:
            return
        links = extract_links_from_html(result.body or "", result.final_url)
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
        for link in allowed:
            if self.frontier.enqueue(link, item.depth + 1):
                self.emit(
                    f"Queued link (depth {item.depth + 1}): {link}",
                    link,
                    "queued",
                )

    def _process(self, item: FrontierItem) -> None:
        if self.robots and not self.robots.can_fetch(item.url):
            self.emit(
                f"URL disallowed by robots.txt: {item.url}", item.url, "blocked"
            )
            self.frontier.finish(item.url)
            self.checkpoints.sync(self.frontier)
            return

        self.emit(
            f"Processing URL {self.processed_count + 1}/{self.options.max_pages} "
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

        self.frontier.finish(item.url)
        if not result.success or not result.body:
            error = result.error or "Failed to fetch content"
            self.emit(
                f"Failed to fetch content from {item.url}: {error}",
                item.url,
                "failed",
            )
            self.failed_count += 1
            self.checkpoints.failed(item.url, error, self.frontier)
            return

        if item.depth == 0 and item.url == self.scope.root_url:
            self.scope.root_url = result.final_url
            self.checkpoints.set_scope(result.final_url)

        output_file = self._persist(item, result)
        self.url_mapping[item.url] = output_file
        self.emit(f"Saved markdown to: {output_file}", item.url, "saved")
        self.processed_count += 1
        self.checkpoints.succeeded(item.url, output_file, self.frontier)
        self._discover(item, result)
        self.checkpoints.sync(self.frontier)

    def run(self) -> CrawlRun:
        while self.frontier and self.processed_count < self.options.max_pages:
            item = self.frontier.pop()
            if item is None:
                break
            self.checkpoints.sync(self.frontier, item)
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
        )

