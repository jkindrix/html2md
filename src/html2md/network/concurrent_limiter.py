"""Sequential crawler request accounting and progressive backoff policy."""

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Set, Tuple, Deque, Any
from urllib.parse import urlparse

logger = logging.getLogger("html2md")


class BackoffStrategy(Enum):
    """Backoff strategies for error handling."""
    NONE = "none"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    FIBONACCI = "fibonacci"


@dataclass
class DomainState:
    """State tracking for a specific domain."""
    active_connections: int = 0
    last_request_time: float = 0
    consecutive_errors: int = 0
    backoff_until: Optional[float] = None
    total_requests: int = 0
    total_errors: int = 0
    last_429_time: Optional[float] = None
    retry_after: Optional[int] = None
    error_times: Deque[float] = field(default_factory=lambda: deque(maxlen=10))


@dataclass
class ConcurrentConfig:
    """Configuration retained for request accounting and backoff policy."""
    
    # Backoff configuration
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    initial_backoff: float = 1.0
    max_backoff: float = 300.0  # 5 minutes
    backoff_multiplier: float = 2.0
    retry_after_respect: bool = True
    
    # Error thresholds
    error_threshold_for_backoff: int = 3
    reset_threshold_minutes: int = 10
    
    # Polite mode settings
    polite_mode: bool = False
    polite_delay_multiplier: float = 2.0
    
    # Progress tracking
    enable_progress_tracking: bool = True


