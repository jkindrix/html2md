import logging
import os
import re
from urllib.parse import urljoin, urlparse

# Setup logger
logger = logging.getLogger("html2md")


def find_nth_occurrence(text: str, substring: str, n: int) -> int:
    """
    Find the nth occurrence of a substring in a string.

    Args:
        text (str): The input string to search within.
        substring (str): The substring to find.
        n (int): The occurrence index (1-based).

    Returns:
        int: The starting index of the nth occurrence, or -1 if not found.

    Edge Cases:
        - If `text` or `substring` is empty, returns -1.
        - If `n <= 0`, returns -1 (invalid occurrence count).
        - If `substring` is not found at least `n` times, returns -1.
    """
    if not text or not substring or n <= 0:
        return -1  # Invalid input

    matches = [match.start() for match in re.finditer(re.escape(substring), text)]

    return matches[n - 1] if len(matches) >= n else -1


def extract_urls_from_markdown(markdown_content):
    """
    Extract URLs from markdown content using regex.
    Supports multiple URL formats including markdown links, plain URLs, and URLs in bullet points.

    Args:
        markdown_content (str): Markdown content to extract URLs from.

    Returns:
        list: List of URLs found in the markdown.
    """
    urls = []

    # Pattern 1: Markdown links [text](url)
    pattern1 = r"\[.*?\]\((https?://[^\s)]+)\)"
    urls.extend(re.findall(pattern1, markdown_content))

    # Pattern 2: Plain URLs starting with http:// or https://
    # Exclude URLs that are already part of markdown links
    content_without_md_links = re.sub(
        r"\[.*?\]\(https?://[^\s)]+\)", "", markdown_content
    )
    pattern2 = r"(https?://[^\s)<>\"']+)"
    urls.extend(re.findall(pattern2, content_without_md_links))

    # Pattern 3: URLs in HTML href attributes
    pattern3 = r'href=[\'"]?(https?://[^\'"<>\s]+)'
    urls.extend(re.findall(pattern3, markdown_content))

    # Pattern 4: One URL per line (common in URL list files)
    pattern4 = r"^(https?://[^\s)<>\"']+)$"
    urls.extend(re.findall(pattern4, markdown_content, re.MULTILINE))

    # Remove duplicates while preserving order
    unique_urls = []
    for url in urls:
        if url not in unique_urls:
            unique_urls.append(url)

    # Log the number of URLs found
    logger.info(f"Found {len(unique_urls)} URLs in markdown content")

    return unique_urls


def extract_links_from_html(html_content, base_url):
    """
    Extract all links from HTML content.

    Args:
        html_content (str): HTML content to extract links from
        base_url (str): Base URL to resolve relative links

    Returns:
        list: List of absolute URLs found in the HTML
    """
    # Use a simple regex to find all href attributes
    href_pattern = re.compile(r'href=[\'"]([^\'"]+)[\'"]')
    relative_links = href_pattern.findall(html_content)

    # Convert relative links to absolute URLs and filter out non-HTTP(S) links
    absolute_urls = []
    for link in relative_links:
        # Skip javascript:, mailto:, tel: links, anchors, etc.
        if link.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue

        # Resolve relative links to absolute URLs
        absolute_url = urljoin(base_url, link)

        # Ensure it's an HTTP(S) URL
        if absolute_url.startswith(("http://", "https://")):
            absolute_urls.append(absolute_url)

    # Remove duplicates while preserving order
    unique_urls = []
    for url in absolute_urls:
        if url not in unique_urls:
            unique_urls.append(url)

    logger.info(f"Found {len(unique_urls)} links in HTML content from {base_url}")
    return unique_urls


def should_follow_link(url, base_url, follow_option):
    """
    Determine if a link should be followed based on the follow option.

    Args:
        url (str): The URL to check
        base_url (str): The original base URL
        follow_option (str): The follow option (domain-only, host-only, subdomain, or regex pattern)

    Returns:
        bool: True if the link should be followed, False otherwise
    """
    # Parse URLs
    parsed_url = urlparse(url)
    parsed_base = urlparse(base_url)

    # Domain-only: Only follow links to the same domain
    if follow_option == "domain-only":
        return parsed_url.netloc == parsed_base.netloc

    # Host-only: Only follow links to the same host (excluding subdomains)
    elif follow_option == "host-only":
        base_domain = ".".join(parsed_base.netloc.split(".")[-2:])
        url_domain = ".".join(parsed_url.netloc.split(".")[-2:])
        return url_domain == base_domain

    # Subdomain: Follow links to the same domain and its subdomains
    elif follow_option == "subdomain":
        base_domain = ".".join(parsed_base.netloc.split(".")[-2:])
        return parsed_url.netloc.endswith(base_domain)

    # Regex pattern: Follow links matching the regex pattern
    else:
        try:
            pattern = re.compile(follow_option)
            return bool(pattern.search(url))
        except re.error:
            logger.error(f"Invalid regex pattern: {follow_option}")
            return False


def get_urls_from_file(file_path):
    """
    Read a file and extract URLs from its content.

    Args:
        file_path (str): Path to the markdown file.

    Returns:
        list: List of URLs found in the file.
    """
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return []

        # Read the file content
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract URLs from the content
        urls = extract_urls_from_markdown(content)
        logger.info(f"Extracted {len(urls)} URLs from {file_path}")

        return urls

    except Exception as e:
        logger.error(f"Error reading file {file_path}: {str(e)}")
        return []


def generate_safe_filename(url):
    """
    Generate a safe filename from a URL.

    Args:
        url (str): URL to convert to a safe filename.

    Returns:
        str: Safe filename based on the URL.
    """
    parsed = urlparse(url)

    # Create a base for the filename from the netloc and path
    base = parsed.netloc + parsed.path

    # Include query parameters if present
    if parsed.query:
        base += "_" + parsed.query

    # Include fragment if present
    if parsed.fragment:
        base += "_" + parsed.fragment

    # Remove any special characters and replace with underscores
    safe_name = re.sub(r"[^\w\-_.]", "_", base)

    # Remove any leading or trailing underscores
    safe_name = safe_name.strip("_")

    # Ensure the filename is not too long
    if len(safe_name) > 100:
        safe_name = safe_name[:100]

    # Add .md extension
    if not safe_name.endswith(".md"):
        safe_name += ".md"

    return safe_name


def is_url(source, force_local=False):
    """
    Determine if the source is a URL or a local file path.

    Args:
        source (str): The source string to check
        force_local (bool, optional): Force treating as local file. Defaults to False.

    Returns:
        bool: True if source is a URL, False otherwise
    """
    if force_local:
        return False

    parsed = urlparse(source)
    return bool(parsed.scheme in ("http", "https") and parsed.netloc)
