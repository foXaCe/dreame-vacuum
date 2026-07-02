"""Tests for Dreame Vacuum diagnostics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
)


@pytest.fixture
def entry() -> MagicMock:
    """Return a config entry carrying secrets in both data and options."""
    entry = MagicMock()
    entry.data = {
        "name": "Test Vacuum",
        "host": "192.168.1.50",
        "token": "supersecrettoken",
        "username": "user@example.com",
        "password": "hunter2",
        "auth_key": "secret_auth_key",
        "mac": "AA:BB:CC:DD:EE:FF",
        "did": "123456789",
    }
    entry.options = {
        "color_scheme": "Dreame Light",
        "access_token": "another_secret",
    }
    return entry


@pytest.fixture
def device() -> MagicMock:
    """Return a connected device mock with populated status and info."""
    device = MagicMock()
    device.name = "Test Vacuum"
    device.device_connected = True
    device.cloud_connected = True
    device.info.model = "dreame.vacuum.test"
    device.info.version = "1.2.3"

    device.status.battery_level = 88
    device.status.state.name = "cleaning"
    device.status.task_status.name = "auto_cleaning"
    device.status.water_tank.name = "installed"
    device.status.error.name = "no_error"
    return device


def _entry_with_device(entry: MagicMock, device: MagicMock | None) -> MagicMock:
    entry.runtime_data.coordinator.device = device
    return entry


def test_to_redact_is_stable() -> None:
    """Pin the full redaction set.

    Any new sensitive key must be added intentionally; this test catches
    accidental removal of redactions when diagnostics.py is edited. Kept
    as a plain assertion (rather than a syrupy snapshot) to avoid adding
    a dev-only pytest plugin to the test requirements.
    """
    expected = {
        "_client_id",
        "_key",
        "_secondary_key",
        "access_token",
        "auth_key",
        "client_id",
        "did",
        "host",
        "key",
        "mac",
        "password",
        "secondary_key",
        "serial_number",
        "service_token",
        "ssecurity",
        "token",
        "uid",
        "username",
        "uuid",
    }
    assert set(TO_REDACT) == expected


# --- async_get_config_entry_diagnostics ----------------------------------------

REDACTED = "**REDACTED**"


async def test_diagnostics_redacts_secrets(entry: MagicMock, device: MagicMock) -> None:
    """Secrets in entry.data and entry.options are redacted in the output."""
    diagnostics = await async_get_config_entry_diagnostics(MagicMock(), _entry_with_device(entry, device))

    data = diagnostics["entry"]["data"]
    assert data["token"] == REDACTED
    assert data["password"] == REDACTED
    assert data["username"] == REDACTED
    assert data["auth_key"] == REDACTED
    assert data["mac"] == REDACTED
    assert data["did"] == REDACTED
    assert data["host"] == REDACTED
    # Non-secret values pass through untouched.
    assert data["name"] == "Test Vacuum"

    options = diagnostics["entry"]["options"]
    assert options["access_token"] == REDACTED
    assert options["color_scheme"] == "Dreame Light"

    # No secret value must leak anywhere in the rendered diagnostics.
    rendered = repr(diagnostics)
    for leak in ("supersecrettoken", "hunter2", "secret_auth_key", "another_secret"):
        assert leak not in rendered


async def test_diagnostics_device_section(entry: MagicMock, device: MagicMock) -> None:
    """The device section reports name/model/firmware and connection flags."""
    diagnostics = await async_get_config_entry_diagnostics(MagicMock(), _entry_with_device(entry, device))

    dev = diagnostics["device"]
    assert dev["name"] == "Test Vacuum"
    assert dev["model"] == "dreame.vacuum.test"
    assert dev["firmware"] == "1.2.3"
    assert dev["connected"] is True
    assert dev["cloud_connected"] is True


async def test_diagnostics_status_section(entry: MagicMock, device: MagicMock) -> None:
    """The status section reflects the device status enum names."""
    diagnostics = await async_get_config_entry_diagnostics(MagicMock(), _entry_with_device(entry, device))

    status = diagnostics["status"]
    assert status["battery_level"] == 88
    assert status["state"] == "cleaning"
    assert status["task_status"] == "auto_cleaning"
    assert status["water_tank"] == "installed"
    assert status["error"] == "no_error"


async def test_diagnostics_no_device(entry: MagicMock) -> None:
    """With no device, the device section is empty and no status key is present."""
    diagnostics = await async_get_config_entry_diagnostics(MagicMock(), _entry_with_device(entry, None))

    dev = diagnostics["device"]
    assert dev["name"] is None
    assert dev["model"] is None
    assert dev["firmware"] is None
    assert dev["connected"] is False
    assert dev["cloud_connected"] is False
    assert "status" not in diagnostics


async def test_diagnostics_device_without_status(entry: MagicMock, device: MagicMock) -> None:
    """A device whose status is None omits the status section but keeps device info."""
    device.status = None
    diagnostics = await async_get_config_entry_diagnostics(MagicMock(), _entry_with_device(entry, device))

    assert "status" not in diagnostics
    assert diagnostics["device"]["model"] == "dreame.vacuum.test"


async def test_diagnostics_status_enum_none_fields(entry: MagicMock, device: MagicMock) -> None:
    """Enum status fields that are None render as None rather than raising."""
    device.status.state = None
    device.status.task_status = None
    device.status.water_tank = None
    device.status.error = None
    diagnostics = await async_get_config_entry_diagnostics(MagicMock(), _entry_with_device(entry, device))

    status = diagnostics["status"]
    assert status["state"] is None
    assert status["task_status"] is None
    assert status["water_tank"] is None
    assert status["error"] is None


async def test_diagnostics_device_without_info(entry: MagicMock, device: MagicMock) -> None:
    """A device with no ``info`` reports model/firmware as None but stays connected."""
    device.info = None
    diagnostics = await async_get_config_entry_diagnostics(MagicMock(), _entry_with_device(entry, device))

    dev = diagnostics["device"]
    assert dev["model"] is None
    assert dev["firmware"] is None
    assert dev["name"] == "Test Vacuum"
