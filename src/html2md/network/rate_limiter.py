"""
Advanced rate limiting system for respectful web crawling.

This module provides:
- Requests-per-minute limiting with sliding window
- Per-domain request tracking and throttling
- Circuit breaker pattern for error handling
- Adaptive rate limiting based on server responses
- Comprehensive monitoring and statistics
"""

import logging
import time
import threading
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("html2md")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class RateLimitStats:
    """Statistics for rate limiting per domain."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    blocked_requests: int = 0
    last_request_time: float = 0
    average_response_time: float = 0
    circuit_state: CircuitState = CircuitState.CLOSED
    circuit_failures: int = 0
    circuit_last_failure: float = 0


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_minute: int = 30
    burst_allowance: int = 5
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: float = 300.0  # 5 minutes
    circuit_test_requests: int = 3
    adaptive_slowdown_factor: float = 1.5
    max_adaptive_delay: float = 60.0
    enable_adaptive_limiting: bool = True


class SlidingWindowCounter:
    """Sliding window counter for rate limiting."""

    def __init__(self, window_size_seconds: int = 60):
        self.window_size = window_size_seconds
        self.requests: deque[float] = deque()
        self.lock = threading.Lock()

    def add_request(self, timestamp: Optional[float] = None) -> None:
        """Add a request to the counter."""
        if timestamp is None:
            timestamp = time.time()

        with self.lock:
            self.requests.append(timestamp)
            self._cleanup_old_requests(timestamp)

    def get_request_count(self, timestamp: Optional[float] = None) -> int:
        """Get current request count in the window."""
        if timestamp is None:
            timestamp = time.time()

        with self.lock:
            self._cleanup_old_requests(timestamp)
            return len(self.requests)

    def _cleanup_old_requests(self, current_time: float) -> None:
        """Remove requests outside the window."""
        cutoff_time = current_time - self.window_size
        while self.requests and self.requests[0] < cutoff_time:
            self.requests.popleft()


class CircuitBreaker:
    """Circuit breaker for handling failures."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.test_request_count = 0
        self.lock = threading.Lock()

    def can_proceed(self) -> bool:
        """Check if requests can proceed through the circuit."""
        with self.lock:
            current_time = time.time()

            if self.state == CircuitState.CLOSED:
                return True

            elif self.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if (
                    current_time - self.last_failure_time
                    >= self.config.circuit_recovery_timeout
                ):
                    self.state = CircuitState.HALF_OPEN
                    self.test_request_count = 0
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                    return True
                return False

            elif self.state == CircuitState.HALF_OPEN:
                # Allow limited test requests
                return self.test_request_count < self.config.circuit_test_requests

    def record_success(self) -> None:
        """Record a successful request."""
        with self.lock:
            if self.state == CircuitState.HALF_OPEN:
                self.test_request_count += 1
                if self.test_request_count >= self.config.circuit_test_requests:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    logger.info("Circuit breaker transitioning to CLOSED (recovered)")
            elif self.state == CircuitState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self) -> None:
        """Record a failed request."""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                # Failed during testing, go back to OPEN
                self.state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker failed during testing, returning to OPEN"
                )
            elif self.failure_count >= self.config.circuit_failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker OPEN due to {self.failure_count} failures"
                )


