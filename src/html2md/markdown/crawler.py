import logging
import os
import re
from collections import deque
from urllib.parse import urlparse

from html2md.cookies.session_manager import get_session
from html2md.markdown.converter import html_to_markdown
from html2md.network.request_handler import fetch_html
from html2md.utils.parser import (
    extract_links_from_html,
    generate_safe_filename,
    should_follow_link,
)

# Setup logger
logger = logging.getLogger("html2md")


def build_headers(url):
    """Dynamically construct request headers based on the target URL."""
    parsed_url = urlparse(url)
    domain = parsed_url.netloc

    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://{domain}/",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }


def rewrite_links(content, url_mapping, base_output_dir):
    """
    Rewrite links in markdown content to point to local files.

    Args:
        content (str): Markdown content to process
        url_mapping (dict): Mapping from URLs to local file paths
        base_output_dir (str): Base output directory

    Returns:
        str: Markdown content with rewritten links
    """
    for url, local_path in url_mapping.items():
        # Create relative path from base_output_dir
        relative_path = os.path.relpath(local_path, base_output_dir)

        # Replace the URL with the relative path in markdown links
        pattern = rf"\[(.*?)\]\({re.escape(url)}\)"
        replacement = rf"[\1]({relative_path})"
        content = re.sub(pattern, replacement, content)

    return content


def crawl_website(
    start_url,
    output_dir,
    follow_option="domain-only",
    max_depth=3,
    max_pages=100,
    trim=True,
    progress_callback=None,
    flatten_output=False,
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
        trim (bool, optional): Whether to trim the markdown. Defaults to True.
        progress_callback (callable, optional): Function to call with progress updates
        flatten_output (bool, optional): If True, creates output directories directly
                                       named after domain. Defaults to False.

    Returns:
        tuple: (processed_urls_count, url_to_file_mapping)
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # URL to local file mapping for link rewriting
    url_to_file_mapping = {}
    visited_urls = set()
    queue = deque([(start_url, 0)])  # (url, depth)
    processed_urls_count = 0

    # Helper function to update progress
    def update_progress(message, url=None, status=None):
        logger.info(message)
        if progress_callback:
            progress_callback(message, url, status)

    # Create session for requests
    session = get_session()

    # Process URLs breadth-first up to max_depth
    while queue and processed_urls_count < max_pages:
        url, depth = queue.popleft()

        # Skip if already visited
        if url in visited_urls:
            continue

        # Mark as visited
        visited_urls.add(url)

        # Process the URL
        update_progress(
            f"Processing URL {processed_urls_count+1}/{max_pages} (depth {depth}/{max_depth}): {url}",
            url,
            "processing",
        )

        try:
            # Fetch HTML content
            update_progress(f"Fetching content from {url}", url, "fetching")
            headers = build_headers(url)
            html_content = fetch_html(url, session, headers)

            if not html_content:
                update_progress(f"Failed to fetch content from {url}", url, "failed")
                continue

            # Create directory structure for the URL
            parsed_url = urlparse(url)
            domain = parsed_url.netloc

            if flatten_output:
                # Just use the domain as the output directory
                url_dir = os.path.join(output_dir, domain)
            else:
                # Create domain directory as a subdirectory
                url_dir = os.path.join(output_dir, domain)

                # Create path directories if they exist
                path_parts = parsed_url.path.strip("/").split("/")
                if path_parts and path_parts[0]:
                    # If there are path components, create directories for them
                    for i in range(
                        len(path_parts) - 1
                    ):  # Exclude the last part (filename)
                        if path_parts[i]:
                            url_dir = os.path.join(url_dir, path_parts[i])

            # Create the directories if they don't exist
            os.makedirs(url_dir, exist_ok=True)

            # Generate a safe filename for the URL
            safe_filename = generate_safe_filename(url)
            output_file = os.path.join(url_dir, safe_filename)

            # Save mapping
            url_to_file_mapping[url] = output_file

            # Convert HTML to markdown
            markdown_content = html_to_markdown(
                url, session=session, headers=headers, trim=trim
            )

            if markdown_content:
                # Save to file
                update_progress(f"Saving markdown to {output_file}", url, "saving")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(markdown_content)

                update_progress(f"Saved markdown to: {output_file}", url, "saved")
                processed_urls_count += 1

                # Extract links if we haven't reached max depth
                if depth < max_depth:
                    links = extract_links_from_html(html_content, url)
                    update_progress(
                        f"Found {len(links)} links on {url}", url, "extracting_links"
                    )

                    # Filter links according to follow_option
                    for link in links:
                        if link not in visited_urls and should_follow_link(
                            link, start_url, follow_option
                        ):
                            queue.append((link, depth + 1))
                            update_progress(
                                f"Queued link (depth {depth+1}): {link}", link, "queued"
                            )

            else:
                update_progress(f"Failed to convert HTML from {url}", url, "failed")

        except Exception as e:
            update_progress(f"Error processing URL {url}: {str(e)}", url, "error")

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
                    content, url_to_file_mapping, output_dir
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

    update_progress(
        f"Completed crawling. Processed {processed_urls_count} pages, visited {len(visited_urls)} URLs."
    )
    return processed_urls_count, url_to_file_mapping
