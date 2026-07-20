"""Owner-private lifecycle for copied browser cookie databases."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def copy_cookie_database(
    source_path: str | Path,
) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    """Stage a browser database in unpredictable owner-only storage."""
    temp_directory = tempfile.TemporaryDirectory(prefix="grab2md-cookies-")
    if os.name == "posix":
        os.chmod(temp_directory.name, 0o700)
    destination = Path(temp_directory.name) / "cookies.sqlite"
    try:
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with open(source_path, "rb") as source, os.fdopen(fd, "wb") as target:
            shutil.copyfileobj(source, target)
        if os.name == "posix":
            os.chmod(destination, 0o600)
        return temp_directory, destination
    except BaseException:
        temp_directory.cleanup()
        raise


def snapshot_cookie_database(
    source_path: str | Path,
) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    """Create a consistent SQLite snapshot, including committed WAL records."""
    temp_directory, destination = copy_cookie_database(source_path)
    source_connection: sqlite3.Connection | None = None
    destination_connection: sqlite3.Connection | None = None
    try:
        source_uri = f"{Path(source_path).resolve().as_uri()}?mode=ro"
        source_connection = sqlite3.connect(source_uri, uri=True)
        destination_connection = sqlite3.connect(str(destination))
        source_connection.backup(destination_connection)
        destination_connection.commit()
        if os.name == "posix":
            os.chmod(destination, 0o600)
        return temp_directory, destination
    except BaseException:
        temp_directory.cleanup()
        raise
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            source_connection.close()


@contextmanager
def copied_cookie_connection(
    source_path: str | Path,
) -> Iterator[sqlite3.Connection]:
    """Open a consistent disposable snapshot and release every resource."""
    temp_directory, copied_path = snapshot_cookie_database(source_path)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(str(copied_path))
        yield connection
    finally:
        try:
            if connection is not None:
                connection.close()
        finally:
            temp_directory.cleanup()
