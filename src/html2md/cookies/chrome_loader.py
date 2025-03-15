import os
import sqlite3
import logging
import win32crypt
import shutil
from html2md.cookies.session_manager import session

logger = logging.getLogger("chrome_loader")

# Default path to Chrome cookies database (Windows)
DEFAULT_COOKIE_PATH = os.path.expanduser(
    "/mnt/c/Users/justin.kindrix/AppData/Local/Google/Chrome/User Data/Profile 1/Network/Cookies"
)


def get_chrome_cookie_path():
    """Retrieve Chrome cookie database path from an environment variable or use the default."""
    return os.getenv("CHROME_COOKIES_DB_PATH", DEFAULT_COOKIE_PATH)


def load_cookies_from_chrome(domain):
    """Load cookies from Chrome's SQLite database, handling file locks and encryption."""
    chrome_cookie_path = get_chrome_cookie_path()

    if not os.path.exists(chrome_cookie_path):
        logger.error(f"Chrome cookie database not found at {chrome_cookie_path}")
        return {}

    # Create a temporary copy of the database to prevent locking issues
    temp_cookie_db = "/tmp/chrome_cookies.db"
    try:
        shutil.copy2(chrome_cookie_path, temp_cookie_db)
    except Exception as e:
        logger.error(f"Failed to create temporary copy of Chrome cookies DB: {e}")
        return {}

    try:
        conn = sqlite3.connect(temp_cookie_db)
        cursor = conn.cursor()

        query = "SELECT name, encrypted_value FROM cookies WHERE host_key LIKE ?"
        cursor.execute(query, (f"%{domain}%",))

        cookies = {}
        for name, encrypted_value in cursor.fetchall():
            try:
                # Decrypt the cookie using Windows DPAPI
                decrypted_value = win32crypt.CryptUnprotectData(
                    encrypted_value, None, None, None, 0
                )[1]
                cookies[name] = decrypted_value.decode("utf-8")
            except Exception as e:
                logger.warning(f"Failed to decrypt cookie {name}: {e}")

        session.cookies.update(cookies)
        logger.info(
            f"Loaded {len(cookies)} cookies from Chrome SQLite database for {domain}"
        )

        conn.close()
    except sqlite3.DatabaseError as e:
        logger.error(f"Database error when accessing Chrome cookies: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error while loading cookies from Chrome: {e}")
        return {}
    finally:
        try:
            os.remove(temp_cookie_db)
        except OSError:
            pass  # Ignore cleanup failures

    return cookies
