"""Dreame Vacuum device map operations mixin."""

from __future__ import annotations

import copy
import json
import logging
import time
from typing import Any, cast

from ._device_base import DreameVacuumDeviceState
from .exceptions import (
    InvalidActionException,
    InvalidValueException,
)
from .vacuum_types import (
    PIID,
    CleanupMethod,
    Coordinate,
    DreameVacuumAction,
    DreameVacuumCleaningMode,
    DreameVacuumMapBackupStatus,
    DreameVacuumMapRecoveryStatus,
    DreameVacuumProperty,
    DreameVacuumTaskStatus,
    GoToZoneSettings,
    MapData,
    ObstacleType,
    Path,
    PathType,
    RobotType,
)

_LOGGER = logging.getLogger(__name__)


class DreameVacuumDeviceMapMixin(DreameVacuumDeviceState):
    """Mixin providing map operations for DreameVacuumDevice."""

    def _map_property_changed(self, previous_property: Any = None) -> None:
        """Update last update time of the map when a property associated with rendering map changed."""
        if self._map_manager and previous_property is not None:
            self._map_manager.editor.refresh_map()

    def _map_list_changed(self, previous_map_list: Any = None) -> None:
        """Update map list object name on map manager map list property when changed"""
        if self._map_manager:
            map_list = self.get_property(DreameVacuumProperty.MAP_LIST)
            if map_list and map_list != "":
                try:
                    map_list = json.loads(map_list)
                    object_name = map_list.get("object_name")
                    if object_name is None:
                        object_name = map_list.get("obj_name")
                    if object_name and object_name != "":
                        _LOGGER.debug("Property MAP_LIST Changed: %s", object_name)
                        self._map_manager.set_map_list_object_name(object_name, map_list.get("md5"))
                    else:
                        self._last_map_list_request = 0
                except (json.JSONDecodeError, ValueError, AttributeError, TypeError):
                    _LOGGER.debug("MAP_LIST payload parse failed", exc_info=True)

    def _recovery_map_list_changed(self, previous_recovery_map_list: Any = None) -> None:
        """Update recovery list object name on map manager recovery list property when changed"""
        if self._map_manager:
            map_list = self.get_property(DreameVacuumProperty.RECOVERY_MAP_LIST)
            if map_list and map_list != "":
                try:
                    map_list = json.loads(map_list)
                    object_name = map_list.get("object_name")
                    if object_name is None:
                        object_name = map_list.get("obj_name")
                    if object_name and object_name != "":
                        self._map_manager.set_recovery_map_list_object_name(object_name)
                    else:
                        self._last_map_list_request = 0
                except (json.JSONDecodeError, ValueError, AttributeError, TypeError):
                    _LOGGER.debug("RECOVERY_MAP_LIST payload parse failed", exc_info=True)

    def _map_recovery_status_changed(self, previous_map_recovery_status: Any = None) -> None:
        if previous_map_recovery_status and self.status.map_recovery_status:
            if self.status.map_recovery_status == DreameVacuumMapRecoveryStatus.SUCCESS.value:
                if not self._protocol.dreame_cloud:
                    self._last_map_list_request = 0
                self._last_map_change_time = time.time()
                self._map_manager.request_next_map()
                self._map_manager.request_next_recovery_map_list()

            if self.status.map_recovery_status != DreameVacuumMapRecoveryStatus.RUNNING.value:
                self._request_properties([DreameVacuumProperty.MAP_RECOVERY_STATUS])

    def _map_backup_status_changed(self, previous_map_backup_status: Any = None) -> None:
        if previous_map_backup_status and self.status.map_backup_status:
            if self.status.map_backup_status == DreameVacuumMapBackupStatus.SUCCESS.value:
                if not self._protocol.dreame_cloud:
                    self._last_map_list_request = 0
                self._last_map_change_time = time.time()
                self._map_manager.request_next_recovery_map_list()
            if self.status.map_backup_status != DreameVacuumMapBackupStatus.RUNNING.value:
                self._request_properties([DreameVacuumProperty.MAP_BACKUP_STATUS])

    def _map_updated(self) -> None:
        """Call external listener when a map updated from local"""
        self._last_map_change_time = time.time()
        self._property_changed()

    def _map_changed(self, saved_map: Any) -> None:
        """Call external listener when a map changed"""
        map_data = self.status.current_map
        if self._map_select_time:
            self._map_select_time = None
        if not saved_map:
            self._last_map_change_time = time.time()
        if map_data and self.status.started:
            if self.status.go_to_zone is None and not self.status._capability.cruising and self.status.zone_cleaning:
                if map_data.active_areas and len(map_data.active_areas) == 1 and map_data.dimensions:
                    area = map_data.active_areas[0]
                    dimensions = map_data.dimensions
                    size = dimensions.grid_size * 2
                    if area.check_size(size):
                        new_cleaning_mode = None
                        if not (self.capability.self_wash_base or self.capability.mop_pad_lifting):
                            if (
                                self.status.cleaning_mode == DreameVacuumCleaningMode.MOPPING
                                and not self.status.water_tank_or_mop_installed
                            ):
                                new_cleaning_mode = DreameVacuumCleaningMode.SWEEPING.value
                            elif (
                                self.status.cleaning_mode == DreameVacuumCleaningMode.SWEEPING
                                and self.status.water_tank_or_mop_installed
                            ):
                                new_cleaning_mode = DreameVacuumCleaningMode.SWEEPING_AND_MOPPING.value

                        self.status.go_to_zone = GoToZoneSettings(
                            x=int(area.x0 + dimensions.grid_size),
                            y=int(area.y0 + dimensions.grid_size),
                            stop=bool(not self._map_manager.ready),
                            size=size,
                            cleaning_mode=new_cleaning_mode,
                        )
                        self._map_manager.editor.set_active_areas([])
                    else:
                        self.status.go_to_zone = False
                else:
                    self.status.go_to_zone = False

            if self.status.go_to_zone:
                position = map_data.robot_position
                if position:
                    size = self.status.go_to_zone.size
                    x = self.status.go_to_zone.x or 0
                    y = self.status.go_to_zone.y or 0
                    if (
                        position.x >= x - size
                        and position.x <= x + size
                        and position.y >= y - size
                        and position.y <= y + size
                    ):
                        self._restore_go_to_zone(True)

            if self.status.docked != map_data.docked and self._protocol.prefer_cloud:
                self.schedule_update(self._update_interval, True)

        if self._map_manager.ready:
            self._property_changed()

    def get_map_for_render(self, map_data: MapData) -> MapData | None:
        """Makes changes on map data for device related properties for renderer.
        Map manager does not need any device property for parsing and storing map data but map renderer does.
        For example if device is running but not mopping renderer does not show no mopping areas and this function handles that so renderer does not need device data too.
        """
        if map_data:
            if map_data.need_optimization:
                map_data = self._map_manager.optimizer.optimize(
                    map_data,
                    self._map_manager.selected_map if map_data.saved_map_status == 2 else None,
                )
                map_data.need_optimization = False

            render_map_data: Any = copy.deepcopy(map_data)
            if (
                not self.capability.lidar_navigation
                and self.status.docked
                and not self.status.started
                and map_data.saved_map_status == 1
            ):
                saved_map_data = self._map_manager.selected_map
                render_map_data.segments = copy.deepcopy(saved_map_data.segments)
                render_map_data.data = copy.deepcopy(saved_map_data.data)
                render_map_data.pixel_type = copy.deepcopy(saved_map_data.pixel_type)
                render_map_data.dimensions = copy.deepcopy(saved_map_data.dimensions)
                render_map_data.charger_position = copy.deepcopy(saved_map_data.charger_position)
                render_map_data.no_go_areas = saved_map_data.no_go_areas
                render_map_data.no_mopping_areas = saved_map_data.no_mopping_areas
                render_map_data.virtual_walls = saved_map_data.virtual_walls
                render_map_data.robot_position = render_map_data.charger_position
                render_map_data.docked = True
                render_map_data.path = None
                render_map_data.need_optimization = False
                render_map_data.saved_map_status = 2
                render_map_data.optimized_pixel_type = None
                render_map_data.optimized_charger_position = None

            if render_map_data.optimized_pixel_type is not None:
                render_map_data.pixel_type = render_map_data.optimized_pixel_type
                render_map_data.dimensions = render_map_data.optimized_dimensions
                if render_map_data.optimized_charger_position is not None:
                    render_map_data.charger_position = render_map_data.optimized_charger_position

                # if not self.status.started and render_map_data.docked and render_map_data.robot_position and render_map_data.charger_position:
                #    render_map_data.charger_position = copy.deepcopy(render_map_data.robot_position)

            if render_map_data.combined_pixel_type is not None:
                render_map_data.pixel_type = render_map_data.combined_pixel_type
                render_map_data.dimensions = render_map_data.combined_dimensions

            if self.capability.map_object_offset:
                offset = render_map_data.dimensions.grid_size / 2
                render_map_data.dimensions.left = render_map_data.dimensions.left - offset
                render_map_data.dimensions.top = render_map_data.dimensions.top - offset
            else:
                render_map_data.dimensions.top = render_map_data.dimensions.top - render_map_data.dimensions.grid_size

            if render_map_data.wifi_map:
                return cast("MapData | None", render_map_data)

            if render_map_data.furniture_version == 1 and self.capability.new_furnitures:
                render_map_data.furniture_version = 3 if self.capability.mijia else 2

            if not render_map_data.history_map:
                if self.status.started and not (
                    self.status.zone_cleaning
                    or self.status.go_to_zone
                    or (
                        render_map_data.active_areas
                        and self.status.task_status is DreameVacuumTaskStatus.DOCKING_PAUSED
                    )
                ):
                    # Map data always contains last active areas
                    render_map_data.active_areas = None

                if self.status.started and not self.status.spot_cleaning:
                    # Map data always contains last active points
                    render_map_data.active_points = None

                if not self.status.segment_cleaning:
                    # Map data always contains last active segments
                    render_map_data.active_segments = None

                if not self.status.cruising:
                    # Map data always contains last active path points
                    render_map_data.active_cruise_points = None

                if self.capability.camera_streaming and render_map_data.predefined_points is None:
                    render_map_data.predefined_points = []
            else:
                if not self.capability.camera_streaming:
                    if render_map_data.active_areas and len(render_map_data.active_areas) == 1:
                        area = render_map_data.active_areas[0]
                        size = render_map_data.dimensions.grid_size * 2
                        if area.check_size(size):
                            x = area.x0 + render_map_data.dimensions.grid_size
                            y = area.y0 + render_map_data.dimensions.grid_size
                            render_map_data.task_cruise_points = {
                                1: Coordinate(
                                    x,
                                    y,
                                    False,
                                    0,
                                )
                            }

                            if not render_map_data.completed:
                                if render_map_data.robot_position:
                                    render_map_data.completed = bool(
                                        render_map_data.robot_position.x >= x - size
                                        and render_map_data.robot_position.x <= x + size
                                        and render_map_data.robot_position.y >= y - size
                                        and render_map_data.robot_position.y <= y + size
                                    )
                                else:
                                    render_map_data.completed = True

                            render_map_data.active_areas = None

                if render_map_data.active_areas or render_map_data.active_points:
                    render_map_data.segments = None

                if render_map_data.customized_cleaning != 1:
                    render_map_data.cleanset = None

                if (
                    render_map_data.cleanup_method is None
                    or render_map_data.cleanup_method != CleanupMethod.CUSTOMIZED_CLEANING
                ):
                    render_map_data.cleanset = None

                if render_map_data.task_cruise_points:
                    render_map_data.active_cruise_points = render_map_data.task_cruise_points.copy()
                    render_map_data.task_cruise_points = True
                    render_map_data.active_areas = None
                    render_map_data.path = None
                    render_map_data.no_mopping_areas = None
                    render_map_data.cleanset = None
                    if render_map_data.furnitures is not None:
                        render_map_data.furnitures = {}

                if render_map_data.segments:
                    if render_map_data.task_cruise_points or (
                        render_map_data.cleanup_method is not None
                        and (
                            render_map_data.cleanup_method == CleanupMethod.CLEANGENIUS
                            and not self.capability.cleangenius_mode
                        )
                    ):
                        render_map_data.sequence = False
                    elif render_map_data.active_segments:
                        order = 1
                        render_map_data.sequence = True
                        for segment_id in sorted(
                            render_map_data.segments,
                            key=lambda segment_id: (
                                render_map_data.segments[segment_id].order
                                if render_map_data.segments[segment_id].order
                                else 99
                            ),
                        ):
                            if (
                                len(render_map_data.active_segments) > 1
                                and render_map_data.segments[segment_id].order
                                and segment_id in render_map_data.active_segments
                            ):
                                render_map_data.segments[segment_id].order = order
                                order = order + 1
                            else:
                                render_map_data.segments[segment_id].order = None

                    if self.capability.cleaning_route:
                        for k, v in render_map_data.segments.items():
                            render_map_data.segments[k].custom_mopping_route = None

                return cast("MapData | None", render_map_data)

            if not render_map_data.saved_map and not render_map_data.recovery_map:
                # if self.status.started and (self.status.sweeping or self.status.cruising):
                #    # App does not render no mopping areas when cleaning mode is sweeping
                #    render_map_data.no_mopping_areas = None

                if not self.status._capability.cruising:
                    if self.status.go_to_zone:
                        render_map_data.active_cruise_points = {
                            1: Coordinate(
                                self.status.go_to_zone.x or 0,
                                self.status.go_to_zone.y or 0,
                                False,
                                0,
                            )
                        }
                        render_map_data.active_areas = None
                        render_map_data.path = None

                    if render_map_data.active_areas and len(render_map_data.active_areas) == 1:
                        area = render_map_data.active_areas[0]
                        size = render_map_data.dimensions.grid_size * 2
                        if area.check_size(size):
                            if self.status.started and not self.status.go_to_zone and self.status.zone_cleaning:
                                render_map_data.active_cruise_points = {
                                    1: Coordinate(
                                        area.x0 + render_map_data.dimensions.grid_size,
                                        area.y0 + render_map_data.dimensions.grid_size,
                                        False,
                                        0,
                                    )
                                }
                            render_map_data.active_areas = None
                            render_map_data.path = None

                if not self.status.go_to_zone and (
                    (self.status.zone_cleaning and render_map_data.active_areas)
                    or (self.status.spot_cleaning and render_map_data.active_points)
                ):
                    # App does not render segments when zone or spot cleaning
                    render_map_data.segments = None

                # App does not render pet obstacles when pet detection turned off
                # App does not render stain obstacles when stain avoidance turned off
                if render_map_data.obstacles:
                    obstacles = copy.deepcopy(render_map_data.obstacles)
                    for k, v in obstacles.items():
                        if (
                            (v.type == ObstacleType.PET and self.status.ai_pet_detection == 0)
                            or (
                                self.capability.fluid_detection
                                and (
                                    v.type == ObstacleType.LIQUID_STAIN
                                    or v.type == ObstacleType.DRIED_STAIN
                                    or v.type == ObstacleType.DETECTED_STAIN
                                    or v.type == ObstacleType.MIXED_STAIN
                                )
                                and not self.status.ai_fluid_detection
                            )
                            or (v.picture_status is not None and v.picture_status.value == 0)
                        ):
                            del render_map_data.obstacles[k]

                if render_map_data.furnitures and self.status.ai_furniture_detection == 0:
                    render_map_data.furnitures = {}

                # App adds robot position to paths as last line when map data is line to robot
                if render_map_data.line_to_robot and render_map_data.path and render_map_data.robot_position:
                    render_map_data.path.append(
                        Path(
                            render_map_data.robot_position.x,
                            render_map_data.robot_position.y,
                            PathType.LINE,
                        )
                    )

            if not self.status.customized_cleaning or self.status.cruising or self.status.cleangenius_cleaning:
                # App does not render customized cleaning settings on saved map list
                render_map_data.cleanset = None
            elif (
                not render_map_data.saved_map
                and not render_map_data.recovery_map
                and render_map_data.cleanset is None
                and self.status.customized_cleaning
                and not self.status.cleangenius_cleaning
            ):
                from .map_decoder import DreameVacuumMapDecoder

                DreameVacuumMapDecoder.set_segment_cleanset(render_map_data, {}, self.capability)
                render_map_data.cleanset = True

            if render_map_data.segments:
                if not self.status.custom_order or render_map_data.saved_map or render_map_data.recovery_map:
                    render_map_data.sequence = False

                if self.capability.cleaning_route:
                    for k, v in render_map_data.segments.items():
                        render_map_data.segments[k].custom_mopping_route = None

            if render_map_data.robot_position:
                # Device currently may not be docked but map data can be old and still showing when robot is docked
                render_map_data.docked = bool(render_map_data.docked or self.status.docked)

            if (
                not self.capability.lidar_navigation
                and not render_map_data.saved_map
                and not render_map_data.recovery_map
                and render_map_data.saved_map_status == 1
                and render_map_data.docked
            ):
                # For correct scaling of vslam saved map
                render_map_data.saved_map_status = 2

            if (
                render_map_data.docked
                and render_map_data.robot_position
                and not render_map_data.saved_map
                and not render_map_data.recovery_map
            ):
                if render_map_data.charger_position is None:
                    if not self.status.multi_map:
                        render_map_data.charger_position = copy.deepcopy(render_map_data.robot_position)
                        if (
                            self.capability.robot_type != RobotType.MOPPING
                            and self.capability.robot_type != RobotType.SWEEPING_AND_MOPPING
                        ):
                            render_map_data.charger_position.a = render_map_data.robot_position.a + 180
                elif (
                    not self.status.docked
                    and not self.status.started
                    and render_map_data.robot_position.x == render_map_data.charger_position.x
                    and render_map_data.robot_position.y == render_map_data.charger_position.y
                ):
                    render_map_data.docked = False
                    render_map_data.robot_position = None

            if render_map_data.saved_map or render_map_data.recovery_map:
                render_map_data.active_areas = None
                render_map_data.active_points = None
                render_map_data.active_segments = None
                render_map_data.active_cruise_points = None
                render_map_data.path = None
                render_map_data.cleanset = None
            elif render_map_data.charger_position and render_map_data.docked and not self.status.fast_mapping:
                if not render_map_data.robot_position:
                    render_map_data.robot_position = copy.deepcopy(render_map_data.charger_position)
            return cast("MapData | None", render_map_data)
        return map_data

    def get_map(self, map_index: int) -> MapData | None:
        """Get stored map data by index from map manager."""
        if self._map_manager:
            if self.status.multi_map:
                return cast("MapData | None", self._map_manager.get_map(map_index))
            if map_index == 1:
                return cast("MapData | None", self._map_manager.selected_map)
            if map_index == 0:
                return self.status.current_map
        return None

    def update_map(self) -> None:
        """Trigger a map update.
        This function is used for requesting map data when a image request has been made to renderer
        """

        self._last_change = time.time()
        if self._map_manager:
            now = time.time()
            if now - self._last_map_request > 120:
                self._last_map_request = now
                self._map_manager.set_update_interval(self._map_update_interval)
                self._map_manager.schedule_update(0.01)

    def request_map(self) -> dict[str, Any] | None:
        """Send map request action to the device.
        Device will upload a new map on cloud after this command if it has a saved map on memory.
        Otherwise this action will timeout when device is spot cleaning or a restored map exists on memory.
        """

        if self._map_manager:
            return cast("dict[str, Any] | None", self._map_manager.request_new_map())
        return self.call_action(
            DreameVacuumAction.REQUEST_MAP,
            [
                {
                    "piid": PIID(DreameVacuumProperty.FRAME_INFO, self.property_mapping),
                    "value": '{"frame_type":"I"}',
                }
            ],
        )

    def update_map_data_async(self, parameters: dict[str, Any]) -> dict[str, Any] | None:
        """Send update map action to the device."""
        if self._map_manager:
            self._map_manager.schedule_update(10)
            self._property_changed(False)
            self._last_map_request = time.time()

        payload = [
            {
                "piid": PIID(DreameVacuumProperty.MAP_EXTEND_DATA, self.property_mapping),
                "value": str(json.dumps(parameters, separators=(",", ":"))),
            }
        ]

        def callback(result: Any) -> None:
            if result and result.get("code") == 0:
                _LOGGER.debug("Send action UPDATE_MAP_DATA async %s", payload)
                self._last_change = time.time()
            else:
                _LOGGER.error(
                    "Send action failed UPDATE_MAP_DATA async (%s): %s",
                    payload,
                    result,
                )

            self.schedule_update(5)

            if self._map_manager:
                if self._protocol.dreame_cloud:
                    self._map_manager.schedule_update(3)
                    self._map_manager.request_next_map_list()
                else:
                    self._last_map_change_time = self._last_change
                    self._map_manager.request_next_map(True)
                    self._map_manager.request_next_map_list()
                    self._last_map_list_request = 0

        mapping = self.action_mapping[DreameVacuumAction.UPDATE_MAP_DATA]
        self._protocol.action_async(callback, mapping["siid"], mapping["aiid"], payload)
        return None

    def update_map_data(self, parameters: dict[str, Any]) -> dict[str, Any] | None:
        """Send update map action to the device."""
        if self._map_manager:
            self._map_manager.schedule_update(10)
            self._property_changed(False)
            self._last_map_request = time.time()

        response = self.call_action(
            DreameVacuumAction.UPDATE_MAP_DATA,
            [
                {
                    "piid": PIID(DreameVacuumProperty.MAP_EXTEND_DATA, self.property_mapping),
                    "value": str(json.dumps(parameters, separators=(",", ":"))),
                }
            ],
        )

        self.schedule_update(5, True)

        if self._map_manager:
            if self._protocol.dreame_cloud:
                self._map_manager.schedule_update(3)
                self._map_manager.request_next_map_list()
            else:
                self._last_map_change_time = self._last_change
                self._map_manager.request_next_map(True)
                self._map_manager.request_next_map_list()
                self._last_map_list_request = 0

        return response

    def rename_map(self, map_id: int, map_name: str = "") -> dict[str, Any] | None:
        """Set custom name for a map"""
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot rename a map when temporary map is present")

        if map_name is None:
            map_name = ""

        if self._map_manager:
            map_data_list = self.status.map_data_list
            if not map_data_list or map_id not in map_data_list:
                raise InvalidActionException("Map not found! (%s)", map_id)
            self._map_manager.editor.set_map_name(map_id, map_name)
        return self.update_map_data_async({"nrism": {map_id: {"name": map_name if len(map_name) else None}}})

    def set_map_rotation(self, rotation: int, map_id: int | None = None) -> dict[str, Any] | None:
        """Set rotation of a map"""
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot rotate a map when temporary map is present")

        if rotation is not None:
            rotation = int(rotation)
            if rotation > 270 or rotation < 0:
                rotation = 0

            if self._map_manager:
                if map_id is None and self.status.selected_map is not None:
                    map_id = self.status.selected_map.map_id
                self._map_manager.editor.set_rotation(map_id, rotation)

            if map_id is not None:
                return self.update_map_data_async({"smra": {map_id: {"ra": rotation}}})
        return None

    def set_restricted_zone(self, walls: Any = None, zones: Any = None, no_mops: Any = None) -> dict[str, Any] | None:
        """Set restricted zones on current saved map."""
        if walls is None or walls == "":
            walls = []
        if zones is None or zones == "":
            zones = []
        if no_mops is None or no_mops == "":
            no_mops = []

        if self._map_manager:
            self._map_manager.editor.set_zones(walls, zones, no_mops)

        payload = {"line": walls, "rect": zones, "mop": no_mops}
        current_map = self.status.current_map
        if current_map and current_map.saved_map_status != 2:  # and self.capability.lidar_navigation:
            payload["temp"] = {}

        return self.update_map_data_async({"vw": payload})

    def set_carpet_area(self, carpets: Any = None, ignored_carpets: Any = None) -> dict[str, Any] | None:
        """Set carpet areas on current saved map."""
        if carpets is None or carpets == "":
            carpets = []
        if ignored_carpets is None or ignored_carpets == "":
            ignored_carpets = []

        for index in range(len(carpets)):
            carpets[index].append(index + 1)

        if self._map_manager:
            if self.status.current_map and not (
                self.status.current_map.carpets is not None
                or self.status.current_map.detected_carpets is not None
                or self.status.current_map.ignored_carpets is not None
            ):
                raise InvalidActionException("Carpets are not supported on this device")
            if self.status.current_map and not self.status.has_saved_map:
                raise InvalidActionException("Cannot edit carpets on current map")

            self._map_manager.editor.set_carpets(carpets, ignored_carpets)
        else:
            if not self.capability.carpet_recognition:
                raise InvalidActionException("Carpets are not supported on this device")
        return self.update_map_data_async({"cpt": {"addcpt": carpets, "nocpt": ignored_carpets}})

    def set_virtual_threshold(self, virtual_thresholds: Any = None) -> dict[str, Any] | None:
        """Set virtual thresholds on current saved map."""
        if virtual_thresholds is None or virtual_thresholds == "":
            virtual_thresholds = []

        if self._map_manager:
            if self.status.current_map and not (
                self.status.current_map.virtual_thresholds is not None
                or self.status.current_map.passable_thresholds is not None
                or self.capability.floor_material
            ):
                raise InvalidActionException("Virtual thresholds are not supported on this device")

            if self.status.current_map and not self.status.has_saved_map:
                raise InvalidActionException("Cannot edit virtual thresholds on current map")
            self._map_manager.editor.set_virtual_thresholds(virtual_thresholds)
        else:
            if not (
                self.get_property(DreameVacuumProperty.CARPET_RECOGNITION) is not None
                or self.get_property(DreameVacuumProperty.CARPET_CLEANING) is not None
            ):
                raise InvalidActionException("Virtual thresholds are not supported on this device")
        return self.update_map_data_async({"vws": {"vwsl": virtual_thresholds}})

    def set_predefined_points(self, points: Any = None) -> dict[str, Any] | None:
        """Set predefined points on current saved map."""
        if points is None or points == "":
            points = []

        if not self.capability.cruising:
            raise InvalidActionException("Predefined points are not supported on this device")

        if self.status.started:
            raise InvalidActionException("Cannot set predefined points while vacuum is running")

        if self.status.current_map:
            for point in points:
                if not self.status.current_map.check_point(point[0], point[1]):
                    raise InvalidActionException(f"Coordinate ({point[0]}, {point[1]}) is not inside the map")

        predefined_points = []
        for point in points:
            predefined_points.append([point[0], point[1], 0, 1])

        if self._map_manager:
            if self.status.current_map and not self.status.has_saved_map:
                raise InvalidActionException("Cannot edit predefined points on current map")
            self._map_manager.editor.set_predefined_points(predefined_points[:20])

        return self.update_map_data_async({"spoint": predefined_points[:20], "tpoint": []})

    def set_selected_map(self, map_id: int) -> dict[str, Any] | None:
        """Change currently selected map when multi floor map is enabled."""
        if self._map_manager:
            map_data_list = self.status.map_data_list
            if not map_data_list or map_id not in map_data_list:
                raise InvalidActionException("Map not found! (%s)", map_id)
            self._map_manager.editor.set_selected_map(map_id)
        self._map_select_time = time.time()
        return self.update_map_data({"sm": {}, "mapid": map_id})

    def delete_map(self, map_id: int | None = None) -> dict[str, Any] | None:
        """Delete a map."""
        map_id = int(map_id) if map_id is not None else None

        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot delete a map when temporary map is present")

        if self.status.started:
            raise InvalidActionException("Cannot delete a map while vacuum is running")

        if self._map_manager:
            if map_id is not None and map_id != 0:
                map_data_list = self.status.map_data_list
                if not map_data_list or map_id not in map_data_list:
                    raise InvalidActionException("Map not found! (%s)", map_id)

            if map_id == 0:
                map_id = None

            # Device do not deletes saved maps when you disable multi floor map feature
            # but it deletes all maps if you delete any map when multi floor map is disabled.
            if self.status.multi_map:
                if not map_id and self._map_manager.selected_map:
                    map_id = self._map_manager.selected_map.map_id
                self._map_manager.editor.delete_map(map_id)
            else:
                if self._map_manager.selected_map and map_id == self._map_manager.selected_map.map_id:
                    self._map_manager.editor.delete_map()
                else:
                    self._map_manager.editor.delete_map(map_id)
        parameters: dict[str, Any] = {"cm": {}}
        if map_id:
            parameters["mapid"] = map_id
        return self.update_map_data(parameters)

    def save_temporary_map(self) -> dict[str, Any] | None:
        """Replace new map with an old one when multi floor map is disabled."""
        if self.status.has_temporary_map:
            if self._map_manager:
                self._map_manager.editor.save_temporary_map()
            return self.update_map_data({"cw": 5})
        return None

    def discard_temporary_map(self) -> dict[str, Any] | None:
        """Discard new map when device have reached maximum number of maps it can store."""
        if self.status.has_temporary_map:
            if self._map_manager:
                self._map_manager.editor.discard_temporary_map()
            return self.update_map_data({"cw": 0})
        return None

    def replace_temporary_map(self, map_id: int | None = None) -> dict[str, Any] | None:
        """Replace new map with an old one when device have reached maximum number of maps it can store."""
        if self.status.has_temporary_map:
            if self.status.multi_map:
                raise InvalidActionException("Cannot replace a map when multi floor map is disabled")

            if self._map_manager:
                self._map_manager.editor.replace_temporary_map(map_id)
            parameters = {"cw": 1}
            if map_id:
                parameters["mapid"] = map_id
            return self.update_map_data(parameters)
        return None

    def restore_map_from_file(self, map_url: Any, map_id: Any = None) -> dict[str, Any] | None:
        from urllib.parse import urlparse

        parsed = urlparse(str(map_url))
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise InvalidActionException(f"restore_map_from_file: URL must be http(s) with a host, got {map_url!r}")

        map_recovery_status = self.status.map_recovery_status
        if map_recovery_status is None:
            raise InvalidActionException("Map recovery is not supported on this device")

        if map_recovery_status == DreameVacuumMapRecoveryStatus.RUNNING.value:
            raise InvalidActionException("Map recovery in progress")

        if map_id is None or map_id == "":
            if self.status.selected_map is None:
                raise InvalidActionException("Map ID is required")

            map_id = self.status.selected_map.map_id

        if self.status.map_data_list and map_id not in self.status.map_data_list:
            raise InvalidActionException("Map not found")

        if self.status.started:
            raise InvalidActionException("Cannot set restore a map while vacuum is running")

        self.schedule_update(15)
        if self._map_manager:
            self._last_map_request = time.time()
            self._map_manager.schedule_update(15)

        self._update_property(
            DreameVacuumProperty.MAP_RECOVERY_STATUS,
            DreameVacuumMapRecoveryStatus.RUNNING.value,
        )
        mapping = self.property_mapping[DreameVacuumProperty.MAP_RECOVERY]
        response = self._protocol.set_property(
            mapping["siid"],
            mapping["piid"],
            str(json.dumps({"map_id": map_id, "map_url": map_url}, separators=(",", ":"))).replace(" ", ""),
        )
        if not response or response[0]["code"] != 0:
            self._update_property(DreameVacuumProperty.MAP_RECOVERY_STATUS, map_recovery_status)
            raise InvalidActionException("Map recovery failed with error code %s", response[0]["code"])
        self._map_manager.schedule_update(5)
        self.schedule_update(1)
        return cast("dict[str, Any] | None", response)

    def restore_map(self, recovery_map_index: Any, map_id: Any = None) -> dict[str, Any] | None:
        """Replace a map with previously saved version by device."""
        map_recovery_status = self.status.map_recovery_status
        if map_recovery_status is None:
            raise InvalidActionException("Map recovery is not supported on this device")

        if not self._map_manager:
            raise InvalidActionException("Map recovery requires cloud connection")

        if map_recovery_status == DreameVacuumMapRecoveryStatus.RUNNING.value:
            raise InvalidActionException("Map recovery in progress")

        if self.status.started:
            raise InvalidActionException("Cannot set restore a map while vacuum is running")

        if self.status.has_temporary_map:
            raise InvalidActionException("Restore a map when temporary map is present")

        if (map_id is None or map_id == "") and self.status.selected_map:
            map_id = self.status.selected_map.map_id

        map_data_list = self.status.map_data_list
        if not map_id or not map_data_list or map_id not in map_data_list:
            raise InvalidActionException("Map not found")

        recovery_list = map_data_list[map_id].recovery_map_list
        if recovery_list is None or len(recovery_list) <= int(recovery_map_index) - 1:
            raise InvalidActionException("Invalid recovery map index")

        recovery_map_info = recovery_list[int(recovery_map_index) - 1]
        object_name = recovery_map_info.object_name
        if object_name and object_name != "":
            file, map_url, object_name = self.recovery_map_file(map_id, recovery_map_index)
            if map_url is None:
                raise InvalidActionException("Failed get recovery map file url: %s", object_name)

            if file is None:
                raise InvalidActionException("Failed to download recovery map file: %s", map_url)

            response: Any = self.restore_map_from_file(map_url, map_id)
            if response and response[0]["code"] == 0:
                self._map_manager.editor.restore_map(recovery_map_info)
            return cast("dict[str, Any] | None", response)
        raise InvalidActionException("Invalid recovery map object name")

    def backup_map(self, map_id: Any = None) -> dict[str, Any] | None:
        """Save a map map to cloud for later use of restoring."""
        if not self.capability.backup_map:
            raise InvalidActionException("Map backup is not supported on this device")

        if self.status.map_backup_status == DreameVacuumMapBackupStatus.RUNNING.value:
            raise InvalidActionException("Map backup in progress")

        if map_id is None or map_id == "":
            if self.status.selected_map is None:
                raise InvalidActionException("Map ID is required")

            map_id = self.status.selected_map.map_id

        if self.status.map_data_list and map_id not in self.status.map_data_list:
            raise InvalidActionException("Map not found")

        response = self.call_action(
            DreameVacuumAction.BACKUP_MAP,
            [
                {
                    "piid": PIID(DreameVacuumProperty.MAP_EXTEND_DATA, self.property_mapping),
                    "value": str(map_id),
                }
            ],
        )
        self.schedule_update(3, True)
        if response and response.get("code") == 0:
            self._last_map_change_time = time.time()
            self._update_property(
                DreameVacuumProperty.MAP_BACKUP_STATUS,
                DreameVacuumMapBackupStatus.RUNNING.value,
            )
        return response

    def merge_segments(self, map_id: Any, segments: Any) -> dict[str, Any] | None:
        """Merge segments on a map"""
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit segments when temporary map is present")

        if segments:
            if map_id == "":
                map_id = None

            if self._map_manager:
                if not map_id:
                    if self.capability.lidar_navigation and self._map_manager.selected_map:
                        map_id = self._map_manager.selected_map.map_id
                    else:
                        map_id = 0
                self._map_manager.editor.merge_segments(map_id, segments)

            if not map_id and self.capability.lidar_navigation:
                raise InvalidActionException("Map ID is required")

            data = {"msr": [segments[0], segments[1]]}
            if map_id:
                data["mapid"] = map_id
            return self.update_map_data(data)
        return None

    def split_segments(self, map_id: Any, segment: Any, line: Any) -> dict[str, Any] | None:
        """Split segments on a map"""
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit segments when temporary map is present")

        if segment and line is not None:
            if map_id == "":
                map_id = None

            if self._map_manager:
                if not map_id:
                    if self.capability.lidar_navigation and self._map_manager.selected_map:
                        map_id = self._map_manager.selected_map.map_id
                    else:
                        map_id = 0
                self._map_manager.editor.split_segments(map_id, segment, line)

            if not map_id and self.capability.lidar_navigation:
                raise InvalidActionException("Map ID is required")

            line.append(segment)
            data = {"dsrid": line}
            if map_id:
                data["mapid"] = map_id
            return self.update_map_data(data)
        return None

    def set_cleaning_sequence(self, cleaning_sequence: Any) -> dict[str, Any] | None:
        """Set cleaning sequence on current map.
        Device will use this order even you specify order in segment cleaning."""

        if not self.capability.customized_cleaning:
            raise InvalidActionException("Cleaning sequence is not supported on this device")

        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit segments when temporary map is present")

        if self.status.started:
            raise InvalidActionException("Cannot set cleaning sequence while vacuum is running")

        if cleaning_sequence == "" or not cleaning_sequence:
            cleaning_sequence = []

        if self._map_manager:
            if cleaning_sequence and self.status.segments:
                for k in cleaning_sequence:
                    if int(k) not in self.status.segments.keys():
                        raise InvalidValueException("Segment not found! (%s)", k)

            map_data = self.status.current_map
            if map_data and map_data.segments and not map_data.temporary_map:
                if not cleaning_sequence:
                    current = self._map_manager.cleaning_sequence
                    mid = map_data.map_id
                    if mid is not None:
                        if current and len(current):
                            self.status._previous_cleaning_sequence[mid] = current
                        elif mid in self.status._previous_cleaning_sequence:
                            del self.status._previous_cleaning_sequence[mid]

                cleaning_sequence = self._map_manager.editor.set_cleaning_sequence(cleaning_sequence)

        return self.update_map_data_async({"cleanOrder": cleaning_sequence})

    def set_cleanset(self, cleanset: Any) -> dict[str, Any] | None:
        """Set customized cleaning settings on current map. Device will use these settings even you pass another setting for custom segment cleaning."""
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit customized cleaning settings when temporary map is present")

        if cleanset is not None:
            return self.update_map_data_async({"customeClean": cleanset})
        return None

    def set_custom_cleaning(
        self,
        segment_id: Any,
        suction_level: Any,
        water_volume: Any,
        cleaning_times: Any,
        cleaning_mode: Any = None,
        custom_mopping_route: Any = None,
        cleaning_route: Any = None,
        wetness_level: Any = None,
    ) -> dict[str, Any] | None:
        """Set customized cleaning settings on current map.
        Device will use these settings even you pass another setting for custom segment cleaning.
        """

        if not self.capability.customized_cleaning:
            raise InvalidActionException("Customized cleaning is not supported on this device")

        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit customized cleaning parameters when temporary map is present")

        if self.status.started:
            raise InvalidActionException("Cannot edit customized cleaning parameters while vacuum is running")

        if suction_level is not None:
            for v in suction_level:
                if int(v) < 0 or int(v) > 3:
                    raise InvalidActionException("Invalid suction level: %s", v)

        if water_volume is not None:
            for v in water_volume:
                if int(v) < 1 or int(v) > 3:
                    raise InvalidActionException("Invalid water volume: %s", v)

        if cleaning_times is not None:
            for v in cleaning_times:
                if int(v) < 1 or int(v) > 3:
                    raise InvalidActionException("Invalid cleaning times: %s", v)

        if cleaning_mode is not None:
            for v in cleaning_mode:
                if int(v) < 0 or int(v) > 2:
                    raise InvalidActionException("Invalid cleaning mode: %s", v)

        if custom_mopping_route is not None:
            if self.capability.segment_mopping_settings and not self.capability.cleaning_route and self.capability.map:
                for v in custom_mopping_route:
                    if int(v) < -1 or int(v) > 2:
                        raise InvalidActionException("Invalid custom mopping route: %s", v)
            else:
                raise InvalidActionException("Custom mopping route is not supported on this device")

        if cleaning_route is not None:
            if self.capability.cleaning_route and self.capability.map:
                for v in cleaning_route:
                    if int(v) < 1 or int(v) > (3 if self.capability.segment_slow_clean_route else 4):
                        raise InvalidActionException("Invalid cleaning route: %s", v)
            else:
                raise InvalidActionException("Cleaning route is not supported on this device")

        if wetness_level is not None:
            if self.capability.wetness_level and self.capability.map:
                for v in wetness_level:
                    if int(v) < 1 or int(v) > 32:
                        raise InvalidActionException("Invalid wetness level: %s", v)
            else:
                raise InvalidActionException("Wetness level is not supported on this device")

        if self.capability.map:
            if not self.status.has_saved_map:
                raise InvalidActionException("Cannot edit customized cleaning parameters on current map")

            current_map = self.status.current_map
            if current_map:
                segments = self.status.segments
                index = 0
                if not segment_id or segment_id == "":
                    raise InvalidActionException("Segment ID is required")

                for k in segment_id:
                    id = int(k)
                    if not segments or id not in segments:
                        raise InvalidActionException("Invalid Segment ID: %s", id)
                    self._map_manager.editor.set_segment_suction_level(id, int(suction_level[index]), False)
                    if self.capability.wetness_level and wetness_level is not None:
                        self._map_manager.editor.set_segment_wetness_level(id, int(wetness_level[index]), False)
                    else:
                        self._map_manager.editor.set_segment_water_volume(id, int(water_volume[index]), False)
                    self._map_manager.editor.set_segment_cleaning_times(id, int(cleaning_times[index]), False)
                    if self.capability.custom_cleaning_mode and cleaning_mode is not None:
                        self._map_manager.editor.set_segment_cleaning_mode(id, int(cleaning_mode[index]), False)
                    if (
                        self.capability.segment_mopping_settings
                        and not self.capability.cleaning_route
                        and custom_mopping_route is not None
                    ):
                        self._map_manager.editor.set_segment_custom_mopping_route(
                            id, int(custom_mopping_route[index]), False
                        )
                    elif self.capability.cleaning_route and cleaning_route is not None:
                        self._map_manager.editor.set_segment_cleaning_route(id, int(cleaning_route[index]), False)
                    index = index + 1
                self._map_manager.editor.refresh_map()
                return self.set_cleanset(self._map_manager.editor.cleanset(current_map))

        custom_cleaning_mode = self.capability.custom_cleaning_mode
        has_cleaning_mode = cleaning_mode != "" and cleaning_mode is not None
        if (
            segment_id != ""
            and segment_id
            and suction_level != ""
            and suction_level
            and water_volume != ""
            and water_volume
            and cleaning_times != ""
            and cleaning_times is not None
        ):
            if has_cleaning_mode and not custom_cleaning_mode:
                raise InvalidActionException(
                    "Setting custom cleaning mode for segments is not supported by the device!"
                )
            if not has_cleaning_mode and custom_cleaning_mode:
                raise InvalidActionException("Cleaning mode is required")

            if segments:
                count = len(segments.items())
                if (
                    len(segment_id) != count
                    or len(suction_level) != count
                    or len(water_volume) != count
                    or len(cleaning_times) != count
                    or (custom_cleaning_mode and cleaning_mode is not None and len(cleaning_mode) != count)
                ):
                    raise InvalidActionException("Parameter count mismatch!")

            custom_cleaning = []
            index = 0
            water_level = water_volume[index]
            if self.capability.wetness_level:
                if water_level == 1:
                    water_level = 5
                elif water_level == 3:
                    water_level = 27
                else:
                    water_level = 16
            else:
                water_level = water_level + 1

            for id in segment_id:
                # for some reason cleanset uses different int values for water volume
                values = [
                    id,
                    suction_level[index],
                    water_level,
                    cleaning_times[index],
                ]
                if custom_cleaning_mode:
                    values.append(cleaning_mode[index])
                    if segments:
                        if id not in segments:
                            raise InvalidActionException("Invalid Segment ID: %s", id)

                        if segments[id].custom_mopping_route is not None:
                            from .map_decoder import DreameVacuumMapDecoder

                            map_decoder = DreameVacuumMapDecoder
                            mopping_values = map_decoder.split_mopping_settings(segments[id].mopping_settings or 0)
                            if mopping_values:
                                if self.capability.wetness_level:
                                    mopping_values[1] = 0
                                    mopping_values[2] = 0
                                else:
                                    # Set mopping mode or water volume according to the mopping effect switch
                                    mopping_values[2 if segments[id].custom_mopping_route == -1 else 1] = water_volume[
                                        index
                                    ]
                                    values.append(map_decoder.combine_mopping_settings(mopping_values))
                            else:
                                values.append(segments[id].mopping_settings)
                custom_cleaning.append(values)
                index = index + 1

            return self.set_cleanset(custom_cleaning)

        raise InvalidActionException("Missing parameters!")

    def set_custom_carpet_cleaning(
        self,
        id: Any,
        type: Any,
        carpet_cleaning: Any = None,
        carpet_settings: Any = None,
    ) -> dict[str, Any] | None:
        """Set customized carpet cleaning settings on current map."""
        if not self.capability.carpet_recognition:
            raise InvalidActionException("Custom carpet cleaning is not supported on this device")

        if carpet_settings is not None and not self.capability.carpet_cleanset_v3:
            raise InvalidActionException("Custom carpet settings is not supported on this device")

        if id is None or type is None:
            raise InvalidActionException("Missing id or type")

        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit carpets when temporary map is present")

        if not isinstance(id, list):
            id = [id]

        carpet_cleanset = []
        index = 0
        for carpet_id in id:
            if isinstance(type, list):
                if index < len(type):
                    carpet_type = type[index]
                else:
                    raise InvalidActionException("Missing carpet type")
            else:
                carpet_type = type

            if isinstance(carpet_cleaning, list):
                if index < len(carpet_cleaning):
                    cleaning_setting = carpet_cleaning[index]
                else:
                    raise InvalidActionException("Missing carpet cleaning")
            else:
                cleaning_setting = carpet_cleaning

            if (
                carpet_settings is not None
                and isinstance(carpet_settings, list)
                and carpet_settings
                and isinstance(carpet_settings[0], list)
            ):
                if index < len(carpet_settings):
                    enabled_settings = carpet_settings[index]
                else:
                    enabled_settings = None
            else:
                enabled_settings = carpet_settings

            if not (carpet_type == 0 or carpet_type == 1 or carpet_type == 2):
                raise InvalidActionException(
                    "Invalid type: %s (0 = Automatically Detected Carpet, 1 = Manually Created Carpet, 2 = Room Carpet)",
                    carpet_type,
                )

            if carpet_type == 2 and not self.capability.carpet_material:
                raise InvalidActionException("Room carpets are not supported on this device: %s", cleaning_setting)

            if cleaning_setting is None or cleaning_setting == 0:
                cleaning_setting = -1

            if not (cleaning_setting >= -1 and cleaning_setting <= 7):
                raise InvalidActionException("Invalid carpet cleaning setting: %s", cleaning_setting)

            if (
                cleaning_setting == 4
                and (
                    not self.capability.mop_pad_lifting_plus
                    or self.capability.auto_carpet_cleaning
                    or self.capability.carpet_crossing
                )
            ) or (
                cleaning_setting == 6
                and (not self.capability.mop_pad_lifting_plus and not self.capability.auto_carpet_cleaning)
            ):
                raise InvalidActionException(
                    "Selected cleaning setting is not supported on this device: %s", cleaning_setting
                )

            index = index + 1
            cleanset = [carpet_type, carpet_id, cleaning_setting]

            if self.capability.carpet_cleanset_v3:
                if cleaning_setting == -1 or enabled_settings is None:
                    settings = -1
                else:
                    settings = 0
                    if self.capability.clean_carpets_first and "clean_carpets_first" in enabled_settings:
                        settings |= 1
                    if (
                        self.get_property(DreameVacuumProperty.CARPET_BOOST) is not None
                        and "carpet_boost" in enabled_settings
                    ):
                        settings |= 2
                    if self.capability.intensive_carpet_cleaning and "intensive_carpet_cleaning" in enabled_settings:
                        settings |= 4
                    if self.capability.side_brush_carpet_rotate and "side_brush_carpet_rotate" in enabled_settings:
                        settings |= 8

                cleanset.append(settings)
            carpet_cleanset.append(cleanset)

        if carpet_cleanset:
            if self.capability.map:
                current_map = self.status.current_map
                if current_map:
                    if current_map.carpet_cleanset is None:
                        raise InvalidActionException("Cannot set custom carpet cleaning on selected map")
                    carpet_cleanset = self._map_manager.editor.set_custom_carpet_cleaning(carpet_cleanset)
                    if not carpet_cleanset:
                        raise InvalidActionException("Cannot find selected carpet(s)")

            return self.update_map_data_async({"carpetcleanset": carpet_cleanset})
        return None

    def set_hidden_segments(self, hidden_segments: Any) -> dict[str, Any] | None:
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit segments when temporary map is present")

        if self.status.started:
            raise InvalidActionException("Cannot set room visibility while vacuum is running")

        if hidden_segments == "" or not hidden_segments:
            hidden_segments = []

        if self._map_manager:
            if hidden_segments and self.status.segments:
                for k in hidden_segments:
                    if int(k) not in self.status.segments.keys():
                        raise InvalidValueException("Segment not found! (%s)", k)

            # hidden_segments = self._map_manager.editor.set_hidden_segments(hidden_segments)

        return self.update_map_data_async({"delsr": hidden_segments})

    def set_segment_name(
        self, segment_id: int, segment_type: int, custom_name: str | None = None
    ) -> dict[str, Any] | None:
        """Update name of a segment on current map"""
        if self.status.has_temporary_map:
            raise InvalidActionException("Cannot edit segment when temporary map is present")

        if self._map_manager:
            segment_info = self._map_manager.editor.set_segment_name(segment_id, segment_type, custom_name)
            if segment_info:
                data = {"nsr": segment_info}
                if self.status.current_map:
                    data["mapid"] = self.status.current_map.map_id
                if self.capability.auto_rename_segment:
                    data["autonsr"] = True
                return self.update_map_data_async(data)
        return None

    def set_segment_order(self, segment_id: int, order: int) -> dict[str, Any] | None:
        """Update cleaning order of a segment on current map"""
        if self._map_manager and not self.status.has_temporary_map:
            if order is None or (isinstance(order, str) and not order.isnumeric()):
                order = 0

            cleaning_order = self._map_manager.editor.set_segment_order(segment_id, order)

            return self.update_map_data_async({"cleanOrder": cleaning_order})
        return None

    def set_segment_suction_level(self, segment_id: int, suction_level: int) -> dict[str, Any] | None:
        """Update suction level of a segment on current map"""
        if self._map_manager and not self.status.has_temporary_map:
            return self.set_cleanset(self._map_manager.editor.set_segment_suction_level(segment_id, suction_level))
        return None

    def set_segment_water_volume(self, segment_id: int, water_volume: int) -> dict[str, Any] | None:
        """Update water volume of a segment on current map"""
        if not self.capability.self_wash_base and self._map_manager and not self.status.has_temporary_map:
            if self.capability.wetness_level:
                if self.capability.mop_clean_frequency:
                    if water_volume == 1:
                        water_volume = 5
                    elif water_volume == 3:
                        water_volume = 15
                    else:
                        water_volume = 10
                else:
                    if water_volume == 1:
                        water_volume = 5
                    elif water_volume == 3:
                        water_volume = 27
                    else:
                        water_volume = 16

                return self.set_cleanset(self._map_manager.editor.set_segment_wetness_level(segment_id, water_volume))

            return self.set_cleanset(self._map_manager.editor.set_segment_water_volume(segment_id, water_volume))
        return None

    def set_segment_mop_pad_humidity(self, segment_id: int, mop_pad_humidity: int) -> dict[str, Any] | None:
        """Update mop pad humidity of a segment on current map"""
        if self.capability.self_wash_base and self._map_manager and not self.status.has_temporary_map:
            if self.capability.wetness_level:
                if self.capability.mop_clean_frequency:
                    if mop_pad_humidity == 1:
                        mop_pad_humidity = 2
                    elif mop_pad_humidity == 3:
                        mop_pad_humidity = 14
                    else:
                        mop_pad_humidity = 8
                else:
                    if mop_pad_humidity == 1:
                        mop_pad_humidity = 5
                    elif mop_pad_humidity == 3:
                        mop_pad_humidity = 27
                    else:
                        mop_pad_humidity = 16

                return self.set_cleanset(
                    self._map_manager.editor.set_segment_wetness_level(segment_id, mop_pad_humidity)
                )

            return self.set_cleanset(self._map_manager.editor.set_segment_water_volume(segment_id, mop_pad_humidity))
        return None

    def set_segment_wetness_level(self, segment_id: int, wetness_level: int) -> dict[str, Any] | None:
        """Update wetness level of a segment on current map"""
        if self.capability.wetness_level and self._map_manager and not self.status.has_temporary_map:
            return self.set_cleanset(self._map_manager.editor.set_segment_wetness_level(segment_id, int(wetness_level)))
        return None

    def set_segment_cleaning_mode(self, segment_id: int, cleaning_mode: int) -> dict[str, Any] | None:
        """Update mop pad humidity of a segment on current map"""
        if self._map_manager and not self.status.has_temporary_map:
            return self.set_cleanset(self._map_manager.editor.set_segment_cleaning_mode(segment_id, cleaning_mode))
        return None

    def set_segment_custom_mopping_route(self, segment_id: int, custom_mopping_route: int) -> dict[str, Any] | None:
        """Update custom mopping route of a segment on current map"""
        if (
            self.capability.self_wash_base
            and self.capability.custom_mopping_route
            and self._map_manager
            and not self.status.has_temporary_map
        ):
            return self.set_cleanset(
                self._map_manager.editor.set_segment_custom_mopping_route(segment_id, custom_mopping_route)
            )
        return None

    def set_segment_cleaning_route(self, segment_id: int, cleaning_route: int) -> dict[str, Any] | None:
        """Update cleaning route of a segment on current map"""
        if (
            self.capability.self_wash_base
            and self.capability.cleaning_route
            and self._map_manager
            and not self.status.has_temporary_map
        ):
            return self.set_cleanset(self._map_manager.editor.set_segment_cleaning_route(segment_id, cleaning_route))
        return None

    def set_segment_cleaning_times(self, segment_id: int, cleaning_times: int) -> dict[str, Any] | None:
        """Update cleaning times of a segment on current map."""
        if self.status.started:
            raise InvalidActionException("Cannot set room cleaning times while vacuum is running")

        if self._map_manager and not self.status.has_temporary_map:
            return self.set_cleanset(self._map_manager.editor.set_segment_cleaning_times(segment_id, cleaning_times))
        return None

    def set_segment_floor_material(
        self, segment_id: int, floor_material: int, direction: int | None = None
    ) -> dict[str, Any] | None:
        """Update floor material of a segment on current map"""
        if self._map_manager and not self.status.has_temporary_map:
            if (
                floor_material > 4
                and floor_material < 8
                and not (self.capability.carpet_material and self.capability.carpet_type)
            ):
                raise InvalidActionException("Setting floor material as carpet is not supported on this device")

            if not self.capability.floor_direction_cleaning:
                direction = None
            else:
                if floor_material != 1:
                    direction = None
                elif direction is None:
                    segment = self.status.segments.get(segment_id) if self.status.segments else None
                    current_map = self.status.current_map
                    direction = (
                        segment.floor_material_rotated_direction
                        if segment is not None and segment.floor_material_rotated_direction is not None
                        else (0 if current_map and (current_map.rotation == 0 or current_map.rotation == 90) else 90)
                    )

            data = {"nsm": self._map_manager.editor.set_segment_floor_material(segment_id, floor_material, direction)}
            if self.status.selected_map:
                data["map_id"] = self.status.selected_map.map_id
            return self.update_map_data_async(data)
        return None

    def set_segment_floor_material_direction(
        self, segment_id: int, floor_material_direction: int
    ) -> dict[str, Any] | None:
        """Update floor material direction of a segment on current map"""
        if self.capability.floor_direction_cleaning and self._map_manager and not self.status.has_temporary_map:
            data = {"nsm": self._map_manager.editor.set_segment_floor_material(segment_id, 1, floor_material_direction)}
            if self.status.selected_map:
                data["map_id"] = self.status.selected_map.map_id
            return self.update_map_data_async(data)
        return None

    def set_segment_visibility(self, segment_id: int, visibility: int) -> dict[str, Any] | None:
        """Update visibility a segment on current map"""
        if self.capability.segment_visibility and self._map_manager and not self.status.has_temporary_map:
            data = {"delsr": self._map_manager.editor.set_segment_visibility(segment_id, int(visibility))}
            # if self.status.selected_map:
            #    data["map_id"] = self.status.selected_map.map_id
            return self.update_map_data_async(data)
        return None
