"""Central redaction helpers for diagnostics."""

import logging
import re
from collections.abc import Mapping


REDACTED = "[REDACTED]"
SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
    "access_token",
    "refresh_token",
    "session_token",
    "password",
    "client_secret",
}
PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)(authorization|proxy-authorization|set-cookie|cookie|x-api-key)"
        r"(\s*[:=]\s*)([^\s,;}]+)"
    ),
    re.compile(
        r"(?i)(['\"]?(?:access_token|refresh_token|session_token|password|client_secret)"
        r"['\"]?\s*[:=]\s*['\"]?)([^'\"\s,;}]+)"
    ),
    re.compile(r"(?i)([?&](?:token|access_token|key|password|secret|session)=)[^&#\s]+"),
)


def redact_text(value) -> str:
    """Redact common credential forms from arbitrary diagnostic text."""
    text = PATTERNS[0].sub(f"Bearer {REDACTED}", str(value))
    for pattern in PATTERNS[1:]:
        text = pattern.sub(
            lambda match: (
                f"{match.group(1)}{match.group(2)}{REDACTED}"
                if match.lastindex == 3
                else f"{match.group(1)}{REDACTED}"
            ),
            text,
        )
    return text


def redact_mapping(values) -> dict:
    """Copy a mapping while replacing values of credential-bearing keys."""
    if not isinstance(values, Mapping):
        return {}
    return {
        key: REDACTED if str(key).lower() in SENSITIVE_KEYS else redact_text(value)
        for key, value in values.items()
    }


class RedactingFilter(logging.Filter):
    """Sanitize each formatted log message before a handler emits it."""

    def filter(self, record):
        record.msg = redact_text(record.getMessage())
        record.args = ()
        return True


def get_redacting_logger(name: str) -> logging.Logger:
    """Return a logger that sanitizes records before propagation."""
    logger = logging.getLogger(name)
    if not any(isinstance(item, RedactingFilter) for item in logger.filters):
        logger.addFilter(RedactingFilter())
    return logger
