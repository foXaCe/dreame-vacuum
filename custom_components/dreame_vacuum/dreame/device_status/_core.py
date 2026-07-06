from __future__ import annotations

"""Device status module for Dreame vacuum integration.

Contains DreameVacuumDeviceStatus which provides computed properties
and attributes from raw device property values.
"""

from datetime import datetime
import time
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from ..device import DreameVacuumDevice
    from ..map_manager import DreameMapVacuumMapManager

from ..const import (
    ATTR_AP,
    ATTR_AUTO_EMPTY_MODE,
    ATTR_BATTERY,
    ATTR_CAPABILITIES,
    ATTR_CARPET_AVOIDANCE,
    ATTR_CHARGING,
    ATTR_CLEANED_AREA,
    ATTR_CLEANGENIUS,
    ATTR_CLEANING_MODE,
    ATTR_CLEANING_SEQUENCE,
    ATTR_CLEANING_TIME,
    ATTR_CLEANUP_METHOD,
    ATTR_COMPLETED,
    ATTR_CRUISING_TIME,
    ATTR_CRUISING_TYPE,
    ATTR_CRUSING,
    ATTR_CURRENT_SEGMENT,
    ATTR_DID,
    ATTR_DND,
    ATTR_DOCKED,
    ATTR_DRAINING,
    ATTR_DRAINING_AVAILABLE,
    ATTR_DRYING,
    ATTR_DRYING_AVAILABLE,
    ATTR_DUST_COLLECTION_AVAILABLE,
    ATTR_FIRMWARE_VERSION,
    ATTR_FLOOR_DIRECTION_CLEANING_AVAILABLE,
    ATTR_HAS_SAVED_MAP,
    ATTR_HAS_TEMPORARY_MAP,
    ATTR_ICON,
    ATTR_ID,
    ATTR_INTERRUPT_REASON,
    ATTR_LOW_WATER,
    ATTR_MAP_INDEX,
    ATTR_MAP_NAME,
    ATTR_MAPPING,
    ATTR_MAPPING_AVAILABLE,
    ATTR_MOP_CLEAN_FREQUENCY,
    ATTR_MOP_PAD,
    ATTR_MOP_PAD_HUMIDITY,
    ATTR_MULTIPLE_CLEANING_TIME,
    ATTR_NAME,
    ATTR_NEGLECTED_SEGMENTS,
    ATTR_OFF_PEAK_CHARGING,
    ATTR_OFF_PEAK_CHARGING_END,
    ATTR_OFF_PEAK_CHARGING_START,
    ATTR_PAUSED,
    ATTR_PREVIOUS_SELF_CLEAN_AREA,
    ATTR_PREVIOUS_SELF_CLEAN_TIME,
    ATTR_RETURNING,
    ATTR_RETURNING_PAUSED,
    ATTR_ROOMS,
    ATTR_RUNNING,
    ATTR_SEGMENT_CLEANING,
    ATTR_SELECTED_MAP,
    ATTR_SELECTED_MAP_ID,
    ATTR_SELECTED_MAP_INDEX,
    ATTR_SELF_CLEAN_AREA,
    ATTR_SELF_CLEAN_AREA_MAX,
    ATTR_SELF_CLEAN_AREA_MIN,
    ATTR_SELF_CLEAN_TIME,
    ATTR_SELF_CLEAN_TIME_MAX,
    ATTR_SELF_CLEAN_TIME_MIN,
    ATTR_SHORTCUT_TASK,
    ATTR_SHORTCUTS,
    ATTR_SPOT_CLEANING,
    ATTR_STARTED,
    ATTR_STATUS,
    ATTR_SUCTION_LEVEL,
    ATTR_TIMESTAMP,
    ATTR_VACUUM_STATE,
    ATTR_WASHING,
    ATTR_WASHING_AVAILABLE,
    ATTR_WASHING_MODE,
    ATTR_WASHING_PAUSED,
    ATTR_WATER_TANK,
    ATTR_ZONE_CLEANING,
    AUTO_EMPTY_MODE_TO_NAME,
    CARPET_CLEANING_CODE_TO_NAME,
    CARPET_SENSITIVITY_CODE_TO_NAME,
    CLEANGENIUS_MODE_TO_NAME,
    CLEANGENIUS_TO_NAME,
    CLEANING_MODE_CODE_TO_NAME,
    CLEANING_ROUTE_TO_NAME,
    CONSUMABLE_TO_LIFE_WARNING_DESCRIPTION,
    CUSTOM_MOPPING_ROUTE_TO_NAME,
    ERROR_CODE_TO_ERROR_DESCRIPTION,
    ERROR_CODE_TO_ERROR_NAME,
    ERROR_CODE_TO_IMAGE_INDEX,
    FLOOR_MATERIAL_CODE_TO_NAME,
    FLOOR_MATERIAL_DIRECTION_CODE_TO_NAME,
    MOP_CLEAN_FREQUENCY_TO_NAME,
    MOP_EXTEND_FREQUENCY_TO_NAME,
    MOP_PAD_HUMIDITY_CODE_TO_NAME,
    MOP_PAD_SWING_TO_NAME,
    MOP_WASH_LEVEL_TO_NAME,
    MOPPING_TYPE_TO_NAME,
    PROPERTY_TO_NAME,
    SECOND_CLEANING_TO_NAME,
    SEGMENT_VISIBILITY_CODE_TO_NAME,
    SELF_CLEAN_FREQUENCY_TO_NAME,
    STATE_UNKNOWN,
    STATUS_CODE_TO_NAME,
    SUCTION_LEVEL_CODE_TO_NAME,
    VOICE_ASSISTANT_LANGUAGE_TO_NAME,
    WASHING_MODE_TO_NAME,
    WATER_TANK_CODE_TO_NAME,
    WATER_TEMPERATURE_TO_NAME,
    WATER_VOLUME_CODE_TO_NAME,
    WIDER_CORNER_COVERAGE_TO_NAME,
)

# ERROR_IMAGE is imported lazily inside `error_image` from the lightweight
# _notification_images sibling module (~8.7MB) to keep notification paths
# independent of the map renderer resources.
from ..vacuum_types import (
    ATTR_ACTIVE_AREAS,
    ATTR_ACTIVE_CRUISE_POINTS,
    ATTR_ACTIVE_POINTS,
    ATTR_ACTIVE_SEGMENTS,
    ATTR_PREDEFINED_POINTS,
    PROPERTY_AVAILABILITY,
    Coordinate,
    DreameVacuumAIProperty,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumCarpetCleaning,
    DreameVacuumCleaningMode,
    DreameVacuumDeviceCapability,
    DreameVacuumErrorCode,
    DreameVacuumProperty,
    DreameVacuumStreamStatus,
    DreameVacuumWaterTank,
    GoToZoneSettings,
    MapData,
)

_BOOLEAN_PROPERTIES = frozenset(
    [
        DreameVacuumProperty.TIGHT_MOPPING,
        DreameVacuumProperty.MULTI_FLOOR_MAP,
        DreameVacuumProperty.INTELLIGENT_RECOGNITION,
        DreameVacuumProperty.SELF_CLEAN,
        DreameVacuumProperty.CHILD_LOCK,
        DreameVacuumProperty.MAP_SAVING,
        DreameVacuumProperty.RESUME_CLEANING,
        DreameVacuumProperty.CARPET_RECOGNITION,
        DreameVacuumProperty.CARPET_CLEANING,
        DreameVacuumProperty.CARPET_BOOST,
        DreameVacuumProperty.CLEAN_CARPETS_FIRST,
        DreameVacuumProperty.OBSTACLE_AVOIDANCE,
        DreameVacuumProperty.AUTO_MOUNT_MOP,
        DreameVacuumProperty.VOICE_ASSISTANT,
        DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE,
        DreameVacuumAutoSwitchProperty.UV_STERILIZATION,
        DreameVacuumAutoSwitchProperty.HOT_WASHING,
        DreameVacuumAutoSwitchProperty.MAX_SUCTION_POWER,
        DreameVacuumAutoSwitchProperty.AUTO_DRYING,
        DreameVacuumAutoSwitchProperty.CUSTOM_MOPPING_MODE,
        DreameVacuumAutoSwitchProperty.MOP_EXTEND,
        DreameVacuumAutoSwitchProperty.INTENSIVE_CARPET_CLEANING,
        DreameVacuumAutoSwitchProperty.FLOOR_DIRECTION_CLEANING,
        DreameVacuumAutoSwitchProperty.GAP_CLEANING_EXTENSION,
        DreameVacuumAutoSwitchProperty.MOPPING_UNDER_FURNITURES,
        DreameVacuumAutoSwitchProperty.COLLISION_AVOIDANCE,
        DreameVacuumAutoSwitchProperty.FILL_LIGHT,
        DreameVacuumAutoSwitchProperty.STREAMING_VOICE_PROMPT,
    ]
)


