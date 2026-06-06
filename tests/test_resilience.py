"""Tests for Dreame Vacuum resilience module."""

import threading
import time
from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame.exceptions import CircuitOpenError
from custom_components.dreame_vacuum.dreame.resilience import (
    CircuitBreaker,
    CircuitState,
    TimeoutConfig,
    retry_with_backoff,
)

# --- TimeoutConfig ---


def test_timeout_config_defaults():
    """Test TimeoutConfig has expected defaults."""
    config = TimeoutConfig()
    assert config.login == 10.0
    assert config.request == 15.0
    assert config.file_download == 15.0
    assert config.mi_home_request == 5.0


def test_timeout_config_custom():
    """Test TimeoutConfig accepts custom values."""
    config = TimeoutConfig(login=20.0, request=30.0)
    assert config.login == 20.0
    assert config.request == 30.0
    assert config.file_download == 15.0  # default


# --- CircuitBreaker ---


def test_circuit_breaker_starts_closed():
    """Test circuit breaker starts in CLOSED state."""
    cb = CircuitBreaker()
    assert cb.state is CircuitState.CLOSED
    assert cb.is_closed


def test_circuit_breaker_opens_after_threshold():
    """Test circuit breaker opens after failure_threshold failures."""
    cb = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state is CircuitState.OPEN
    assert not cb.is_closed


def test_circuit_breaker_stays_closed_below_threshold():
    """Test circuit breaker stays closed below failure threshold."""
    cb = CircuitBreaker(failure_threshold=5)
    for _ in range(4):
        cb.record_failure()
    assert cb.state is CircuitState.CLOSED


def test_circuit_breaker_success_resets_count():
    """Test that a success resets the failure count."""
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    cb.record_failure()
    # Still closed: 2 consecutive failures, not 3
    assert cb.state is CircuitState.CLOSED


def test_circuit_breaker_half_open_after_timeout():
    """Test circuit breaker transitions to HALF_OPEN after recovery timeout."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    cb.record_failure()
    cb.record_failure()
    assert cb.state is CircuitState.OPEN

    time.sleep(0.15)
    assert cb.state is CircuitState.HALF_OPEN


def test_circuit_breaker_half_open_success_closes():
    """Test that success in HALF_OPEN transitions to CLOSED."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.15)
    assert cb.state is CircuitState.HALF_OPEN

    cb.record_success()
    assert cb.state is CircuitState.CLOSED


def test_circuit_breaker_half_open_failure_reopens():
    """Test that failure in HALF_OPEN transitions back to OPEN."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.15)
    assert cb.state is CircuitState.HALF_OPEN

    cb.record_failure()
    assert cb.state is CircuitState.OPEN


def test_circuit_breaker_reset():
    """Test circuit breaker reset returns to CLOSED."""
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure()
    cb.record_failure()
    assert cb.state is CircuitState.OPEN

    cb.reset()
    assert cb.state is CircuitState.CLOSED
    assert cb.is_closed


def test_circuit_breaker_check_raises_when_open():
    """Test check() raises CircuitOpenError when circuit is open."""
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure()
    cb.record_failure()

    with pytest.raises(CircuitOpenError):
        cb.check()


def test_circuit_breaker_check_passes_when_closed():
    """Test check() does not raise when circuit is closed."""
    cb = CircuitBreaker()
    cb.check()  # Should not raise


def test_circuit_breaker_thread_safety():
    """Test circuit breaker is safe under concurrent access."""
    cb = CircuitBreaker(failure_threshold=100)
    errors = []

    def hammer_failures():
        try:
            for _ in range(50):
                cb.record_failure()
        except Exception as exc:
            errors.append(exc)

    def hammer_successes():
        try:
            for _ in range(50):
                cb.record_success()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=hammer_failures) for _ in range(4)] + [
        threading.Thread(target=hammer_successes) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    # State should be valid (CLOSED or OPEN, not corrupted)
    assert cb.state in (CircuitState.CLOSED, CircuitState.OPEN, CircuitState.HALF_OPEN)


# --- retry_with_backoff ---


def test_retry_with_backoff_succeeds_first_try():
    """Test retry_with_backoff returns on first success."""
    func = MagicMock(return_value="ok")
    result = retry_with_backoff(func, retry_count=2, base_delay=0.01)
    assert result == "ok"
    assert func.call_count == 1


def test_retry_with_backoff_retries_on_failure():
    """Test retry_with_backoff retries the specified number of times."""
    func = MagicMock(side_effect=[ValueError("err"), ValueError("err"), "ok"])
    result = retry_with_backoff(func, retry_count=2, base_delay=0.01, exceptions=(ValueError,))
    assert result == "ok"
    assert func.call_count == 3


def test_retry_with_backoff_exhaustion():
    """Test retry_with_backoff raises last exception after exhaustion."""
    func = MagicMock(side_effect=ValueError("persistent error"))
    with pytest.raises(ValueError, match="persistent error"):
        retry_with_backoff(func, retry_count=2, base_delay=0.01, exceptions=(ValueError,))
    assert func.call_count == 3  # 1 attempt + 2 retries


def test_retry_with_backoff_only_catches_specified():
    """Test retry_with_backoff does not catch unspecified exceptions."""
    func = MagicMock(side_effect=TypeError("wrong type"))
    with pytest.raises(TypeError, match="wrong type"):
        retry_with_backoff(func, retry_count=2, base_delay=0.01, exceptions=(ValueError,))
    assert func.call_count == 1  # No retry for TypeError
