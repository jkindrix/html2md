"""Policy-enforced image acquisition for HTML conversion."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from requests import Response, Session
from rich.progress import Progress, TaskID

from html2md.utils.path_safety import contained_output_file, contained_path
from html2md.network.safe_http import (
    DestinationPolicy,
    PinnedHttpClient,
    SAFE_CROSS_ORIGIN_HEADERS,
    UnsafeNetworkTarget,
    _PinnedAddressAdapter,
)

__all__ = ["ImageDownloader", "UnsafeImageSource", "_PinnedAddressAdapter"]

logger = logging.getLogger("html2md")


class UnsafeImageSource(ValueError):
    """Raised when an image source violates the acquisition policy."""


@dataclass
class _PinnedExchange:
    response: Response
    session: Optional[Session]


class ImageDownloader:
    """Download public web images and copy explicitly rooted local images."""

    ALLOWED_REMOTE_SCHEMES = {"http", "https"}
    REDIRECT_STATUSES = {301, 302, 303, 307, 308}
    MIME_EXTENSIONS = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "image/x-icon": ".ico",
        "image/vnd.microsoft.icon": ".ico",
        "image/avif": ".avif",
    }
    MAX_FILENAME_LENGTH = 200

    def __init__(
        self,
        session: Optional[Session] = None,
        images_dir: str = "images",
        *,
        local_root: Optional[Path] = None,
        max_file_bytes: int = 10 * 1024 * 1024,
        max_total_bytes: int = 50 * 1024 * 1024,
        max_redirects: int = 5,
        timeout: int = 30,
        allow_private_network: bool = False,
    ):
        """Initialize with explicit local and remote acquisition limits."""
        if max_file_bytes <= 0 or max_total_bytes <= 0:
            raise ValueError("Image byte limits must be positive")
        if max_redirects < 0:
            raise ValueError("max_redirects cannot be negative")

        self.session = session or requests.Session()
        self.images_dir = images_dir
        self.local_root = Path(local_root).resolve() if local_root is not None else None
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.max_redirects = max_redirects
        self.timeout = timeout
        self.allow_private_network = allow_private_network
        self.total_downloaded_bytes = 0
        self.downloaded_images: Dict[str, str] = {}

    def extract_image_urls(self, html_content: str, base_url: str) -> List[str]:
        """Extract absolute image URLs from image and inline-style attributes."""
        soup = BeautifulSoup(html_content, "html.parser")
        image_urls = []

        for img in soup.find_all("img"):
            if not isinstance(img, Tag):
                continue
            src = self._attribute_text(img, "src").strip()
            if src:
                image_urls.append(urljoin(base_url, src))

            srcset = self._attribute_text(img, "srcset")
            for part in srcset.split(",") if srcset else ():
                url_part = part.strip().split()[0] if part.strip() else ""
                if url_part:
                    image_urls.append(urljoin(base_url, url_part))

        style_pattern = re.compile(
            r"background-image:\s*url\([\"']?([^\"'()]+)[\"']?\)", re.IGNORECASE
        )
        for element in soup.find_all(style=True):
            if not isinstance(element, Tag):
                continue
            for match in style_pattern.finditer(self._attribute_text(element, "style")):
                image_urls.append(urljoin(base_url, match.group(1)))

        return list(dict.fromkeys(image_urls))

    @staticmethod
    def _attribute_text(tag: Tag, name: str) -> str:
        """Normalize a Beautiful Soup attribute to text."""
        value = tag.attrs.get(name)
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return " ".join(str(part) for part in value)
        return str(value)

    @staticmethod
    def _content_type(value: str) -> str:
        return value.split(";", 1)[0].strip().lower()

    @staticmethod
    def _detected_mime(prefix: bytes) -> Optional[str]:
        if prefix.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if prefix.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP":
            return "image/webp"
        if prefix.startswith(b"BM"):
            return "image/bmp"
        if prefix.startswith(b"\x00\x00\x01\x00"):
            return "image/x-icon"
        if prefix[4:8] == b"ftyp" and prefix[8:12] in {b"avif", b"avis"}:
            return "image/avif"
        return None

    @classmethod
    def _verify_image(cls, path: Path, declared_type: Optional[str] = None) -> str:
        with path.open("rb") as image_file:
            detected = cls._detected_mime(image_file.read(32))
        if detected is None:
            raise UnsafeImageSource("Content does not match a supported image format")

        if declared_type:
            declared = cls._content_type(declared_type)
            if declared not in cls.MIME_EXTENSIONS:
                raise UnsafeImageSource(
                    f"Unsupported image Content-Type: {declared or 'missing'}"
                )
            if cls.MIME_EXTENSIONS[declared] != cls.MIME_EXTENSIONS[detected]:
                raise UnsafeImageSource(
                    f"Image Content-Type {declared} does not match detected {detected}"
                )
        return detected

    @classmethod
    def _validate_remote_url(cls, url: str) -> List[str]:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in cls.ALLOWED_REMOTE_SCHEMES:
            raise UnsafeImageSource(
                f"Unsupported remote image scheme: {parsed.scheme or 'missing'}"
            )
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeImageSource("Image URLs containing credentials are not allowed")
        try:
            port = parsed.port
        except ValueError as error:
            raise UnsafeImageSource("Image URL contains an invalid port") from error
        del port
        try:
            return list(DestinationPolicy().addresses_for(url))
        except UnsafeNetworkTarget as error:
            raise UnsafeImageSource(str(error)) from error

    def _direct_session(
        self, address: str, *, retain_credentials: bool = True
    ) -> Session:
        """Clone request identity into a direct, address-pinned session."""
        client = PinnedHttpClient(self.session, DestinationPolicy())
        client._mount(address)
        if not retain_credentials:
            client.session.headers = requests.structures.CaseInsensitiveDict(
                {
                    name: value
                    for name, value in client.session.headers.items()
                    if name.casefold() in SAFE_CROSS_ORIGIN_HEADERS
                }
            )
            client.session.auth = None
        return client.session

    def _send_to_address(
        self, url: str, address: str, *, retain_credentials: bool = True
    ) -> _PinnedExchange:
        direct = self._direct_session(address, retain_credentials=retain_credentials)
        try:
            response = direct.get(
                url,
                timeout=self.timeout,
                stream=True,
                allow_redirects=False,
            )
            return _PinnedExchange(response=response, session=direct)
        except BaseException:
            direct.close()
            raise

    def _request_remote(self, url: str) -> tuple[Response, str, Optional[Session]]:
        current_url = url
        previous_url: Optional[str] = None
        retain_credentials = True
        for redirect_count in range(self.max_redirects + 1):
            if self.allow_private_network:
                try:
                    addresses = list(
                        DestinationPolicy(allow_private=True).addresses_for(current_url)
                    )
                except UnsafeNetworkTarget as error:
                    raise UnsafeImageSource(str(error)) from error
            else:
                addresses = self._validate_remote_url(current_url)
            exchange: Optional[_PinnedExchange] = None
            last_connection_error: Optional[requests.RequestException] = None
            for address in addresses:
                try:
                    if previous_url is not None and DestinationPolicy._origin(
                        previous_url
                    ) != DestinationPolicy._origin(current_url):
                        retain_credentials = False
                    exchange = self._send_to_address(
                        current_url,
                        address,
                        retain_credentials=retain_credentials,
                    )
                    break
                except (requests.ConnectionError, requests.Timeout) as error:
                    last_connection_error = error
            if exchange is None:
                if last_connection_error is not None:
                    raise last_connection_error
                raise UnsafeImageSource("Image host has no usable public address")

            response = exchange.response
            if response.status_code not in self.REDIRECT_STATUSES:
                try:
                    response.raise_for_status()
                except BaseException:
                    response.close()
                    if exchange.session is not None:
                        exchange.session.close()
                    raise
                return response, current_url, exchange.session

            location = response.headers.get("Location")
            response.close()
            if exchange.session is not None:
                exchange.session.close()
            if not location:
                raise UnsafeImageSource("Image redirect has no Location header")
            if redirect_count == self.max_redirects:
                raise UnsafeImageSource("Image redirect limit exceeded")
            previous_url = current_url
            current_url = urljoin(current_url, location)
        raise UnsafeImageSource("Image redirect limit exceeded")

    def _destination(self, output_dir: Path, url: str, mime_type: str) -> Path:
        output_root = Path(output_dir).resolve()
        images_path = contained_path(output_root, self.images_dir)
        images_path.mkdir(parents=True, exist_ok=True)
        # Recheck after creation to catch a concurrently substituted symlink.
        images_path = contained_path(output_root, images_path)

        parsed = urlparse(url)
        raw_filename = os.path.basename(unquote(parsed.path))
        name = os.path.splitext(raw_filename)[0] if raw_filename else ""
        if not name or name.startswith("."):
            name = f"image_{hashlib.sha256(url.encode()).hexdigest()[:12]}"
        name = re.sub(r"[^\w\-]", "_", name).strip("._") or "image"
        extension = self.MIME_EXTENSIONS[mime_type]
        name = name[: self.MAX_FILENAME_LENGTH - len(extension)]
        filename = f"{name}{extension}"

        destination = contained_output_file(output_root, self.images_dir, filename)
        counter = 1
        while destination.exists():
            suffix = f"_{counter}"
            truncated = name[: self.MAX_FILENAME_LENGTH - len(extension) - len(suffix)]
            destination = contained_output_file(
                output_root, self.images_dir, f"{truncated}{suffix}{extension}"
            )
            counter += 1
        return destination

    def _stage_chunks(self, chunks, output_dir: Path) -> tuple[Path, int]:
        output_root = Path(output_dir).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.NamedTemporaryFile(
            mode="wb", prefix=".html2md-image-", dir=output_root, delete=False
        )
        staged_path = Path(temporary.name)
        byte_count = 0
        try:
            with temporary:
                for chunk in chunks:
                    if not chunk:
                        continue
                    byte_count += len(chunk)
                    if byte_count > self.max_file_bytes:
                        raise UnsafeImageSource("Image exceeds the per-file byte limit")
                    if self.total_downloaded_bytes + byte_count > self.max_total_bytes:
                        raise UnsafeImageSource(
                            "Images exceed the aggregate byte limit"
                        )
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            return staged_path, byte_count
        except BaseException:
            staged_path.unlink(missing_ok=True)
            raise

    def _acquire_remote(self, url: str, output_dir: Path) -> Path:
        response, final_url, direct_session = self._request_remote(url)
        staged_path: Optional[Path] = None
        try:
            declared_type = response.headers.get("Content-Type", "")
            if self._content_type(declared_type) not in self.MIME_EXTENSIONS:
                raise UnsafeImageSource(
                    f"Unsupported image Content-Type: {self._content_type(declared_type) or 'missing'}"
                )
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    stated_size = int(content_length)
                except ValueError as error:
                    raise UnsafeImageSource("Invalid image Content-Length") from error
                if stated_size < 0 or stated_size > self.max_file_bytes:
                    raise UnsafeImageSource("Image exceeds the per-file byte limit")
                if self.total_downloaded_bytes + stated_size > self.max_total_bytes:
                    raise UnsafeImageSource("Images exceed the aggregate byte limit")

            staged_path, byte_count = self._stage_chunks(
                response.iter_content(chunk_size=8192), output_dir
            )
            mime_type = self._verify_image(staged_path, declared_type)
            destination = self._destination(output_dir, final_url, mime_type)
            os.replace(staged_path, destination)
            staged_path = None
            self.total_downloaded_bytes += byte_count
            return destination
        finally:
            response.close()
            if direct_session is not None:
                direct_session.close()
            if staged_path is not None:
                staged_path.unlink(missing_ok=True)

    def _acquire_local(self, url: str, output_dir: Path) -> Path:
        if self.local_root is None:
            raise UnsafeImageSource("Local images are disabled for this conversion")
        parsed = urlparse(url)
        if parsed.netloc not in {"", "localhost"}:
            raise UnsafeImageSource("Remote file URL authorities are not allowed")
        source = Path(unquote(parsed.path)).resolve(strict=True)
        try:
            source.relative_to(self.local_root)
        except ValueError as error:
            raise UnsafeImageSource(
                "Local image escapes the HTML document directory"
            ) from error
        if not source.is_file():
            raise UnsafeImageSource("Local image source is not a regular file")

        with source.open("rb") as source_file:
            staged_path, byte_count = self._stage_chunks(
                iter(lambda: source_file.read(8192), b""), output_dir
            )
        try:
            mime_type = self._verify_image(staged_path)
            destination = self._destination(output_dir, url, mime_type)
            os.replace(staged_path, destination)
            self.total_downloaded_bytes += byte_count
            return destination
        finally:
            staged_path.unlink(missing_ok=True)

    def download_image(self, url: str, output_dir: Path) -> Optional[Path]:
        """Acquire one image if it satisfies the configured source policy."""
        if url in self.downloaded_images:
            return Path(output_dir).resolve() / self.downloaded_images[url]

        try:
            scheme = urlparse(url).scheme.lower()
            if scheme == "file":
                destination = self._acquire_local(url, output_dir)
            elif scheme in self.ALLOWED_REMOTE_SCHEMES:
                destination = self._acquire_remote(url, output_dir)
            else:
                raise UnsafeImageSource(
                    f"Unsupported image scheme: {scheme or 'missing'}"
                )

            relative_path = destination.relative_to(
                Path(output_dir).resolve()
            ).as_posix()
            self.downloaded_images[url] = relative_path
            logger.debug("Acquired image: %s -> %s", url, relative_path)
            return destination
        except (
            OSError,
            RuntimeError,
            requests.RequestException,
            UnsafeImageSource,
            ValueError,
        ) as error:
            logger.warning("Skipped image %s: %s", url, error)
            return None

    def download_images(
        self,
        image_urls: List[str],
        output_dir: Path,
        progress: Optional[Progress] = None,
        task: Optional[TaskID] = None,
    ) -> Dict[str, str]:
        """Acquire multiple images within one aggregate byte budget."""
        results = {}
        total = len(image_urls)
        for index, url in enumerate(image_urls):
            if progress and task is not None:
                progress.update(
                    task,
                    advance=1,
                    description=f"Downloading images... [{index + 1}/{total}]",
                )
            local_path = self.download_image(url, output_dir)
            if local_path:
                results[url] = local_path.relative_to(
                    Path(output_dir).resolve()
                ).as_posix()
        return results

    def rewrite_image_urls(
        self,
        markdown_content: str,
        url_mapping: Dict[str, str],
        base_url: Optional[str] = None,
    ) -> str:
        """Rewrite exact downloaded image references to their local paths."""
        image_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

        def replace_url(match):
            alt_text, url = match.groups()
            local_path = url_mapping.get(url)
            if local_path is None and base_url is not None:
                local_path = url_mapping.get(urljoin(base_url, url))
            return f"![{alt_text}]({local_path})" if local_path else match.group(0)

        return image_pattern.sub(replace_url, markdown_content)

    def process_markdown_with_images(
        self,
        markdown_content: str,
        html_content: str,
        base_url: str,
        output_dir: Path,
        progress: Optional[Progress] = None,
    ) -> str:
        """Acquire discovered images and rewrite successful exact references."""
        image_urls = self.extract_image_urls(html_content, base_url)
        if not image_urls:
            return markdown_content

        task = (
            progress.add_task("Downloading images...", total=len(image_urls))
            if progress
            else None
        )
        url_mapping = self.download_images(image_urls, output_dir, progress, task)
        return self.rewrite_image_urls(markdown_content, url_mapping, base_url)
