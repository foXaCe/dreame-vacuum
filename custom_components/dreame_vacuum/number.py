"""Support for Dreame Vacuum numbers.

This module provides number entities for Dreame vacuum robots,
such as volume control and cleaning parameters.
"""

from __future__ import annotations

from collections.abc import Callable
import copy
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import (
    ENTITY_ID_FORMAT,
    NumberEntity,
    NumberMode,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity import EntityCategory, async_generate_entity_id

from .const import DOMAIN, UNIT_AREA, UNIT_HOURS, UNIT_MINUTES, UNIT_PERCENT, DreameVacuumConfigEntry

PARALLEL_UPDATES = 1

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import DreameVacuumDataUpdateCoordinator
from .dreame import DreameVacuumCleaningMode, DreameVacuumProperty
from .entity import DreameVacuumEntity, DreameVacuumNumberEntityDescription, default_exists_fn


def WETNESS_LEVEL_TO_ICON(wetness, max_level):
    if wetness:
        if wetness > max_level:
            return "mdi:water-plus"
        if wetness < 6:
            return "mdi:water-minus"
        return "mdi:water"
    return "mdi:water-off"


NUMBERS: tuple[DreameVacuumNumberEntityDescription, ...] = (
    DreameVacuumNumberEntityDescription(
        property_key=DreameVacuumProperty.VOLUME,
        icon_fn=lambda value, device: (
            "mdi:volume-off"
            if not value
            else "mdi:volume-low"
            if value <= 35
            else "mdi:volume-medium"
            if value <= 65
            else "mdi:volume-high"
        ),
        mode=NumberMode.SLIDER,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=UNIT_PERCENT,
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumNumberEntityDescription(
        property_key=DreameVacuumProperty.MOP_CLEANING_REMAINDER,
        icon="mdi:alarm-check",
        mode=NumberMode.BOX,
        native_unit_of_measurement=UNIT_MINUTES,
        native_min_value=0,
        native_max_value=180,
        native_step=15,
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: (
            not device.capability.self_wash_base and default_exists_fn(description, device)
        ),
    ),
    DreameVacuumNumberEntityDescription(
        key="self_clean_area",
        icon_fn=lambda value, device: (
            "mdi:texture-box"
            if device.status.self_clean_value or (device.status.current_map and not device.status.has_saved_map)
            else "mdi:checkbox-blank-off-outline"
        ),
        mode=NumberMode.SLIDER,
        native_unit_of_measurement=UNIT_AREA,
        exists_fn=lambda description, device: (
            device.capability.self_wash_base and not device.capability.mop_clean_frequency
        ),
        min_value_fn=lambda device: device.status.self_clean_area_min,
        max_value_fn=lambda device: device.status.self_clean_area_max,
        native_step=1,
        entity_category=None,
        value_fn=lambda value, device: (
            (
                device.status.self_clean_area_min
                if device.status.self_clean_value < device.status.self_clean_area_min
                else (
                    device.status.self_clean_area_max
                    if device.status.self_clean_value > device.status.self_clean_area_max
                    else device.status.self_clean_value
                )
            )
            if device.status.self_clean_value and device.status.self_clean_value > 0
            else device.status.self_clean_area_default
        ),
    ),
    DreameVacuumNumberEntityDescription(
        key="self_clean_time",
        icon="mdi:table-clock",
        mode=NumberMode.SLIDER,
        native_unit_of_measurement=UNIT_MINUTES,
        exists_fn=lambda description, device: (
            device.capability.self_clean_frequency and not device.capability.mop_clean_frequency
        ),
        min_value_fn=lambda device: device.status.self_clean_time_min,
        max_value_fn=lambda device: device.status.self_clean_time_max,
        native_step=1,
        entity_category=None,
        value_fn=lambda value, device: (
            (
                device.status.self_clean_time_min
                if device.status.self_clean_value < device.status.self_clean_time_min
                else (
                    device.status.self_clean_time_max
                    if device.status.self_clean_value > device.status.self_clean_time_max
                    else device.status.self_clean_value
                )
            )
            if device.status.self_clean_value and device.status.self_clean_value > 0
            else device.status.self_clean_time_default
        ),
    ),
    DreameVacuumNumberEntityDescription(
        property_key=DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS,
        icon="mdi:brightness-percent",
        mode=NumberMode.SLIDER,
        native_min_value=40,
        native_max_value=100,
        native_step=1,
        exists_fn=lambda description, device: (
            device.capability.camera_streaming and device.capability.fill_light
        ),  # and default_exists_fn(description, device),
        native_unit_of_measurement=UNIT_PERCENT,
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumNumberEntityDescription(
        property_key=DreameVacuumProperty.WETNESS_LEVEL,
        icon_fn=lambda value, device: (
            "mdi:water-off"
            if (
                not (device.status.water_tank_or_mop_installed)
                or device.status.cleaning_mode is DreameVacuumCleaningMode.SWEEPING
            )
            else WETNESS_LEVEL_TO_ICON(device.status.wetness_level, 14 if device.capability.mop_clean_frequency else 26)
        ),
        mode=NumberMode.SLIDER,
        native_min_value=1,
        max_value_fn=lambda device: 15 if device.capability.mop_clean_frequency else 32,
        native_step=1,
        exists_fn=lambda description, device: (
            device.capability.wetness_level and default_exists_fn(description, device)
        ),
    ),
    DreameVacuumNumberEntityDescription(
        property_key=DreameVacuumProperty.DRYING_TIME,
        icon="mdi:sun-clock",
        native_unit_of_measurement=UNIT_HOURS,
        mode=NumberMode.SLIDER,
        native_min_value=2,
        native_max_value=12,
        native_step=1,
        entity_category=None,
        exists_fn=lambda description, device: (
            device.capability.mop_clean_frequency and default_exists_fn(description, device)
        ),
    ),
)


SEGMENT_NUMBERS: tuple[DreameVacuumNumberEntityDescription, ...] = (
    DreameVacuumNumberEntityDescription(
        key=DreameVacuumProperty.WETNESS_LEVEL.name.lower(),
        segment_icon_fn=lambda value, device, segment: (
            WETNESS_LEVEL_TO_ICON(segment.wetness_level, 14 if device.capability.mop_clean_frequency else 26)
            if segment
            else "mdi:water-off"
        ),
        segment_available_fn=lambda device, segment: bool(
            device.status.current_segments
            and segment.wetness_level is not None
            and device.status.customized_cleaning
            and not (device.status.zone_cleaning or device.status.spot_cleaning)
            and not device.status.fast_mapping
            and not device.status.scheduled_clean
            and not device.status.cruising
            and segment.cleaning_mode is not DreameVacuumCleaningMode.SWEEPING.value
            and not device.status.cleangenius_cleaning
        ),
        mode=NumberMode.SLIDER,
        native_min_value=1,
        native_max_value=32,
        native_step=1,
        value_fn=lambda device, segment: segment.wetness_level,
        exists_fn=lambda description, device: device.capability.wetness_level,
        segment_list_fn=lambda device: device.status.current_segments,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DreameVacuumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Vacuum number based on a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DreameVacuumNumberEntity(coordinator, description)
        for description in NUMBERS
        if description.exists_fn(description, coordinator.device)
    )

    update_segment_numbers = partial(async_update_segment_numbers, coordinator, {}, async_add_entities)
    coordinator.async_add_listener(update_segment_numbers)
    update_segment_numbers()


@callback
def async_update_segment_numbers(
    coordinator: DreameVacuumDataUpdateCoordinator,
    current: dict[int, list[DreameVacuumSegmentNumberEntity]],
    async_add_entities,
) -> None:
    new_ids: list[int] = []
    if coordinator.device and coordinator.device.status.map_list:
        for k, v in (coordinator.device.status.map_data_list or {}).items():
            for j, s in (v.segments or {}).items():
                if j not in new_ids:
                    new_ids.append(j)

    new_id_set = set(new_ids)
    current_ids = set(current)

    for segment_id in current_ids - new_id_set:
        async_remove_segment_numbers(segment_id, coordinator, current)

    new_entities: list[DreameVacuumSegmentNumberEntity] = []
    for segment_id in new_id_set - current_ids:
        current[segment_id] = [
            DreameVacuumSegmentNumberEntity(coordinator, description, segment_id)
            for description in SEGMENT_NUMBERS
            if description.exists_fn(description, coordinator.device)
        ]
        new_entities = new_entities + current[segment_id]

    if new_entities:
        async_add_entities(new_entities)


def async_remove_segment_numbers(
    segment_id: int,
    coordinator: DreameVacuumDataUpdateCoordinator,
    current: dict[int, list[DreameVacuumSegmentNumberEntity]],
) -> None:
    registry = entity_registry.async_get(coordinator.hass)
    entities = current[segment_id]
    for entity in entities:
        if entity.entity_id in registry.entities:
            registry.async_remove(entity.entity_id)
    del current[segment_id]


class DreameVacuumNumberEntity(DreameVacuumEntity, NumberEntity):
    """Defines a Dreame Vacuum number."""

    __slots__ = ("_computed_set_fn",)

    entity_description: DreameVacuumNumberEntityDescription

    def __init__(
        self,
        coordinator: DreameVacuumDataUpdateCoordinator,
        description: DreameVacuumNumberEntityDescription,
    ) -> None:
        """Initialize Dreame Vacuum number."""
        self._computed_set_fn: Callable[[Any, int], None] | None = description.set_fn

        super().__init__(coordinator, description)

        self._computed_set_fn = self._resolve_set_fn(coordinator, description)

        # Set initial min/max values using _attr_ attributes
        if description.min_value_fn:
            self._attr_native_min_value = description.min_value_fn(coordinator.device)
        if description.max_value_fn:
            self._attr_native_max_value = description.max_value_fn(coordinator.device)

        self._generate_entity_id(ENTITY_ID_FORMAT)
        if description.mode is not None:
            self._attr_mode = description.mode
        self._attr_native_value = super().native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.device is not None:
            self._attr_native_value = super().native_value
            if self.entity_description.min_value_fn:
                self._attr_native_min_value = self.entity_description.min_value_fn(self.device)
            if self.entity_description.max_value_fn:
                self._attr_native_max_value = self.entity_description.max_value_fn(self.device)
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Set the Dreame Vacuum number value."""
        if not self.available:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="entity_unavailable",
            )

        value = int(value)
        if self.entity_description.format_fn is not None:
            value = self.entity_description.format_fn(value, self.device)

        if value is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
            )

        if self._computed_set_fn is not None:
            await self._try_command("Unable to call: %s", self._computed_set_fn, self.device, value)
        elif self.entity_description.property_key is not None:
            await self._try_command(
                "Unable to call: %s",
                self.device.set_property,
                self.entity_description.property_key,
                value,
            )

    @property
    def native_value(self) -> float | None:
        """Return the current Dreame Vacuum number value."""
        return self._attr_native_value


class DreameVacuumSegmentNumberEntity(DreameVacuumEntity, NumberEntity):
    """Defines a Dreame Vacuum Segment number."""

    __slots__ = ("_segment_set_fn", "segment", "segment_id", "segments")

    entity_description: DreameVacuumNumberEntityDescription

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Per-room controls are advanced — only useful with "Customized cleaning".

        Ship them disabled by default so they don't flood the UI with unavailable
        rows; users who want per-room control enable them once.
        """
        return False

    def __init__(
        self,
        coordinator: DreameVacuumDataUpdateCoordinator,
        description: DreameVacuumNumberEntityDescription,
        segment_id: int,
    ) -> None:
        """Initialize Dreame Vacuum Segment Number."""
        self.segment_id = segment_id
        self.segment = None
        self.segments = None
        self._segment_set_fn: Callable[..., None] | None = description.set_fn
        if coordinator.device and description.segment_list_fn is not None:
            self.segments = copy.deepcopy(description.segment_list_fn(coordinator.device))
            if segment_id in self.segments:
                self.segment = self.segments[segment_id]

        super().__init__(coordinator, description)

        self._segment_set_fn = self._resolve_segment_set_fn(coordinator, description)

        key_lower = self._computed_key.lower() if self._computed_key else "unknown"
        self._attr_unique_id = f"{self.device.mac}_room_{segment_id}_{key_lower}"
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT,
            f"{self.device.name} room_{segment_id}_{key_lower}",
            hass=self.coordinator.hass,
        )
        self._attr_native_value = None
        if self.segment and description.value_fn is not None:
            self._attr_native_value = description.value_fn(coordinator.device, self.segment)

        # Set initial min/max values using _attr_ attributes
        if description.min_value_fn:
            self._attr_native_min_value = description.min_value_fn(coordinator.device)
        if description.max_value_fn:
            self._attr_native_max_value = description.max_value_fn(coordinator.device)

    def _set_id(self) -> None:
        """Set name, unique id and icon of the entity"""
        key = self._computed_key or self.entity_description.key
        if self.entity_description.name == "":
            self._attr_translation_key = "room_name"
            self._attr_translation_placeholders = {"room_id": str(self.segment_id)}
        elif self.segment:
            self._attr_translation_key = f"{key}_room"
            self._attr_translation_placeholders = {
                "room": self.segment.get_translated_name(self.coordinator.hass.config.language)
            }
        else:
            self._attr_translation_key = f"{key}_room"
            self._attr_translation_placeholders = {"room": "?"}

        if self.entity_description.segment_icon_fn is not None:
            self._attr_icon = self.entity_description.segment_icon_fn(
                self._attr_native_value, self.device, self.segment
            )
        elif self.segment:
            self._attr_icon = self.segment.icon
        else:
            self._attr_icon = "mdi:home-off-outline"

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.device is None:
            self.async_write_ha_state()
            return
        device_segments = self._device_segments
        if self.segments != device_segments:
            self.segments = copy.deepcopy(device_segments)
            if self.segments and self.segment_id in self.segments:
                if self.segment != self.segments[self.segment_id]:
                    self.segment = self.segments[self.segment_id]
                    if self.entity_description.min_value_fn:
                        self._attr_native_min_value = self.entity_description.min_value_fn(self.device)
                    if self.entity_description.max_value_fn:
                        self._attr_native_max_value = self.entity_description.max_value_fn(self.device)
                    if self.entity_description.value_fn is not None:
                        self._attr_native_value = self.entity_description.value_fn(self.device, self.segment)
                    self._set_id()
            elif self.segment:
                self.segment = None
                self._set_id()

        self.async_write_ha_state()

    @property
    def _device_segments(self):
        return self.entity_description.segment_list_fn(self.device)

    async def async_set_native_value(self, value: float) -> None:
        """Set the Dreame Vacuum number value."""
        if not self.available:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="entity_unavailable",
            )

        await self._try_command(
            "Unable to call %s",
            self._segment_set_fn,
            self.device,
            self.segment_id,
            int(value),
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.device.device_connected or (self._attr_available and self.segment is None):
            return False
        if self.entity_description.segment_available_fn is not None:
            return self.entity_description.segment_available_fn(self.device, self.segment)
        return self._attr_available

    @property
    def native_value(self) -> float | None:
        """Return the current Dreame Vacuum number value."""
        if self.segment:
            return self._attr_native_value
        return None
