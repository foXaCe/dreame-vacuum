"""Common fixtures for Dreame Vacuum tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
)
import pytest

from custom_components.dreame_vacuum.const import DOMAIN


@pytest.fixture
def mock_config_entry():
    """Return a mock config entry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        title="Dreame Vacuum",
        data={
            CONF_NAME: "Test Vacuum",
            CONF_HOST: "192.168.1.100",
            CONF_TOKEN: "a" * 32,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "password",
            "country": "eu",
            "mac": "AA:BB:CC:DD:EE:FF",
            "did": "123456789",
            "account_type": "dreame",
        },
        options={
            "notify": ["cleanup_completed", "error"],
            "color_scheme": "Dreame Light",
            "icon_set": "Dreame",
        },
        unique_id="aa:bb:cc:dd:ee:ff",
    )


@pytest.fixture
def mock_device() -> MagicMock:
    """Return a mock device."""
    device = MagicMock()
    device.name = "Test Vacuum"
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.available = True
    device.device_connected = True
    device.cloud_connected = True
    device.disconnected = False
    device.auth_failed = False

    # Mock status
    device.status = MagicMock()
    device.status.battery_level = 100
    device.status.state = MagicMock()
    device.status.state.name = "idle"
    device.status.task_status = MagicMock()
    device.status.task_status.name = "completed"
    device.status.has_warning = False
    device.status.has_error = False

    # Mock info
    device.info = MagicMock()
    device.info.model = "dreame.vacuum.test"
    device.info.version = "1.0.0"

    # Mock capability
    device.capability = MagicMock()
    device.capability.map = True
    device.capability.dnd = True
    device.capability.shortcuts = True

    return device


@pytest.fixture
def mock_coordinator(mock_device: MagicMock) -> MagicMock:
    """Return a mock coordinator."""
    coordinator = MagicMock()
    coordinator.device = mock_device
    coordinator.last_update_success = True
    coordinator.async_refresh = AsyncMock()
    return coordinator


@pytest.fixture
def mock_dreame_vacuum_protocol() -> Generator[MagicMock, None, None]:
    """Mock DreameVacuumProtocol."""
    with patch("custom_components.dreame_vacuum.config_flow.DreameVacuumProtocol") as mock_protocol:
        protocol = MagicMock()
        protocol.cloud = MagicMock()
        protocol.cloud.logged_in = True
        protocol.cloud.captcha_img = None
        protocol.cloud.verification_url = None
        protocol.cloud.auth_key = "test_auth_key"
        protocol.cloud.get_supported_devices = MagicMock(
            return_value=(
                {
                    "test_device": {
                        "mac": "AA:BB:CC:DD:EE:FF",
                        "model": "dreame.vacuum.test",
                        "name": "Test Vacuum",
                        "did": "123456789",
                        "bindDomain": "192.168.1.100",
                        "customName": "My Vacuum",
                        "deviceInfo": {"displayName": "Dreame Test"},
                    }
                },
                {},
            )
        )
        mock_protocol.return_value = protocol
        yield mock_protocol
