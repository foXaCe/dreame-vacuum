"""System health for Dreame Vacuum.

Surfaces a small connectivity summary on Home Assistant's System Health page:
how many configured Dreame vacuums are currently reachable locally and via the
Dreame cloud (MQTT push).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, DreameVacuumConfigEntry


@callback
def async_register(hass: HomeAssistant, register: system_health.SystemHealthRegistration) -> None:
    """Register system health callbacks."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return information for the system health card."""
    entries: list[DreameVacuumConfigEntry] = hass.config_entries.async_entries(DOMAIN)

    configured = 0
    connected = 0
    cloud_connected = 0
    for entry in entries:
        runtime_data = getattr(entry, "runtime_data", None)
        if runtime_data is None:
            continue
        device = runtime_data.coordinator.device
        if device is None:
            continue
        configured += 1
        if device.device_connected:
            connected += 1
        if device.cloud_connected:
            cloud_connected += 1

    return {
        "configured_devices": configured,
        "connected_devices": connected,
        "cloud_connected_devices": cloud_connected,
    }
