"""Resilience primitives for Dreame Vacuum API communication.

Provides circuit breaker, configurable timeouts, and retry with exponential backoff.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
import logging
import random
import threading
import time
from typing import TypeVar

from .exceptions import CircuitOpenError

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class TimeoutConfig:
    """Configurable timeout values for different API operations."""

    login: float = 10.0
    request: float = 15.0
    file_download: float = 15.0
    mi_home_request: float = 5.0


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Thread-safe circuit breaker.

    Transitions:
        CLOSED  → OPEN       after `failure_threshold` consecutive failures
        OPEN    → HALF_OPEN  after `recovery_timeout` seconds
        HALF_OPEN → CLOSED   on first success
        HALF_OPEN → OPEN     on first failure
    """

    failure_threshold: int = 5
    recovery_timeout: float = 300.0  # 5 minutes
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state is CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    _LOGGER.debug("Circuit breaker → HALF_OPEN (recovery timeout elapsed)")
            return self._state

    @property
    def is_closed(self) -> bool:
        return self.state is CircuitState.CLOSED

    def check(self) -> None:
        """Raise CircuitOpenError if the circuit is open."""
        with self._lock:
            if self._state is CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    _LOGGER.debug("Circuit breaker → HALF_OPEN (recovery timeout elapsed)")
                else:
                    raise CircuitOpenError(
                        f"Circuit breaker is open ({self._failure_count} consecutive failures). "
                        f"Will retry in {self.recovery_timeout - (time.monotonic() - self._last_failure_time):.0f}s."
                    )

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state is not CircuitState.CLOSED:
                _LOGGER.info("Circuit breaker → CLOSED (success recorded)")
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                _LOGGER.warning("Circuit breaker → OPEN (failure during HALF_OPEN)")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                _LOGGER.warning("Circuit breaker → OPEN (%d consecutive failures)", self._failure_count)

    def reset(self) -> None:
        """Reset to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = 0.0


def retry_with_backoff(
    func: Callable[[], T],
    *,
    retry_count: int = 2,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    jitter: bool = True,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Retry a callable with exponential backoff.

    Args:
        func: Zero-argument callable to retry.
        retry_count: Maximum number of retries (0 = no retry, just one attempt).
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay in seconds.
        jitter: Add random jitter to delay.
        exceptions: Exception types to catch and retry on.

    Returns:
        The return value of func on success.

    Raises:
        The last exception if all attempts fail.
    """
    last_exc: BaseException | None = None
    for attempt in range(retry_count + 1):
        try:
            return func()
        except exceptions as exc:
            last_exc = exc
            if attempt < retry_count:
                delay = min(base_delay * (2**attempt), max_delay)
                if jitter:
                    delay *= 0.5 + random.random()
                _LOGGER.debug(
                    "Retry %d/%d after %.1fs (error: %s)",
                    attempt + 1,
                    retry_count,
                    delay,
                    exc,
                )
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]
