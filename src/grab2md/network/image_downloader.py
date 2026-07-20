"""Policy-enforced image acquisition for HTML conversion."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import requests
from requests import Session
from rich.progress import Progress, TaskID

from grab2md.network.safe_http import (
    DestinationPolicy,
    UnsafeNetworkTarget,
    guarded_stream,
)
from grab2md.utils.path_safety import contained_output_file, contained_path
from grab2md.utils.redaction import get_redacting_logger

__all__ = ["ImageDownloader", "UnsafeImageSource"]

logger = get_redacting_logger(__name__)


class UnsafeImageSource(ValueError):
    """Raised when an image source violates the acquisition policy."""


class ImageDownloader:
    """Download public web images and copy explicitly rooted local images."""

    ALLOWED_REMOTE_SCHEMES = {"http", "https"}
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
        scheduler: Any = None,
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
        self.scheduler = scheduler
        self.total_downloaded_bytes = 0
        self.downloaded_images: Dict[str, str] = {}

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

    def _destination_directory(self, output_dir: Path) -> tuple[Path, Path]:
        output_root = Path(output_dir).resolve()
        images_path = contained_path(output_root, self.images_dir)
        images_path.mkdir(parents=True, exist_ok=True)
        images_path = contained_path(output_root, images_path)
        return output_root, images_path

    def _destination_name(
        self, url: str, mime_type: str, exists: Callable[[str], bool]
    ) -> str:
        parsed = urlparse(url)
        raw_filename = os.path.basename(unquote(parsed.path))
        name = os.path.splitext(raw_filename)[0] if raw_filename else ""
        if not name or name.startswith("."):
            name = f"image_{hashlib.sha256(url.encode()).hexdigest()[:12]}"
        name = re.sub(r"[^\w\-]", "_", name).strip("._") or "image"
        extension = self.MIME_EXTENSIONS[mime_type]
        name = name[: self.MAX_FILENAME_LENGTH - len(extension)]
        filename = f"{name}{extension}"

        counter = 1
        while exists(filename):
            suffix = f"_{counter}"
            truncated = name[: self.MAX_FILENAME_LENGTH - len(extension) - len(suffix)]
            filename = f"{truncated}{suffix}{extension}"
            counter += 1
        return filename

    def _commit_staged(
        self, staged_path: Path, output_dir: Path, url: str, mime_type: str
    ) -> Path:
        """Finalize a staged image against an anchored destination directory."""
        output_root, images_path = self._destination_directory(output_dir)
        if os.name == "posix":
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            directory_fd = os.open(images_path, flags)
            try:
                filename = self._destination_name(
                    url,
                    mime_type,
                    lambda candidate: self._entry_exists(directory_fd, candidate),
                )
                os.replace(staged_path, filename, dst_dir_fd=directory_fd)
            finally:
                os.close(directory_fd)
            return contained_output_file(output_root, self.images_dir, filename)

        # Windows has no portable no-follow directory handle for os.replace.
        # Revalidate immediately before the atomic replacement.
        output_root, images_path = self._destination_directory(output_dir)
        filename = self._destination_name(
            url, mime_type, lambda candidate: (images_path / candidate).exists()
        )
        destination = contained_output_file(output_root, self.images_dir, filename)
        os.replace(staged_path, destination)
        return destination

    @staticmethod
    def _entry_exists(directory_fd: int, filename: str) -> bool:
        try:
            os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return True

    def _stage_chunks(self, chunks, output_dir: Path) -> tuple[Path, int]:
        output_root = Path(output_dir).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.NamedTemporaryFile(
            mode="wb", prefix=".grab2md-image-", dir=output_root, delete=False
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
        staged_path: Optional[Path] = None
        try:
            policy = DestinationPolicy(allow_private=self.allow_private_network)
            with guarded_stream(
                self.session,
                "GET",
                url,
                policy=policy,
                timeout=self.timeout,
                max_redirects=self.max_redirects,
                request_scheduler=self.scheduler,
            ) as response:
                response.raise_for_status()
                declared_type = response.headers.get("Content-Type", "")
                if self._content_type(declared_type) not in self.MIME_EXTENSIONS:
                    raise UnsafeImageSource(
                        "Unsupported image Content-Type: "
                        f"{self._content_type(declared_type) or 'missing'}"
                    )
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        stated_size = int(content_length)
                    except ValueError as error:
                        raise UnsafeImageSource(
                            "Invalid image Content-Length"
                        ) from error
                    if stated_size < 0 or stated_size > self.max_file_bytes:
                        raise UnsafeImageSource("Image exceeds the per-file byte limit")
                    if self.total_downloaded_bytes + stated_size > self.max_total_bytes:
                        raise UnsafeImageSource(
                            "Images exceed the aggregate byte limit"
                        )

                staged_path, byte_count = self._stage_chunks(
                    response.iter_content(chunk_size=8192), output_dir
                )
            mime_type = self._verify_image(staged_path, declared_type)
            destination = self._commit_staged(
                staged_path, output_dir, response.url, mime_type
            )
            staged_path = None
            self.total_downloaded_bytes += byte_count
            return destination
        except UnsafeNetworkTarget as error:
            raise UnsafeImageSource(str(error)) from error
        finally:
            if staged_path is not None:
                staged_path.unlink(missing_ok=True)

    def _acquire_local(self, url: str, output_dir: Path) -> Path:
        if self.local_root is None:
            raise UnsafeImageSource("Local images are disabled for this conversion")
        parsed = urlparse(url)
        if parsed.netloc not in {"", "localhost"}:
            raise UnsafeImageSource("Remote file URL authorities are not allowed")
        source = Path(url2pathname(parsed.path)).resolve(strict=True)
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
            destination = self._commit_staged(staged_path, output_dir, url, mime_type)
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
