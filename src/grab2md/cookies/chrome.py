"""Fail-closed Chrome cookie extraction."""

from __future__ import annotations

import base64
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from Cryptodome.Cipher import AES

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

from grab2md.cookies.browser_paths import get_browser_cookie_path
from grab2md.cookies.database import copied_cookie_connection
from grab2md.cookies.errors import CookieSourceError
from grab2md.cookies.replay import (
    CookieRecord,
    cookie_domain_matches,
    normalize_hostname,
)
from grab2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger(__name__)


def get_chrome_encryption_key() -> bytes:
    """Return a supported Chrome key or fail before cookie decryption."""
    if not HAS_CRYPTO:
        raise ImportError(
            "pycryptodomex is required for browser cookie extraction. Install "
            "grab2md with its declared dependencies."
        )

    if sys.platform == "win32":
        import win32crypt

        try:
            local_state_path = (
                Path.home()
                / "AppData"
                / "Local"
                / "Google"
                / "Chrome"
                / "User Data"
                / "Local State"
            )
            with local_state_path.open("r", encoding="utf-8") as state_file:
                local_state = json.load(state_file)

            encoded_key = local_state["os_crypt"]["encrypted_key"]
            encrypted_key = base64.b64decode(encoded_key, validate=True)
            if not encrypted_key.startswith(b"DPAPI"):
                raise CookieSourceError(
                    "Chrome Local State uses an unsupported Windows key format"
                )
            return win32crypt.CryptUnprotectData(
                encrypted_key[5:], None, None, None, 0
            )[1]
        except CookieSourceError:
            raise
        except Exception as error:
            raise CookieSourceError(
                "Could not retrieve Chrome's Windows DPAPI encryption key; "
                "use an owner-private exported cookie JSON file"
            ) from error

    if sys.platform == "darwin":
        raise CookieSourceError(
            "Automatic Chrome cookie decryption is unavailable on macOS because "
            "grab2md does not access the Chrome Safe Storage Keychain secret. "
            "Export cookies to an owner-private JSON file instead."
        )
    if sys.platform.startswith("linux"):
        raise CookieSourceError(
            "Automatic Chrome cookie decryption is unavailable on Linux because "
            "grab2md does not access the desktop keyring. Export cookies to an "
            "owner-private JSON file instead."
        )
    raise CookieSourceError(
        f"Automatic Chrome cookie decryption is unsupported on {sys.platform}; "
        "use an owner-private exported cookie JSON file"
    )


def decrypt_chrome_cookie(encrypted_value: bytes, key: bytes) -> str:
    """Decrypt a recognized Chrome cookie representation."""
    if not HAS_CRYPTO:
        raise ImportError(
            "pycryptodomex is required for browser cookie extraction. Install "
            "grab2md with its declared dependencies."
        )

    try:
        if encrypted_value.startswith(b"v20"):
            raise CookieSourceError(
                "Chrome app-bound (v20) cookie encryption is unsupported; use an "
                "owner-private exported cookie JSON file"
            )
        if encrypted_value.startswith((b"v10", b"v11")):
            nonce = encrypted_value[3:15]
            ciphertext = encrypted_value[15:-16]
            tag = encrypted_value[-16:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            return cipher.decrypt_and_verify(ciphertext, tag).decode()
        if sys.platform == "win32":
            import win32crypt

            return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[
                1
            ].decode()
        raise CookieSourceError(
            f"Unsupported Chrome cookie encryption format on {sys.platform}"
        )
    except CookieSourceError:
        raise
    except Exception as error:
        raise CookieSourceError("Chrome cookie decryption failed") from error


def get_chrome_cookies(
    domain: str, *, cookie_path: str | Path | None = None
) -> list[CookieRecord]:
    """Retrieve applicable Chrome cookies for one hostname."""
    cookie_records: list[CookieRecord] = []
    target_hostname = normalize_hostname(domain)
    if not target_hostname:
        raise CookieSourceError("Chrome cookie extraction requires a valid hostname")
    resolved_path = get_browser_cookie_path("chrome", cookie_path)
    if not resolved_path or not resolved_path.exists():
        raise CookieSourceError(f"Chrome cookie database not found at {resolved_path}")

    encryption_key = get_chrome_encryption_key()
    if not encryption_key:
        raise CookieSourceError("Could not retrieve the Chrome cookie encryption key")

    try:
        with copied_cookie_connection(resolved_path) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT name, value, encrypted_value, host_key, expires_utc, path,
                       is_secure, is_httponly
                  FROM cookies
                 WHERE host_key = ?
                    OR (
                        substr(host_key, 1, 1) = '.'
                        AND (
                            ltrim(host_key, '.') = ?
                            OR ? LIKE '%.' || ltrim(host_key, '.')
                        )
                    )
                """,
                (target_hostname, target_hostname, target_hostname),
            )
            now = int(datetime.now(timezone.utc).timestamp())
            for (
                name,
                value,
                encrypted_value,
                host_key,
                expires_utc,
                path,
                is_secure,
                is_httponly,
            ) in cursor.fetchall():
                try:
                    host_only = not str(host_key).startswith(".")
                    if not cookie_domain_matches(
                        target_hostname, host_key, host_only=host_only
                    ):
                        continue
                    expires = (
                        int(expires_utc / 1_000_000 - 11_644_473_600)
                        if expires_utc
                        else None
                    )
                    if expires is not None and expires <= now:
                        continue
                    if not value and encrypted_value:
                        value = decrypt_chrome_cookie(encrypted_value, encryption_key)
                    else:
                        value = str(value)
                    if value:
                        cookie_records.append(
                            CookieRecord(
                                name=str(name),
                                value=value,
                                domain=str(host_key),
                                path=str(path or "/"),
                                expires=expires,
                                secure=bool(is_secure),
                                http_only=bool(is_httponly),
                                host_only=host_only,
                            )
                        )
                except CookieSourceError:
                    raise
                except Exception as error:
                    logger.debug("Error processing cookie %s: %s", name, error)
    except Exception as error:
        logger.error("Error reading Chrome cookies: %s", error)
        if isinstance(error, CookieSourceError):
            raise
        if isinstance(error, sqlite3.Error):
            raise CookieSourceError(
                f"Could not read Chrome cookies: {error}"
            ) from error
        raise CookieSourceError(f"Could not read Chrome cookies: {error}") from error

    logger.info("Retrieved %s cookies for domain %s", len(cookie_records), domain)
    return cookie_records
