import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from html2md.cookies.session_manager import get_session
from html2md.markdown.content_extractor import ContentMode, validate_content_request
from html2md.markdown.archive import (
    ArtifactManifest,
    ArtifactRecord,
    ArtifactStore,
    OutputPlanner,
    canonical_url_identity,
)
from html2md.markdown.link_rewriter import rewrite_archived_files
from html2md.markdown.pipeline import PagePipeline, acquire_http_page
from html2md.network.header_manager import HeaderManager
from html2md.utils.parser import get_urls_from_file
from html2md.utils.path_safety import contained_path, safe_path_segment

# Setup logger
logger = logging.getLogger("html2md")


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

    @property
    def processed_count(self) -> int:
        return sum(item.success for item in self.items)

    @property
    def failed_count(self) -> int:
        return sum(not item.success for item in self.items)

    @property
    def success(self) -> bool:
        return bool(self.items) and self.failed_count == 0 and self.error is None


def create_directory_structure(
    output_dir, url, flatten_domain=False, flatten_all=False, hierarchical_domains=False
):
    """
    Create a directory structure based on the URL's domain.

    Args:
        output_dir (str): Base output directory
        url (str): URL to create structure for
        flatten_domain (bool, optional): If True, uses the domain name directly as output directory
                                         instead of creating a subdirectory structure. Defaults to False.
        flatten_all (bool, optional): If True, returns the output_dir directly without creating
                                     any domain-based subdirectories. Defaults to False.
        hierarchical_domains (bool, optional): If True, creates hierarchical domain structure
                                              (e.g., com/jetbrains/www). Defaults to False.

    Returns:
        str: Path to the directory where the file should be saved
    """
    output_root = Path(output_dir).expanduser().resolve()
    parsed_url = urlparse(url)
    domain = safe_path_segment(parsed_url.netloc)

    if flatten_all:
        domain_dir = output_root
    elif hierarchical_domains:
        # Split domain into parts and reverse them
        # e.g., www.jetbrains.com -> ['com', 'jetbrains', 'www']
        domain_parts = [safe_path_segment(part) for part in domain.split(".")]
        domain_parts.reverse()

        # Build hierarchical path
        domain_dir = output_root
        for part in domain_parts:
            domain_dir = os.path.join(domain_dir, part)
    elif flatten_domain:
        # Just use the domain as the output directory
        domain_dir = output_root / domain
    else:
        # Create domain directory as a subdirectory
        domain_dir = output_root / domain

        # Create path directories if they exist
        path_parts = [
            safe_path_segment(part) for part in parsed_url.path.strip("/").split("/")
        ]
        if path_parts and path_parts[0]:
            # If there are path components, create directories for them
            for i in range(len(path_parts) - 1):  # Exclude the last part (filename)
                if path_parts[i]:
                    domain_dir = Path(domain_dir) / path_parts[i]

    # Create the directories if they don't exist
    domain_dir = contained_path(output_root, domain_dir)
    domain_dir.mkdir(parents=True, exist_ok=True)

    return str(domain_dir)


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

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # URL to local file mapping for link rewriting
    url_to_file_mapping = {}
    item_results = []
    manifest = ArtifactManifest()
    planner = OutputPlanner(
        output_dir,
        flatten_domain=flatten_output,
        flatten_all=flatten_all,
        hierarchical_domains=hierarchical_domains,
    )
    discovered_identities = set()
    header_manager = header_manager or HeaderManager()
    page_pipeline = page_pipeline or PagePipeline()

    # Helper function to update progress
    def update_progress(message, url=None, status=None):
        logger.info(message)
        if progress_callback:
            progress_callback(message, url, status)

    # First pass: Process all URLs and build the mapping
    for source_file in source_files:
        update_progress(f"Processing links in file: {source_file}")

        # Extract URLs from the source file
        urls = get_urls_from_file(source_file)
        if not urls:
            update_progress(f"No URLs found in file: {source_file}", status="warning")
            update_progress(
                "This file may contain URLs in a format that's not being detected.",
                status="info",
            )
            update_progress(
                "Supported formats: Markdown links, plain URLs, and HTML links.",
                status="info",
            )
            continue

        update_progress(f"Found {len(urls)} URLs in {source_file}")

        # Log all found URLs for visibility
        update_progress("URLs to process:", status="info")
        for i, url in enumerate(urls, 1):
            update_progress(f"  {i}. {url}", status="info")

        # Process each URL
        for index, url in enumerate(urls):
            # Skip if already processed
            identity = canonical_url_identity(url)
            if identity in discovered_identities:
                update_progress(
                    f"Skipping already processed URL: {url}", url, "skipped"
                )
                continue
            discovered_identities.add(identity)

            # Update progress
            update_progress(
                f"Processing URL {index+1}/{len(urls)}: {url}", url, "processing"
            )

            try:
                # Create session for the URL
                update_progress(f"Fetching content from {url}", url, "fetching")
                session = get_session(verify_ssl=verify_ssl)
                headers = header_manager.get_headers(url)

                try:
                    page = acquire_http_page(
                        url,
                        session=session,
                        headers=headers,
                        allow_private_network=allow_private_network,
                    )
                    existing = manifest.resolve(page.final_url)
                    if existing is not None:
                        manifest.register_alias(url, existing)
                        output_file = str(existing.output_path)
                        url_to_file_mapping[url] = output_file
                        item_results.append(
                            BatchItemResult(url, output_file=output_file)
                        )
                        update_progress(
                            f"Reused archived redirect target: {output_file}",
                            url,
                            "skipped",
                        )
                        continue
                    output_path = planner.plan(page.final_url)
                    document = page_pipeline.convert(
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
                    markdown_content = document.markdown
                finally:
                    session.close()

                if markdown_content:
                    # Save to file
                    canonical_url = document.metadata.canonical_url
                    existing = (
                        manifest.resolve(canonical_url) if canonical_url else None
                    )
                    if existing is not None:
                        manifest.register_alias(url, existing)
                        manifest.register_alias(page.final_url, existing)
                        output_path = existing.output_path
                    else:
                        ArtifactStore.write_text(output_path, markdown_content)
                        manifest.register(
                            ArtifactRecord(
                                requested_url=url,
                                final_url=page.final_url,
                                canonical_url=canonical_url,
                                output_path=output_path,
                            )
                        )
                    output_file = str(output_path)

                    # Only durable output files are eligible for local rewriting.
                    url_to_file_mapping[url] = output_file
                    item_results.append(BatchItemResult(url, output_file=output_file))
                    update_progress(f"Saved markdown to: {output_file}", url, "saved")
                else:
                    item_results.append(
                        BatchItemResult(
                            url, error="Conversion returned no Markdown content"
                        )
                    )
                    update_progress(f"Failed to process URL: {url}", url, "failed")

            except Exception as e:
                item_results.append(BatchItemResult(url, error=str(e)))
                update_progress(f"Error processing URL {url}: {str(e)}", url, "error")

    # Second pass: Rewrite links in all files to point to local files.
    rewrite_archived_files(manifest, update_progress)

    processed_count = sum(item.success for item in item_results)
    update_progress(f"Completed processing {processed_count} URLs")
    error = None if item_results else "No URLs were found in the batch inputs"
    return BatchResult(
        item_results, url_to_file_mapping, error=error, manifest=manifest
    )
