"""Compatibility functions over the typed page acquisition/conversion pipeline."""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from html2md.cookies.session_manager import disable_ssl_verification, get_session
from html2md.markdown.content_extractor import ContentMode
from html2md.markdown.pipeline import (
    AcquisitionFailure,
    AcquiredPage,
    ConversionFailure,
    PagePipeline,
    acquire_http_page,
    acquire_local_page,
    acquire_rendered_page,
)
from html2md.network.safe_http import DEFAULT_MAX_BODY_BYTES

logger = logging.getLogger("html2md")


def html_to_markdown(
    url,
    session=None,
    headers=None,
    content_mode=ContentMode.FULL,
    selector=None,
    download_images=False,
    output_dir=None,
    images_dir="images",
    verify_ssl=True,
    include_metadata=False,
    render_js=False,
    allow_private_network=False,
    network_policy=None,
    max_html_bytes=DEFAULT_MAX_BODY_BYTES,
    storage_state=None,
):
    """Acquire one URL and return Markdown, preserving the legacy optional API."""
    owned_session = None
    active_session = session
    try:
        if render_js:
            page = acquire_rendered_page(
                url,
                headers=headers,
                verify_ssl=verify_ssl,
                allow_private_network=allow_private_network,
                max_html_bytes=max_html_bytes,
                storage_state=storage_state,
            )
        else:
            if active_session is None:
                owned_session = get_session(verify_ssl=verify_ssl)
                active_session = owned_session
            elif not verify_ssl:
                disable_ssl_verification(active_session)
            page = acquire_http_page(
                url,
                session=active_session,
                headers=headers,
                network_policy=network_policy,
                allow_private_network=allow_private_network,
                max_html_bytes=max_html_bytes,
            )
        document = PagePipeline().convert(
            page,
            content_mode=content_mode,
            selector=selector,
            include_metadata=include_metadata,
            download_images=download_images,
            output_dir=Path(output_dir) if output_dir is not None else None,
            images_dir=images_dir,
            session=active_session,
            allow_private_network=allow_private_network,
        )
        logger.info("Successfully converted HTML from %s to Markdown.", page.final_url)
        return document.markdown
    except (AcquisitionFailure, ConversionFailure) as error:
        logger.error("%s", error)
        return None
    finally:
        if owned_session is not None:
            owned_session.close()


def html_content_to_markdown(
    html_content,
    base_url,
    session=None,
    content_mode=ContentMode.FULL,
    selector=None,
    download_images=False,
    output_dir=None,
    images_dir="images",
    include_metadata=False,
    allow_private_network=False,
):
    """Convert an already-acquired HTML document through the shared pipeline."""
    if not html_content or not html_content.strip():
        logger.warning("Empty HTML response from %s", base_url)
        return None
    page = AcquiredPage(
        requested_url=base_url,
        final_url=base_url,
        html=html_content,
        status_code=None,
        headers={},
        media_type="text/html",
        charset="utf-8",
        source_path=(
            Path(base_url.removeprefix("file://"))
            if base_url.startswith("file://")
            else None
        ),
    )
    try:
        return (
            PagePipeline()
            .convert(
                page,
                content_mode=content_mode,
                selector=selector,
                include_metadata=include_metadata,
                download_images=download_images,
                output_dir=Path(output_dir) if output_dir is not None else None,
                images_dir=images_dir,
                session=session,
                allow_private_network=allow_private_network,
            )
            .markdown
        )
    except ConversionFailure:
        raise


def local_html_to_markdown(
    file_path,
    content_mode=ContentMode.FULL,
    selector=None,
    download_images=False,
    output_dir=None,
    images_dir="images",
    verify_ssl=True,
    include_metadata=False,
    allow_private_network=False,
):
    """Acquire one local UTF-8 HTML file and return Markdown if successful."""
    asset_session: requests.Session | None = None
    try:
        page = acquire_local_page(file_path)
        if download_images:
            asset_session = get_session(verify_ssl=verify_ssl)
        return (
            PagePipeline()
            .convert(
                page,
                content_mode=content_mode,
                selector=selector,
                include_metadata=include_metadata,
                download_images=download_images,
                output_dir=Path(output_dir) if output_dir is not None else None,
                images_dir=images_dir,
                session=asset_session,
                allow_private_network=allow_private_network,
            )
            .markdown
        )
    except AcquisitionFailure as error:
        logger.error("%s", error)
        return None
    finally:
        if asset_session is not None:
            asset_session.close()
