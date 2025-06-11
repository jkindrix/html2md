import argparse
import glob
import logging
import os
import sys
from urllib.parse import urlparse

# Delay imports that might trigger config validation
from html2md.utils.logger import setup_logging

logger = setup_logging()


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
        "Accept-Encoding": "gzip, deflate, br",
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
    if "chatgpt.com" in domain or "chat.openai.com" in domain:
        # Use headers that closely mimic a real browser for ChatGPT
        headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Origin": f"https://{domain}",
            "Referer": f"https://{domain}/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "DNT": "1",
            "Authority": domain,
            "Host": domain,
            "Pragma": "no-cache",
            "Sec-CH-UA": '"Google Chrome";v="123", "Not:A-Brand";v="8", "Chromium";v="123"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        })
        
    return headers


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


def process_single(source, trim=True, output=None, no_cookies=False, browser_cookies=False, browser=None, cookie_path=None, cookie_json=None, local=False, oauth_email=None, oauth_password=None, download_images=False, images_dir="images"):
    """Process a single URL or file and save/print the result."""
    if is_url(source, local):
        # Process as URL
        headers = build_headers(source)
        logger.info(f"Processing URL: {source}")

        try:
            # Create a new session
            session = None
            
            # Determine session type based on flags
            if not no_cookies:
                session = get_session()
                
                # Update config with cookie path if provided
                from html2md.config.loader import load_config
                config = load_config()
                
                if cookie_path:
                    config.setdefault('browser', {}).setdefault('custom_path', {})
                    if browser:
                        config['browser']['custom_path'][browser] = str(cookie_path)
                    else:
                        pref_browser = config.get('browser', {}).get('preferred', 'chrome')
                        config['browser']['custom_path'][pref_browser] = str(cookie_path)
                
                # If browser cookies flag is set, apply browser cookies to session
                if browser_cookies and session:
                    # Store browser preference in config or use specified one
                    if browser:
                        config.setdefault('browser', {})['preferred'] = browser
                    
                    # Apply browser cookies to session
                    if cookie_json:
                        logger.info(f"Using cookies from JSON file: {cookie_json}")
                        session = apply_browser_cookies(session, source, cookie_json)
                    else:
                        session = apply_browser_cookies(session, source)
                        logger.info(f"Using cookies from {browser or config.get('browser', {}).get('preferred', 'chrome')} browser for {source}")
            
            # For debugging - log all available cookies for the domain
            if logger.level <= logging.DEBUG:
                domain = urlparse(source).netloc
                cookies_for_domain = {k: v for k, v in session.cookies.items() if domain in session.cookies.domains.get(k, [])}
                logger.debug(f"Cookies available for {domain}: {cookies_for_domain}")

            # Determine output directory for images if needed
            output_dir = None
            if download_images and output:
                output_dir = os.path.dirname(os.path.abspath(output))
            elif download_images:
                # If no output file specified but downloading images, use current directory
                output_dir = os.getcwd()

            # Process URL with session and headers
            markdown_result = html_to_markdown(
                source, session=session, headers=headers, trim=trim,
                oauth_email=oauth_email, oauth_password=oauth_password,
                download_images=download_images, output_dir=output_dir, images_dir=images_dir
            )

            if markdown_result:
                if output:
                    save_to_file(output, markdown_result)
                else:
                    print(f"\n# URL: {source}\n")
                    print(markdown_result)
                logger.info(f"Successfully processed URL: {source}")
                return True
        except Exception as e:
            logger.error(f"Failed to process URL {source}: {e}")
            return False
    else:
        # Process as local file
        logger.info(f"Processing local file: {source}")

        try:
            # Expand to absolute path if needed
            file_path = os.path.abspath(os.path.expanduser(source))

            # Determine output directory for images if needed
            output_dir = None
            if download_images and output:
                output_dir = os.path.dirname(os.path.abspath(output))
            elif download_images:
                # If no output file specified but downloading images, use file's directory
                output_dir = os.path.dirname(file_path)

            # Process local file
            markdown_result = local_html_to_markdown(file_path, trim=trim, 
                                                    download_images=download_images, 
                                                    output_dir=output_dir, 
                                                    images_dir=images_dir)

            if markdown_result:
                if output:
                    save_to_file(output, markdown_result)
                else:
                    print(f"\n# File: {file_path}\n")
                    print(markdown_result)
                logger.info(f"Successfully processed local file: {file_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to process local file {source}: {e}")
            return False

    return False


