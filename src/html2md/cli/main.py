import argparse
import sys
import logging
from urllib.parse import urlparse
from html2md.markdown.converter import html_to_markdown
from html2md.cookies.session_manager import session
from html2md.utils.logger import setup_logging

logger = setup_logging()


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


def main():
    """Parse arguments and process URLs."""
    parser = argparse.ArgumentParser(
        description="Convert HTML content from URLs to Markdown."
    )
    parser.add_argument("urls", nargs="+", help="URLs to fetch and convert.")
    parser.add_argument(
        "--no-trim",
        action="store_false",
        dest="trim",
        help="Disable trimming based on domain-specific rules.",
    )

    args = parser.parse_args()
    args.trim = True if args.trim is None else args.trim  # Ensure default is True

    for url in args.urls:
        headers = build_headers(url)
        logger.info(f"Processing URL: {url}")

        try:
            markdown_result = html_to_markdown(
                url, session, headers=headers, trim=args.trim
            )
            if markdown_result:
                print(f"\n# URL: {url}\n")
                print(markdown_result)
                logger.info(f"Successfully processed: {url}")
        except Exception as e:
            logger.error(f"Failed to process {url}: {e}")
            continue  # Skip instead of exiting


if __name__ == "__main__":
    main()
