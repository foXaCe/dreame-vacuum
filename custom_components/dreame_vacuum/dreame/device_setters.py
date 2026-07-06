"""Dreame Vacuum device setters mixin."""

from __future__ import annotations

from collections.abc import Callable
import json
import logging
import re
import time
from typing import Any, cast

from ._device_base import DreameVacuumDeviceState
from .const import (
    CARPET_CLEANING_CODE_TO_NAME,
)
from .exceptions import (
    DeviceException,
    DeviceUpdateFailedException,
    InvalidActionException,
    InvalidValueException,
)
from .vacuum_types import (
    ACTION_AVAILABILITY,
    PROPERTY_AVAILABILITY,
    DirtyData,
    DreameVacuumAction,
    DreameVacuumAIProperty,
    DreameVacuumAutoEmptyMode,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumCarpetCleaning,
    DreameVacuumCarpetSensitivity,
    DreameVacuumCleanGenius,
    DreameVacuumCleanGeniusMode,
    DreameVacuumCleaningMode,
    DreameVacuumCleaningRoute,
    DreameVacuumCustomMoppingRoute,
    DreameVacuumMopExtendFrequency,
    DreameVacuumMopPadHumidity,
    DreameVacuumMopPadSwing,
    DreameVacuumMoppingType,
    DreameVacuumMopWashLevel,
    DreameVacuumProperty,
    DreameVacuumSecondCleaning,
    DreameVacuumSelfCleanFrequency,
    DreameVacuumStatus,
    DreameVacuumStrAIProperty,
    DreameVacuumSuctionLevel,
    DreameVacuumTaskStatus,
    DreameVacuumVoiceAssistantLanguage,
    DreameVacuumWashingMode,
    DreameVacuumWaterTemperature,
    DreameVacuumWaterVolume,
    DreameVacuumWiderCornerCoverage,
    GoToZoneSettings,
)

_LOGGER = logging.getLogger(__name__)


