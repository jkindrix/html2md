import logging
import os

import requests
from markdownify import markdownify as md

from html2md.cookies.session_manager import get_session
from html2md.markdown.trimmer import trim_markdown, trim_markdown_local
from html2md.utils.formatter import format_markdown

# Setup logger
logger = logging.getLogger("html2md")

# Default headers for web requests
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}


def html_to_markdown(url, session=None, headers=None, trim=False):
    """
    Fetch HTML and convert to Markdown.

    Args:
        url (str): URL to fetch HTML content from.
        session (requests.Session, optional): Session object for HTTP requests.
        headers (dict, optional): Custom headers for the HTTP request.
        trim (bool, optional): Whether to apply trimming rules to the resulting markdown.

    Returns:
        str or None: Markdown content if successful, None otherwise.
    """

    # Use provided session or initialize a new one
    session = session or get_session()

    # Use default headers if none are provided
    if headers is None:
        headers = DEFAULT_HEADERS

    try:
        logger.info(f"Fetching URL: {url}")
        # Send GET request to fetch the HTML content
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html_content = response.text
        logger.info(f"Received {len(html_content)} bytes of HTML from {url}.")

    except requests.exceptions.Timeout:
        logger.error(f"Timeout while fetching {url}")
        return None
    except requests.exceptions.TooManyRedirects:
        logger.error(f"Too many redirects while fetching {url}")
        return None
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error while fetching {url}")
        return None
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if hasattr(e, "response") else "unknown"
        logger.error(f"HTTP error {status_code} while fetching {url}: {e}")
        return None
    except requests.RequestException as e:
        logger.error(f"Failed to retrieve {url}: {e}")
        return None

    # Handle empty HTML response
    if not html_content.strip():
        logger.warning(f"Empty HTML response from {url}")
        return None

    # Check for tiny responses that are likely error pages
    if len(html_content) < 100:
        logger.warning(
            f"Very small response ({len(html_content)} bytes) from {url}, might be an error page"
        )
        # We'll still try to convert it, but log a warning

    # Convert HTML to Markdown using markdownify
    markdown_content = md(html_content, heading_style="ATX")

    # Apply formatting rules to clean up the generated markdown
    formatted_markdown = format_markdown(markdown_content)

    # Apply trimming if requested
    if trim:
        formatted_markdown = trim_markdown(formatted_markdown, url)

    logger.info(f"Successfully converted HTML from {url} to Markdown.")
    return formatted_markdown


def local_html_to_markdown(file_path, trim=False):
    """
    Convert HTML from a local file to Markdown.

    Args:
        file_path (str): Path to the local HTML file.
        trim (bool, optional): Whether to apply trimming rules to the resulting markdown.

    Returns:
        str or None: Markdown content if successful, None otherwise.
    """
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None

        logger.info(f"Reading local file: {file_path}")

        # Read the HTML content from the file
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        logger.info(f"Read {len(html_content)} bytes of HTML from {file_path}.")

        # Handle empty HTML file
        if not html_content.strip():
            logger.warning(f"Empty HTML file: {file_path}")
            return None

        # Convert HTML to Markdown using markdownify
        markdown_content = md(html_content, heading_style="ATX")

        # Apply formatting rules to clean up the generated markdown
        formatted_markdown = format_markdown(markdown_content)

        # Apply trimming if requested
        if trim:
            file_name = os.path.basename(file_path)
            formatted_markdown = trim_markdown_local(formatted_markdown, file_name)

        logger.info(f"Successfully converted HTML from {file_path} to Markdown.")
        return formatted_markdown

    except Exception as e:
        logger.error(f"Error processing local file {file_path}: {str(e)}")
        return None
