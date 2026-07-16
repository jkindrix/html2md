"""Owner-only atomic persistence for credentials and other secrets."""

import os
import tempfile
from pathlib import Path


def atomic_write_private_text(file_path: Path, content: str) -> None:
    """Atomically write text with 0600 file and 0700 directory modes on POSIX."""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        os.chmod(file_path.parent, 0o700)
    fd, temp_path = tempfile.mkstemp(
        dir=file_path.parent,
        prefix=f".{file_path.stem}.",
        suffix=".tmp",
    )
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, file_path)
        if os.name == "posix":
            os.chmod(file_path, 0o600)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
