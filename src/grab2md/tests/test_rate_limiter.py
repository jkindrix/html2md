"""
Comprehensive tests for rate limiting functionality.
"""

import pytest
import time

from grab2md.network.rate_limiter import (
    GlobalRateLimiter,
    DomainRateLimiter,
    RateLimitConfig,
    SlidingWindowCounter,
    CircuitBreaker,
    CircuitState,
)


class TestSlidingWindowCounter:
    """Test suite for SlidingWindowCounter."""

    def test_empty_counter(self):
        """Test empty counter behavior."""
        counter = SlidingWindowCounter(60)
        assert counter.get_request_count() == 0

    def test_add_requests(self):
        """Test adding requests to counter."""
        counter = SlidingWindowCounter(60)

        # Add some requests
        counter.add_request()
        counter.add_request()
        assert counter.get_request_count() == 2

    def test_window_cleanup(self):
        """Test that old requests are cleaned up."""
        counter = SlidingWindowCounter(2)  # 2 second window

        current_time = time.time()

        # Add request at current time
        counter.add_request(current_time)
        assert counter.get_request_count(current_time) == 1

        # Add request 1 second later
        counter.add_request(current_time + 1)
        assert counter.get_request_count(current_time + 1) == 2

        # Check 3 seconds later - first request should be gone
        assert counter.get_request_count(current_time + 3) == 1

        # Check 4 seconds later - both should be gone
        assert counter.get_request_count(current_time + 4) == 0


class TestCircuitBreaker:
    """Test suite for CircuitBreaker."""

    def test_initial_state(self):
        """Test circuit breaker initial state."""
        config = RateLimitConfig(circuit_failure_threshold=3)
        breaker = CircuitBreaker(config)

        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_proceed() is True

    def test_failure_accumulation(self):
        """Test failure accumulation and circuit opening."""
        config = RateLimitConfig(circuit_failure_threshold=3)
        breaker = CircuitBreaker(config)

        # Record failures
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_proceed() is True

        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

        # Third failure should open circuit
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.can_proceed() is False

    def test_recovery_timeout(self):
        """Test circuit recovery after timeout."""
        config = RateLimitConfig(
            circuit_failure_threshold=2, circuit_recovery_timeout=1.0  # 1 second
        )
        breaker = CircuitBreaker(config)

        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Should still be blocked immediately
        assert breaker.can_proceed() is False

        # Wait for recovery timeout
        time.sleep(1.1)

        # Should transition to HALF_OPEN
        assert breaker.can_proceed() is True
        assert breaker.state == CircuitState.HALF_OPEN

    def test_half_open_success(self):
        """Test successful recovery from HALF_OPEN state."""
        config = RateLimitConfig(
            circuit_failure_threshold=2,
            circuit_recovery_timeout=0.1,
            circuit_test_requests=2,
        )
        breaker = CircuitBreaker(config)

        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()

        # Wait for recovery
        time.sleep(0.2)
        breaker.can_proceed()  # Transition to HALF_OPEN

        # Record successful test requests
        breaker.record_success()
        assert breaker.state == CircuitState.HALF_OPEN

        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED


class TestDomainRateLimiter:
    """Test suite for DomainRateLimiter."""

    def test_basic_rate_limiting(self):
        """Test basic rate limiting functionality."""
        config = RateLimitConfig(requests_per_minute=60)  # 1 per second
        limiter = DomainRateLimiter("example.com", config)

        # Should allow first request
        can_proceed, delay = limiter.can_make_request()
        assert can_proceed is True
        assert delay >= 0

        # Record many requests quickly
        for _ in range(60):
            limiter.record_request_start()

        # Should now be rate limited
        can_proceed, delay = limiter.can_make_request()
        assert can_proceed is False
        assert delay > 0

    def test_default_configuration_has_no_undisclosed_burst(self):
        limiter = DomainRateLimiter(
            "example.com", RateLimitConfig(requests_per_minute=1)
        )

        allowed, _ = limiter.can_make_request()
        assert allowed is True
        limiter.record_request_start()

        allowed, delay = limiter.can_make_request()
        assert allowed is False
        assert delay > 0

    def test_success_failure_tracking(self):
        """Test success and failure tracking."""
        config = RateLimitConfig()
        limiter = DomainRateLimiter("example.com", config)

        # Record requests
        start_time = limiter.record_request_start()
        limiter.record_request_end(start_time, True)  # Success

        start_time = limiter.record_request_start()
        limiter.record_request_end(start_time, False)  # Failure

        stats = limiter.get_stats()
        assert stats.total_requests == 2
        assert stats.successful_requests == 1
        assert stats.failed_requests == 1

    def test_adaptive_delay(self):
        """Test adaptive delay calculation."""
        config = RateLimitConfig(enable_adaptive_limiting=True)
        limiter = DomainRateLimiter("example.com", config)

        # Record slow responses
        start_time = time.time()
        limiter.record_request_end(start_time, True, response_time=3.0)
        limiter.record_request_end(start_time, True, response_time=4.0)

        # Should calculate adaptive delay
        adaptive_delay = limiter._calculate_adaptive_delay()
        assert adaptive_delay > 0


