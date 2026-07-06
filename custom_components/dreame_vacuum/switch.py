"""Support for Dreame Vacuum switches.

This module provides switch entities for Dreame vacuum robots,
controlling features like carpet boost, child lock, and DnD mode.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import (
    ENTITY_ID_FORMAT,
    SwitchEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, DreameVacuumConfigEntry

PARALLEL_UPDATES = 1

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import DreameVacuumDataUpdateCoordinator
from .dreame import (
    DreameVacuumAIProperty,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumProperty,
    DreameVacuumStrAIProperty,
)
from .entity import DreameVacuumEntity, DreameVacuumSwitchEntityDescription, default_exists_fn

SWITCHES: tuple[DreameVacuumSwitchEntityDescription, ...] = (
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.RESUME_CLEANING,
        value_fn=lambda value, device: bool(value),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.CARPET_BOOST,
        icon_fn=lambda value, device: "mdi:upload-off" if value == 0 else "mdi:upload",
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.OBSTACLE_AVOIDANCE,
        icon_fn=lambda value, device: "mdi:video-3d-off" if value == 0 else "mdi:video-3d",
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.CUSTOMIZED_CLEANING,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.CHILD_LOCK,
        icon_fn=lambda value, device: "mdi:lock-off" if value == 0 else "mdi:lock",
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.TIGHT_MOPPING,
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: bool(
            default_exists_fn(description, device) and device.status.mopping_type is None
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        key="dnd",
        name="DnD",
        icon_fn=lambda value, device: "mdi:minus-circle-off-outline" if not value else "mdi:minus-circle-outline",
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.DND_DISABLE_RESUME_CLEANING,
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: bool(
            device.capability.dnd_functions and default_exists_fn(description, device)
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.DND_DISABLE_AUTO_EMPTY,
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: bool(
            device.capability.dnd_functions and default_exists_fn(description, device)
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.DND_REDUCE_VOLUME,
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: bool(
            device.capability.dnd_functions and default_exists_fn(description, device)
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.MULTI_FLOOR_MAP,
        icon_fn=lambda value, device: "mdi:layers-off" if value == 0 else "mdi:layers",
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: bool(
            default_exists_fn(description, device) and device.capability.lidar_navigation
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.AUTO_DUST_COLLECTING,
        icon_fn=lambda value, device: "mdi:autorenew-off" if value == 0 else "mdi:autorenew",
        entity_category=None,
        exists_fn=lambda description, device: bool(
            default_exists_fn(description, device) and not device.capability.auto_empty_mode
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.CARPET_RECOGNITION,
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: bool(
            default_exists_fn(description, device)
            and not device.capability.auto_carpet_cleaning
            and not device.capability.mop_pad_lifting_plus
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.SELF_CLEAN,
        icon_fn=lambda value, device: "mdi:water-off-outline" if value == 0 else "mdi:water-sync",
        entity_category=None,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.WATER_ELECTROLYSIS,
        icon_fn=lambda value, device: "mdi:lightning-bolt-outline" if value == 0 else "mdi:lightning-bolt",
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: bool(
            default_exists_fn(description, device)
            and device.capability.self_wash_base
            and not device.capability.mop_clean_frequency
            and not device.capability.small_self_clean_area
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.AUTO_WATER_REFILLING,
        icon_fn=lambda value, device: "mdi:water-boiler-off" if value == 0 else "mdi:water-boiler-auto",
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: device.capability.water_check and default_exists_fn(description, device),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.INTELLIGENT_RECOGNITION,
        icon_fn=lambda value, device: "mdi:wifi-remove" if value == 0 else "mdi:wifi-marker",
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: device.capability.wifi_map and default_exists_fn(description, device),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.AUTO_DRYING,
        icon_fn=lambda value, device: "mdi:weather-sunny-off" if not value else "mdi:weather-sunny",
        entity_category=None,
        exists_fn=lambda description, device: device.capability.self_wash_base,
    ),
    DreameVacuumSwitchEntityDescription(
        key="carpet_avoidance",
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: (
            not (
                device.capability.mop_pad_unmounting
                or device.capability.auto_carpet_cleaning
                or device.capability.mop_pad_lifting_plus
            )
            and device.capability.carpet_recognition
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.AUTO_ADD_DETERGENT,
        entity_category=EntityCategory.CONFIG,
        format_fn=lambda value, device: int(value),
        exists_fn=lambda description, device: bool(
            default_exists_fn(description, device)
            and (device.capability.detergent or device.capability.smart_mop_washing)
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.MOP_WASHING_WITH_DETERGENT,
        entity_category=EntityCategory.CONFIG,
        format_fn=lambda value, device: int(value),
        exists_fn=lambda description, device: bool(
            device.capability.mop_washing_with_detergent and default_exists_fn(description, device)
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.MAP_SAVING,
        entity_category=EntityCategory.CONFIG,
        format_fn=lambda value, device: int(value),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.AUTO_MOUNT_MOP,
        entity_category=EntityCategory.CONFIG,
        format_fn=lambda value, device: int(value),
        exists_fn=lambda description, device: bool(
            device.capability.mop_pad_unmounting and default_exists_fn(description, device)
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.VOICE_ASSISTANT,
        icon_fn=lambda value, device: "mdi:microphone-message-off" if not value else "mdi:microphone-message",
        entity_category=EntityCategory.CONFIG,
        format_fn=lambda value, device: int(value),
    ),
    DreameVacuumSwitchEntityDescription(
        key="cleaning_sequence",
        value_fn=lambda value, device: device.status.custom_order,
        exists_fn=lambda description, device: device.capability.customized_cleaning and device.capability.map,
        set_fn=lambda device, value: device.set_cleaning_sequence(
            []
            if not value
            else (
                device.status.previous_cleaning_sequence
                if device.status.previous_cleaning_sequence
                else sorted(device.status.current_segments.keys())
            )
        ),
        format_fn=lambda value, device: int(value),
        entity_category=None,
    ),
    DreameVacuumSwitchEntityDescription(
        key="self_clean_by_zone",
        icon_fn=lambda value, device: "mdi:texture-box" if not value else "mdi:home-switch",
        value_fn=lambda value, device: bool(not device.status.self_clean_value),
        exists_fn=lambda description, device: (
            device.capability.self_wash_base
            and not device.capability.self_clean_frequency
            and device.status.self_clean_value is not None
            and not device.capability.mop_clean_frequency
        ),
        set_fn=lambda device, value: device.set_self_clean_value(value),
        format_fn=lambda value, device: (
            0 if value else device.status.previous_self_clean_area if device.status.previous_self_clean_area else 20
        ),
        entity_category=None,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAIProperty.AI_OBSTACLE_DETECTION,
        icon_fn=lambda value, device: "mdi:robot-off" if not value else "mdi:robot",
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAIProperty.AI_OBSTACLE_IMAGE_UPLOAD,
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAIProperty.AI_OBSTACLE_PICTURE,
        icon_fn=lambda value, device: "mdi:camera-off" if not value else "mdi:camera",
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAIProperty.AI_PET_DETECTION,
        icon_fn=lambda value, device: "mdi:dog-side-off" if not value else "mdi:dog-side",
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumStrAIProperty.AI_HUMAN_DETECTION,
        icon_fn=lambda value, device: "mdi:account-off" if not value else "mdi:account",
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAIProperty.AI_FURNITURE_DETECTION,
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAIProperty.AI_FLUID_DETECTION,
        icon_fn=lambda value, device: "mdi:water-off-outline" if not value else "mdi:water-outline",
        exists_fn=lambda description, device: device.capability.fluid_detection,
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAIProperty.FUZZY_OBSTACLE_DETECTION,
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAIProperty.AI_PET_AVOIDANCE,
        exists_fn=lambda description, device: device.capability.pet_detective,
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAIProperty.PET_PICTURE,
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAIProperty.PET_FOCUSED_DETECTION,
        exists_fn=lambda description, device: device.capability.pet_furniture,
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAIProperty.LARGE_PARTICLES_BOOST,
        exists_fn=lambda description, device: bool(device.capability.large_particles_boost),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.FILL_LIGHT,
        icon_fn=lambda value, device: "mdi:lightbulb-off" if not value else "mdi:lightbulb-on",
        exists_fn=lambda description, device: bool(
            device.capability.fill_light and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.COLLISION_AVOIDANCE,
        icon_fn=lambda value, device: "mdi:sign-direction-remove" if not value else "mdi:sign-direction",
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.STAIN_AVOIDANCE,
        format_fn=lambda value, device: 2 if value else 1,
        exists_fn=lambda description, device: bool(
            device.capability.fluid_detection and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.FLOOR_DIRECTION_CLEANING,
        exists_fn=lambda description, device: bool(
            device.capability.floor_direction_cleaning and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.PET_FOCUSED_CLEANING,
        exists_fn=lambda description, device: bool(
            device.capability.pet_detective and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.INTENSIVE_CARPET_CLEANING,
        exists_fn=lambda description, device: bool(
            device.capability.intensive_carpet_cleaning and default_exists_fn(description, device)
        ),
        available_fn=lambda device: (
            not device.status.started and device.status.carpet_recognition and not device.status.carpet_avoidance
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.SIDE_REACH,
        exists_fn=lambda description, device: bool(
            device.capability.side_reach and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.MOP_EXTEND,
        exists_fn=lambda description, device: bool(
            device.capability.mop_extend and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.GAP_CLEANING_EXTENSION,
        exists_fn=lambda description, device: bool(
            device.capability.mop_pad_swing_plus and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.MOPPING_UNDER_FURNITURES,
        exists_fn=lambda description, device: bool(
            device.capability.mop_pad_swing_plus and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.OFF_PEAK_CHARGING,
        entity_category=EntityCategory.CONFIG,
        exists_fn=lambda description, device: device.capability.off_peak_charging,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.AUTO_CHARGING,
        exists_fn=lambda description, device: bool(
            device.capability.auto_charging and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.HUMAN_FOLLOW,
        icon_fn=lambda value, device: "mdi:account-off" if not value else "mdi:account-arrow-left",
        exists_fn=lambda description, device: bool(
            device.capability.mop_pad_swing
            and device.capability.camera_streaming
            and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.MAX_SUCTION_POWER,
        exists_fn=lambda description, device: bool(
            device.capability.max_suction_power and default_exists_fn(description, device)
        ),
        entity_category=None,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.SMART_DRYING,
        exists_fn=lambda description, device: bool(
            device.capability.smart_drying and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.HOT_WASHING,
        exists_fn=lambda description, device: bool(
            device.capability.hot_washing
            and not device.capability.smart_mop_washing
            and default_exists_fn(description, device)
        ),
        entity_category=None,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.UV_STERILIZATION,
        exists_fn=lambda description, device: bool(
            device.capability.uv_sterilization and default_exists_fn(description, device)
        ),
        entity_category=None,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE,
        exists_fn=lambda description, device: bool(
            device.capability.ultra_clean_mode
            and not device.capability.smart_mop_washing
            and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumAutoSwitchProperty.STREAMING_VOICE_PROMPT,
        icon_fn=lambda value, device: "mdi:account-tie-voice-off" if not value else "mdi:account-tie-voice",
        exists_fn=lambda description, device: bool(
            device.capability.camera_streaming and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.CLEAN_CARPETS_FIRST,
        exists_fn=lambda description, device: bool(
            device.capability.clean_carpets_first and default_exists_fn(description, device)
        ),
        available_fn=lambda device: (
            not device.status.started and device.status.carpet_recognition and not device.status.carpet_avoidance
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.SMART_MOP_WASHING,
        exists_fn=lambda description, device: bool(
            device.capability.smart_mop_washing and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.SILENT_DRYING,
        exists_fn=lambda description, device: bool(
            device.capability.silent_drying and default_exists_fn(description, device)
        ),
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.HAIR_COMPRESSION,
        exists_fn=lambda description, device: bool(
            device.capability.hair_compression and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.SIDE_BRUSH_CARPET_ROTATE,
        exists_fn=lambda description, device: bool(
            device.capability.side_brush_carpet_rotate and default_exists_fn(description, device)
        ),
        available_fn=lambda device: (
            not device.status.started and device.status.carpet_recognition and not device.status.carpet_avoidance
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        property_key=DreameVacuumProperty.AUTO_LDS_LIFTING,
        exists_fn=lambda description, device: bool(
            device.capability.auto_lds_lifting and default_exists_fn(description, device)
        ),
        entity_category=EntityCategory.CONFIG,
    ),
    DreameVacuumSwitchEntityDescription(
        key="camera_light_brightness_auto",
        icon_fn=lambda value, device: "mdi:brightness-percent" if not value else "mdi:brightness-auto",
        value_fn=lambda value, device: bool(device.status.camera_light_brightness == 101),
        exists_fn=lambda description, device: device.capability.camera_streaming and device.capability.fill_light,
        format_fn=lambda value, device: 101 if value else 40,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DreameVacuumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dreame Vacuum switch based on a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DreameVacuumSwitchEntity(coordinator, description)
        for description in SWITCHES
        if description.exists_fn(description, coordinator.device)
    )


class DreameVacuumSwitchEntity(DreameVacuumEntity, SwitchEntity):
    """Defines a Dreame Vacuum Switch entity."""

    __slots__ = ("_computed_set_fn",)

    entity_description: DreameVacuumSwitchEntityDescription

    def __init__(
        self,
        coordinator: DreameVacuumDataUpdateCoordinator,
        description: DreameVacuumSwitchEntityDescription,
    ) -> None:
        """Initialize a Dreame Vacuum switch entity."""
        self._computed_set_fn: Callable[[Any, int], None] | None = description.set_fn

        super().__init__(coordinator, description)

        self._computed_set_fn = self._resolve_set_fn(coordinator, description)

        self._generate_entity_id(ENTITY_ID_FORMAT)
        value = self.native_value
        self._attr_is_on = None if value is None else bool(value)

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.device is not None:
            value = self.native_value
            self._attr_is_on = None if value is None else bool(value)
        super()._handle_coordinator_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the Dreame Vacuum sync receive switch."""
        await self.async_set_state(0)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the Dreame Vacuum sync receive switch."""
        await self.async_set_state(1)

    async def async_set_state(self, state: int) -> None:
        """Turn on or off the Dreame Vacuum sync receive switch."""
        if not self.available:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="entity_unavailable",
            )

        value = int(state)
        if self.entity_description.format_fn is not None:
            value = self.entity_description.format_fn(state, self.device)

        if self._computed_set_fn is not None:
            await self._try_command("Unable to call: %s", self._computed_set_fn, self.device, value)
        elif self.entity_description.property_key is not None:
            await self._try_command(
                "Unable to call: %s",
                self.device.set_property,
                self.entity_description.property_key,
                value,
            )
