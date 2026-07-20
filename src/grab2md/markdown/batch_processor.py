from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from grab2md.cookies.session_manager import get_session
from grab2md.markdown.content_extractor import ContentMode, validate_content_request
from grab2md.markdown.archive import (
    ArtifactManifest,
    ArtifactStore,
    OutputPlanner,
    canonical_url_identity,
)
from grab2md.markdown.archiving import ArchiveCoordinator
from grab2md.markdown.link_rewriter import rewrite_archived_files
from grab2md.markdown.pipeline import PagePipeline, acquire_http_page
from grab2md.network.header_manager import HeaderManager
from grab2md.utils.parser import extract_urls_from_markdown
from grab2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger(__name__)


@dataclass(frozen=True)
class BatchItemResult:
    """Outcome for one unique URL discovered by a batch input."""

    url: str
    output_file: str | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.output_file is not None and self.error is None


@dataclass
class BatchResult:
    """Typed aggregate result for batch orchestration and presentation."""

    items: list[BatchItemResult] = field(default_factory=list)
    url_mapping: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    manifest: ArtifactManifest | None = None
    input_errors: list[str] = field(default_factory=list)

    @property
    def processed_count(self) -> int:
        return sum(item.success for item in self.items)

    @property
    def failed_count(self) -> int:
        return sum(not item.success for item in self.items)

    @property
    def success(self) -> bool:
        return (
            bool(self.items)
            and self.failed_count == 0
            and not self.input_errors
            and self.error is None
        )


class BatchInputError(ValueError):
    """A batch source could not be read as a UTF-8 text document."""


@dataclass(frozen=True)
class BatchInput:
    path: Path
    urls: tuple[str, ...]


ProgressCallback = Callable[[str, str | None, str | None], None]


def load_batch_input(source_file: str | Path) -> BatchInput:
    """Load one input, distinguishing an unreadable file from an empty one."""
    path = Path(source_file).expanduser()
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise BatchInputError(f"Could not read batch input {path}: {error}") from error
    return BatchInput(path, tuple(extract_urls_from_markdown(content)))


def discover_batch_urls(inputs: Iterable[BatchInput]) -> list[str]:
    """Return canonical-identity-deduplicated URLs in source order."""
    discovered: list[str] = []
    identities: set[str] = set()
    for batch_input in inputs:
        for url in batch_input.urls:
            identity = canonical_url_identity(url)
            if identity not in identities:
                identities.add(identity)
                discovered.append(url)
    return discovered


def _archive_batch_url(
    url: str,
    *,
    content_mode: ContentMode,
    selector: str | None,
    download_images: bool,
    images_dir: str,
    verify_ssl: bool,
    include_metadata: bool,
    allow_private_network: bool,
    header_manager: HeaderManager,
    page_pipeline: PagePipeline,
    planner: OutputPlanner,
    manifest: ArtifactManifest,
    progress: ProgressCallback,
) -> BatchItemResult:
    """Convert one URL and register only its durable output."""
    progress(f"Fetching content from {url}", url, "fetching")
    session = get_session(verify_ssl=verify_ssl)
    try:
        page = acquire_http_page(
            url,
            session=session,
            headers=header_manager.get_headers(url),
            allow_private_network=allow_private_network,
        )
        archiver = ArchiveCoordinator(
            manifest=manifest,
            planner=planner,
            write_text=ArtifactStore.write_text,
        )

        def convert(output_path: Path):
            return page_pipeline.convert(
                page,
                content_mode=content_mode,
                selector=selector,
                download_images=download_images,
                output_dir=output_path.parent,
                images_dir=images_dir,
                include_metadata=include_metadata,
                session=session,
                allow_private_network=allow_private_network,
            )

        outcome = archiver.archive(url, page, convert)
    finally:
        session.close()

    output_file = str(outcome.output_path)
    if outcome.reused:
        progress(f"Reused archived target: {output_file}", url, "skipped")
    else:
        progress(f"Saved markdown to: {output_file}", url, "saved")
    return BatchItemResult(url, output_file=output_file)


