"""Tests for Dreame Vacuum exceptions."""

import pytest

from custom_components.dreame_vacuum.dreame.exceptions import (
    DeviceConnectionError,
    DeviceException,
    DeviceUpdateFailedException,
    InvalidActionException,
    InvalidValueException,
    RateLimitError,
)


def test_exception_hierarchy():
    """Test that all exceptions inherit from the expected base classes."""
    assert issubclass(DeviceUpdateFailedException, DeviceException)
    assert issubclass(DeviceConnectionError, DeviceException)
    assert issubclass(RateLimitError, DeviceException)
    assert issubclass(InvalidValueException, ValueError)
    assert issubclass(InvalidActionException, ValueError)


def test_backward_compat_catch():
    """Catching DeviceException catches every device-level exception."""
    for exc_cls in (DeviceConnectionError, RateLimitError, DeviceUpdateFailedException):
        with pytest.raises(DeviceException):
            raise exc_cls("test")


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
