"""Support for Dreame Vacuum Binary Sensors.

This module provides binary sensor entities for Dreame vacuum robots,
such as charging state and error indicators.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    ENTITY_ID_FORMAT,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .const import DreameVacuumConfigEntry
from .entity import DreameVacuumBinarySensorEntityDescription, DreameVacuumEntity

PARALLEL_UPDATES = 1

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import DreameVacuumDataUpdateCoordinator


BINARY_SENSORS: tuple[DreameVacuumBinarySensorEntityDescription, ...] = (
    # Needed for the battery icon: the vacuum entity no longer exposes
    # the deprecated charging attribute.
    DreameVacuumBinarySensorEntityDescription(
        key="charging_state",
        name="Charging state",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        icon_fn=lambda value, device: (
            "mdi:power-plug-battery"
            if device.status.charging
            else "mdi:power-plug-off"
            if not device.status.docked
            else "mdi:power-plug"
        ),
        value_fn=lambda value, device: device.status.charging,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DreameVacuumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Vacuum Binary Sensor based on a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DreameVacuumBinarySensorEntity(coordinator, description)
        for description in BINARY_SENSORS
        if description.exists_fn(description, coordinator.device)
    )


class DreameVacuumBinarySensorEntity(DreameVacuumEntity, BinarySensorEntity):
    """Defines a Dreame Vacuum Binary Sensor entity."""

    __slots__ = ()

    entity_description: DreameVacuumBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: DreameVacuumDataUpdateCoordinator,
        description: DreameVacuumBinarySensorEntityDescription,
    ) -> None:
        """Initialize a Dreame Vacuum BinarySensor entity."""
        super().__init__(coordinator, description)
        self._generate_entity_id(ENTITY_ID_FORMAT)

    @property
    def is_on(self) -> bool | None:
        """Return value of binary sensor."""
        value = None
        if self.entity_description.property_key is not None:
            value = self.device.get_property(self.entity_description.property_key)
        if self.entity_description.value_fn is not None:
            return bool(self.entity_description.value_fn(value, self.device))
        return bool(value)