def process_markdown_links(
    source_files,
    output_dir,
    content_mode=ContentMode.FULL,
    selector=None,
    progress_callback=None,
    flatten_output=False,
    flatten_all=False,
    hierarchical_domains=False,
    download_images=False,
    images_dir="images",
    verify_ssl=True,
    include_metadata=False,
    allow_private_network=False,
    header_manager=None,
    page_pipeline=None,
):
    """
    Process markdown files, extract URLs, and convert each URL to markdown.

    Args:
        source_files (list): List of markdown files to process
        output_dir (str): Directory to save the output files
        content_mode: Full document, inferred main content, or explicit selector.
        selector: CSS selector required by selector mode.
        progress_callback (callable, optional): Function to call with progress updates
        flatten_output (bool, optional): If True, creates output directories directly
                                        named after domain. Defaults to False.
        flatten_all (bool, optional): If True, outputs all files to a single directory,
                                     ignoring domain structure. Defaults to False.
        hierarchical_domains (bool, optional): If True, creates hierarchical domain structure
                                              (e.g., com/jetbrains/www). Defaults to False.
        download_images (bool, optional): Whether to download images from pages.
        images_dir (str, optional): Directory name for images (default: "images").
        verify_ssl (bool, optional): Whether to verify SSL certificates. Defaults to True.
            Set to False only for trusted hosts with invalid/self-signed certificates.
        include_metadata (bool, optional): Prepend YAML front matter to each output.

    Returns:
        BatchResult: Per-URL outcomes and durable URL-to-file mappings.
    """
    content_mode = validate_content_request(content_mode, selector)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    def update_progress(
        message: str, url: str | None = None, status: str | None = None
    ) -> None:
        logger.info(message)
        if progress_callback:
            progress_callback(message, url, status)

    inputs: list[BatchInput] = []
    input_errors: list[str] = []
    for source_file in source_files:
        update_progress(f"Processing links in file: {source_file}")
        try:
            batch_input = load_batch_input(source_file)
        except BatchInputError as error:
            input_errors.append(str(error))
            update_progress(str(error), status="error")
            continue
        inputs.append(batch_input)
        if batch_input.urls:
            update_progress(f"Found {len(batch_input.urls)} URLs in {source_file}")
        else:
            update_progress(f"No URLs found in file: {source_file}", status="warning")

    urls = discover_batch_urls(inputs)
    manifest = ArtifactManifest()
    planner = OutputPlanner(
        output_dir,
        flatten_domain=flatten_output,
        flatten_all=flatten_all,
        hierarchical_domains=hierarchical_domains,
    )
    active_headers = header_manager or HeaderManager()
    active_pipeline = page_pipeline or PagePipeline()
    item_results: list[BatchItemResult] = []
    url_to_file_mapping: dict[str, str] = {}

    for index, url in enumerate(urls, 1):
        update_progress(f"Processing URL {index}/{len(urls)}: {url}", url, "processing")
        try:
            item = _archive_batch_url(
                url,
                content_mode=content_mode,
                selector=selector,
                download_images=download_images,
                images_dir=images_dir,
                verify_ssl=verify_ssl,
                include_metadata=include_metadata,
                allow_private_network=allow_private_network,
                header_manager=active_headers,
                page_pipeline=active_pipeline,
                planner=planner,
                manifest=manifest,
                progress=update_progress,
            )
        except Exception as failure:
            item = BatchItemResult(url, error=str(failure))
            update_progress(f"Error processing URL {url}: {failure}", url, "error")
        item_results.append(item)
        if item.success and item.output_file is not None:
            url_to_file_mapping[url] = item.output_file

    rewrite_archived_files(manifest, update_progress)
    processed_count = sum(item.success for item in item_results)
    update_progress(f"Completed processing {processed_count} URLs")
    result_error = "; ".join(input_errors) if input_errors else None
    if not item_results and result_error is None:
        result_error = "No URLs were found in the batch inputs"
    return BatchResult(
        items=item_results,
        url_mapping=url_to_file_mapping,
        error=result_error,
        manifest=manifest,
        input_errors=input_errors,
    )
