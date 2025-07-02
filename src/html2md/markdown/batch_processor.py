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

    # Basic headers for most sites
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://{domain}/",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Encoding": "gzip, deflate",
        "sec-ch-ua": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Dest": "document",
    }
    
    # Special case for ChatGPT which has stricter bot detection
    if "chatgpt.com" in domain:
        headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Origin": f"https://{domain}",
            "dnt": "1",
            "authority": domain,
            "Pragma": "no-cache",
        })
        
    return headers


def create_directory_structure(output_dir, url, flatten_domain=False, flatten_all=False, hierarchical_domains=False):
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
    # If flatten_all is True, just return the output directory
    if flatten_all:
        return output_dir
    
    parsed_url = urlparse(url)
    domain = parsed_url.netloc

    if hierarchical_domains:
        # Split domain into parts and reverse them
        # e.g., www.jetbrains.com -> ['com', 'jetbrains', 'www']
        domain_parts = domain.split('.')
        domain_parts.reverse()
        
        # Build hierarchical path
        domain_dir = output_dir
        for part in domain_parts:
            domain_dir = os.path.join(domain_dir, part)
    elif flatten_domain:
        # Just use the domain as the output directory
        domain_dir = domain

        # Check if an absolute output path was provided
        if os.path.isabs(output_dir):
            domain_dir = os.path.join(output_dir, domain_dir)
    else:
        # Create domain directory as a subdirectory
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


def process_markdown_links(
    source_files, output_dir, trim=True, progress_callback=None, flatten_output=False,
    flatten_all=False, hierarchical_domains=False, download_images=False, images_dir="images"
):
    """
    Process markdown files, extract URLs, and convert each URL to markdown.

    Args:
        source_files (list): List of markdown files to process
        output_dir (str): Directory to save the output files
        trim (bool, optional): Whether to trim the markdown. Defaults to True.
        progress_callback (callable, optional): Function to call with progress updates
        flatten_output (bool, optional): If True, creates output directories directly
                                        named after domain. Defaults to False.
        flatten_all (bool, optional): If True, outputs all files to a single directory,
                                     ignoring domain structure. Defaults to False.
        hierarchical_domains (bool, optional): If True, creates hierarchical domain structure
                                              (e.g., com/jetbrains/www). Defaults to False.
        download_images (bool, optional): Whether to download images from pages.
        images_dir (str, optional): Directory name for images (default: "images").

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
            url_dir = create_directory_structure(
                output_dir, url, flatten_domain=flatten_output, flatten_all=flatten_all,
                hierarchical_domains=hierarchical_domains
            )

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
                    url, session=session, headers=headers, trim=trim,
                    download_images=download_images, output_dir=url_dir, images_dir=images_dir
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
    return processed_urls_count, url_to_file_mapping
