"""Stateless helpers for :class:`DreameVacuumMapRenderer`.

These were originally staticmethods directly inside the monolithic
``map_renderer.py``. Moving them to a dedicated mixin keeps the core
class file focused on the rendering logic while preserving both
``self._xxx`` and ``DreameVacuumMapRenderer._xxx`` call sites — the
mixin is inherited by the renderer, so existing call sites keep working.
"""

from __future__ import annotations

import io
import math
from typing import Any

import numpy as np
from PIL import Image

from ..const import (
    MAP_DATA_JSON_PARAMETER_X,
    MAP_DATA_JSON_PARAMETER_Y,
    MAP_PARAMETER_MAP,
    MAP_PARAMETER_VACUUM,
)
from ..vacuum_types import MapData, Point


class _StaticHelpersMixin:
    """Collection of pure-function staticmethods used by the renderer.

    None of these reference ``self`` — they operate purely on their
    arguments — but they are exposed as staticmethods of the class so that
    the historical call pattern (``self._to_buffer(img)`` /
    ``DreameVacuumMapRenderer._alpha_composite(a, b)``) still works after
    the split.
    """

    @staticmethod
    def _to_buffer(image: Image.Image | None) -> bytes | None:
        if image:
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()
        return None

    @staticmethod
    def _set_icon_color(image: Image.Image, size: float, color: Any) -> Image.Image:
        ico = image.resize((int(size), int(size)))
        arr = np.array(ico)
        mask = (arr[:, :, 0] > 80) & (arr[:, :, 1] > 80) & (arr[:, :, 2] > 80) & (arr[:, :, 3] > 80)
        arr[mask] = color
        return Image.fromarray(arr)

    @staticmethod
    def _round_coord(coord: float, grid_size: float) -> float:
        remainder = coord % grid_size
        if remainder <= grid_size / 2:
            return coord - remainder
        return coord + grid_size - remainder

    @staticmethod
    def _calculate_calibration_points(map_data: MapData) -> list[dict[str, Any]] | None:
        if map_data.dimensions and (map_data.dimensions.width * map_data.dimensions.height) > 0:
            calibration_points = []
            for point in [Point(0, 0), Point(1000, 0), Point(0, 1000)]:
                img_point = point.to_img(map_data.dimensions).rotated(map_data.dimensions, map_data.rotation)
                calibration_points.append(
                    {
                        MAP_PARAMETER_VACUUM: {
                            MAP_DATA_JSON_PARAMETER_X: point.x,
                            MAP_DATA_JSON_PARAMETER_Y: point.y,
                        },
                        MAP_PARAMETER_MAP: {
                            MAP_DATA_JSON_PARAMETER_X: int(img_point.x),
                            MAP_DATA_JSON_PARAMETER_Y: int(img_point.y),
                        },
                    }
                )
            return calibration_points
        return None

    @staticmethod
    def _alpha_composite(source: Any, destination: Any) -> Any:
        srcA = source[3] / 255.0
        dstA = destination[3] / 255.0
        outA = srcA + dstA * (1 - srcA)
        if outA:
            outRGB = []
            for i in range(3):
                outRGB.append((float(source[i]) * srcA + float(destination[i]) * dstA * (1 - srcA)) / outA)
            return (int(outRGB[0]), int(outRGB[1]), int(outRGB[2]), int(outA * 255))
        return source

    @staticmethod
    def _close_image(img: Image.Image | None) -> None:
        """Safely close a PIL Image to release memory."""
        if img is not None:
            try:
                img.close()
            except (AttributeError, ValueError, OSError):
                # Already closed, not a PIL image, or backend error — nothing to do.
                pass

    @staticmethod
    def _del_layer(cached_layers: dict[Any, Any], key: Any) -> None:
        """Remove a layer from cache, closing its image(s) to free memory."""
        old = cached_layers.pop(key, None)
        if old is None:
            return
        if isinstance(old, dict):
            for v in old.values():
                _StaticHelpersMixin._close_image(v)
        else:
            _StaticHelpersMixin._close_image(old)

    @staticmethod
    def _replace_layer(cached_layers: dict[Any, Any], key: Any, new_image: Image.Image | None) -> None:
        """Replace a cached layer, closing the old image to free memory."""
        old = cached_layers.get(key)
        cached_layers[key] = new_image
        if old is not None and old is not new_image:
            _StaticHelpersMixin._close_image(old)

    @staticmethod
    def _combine_layers(cached_layers: dict[Any, Any], layer_size: tuple[int, int], parent: Any, sub: Any) -> None:
        old_parent = cached_layers.get(parent)
        cached_layers[parent] = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        if old_parent is not None:
            _StaticHelpersMixin._close_image(old_parent)
        if sub in cached_layers:
            for k, v in sorted(cached_layers[sub].items()):
                if v is not None:
                    old = cached_layers[parent]
                    cached_layers[parent] = Image.alpha_composite(old, v)
                    _StaticHelpersMixin._close_image(old)

    @staticmethod
    def _coords_on_line(
        x0: float, y0: float, x1: float, y1: float, spacing: float, size: int | None = None
    ) -> list[tuple[float, float]]:
        x = x1 - x0
        y = y1 - y0
        count = size - 1 if size else math.floor(math.sqrt(x * x + y * y) / spacing) if spacing else 0
        if count <= 0:
            return [(x0, y0)]
        points = []
        for i in range(count + 1):
            points.append((x0 + x * (i / count), y0 + y * (i / count)))
        return points
