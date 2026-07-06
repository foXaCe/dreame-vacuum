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
    AUTO_EMPTY_STATUS_TO_NAME,
    CARPET_CLEANING_CODE_TO_NAME,
    CARPET_SENSITIVITY_CODE_TO_NAME,
    CHARGING_STATUS_CODE_TO_NAME,
    CLEANGENIUS_MODE_TO_NAME,
    CLEANGENIUS_TO_NAME,
    CLEANING_MODE_CODE_TO_NAME,
    CLEANING_ROUTE_TO_NAME,
    CONSUMABLE_TO_LIFE_WARNING_DESCRIPTION,
    CUSTOM_MOPPING_ROUTE_TO_NAME,
    DRAINAGE_STATUS_TO_NAME,
    DUST_COLLECTION_TO_NAME,
    ERROR_CODE_TO_ERROR_DESCRIPTION,
    ERROR_CODE_TO_ERROR_NAME,
    ERROR_CODE_TO_IMAGE_INDEX,
    FLOOR_MATERIAL_CODE_TO_NAME,
    FLOOR_MATERIAL_DIRECTION_CODE_TO_NAME,
    LOW_WATER_WARNING_CODE_TO_DESCRIPTION,
    LOW_WATER_WARNING_TO_NAME,
    MAP_BACKUP_STATUS_TO_NAME,
    MAP_RECOVERY_STATUS_TO_NAME,
    MOP_CLEAN_FREQUENCY_TO_NAME,
    MOP_EXTEND_FREQUENCY_TO_NAME,
    MOP_PAD_HUMIDITY_CODE_TO_NAME,
    MOP_PAD_SWING_TO_NAME,
    MOP_WASH_LEVEL_TO_NAME,
    MOPPING_TYPE_TO_NAME,
    PROPERTY_TO_NAME,
    RELOCATION_STATUS_CODE_TO_NAME,
    SECOND_CLEANING_TO_NAME,
    SEGMENT_VISIBILITY_CODE_TO_NAME,
    SELF_CLEAN_FREQUENCY_TO_NAME,
    SELF_WASH_BASE_STATUS_TO_NAME,
    STATE_CODE_TO_STATE,
    STATE_UNKNOWN,
    STATION_DRAINAGE_STATUS_TO_NAME,
    STATUS_CODE_TO_NAME,
    STREAM_STATUS_TO_NAME,
    SUCTION_LEVEL_CODE_TO_NAME,
    TASK_STATUS_CODE_TO_NAME,
    TASK_TYPE_TO_NAME,
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
    DreameVacuumAutoEmptyMode,
    DreameVacuumAutoEmptyStatus,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumCarpetCleaning,
    DreameVacuumCarpetSensitivity,
    DreameVacuumChargingStatus,
    DreameVacuumCleanGenius,
    DreameVacuumCleanGeniusMode,
    DreameVacuumCleaningMode,
    DreameVacuumCleaningRoute,
    DreameVacuumCustomMoppingRoute,
    DreameVacuumDeviceCapability,
    DreameVacuumDrainageStatus,
    DreameVacuumDustCollection,
    DreameVacuumErrorCode,
    DreameVacuumLowWaterWarning,
    DreameVacuumMopCleanFrequency,
    DreameVacuumMopExtendFrequency,
    DreameVacuumMopPadHumidity,
    DreameVacuumMopPadSwing,
    DreameVacuumMoppingType,
    DreameVacuumMopWashLevel,
    DreameVacuumProperty,
    DreameVacuumRelocationStatus,
    DreameVacuumSecondCleaning,
    DreameVacuumSelfCleanFrequency,
    DreameVacuumSelfWashBaseStatus,
    DreameVacuumState,
    DreameVacuumStateOld,
    DreameVacuumStationDrainageStatus,
    DreameVacuumStatus,
    DreameVacuumStreamStatus,
    DreameVacuumSuctionLevel,
    DreameVacuumTaskStatus,
    DreameVacuumTaskType,
    DreameVacuumVoiceAssistantLanguage,
    DreameVacuumWashingMode,
    DreameVacuumWaterTank,
    DreameVacuumWaterTemperature,
    DreameVacuumWaterVolume,
    DreameVacuumWiderCornerCoverage,
    GoToZoneSettings,
    MapData,
    Segment,
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


from ._consumables import _ConsumablesMixin
from ._station import _StationMixin


