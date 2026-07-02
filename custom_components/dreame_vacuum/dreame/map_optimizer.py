from __future__ import annotations

"""Map optimizer module for Dreame vacuum integration.

Contains DreameVacuumMapOptimizer for post-processing map data
including flood fill, denoising and path optimization.
"""

import base64
import logging
import traceback
from typing import Any

import numpy as np
from py_mini_racer import MiniRacer

from .resources import MAP_OPTIMIZER_JS
from .vacuum_types import (
    MapImageDimensions,
    MapPixelType,
)

_LOGGER = logging.getLogger(__name__)


class DreameVacuumMapOptimizer:
    """Post-processes decoded map grids before rendering (V8 port of the app algorithm)."""

    def __init__(self) -> None:
        self._js_optimizer: MiniRacer | None = None

    def close(self) -> None:
        """Drop the embedded V8 context so it can be reclaimed on unload."""
        self._js_optimizer = None


    def _merge_saved_map_data(self, map_data: Any, saved_map_data: Any, original_data: Any = None) -> Any:
        if saved_map_data:
            maxX = map_data.dimensions.left + (map_data.dimensions.width * map_data.dimensions.grid_size)
            maxY = map_data.dimensions.top + (map_data.dimensions.height * map_data.dimensions.grid_size)

            if maxX < saved_map_data.dimensions.left + (
                saved_map_data.dimensions.width * saved_map_data.dimensions.grid_size
            ):
                maxX = saved_map_data.dimensions.left + (
                    saved_map_data.dimensions.width * saved_map_data.dimensions.grid_size
                )

            if maxY < saved_map_data.dimensions.top + (
                saved_map_data.dimensions.height * saved_map_data.dimensions.grid_size
            ):
                maxY = saved_map_data.dimensions.top + (
                    saved_map_data.dimensions.height * saved_map_data.dimensions.grid_size
                )

            left = map_data.dimensions.left
            top = map_data.dimensions.top

            if saved_map_data.dimensions.left < left:
                left = saved_map_data.dimensions.left

            if saved_map_data.dimensions.top < top:
                top = saved_map_data.dimensions.top

            width = int((maxX - left) / saved_map_data.dimensions.grid_size)
            height = int((maxY - top) / saved_map_data.dimensions.grid_size)

            si = int((saved_map_data.dimensions.left - left) / saved_map_data.dimensions.grid_size)
            sj = int((saved_map_data.dimensions.top - top) / saved_map_data.dimensions.grid_size)

            sim = si + saved_map_data.dimensions.width
            sjm = sj + saved_map_data.dimensions.height

            ni = int((map_data.dimensions.left - left) / map_data.dimensions.grid_size)
            nj = int((map_data.dimensions.top - top) / map_data.dimensions.grid_size)

            nim = ni + map_data.dimensions.width
            njm = nj + map_data.dimensions.height

            pixel_type = np.zeros((width, height), np.uint8)
            data = map_data.optimized_pixel_type if map_data.optimized_pixel_type is not None else map_data.pixel_type

            for j in range(height):
                for i in range(width):
                    if j >= sj and i >= si and j < sjm and i < sim:
                        saved_value = int(saved_map_data.pixel_type[(i - si), (j - sj)])
                    else:
                        saved_value = 0

                    if j >= nj and i >= ni and j < njm and i < nim:
                        clean_value = int(data[(i - ni), (j - nj)])
                    else:
                        clean_value = 0

                    if saved_value != 0:
                        if saved_value != 255:
                            pixel_type[i, j] = saved_value
                        else:
                            if clean_value != 0 and clean_value != 255:
                                pixel_type[i, j] = 254
                            else:
                                pixel_type[i, j] = 255
                    elif clean_value != 0:
                        if clean_value == 255:
                            pixel_type[i, j] = 255
                        else:
                            pixel_type[i, j] = 254

            if original_data is not None:
                for j in range(height):
                    for i in range(width):
                        if j >= nj and i >= ni and j < njm and i < nim:
                            if (
                                original_data[(j - nj) * map_data.dimensions.width + (i - ni)] == 2
                                and pixel_type[i, j] != 0
                            ):
                                dis = 3
                                hasBorder = False
                                for _j in range(j - dis, j + dis + 1):
                                    for _i in range(i - dis, i + dis):
                                        if _j < 0 or _i < 0 or _j >= height or _i >= width:
                                            continue
                                        if hasBorder:
                                            break
                                        if pixel_type[_i, _j] == 255:
                                            hasBorder = True
                                            break

                                if not hasBorder:
                                    pixel_type[i, j] = 251

            map_data.optimized_pixel_type = pixel_type
            map_data.optimized_dimensions = MapImageDimensions(top, left, height, width, map_data.dimensions.grid_size)

    def optimize(self, map_data: Any, saved_map_data: Any = None) -> Any:
        if map_data.saved_map:
            return map_data

        if map_data.wifi_map:
            map_data.optimized_pixel_type = np.copy(map_data.pixel_type)
            map_data.optimized_dimensions = map_data.dimensions
            if not map_data.empty_map:
                for y in range(map_data.dimensions.height):
                    for x in range(map_data.dimensions.width):
                        if int(map_data.pixel_type[x, y]) > 2:
                            max_count = 0
                            max_px = -1
                            value_count = [0, 0, 0, 0]
                            for delta in range(3, 6):
                                for n in range(y - delta, y + delta + 1):
                                    for m in range(x - delta, x + delta + 1):
                                        if (
                                            n < 0
                                            or n >= map_data.dimensions.height
                                            or m < 0
                                            or m >= map_data.dimensions.width
                                        ):
                                            continue

                                        px = int(map_data.pixel_type[m, n]) - 11
                                        if px >= 0:
                                            value_count[px] = value_count[px] + 1
                                            if value_count[px] > max_count:
                                                max_count = value_count[px]
                                                max_px = px

                                if max_px >= 0:
                                    map_data.optimized_pixel_type[x, y] = MapPixelType(max_px + 11)
                                    break
            return map_data

        try:
            if self._js_optimizer is None:
                self._js_optimizer = MiniRacer()
                self._js_optimizer.eval(base64.b64decode(MAP_OPTIMIZER_JS).decode("utf-8"))

            data = map_data.pixel_type.tolist()
            data_size = [
                map_data.dimensions.left,
                map_data.dimensions.top,
                map_data.dimensions.width,
                map_data.dimensions.height,
                map_data.dimensions.grid_size,
            ]
            saved_data = saved_map_data.pixel_type.tolist() if saved_map_data else None
            saved_data_size = (
                [
                    saved_map_data.dimensions.left,
                    saved_map_data.dimensions.top,
                    saved_map_data.dimensions.width,
                    saved_map_data.dimensions.height,
                    saved_map_data.dimensions.grid_size,
                ]
                if saved_map_data
                else None
            )
            charger_position = None
            if map_data.charger_position:
                left = map_data.dimensions.left
                top = map_data.dimensions.top

                if saved_map_data:
                    if saved_map_data.dimensions.left < left:
                        left = saved_map_data.dimensions.left

                    if saved_map_data.dimensions.top < top:
                        top = saved_map_data.dimensions.top

                charger_position = [
                    (map_data.charger_position.x - left) / map_data.dimensions.grid_size,
                    (map_data.charger_position.y - top) / map_data.dimensions.grid_size,
                    map_data.charger_position.a,
                ]

            result = self._js_optimizer.call(
                "optimize",
                data,
                data_size,
                saved_data,
                saved_data_size,
                charger_position,
            )
            if result and result[0]:
                map_data.optimized_pixel_type = np.array(result[0], dtype=np.uint8)

                dimensions = result[1]
                map_data.optimized_dimensions = MapImageDimensions(
                    dimensions[1],
                    dimensions[0],
                    dimensions[3],
                    dimensions[2],
                    map_data.dimensions.grid_size,
                )

        except Exception:
            _LOGGER.warning("Optimize map failed: %s", traceback.format_exc())

            self._merge_saved_map_data(map_data, saved_map_data)


        return map_data
