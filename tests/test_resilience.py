"""Tests for Dreame Vacuum resilience module."""

import threading
import time

from custom_components.dreame_vacuum.dreame.resilience import (
    CircuitBreaker,
    CircuitState,
    TimeoutConfig,
    backoff_delay,
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


# --- backoff_delay ---


def test_backoff_delay_grows_exponentially_without_jitter():
    """Delays double each attempt and are capped at max_delay."""
    assert backoff_delay(1, jitter=False) == 0.5
    assert backoff_delay(2, jitter=False) == 1.0
    assert backoff_delay(3, jitter=False) == 2.0
    assert backoff_delay(10, jitter=False) == 10.0  # capped


def test_backoff_delay_jitter_stays_in_bounds():
    """With jitter the delay stays within 50%-150% of the nominal value."""
    for attempt in (1, 2, 5):
        nominal = backoff_delay(attempt, jitter=False)
        for _ in range(50):
            delay = backoff_delay(attempt)
            assert nominal * 0.5 <= delay <= nominal * 1.5


def test_backoff_delay_custom_base_and_cap():
    """base_delay and max_delay parameters drive the progression."""
    assert backoff_delay(1, base_delay=2.0, max_delay=5.0, jitter=False) == 2.0
    assert backoff_delay(2, base_delay=2.0, max_delay=5.0, jitter=False) == 4.0
    assert backoff_delay(3, base_delay=2.0, max_delay=5.0, jitter=False) == 5.0  # capped