class TestGlobalRateLimiter:
    """Test suite for GlobalRateLimiter."""

    def test_domain_separation(self):
        """Test that different domains are tracked separately."""
        config = RateLimitConfig(requests_per_minute=2)
        limiter = GlobalRateLimiter(config)

        # Make requests to different domains
        limiter.record_request_start("https://example.com/page1")
        limiter.record_request_start("https://example.com/page2")
        limiter.record_request_start("https://other.com/page1")

        # Should create separate domain limiters
        stats = limiter.get_all_stats()
        assert "example.com" in stats
        assert "other.com" in stats
        assert stats["example.com"].total_requests == 2
        assert stats["other.com"].total_requests == 1

    def test_rate_limit_per_domain(self):
        """Test rate limiting works per domain."""
        config = RateLimitConfig(requests_per_minute=2, burst_allowance=0)
        limiter = GlobalRateLimiter(config)

        # Saturate one domain
        for _ in range(3):
            limiter.record_request_start("https://example.com/")

        # Should be rate limited for that domain
        can_proceed, _ = limiter.can_make_request("https://example.com/page")
        assert can_proceed is False

        # But should still work for other domains
        can_proceed, _ = limiter.can_make_request("https://other.com/page")
        assert can_proceed is True

    def test_hard_maximum_is_independent_for_each_destination_origin(self):
        config = RateLimitConfig(requests_per_minute=1, burst_allowance=0)
        limiter = GlobalRateLimiter(config)

        for url in ("https://a.example/page", "https://b.example/page"):
            can_proceed, _ = limiter.can_make_request(url)
            assert can_proceed is True
            limiter.record_request_start(url)

        assert limiter.can_make_request("https://a.example/next")[0] is False
        assert limiter.can_make_request("https://b.example/next")[0] is False

    def test_config_update(self):
        """Test configuration updates."""
        config1 = RateLimitConfig(requests_per_minute=10)
        limiter = GlobalRateLimiter(config1)

        # Create a domain limiter
        limiter.record_request_start("https://example.com/")

        # Update config
        config2 = RateLimitConfig(requests_per_minute=20)
        limiter.update_config(config2)

        # Should use new config
        assert limiter.config.requests_per_minute == 20

    def test_reset_functionality(self):
        """Test reset functionality."""
        config = RateLimitConfig()
        limiter = GlobalRateLimiter(config)

        # Make some requests
        limiter.record_request_start("https://example.com/")
        limiter.record_request_start("https://other.com/")

        # Should have stats
        stats = limiter.get_all_stats()
        assert len(stats) == 2

        # Reset specific domain
        limiter.reset_domain("https://example.com/")
        stats = limiter.get_all_stats()
        assert "example.com" not in stats
        assert "other.com" in stats

        # Reset all
        limiter.reset_all()
        stats = limiter.get_all_stats()
        assert len(stats) == 0


class TestRateLimitIntegration:
    """Integration tests for rate limiting."""

    def test_end_to_end_flow(self):
        """Test complete request flow with rate limiting."""
        config = RateLimitConfig(requests_per_minute=10, circuit_failure_threshold=2)
        limiter = GlobalRateLimiter(config)

        url = "https://example.com/test"

        # Normal request flow
        can_proceed, delay = limiter.can_make_request(url)
        assert can_proceed is True

        start_time = limiter.record_request_start(url)
        time.sleep(0.1)  # Simulate request time
        limiter.record_request_end(url, start_time, True)

        # Check stats
        stats = limiter.get_domain_stats(url)
        assert stats.total_requests == 1
        assert stats.successful_requests == 1
        assert stats.circuit_state == CircuitState.CLOSED

    def test_circuit_breaker_integration(self):
        """Test circuit breaker integration with rate limiting."""
        config = RateLimitConfig(
            requests_per_minute=100, circuit_failure_threshold=2  # High limit
        )
        limiter = GlobalRateLimiter(config)

        url = "https://example.com/test"

        # Record failures to trip circuit breaker
        start_time = limiter.record_request_start(url)
        limiter.record_request_end(url, start_time, False)

        start_time = limiter.record_request_start(url)
        limiter.record_request_end(url, start_time, False)

        # Circuit should be open now
        can_proceed, delay = limiter.can_make_request(url)
        assert can_proceed is False

        stats = limiter.get_domain_stats(url)
        assert stats.circuit_state == CircuitState.OPEN


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
