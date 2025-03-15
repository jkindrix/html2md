import requests
import logging
from markdownify import markdownify as md
from html2md.utils.formatter import format_markdown
from html2md.markdown.trimmer import trim_markdown

# Setup logger
logger = logging.getLogger("html2md")

# Default headers for web requests
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0"
}


def html_to_markdown(url, session, headers=None, trim=False):
    """Fetch HTML and convert to Markdown."""

    if headers is None:
        headers = DEFAULT_HEADERS  # Use default headers if none provided

    try:
        logger.info(f"Fetching URL: {url}")
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html_content = response.text
        logger.info(f"Received {len(html_content)} bytes of HTML.")

    except requests.RequestException as e:
        logger.error(f"Failed to retrieve {url}: {e}")
        return None

    if not html_content.strip():
        logger.warning(f"Empty HTML response from {url}")
        return None

    markdown_content = md(html_content, heading_style="ATX")
    formatted_markdown = format_markdown(markdown_content)

    if trim:
        formatted_markdown = trim_markdown(formatted_markdown, url)

    logger.info(f"Successfully converted HTML from {url} to Markdown.")
    return formatted_markdown
