"""HTTP request helpers used by the crawler."""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import requests

from grab2md.network.safe_http import (
    DEFAULT_MAX_BODY_BYTES,
    DestinationPolicy,
    guarded_request,
)
from grab2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger(__name__)


@dataclass(frozen=True)
class FetchResult:
    """The observable result of an HTTP fetch, including failures."""

    requested_url: str
    final_url: str
    status_code: Optional[int] = None
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[str] = None
    content: Optional[bytes] = None
    error: Optional[str] = None
    attempts: int = 1
    elapsed: float = 0.0

    @property
    def success(self) -> bool:
        return (
            self.status_code is not None
            and 200 <= self.status_code < 400
            and (self.content is not None or self.body is not None)
        )


def fetch_html(
    url,
    session,
    headers,
    method="GET",
    data=None,
    max_retries=3,
    *,
    network_policy=None,
    allow_private_network=False,
    max_body_bytes=DEFAULT_MAX_BODY_BYTES,
    redirect_validator=None,
    request_scheduler=None,
):
    """Fetch a URL and preserve status, headers, redirects, and failure details.

    Connection failures, timeouts, and server errors are retried with
    exponential backoff. Client errors (including 429) are returned to the
    caller immediately so domain-level policy can handle them.
    """
    started_at = time.monotonic()
    backoff = 1
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "Attempt %s/%s: Fetching %s %s", attempt, max_retries, method, url
            )
            policy = network_policy or DestinationPolicy(
                allow_private=allow_private_network
            )
            response = guarded_request(
                session,
                method,
                url,
                policy=policy,
                headers=headers,
                data=data,
                timeout=10,
                max_body_bytes=max_body_bytes,
                redirect_validator=redirect_validator,
                request_scheduler=request_scheduler,
            )
            result = FetchResult(
                requested_url=url,
                final_url=response.url,
                status_code=response.status_code,
                headers=dict(response.headers),
                content=response.content,
                error=(
                    None
                    if response.status_code < 400
                    else f"HTTP {response.status_code}"
                ),
                attempts=attempt,
                elapsed=time.monotonic() - started_at,
            )

            if response.status_code < 500:
                if result.success:
                    logger.info("Success: %s [HTTP %s]", url, response.status_code)
                else:
                    logger.warning(
                        "Request failed: %s [HTTP %s]", url, response.status_code
                    )
                return result

            last_error = result.error
            if attempt == max_retries:
                return result
            logger.warning(
                "Server error %s while fetching %s. Retrying in %ss...",
                response.status_code,
                url,
                backoff,
            )
        except (requests.Timeout, requests.ConnectionError) as error:
            last_error = f"{error.__class__.__name__}: {error}"
            if attempt == max_retries:
                break
            logger.warning(
                "%s while fetching %s. Retrying in %ss...", last_error, url, backoff
            )
        except requests.RequestException as error:
            last_error = f"{error.__class__.__name__}: {error}"
            logger.error("Request failed for %s: %s", url, last_error)
            break

        time.sleep(backoff)
        backoff *= 2

    logger.error("Failed to retrieve %s after %s attempts.", url, max_retries)
    return FetchResult(
        requested_url=url,
        final_url=url,
        error=last_error or "Request failed",
        attempts=max_retries,
        elapsed=time.monotonic() - started_at,
    )
