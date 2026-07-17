import json
import os
import re
import sqlite3
import sys
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookiejar import DefaultCookiePolicy
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, cast
from urllib.parse import urlparse

import requests
from html2md.network.safe_http import guarded_request

# Optional dependencies for browser cookie extraction
try:
    from Cryptodome.Cipher import AES
    from Cryptodome.Protocol.KDF import PBKDF2

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# Optional dependencies for OAuth
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    HAS_GOOGLE_AUTH = True
except ImportError:
    HAS_GOOGLE_AUTH = False

from html2md.config.loader import TOKENS_FILE, load_config
from html2md.utils.secure_files import atomic_write_private_text
from html2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger("session_manager")


def _normalize_hostname(value: str) -> str:
    """Return a comparison-safe ASCII hostname without a cookie-domain dot."""
    hostname = value.strip().lstrip(".").rstrip(".")
    if not hostname:
        return ""
    try:
        return hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError:
        return ""


def _target_hostname(url: str) -> str:
    parsed = urlparse(url)
    return _normalize_hostname(parsed.hostname or "")


def _cookie_domain_matches(hostname: str, domain: str, *, host_only: bool) -> bool:
    normalized_host = _normalize_hostname(hostname)
    normalized_domain = _normalize_hostname(domain)
    if not normalized_host or not normalized_domain:
        return False
    if host_only:
        return normalized_host == normalized_domain
    return normalized_host == normalized_domain or normalized_host.endswith(
        "." + normalized_domain
    )


@dataclass(frozen=True)
class CookieRecord:
    """One browser cookie with the scope needed for safe replay."""

    name: str
    value: str
    domain: str
    path: str = "/"
    expires: Optional[int] = None
    secure: bool = False
    http_only: bool = False
    same_site: Optional[str] = None
    host_only: bool = False

    def applies_to(self, hostname: str) -> bool:
        return _cookie_domain_matches(hostname, self.domain, host_only=self.host_only)


class _ScopedCookiePolicy(DefaultCookiePolicy):
    """Teach requests' legacy cookie jar about RFC 6265 host-only cookies."""

    def return_ok(self, cookie, request):
        if cookie.get_nonstandard_attr("HostOnly"):
            hostname = _target_hostname(request.get_full_url())
            if hostname != _normalize_hostname(cookie.domain):
                return False
        return super().return_ok(cookie, request)


def _path_matches(request_path: str, cookie_path: str) -> bool:
    normalized_cookie_path = cookie_path if cookie_path.startswith("/") else "/"
    if request_path == normalized_cookie_path:
        return True
    if not request_path.startswith(normalized_cookie_path):
        return False
    return normalized_cookie_path.endswith("/") or request_path[
        len(normalized_cookie_path) :
    ].startswith("/")


class ScopedCookieSession(requests.Session):
    """A requests session that enforces host-only and path cookie semantics."""

    def prepare_request(self, request):
        prepared = super().prepare_request(request)
        prepared.headers.pop("Cookie", None)
        hostname = _target_hostname(prepared.url or "")
        parsed = urlparse(prepared.url or "")
        request_path = parsed.path or "/"
        now = int(datetime.now(timezone.utc).timestamp())
        applicable = []
        for cookie in prepared._cookies:
            host_only = bool(cookie.get_nonstandard_attr("HostOnly")) or not bool(
                cookie.domain_specified
            )
            if not _cookie_domain_matches(hostname, cookie.domain, host_only=host_only):
                continue
            if cookie.secure and parsed.scheme.casefold() != "https":
                continue
            if cookie.expires is not None and cookie.expires <= now:
                continue
            if not _path_matches(request_path, cookie.path):
                continue
            applicable.append(cookie)
        applicable.sort(key=lambda item: len(item.path or "/"), reverse=True)
        if applicable:
            prepared.headers["Cookie"] = "; ".join(
                f"{cookie.name}={cookie.value}" for cookie in applicable
            )
        return prepared


def _as_scoped_session(session: requests.Session) -> ScopedCookieSession:
    if isinstance(session, ScopedCookieSession):
        return session
    scoped = ScopedCookieSession()
    scoped.headers.clear()
    scoped.headers.update(session.headers)
    scoped.cookies.update(session.cookies)
    scoped.auth = session.auth
    scoped.verify = session.verify
    scoped.cert = session.cert
    scoped.params = dict(cast(Mapping[str, Any], session.params))
    scoped.trust_env = session.trust_env
    return scoped


