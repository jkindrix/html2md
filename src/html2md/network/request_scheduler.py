"""One sequential politeness scheduler for every crawl-owned request."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urlsplit

from html2md.network.rate_limiter import GlobalRateLimiter, RateLimitConfig


@dataclass(frozen=True)
class ScheduledRequest:
    url: str
    started_at: float


class SequentialRequestScheduler:
    """Apply rate, minimum-delay, and Retry-After policy serially per origin."""

    def __init__(
        self,
        *,
        requests_per_minute: int | None = None,
        minimum_delay: float = 0.0,
        jitter: float = 0.3,
        polite: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if requests_per_minute is not None and requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        if minimum_delay < 0 or not 0 <= jitter <= 1:
            raise ValueError("Invalid scheduler delay configuration")
        self.minimum_delay = minimum_delay * (2.0 if polite else 1.0)
        self.jitter = jitter
        self.sleep = sleep
        self.clock = clock
        self.rate_limiter = (
            GlobalRateLimiter(RateLimitConfig(requests_per_minute=requests_per_minute))
            if requests_per_minute is not None
            else None
        )
        self._ready_at: dict[str, float] = {}

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme.casefold()}://{parts.netloc.casefold()}"

    def before_request(self, url: str) -> ScheduledRequest:
        """Wait until policy permits a request, then record its start."""
        delay = max(0.0, self._ready_at.get(self._origin(url), 0.0) - self.clock())
        if self.rate_limiter is not None:
            allowed, suggested = self.rate_limiter.can_make_request(url)
            delay = max(delay, suggested)
            if not allowed:
                delay = max(delay, suggested)
        if delay > 0:
            self.sleep(delay)
        started_at = (
            self.rate_limiter.record_request_start(url)
            if self.rate_limiter is not None
            else self.clock()
        )
        return ScheduledRequest(url, started_at)

    def after_request(
        self,
        request: ScheduledRequest,
        *,
        success: bool,
        status_code: int | None = None,
        retry_after: int | None = None,
        response_time: float | None = None,
    ) -> None:
        """Record outcome and establish the next permissible origin time."""
        if self.rate_limiter is not None:
            self.rate_limiter.record_request_end(
                request.url,
                request.started_at,
                success,
                response_time=response_time,
            )
        delay = self.minimum_delay
        if delay and self.jitter:
            delay = max(
                0.0, delay + random.uniform(-delay * self.jitter, delay * self.jitter)
            )
        if status_code == 429 and retry_after is not None:
            delay = max(delay, float(retry_after))
        self._ready_at[self._origin(request.url)] = self.clock() + delay

    def after_response(
        self,
        request: ScheduledRequest,
        response,
        *,
        response_time: float | None = None,
    ) -> None:
        """Record an HTTP response, including a usable Retry-After value."""
        retry_after = None
        value = response.headers.get("Retry-After")
        if value:
            try:
                retry_after = max(0, int(value))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(value)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    now = datetime.now(retry_at.tzinfo)
                    retry_after = max(0, int((retry_at - now).total_seconds()))
                except (TypeError, ValueError, OverflowError):
                    pass
        self.after_request(
            request,
            success=response.status_code < 400,
            status_code=response.status_code,
            retry_after=retry_after,
            response_time=response_time,
        )

    def get_all_stats(self):
        return self.rate_limiter.get_all_stats() if self.rate_limiter else {}
