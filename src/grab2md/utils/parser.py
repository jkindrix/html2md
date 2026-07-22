import os
import re
from typing import Pattern
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from grab2md.utils.crawl_policy import FollowRule, compile_follow_option
from grab2md.utils.html_references import resolve_document_base
from grab2md.utils.markdown_links import scan_inline_links
from grab2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger(__name__)


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
    urls: list[str] = []

    # Structurally scan inline Markdown links, including balanced parentheses.
    urls.extend(
        link.destination
        for link in scan_inline_links(markdown_content)
        if link.destination.startswith(("http://", "https://"))
    )

    # Pattern 2: Plain URLs starting with http:// or https://
    # Exclude URLs that are already part of markdown links
    content_without_md_links = markdown_content
    for link in reversed(scan_inline_links(markdown_content)):
        content_without_md_links = (
            content_without_md_links[: link.start]
            + content_without_md_links[link.end :]
        )
    pattern2 = r"(https?://[^\s)<>\"']+)"
    urls.extend(re.findall(pattern2, content_without_md_links))

    # Embedded HTML is parsed as HTML rather than with an attribute regex.
    soup = BeautifulSoup(markdown_content, "html.parser")
    for tag in soup.find_all(href=True):
        if isinstance(tag, Tag):
            href = tag.get("href")
            if isinstance(href, str) and href.startswith(("http://", "https://")):
                urls.append(href)

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
    soup = BeautifulSoup(html_content, "html.parser")
    document_base = resolve_document_base(soup, base_url)

    # Convert relative links to absolute URLs and filter out non-HTTP(S) links
    absolute_urls = []
    for tag in soup.find_all(["a", "area"], href=True):
        if not isinstance(tag, Tag) or not isinstance(tag.get("href"), str):
            continue
        link = str(tag.get("href")).strip()
        # Skip javascript:, mailto:, tel: links, anchors, etc.
        if link.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue

        # Resolve relative links to absolute URLs
        absolute_url = urljoin(document_base, link)

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


def should_follow_link(url: str, base_url: str, follow_option: FollowRule) -> bool:
    """
    Determine if a link should be followed based on the follow option.

    Args:
        url (str): The URL to check
        base_url (str): The original base URL
        follow_option: A built-in scope name or compiled regular expression.

    Returns:
        bool: True if the link should be followed, False otherwise
    """
    # Parse URLs
    parsed_url = urlparse(url)
    parsed_base = urlparse(base_url)
    if (
        parsed_url.scheme.casefold() not in {"http", "https"}
        or parsed_base.scheme.casefold() not in {"http", "https"}
        or not parsed_url.hostname
        or not parsed_base.hostname
        or parsed_url.username is not None
        or parsed_url.password is not None
    ):
        return False
    url_host = parsed_url.hostname.casefold().rstrip(".")
    base_host = parsed_base.hostname.casefold().rstrip(".")
    try:
        url_port = parsed_url.port or (
            443 if parsed_url.scheme.casefold() == "https" else 80
        )
        base_port = parsed_base.port or (
            443 if parsed_base.scheme.casefold() == "https" else 80
        )
    except ValueError:
        return False

    # Domain-only: only the same hostname and effective port.
    if follow_option == "domain-only":
        return url_host == base_host and url_port == base_port

    # Host-only: the exact hostname, independent of scheme/default port.
    elif follow_option == "host-only":
        return url_host == base_host

    # Subdomain: the exact starting hostname or a dot-delimited descendant.
    elif follow_option == "subdomain":
        return url_host == base_host or url_host.endswith(f".{base_host}")

    # Regex pattern: follow links matching the precompiled expression.
    pattern: Pattern[str]
    if isinstance(follow_option, str):
        compiled = compile_follow_option(follow_option)
        if isinstance(compiled, str):
            raise ValueError(f"Unknown built-in follow option: {compiled}")
        pattern = compiled
    else:
        pattern = follow_option
    return bool(pattern.search(url))


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