def _coerce_cookie_records(
    cookies: Iterable[CookieRecord] | dict[str, str], hostname: str
) -> list[CookieRecord]:
    """Accept the structured contract and legacy test/client mappings."""
    if isinstance(cookies, dict):
        return [
            CookieRecord(name, value, hostname, host_only=True)
            for name, value in cookies.items()
        ]
    return list(cookies)


def _set_cookie_record(session: requests.Session, cookie: CookieRecord) -> None:
    rest: dict[str, Any] = {"HostOnly": cookie.host_only}
    if cookie.http_only:
        rest["HttpOnly"] = True
    if cookie.same_site:
        rest["SameSite"] = cookie.same_site
    normalized_domain = _normalize_hostname(cookie.domain)
    stored_domain = normalized_domain if cookie.host_only else "." + normalized_domain
    session.cookies.set(
        cookie.name,
        cookie.value,
        domain=stored_domain,
        path=cookie.path or "/",
        expires=cookie.expires,
        secure=cookie.secure,
        rest=rest,
    )


# Load configuration
config = load_config()

# Load OAuth credentials from config
CLIENT_ID = config.get("oauth", {}).get("CLIENT_ID", "")
CLIENT_SECRET = config.get("oauth", {}).get("CLIENT_SECRET", "")


# Defer validation until OAuth is actually needed
def validate_oauth_config():
    """Validate OAuth configuration when needed."""
    if not CLIENT_ID or not CLIENT_SECRET:
        logger.error("Missing OAuth credentials in config file.")
        raise ValueError(
            "OAuth credentials (CLIENT_ID, CLIENT_SECRET) must be set in config.json. "
            "Run 'html2md --init-config' to create a config file with placeholders."
        )


REDIRECT_URI = "http://localhost"
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


# -------------------------------
# OAuth Token Management
# -------------------------------


def load_tokens():
    """Load OAuth tokens from a local file."""
    if not HAS_GOOGLE_AUTH:
        raise ImportError(
            "Google auth libraries are required for OAuth. Install html2md-cli with its declared dependencies."
        )

    validate_oauth_config()  # Validate when tokens are actually needed
    if not TOKENS_FILE.exists():
        logger.warning(
            f"Token file not found at {TOKENS_FILE}. Performing fresh authentication."
        )
        return None

    try:
        with TOKENS_FILE.open("r", encoding="utf-8") as f:
            token_data = json.load(f)
        logger.info(f"Loaded OAuth tokens from {TOKENS_FILE}")
        return Credentials.from_authorized_user_info(token_data)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load tokens from {TOKENS_FILE}: {e}")
        return None


def save_tokens(creds):
    """Save OAuth tokens to a local file."""
    try:
        atomic_write_private_text(TOKENS_FILE, creds.to_json())
        logger.info(f"Saved OAuth tokens to {TOKENS_FILE}")
    except IOError as e:
        logger.error(f"Failed to save tokens to {TOKENS_FILE}: {e}")


