from __future__ import annotations

"""Map renderer module for Dreame vacuum integration.

Contains DreameVacuumMapRenderer for rendering map images with layers,
segments and objects.

Note: DreameVacuumMapDataJsonRenderer has been moved to map_data_json_renderer.py.
"""

import base64
import io
from io import BytesIO
import json
import logging
import math
import textwrap
import time
import traceback
from typing import Any, cast
import zlib

import numpy as np
from PIL import (
    Image,
    ImageDraw,
    ImageFilter,
    ImageFont,
    ImageOps,
)

from ..const import (
    MAP_DATA_JSON_PARAMETER_X,
    MAP_DATA_JSON_PARAMETER_Y,
    MAP_PARAMETER_MAP,
    MAP_PARAMETER_VACUUM,
)
from ..resources import *
from ..vacuum_types import (
    MAP_COLOR_SCHEME_LIST,
    MAP_ICON_SET_LIST,
    CleansetType,
    MapData,
    MapPixelType,
    MapRendererColorScheme,
    MapRendererConfig,
    MapRendererData,
    MapRendererLayer,
    MapRendererResources,
    Obstacle,
    PathType,
    Point,
    RecoveryMapType,
    RobotType,
)
from ._helpers import _StaticHelpersMixin
from ._layers import _LayersMixin
from ._objects import _ObjectsMixin
from ._resources_props import _ResourcesMixin
from ._segments_render import _SegmentsRenderMixin
from ._shapes import _ShapesMixin

_LOGGER = logging.getLogger(__name__)


