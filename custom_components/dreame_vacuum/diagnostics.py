"""Diagnostics support for Dreame Vacuum."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_AUTH_KEY, DreameVacuumConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
    CONF_AUTH_KEY,
    "mac",
    "did",
    "uid",
    "auth_key",
    "access_token",
    "host",
    "serial_number",
    "ssecurity",
    "service_token",
    "client_id",
    "_client_id",
    "uuid",
    "key",
    "_key",
    "_secondary_key",
    "secondary_key",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: DreameVacuumConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    device = coordinator.device

    diagnostics_data = {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "device": {
            "name": device.name if device else None,
            "model": device.info.model if device and device.info else None,
            "firmware": device.info.version if device and device.info else None,
            "connected": device.device_connected if device else False,
            "cloud_connected": device.cloud_connected if device else False,
        },
    }

    if device and device.status:
        diagnostics_data["status"] = {
            "battery_level": device.status.battery_level,
            "state": device.status.state.name if device.status.state else None,
            "task_status": device.status.task_status.name if device.status.task_status else None,
            "water_tank": device.status.water_tank.name if device.status.water_tank else None,
            "error": device.status.error.name if device.status.error else None,
        }

    return diagnostics_data
