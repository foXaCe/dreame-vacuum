"""Tests for the Dreame Vacuum system health."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.dreame_vacuum.system_health import async_register, system_health_info


def _entry_with_device(connected: bool, cloud: bool) -> MagicMock:
    entry = MagicMock()
    device = MagicMock()
    device.device_connected = connected
    device.cloud_connected = cloud
    entry.runtime_data.coordinator.device = device
    return entry


def _hass_with_entries(entries: list[MagicMock]) -> MagicMock:
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = entries
    return hass


def test_async_register_registers_info() -> None:
    """async_register wires the info callback into the registration."""
    register = MagicMock()
    async_register(MagicMock(), register)
    register.async_register_info.assert_called_once()


async def test_system_health_info_counts_devices() -> None:
    """configured / connected / cloud-connected devices are tallied correctly."""
    hass = _hass_with_entries(
        [
            _entry_with_device(connected=True, cloud=True),
            _entry_with_device(connected=True, cloud=False),
            _entry_with_device(connected=False, cloud=False),
        ]
    )
    info = await system_health_info(hass)
    assert info == {
        "configured_devices": 3,
        "connected_devices": 2,
        "cloud_connected_devices": 1,
    }


async def test_system_health_info_skips_entries_without_runtime_data() -> None:
    """Entries still setting up (no runtime_data) and None devices are skipped."""
    entry_no_runtime = MagicMock()
    entry_no_runtime.runtime_data = None
    entry_none_device = MagicMock()
    entry_none_device.runtime_data.coordinator.device = None

    hass = _hass_with_entries([entry_no_runtime, entry_none_device, _entry_with_device(connected=True, cloud=True)])
    info = await system_health_info(hass)
    assert info == {
        "configured_devices": 1,
        "connected_devices": 1,
        "cloud_connected_devices": 1,
    }
