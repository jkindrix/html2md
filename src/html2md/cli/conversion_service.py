"""Shared conversion orchestration for CLI presentation modes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from html2md.cli.runtime import build_header_config
from html2md.config.loader import load_config
from html2md.cookies.session_manager import apply_browser_cookies, get_session
from html2md.markdown.content_extractor import ContentMode, validate_content_request
from html2md.markdown.converter import html_to_markdown, local_html_to_markdown
from html2md.network.auth_inputs import load_private_headers, load_storage_state
from html2md.network.header_manager import HeaderManager
from html2md.utils.parser import is_url

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]


@dataclass(frozen=True)
class ConversionResult:
    """The presentation-neutral outcome of converting one source."""

    source: str
    source_label: str
    markdown: Optional[str]
    is_remote: bool
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return bool(self.markdown) and self.error is None


def _ignore_status(_message: str) -> None:
    """Default status callback for non-interactive callers."""


def convert_source(
    source: str,
    *,
    content_mode: ContentMode = ContentMode.FULL,
    selector: Optional[str] = None,
    output: Optional[Path],
    no_cookies: bool,
    browser_cookies: bool,
    browser: Optional[str],
    cookie_json: Optional[Path] = None,
    headers_file: Optional[Path] = None,
    storage_state: Optional[Path] = None,
    local: bool = False,
    download_images: bool = False,
    images_dir: str = "images",
    enhanced_headers: bool = True,
    user_agent_contact: Optional[str] = None,
    simulate_browser: bool = False,
    insecure: bool = False,
    include_metadata: bool = False,
    render_js: bool = False,
    allow_private_network: bool = False,
    on_status: StatusCallback = _ignore_status,
) -> ConversionResult:
    """Fetch and convert one URL or local file without rendering CLI output."""

    remote = is_url(source, local)
    if remote:
        return _convert_url(
            source,
            content_mode=content_mode,
            selector=selector,
            output=output,
            no_cookies=no_cookies,
            browser_cookies=browser_cookies,
            browser=browser,
            cookie_json=cookie_json,
            headers_file=headers_file,
            storage_state=storage_state,
            download_images=download_images,
            images_dir=images_dir,
            enhanced_headers=enhanced_headers,
            user_agent_contact=user_agent_contact,
            simulate_browser=simulate_browser,
            insecure=insecure,
            include_metadata=include_metadata,
            render_js=render_js,
            allow_private_network=allow_private_network,
            on_status=on_status,
        )

    if render_js:
        return ConversionResult(
            source,
            str(Path(source).expanduser().resolve()),
            None,
            False,
            "JavaScript rendering is available only for HTTP(S) URLs.",
        )
    if headers_file or storage_state:
        return ConversionResult(
            source,
            str(Path(source).expanduser().resolve()),
            None,
            False,
            "Authentication inputs are available only for HTTP(S) URLs.",
        )

    return _convert_file(
        source,
        content_mode=content_mode,
        selector=selector,
        output=output,
        download_images=download_images,
        images_dir=images_dir,
        insecure=insecure,
        include_metadata=include_metadata,
        allow_private_network=allow_private_network,
        on_status=on_status,
    )


def _convert_url(
    source: str,
    *,
    content_mode: ContentMode,
    selector: Optional[str],
    output: Optional[Path],
    no_cookies: bool,
    browser_cookies: bool,
    browser: Optional[str],
    cookie_json: Optional[Path],
    headers_file: Optional[Path],
    storage_state: Optional[Path],
    download_images: bool,
    images_dir: str,
    enhanced_headers: bool,
    user_agent_contact: Optional[str],
    simulate_browser: bool,
    insecure: bool,
    include_metadata: bool,
    render_js: bool,
    allow_private_network: bool,
    on_status: StatusCallback,
) -> ConversionResult:
    logger.info("Processing URL: %s", source)
    try:
        validate_content_request(content_mode, selector)
        if render_js and (browser_cookies or cookie_json):
            raise ValueError(
                "JavaScript rendering does not import browser or JSON cookies; "
                "use the static authenticated path."
            )
        if storage_state and not render_js:
            raise ValueError("Browser storage state requires --render-js.")
        loaded_storage_state = (
            load_storage_state(storage_state) if storage_state else None
        )
        config = load_config()
        header_config = build_header_config(
            config,
            enhanced_headers=enhanced_headers,
            user_agent_contact=user_agent_contact,
            simulate_browser=simulate_browser,
        )
        headers = HeaderManager(header_config).get_headers(source)
        if headers_file:
            headers.update(load_private_headers(headers_file))

        on_status(f"Fetching content from {source}")
        session = None
        if not no_cookies and not render_js:
            session = get_session(verify_ssl=not insecure)
            if browser_cookies and session:
                if cookie_json:
                    on_status(f"Loading cookies from JSON file for {source}")
                else:
                    browser_name = browser or config.get("browser", {}).get(
                        "preferred", "chrome"
                    )
                    on_status(f"Extracting cookies from {browser_name} for {source}")
                session = apply_browser_cookies(
                    session, source, cookie_json, browser=browser
                )

        output_dir = None
        if download_images:
            output_dir = output.parent.resolve() if output else Path.cwd()

        markdown = html_to_markdown(
            source,
            session=session,
            headers=headers,
            content_mode=content_mode,
            selector=selector,
            download_images=download_images,
            output_dir=output_dir,
            images_dir=images_dir,
            verify_ssl=not insecure,
            include_metadata=include_metadata,
            render_js=render_js,
            allow_private_network=allow_private_network,
            storage_state=loaded_storage_state,
        )
        on_status(f"Converting {source} to markdown")
        return ConversionResult(source, source, markdown, True)
    except Exception as error:
        logger.error("Failed to process URL %s: %s", source, error)
        return ConversionResult(source, source, None, True, str(error))


def _convert_file(
    source: str,
    *,
    content_mode: ContentMode,
    selector: Optional[str],
    output: Optional[Path],
    download_images: bool,
    images_dir: str,
    insecure: bool,
    include_metadata: bool,
    allow_private_network: bool,
    on_status: StatusCallback,
) -> ConversionResult:
    file_path = Path(source).expanduser().resolve()
    logger.info("Processing local file: %s", file_path)
    try:
        validate_content_request(content_mode, selector)
        on_status(f"Reading local file {file_path}")
        output_dir = None
        if download_images:
            output_dir = output.parent.resolve() if output else file_path.parent

        markdown = local_html_to_markdown(
            file_path,
            content_mode=content_mode,
            selector=selector,
            download_images=download_images,
            output_dir=output_dir,
            images_dir=images_dir,
            verify_ssl=not insecure,
            include_metadata=include_metadata,
            allow_private_network=allow_private_network,
        )
        on_status(f"Converting {file_path} to markdown")
        return ConversionResult(source, str(file_path), markdown, False)
    except Exception as error:
        logger.error("Failed to process local file %s: %s", source, error)
        return ConversionResult(source, str(file_path), None, False, str(error))