class DreameVacuumDeviceSettersMixin(DreameVacuumDeviceState):
    """Mixin providing property getters, setters, and update helpers for DreameVacuumDevice."""

    def _update_cleaning_mode(self, cleaning_mode: int) -> bool:
        if self.capability.self_wash_base:
            values = self.split_group_value(
                self.get_property(DreameVacuumProperty.CLEANING_MODE),
                self.capability.mop_pad_lifting,
            )
            if not (values and len(values) == 3):
                return False

            if self.capability.mop_pad_lifting:
                if cleaning_mode == 2:
                    values[0] = 0
                elif cleaning_mode == 0:
                    values[0] = 2
                else:
                    values[0] = cleaning_mode
            elif cleaning_mode == 2:
                values[0] = 0
            cleaning_mode = self.combine_group_value(values)
        elif self.capability.mop_pad_lifting:
            if cleaning_mode == 2:
                cleaning_mode = 0
            elif cleaning_mode == 0:
                cleaning_mode = 2
        return self.set_property(DreameVacuumProperty.CLEANING_MODE, cleaning_mode)

    def _update_self_clean_value(self, self_clean_value: int) -> bool:
        if self.capability.self_wash_base:
            values = self.split_group_value(
                self.get_property(DreameVacuumProperty.CLEANING_MODE),
                self.capability.mop_pad_lifting,
            )
            if values and len(values) == 3:
                values[1] = self_clean_value
                return self.set_property(
                    DreameVacuumProperty.CLEANING_MODE,
                    self.combine_group_value(values),
                )
        return False

    def _update_water_level(self, water_level: int) -> bool:
        if (
            self.capability.mopping_settings
            and self.capability.self_wash_base
            and not self.capability.wetness_level
            and water_level == 3
            and (self.status.self_clean_value or 0) > 15
            and not self.status.self_clean_by_time
        ):
            self.set_self_clean_value(15)

        if self.capability.custom_mopping_route and not self.status.custom_mopping_mode:
            self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.MOPPING_MODE, water_level)

        if self.capability.wetness:
            wetness_level = 0
            if self.capability.custom_mopping_route and not self.status.custom_mopping_mode:
                if water_level == 1:
                    wetness_level = 100
                elif water_level == 3:
                    wetness_level = 400
                else:
                    wetness_level = 200
            elif self.capability.mop_clean_frequency:
                if water_level == 1:
                    wetness_level = 2
                elif water_level == 3:
                    wetness_level = 14
                else:
                    wetness_level = 8
            else:
                if water_level == 1:
                    wetness_level = 5
                elif water_level == 3:
                    wetness_level = 27
                else:
                    wetness_level = 16
            result = self.set_wetness_level(wetness_level)
            if self.capability.wetness_level:
                return result

        if not self.capability.self_wash_base:
            result = self.set_property(DreameVacuumProperty.WATER_VOLUME, int(water_level))
        else:
            values = self.split_group_value(
                self.get_property(DreameVacuumProperty.CLEANING_MODE),
                self.capability.mop_pad_lifting,
            )
            if values and len(values) == 3:
                if self.capability.wetness and not self.capability.wetness_level and values[2] == 0:
                    return result
                values[2] = water_level
                return self.set_property(
                    DreameVacuumProperty.CLEANING_MODE,
                    self.combine_group_value(values),
                )
            return False
        return result

    def _update_suction_level(self, suction_level: int) -> bool:
        return self.set_property(DreameVacuumProperty.SUCTION_LEVEL, int(suction_level))

    def _set_go_to_zone(self, x: int, y: int, size: int) -> None:
        current_cleaning_mode: int | None = int(self.status.cleaning_mode.value) if self.status.cleaning_mode else 0
        current_suction_level: int | None = int(self.status.suction_level.value)
        current_water_level: int | None = int(
            self.status.mop_pad_humidity if self.capability.self_wash_base else self.status.water_volume.value
        )

        new_cleaning_mode: int | None = None
        new_suction_level: int | None = None
        new_water_level: int | None = None

        if self.capability.self_wash_base or self.capability.mop_pad_lifting:
            if current_cleaning_mode != DreameVacuumCleaningMode.SWEEPING.value:
                new_cleaning_mode = DreameVacuumCleaningMode.SWEEPING.value
            else:
                current_cleaning_mode = None

            if current_suction_level != DreameVacuumSuctionLevel.QUIET.value:
                new_suction_level = DreameVacuumSuctionLevel.QUIET.value
            else:
                current_suction_level = None

            current_water_level = None
        else:
            cleaning_mode = DreameVacuumCleaningMode.MOPPING.value
            if self.status.water_tank_or_mop_installed:
                if self.status.current_map and self.status.current_map.no_mopping_areas:
                    for area in self.status.current_map.no_mopping_areas:
                        if area.check_point(x, y, size):
                            cleaning_mode = DreameVacuumCleaningMode.SWEEPING.value
                            break

            if current_cleaning_mode != cleaning_mode:
                new_cleaning_mode = cleaning_mode
            else:
                if (
                    current_cleaning_mode == DreameVacuumCleaningMode.MOPPING.value
                    and not self.status.water_tank_or_mop_installed
                ):
                    current_cleaning_mode = DreameVacuumCleaningMode.SWEEPING.value
                elif (
                    current_cleaning_mode == DreameVacuumCleaningMode.SWEEPING.value
                    and self.status.water_tank_or_mop_installed
                ):
                    current_cleaning_mode = DreameVacuumCleaningMode.SWEEPING_AND_MOPPING.value
                else:
                    current_cleaning_mode = None

            if current_water_level != DreameVacuumWaterVolume.LOW.value:
                new_water_level = DreameVacuumWaterVolume.LOW.value
            else:
                current_water_level = None

            current_suction_level = None

        try:
            if new_suction_level is not None:
                self._update_suction_level(new_suction_level)

            if new_water_level is not None:
                self._update_water_level(new_water_level)

            if new_cleaning_mode is not None:
                self._update_cleaning_mode(new_cleaning_mode)
        except (AttributeError, KeyError, ValueError, TypeError):
            _LOGGER.debug("go_to_zone: failed to snapshot cleaning state", exc_info=True)

        self.status.go_to_zone = GoToZoneSettings(
            x=x,
            y=y,
            stop=True,
            suction_level=current_suction_level,
            water_level=current_water_level,
            cleaning_mode=current_cleaning_mode,
            size=size,
        )

    def _restore_go_to_zone(self, stop: bool = False) -> None:
        if self.status.go_to_zone is not None:
            if self.status.go_to_zone:
                stop = stop and self.status.go_to_zone.stop
                suction_level = self.status.go_to_zone.suction_level
                water_level = self.status.go_to_zone.water_level
                cleaning_mode = self.status.go_to_zone.cleaning_mode
                self.status.go_to_zone = None
                if stop:
                    self.schedule_update(10, True)
                    try:
                        mapping = self.action_mapping[DreameVacuumAction.STOP]
                        self._protocol.action(mapping["siid"], mapping["aiid"])
                    except (KeyError, AttributeError, DeviceException):
                        _LOGGER.debug("restore_go_to_zone: stop action failed", exc_info=True)

                try:
                    self._cleaning_history_update = time.time()
                    if (
                        cleaning_mode is not None
                        and self.status.cleaning_mode is not None
                        and self.status.cleaning_mode.value != cleaning_mode
                    ):
                        self._update_cleaning_mode(cleaning_mode)
                    if suction_level is not None and self.status.suction_level.value != suction_level:
                        self._update_suction_level(suction_level)
                    if water_level is not None and self.status.water_volume.value != water_level:
                        self._update_water_level(water_level)

                    if stop and self.status.started:
                        self._update_status(DreameVacuumTaskStatus.COMPLETED, DreameVacuumStatus.STANDBY)
                except (AttributeError, KeyError, ValueError, TypeError):
                    _LOGGER.debug("restore_go_to_zone: failed to restore state", exc_info=True)

                if self._protocol.dreame_cloud:
                    self.schedule_update(3, True)
            else:
                self.status.go_to_zone = None

    def get_property(
        self,
        prop: (
            DreameVacuumProperty | DreameVacuumAutoSwitchProperty | DreameVacuumStrAIProperty | DreameVacuumAIProperty
        ),
    ) -> Any:
        """Get a device property from memory"""
        if isinstance(prop, DreameVacuumAutoSwitchProperty):
            return self.get_auto_switch_property(prop)
        if isinstance(prop, DreameVacuumStrAIProperty) or isinstance(prop, DreameVacuumAIProperty):
            return self.get_ai_property(prop)
        if prop is not None and prop.value in self.data:
            return self.data[prop.value]
        return None

    def get_auto_switch_property(self, prop: DreameVacuumAutoSwitchProperty) -> int | None:
        """Get a device auto switch property from memory"""
        if self.capability.auto_switch_settings and self.auto_switch_data:
            if prop is not None and prop.name in self.auto_switch_data:
                return int(self.auto_switch_data[prop.name])
        return None

    def get_ai_property(self, prop: DreameVacuumStrAIProperty | DreameVacuumAIProperty) -> bool | None:
        """Get a device AI property from memory"""
        if self.capability.ai_detection and self.ai_data:
            if prop is not None and prop.name in self.ai_data:
                return bool(self.ai_data[prop.name])
        return None

    def set_property_value(self, prop: Any, value: Any) -> Any:
        if prop is not None and value is not None:
            set_fn: Any = "set_" + prop.lower()
            if hasattr(self, set_fn):
                set_fn = getattr(self, set_fn)
            else:
                set_fn = None

            prop = prop.upper()
            if prop in DreameVacuumProperty.__members__:
                prop = DreameVacuumProperty(DreameVacuumProperty[prop])
                if prop not in self._read_write_properties:
                    raise InvalidActionException("Invalid property: %s", prop)
            elif prop in DreameVacuumAutoSwitchProperty.__members__:
                prop = DreameVacuumAutoSwitchProperty(DreameVacuumAutoSwitchProperty[prop])
            elif prop in DreameVacuumAIProperty.__members__:
                prop = DreameVacuumAIProperty(DreameVacuumAIProperty[prop])
            elif prop in DreameVacuumStrAIProperty.__members__:
                prop = DreameVacuumStrAIProperty(DreameVacuumStrAIProperty[prop])
            elif set_fn is None:
                raise InvalidActionException("Invalid property: %s", prop)

            if set_fn is None and self.get_property(prop) is None:
                raise InvalidActionException("Invalid property: %s", prop)

            prop_name = prop.lower() if isinstance(prop, str) else prop.name

            if (
                (
                    self.status.started
                    or not (
                        prop is DreameVacuumProperty.SUCTION_LEVEL
                        or prop is DreameVacuumProperty.WATER_VOLUME
                        or prop is DreameVacuumProperty.CLEANING_MODE
                        or prop is DreameVacuumProperty.WETNESS_LEVEL
                        or prop is DreameVacuumAutoSwitchProperty.CLEANING_ROUTE
                        or prop == "CUSTOM_MOPPING_ROUTE"
                        or prop == "MOP_PAD_HUMIDITY"
                    )
                )
                and prop_name in PROPERTY_AVAILABILITY
                and not cast("Callable[..., Any]", PROPERTY_AVAILABILITY[prop_name])(self)
            ):
                raise InvalidActionException("Property unavailable: %s", prop)

            def get_int_value(enum: Any, value: Any, enum_list: Any = None) -> int | None:
                if isinstance(value, str):
                    value = value.upper()
                    if value.isnumeric():
                        value = int(value)
                    elif value in enum.__members__:
                        value = enum[value].value
                        if enum_list is None:
                            return int(value)

                if isinstance(value, int):
                    if enum_list is None:
                        if value in enum._value2member_map_:
                            return value
                    elif value in enum_list.values():
                        return value
                return None

            string_value: Any = False
            if prop is DreameVacuumProperty.SUCTION_LEVEL:
                value = get_int_value(DreameVacuumSuctionLevel, value)
            elif prop is DreameVacuumProperty.WATER_VOLUME:
                value = get_int_value(DreameVacuumWaterVolume, value)
            elif prop is DreameVacuumProperty.CLEANING_MODE:
                value = get_int_value(DreameVacuumCleaningMode, value)
            elif prop is DreameVacuumProperty.CARPET_SENSITIVITY:
                value = get_int_value(DreameVacuumCarpetSensitivity, value)
            elif prop is DreameVacuumProperty.CARPET_CLEANING:
                value = get_int_value(
                    DreameVacuumCarpetCleaning, value, {v: k for k, v in CARPET_CLEANING_CODE_TO_NAME.items()}
                )
            elif prop is DreameVacuumProperty.MOP_WASH_LEVEL:
                value = get_int_value(DreameVacuumMopWashLevel, value)
            elif prop is DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE:
                value = get_int_value(
                    DreameVacuumVoiceAssistantLanguage, value, self.status.voice_assistant_language_list
                )
            elif prop is DreameVacuumProperty.SCHEDULE:  # Schedule uses string format, not a HA service
                valid = True
                if value and value != "":
                    tasks = value.split(";")
                    for task in tasks:
                        props = task.split("-")
                        if len(props) < 9:
                            valid = False
                            break
                        id = int(props[0])
                        if not id:
                            valid = False
                            break
                        time = props[2]
                        if ":" not in time:
                            valid = False
                            break
                if valid:
                    # Flag-only marker: an empty string is a valid payload here
                    # (it clears the schedule), so do not store the falsy value.
                    string_value = True
            elif prop is DreameVacuumProperty.CLEANGENIUS_MODE:
                value = get_int_value(DreameVacuumCleanGeniusMode, value)
            elif prop is DreameVacuumProperty.WATER_TEMPERATURE:
                value = get_int_value(DreameVacuumWaterTemperature, value)
            elif prop is DreameVacuumAutoSwitchProperty.MOPPING_TYPE:
                value = get_int_value(DreameVacuumMoppingType, value)
            elif prop is DreameVacuumAutoSwitchProperty.WIDER_CORNER_COVERAGE:
                value = get_int_value(DreameVacuumWiderCornerCoverage, value)
            elif prop is DreameVacuumAutoSwitchProperty.MOP_PAD_SWING:
                value = get_int_value(DreameVacuumMopPadSwing, value)
            elif prop is DreameVacuumAutoSwitchProperty.MOP_EXTEND_FREQUENCY:
                value = get_int_value(DreameVacuumMopExtendFrequency, value)
            elif prop is DreameVacuumAutoSwitchProperty.SELF_CLEAN_FREQUENCY:
                value = get_int_value(DreameVacuumSelfCleanFrequency, value)
            elif (
                prop is DreameVacuumAutoSwitchProperty.AUTO_RECLEANING
                or prop is DreameVacuumAutoSwitchProperty.AUTO_REWASHING
            ):
                value = get_int_value(DreameVacuumSecondCleaning, value)
            elif prop is DreameVacuumAutoSwitchProperty.CLEANING_ROUTE:
                value = get_int_value(DreameVacuumCleaningRoute, value, self.status.cleaning_route_list)
            elif prop is DreameVacuumAutoSwitchProperty.CLEANGENIUS:
                value = get_int_value(DreameVacuumCleanGenius, value)
            elif prop == "MOP_PAD_HUMIDITY":
                value = get_int_value(DreameVacuumMopPadHumidity, value)
            elif prop == "CUSTOM_MOPPING_ROUTE":
                value = get_int_value(DreameVacuumCustomMoppingRoute, value)
            elif prop == "AUTO_EMPTY_MODE":
                value = get_int_value(DreameVacuumAutoEmptyMode, value)
            elif prop == "WASHING_MODE":
                value = get_int_value(DreameVacuumWashingMode, value)
            elif prop == "SELECTED_MAP":
                if not self.status.map_data_list or value not in self.status.map_data_list:
                    value = None
            elif (
                prop == DreameVacuumProperty.DND_START
                or prop == DreameVacuumProperty.DND_END
                or prop == "OFF_PEAK_CHARGING_START"
                or prop == "OFF_PEAK_CHARGING_END"
            ):
                string_value = re.match(r"([0-1][0-9]|2[0-3]):[0-5][0-9]$", value)
            elif isinstance(value, bool):
                value = int(value)
            elif isinstance(value, str):
                value = value.upper()
                if value == "TRUE" or value == "1":
                    value = 1
                elif value == "FALSE" or value == "0":
                    value = 0
                elif value.isnumeric():
                    value = int(value)
                else:
                    value = None

            if value is None or not (isinstance(value, int) or string_value):
                if value is not None:
                    raise InvalidActionException("Invalid value: %s", value)
                raise InvalidActionException("Invalid value")

            if prop == DreameVacuumProperty.VOLUME:
                if value < 0 or value > 100:
                    value = None
            elif prop == DreameVacuumProperty.MOP_CLEANING_REMAINDER:
                if value < 0 or value > 180:
                    value = None
            elif prop == DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS:
                if value < 40 or value > 100:
                    value = None
            elif prop == DreameVacuumProperty.WETNESS_LEVEL:
                if value < 1 or value > 32:
                    value = None
            elif prop == "SELF_CLEAN_AREA":
                if value < self.status.self_clean_area_min or value > self.status.self_clean_area_max:
                    value = None
            elif prop == "SELF_CLEAN_TIME":
                if value < self.status.self_clean_time_min or value > self.status.self_clean_time_max:
                    value = None

            if value is None:
                raise InvalidActionException("Invalid value")

            if not self.device_connected:
                raise InvalidActionException("Device unavailable")

            if set_fn:
                return set_fn(value)

            if self.get_property(prop) == value or self.set_property(prop, value):
                return None
            raise InvalidActionException("Property %s not updated: %s", prop, value)
        raise InvalidActionException("Invalid property or value")

    def call_action_value(self, action: Any, params: Any = None) -> Any:
        if action is not None:
            if hasattr(self, action) and not action.startswith("_"):
                action_fn: Any = getattr(self, action)
            else:
                action_fn = None

            action = action.upper()
            if action in DreameVacuumAction.__members__:
                action = DreameVacuumAction(DreameVacuumAction[action])
            elif action_fn is None:
                raise InvalidActionException("Invalid action")

            action_name = action.lower() if isinstance(action, str) else action.name

            if action_name in ACTION_AVAILABILITY and not cast("Callable[..., Any]", ACTION_AVAILABILITY[action_name])(
                self
            ):
                raise InvalidActionException("Action unavailable")

            if not self.device_connected:
                raise InvalidActionException("Device unavailable")

            if action_fn:
                if params is not None:
                    return action_fn(params)
                return action_fn()

            result = self.call_action(action, params)
            if result and result.get("code") == 0:
                return None
            raise InvalidActionException("Unable to call action")
        raise InvalidActionException("Invalid action")

    def set_property(
        self,
        prop: (
            DreameVacuumProperty | DreameVacuumAutoSwitchProperty | DreameVacuumStrAIProperty | DreameVacuumAIProperty
        ),
        value: Any,
    ) -> bool:
        """Sets property value using the existing property mapping and notify listeners
        Property must be set on memory first and notify its listeners because device does not return new value immediately.
        """
        if value is None:
            return False

        if isinstance(prop, DreameVacuumAutoSwitchProperty):
            return bool(self.set_auto_switch_property(prop, value))
        if isinstance(prop, DreameVacuumStrAIProperty) or isinstance(prop, DreameVacuumAIProperty):
            return bool(self.set_ai_property(prop, value))

        self.schedule_update(10)
        current_value = self._update_property(prop, value, False)
        if current_value is not None:
            if prop not in self._discarded_properties:
                self._dirty_data[prop.value] = DirtyData(value, current_value, time.time())

            self._last_change = time.time()
            self._last_settings_request = 0

            try:
                mapping = self.property_mapping[prop]
                result = self._protocol.set_property(mapping["siid"], mapping["piid"], value)

                if result is None or not result or result[0].get("code") != 0:
                    _LOGGER.error(
                        "Property not updated: %s: %s -> %s",
                        prop.name,
                        current_value,
                        value,
                    )
                    self._update_property(prop, current_value)
                    if prop.value in self._dirty_data:
                        del self._dirty_data[prop.value]
                    self._property_changed(False)

                    self.schedule_update(2)
                    return False
                _LOGGER.debug("Update Property: %s: %s -> %s", prop.name, current_value, value)
                if prop.value in self._dirty_data:
                    self._dirty_data[prop.value].update_time = time.time()

                self.schedule_update(3)
                return True
            except Exception as ex:
                self._update_property(prop, current_value)
                if prop.value in self._dirty_data:
                    del self._dirty_data[prop.value]
                self.schedule_update(1)
                raise DeviceUpdateFailedException("Set property failed %s: %s", prop.name, ex) from None

        self.schedule_update(1)
        return False

    def set_volume(self, volume: int) -> bool:
        """Set volume."""
        result = self.set_property(DreameVacuumProperty.VOLUME, volume)
        if result:
            self.call_action(DreameVacuumAction.TEST_SOUND)
        return result

    def set_suction_level(self, suction_level: int) -> bool:
        """Set suction level."""
        if self.status.cruising:
            raise InvalidActionException("Cannot set suction level when cruising")

        if self.status.started and (
            self.status.customized_cleaning and not (self.status.zone_cleaning or self.status.spot_cleaning)
        ):
            raise InvalidActionException("Cannot set suction level when customized cleaning is enabled")
        return self._update_suction_level(suction_level)

    def set_cleaning_mode(self, cleaning_mode: int) -> bool:
        """Set cleaning mode."""
        if self.status.cleaning_mode is None:
            raise InvalidActionException("Cleaning mode is not supported on this device")

        if self.status.cruising:
            raise InvalidActionException("Cannot set cleaning mode when cruising")

        if self.status.draining:
            raise InvalidActionException("Cannot set cleaning mode when draining")

        if self.status.scheduled_clean or self.status.shortcut_task:
            raise InvalidActionException("Cannot set cleaning mode when scheduled cleaning or shortcut task")

        if (
            self.status.started
            and self.capability.custom_cleaning_mode
            and (self.status.customized_cleaning and not (self.status.zone_cleaning or self.status.spot_cleaning))
        ):
            raise InvalidActionException("Cannot set cleaning mode when customized cleaning is enabled")

        cleaning_mode = int(cleaning_mode)
        if cleaning_mode == DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING.value and (
            not self.capability.mopping_after_sweeping
            or (
                self.status.started and self.status.cleaning_mode is not DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING
            )
        ):
            raise InvalidActionException("Cannot set mopping after sweeping")

        if not self.status.auto_mount_mop or not self.status.mop_in_station:
            if cleaning_mode == DreameVacuumCleaningMode.SWEEPING.value:
                if self.status.water_tank_or_mop_installed and not self.capability.mop_pad_lifting:
                    if self.capability.self_wash_base:
                        raise InvalidActionException("Cannot set sweeping while mop pads are installed")
                    raise InvalidActionException("Cannot set sweeping while water tank is installed")
            elif not self.status.water_tank_or_mop_installed:
                if self.capability.self_wash_base:
                    raise InvalidActionException("Cannot set mopping while mop pads are not installed")
                raise InvalidActionException("Cannot set mopping while water tank is not installed")

        if self.status.started and not cast(
            "Callable[..., Any]", PROPERTY_AVAILABILITY[DreameVacuumProperty.CLEANING_MODE.name]
        )(self):
            raise InvalidActionException("Cleaning mode unavailable")

        return self._update_cleaning_mode(cleaning_mode)

    def set_self_clean_area(self, self_clean_area: int) -> bool:
        """Set self clean area."""
        if self.capability.self_wash_base and (
            not self.capability.self_clean_frequency or not self.status.self_clean_by_time
        ):
            return self.set_self_clean_value(self_clean_area)
        return False

    def set_self_clean_time(self, self_clean_time: int) -> bool:
        """Set self clean time."""
        if self.capability.self_wash_base and self.capability.self_clean_frequency and self.status.self_clean_by_time:
            return self.set_self_clean_value(self_clean_time)
        return False

    def set_self_clean_value(self, self_clean_value: int) -> bool:
        """Set self clean value."""
        if self.capability.self_wash_base:
            current_self_clean_value = self.status.self_clean_value
            if self._update_self_clean_value(self_clean_value):
                if self_clean_value and self_clean_value != current_self_clean_value:
                    if self.status.self_clean_by_time:
                        self.status.previous_self_clean_time = self_clean_value
                    else:
                        self.status.previous_self_clean_area = self_clean_value
                return True
        return False

    def set_mop_clean_frequency(self, mop_clean_frequency: int) -> bool:
        """Set mop clean frequency."""
        if self.capability.self_wash_base and self.capability.mop_clean_frequency:
            return self.set_self_clean_value(mop_clean_frequency)
        return False

    def set_mop_pad_humidity(self, mop_pad_humidity: int) -> bool:
        """Set mop pad humidity."""
        if self.capability.self_wash_base:
            if self.status.cruising:
                raise InvalidActionException("Cannot set mop pad humidity when cruising")

            if self.status.started and (
                self.status.customized_cleaning and not (self.status.zone_cleaning or self.status.spot_cleaning)
            ):
                raise InvalidActionException("Cannot set mop pad humidity when customized cleaning is enabled")
            return self._update_water_level(mop_pad_humidity)
        return False

    def set_water_volume(self, water_volume: int) -> bool:
        """Set water volume."""
        if not self.capability.self_wash_base:
            if self.status.cruising:
                raise InvalidActionException("Cannot set water level when cruising")

            if self.status.started and (
                self.status.customized_cleaning and not (self.status.zone_cleaning or self.status.spot_cleaning)
            ):
                raise InvalidActionException("Cannot set water volume when customized cleaning is enabled")

            return self._update_water_level(water_volume)
        return False

    def set_wetness_level(self, wetness_level: int) -> bool:
        """Set wetness level."""
        if self.capability.wetness:
            if self.status.started and (
                self.status.customized_cleaning and not (self.status.zone_cleaning or self.status.spot_cleaning)
            ):
                raise InvalidActionException("Cannot set wetness level when customized cleaning is enabled")

            if self.capability.self_wash_base and self.capability.wetness_level:
                if (
                    wetness_level > 26
                    and (self.status.self_clean_value or 0) > 20
                    and (
                        not self.capability.self_clean_frequency
                        or (
                            self.status.self_clean_frequency == DreameVacuumSelfCleanFrequency.BY_TIME
                            or self.status.self_clean_frequency == DreameVacuumSelfCleanFrequency.BY_ROOM
                        )
                    )
                ):
                    self.set_self_clean_value(20)

            return self.set_property(DreameVacuumProperty.WETNESS_LEVEL, int(wetness_level))
        return False

    def set_dnd_task(self, enabled: bool | None, dnd_start: str | None, dnd_end: str | None) -> bool:
        """Set do not disturb task"""
        if dnd_start is None or dnd_start == "":
            dnd_start = "22:00"

        if dnd_end is None or dnd_end == "":
            dnd_end = "08:00"

        time_pattern = re.compile("([0-1][0-9]|2[0-3]):[0-5][0-9]$")
        if not re.match(time_pattern, dnd_start):
            raise InvalidValueException("DnD start time is not valid: (%s).", dnd_start)
        if not re.match(time_pattern, dnd_end):
            raise InvalidValueException("DnD end time is not valid: (%s).", dnd_end)
        if dnd_start == dnd_end:
            raise InvalidValueException(
                "DnD Start time must be different from DnD end time: (%s == %s).",
                dnd_start,
                dnd_end,
            )

        if self.status.dnd_tasks is None:
            self.status.dnd_tasks = []
        dnd_tasks = self.status.dnd_tasks

        if len(dnd_tasks) == 0:
            dnd_tasks.append(
                {
                    "id": 1,
                    "en": enabled,
                    "st": dnd_start,
                    "et": dnd_end,
                    "wk": 127,
                    "ss": 0,
                }
            )
        else:
            dnd_tasks[0]["en"] = enabled
            dnd_tasks[0]["st"] = dnd_start
            dnd_tasks[0]["et"] = dnd_end
        return self.set_property(
            DreameVacuumProperty.DND_TASK,
            str(json.dumps(dnd_tasks, separators=(",", ":"))).replace(" ", ""),
        )

    def set_dnd(self, enabled: bool) -> bool:
        """Set do not disturb function"""
        return (
            self.set_property(DreameVacuumProperty.DND, bool(enabled))
            if not self.capability.dnd_task
            else self.set_dnd_task(bool(enabled), self.status.dnd_start, self.status.dnd_end)
        )

    def set_dnd_start(self, dnd_start: str) -> bool:
        """Set do not disturb function"""
        return (
            self.set_property(DreameVacuumProperty.DND_START, dnd_start)
            if not self.capability.dnd_task
            else self.set_dnd_task(self.status.dnd, str(dnd_start), self.status.dnd_end)
        )

    def set_dnd_end(self, dnd_end: str) -> bool:
        """Set do not disturb function"""
        if not self.capability.dnd_task:
            return self.set_property(DreameVacuumProperty.DND_END, dnd_end)
        return self.set_dnd_task(self.status.dnd, self.status.dnd_start, str(dnd_end))

    def set_off_peak_charging_config(self, enabled: bool | None, start: str | None, end: str | None) -> bool:
        """Set of peak charging config"""
        if start is None or start == "":
            start = "22:00"

        if end is None or end == "":
            end = "08:00"

        time_pattern = re.compile("([0-1][0-9]|2[0-3]):[0-5][0-9]$")
        if not re.match(time_pattern, start):
            raise InvalidValueException("Start time is not valid: (%s).", start)
        if not re.match(time_pattern, end):
            raise InvalidValueException("End time is not valid: (%s).", end)
        if start == end:
            raise InvalidValueException("Start time must be different from end time: (%s == %s).", start, end)

        self.status.off_peak_charging_config = {
            "enable": enabled,
            "startTime": start,
            "endTime": end,
        }
        return self.set_property(
            DreameVacuumProperty.OFF_PEAK_CHARGING,
            str(json.dumps(self.status.off_peak_charging_config, separators=(",", ":"))).replace(" ", ""),
        )

    def set_off_peak_charging(self, enabled: bool) -> bool:
        """Set off peak charging function"""
        return self.set_off_peak_charging_config(
            bool(enabled),
            self.status.off_peak_charging_start,
            self.status.off_peak_charging_end,
        )

    def set_off_peak_charging_start(self, off_peak_charging_start: str) -> bool:
        """Set off peak charging function"""
        return self.set_off_peak_charging_config(
            self.status.off_peak_charging,
            str(off_peak_charging_start),
            self.status.off_peak_charging_end,
        )

    def set_off_peak_charging_end(self, off_peak_charging_end: str) -> bool:
        """Set off peak charging function"""
        return self.set_off_peak_charging_config(
            self.status.off_peak_charging,
            self.status.off_peak_charging_start,
            str(off_peak_charging_end),
        )

    def set_schedule_task(
        self,
        schedule_id: int | None,
        enabled: bool,
        time: str,
        repeats: str | None = None,
        once: bool = False,
        map_id: str | None = None,
        suction_level: int | None = None,
        water_volume: int | None = None,
        options: list[str] | None = None,
    ) -> bool:
        """Create or update a scheduled cleaning task.

        Rebuilds the ``;``/``-``-joined ``SCHEDULE`` wire string (see
        docs/dev/schedule-format.md and the parser at ``device.py``'s
        ``_schedule_changed``) by replacing only the target task (or
        appending a new one when ``schedule_id`` is ``None``) and leaving
        every sibling task byte-identical, so fields this integration does
        not decode (``repeats``, ``options``) are never corrupted for tasks
        that are not being edited.

        Wire-format caveats (see docs/dev/schedule-format.md for the full
        derivation):

        - The enabled/status field has two confirmed-enabled wire values
          (``"1"`` and ``"2"``); what distinguishes them is unconfirmed from
          static analysis, so this integration always writes ``"1"`` for
          ``enabled=True`` (a confirmed round-trippable value) and ``"0"``
          for ``enabled=False``.
        - ``repeats`` and ``options`` are opaque pass-through values: this
          method never encodes/decodes them. When omitted on an edit, the
          previous task's raw value is preserved; when omitted on create, a
          neutral ``"0"`` placeholder is sent (its acceptance by firmware for
          a repeating task is unconfirmed - pass an explicit ``repeats``
          value if you need a specific repeat pattern).
        - ``suction_level``/``water_volume`` have no confirmed default value,
          so they are required when creating a new task; they remain
          optional when editing an existing task, where the previous
          task's value is kept if omitted.
        """
        if not time or not re.match(r"([0-1][0-9]|2[0-3]):[0-5][0-9]$", time):
            raise InvalidValueException("Schedule time is not valid: (%s).", time)

        if schedule_id is not None and not int(schedule_id):
            raise InvalidValueException("Schedule id must be a positive integer: (%s).", schedule_id)

        raw_schedule = self.get_property(DreameVacuumProperty.SCHEDULE) or ""
        tasks = raw_schedule.split(";") if raw_schedule else []

        target_index: int | None = None
        existing_props: list[str] | None = None
        existing_ids: list[int] = []
        for index, task in enumerate(tasks):
            props = task.split("-")
            if len(props) < 9:
                continue
            try:
                props_id = int(props[0])
            except ValueError:
                continue
            existing_ids.append(props_id)
            if schedule_id is not None and props_id == int(schedule_id):
                target_index = index
                existing_props = props

        if schedule_id is None:
            task_id = max(existing_ids, default=0) + 1
        else:
            if target_index is None:
                raise InvalidActionException("Schedule not found! (%s)", schedule_id)
            task_id = int(schedule_id)

        if repeats is None:
            repeats = existing_props[3] if existing_props else "0"
        if map_id is None:
            map_id = existing_props[5] if existing_props else "0"

        if suction_level is None:
            if existing_props is None:
                raise InvalidValueException("Schedule suction_level is required when creating a new task.")
            suction_level = int(existing_props[6])

        if water_volume is None:
            if existing_props is None:
                raise InvalidValueException("Schedule water_volume is required when creating a new task.")
            water_volume = int(existing_props[7])

        if options is None:
            # Options is the last field, so join any trailing fragments back
            # together in case it legitimately contains a "-" (unconfirmed,
            # but this avoids silently dropping data if it ever does).
            options_value = "-".join(existing_props[8:]) if existing_props else "0"
        else:
            options_value = ",".join(str(option) for option in options) if options else "0"

        new_task = "-".join(
            [
                str(task_id),
                "1" if enabled else "0",
                str(time),
                str(repeats),
                "0" if once else "1",
                str(map_id),
                str(int(suction_level)),
                str(int(water_volume)),
                options_value,
            ]
        )

        if target_index is not None:
            tasks[target_index] = new_task
        else:
            tasks.append(new_task)

        return self.set_property(DreameVacuumProperty.SCHEDULE, ";".join(tasks))

    def set_voice_assistant_language(self, voice_assistant_language: str) -> bool:
        if (
            self.get_property(DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE) is None
            or voice_assistant_language is None
            or len(voice_assistant_language) < 2
            or voice_assistant_language.upper() not in DreameVacuumVoiceAssistantLanguage.__members__
        ):
            raise InvalidActionException(f"Voice assistant language ({voice_assistant_language}) is not supported")
        return self.set_property(
            DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE,
            DreameVacuumVoiceAssistantLanguage[voice_assistant_language.upper()],
        )

    def set_washing_mode(self, washing_mode: int) -> bool:
        if self.capability.smart_mop_washing:
            result: Any = False
            if washing_mode < 3:
                if washing_mode != self.status.mop_wash_level.value:
                    result = self.set_property(DreameVacuumProperty.MOP_WASH_LEVEL, washing_mode)
                if result and self.status.ultra_clean_mode:
                    result = self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE, 0)
            elif self.capability.ultra_clean_mode:
                result = self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE, 1)

            if result and self.status.smart_mop_washing:
                self.set_property(DreameVacuumProperty.SMART_MOP_WASHING, 0)
            return bool(result)
        return False

    def set_mop_wash_level(self, mop_wash_level: int) -> bool:
        if not self.capability.smart_mop_washing:
            result = self.set_property(DreameVacuumProperty.MOP_WASH_LEVEL, mop_wash_level)
            if result and self.capability.ultra_clean_mode and self.status.ultra_clean_mode:
                return bool(self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE, 0))
            return result
        return False

    def set_drying_time(self, drying_time: int) -> bool:
        result = self.set_property(DreameVacuumProperty.DRYING_TIME, drying_time)
        if result and self.capability.silent_drying and self.status.silent_drying:
            return self.set_property(DreameVacuumProperty.SILENT_DRYING, 0)
        return result

    def set_ai_detection(self, settings: dict[str, bool] | int) -> dict[str, Any] | None:
        """Send ai detection parameters to the device."""
        if self.capability.ai_detection:
            mapping = self.property_mapping[DreameVacuumProperty.AI_DETECTION]
            if isinstance(settings, int):
                return cast(
                    "dict[str, Any] | None", self._protocol.set_property(mapping["siid"], mapping["piid"], settings, 3)
                )
            return cast(
                "dict[str, Any] | None",
                self._protocol.set_property(
                    mapping["siid"],
                    mapping["piid"],
                    str(json.dumps(settings, separators=(",", ":"))).replace(" ", ""),
                    3,
                ),
            )
        return None

    def set_ai_property(
        self, prop: DreameVacuumStrAIProperty | DreameVacuumAIProperty, value: bool
    ) -> dict[str, Any] | None:
        if self.capability.ai_detection and self.ai_data is not None:
            ad = self.ai_data
            if prop.name not in ad:
                raise InvalidActionException("Not supported")
            current_value = self.get_ai_property(prop)

            self._dirty_ai_data[prop.name] = DirtyData(value, current_value, time.time())
            ad[prop.name] = value
            ai_value = self.get_property(DreameVacuumProperty.AI_DETECTION)
            self._property_changed(False)
            result: Any = None
            try:
                if isinstance(ai_value, int):
                    bit = DreameVacuumAIProperty[prop.name].value
                    result = self.set_ai_detection((ai_value | bit) if value else (ai_value & -(bit + 1)))
                else:
                    result = self.set_ai_detection({DreameVacuumStrAIProperty[prop.name].value: bool(value)})

                if result is None or not result or result[0].get("code") != 0:
                    _LOGGER.error(
                        "AI Property not updated: %s: %s -> %s",
                        prop.name,
                        current_value,
                        value,
                    )
                    if prop.name in self._dirty_ai_data:
                        del self._dirty_ai_data[prop.name]
                    ad[prop.name] = current_value
                    self._property_changed(False)
            except (DeviceException, KeyError, ValueError, TypeError):
                _LOGGER.debug("set_ai_property %s: rolling back", prop.name, exc_info=True)
                if prop.name in self._dirty_ai_data:
                    del self._dirty_ai_data[prop.name]
                ad[prop.name] = current_value
                self._property_changed(False)
            return cast("dict[str, Any] | None", result)
        return None

    def set_auto_switch_settings(self, settings: Any) -> dict[str, Any] | None:
        if self.capability.auto_switch_settings:
            mapping = self.property_mapping[DreameVacuumProperty.AUTO_SWITCH_SETTINGS]
            return cast(
                "dict[str, Any] | None",
                self._protocol.set_property(
                    mapping["siid"],
                    mapping["piid"],
                    str(json.dumps(settings, separators=(",", ":"))).replace(" ", ""),
                    1,
                ),
            )
        return None

    def set_auto_switch_property(self, prop: DreameVacuumAutoSwitchProperty, value: int) -> dict[str, Any] | None:
        if self.capability.auto_switch_settings:
            asd: Any = self.auto_switch_data
            if prop.name not in asd:
                raise InvalidActionException("Not supported")
            current_value = self.get_auto_switch_property(prop)
            if current_value != value:
                self._dirty_auto_switch_data[prop.name] = DirtyData(value, current_value, time.time())
                asd[prop.name] = value
                self._property_changed(False)
                result: Any = None
                if prop is DreameVacuumAutoSwitchProperty.CLEANGENIUS and self._map_manager:
                    self._map_manager.editor.refresh_map()
                try:
                    result = self.set_auto_switch_settings({"k": prop.value, "v": int(value)})
                    if result is None or not result or result[0].get("code") != 0:
                        _LOGGER.error(
                            "Auto Switch Property not updated: %s: %s -> %s",
                            prop.name,
                            current_value,
                            value,
                        )
                        if prop.name in self._dirty_auto_switch_data:
                            del self._dirty_auto_switch_data[prop.name]
                        asd[prop.name] = current_value
                        self._property_changed(False)
                    else:
                        _LOGGER.debug("Update Property: %s: %s -> %s", prop.name, current_value, value)
                        if prop.name in self._dirty_auto_switch_data:
                            self._dirty_auto_switch_data[prop.name].update_time = time.time()
                except (DeviceException, KeyError, ValueError, TypeError):
                    _LOGGER.debug("set_auto_switch_property %s: rolling back", prop.name, exc_info=True)
                    if prop.name in self._dirty_auto_switch_data:
                        del self._dirty_auto_switch_data[prop.name]
                    asd[prop.name] = current_value
                    self._property_changed(False)
                return cast("dict[str, Any] | None", result)
        elif self.capability.self_wash_base and prop == DreameVacuumAutoSwitchProperty.AUTO_DRYING:
            return cast(
                "dict[str, Any] | None", self.set_property(DreameVacuumProperty.INTELLIGENT_RECOGNITION, int(value))
            )
        return None

    def set_camera_light_brightness(self, brightness: int) -> dict[str, Any] | None:
        if self.capability.auto_switch_settings:
            if brightness < 40:
                brightness = 40
            current_value = self.status.camera_light_brightness
            self._update_property(DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, str(brightness))
            result = self.call_stream_property_action(
                DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, {"value": str(brightness)}
            )
            if result is None or result.get("code") != 0:
                self._update_property(DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, str(current_value))
            return result
        return None

    def set_wider_corner_coverage(self, value: int) -> dict[str, Any] | None:
        if self.capability.auto_switch_settings:
            current_value = self.get_auto_switch_property(DreameVacuumAutoSwitchProperty.WIDER_CORNER_COVERAGE)
            if current_value is not None and current_value > 0 and value <= 0:
                value = -current_value
            return self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.WIDER_CORNER_COVERAGE, value)
        return None

    def set_mop_pad_swing(self, value: int) -> dict[str, Any] | None:
        if self.capability.auto_switch_settings:
            current_value = self.get_auto_switch_property(DreameVacuumAutoSwitchProperty.MOP_PAD_SWING)
            if current_value is not None and current_value > 0 and value <= 0:
                value = -current_value
            return self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.MOP_PAD_SWING, value)
        return None

    def set_auto_recleaning(self, value: int) -> dict[str, Any] | None:
        if self.capability.auto_switch_settings and self.capability.auto_recleaning:
            current_value = self.get_auto_switch_property(DreameVacuumAutoSwitchProperty.AUTO_RECLEANING)
            if current_value is not None and current_value > 0 and value <= 0:
                value = -current_value
            return self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.AUTO_RECLEANING, value)
        return None

    def set_auto_rewashing(self, value: int) -> dict[str, Any] | None:
        if self.capability.auto_switch_settings and self.capability.auto_rewashing:
            current_value = self.get_auto_switch_property(DreameVacuumAutoSwitchProperty.AUTO_REWASHING)
            if current_value is not None and current_value > 0 and value <= 0:
                value = -current_value
            return self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.AUTO_REWASHING, value)
        return None

    def set_self_clean_frequency(self, value: int) -> bool | dict[str, Any] | None:
        if self.capability.auto_switch_settings:
            current_value = self.get_auto_switch_property(DreameVacuumAutoSwitchProperty.SELF_CLEAN_FREQUENCY)
            if current_value is not None and current_value > 0 and value <= 0:  # OFF
                if current_value == DreameVacuumSelfCleanFrequency.BY_TIME.value:
                    self.status.previous_self_clean_time = self.status.self_clean_value or 0
                elif current_value == DreameVacuumSelfCleanFrequency.BY_AREA.value:
                    self.status.previous_self_clean_area = self.status.self_clean_value or 0

            if not value:
                result: bool | dict[str, Any] | None = self.set_self_clean_value(0)
                if not self.capability.self_clean_frequency:
                    return result

            result = not self.capability.self_clean_frequency or self.set_auto_switch_property(
                DreameVacuumAutoSwitchProperty.SELF_CLEAN_FREQUENCY, value
            )
            if result and value:
                if self.capability.self_clean_frequency and value == DreameVacuumSelfCleanFrequency.BY_TIME.value:
                    self.set_self_clean_value(
                        self.status.previous_self_clean_time
                        if self.status.previous_self_clean_time
                        else self.status.self_clean_time_default
                    )
                else:
                    self.set_self_clean_value(
                        self.status.previous_self_clean_area
                        if self.status.previous_self_clean_area
                        else self.status.self_clean_area_default
                    )
            return result
        return None

    def set_auto_empty_mode(self, value: int) -> bool | dict[str, Any] | None:
        if self.capability.auto_empty_mode:
            return self.set_property(DreameVacuumProperty.AUTO_DUST_COLLECTING, value)
        return None

    def set_custom_mopping_route(self, value: int) -> bool | dict[str, Any] | None:
        if self.capability.custom_mopping_route:
            if value < 0:
                result = self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.CUSTOM_MOPPING_MODE, 0)
                if result:
                    return self._update_water_level(
                        self.get_auto_switch_property(DreameVacuumAutoSwitchProperty.MOPPING_MODE) or 0
                    )
            if not self.status.custom_mopping_mode:
                result = self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.CUSTOM_MOPPING_MODE, 1)
                if result:
                    self._update_water_level(
                        self.status.mop_pad_humidity
                        if self.capability.self_wash_base
                        else self.status.water_volume.value
                    )
            return self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.MOPPING_TYPE, value)
        return None

    def set_resume_cleaning(self, value: int) -> bool | dict[str, Any] | None:
        if self.capability.auto_charging and bool(value):
            value = 2
        return self.set_property(DreameVacuumProperty.RESUME_CLEANING, value)

    def set_carpet_avoidance(self, value: bool) -> bool | dict[str, Any] | None:
        return self.set_property(DreameVacuumProperty.CARPET_CLEANING, 1 if value else 2)

    def set_carpet_cleaning(self, value: int) -> dict[str, Any] | None:
        if self.get_property(DreameVacuumProperty.CARPET_CLEANING) is not None:
            if (
                value == 4
                and (
                    not self.capability.mop_pad_lifting_plus
                    or self.capability.auto_carpet_cleaning
                    or self.capability.carpet_crossing
                )
            ) or (
                value == 6 and (not self.capability.mop_pad_lifting_plus and not self.capability.auto_carpet_cleaning)
            ):
                raise InvalidActionException("Selected cleaning setting is not supported on this device: %s", value)

            if value == 6:
                return self.set_carpet_recognition(0)
            if not self.status.carpet_recognition:
                self.set_carpet_recognition(1)
            result = self.set_property(DreameVacuumProperty.CARPET_CLEANING, value)
            if result and self.capability.mop_pad_unmounting and value == 3 and not self.status.auto_mount_mop:
                self.set_property(DreameVacuumProperty.AUTO_MOUNT_MOP, 1)
        return None

    def set_carpet_recognition(self, value: int) -> dict[str, Any] | None:
        if self.capability.carpet_recognition:
            current_value = self.get_property(DreameVacuumProperty.CARPET_RECOGNITION)
            if current_value is not None:
                if bool(value):
                    value = 1
                else:
                    value = 3 if self.get_property(DreameVacuumProperty.CARPET_BOOST) == 1 else 0
                if self.set_property(DreameVacuumProperty.CARPET_RECOGNITION, value):
                    self.set_property(
                        DreameVacuumProperty.CARPET_BOOST,
                        1 if value == 1 and current_value == 3 else 0,
                    )
        return None

    def set_multi_floor_map(self, enabled: bool) -> bool:
        if self.set_property(DreameVacuumProperty.MULTI_FLOOR_MAP, int(enabled)):
            if (
                self.capability.auto_switch_settings
                and not enabled
                and self.get_property(DreameVacuumProperty.INTELLIGENT_RECOGNITION) == 1
            ):
                self.set_property(DreameVacuumProperty.INTELLIGENT_RECOGNITION, 0)
            return True
        return False

    def set_obstacle_ignore(self, x: Any, y: Any, obstacle_ignored: Any) -> dict[str, Any] | None:
        if not self.capability.ai_detection:
            raise InvalidActionException("Obstacle detection is not available on this device")

        if not self._map_manager:
            raise InvalidActionException("Obstacle ignore requires cloud connection")

        if self.status.started:
            raise InvalidActionException("Cannot set obstacle ignore status while vacuum is running")

        if not self.status.current_map or not self.status.current_map.obstacles:
            raise InvalidActionException("Obstacle not found")

        if self.status.current_map.obstacles is None or (
            len(self.status.current_map.obstacles)
            and next(iter(self.status.current_map.obstacles.values())).ignore_status is None
        ):
            raise InvalidActionException("Obstacle ignore is not supported on this device")

        found = False
        obstacle_type = 142
        for _k, v in self.status.current_map.obstacles.items():
            if int(v.x) == int(x) and int(v.y) == int(y):
                if v.ignore_status.value == 2:
                    raise InvalidActionException("Cannot ignore a dynamically ignored obstacle")
                obstacle_type = v.type.value
                found = True
                break

        if not found:
            raise InvalidActionException("Obstacle not found")

        self._map_manager.editor.set_obstacle_ignore(x, y, obstacle_ignored)
        self.update_map_data_async(
            {
                "obstacleignore": [
                    int(x),
                    int(y),
                    obstacle_type,
                    1 if bool(obstacle_ignored) else 0,
                ]
            }
        )
        return None

    def set_router_position(self, x: Any, y: Any) -> None:
        if not self.capability.wifi_map:
            raise InvalidActionException("WiFi map is not available on this device")

        if self.status.started:
            raise InvalidActionException("Cannot set router position while vacuum is running")

        if self._map_manager:
            self._map_manager.editor.set_router_position(x, y)
        self.update_map_data_async({"wrp": [int(x), int(y)]})
