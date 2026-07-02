"""The Dreame Vacuum integration for Home Assistant.

This integration provides support for Dreame vacuum robots, including:
- Live and multi-floor map support
- Cleaning and cruising history
- Room-based cleaning controls
- Device settings and configuration
"""

from __future__ import annotations

import logging
import time as time_module

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import CONFIG_ENTRY_VERSION, DOMAIN, DreameVacuumConfigEntry, DreameVacuumRuntimeData
from .coordinator import DreameVacuumDataUpdateCoordinator

# Apply patch for python-miio Python 3.13 compatibility
from .dreame.miio_patch import apply_miio_patch

apply_miio_patch()

_LOGGER = logging.getLogger(__name__)

PLATFORMS = (
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.CAMERA,
    Platform.TIME,
)


async def async_setup_entry(hass: HomeAssistant, entry: DreameVacuumConfigEntry) -> bool:
    """Set up Dreame Vacuum from a config entry."""
    _LOGGER.info("Starting Dreame Vacuum integration setup for %s", entry.data.get("name", "unknown"))
    setup_start = time_module.time()

    # Step 1: Initialize coordinator
    t0 = time_module.time()
    coordinator = DreameVacuumDataUpdateCoordinator(hass, entry=entry)
    _LOGGER.debug("Coordinator initialization took %.2f seconds", time_module.time() - t0)

    # Store runtime data on the config entry (Platinum pattern)
    entry.runtime_data = DreameVacuumRuntimeData(coordinator=coordinator)

    # Step 2: Initial device refresh (must be done BEFORE platform setup)
    # This ensures the device is initialized before entities are created
    t2 = time_module.time()
    try:
        await coordinator.async_config_entry_first_refresh()

        # Step 3: Ensure the device is actually reachable before publishing platforms.
        # Without a MAC we cannot build a stable unique_id, so abort and let HA retry.
        if not coordinator.device or not coordinator.device.mac:
            raise ConfigEntryNotReady("Device is not ready yet (no MAC available after first refresh)")
    except Exception:
        # async_config_entry_first_refresh() starts cloud/MQTT worker threads and arms
        # update timers; HA does NOT call async_unload_entry when setup raises, so release
        # them here, otherwise every ConfigEntryNotReady retry leaks a fresh thread set.
        coordinator.cleanup()
        raise
    _LOGGER.debug("Device refresh took %.2f seconds", time_module.time() - t2)

    # Remove stale devices from device registry: each config entry supports
    # exactly one device, so drop any identifier that no longer matches.
    current_mac = coordinator.device.mac
    device_registry = dr.async_get(hass)
    for device_entry in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if (DOMAIN, current_mac) not in device_entry.identifiers:
            _LOGGER.info(
                "Removing stale device %s (identifiers: %s)",
                device_entry.name,
                device_entry.identifiers,
            )
            device_registry.async_remove_device(device_entry.id)

    # Step 4: Set up all platforms for this device/entry
    t3 = time_module.time()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Platform setup took %.2f seconds", time_module.time() - t3)

    total_time = time_module.time() - setup_start
    _LOGGER.info("Dreame Vacuum integration setup completed in %.2f seconds", total_time)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DreameVacuumConfigEntry) -> bool:
    """Unload Dreame Vacuum config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        entry.runtime_data.coordinator.cleanup()

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entry to new version.

    This function is called when the config entry version is older than
    CONFIG_ENTRY_VERSION. It should update the config entry data to the
    current version format.

    Args:
        hass: Home Assistant instance.
        config_entry: The config entry to migrate.

    Returns:
        True if migration was successful, False otherwise.
    """
    _LOGGER.debug(
        "Migrating config entry from version %s to %s",
        config_entry.version,
        CONFIG_ENTRY_VERSION,
    )

    if config_entry.version == CONFIG_ENTRY_VERSION:
        _LOGGER.debug("Config entry already at version %s, no migration needed", CONFIG_ENTRY_VERSION)
        return True

    if config_entry.version < CONFIG_ENTRY_VERSION:
        hass.config_entries.async_update_entry(config_entry, version=CONFIG_ENTRY_VERSION)

    _LOGGER.info("Migration to version %s successful", CONFIG_ENTRY_VERSION)
    return True
