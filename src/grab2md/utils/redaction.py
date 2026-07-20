"""Central redaction helpers for project-owned diagnostics."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from urllib.parse import unquote_plus, urlsplit, urlunsplit

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = {
    "access_key",
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_assertion",
    "client_secret",
    "code",
    "cookie",
    "credential",
    "id_token",
    "jwt",
    "key",
    "password",
    "proxy_authorization",
    "refresh_token",
    "saml_response",
    "secret",
    "session",
    "session_token",
    "set_cookie",
    "sig",
    "signature",
    "state",
    "ticket",
    "token",
    "x_api_key",
    "x_amz_credential",
    "x_amz_security_token",
    "x_amz_signature",
    "x_goog_credential",
    "x_goog_signature",
}
SENSITIVE_SUFFIXES = (
    "_access_key",
    "_api_key",
    "_auth",
    "_credential",
    "_key",
    "_password",
    "_secret",
    "_signature",
    "_token",
)
URL_PATTERN = re.compile(r"(?i)https?://[^\s<>\"']+")
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
QUOTED_COOKIE_PATTERN = re.compile(
    r"(?i)(['\"](?:set-cookie|cookie)['\"]\s*:\s*['\"])(.*?)(['\"](?:\s*[,}]))"
)
COOKIE_HEADER_PATTERN = re.compile(r"(?i)(\b(?:set-cookie|cookie)\s*[:=]\s*)([^\r\n]+)")
HEADER_PATTERN = re.compile(
    r"(?i)(authorization|proxy-authorization|x-api-key)" r"(\s*[:=]\s*)([^\s,;}]+)"
)
ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(['\"]?(?:access[_-]?token|refresh[_-]?token|session[_-]?token|"
    r"api[_-]?key|client[_-]?secret|password|signature|credential|secret|"
    r"token|code|sig|auth)['\"]?\s*[:=]\s*['\"]?)"
    r"([^'\"\s,;}&]+)"
)
QUERY_PATTERN = re.compile(
    r"(?i)([?&](?:access[_-]?token|refresh[_-]?token|session[_-]?token|"
    r"api[_-]?key|client[_-]?secret|password|signature|credential|secret|"
    r"token|code|key|sig|auth)=)[^&#\s]+"
)
STANDARD_LOG_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def is_sensitive_key(value: str) -> bool:
    """Return whether a diagnostic field name conventionally carries a secret."""
    normalized = _normalized_key(value)
    return normalized in SENSITIVE_KEYS or normalized.endswith(SENSITIVE_SUFFIXES)


def _redact_parameters(value: str) -> str:
    """Redact sensitive values in an authored query or fragment string."""
    fields = re.split(r"([&;])", value)
    redacted: list[str] = []
    for field in fields:
        if field in {"&", ";"}:
            redacted.append(field)
            continue
        raw_key, separator, _raw_value = field.partition("=")
        if separator and is_sensitive_key(unquote_plus(raw_key)):
            redacted.append(f"{raw_key}={REDACTED}")
        else:
            redacted.append(field)
    return "".join(redacted)


def _redact_url(match: re.Match[str]) -> str:
    """Redact userinfo and sensitive URL parameters without hiding the origin."""
    original = match.group(0)
    try:
        parsed = urlsplit(original)
    except ValueError:
        return original

    netloc = parsed.netloc
    if "@" in netloc:
        netloc = f"{REDACTED}@{netloc.rsplit('@', 1)[1]}"
    query = _redact_parameters(parsed.query)
    fragment = _redact_parameters(parsed.fragment)
    if (netloc, query, fragment) == (parsed.netloc, parsed.query, parsed.fragment):
        return original
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, fragment))


def redact_text(value: object) -> str:
    """Redact common credential forms from arbitrary diagnostic text."""
    text = URL_PATTERN.sub(_redact_url, str(value))
    text = BEARER_PATTERN.sub(f"Bearer {REDACTED}", text)
    text = QUOTED_COOKIE_PATTERN.sub(
        lambda match: f"{match.group(1)}{REDACTED}{match.group(3)}", text
    )
    text = COOKIE_HEADER_PATTERN.sub(lambda match: f"{match.group(1)}{REDACTED}", text)
    text = HEADER_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", text
    )
    text = ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}{REDACTED}", text)
    return QUERY_PATTERN.sub(lambda match: f"{match.group(1)}{REDACTED}", text)


def redact_mapping(values: object) -> dict[object, object]:
    """Copy a mapping while replacing credential-bearing values."""
    if not isinstance(values, Mapping):
        return {}
    return {
        key: REDACTED if is_sensitive_key(str(key)) else redact_text(value)
        for key, value in values.items()
    }


class RedactingFilter(logging.Filter):
    """Sanitize each formatted log message before a handler emits it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact_text(
                logging.Formatter().formatException(record.exc_info)
            )
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info)
        for key in record.__dict__.keys() - STANDARD_LOG_FIELDS:
            value = record.__dict__[key]
            if is_sensitive_key(key):
                record.__dict__[key] = REDACTED
            elif isinstance(value, Mapping):
                record.__dict__[key] = redact_mapping(value)
            elif isinstance(value, str):
                record.__dict__[key] = redact_text(value)
        return True


def get_redacting_logger(name: str) -> logging.Logger:
    """Return an always-redacting logger inside the project namespace."""
    normalized = name.strip().strip(".") or "grab2md"
    qualified = (
        normalized
        if normalized == "grab2md" or normalized.startswith("grab2md.")
        else f"grab2md.{normalized}"
    )
    logger = logging.getLogger(qualified)
    if not any(isinstance(item, RedactingFilter) for item in logger.filters):
        logger.addFilter(RedactingFilter())
    return logger
