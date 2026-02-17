"""
Shared resilience utilities for the WASDE pipeline.

Provides: structured logging, retry with backoff, circuit breaker,
thread-safe token management, and timezone helpers.
"""

import logging
import random
import threading
import time
import functools
from datetime import datetime

import pytz

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

_ET = pytz.timezone("America/New_York")


def get_logger(name: str) -> logging.Logger:
    """Return a logger with a consistent format (timestamp + level + name)."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


# ---------------------------------------------------------------------------
# Retry decorator with exponential backoff + jitter
# ---------------------------------------------------------------------------


def retry(max_attempts=3, base_delay=1.0, max_delay=30.0, exceptions=(Exception,)):
    """Decorator: retry on failure with exponential backoff and jitter.

    Args:
        max_attempts: Total attempts (including the first).
        base_delay: Initial delay in seconds.
        max_delay: Cap on delay.
        exceptions: Tuple of exception types to catch.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            logger = get_logger(fn.__module__ or "retry")
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            fn.__name__, max_attempts, exc,
                        )
                        raise
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    jitter = random.uniform(0, delay * 0.5)
                    sleep_time = delay + jitter
                    logger.warning(
                        "%s attempt %d/%d failed (%s), retrying in %.1fs",
                        fn.__name__, attempt, max_attempts, exc, sleep_time,
                    )
                    time.sleep(sleep_time)
            raise last_exc  # should never reach here
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Simple circuit breaker: CLOSED -> OPEN -> HALF_OPEN -> CLOSED.

    Args:
        failure_threshold: Consecutive failures before opening.
        recovery_timeout: Seconds to wait before trying half-open.
        name: Label for log messages.
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold=5, recovery_timeout=60, name="circuit"):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()
        self._logger = get_logger(f"circuit.{name}")

    @property
    def state(self):
        with self._lock:
            if self._state == self.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = self.HALF_OPEN
                    self._logger.info("Circuit %s -> HALF_OPEN", self.name)
            return self._state

    def record_success(self):
        with self._lock:
            if self._state in (self.HALF_OPEN, self.CLOSED):
                self._failure_count = 0
                if self._state == self.HALF_OPEN:
                    self._logger.info("Circuit %s -> CLOSED", self.name)
                self._state = self.CLOSED

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                if self._state != self.OPEN:
                    self._logger.warning(
                        "Circuit %s -> OPEN after %d failures",
                        self.name, self._failure_count,
                    )
                self._state = self.OPEN

    def allow_request(self) -> bool:
        """Return True if a request should be attempted."""
        return self.state != self.OPEN


# ---------------------------------------------------------------------------
# Thread-safe Token Manager
# ---------------------------------------------------------------------------

class TokenManager:
    """Thread-safe cache for an access token with expiry."""

    def __init__(self):
        self._token = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def get_token(self):
        with self._lock:
            if self._token and time.time() < self._expires_at:
                return self._token
            return None

    def set_token(self, token: str, ttl_seconds: float = 840):
        with self._lock:
            self._token = token
            self._expires_at = time.time() + ttl_seconds

    def clear(self):
        with self._lock:
            self._token = None
            self._expires_at = 0.0


# ---------------------------------------------------------------------------
# Timezone helper
# ---------------------------------------------------------------------------

def now_et() -> datetime:
    """Return current time in US Eastern (America/New_York)."""
    return datetime.now(_ET)