def authenticate_google():
    """Authenticate using Google OAuth and obtain an access token."""
    if not HAS_GOOGLE_AUTH:
        raise ImportError(
            "Google auth libraries are required for OAuth. Install html2md-cli with its declared dependencies."
        )

    validate_oauth_config()  # Validate when OAuth is actually needed
    creds = None

    # Load existing credentials if available
    creds = load_tokens()

    # Refresh the token if it's expired and refresh_token is available
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            logger.info("Access token refreshed using the refresh token.")
            save_tokens(creds)
            return creds
        except Exception as e:
            logger.warning(
                f"Token refresh failed: {e}. Proceeding with re-authentication."
            )
            creds = None

    # Perform fresh OAuth if no valid credentials are available
    if not creds or not creds.valid:
        try:
            # Run local server for OAuth authorization with browser
            flow = InstalledAppFlow.from_client_config(
                {
                    "installed": {
                        "client_id": CLIENT_ID,
                        "client_secret": CLIENT_SECRET,
                        "redirect_uris": [REDIRECT_URI],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                SCOPES,
            )

            creds = flow.run_local_server(port=0)
            logger.info("Google OAuth authentication successful via local server.")
            save_tokens(creds)

        except Exception as e:
            logger.error(f"OAuth authentication failed: {e}")
            raise ValueError(
                "OAuth authentication failed. No valid access token found."
            )

    return creds


def refresh_token_if_expired(creds):
    """Refresh access token if it has expired."""
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            logger.info("Access token refreshed using refresh token.")
            save_tokens(creds)
        except Exception as e:
            logger.error(f"Token refresh failed: {e}. Performing fresh authentication.")
            return authenticate_google()
    return creds


def get_credentials():
    """Get credentials using stored tokens or authenticate fresh."""
    if not HAS_GOOGLE_AUTH:
        raise ImportError(
            "Google auth libraries are required for OAuth. Install html2md-cli with its declared dependencies."
        )

    validate_oauth_config()  # Validate when OAuth is actually needed
    creds = load_tokens()

    # Refresh or authenticate if necessary
    if not creds or not creds.valid:
        creds = authenticate_google()

    if creds.expired:
        creds = refresh_token_if_expired(creds)

    return creds


# -------------------------------
# Browser Cookie Management
# -------------------------------


def get_browser_cookie_path(browser=None):
    """Return the path to browser cookie files based on platform and browser."""

    # Define browser and profile configurations
    browser_config = config.get("browser", {})
    preferred_browser = browser or browser_config.get("preferred", "chrome")

    # Check for custom path override in config
    custom_paths = browser_config.get("custom_path", {})
    if preferred_browser in custom_paths and custom_paths[preferred_browser]:
        # Handle Windows path in WSL
        custom_path_str = custom_paths[preferred_browser]

        # Convert Windows path to WSL path if needed
        if (
            sys.platform.startswith("linux")
            and not custom_path_str.startswith("/")
            and ":" in custom_path_str
        ):
            # Looks like Windows path (C:\...) but we're in Linux/WSL
            drive = custom_path_str[0].lower()
            path_without_drive = custom_path_str[3:]
            # Replace backslashes with forward slashes
            path_with_slashes = path_without_drive.replace("\\", "/")
            wsl_path = f"/mnt/{drive}/{path_with_slashes}"
            logger.info(
                f"Converting Windows path {custom_path_str} to WSL path {wsl_path}"
            )
            custom_path = Path(wsl_path)
        else:
            custom_path = Path(custom_path_str)

        if custom_path.exists():
            logger.info(
                f"Using custom cookie path for {preferred_browser}: {custom_path}"
            )
            return custom_path
        else:
            logger.warning(
                f"Custom cookie path for {preferred_browser} not found: {custom_path}"
            )

    home = Path.home()

    # Browser storage paths based on platform
    if sys.platform == "win32":  # Windows
        if preferred_browser == "chrome":
            return (
                home
                / "AppData"
                / "Local"
                / "Google"
                / "Chrome"
                / "User Data"
                / "Default"
                / "Network"
                / "Cookies"
            )
        elif preferred_browser == "firefox":
            return home / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles"
        elif preferred_browser == "edge":
            return (
                home
                / "AppData"
                / "Local"
                / "Microsoft"
                / "Edge"
                / "User Data"
                / "Default"
                / "Network"
                / "Cookies"
            )

    elif sys.platform == "darwin":  # macOS
        if preferred_browser == "chrome":
            return (
                home
                / "Library"
                / "Application Support"
                / "Google"
                / "Chrome"
                / "Default"
                / "Cookies"
            )
        elif preferred_browser == "firefox":
            return home / "Library" / "Application Support" / "Firefox" / "Profiles"
        elif preferred_browser == "safari":
            return home / "Library" / "Cookies" / "Cookies.binarycookies"

    else:  # Linux/Unix
        if preferred_browser == "chrome":
            return home / ".config" / "google-chrome" / "Default" / "Cookies"
        elif preferred_browser == "firefox":
            return home / ".mozilla" / "firefox"
        elif preferred_browser == "edge":
            return home / ".config" / "microsoft-edge" / "Default" / "Cookies"

    logger.warning(
        f"Unsupported browser '{preferred_browser}' or platform '{sys.platform}'"
    )
    return None


def get_chrome_encryption_key():
    """Get encryption key for Chrome cookies"""
    if not HAS_CRYPTO:
        raise ImportError(
            "pycryptodomex is required for browser cookie extraction. Install html2md-cli with its declared dependencies."
        )

    if sys.platform == "win32":  # Windows
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
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.loads(f.read())

            # Decode the encrypted key
            encrypted_key = local_state["os_crypt"]["encrypted_key"]
            encrypted_key = encrypted_key.encode()
            encrypted_key = encrypted_key[5:]  # Remove 'DPAPI' prefix

            # Decrypt the key using Windows DPAPI
            decrypted_key = win32crypt.CryptUnprotectData(
                encrypted_key, None, None, None, 0
            )[1]
            return decrypted_key
        except Exception as e:
            logger.error(f"Error getting Chrome encryption key: {e}")
            return None

    elif sys.platform == "darwin":  # macOS
        # macOS uses the keychain for encryption
        # This is a simplified implementation
        try:
            key_material = "Chrome Safe Storage"
            password = key_material.encode()
            # Use OSX keychain to get the actual password
            # This would require additional macOS-specific libraries
            salt = b"saltysalt"
            iterations = 1003
            key = PBKDF2(password, salt, dkLen=16, count=iterations)
            return key
        except Exception as e:
            logger.error(f"Error getting Chrome encryption key on macOS: {e}")
            return None

    elif "linux" in sys.platform:  # Linux
        # Linux Chrome may use different encryption based on distribution
        # Here's a basic implementation for Ubuntu/Debian
        try:
            salt = b"saltysalt"
            iterations = 1
            # Many Linux distros store this in the Gnome keyring
            # This is a simplified implementation that works on some systems
            password = "peanuts".encode()  # Default password on some Linux systems
            key = PBKDF2(password, salt, dkLen=16, count=iterations)
            return key
        except Exception as e:
            logger.error(f"Error getting Chrome encryption key on Linux: {e}")
            return None

    return None


def decrypt_chrome_cookie(encrypted_value, key):
    """Decrypt Chrome cookie value"""
    if not HAS_CRYPTO:
        raise ImportError(
            "pycryptodomex is required for browser cookie extraction. Install html2md-cli with its declared dependencies."
        )

    try:
        # For newer Chrome versions, cookies are encrypted with AES-256-GCM
        if encrypted_value.startswith(b"v10") or encrypted_value.startswith(b"v11"):
            # Extract required values
            nonce = encrypted_value[3 : 3 + 12]
            ciphertext = encrypted_value[3 + 12 : -16]
            tag = encrypted_value[-16:]

            # Create cipher
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)

            # Decrypt
            decrypted = cipher.decrypt_and_verify(ciphertext, tag)
            return decrypted.decode()

        # Windows may also use DPAPI for older Chrome versions
        elif sys.platform == "win32":
            import win32crypt

            return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[
                1
            ].decode()

        # Older versions or other platforms might use simple AES
        else:
            iv = b" " * 16
            cipher = AES.new(key, AES.MODE_CBC, iv)
            # Remove padding
            decrypted = cipher.decrypt(encrypted_value)
            padding_length = decrypted[-1]
            if padding_length:
                decrypted = decrypted[:-padding_length]
            return decrypted.decode()

    except Exception as e:
        logger.error(f"Cookie decryption error: {e}")
        return None


def _copy_cookie_database(source_path):
    """Copy a locked browser database into unpredictable owner-only storage."""
    temp_directory = tempfile.TemporaryDirectory(prefix="html2md-cookies-")
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


def get_chrome_cookies(domain):
    """Retrieve Chrome cookies for a specific domain"""
    cookie_records = []
    target_hostname = _normalize_hostname(domain)
    if not target_hostname:
        return cookie_records
    cookie_path = get_browser_cookie_path("chrome")

    if not cookie_path or not cookie_path.exists():
        logger.warning(f"Chrome cookie database not found at {cookie_path}")
        return cookie_records

    # Get encryption key (specific to Chrome)
    encryption_key = get_chrome_encryption_key()
    if not encryption_key:
        logger.warning("Could not retrieve Chrome encryption key")
        return cookie_records

    temp_directory = None
    conn = None
    try:
        temp_directory, temp_db_path = _copy_cookie_database(cookie_path)
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()

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

        # Current time for expiration check
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
                if not _cookie_domain_matches(
                    target_hostname, host_key, host_only=host_only
                ):
                    continue

                # Chromium stores microseconds since 1601-01-01 UTC.
                expires = (
                    int(expires_utc / 1_000_000 - 11_644_473_600)
                    if expires_utc
                    else None
                )

                # Skip expired cookies
                if expires is not None and expires <= now:
                    continue

                # If value is not set but encrypted_value is, decrypt it
                if not value and encrypted_value:
                    # Skip the 'v10' prefix for encrypted values
                    decrypted_value = decrypt_chrome_cookie(
                        encrypted_value, encryption_key
                    )
                    if decrypted_value:
                        value = decrypted_value
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
            except Exception as e:
                logger.debug(f"Error processing cookie {name}: {e}")

    except Exception as e:
        logger.error(f"Error reading Chrome cookies: {e}")
    finally:
        try:
            if conn is not None:
                conn.close()
        finally:
            if temp_directory is not None:
                temp_directory.cleanup()

    logger.info(f"Retrieved {len(cookie_records)} cookies for domain {domain}")
    return cookie_records


def get_firefox_cookies(domain):
    """Retrieve Firefox cookies for a specific domain"""
    cookie_records = []
    target_hostname = _normalize_hostname(domain)
    if not target_hostname:
        return cookie_records
    cookie_path = get_browser_cookie_path("firefox")

    if not cookie_path or not cookie_path.exists():
        logger.warning(f"Firefox profile directory not found at {cookie_path}")
        return cookie_records

    # Find the default profile
    profile_dir = None

    # Firefox uses a profiles.ini file to identify the default profile
    if cookie_path.is_dir():
        profiles_ini = cookie_path.parent / "profiles.ini"
        if profiles_ini.exists():
            try:
                # Parse profiles.ini to find default profile
                with open(profiles_ini, "r") as f:
                    profile_data = f.read()

                # Find the default profile section
                profile_sections = re.findall(
                    r"\[Profile\d+\].*?(?=\[|$)", profile_data, re.DOTALL
                )
                for section in profile_sections:
                    if "Default=1" in section or "IsRelative=1" in section:
                        path_match = re.search(r"Path=(.*)", section)
                        if path_match:
                            profile_name = path_match.group(1)
                            if "IsRelative=1" in section:
                                profile_dir = cookie_path.parent / profile_name
                            else:
                                profile_dir = Path(profile_name)
                            break

                # If no default found, try to find any profile
                if not profile_dir:
                    for section in profile_sections:
                        path_match = re.search(r"Path=(.*)", section)
                        if path_match:
                            profile_name = path_match.group(1)
                            if "IsRelative=1" in section:
                                profile_dir = cookie_path.parent / profile_name
                            else:
                                profile_dir = Path(profile_name)
                            break
            except Exception as e:
                logger.error(f"Error parsing Firefox profiles.ini: {e}")

    # If still no profile found, check if there's only one subdirectory
    if not profile_dir and cookie_path.is_dir():
        profiles = [
            p
            for p in cookie_path.iterdir()
            if p.is_dir() and p.name.endswith(".default")
        ]
        if len(profiles) == 1:
            profile_dir = profiles[0]
        else:
            # Try any .default profile directory
            for p in cookie_path.iterdir():
                if p.is_dir() and ".default" in p.name:
                    profile_dir = p
                    break

    if not profile_dir or not profile_dir.exists():
        logger.warning("Could not find a valid Firefox profile")
        return cookie_records

    # Locate cookies.sqlite in the profile
    cookies_db = profile_dir / "cookies.sqlite"
    if not cookies_db.exists():
        logger.warning(f"Firefox cookies database not found at {cookies_db}")
        return cookie_records

    temp_directory = None
    conn = None
    try:
        temp_directory, temp_path = _copy_cookie_database(cookies_db)
        conn = sqlite3.connect(str(temp_path))
        cursor = conn.cursor()

        # Query cookies
        try:
            cursor.execute(
                """
                SELECT name, value, host, expiry, path, isSecure, isHttpOnly
                  FROM moz_cookies
                 WHERE host = ?
                    OR (
                        substr(host, 1, 1) = '.'
                        AND (
                            ltrim(host, '.') = ?
                            OR ? LIKE '%.' || ltrim(host, '.')
                        )
                    )
                """,
                (target_hostname, target_hostname, target_hostname),
            )

            # Current time for expiration check
            now = int(datetime.now().timestamp())

            for (
                name,
                value,
                host,
                expiry,
                path,
                is_secure,
                is_httponly,
            ) in cursor.fetchall():
                host_only = not str(host).startswith(".")
                if not _cookie_domain_matches(
                    target_hostname, host, host_only=host_only
                ):
                    continue
                # Skip expired cookies
                if expiry < now and expiry != 0:
                    continue

                cookie_records.append(
                    CookieRecord(
                        name=str(name),
                        value=str(value),
                        domain=str(host),
                        path=str(path or "/"),
                        expires=int(expiry) if expiry else None,
                        secure=bool(is_secure),
                        http_only=bool(is_httponly),
                        host_only=host_only,
                    )
                )
        except sqlite3.OperationalError as e:
            logger.error(f"Error querying Firefox cookies: {e}")

    except Exception as e:
        logger.error(f"Error reading Firefox cookies: {e}")
    finally:
        try:
            if conn is not None:
                conn.close()
        finally:
            if temp_directory is not None:
                temp_directory.cleanup()

    logger.info(f"Retrieved {len(cookie_records)} cookies for domain {domain}")
    return cookie_records


def get_domain_cookies(url, browser=None):
    """Get cookies for a specific domain from the preferred browser"""
    # Parse domain from URL
    domain = _target_hostname(url)
    if not domain:
        logger.warning("Cannot extract cookies for a URL without a valid hostname")
        return []

    browser_config = config.get("browser", {})
    preferred_browser = browser or browser_config.get("preferred", "chrome")

    if preferred_browser == "chrome":
        return get_chrome_cookies(domain)
    elif preferred_browser == "firefox":
        return get_firefox_cookies(domain)
    else:
        logger.warning(
            f"Cookie extraction not implemented for browser: {preferred_browser}"
        )
        return {}


# -------------------------------
# HTTP Session Management
# -------------------------------

# Tracks whether the insecure-mode warning has been shown, so multi-URL runs
# (batch, crawl) warn once instead of once per request/session.
_insecure_warning_emitted = False


def disable_ssl_verification(session):
    """
    Disable SSL certificate verification on a session (opt-in via --insecure).

    Emits a single prominent warning per process and suppresses urllib3's
    per-request InsecureRequestWarning, since the user has explicitly
    acknowledged the risk by passing the flag.

    Args:
        session (requests.Session): Session to modify in place.

    Returns:
        requests.Session: The same session, with verification disabled.
    """
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
    """
    Return a new configured requests session.

    Args:
        verify_ssl (bool, optional): Whether to verify SSL certificates.
            Defaults to True. Set to False only for trusted hosts with
            invalid/self-signed certificates (CLI: --insecure).
    """
    session = ScopedCookieSession()
    session.cookies.set_policy(_ScopedCookiePolicy())
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            # Let requests handle Accept-Encoding automatically
            # This allows proper decompression of gzip, deflate, and br (brotli) content
        }
    )
    if not verify_ssl:
        disable_ssl_verification(session)
    logger.info("New session initialized with default headers.")
    return session


