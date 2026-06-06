"""Exceptions for Dreame Vacuum device communication."""

from __future__ import annotations


class DeviceException(Exception):
    """Exception wrapping any communication errors with the device."""


class DeviceUpdateFailedException(DeviceException):
    """Raised when a device update/refresh operation fails."""


class InvalidValueException(ValueError):
    """Raised when an invalid value is provided for a device property."""


class InvalidActionException(ValueError):
    """Raised when an invalid or unsupported action is requested."""


class AuthenticationError(DeviceException):
    """Raised on HTTP 401 or login failures."""


class DeviceConnectionError(DeviceException):
    """Raised when the failure threshold is reached and the device is unreachable."""


class RateLimitError(DeviceException):
    """Raised on HTTP 429 responses.

    Attributes:
        retry_after: Seconds to wait before retrying.
    """

    def __init__(self, message: str = "Rate limited", retry_after: float = 60.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class InvalidResponseError(DeviceException):
    """Raised when the API returns invalid or unparsable JSON."""


class CircuitOpenError(DeviceConnectionError):
    """Raised when the circuit breaker is open and requests are rejected."""
