"""Enum + ``*_name`` accessor pairs for DreameVacuumDeviceStatus.

Wraps the raw enum-valued properties reported by the device (suction
level, status, water tank, charging status, ...) into their typed enum
counterparts, with a matching ``*_name`` accessor for translation
lookups. Extracted from the monolithic ``_core.py`` module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from ..const import (
    AUTO_EMPTY_MODE_TO_NAME,
    AUTO_EMPTY_STATUS_TO_NAME,
    CARPET_CLEANING_CODE_TO_NAME,
    CARPET_SENSITIVITY_CODE_TO_NAME,
    CHARGING_STATUS_CODE_TO_NAME,
    CLEANGENIUS_MODE_TO_NAME,
    CLEANGENIUS_TO_NAME,
    CLEANING_MODE_CODE_TO_NAME,
    CLEANING_ROUTE_TO_NAME,
    CUSTOM_MOPPING_ROUTE_TO_NAME,
    DRAINAGE_STATUS_TO_NAME,
    DUST_COLLECTION_TO_NAME,
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
    RELOCATION_STATUS_CODE_TO_NAME,
    SECOND_CLEANING_TO_NAME,
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
from ..vacuum_types import (
    DreameVacuumAutoEmptyMode,
    DreameVacuumAutoEmptyStatus,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumCarpetCleaning,
    DreameVacuumCarpetSensitivity,
    DreameVacuumChargingStatus,
    DreameVacuumCleanGenius,
    DreameVacuumCleanGeniusMode,
    DreameVacuumCleaningRoute,
    DreameVacuumCustomMoppingRoute,
    DreameVacuumDrainageStatus,
    DreameVacuumDustCollection,
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
    DreameVacuumSuctionLevel,
    DreameVacuumTaskStatus,
    DreameVacuumTaskType,
    DreameVacuumVoiceAssistantLanguage,
    DreameVacuumWashingMode,
    DreameVacuumWaterTank,
    DreameVacuumWaterTemperature,
    DreameVacuumWaterVolume,
    DreameVacuumWiderCornerCoverage,
)


class _NamedPropsMixin:
    """Typed enum accessors and their ``*_name`` translation-lookup counterparts."""

    if TYPE_CHECKING:
        # Provided by DreameVacuumDeviceStatus (_core) and its other mixins.
        def _get_property(self, prop: Any) -> Any: ...
        def consumable_life_warning_description(self, consumable_property: Any) -> list[str] | None: ...

        _capability: Any
        _device: Any
        mop_pad_humidity: int
        go_to_zone: Any
        self_clean_value: int | None
        battery_level: int
        cleaning_mode: Any
        stream_status: Any

        charging: bool
        paused: bool
        started: bool
        cleaning_paused: bool
        fast_mapping_paused: bool
        docked: bool
        washing: bool
        washing_paused: bool
        drying: bool
        mop_in_station: bool
        current_map: Any
        has_saved_map: bool
        carpet_recognition: bool
        auto_mount_mop: bool
        custom_mopping_mode: bool
        ultra_clean_mode: bool

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
