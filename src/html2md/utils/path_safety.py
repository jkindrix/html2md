"""Filesystem containment helpers for generated output."""

import os
import re
from pathlib import Path
from urllib.parse import unquote


def safe_path_segment(value: str) -> str:
    """Return a non-special, separator-free path segment."""
    decoded = unquote(value).strip()
    sanitized = re.sub(r"[^\w.-]", "_", decoded, flags=re.UNICODE)
    sanitized = sanitized.strip(". ")
    return sanitized if sanitized not in {"", ".", ".."} else "_"


def contained_path(root, candidate) -> Path:
    """Resolve a candidate and reject paths outside root, including symlinks."""
    root_path = Path(root).expanduser().resolve()
    candidate_path = Path(candidate).expanduser()
    if not candidate_path.is_absolute():
        candidate_path = root_path / candidate_path
    resolved = candidate_path.resolve(strict=False)
    try:
        resolved.relative_to(root_path)
    except ValueError as error:
        raise ValueError(f"Output path escapes configured root: {resolved}") from error
    return resolved


def contained_output_file(root, directory, filename) -> Path:
    """Build a generated output file and enforce final root containment."""
    safe_filename = os.path.basename(filename)
    if safe_filename in {"", ".", ".."} or safe_filename != filename:
        raise ValueError(f"Unsafe output filename: {filename!r}")
    return contained_path(root, Path(directory) / safe_filename)
