"""Dreame Vacuum device actions mixin."""

from __future__ import annotations

import base64
from collections.abc import Callable
import json
import logging
from random import randrange
import re
import time
from typing import Any, cast

from ._device_base import DreameVacuumDeviceState
from .exceptions import (
    InvalidActionException,
    InvalidValueException,
)
from .vacuum_types import (
    ACTION_AVAILABILITY,
    PIID,
    CleanupMethod,
    DreameVacuumAction,
    DreameVacuumAutoEmptyStatus,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumCleanGenius,
    DreameVacuumCleaningMode,
    DreameVacuumErrorCode,
    DreameVacuumProperty,
    DreameVacuumSelfWashBaseStatus,
    DreameVacuumState,
    DreameVacuumStatus,
    DreameVacuumStreamStatus,
    DreameVacuumTaskStatus,
    Shortcut,
    ShortcutTask,
)

_LOGGER = logging.getLogger(__name__)


# action -> (LEFT property, TIME_LEFT property, TIME_LEFT default). On reset, LEFT is
# always restored to 100; only the time-left default is consumable-specific.
_RESET_CONSUMABLES = {
    DreameVacuumAction.RESET_MAIN_BRUSH: (
        DreameVacuumProperty.MAIN_BRUSH_LEFT,
        DreameVacuumProperty.MAIN_BRUSH_TIME_LEFT,
        300,
    ),
    DreameVacuumAction.RESET_SIDE_BRUSH: (
        DreameVacuumProperty.SIDE_BRUSH_LEFT,
        DreameVacuumProperty.SIDE_BRUSH_TIME_LEFT,
        200,
    ),
    DreameVacuumAction.RESET_FILTER: (
        DreameVacuumProperty.FILTER_LEFT,
        DreameVacuumProperty.FILTER_TIME_LEFT,
        150,
    ),
    DreameVacuumAction.RESET_SENSOR: (
        DreameVacuumProperty.SENSOR_DIRTY_LEFT,
        DreameVacuumProperty.SENSOR_DIRTY_TIME_LEFT,
        30,
    ),
    DreameVacuumAction.RESET_TANK_FILTER: (
        DreameVacuumProperty.TANK_FILTER_LEFT,
        DreameVacuumProperty.TANK_FILTER_TIME_LEFT,
        30,
    ),
    DreameVacuumAction.RESET_MOP_PAD: (
        DreameVacuumProperty.MOP_PAD_LEFT,
        DreameVacuumProperty.MOP_PAD_TIME_LEFT,
        80,
    ),
    DreameVacuumAction.RESET_SILVER_ION: (
        DreameVacuumProperty.SILVER_ION_LEFT,
        DreameVacuumProperty.SILVER_ION_TIME_LEFT,
        365,
    ),
    DreameVacuumAction.RESET_DETERGENT: (
        DreameVacuumProperty.DETERGENT_LEFT,
        DreameVacuumProperty.DETERGENT_TIME_LEFT,
        18,
    ),
    DreameVacuumAction.RESET_SQUEEGEE: (
        DreameVacuumProperty.SQUEEGEE_LEFT,
        DreameVacuumProperty.SQUEEGEE_TIME_LEFT,
        100,
    ),
    DreameVacuumAction.RESET_ONBOARD_DIRTY_WATER_TANK: (
        DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_LEFT,
        DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_TIME_LEFT,
        100,
    ),
    DreameVacuumAction.RESET_DIRTY_WATER_TANK: (
        DreameVacuumProperty.DIRTY_WATER_TANK_LEFT,
        DreameVacuumProperty.DIRTY_WATER_TANK_TIME_LEFT,
        100,
    ),
    DreameVacuumAction.RESET_DEODORIZER: (
        DreameVacuumProperty.DEODORIZER_LEFT,
        DreameVacuumProperty.DEODORIZER_TIME_LEFT,
        180,
    ),
    DreameVacuumAction.RESET_WHEEL: (
        DreameVacuumProperty.WHEEL_DIRTY_LEFT,
        DreameVacuumProperty.WHEEL_DIRTY_TIME_LEFT,
        30,
    ),
    DreameVacuumAction.RESET_SCALE_INHIBITOR: (
        DreameVacuumProperty.SCALE_INHIBITOR_LEFT,
        DreameVacuumProperty.SCALE_INHIBITOR_TIME_LEFT,
        1095,
    ),
}