class DreameVacuumMapRenderer(
    _LayersMixin, _SegmentsRenderMixin, _ResourcesMixin, _ObjectsMixin, _ShapesMixin, _StaticHelpersMixin
):
    def __init__(
        self,
        color_scheme: str | None = None,
        icon_set: str | None = None,
        hidden_map_objects: list[str] | None = None,
        robot_type: Any = 0,
        low_resolution: bool = False,
        square: bool = False,
        cache: bool = True,
        language: str | None = None,
        vector_rooms: bool = False,
        render_scale: int = 2,
    ) -> None:
        self.color_scheme: MapRendererColorScheme = MAP_COLOR_SCHEME_LIST.get(
            color_scheme or "", MapRendererColorScheme()
        )
        self.icon_set: int = MAP_ICON_SET_LIST.get(icon_set or "", 0)
        self.config: MapRendererConfig = MapRendererConfig()
        if hidden_map_objects is not None:
            for attr in self.config.__dict__:
                if attr in hidden_map_objects:
                    setattr(self.config, attr, False)

        self._map_data: MapData | None = None
        self.render_complete: bool = True
        self._layers: dict[MapRendererLayer, Any] = {}
        self._robot_status: int | None = None
        self._station_status: int | None = None
        self._robot_type: Any = robot_type
        self._low_resolution: bool = low_resolution
        self._low_memory: bool = low_resolution
        # Render-resolution multiplier for the live map PNG (1/2/3). Higher =
        # crisper under the card's pinch-zoom, at a memory/CPU cost that grows
        # with the square of the factor. Ignored in low-resolution mode.
        self._render_scale: int = max(1, min(3, int(render_scale)))
        # Subtle inner-edge shading so the floor reads as a slightly raised panel
        # over the transparent surround (relief vs the non-room zone).
        self._map_relief: bool = True
        self._square: bool = square
        self._vector_rooms: bool = vector_rooms
        self._cache: bool = cache
        self._language: str | None = language
        self._has_mask: bool = False
        self._calibration_points: Any = None
        self._default_calibration_points: Any = [
            {
                MAP_PARAMETER_VACUUM: {
                    MAP_DATA_JSON_PARAMETER_X: 0,
                    MAP_DATA_JSON_PARAMETER_Y: 0,
                },
                MAP_PARAMETER_MAP: {
                    MAP_DATA_JSON_PARAMETER_X: 0,
                    MAP_DATA_JSON_PARAMETER_Y: 0,
                },
            },
            {
                MAP_PARAMETER_VACUUM: {
                    MAP_DATA_JSON_PARAMETER_X: 1000,
                    MAP_DATA_JSON_PARAMETER_Y: 0,
                },
                MAP_PARAMETER_MAP: {
                    MAP_DATA_JSON_PARAMETER_X: 0,
                    MAP_DATA_JSON_PARAMETER_Y: 0,
                },
            },
            {
                MAP_PARAMETER_VACUUM: {
                    MAP_DATA_JSON_PARAMETER_X: 0,
                    MAP_DATA_JSON_PARAMETER_Y: 1000,
                },
                MAP_PARAMETER_MAP: {
                    MAP_DATA_JSON_PARAMETER_X: 0,
                    MAP_DATA_JSON_PARAMETER_Y: 0,
                },
            },
        ]

        self._image: Any = None
        self._charger_icon = None
        self._robot_icon = None
        self._robot_icon_data_uri = None
        self._robot_icon_lit_data_uri = None
        self._robot_beam_icon_data_uri = None
        self._robot_charging_icon = None
        self._robot_cleaning_icon = None
        self._robot_warning_icon = None
        self._robot_sleeping_icon = None
        self._robot_washing_icon = None
        self._robot_hot_washing_icon = None
        self._robot_drying_icon = None
        self._robot_hot_drying_icon = None
        self._robot_emptying_icon = None
        self._robot_cleaning_direction_icon = None
        self._obstacle_background = None
        self._obstacle_hidden_background = None
        self._cruise_path_point_background = None
        self._cruise_point_background = None
        self._furniture_background = None
        self._wifi_icon = None
        self._font_file = None
        self._light_font_file: Any = None
        self._default_map_image: Any = None
        self._default_map_image_data: bytes | None = None
        self._disconnected_map_image_data: bytes | None = None
        self._disconnected_map_image_src: Any = None
        self._obstacle_bottom_left_icon: Any = None
        self._obstacle_top_left_icon: Any = None
        self._obstacle_bottom_right_icon: Any = None
        self._obstacle_top_right_icon: Any = None
        self._map_problem_icon = None

        # Status-icon sets: decoded lazily by _warm_up_icons() (first
        # render_map() call, always executor-side) so constructing a
        # renderer on the event loop stays cheap. See _warm_up_icons().
        self._icons_warmed = False
        self._cleaning_times_icon: Any = None
        self._suction_level_icon: Any = None
        self._water_volume_icon: Any = None
        self._mop_pad_humidity_icon: Any = None
        self._cleaning_mode_icon: Any = None
        self._cleaning_route_icon: Any = None
        self._custom_mopping_route_icon: Any = None

        self._segment_icons: dict[Any, Any] = {}
        self._obstacle_icons = {}
        self._obstacle_hidden_icons = {}
        self._furniture_icons = {}
        self._furniture_images = {}
        self._badge_positions: dict[Any, Any] = {}
        self._name_offsets: dict[Any, Any] = {}

        if self._low_memory:
            self.config.obstacle = False
            self.config.pet = False
            self.config.furniture = False

    def _warm_up_icons(self) -> None:
        """Decode the status-icon sets (PIL, CPU-bound).

        Deferred out of __init__ so constructing a renderer on the event
        loop stays cheap; render paths run in an executor and call this
        before touching the icon lists.
        """
        if self._icons_warmed:
            return
        self._icons_warmed = True

        if self.icon_set == 2:
            repeats = MAP_ICON_REPEATS_MIJIA
            suction_level = MAP_ICON_SUCTION_LEVEL_MIJIA
            water_volume = MAP_ICON_WATER_VOLUME_MIJIA
            cleaning_mode = MAP_ICON_CLEANING_MODE_MIJIA
        elif self.icon_set == 3:
            repeats = MAP_ICON_REPEATS_MATERIAL
            suction_level = MAP_ICON_SUCTION_LEVEL_MATERIAL
            water_volume = MAP_ICON_WATER_VOLUME_MATERIAL
            cleaning_mode = MAP_ICON_CLEANING_MODE_MATERIAL
        else:
            repeats = MAP_ICON_REPEATS_DREAME
            suction_level = MAP_ICON_SUCTION_LEVEL_DREAME
            water_volume = MAP_ICON_WATER_VOLUME_DREAME
            cleaning_mode = MAP_ICON_CLEANING_MODE_DREAME

        if self.config.cleaning_times:
            self._cleaning_times_icon = [
                Image.open(BytesIO(base64.b64decode(icon))).convert("RGBA") for icon in repeats
            ]
        if self.config.suction_level:
            self._suction_level_icon = [
                Image.open(BytesIO(base64.b64decode(icon))).convert("RGBA") for icon in suction_level
            ]
        if self.config.water_volume:
            self._water_volume_icon = [
                Image.open(BytesIO(base64.b64decode(icon))).convert("RGBA") for icon in water_volume
            ]
            self._mop_pad_humidity_icon = [
                Image.open(BytesIO(base64.b64decode(icon))).convert("RGBA")
                for icon in (
                    MAP_ICON_MOP_PAD_HUMIDITY_MATERIAL if self.icon_set == 3 else MAP_ICON_MOP_PAD_HUMIDITY_DREAME
                )
            ]
        if self.config.cleaning_mode:
            self._cleaning_mode_icon = [
                Image.open(BytesIO(base64.b64decode(icon))).convert("RGBA") for icon in cleaning_mode
            ]
        if self.config.mopping_mode:
            self._cleaning_route_icon = [
                Image.open(BytesIO(base64.b64decode(icon))).convert("RGBA")
                for icon in (MAP_ICON_CLEANING_ROUTE_MATERIAL if self.icon_set == 3 else MAP_ICON_CLEANING_ROUTE_DREAME)
            ]
            self._custom_mopping_route_icon = [
                Image.open(BytesIO(base64.b64decode(icon))).convert("RGBA")
                for icon in MAP_ICON_CUSTOM_MOPPING_ROUTE_DREAME
            ]

    # _to_buffer, _set_icon_color: see _StaticHelpersMixin

    @staticmethod
    def _calculate_bounds(dimensions: Any, segments: Any) -> list[int] | None:
        if segments:
            min_x = dimensions.width - 1
            min_y = dimensions.height - 1
            max_x = 0
            max_y = 0
            for segment in segments.values():
                p = segment.to_coord(dimensions, False)
                x_coords = [int(p.x0), int(p.x1)]
                y_coords = [int(p.y0), int(p.y1)]
                min_x = min(min(x_coords), min_x)
                max_x = max(max(x_coords), max_x)
                min_y = min(min(y_coords), min_y)
                max_y = max(max(y_coords), max_y)

            return [min_x, min_y, max_x, min_y]
        return None

    @staticmethod
    def _calculate_padding(
        dimensions: Any,
        active_areas: Any,
        no_mopping_areas: Any,
        no_go_areas: Any,
        walls: Any,
        virtual_thresholds: Any,
        passable_thresholds: Any,
        impassable_thresholds: Any,
        ramps: Any,
        furnitures: Any,
        furniture_version: Any,
        curtains: Any,
        segments: Any,
        padding: Any,
        min_width: Any,
        min_height: Any,
        scale: Any,
        icon_set: Any,
    ) -> Any:
        min_x: float = 0
        min_y: float = 0
        max_x = dimensions.width
        max_y = dimensions.height

        if segments:
            for segment in segments.values():
                p = segment.to_coord(dimensions, False)
                x_coords = sorted([int(p.x0), int(p.x1)])
                y_coords = sorted([int(p.y0), int(p.y1)])
                min_x = min(x_coords[0], min_x)
                max_x = max(x_coords[1], max_x)
                min_y = min(y_coords[0], min_y)
                max_y = max(y_coords[1], max_y)

        if active_areas:
            for area in active_areas:
                p = area.to_coord(dimensions)
                x_coords = [p.x0, p.x1, p.x2, p.x3]
                y_coords = [p.y0, p.y1, p.y2, p.y3]
                min_x = min(min(x_coords), min_x)
                max_x = max(max(x_coords), max_x)
                min_y = min(min(y_coords), min_y)
                max_y = max(max(y_coords), max_y)

        if no_mopping_areas:
            for area in no_mopping_areas:
                p = area.to_coord(dimensions)
                x_coords = [p.x0, p.x1, p.x2, p.x3]
                y_coords = [p.y0, p.y1, p.y2, p.y3]
                min_x = min(min(x_coords), min_x)
                max_x = max(max(x_coords), max_x)
                min_y = min(min(y_coords), min_y)
                max_y = max(max(y_coords), max_y)

        if no_go_areas:
            for area in no_go_areas:
                p = area.to_coord(dimensions)
                x_coords = [p.x0, p.x1, p.x2, p.x3]
                y_coords = [p.y0, p.y1, p.y2, p.y3]
                min_x = min(min(x_coords), min_x)
                max_x = max(max(x_coords), max_x)
                min_y = min(min(y_coords), min_y)
                max_y = max(max(y_coords), max_y)

        if walls:
            for wall in walls:
                p = wall.to_coord(dimensions)
                x_coords = [p.x0, p.x1]
                y_coords = [p.y0, p.y1]
                min_x = min(min(x_coords), min_x)
                max_x = max(max(x_coords), max_x)
                min_y = min(min(y_coords), min_y)
                max_y = max(max(y_coords), max_y)

        if virtual_thresholds:
            for line in virtual_thresholds:
                p = line.to_coord(dimensions)
                x_coords = [p.x0, p.x1]
                y_coords = [p.y0, p.y1]
                min_x = min(min(x_coords), min_x)
                max_x = max(max(x_coords), max_x)
                min_y = min(min(y_coords), min_y)
                max_y = max(max(y_coords), max_y)

        if passable_thresholds:
            for line in passable_thresholds:
                p = line.to_coord(dimensions)
                x_coords = [p.x0, p.x1]
                y_coords = [p.y0, p.y1]
                min_x = min(min(x_coords), min_x)
                max_x = max(max(x_coords), max_x)
                min_y = min(min(y_coords), min_y)
                max_y = max(max(y_coords), max_y)

        if impassable_thresholds:
            for line in impassable_thresholds:
                p = line.to_coord(dimensions)
                x_coords = [p.x0, p.x1]
                y_coords = [p.y0, p.y1]
                min_x = min(min(x_coords), min_x)
                max_x = max(max(x_coords), max_x)
                min_y = min(min(y_coords), min_y)
                max_y = max(max(y_coords), max_y)

        if ramps:
            for area in ramps:
                p = area.to_coord(dimensions)
                x_coords = [p.x0, p.x1, p.x2, p.x3]
                y_coords = [p.y0, p.y1, p.y2, p.y3]
                min_x = min(min(x_coords), min_x)
                max_x = max(max(x_coords), max_x)
                min_y = min(min(y_coords), min_y)
                max_y = max(max(y_coords), max_y)

        if furnitures:
            if furniture_version >= 2:
                furniture_images = (
                    FURNITURE_V2_TYPE_MIJIA_TO_IMAGE if furniture_version == 3 else FURNITURE_V2_TYPE_TO_IMAGE
                )
                furniture_icons = FURNITURE_V2_TYPE_TO_ICON
            else:
                furniture_images = FURNITURE_TYPE_TO_IMAGE
                furniture_icons = FURNITURE_TYPE_TO_ICON

            for v in furnitures.values():
                p = Point(v.x, v.y).to_coord(dimensions)
                w = 0
                h = 0
                if v.width and v.height:
                    if v.type.value not in furniture_images:
                        continue
                    w = int((v.width / dimensions.grid_size) / 2)
                    h = int((v.height / dimensions.grid_size) / 2)
                elif v.type.value not in furniture_icons:
                    continue
                min_x = min(p.x - w, min_x)
                max_x = max(p.x + w, max_x)
                min_y = min(p.y - h, min_y)
                max_y = max(p.y + h, max_y)

        if curtains:
            for line in curtains:
                p = line.to_coord(dimensions)
                x_coords = [p.x0, p.x1]
                y_coords = [p.y0, p.y1]
                min_x = min(min(x_coords), min_x)
                max_x = max(max(x_coords), max_x)
                min_y = min(min(y_coords), min_y)
                max_y = max(max(y_coords), max_y)

        if min_x < 0:
            padding[0] = padding[0] + int(-min_x)
        if max_x > dimensions.width:
            padding[2] = padding[2] + int(max_x - dimensions.width)
        if min_y < 0:
            padding[1] = padding[1] + int(-min_y)
        if max_y > dimensions.height:
            padding[3] = padding[3] + int(max_y - dimensions.height)

        if dimensions.width + padding[0] + padding[2] < min_width:
            size = int((min_width - dimensions.width + padding[0] + padding[2]) / 2)
            padding[0] = padding[0] + size
            padding[2] = padding[2] + size

        if dimensions.height + padding[1] + padding[3] < min_height:
            size = int((min_height - dimensions.height + padding[1] + padding[3]) / 2)
            padding[1] = padding[1] + size
            padding[3] = padding[3] + size

        for k in range(4):
            padding[k] = padding[k] * scale

        return padding

    # _round_coord: see _StaticHelpersMixin

    @staticmethod
    def _get_carpet_coords(carpet: Any, dimensions: Any) -> Any:
        grid_size = dimensions.grid_size
        if carpet.ellipse:
            x0 = DreameVacuumMapRenderer._round_coord(carpet.x0 - grid_size / 2, grid_size) + grid_size / 2
            y0 = DreameVacuumMapRenderer._round_coord(carpet.y0 - grid_size / 2, grid_size) + grid_size / 2
            x2 = DreameVacuumMapRenderer._round_coord(carpet.x2, grid_size)
            y2 = DreameVacuumMapRenderer._round_coord(carpet.y2, grid_size)

            x_coords = sorted([x0, x2])
            y_coords = sorted([y0, y2])

            return (
                int(math.ceil((x_coords[0] - x_coords[1] - dimensions.left) / grid_size)),
                int(math.ceil((y_coords[0] - y_coords[1] - dimensions.top) / grid_size)),
                int(math.ceil(((x_coords[0] + x_coords[1] - dimensions.left) / grid_size) + 1)),
                int(math.ceil(((y_coords[0] + y_coords[1] - dimensions.top) / grid_size) + 1)),
            )
        left = dimensions.left
        top = dimensions.top
        if left % dimensions.grid_size != 0 or top % dimensions.grid_size != 0:
            left = left + (dimensions.grid_size / 2)
            top = top + (dimensions.grid_size / 2)

        x_coords = sorted([carpet.x0, carpet.x2])
        y_coords = sorted([carpet.y0, carpet.y2])

        return (
            int(math.ceil((x_coords[0] - left) / grid_size)),
            int(math.ceil((y_coords[0] - top) / grid_size)),
            int(math.ceil((x_coords[1] - left) / grid_size)),
            int(math.ceil((y_coords[1] - top) / grid_size)),
        )

    @staticmethod
    def _optimize_carpet_pixels(carpet_pixels: Any, dimensions: Any, pixel_type: Any) -> Any:
        carpet_data = {}
        for pixel in carpet_pixels:
            x = pixel[0]
            y = pixel[1]
            for xx in range(max(0, x - 1), min(x + 3, dimensions.width - 1)):
                for yy in range(max(0, y - 1), min(y + 2, dimensions.height - 1)):
                    val = int(pixel_type[xx, yy])
                    if val > 0 and val != 255:
                        carpet_data[(xx, yy)] = 1
        return carpet_data

    @staticmethod
    def _check_carpet(x: Any, y: Any, carpet: Any, dimensions: Any, pixel_type: Any = None) -> Any:
        if pixel_type is not None and (
            pixel_type >= 255
            or pixel_type <= 0
            or (pixel_type < 254 and not carpet.polygon and carpet.segments and pixel_type not in carpet.segments)
        ):
            return False

        if carpet.ellipse or carpet.ignored_areas or carpet.polygon:
            x = (x * dimensions.grid_size) + dimensions.left
            y = (y * dimensions.grid_size) + dimensions.top

        if carpet.ellipse and not (
            (x - carpet.x0) * (x - carpet.x0) / (carpet.x2 * carpet.x2)
            + (y - carpet.y0) * (y - carpet.y0) / (carpet.y2 * carpet.y2)
            < 1
        ):
            return False

        if carpet.ignored_areas and isinstance(carpet.ignored_areas, list):
            for area in carpet.ignored_areas:
                if (
                    area
                    and isinstance(area, list)
                    and len(area) > 3
                    and x >= area[0]
                    and x <= area[2]
                    and y >= area[1]
                    and y <= area[3]
                ):
                    return False

        if carpet.polygon and len(carpet.polygon) <= 100:
            check = False
            polygon = carpet.polygon
            for i in range(0, len(polygon), 2):
                j = len(polygon) - 2 if i == 0 else i - 2

                sx = polygon[i]
                sy = polygon[i + 1]
                tx = polygon[j]
                ty = polygon[j + 1]

                if sx == x and sy == y and tx == x and ty == y:
                    return True
                if sy == ty and sy == y and ((sx > x and tx < x) or (sx < x and tx > x)):
                    return True
                if (sy < y and ty >= y) or (sy >= y and ty < y):
                    xx = sx + (y - sy) * (tx - sx) / (ty - sy)
                    if xx == x:
                        return True
                    if xx > x:
                        check = not check
            return check
        return True

    # _calculate_calibration_points, _alpha_composite, _close_image, _del_layer,
    # _replace_layer, _combine_layers, _coords_on_line: see _StaticHelpersMixin

    def get_data_string(
        self,
        map_data: MapData | None,
        resources: MapRendererResources | str | None = None,
        robot_status: int = 0,
        station_status: int = 0,
    ) -> str:
        if (
            not map_data
            or map_data.dimensions is None
            or map_data.empty_map
            or (map_data.dimensions.width * map_data.dimensions.height) < 2
        ):
            map_data_json = MapRendererData(
                size=[
                    0,
                    0,
                    1,
                    1,
                    0,
                    0,
                    [0, 0, 0, 0],
                ],
                data=None,
                empty_map=True,
                resources=resources,
            )
        else:
            pixels: dict[int, Any] = {}
            min_x = map_data.dimensions.width - 1
            min_y = map_data.dimensions.height - 1
            max_x = 0
            max_y = 0
            for y in range(map_data.dimensions.height):
                for x in range(map_data.dimensions.width):
                    px_type = int(map_data.pixel_type[x, y])
                    if px_type:
                        # if map_data.segments and map_data.saved_map and px_type == 255:
                        #    pixel = map_data.data[(map_data.dimensions.width * y) + x]
                        #    if pixel > 0:
                        #        px_type = px_type + (pixel & 0x3F)

                        if px_type in pixels:
                            pixels[px_type].extend([x, y])
                        else:
                            pixels[px_type] = [x, y]
                        max_x = max(x, max_x)
                        min_x = min(x, min_x)
                        max_y = max(y, max_y)
                        min_y = min(y, min_y)

            if map_data.carpet_pixels:
                px_type = 512
                for px in map_data.carpet_pixels:
                    if px_type in pixels:
                        pixels[px_type].extend([px[0], px[1]])
                    else:
                        pixels[px_type] = [px[0], px[1]]

            crop = [0, 0, 0, 0]

            if not map_data.saved_map:
                map_data.dimensions.bounds = DreameVacuumMapRenderer._calculate_bounds(
                    map_data.dimensions, map_data.segments
                )

            if map_data.dimensions.bounds:
                min_x = max(min(map_data.dimensions.bounds[0], min_x), min_x)
                max_x = min(max(map_data.dimensions.bounds[2], max_x), max_x)
                min_y = max(min(map_data.dimensions.bounds[1], min_y), min_y)
                max_y = min(max(map_data.dimensions.bounds[3], max_y), max_y)

            if (
                min_x != (map_data.dimensions.width - 1)
                and min_y != (map_data.dimensions.height - 1)
                and max_x != 0
                and max_y != 0
            ) and (
                min_x != 0
                or min_y != 0
                or max_x != (map_data.dimensions.width - 1)
                or max_y != (map_data.dimensions.height - 1)
            ):
                crop = [
                    min_x,
                    (map_data.dimensions.height - (max_y + 1)),
                    (map_data.dimensions.width - (max_x + 1)),
                    min_y,
                ]

            for layer in pixels:
                current_x_start = -1
                current_y = -1
                current_count = 0
                compressed_pixels = []
                coords = pixels[layer]
                for i in range(0, len(coords), 2):
                    x = coords[i]
                    y = coords[i + 1]
                    if y != current_y or x > (current_x_start + current_count):
                        compressed_pixels.extend([current_x_start, current_y, current_count])
                        current_x_start = x
                        current_y = y
                        current_count = 1
                    elif x != current_x_start:
                        current_count = current_count + 1
                compressed_pixels.extend([current_x_start, current_y, current_count])
                pixels[layer] = compressed_pixels[3:]

            path_types = {"S": 1, "W": 2, "M": 3}
            paths: Any = None
            if map_data.path:
                paths = []
                coords = [
                    path_types.get(map_data.path[0].path_type),
                    map_data.path[0].x,
                    map_data.path[0].y,
                ]
                for path in map_data.path[1:]:
                    if path.path_type.value != "L":
                        paths.append(coords)
                        coords = [path_types.get(path.path_type)]
                    coords.extend([path.x, path.y])

                if len(coords) > 2:
                    paths.append(coords)

            map_data_json = MapRendererData(
                data=pixels,
                size=[
                    map_data.dimensions.left,
                    map_data.dimensions.top,
                    map_data.dimensions.width if not map_data.empty_map else 1,
                    map_data.dimensions.height if not map_data.empty_map else 1,
                    map_data.dimensions.grid_size,
                    map_data.rotation,
                    crop,
                ],
                map_id=map_data.map_id,
                saved_map_id=map_data.saved_map_id,
                map_index=map_data.map_index,
                saved_map_status=map_data.saved_map_status,
                empty_map=map_data.empty_map,
                frame_id=map_data.frame_id,
                active_segments=map_data.active_segments,
                cleanset=bool(map_data.cleanset) if not map_data.saved_map and not map_data.wifi_map else False,
                sequence=bool(map_data.sequence) if not map_data.saved_map and not map_data.wifi_map else False,
                docked=map_data.docked,
                floor_material=map_data.floor_material,
                hidden_segments=map_data.hidden_segments,
                neglected_segments=map_data.neglected_segments,
                robot_status=robot_status if not map_data.saved_map and not map_data.wifi_map else 0,
                station_status=station_status if not map_data.saved_map and not map_data.wifi_map else 0,
                saved_map=map_data.saved_map,
                wifi_map=map_data.wifi_map,
                history_map=map_data.history_map,
                recovery_map=map_data.recovery_map,
                path=paths if not map_data.saved_map and not map_data.wifi_map else [],
                robot_position=(
                    [
                        map_data.robot_position.x,
                        map_data.robot_position.y,
                        map_data.robot_position.a,
                    ]
                    if map_data.robot_position
                    else None
                ),
                charger_position=(
                    [
                        map_data.charger_position.x,
                        map_data.charger_position.y,
                        map_data.charger_position.a,
                    ]
                    if map_data.charger_position
                    else None
                ),
                router_position=(
                    [
                        map_data.router_position.x,
                        map_data.router_position.y,
                    ]
                    if map_data.router_position
                    else None
                ),
                startup_method=map_data.startup_method.name.lower() if map_data.startup_method is not None else None,
                cleanup_method=map_data.cleanup_method.name.lower() if map_data.cleanup_method is not None else None,
                second_cleaning=map_data.second_cleaning,
                mop_wash_count=map_data.mop_wash_count,
                dust_collection_count=map_data.dust_collection_count,
                multiple_cleaning_time=map_data.multiple_cleaning_time,
                dos=map_data.dos,
                cleaned_area=map_data.cleaned_area,
                cleaning_time=map_data.cleaning_time,
                work_status=map_data.work_status,
                completed=map_data.completed,
                remaining_battery=map_data.remaining_battery,
                segments=(
                    [
                        [
                            k,
                            v.x,
                            v.y,
                            v.type,
                            base64.b64encode(v.custom_name.encode("utf-8")).decode("utf-8") if v.custom_name else None,
                            v.index,
                            v.color_index,
                            v.order,
                            v.suction_level,
                            v.water_volume,
                            v.cleaning_times,
                            v.cleaning_mode if v.cleanset_type != CleansetType.DEFAULT else None,
                            v.custom_mopping_route if v.cleanset_type == CleansetType.CUSTOM_MOPPING_ROUTE else None,
                            v.cleaning_route if v.cleanset_type != CleansetType.CUSTOM_MOPPING_ROUTE else None,
                            (
                                v.wetness_level
                                if v.cleanset_type == CleansetType.WETNESS_LEVEL
                                or v.cleanset_type == CleansetType.WETNESS_LEVEL_MAX_15
                                else None
                            ),
                            v.floor_material,
                            v.floor_material_direction,
                            v.visibility,
                            [v.x0, v.y0, v.x1, v.y1],
                            v.carpet_cleaning,
                            v.carpet_settings,
                        ]
                        for (k, v) in map_data.segments.items()
                    ]
                    if map_data.segments
                    else None
                ),
                active_areas=(
                    [
                        [
                            area.x0,
                            area.y0,
                            area.x1,
                            area.y1,
                            area.x2,
                            area.y2,
                            area.x3,
                            area.y3,
                        ]
                        for area in map_data.active_areas
                    ]
                    if map_data.active_areas
                    else []
                ),
                active_points=(
                    [[point.x0, point.y0] for point in cast("list[Any]", map_data.active_points)]
                    if map_data.active_points
                    else []
                ),
                active_cruise_points=(
                    [
                        [point.x, point.y, point.type, point.completed]
                        for point in map_data.active_cruise_points.values()
                    ]
                    if map_data.active_cruise_points
                    else []
                ),
                task_cruise_points=bool(map_data.task_cruise_points),
                virtual_walls=(
                    [
                        [virtual_wall.x0, virtual_wall.y0, virtual_wall.x1, virtual_wall.y1]
                        for virtual_wall in map_data.virtual_walls
                    ]
                    if map_data.virtual_walls
                    else []
                ),
                no_mop=(
                    [
                        [
                            area.x0,
                            area.y0,
                            area.x1,
                            area.y1,
                            area.x2,
                            area.y2,
                            area.x3,
                            area.y3,
                            area.angle,
                        ]
                        for area in map_data.no_mopping_areas
                    ]
                    if map_data.no_mopping_areas
                    else []
                ),
                no_go=(
                    [
                        [
                            area.x0,
                            area.y0,
                            area.x1,
                            area.y1,
                            area.x2,
                            area.y2,
                            area.x3,
                            area.y3,
                            area.angle,
                        ]
                        for area in map_data.no_go_areas
                    ]
                    if map_data.no_go_areas
                    else []
                ),
                obstacles=(
                    [
                        [
                            k,
                            v.x,
                            v.y,
                            v.type.value,
                            v.possibility,
                            v.ignore_status,
                            v.picture_status,
                            v.id,
                            v.pos_x,
                            v.pos_y,
                            v.width,
                            v.height,
                            v.segment,
                            v.color_index,
                        ]
                        for k, v in map_data.obstacles.items()
                    ]
                    if map_data.obstacles
                    else []
                ),
                predefined_points=(
                    [[point.x0, point.y0] for point in cast("list[Any]", map_data.predefined_points)]
                    if map_data.predefined_points is not None
                    else None
                ),
                carpets=(
                    [
                        [
                            area.x0,
                            area.y0,
                            area.x1,
                            area.y1,
                            area.x2,
                            area.y2,
                            area.x3,
                            area.y3,
                            area.id,
                            area.ellipse,
                            area.carpet_cleaning,
                            area.carpet_settings,
                            area.carpet_type,
                        ]
                        for area in map_data.carpets
                    ]
                    if map_data.carpets is not None
                    else None
                ),
                ignored_carpets=(
                    [
                        [
                            area.x0,
                            area.y0,
                            area.x1,
                            area.y1,
                            area.x2,
                            area.y2,
                            area.x3,
                            area.y3,
                            area.id,
                        ]
                        for area in map_data.ignored_carpets
                    ]
                    if map_data.ignored_carpets is not None
                    else None
                ),
                detected_carpets=(
                    [
                        [
                            area.x0,
                            area.y0,
                            area.x1,
                            area.y1,
                            area.x2,
                            area.y2,
                            area.x3,
                            area.y3,
                            area.id,
                            area.ellipse,
                            area.carpet_cleaning,
                            area.carpet_settings,
                            area.carpet_type,
                            area.segments,
                            area.ignored_areas,
                            area.polygon,
                        ]
                        for area in map_data.detected_carpets
                    ]
                    if map_data.detected_carpets is not None
                    else None
                ),
                virtual_thresholds=(
                    [[wall.x0, wall.y0, wall.x1, wall.y1] for wall in map_data.virtual_thresholds]
                    if map_data.virtual_thresholds is not None
                    else None
                ),
                passable_thresholds=(
                    [[wall.x0, wall.y0, wall.x1, wall.y1] for wall in map_data.passable_thresholds]
                    if map_data.passable_thresholds is not None
                    else None
                ),
                impassable_thresholds=(
                    [[wall.x0, wall.y0, wall.x1, wall.y1] for wall in map_data.impassable_thresholds]
                    if map_data.impassable_thresholds is not None
                    else None
                ),
                ramps=(
                    [
                        [
                            area.x0,
                            area.y0,
                            area.x1,
                            area.y1,
                            area.x2,
                            area.y2,
                            area.x3,
                            area.y3,
                            area.angle,
                        ]
                        for area in map_data.ramps
                    ]
                    if map_data.ramps
                    else None
                ),
                low_lying_areas=(
                    [
                        [
                            area.x0,
                            area.y0,
                            area.x1,
                            area.y1,
                            area.x2,
                            area.y2,
                            area.x3,
                            area.y3,
                            area.id,
                            area.polygon,
                            area.type,
                            area.hidden,
                            area.ms,
                            area.area,
                        ]
                        for area in map_data.low_lying_areas
                    ]
                    if map_data.low_lying_areas is not None
                    else None
                ),
                furnitures=(
                    [
                        [
                            area.x0,
                            area.y0,
                            area.x1,
                            area.y1,
                            area.x2,
                            area.y2,
                            area.x3,
                            area.y3,
                            area.x,
                            area.y,
                            area.width,
                            area.height,
                            area.type.value,
                            area.size_type,
                            area.angle,
                            area.scale,
                        ]
                        for key, area in map_data.furnitures.items()
                    ]
                    if map_data.furnitures is not None
                    else None
                ),
                furniture_version=map_data.furniture_version,
                curtains=(
                    [[wall.x0, wall.y0, wall.x1, wall.y1] for wall in map_data.curtains]
                    if map_data.curtains is not None
                    else None
                ),
                resources=resources,
            )

        return json.dumps(
            map_data_json,
            default=lambda o: {key: value for key, value in o.__dict__.items() if value is not None},
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def render_obstacle_image(
        self,
        image_bytes: Any,
        obstacle: Obstacle,
        ai_image_crop: bool,
        render_box: bool = True,
        crop_image: bool = False,
    ) -> Any:
        if image_bytes:
            if (
                not obstacle
                or not (
                    obstacle.width and obstacle.height and obstacle.pos_x is not None and obstacle.pos_y is not None
                )
                or (not crop_image and not render_box)
            ):
                return image_bytes

            image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
            w = image.size[0]
            h = image.size[1]
            crop = (int((h * 105) / 100.0) - h) * 2
            x0_offset = 0
            x1_offset = 0
            if ai_image_crop:
                if crop_image:
                    image = image.crop((crop, 0, w - crop, h - int(crop / 2)))
                    w = image.size[0]
                    h = image.size[1]
                else:
                    x0_offset = crop
                    w = w - (crop * 2)
                    h = h - int(crop / 2)
            else:
                crop = int(round(crop * 0.55))
                if crop_image:
                    image = image.crop((crop, 0, w - crop, h))
                    w = image.size[0]
                    h = image.size[1]
                else:
                    x0_offset = crop
                    w = w - (crop * 2)

            if render_box:
                if self._obstacle_bottom_left_icon is None:
                    self._obstacle_bottom_left_icon = Image.open(
                        BytesIO(base64.b64decode(MAP_ROBOT_OBSTACLE_BOTTOM_LEFT_IMAGE))
                    ).convert("RGBA")
                    self._obstacle_top_left_icon = Image.open(
                        BytesIO(base64.b64decode(MAP_ROBOT_OBSTACLE_TOP_LEFT_IMAGE))
                    ).convert("RGBA")
                    self._obstacle_bottom_right_icon = Image.open(
                        BytesIO(base64.b64decode(MAP_ROBOT_OBSTACLE_BOTTOM_RIGHT_IMAGE))
                    ).convert("RGBA")
                    self._obstacle_top_right_icon = Image.open(
                        BytesIO(base64.b64decode(MAP_ROBOT_OBSTACLE_TOP_RIGHT_IMAGE))
                    ).convert("RGBA")

                icon_size = int(round(5 * h / 100.0))
                obstacle_bottom_left_icon = self._obstacle_bottom_left_icon.resize((icon_size, icon_size))
                obstacle_top_left_icon = self._obstacle_top_left_icon.resize((icon_size, icon_size))
                obstacle_bottom_right_icon = self._obstacle_bottom_right_icon.resize((icon_size, icon_size))
                obstacle_top_right_icon = self._obstacle_top_right_icon.resize((icon_size, icon_size))

                x = obstacle.pos_x - 4
                y = obstacle.pos_y - 4
                width = obstacle.width + 8
                height = obstacle.height + 8

                stroke = 3
                offset = 6
                x0 = ((x * w) / 100.0) - stroke + x0_offset
                y0 = ((y * h) / 100.0) - stroke
                x1 = (x0 + ((width * w) / 100.0)) + stroke + x1_offset
                y1 = (y0 + ((height * h) / 100.0)) + stroke

                if x0 <= 0:
                    new_x = int(w * 0.5 / 100.0)
                    x1 = x1 + new_x - x0
                    x0 = new_x
                if y0 <= 0:
                    new_y = int(h * 0.5 / 100.0)
                    y1 = y1 + new_y - y0
                    y0 = new_y

                if x1 >= w:
                    x1 = w - int(w * 0.5 / 100.0)
                if y1 >= h:
                    y1 = h - int(h * 0.5 / 100.0)

                new_layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
                draw = ImageDraw.Draw(new_layer, "RGBA")
                draw.polygon(
                    [
                        int(round(x0)),
                        int(round(y0)),
                        int(round(x0)),
                        int(round(y1)),
                        int(round(x1)),
                        int(round(y1)),
                        int(round(x1)),
                        int(round(y0)),
                    ],
                    (49, 85, 225, 30),
                    (49, 85, 225, 255),
                    width=stroke,
                )
                image = Image.alpha_composite(image, new_layer)

                new_layer = Image.new("RGBA", image.size, (255, 255, 255, 0))
                draw = ImageDraw.Draw(new_layer, "RGBA")
                new_layer.paste(
                    obstacle_top_left_icon,
                    (int(round(x0 + offset)), int(round(y0 + offset))),
                )
                new_layer.paste(
                    obstacle_bottom_left_icon,
                    (
                        int(round(x0 + offset)),
                        int(round(y1 - obstacle_bottom_left_icon.size[1] - offset)),
                    ),
                )
                new_layer.paste(
                    obstacle_bottom_right_icon,
                    (
                        int(round(x1 - obstacle_top_right_icon.size[0] - offset)),
                        int(round(y1 - obstacle_bottom_right_icon.size[1] - offset)),
                    ),
                )
                new_layer.paste(
                    obstacle_top_right_icon,
                    (
                        int(round(x1 - obstacle_top_right_icon.size[0] - offset)),
                        int(round(y0 + offset)),
                    ),
                )
                image = Image.alpha_composite(image, new_layer)

            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG")
            return buffer.getvalue()
        return None

    def _apply_floor_relief(self, pixels: np.ndarray, scale: int) -> np.ndarray:
        """Give the floor a subtle raised look against the transparent surround.

        Darkens a thin band along the inner edge of the floor silhouette (an
        inner shadow / bevel), so the rooms read as a slightly raised panel over
        the non-room zone instead of a flat cut-out. Stays entirely within the
        floor pixels — the outside remains fully transparent (contract 3.1), the
        image size, calibration and the separate segment_map are untouched.
        """
        try:
            alpha = pixels[..., 3]
            if not alpha.any():
                return pixels
            # Blur the floor silhouette: inside stays ~1.0, it falls off only
            # within ``radius`` of the boundary, which is exactly the edge band.
            radius = max(2.0, float(scale) * 2.0)
            silhouette = Image.fromarray(((alpha > 0).astype(np.uint8) * 255), "L")
            blurred = np.asarray(silhouette.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32) / 255.0
            silhouette.close()
            # 1.0 in the interior, down to ~0.55 right at the edge.
            factor = 0.55 + 0.45 * blurred
            floor = alpha > 0
            rgb = pixels[..., :3].astype(np.float32)
            rgb[floor] *= factor[floor][:, None]
            pixels[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
            return pixels
        except Exception as ex:  # pragma: no cover - defensive, never break the raster path
            _LOGGER.debug("Floor relief skipped: %s", ex)
            return pixels

    def _smooth_upscale(self, pixels: np.ndarray, scale: int) -> np.ndarray:
        """Upscale the base raster with anti-aliasing instead of nearest-neighbour.

        The default ``np.repeat`` upscale turns every grid cell into a hard
        ``scale x scale`` block, so diagonal room and wall boundaries come out
        visibly stair-stepped ("cheap" looking). When the ``vector_rooms`` option
        is enabled we instead resample the base-resolution colour grid with a
        bicubic filter, which smooths those diagonals into clean edges while
        keeping flat interiors flat. Robot, path, icons and text are drawn later
        at full resolution, so only the floor/room/wall layer is softened.
        """
        try:
            height, width = pixels.shape[0], pixels.shape[1]
            base = Image.fromarray(pixels)
            smoothed = base.resize((width * scale, height * scale), Image.Resampling.BICUBIC)
            base.close()
            # np.array (not asarray) so the result is a writable, contiguous copy:
            # render_floor_material / render_carpets mutate this array in place.
            result = np.array(smoothed, dtype=np.uint8)
            smoothed.close()
            return result
        except Exception as ex:  # pragma: no cover - defensive, never break the raster path
            _LOGGER.debug("Smooth upscale skipped, falling back to nearest: %s", ex)
            return pixels.repeat(scale, axis=0).repeat(scale, axis=1)

    def render_map(
        self,
        map_data: MapData,
        robot_status: int = 0,
        station_status: int = 0,
        info_text: bool = False,
    ) -> bytes:
        if (
            map_data is None
            or map_data.dimensions is None
            or map_data.empty_map
            or (map_data.dimensions.width * map_data.dimensions.height) < 2
        ):
            return self.default_map_image

        self._warm_up_icons()
        self.render_complete = False
        image = self._image

        if map_data.saved_map:
            robot_status = 0
            station_status = 0
        try:
            if self._cache:
                if (
                    self._map_data is None
                    or self._map_data.dimensions != map_data.dimensions
                    or self._map_data.map_id != map_data.map_id
                    or self._map_data.saved_map_status != map_data.saved_map_status
                ):
                    self._map_data = None

                # Désactiver le cache pendant le washing pour permettre l'animation
                # Vérifier tous les cas de washing (normal et hot) avant et après transformation
                # Si >= 10 c'est hot washing, sinon normal
                # Après ligne 8396: station_status -= 10 si >= 10
                # Après ligne 8411: elif station_status < 4 = washing (2, 3 après transform, ou 12, 13 avant)
                original_station = station_status
                is_washing = False
                if original_station >= 10:
                    # Hot washing: 12 ou 13 deviennent 2 ou 3 après -10
                    test_status = original_station - 10
                    is_washing = 1 < test_status < 4
                else:
                    # Normal washing: 2 ou 3 directement
                    is_washing = 1 < original_station < 4

                if (
                    self._map_data
                    and self._map_data == map_data
                    and self._robot_status == robot_status
                    and self._station_status == station_status
                    and self._map_data.segments == map_data.segments
                    and self._map_data.frame_id == map_data.frame_id
                    and self._image
                    and not is_washing  # Ne pas utiliser le cache pendant le washing
                ):
                    self.render_complete = True
                    return cast(bytes, self._to_buffer(self._image))

            scale = (
                2
                if self._low_resolution
                else (
                    4
                    if (map_data.saved_map_status == 2 or map_data.restored_map)
                    and not map_data.recovery_map
                    and not map_data.history_map
                    else 2
                    if (map_data.wifi_map or map_data.history_map) and self._cache
                    else 3
                )
            )
            object_scale = 2

            render_material = False
            render_carpet = bool(
                (not map_data.saved_map or map_data.history_map or map_data.recovery_map) and self.config.carpet
            )
            if (map_data.saved_map_status == 2 or map_data.saved_map) and not map_data.wifi_map:
                render_material = bool(self.config.material and map_data.floor_material)
                render_carpet = render_carpet and bool(
                    map_data.carpets or map_data.detected_carpets or map_data.ignored_carpets or map_data.carpet_pixels
                )

            if scale == 3 and (render_material or render_carpet):
                scale = 2 if info_text else 4

            # Apply the render-resolution multiplier only after the base scale
            # (and its material/carpet bump) is fully resolved. Skip it in
            # low-resolution mode, for the info_text renders (downscaled to a
            # fixed width anyway) and the secondary wifi/history maps. Calibration
            # derives from ``dimensions.scale`` below, so it re-coheres with the
            # multiplied resolution automatically (contract §3.2).
            if (
                self._render_scale > 1
                and not self._low_resolution
                and not info_text
                and not ((map_data.wifi_map or map_data.history_map) and self._cache)
            ):
                scale = scale * self._render_scale

            if not map_data.saved_map:
                if (
                    self._map_data is None
                    or self._map_data.segments != map_data.segments
                    or self._map_data.dimensions != map_data.dimensions
                    or self._map_data.saved_map_id != map_data.saved_map_id
                ):
                    map_data.dimensions.bounds = DreameVacuumMapRenderer._calculate_bounds(
                        map_data.dimensions, map_data.segments
                    )

                    if (
                        self._map_data
                        and self._map_data.dimensions
                        and (
                            self._map_data.dimensions.bounds != map_data.dimensions.bounds
                            or self._map_data.saved_map_id != map_data.saved_map_id
                        )
                    ):
                        self._map_data = None
                else:
                    map_data.dimensions.bounds = self._map_data.dimensions.bounds

            if (
                not self._cache
                or self._map_data is None
                or self._map_data.active_areas != map_data.active_areas
                or self._map_data.no_mopping_areas != map_data.no_mopping_areas
                or self._map_data.no_go_areas != map_data.no_go_areas
                or self._map_data.virtual_walls != map_data.virtual_walls
                or self._map_data.virtual_thresholds != map_data.virtual_thresholds
                or self._map_data.passable_thresholds != map_data.passable_thresholds
                or self._map_data.impassable_thresholds != map_data.impassable_thresholds
                or self._map_data.ramps != map_data.ramps
                or self._map_data.carpets != map_data.carpets
                or self._map_data.curtains != map_data.curtains
                or self._map_data.segments != map_data.segments
                or self._map_data.dimensions != map_data.dimensions
                or self._map_data.restored_map != map_data.restored_map
            ):
                map_data.dimensions.padding = DreameVacuumMapRenderer._calculate_padding(
                    map_data.dimensions,
                    map_data.active_areas if self.config.active_area else None,
                    map_data.no_mopping_areas if self.config.no_mop else None,
                    map_data.no_go_areas if self.config.no_go else None,
                    map_data.virtual_walls if self.config.virtual_wall else None,
                    map_data.virtual_thresholds if self.config.pathway else None,
                    map_data.passable_thresholds if self.config.pathway else None,
                    map_data.impassable_thresholds if self.config.pathway else None,
                    map_data.ramps if self.config.ramp else None,
                    map_data.furnitures if self.config.furniture else None,
                    map_data.furniture_version,
                    map_data.curtains if self.config.curtain else None,
                    map_data.segments,
                    [14, 14, 14, 14],
                    120,
                    80,
                    scale,
                    self.icon_set,
                )

                if (
                    self._cache
                    and self._map_data
                    and self._map_data.dimensions
                    and self._map_data.dimensions.padding != map_data.dimensions.padding
                ):
                    self._map_data = None
            else:
                map_data.dimensions.padding = self._map_data.dimensions.padding

            map_data.dimensions.scale = scale
            segment_mask: Any = None

            if not self._low_memory and self.config.path and map_data.path and self._robot_type != RobotType.VSLAM:
                if not self._cache or self._map_data is None or self._map_data.path != map_data.path:
                    self._has_mask = False
                    for path in map_data.path:
                        if path.path_type == PathType.SWEEP_AND_MOP or path.path_type == PathType.MOP:
                            self._has_mask = True
                            break
            else:
                self._has_mask = False

            cached_layers = self._layers if self._cache else {}
            if self._cache and not self._has_mask and cached_layers.get(MapRendererLayer.PATH_MASK):
                self._del_layer(cached_layers, MapRendererLayer.PATH_MASK)

            if (
                self._cache
                and self._map_data
                and self._map_data.dimensions
                and self._map_data.dimensions.scale != scale
            ):
                self._map_data = None

            if not self._cache or (self._map_data is None or self._map_data.rotation != map_data.rotation):
                self._robot_sleeping_icon = None
                self._obstacle_background = None
                self._obstacle_hidden_background = None
                self._cruise_path_point_background = None
                self._cruise_point_background = None
                self._furniture_background = None

                if self._map_data is None:
                    self._robot_charging_icon = None
                    self._robot_cleaning_icon = None
                    self._robot_warning_icon = None
                    self._robot_washing_icon = None
                    self._robot_hot_washing_icon = None
                    self._robot_drying_icon = None
                    self._robot_hot_drying_icon = None
                    self._robot_emptying_icon = None
                    self._robot_cleaning_direction_icon = None

            bg_color = (
                ((0, 0, 0, 255) if self.color_scheme.dark or self.color_scheme.invert else (255, 255, 255, 255))
                if info_text
                else ((0, 0, 0, 0) if map_data.wifi_map else self.color_scheme.outside)
            )

            if (
                not self._cache
                or self._map_data is None
                or not cached_layers.get(MapRendererLayer.IMAGE)
                or self._map_data.active_segments != map_data.active_segments
                or self._map_data.active_areas != map_data.active_areas
                or self._map_data.segments != map_data.segments
                or self._map_data.data != map_data.data
                or (self._has_mask and not cached_layers.get(MapRendererLayer.PATH_MASK))
                or (render_material and self._map_data.floor_material != map_data.floor_material)
                or (
                    render_carpet
                    and (
                        self._map_data.carpets != map_data.carpets
                        or self._map_data.ignored_carpets != map_data.ignored_carpets
                        or self._map_data.detected_carpets != map_data.detected_carpets
                        or self._map_data.carpet_pixels != map_data.carpet_pixels
                    )
                )
            ):
                area_colors = {}
                # as implemented on the app
                if map_data.cleaning_map:
                    area_colors[MapPixelType.OUTSIDE.value] = bg_color
                    area_colors[MapPixelType.WALL.value] = self.color_scheme.wall
                    if map_data.second_cleaning:
                        area_colors[MapPixelType.DIRTY_AREA.value] = self.color_scheme.second_clean_area
                        area_colors[MapPixelType.CLEAN_AREA.value] = self.color_scheme.cleaned_area
                    else:
                        area_colors[MapPixelType.DIRTY_AREA.value] = self.color_scheme.dirty_area
                        area_colors[MapPixelType.CLEAN_AREA.value] = self.color_scheme.clean_area
                    area_colors[MapPixelType.NEW_SEGMENT.value] = self.color_scheme.passive_segment
                elif map_data.wifi_map:
                    area_colors[MapPixelType.OUTSIDE.value] = bg_color
                    area_colors[MapPixelType.WIFI_EXCELLENT.value] = (
                        129,
                        168,
                        245,
                        255,
                    )
                    area_colors[MapPixelType.WIFI_HIGH.value] = (161, 189, 242, 255)
                    area_colors[MapPixelType.WIFI_LOW.value] = (205, 218, 239, 255)
                    area_colors[MapPixelType.WIFI_POOR.value] = (217, 226, 239, 255)
                    area_colors[MapPixelType.WIFI_UNREACHED.value] = (
                        229,
                        234,
                        238,
                        255,
                    )
                    area_colors[MapPixelType.WIFI_WALL.value] = (160, 160, 160, 255)
                    area_colors[MapPixelType.NEW_SEGMENT.value] = area_colors[MapPixelType.OUTSIDE.value]
                else:
                    area_colors[MapPixelType.OUTSIDE.value] = bg_color
                    area_colors[MapPixelType.WALL.value] = self.color_scheme.wall
                    area_colors[MapPixelType.HIDDEN_WALL.value] = self.color_scheme.hidden_segment
                    area_colors[MapPixelType.FLOOR.value] = self.color_scheme.floor
                    area_colors[MapPixelType.NEW_SEGMENT.value] = self.color_scheme.new_segment
                    area_colors[MapPixelType.UNKNOWN.value] = self.color_scheme.floor
                    area_colors[MapPixelType.OBSTACLE_WALL.value] = self.color_scheme.wall

                if map_data.cleaning_map:
                    if map_data.neglected_segments:
                        for k in map_data.neglected_segments:
                            area_colors[k] = (255, 255, 255, 255)
                elif map_data.segments is not None and not map_data.cleaning_map:
                    for k, v in map_data.segments.items():
                        if self.config.color:
                            if map_data.hidden_segments and k in map_data.hidden_segments:
                                area_colors[k] = self.color_scheme.hidden_segment
                            elif map_data.active_segments and k not in map_data.active_segments:
                                area_colors[k] = self.color_scheme.passive_segment
                            elif v.color_index is not None:
                                area_colors[k] = self.color_scheme.segment[v.color_index][0]
                        else:
                            area_colors[k] = area_colors[MapPixelType.FLOOR.value]

                pixels = np.full(
                    (
                        map_data.dimensions.height,
                        map_data.dimensions.width,
                        4,
                    ),
                    area_colors[MapPixelType.OUTSIDE.value],
                    dtype=np.uint8,
                )

                if self._has_mask:
                    mask_color = (255, 255, 255, 255)
                    mask = np.full(
                        (
                            map_data.dimensions.height,
                            map_data.dimensions.width,
                            4,
                        ),
                        (255, 255, 255, 0),
                        dtype=np.uint8,
                    )

                if map_data.history_map and map_data.neglected_segments:
                    segment_mask = np.full(
                        (
                            map_data.dimensions.height,
                            map_data.dimensions.width,
                            4,
                        ),
                        (255, 255, 255, 0),
                        dtype=np.uint8,
                    )

                min_x = map_data.dimensions.width - 1
                min_y = map_data.dimensions.height - 1
                max_x = 0
                max_y = 0

                for y in range(map_data.dimensions.height):
                    for x in range(map_data.dimensions.width):
                        px_type = int(map_data.pixel_type[x, map_data.dimensions.height - y - 1])

                        if px_type != 0:
                            pixels[y, x] = area_colors.get(px_type, area_colors[253])

                            max_x = max(x, max_x)
                            min_x = min(x, min_x)
                            max_y = max(y, max_y)
                            min_y = min(y, min_y)

                            if self._has_mask and px_type != 255:
                                mask[y, x] = mask_color

                            if segment_mask is not None:
                                if px_type in map_data.neglected_segments:
                                    segment_mask[y, x] = self.color_scheme.neglected_segment

                if render_material or render_carpet:
                    floor_scale = 2
                    if self._vector_rooms:
                        pixels = self._smooth_upscale(pixels, floor_scale)
                    else:
                        pixels = pixels.repeat(floor_scale, axis=0).repeat(floor_scale, axis=1)
                    if render_material:
                        floor_material = self.render_floor_material(
                            pixels,
                            map_data.floor_material,
                            map_data.pixel_type,
                            self.color_scheme.material_color,
                            map_data.dimensions,
                            floor_scale,
                        )
                        if floor_material is not None:
                            pixels = floor_material
                            _LOGGER.debug("Render MATERIAL")

                    carpet = None
                    if render_carpet:
                        carpet = self.render_carpets(
                            pixels,
                            map_data.pixel_type,
                            map_data.carpets,
                            map_data.ignored_carpets,
                            map_data.detected_carpets,
                            map_data.carpet_pixels,
                            map_data.segments,
                            self.color_scheme.carpet_color,
                            self.color_scheme.carpet_color_detected,
                            map_data.dimensions,
                            floor_scale,
                        )

                        if carpet is not None:
                            _LOGGER.debug("Render CARPET")
                            pixels = carpet

                    if scale != floor_scale:
                        repeat_factor = int(scale / floor_scale)
                        if self._vector_rooms:
                            pixels = self._smooth_upscale(pixels, repeat_factor)
                        else:
                            pixels = pixels.repeat(repeat_factor, axis=0).repeat(repeat_factor, axis=1)
                elif self._vector_rooms:
                    pixels = self._smooth_upscale(pixels, scale)
                else:
                    pixels = pixels.repeat(scale, axis=0).repeat(scale, axis=1)

                if self._has_mask:
                    mask = mask.repeat(scale, axis=0).repeat(scale, axis=1)

                if segment_mask is not None:
                    segment_mask = segment_mask.repeat(scale, axis=0).repeat(scale, axis=1)

                if map_data.dimensions.bounds:
                    # min_x = max(0, min(map_data.dimensions.bounds[0], min_x))
                    # max_x = min((map_data.dimensions.width - 1), max(map_data.dimensions.bounds[2], max_x))
                    # min_y = max(0, min(map_data.dimensions.bounds[1], min_y))
                    # max_y = min((map_data.dimensions.height - 1), max(map_data.dimensions.bounds[3], max_y))
                    min_x = max(min(map_data.dimensions.bounds[0], min_x), min_x)
                    max_x = min(max(map_data.dimensions.bounds[2], max_x), max_x)
                    min_y = max(min(map_data.dimensions.bounds[1], min_y), min_y)
                    max_y = min(max(map_data.dimensions.bounds[3], max_y), max_y)

                if (
                    min_x != (map_data.dimensions.width - 1)
                    and min_y != (map_data.dimensions.height - 1)
                    and max_x != 0
                    and max_y != 0
                ) and (
                    min_x != 0
                    or min_y != 0
                    or max_x != (map_data.dimensions.width - 1)
                    or max_y != (map_data.dimensions.height - 1)
                ):
                    from_y = min_y * scale
                    to_y = (max_y + 1) * scale
                    from_x = min_x * scale
                    to_x = (max_x + 1) * scale
                    pixels = pixels[from_y:to_y, from_x:to_x]
                    if self._has_mask:
                        mask = mask[from_y:to_y, from_x:to_x]
                    if segment_mask is not None:
                        segment_mask = segment_mask[from_y:to_y, from_x:to_x]
                    map_data.dimensions.crop = [
                        from_x,
                        from_y,
                        (map_data.dimensions.width - (max_x + 1)) * scale,
                        (map_data.dimensions.height - (max_y + 1)) * scale,
                    ]

                if (
                    self._map_data
                    and self._map_data.dimensions
                    and self._map_data.dimensions.crop != map_data.dimensions.crop
                ):
                    self._map_data = None

                if self._map_relief and not map_data.wifi_map:
                    pixels = self._apply_floor_relief(pixels, scale)

                image = Image.fromarray(pixels)
                if self._square and not map_data.wifi_map:  # and not map_data.saved_map:
                    height = image.size[0] + map_data.dimensions.padding[0] + map_data.dimensions.padding[2]
                    width = image.size[1] + map_data.dimensions.padding[1] + map_data.dimensions.padding[3]
                    if height != width:
                        dif = int(abs(height - width) / 2)
                        if height < width:
                            map_data.dimensions.padding[0] = map_data.dimensions.padding[0] + dif
                            map_data.dimensions.padding[2] = map_data.dimensions.padding[2] + dif
                        else:
                            map_data.dimensions.padding[1] = map_data.dimensions.padding[1] + dif
                            map_data.dimensions.padding[3] = map_data.dimensions.padding[3] + dif

                cached_layers[MapRendererLayer.IMAGE] = ImageOps.expand(
                    Image.fromarray(pixels),
                    border=tuple(map_data.dimensions.padding),
                    fill=bg_color,
                )

                if self._has_mask:
                    if self._cache and self._map_data:
                        self._map_data.path = None

                    cached_layers[MapRendererLayer.PATH_MASK] = ImageOps.expand(
                        Image.fromarray(mask.repeat(object_scale, axis=0).repeat(object_scale, axis=1)),
                        border=(
                            map_data.dimensions.padding[0] * object_scale,
                            map_data.dimensions.padding[1] * object_scale,
                            map_data.dimensions.padding[2] * object_scale,
                            map_data.dimensions.padding[3] * object_scale,
                        ),
                        fill=(255, 255, 255, 0),
                    )

                if segment_mask is not None:
                    segment_mask = ImageOps.expand(
                        Image.fromarray(segment_mask),
                        border=(
                            map_data.dimensions.padding[0],
                            map_data.dimensions.padding[1],
                            map_data.dimensions.padding[2],
                            map_data.dimensions.padding[3],
                        ),
                        fill=(255, 255, 255, 0),
                    )
            else:
                if self._map_data.dimensions:
                    map_data.dimensions.crop = self._map_data.dimensions.crop

            self._calibration_points = self._calculate_calibration_points(map_data)

            image = cached_layers[MapRendererLayer.IMAGE]

            # Track the base cached image so we know not to close it
            base_image = cached_layers[MapRendererLayer.IMAGE]

            if not map_data.saved_map and map_data.path and self.config.path:
                if (
                    not self._cache
                    or self._map_data is None
                    or self._map_data.path != map_data.path
                    or not cached_layers.get(MapRendererLayer.PATH)
                ):
                    self._replace_layer(
                        cached_layers,
                        MapRendererLayer.PATH,
                        self.render_path(
                            map_data.path,
                            self.color_scheme.path,
                            self.color_scheme.mop_path,
                            (
                                int(image.size[0] * object_scale),
                                int(image.size[1] * object_scale),
                            ),
                            cached_layers.get(MapRendererLayer.PATH_MASK),
                            map_data.dimensions,
                            0.375 * scale * object_scale,
                            object_scale,
                        ),
                    )
                    cached_layers[MapRendererLayer.PATH].thumbnail(image.size, Image.Resampling.BOX, reducing_gap=1.5)
                    _LOGGER.debug("Render PATH")
                image = Image.alpha_composite(image, cached_layers[MapRendererLayer.PATH])
            elif self._cache and cached_layers.get(MapRendererLayer.PATH):
                self._close_image(cached_layers.pop(MapRendererLayer.PATH))

            old_image = image
            image = self.render_objects(cached_layers, map_data, robot_status, station_status, image, object_scale)
            if old_image is not image and old_image is not base_image:
                self._close_image(old_image)

            if segment_mask is not None:
                old_image = image
                neglected_layer = self.render_neglected_segments(
                    map_data.neglected_segments,
                    map_data.segments,
                    image.size,
                    segment_mask,
                    map_data.dimensions,
                    map_data.rotation,
                    map_data.cleaning_map,
                )
                image = Image.alpha_composite(image, neglected_layer)
                self._close_image(neglected_layer)
                if old_image is not base_image:
                    self._close_image(old_image)

            if map_data.rotation == 90:
                old_image = image
                image = image.transpose(Image.Transpose.ROTATE_90)
                if old_image is not base_image:
                    self._close_image(old_image)
            elif map_data.rotation == 180:
                old_image = image
                image = image.transpose(Image.Transpose.ROTATE_180)
                if old_image is not base_image:
                    self._close_image(old_image)
            elif map_data.rotation == 270:
                old_image = image
                image = image.transpose(Image.Transpose.ROTATE_270)
                if old_image is not base_image:
                    self._close_image(old_image)

            if info_text:
                base_width = 490  # int(round(image.size[0] / 4 * 3))
                if image.size[0] > base_width:
                    old_image = image
                    image = image.resize(
                        (
                            base_width,
                            int(float(image.size[1]) * float(base_width / float(image.size[0]))),
                        ),
                        Image.Resampling.LANCZOS,
                    )
                    if old_image is not base_image:
                        self._close_image(old_image)

                header_text = f"{time.strftime(('%Y.%m.%d %H:%M:%S' if bool(map_data.saved_map or map_data.recovery_map or map_data.wifi_map) else '%m/%d %H:%M'), time.localtime(map_data.last_updated))}"
                if map_data.history_map:
                    if map_data.task_cruise_points is None:
                        if map_data.startup_method is not None:
                            header_text = f"{header_text} | {map_data.startup_method.name.replace('_', ' ').title().replace('App', 'APP')}"

                        if map_data.second_cleaning:
                            header_text = f"{header_text} | Second Cleaning"
                        elif map_data.cleanup_method is not None:
                            header_text = f"{header_text} | {map_data.cleanup_method.name.replace('_', ' ').title()}"
                elif (
                    map_data.recovery_map
                    and map_data.recovery_map_type
                    and map_data.recovery_map_type is not RecoveryMapType.UNKNOWN
                ):
                    header_text = f"{header_text} | {map_data.recovery_map_type.name.replace('_', ' ').title()}"

                image_width = image.size[0]
                min_width = base_width  # int(160 * scale)
                if image_width < min_width:
                    image_width = min_width

                text_draw = ImageDraw.Draw(image, "RGBA")
                text_size = int(image_width * 0.035)
                if self._light_font_file is None:
                    self._light_font_file = zlib.decompress(base64.b64decode(MAP_FONT_LIGHT), zlib.MAX_WBITS | 32)

                text_font = ImageFont.truetype(BytesIO(self._light_font_file), text_size)
                if map_data.history_map:
                    value_font = ImageFont.truetype(BytesIO(self._light_font_file), int(text_size * 1.8))
                    name_font = ImageFont.truetype(BytesIO(self._light_font_file), int(text_size * 0.8))
                left, top, width, height = text_draw.textbbox((0, 0), header_text, font=text_font)
                max_width = image_width * 0.9
                if width > max_width:
                    lines = textwrap.wrap(header_text, width=int(max_width / (text_size / 2)))
                else:
                    lines = [header_text]

                if map_data.history_map and not map_data.task_cruise_points:
                    header_text = ""
                    if map_data.mop_wash_count:
                        header_text = "Self-Cleaned"
                        if map_data.mop_wash_count > 1:
                            header_text = f"{header_text} {map_data.mop_wash_count}x"

                    if map_data.dust_collection_count:
                        if len(header_text):
                            header_text = f"{header_text} | "
                        header_text = f"{header_text}Auto-Emptied"
                        if map_data.dust_collection_count > 1:
                            header_text = f"{header_text} {map_data.dust_collection_count}x"

                    if len(header_text):
                        lines.append(header_text)

                max_width = 0.0
                header_height = int(text_size * 5) if map_data.history_map else text_size
                total_height: float = header_height

                line_sizes = []
                for line in lines:
                    left, top, width, height = text_draw.textbbox((0, 0), line, font=text_font)
                    line_sizes.append((width, height))
                    max_width = max(max_width, width)
                    total_height = total_height + height

                padding = int((min_width - image.size[0]) / 2)
                if padding < 0:
                    padding = 0
                old_image = image
                image = ImageOps.expand(
                    image,
                    border=(
                        padding,
                        int(total_height) + int(padding / 2),
                        padding,
                        int(padding / 2),
                    ),
                    fill=bg_color,
                )
                if old_image is not base_image:
                    self._close_image(old_image)
                image_width = image.size[0]
                text_draw = ImageDraw.Draw(image, "RGBA")

                text_color = (120, 120, 120, 255)
                value_color = (0, 0, 0, 255)
                if self.color_scheme.dark or self.color_scheme.invert:
                    text_color = (135, 135, 135, 255)
                    value_color = (255, 255, 255, 255)

                if map_data.history_map:
                    cruising_map = bool(map_data.task_cruise_points is not None)
                    map_type = "Cruising" if cruising_map else "Cleaning"
                    header_lines = [
                        (str(map_data.cleaning_time), f"{map_type} Time", "min"),
                        (
                            "Interrupted" if not map_data.completed else "Completed",
                            f"{map_type} Status",
                            "",
                        ),
                    ]

                    if not cruising_map:
                        header_lines.append((str(map_data.cleaned_area), f"{map_type} Area", "m²"))

                    for i in range(len(header_lines)):
                        value = header_lines[i][0]
                        name = header_lines[i][1]
                        unit = header_lines[i][2]
                        left, top, value_width, value_height = text_draw.textbbox((0, 0), value, font=value_font)
                        left, top, unit_width, unit_height = text_draw.textbbox((0, 0), unit, font=name_font)
                        left, top, name_width, name_height = text_draw.textbbox((0, 0), name, font=name_font)
                        y = text_size
                        x = int(image_width * 0.06)
                        pos = []
                        if len(header_lines) == 3:
                            if i == 0:
                                value_x = x + name_width / 2
                                t1 = value_width / 2
                                t2 = unit_width / 2
                                t3 = text_size / 4
                                pos.extend(
                                    [
                                        (value_x - t1 - t2 - t3, y),
                                        (x, y + (text_size * 2)),
                                        (
                                            value_x - t2 + t1 + t3,
                                            y + value_height - unit_height,
                                        ),
                                    ]
                                )
                            elif i == 1:
                                pos.extend(
                                    [
                                        (image_width - x - value_width, text_size),
                                        (
                                            image_width - x - name_width - ((value_width - name_width) / 2),
                                            y + (text_size * 2),
                                        ),
                                    ]
                                )
                            elif i == 2:
                                t1 = text_size / 2
                                pos.extend(
                                    [
                                        (
                                            ((image_width - value_width - unit_width - t1) / 2),
                                            y,
                                        ),
                                        (
                                            (image_width - name_width) / 2,
                                            y + (text_size * 2),
                                        ),
                                        (
                                            ((image_width - unit_width + value_width + t1) / 2),
                                            y + value_height - unit_height,
                                        ),
                                    ]
                                )
                        elif len(header_lines) == 2:
                            if i == 0:
                                t1 = text_size / 2
                                pos.extend(
                                    [
                                        (
                                            ((image_width - value_width - unit_width - t1) / 2) - (image_width / 4),
                                            y,
                                        ),
                                        (
                                            ((image_width - name_width) / 2) - (image_width / 4),
                                            y + (text_size * 2),
                                        ),
                                        (
                                            ((image_width - unit_width + value_width + t1) / 2) - (image_width / 4),
                                            y + value_height - unit_height,
                                        ),
                                    ]
                                )
                            elif i == 1:
                                pos.extend(
                                    [
                                        (
                                            ((image_width - value_width) / 2) + (image_width / 4),
                                            y,
                                        ),
                                        (
                                            ((image_width - name_width) / 2) + (image_width / 4),
                                            y + (text_size * 2),
                                        ),
                                    ]
                                )

                        for k in range(len(pos)):
                            style = (value_color, value_font) if k == 0 else (text_color, name_font)
                            text_draw.text(pos[k], header_lines[i][k], fill=style[0], font=style[1])

                header_x = (image_width - max_width) / 2
                line_y: float = header_height
                for i in range(len(lines)):
                    line_x = header_x + (max_width - line_sizes[i][0]) / 2
                    text_draw.text((line_x, line_y), lines[i], fill=text_color, font=text_font)
                    line_y = line_y + line_sizes[i][1]

            if self._cache:
                self._map_data = map_data
                self._robot_status = robot_status
                self._station_status = station_status
                old_cached_image = self._image
                self._image = image
                if old_cached_image is not None and old_cached_image is not image:
                    self._close_image(old_cached_image)
        except Exception:
            _LOGGER.error("Map render Failed: %s", traceback.format_exc())

        self.render_complete = True
        result = self._image if self._cache else image
        if result is None:
            # A failure during the very first render leaves no image at all;
            # fall back to the placeholder like empty maps do instead of
            # returning None from a bytes-typed API.
            return self.default_map_image
        return cast(bytes, self._to_buffer(result))

    def _calculate_render_sizes(self, map_data: Any, map_image: Any, scale: Any) -> Any:
        """Calculate icon sizes for rendering based on map dimensions."""
        layer_size = (int(map_image.size[0] * scale), int(map_image.size[1] * scale))
        line_width = 3 if map_data.dimensions.scale > 2 else 1
        border_width = 2 if map_data.dimensions.scale > 2 else 1

        if map_data.rotation == 0 or map_data.rotation == 180 or self._square:
            width = (map_data.dimensions.width) + (
                (
                    map_data.dimensions.padding[0]
                    + map_data.dimensions.padding[2]
                    - map_data.dimensions.crop[0]
                    - map_data.dimensions.crop[2]
                )
                / map_data.dimensions.scale
            )
            robot_icon_size = width * 0.037
            icon_size = width * (0.022 if self._square else 0.027)
        else:
            height = (map_data.dimensions.height) + (
                (
                    map_data.dimensions.padding[1]
                    + map_data.dimensions.padding[3]
                    - map_data.dimensions.crop[1]
                    - map_data.dimensions.crop[3]
                )
                / map_data.dimensions.scale
            )
            robot_icon_size = height * 0.037
            icon_size = height * 0.027

        robot_icon_size = max(7, min(14, robot_icon_size))
        icon_size = max(3, min(12, icon_size))
        segment_icon_size = icon_size

        if map_data.dimensions.scale <= 2:
            robot_icon_size = robot_icon_size * 0.7
            icon_size = icon_size * 1.3

        return layer_size, line_width, border_width, robot_icon_size, icon_size, segment_icon_size
