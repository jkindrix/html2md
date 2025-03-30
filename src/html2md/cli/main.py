import argparse
import logging
import os
from urllib.parse import urlparse

from html2md.cookies.session_manager import get_session
from html2md.markdown.converter import html_to_markdown, local_html_to_markdown
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


def save_to_file(output_filename, content):
    """Save the converted markdown content to a file."""
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Saved output to {output_filename}")
    except IOError as e:
        logger.error(f"Failed to write to {output_filename}: {e}")


def is_url(source, force_local=False):
    """Determine if the source is a URL or a local file path."""
    if force_local:
        return False

    parsed = urlparse(source)
    return bool(parsed.scheme in ("http", "https") and parsed.netloc)


def main():
    """Parse arguments and process URLs or local files."""
    parser = argparse.ArgumentParser(
        description="Convert HTML content from URLs or local files to Markdown."
    )
    parser.add_argument(
        "sources", nargs="+", help="URLs or local HTML files to convert."
    )
    parser.add_argument(
        "--no-trim",
        action="store_false",
        dest="trim",
        help="Disable trimming based on domain-specific rules.",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Specify output file to save converted markdown. If not provided, prints to stdout.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level (default: INFO).",
    )
    parser.add_argument(
        "--no-cookies",
        action="store_true",
        help="Disable loading cookies from the browser.",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Force treating sources as local files even if they look like URLs.",
    )

    args = parser.parse_args()

    # Set logging level dynamically
    logger.setLevel(getattr(logging, args.log_level.upper(), logging.INFO))

    args.trim = True if args.trim is None else args.trim  # Ensure default is True

    for source in args.sources:
        if is_url(source, args.local):
            # Process as URL
            headers = build_headers(source)
            logger.info(f"Processing URL: {source}")

            try:
                # Create a new session for each URL if cookies are not disabled
                session = get_session() if not args.no_cookies else None

                # Process URL with session and headers
                markdown_result = html_to_markdown(
                    source, session=session, headers=headers, trim=args.trim
                )

                if markdown_result:
                    if args.output:
                        save_to_file(args.output, markdown_result)
                    else:
                        print(f"\n# URL: {source}\n")
                        print(markdown_result)
                    logger.info(f"Successfully processed URL: {source}")
            except Exception as e:
                logger.error(f"Failed to process URL {source}: {e}")
                continue  # Skip and continue with the next source
        else:
            # Process as local file
            logger.info(f"Processing local file: {source}")

            try:
                # Expand to absolute path if needed
                file_path = os.path.abspath(os.path.expanduser(source))

                # Process local file
                markdown_result = local_html_to_markdown(file_path, trim=args.trim)

                if markdown_result:
                    if args.output:
                        save_to_file(args.output, markdown_result)
                    else:
                        print(f"\n# File: {file_path}\n")
                        print(markdown_result)
                    logger.info(f"Successfully processed local file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to process local file {source}: {e}")
                continue  # Skip and continue with the next source


if __name__ == "__main__":
    main()