from ._activity import _ActivityMixin
from ._consumables import _ConsumablesMixin
from ._map_props import _MapPropsMixin
from ._named_props import _NamedPropsMixin
from ._station import _StationMixin


class DreameVacuumDeviceStatus(_NamedPropsMixin, _ActivityMixin, _MapPropsMixin, _ConsumablesMixin, _StationMixin):
    """Helper class for device status and int enum type properties.
    This class is used for determining various states of the device by its properties.
    Determined states are used by multiple validation and rendering condition checks.
    Almost of the rules are extracted from mobile app that has a similar class with same purpose.
    """

    def __init__(self, device: Any) -> None:
        self._device: DreameVacuumDevice = device
        self._cleaning_history: list[Any] | None = None
        self._cleaning_history_attrs: dict[str, Any] | None = None
        self._last_cleaning_time: datetime | None = None
        self._cruising_history: list[Any] | None = None
        self._cruising_history_attrs: dict[str, Any] | None = None
        self._last_cruising_time: datetime | None = None
        self._history_map_data: dict[str, MapData] = {}
        self._previous_cleaning_sequence: dict[int, list[int]] = {}

        self.suction_level_list = {v: k for k, v in SUCTION_LEVEL_CODE_TO_NAME.items()}
        self.water_volume_list = {v: k for k, v in WATER_VOLUME_CODE_TO_NAME.items()}
        self.mop_pad_humidity_list = {v: k for k, v in MOP_PAD_HUMIDITY_CODE_TO_NAME.items()}
        self.cleaning_mode_list = {v: k for k, v in CLEANING_MODE_CODE_TO_NAME.items()}
        self.carpet_sensitivity_list = {v: k for k, v in CARPET_SENSITIVITY_CODE_TO_NAME.items()}
        self.carpet_cleaning_list = {v: k for k, v in CARPET_CLEANING_CODE_TO_NAME.items()}
        self.mop_wash_level_list = {v: k for k, v in MOP_WASH_LEVEL_TO_NAME.items()}
        self.mop_clean_frequency_list = {v: k for k, v in MOP_CLEAN_FREQUENCY_TO_NAME.items()}
        self.mopping_type_list = {v: k for k, v in MOPPING_TYPE_TO_NAME.items()}
        self.wider_corner_coverage_list = {v: k for k, v in WIDER_CORNER_COVERAGE_TO_NAME.items()}
        self.mop_pad_swing_list = {v: k for k, v in MOP_PAD_SWING_TO_NAME.items()}
        self.mop_extend_frequency_list = {v: k for k, v in MOP_EXTEND_FREQUENCY_TO_NAME.items()}
        self.second_cleaning_list = {v: k for k, v in SECOND_CLEANING_TO_NAME.items()}
        self.cleaning_route_list = {v: k for k, v in CLEANING_ROUTE_TO_NAME.items()}
        self.custom_mopping_route_list = {v: k for k, v in CUSTOM_MOPPING_ROUTE_TO_NAME.items()}
        self.cleangenius_list = {v: k for k, v in CLEANGENIUS_TO_NAME.items()}
        self.washing_mode_list = {v: k for k, v in WASHING_MODE_TO_NAME.items()}
        self.cleangenius_mode_list = {v: k for k, v in CLEANGENIUS_MODE_TO_NAME.items()}
        self.water_temperature_list = {v: k for k, v in WATER_TEMPERATURE_TO_NAME.items()}
        self.self_clean_frequency_list = {v: k for k, v in SELF_CLEAN_FREQUENCY_TO_NAME.items()}
        self.auto_empty_mode_list = {v: k for k, v in AUTO_EMPTY_MODE_TO_NAME.items()}
        self.floor_material_list = {v: k for k, v in FLOOR_MATERIAL_CODE_TO_NAME.items()}
        self.floor_material_direction_list = {v: k for k, v in FLOOR_MATERIAL_DIRECTION_CODE_TO_NAME.items()}
        self.visibility_list = {v: k for k, v in SEGMENT_VISIBILITY_CODE_TO_NAME.items()}
        self.voice_assistant_language_list = {v: k for k, v in VOICE_ASSISTANT_LANGUAGE_TO_NAME.items()}
        self.segment_cleaning_mode_list: dict[Any, Any] = {}
        self.segment_cleaning_route_list: dict[Any, Any] = {}
        self.warning_codes = [
            DreameVacuumErrorCode.REMOVE_MOP,
            DreameVacuumErrorCode.MOP_REMOVED_2,
            DreameVacuumErrorCode.CLEAN_MOP_PAD,
            DreameVacuumErrorCode.BLOCKED,
            DreameVacuumErrorCode.WATER_TANK_DRY,
            DreameVacuumErrorCode.MOP_PAD_STOP_ROTATE,
            DreameVacuumErrorCode.MOP_PAD_STOP_ROTATE_2,
            DreameVacuumErrorCode.STATION_DISCONNECTED,
            DreameVacuumErrorCode.DUST_BAG_FULL,
            DreameVacuumErrorCode.SELF_TEST_FAILED,
            DreameVacuumErrorCode.LOW_BATTERY_TURN_OFF,
            DreameVacuumErrorCode.UNKNOWN_WARNING_2,
        ]

        self.cleaning_mode: DreameVacuumCleaningMode | None = None
        self.mop_pad_humidity = 1
        self.previous_self_clean_area = 0
        self.previous_self_clean_time = 25
        self.self_clean_area_min = 10
        self.self_clean_area_max = 35
        self.self_clean_area_default = 20
        self.self_clean_time_min = 10
        self.self_clean_time_max = 50
        self.self_clean_time_default = 25
        self.self_clean_value: int | None = None
        self.ai_policy_accepted = False
        self.go_to_zone: GoToZoneSettings | Literal[False] | None = None
        self.cleanup_completed: bool = False
        self.cleanup_started: bool = False

        self.stream_status: DreameVacuumStreamStatus | None = None
        self.stream_session = None

        self.dnd_tasks: list[dict[str, Any]] | None = None
        self.schedule: list[Any] = []
        self.off_peak_charging_config: dict[str, Any] | None = None
        self.shortcuts: dict[Any, Any] | None = None

    def _get_property(self, prop: Any) -> Any:
        """Helper function for accessing a property from device"""
        return self._device.get_property(prop)

    @property
    def _capability(self) -> DreameVacuumDeviceCapability:
        """Helper property for accessing device capabilities"""
        return self._device.capability

    @property
    def _map_manager(self) -> DreameMapVacuumMapManager | None:
        """Helper property for accessing map manager from device"""
        return self._device._map_manager

    @property
    def _device_connected(self) -> bool:
        """Helper property for accessing device connection status"""
        return self._device.device_connected

    @property
    def serial_number(self) -> int:
        """Return serial number of the device."""
        return cast(int, self._get_property(DreameVacuumProperty.SERIAL_NUMBER))

    @property
    def battery_level(self) -> int:
        """Return battery level of the device."""
        return cast(int, self._get_property(DreameVacuumProperty.BATTERY_LEVEL))

    @property
    def wetness_level(self) -> int:
        """Return wetness level of the device."""
        return cast(int, self._get_property(DreameVacuumProperty.WETNESS_LEVEL))

    @property
    def faults(self) -> Any:
        faults = self._get_property(DreameVacuumProperty.FAULTS)
        return 0 if faults == "" or faults == " " else faults

    @property
    def error(self) -> DreameVacuumErrorCode:
        """Return error of the device."""
        value = self._get_property(DreameVacuumProperty.ERROR)
        if value is not None and value in DreameVacuumErrorCode._value2member_map_:
            if (
                (self._capability.self_wash_base and value == DreameVacuumErrorCode.REMOVE_MOP.value)
                or value == DreameVacuumErrorCode.LOW_BATTERY_TURN_OFF.value
                or value == DreameVacuumErrorCode.UNKNOWN_WARNING_2.value
            ):
                return DreameVacuumErrorCode.NO_ERROR
            return DreameVacuumErrorCode(value)
        return DreameVacuumErrorCode.UNKNOWN

    @property
    def error_name(self) -> str:
        """Return error as string for translation."""
        if not self.has_error and not self.has_warning:
            return ERROR_CODE_TO_ERROR_NAME.get(DreameVacuumErrorCode.NO_ERROR, STATE_UNKNOWN)
        return ERROR_CODE_TO_ERROR_NAME.get(self.error, STATE_UNKNOWN)

    @property
    def error_description(self) -> list[str]:
        """Return error description of the device."""
        return ERROR_CODE_TO_ERROR_DESCRIPTION.get(self.error, [STATE_UNKNOWN, ""])

    @property
    def error_image(self) -> str | None:
        """Return error image of the device as base64 string."""
        if not self.has_error:
            return None
        from ..resources import ERROR_IMAGE

        return ERROR_IMAGE.get(ERROR_CODE_TO_IMAGE_INDEX.get(self.error, 19))

    @property
    def low_water(self) -> bool:
        """Returns true when water level in the clean water tank is low."""
        if self._capability.self_wash_base and not self.auto_water_refilling_enabled:
            warning = self.low_water_warning
            return bool(warning and warning.value > 1)
        return False

    @property
    def robot_status(self) -> int:  # Composite int for icon rendering (not a HA state)
        """Device status for robot icon rendering."""
        value = 0
        if self.running and not self.returning and not self.fast_mapping and not self.cruising:
            value = 1
        elif self.charging:
            value = 2
        elif self.sleeping:
            value = 3
        if self.has_error:
            value += 10
        if self.started and (self.sweeping or self.cruising):
            value += 100
        return value

    @property
    def station_status(self) -> int:  # Composite int for icon rendering (not a HA state)
        """Station status for charger icon rendering."""
        if self._capability.auto_empty_base and self.auto_emptying:
            return 1
        if self._capability.self_wash_base:
            value = 0
            if self.washing:
                value = 2
            if self.washing_paused:
                value = 3
            if self.drying:
                value = 4
            if value and self.hot_washing:
                value = value + 10
            return value
        return 0

    @property
    def has_error(self) -> bool:
        """Returns true when an error is present."""
        error = self.error
        return bool(error.value > 0 and not self.has_warning and error is not DreameVacuumErrorCode.BATTERY_LOW)

    @property
    def has_warning(self) -> bool:
        """Returns true when a warning is present and available for dismiss."""
        error = self.error
        return bool(error.value > 0 and error in self.warning_codes)

    @property
    def dust_collection_available(self) -> bool:
        """Returns true when robot is docked and can start auto emptying."""
        return bool(
            (
                self._get_property(DreameVacuumProperty.DUST_COLLECTION) == 1
                or (
                    (self._capability.auto_empty_mode or self._capability.gen5)
                    and self.started
                    and (not self.returning or self.returning_paused)
                    and not self.returning_to_wash
                )
            )
            and (not self.washing or self.washing_paused)
            and not self.draining
            and not self.self_repairing
        )

    @property
    def self_clean(self) -> bool:
        return bool(self._get_property(DreameVacuumProperty.SELF_CLEAN) == 1)

    @property
    def scheduled_clean(self) -> bool:
        if self.started:
            value = self._get_property(DreameVacuumProperty.SCHEDULED_CLEAN)
            return bool(value == 1 or value == 2 or value == 4)
        return False

    @property
    def auto_mount_mop(self) -> bool:
        return bool(
            self._capability.mop_pad_unmounting and self._get_property(DreameVacuumProperty.AUTO_MOUNT_MOP) == 1
        )

    @property
    def camera_light_brightness(self) -> int | None:
        if self._capability.camera_streaming:
            brightness = self._get_property(DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS)
            if brightness and str(brightness).isnumeric():
                return int(brightness)
        return None

    @property
    def dnd_remaining(self) -> int | None:
        """Returns remaining seconds to DND period to end."""
        if self.dnd:
            dnd_start = self.dnd_start
            dnd_end = self.dnd_end
            if dnd_start and dnd_end:
                end_time = dnd_end.split(":")
                if len(end_time) == 2:
                    now = datetime.now()
                    hour = now.hour
                    minute = now.minute
                    minute_str = f"0{minute}" if minute < 10 else str(minute)

                    time = int(f"{hour}{minute_str}")
                    start = int(dnd_start.replace(":", ""))
                    end = int(dnd_end.replace(":", ""))
                    current_seconds = hour * 3600 + minute * 60
                    end_seconds = int(end_time[0]) * 3600 + int(end_time[1]) * 60

                    if (
                        (start < end and start < time and time < end)
                        or (end < start and ((time < 2400 and time > start) or (end > time and time > 0)))
                        or time == start
                        or time == end
                    ):
                        return (
                            (end_seconds + 86400 - current_seconds)
                            if current_seconds > end_seconds
                            else (end_seconds - current_seconds)
                        )
                return 0
        return None

    @property
    def water_tank_or_mop_installed(self) -> bool:
        """Returns true when water tank or additional mop is installed to the device."""
        installed = self._get_property(DreameVacuumProperty.WATER_TANK) != DreameVacuumWaterTank.NOT_INSTALLED.value
        if self._capability.mop_pad_unmounting:
            value = self._get_property(DreameVacuumProperty.MOP_PAD_INSTALLED)
            if value is not None:
                return bool(value == 0 or installed)
        return bool(installed or self._capability.embedded_tank)

    @property
    def mop_pad_installed(self) -> bool:
        """Returns true when mop is installed on vacuums with mop pad unmounting feature."""
        if self._capability.mop_pad_unmounting:
            value = self._get_property(DreameVacuumProperty.MOP_PAD_INSTALLED)
            return self.water_tank_or_mop_installed if value is None else bool(value == 0)
        return self.water_tank_or_mop_installed

    @property
    def carpet_avoidance(self) -> bool:
        """Returns true when carpet avoidance is enabled."""
        return bool(
            self._capability.carpet_recognition
            and (
                self.carpet_cleaning is DreameVacuumCarpetCleaning.AVOIDANCE
                or self.carpet_cleaning is DreameVacuumCarpetCleaning.IGNORE
            )
        )

    @property
    def carpet_recognition(self) -> bool:
        """Returns true when carpet recognition is enabled."""
        return bool(
            self._capability.carpet_recognition and self._get_property(DreameVacuumProperty.CARPET_RECOGNITION) == 1
        )

    @property
    def auto_add_detergent(self) -> bool:
        """Returns true when auto-add detergent feature is enabled."""
        value = self._get_property(DreameVacuumProperty.AUTO_ADD_DETERGENT)
        return bool(value == 1 or value == 3)

    @property
    def customized_cleaning(self) -> bool:
        """Returns true when customized cleaning feature is enabled."""
        return bool(
            self._get_property(DreameVacuumProperty.CUSTOMIZED_CLEANING)
            and self.has_saved_map
            and not self.cleangenius_cleaning
        )

    @property
    def cleangenius_cleaning(self) -> bool:
        """Returns true when CleanGenius feature is enabled."""
        return bool(
            self._capability.cleangenius
            and self._get_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS)
            and self.mop_pad_installed
            and not self.zone_cleaning
            and not self.spot_cleaning
        )

    @property
    def custom_mopping_mode(self) -> bool:
        """Returns true when custom mopping mode feature is enabled."""
        return bool(
            self._capability.mopping_settings
            and self._get_property(DreameVacuumAutoSwitchProperty.CUSTOM_MOPPING_MODE) == 1
        )

    @property
    def max_suction_power(self) -> bool:
        """Returns true when max suction power feature is enabled."""
        return bool(
            self._capability.max_suction_power
            and self._get_property(DreameVacuumAutoSwitchProperty.MAX_SUCTION_POWER) == 1
        )

    @property
    def ultra_clean_mode(self) -> bool:
        """Returns true when ultra clean mode is enabled."""
        return bool(
            self._capability.ultra_clean_mode
            and self._get_property(DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE) == 1
        )

    @property
    def mop_extend(self) -> bool:
        """Returns true when mop extend feature is enabled."""
        return bool(self._capability.mop_extend and self._get_property(DreameVacuumAutoSwitchProperty.MOP_EXTEND) == 1)

    @property
    def smart_mop_washing(self) -> bool:
        """Returns true when smart mop washing feature is enabled."""
        return bool(
            self._capability.smart_mop_washing and self._get_property(DreameVacuumProperty.SMART_MOP_WASHING) == 1
        )

    @property
    def last_cleaning_time(self) -> datetime | None:
        if self._cleaning_history:
            return self._last_cleaning_time
        return None

    @property
    def last_cruising_time(self) -> datetime | None:
        if self._cruising_history:
            return self._last_cruising_time
        return None

    @property
    def cleaning_history(self) -> dict[str, Any] | None:
        """Returns the cleaning history list as dict."""
        if self._cleaning_history:
            if self._cleaning_history_attrs is None:
                list = {}
                for history in self._cleaning_history:
                    date = time.strftime("%m-%d %H:%M", time.localtime(history.date.timestamp()))
                    list[date] = {
                        ATTR_TIMESTAMP: history.date.timestamp(),
                        ATTR_CLEANING_TIME: f"{history.cleaning_time} min",
                        ATTR_CLEANED_AREA: f"{history.cleaned_area} m²",
                    }
                    if history.status is not None:
                        list[date][ATTR_STATUS] = (
                            STATUS_CODE_TO_NAME.get(history.status, STATE_UNKNOWN).replace("_", " ").capitalize()
                        )
                    if history.suction_level is not None:
                        list[date][ATTR_SUCTION_LEVEL] = (
                            SUCTION_LEVEL_CODE_TO_NAME.get(history.suction_level, STATE_UNKNOWN)
                            .replace("_", " ")
                            .capitalize()
                        )
                    if history.completed is not None:
                        list[date][ATTR_COMPLETED] = history.completed
                    if history.water_tank_or_mop is not None:
                        list[date][ATTR_MOP_PAD if self._capability.self_wash_base else ATTR_WATER_TANK] = (
                            WATER_TANK_CODE_TO_NAME.get(history.water_tank_or_mop, STATE_UNKNOWN)
                            .replace("_", " ")
                            .capitalize()
                        )
                    if isinstance(history.neglected_segments, dict):
                        list[date][ATTR_NEGLECTED_SEGMENTS] = {
                            k: v.name.replace("_", " ").capitalize() for k, v in history.neglected_segments.items()
                        }
                    if history.cleanup_method is not None:
                        list[date][ATTR_CLEANUP_METHOD] = history.cleanup_method.name.replace("_", " ").capitalize()
                    if history.task_interrupt_reason is not None:
                        list[date][ATTR_INTERRUPT_REASON] = history.task_interrupt_reason.name.replace(
                            "_", " "
                        ).capitalize()
                    if history.multiple_cleaning_time is not None:
                        list[date][ATTR_MULTIPLE_CLEANING_TIME] = history.multiple_cleaning_time
                self._cleaning_history_attrs = list
            return self._cleaning_history_attrs
        return None

    @property
    def cruising_history(self) -> dict[str, Any] | None:
        """Returns the cruising history list as dict."""
        if self._cruising_history:
            if self._cruising_history_attrs is None:
                list = {}
                for history in self._cruising_history:
                    date = time.strftime("%m-%d %H:%M", time.localtime(history.date.timestamp()))
                    list[date] = {
                        ATTR_CRUISING_TIME: f"{history.cleaning_time} min",
                    }
                    if history.status is not None:
                        list[date][ATTR_STATUS] = (
                            STATUS_CODE_TO_NAME.get(history.status, STATE_UNKNOWN).replace("_", " ").capitalize()
                        )
                    if history.cruise_type is not None:
                        list[date][ATTR_CRUISING_TYPE] = history.cruise_type
                    if history.map_index is not None:
                        list[date][ATTR_MAP_INDEX] = history.map_index
                    if history.map_name is not None and len(history.map_name) > 1:
                        list[date][ATTR_MAP_NAME] = history.map_name
                    if history.completed is not None:
                        list[date][ATTR_COMPLETED] = history.completed
                self._cruising_history_attrs = list
            return self._cruising_history_attrs
        return None

    @property
    def dnd(self) -> bool | None:
        """Returns DND is enabled."""
        if self._capability.dnd:
            return (
                bool(self._get_property(DreameVacuumProperty.DND))
                if not self._capability.dnd_task
                else self.dnd_tasks[0].get("en")
                if self.dnd_tasks and len(self.dnd_tasks)
                else False
            )
        return None

    @property
    def dnd_start(self) -> str | None:
        """Returns DND start time."""
        if self._capability.dnd:
            return (
                self._get_property(DreameVacuumProperty.DND_START)
                if not self._capability.dnd_task
                else self.dnd_tasks[0].get("st")
                if self.dnd_tasks and len(self.dnd_tasks)
                else "22:00"
            )
        return None

    @property
    def dnd_end(self) -> str | None:
        """Returns DND end time."""
        if self._capability.dnd:
            return (
                self._get_property(DreameVacuumProperty.DND_END)
                if not self._capability.dnd_task
                else self.dnd_tasks[0].get("et")
                if self.dnd_tasks and len(self.dnd_tasks)
                else "08:00"
            )
        return None

    @property
    def off_peak_charging(self) -> bool | None:
        """Returns Off-Peak charging is enabled."""
        if self._capability.off_peak_charging:
            config = self.off_peak_charging_config
            return bool(self._capability.off_peak_charging and config and len(config) and config.get("enable"))
        return None

    @property
    def off_peak_charging_start(self) -> str | None:
        """Returns Off-Peak charging start time."""
        if self._capability.off_peak_charging:
            return (
                self.off_peak_charging_config.get("startTime")
                if self.off_peak_charging_config and len(self.off_peak_charging_config)
                else "22:00"
            )
        return None

    @property
    def off_peak_charging_end(self) -> str | None:
        """Returns Off-Peak charging end time."""
        if self._capability.off_peak_charging:
            return (
                self.off_peak_charging_config.get("endTime")
                if self.off_peak_charging_config and len(self.off_peak_charging_config)
                else "08:00"
            )
        return None

    @property
    def auto_water_refilling_enabled(self) -> bool:
        """Returns true when auto water refilling is enabled."""
        return bool(self._get_property(DreameVacuumProperty.AUTO_WATER_REFILLING) == 1)

    @property
    def water_draining_available(self) -> bool:
        """Returns true when water tank draining is possible."""
        return bool(
            self._capability.drainage
            and self.auto_water_refilling_enabled
            and not self.draining
            and self.docked
            and not self.drying
            and not self.washing
            and not self.washing_paused
            and not self.started
        )

    @property
    def floor_direction_cleaning_available(self) -> bool:
        """Returns true when water tank draining is possible."""
        return bool(
            self._capability.floor_direction_cleaning
            and not self.started
            and not self.has_temporary_map
            and not self.fast_mapping
            and self.segments
            and len([k for k, v in self.segments.items() if v.floor_material_direction is not None])
        )

    @property
    def ai_obstacle_detection(self) -> bool:
        return bool(self._device.get_ai_property(DreameVacuumAIProperty.AI_OBSTACLE_DETECTION))

    @property
    def ai_obstacle_image_upload(self) -> bool:
        return bool(self._device.get_ai_property(DreameVacuumAIProperty.AI_OBSTACLE_IMAGE_UPLOAD))

    @property
    def ai_pet_detection(self) -> bool:
        return bool(self._device.get_ai_property(DreameVacuumAIProperty.AI_PET_DETECTION))

    @property
    def ai_furniture_detection(self) -> bool:
        return bool(self._device.get_ai_property(DreameVacuumAIProperty.AI_FURNITURE_DETECTION))

    @property
    def ai_fluid_detection(self) -> bool:
        return bool(self._device.get_ai_property(DreameVacuumAIProperty.AI_FLUID_DETECTION))

    @property
    def ai_obstacle_picture(self) -> bool:
        return bool(self._device.get_ai_property(DreameVacuumAIProperty.AI_OBSTACLE_PICTURE))

    @property
    def fill_light(self) -> bool:
        return bool(self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.FILL_LIGHT))

    @property
    def hot_washing(self) -> bool:
        if self._capability.water_temperature:
            return self.hot_water_status.value == 1
        return bool(
            self._capability.hot_washing
            and self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.HOT_WASHING) == 1
        )

    @property
    def auto_drying(self) -> bool:
        if self._device.capability.self_wash_base:
            if not self._device.capability.auto_switch_settings:
                return bool(self._get_property(DreameVacuumProperty.INTELLIGENT_RECOGNITION))
            return bool(self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.AUTO_DRYING) == 1)
        return False

    @property
    def smart_drying(self) -> bool:
        return bool(
            self._device.capability.smart_drying
            and self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.SMART_DRYING) == 1
        )

    @property
    def silent_drying(self) -> bool:
        return bool(
            self._device.capability.silent_drying and self._device.get_property(DreameVacuumProperty.SILENT_DRYING) == 1
        )

    @property
    def stain_avoidance(self) -> bool:
        return bool(self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.STAIN_AVOIDANCE) == 2)

    @property
    def pet_focused_cleaning(self) -> bool:
        return bool(self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.PET_FOCUSED_CLEANING))

    @property
    def uv_sterilization(self) -> bool:
        return bool(
            self._capability.uv_sterilization
            and self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.UV_STERILIZATION) == 1
        )

    @property
    def self_clean_by_time(self) -> bool:
        return bool(
            self.self_clean_value
            and self._capability.self_clean_frequency
            and self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.SELF_CLEAN_FREQUENCY) == 2
        )

    @property
    def job(self) -> dict[str, Any] | None:
        details: dict[str, Any] = {
            ATTR_STATUS: self.status.name,
        }
        if self._device._protocol.cloud:
            details[ATTR_DID] = self._device._protocol.cloud.device_id
        if self._capability.custom_cleaning_mode and self.cleaning_mode is not None:
            details[ATTR_CLEANING_MODE] = self.cleaning_mode.name
        details[ATTR_WATER_TANK if not self._capability.self_wash_base else ATTR_MOP_PAD] = (
            self.water_tank_or_mop_installed
        )

        if self.cleanup_completed:
            details.update(
                {
                    ATTR_CLEANED_AREA: self._get_property(DreameVacuumProperty.CLEANED_AREA),
                    ATTR_CLEANING_TIME: self._get_property(DreameVacuumProperty.CLEANING_TIME),
                    ATTR_COMPLETED: True,
                }
            )
        else:
            details[ATTR_COMPLETED] = False

        map_data = self.current_map
        if map_data:
            if map_data.active_segments:
                details[ATTR_ACTIVE_SEGMENTS] = map_data.active_segments
            elif map_data.active_areas is not None:
                if self.go_to_zone:
                    details[ATTR_ACTIVE_CRUISE_POINTS] = {
                        1: Coordinate(self.go_to_zone.x or 0, self.go_to_zone.y or 0, False, 0)
                    }
                else:
                    details[ATTR_ACTIVE_AREAS] = map_data.active_areas
            elif map_data.active_points is not None:
                details[ATTR_ACTIVE_POINTS] = map_data.active_points
            elif map_data.predefined_points is not None:
                details[ATTR_PREDEFINED_POINTS] = map_data.predefined_points
            elif map_data.active_cruise_points is not None:
                details[ATTR_ACTIVE_CRUISE_POINTS] = map_data.active_cruise_points
        return details

    def _build_property_list(self) -> tuple[list[Any], dict[str, Any], bool]:
        """Build the list of properties and initial attributes based on device capabilities."""
        availability: Any = PROPERTY_AVAILABILITY
        properties: list[Any] = [
            DreameVacuumProperty.STATUS,
            DreameVacuumProperty.CLEANING_MODE,
            DreameVacuumProperty.SUCTION_LEVEL,
            DreameVacuumProperty.TIGHT_MOPPING,
            DreameVacuumProperty.ERROR,
            DreameVacuumProperty.LOW_WATER_WARNING,
            DreameVacuumProperty.CLEANING_TIME,
            DreameVacuumProperty.CLEANED_AREA,
            DreameVacuumProperty.VOICE_PACKET_ID,
            DreameVacuumProperty.TIMEZONE,
            DreameVacuumProperty.MAIN_BRUSH_TIME_LEFT,
            DreameVacuumProperty.MAIN_BRUSH_LEFT,
            DreameVacuumProperty.SIDE_BRUSH_TIME_LEFT,
            DreameVacuumProperty.SIDE_BRUSH_LEFT,
            DreameVacuumProperty.FILTER_LEFT,
            DreameVacuumProperty.FILTER_TIME_LEFT,
            DreameVacuumProperty.TANK_FILTER_LEFT,
            DreameVacuumProperty.TANK_FILTER_TIME_LEFT,
            DreameVacuumProperty.MOP_PAD_LEFT,
            DreameVacuumProperty.MOP_PAD_TIME_LEFT,
            DreameVacuumProperty.SILVER_ION_LEFT,
            DreameVacuumProperty.SILVER_ION_TIME_LEFT,
            DreameVacuumProperty.DETERGENT_LEFT,
            DreameVacuumProperty.DETERGENT_TIME_LEFT,
            DreameVacuumProperty.SQUEEGEE_LEFT,
            DreameVacuumProperty.SQUEEGEE_TIME_LEFT,
            DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_LEFT,
            DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_TIME_LEFT,
            DreameVacuumProperty.DIRTY_WATER_TANK_LEFT,
            DreameVacuumProperty.DIRTY_WATER_TANK_TIME_LEFT,
            DreameVacuumProperty.TOTAL_CLEANED_AREA,
            DreameVacuumProperty.TOTAL_CLEANING_TIME,
            DreameVacuumProperty.CLEANING_COUNT,
            DreameVacuumProperty.CUSTOMIZED_CLEANING,
            DreameVacuumProperty.NATION_MATCHED,
            DreameVacuumProperty.TOTAL_RUNTIME,
            DreameVacuumProperty.TOTAL_CRUISE_TIME,
            DreameVacuumProperty.DRYING_PROGRESS,
            DreameVacuumProperty.CLEANING_PROGRESS,
            DreameVacuumProperty.INTELLIGENT_RECOGNITION,
            DreameVacuumProperty.MULTI_FLOOR_MAP,
            DreameVacuumProperty.WETNESS_LEVEL,
            DreameVacuumProperty.SCHEDULED_CLEAN,
            DreameVacuumProperty.VOICE_ASSISTANT,
            DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE,
            DreameVacuumProperty.AUTO_DUST_COLLECTING,
            DreameVacuumProperty.AUTO_EMPTY_STATUS,
            DreameVacuumProperty.SELF_CLEAN,
            DreameVacuumProperty.DRYING_TIME,
            DreameVacuumProperty.OBSTACLE_AVOIDANCE,
            DreameVacuumProperty.VOLUME,
            DreameVacuumProperty.CHILD_LOCK,
            DreameVacuumProperty.RESUME_CLEANING,
            DreameVacuumProperty.MAP_SAVING,
            DreameVacuumProperty.CARPET_BOOST,
            DreameVacuumProperty.SCHEDULE,
            DreameVacuumProperty.MAP_RECOVERY_STATUS,
            DreameVacuumProperty.DETERGENT_STATUS,
        ]

        if self._capability.deodorizer:
            properties.append(DreameVacuumProperty.DEODORIZER_LEFT)
            properties.append(DreameVacuumProperty.DEODORIZER_TIME_LEFT)

        if self._capability.wheel:
            properties.append(DreameVacuumProperty.WHEEL_DIRTY_LEFT)
            properties.append(DreameVacuumProperty.WHEEL_DIRTY_TIME_LEFT)

        if self._capability.scale_inhibitor:
            properties.append(DreameVacuumProperty.SCALE_INHIBITOR_LEFT)
            properties.append(DreameVacuumProperty.SCALE_INHIBITOR_TIME_LEFT)

        if self._capability.backup_map:
            properties.append(DreameVacuumProperty.MAP_BACKUP_STATUS)

        if not self._capability.disable_sensor_cleaning:
            properties.extend(
                [
                    DreameVacuumProperty.SENSOR_DIRTY_LEFT,
                    DreameVacuumProperty.SENSOR_DIRTY_TIME_LEFT,
                ]
            )

        if not self._capability.dnd_task:
            properties.extend(
                [
                    DreameVacuumProperty.DND_START,
                    DreameVacuumProperty.DND_END,
                ]
            )

        if not self._capability.carpet_recognition:
            properties.append(DreameVacuumProperty.CARPET_SENSITIVITY)
        elif not self._capability.auto_carpet_cleaning and not self._capability.mop_pad_lifting_plus:
            properties.append(DreameVacuumProperty.CARPET_RECOGNITION)

        if (
            self._capability.mop_pad_unmounting
            or self._capability.auto_carpet_cleaning
            or self._capability.mop_pad_lifting_plus
        ):
            properties.append(DreameVacuumProperty.CARPET_CLEANING)

        if not self._capability.auto_empty_mode:
            properties.append(DreameVacuumProperty.AUTO_EMPTY_FREQUENCY)

        if self._capability.mop_pad_unmounting:
            properties.append(DreameVacuumProperty.AUTO_MOUNT_MOP)

        if self._capability.detergent or self._capability.smart_mop_washing:
            properties.append(DreameVacuumProperty.AUTO_ADD_DETERGENT)

        if self._capability.clean_carpets_first:
            properties.append(DreameVacuumProperty.CLEAN_CARPETS_FIRST)

        if self._capability.auto_empty_base:
            properties.append(DreameVacuumProperty.DUST_BAG_STATUS)

        if self._capability.drainage:
            properties.append(DreameVacuumProperty.STATION_DRAINAGE_STATUS)

        if self._capability.hot_washing:
            properties.append(DreameVacuumProperty.HOT_WATER_STATUS)

        attributes: dict[str, Any] = {}

        customized = (
            not self.zone_cleaning
            and not self.spot_cleaning
            and self.has_saved_map
            and (self.cleangenius_cleaning or self.customized_cleaning)
        )
        if not self._capability.self_wash_base:
            if not self._capability.embedded_tank:
                attributes[ATTR_WATER_TANK] = self.water_tank_or_mop_installed
                properties.append(DreameVacuumProperty.WATER_VOLUME)
        else:
            attributes[ATTR_MOP_PAD] = self.water_tank_or_mop_installed
            attributes[ATTR_MOP_PAD_HUMIDITY] = self.mop_pad_humidity_name.replace("_", " ").capitalize()
            attributes[f"{ATTR_MOP_PAD_HUMIDITY}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.mop_pad_humidity_list]
                if availability["mop_pad_humidity"](self._device) or customized
                else []
            )
            properties.extend(
                [
                    DreameVacuumProperty.CLEAN_WATER_TANK_STATUS,
                    DreameVacuumProperty.DIRTY_WATER_TANK_STATUS,
                ]
            )

            if self._capability.mop_clean_frequency:
                attributes[ATTR_MOP_CLEAN_FREQUENCY] = self.self_clean_value
            else:
                if self.self_clean_value is not None:
                    attributes[ATTR_SELF_CLEAN_TIME if self.self_clean_by_time else ATTR_SELF_CLEAN_AREA] = (
                        self.self_clean_value
                    )
                attributes[ATTR_SELF_CLEAN_AREA_MIN] = self.self_clean_area_min
                attributes[ATTR_SELF_CLEAN_AREA_MAX] = self.self_clean_area_max
                attributes[ATTR_PREVIOUS_SELF_CLEAN_AREA] = self.previous_self_clean_area
                if self._capability.self_clean_frequency:
                    attributes[ATTR_SELF_CLEAN_TIME_MIN] = self.self_clean_time_min
                    attributes[ATTR_SELF_CLEAN_TIME_MAX] = self.self_clean_time_max
                    attributes[ATTR_PREVIOUS_SELF_CLEAN_TIME] = self.previous_self_clean_time

            if not self._capability.smart_mop_washing:
                if self._capability.ultra_clean_mode:
                    properties.append(DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE)

                properties.append(DreameVacuumProperty.MOP_WASH_LEVEL)
            else:
                properties.append(DreameVacuumProperty.SMART_MOP_WASHING)

                attributes[ATTR_WASHING_MODE] = self.washing_mode_name.replace("_", " ").capitalize()
                attributes[f"{ATTR_WASHING_MODE}_list"] = (
                    [v.replace("_", " ").capitalize() for v in self.washing_mode_list]
                    if availability["washing_mode"](self._device)
                    else []
                )

            if self._capability.mop_washing_with_detergent:
                properties.append(DreameVacuumProperty.MOP_WASHING_WITH_DETERGENT)

        if self._capability.auto_switch_settings:
            properties.extend(
                [
                    DreameVacuumAutoSwitchProperty.MOPPING_MODE,
                    DreameVacuumAutoSwitchProperty.AUTO_DRYING,
                    DreameVacuumAutoSwitchProperty.COLLISION_AVOIDANCE,
                    DreameVacuumAutoSwitchProperty.FILL_LIGHT,
                    DreameVacuumAutoSwitchProperty.STREAMING_VOICE_PROMPT,
                ]
            )

        if self._capability.camera_streaming:
            properties.extend(
                [
                    DreameVacuumAIProperty.AI_OBSTACLE_DETECTION,
                    DreameVacuumAIProperty.AI_PET_DETECTION,
                    DreameVacuumAIProperty.AI_OBSTACLE_PICTURE,
                    DreameVacuumAIProperty.AI_OBSTACLE_IMAGE_UPLOAD,
                    DreameVacuumAIProperty.PET_FOCUSED_DETECTION,
                ]
            )

        if self._capability.large_particles_boost:
            properties.append(DreameVacuumAIProperty.LARGE_PARTICLES_BOOST)

        if self._capability.self_wash_base and self._capability.hot_washing and not self._capability.smart_mop_washing:
            properties.append(DreameVacuumAutoSwitchProperty.HOT_WASHING)

        if self._capability.max_suction_power:
            properties.append(DreameVacuumAutoSwitchProperty.MAX_SUCTION_POWER)

        if self._capability.uv_sterilization:
            properties.append(DreameVacuumAutoSwitchProperty.UV_STERILIZATION)

        if self._capability.custom_cleaning_mode:
            properties.append(DreameVacuumAutoSwitchProperty.CUSTOM_MOPPING_MODE)

        if self._capability.cleaning_route:
            properties.append(DreameVacuumAutoSwitchProperty.CLEANING_ROUTE)

        if self._capability.cleangenius:
            properties.append(DreameVacuumAutoSwitchProperty.CLEANGENIUS)

        if self._capability.cleangenius_mode:
            properties.append(DreameVacuumProperty.CLEANGENIUS_MODE)

        if self._capability.water_temperature:
            properties.append(DreameVacuumProperty.WATER_TEMPERATURE)

        if self._capability.silent_drying:
            properties.append(DreameVacuumProperty.SILENT_DRYING)

        if self._capability.hair_compression:
            properties.append(DreameVacuumProperty.HAIR_COMPRESSION)

        if self._capability.side_brush_carpet_rotate:
            properties.append(DreameVacuumProperty.SIDE_BRUSH_CARPET_ROTATE)

        if self._capability.auto_lds_lifting:
            properties.append(DreameVacuumProperty.AUTO_LDS_LIFTING)

        if self._device.capability.dnd_functions:
            properties.extend(
                [
                    DreameVacuumProperty.DND_DISABLE_RESUME_CLEANING,
                    DreameVacuumProperty.DND_DISABLE_AUTO_EMPTY,
                    DreameVacuumProperty.DND_REDUCE_VOLUME,
                ]
            )

        if (
            self._capability.self_wash_base
            and not self._capability.custom_mopping_route
            and not self._capability.cleaning_route
        ):
            properties.append(DreameVacuumAutoSwitchProperty.MOPPING_TYPE)

        if self._capability.self_wash_base and self._capability.self_clean_frequency:
            properties.append(DreameVacuumAutoSwitchProperty.SELF_CLEAN_FREQUENCY)

        if self._capability.floor_direction_cleaning:
            properties.append(DreameVacuumAutoSwitchProperty.FLOOR_DIRECTION_CLEANING)

        if self._capability.intensive_carpet_cleaning:
            properties.append(DreameVacuumAutoSwitchProperty.INTENSIVE_CARPET_CLEANING)

        if self._capability.mop_extend:
            properties.append(DreameVacuumAutoSwitchProperty.MOP_EXTEND)
            properties.append(DreameVacuumAutoSwitchProperty.MOP_EXTEND_FREQUENCY)
        elif self._capability.mop_pad_swing:
            properties.append(DreameVacuumAutoSwitchProperty.MOP_PAD_SWING)

        if self._capability.mop_pad_swing_plus:
            properties.append(DreameVacuumAutoSwitchProperty.GAP_CLEANING_EXTENSION)
            properties.append(DreameVacuumAutoSwitchProperty.MOPPING_UNDER_FURNITURES)

        if self._capability.auto_recleaning:
            properties.append(DreameVacuumAutoSwitchProperty.AUTO_RECLEANING)

        if self._capability.auto_rewashing:
            properties.append(DreameVacuumAutoSwitchProperty.AUTO_REWASHING)

        if not self._capability.mop_pad_swing and not self._capability.mop_clean_frequency:
            properties.append(DreameVacuumAutoSwitchProperty.WIDER_CORNER_COVERAGE)

        return properties, attributes, customized

    def _format_property_value(self, prop: Any, value: Any, prop_name: Any, customized: Any) -> Any:
        """Format a single property value for the attributes dict.

        Returns a tuple of (value, extra_attrs) where extra_attrs is a dict
        of additional attributes to add (e.g. _list entries), or None to skip.
        """
        availability: Any = PROPERTY_AVAILABILITY
        extra: dict[str, Any] = {}

        if prop is DreameVacuumProperty.ERROR:
            value = self.error_name.replace("_", " ").capitalize()
        elif prop is DreameVacuumProperty.LOW_WATER_WARNING:
            value = self.low_water_warning_name.replace("_", " ").capitalize()
        elif prop is DreameVacuumProperty.STATUS:
            value = self.status_name.replace("_", " ").capitalize()
        elif prop is DreameVacuumProperty.AUTO_EMPTY_STATUS:
            value = self.auto_empty_status_name.replace("_", " ").capitalize()
        elif prop is DreameVacuumProperty.MAP_RECOVERY_STATUS:
            value = self.map_recovery_status_name.replace("_", " ").capitalize()
        elif prop is DreameVacuumProperty.MAP_BACKUP_STATUS:
            value = self.map_backup_status_name.replace("_", " ").capitalize()
        elif prop is DreameVacuumProperty.CLEAN_WATER_TANK_STATUS:
            value = self.clean_water_tank_status_name.replace("_", " ").capitalize()
        elif prop is DreameVacuumProperty.DIRTY_WATER_TANK_STATUS:
            value = self.dirty_water_tank_status_name.replace("_", " ").capitalize()
        elif prop is DreameVacuumProperty.DUST_BAG_STATUS:
            value = self.dust_bag_status_name.replace("_", " ").capitalize()
        elif prop is DreameVacuumProperty.DETERGENT_STATUS:
            value = self.detergent_status_name.replace("_", " ").capitalize()
        elif prop is DreameVacuumProperty.STATION_DRAINAGE_STATUS:
            value = self.station_drainage_status_name.replace("_", " ").capitalize()
        elif prop is DreameVacuumProperty.HOT_WATER_STATUS:
            value = self.hot_water_status_name.replace("_", " ").capitalize()
        elif prop is DreameVacuumProperty.WATER_VOLUME:
            value = self.water_volume_name.capitalize()
            extra[f"{prop_name}_list"] = (
                [v.capitalize() for v in self.water_volume_list]
                if availability[prop.name](self._device) or customized
                else []
            )
        elif prop is DreameVacuumProperty.SUCTION_LEVEL:
            value = self.suction_level_name.capitalize()
            extra[f"{prop_name}_list"] = (
                [v.capitalize() for v in self.suction_level_list]
                if availability[prop.name](self._device) or customized
                else []
            )
        elif prop is DreameVacuumProperty.CLEANING_MODE:
            value = self.cleaning_mode_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.cleaning_mode_list]
                if availability[prop.name](self._device) or customized
                else []
            )
        elif prop is DreameVacuumProperty.MOP_WASH_LEVEL:
            value = self.mop_wash_level_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.mop_wash_level_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE:
            if not self._capability.voice_assistant:
                return None, None
            value = self.voice_assistant_language_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = [v.replace("_", " ").capitalize() for v in self.voice_assistant_language_list]
        elif prop is DreameVacuumProperty.CLEANGENIUS_MODE:
            value = self.cleangenius_mode_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.cleangenius_mode_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumProperty.WATER_TEMPERATURE:
            value = self.water_temperature_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.water_temperature_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumAutoSwitchProperty.CLEANING_ROUTE:
            value = self.cleaning_route_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.cleaning_route_list]
                if availability[prop.name](self._device) or customized
                else []
            )
        elif prop is DreameVacuumAutoSwitchProperty.CLEANGENIUS:
            value = self.cleangenius_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.cleangenius_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumAutoSwitchProperty.MOPPING_TYPE:
            value = self.mopping_type_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.mopping_type_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumAutoSwitchProperty.WIDER_CORNER_COVERAGE:
            value = self.wider_corner_coverage_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.wider_corner_coverage_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumProperty.CARPET_CLEANING:
            value = self.carpet_cleaning_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.carpet_cleaning_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumProperty.CARPET_SENSITIVITY:
            value = self.carpet_sensitivity_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.carpet_sensitivity_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumAutoSwitchProperty.MOP_PAD_SWING:
            value = self.mop_pad_swing_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.mop_pad_swing_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumAutoSwitchProperty.MOP_EXTEND_FREQUENCY:
            value = self.mop_extend_frequency_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.mop_extend_frequency_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumAutoSwitchProperty.AUTO_REWASHING:
            value = self.auto_rewashing_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.second_cleaning_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumAutoSwitchProperty.AUTO_RECLEANING:
            value = self.auto_recleaning_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.second_cleaning_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumProperty.CUSTOMIZED_CLEANING:
            value = bool(value and not self.zone_cleaning and not self.spot_cleaning and self.has_saved_map)
        elif prop is DreameVacuumProperty.SCHEDULED_CLEAN:
            value = bool(value == 1 or value == 2 or value == 4)
        elif prop is DreameVacuumProperty.AUTO_DUST_COLLECTING:
            if self._capability.auto_empty_mode:
                extra[ATTR_AUTO_EMPTY_MODE] = self.auto_empty_mode_name.replace("_", " ").capitalize()
                extra[f"{ATTR_AUTO_EMPTY_MODE}_list"] = [
                    v.replace("_", " ").capitalize() for v in self.auto_empty_mode_list
                ]
            value = bool(value > 0)
        elif prop is DreameVacuumAutoSwitchProperty.SELF_CLEAN_FREQUENCY:
            value = self.self_clean_frequency_name.replace("_", " ").capitalize()
            extra[f"{prop_name}_list"] = (
                [v.replace("_", " ").capitalize() for v in self.self_clean_frequency_list]
                if availability[prop.name](self._device)
                else []
            )
        elif prop is DreameVacuumProperty.SCHEDULE:
            value = self.schedule
        elif prop in _BOOLEAN_PROPERTIES:
            value = bool(value > 0)

        return value, extra

    def _add_state_attributes(self, attributes: dict[str, Any]) -> None:
        """Add device state, map info, and capability attributes."""
        if self._capability.dnd_task and self.dnd_tasks is not None:
            attributes[ATTR_DND] = {}
            for dnd_task in self.dnd_tasks:
                attributes[ATTR_DND][dnd_task["id"]] = {
                    "enabled": dnd_task.get("en"),
                    "start": dnd_task.get("st"),
                    "end": dnd_task.get("et"),
                    # Raw device weekday bitmask, passed through opaquely.
                    # The bit-to-day mapping is NOT confirmed on a live
                    # device — only 127 (all 7 bits set) is known to mean
                    # "all days" (see docs/dev/dnd-tasks-design.md). Do not
                    # assume any other bit order without verifying against
                    # real hardware.
                    "weekday_mask": dnd_task.get("wk"),
                }
        else:
            attributes[ATTR_DND] = self.dnd

        if self._capability.off_peak_charging:
            attributes[ATTR_OFF_PEAK_CHARGING] = self.off_peak_charging
            attributes[ATTR_OFF_PEAK_CHARGING_START] = self.off_peak_charging_start
            attributes[ATTR_OFF_PEAK_CHARGING_END] = self.off_peak_charging_end

        if self._capability.shortcuts:
            attributes[ATTR_SHORTCUTS] = {}
            if self.shortcuts is not None:
                for id, shortcut in self.shortcuts.items():
                    attributes[ATTR_SHORTCUTS][id] = {
                        "name": shortcut.name,
                        "map_id": shortcut.map_id,
                        "running": shortcut.running,
                        "tasks": shortcut.tasks,
                    }

        attributes[ATTR_BATTERY] = self.battery_level
        attributes[ATTR_CLEANING_SEQUENCE] = self.segment_order
        attributes[ATTR_CHARGING] = self.charging
        attributes[ATTR_DOCKED] = self.docked
        attributes[ATTR_STARTED] = self.started
        attributes[ATTR_PAUSED] = self.paused
        attributes[ATTR_RUNNING] = self.running
        attributes[ATTR_RETURNING_PAUSED] = self.returning_paused
        attributes[ATTR_RETURNING] = self.returning
        attributes[ATTR_SEGMENT_CLEANING] = self.segment_cleaning
        attributes[ATTR_ZONE_CLEANING] = self.zone_cleaning
        attributes[ATTR_SPOT_CLEANING] = self.spot_cleaning
        attributes[ATTR_CRUSING] = self.cruising
        attributes[ATTR_VACUUM_STATE] = self.state_name.lower()
        attributes[ATTR_HAS_SAVED_MAP] = self._map_manager is not None and self.has_saved_map
        attributes[ATTR_HAS_TEMPORARY_MAP] = self.has_temporary_map

        if self._capability.lidar_navigation:
            attributes[ATTR_MAPPING] = self.fast_mapping
            attributes[ATTR_MAPPING_AVAILABLE] = self.mapping_available
        if self._capability.auto_empty_base:
            attributes[ATTR_DUST_COLLECTION_AVAILABLE] = self.dust_collection_available

        if self._capability.self_wash_base:
            attributes[ATTR_WASHING] = self.washing
            attributes[ATTR_WASHING_PAUSED] = self.washing_paused
            attributes[ATTR_DRYING] = self.drying
            if not self.auto_water_refilling_enabled:
                attributes[ATTR_LOW_WATER] = bool(self.low_water_warning)
            else:
                attributes[ATTR_DRAINING] = self.draining
            attributes[ATTR_WASHING_AVAILABLE] = bool(
                (self.washing_available or self.washing or self.returning_to_wash_paused or self.washing_paused)
                and not self.draining
                and not self.self_repairing
            )
            attributes[ATTR_DRYING_AVAILABLE] = self.drying_available
            attributes[ATTR_DRAINING_AVAILABLE] = self.water_draining_available

        if self._capability.cleangenius:
            attributes[ATTR_CLEANGENIUS] = bool(
                self.cleangenius_cleaning and not self.zone_cleaning and not self.spot_cleaning and self.has_saved_map
            )

        if self.map_list:
            attributes[ATTR_ACTIVE_SEGMENTS] = self.active_segments
            if self._capability.lidar_navigation:
                attributes[ATTR_CURRENT_SEGMENT] = self.current_room.segment_id if self.current_room else 0
            attributes[ATTR_SELECTED_MAP] = self.selected_map.map_name if self.selected_map else None
            attributes[ATTR_SELECTED_MAP_ID] = self.selected_map.map_id if self.selected_map else None
            attributes[ATTR_SELECTED_MAP_INDEX] = self.current_map.map_index if self.current_map else None
            attributes[ATTR_ROOMS] = {}
            for _k, v in (self.map_data_list or {}).items():
                attributes[ATTR_ROOMS][v.map_name] = [
                    {ATTR_ID: j, ATTR_NAME: s.name, ATTR_ICON: s.icon} for (j, s) in sorted((v.segments or {}).items())
                ]

        if self._capability.carpet_recognition:
            attributes[ATTR_CARPET_AVOIDANCE] = self.carpet_avoidance

        if self._capability.floor_direction_cleaning:
            attributes[ATTR_FLOOR_DIRECTION_CLEANING_AVAILABLE] = self.floor_direction_cleaning_available

        if self._capability.shortcuts:
            attributes[ATTR_SHORTCUT_TASK] = self.shortcut_task
        attributes[ATTR_FIRMWARE_VERSION] = self._device.info.version if self._device.info else None
        attributes[ATTR_AP] = self._device.info.ap if self._device.info else None
        attributes[ATTR_CAPABILITIES] = self._capability.list

    @property
    def attributes(self) -> dict[str, Any] | None:
        """Return the attributes of the device."""
        properties, attributes, customized = self._build_property_list()

        for prop in properties:
            value = self._get_property(prop)
            if value is not None:
                name_entry = PROPERTY_TO_NAME.get(prop.name)
                prop_name = name_entry[0] if name_entry else prop.name.lower()

                value, extra = self._format_property_value(prop, value, prop_name, customized)
                if value is None:
                    continue
                attributes[prop_name] = value
                if extra:
                    attributes.update(extra)

        self._add_state_attributes(attributes)
        return attributes

    def consumable_life_warning_description(self, consumable_property: Any) -> list[str] | None:
        description = CONSUMABLE_TO_LIFE_WARNING_DESCRIPTION.get(consumable_property)
        if description:
            value = self._get_property(consumable_property)
            if value is not None and value >= 0 and value <= 5:
                if value != 0 and len(description) > 1:
                    return description[1]
                return description[0]
        return None
