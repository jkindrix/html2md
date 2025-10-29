"""
Atomic configuration file writer.

This module provides atomic write operations for configuration files,
ensuring that either the entire write succeeds or the original file
remains unchanged. This prevents partial writes and corruption.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict


def atomic_write_json(
    file_path: Path,
    data: Dict[str, Any],
    indent: int = 4
) -> None:
    """
    Atomically write JSON data to a file using temp-rename pattern.

    This function ensures that:
    - Either the entire write succeeds, or the original file is unchanged
    - No partial or corrupt files are left on disk
    - The operation is atomic on POSIX systems (using os.replace)
    - Works reliably across all supported platforms

    The implementation uses the standard temp-file-then-rename pattern:
    1. Create a temporary file in the same directory as the target
    2. Write all data to the temporary file
    3. Flush and fsync to ensure data is on disk
    4. Atomically rename temp file to target (replaces original)

    Args:
        file_path: Target file path where JSON will be written
        data: Dictionary to serialize as JSON
        indent: JSON indentation level for human readability (default: 4)

    Raises:
        OSError: If write operation fails (permissions, disk full, etc.)
        TypeError: If data cannot be serialized to JSON
        ValueError: If file_path is not a Path object

    Example:
        >>> config = {"domains": {}, "logging": {"level": "INFO"}}
        >>> atomic_write_json(Path("/path/to/config.json"), config)
    """
    if not isinstance(file_path, Path):
        raise ValueError(f"file_path must be a Path object, got {type(file_path)}")

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Create temp file in same directory (ensures same filesystem for atomic rename)
    fd, temp_path = tempfile.mkstemp(
        dir=file_path.parent,
        prefix=f'.{file_path.stem}.',
        suffix='.tmp'
    )

    try:
        # Write JSON data to temp file
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.flush()
            # Force write to disk (prevent data loss on crash/power failure)
            os.fsync(f.fileno())

        # Atomic rename (POSIX guarantees atomicity, Windows best-effort on Python 3.3+)
        os.replace(temp_path, file_path)

    except Exception:
        # Clean up temp file on any failure
        try:
            os.unlink(temp_path)
        except OSError:
            # Ignore errors during cleanup (temp file may not exist)
            pass
        raise
