"""The Dreame Vacuum component."""

from __future__ import annotations

import logging
import time as time_module

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dreame Vacuum from a config entry."""
    _LOGGER.info("Starting Dreame Vacuum integration setup for %s", entry.data.get("name", "unknown"))
    setup_start = time_module.time()

    # Step 1: Initialize coordinator
    t0 = time_module.time()
    coordinator = DreameVacuumDataUpdateCoordinator(hass, entry=entry)
    _LOGGER.debug("Coordinator initialization took %.2f seconds", time_module.time() - t0)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Step 2: Initial device refresh (must be done BEFORE platform setup)
    # This ensures the device is initialized before entities are created
    t2 = time_module.time()
    await coordinator.async_config_entry_first_refresh()
    _LOGGER.debug("Device refresh took %.2f seconds", time_module.time() - t2)

    # Register frontend
    # frontend_js = f"/{DOMAIN}/frontend.js"
    # if DATA_EXTRA_MODULE_URL not in hass.data:
    #    hass.data[DATA_EXTRA_MODULE_URL] = set()
    # if frontend_js not in (
    #    hass.data[DATA_EXTRA_MODULE_URL].urls
    #    if hasattr(hass.data[DATA_EXTRA_MODULE_URL], "urls")
    #    else hass.data[DATA_EXTRA_MODULE_URL]
    # ):
    #    hass.data[DATA_EXTRA_MODULE_URL].add(frontend_js)
    #    hass.http.register_static_path(frontend_js, str(Path(Path(__file__).parent / "frontend.js")), True)

    # Step 3: Set up all platforms for this device/entry
    t3 = time_module.time()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Platform setup took %.2f seconds", time_module.time() - t3)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    total_time = time_module.time() - setup_start
    _LOGGER.info("Dreame Vacuum integration setup completed in %.2f seconds", total_time)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Dreame Vacuum config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: DreameVacuumDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
        coordinator._device.listen(None)
        coordinator._device.disconnect()
        del coordinator._device
        coordinator._device = None
        del hass.data[DOMAIN][entry.entry_id]

    return unload_ok


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)