def reset_session(session):
    """Reset the session by closing and creating a new session."""
    # Preserve the verification setting (bool or CA bundle path) across the reset
    verify = getattr(session, "verify", True)

    try:
        session.close()
        logger.info("Session closed successfully.")
    except Exception as e:
        logger.warning(f"Error while closing session: {e}")

    # Return a new session
    new_session = get_session(verify_ssl=verify is not False)
    new_session.verify = verify
    logger.info("New session initialized after reset.")
    return new_session


def load_cookies_from_json(json_file, url=None):
    """Load scoped cookie records from a browser developer-tools export."""
    cookies = []
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            cookie_data = json.load(f)

        hostname = ""
        if url:
            hostname = _target_hostname(url)
            logger.debug(f"URL domain for cookie matching: {hostname}")

        # Handle different JSON cookie formats
        if isinstance(cookie_data, list):
            # Format: Array of cookie objects with name, value, domain
            logger.debug(f"JSON cookie format: Array with {len(cookie_data)} items")
            for cookie in cookie_data:
                if isinstance(cookie, dict) and "name" in cookie and "value" in cookie:
                    cookie_domain = str(cookie.get("domain", hostname))
                    host_only = bool(
                        cookie.get("hostOnly", not cookie_domain.startswith("."))
                    )
                    record = CookieRecord(
                        name=str(cookie["name"]),
                        value=str(cookie["value"]),
                        domain=cookie_domain,
                        path=str(cookie.get("path", "/") or "/"),
                        expires=(
                            int(cookie["expirationDate"])
                            if cookie.get("expirationDate") is not None
                            else None
                        ),
                        secure=bool(cookie.get("secure", False)),
                        http_only=bool(cookie.get("httpOnly", False)),
                        same_site=(
                            str(cookie["sameSite"])
                            if cookie.get("sameSite") is not None
                            else None
                        ),
                        host_only=host_only,
                    )
                    if not hostname or record.applies_to(hostname):
                        cookies.append(record)
                        logger.debug(
                            "Included cookie %s for domain %s",
                            record.name,
                            hostname,
                        )
                    else:
                        logger.debug(
                            "Excluded cookie %s (domain mismatch)", record.name
                        )
        elif isinstance(cookie_data, dict):
            if not hostname:
                raise ValueError(
                    "A target URL is required for an unscoped cookie mapping"
                )
            logger.debug(
                f"JSON cookie format: Dictionary with {len(cookie_data)} items"
            )
            for name, value in cookie_data.items():
                cookies.append(
                    CookieRecord(str(name), str(value), hostname, host_only=True)
                )
                logger.debug(f"Added host-only cookie: {name}")

        logger.info(f"Loaded {len(cookies)} cookies from JSON file: {json_file}")
    except Exception as e:
        logger.error(f"Error loading cookies from JSON file: {e}")
        import traceback

        logger.debug(f"Cookie loading traceback: {traceback.format_exc()}")

    return cookies