def process_batch(input_files, output_dir, trim=True, flatten_output=False, download_images=False, images_dir="images"):
    """Process a batch of markdown files with links to convert."""
    # Expand any glob patterns in input files
    expanded_files = []
    for pattern in input_files:
        matches = glob.glob(os.path.expanduser(pattern))
        if matches:
            expanded_files.extend(matches)
        else:
            logger.warning(f"No files found matching pattern: {pattern}")

    if not expanded_files:
        logger.error("No input files found to process.")
        return False

    # Process the files
    try:
        processed_count = process_markdown_links(
            expanded_files, output_dir, trim, flatten_output=flatten_output,
            download_images=download_images, images_dir=images_dir
        )
        logger.info(f"Batch processing complete. Processed {processed_count} URLs.")
        return processed_count > 0
    except Exception as e:
        logger.error(f"Error during batch processing: {e}")
        return False


def process_recursive(
    start_urls,
    output_dir,
    follow_option="domain-only",
    max_depth=3,
    max_pages=100,
    trim=True,
    flatten_output=False,
    download_images=False,
    images_dir="images",
):
    """Process URLs recursively, following links according to the follow option."""
    total_processed = 0

    for start_url in start_urls:
        if not is_url(start_url):
            logger.error(f"Invalid URL: {start_url}")
            continue

        try:
            logger.info(f"Starting recursive crawl from: {start_url}")
            processed_count, _ = crawl_website(
                start_url,
                output_dir,
                follow_option=follow_option,
                max_depth=max_depth,
                max_pages=max_pages,
                trim=trim,
                flatten_output=flatten_output,
                download_images=download_images,
                images_dir=images_dir,
            )
            total_processed += processed_count
            logger.info(
                f"Crawling complete for {start_url}. Processed {processed_count} pages."
            )
        except Exception as e:
            logger.error(f"Error during recursive processing of {start_url}: {e}")

    logger.info(
        f"Recursive processing complete. Total processed: {total_processed} pages."
    )
    return total_processed > 0


def init_config():
    """Initialize configuration file with example values."""
    from html2md.config.loader import CONFIG_PATH
    import json
    import shutil
    from pathlib import Path
    
    logger = setup_logging()
    
    # Path to template config file
    template_path = Path(__file__).parent.parent / "config" / "config.json"
    
    # Check if config already exists
    if CONFIG_PATH.exists():
        logger.warning(f"Config file already exists at: {CONFIG_PATH}")
        response = input("Do you want to overwrite it? (y/N): ")
        if response.lower() != 'y':
            logger.info("Config initialization cancelled.")
            return False
    
    # Ensure directory exists
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Copy template file or create default
    try:
        if template_path.exists():
            shutil.copy2(template_path, CONFIG_PATH)
            logger.info(f"Config file created from template at: {CONFIG_PATH}")
        else:
            # Fallback to creating a basic config
            example_config = {
                "oauth": {
                    "CLIENT_ID": "YOUR_GOOGLE_CLIENT_ID_HERE",
                    "CLIENT_SECRET": "YOUR_GOOGLE_CLIENT_SECRET_HERE"
                },
                "browser": {
                    "preferred": "chrome",
                    "custom_path": {}
                },
                "domains": {},
                "logging": {
                    "level": "INFO"
                }
            }
            with open(CONFIG_PATH, 'w') as f:
                json.dump(example_config, f, indent=2)
            logger.info(f"Config file created at: {CONFIG_PATH}")
        
        logger.info("Please edit the config file to add your Google OAuth credentials.")
        logger.info("You can get OAuth credentials from: https://console.cloud.google.com/")
        logger.info("\nFor ChatGPT conversion, OAuth is required. For other sites, you can use the tool without OAuth.")
        return True
    except Exception as e:
        logger.error(f"Failed to create config file: {e}")
        return False