class DreameVacuumDeviceStatus(_ConsumablesMixin, _StationMixin):
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
    def suction_level(self) -> DreameVacuumSuctionLevel:
        """Return suction level of the device."""
        value = self._get_property(DreameVacuumProperty.SUCTION_LEVEL)
        if value is not None and value in DreameVacuumSuctionLevel._value2member_map_:
            return DreameVacuumSuctionLevel(value)
        return DreameVacuumSuctionLevel.UNKNOWN

    @property
    def suction_level_name(self) -> str:
        """Return suction level as string for translation."""
        return SUCTION_LEVEL_CODE_TO_NAME.get(self.suction_level, STATE_UNKNOWN)

    @property
    def water_volume(self) -> DreameVacuumWaterVolume:
        """Return water volume of the device."""
        if self._capability.self_wash_base:
            if self.mop_pad_humidity is None:
                if self._capability.wetness_level:
                    wetness_level = self.status.wetness_level
                    if wetness_level > 32:
                        if wetness_level > 200:
                            return DreameVacuumMopPadHumidity.WET
                        if wetness_level < 200:
                            return DreameVacuumMopPadHumidity.SLIGHTLY_DRY
                    else:
                        if wetness_level > (14 if self._capability.mop_clean_frequency else 26):
                            return DreameVacuumMopPadHumidity.WET
                        if wetness_level < 6:
                            return DreameVacuumMopPadHumidity.SLIGHTLY_DRY
                    return DreameVacuumMopPadHumidity.MOIST
                return DreameVacuumMopPadHumidity.UNKNOWN
            return cast(DreameVacuumWaterVolume, DreameVacuumMopPadHumidity(self.mop_pad_humidity))

        value = self._get_property(DreameVacuumProperty.WATER_VOLUME)
        if value is not None and value in DreameVacuumWaterVolume._value2member_map_:
            return DreameVacuumWaterVolume(value)
        return DreameVacuumWaterVolume.UNKNOWN

    @property
    def water_volume_name(self) -> str:
        """Return water volume as string for translation."""
        return WATER_VOLUME_CODE_TO_NAME.get(self.water_volume, STATE_UNKNOWN)

    @property
    def mop_pad_humidity_name(self) -> str:
        """Return mop pad humidity as string for translation."""
        return MOP_PAD_HUMIDITY_CODE_TO_NAME.get(DreameVacuumMopPadHumidity(self.mop_pad_humidity), STATE_UNKNOWN)

    @property
    def cleaning_mode_name(self) -> str:
        """Return cleaning mode as string for translation."""
        mode = self.cleaning_mode
        if mode is None:
            return STATE_UNKNOWN
        return CLEANING_MODE_CODE_TO_NAME.get(mode, STATE_UNKNOWN)

    @property
    def wetness_level(self) -> int:
        """Return wetness level of the device."""
        return cast(int, self._get_property(DreameVacuumProperty.WETNESS_LEVEL))

    @property
    def status(self) -> DreameVacuumStatus:
        """Return status of the device."""
        value = self._get_property(DreameVacuumProperty.STATUS)
        if value is not None and value in DreameVacuumStatus._value2member_map_:
            if self.go_to_zone and value == DreameVacuumStatus.ZONE_CLEANING.value:
                return DreameVacuumStatus.CRUISING_POINT
            if value == DreameVacuumStatus.CHARGING.value and not self.charging:
                return DreameVacuumStatus.IDLE
            return DreameVacuumStatus(value)
        return DreameVacuumStatus.UNKNOWN

    @property
    def status_name(self) -> str:
        """Return status as string for translation."""
        return STATUS_CODE_TO_NAME.get(self.status, STATE_UNKNOWN)

    @property
    def task_status(self) -> DreameVacuumTaskStatus:
        """Return task status of the device."""
        value = self._get_property(DreameVacuumProperty.TASK_STATUS)
        if value is not None and value in DreameVacuumTaskStatus._value2member_map_:
            if self.go_to_zone:
                if value == DreameVacuumTaskStatus.ZONE_CLEANING.value:
                    return DreameVacuumTaskStatus.CRUISING_POINT
                if value == DreameVacuumTaskStatus.ZONE_CLEANING_PAUSED.value:
                    return DreameVacuumTaskStatus.CRUISING_POINT_PAUSED
            return DreameVacuumTaskStatus(value)
        return DreameVacuumTaskStatus.UNKNOWN

    @property
    def task_status_name(self) -> str:
        """Return task status as string for translation."""
        return TASK_STATUS_CODE_TO_NAME.get(self.task_status, STATE_UNKNOWN)

    @property
    def water_tank(self) -> DreameVacuumWaterTank:
        """Return water tank of the device."""
        value = self._get_property(DreameVacuumProperty.WATER_TANK)
        if value is not None:
            if value == 3:
                return DreameVacuumWaterTank.INSTALLED
            if self.mop_in_station:
                return DreameVacuumWaterTank.MOP_IN_STATION
            if value == 2:
                return DreameVacuumWaterTank.MOP_INSTALLED

            if value in DreameVacuumWaterTank._value2member_map_:
                return DreameVacuumWaterTank(value)
        return DreameVacuumWaterTank.UNKNOWN

    @property
    def water_tank_name(self) -> str:
        """Return water tank as string for translation."""
        return WATER_TANK_CODE_TO_NAME.get(self.water_tank, STATE_UNKNOWN)

    @property
    def mop_pad_name(self) -> str:
        """Return mop pad as string for translation."""
        return self.water_tank_name

    @property
    def charging_status(self) -> DreameVacuumChargingStatus:
        """Return charging status of the device."""
        value = self._get_property(DreameVacuumProperty.CHARGING_STATUS)
        if value is not None and value in DreameVacuumChargingStatus._value2member_map_:
            value = DreameVacuumChargingStatus(value)
            # Charging status complete is not present on older firmwares
            if value is DreameVacuumChargingStatus.CHARGING and self.battery_level == 100:
                return DreameVacuumChargingStatus.CHARGING_COMPLETED
            return value
        return DreameVacuumChargingStatus.UNKNOWN

    @property
    def charging_status_name(self) -> str:
        """Return charging status as string for translation."""
        return CHARGING_STATUS_CODE_TO_NAME.get(self.charging_status, STATE_UNKNOWN)

    @property
    def auto_empty_status(self) -> DreameVacuumAutoEmptyStatus:
        """Return auto empty status of the device."""
        value = self._get_property(DreameVacuumProperty.AUTO_EMPTY_STATUS)
        if value is not None and value in DreameVacuumAutoEmptyStatus._value2member_map_:
            return DreameVacuumAutoEmptyStatus(value)
        return DreameVacuumAutoEmptyStatus.UNKNOWN

    @property
    def auto_empty_status_name(self) -> str:
        """Return auto empty status as string for translation."""
        return AUTO_EMPTY_STATUS_TO_NAME.get(self.auto_empty_status, STATE_UNKNOWN)

    @property
    def relocation_status(self) -> DreameVacuumRelocationStatus:
        """Return relocation status of the device."""
        value = self._get_property(DreameVacuumProperty.RELOCATION_STATUS)
        if value is not None and value in DreameVacuumRelocationStatus._value2member_map_:
            return DreameVacuumRelocationStatus(value)
        return DreameVacuumRelocationStatus.UNKNOWN

    @property
    def relocation_status_name(self) -> str:
        """Return relocation status as string for translation."""
        return RELOCATION_STATUS_CODE_TO_NAME.get(self.relocation_status, STATE_UNKNOWN)

    @property
    def self_wash_base_status(self) -> DreameVacuumSelfWashBaseStatus:
        """Return self-wash base status of the device."""
        value = self._get_property(DreameVacuumProperty.SELF_WASH_BASE_STATUS)
        if value is not None and value in DreameVacuumSelfWashBaseStatus._value2member_map_:
            return DreameVacuumSelfWashBaseStatus(value)
        return DreameVacuumSelfWashBaseStatus.UNKNOWN

    @property
    def self_wash_base_status_name(self) -> str:
        """Return self-wash base status as string for translation."""
        return SELF_WASH_BASE_STATUS_TO_NAME.get(self.self_wash_base_status, STATE_UNKNOWN)

    @property
    def dust_collection(self) -> DreameVacuumDustCollection:
        value = self._get_property(DreameVacuumProperty.DUST_COLLECTION)
        if value is not None and value in DreameVacuumDustCollection._value2member_map_:
            return DreameVacuumDustCollection(value)
        return DreameVacuumDustCollection.UNKNOWN

    @property
    def dust_collection_name(self) -> str:
        """Return dust collection as string for translation."""
        return DUST_COLLECTION_TO_NAME.get(self.dust_collection, STATE_UNKNOWN)

    @property
    def carpet_sensitivity(self) -> DreameVacuumCarpetSensitivity:
        """Return carpet sensitivity of the device."""
        value = self._get_property(DreameVacuumProperty.CARPET_SENSITIVITY)
        if value is not None and value in DreameVacuumCarpetSensitivity._value2member_map_:
            return DreameVacuumCarpetSensitivity(value)
        return DreameVacuumCarpetSensitivity.UNKNOWN

    @property
    def carpet_sensitivity_name(self) -> str:
        """Return carpet sensitivity as string for translation."""
        return CARPET_SENSITIVITY_CODE_TO_NAME.get(self.carpet_sensitivity, STATE_UNKNOWN)

    @property
    def carpet_cleaning(self) -> DreameVacuumCarpetCleaning:
        """Return carpet cleaning of the device."""
        value = self._get_property(DreameVacuumProperty.CARPET_CLEANING)

        if (
            not self.carpet_recognition
            and self._capability.mop_pad_lifting_plus
            and self._capability.auto_carpet_cleaning
        ):
            return DreameVacuumCarpetCleaning.IGNORE
        if value == 6 or (value == 3 and self._capability.mop_pad_unmounting and not self.auto_mount_mop):
            return DreameVacuumCarpetCleaning.ADAPTATION

        if value is not None and value in DreameVacuumCarpetCleaning._value2member_map_:
            return DreameVacuumCarpetCleaning(value)
        return DreameVacuumCarpetCleaning.UNKNOWN

    @property
    def carpet_cleaning_name(self) -> str:
        """Return carpet cleaning as string for translation."""
        return CARPET_CLEANING_CODE_TO_NAME.get(self.carpet_cleaning, STATE_UNKNOWN)

    @property
    def state(self) -> DreameVacuumState:
        """Return state of the device."""
        value = self._get_property(DreameVacuumProperty.STATE)
        if (
            value is not None
            and int(value) > 18
            and not self._capability.new_state
            and value in DreameVacuumStateOld._value2member_map_
        ):
            value = DreameVacuumState[DreameVacuumStateOld(value).name].value

        if value is not None and value in DreameVacuumState._value2member_map_:
            if self.go_to_zone and (
                value == DreameVacuumState.IDLE
                or value == DreameVacuumState.SWEEPING.value
                or value == DreameVacuumState.MOPPING.value
                or value == DreameVacuumState.SWEEPING_AND_MOPPING.value
            ):
                if self.paused:
                    return DreameVacuumState.MONITORING_PAUSED
                return DreameVacuumState.MONITORING
            vacuum_state = DreameVacuumState(value)

            ## Determine state as implemented on the app
            if vacuum_state is DreameVacuumState.IDLE:
                if self.started or self.cleaning_paused or self.fast_mapping_paused:
                    return DreameVacuumState.PAUSED
                if self.docked:
                    if self.washing:
                        return DreameVacuumState.WASHING
                    if self.washing_paused:
                        return DreameVacuumState.WASHING_PAUSED
                    if self.drying:
                        return DreameVacuumState.DRYING
                    if self.charging:
                        return DreameVacuumState.CHARGING
                    ## This is for compatibility with various lovelace vacuum cards
                    ## Device will report idle when charging is completed and vacuum card will display return to dock icon even when robot is docked
                    if self.charging_status is DreameVacuumChargingStatus.CHARGING_COMPLETED:
                        return DreameVacuumState.CHARGING_COMPLETED
            return vacuum_state

        return DreameVacuumState.UNKNOWN

    @property
    def state_name(self) -> str:
        """Return state as string for translation."""
        return STATE_CODE_TO_STATE.get(self.state, STATE_UNKNOWN)

    @property
    def mop_wash_level(self) -> DreameVacuumMopWashLevel:
        """Return mop wash level of the device."""
        if self._capability.self_wash_base:
            value = self._get_property(DreameVacuumProperty.MOP_WASH_LEVEL)
            if value is not None and value in DreameVacuumMopWashLevel._value2member_map_:
                return DreameVacuumMopWashLevel(value)
        return DreameVacuumMopWashLevel.UNKNOWN

    @property
    def mop_wash_level_name(self) -> str:
        """Return mop wash level as string for translation."""
        return MOP_WASH_LEVEL_TO_NAME.get(self.mop_wash_level, STATE_UNKNOWN)

    @property
    def mop_clean_frequency(self) -> DreameVacuumMopCleanFrequency:
        """Return mop clean frequency of the device."""
        if self._capability.self_wash_base and self._capability.mop_clean_frequency:
            value = self.self_clean_value
            if value == 0:
                return DreameVacuumMopCleanFrequency.BY_ROOM
            if value is not None and value in DreameVacuumMopCleanFrequency._value2member_map_:
                return DreameVacuumMopCleanFrequency(value)
        return DreameVacuumMopCleanFrequency.UNKNOWN

    @property
    def mop_clean_frequency_name(self) -> str:
        """Return mop clean frequency as string for translation."""
        return MOP_CLEAN_FREQUENCY_TO_NAME.get(self.mop_clean_frequency, STATE_UNKNOWN)

    @property
    def mopping_type(self) -> DreameVacuumMoppingType | None:
        value = self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.MOPPING_TYPE)
        if value is not None:
            if value in DreameVacuumMoppingType._value2member_map_:
                return DreameVacuumMoppingType(value)
            return DreameVacuumMoppingType.UNKNOWN
        return None

    @property
    def mopping_type_name(self) -> str:
        """Return moping type as string for translation."""
        if self.mopping_type is not None and self.mopping_type in DreameVacuumMoppingType._value2member_map_:
            return MOPPING_TYPE_TO_NAME.get(DreameVacuumMoppingType(self.mopping_type), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def stream_status_name(self) -> str:
        """Return camera stream status as string for translation."""
        status = self.stream_status
        if status is None:
            return STATE_UNKNOWN
        return STREAM_STATUS_TO_NAME.get(status, STATE_UNKNOWN)

    @property
    def wider_corner_coverage(self) -> DreameVacuumWiderCornerCoverage:
        value = self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.WIDER_CORNER_COVERAGE)
        if value is not None and value < 0:
            value = 0
        if value is not None and value in DreameVacuumWiderCornerCoverage._value2member_map_:
            return DreameVacuumWiderCornerCoverage(value)
        return DreameVacuumWiderCornerCoverage.UNKNOWN

    @property
    def wider_corner_coverage_name(self) -> str:
        """Return wider corner coverage as string for translation."""
        wider_corner_coverage = 0 if self.wider_corner_coverage < 0 else self.wider_corner_coverage
        if (
            wider_corner_coverage is not None
            and wider_corner_coverage in DreameVacuumWiderCornerCoverage._value2member_map_
        ):
            return WIDER_CORNER_COVERAGE_TO_NAME.get(
                DreameVacuumWiderCornerCoverage(wider_corner_coverage), STATE_UNKNOWN
            )
        return STATE_UNKNOWN

    @property
    def mop_pad_swing(self) -> DreameVacuumMopPadSwing:
        if self._capability.mop_pad_swing:
            value = self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.MOP_PAD_SWING)
            if value is not None and value < 0:
                value = 0
            if value is not None and value in DreameVacuumMopPadSwing._value2member_map_:
                return DreameVacuumMopPadSwing(value)
        return DreameVacuumMopPadSwing.UNKNOWN

    @property
    def mop_pad_swing_name(self) -> str:
        """Return mop pad swing as string for translation."""
        mop_pad_swing = 0 if self.mop_pad_swing < 0 else self.mop_pad_swing
        if mop_pad_swing is not None and mop_pad_swing in DreameVacuumMopPadSwing._value2member_map_:
            return MOP_PAD_SWING_TO_NAME.get(DreameVacuumMopPadSwing(mop_pad_swing), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def mop_extend_frequency(self) -> DreameVacuumMopExtendFrequency:
        if self._capability.mop_extend:
            value = self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.MOP_EXTEND_FREQUENCY)
            if value is not None and value < 0:
                value = 0
            if value is not None and value in DreameVacuumMopExtendFrequency._value2member_map_:
                return DreameVacuumMopExtendFrequency(value)
        return DreameVacuumMopExtendFrequency.UNKNOWN

    @property
    def mop_extend_frequency_name(self) -> str:
        """Return mop pad swing as string for translation."""
        mop_extend_frequency = 0 if self.mop_extend_frequency < 0 else self.mop_extend_frequency
        if (
            mop_extend_frequency is not None
            and mop_extend_frequency in DreameVacuumMopExtendFrequency._value2member_map_
        ):
            return MOP_EXTEND_FREQUENCY_TO_NAME.get(DreameVacuumMopExtendFrequency(mop_extend_frequency), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def auto_recleaning(self) -> DreameVacuumSecondCleaning:
        if self._capability.auto_recleaning:
            value = self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.AUTO_RECLEANING)
            if value is not None and value < 0:
                value = 0
            if value is not None and value in DreameVacuumSecondCleaning._value2member_map_:
                return DreameVacuumSecondCleaning(value)
        return DreameVacuumSecondCleaning.UNKNOWN

    @property
    def auto_recleaning_name(self) -> str:
        """Return mop pad swing as string for translation."""
        auto_recleaning = 0 if self.auto_recleaning < 0 else self.auto_recleaning
        if auto_recleaning is not None and auto_recleaning in DreameVacuumSecondCleaning._value2member_map_:
            return SECOND_CLEANING_TO_NAME.get(DreameVacuumSecondCleaning(auto_recleaning), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def auto_rewashing(self) -> DreameVacuumSecondCleaning:
        if self._capability.auto_rewashing:
            value = self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.AUTO_REWASHING)
            if value is not None and value < 0:
                value = 0
            if value is not None and value in DreameVacuumSecondCleaning._value2member_map_:
                return DreameVacuumSecondCleaning(value)
        return DreameVacuumSecondCleaning.UNKNOWN

    @property
    def auto_rewashing_name(self) -> str:
        """Return mop pad swing as string for translation."""
        auto_rewashing = 0 if self.auto_rewashing < 0 else self.auto_rewashing
        if auto_rewashing is not None and auto_rewashing in DreameVacuumSecondCleaning._value2member_map_:
            return SECOND_CLEANING_TO_NAME.get(DreameVacuumSecondCleaning(auto_rewashing), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def cleaning_route(self) -> DreameVacuumCleaningRoute:
        if self._capability.cleaning_route:
            value = self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.CLEANING_ROUTE)
            if value is not None and value < 0:
                value = 0
            if value is not None and value in DreameVacuumCleaningRoute._value2member_map_:
                return DreameVacuumCleaningRoute(value)
        return DreameVacuumCleaningRoute.UNKNOWN

    @property
    def cleaning_route_name(self) -> str:
        """Return cleaning route as string for translation."""
        cleaning_route = 0 if self.cleaning_route < 0 else self.cleaning_route
        if cleaning_route is not None and cleaning_route in DreameVacuumCleaningRoute._value2member_map_:
            return CLEANING_ROUTE_TO_NAME.get(DreameVacuumCleaningRoute(cleaning_route), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def custom_mopping_route(self) -> DreameVacuumCustomMoppingRoute:
        if self._capability.custom_mopping_route:
            value = self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.MOPPING_TYPE)
            if value is not None and value < 0:
                value = 0
            if value is not None and value in DreameVacuumCustomMoppingRoute._value2member_map_:
                if not self.custom_mopping_mode:
                    return DreameVacuumCustomMoppingRoute.OFF
                return DreameVacuumCustomMoppingRoute(value)
        return DreameVacuumCustomMoppingRoute.UNKNOWN

    @property
    def custom_mopping_route_name(self) -> str:
        """Return mopping route as string for translation."""
        mopping_route = -2 if self.custom_mopping_route < -2 else self.custom_mopping_route
        if mopping_route is not None and mopping_route in DreameVacuumCustomMoppingRoute._value2member_map_:
            return CUSTOM_MOPPING_ROUTE_TO_NAME.get(DreameVacuumCustomMoppingRoute(mopping_route), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def cleangenius(self) -> DreameVacuumCleanGenius:
        if self._capability.cleangenius:
            value = self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS)
            if value is not None and value < 0:
                value = 0
            if value is not None and value in DreameVacuumCleanGenius._value2member_map_:
                return DreameVacuumCleanGenius(value)
        return DreameVacuumCleanGenius.UNKNOWN

    @property
    def cleangenius_name(self) -> str:
        """Return CleanGenius as string for translation."""
        cleangenius = 0 if not self.cleangenius or self.cleangenius < 0 else self.cleangenius
        if cleangenius is not None and cleangenius in DreameVacuumCleanGenius._value2member_map_:
            return CLEANGENIUS_TO_NAME.get(DreameVacuumCleanGenius(cleangenius), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def cleangenius_mode(self) -> DreameVacuumCleanGeniusMode:
        if self._capability.cleangenius_mode:
            value = self._device.get_property(DreameVacuumProperty.CLEANGENIUS_MODE)
            if value is not None and value < 0:
                value = 0
            if value is not None and value in DreameVacuumCleanGeniusMode._value2member_map_:
                return DreameVacuumCleanGeniusMode(value)
        return DreameVacuumCleanGeniusMode.UNKNOWN

    @property
    def cleangenius_mode_name(self) -> str:
        """Return Smart Clean Mode as string for translation."""
        cleangenius_mode = 2 if not self.cleangenius_mode or self.cleangenius_mode < 1 else self.cleangenius_mode
        if cleangenius_mode is not None and cleangenius_mode in DreameVacuumCleanGeniusMode._value2member_map_:
            return CLEANGENIUS_MODE_TO_NAME.get(DreameVacuumCleanGeniusMode(cleangenius_mode), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def water_temperature(self) -> DreameVacuumWaterTemperature:
        if self._capability.water_temperature:
            value = self._device.get_property(DreameVacuumProperty.WATER_TEMPERATURE)
            if value is not None and value < 0:
                value = 0
            if value is not None and value in DreameVacuumWaterTemperature._value2member_map_:
                return DreameVacuumWaterTemperature(value)
        return DreameVacuumWaterTemperature.UNKNOWN

    @property
    def water_temperature_name(self) -> str:
        """Return Water Temperature as string for translation."""
        water_temperature = self.water_temperature
        if water_temperature is not None and water_temperature in DreameVacuumWaterTemperature._value2member_map_:
            return WATER_TEMPERATURE_TO_NAME.get(DreameVacuumWaterTemperature(water_temperature), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def washing_mode(self) -> DreameVacuumWashingMode:
        if self._capability.cleangenius_mode:
            if self.ultra_clean_mode:
                return DreameVacuumWashingMode.ULTRA_WASHING
            value = self.mop_wash_level.value
            if value is not None and value < 0:
                value = 1
            if value is not None and value in DreameVacuumWashingMode._value2member_map_:
                return DreameVacuumWashingMode(value)
        return DreameVacuumWashingMode.UNKNOWN

    @property
    def washing_mode_name(self) -> str:
        """Return Washing Mode as string for translation."""
        washing_mode = self.washing_mode
        if washing_mode is not None and washing_mode in DreameVacuumWashingMode._value2member_map_:
            return WASHING_MODE_TO_NAME.get(DreameVacuumWashingMode(washing_mode), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def self_clean_frequency(self) -> DreameVacuumSelfCleanFrequency:
        if self._capability.self_clean_frequency:
            if not self.self_clean_value:
                return DreameVacuumSelfCleanFrequency.BY_ROOM
            value = self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.SELF_CLEAN_FREQUENCY)
            if value is not None and value < 0:
                value = 0
            if value is not None and value in DreameVacuumSelfCleanFrequency._value2member_map_:
                if value == DreameVacuumSelfCleanFrequency.BY_ROOM.value and (
                    self.current_map and not self.has_saved_map
                ):
                    return DreameVacuumSelfCleanFrequency.BY_AREA
                return DreameVacuumSelfCleanFrequency(value)
        return DreameVacuumSelfCleanFrequency.UNKNOWN

    @property
    def self_clean_frequency_name(self) -> str:
        """Return self clean frequency as string for translation."""
        self_clean_frequency = 0 if self.self_clean_frequency < 0 else self.self_clean_frequency
        if (
            self_clean_frequency is not None
            and self_clean_frequency in DreameVacuumSelfCleanFrequency._value2member_map_
        ):
            return SELF_CLEAN_FREQUENCY_TO_NAME.get(DreameVacuumSelfCleanFrequency(self_clean_frequency), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def auto_empty_mode(self) -> DreameVacuumAutoEmptyMode:
        if self._capability.auto_empty_mode:
            value = self._get_property(DreameVacuumProperty.AUTO_DUST_COLLECTING)
            if value is not None and value in DreameVacuumAutoEmptyMode._value2member_map_:
                return DreameVacuumAutoEmptyMode(value)
        return DreameVacuumAutoEmptyMode.UNKNOWN

    @property
    def auto_empty_mode_name(self) -> str:
        """Return auto empty mode as string for translation."""
        if self._capability.auto_empty_mode:
            auto_empty_mode = self._get_property(DreameVacuumProperty.AUTO_DUST_COLLECTING)
            if auto_empty_mode is not None and auto_empty_mode in DreameVacuumAutoEmptyMode._value2member_map_:
                return AUTO_EMPTY_MODE_TO_NAME.get(DreameVacuumAutoEmptyMode(auto_empty_mode), STATE_UNKNOWN)
        return STATE_UNKNOWN

    @property
    def low_water_warning(self) -> DreameVacuumLowWaterWarning:
        """Return low water warning of the device."""
        value = self._get_property(DreameVacuumProperty.LOW_WATER_WARNING)
        if value is not None and value in DreameVacuumLowWaterWarning._value2member_map_:
            return DreameVacuumLowWaterWarning(value)
        return DreameVacuumLowWaterWarning.UNKNOWN

    @property
    def low_water_warning_name(self) -> str:
        """Return low water warning as string for translation."""
        return LOW_WATER_WARNING_TO_NAME.get(self.low_water_warning, STATE_UNKNOWN)

    @property
    def low_water_warning_name_description(self) -> list[str]:
        """Return low water warning description of the device."""
        return LOW_WATER_WARNING_CODE_TO_DESCRIPTION.get(self.low_water_warning, [STATE_UNKNOWN, ""])

    @property
    def voice_assistant_language(self) -> DreameVacuumVoiceAssistantLanguage:
        """Return voice assistant language of the device."""
        value = self._get_property(DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE)
        if value is not None and value in DreameVacuumVoiceAssistantLanguage._value2member_map_:
            return DreameVacuumVoiceAssistantLanguage(value)
        return DreameVacuumVoiceAssistantLanguage.DEFAULT

    @property
    def voice_assistant_language_name(self) -> str:
        """Return voice assistant language as string for translation."""
        return VOICE_ASSISTANT_LANGUAGE_TO_NAME.get(self.voice_assistant_language, STATE_UNKNOWN)

    @property
    def drainage_status(self) -> DreameVacuumDrainageStatus:
        """Return drainage status of the device."""
        value = self._get_property(DreameVacuumProperty.DRAINAGE_STATUS)
        if value is not None and value in DreameVacuumDrainageStatus._value2member_map_:
            if self.state == DreameVacuumState.AUTO_WATER_DRAINING or self.state == DreameVacuumState.DRAINING:
                return DreameVacuumDrainageStatus.DRAINING
            return DreameVacuumDrainageStatus(value)
        return DreameVacuumDrainageStatus.UNKNOWN

    @property
    def drainage_status_name(self) -> str:
        """Return drainage status as string for translation."""
        return DRAINAGE_STATUS_TO_NAME.get(self.drainage_status, STATE_UNKNOWN)

    @property
    def task_type(self) -> DreameVacuumTaskType:
        """Return drainage status of the device."""
        value = self._get_property(DreameVacuumProperty.TASK_TYPE)
        if value is not None and value in DreameVacuumTaskType._value2member_map_:
            return DreameVacuumTaskType(value)
        return DreameVacuumTaskType.UNKNOWN

    @property
    def task_type_name(self) -> str:
        """Return drainage status as string for translation."""
        return TASK_TYPE_TO_NAME.get(self.task_type, STATE_UNKNOWN)

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
    def located(self) -> bool:
        """Returns true when robot knows its position on current map."""
        relocation_status = self.relocation_status
        return bool(
            relocation_status is DreameVacuumRelocationStatus.LOCATED
            or relocation_status is DreameVacuumRelocationStatus.UNKNOWN
            or self.fast_mapping
        )

    @property
    def sweeping(self) -> bool:
        """Returns true when cleaning mode is sweeping therefore cannot set its water volume."""
        cleaning_mode = self.cleaning_mode
        if cleaning_mode is None:
            return not self.water_tank_or_mop_installed
        return bool(
            cleaning_mode is not DreameVacuumCleaningMode.MOPPING
            and cleaning_mode is not DreameVacuumCleaningMode.SWEEPING_AND_MOPPING
            and cleaning_mode is not DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING
        )

    @property
    def mopping(self) -> bool:
        """Returns true when cleaning mode is mopping therefore cannot set its suction level."""
        return bool(self.cleaning_mode is DreameVacuumCleaningMode.MOPPING)

    @property
    def mopping_after_sweeping(self) -> bool:
        """Returns true when cleaning mode is mopping after sweeping therefore cannot change the cleaning mode when active."""
        return bool(self.cleaning_mode is DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING)

    @property
    def zone_cleaning(self) -> bool:
        """Returns true when device is currently performing a zone cleaning task."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and self.started
            and (
                task_status is DreameVacuumTaskStatus.ZONE_CLEANING
                or task_status is DreameVacuumTaskStatus.ZONE_CLEANING_PAUSED
                or task_status is DreameVacuumTaskStatus.ZONE_MOPPING_PAUSED
                or task_status is DreameVacuumTaskStatus.ZONE_DOCKING_PAUSED
            )
        )

    @property
    def spot_cleaning(self) -> bool:
        """Returns true when device is currently performing a spot cleaning task."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and self.started
            and (
                task_status is DreameVacuumTaskStatus.SPOT_CLEANING
                or task_status is DreameVacuumTaskStatus.SPOT_CLEANING_PAUSED
                or self.status is DreameVacuumStatus.SPOT_CLEANING
            )
        )

    @property
    def segment_cleaning(self) -> bool:
        """Returns true when device is currently performing a custom segment cleaning task."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and self.started
            and (
                task_status is DreameVacuumTaskStatus.SEGMENT_CLEANING
                or task_status is DreameVacuumTaskStatus.SEGMENT_CLEANING_PAUSED
                or task_status is DreameVacuumTaskStatus.SEGMENT_MOPPING_PAUSED
                or task_status is DreameVacuumTaskStatus.SEGMENT_DOCKING_PAUSED
            )
        )

    @property
    def auto_cleaning(self) -> bool:
        """Returns true when device is currently performing a complete map cleaning task."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and self.started
            and (
                task_status is DreameVacuumTaskStatus.AUTO_CLEANING
                or task_status is DreameVacuumTaskStatus.AUTO_CLEANING_PAUSED
                or task_status is DreameVacuumTaskStatus.AUTO_MOPPING_PAUSED
                or task_status is DreameVacuumTaskStatus.AUTO_DOCKING_PAUSED
            )
        )

    @property
    def fast_mapping(self) -> bool:
        """Returns true when device is creating a new map."""
        return bool(
            self._device_connected
            and (
                self.task_status is DreameVacuumTaskStatus.FAST_MAPPING
                or self.status is DreameVacuumStatus.FAST_MAPPING
                or self.fast_mapping_paused
            )
        )

    @property
    def fast_mapping_paused(self) -> bool:
        """Returns true when creating a new map paused by user.
        Used for resuming fast cleaning on start because standard start action can not be used for resuming fast mapping.
        """

        state = self._get_property(DreameVacuumProperty.STATE)
        task_status = self.task_status
        return bool(
            (
                task_status is DreameVacuumTaskStatus.FAST_MAPPING
                or task_status is DreameVacuumTaskStatus.MAP_CLEANING_PAUSED
            )
            and (
                state == DreameVacuumState.PAUSED.value
                or state == DreameVacuumState.ERROR.value
                or state == DreameVacuumState.IDLE.value
            )
        )

    @property
    def draining(self) -> bool:
        """Returns true when device has a self-wash base and draining is performing."""
        return bool(self._capability.drainage and self.drainage_status is DreameVacuumDrainageStatus.DRAINING)

    @property
    def draining_complete(self) -> bool:
        """Returns true when device has a self-wash base and draining is performing."""
        return bool(
            self._capability.drainage
            and (
                self.drainage_status is DreameVacuumDrainageStatus.DRAINING_FAILED
                or self.drainage_status is DreameVacuumDrainageStatus.DRAINING_SUCCESS
            )
        )

    @property
    def self_repairing(self) -> bool:
        """Returns true when device is self repairing/testing or water checking."""
        status = self.status
        return bool(
            status is DreameVacuumStatus.SELF_REPAIR
            or status is DreameVacuumStatus.WATER_CHECK
            or self.state is DreameVacuumState.WATER_CHECK
        )

    @property
    def station_cleaning(self) -> bool:
        """Returns true when base station is cleaning."""
        task_status = self.task_status
        return bool(task_status is DreameVacuumTaskStatus.STATION_CLEANING)

    @property
    def cruising(self) -> bool:
        """Returns true when device is cruising."""
        if self._capability.cruising:
            task_status = self.task_status
            status = self.status
            return bool(
                task_status is DreameVacuumTaskStatus.CRUISING_PATH
                or task_status is DreameVacuumTaskStatus.CRUISING_POINT
                or task_status is DreameVacuumTaskStatus.CRUISING_PATH_PAUSED
                or task_status is DreameVacuumTaskStatus.CRUISING_POINT_PAUSED
                or status is DreameVacuumStatus.CRUISING_PATH
                or status is DreameVacuumStatus.CRUISING_POINT
            )
        return bool(self.go_to_zone)

    @property
    def cruising_paused(self) -> bool:
        """Returns true when cruising paused."""
        if self._capability.cruising:
            task_status = self.task_status
            return bool(
                task_status is DreameVacuumTaskStatus.CRUISING_PATH_PAUSED
                or task_status is DreameVacuumTaskStatus.CRUISING_POINT_PAUSED
            )
        if self.go_to_zone:
            status = self.status
            if self.started and (
                status is DreameVacuumStatus.PAUSED
                or status is DreameVacuumStatus.SLEEPING
                or status is DreameVacuumStatus.IDLE
                or status is DreameVacuumStatus.STANDBY
            ):
                return True
        return False

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
    def resume_cleaning(self) -> bool:
        """Returns true when resume_cleaning is enabled."""
        return bool(
            self._get_property(DreameVacuumProperty.RESUME_CLEANING) == (2 if self._capability.auto_charging else 1)
        )

    @property
    def carpet_recognition(self) -> bool:
        """Returns true when carpet recognition is enabled."""
        return bool(
            self._capability.carpet_recognition and self._get_property(DreameVacuumProperty.CARPET_RECOGNITION) == 1
        )

    @property
    def mop_in_station(self) -> bool:
        """Returns true when the mop pad is in the station."""
        value = self._get_property(DreameVacuumProperty.MOP_IN_STATION)
        return bool(value == 1 or value == 4) and not self.docked

    @property
    def auto_add_detergent(self) -> bool:
        """Returns true when auto-add detergent feature is enabled."""
        value = self._get_property(DreameVacuumProperty.AUTO_ADD_DETERGENT)
        return bool(value == 1 or value == 3)

    @property
    def cleaning_paused(self) -> bool:
        """Returns true when device battery is too low for resuming its task and needs to be charged before continuing."""
        return bool(self._get_property(DreameVacuumProperty.CLEANING_PAUSED))

    @property
    def charging(self) -> bool:
        """Returns true when device is currently charging."""
        return bool(self.charging_status is DreameVacuumChargingStatus.CHARGING and self.battery_level < 100)

    @property
    def docked(self) -> bool:
        """Returns true when device is docked."""
        return bool(
            (
                self.charging
                or self.charging_status is DreameVacuumChargingStatus.CHARGING_COMPLETED
                or self.washing
                or self.drying
                or self.washing_paused
            )
            and not (self.running and not self.returning and not self.fast_mapping and not self.cruising)
        )

    @property
    def sleeping(self) -> bool:
        """Returns true when device is sleeping."""
        return bool(self.status is DreameVacuumStatus.SLEEPING)

    @property
    def returning_paused(self) -> bool:
        """Returns true when returning to dock is paused."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and not self.docked
            and (
                task_status is DreameVacuumTaskStatus.DOCKING_PAUSED
                or task_status is DreameVacuumTaskStatus.AUTO_DOCKING_PAUSED
                or task_status is DreameVacuumTaskStatus.SEGMENT_DOCKING_PAUSED
                or task_status is DreameVacuumTaskStatus.ZONE_DOCKING_PAUSED
            )
        )

    @property
    def returning(self) -> bool:
        """Returns true when returning to dock for charging or washing."""
        return bool(
            self._device_connected
            and (self.status is DreameVacuumStatus.BACK_HOME or self.returning_to_wash)
            and not self.docked
        )

    @property
    def started(self) -> bool:
        """Returns true when device has an active task.
        Used for preventing updates on settings that relates to currently performing task.
        """
        status = self.status
        return bool(
            (
                self.task_status is not DreameVacuumTaskStatus.COMPLETED
                and self.task_status is not DreameVacuumTaskStatus.DOCKING_PAUSED
            )
            or self.cleaning_paused
            or status is DreameVacuumStatus.CLEANING
            or status is DreameVacuumStatus.SEGMENT_CLEANING
            or status is DreameVacuumStatus.ZONE_CLEANING
            or status is DreameVacuumStatus.SPOT_CLEANING
            or status is DreameVacuumStatus.PART_CLEANING
            or status is DreameVacuumStatus.FAST_MAPPING
            or status is DreameVacuumStatus.CRUISING_PATH
            or status is DreameVacuumStatus.CRUISING_POINT
            or status is DreameVacuumStatus.SHORTCUT
        )

    @property
    def paused(self) -> bool:
        """Returns true when device has an active paused task."""
        status = self.status
        return bool(
            self.cleaning_paused
            or self.cruising_paused
            or (
                self.started
                and (
                    status is DreameVacuumStatus.PAUSED
                    or status is DreameVacuumStatus.SLEEPING
                    or status is DreameVacuumStatus.IDLE
                    or status is DreameVacuumStatus.STANDBY
                )
            )
        )

    @property
    def active(self) -> bool:
        """Returns true when device is moving or not sleeping."""
        return self.status is DreameVacuumStatus.STANDBY or self.running

    @property
    def running(self) -> bool:
        """Returns true when device is moving."""
        status = self.status
        return bool(
            not (
                self.charging
                or self.charging_status is DreameVacuumChargingStatus.CHARGING_COMPLETED
                or self.washing
                or self.drying
                or self.washing_paused
            )
            and (
                status is DreameVacuumStatus.CLEANING
                or status is DreameVacuumStatus.BACK_HOME
                or status is DreameVacuumStatus.PART_CLEANING
                or status is DreameVacuumStatus.FOLLOW_WALL
                or status is DreameVacuumStatus.REMOTE_CONTROL
                or status is DreameVacuumStatus.SEGMENT_CLEANING
                or status is DreameVacuumStatus.ZONE_CLEANING
                or status is DreameVacuumStatus.SPOT_CLEANING
                or status is DreameVacuumStatus.FAST_MAPPING
                or status is DreameVacuumStatus.CRUISING_PATH
                or status is DreameVacuumStatus.CRUISING_POINT
                or status is DreameVacuumStatus.SUMMON_CLEAN
                or status is DreameVacuumStatus.SHORTCUT
                or status is DreameVacuumStatus.PERSON_FOLLOW
            )
        )

    @property
    def shortcut_task(self) -> bool:
        """Returns true when device has an active shortcut task."""
        if self.started and self.shortcuts:
            for _k, v in self.shortcuts.items():
                if v.running:
                    return True
        return False

    @property
    def auto_emptying(self) -> bool:
        """Returns true when device is auto emptying."""
        return bool(self.auto_empty_status is DreameVacuumAutoEmptyStatus.ACTIVE)

    @property
    def auto_emptying_not_performed(self) -> bool:
        """Returns true when auto emptying is not performed due to DND settings."""
        return bool(self.auto_empty_status is DreameVacuumAutoEmptyStatus.NOT_PERFORMED)

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
    def multi_map(self) -> bool:
        """Returns true when multi floor map feature is enabled."""
        return bool(self._get_property(DreameVacuumProperty.MULTI_FLOOR_MAP))

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
    def washing(self) -> bool:
        """Returns true the when device is currently performing mop washing."""
        return bool(
            self._capability.self_wash_base
            and (
                self.self_wash_base_status is DreameVacuumSelfWashBaseStatus.WASHING
                or self.self_wash_base_status is DreameVacuumSelfWashBaseStatus.CLEAN_ADD_WATER
            )
        )

    @property
    def drying(self) -> bool:
        """Returns true the when device is currently performing mop drying."""
        return bool(
            self._capability.self_wash_base and self.self_wash_base_status is DreameVacuumSelfWashBaseStatus.DRYING
        )

    @property
    def washing_paused(self) -> bool:
        """Returns true when mop washing paused."""
        return bool(
            self._capability.self_wash_base and self.self_wash_base_status is DreameVacuumSelfWashBaseStatus.PAUSED
        )

    @property
    def returning_to_wash(self) -> bool:
        """Returns true when the device returning to self-wash base to wash or dry its mop."""
        return bool(
            self._capability.self_wash_base
            and self.self_wash_base_status is DreameVacuumSelfWashBaseStatus.RETURNING
            and (self.state is DreameVacuumState.RETURNING or self.state is DreameVacuumState.RETURNING_TO_WASH)
        )

    @property
    def returning_to_wash_paused(self) -> bool:
        """Returns true when the device returning to self-wash base to wash or dry its mop."""
        return bool(
            self._capability.self_wash_base
            and self.self_wash_base_status is DreameVacuumSelfWashBaseStatus.RETURNING
            and self.state is DreameVacuumState.PAUSED
        )

    @property
    def washing_available(self) -> bool:
        """Returns true when device has a self-wash base and washing mop can be performed."""
        return bool(
            self._capability.self_wash_base
            and (self.water_tank_or_mop_installed or self.mop_in_station)
            and not (
                self.washing
                or self.washing_paused
                or self.returning_to_wash_paused
                or self.returning_to_wash
                or self.returning
                or self.returning_paused
                or self.cleaning_paused
                # or self.drying
            )
        )

    @property
    def drying_available(self) -> bool:
        """Returns true when device has a self-wash base and drying mop can be performed."""
        return bool(
            self._capability.self_wash_base
            and self.water_tank_or_mop_installed
            and self.docked
            and not (self.washing or self.washing_paused)
            and not self.started
        )

    @property
    def maximum_maps(self) -> int:
        return (
            1 if not self._capability.lidar_navigation or not self.multi_map else 4 if self._capability.wifi_map else 3
        )

    @property
    def mapping_available(self) -> bool:
        """Returns true when creating a new map is possible."""
        return bool(
            not self.started
            and not self.fast_mapping
            and (not self._device.capability.map or self.maximum_maps > len(self.map_list or []))
        )

    @property
    def second_cleaning_available(self) -> bool:
        if self._capability.auto_recleaning and self._cleaning_history and self.current_map:
            history = self._cleaning_history[0]
            if history.object_name:
                map_data = self._history_map_data.get(history.object_name)
                return bool(
                    (map_data is not None and self.current_map.map_id == map_data.map_id)
                    and (
                        bool(history.neglected_segments)
                        or bool(
                            history.cleanup_method.value == 2
                            and not (history.mopping_mode != 2 and not self.mop_pad_installed)
                            and (history.second_mopping == 2 or map_data.cleaned_segments)
                            and map_data.cleaning_map_data is not None
                            and map_data.cleaning_map_data.has_dirty_area
                        )
                    )
                )
        return False

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
    def map_backup_status(self) -> int | None:
        value = self._get_property(DreameVacuumProperty.MAP_BACKUP_STATUS)
        if value == 1:
            return 2
        return cast("int | None", value)

    @property
    def map_backup_status_name(self) -> str:
        """Return map backup status as string for translation."""
        status = self.map_backup_status
        if status is None:
            return STATE_UNKNOWN
        backup_names: dict[Any, str] = MAP_BACKUP_STATUS_TO_NAME
        return backup_names.get(status, STATE_UNKNOWN)

    @property
    def map_recovery_status(self) -> int | None:
        value = self._get_property(DreameVacuumProperty.MAP_RECOVERY_STATUS)
        if value == 1:
            return 2
        return cast("int | None", value)

    @property
    def map_recovery_status_name(self) -> str:
        """Return map recovery status as string for translation."""
        status = self.map_recovery_status
        if status is None:
            return STATE_UNKNOWN
        recovery_names: dict[Any, str] = MAP_RECOVERY_STATUS_TO_NAME
        return recovery_names.get(status, STATE_UNKNOWN)

    @property
    def station_drainage_status(self) -> DreameVacuumStationDrainageStatus:
        """Return station drainage status of the device."""
        value = self._get_property(DreameVacuumProperty.STATION_DRAINAGE_STATUS)
        if value is not None and value in DreameVacuumStationDrainageStatus._value2member_map_:
            return DreameVacuumStationDrainageStatus(value)
        return DreameVacuumStationDrainageStatus.UNKNOWN

    @property
    def station_drainage_status_name(self) -> str:
        """Return station drainage status as string for translation."""
        return STATION_DRAINAGE_STATUS_TO_NAME.get(self.station_drainage_status, STATE_UNKNOWN)

    @property
    def custom_order(self) -> bool:
        """Returns true when custom cleaning sequence is set."""
        if self.cleangenius_cleaning and not self._capability.cleangenius_mode:
            return False
        segments = self.current_segments
        if segments:
            for v in segments.values():
                if v.order:
                    return True
        return False

    @property
    def segment_order(self) -> list[int] | None:
        """Returns cleaning order list."""
        segments = self.current_segments
        if segments:
            return (
                sorted(
                    segments,
                    key=lambda segment_id: segments[segment_id].order or 99,
                )
                if self.custom_order
                else None
            )
        return [] if self.custom_order else None

    @property
    def has_saved_map(self) -> bool:
        """Returns true when device has saved map and knowns its location on saved map."""
        if self._map_manager is None:
            return True

        current_map = self.current_map
        return bool(
            current_map is not None
            and current_map.saved_map_status == 2
            and not self.has_temporary_map
            and not self.has_new_map
            and not current_map.empty_map
        )

    @property
    def has_temporary_map(self) -> bool:
        """Returns true when device cannot store the newly created map and waits prompt for restoring or discarding it."""
        if self._map_manager is None:
            return False

        current_map = self.current_map
        return bool(current_map is not None and current_map.temporary_map and not current_map.empty_map)

    @property
    def has_new_map(self) -> bool:
        """Returns true when fast mapping from empty map."""
        if self._map_manager is None:
            return False

        current_map = self.current_map
        return bool(
            current_map is not None
            and not current_map.temporary_map
            and not current_map.empty_map
            and current_map.new_map
        )

    @property
    def selected_map(self) -> MapData | None:
        """Return the selected map data"""
        if self._map_manager and not self.has_temporary_map and not self.has_new_map:
            return self._map_manager.selected_map
        return None

    @property
    def current_map(self) -> MapData | None:
        """Return the current map data"""
        if self._map_manager:
            return self._map_manager.get_map()
        return None

    @property
    def map_list(self) -> list[int] | None:
        """Return the saved map id list if multi floor map is enabled"""
        if self._map_manager:
            if self.multi_map:
                return self._map_manager.map_list

            selected_map = self._map_manager.selected_map
            if selected_map and selected_map.map_id is not None:
                return [selected_map.map_id]
        return []

    @property
    def map_data_list(self) -> dict[int, MapData] | None:
        """Return the saved map data list if multi floor map is enabled"""
        if self._map_manager:
            if self.multi_map:
                return self._map_manager.map_data_list
            selected_map = self.selected_map
            if selected_map and selected_map.map_id is not None:
                return {selected_map.map_id: selected_map}
        return {}

    @property
    def current_segments(self) -> dict[int, Segment] | None:
        """Return the segments of current map"""
        current_map = self.current_map
        if current_map and current_map.segments and not current_map.empty_map:
            return current_map.segments
        return {}

    @property
    def segments(self) -> dict[int, Segment] | None:
        """Return the segments of selected map"""
        current_map = self.selected_map
        if current_map and current_map.segments and not current_map.empty_map:
            return current_map.segments
        return {}

    @property
    def current_room(self) -> Segment | None:
        """Return the segment that device is currently on"""
        if self._capability.lidar_navigation:
            current_map = self.current_map
            if current_map and current_map.segments and current_map.robot_segment and not current_map.empty_map:
                return current_map.segments[current_map.robot_segment]
        return None

    @property
    def cleaning_sequence(self) -> list[int] | None:
        """Returns custom segment cleaning sequence list."""
        if self._map_manager:
            return cast("list[int] | None", self._map_manager.cleaning_sequence)
        return None

    @property
    def previous_cleaning_sequence(self) -> Any:
        if self.current_map and self.current_map.map_id in self._previous_cleaning_sequence:
            return self._previous_cleaning_sequence[self.current_map.map_id]
        return None

    @property
    def active_segments(self) -> list[int] | None:
        map_data = self.current_map
        if map_data and self.started and not self.fast_mapping:
            if self.segment_cleaning:
                if map_data.active_segments:
                    return map_data.active_segments
            elif (
                not self.zone_cleaning
                and not self.spot_cleaning
                and map_data.segments
                and not self.docked
                and not self.returning
                and not self.returning_paused
            ):
                return list(map_data.segments.keys())
            return []
        return None

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

    def segment_order_list(self, segment: Any) -> Any:
        order: list[Any] = []
        if self.current_segments:
            order = [
                v.order
                for k, v in sorted(
                    self.current_segments.items(),
                    key=lambda s: s[1].order if s[1].order is not None else 0,
                )
                if v.order
            ]
            if not segment.order and len(order):
                order = order + [max(order) + 1]
        return list(map(str, order))
