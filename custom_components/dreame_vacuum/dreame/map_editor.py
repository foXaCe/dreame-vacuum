from __future__ import annotations

"""Map editor module for Dreame vacuum integration.

Contains DreameMapVacuumMapEditor for in-memory map editing operations.
"""

import base64
import copy
import logging
from threading import Timer
import time
from typing import TYPE_CHECKING, Any, cast

import numpy as np

if TYPE_CHECKING:
    from .map_manager import DreameMapVacuumMapManager

from .const import (
    MAP_PARAMETER_NAME,
    MAP_REQUEST_PARAMETER_INDEX,
    MAP_REQUEST_PARAMETER_ROOM_ID,
    MAP_REQUEST_PARAMETER_TYPE,
)
from .map_decoder import DreameVacuumMapDecoder
from .vacuum_types import (
    Area,
    Carpet,
    Coordinate,
    MapData,
    ObstacleIgnoreStatus,
    Point,
    RecoveryMapInfo,
    Wall,
)

_LOGGER = logging.getLogger(__name__)


class DreameMapVacuumMapEditor:
    """Every map change must be handled on memory before actually requesting it to the device because it takes too much time to get the updated map from the cloud.
    This class handles user edits on stored map data like updating customized cleaning settings or setting active segments on segment cleaning.
    Original app has a similar class to handle the same issue (Works optimistically)"""

    def __init__(self, map_manager: Any) -> None:
        self.map_manager: DreameMapVacuumMapManager = map_manager
        self._refresh_timer: Timer | None = None

    def _set_updated_frame_id(self, frame_id: Any) -> None:
        self.map_manager._updated_frame_id = frame_id

    def _refresh_map(self, map_id: int | None = None) -> None:
        if map_id:
            if self._saved_map_data and map_id in self._saved_map_data:
                self._saved_map_data[map_id].last_updated = time.time()
                self.map_manager._map_data_updated()
            return
        if self._map_data is not None:
            self._map_data.last_updated = time.time()
            self.map_manager._map_data_updated()

    def refresh_map(self, map_id: int | None = None) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.cancel()
        self._refresh_timer = Timer(0.5, self._refresh_map, [map_id])
        self._refresh_timer.start()

    def cancel_pending(self) -> None:
        """Cancel any pending deferred refresh so unload is clean."""
        if self._refresh_timer is not None:
            self._refresh_timer.cancel()
            self._refresh_timer = None

    def set_active_areas(self, active_areas: list[list[int]]) -> None:
        map_data = self._map_data
        if map_data is not None:
            map_data.active_cruise_points = None
            map_data.active_areas = []
            for area in active_areas:
                x_coords = sorted([area[0], area[2]])
                y_coords = sorted([area[1], area[3]])
                map_data.active_areas.append(
                    Area(
                        x_coords[0],
                        y_coords[0],
                        x_coords[1],
                        y_coords[0],
                        x_coords[1],
                        y_coords[1],
                        x_coords[0],
                        y_coords[1],
                    )
                )
            self._set_updated_frame_id(map_data.frame_id)
            self.refresh_map()

    def set_active_segments(self, active_segments: list[int]) -> None:
        map_data = self._map_data
        if map_data is not None:
            map_data.active_segments = active_segments
            self._set_updated_frame_id(map_data.frame_id)
            self.refresh_map()

    def set_active_points(self, active_points: list[list[int]]) -> None:
        map_data = self._map_data
        if map_data is not None:
            map_data.active_points = []
            for point in active_points:
                map_data.active_points.append(
                    Point(
                        point[0],
                        point[1],
                    )
                )
            self._set_updated_frame_id(map_data.frame_id)
            self.refresh_map()

    def set_cruise_points(self, active_cruise_points: list[list[int]]) -> None:
        map_data = self._map_data
        if map_data is not None:
            map_data.active_cruise_points = {}
            index = 0
            if active_cruise_points:
                map_data.path = None
                map_data.obstacles = None
                map_data.active_areas = None
                map_data.active_segments = None
                for point in active_cruise_points:
                    index = index + 1
                    map_data.active_cruise_points[index] = Coordinate(
                        point[0],
                        point[1],
                        bool(point[2]),
                        point[3],
                    )
            self._set_updated_frame_id(map_data.frame_id)
            self.refresh_map()

    def clear_path(self) -> None:
        map_data = self._map_data
        if map_data is not None:
            map_data.path = None
            # map_data.obstacles = None
            # map_data.active_cruise_points = None
            map_data.active_areas = None
            map_data.active_segments = None
            self._set_updated_frame_id(map_data.frame_id)
            self.refresh_map()

    def reset_map(self) -> None:
        map_data = self._map_data
        if map_data is not None and map_data.dimensions is not None:
            map_data.dimensions.width = 0
            map_data.dimensions.height = 0
            map_data.segments = {}
            map_data.floor_material = None
            map_data.carpet_cleanset = None
            map_data.hidden_segments = None
            map_data.path = None
            map_data.carpets = None
            map_data.detected_carpets = None
            map_data.ignored_carpets = None
            map_data.carpet_pixels = None
            map_data.obstacles = None
            map_data.empty_map = True
            map_data.saved_map_status = 0
            self._set_updated_frame_id((map_data.frame_id or 0) + 1)
            self.refresh_map()

    def set_rotation(self, map_id: int, rotation: int) -> None:
        if map_id in self._saved_map_data:
            self._saved_map_data[map_id].rotation = rotation
            DreameVacuumMapDecoder.set_floor_material(self._saved_map_data[map_id])
            if self._map_data is not None and map_id == self._selected_map_id:
                self._map_data.rotation = rotation
                DreameVacuumMapDecoder.set_floor_material(self._map_data)
                self.refresh_map()
            self.refresh_map(map_id)

    def set_map_name(self, map_id: int, name: str) -> None:
        if map_id in self._saved_map_data:
            if name and len(name):
                self._saved_map_data[map_id].custom_name = name
                self._saved_map_data[map_id].map_name = name
            else:
                self._saved_map_data[map_id].custom_name = None
                self._saved_map_data[map_id].map_name = f"Map {self._saved_map_data[map_id].map_index!s}"
            self.refresh_map(map_id)
            self.refresh_map()

    def set_selected_map(self, map_id: int) -> None:
        if map_id != self._selected_map_id:
            self.set_current_map(map_id)

    def set_current_map(self, map_id: int) -> None:
        if map_id and map_id in self._saved_map_data:
            saved_map_data = copy.deepcopy(self._saved_map_data[map_id])
            saved_map_data.docked = self._map_data.docked if self._map_data else None
            saved_map_data.timestamp_ms = self._current_timestamp_ms
            saved_map_data.frame_id = None
            saved_map_data.map_name = None
            saved_map_data.saved_map_id = map_id
            saved_map_data.custom_name = None
            saved_map_data.saved_map = False
            saved_map_data.restored_map = True
            saved_map_data.temporary_map = False
            saved_map_data.empty_map = False
            saved_map_data.saved_map_status = 2
            DreameVacuumMapDecoder.set_segment_cleanset(
                saved_map_data,
                saved_map_data.cleanset,
                self._capability,
            )
            DreameVacuumMapDecoder.set_carpet_cleanset(saved_map_data, saved_map_data.carpet_cleanset, self._capability)
            self.map_manager._map_data = saved_map_data
            self.map_manager._current_frame_id = None
            self.map_manager._current_map_id = map_id
            self.map_manager._selected_map_id = map_id
            self.refresh_map()
            self.refresh_map(map_id)

    def set_carpets(self, carpets: Any, ignored_carpets: Any) -> None:
        map_data = self._map_data
        if not map_data or not self._selected_map_id or (map_data.carpets is None and map_data.ignored_carpets is None):
            return

        map_data.carpets = []
        if carpets:
            for carpet in carpets:
                x_coords = sorted([carpet[0], carpet[2]])
                y_coords = sorted([carpet[1], carpet[3]])
                map_data.carpets.append(
                    Carpet(
                        carpet[4] if len(carpet) > 4 else 0,
                        x_coords[0],
                        y_coords[0],
                        x_coords[1],
                        y_coords[0],
                        x_coords[1],
                        y_coords[1],
                        x_coords[0],
                        y_coords[1],
                        carpet[5] if len(carpet) > 5 else None,
                        carpet[6] if len(carpet) > 6 else None,
                    )
                )

        map_data.ignored_carpets = []
        if ignored_carpets:
            index = 1
            for carpet in ignored_carpets:
                x_coords = sorted([carpet[0], carpet[2]])
                y_coords = sorted([carpet[1], carpet[3]])
                map_data.ignored_carpets.append(
                    Carpet(
                        index,
                        x_coords[0],
                        y_coords[0],
                        x_coords[1],
                        y_coords[0],
                        x_coords[1],
                        y_coords[1],
                        x_coords[0],
                        y_coords[1],
                    )
                )
                index = index + 1

        self._saved_map_data[self._selected_map_id].carpets = map_data.carpets
        self._saved_map_data[self._selected_map_id].ignored_carpets = map_data.ignored_carpets
        self._set_updated_frame_id(map_data.frame_id)
        self.refresh_map(self._selected_map_id)
        self.refresh_map()
        return

    def set_virtual_thresholds(self, virtual_thresholds: Any) -> None:
        map_data = self._map_data
        if (
            not map_data
            or not self._selected_map_id
            or not (map_data.virtual_thresholds is not None or map_data.passable_thresholds is not None)
        ):
            return

        thresholds = []
        if virtual_thresholds:
            for line in virtual_thresholds:
                thresholds.append(
                    Wall(
                        line[0],
                        line[1],
                        line[2],
                        line[3],
                    )
                )

        if map_data.passable_thresholds is not None:
            map_data.passable_thresholds = thresholds
            self._saved_map_data[self._selected_map_id].passable_thresholds = map_data.passable_thresholds
        else:
            map_data.virtual_thresholds = thresholds
            self._saved_map_data[self._selected_map_id].virtual_thresholds = map_data.virtual_thresholds
        self._set_updated_frame_id(map_data.frame_id)
        self.refresh_map(self._selected_map_id)
        self.refresh_map()
        return

    def set_predefined_points(self, predefined_points: Any) -> None:
        map_data = self._map_data
        if not map_data or not self._selected_map_id or map_data.predefined_points is None:
            return

        map_data.predefined_points = {}
        index = 0
        if predefined_points:
            for point in predefined_points:
                index = index + 1
                map_data.predefined_points[index] = Coordinate(
                    point[0],
                    point[1],
                    bool(point[2]),
                    point[3],
                )

        self._saved_map_data[self._selected_map_id].predefined_points = map_data.predefined_points
        self._set_updated_frame_id(map_data.frame_id)
        self.refresh_map(self._selected_map_id)
        self.refresh_map()
        return

    def set_obstacle_ignore(self, x: Any, y: Any, obstacle_ignored: Any) -> None:
        map_data = self._map_data
        if not map_data or not map_data.obstacles:
            return

        for k, v in map_data.obstacles.items():
            if int(v.x) == int(x) and int(v.y) == int(y):
                map_data.obstacles[k].ignore_status = (
                    ObstacleIgnoreStatus.MANUALLY_IGNORED
                    if bool(obstacle_ignored)
                    else ObstacleIgnoreStatus.NOT_IGNORED
                )
                break

        self._set_updated_frame_id(map_data.frame_id)
        self.refresh_map()
        return

    def set_router_position(self, x: Any, y: Any) -> None:
        map_data = self._map_data
        if not map_data or not self._selected_map_id or map_data.router_position is None:
            return

        router_position = Point(int(x), int(y))
        saved_entry = self._saved_map_data[self._selected_map_id]
        saved_entry.router_position = router_position
        if saved_entry.wifi_map_data:
            saved_entry.wifi_map_data.router_position = router_position
        map_data.router_position = router_position
        if map_data.wifi_map_data:
            map_data.wifi_map_data.router_position = router_position
        self._set_updated_frame_id(map_data.frame_id)
        self.refresh_map(self._selected_map_id)
        self.refresh_map()
        return

    def delete_map(self, map_id: int | None = None) -> None:
        map_data = self._map_data
        if map_data and map_data.temporary_map:
            return

        if map_id is None:
            self.map_manager._map_data = None
            self.map_manager._selected_map_id = None
            self.map_manager._updated_frame_id = None
            self.map_manager._saved_map_data = {}
            self.map_manager._refresh_map_list()
            self.map_manager.request_next_map_list()
        else:
            if self._saved_map_data and map_id not in self._saved_map_data:
                self.map_manager.schedule_update(2)
                return

            if map_data and self._selected_map_id == map_id:
                if len(self.map_manager._map_list) >= 2:
                    for id in reversed(self.map_manager._saved_map_data.keys()):
                        if id != map_id:
                            del self.map_manager._saved_map_data[map_id]
                            self.map_manager._refresh_map_list()
                            self.set_current_map(id)
                            break
                else:
                    del self.map_manager._saved_map_data[map_id]
                    self.map_manager._map_data = None
                    self.map_manager._updated_frame_id = None
                    self.map_manager._selected_map_id = None
                    self.map_manager._refresh_map_list()
            else:
                del self.map_manager._saved_map_data[map_id]
                self.map_manager._refresh_map_list()

            self.map_manager.request_next_map_list()

    def merge_segments(self, map_id: int, segments: list[int]) -> None:
        saved_map_data = self._saved_map_data
        if saved_map_data and map_id in saved_map_data and len(segments) == 2:
            map_data = saved_map_data[map_id]
            dims = map_data.dimensions
            if dims and map_data.segments and segments[0] in map_data.segments and segments[1] in map_data.segments:
                if segments[1] not in map_data.segments[segments[0]].neighbors:
                    _LOGGER.error("Segments are not neighbors with each other: %s", segments)
                    return

                raw_data: Any = map_data.data
                pixel_type: Any = map_data.pixel_type
                data = np.zeros((dims.width * dims.height), np.uint8)
                for y in range(dims.height):
                    for x in range(dims.width):
                        index = y * dims.width + x
                        if (raw_data[index] & 0x3F) == segments[1]:
                            data[index] = segments[0]
                        else:
                            data[index] = raw_data[index]

                        if int(pixel_type[x, y]) == segments[1]:
                            pixel_type[x, y] = segments[0]

                map_data.data = bytes(data)
                manager_segments: Any = self.map_manager._saved_map_data[map_id].segments
                del manager_segments[segments[1]]
                new_segments = DreameVacuumMapDecoder.get_segments(map_data, self.map_manager._vslam_map)
                map_data.segments[segments[0]].x = new_segments[segments[0]].x
                map_data.segments[segments[0]].y = new_segments[segments[0]].y
                if map_data.hidden_segments and segments[1] in map_data.hidden_segments:
                    map_data.hidden_segments.remove(segments[1])

                DreameVacuumMapDecoder.set_floor_material(map_data, self._capability)
                for k, v in map_data.segments.items():
                    if segments[1] in v.neighbors:
                        map_data.segments[k].neighbors.remove(segments[1])

                DreameVacuumMapDecoder.set_segment_color_index(map_data)
                if self._map_data and map_id == self._selected_map_id:
                    self.set_current_map(map_id)
                self.refresh_map(map_id)

    def split_segments(self, map_id: int, segment: int, line: list[int]) -> None:
        if self._saved_map_data and map_id in self._saved_map_data:
            if self._map_data and map_id == self._selected_map_id:
                self.set_current_map(map_id)
            self.refresh_map(map_id)

    def save_temporary_map(self) -> None:
        if self._map_data and self._map_data.temporary_map:
            self._map_data.temporary_map = False
            self.refresh_map()
            self.map_manager.request_next_map_list()

    def discard_temporary_map(self) -> None:
        if self._map_data and self._map_data.temporary_map and self._selected_map_id:
            self.set_current_map(self._selected_map_id)
            self.map_manager.request_next_map_list()

    def replace_temporary_map(self, map_id: int | None = None) -> None:
        map_data = self._map_data
        if map_data and map_data.temporary_map:
            if not map_id and self._selected_map_id:
                map_id = self._selected_map_id

            if map_id in self._saved_map_data:
                new_map = copy.deepcopy(map_data)
                new_map.map_id = new_map.saved_map_id
                new_map.saved_map_id = None
                new_map.saved_map_status = -1
                new_map.saved_map = True
                new_map.cleanset = {}
                self.map_manager._saved_map_data[cast(int, new_map.map_id)] = new_map
                del self.map_manager._saved_map_data[map_id]
                self.map_manager._refresh_map_list()

                map_data.saved_map_id = new_map.map_id
                if map_data.saved_map_id and map_data.saved_map_id in self._saved_map_data:
                    map_data.map_index = self._saved_map_data[map_data.saved_map_id].map_index
                else:
                    map_data.map_index = 0
                map_data.temporary_map = False
                map_data.saved_map = False
                map_data.saved_map_status = 0
                map_data.restored_map = True
                map_data.empty_map = False
                map_data.cleanset = {}
                DreameVacuumMapDecoder.set_segment_cleanset(map_data, map_data.cleanset, self._capability)
                DreameVacuumMapDecoder.set_carpet_cleanset(map_data, map_data.carpet_cleanset, self._capability)
                self.map_manager._map_data = map_data
                self.map_manager._selected_map_id = new_map.map_id
                self.map_manager.request_next_map_list()
                self.refresh_map()

    def restore_map(self, recovery_map_info: RecoveryMapInfo) -> None:
        if recovery_map_info and recovery_map_info.map_id in self.map_manager._map_list:
            self.map_manager.schedule_update(15)

            if recovery_map_info.raw_map is None and recovery_map_info.map_object_name is not None:
                try:
                    response = self._get_interim_file_data(recovery_map_info.map_object_name)
                    if response:
                        recovery_map_info.raw_map = response.decode()
                except Exception as ex:
                    _LOGGER.warning("Get Recovery Map Object failed: %s", ex)
                    return

            recovery_map_data = (
                (
                    DreameVacuumMapDecoder.decode_saved_map(
                        recovery_map_info.raw_map,
                        self.map_manager._vslam_map,
                        self._saved_map_data[recovery_map_info.map_id].rotation,
                        self.map_manager._aes_iv,
                    )
                )
                if recovery_map_info.map_data is None
                else recovery_map_info.map_data
            )
            if recovery_map_data is None:
                return
            recovery_map_data.recovery_map = False
            recovery_map_data.saved_map = True
            recovery_map_data.map_name = self._saved_map_data[recovery_map_info.map_id].map_name
            recovery_map_data.custom_name = self._saved_map_data[recovery_map_info.map_id].custom_name
            recovery_map_data.rotation = self._saved_map_data[recovery_map_info.map_id].rotation
            recovery_map_data.map_index = self._saved_map_data[recovery_map_info.map_id].map_index
            recovery_map_data.recovery_map_list = self._saved_map_data[recovery_map_info.map_id].recovery_map_list
            recovery_map_data.timestamp_ms = self._saved_map_data[recovery_map_info.map_id].timestamp_ms
            recovery_map_data.last_updated = time.time()
            if recovery_map_data.wifi_map_data:
                recovery_map_data.wifi_map_data.last_updated = time.time()

            self._saved_map_data[recovery_map_info.map_id] = recovery_map_data
            self.refresh_map(recovery_map_info.map_id)
            if recovery_map_info.map_id == self._selected_map_id:
                self.set_current_map(recovery_map_info.map_id)
                # self._map_data.restored_map = False
                if self._map_data is not None:
                    DreameVacuumMapDecoder.set_floor_material(self._map_data, self._capability)

            self.map_manager._map_request_count = 0
            self.map_manager._map_request_time = None
            self.map_manager._need_map_request = True
            self.map_manager._need_map_list_request = True

    def set_cleaning_sequence(self, cleaning_sequence: list[int]) -> list[int] | None:
        map_data = self._map_data
        if map_data and map_data.segments and not map_data.temporary_map:
            new_cleaning_sequence = []
            if cleaning_sequence:
                for k, v in map_data.segments.items():
                    if k not in cleaning_sequence:
                        map_data.segments[k].order = 0
                        map_data.cleanset[str(k)][3] = 0

                index = 1
                for k in cleaning_sequence:
                    if int(k) in map_data.segments.keys():
                        map_data.segments[k].order = index
                        map_data.cleanset[str(k)][3] = index
                        new_cleaning_sequence.append(k)
                        index = index + 1
            else:
                for k in map_data.segments.keys():
                    map_data.segments[k].order = 0
                    map_data.cleanset[str(k)][3] = 0

            if self._saved_map_data and map_data.map_id in self._saved_map_data:
                self._saved_map_data[map_data.map_id].cleanset = copy.deepcopy(map_data.cleanset)

            self._set_updated_frame_id(map_data.frame_id)
            self.refresh_map()
            return cast("list[int] | None", self.map_manager.cleaning_sequence)
        return None

    def set_segment_order(self, segment_id: int, order: int) -> list[int] | None:
        map_data = self._map_data
        if map_data and map_data.segments and segment_id in map_data.segments and not map_data.temporary_map:
            if order > 0:
                current_order = map_data.segments[segment_id].order
                if current_order != order:
                    map_data.segments[segment_id].order = order
                    map_data.cleanset[str(segment_id)][3] = order
                    for k, v in map_data.segments.items():
                        if k != segment_id and v.order == order:
                            map_data.segments[k].order = (
                                len(self.map_manager.cleaning_sequence or []) if not current_order else current_order
                            )
            else:
                map_data.segments[segment_id].order = 0

            index = 1
            for k in self.map_manager.cleaning_sequence or []:
                if map_data.segments[k].order:
                    map_data.segments[k].order = index
                    map_data.cleanset[str(k)][3] = index
                    index = index + 1
                else:
                    map_data.cleanset[str(k)][3] = 0

            if (
                self._saved_map_data
                and self._selected_map_id is not None
                and self._selected_map_id in self._saved_map_data
            ):
                self._saved_map_data[self._selected_map_id].cleanset = copy.deepcopy(map_data.cleanset)

            self._set_updated_frame_id(map_data.frame_id)
            self.refresh_map()
            return cast("list[int] | None", self.map_manager.cleaning_sequence)
        return None

    def cleanset(self, map_data: MapData) -> Any:
        cleanset: list[Any] = []
        has_cleaning_mode = False
        has_mopping_settings = False
        for k, v in (map_data.segments or {}).items():
            if v.suction_level is None:
                v.suction_level = 1
            if v.water_volume is None:
                v.water_volume = 2
            if v.cleaning_times is None:
                v.cleaning_times = 1

            settings = [
                k,
                v.suction_level,
                v.wetness_level if v.wetness_level is not None else v.water_volume + 1,
                v.cleaning_times,
            ]

            if v.cleaning_mode is not None:
                has_cleaning_mode = True

            if has_cleaning_mode:
                settings.append(v.cleaning_mode if v.cleaning_mode is not None else 2)

            if v.mopping_settings:
                has_mopping_settings = True

            if has_mopping_settings:
                settings.append(v.mopping_settings if v.mopping_settings else 0)

            cleanset.append(settings)
        return cleanset

    def set_carpet_cleanset(self, carpet_cleanset: Any) -> None:
        map_data = self._map_data
        if map_data is None:
            return
        DreameVacuumMapDecoder.set_carpet_cleanset(map_data, carpet_cleanset, self._capability)
        map_data.carpet_cleanset = carpet_cleanset
        self._set_updated_frame_id(map_data.frame_id)
        self.refresh_map()

    def set_custom_carpet_settings(self, carpet_cleanset: Any) -> Any:
        map_data = self._map_data
        if map_data is not None and map_data.carpet_cleanset:
            cleanset = []
            new_carpet_cleanset = map_data.carpet_cleanset.copy()
            for selected_carpet in carpet_cleanset:
                for carpet in new_carpet_cleanset:
                    if carpet[0] == selected_carpet[0] and carpet[1] == selected_carpet[1]:
                        if len(carpet) > 3:
                            carpet[3] = selected_carpet[3]
                        cleanset.append(carpet.copy())
                        break
            self.set_carpet_cleanset(new_carpet_cleanset)
            carpet_cleanset = cleanset
        return carpet_cleanset

    def set_custom_carpet_cleaning(self, carpet_cleanset: Any) -> Any:
        map_data = self._map_data
        if map_data is not None and map_data.carpet_cleanset:
            cleanset = []
            new_carpet_cleanset = map_data.carpet_cleanset.copy()
            for selected_carpet in carpet_cleanset:
                for carpet in new_carpet_cleanset:
                    if carpet[0] == selected_carpet[0] and carpet[1] == selected_carpet[1]:
                        carpet[2] = selected_carpet[2]
                        item = [carpet[0], carpet[1], carpet[2]]
                        if len(carpet) > 3 and self._capability.carpet_cleanset_v3:
                            if (
                                carpet[2] == -1
                                or len(selected_carpet) < 4
                                or selected_carpet[3] == -1
                                or selected_carpet[3] is None
                            ):
                                carpet[3] = -1
                            else:
                                carpet[3] = selected_carpet[3]
                                item.append(carpet[3])
                        cleanset.append(item)
                        break
            self.set_carpet_cleanset(new_carpet_cleanset)
            carpet_cleanset = cleanset
        return carpet_cleanset

    def set_segment_suction_level(self, segment_id: int, suction_level: int, refresh_map: bool = True) -> Any:
        map_data = self._map_data
        if map_data and map_data.segments and segment_id in map_data.segments and not map_data.temporary_map:
            map_data.segments[segment_id].suction_level = suction_level
            map_data.cleanset[str(segment_id)][0] = suction_level
            if (
                self._saved_map_data
                and self._selected_map_id is not None
                and self._selected_map_id in self._saved_map_data
            ):
                self._saved_map_data[self._selected_map_id].cleanset = copy.deepcopy(map_data.cleanset)
            if refresh_map:
                self._set_updated_frame_id(map_data.frame_id)
                self.refresh_map()
                return self.cleanset(map_data)
        return None

    def set_segment_water_volume(self, segment_id: int, water_volume: int, refresh_map: bool = True) -> Any:
        map_data = self._map_data
        if map_data and map_data.segments and segment_id in map_data.segments:
            map_data.segments[segment_id].water_volume = water_volume
            map_data.cleanset[str(segment_id)][1] = water_volume + 1
            if map_data.segments[segment_id].custom_mopping_route is not None:
                values = DreameVacuumMapDecoder.split_mopping_settings(
                    map_data.segments[segment_id].mopping_settings or 0
                )
                if values:
                    # Set mopping mode or water volume according to the mopping effect switch
                    values[2 if map_data.segments[segment_id].custom_mopping_route == -1 else 1] = water_volume
                    map_data.segments[segment_id].mopping_settings = DreameVacuumMapDecoder.combine_mopping_settings(
                        values
                    )
                    map_data.cleanset[str(segment_id)][5] = map_data.segments[segment_id].mopping_settings

            if (
                self._saved_map_data
                and self._selected_map_id is not None
                and self._selected_map_id in self._saved_map_data
            ):
                self._saved_map_data[self._selected_map_id].cleanset = copy.deepcopy(map_data.cleanset)
            if refresh_map:
                self._set_updated_frame_id(map_data.frame_id)
                self.refresh_map()
                return self.cleanset(map_data)
        return None

    def set_segment_wetness_level(self, segment_id: int, wetness_level: int, refresh_map: bool = True) -> Any:
        map_data = self._map_data
        if map_data and map_data.segments and segment_id in map_data.segments:
            wetness_level = int(wetness_level)
            map_data.cleanset[str(segment_id)][1] = wetness_level
            map_data.segments[segment_id].wetness_level = wetness_level

            if wetness_level > (14 if self._capability.mop_clean_frequency else 26):
                map_data.segments[segment_id].water_volume = 3
            elif wetness_level < 6:
                map_data.segments[segment_id].water_volume = 1
            else:
                map_data.segments[segment_id].water_volume = 2

            if map_data.segments[segment_id].custom_mopping_route is not None:
                map_data.segments[segment_id].custom_mopping_route = 0

                values = DreameVacuumMapDecoder.split_mopping_settings(
                    map_data.segments[segment_id].mopping_settings or 0
                )
                if values:
                    values[1] = 0
                    values[2] = 0
                    map_data.segments[segment_id].mopping_settings = DreameVacuumMapDecoder.combine_mopping_settings(
                        values
                    )
                    map_data.cleanset[str(segment_id)][5] = map_data.segments[segment_id].mopping_settings

            if (
                self._saved_map_data
                and self._selected_map_id is not None
                and self._selected_map_id in self._saved_map_data
            ):
                self._saved_map_data[self._selected_map_id].cleanset = copy.deepcopy(map_data.cleanset)
            if refresh_map:
                self._set_updated_frame_id(map_data.frame_id)
                self.refresh_map()
                return self.cleanset(map_data)
        return None

    def set_segment_cleaning_times(self, segment_id: int, cleaning_times: int, refresh_map: bool = True) -> Any:
        map_data = self._map_data
        if map_data and map_data.segments and segment_id in map_data.segments and not map_data.temporary_map:
            map_data.segments[segment_id].cleaning_times = cleaning_times
            map_data.cleanset[str(segment_id)][2] = cleaning_times
            if (
                self._saved_map_data
                and self._selected_map_id is not None
                and self._selected_map_id in self._saved_map_data
            ):
                self._saved_map_data[self._selected_map_id].cleanset = copy.deepcopy(map_data.cleanset)
            if refresh_map:
                self._set_updated_frame_id(map_data.frame_id)
                self.refresh_map()
                return self.cleanset(map_data)
        return None

    def set_segment_cleaning_mode(self, segment_id: int, cleaning_mode: int, refresh_map: bool = True) -> Any:
        map_data = self._map_data
        if (
            map_data
            and map_data.segments
            and segment_id in map_data.segments
            and not map_data.temporary_map
            and map_data.segments[segment_id].cleaning_mode is not None
        ):
            map_data.segments[segment_id].cleaning_mode = cleaning_mode
            map_data.cleanset[str(segment_id)][4] = cleaning_mode
            if (
                self._saved_map_data
                and self._selected_map_id is not None
                and self._selected_map_id in self._saved_map_data
            ):
                self._saved_map_data[self._selected_map_id].cleanset = copy.deepcopy(map_data.cleanset)
            if refresh_map:
                self._set_updated_frame_id(map_data.frame_id)
                self.refresh_map()
                return self.cleanset(map_data)
        return None

    def set_segment_custom_mopping_route(
        self, segment_id: int, custom_mopping_route: int, refresh_map: bool = True
    ) -> Any:
        map_data = self._map_data
        if map_data and map_data.segments and segment_id in map_data.segments:
            if map_data.segments[segment_id].custom_mopping_route is not None:
                map_data.segments[segment_id].custom_mopping_route = custom_mopping_route
                values = DreameVacuumMapDecoder.split_mopping_settings(
                    map_data.segments[segment_id].mopping_settings or 0
                )
                if values:
                    # Set mopping effect switch or cleaning route
                    if map_data.segments[segment_id].custom_mopping_route == -1:
                        values[2] = map_data.segments[segment_id].water_volume or 0
                        map_data.segments[segment_id].cleaning_route = 1 if values[2] == 2 else values[2]
                    else:
                        values[2] = 0
                        values[0] = custom_mopping_route + 1
                        map_data.segments[segment_id].cleaning_route = values[0]

                    map_data.segments[segment_id].mopping_settings = DreameVacuumMapDecoder.combine_mopping_settings(
                        values
                    )
                    map_data.cleanset[str(segment_id)][5] = map_data.segments[segment_id].mopping_settings

            if (
                self._saved_map_data
                and self._selected_map_id is not None
                and self._selected_map_id in self._saved_map_data
            ):
                self._saved_map_data[self._selected_map_id].cleanset = copy.deepcopy(map_data.cleanset)
            if refresh_map:
                self._set_updated_frame_id(map_data.frame_id)
                self.refresh_map()
                return self.cleanset(map_data)
        return None

    def set_segment_cleaning_route(self, segment_id: int, cleaning_route: int, refresh_map: bool = True) -> Any:
        map_data = self._map_data
        if map_data and map_data.segments and segment_id in map_data.segments:
            if map_data.segments[segment_id].cleaning_route is not None:
                map_data.segments[segment_id].cleaning_route = cleaning_route
                values = DreameVacuumMapDecoder.split_mopping_settings(
                    map_data.segments[segment_id].mopping_settings or 0
                )
                if values:
                    values[2] = 0
                    values[0] = cleaning_route
                    map_data.segments[segment_id].custom_mopping_route = values[2] - 1
                    map_data.segments[segment_id].mopping_settings = DreameVacuumMapDecoder.combine_mopping_settings(
                        values
                    )
                    map_data.cleanset[str(segment_id)][5] = map_data.segments[segment_id].mopping_settings

            if (
                self._saved_map_data
                and self._selected_map_id is not None
                and self._selected_map_id in self._saved_map_data
            ):
                self._saved_map_data[self._selected_map_id].cleanset = copy.deepcopy(map_data.cleanset)
            if refresh_map:
                self._set_updated_frame_id(map_data.frame_id)
                self.refresh_map()
                return self.cleanset(map_data)
        return None

    def set_segment_floor_material(self, segment_id: int, floor_material: int, direction: int | None = None) -> Any:
        map_data = self._map_data
        if map_data and map_data.segments and segment_id in map_data.segments and not map_data.temporary_map:
            if direction is not None:
                if floor_material != 1:
                    direction = None
                elif map_data.rotation == 90 or map_data.rotation == 270:
                    direction = 0 if direction else 90

            map_data.segments[segment_id].floor_material = floor_material
            map_data.segments[segment_id].floor_material_direction = direction
            saved_entry = self._saved_map_data.get(self._selected_map_id) if self._selected_map_id is not None else None
            if saved_entry and saved_entry.segments and segment_id in saved_entry.segments:
                saved_entry.segments[segment_id].floor_material = floor_material
                saved_entry.segments[segment_id].floor_material_direction = direction
                DreameVacuumMapDecoder.set_segment_floor_material(
                    saved_entry,
                    segment_id,
                    saved_entry.floor_material,
                    self._capability,
                )
                self.refresh_map(self._selected_map_id)

            DreameVacuumMapDecoder.set_segment_floor_material(
                map_data, segment_id, map_data.floor_material, self._capability
            )
            self._set_updated_frame_id(map_data.frame_id)
            self.refresh_map()
            return {
                str(k): (
                    {
                        "material": v.floor_material,
                        "direction": v.floor_material_direction,
                    }
                    if v.floor_material_direction is not None
                    else {"material": v.floor_material}
                )
                for k, v in map_data.segments.items()
            }
        return {}

    def set_segment_visibility(self, segment_id: int, visibility: int) -> Any:
        map_data = self._map_data
        if map_data and map_data.segments and segment_id in map_data.segments and not map_data.temporary_map:
            map_data.segments[segment_id].visibility = visibility
            map_data.hidden_segments = [k for k, v in map_data.segments.items() if not v.visibility]
            if (
                self._saved_map_data
                and self._selected_map_id is not None
                and self._selected_map_id in self._saved_map_data
            ):
                saved_visibility_entry = self._saved_map_data[self._selected_map_id]
                saved_segments: Any = saved_visibility_entry.segments
                saved_segments[segment_id].visibility = visibility
                saved_visibility_entry.hidden_segments = [
                    k for k, v in (saved_visibility_entry.segments or {}).items() if not v.visibility
                ]

            self._set_updated_frame_id(map_data.frame_id)
            self.refresh_map()
            return map_data.hidden_segments
        return []

    def set_segment_name(
        self, segment_id: int, segment_type: int, custom_name: str | None = None
    ) -> dict[str, Any] | None:
        map_data = self._map_data
        if (
            map_data
            and map_data.segments
            and segment_id in map_data.segments
            and self._selected_map_id
            and not map_data.temporary_map
        ):
            if (
                map_data.segments[segment_id].type != segment_type
                or map_data.segments[segment_id].custom_name != custom_name
            ):
                segment_info: dict[Any, Any] = {}
                map_data.segments[segment_id].type = segment_type
                if segment_type == 0:
                    map_data.segments[segment_id].index = 0
                    if custom_name is not None:
                        if custom_name == "":
                            custom_name = None
                        map_data.segments[segment_id].custom_name = custom_name
                else:
                    map_data.segments[segment_id].custom_name = None
                    map_data.segments[segment_id].index = map_data.segments[segment_id].next_type_index(
                        segment_type, map_data.segments
                    )

                map_data.segments[segment_id].set_name()

                saved_name_segments: Any = self._saved_map_data[self._selected_map_id].segments
                saved_name_segments[segment_id].custom_name = map_data.segments[segment_id].custom_name
                saved_name_segments[segment_id].index = map_data.segments[segment_id].index
                saved_name_segments[segment_id].type = map_data.segments[segment_id].type
                saved_name_segments[segment_id].set_name()
                self.refresh_map(self._selected_map_id)

                for k, v in map_data.segments.items():
                    segment_name = v.custom_name
                    if segment_name is not None:
                        segment_info[k] = {
                            MAP_PARAMETER_NAME: base64.b64encode(segment_name.encode("utf-8")).decode("utf-8"),
                            MAP_REQUEST_PARAMETER_TYPE: 0,
                            MAP_REQUEST_PARAMETER_INDEX: 0,
                        }
                    elif v.type:
                        segment_info[k] = {
                            MAP_REQUEST_PARAMETER_TYPE: v.type,
                            MAP_REQUEST_PARAMETER_INDEX: v.index,
                        }
                    else:
                        segment_info[k] = {}

                    if v.unique_id:
                        segment_info[k][MAP_REQUEST_PARAMETER_ROOM_ID] = v.unique_id

                self._set_updated_frame_id(map_data.frame_id)
                self.refresh_map()
                return segment_info
        return None

    def set_zones(self, virtual_walls: Any, no_go_areas: Any, no_mopping_areas: Any) -> None:
        map_data = self._map_data
        if not map_data or not self._selected_map_id:
            return

        map_data.no_mopping_areas = []
        if no_mopping_areas:
            for area in no_mopping_areas:
                x_coords = sorted([area[0], area[2]])
                y_coords = sorted([area[1], area[3]])
                map_data.no_mopping_areas.append(
                    Area(
                        x_coords[0],
                        y_coords[0],
                        x_coords[1],
                        y_coords[0],
                        x_coords[1],
                        y_coords[1],
                        x_coords[0],
                        y_coords[1],
                    )
                )

        map_data.no_go_areas = []
        if no_go_areas:
            for area in no_go_areas:
                x_coords = sorted([area[0], area[2]])
                y_coords = sorted([area[1], area[3]])
                map_data.no_go_areas.append(
                    Area(
                        x_coords[0],
                        y_coords[0],
                        x_coords[1],
                        y_coords[0],
                        x_coords[1],
                        y_coords[1],
                        x_coords[0],
                        y_coords[1],
                    )
                )

        if virtual_walls:
            map_data.virtual_walls = [
                Wall(
                    wall[0],
                    wall[1],
                    wall[2],
                    wall[3],
                )
                for wall in virtual_walls
            ]
        else:
            map_data.virtual_walls = []

        self._set_updated_frame_id(map_data.frame_id)
        if self._saved_map_data and self._selected_map_id is not None and self._selected_map_id in self._saved_map_data:
            self._saved_map_data[self._selected_map_id].no_go_areas = map_data.no_go_areas
            self._saved_map_data[self._selected_map_id].no_mopping_areas = map_data.no_mopping_areas
            self._saved_map_data[self._selected_map_id].virtual_walls = map_data.virtual_walls
            self.refresh_map(self._selected_map_id)
        self.refresh_map()

    @property
    def _map_data(self) -> MapData | None:
        return self.map_manager._map_data

    @property
    def _capability(self) -> Any:
        return self.map_manager._capability

    @property
    def _saved_map_data(self) -> dict[int, MapData]:
        return self.map_manager._saved_map_data

    @property
    def _selected_map_id(self) -> int | None:
        return self.map_manager._selected_map_id

    @property
    def _current_timestamp_ms(self) -> int | None:
        return self.map_manager._current_timestamp_ms