class DreameVacuumDeviceActionsMixin(DreameVacuumDeviceState):
    """Mixin providing action methods for DreameVacuumDevice."""

    def call_stream_audio_action(self, property: DreameVacuumProperty, parameters: Any = None) -> dict[str, Any] | None:
        return self.call_stream_action(DreameVacuumAction.STREAM_AUDIO, property, parameters)

    def call_stream_video_action(self, property: DreameVacuumProperty, parameters: Any = None) -> dict[str, Any] | None:
        return self.call_stream_action(DreameVacuumAction.STREAM_VIDEO, property, parameters)

    def call_stream_property_action(
        self, property: DreameVacuumProperty, parameters: Any = None
    ) -> dict[str, Any] | None:
        return self.call_stream_action(DreameVacuumAction.STREAM_PROPERTY, property, parameters)

    def call_stream_action(
        self,
        action: DreameVacuumAction,
        property: DreameVacuumProperty,
        parameters: Any = None,
    ) -> dict[str, Any] | None:
        params = {"session": self.status.stream_session}
        if parameters:
            params.update(parameters)
        return self.call_action(
            action,
            [
                {
                    "piid": PIID(property),
                    "value": str(json.dumps(params, separators=(",", ":"))).replace(" ", ""),
                }
            ],
        )

    def call_shortcut_action(self, command: str, parameters: Any = None) -> dict[str, Any] | None:
        if parameters is None:
            parameters = {}
        return self.call_action(
            DreameVacuumAction.SHORTCUTS,
            [
                {
                    "piid": PIID(DreameVacuumProperty.CLEANING_PROPERTIES),
                    "value": str(
                        json.dumps(
                            {"cmd": command, "params": parameters},
                            separators=(",", ":"),
                        )
                    ).replace(" ", ""),
                }
            ],
        )

    def call_shortcut_action_async(self, callback: Callable[..., Any], command: str, parameters: Any = None) -> None:
        if parameters is None:
            parameters = {}
        mapping = self.action_mapping[DreameVacuumAction.SHORTCUTS]
        return self._protocol.action_async(
            callback,
            mapping["siid"],
            mapping["aiid"],
            [
                {
                    "piid": PIID(DreameVacuumProperty.CLEANING_PROPERTIES),
                    "value": str(
                        json.dumps(
                            {"cmd": command, "params": parameters},
                            separators=(",", ":"),
                        )
                    ).replace(" ", ""),
                }
            ],
        )

    def call_action(
        self, action: DreameVacuumAction, parameters: list[Any] | dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Call an action."""
        if action not in self.action_mapping:
            raise InvalidActionException(f"Unable to find {action} in the action mapping")

        mapping = self.action_mapping[action]
        if "siid" not in mapping or "aiid" not in mapping:
            raise InvalidActionException(f"{action} is not an action (missing siid or aiid)")

        if self.status.draining_complete:
            self.set_property(DreameVacuumProperty.DRAINAGE_STATUS, 0)

        map_action = bool(action is DreameVacuumAction.REQUEST_MAP or action is DreameVacuumAction.UPDATE_MAP_DATA)

        if not map_action:
            self.schedule_update(10, True)

        cleaning_action = bool(
            action
            in [
                DreameVacuumAction.START,
                DreameVacuumAction.START_CUSTOM,
                DreameVacuumAction.PAUSE,
                DreameVacuumAction.STOP,
                DreameVacuumAction.CHARGE,
            ]
        )

        if not cleaning_action:
            available_fn: Callable[..., Any] | None = ACTION_AVAILABILITY.get(action.name)
            if available_fn and not available_fn(self):
                raise InvalidActionException("Action unavailable")
        elif self._map_select_time:
            # Let the previous map-select settle before issuing the next action.
            # call_action is always dispatched through async_add_executor_job, so
            # this blocks an executor thread (not the event loop). Capped to keep
            # the worker pool from saturating when actions are chained.
            elapsed = time.time() - self._map_select_time
            self._map_select_time = None
            if elapsed < 5:
                time.sleep(min(5 - elapsed, 3))

        # Reset consumable on memory (table-driven, see _RESET_CONSUMABLES above).
        reset = _RESET_CONSUMABLES.get(action)
        if reset is not None:
            left_prop, time_left_prop, time_left_default = reset
            self._consumable_change = True
            self._update_property(left_prop, 100)
            self._update_property(time_left_prop, time_left_default)
        elif action is DreameVacuumAction.START_AUTO_EMPTY:
            self._update_property(
                DreameVacuumProperty.AUTO_EMPTY_STATUS,
                DreameVacuumAutoEmptyStatus.ACTIVE.value,
            )
        elif action is DreameVacuumAction.CLEAR_WARNING:
            self._update_property(DreameVacuumProperty.ERROR, DreameVacuumErrorCode.NO_ERROR.value)

        # Update listeners
        if cleaning_action or self._consumable_change:
            self._property_changed(False)

        try:
            result: dict[str, Any] | None = self._protocol.action(mapping["siid"], mapping["aiid"], parameters)
        except Exception as ex:
            _LOGGER.error("Send action failed %s: %s", action.name, ex)
            self.schedule_update(1, True)
            return None

        # Schedule update for retrieving new properties after action sent
        self.schedule_update(6, bool(not map_action and self._protocol.dreame_cloud))
        if result and result.get("code") == 0:
            _LOGGER.debug("Send action %s %s", action.name, parameters)
            self._last_change = time.time()
            if not map_action:
                self._last_settings_request = 0
        else:
            _LOGGER.error("Send action failed %s (%s): %s", action.name, parameters, result)

        return result

    def send_command(self, command: str, parameters: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Send a raw command to the device. This is mostly useful when trying out
        commands which are not implemented by a given device instance. (Not likely)"""

        if command == "":
            raise InvalidActionException(f"Invalid Command: ({command}).")

        self.schedule_update(10, True)
        response = self._protocol.send(command, parameters, 3)
        if response:
            _LOGGER.debug("Send command response: %s", response)
        self.schedule_update(2, True)
        return None

    def delete_schedule(self, schedule_id: Any) -> dict[str, Any] | None:
        """Delete a scheduled task."""
        found = False
        for schedule in self.status.schedule:
            if str(schedule.id) == str(schedule_id):
                found = True
                break

        if not found:
            raise InvalidActionException(f"Schedule not found! ({schedule_id})")

        schedule_list = self.get_property(DreameVacuumProperty.SCHEDULE)
        if schedule_list and schedule_list != "":
            tasks = schedule_list.split(";")
            schedule = ""
            for task in tasks:
                props = task.split("-")
                if props[0] != str(schedule_id):
                    if len(schedule) > 1:
                        schedule = f"{schedule};"
                    schedule = f"{schedule}{task}"
            self.set_property(DreameVacuumProperty.SCHEDULE, schedule)

        response = self.call_action(
            DreameVacuumAction.DELETE_SCHEDULE,
            [
                {
                    "piid": PIID(DreameVacuumProperty.SCHEDULE_ID, self.property_mapping),
                    "value": schedule_id,
                }
            ],
        )
        self.schedule_update(3, True)
        if not response or response.get("code") != 0:
            self.set_property(DreameVacuumProperty.SCHEDULE, schedule_list)
        return response

    def locate(self) -> dict[str, Any] | None:
        """Locate the vacuum cleaner."""
        return self.call_action(DreameVacuumAction.LOCATE)

    def start(self) -> dict[str, Any] | None:
        """Start or resume the cleaning task."""
        if self.status.fast_mapping_paused:
            self._update_status(DreameVacuumTaskStatus.FAST_MAPPING, DreameVacuumStatus.FAST_MAPPING)
            return self.start_custom(DreameVacuumStatus.FAST_MAPPING.value)

        if self.status.returning_paused:
            return self.return_to_base()

        if self.status.returning_to_wash_paused:
            return self.start_washing()

        if self.capability.cruising:
            if self.status.cruising_paused:
                return self.start_custom(self.status.status.value)
        elif not self.status.paused:
            self._restore_go_to_zone()

        if self.status.draining or self.status.self_repairing:
            raise InvalidActionException("Cannot start cleaning while draining or self repairing/testing")

        self.schedule_update(10, True)

        if not self.status.started:
            self._update_status(DreameVacuumTaskStatus.AUTO_CLEANING, DreameVacuumStatus.CLEANING)
        elif (
            self.status.paused
            and not self.status.cleaning_paused
            and not self.status.cruising
            and not self.status.scheduled_clean
        ):
            self._update_property(DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value)
            if self.status.task_status is not DreameVacuumTaskStatus.COMPLETED:
                new_state = DreameVacuumState.SWEEPING
                if self.status.cleaning_mode is DreameVacuumCleaningMode.MOPPING:
                    new_state = DreameVacuumState.MOPPING
                elif self.status.cleaning_mode is DreameVacuumCleaningMode.SWEEPING_AND_MOPPING:
                    new_state = DreameVacuumState.SWEEPING_AND_MOPPING
                self._update_property(DreameVacuumProperty.STATE, new_state.value)

        if self._map_manager:
            if not self.status.started:
                self._map_manager.editor.clear_path()
            self._map_manager.editor.refresh_map()

        return self.call_action(DreameVacuumAction.START)

    def start_custom(self, status: Any, parameters: Any = None) -> dict[str, Any] | None:
        """Start custom cleaning task."""
        if not self.capability.cruising and status != DreameVacuumStatus.ZONE_CLEANING.value:
            self._restore_go_to_zone()

        if status is not DreameVacuumStatus.FAST_MAPPING.value and self.status.fast_mapping:
            raise InvalidActionException("Cannot start cleaning while fast mapping")

        payload = [
            {
                "piid": PIID(DreameVacuumProperty.STATUS, self.property_mapping),
                "value": status,
            }
        ]

        if parameters is not None:
            payload.append(
                {
                    "piid": PIID(DreameVacuumProperty.CLEANING_PROPERTIES, self.property_mapping),
                    "value": parameters,
                }
            )

        return self.call_action(DreameVacuumAction.START_CUSTOM, payload)

    def stop(self) -> dict[str, Any] | None:
        """Stop the vacuum cleaner."""
        if self.status.fast_mapping:
            return self.return_to_base()

        if self.status.draining or self.status.self_repairing:
            raise InvalidActionException("Cannot stop while draining or self repairing/testing")

        self.schedule_update(10, True)

        response = None
        if self.status.go_to_zone:
            response = self.call_action(DreameVacuumAction.STOP)

        if self.status.started:
            self._update_status(DreameVacuumTaskStatus.COMPLETED, DreameVacuumStatus.STANDBY)

            # Clear active segments on current map data
            if self._map_manager:
                if self.status.go_to_zone:
                    self._map_manager.editor.set_active_areas([])
                self._map_manager.editor.set_cruise_points([])
                self._map_manager.editor.set_active_segments([])
        elif self.status.drying:
            return self.stop_drying()

        if response:
            return response

        return self.call_action(DreameVacuumAction.STOP)

    def pause(self) -> dict[str, Any] | None:
        """Pause the cleaning task."""
        if self.status.draining or self.status.self_repairing:
            raise InvalidActionException("Cannot pause while draining or self repairing/testing")

        self.schedule_update(10, True)

        if not self.status.started and self.status.washing:
            return self.pause_washing()

        if not self.status.paused and self.status.started:
            if self.status.cruising and not self.capability.cruising:
                self._update_property(
                    DreameVacuumProperty.STATE,
                    DreameVacuumState.MONITORING_PAUSED.value,
                )
            else:
                self._update_property(DreameVacuumProperty.STATE, DreameVacuumState.PAUSED.value)
            self._update_property(DreameVacuumProperty.STATUS, DreameVacuumStatus.PAUSED.value)
            if self.status.go_to_zone:
                self._update_property(
                    DreameVacuumProperty.TASK_STATUS,
                    DreameVacuumTaskStatus.CRUISING_POINT_PAUSED.value,
                )

        return self.call_action(DreameVacuumAction.PAUSE)

    def return_to_base(self) -> dict[str, Any] | None:
        """Set the vacuum cleaner to return to the dock."""
        if self._map_manager:
            self._map_manager.editor.set_cruise_points([])

        # if self.status.started:
        if not self.status.docked:
            self._update_property(DreameVacuumProperty.STATUS, DreameVacuumStatus.BACK_HOME.value)
            self._update_property(DreameVacuumProperty.STATE, DreameVacuumState.RETURNING.value)

        # Clear active segments on current map data
        # if self._map_manager:
        #    self._map_manager.editor.set_active_segments([])

        if not self.capability.cruising:
            self._restore_go_to_zone()
        return self.call_action(DreameVacuumAction.CHARGE)

    def start_pause(self) -> dict[str, Any] | None:
        """Start or resume the cleaning task."""
        if (
            not self.status.started
            or self.status.state is DreameVacuumState.PAUSED
            or self.status.status is DreameVacuumStatus.BACK_HOME
        ):
            return self.start()
        return self.pause()

    def clean_zone(
        self,
        zones: Any,
        cleaning_times: Any,
        suction_level: Any,
        water_volume: Any,
    ) -> dict[str, Any] | None:
        """Clean selected area."""
        if self.status.draining or self.status.self_repairing:
            raise InvalidActionException("Cannot start cleaning while draining or self repairing/testing")

        if not isinstance(zones, list) or not zones:
            raise InvalidActionException(f"Invalid zone coordinates: {zones}")

        if not isinstance(zones[0], list):
            zones = [zones]

        if suction_level is None or suction_level == "":
            suction_level = self.status.suction_level.value
        else:
            first_suction = suction_level[0] if isinstance(suction_level, list) and suction_level else suction_level
            self._update_suction_level(first_suction)

        if water_volume is None or water_volume == "":
            water_volume = self.status.water_volume.value
        else:
            first_water = water_volume[0] if isinstance(water_volume, list) and water_volume else water_volume
            self._update_water_level(int(first_water))

        if cleaning_times is None or cleaning_times == "":
            cleaning_times = 1

        cleanlist = []
        index = 0
        for zone in zones:
            if not isinstance(zone, list) or len(zone) != 4:
                raise InvalidActionException(f"Invalid zone coordinates: {zone}")

            if isinstance(cleaning_times, list):
                if index < len(cleaning_times):
                    repeat = cleaning_times[index]
                else:
                    repeat = 1
            else:
                repeat = cleaning_times

            if isinstance(suction_level, list):
                if index < len(suction_level):
                    fan = suction_level[index]
                else:
                    fan = self.status.suction_level.value
            else:
                fan = suction_level

            if isinstance(water_volume, list):
                if index < len(water_volume):
                    water = water_volume[index]
                else:
                    if self.capability.self_wash_base:
                        water = self.status.mop_pad_humidity
                    else:
                        water = self.status.water_volume.value
            else:
                water = water_volume

            index = index + 1

            x_coords = sorted([zone[0], zone[2]])
            y_coords = sorted([zone[1], zone[3]])

            size = (
                (self.status.current_map.dimensions.grid_size * 2)
                if self.status.current_map and self.status.current_map.dimensions
                else 100
            )
            w = (x_coords[1] - x_coords[0]) / size
            h = (y_coords[1] - y_coords[0]) / size

            if h <= 1.0 or w <= 1.0:
                raise InvalidActionException(f"Zone {index} is smaller than minimum zone size ({h}, {w})")

            cleanlist.append(
                [
                    int(round(zone[0])),
                    int(round(zone[1])),
                    int(round(zone[2])),
                    int(round(zone[3])),
                    max(1, repeat),
                    fan,
                    water,
                ]
            )

        self.schedule_update(10, True)
        if not self.capability.cruising:
            self._restore_go_to_zone()

        if self.status.cleangenius_cleaning:
            self._previous_cleangenius = self.get_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS)
            self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS, DreameVacuumCleanGenius.OFF.value)
        else:
            self._previous_cleangenius = None

        if not self.status.started or self.status.paused:
            self._update_status(DreameVacuumTaskStatus.ZONE_CLEANING, DreameVacuumStatus.ZONE_CLEANING)

            if self._map_manager:
                # Set active areas on current map data is implemented on the app
                if not self.status.started:
                    self._map_manager.editor.clear_path()
                self._map_manager.editor.set_active_areas(zones)

        return self.start_custom(
            DreameVacuumStatus.ZONE_CLEANING.value,
            str(json.dumps({"areas": cleanlist}, separators=(",", ":"))).replace(" ", ""),
        )

    def clean_segment(
        self,
        selected_segments: Any,
        cleaning_times: Any = None,
        suction_level: Any = None,
        water_volume: Any = None,
        timestamp: Any = None,
    ) -> dict[str, Any] | None:
        """Clean selected segment using id."""
        if self.status.draining or self.status.self_repairing:
            raise InvalidActionException("Cannot start cleaning while draining or self repairing/testing")

        if self.status.current_map and not self.status.has_saved_map:
            raise InvalidActionException("Cannot clean segments on current map")

        if not isinstance(selected_segments, list):
            selected_segments = [selected_segments]

        if suction_level is None or suction_level == "":
            suction_level = self.status.suction_level.value

        if water_volume is None or water_volume == "":
            water_volume = self.status.water_volume.value

        if cleaning_times is None or cleaning_times == "":
            cleaning_times = 1

        cleanlist = []
        index = 0
        segments = self.status.current_segments

        for segment_id in selected_segments:
            if isinstance(cleaning_times, list):
                if index < len(cleaning_times):
                    repeat = cleaning_times[index]
                else:
                    if segments and segment_id in segments and self.status.customized_cleaning:
                        repeat = segments[segment_id].cleaning_times
                    else:
                        repeat = 1
            else:
                repeat = cleaning_times

            if isinstance(suction_level, list):
                if index < len(suction_level):
                    fan = suction_level[index]
                elif segments and segment_id in segments and self.status.customized_cleaning:
                    fan = segments[segment_id].suction_level
                else:
                    fan = self.status.suction_level.value
            else:
                fan = suction_level

            if isinstance(water_volume, list):
                if index < len(water_volume):
                    water = water_volume[index]
                elif segments and segment_id in segments and self.status.customized_cleaning:
                    water = segments[segment_id].water_volume
                else:
                    if self.capability.self_wash_base:
                        water = self.status.mop_pad_humidity
                    else:
                        water = self.status.water_volume.value
            else:
                water = water_volume

            index = index + 1
            cleanlist.append(
                [segment_id, max(1, repeat), fan, water, 1 if self.capability.customized_cleaning else index]
            )  ## Sending index other than 1 breaks the operation of 5th gen devices

        self.schedule_update(10, True)
        if not self.status.started or self.status.paused:
            self._update_status(
                DreameVacuumTaskStatus.SEGMENT_CLEANING,
                DreameVacuumStatus.SEGMENT_CLEANING,
            )

            if self._map_manager:
                if not self.status.started:
                    self._map_manager.editor.clear_path()

                # Set active segments on current map data is implemented on the app
                self._map_manager.editor.set_active_segments(selected_segments)

        data: dict[str, Any] = {"selects": cleanlist}
        if timestamp is not None:
            data["timestamp"] = timestamp

        return self.start_custom(
            DreameVacuumStatus.SEGMENT_CLEANING.value,
            str(json.dumps(data, separators=(",", ":"))).replace(" ", ""),
        )

    def clean_spot(
        self,
        points: Any,
        cleaning_times: Any,
        suction_level: Any,
        water_volume: Any,
    ) -> dict[str, Any] | None:
        """Clean 1.5 square meters area of selected points."""
        if self.status.draining or self.status.self_repairing:
            raise InvalidActionException("Cannot start cleaning while draining or self repairing/testing")

        if not isinstance(points, list) or not points:
            raise InvalidActionException(f"Invalid point coordinates: {points}")

        if not isinstance(points[0], list):
            points = [points]

        if suction_level is None or suction_level == "":
            suction_level = self.status.suction_level.value
        else:
            first_suction = suction_level[0] if isinstance(suction_level, list) and suction_level else suction_level
            self._update_suction_level(first_suction)

        if water_volume is None or water_volume == "":
            water_volume = self.status.water_volume.value
        else:
            first_water = water_volume[0] if isinstance(water_volume, list) and water_volume else water_volume
            self._update_water_level(int(first_water))

        if cleaning_times is None or cleaning_times == "":
            cleaning_times = 1

        cleanlist = []
        index = 0
        for point in points:
            if isinstance(cleaning_times, list):
                if index < len(cleaning_times):
                    repeat = cleaning_times[index]
                else:
                    repeat = 1
            else:
                repeat = cleaning_times

            if isinstance(suction_level, list):
                if index < len(suction_level):
                    fan = suction_level[index]
                else:
                    fan = self.status.suction_level.value
            else:
                fan = suction_level

            if isinstance(water_volume, list):
                if index < len(water_volume):
                    water = water_volume[index]
                else:
                    if self.capability.self_wash_base:
                        water = self.status.mop_pad_humidity
                    else:
                        water = self.status.water_volume.value
            else:
                water = water_volume

            index = index + 1

            if self.status.current_map and not self.status.current_map.check_point(point[0], point[1]):
                raise InvalidActionException(f"Coordinate ({point[0]}, {point[1]}) is not inside the map")

            cleanlist.append(
                [
                    int(round(point[0])),
                    int(round(point[1])),
                    repeat,
                    fan,
                    water,
                ]
            )

        self.schedule_update(10, True)

        if self.status.cleangenius_cleaning:
            self._previous_cleangenius = self.get_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS)
            self.set_auto_switch_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS, DreameVacuumCleanGenius.OFF.value)
        else:
            self._previous_cleangenius = None

        if not self.status.started or self.status.paused:
            self._update_status(DreameVacuumTaskStatus.SPOT_CLEANING, DreameVacuumStatus.SPOT_CLEANING)

            if self._map_manager:
                if not self.status.started:
                    self._map_manager.editor.clear_path()

                # Set active points on current map data is implemented on the app
                self._map_manager.editor.set_active_points(points)

        return self.start_custom(
            DreameVacuumStatus.SPOT_CLEANING.value,
            str(json.dumps({"points": cleanlist}, separators=(",", ":"))).replace(" ", ""),
        )

    def go_to(self, x: Any, y: Any) -> dict[str, Any] | None:
        """Go to a point and take pictures around."""
        if self.status.draining or self.status.self_repairing:
            raise InvalidActionException("Cannot go to point while draining or self repairing/testing")

        if self.status.current_map and not self.status.current_map.check_point(x, y):
            raise InvalidActionException("Coordinate is not inside the map")

        if self.status.battery_level < 15:
            raise InvalidActionException(
                "Low battery capacity. Please start the robot for working after it being fully charged."
            )

        if not self.capability.cruising:
            size = (
                (self.status.current_map.dimensions.grid_size * 2)
                if self.status.current_map and self.status.current_map.dimensions
                else 100
            )
            if self.status.current_map and self.status.current_map.robot_position:
                position = self.status.current_map.robot_position
                if abs(x - position.x) <= size and abs(y - position.y) <= size:
                    raise InvalidActionException("Robot is already on selected coordinate")
            self._set_go_to_zone(x, y, size)
            size = int(size / 2)
            zone = [
                x - size,
                y - size,
                x + size,
                y + size,
            ]

        if not (self.status.started or self.status.paused):
            if not self.capability.cruising and self.status.cleangenius_cleaning:
                self._previous_cleangenius = self.get_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS)
                self.set_auto_switch_property(
                    DreameVacuumAutoSwitchProperty.CLEANGENIUS, DreameVacuumCleanGenius.OFF.value
                )
            else:
                self._previous_cleangenius = None

            self._update_property(DreameVacuumProperty.STATE, DreameVacuumState.MONITORING.value)
            self._update_property(DreameVacuumProperty.STATUS, DreameVacuumStatus.CRUISING_POINT.value)
            self._update_property(
                DreameVacuumProperty.TASK_STATUS,
                DreameVacuumTaskStatus.CRUISING_POINT.value,
            )

            if self._map_manager:
                # Set active cruise points on current map data is implemented on the app
                self._map_manager.editor.set_cruise_points([[x, y, 0, 0]])

        if self.capability.cruising:
            return self.start_custom(
                DreameVacuumStatus.CRUISING_POINT.value,
                str(
                    json.dumps(
                        {"tpoint": [[x, y, 0, 0]]},
                        separators=(",", ":"),
                    )
                ).replace(" ", ""),
            )
        cleanlist = [
            int(round(zone[0])),
            int(round(zone[1])),
            int(round(zone[2])),
            int(round(zone[3])),
            1,
            0,
            1,
        ]

        response = self.start_custom(
            DreameVacuumStatus.ZONE_CLEANING.value,
            str(json.dumps({"areas": [cleanlist]}, separators=(",", ":"))).replace(" ", ""),
        )
        if not response:
            self._restore_go_to_zone()

        return response

    def follow_path(self, points: Any) -> dict[str, Any] | None:
        """Start a surveillance job."""
        if not self.capability.cruising:
            raise InvalidActionException("Follow path is not supported on this device")

        if self.status.stream_status != DreameVacuumStreamStatus.IDLE:
            raise InvalidActionException("Follow path only works with live camera streaming")

        if self.status.draining or self.status.self_repairing:
            raise InvalidActionException("Cannot follow path while draining or self repairing/testing")

        if self.status.battery_level < 15:
            raise InvalidActionException(
                "Low battery capacity. Please start the robot for working after it being fully charged."
            )

        if not points:
            points = []

        if points and not isinstance(points[0], list):
            points = [points]

        if self.status.current_map:
            for point in points:
                if not self.status.current_map.check_point(point[0], point[1]):
                    raise InvalidActionException(f"Coordinate ({point[0]}, {point[1]}) is not inside the map")

        path = []
        for point in points:
            path.append([int(round(point[0])), int(round(point[1])), 0, 1])

        predefined_points = []
        if self.status.current_map and self.status.current_map.predefined_points:
            for point in self.status.current_map.predefined_points.values():
                predefined_points.append([int(round(point.x)), int(round(point.y)), 0, 1])

        if len(path) == 0:
            path.extend(predefined_points)

        if len(path) == 0:
            raise InvalidActionException("At least one valid or saved coordinate is required")

        if not self.status.started or self.status.paused:
            self._update_property(DreameVacuumProperty.STATE, DreameVacuumState.MONITORING.value)
            self._update_property(DreameVacuumProperty.STATUS, DreameVacuumStatus.CRUISING_PATH.value)
            self._update_property(
                DreameVacuumProperty.TASK_STATUS,
                DreameVacuumTaskStatus.CRUISING_PATH.value,
            )

            if self._map_manager:
                # Set active cruise points on current map data is implemented on the app
                self._map_manager.editor.set_cruise_points(path[:20])

        return self.start_custom(
            DreameVacuumStatus.CRUISING_PATH.value,
            str(
                json.dumps(
                    {"tpoint": path[:20]},
                    separators=(",", ":"),
                )
            ).replace(" ", ""),
        )

    def start_shortcut(self, shortcut_id: int) -> dict[str, Any] | None:
        """Start shortcut job."""
        if not self.capability.shortcuts and not self.status.shortcuts:
            raise InvalidActionException("Shortcuts are not supported on this device")

        if shortcut_id < 32 or shortcut_id > 128:
            raise InvalidActionException(f"Invalid shortcut ID: {shortcut_id}")

        if self.status.draining or self.status.self_repairing:
            raise InvalidActionException("Cannot start cleaning while draining or self repairing/testing")

        if not self.status.started:
            if self.status.status is DreameVacuumStatus.STANDBY:
                self._update_property(DreameVacuumProperty.STATE, DreameVacuumState.IDLE.value)

            self._update_property(DreameVacuumProperty.STATUS, DreameVacuumStatus.SEGMENT_CLEANING.value)
            self._update_property(
                DreameVacuumProperty.TASK_STATUS,
                DreameVacuumTaskStatus.AUTO_CLEANING.value,
            )

        if self.status.shortcuts and shortcut_id in self.status.shortcuts:
            self.status.shortcuts[shortcut_id].running = True

        return self.start_custom(
            DreameVacuumStatus.SHORTCUT.value,
            str(shortcut_id),
        )

    def start_fast_mapping(self) -> dict[str, Any] | None:
        """Fast map."""
        if self.status.fast_mapping:
            return None

        if self.status.battery_level < 15:
            raise InvalidActionException(
                "Low battery capacity. Please start the robot for working after it being fully charged."
            )

        if self.status.water_tank_or_mop_installed and not self.capability.mop_pad_lifting:
            raise InvalidActionException("Please make sure the mop pad is not installed before fast mapping.")

        self.schedule_update(10, True)
        self._update_status(DreameVacuumTaskStatus.FAST_MAPPING, DreameVacuumStatus.FAST_MAPPING)

        if self._map_manager:
            self._map_manager.editor.reset_map()

        return self.start_custom(DreameVacuumStatus.FAST_MAPPING.value)

    def start_mapping(self) -> dict[str, Any] | None:
        """Create a new map by cleaning whole floor."""
        self.schedule_update(10, True)
        self._update_status(DreameVacuumTaskStatus.AUTO_CLEANING, DreameVacuumStatus.CLEANING)

        if self._map_manager:
            self._map_manager.editor.reset_map()

        return self.start_custom(DreameVacuumStatus.CLEANING.value, "3")

    def start_self_wash_base(self, parameters: Any = None) -> dict[str, Any] | None:
        """Start self-wash base for cleaning or drying the mop."""
        if not self.capability.self_wash_base:
            return None

        if self.info and self.info.version <= 1037:
            parameters = None

        payload = None
        if parameters is not None:
            payload = [
                {
                    "piid": PIID(DreameVacuumProperty.CLEANING_PROPERTIES, self.property_mapping),
                    "value": parameters,
                }
            ]
        return self.call_action(DreameVacuumAction.START_WASHING, payload)

    def toggle_washing(self) -> dict[str, Any] | None:
        """Toggle washing the mop if self-wash base is present."""
        if self.status.washing:
            return self.pause_washing()
        return self.start_washing()

    def start_washing(self) -> dict[str, Any] | None:
        """Start washing the mop if self-wash base is present."""
        if self.status.washing_paused:
            self._update_property(
                DreameVacuumProperty.SELF_WASH_BASE_STATUS,
                DreameVacuumSelfWashBaseStatus.WASHING.value,
            )
            if self.info and self.info.version <= 1037:
                return self.start()
            return self.start_self_wash_base("1,1")
        if self.status.washing_available or self.status.returning_to_wash_paused:
            self._update_property(
                DreameVacuumProperty.SELF_WASH_BASE_STATUS,
                DreameVacuumSelfWashBaseStatus.WASHING.value,
            )
            return self.start_self_wash_base("2,1")
        return None

    def pause_washing(self) -> dict[str, Any] | None:
        """Pause washing the mop if self-wash base is present."""
        if self.status.washing:
            self._update_property(
                DreameVacuumProperty.SELF_WASH_BASE_STATUS,
                DreameVacuumSelfWashBaseStatus.PAUSED.value,
            )
            if self.info and self.info.version <= 1037:
                return self.pause()
            return self.start_self_wash_base("1,0")
        return None

    def toggle_drying(self) -> dict[str, Any] | None:
        """Toggle drying the mop if self-wash base is present."""
        if self.status.drying_available and self.status.drying:
            return self.stop_drying()
        return self.start_drying()

    def start_drying(self) -> dict[str, Any] | None:
        """Start drying the mop if self-wash base is present."""
        if self.status.drying_available and not self.status.drying:
            self._update_property(
                DreameVacuumProperty.SELF_WASH_BASE_STATUS,
                DreameVacuumSelfWashBaseStatus.DRYING.value,
            )
            return self.start_self_wash_base("3,1")
        return None

    def stop_drying(self) -> dict[str, Any] | None:
        """Stop drying the mop if self-wash base is present."""
        if self.status.drying_available and self.status.drying:
            self._update_property(
                DreameVacuumProperty.SELF_WASH_BASE_STATUS,
                DreameVacuumSelfWashBaseStatus.IDLE.value,
            )
            return self.start_self_wash_base("3,0")
        return None

    def start_draining(self, clean_water_tank: bool = False) -> dict[str, Any] | None:
        """Start draining water if self-wash base is present."""
        if clean_water_tank:
            if self.capability.empty_water_tank:
                return self.start_self_wash_base("9,1")
        if self.status.washing_available and self.status.drying_available:
            return self.start_self_wash_base("7,1")
        return None

    def start_self_repairing(self) -> dict[str, Any] | None:
        """Start self repairing if self-wash base is present."""
        if not self.status.draining and not self.status.self_repairing:
            current_status = self.status.status
            self.schedule_update(10)
            self._update_property(DreameVacuumProperty.STATUS, DreameVacuumStatus.SELF_REPAIR.value)
            mapping = self.property_mapping[DreameVacuumProperty.SELF_TEST_STATUS]
            result = self._protocol.set_property(mapping["siid"], mapping["piid"], '{"bittest":[17,0]}')

            self.schedule_update(3)
            if result is None or not result or result[0].get("code") != 0:
                _LOGGER.error("Start self repairing failed")
                self._update_property(DreameVacuumProperty.STATUS, current_status)
                raise InvalidActionException("Start self repairing failed")
            return cast("dict[str, Any] | None", result)
        return None

    def start_station_cleaning(self) -> dict[str, Any] | None:
        """Start base station cleaning if self-wash base is present."""
        if (
            self.capability.station_cleaning
            and not self.status.draining
            and not self.status.self_repairing
            and not self.status.station_cleaning
        ):
            current_status = self.status.task_status
            self.schedule_update(10)
            self._update_property(DreameVacuumProperty.TASK_STATUS, DreameVacuumTaskStatus.STATION_CLEANING.value)
            result: Any = self.start_self_wash_base("5,1")
            self.schedule_update(3)
            if result is None or not result or result[0].get("code") != 0:
                _LOGGER.error("Start base station cleaning failed")
                self._update_property(DreameVacuumProperty.TASK_STATUS, current_status)
                raise InvalidActionException("Start base station cleaning failed")
            return cast("dict[str, Any] | None", result)
        return None

    def start_recleaning(self) -> dict[str, Any] | None:
        """Start self repairing if dirty areas or neglected rooms are present."""
        if self.capability.auto_recleaning and self.status._cleaning_history and self.status.current_map:
            history = self.status._cleaning_history[0]
            map_data = self.status._history_map_data.get(history.object_name) if history.object_name else None
            if map_data and self.status.current_map.map_id == map_data.map_id:
                neglected: Any = map_data.neglected_segments
                timestamp = history.multiple_cleaning_time if history.multiple_cleaning_time else ""
                if history.cleanup_method != CleanupMethod.CLEANGENIUS and not map_data.cleaned_segments and neglected:
                    return self.clean_segment(neglected.keys(), timestamp=timestamp)
                data: dict[str, Any] = {
                    "MopAgain": map_data.dos if map_data.dos is not None else 1,
                    "timestamp": timestamp,
                    "CleanArea": map_data.cleaned_segments if map_data.cleaned_segments else [],
                    "BigArea": neglected.keys() if neglected else [],
                }
                self.schedule_update(10, True)
                self._update_property(
                    DreameVacuumProperty.STATE,
                    DreameVacuumState.SECOND_CLEANING.value,
                )
                self._update_property(DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value)
                self._update_property(
                    DreameVacuumProperty.TASK_STATUS,
                    DreameVacuumStatus.CLEANING.value,
                )
                return self.start_custom(
                    DreameVacuumStatus.CLEANING.value,
                    str(json.dumps(data, separators=(",", ":"))).replace(" ", ""),
                )
        return None

    def reload_shortcuts(self) -> None:
        shortcuts = self.get_property(DreameVacuumProperty.SHORTCUTS)
        if shortcuts and shortcuts != "":
            shortcuts = json.loads(shortcuts)
            if shortcuts:
                new_shortcuts = {}
                for shortcut in shortcuts:
                    id = shortcut["id"]
                    running = (
                        False if "state" not in shortcut else bool(shortcut["state"] == "0" or shortcut["state"] == "1")
                    )
                    name = base64.decodebytes(shortcut["name"].encode("utf8")).decode("utf-8")
                    new_shortcuts[id] = Shortcut(id=id, name=name, running=running)
                self.status.shortcuts = new_shortcuts
                self._property_changed()

                def callback(response: Any) -> None:
                    detail = {}
                    if response and "out" in response:
                        data = response["out"]
                        if data and len(data):
                            if "value" in data[0] and data[0]["value"] != "":
                                for task in json.loads(data[0]["value"]):
                                    detail[task["id"]] = task["mapId"]

                    new_shortcuts = {}
                    for shortcut in shortcuts:
                        id = shortcut["id"]
                        running = (
                            False
                            if "state" not in shortcut
                            else bool(shortcut["state"] == "0" or shortcut["state"] == "1")
                        )
                        name = base64.decodebytes(shortcut["name"].encode("utf8")).decode("utf-8")
                        map_id = detail[id] if id in detail else None
                        tasks = None
                        response = self.call_shortcut_action("GET_COMMAND_BY_ID", {"id": id})
                        if response and "out" in response:
                            data = response["out"]
                            if data and len(data):
                                if "value" in data[0] and data[0]["value"] != "":
                                    tasks = []
                                    for task in json.loads(data[0]["value"]):
                                        segments = []
                                        for segment in task:
                                            segments.append(
                                                ShortcutTask(
                                                    segment_id=segment[0],
                                                    suction_level=segment[1],
                                                    water_volume=segment[2],
                                                    cleaning_times=segment[3],
                                                    cleaning_mode=segment[4],
                                                )
                                            )
                                        tasks.append(segments)
                        new_shortcuts[id] = Shortcut(id=id, name=name, map_id=map_id, running=running, tasks=tasks)
                    self.status.shortcuts = new_shortcuts
                    self._property_changed()

                self.call_shortcut_action_async(callback, "GET_COMMANDS")

    def clear_warning(self) -> bool | dict[str, Any] | None:
        """Clear warning error code from the vacuum cleaner."""
        if self.status.draining_complete:
            return self.set_property(DreameVacuumProperty.DRAINAGE_STATUS, 0)
        if self.status.has_warning:
            return self.call_action(
                DreameVacuumAction.CLEAR_WARNING,
                [
                    {
                        "piid": PIID(
                            DreameVacuumProperty.CLEANING_PROPERTIES,
                            self.property_mapping,
                        ),
                        "value": f"[{self.status.error.value}]",
                    }
                ],
            )
        return self.clear_low_water_warning()

    def clear_low_water_warning(self) -> bool | dict[str, Any] | None:
        """Clear low water warning error code from the vacuum cleaner."""
        if self.status.low_water:
            return self.set_property(DreameVacuumProperty.LOW_WATER_WARNING, 1)
        return None

    def remote_control_move_step(
        self, rotation: int = 0, velocity: int = 0, prompt: bool | None = None
    ) -> dict[str, Any] | None:
        """Send remote control command to device."""
        if self.status.fast_mapping:
            raise InvalidActionException("Cannot remote control vacuum while fast mapping")

        if self.status.washing:
            raise InvalidActionException("Cannot remote control vacuum while self-wash base is running")

        payload = '{"spdv":%(velocity)d,"spdw":%(rotation)d,"audio":"%(audio)s","random":%(random)d}' % {
            "velocity": velocity,
            "rotation": rotation,
            "audio": (
                "true"
                if prompt
                else (
                    "false"
                    if not prompt or self._remote_control or self.status.status is DreameVacuumStatus.SLEEPING
                    else "true"
                )
            ),
            "random": randrange(65535),
        }
        self._remote_control = True
        mapping = self.property_mapping[DreameVacuumProperty.REMOTE_CONTROL]
        return cast("dict[str, Any] | None", self._protocol.set_property(mapping["siid"], mapping["piid"], payload, 1))

    def install_voice_pack(self, lang_id: int, url: str, md5: str, size: int) -> dict[str, Any] | None:
        """install a custom language pack"""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise InvalidValueException(f"install_voice_pack: URL must be http(s) with a host, got {url!r}")
        if not re.fullmatch(r"[A-Fa-f0-9]{32}", md5 or ""):
            raise InvalidValueException("install_voice_pack: md5 must be a 32-char hex digest")
        payload = json.dumps(
            {"id": str(lang_id), "url": url, "md5": md5, "size": int(size)},
            separators=(",", ":"),
        )
        mapping = self.property_mapping[DreameVacuumProperty.VOICE_CHANGE]
        return cast("dict[str, Any] | None", self._protocol.set_property(mapping["siid"], mapping["piid"], payload, 3))

    def obstacle_image(self, index: Any) -> Any:
        mgr: Any = self._map_manager
        if self.capability.map and self.status.current_map and mgr:
            map_data = self.status.current_map
            if map_data:
                return mgr.get_obstacle_image(map_data, index)
        return (None, None)

    def obstacle_history_image(self, index: Any, history_index: Any, cruising: bool = False) -> Any:
        mgr: Any = self._map_manager
        if self.capability.map and mgr:
            map_data = self.history_map(history_index, cruising)
            if map_data:
                return mgr.get_obstacle_image(map_data, index)
        return (None, None)

    def history_map(self, index: Any, cruising: bool = False) -> Any:
        mgr: Any = self._map_manager
        if self.capability.map and index and str(index).isnumeric() and mgr:
            item = None
            if cruising:
                if self.status._cruising_history and len(self.status._cruising_history) > int(index) - 1:
                    item = self.status._cruising_history[int(index) - 1]
            else:
                if self.status._cleaning_history and len(self.status._cleaning_history) > int(index) - 1:
                    item = self.status._cleaning_history[int(index) - 1]
            if item and item.object_name:
                if item.object_name not in self.status._history_map_data:
                    map_data = mgr.get_history_map(item.object_name, item.key)
                    if map_data is None:
                        return None
                    map_data.last_updated = item.date.timestamp()
                    map_data.completed = item.completed
                    map_data.neglected_segments = item.neglected_segments
                    map_data.second_cleaning = item.second_cleaning
                    map_data.cleaned_area = item.cleaned_area
                    map_data.cleaning_time = item.cleaning_time
                    if item.cleanup_method is not None:
                        map_data.cleanup_method = item.cleanup_method
                    if map_data.cleaning_map_data:
                        map_data.cleaning_map_data.last_updated = item.date.timestamp()
                        map_data.cleaning_map_data.completed = item.completed
                        map_data.cleaning_map_data.neglected_segments = item.neglected_segments
                        map_data.cleaning_map_data.second_cleaning = item.second_cleaning
                        map_data.cleaning_map_data.cleaned_area = item.cleaned_area
                        map_data.cleaning_map_data.cleaning_time = item.cleaning_time
                        map_data.cleaning_map_data.cleanup_method = map_data.cleanup_method
                    self.status._history_map_data[item.object_name] = map_data
                return self.status._history_map_data[item.object_name]
        return None

    def recovery_map(self, map_id: Any, index: Any) -> Any:
        mgr: Any = self._map_manager
        if self.capability.map and map_id and index and str(index).isnumeric() and mgr:
            if (map_id is None or map_id == "") and self.status.selected_map:
                map_id = self.status.selected_map.map_id

            return mgr.get_recovery_map(map_id, index)
        return None

    def recovery_map_file(self, map_id: Any, index: Any) -> Any:
        mgr: Any = self._map_manager
        if self.capability.map and map_id and index and str(index).isnumeric() and mgr:
            if (map_id is None or map_id == "") and self.status.selected_map:
                map_id = self.status.selected_map.map_id

            return mgr.get_recovery_map_file(map_id, index)
        return None

    def rename_shortcut(self, shortcut_id: int, shortcut_name: str = "") -> dict[str, Any] | None:
        """Rename a shortcut"""
        if self.status.started:
            raise InvalidActionException("Cannot rename a shortcut while vacuum is running")

        if not self.capability.shortcuts or not self.status.shortcuts:
            raise InvalidActionException("Shortcuts are not supported on this device")

        if shortcut_id not in self.status.shortcuts:
            raise InvalidActionException(f"Shortcut {shortcut_id} not found")

        if shortcut_name and len(shortcut_name) > 0:
            current_name = self.status.shortcuts[shortcut_id]
            if current_name != shortcut_name:
                counter = 1
                for _id, shortcut in self.status.shortcuts.items():
                    if shortcut.name == shortcut_name and shortcut.id != shortcut_id:
                        counter = counter + 1

                if counter > 1:
                    shortcut_name = f"{shortcut_name}{counter}"

                self.status.shortcuts[shortcut_id].name = shortcut_name
                shortcut_name = base64.b64encode(shortcut_name.encode("utf-8")).decode("utf-8")
                shortcuts = self.get_property(DreameVacuumProperty.SHORTCUTS)
                if shortcuts and shortcuts != "":
                    shortcuts = json.loads(shortcuts)
                    if shortcuts:
                        for shortcut in shortcuts:
                            if shortcut["id"] == shortcut_id:
                                shortcut["name"] = shortcut_name
                                break
                self._update_property(
                    DreameVacuumProperty.SHORTCUTS,
                    str(json.dumps(shortcuts, separators=(",", ":"))).replace(" ", ""),
                )
                self._property_changed(False)

                success = False
                response = self.call_shortcut_action(
                    "EDIT_COMMAND",
                    {"id": shortcut_id, "name": shortcut_name, "type": 3},
                )
                if response and "out" in response:
                    data = response["out"]
                    if data and len(data):
                        if "value" in data[0] and data[0]["value"] != "":
                            success = data[0]["value"] == "0"
                if not success:
                    self.status.shortcuts[shortcut_id].name = current_name
                    self._property_changed(False)
                return response
        return None