def main():
    """Parse arguments and process URLs or local files."""
    # Handle --init-config before full argument parsing to avoid import issues
    if "--init-config" in sys.argv:
        success = init_config()
        sys.exit(0 if success else 1)
    
    # Handle --help for main command only (not subcommands)
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] in ["--help", "-h"]):
        parser = argparse.ArgumentParser(
            description="Convert HTML content from URLs or local files to Markdown."
        )
        parser.add_argument(
            "--init-config",
            action="store_true",
            help="Initialize configuration file with example values."
        )
        # Add basic help for commands without importing modules
        parser.add_argument(
            "command",
            nargs="?",
            choices=["convert", "batch", "crawl"],
            help="Command to execute (convert, batch, or crawl)"
        )
        parser.print_help()
        print("\nCommands:")
        print("  convert    Convert a single URL or file to markdown")
        print("  batch      Process markdown files with links and create modular output")
        print("  crawl      Recursively crawl websites and convert to markdown")
        print("\nUse 'html2md <command> --help' for help on a specific command.")
        sys.exit(0)
    
    # Now import the modules that might trigger config validation
    from html2md.cookies.session_manager import get_session, apply_browser_cookies
    from html2md.markdown.batch_processor import process_markdown_links
    from html2md.markdown.converter import html_to_markdown, local_html_to_markdown
    from html2md.markdown.crawler import crawl_website
    
    parser = argparse.ArgumentParser(
        description="Convert HTML content from URLs or local files to Markdown."
    )
    
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Initialize configuration file with example values."
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Single file/URL conversion (default)
    single_parser = subparsers.add_parser(
        "convert", help="Convert a single URL or file to markdown"
    )
    single_parser.add_argument(
        "sources", nargs="+", help="URLs or local HTML files to convert."
    )
    single_parser.add_argument(
        "--no-trim",
        action="store_false",
        dest="trim",
        help="Disable trimming based on domain-specific rules.",
    )
    single_parser.add_argument(
        "--output",
        type=str,
        help="Specify output file to save converted markdown. If not provided, prints to stdout.",
    )
    single_parser.add_argument(
        "--no-cookies",
        action="store_true",
        help="Disable loading cookies from the browser.",
    )
    single_parser.add_argument(
        "--browser-cookies",
        action="store_true",
        help="Use cookies from the local browser to authenticate with websites.",
    )
    single_parser.add_argument(
        "--browser",
        type=str,
        choices=["chrome", "firefox", "edge", "safari"],
        default="chrome",
        help="Specify which browser to extract cookies from (default: chrome).",
    )
    single_parser.add_argument(
        "--cookie-path",
        type=str,
        help="Path to browser cookies database file (helps with Windows/WSL).",
    )
    single_parser.add_argument(
        "--cookie-json",
        type=str,
        help="Path to JSON file with exported cookies (from browser developer tools).",
    )
    single_parser.add_argument(
        "--local",
        action="store_true",
        help="Force treating sources as local files even if they look like URLs.",
    )
    single_parser.add_argument(
        "--oauth-email",
        type=str,
        help="Email address for OAuth authentication with ChatGPT.",
    )
    single_parser.add_argument(
        "--oauth-password",
        type=str,
        help="Password for OAuth authentication with ChatGPT.",
    )
    single_parser.add_argument(
        "--download-images",
        action="store_true",
        help="Download images from the webpage and store them locally.",
    )
    single_parser.add_argument(
        "--images-dir",
        type=str,
        default="images",
        help="Directory name for storing downloaded images (default: images).",
    )

    # Batch processing
    batch_parser = subparsers.add_parser(
        "batch", help="Process markdown files with links and create modular output"
    )
    batch_parser.add_argument(
        "input_files", nargs="+", help="Markdown files containing links to process."
    )
    batch_parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Directory to save the output files and folders. Default is 'output'.",
    )
    batch_parser.add_argument(
        "--no-trim",
        action="store_false",
        dest="trim",
        help="Disable trimming based on domain-specific rules.",
    )
    batch_parser.add_argument(
        "--flatten",
        action="store_true",
        dest="flatten_output",
        help="Output files directly to domain directories (e.g., 'docs.github.com/')",
    )
    batch_parser.add_argument(
        "--download-images",
        action="store_true",
        help="Download images from the webpages and store them locally.",
    )
    batch_parser.add_argument(
        "--images-dir",
        type=str,
        default="images",
        help="Directory name for storing downloaded images (default: images).",
    )

    # Recursive crawling
    crawl_parser = subparsers.add_parser(
        "crawl",
        help="Recursively crawl websites from starting URLs and convert to markdown",
    )
    crawl_parser.add_argument("start_urls", nargs="+", help="Starting URLs to crawl.")
    crawl_parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Directory to save the output files and folders. Default is 'output'.",
    )
    crawl_parser.add_argument(
        "--follow",
        type=str,
        default="domain-only",
        help="How to follow links. Options: 'domain-only', 'host-only', 'subdomain', or a regex pattern.",
    )
    crawl_parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum link depth to follow. Default is 3.",
    )
    crawl_parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="Maximum number of pages to crawl. Default is 100.",
    )
    crawl_parser.add_argument(
        "--no-trim",
        action="store_false",
        dest="trim",
        help="Disable trimming based on domain-specific rules.",
    )
    crawl_parser.add_argument(
        "--flatten",
        action="store_true",
        dest="flatten_output",
        help="Output files directly to domain directories (e.g., 'docs.github.com/')",
    )
    crawl_parser.add_argument(
        "--download-images",
        action="store_true",
        help="Download images from the webpages and store them locally.",
    )
    crawl_parser.add_argument(
        "--images-dir",
        type=str,
        default="images",
        help="Directory name for storing downloaded images (default: images).",
    )

    # Common arguments
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level (default: INFO).",
    )
    parser.add_argument(
        "--debug-log",
        type=str,
        help="Write debug logs to specified file (always at DEBUG level regardless of --log-level).",
    )

    args = parser.parse_args()

    # Set up logging with the debug file if specified
    global logger
    if hasattr(args, 'debug_log') and args.debug_log:
        from html2md.utils.logger import setup_logging
        logger = setup_logging(console_output=True, debug_file=args.debug_log)
        logger.info(f"Debug logs will be written to: {args.debug_log}")
    
    # Set logging level dynamically
    logger.setLevel(getattr(logging, args.log_level.upper(), logging.INFO))

    # Default to 'convert' if no command is specified
    if not args.command:
        parser.print_help()
        return

    # Ensure trim is True by default
    if hasattr(args, "trim"):
        args.trim = True if args.trim is None else args.trim

    # Process based on command
    if args.command == "convert":
        for source in args.sources:
            process_single(
                source,
                trim=args.trim,
                output=args.output,
                no_cookies=args.no_cookies,
                browser_cookies=getattr(args, "browser_cookies", False),
                browser=getattr(args, "browser", None),
                cookie_path=getattr(args, "cookie_path", None),
                cookie_json=getattr(args, "cookie_json", None),
                local=args.local,
                oauth_email=getattr(args, "oauth_email", None),
                oauth_password=getattr(args, "oauth_password", None),
                download_images=getattr(args, "download_images", False),
                images_dir=getattr(args, "images_dir", "images"),
            )
    elif args.command == "batch":
        process_batch(
            args.input_files,
            args.output_dir,
            args.trim,
            flatten_output=getattr(args, "flatten_output", False),
            download_images=getattr(args, "download_images", False),
            images_dir=getattr(args, "images_dir", "images"),
        )
    elif args.command == "crawl":
        process_recursive(
            args.start_urls,
            args.output_dir,
            follow_option=args.follow,
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            trim=args.trim,
            flatten_output=args.flatten_output,
            download_images=getattr(args, "download_images", False),
            images_dir=getattr(args, "images_dir", "images"),
        )


if __name__ == "__main__":
    main()