class DomainRateLimiter:
    """Rate limiter for a specific domain."""

    def __init__(self, domain: str, config: RateLimitConfig):
        self.domain = domain
        self.config = config
        self.counter = SlidingWindowCounter()
        self.circuit_breaker = CircuitBreaker(config)
        self.stats = RateLimitStats()
        self.last_request_time = 0.0
        self.response_times: deque[float] = deque(
            maxlen=100
        )  # Keep last 100 response times
        self.lock = threading.Lock()

    def can_make_request(self) -> Tuple[bool, float]:
        """
        Check if a request can be made now.

        Returns:
            Tuple of (can_proceed, suggested_delay_seconds)
        """
        with self.lock:
            current_time = time.time()

            # Check circuit breaker first
            if not self.circuit_breaker.can_proceed():
                self.stats.blocked_requests += 1
                self.stats.circuit_state = self.circuit_breaker.state
                return False, self.config.circuit_recovery_timeout

            # Check rate limit
            current_count = self.counter.get_request_count(current_time)

            # Allow burst up to the limit + burst allowance
            max_requests = self.config.requests_per_minute + self.config.burst_allowance

            if current_count >= max_requests:
                # Calculate delay until we can make the next request
                oldest_request = (
                    self.counter.requests[0] if self.counter.requests else current_time
                )
                delay = 60.0 - (current_time - oldest_request) + 1.0  # Add 1s buffer
                self.stats.blocked_requests += 1
                return False, delay

            # Calculate adaptive delay based on recent response times
            adaptive_delay = self._calculate_adaptive_delay()

            return True, adaptive_delay

    def record_request_start(self) -> float:
        """Record the start of a request."""
        current_time = time.time()

        with self.lock:
            self.counter.add_request(current_time)
            self.last_request_time = current_time
            self.stats.total_requests += 1
            self.stats.last_request_time = current_time

        return current_time

    def record_request_end(
        self, start_time: float, success: bool, response_time: Optional[float] = None
    ) -> None:
        """Record the completion of a request."""
        if response_time is None:
            response_time = time.time() - start_time

        with self.lock:
            self.response_times.append(response_time)

            # Update average response time
            if self.response_times:
                self.stats.average_response_time = sum(self.response_times) / len(
                    self.response_times
                )

            if success:
                self.stats.successful_requests += 1
                self.circuit_breaker.record_success()
            else:
                self.stats.failed_requests += 1
                self.circuit_breaker.record_failure()

            # Update circuit state in stats
            self.stats.circuit_state = self.circuit_breaker.state
            self.stats.circuit_failures = self.circuit_breaker.failure_count
            self.stats.circuit_last_failure = self.circuit_breaker.last_failure_time

    def _calculate_adaptive_delay(self) -> float:
        """Calculate adaptive delay based on server response patterns."""
        if not self.config.enable_adaptive_limiting or not self.response_times:
            return 0.0

        avg_response_time = self.stats.average_response_time

        # If average response time is high, increase delay
        if avg_response_time > 2.0:  # 2 seconds
            adaptive_delay = avg_response_time * self.config.adaptive_slowdown_factor
            return min(adaptive_delay, self.config.max_adaptive_delay)

        return 0.0

    def get_stats(self) -> RateLimitStats:
        """Get current statistics for this domain."""
        with self.lock:
            return RateLimitStats(
                total_requests=self.stats.total_requests,
                successful_requests=self.stats.successful_requests,
                failed_requests=self.stats.failed_requests,
                blocked_requests=self.stats.blocked_requests,
                last_request_time=self.stats.last_request_time,
                average_response_time=self.stats.average_response_time,
                circuit_state=self.stats.circuit_state,
                circuit_failures=self.stats.circuit_failures,
                circuit_last_failure=self.stats.circuit_last_failure,
            )


class GlobalRateLimiter:
    """Global rate limiter managing multiple domains."""

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self.domain_limiters: Dict[str, DomainRateLimiter] = {}
        self.lock = threading.Lock()

    def _get_domain_limiter(self, url: str) -> DomainRateLimiter:
        """Get or create a domain-specific rate limiter."""
        domain = urlparse(url).netloc.lower()

        with self.lock:
            if domain not in self.domain_limiters:
                self.domain_limiters[domain] = DomainRateLimiter(domain, self.config)

        return self.domain_limiters[domain]

    def can_make_request(self, url: str) -> Tuple[bool, float]:
        """
        Check if a request can be made to the given URL.

        Returns:
            Tuple of (can_proceed, suggested_delay_seconds)
        """
        limiter = self._get_domain_limiter(url)
        return limiter.can_make_request()

    def record_request_start(self, url: str) -> float:
        """Record the start of a request."""
        limiter = self._get_domain_limiter(url)
        return limiter.record_request_start()

    def record_request_end(
        self,
        url: str,
        start_time: float,
        success: bool,
        response_time: Optional[float] = None,
    ) -> None:
        """Record the completion of a request."""
        limiter = self._get_domain_limiter(url)
        limiter.record_request_end(start_time, success, response_time)

    def get_domain_stats(self, url: str) -> RateLimitStats:
        """Get statistics for a specific domain."""
        limiter = self._get_domain_limiter(url)
        return limiter.get_stats()

    def get_all_stats(self) -> Dict[str, RateLimitStats]:
        """Get statistics for all domains."""
        with self.lock:
            return {
                domain: limiter.get_stats()
                for domain, limiter in self.domain_limiters.items()
            }

    def update_config(self, config: RateLimitConfig) -> None:
        """Update configuration for all domain limiters."""
        with self.lock:
            self.config = config
            for limiter in self.domain_limiters.values():
                limiter.config = config

    def reset_domain(self, url: str) -> None:
        """Reset rate limiting for a specific domain."""
        domain = urlparse(url).netloc.lower()
        with self.lock:
            if domain in self.domain_limiters:
                del self.domain_limiters[domain]

    def reset_all(self) -> None:
        """Reset all rate limiting data."""
        with self.lock:
            self.domain_limiters.clear()
