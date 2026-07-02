"""Tests for Dreame Vacuum integration setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import ConfigEntryNotReady
import pytest

import custom_components.dreame_vacuum as dreame_init
from custom_components.dreame_vacuum import (
    CONFIG_ENTRY_VERSION,
    PLATFORMS,
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.dreame_vacuum.const import DOMAIN


@pytest.fixture
def coordinator() -> MagicMock:
    """Return a mock coordinator whose first refresh succeeds with a MAC."""
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.cleanup = MagicMock()
    coordinator.device = MagicMock()
    coordinator.device.mac = "AA:BB:CC:DD:EE:FF"
    return coordinator


@pytest.fixture
def entry() -> MagicMock:
    """Return a mock config entry suitable for async_setup_entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {"name": "Test Vacuum"}
    return entry


@pytest.fixture
def hass() -> MagicMock:
    """Return a mock HomeAssistant with async config-entry helpers."""
    hass = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_reload = AsyncMock()
    return hass


def _patch_coordinator(coordinator: MagicMock):
    """Patch the coordinator class referenced by __init__ to return ``coordinator``."""
    return patch.object(dreame_init, "DreameVacuumDataUpdateCoordinator", return_value=coordinator)


def _patch_registry(device_entries: list | None = None):
    """Patch the device registry helpers used during stale-device cleanup."""
    registry = MagicMock()
    entries_patch = patch.object(dreame_init.dr, "async_entries_for_config_entry", return_value=device_entries or [])
    get_patch = patch.object(dreame_init.dr, "async_get", return_value=registry)
    return registry, get_patch, entries_patch


async def test_platforms_defined() -> None:
    """Test that platforms are defined."""
    assert len(PLATFORMS) > 0
    assert "vacuum" in [p.value for p in PLATFORMS]
    assert "sensor" in [p.value for p in PLATFORMS]


async def test_config_entry_version() -> None:
    """Test config entry version is defined."""
    assert CONFIG_ENTRY_VERSION >= 1


async def test_domain_constant() -> None:
    """Test that domain constant is correct."""
    assert DOMAIN == "dreame_vacuum"


async def test_platforms_contains_expected() -> None:
    """Test that expected platforms are included."""
    platform_values = [p.value for p in PLATFORMS]
    expected_platforms = ["vacuum", "sensor", "binary_sensor", "switch", "button"]
    for platform in expected_platforms:
        assert platform in platform_values, f"Missing platform: {platform}"


# --- async_setup_entry ----------------------------------------------------------


async def test_setup_entry_success(hass: MagicMock, entry: MagicMock, coordinator: MagicMock) -> None:
    """A healthy first refresh sets up runtime data and forwards platforms."""
    registry, get_patch, entries_patch = _patch_registry()
    with _patch_coordinator(coordinator), get_patch, entries_patch:
        result = await async_setup_entry(hass, entry)

    assert result is True
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    assert entry.runtime_data.coordinator is coordinator
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, PLATFORMS)
    # Options reload is handled by OptionsFlowWithReload; no manual listener.
    entry.add_update_listener.assert_not_called()
    coordinator.cleanup.assert_not_called()


async def test_setup_entry_no_mac_raises_not_ready_and_cleans_up(
    hass: MagicMock, entry: MagicMock, coordinator: MagicMock
) -> None:
    """A successful refresh without a MAC must raise ConfigEntryNotReady and clean up.

    Without a MAC the integration cannot build a stable unique_id, so it aborts
    and HA retries — but the coordinator's worker threads must be released first.
    """
    coordinator.device.mac = None
    registry, get_patch, entries_patch = _patch_registry()
    with _patch_coordinator(coordinator), get_patch, entries_patch, pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)

    coordinator.cleanup.assert_called_once()
    hass.config_entries.async_forward_entry_setups.assert_not_called()


async def test_setup_entry_no_device_raises_not_ready_and_cleans_up(
    hass: MagicMock, entry: MagicMock, coordinator: MagicMock
) -> None:
    """A missing device object also aborts with cleanup."""
    coordinator.device = None
    registry, get_patch, entries_patch = _patch_registry()
    with _patch_coordinator(coordinator), get_patch, entries_patch, pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)

    coordinator.cleanup.assert_called_once()


async def test_setup_entry_first_refresh_failure_calls_cleanup(
    hass: MagicMock, entry: MagicMock, coordinator: MagicMock
) -> None:
    """If the first refresh raises, cleanup() must run and the error propagates.

    This pins the recent fix: HA does not call async_unload_entry when setup
    raises, so the coordinator releases its threads/timers itself.
    """
    coordinator.async_config_entry_first_refresh.side_effect = ConfigEntryNotReady("boom")
    registry, get_patch, entries_patch = _patch_registry()
    with (
        _patch_coordinator(coordinator),
        get_patch,
        entries_patch,
        pytest.raises(ConfigEntryNotReady, match="boom"),
    ):
        await async_setup_entry(hass, entry)

    coordinator.cleanup.assert_called_once()
    hass.config_entries.async_forward_entry_setups.assert_not_called()


async def test_setup_entry_removes_stale_devices(hass: MagicMock, entry: MagicMock, coordinator: MagicMock) -> None:
    """Device-registry entries whose identifiers no longer match are removed.

    Each config entry maps to exactly one device; the entry keyed by the current
    MAC is kept, the stale one is dropped.
    """
    stale = MagicMock()
    stale.id = "stale_id"
    stale.name = "Old Vacuum"
    stale.identifiers = {(DOMAIN, "00:00:00:00:00:00")}
    current = MagicMock()
    current.id = "current_id"
    current.name = "Test Vacuum"
    current.identifiers = {(DOMAIN, "AA:BB:CC:DD:EE:FF")}

    registry, get_patch, entries_patch = _patch_registry([stale, current])
    with _patch_coordinator(coordinator), get_patch, entries_patch:
        await async_setup_entry(hass, entry)

    registry.async_remove_device.assert_called_once_with("stale_id")


# --- async_unload_entry ---------------------------------------------------------


async def test_unload_entry_success_calls_cleanup(hass: MagicMock, entry: MagicMock) -> None:
    """A successful platform unload cleans up the coordinator."""
    coordinator = MagicMock()
    entry.runtime_data.coordinator = coordinator
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    result = await async_unload_entry(hass, entry)

    assert result is True
    coordinator.cleanup.assert_called_once()


async def test_unload_entry_failure_skips_cleanup(hass: MagicMock, entry: MagicMock) -> None:
    """If platforms fail to unload, the coordinator is left intact."""
    coordinator = MagicMock()
    entry.runtime_data.coordinator = coordinator
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

    result = await async_unload_entry(hass, entry)

    assert result is False
    coordinator.cleanup.assert_not_called()


# --- async_migrate_entry --------------------------------------------------------


async def test_migrate_entry_same_version_noop(hass: MagicMock) -> None:
    """Migrating an entry already at the current version is a no-op success."""
    config_entry = MagicMock()
    config_entry.version = CONFIG_ENTRY_VERSION

    assert await async_migrate_entry(hass, config_entry) is True
    hass.config_entries.async_update_entry.assert_not_called()


async def test_migrate_entry_older_version_updates(hass: MagicMock) -> None:
    """An older entry is bumped to the current version."""
    config_entry = MagicMock()
    config_entry.version = CONFIG_ENTRY_VERSION - 1

    assert await async_migrate_entry(hass, config_entry) is True
    hass.config_entries.async_update_entry.assert_called_once_with(config_entry, version=CONFIG_ENTRY_VERSION)
