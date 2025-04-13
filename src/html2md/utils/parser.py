import logging
import os
import re
from urllib.parse import urlparse

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

    Args:
        markdown_content (str): Markdown content to extract URLs from.

    Returns:
        list: List of URLs found in the markdown.
    """
    # Regex pattern to match markdown links [text](url)
    pattern = r"\[.*?\]\((https?://[^\s)]+)\)"

    # Find all matches
    matches = re.findall(pattern, markdown_content)

    # Log the number of URLs found
    logger.info(f"Found {len(matches)} URLs in markdown content")

    return matches


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