class ConcurrentLimiter:
    """
    Tracks the single synchronous crawler request and domain backoff state.

    The crawler is deliberately sequential. A single re-entrant lock protects
    every state transition so future threaded callers cannot introduce lock-order
    inversion while the compatibility configuration is retired.
    """
    
    def __init__(self, config: Optional[ConcurrentConfig] = None):
        self.config = config or ConcurrentConfig()
        self.domain_states: Dict[str, DomainState] = defaultdict(DomainState)
        self.active_domains: Set[str] = set()
        self.global_active: int = 0
        self._lock = threading.RLock()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused by default
        
        # Progress tracking
        self.total_urls_queued: int = 0
        self.total_urls_completed: int = 0
        self.total_errors: int = 0
        self.start_time: float = time.time()
        
        # Apply polite mode adjustments
        if self.config.polite_mode:
            logger.info("Polite mode enabled for sequential request policy")
    
    def get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        return urlparse(url).netloc
    
    def can_make_request(self, url: str) -> Tuple[bool, Optional[float]]:
        """
        Check if a request can be made to the URL's domain.
        
        Returns:
            Tuple of (can_proceed, wait_time_seconds)
        """
        domain = self.get_domain(url)
        
        with self._lock:
            state = self.domain_states[domain]
            
            # Check if paused
            if not self._pause_event.is_set():
                return False, None
            
            # Check backoff
            if state.backoff_until and time.time() < state.backoff_until:
                wait_time = state.backoff_until - time.time()
                logger.debug(f"Domain {domain} in backoff for {wait_time:.1f}s")
                return False, wait_time
            
            if state.active_connections or self.global_active:
                return False, None
            
            return True, None
    
    def acquire_slot(self, url: str) -> bool:
        """
        Try to acquire a slot for making a request.
        
        Returns:
            True if slot acquired, False otherwise
        """
        domain = self.get_domain(url)
        
        # Wait for unpause
        self._pause_event.wait()
        
        # Check if we can proceed
        can_proceed, wait_time = self.can_make_request(url)
        if not can_proceed:
            if wait_time:
                logger.info(f"Waiting {wait_time:.1f}s for domain {domain} backoff")
                time.sleep(wait_time)
                # Retry after wait
                can_proceed, _ = self.can_make_request(url)
                if not can_proceed:
                    return False
            else:
                return False
        
        # Acquire the slot
        with self._lock:
            with self._lock:
                # Double-check availability
                state = self.domain_states[domain]
                if state.active_connections == 0 and self.global_active == 0:
                    state.active_connections += 1
                    self.global_active += 1
                    self.active_domains.add(domain)
                    self.total_urls_queued += 1
                    logger.debug(f"Acquired slot for {domain} ({state.active_connections} active)")
                    return True
                else:
                    return False
    
    def release_slot(self, url: str, success: bool = True, 
                    status_code: Optional[int] = None,
                    retry_after: Optional[int] = None):
        """Release a slot after request completion."""
        domain = self.get_domain(url)
        
        with self._lock:
            with self._lock:
                state = self.domain_states[domain]
                
                # Update connection count
                if state.active_connections > 0:
                    state.active_connections -= 1
                    self.global_active -= 1
                    
                if state.active_connections == 0:
                    self.active_domains.discard(domain)
                
                # Update statistics
                state.total_requests += 1
                self.total_urls_completed += 1
                
                # Update error tracking
                if not success or (status_code and status_code >= 400):
                    state.consecutive_errors += 1
                    state.total_errors += 1
                    state.error_times.append(time.time())
                    self.total_errors += 1
                    
                    logger.info(f"Error for domain {domain}: status={status_code}, "
                              f"consecutive={state.consecutive_errors}")
                    
                    # Handle specific error codes
                    if status_code == 429:
                        state.last_429_time = time.time()
                        if retry_after and self.config.retry_after_respect:
                            state.retry_after = retry_after
                            state.backoff_until = time.time() + retry_after
                            logger.warning(f"Domain {domain} requested retry after {retry_after}s")
                        else:
                            self._apply_backoff(domain, state)
                    elif status_code and status_code >= 500:
                        self._apply_backoff(domain, state)
                    elif state.consecutive_errors >= self.config.error_threshold_for_backoff:
                        self._apply_backoff(domain, state)
                else:
                    # Reset on success
                    if state.consecutive_errors > 0:
                        logger.info(f"Domain {domain} recovered after {state.consecutive_errors} errors")
                    state.consecutive_errors = 0
                    
                    # Clear backoff if enough time has passed
                    if state.backoff_until and time.time() > state.backoff_until:
                        state.backoff_until = None
                
                logger.debug(f"Released slot for {domain} ({state.active_connections} active)")
    
    def _apply_backoff(self, domain: str, state: DomainState):
        """Apply backoff strategy to a domain."""
        if self.config.backoff_strategy == BackoffStrategy.NONE:
            return
        
        # Calculate backoff time based on strategy
        if self.config.backoff_strategy == BackoffStrategy.LINEAR:
            backoff_time = self.config.initial_backoff * state.consecutive_errors
        elif self.config.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            backoff_time = self.config.initial_backoff * (
                self.config.backoff_multiplier ** (state.consecutive_errors - 1)
            )
        elif self.config.backoff_strategy == BackoffStrategy.FIBONACCI:
            # Fibonacci sequence for backoff
            fib = [self.config.initial_backoff, self.config.initial_backoff]
            for i in range(2, state.consecutive_errors + 1):
                fib.append(fib[-1] + fib[-2])
            backoff_time = fib[-1]
        else:
            backoff_time = self.config.initial_backoff
        
        # Apply max backoff limit
        backoff_time = min(backoff_time, self.config.max_backoff)
        
        # Apply polite mode multiplier
        if self.config.polite_mode:
            backoff_time *= self.config.polite_delay_multiplier
        
        state.backoff_until = time.time() + backoff_time
        
        logger.warning(f"Applying {backoff_time:.1f}s backoff to domain {domain} "
                      f"after {state.consecutive_errors} consecutive errors")
    
    def pause(self):
        """Pause all request processing."""
        self._pause_event.clear()
        logger.info("Request processing paused")
    
    def resume(self):
        """Resume request processing."""
        self._pause_event.set()
        logger.info("Request processing resumed")
    
    def is_paused(self) -> bool:
        """Check if processing is paused."""
        return not self._pause_event.is_set()
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Get progress information.
        
        Returns:
            Dictionary with progress metrics
        """
        elapsed = time.time() - self.start_time
        rate = self.total_urls_completed / elapsed if elapsed > 0 else 0
        
        # Calculate domain statistics
        with self._lock:
            active_domain_count = len(self.active_domains)
            backoff_domains = sum(1 for state in self.domain_states.values() 
                                if state.backoff_until and time.time() < state.backoff_until)
            
            # Count queued (this is approximate since we don't maintain a queue)
            queued = self.total_urls_queued - self.total_urls_completed
            
            # Estimate time remaining
            eta_seconds = queued / rate if rate > 0 and queued > 0 else None
        
        return {
            'total_queued': self.total_urls_queued,
            'total_completed': self.total_urls_completed,
            'total_errors': self.total_errors,
            'currently_active': self.global_active,
            'active_domains': active_domain_count,
            'domains_in_backoff': backoff_domains,
            'requests_per_second': rate,
            'elapsed_seconds': elapsed,
            'eta_seconds': eta_seconds,
            'queued_requests': queued,
            'is_paused': not self._pause_event.is_set(),
        }
    
    def get_domain_stats(self, domain: str) -> Dict[str, Any]:
        """Get statistics for a specific domain."""
        with self._lock:
            state = self.domain_states.get(domain)
            if not state:
                return {}
            
            return {
                'active_connections': state.active_connections,
                'total_requests': state.total_requests,
                'total_errors': state.total_errors,
                'consecutive_errors': state.consecutive_errors,
                'in_backoff': bool(state.backoff_until and time.time() < state.backoff_until),
                'backoff_remaining': max(0, (state.backoff_until - time.time()) 
                                       if state.backoff_until else 0),
                'error_rate': (state.total_errors / state.total_requests * 100 
                             if state.total_requests > 0 else 0)
            }
    
    def get_all_domain_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all domains."""
        stats = {}
        for domain in list(self.domain_states.keys()):
            stats[domain] = self.get_domain_stats(domain)
        return stats
    
    def reset_domain(self, domain: str):
        """Reset error state for a domain."""
        with self._lock:
            if domain in self.domain_states:
                state = self.domain_states[domain]
                state.consecutive_errors = 0
                state.backoff_until = None
                logger.info(f"Reset error state for domain: {domain}")
    
    def should_wait(self, url: str) -> Optional[float]:
        """
        Check if we should wait before making a request.
        
        Returns:
            Wait time in seconds, or None if no wait needed
        """
        can_proceed, wait_time = self.can_make_request(url)
        if not can_proceed and wait_time:
            return wait_time
        return None
    
    def update_domain_config(self, domain: str, config: Dict[str, Any]):
        """
        Update configuration for a specific domain.
        
        Args:
            domain: Domain to configure
            config: Configuration values (max_concurrent, backoff_multiplier, etc.)
        """
        # This would be used with domain_limits configuration
        logger.info(f"Updated configuration for domain {domain}: {config}")
        # Implementation would store domain-specific overrides
