import logging
import os
import re
from urllib.parse import urlparse

from html2md.cookies.session_manager import get_session
from html2md.markdown.converter import html_to_markdown
from html2md.utils.parser import generate_safe_filename, get_urls_from_file

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


def create_directory_structure(output_dir, url):
    """
    Create a directory structure based on the URL's domain.

    Args:
        output_dir (str): Base output directory
        url (str): URL to create structure for

    Returns:
        str: Path to the directory where the file should be saved
    """
    parsed_url = urlparse(url)
    domain = parsed_url.netloc

    # Create domain directory
    domain_dir = os.path.join(output_dir, domain)

    # Create path directories if they exist
    path_parts = parsed_url.path.strip("/").split("/")
    if path_parts and path_parts[0]:
        # If there are path components, create directories for them
        for i in range(len(path_parts) - 1):  # Exclude the last part (filename)
            if path_parts[i]:
                domain_dir = os.path.join(domain_dir, path_parts[i])

    # Create the directories if they don't exist
    os.makedirs(domain_dir, exist_ok=True)

    return domain_dir


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


def process_markdown_links(source_files, output_dir, trim=True, progress_callback=None):
    """
    Process markdown files, extract URLs, and convert each URL to markdown.

    Args:
        source_files (list): List of markdown files to process
        output_dir (str): Directory to save the output files
        trim (bool, optional): Whether to trim the markdown. Defaults to True.
        progress_callback (callable, optional): Function to call with progress updates

    Returns:
        int: Number of processed URLs
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # URL to local file mapping for link rewriting
    url_to_file_mapping = {}
    processed_urls_count = 0

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
            continue

        update_progress(f"Found {len(urls)} URLs in {source_file}")

        # Process each URL
        for index, url in enumerate(urls):
            # Skip if already processed
            if url in url_to_file_mapping:
                update_progress(
                    f"Skipping already processed URL: {url}", url, "skipped"
                )
                continue

            # Update progress
            update_progress(
                f"Processing URL {index+1}/{len(urls)}: {url}", url, "processing"
            )

            # Create directory structure for the URL
            url_dir = create_directory_structure(output_dir, url)

            # Generate a safe filename for the URL
            safe_filename = generate_safe_filename(url)
            output_file = os.path.join(url_dir, safe_filename)

            # Save mapping
            url_to_file_mapping[url] = output_file

            try:
                # Create session for the URL
                update_progress(f"Fetching content from {url}", url, "fetching")
                session = get_session()
                headers = build_headers(url)

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
                else:
                    update_progress(f"Failed to process URL: {url}", url, "failed")

            except Exception as e:
                update_progress(f"Error processing URL {url}: {str(e)}", url, "error")

    # Second pass: Rewrite links in all files to point to local files
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
            updated_content = rewrite_links(content, url_to_file_mapping, output_dir)

            # Save updated content
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(updated_content)

            update_progress(f"Updated links in file: {output_file}", url, "updated")

        except Exception as e:
            update_progress(
                f"Error updating links in file {output_file}: {str(e)}", url, "error"
            )

    update_progress(f"Completed processing {processed_urls_count} URLs")
    return processed_urls_count
