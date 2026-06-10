"""Logbook support for Dreame Vacuum."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook.const import (
    LOGBOOK_ENTRY_ICON,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.core import Event, HomeAssistant, callback

from .const import (
    DOMAIN,
    EVENT_CONSUMABLE,
    EVENT_DRAINAGE_STATUS,
    EVENT_ERROR,
    EVENT_INFORMATION,
    EVENT_LOW_WATER,
    EVENT_TASK_STATUS,
    EVENT_WARNING,
)


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Describe logbook events."""

    @callback
    def async_describe_task_status(event: Event) -> dict[str, str]:
        """Describe task status event."""
        return {
            LOGBOOK_ENTRY_NAME: "Dreame Vacuum",
            LOGBOOK_ENTRY_MESSAGE: f"task status changed: {event.data.get('status', 'unknown')}",
            LOGBOOK_ENTRY_ICON: "mdi:robot-vacuum",
        }

    @callback
    def async_describe_consumable(event: Event) -> dict[str, str]:
        """Describe consumable event."""
        consumable = event.data.get(EVENT_CONSUMABLE, "unknown")
        life_left = event.data.get("life_left", "unknown")
        return {
            LOGBOOK_ENTRY_NAME: "Dreame Vacuum",
            LOGBOOK_ENTRY_MESSAGE: f"consumable alert: {consumable} ({life_left}% remaining)",
            LOGBOOK_ENTRY_ICON: "mdi:alert-circle",
        }

    @callback
    def async_describe_warning(event: Event) -> dict[str, str]:
        """Describe warning event."""
        warning = event.data.get(EVENT_WARNING, "unknown")
        return {
            LOGBOOK_ENTRY_NAME: "Dreame Vacuum",
            LOGBOOK_ENTRY_MESSAGE: f"warning: {warning}",
            LOGBOOK_ENTRY_ICON: "mdi:alert",
        }

    @callback
    def async_describe_error(event: Event) -> dict[str, str]:
        """Describe error event."""
        error = event.data.get(EVENT_ERROR, "unknown")
        code = event.data.get("code", "")
        return {
            LOGBOOK_ENTRY_NAME: "Dreame Vacuum",
            LOGBOOK_ENTRY_MESSAGE: f"error: {error} (code: {code})",
            LOGBOOK_ENTRY_ICON: "mdi:alert-octagon",
        }

    @callback
    def async_describe_low_water(event: Event) -> dict[str, str]:
        """Describe low water event."""
        return {
            LOGBOOK_ENTRY_NAME: "Dreame Vacuum",
            LOGBOOK_ENTRY_MESSAGE: f"low water warning: {event.data.get(EVENT_LOW_WATER, 'unknown')}",
            LOGBOOK_ENTRY_ICON: "mdi:water-alert",
        }

    @callback
    def async_describe_information(event: Event) -> dict[str, str]:
        """Describe information event."""
        return {
            LOGBOOK_ENTRY_NAME: "Dreame Vacuum",
            LOGBOOK_ENTRY_MESSAGE: f"information: {event.data.get(EVENT_INFORMATION, 'unknown')}",
            LOGBOOK_ENTRY_ICON: "mdi:information",
        }

    @callback
    def async_describe_drainage_status(event: Event) -> dict[str, str]:
        """Describe drainage status event."""
        success = event.data.get(EVENT_DRAINAGE_STATUS, False)
        status = "completed" if success else "failed"
        return {
            LOGBOOK_ENTRY_NAME: "Dreame Vacuum",
            LOGBOOK_ENTRY_MESSAGE: f"drainage {status}",
            LOGBOOK_ENTRY_ICON: "mdi:water-pump",
        }

    async_describe_event(DOMAIN, f"{DOMAIN}_{EVENT_TASK_STATUS}", async_describe_task_status)
    async_describe_event(DOMAIN, f"{DOMAIN}_{EVENT_CONSUMABLE}", async_describe_consumable)
    async_describe_event(DOMAIN, f"{DOMAIN}_{EVENT_WARNING}", async_describe_warning)
    async_describe_event(DOMAIN, f"{DOMAIN}_{EVENT_ERROR}", async_describe_error)
    async_describe_event(DOMAIN, f"{DOMAIN}_{EVENT_LOW_WATER}", async_describe_low_water)
    async_describe_event(DOMAIN, f"{DOMAIN}_{EVENT_INFORMATION}", async_describe_information)
    async_describe_event(DOMAIN, f"{DOMAIN}_{EVENT_DRAINAGE_STATUS}", async_describe_drainage_status)
