"""Private, redacting diagnostic-log configuration."""

from __future__ import annotations

import logging
import os
import stat
import sys
from collections.abc import Mapping
from io import TextIOWrapper
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import cast

from grab2md.utils.redaction import RedactingFilter, get_redacting_logger

try:
    from pythonjsonlogger import json as jsonlogger

    HAS_JSON_LOGGER = True
except ImportError:
    HAS_JSON_LOGGER = False


def default_log_file(
    *,
    platform: str | None = None,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return the conventional per-user application log path."""
    platform = platform or sys.platform
    home = Path.home() if home is None else Path(home)
    environ = os.environ if environ is None else environ
    if platform == "win32":
        root = Path(environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        return root / "grab2md" / "Logs" / "grab2md.log"
    if platform == "darwin":
        return home / "Library" / "Logs" / "grab2md" / "grab2md.log"
    state_root = Path(environ.get("XDG_STATE_HOME", str(home / ".local" / "state")))
    return state_root / "grab2md" / "grab2md.log"


DEFAULT_LOG_FILE = str(default_log_file())
DEFAULT_LOG_DIR = str(Path(DEFAULT_LOG_FILE).parent)
LOG_FILE = str(Path(os.getenv("GRAB2MD_LOG_PATH", DEFAULT_LOG_FILE)).expanduser())
LOG_LEVEL = os.getenv("GRAB2MD_LOG_LEVEL", "WARNING").upper()
ENABLE_JSON_LOGGING = (
    os.getenv("GRAB2MD_JSON_LOGGING", "false").lower() == "true" and HAS_JSON_LOGGER
)


def _private_log_stream(
    filename: str,
    *,
    mode: str,
    encoding: str | None,
    errors: str | None,
) -> TextIOWrapper:
    """Open one regular log file without an ambient-permissions window."""
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= os.O_APPEND if "a" in mode else os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(filename, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError(f"Diagnostic log must be a regular file: {filename}")
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
        return cast(
            TextIOWrapper,
            os.fdopen(
                descriptor,
                mode,
                encoding=encoding,
                errors=errors,
            ),
        )
    except BaseException:
        os.close(descriptor)
        raise


def _secure_existing_log(filename: str) -> None:
    """Reject non-regular log-family entries and make regular files private."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(filename, flags)
    except FileNotFoundError:
        return
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError(f"Diagnostic log must be a regular file: {filename}")
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


class PrivateRotatingFileHandler(RotatingFileHandler):
    """Rotating handler whose current file is owner-only on every open."""

    def _open(self) -> TextIOWrapper:
        return _private_log_stream(
            self.baseFilename,
            mode=self.mode,
            encoding=self.encoding,
            errors=self.errors,
        )

    def secure_family(self) -> None:
        """Apply the private-file contract to current and retained logs."""
        for index in range(self.backupCount + 1):
            suffix = f".{index}" if index else ""
            _secure_existing_log(f"{self.baseFilename}{suffix}")

    def doRollover(self) -> None:
        """Rotate only a validated log family and secure every result."""
        self.secure_family()
        super().doRollover()
        self.secure_family()


class PrivateFileHandler(logging.FileHandler):
    """Non-rotating owner-only handler for an explicit debug log."""

    def _open(self) -> TextIOWrapper:
        return _private_log_stream(
            self.baseFilename,
            mode=self.mode,
            encoding=self.encoding,
            errors=self.errors,
        )


def _ensure_log_directory(path: Path, *, application_default: bool) -> None:
    existed = path.exists()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix" and (application_default or not existed):
        path.chmod(0o700)


def _close_handlers(logger: logging.Logger) -> None:
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def setup_logging(
    console_output: bool = True, debug_file: str | None = None
) -> logging.Logger:
    """Configure private rotating logs and redacted console diagnostics."""
    log_path = Path(LOG_FILE)
    default_path = Path(DEFAULT_LOG_FILE)
    _ensure_log_directory(
        log_path.parent,
        application_default=log_path == default_path,
    )

    logger = get_redacting_logger("grab2md")
    logger.propagate = False
    _close_handlers(logger)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.WARNING))
    redacting_filter = RedactingFilter()

    if console_output:
        console_handler = logging.StreamHandler()
        console_formatter: logging.Formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        if ENABLE_JSON_LOGGING:
            console_formatter = jsonlogger.JsonFormatter(
                "%(asctime)s %(name)s %(levelname)s %(message)s"
            )
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(redacting_filter)
        logger.addHandler(console_handler)
    else:
        error_handler = logging.StreamHandler()
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        error_handler.addFilter(redacting_filter)
        logger.addHandler(error_handler)

    file_handler = PrivateRotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=3
    )
    file_handler.secure_family()
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    file_handler.addFilter(redacting_filter)
    logger.addHandler(file_handler)

    if debug_file:
        debug_path = Path(debug_file).expanduser()
        _ensure_log_directory(debug_path.parent, application_default=False)
        debug_handler = PrivateFileHandler(debug_path, mode="w")
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        debug_handler.addFilter(redacting_filter)
        logger.addHandler(debug_handler)
        logger.debug("Debug logging enabled to: %s", debug_path)

    return logger
