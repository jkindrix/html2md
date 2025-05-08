import logging
import time

import requests


def fetch_html(url, session, headers, method="GET", data=None, max_retries=3):
    """
    Fetch HTML content from a URL with error handling, logging, and retries.

    Args:
        url (str): The target URL.
        session (requests.Session): Session object to maintain cookies.
        headers (dict): Headers for the request.
        method (str, optional): HTTP method (GET, POST, etc.). Defaults to "GET".
        data (dict, optional): Payload for POST/PUT requests. Defaults to None.
        max_retries (int, optional): Maximum retry attempts for failed requests. Defaults to 3.

    Returns:
        str | None: HTML content if successful, None otherwise.
    """
    attempt = 0
    backoff = 1  # Initial backoff time in seconds

    while attempt < max_retries:
        try:
            logging.info(
                f"Attempt {attempt + 1}/{max_retries}: Fetching {method} {url}"
            )

            response = session.request(
                method, url, headers=headers, data=data, timeout=10
            )
            response.raise_for_status()

            logging.info(f"Success: {url} [HTTP {response.status_code}]")
            return response.text  # Return HTML content

        except requests.Timeout:
            logging.warning(
                f"Timeout occurred when fetching {url}. Retrying in {backoff}s..."
            )

        except requests.RequestException as e:
            logging.error(f"HTTP Error [{e.__class__.__name__}]: {url} - {str(e)}")

        attempt += 1
        time.sleep(backoff)
        backoff *= 2  # Exponential backoff

    logging.error(f"Failed to retrieve {url} after {max_retries} attempts.")
    return None  # Final failure