def apply_browser_cookies(session, url, cookie_json=None, browser=None):
    """Apply cookies from browser to a requests session"""
    session = _as_scoped_session(session)
    url_domain = _target_hostname(url)
    if not url_domain:
        raise ValueError("Cannot apply cookies to a URL without a valid hostname")
    logger.debug(f"Setting cookies for domain: {url_domain}")
    session.cookies.set_policy(_ScopedCookiePolicy())

    # Clear existing cookies for this domain to avoid conflicts
    for existing in list(session.cookies):
        host_only = bool(existing.get_nonstandard_attr("HostOnly"))
        if _cookie_domain_matches(url_domain, existing.domain, host_only=host_only):
            logger.debug(f"Removing existing cookie: {existing.name}")
            session.cookies.clear(existing.domain, existing.path, existing.name)

    if cookie_json:
        cookies = load_cookies_from_json(cookie_json, url)
    else:
        cookies = get_domain_cookies(url, browser=browser)

    for cookie in _coerce_cookie_records(cookies, url_domain):
        if cookie.applies_to(url_domain):
            logger.debug("Setting scoped browser cookie: %s", cookie.name)
            _set_cookie_record(session, cookie)

    logger.debug("Applied %s cookies to session", len(session.cookies.get_dict()))
    logger.info(f"Applied cookies to session for {url}")

    return session


# -------------------------------
# Utility for Testing
# -------------------------------


def test_google_authentication():
    """Test OAuth authentication and session initialization."""
    try:
        get_credentials()
        logger.info("Testing OAuth authentication. Token obtained successfully.")
    except Exception as e:
        logger.error(f"OAuth test failed: {e}")
        raise

    session = get_session()
    try:
        response = guarded_request(
            session,
            "GET",
            "https://www.googleapis.com/oauth2/v1/userinfo",
            timeout=5,
        )
        if response.status_code == 200:
            logger.info("Test API call successful.")
        else:
            logger.warning(
                f"Test API call failed with status code: {response.status_code}"
            )
    except requests.RequestException as e:
        logger.error(f"Failed to connect to Google API: {e}")


if __name__ == "__main__":
    test_google_authentication()
