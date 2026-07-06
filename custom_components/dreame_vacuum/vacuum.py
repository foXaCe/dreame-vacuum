"""Vacuum platform for Dreame Vacuum.

Exposes the main StateVacuumEntity that drives cleaning, docking, and the
battery of services (`vacuum_clean_segment`, `vacuum_clean_zone`, etc.)
declared in services.yaml.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Final

# VacuumEntityFeature: import from the public package, not vacuum.const
# (removed in recent HA). Older HA re-exports it implicitly, hence the ignore.
from homeassistant.components.vacuum import (  # type: ignore[attr-defined]
    StateVacuumEntity,
    VacuumEntityFeature,
)

try:
    from homeassistant.components.vacuum import Segment  # type: ignore[attr-defined]
except ImportError:
    from dataclasses import dataclass

    @dataclass
    class Segment:  # type: ignore[no-redef]
        """Fallback room segment descriptor for Home Assistant cores lacking it."""

        id: str
        name: str
        group: str | None = None


CLEAN_AREA_ENTITY_FEATURE = getattr(VacuumEntityFeature, "CLEAN_AREA", 0)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue

PARALLEL_UPDATES = 1

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONSUMABLE_DEODORIZER,
    CONSUMABLE_DETERGENT,
    CONSUMABLE_DIRTY_WATER_TANK,
    CONSUMABLE_FILTER,
    CONSUMABLE_MAIN_BRUSH,
    CONSUMABLE_MOP_PAD,
    CONSUMABLE_ONBOARD_DIRTY_WATER_TANK,
    CONSUMABLE_SCALE_INHIBITOR,
    CONSUMABLE_SENSOR,
    CONSUMABLE_SIDE_BRUSH,
    CONSUMABLE_SILVER_ION,
    CONSUMABLE_SQUEEGEE,
    CONSUMABLE_TANK_FILTER,
    CONSUMABLE_WHEEL,
    DOMAIN,
    FAN_SPEED_SILENT,
    FAN_SPEED_STANDARD,
    FAN_SPEED_STRONG,
    FAN_SPEED_TURBO,
    DreameVacuumConfigEntry,
)
from .coordinator import DreameVacuumDataUpdateCoordinator
from .dreame import DreameVacuumAction, DreameVacuumState, DreameVacuumSuctionLevel
from .dreame.const import (
    STATE_CLEANING,
    STATE_DOCKED,
    STATE_ERROR,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_RETURNING,
    STATE_UNKNOWN,
)
from .entity import DreameVacuumEntity
from .recorder import VACUUM_UNRECORDED_ATTRIBUTES

STATE_CODE_TO_STATE: Final = {
    DreameVacuumState.UNKNOWN: STATE_UNKNOWN,
    DreameVacuumState.SWEEPING: STATE_CLEANING,
    DreameVacuumState.IDLE: STATE_IDLE,
    DreameVacuumState.PAUSED: STATE_PAUSED,
    DreameVacuumState.ERROR: STATE_ERROR,
    DreameVacuumState.RETURNING: STATE_RETURNING,
    DreameVacuumState.CHARGING: STATE_DOCKED,
    DreameVacuumState.MOPPING: STATE_CLEANING,
    DreameVacuumState.DRYING: STATE_DOCKED,
    DreameVacuumState.WASHING: STATE_CLEANING,
    DreameVacuumState.RETURNING_TO_WASH: STATE_RETURNING,
    DreameVacuumState.BUILDING: STATE_DOCKED,
    DreameVacuumState.SWEEPING_AND_MOPPING: STATE_CLEANING,
    DreameVacuumState.CHARGING_COMPLETED: STATE_DOCKED,
    DreameVacuumState.UPGRADING: STATE_IDLE,
    DreameVacuumState.CLEAN_SUMMON: STATE_CLEANING,
    DreameVacuumState.STATION_RESET: STATE_IDLE,
    DreameVacuumState.RETURNING_INSTALL_MOP: STATE_RETURNING,
    DreameVacuumState.RETURNING_REMOVE_MOP: STATE_RETURNING,
    DreameVacuumState.WATER_CHECK: STATE_DOCKED,
    DreameVacuumState.CLEAN_ADD_WATER: STATE_CLEANING,
    DreameVacuumState.WASHING_PAUSED: STATE_PAUSED,
    DreameVacuumState.AUTO_EMPTYING: STATE_DOCKED,
    DreameVacuumState.REMOTE_CONTROL: STATE_CLEANING,
    DreameVacuumState.SMART_CHARGING: STATE_DOCKED,
    DreameVacuumState.SECOND_CLEANING: STATE_CLEANING,
    DreameVacuumState.HUMAN_FOLLOWING: STATE_CLEANING,
    DreameVacuumState.SPOT_CLEANING: STATE_CLEANING,
    DreameVacuumState.RETURNING_AUTO_EMPTY: STATE_RETURNING,
    DreameVacuumState.SHORTCUT: STATE_CLEANING,
    DreameVacuumState.WAITING_FOR_TASK: STATE_IDLE,
    DreameVacuumState.STATION_CLEANING: STATE_CLEANING,
    DreameVacuumState.RETURNING_TO_DRAIN: STATE_RETURNING,
    DreameVacuumState.DRAINING: STATE_CLEANING,
    DreameVacuumState.AUTO_WATER_DRAINING: STATE_CLEANING,
    DreameVacuumState.EMPTYING: STATE_DOCKED,
    DreameVacuumState.DUST_BAG_DRYING: STATE_DOCKED,
    DreameVacuumState.DUST_BAG_DRYING_PAUSED: STATE_PAUSED,
    DreameVacuumState.HEADING_TO_EXTRA_CLEANING: STATE_CLEANING,
    DreameVacuumState.EXTRA_CLEANING: STATE_CLEANING,
    DreameVacuumState.FINDING_PET_PAUSED: STATE_PAUSED,
    DreameVacuumState.FINDING_PET: STATE_CLEANING,
    DreameVacuumState.MONITORING: STATE_CLEANING,
    DreameVacuumState.MONITORING_PAUSED: STATE_PAUSED,
    DreameVacuumState.INITIAL_DEEP_CLEANING: STATE_CLEANING,
    DreameVacuumState.INITIAL_DEEP_CLEANING_PAUSED: STATE_PAUSED,
    DreameVacuumState.SANITIZING: STATE_DOCKED,
    DreameVacuumState.SANITIZING_WITH_DRY: STATE_DOCKED,
}

SUCTION_LEVEL_TO_FAN_SPEED: Final = {
    DreameVacuumSuctionLevel.QUIET: FAN_SPEED_SILENT,
    DreameVacuumSuctionLevel.STANDARD: FAN_SPEED_STANDARD,
    DreameVacuumSuctionLevel.STRONG: FAN_SPEED_STRONG,
    DreameVacuumSuctionLevel.TURBO: FAN_SPEED_TURBO,
}

CONSUMABLE_RESET_ACTION = {
    CONSUMABLE_MAIN_BRUSH: DreameVacuumAction.RESET_MAIN_BRUSH,
    CONSUMABLE_SIDE_BRUSH: DreameVacuumAction.RESET_SIDE_BRUSH,
    CONSUMABLE_FILTER: DreameVacuumAction.RESET_FILTER,
    CONSUMABLE_TANK_FILTER: DreameVacuumAction.RESET_TANK_FILTER,
    CONSUMABLE_SENSOR: DreameVacuumAction.RESET_SENSOR,
    CONSUMABLE_MOP_PAD: DreameVacuumAction.RESET_MOP_PAD,
    CONSUMABLE_SILVER_ION: DreameVacuumAction.RESET_SILVER_ION,
    CONSUMABLE_DETERGENT: DreameVacuumAction.RESET_DETERGENT,
    CONSUMABLE_SQUEEGEE: DreameVacuumAction.RESET_SQUEEGEE,
    CONSUMABLE_ONBOARD_DIRTY_WATER_TANK: DreameVacuumAction.RESET_ONBOARD_DIRTY_WATER_TANK,
    CONSUMABLE_DIRTY_WATER_TANK: DreameVacuumAction.RESET_DIRTY_WATER_TANK,
    CONSUMABLE_DEODORIZER: DreameVacuumAction.RESET_DEODORIZER,
    CONSUMABLE_WHEEL: DreameVacuumAction.RESET_WHEEL,
    CONSUMABLE_SCALE_INHIBITOR: DreameVacuumAction.RESET_SCALE_INHIBITOR,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DreameVacuumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a Dreame Vacuum based on a config entry."""
    coordinator = entry.runtime_data.coordinator

    async_add_entities([DreameVacuum(coordinator)])


