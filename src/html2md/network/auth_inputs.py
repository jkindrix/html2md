"""Validated file inputs for target-site authentication state."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

MAX_AUTH_FILE_BYTES = 256 * 1024
FORBIDDEN_REQUEST_HEADERS = {
    "connection",
    "content-length",
    "host",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _load_private_json(path: Path) -> Any:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise ValueError(f"Authentication input must be a regular file: {candidate}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
        with os.fdopen(descriptor, "rb") as auth_file:
            metadata = os.fstat(auth_file.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(
                    f"Authentication input must be a regular file: {candidate}"
                )
            if metadata.st_size > MAX_AUTH_FILE_BYTES:
                raise ValueError(
                    f"Authentication input exceeds {MAX_AUTH_FILE_BYTES} bytes: "
                    f"{candidate}"
                )
            if os.name == "posix" and metadata.st_mode & 0o077:
                raise ValueError(
                    f"Authentication input must be owner-only (chmod 600): {candidate}"
                )
            contents = auth_file.read(MAX_AUTH_FILE_BYTES + 1)
        if len(contents) > MAX_AUTH_FILE_BYTES:
            raise ValueError(
                f"Authentication input exceeds {MAX_AUTH_FILE_BYTES} bytes: {candidate}"
            )
        return json.loads(contents.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Authentication input is not valid UTF-8 JSON: {candidate}"
        ) from error


def load_private_headers(path: Path) -> dict[str, str]:
    """Return caller-supplied request headers from an owner-only JSON object."""
    payload = _load_private_json(path)
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Header input must be a non-empty JSON object")
    headers: dict[str, str] = {}
    for raw_name, raw_value in payload.items():
        if not isinstance(raw_name, str) or not isinstance(raw_value, str):
            raise ValueError("Header names and values must be strings")
        name = raw_name.strip()
        if (
            not name
            or any(character in name for character in "\r\n:")
            or "\r" in raw_value
            or "\n" in raw_value
        ):
            raise ValueError("Header input contains an invalid name or value")
        if name.casefold() in FORBIDDEN_REQUEST_HEADERS:
            raise ValueError(f"Header input cannot override transport header: {name}")
        headers[name] = raw_value
    return headers


def load_storage_state(path: Path) -> dict[str, Any]:
    """Load private Playwright state once so the browser cannot reopen a replacement."""
    payload = _load_private_json(path)
    if not isinstance(payload, dict):
        raise ValueError("Browser storage state must be a JSON object")
    cookies = payload.get("cookies", [])
    origins = payload.get("origins", [])
    if not isinstance(cookies, list) or not isinstance(origins, list):
        raise ValueError("Browser storage state requires cookie and origin arrays")
    return payload
