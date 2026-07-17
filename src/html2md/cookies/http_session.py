"""HTTP session construction independent of cookie-source acquisition."""

from __future__ import annotations

from html2md.cookies.replay import ScopedCookieSession, _ScopedCookiePolicy
from html2md.network.header_manager import HeaderManager
from html2md.utils.redaction import get_redacting_logger


logger = get_redacting_logger("session_manager")
_insecure_warning_emitted = False


def disable_ssl_verification(session):
    """Disable certificate verification after an explicit caller opt-in."""
    global _insecure_warning_emitted
    session.verify = False

    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    if not _insecure_warning_emitted:
        logger.warning(
            "SSL certificate verification is DISABLED (--insecure). "
            "Connections can be intercepted; only use this with hosts you trust "
            "(e.g. internal servers with self-signed certificates)."
        )
        _insecure_warning_emitted = True
    return session


def get_session(verify_ssl=True):
    """Return a new cookie-scope-aware requests session."""
    session = ScopedCookieSession()
    session.cookies.set_policy(_ScopedCookiePolicy())
    session.headers.update(HeaderManager().get_headers(""))
    if not verify_ssl:
        disable_ssl_verification(session)
    logger.info("New session initialized with default headers.")
    return session


def reset_session(session):
    """Close a session and replace it while preserving verification policy."""
    verify = getattr(session, "verify", True)
    try:
        session.close()
        logger.info("Session closed successfully.")
    except Exception as error:
        logger.warning("Error while closing session: %s", error)
    new_session = get_session(verify_ssl=verify is not False)
    new_session.verify = verify
    logger.info("New session initialized after reset.")
    return new_session
