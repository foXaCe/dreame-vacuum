"""Support for Dreame Vacuum times.

This module provides time entities for Dreame vacuum robots,
such as DnD (Do Not Disturb) start and end times.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import time
from typing import TYPE_CHECKING, Any

from homeassistant.components.time import (
    ENTITY_ID_FORMAT,
    TimeEntity,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, DreameVacuumConfigEntry

PARALLEL_UPDATES = 1

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import DreameVacuumDataUpdateCoordinator
from .entity import DreameVacuumEntity, DreameVacuumTimeEntityDescription

TIMES: tuple[DreameVacuumTimeEntityDescription, ...] = (
    DreameVacuumTimeEntityDescription(
        key="dnd_start",
        name="DnD start",
        icon="mdi:clock-start",
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: device.capability.dnd,
    ),
    DreameVacuumTimeEntityDescription(
        key="dnd_end",
        name="DnD end",
        icon="mdi:clock-end",
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: device.capability.dnd,
    ),
    DreameVacuumTimeEntityDescription(
        key="off_peak_charging_start",
        name="Off-peak charging start",
        icon="mdi:battery-lock-open",
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: device.capability.off_peak_charging,
    ),
    DreameVacuumTimeEntityDescription(
        key="off_peak_charging_end",
        name="Off-peak charging end",
        icon="mdi:battery-lock",
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: device.capability.off_peak_charging,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DreameVacuumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Vacuum time based on a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DreameVacuumTimeEntity(coordinator, description)
        for description in TIMES
        if description.exists_fn(description, coordinator.device)
    )


class DreameVacuumTimeEntity(DreameVacuumEntity, TimeEntity):
    """Defines a Dreame Vacuum time."""

    __slots__ = ("_computed_set_fn",)

    entity_description: DreameVacuumTimeEntityDescription

    def __init__(
        self,
        coordinator: DreameVacuumDataUpdateCoordinator,
        description: DreameVacuumTimeEntityDescription,
    ) -> None:
        """Initialize Dreame Vacuum time."""
        self._computed_set_fn: Callable[[Any, int], None] | None = description.set_fn

        super().__init__(coordinator, description)

        self._computed_set_fn = self._resolve_set_fn(coordinator, description)

        self._generate_entity_id(ENTITY_ID_FORMAT)
        value = super().native_value
        if value:
            try:
                values = value.split(":")
                self._attr_native_value = time(int(values[0]), int(values[1]), 0)
            except (ValueError, IndexError):
                self._attr_native_value = None
        else:
            self._attr_native_value = None

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.device is None:
            super()._handle_coordinator_update()
            return
        value = super().native_value
        if value:
            try:
                values = value.split(":")
                self._attr_native_value = time(int(values[0]), int(values[1]), 0)
            except (ValueError, IndexError):
                self._attr_native_value = None
        else:
            self._attr_native_value = None
        super()._handle_coordinator_update()

    async def async_set_value(self, value: time) -> None:
        """Set the Dreame Vacuum time value."""
        if not self.available:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="entity_unavailable",
            )

        if value is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
            )

        value_str = value.strftime("%H:%M")
        if self._computed_set_fn is not None:
            await self._try_command("Unable to call: %s", self._computed_set_fn, self.device, value_str)
        elif self.entity_description.property_key is not None:
            await self._try_command(
                "Unable to call: %s",
                self.device.set_property,
                self.entity_description.property_key,
                value_str,
            )
        else:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_implemented",
            )

    @property
    def native_value(self):
        """Return the current Dreame Vacuum time value."""
        return self._attr_native_value
