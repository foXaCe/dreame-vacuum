"""Tests for Dreame Vacuum exceptions."""

from custom_components.dreame_vacuum.dreame.exceptions import (
    AuthenticationError,
    CircuitOpenError,
    DeviceConnectionError,
    DeviceException,
    DeviceUpdateFailedException,
    InvalidActionException,
    InvalidResponseError,
    InvalidValueException,
    RateLimitError,
)


def test_exception_hierarchy():
    """Test that all exceptions inherit from the expected base classes."""
    assert issubclass(DeviceUpdateFailedException, DeviceException)
    assert issubclass(AuthenticationError, DeviceException)
    assert issubclass(DeviceConnectionError, DeviceException)
    assert issubclass(RateLimitError, DeviceException)
    assert issubclass(InvalidResponseError, DeviceException)
    assert issubclass(CircuitOpenError, DeviceConnectionError)
    assert issubclass(InvalidValueException, ValueError)
    assert issubclass(InvalidActionException, ValueError)


def test_backward_compat_catch():
    """Test that catching DeviceException still catches all new exceptions."""
    for exc_cls in (AuthenticationError, DeviceConnectionError, RateLimitError, InvalidResponseError, CircuitOpenError):
        try:
            raise exc_cls("test")
        except DeviceException:
            pass  # Expected — backward compatible


def test_rate_limit_error_attributes():
    """Test RateLimitError stores retry_after."""
    exc = RateLimitError("slow down", retry_after=120.0)
    assert exc.retry_after == 120.0
    assert str(exc) == "slow down"


def test_rate_limit_error_defaults():
    """Test RateLimitError has sensible defaults."""
    exc = RateLimitError()
    assert exc.retry_after == 60.0
    assert str(exc) == "Rate limited"