class DreameVacuum(DreameVacuumEntity, StateVacuumEntity):  # type: ignore[misc]
    """Representation of a Dreame Vacuum cleaner robot."""

    __slots__ = ("_activity_class", "_vacuum_state", "last_seen_segments")

    _unrecorded_attributes = frozenset(VACUUM_UNRECORDED_ATTRIBUTES)

    def __init__(self, coordinator: DreameVacuumDataUpdateCoordinator) -> None:
        """Initialize the vacuum entity."""
        super().__init__(coordinator)

        self._attr_device_class = DOMAIN
        # _attr_name = None + has_entity_name=True makes the entity inherit
        # the device name, per modern HA conventions. Existing entity_ids are
        # persisted in the entity registry and remain stable.
        #
        # Legacy note: pre-6.2.x installations used a leading-whitespace hack
        # on _attr_name to force the vacuum to sort first on the device
        # configuration page. That produced duplicated entity_ids of the form
        # "vacuum.<slug>_<slug>". Those entity_ids are preserved as-is so
        # automations and dashboards keep working; users who want the cleaner
        # form can rename the entity from the UI.
        self._attr_name = None
        self._attr_unique_id = f"{coordinator.device.mac}_" + DOMAIN
        self._attr_supported_features = (
            VacuumEntityFeature.SEND_COMMAND
            | VacuumEntityFeature.LOCATE
            | VacuumEntityFeature.STATE
            | VacuumEntityFeature.MAP
            | VacuumEntityFeature.START
            | VacuumEntityFeature.PAUSE
            | VacuumEntityFeature.STOP
            | VacuumEntityFeature.RETURN_HOME
            | CLEAN_AREA_ENTITY_FEATURE
        )

        # VacuumActivity was added in HA 2024.12; fallback for older versions
        try:
            module = importlib.import_module("homeassistant.components.vacuum")
            self._activity_class = module.VacuumActivity
        except (ImportError, AttributeError):
            self._activity_class = None

        # Baseline for map-segment change detection (see _check_segments_changed).
        self.last_seen_segments: set[str] | None = None

        self._set_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._set_attrs()
        if CLEAN_AREA_ENTITY_FEATURE:
            self._check_segments_changed()
        self.async_write_ha_state()

    @callback
    def _check_segments_changed(self) -> None:
        """Surface a repair issue when the cleanable map segments (rooms) change.

        Room ids are referenced by segment-based automations and scripts; when
        the robot re-maps a floor those ids can shift, silently breaking the
        automations. We record a baseline the first time segments are seen and
        raise a repair issue whenever the set of ids changes afterwards.
        """
        current_ids = {seg.id for seg in self._get_segments()}
        if not current_ids:
            # No map / no visible segments yet: wait for a stable baseline.
            return

        if self.last_seen_segments is None:
            self.last_seen_segments = current_ids
            return

        if current_ids != self.last_seen_segments:
            self.last_seen_segments = current_ids
            self.async_create_segments_issue()

    @callback
    def async_create_segments_issue(self) -> None:
        """Raise a repair issue informing that the map segments (rooms) changed."""
        async_create_issue(
            self.hass,
            DOMAIN,
            f"segments_changed_{self.device.mac}",
            is_fixable=True,
            severity=IssueSeverity.WARNING,
            translation_key="segments_changed",
            translation_placeholders={"device_name": self.device.name},
        )

    def _set_attrs(self) -> None:
        if self.device is None or self.device.status is None:
            return
        if self.device.status.has_error:
            self._attr_icon = "mdi:alert-octagon"
        elif self.device.status.has_warning or self.device.status.low_water or self.device.status.draining_complete:
            self._attr_icon = "mdi:robot-vacuum-alert"
        elif self.device.status.returning_to_wash:
            self._attr_icon = "mdi:water-circle"
        elif self.device.status.washing:
            self._attr_icon = "mdi:water-sync"
        elif (
            self.device.status.paused
            or self.device.status.washing_paused
            or self.device.status.returning_to_wash_paused
        ):
            self._attr_icon = "mdi:pause-circle"
        elif self.device.status.drying:
            self._attr_icon = "mdi:hair-dryer"
        elif self.device.status.sleeping:
            self._attr_icon = "mdi:sleep"
        elif self.device.status.charging:
            self._attr_icon = "mdi:lightning-bolt-circle"
        elif self.device.status.docked:
            self._attr_icon = "mdi:ev-station"
        elif self.device.status.cruising:
            self._attr_icon = "mdi:map-marker-path"
        else:
            self._attr_icon = "mdi:robot-vacuum"

        if (
            not (
                self.device.status
                and self.device.status.started
                and (
                    self.device.status.customized_cleaning
                    and not (self.device.status.zone_cleaning or self.device.status.spot_cleaning)
                )
            )
            and not self.device.status.scheduled_clean
        ):
            self._attr_supported_features = self._attr_supported_features | VacuumEntityFeature.FAN_SPEED
            self._attr_fan_speed = SUCTION_LEVEL_TO_FAN_SPEED.get(self.device.status.suction_level, STATE_UNKNOWN)
            self._attr_fan_speed_list = list(SUCTION_LEVEL_TO_FAN_SPEED.values())
        else:
            self._attr_supported_features = self._attr_supported_features & ~VacuumEntityFeature.FAN_SPEED
            self._attr_fan_speed = None
            self._attr_fan_speed_list = []

        self._vacuum_state = STATE_CODE_TO_STATE.get(self.device.status.state, STATE_UNKNOWN)
        if self._activity_class is None:
            self._attr_state = self._vacuum_state
        self._attr_extra_state_attributes = self.device.status.attributes or {}

    @property
    def supported_features(self) -> VacuumEntityFeature:
        """Flag vacuum cleaner features that are supported."""
        return self._attr_supported_features

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return the extra state attributes of the entity."""
        return self._attr_extra_state_attributes

    @property
    def activity(self) -> Any:
        """Return the current vacuum activity state."""
        if self._activity_class is not None and self._vacuum_state != STATE_UNKNOWN:
            try:
                return self._activity_class(self._vacuum_state)
            except ValueError:
                return None
        return None if self._vacuum_state == STATE_UNKNOWN else self._vacuum_state

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if self.device is None:
            return False
        return self._attr_available and self.device.device_connected

    async def async_locate(self, **kwargs: Any) -> None:
        """Locate the vacuum cleaner."""
        await self._try_command("Unable to call locate: %s", self.device.locate)

    async def async_start(self) -> None:
        """Start or resume the cleaning task."""
        await self._try_command("Unable to call start: %s", self.device.start)

    async def async_start_pause(self) -> None:
        """Start or resume the cleaning task."""
        await self._try_command("Unable to call start_pause: %s", self.device.start_pause)

    async def async_stop(self, **kwargs: Any) -> None:
        """Stop the vacuum cleaner."""
        await self._try_command("Unable to call stop: %s", self.device.stop)

    async def async_pause(self) -> None:
        """Pause the cleaning task."""
        await self._try_command("Unable to call pause: %s", self.device.pause)

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Set the vacuum cleaner to return to the dock."""
        await self._try_command("Unable to call return_to_base: %s", self.device.return_to_base)

    async def async_clean_zone(
        self, zone: Any, repeats: int = 1, suction_level: str = "", water_volume: str = ""
    ) -> None:
        """Clean the given zone with the requested settings."""
        await self._try_command(
            "Unable to call clean_zone: %s",
            self.device.clean_zone,
            zone,
            repeats,
            suction_level,
            water_volume,
        )

    async def async_clean_segment(
        self, segments: Any, repeats: int = 1, suction_level: str = "", water_volume: str = ""
    ) -> None:
        """Clean selected segments."""
        await self._try_command(
            "Unable to call clean_segment: %s",
            self.device.clean_segment,
            segments,
            repeats,
            suction_level,
            water_volume,
        )

    async def async_clean_spot(  # type: ignore[override]
        self, points: Any, repeats: int = 1, suction_level: str = "", water_volume: str = ""
    ) -> None:
        """Clean 1.5 square meters area of selected points."""
        await self._try_command(
            "Unable to call clean_spot: %s",
            self.device.clean_spot,
            points,
            repeats,
            suction_level,
            water_volume,
        )

    def _get_segments(self) -> list[Segment]:
        """Get the segments that can be cleaned."""
        segments: list[Segment] = []
        map_data_list = self.device.status.map_data_list
        if map_data_list is None:
            return segments

        for map_data in map_data_list.values():
            if map_data.segments is None or map_data.map_index is None:
                continue

            for segment_id, segment in map_data.segments.items():
                if segment.visibility is False:
                    continue

                segments.append(
                    Segment(
                        id=f"{map_data.map_index}_{segment_id}",
                        name=segment.name,
                        group=map_data.map_name,
                    )
                )

        return segments

    async def async_get_segments(self) -> list[Segment]:
        """Get the segments that can be cleaned."""
        return self._get_segments()

    async def async_clean_segments(self, segment_ids: list[str], **kwargs: Any) -> None:
        """Perform an area clean.

        Only cleans segments from the currently selected map.
        """
        selected_map = self.device.status.selected_map
        if selected_map is None or selected_map.map_index is None:
            return

        selected_map_index = selected_map.map_index

        # Parse composite IDs and filter to only segments from the selected map
        int_segment_ids: list[int] = []
        for composite_id in segment_ids:
            map_index_str, segment_id_str = composite_id.split("_", 1)
            if int(map_index_str) == selected_map_index:
                int_segment_ids.append(int(segment_id_str))

        if not int_segment_ids:
            return

        await self._try_command(
            "Unable to call clean_segment: %s",
            self.device.clean_segment,
            int_segment_ids,
        )

    async def async_goto(self, x: Any, y: Any) -> None:
        """Go to a point and take pictures around."""
        if x is not None and y is not None and x != "" and y != "":
            await self._try_command("Unable to call go_to: %s", self.device.go_to, x, y)

    async def async_follow_path(self, points: str = "") -> None:
        """Start a surveillance job."""
        await self._try_command("Unable to call follow_path: %s", self.device.follow_path, points)

    async def async_start_shortcut(self, shortcut_id: str = "") -> None:
        """Start a shortct job."""
        await self._try_command("Unable to call start_shortcut: %s", self.device.start_shortcut, shortcut_id)

    async def async_set_restricted_zone(self, walls: str = "", zones: str = "", no_mops: str = "") -> None:
        """Create restricted zone."""
        await self._try_command(
            "Unable to call set_restricted_zone: %s",
            self.device.set_restricted_zone,
            walls,
            zones,
            no_mops,
        )

    async def async_set_carpet_area(self, carpets: str = "", ignored_carpets: str = "") -> None:
        """Create or update carpet areas."""
        await self._try_command(
            "Unable to call set_carpet_area: %s",
            self.device.set_carpet_area,
            carpets,
            ignored_carpets,
        )

    async def async_set_virtual_threshold(self, virtual_thresholds: str = "") -> None:
        """Create or update virtual thresholds."""
        await self._try_command(
            "Unable to call set_virtual_threshold: %s",
            self.device.set_virtual_threshold,
            virtual_thresholds,
        )

    async def async_set_predefined_points(self, points: str = "") -> None:
        """Create or update predefined coordinates on the map."""
        await self._try_command(
            "Unable to call set_predefined_points: %s",
            self.device.set_predefined_points,
            points,
        )

    async def async_remote_control_move_step(
        self, rotation: int = 0, velocity: int = 0, prompt: bool | None = None
    ) -> None:
        """Remote control the robot."""
        await self._try_command(
            "Unable to call remote_control_move_step: %s",
            self.device.remote_control_move_step,
            rotation,
            velocity,
            prompt,
        )

    async def async_set_fan_speed(self, fan_speed: Any, **kwargs: Any) -> None:
        """Set fan speed."""
        if self.device.status.cruising:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="fan_speed_cruising",
            )

        if self.device.status.started and (
            self.device.status.customized_cleaning
            and not (self.device.status.zone_cleaning or self.device.status.spot_cleaning)
        ):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="fan_speed_customized_cleaning",
            )

        if isinstance(fan_speed, str) and fan_speed.isnumeric():
            fan_speed = int(fan_speed)

        if isinstance(fan_speed, int):
            if fan_speed not in DreameVacuumSuctionLevel._value2member_map_:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_fan_speed",
                )
        else:
            fan_speed = fan_speed.lower()
            fan_speed_list = {v.lower(): k for k, v in SUCTION_LEVEL_TO_FAN_SPEED.items()}
            if fan_speed in fan_speed_list:
                fan_speed = fan_speed_list[fan_speed]
            else:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="fan_speed_not_recognized",
                    translation_placeholders={"options": str(self.fan_speed_list)},
                )

        await self._try_command("Unable to set fan speed: %s", self.device.set_suction_level, fan_speed)

    async def async_select_map(self, map_id: Any) -> None:
        """Switch selected map."""
        await self._try_command("Unable to switch to selected map: %s", self.device.set_selected_map, map_id)

    async def async_delete_map(self, map_id: Any = None) -> None:
        """Delete a map."""
        await self._try_command("Unable to delete map: %s", self.device.delete_map, map_id)

    async def async_save_temporary_map(self) -> None:
        """Save the temporary map."""
        await self._try_command("Unable to save map: %s", self.device.save_temporary_map)

    async def async_discard_temporary_map(self) -> None:
        """Discard the temporary map."""
        await self._try_command("Unable to discard temporary map: %s", self.device.discard_temporary_map)

    async def async_replace_temporary_map(self, map_id: Any = None) -> None:
        """Replace the temporary map with another saved map."""
        await self._try_command(
            "Unable to replace temporary map: %s",
            self.device.replace_temporary_map,
            map_id,
        )

    async def async_request_map(self) -> None:
        """Request new map."""
        await self._try_command("Unable to call request_map: %s", self.device.request_map)

    async def async_set_property(self, key: Any, value: Any) -> None:
        """Set property."""
        if key is not None and value is not None and key != "" and value != "":
            await self._try_command("set_property failed: %s", self.device.set_property_value, key, value)

    async def async_call_action(self, key: Any, value: Any = None) -> None:
        """Call action."""
        if key is not None and key != "":
            await self._try_command("call_action failed: %s", self.device.call_action_value, key, value)

    async def async_delete_schedule(self, schedule_id: Any) -> None:
        """Delete a scheduled cleaning task."""
        await self._try_command(
            "Unable to call delete_schedule: %s",
            self.device.delete_schedule,
            schedule_id,
        )

    async def async_set_schedule(
        self,
        enabled: Any,
        time: Any,
        schedule_id: Any = None,
        repeats: Any = None,
        once: Any = False,
        map_id: Any = None,
        suction_level: Any = None,
        water_volume: Any = None,
        options: Any = None,
    ) -> None:
        """Create or update a scheduled cleaning task."""
        await self._try_command(
            "Unable to call set_schedule_task: %s",
            self.device.set_schedule_task,
            schedule_id,
            enabled,
            time,
            repeats,
            once,
            map_id,
            suction_level,
            water_volume,
            options,
        )

    async def async_rename_map(self, map_id: Any, map_name: str = "") -> None:
        """Rename a map"""
        await self._try_command(
            "Unable to call rename_map: %s",
            self.device.rename_map,
            map_id,
            map_name,
        )

    async def async_restore_map(self, recovery_map_index: Any, map_id: Any = None) -> None:
        """Restore a map"""
        if recovery_map_index and recovery_map_index != "":
            await self._try_command(
                "Unable to call restore_map: %s",
                self.device.restore_map,
                recovery_map_index,
                map_id,
            )

    async def async_restore_map_from_file(self, file_url: Any, map_id: Any = None) -> None:
        """Restore a map from file"""
        if file_url and file_url != "":
            await self._try_command(
                "Unable to call restore_map_from_file: %s",
                self.device.restore_map_from_file,
                file_url,
                map_id,
            )

    async def async_backup_map(self, map_id: Any = None) -> None:
        """Backup a map"""
        await self._try_command(
            "Unable to call backup_map: %s",
            self.device.backup_map,
            map_id,
        )

    async def async_rename_segment(self, segment_id: Any, segment_name: str = "") -> None:
        """Rename a segment"""
        if segment_name != "":
            await self._try_command(
                "Unable to call set_segment_name: %s",
                self.device.set_segment_name,
                segment_id,
                0,
                segment_name,
            )

    async def async_merge_segments(self, map_id: Any = None, segments: Any = None) -> None:
        """Merge segments"""
        if segments is not None:
            await self._try_command(
                "Unable to call merge_segments: %s",
                self.device.merge_segments,
                map_id,
                segments,
            )

    async def async_split_segments(self, map_id: Any = None, segment: Any = None, line: Any = None) -> None:
        """Split segments"""
        if segment is not None and line is not None:
            await self._try_command(
                "Unable to call split_segments: %s",
                self.device.split_segments,
                map_id,
                segment,
                line,
            )

    async def async_set_cleaning_sequence(self, cleaning_sequence: Any) -> None:
        """Set cleaning sequence"""
        if cleaning_sequence != "" and cleaning_sequence is not None:
            await self._try_command(
                "Unable to call cleaning_sequence: %s",
                self.device.set_cleaning_sequence,
                cleaning_sequence,
            )

    async def async_set_custom_cleaning(
        self,
        segment_id: Any,
        suction_level: Any,
        water_volume: Any,
        repeats: Any,
        cleaning_mode: Any = None,
        custom_mopping_route: Any = None,
        cleaning_route: Any = None,
        wetness_level: Any = None,
    ) -> None:
        """Set custom cleaning"""
        if (
            segment_id != ""
            and segment_id is not None
            and suction_level != ""
            and suction_level is not None
            and water_volume != ""
            and water_volume is not None
            and repeats != ""
            and repeats is not None
        ):
            await self._try_command(
                "Unable to call set_custom_cleaning: %s",
                self.device.set_custom_cleaning,
                segment_id,
                suction_level,
                water_volume,
                repeats,
                cleaning_mode,
                custom_mopping_route,
                cleaning_route,
                wetness_level,
            )

    async def async_set_custom_carpet_cleaning(
        self,
        id: Any,
        type: Any,
        carpet_cleaning: Any = None,
        carpet_settings: Any = None,
    ) -> None:
        """Set custom carpet cleaning"""
        if id != "" and id is not None and type != "" and type is not None:
            await self._try_command(
                "Unable to call set_custom_carpet_cleaning: %s",
                self.device.set_custom_carpet_cleaning,
                id,
                type,
                carpet_cleaning,
                carpet_settings,
            )

    async def async_install_voice_pack(self, lang_id: Any, url: Any, md5: Any, size: Any, **kwargs: Any) -> None:
        """install a custom language pack"""
        await self._try_command(
            "Unable to call install_voice_pack: %s",
            self.device.install_voice_pack,
            lang_id,
            url,
            md5,
            size,
        )

    async def async_send_command(self, command: str, params: Any = None, **kwargs: Any) -> None:
        """Send a command to a vacuum cleaner."""
        await self._try_command("Unable to call send_command: %s", self.device.send_command, command, params)

    async def async_reset_consumable(self, consumable: str) -> None:
        """Reset consumable"""
        action = CONSUMABLE_RESET_ACTION.get(consumable)
        if action:
            await self._try_command(
                "Unable to call reset_consumable: %s",
                self.device.call_action,
                action,
            )

    async def async_rename_shortcut(self, shortcut_id: Any, shortcut_name: Any) -> None:
        """Rename a shortcut"""
        if shortcut_name and shortcut_name != "":
            await self._try_command(
                "Unable to call rename_shortcut: %s",
                self.device.rename_shortcut,
                shortcut_id,
                shortcut_name,
            )

    async def async_set_obstacle_ignore(self, x: Any, y: Any, obstacle_ignored: Any) -> None:
        """Set obstacle ignore status"""
        if x is not None and x != "" and y is not None and y != "":
            await self._try_command(
                "Unable to call set_obstacle_ignore: %s",
                self.device.set_obstacle_ignore,
                x,
                y,
                obstacle_ignored,
            )

    async def async_set_router_position(self, x: Any, y: Any) -> None:
        """Set router position on current map"""
        if x is not None and x != "" and y is not None and y != "":
            await self._try_command(
                "Unable to call set_router_position: %s",
                self.device.set_router_position,
                x,
                y,
            )
