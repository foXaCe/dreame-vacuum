"""Characterization tests for the map-rendering pipeline (map_renderer package).

Exercises ``DreameVacuumMapRenderer`` (``_core.py``) end-to-end plus the
``_StaticHelpersMixin`` (``_helpers.py``), ``_ShapesMixin`` (``_shapes.py``) and
``_ObjectsMixin`` (``_objects.py``) building blocks directly. Real
``MapData``/``Segment``/... instances are used throughout (no ``SimpleNamespace``
shortcuts) and pixel values are decoded via PIL and asserted exactly, in the same
spirit as ``tests/test_camera.py``.
"""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import numpy as np
from PIL import Image
import pytest

from custom_components.dreame_vacuum.dreame.map_renderer._core import DreameVacuumMapRenderer
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    Area,
    Furniture,
    FurnitureType,
    MapData,
    MapImageDimensions,
    MapPixelType,
    MapRendererColorScheme,
    MapRendererLayer,
    Obstacle,
    ObstacleType,
    Point,
    Segment,
    Wall,
)

GRID_SIZE = 50
WIDTH = 20
HEIGHT = 20


def _make_small_map_data() -> MapData:
    """20x20 grid: WALL border, left interior half segment 1, right half segment 2."""
    pixel_type = np.zeros((WIDTH, HEIGHT), dtype=np.uint8)
    pixel_type[1:10, 1:19] = 1
    pixel_type[10:19, 1:19] = 2
    pixel_type[0, :] = MapPixelType.WALL.value
    pixel_type[WIDTH - 1, :] = MapPixelType.WALL.value
    pixel_type[:, 0] = MapPixelType.WALL.value
    pixel_type[:, HEIGHT - 1] = MapPixelType.WALL.value

    seg1 = Segment(1, x0=50, y0=100, x1=450, y1=900, x=250, y=500)
    seg1.color_index = 0
    seg2 = Segment(2, x0=500, y0=100, x1=900, y1=900, x=700, y=500)
    seg2.color_index = 1

    md = MapData()
    md.dimensions = MapImageDimensions(top=0, left=0, height=HEIGHT, width=WIDTH, grid_size=GRID_SIZE)
    md.pixel_type = pixel_type
    md.segments = {1: seg1, 2: seg2}
    md.robot_position = Point(75, 850, a=0)
    md.charger_position = Point(75, 750, a=0)
    md.rotation = 0
    md.map_id = 1
    md.frame_id = 1
    md.saved_map = False
    md.wifi_map = False
    md.history_map = False
    md.recovery_map = False
    md.restored_map = False
    md.cleaning_map = False
    md.saved_map_status = None
    md.empty_map = False
    return md


# ---------------------------------------------------------------------------
# render_map: full pipeline
# ---------------------------------------------------------------------------


class TestRenderMapFullPipeline:
    def test_renders_wall_segment_and_outside_colors(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)

        png_bytes = renderer.render_map(map_data, robot_status=1, station_status=0)
        img = Image.open(io.BytesIO(png_bytes))

        assert img.format == "PNG"
        assert img.size == (352, 272)

        rgba = img.convert("RGBA")
        # Outside/background: fully transparent corners, far from any content.
        assert rgba.getpixel((0, 0)) == (0, 0, 0, 0)
        assert rgba.getpixel((5, 5)) == (0, 0, 0, 0)

        # Wall border pixel (grid x=0, y=2) -> exact renderer wall color.
        assert rgba.getpixel((156, 150)) == MapRendererColorScheme().wall
        # Segment 1 interior pixel (grid x=2, y=2) -> segment color_index 0.
        assert rgba.getpixel((160, 150)) == MapRendererColorScheme().segment[0][0]
        # Segment 2 interior pixel (grid x=15, y=2) -> segment color_index 1.
        assert rgba.getpixel((186, 150)) == MapRendererColorScheme().segment[1][0]

    def test_calibration_points_set_after_render(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)
        renderer.render_map(map_data, robot_status=1, station_status=0)

        points = renderer.calibration_points
        assert isinstance(points, list)
        assert len(points) == 3
        for point in points:
            assert set(point.keys()) == {"vacuum", "map"}

    def test_cache_hit_skips_full_re_render(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)

        first = renderer.render_map(map_data, robot_status=1, station_status=0)
        assert MapRendererLayer.IMAGE in renderer._layers

        calls: list[int] = []
        original = DreameVacuumMapRenderer._calculate_padding

        def _counting_calculate_padding(*args: object, **kwargs: object) -> object:
            calls.append(1)
            return original(*args, **kwargs)

        DreameVacuumMapRenderer._calculate_padding = staticmethod(_counting_calculate_padding)
        try:
            second = renderer.render_map(map_data, robot_status=1, station_status=0)
        finally:
            DreameVacuumMapRenderer._calculate_padding = original

        # Cache short-circuit returns before _calculate_padding is ever reached.
        assert calls == []
        assert second == first
        assert renderer.render_complete is True

    def test_render_map_none_returns_default_image(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        result = renderer.render_map(None, robot_status=0, station_status=0)
        assert result == renderer.default_map_image

    def test_render_map_empty_map_returns_default_image(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        map_data = MapData()
        map_data.empty_map = True
        result = renderer.render_map(map_data, robot_status=0, station_status=0)
        assert result == renderer.default_map_image

    def test_render_map_no_dimensions_returns_default_image(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        map_data = MapData()
        map_data.empty_map = False
        map_data.dimensions = None
        result = renderer.render_map(map_data, robot_status=0, station_status=0)
        assert result == renderer.default_map_image

    def test_render_map_tiny_area_returns_default_image(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        map_data = MapData()
        map_data.empty_map = False
        map_data.dimensions = MapImageDimensions(top=0, left=0, height=1, width=1, grid_size=50)
        result = renderer.render_map(map_data, robot_status=0, station_status=0)
        assert result == renderer.default_map_image


# ---------------------------------------------------------------------------
# default_map_image / disconnected_map_image
# ---------------------------------------------------------------------------


class TestDefaultAndDisconnectedMapImage:
    def test_default_map_image_bytes_are_cached(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        first = renderer.default_map_image
        second = renderer.default_map_image
        assert first is second
        img = Image.open(io.BytesIO(first))
        assert img.format == "PNG"

    def test_disconnected_map_image_falls_back_to_default_without_render(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        assert renderer.disconnected_map_image == renderer.default_map_image

    def test_disconnected_map_image_bytes_are_cached_after_render(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)
        renderer.render_map(map_data, robot_status=1, station_status=0)

        first = renderer.disconnected_map_image
        second = renderer.disconnected_map_image
        assert first is second
        img = Image.open(io.BytesIO(first))
        assert img.format == "PNG"
        assert img.size == (352, 272)


# ---------------------------------------------------------------------------
# get_data_string
# ---------------------------------------------------------------------------


class TestGetDataString:
    def test_none_map_data_returns_empty_payload(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        parsed = json.loads(renderer.get_data_string(None))
        assert parsed["empty_map"] is True
        assert parsed["size"] == [0, 0, 1, 1, 0, 0, [0, 0, 0, 0]]

    def test_full_map_payload_structure(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=True)

        parsed = json.loads(renderer.get_data_string(map_data, robot_status=1, station_status=0))

        assert parsed["empty_map"] is False
        assert parsed["size"] == [0, 0, 20, 20, 50, 0, [0, 0, 0, 0]]
        assert parsed["robot_position"] == [75, 850, 0]
        assert parsed["charger_position"] == [75, 750, 0]
        assert parsed["robot_status"] == 1

        assert isinstance(parsed["data"], dict)
        assert set(parsed["data"].keys()) == {"1", "2", "255"}
        for rle in parsed["data"].values():
            assert isinstance(rle, list)
            assert len(rle) % 3 == 0

        assert parsed["segments"] == [
            [
                1,
                250,
                500,
                0,
                None,
                0,
                0,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                [50, 100, 450, 900],
                None,
                None,
            ],
            [
                2,
                700,
                500,
                0,
                None,
                0,
                1,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                [500, 100, 900, 900],
                None,
                None,
            ],
        ]


# ---------------------------------------------------------------------------
# _StaticHelpersMixin (_helpers.py)
# ---------------------------------------------------------------------------


class TestStaticHelpers:
    def test_to_buffer_none(self) -> None:
        assert DreameVacuumMapRenderer._to_buffer(None) is None

    def test_to_buffer_encodes_png(self) -> None:
        img = Image.new("RGBA", (2, 2), (1, 2, 3, 4))
        data = DreameVacuumMapRenderer._to_buffer(img)
        assert isinstance(data, bytes)
        decoded = Image.open(io.BytesIO(data))
        assert decoded.format == "PNG"
        assert decoded.size == (2, 2)

    def test_set_icon_color_masks_bright_pixels_only(self) -> None:
        img = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
        img.putpixel((0, 0), (200, 200, 200, 200))  # all channels > 80 -> masked
        img.putpixel((1, 0), (50, 200, 200, 200))  # R <= 80 -> unchanged
        img.putpixel((0, 1), (200, 200, 200, 50))  # A <= 80 -> unchanged
        img.putpixel((1, 1), (90, 90, 90, 90))  # all channels > 80 -> masked

        out = DreameVacuumMapRenderer._set_icon_color(img, 2, (1, 2, 3, 4))
        arr = np.array(out)

        assert tuple(arr[0, 0]) == (1, 2, 3, 4)
        assert tuple(arr[0, 1]) == (50, 200, 200, 200)
        assert tuple(arr[1, 0]) == (200, 200, 200, 50)
        assert tuple(arr[1, 1]) == (1, 2, 3, 4)

    def test_calculate_calibration_points_worked_example(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=50)
        map_data = MapData()
        map_data.dimensions = dims
        map_data.rotation = 0

        result = DreameVacuumMapRenderer._calculate_calibration_points(map_data)

        assert result == [
            {"vacuum": {"x": 0, "y": 0}, "map": {"x": 0, "y": 9}},
            {"vacuum": {"x": 1000, "y": 0}, "map": {"x": 20, "y": 9}},
            {"vacuum": {"x": 0, "y": 1000}, "map": {"x": 0, "y": -10}},
        ]

    def test_calculate_calibration_points_none_without_dimensions(self) -> None:
        map_data = MapData()
        map_data.dimensions = None
        assert DreameVacuumMapRenderer._calculate_calibration_points(map_data) is None

    def test_calculate_calibration_points_none_with_zero_area(self) -> None:
        map_data = MapData()
        map_data.dimensions = MapImageDimensions(top=0, left=0, height=0, width=10, grid_size=50)
        map_data.rotation = 0
        assert DreameVacuumMapRenderer._calculate_calibration_points(map_data) is None

    def test_alpha_composite_blends_partial_alpha(self) -> None:
        assert DreameVacuumMapRenderer._alpha_composite((255, 0, 0, 128), (0, 255, 0, 255)) == (128, 127, 0, 255)

    def test_alpha_composite_zero_alpha_returns_source_unchanged(self) -> None:
        assert DreameVacuumMapRenderer._alpha_composite((10, 20, 30, 0), (40, 50, 60, 0)) == (10, 20, 30, 0)

    def test_close_image_handles_none_and_double_close(self) -> None:
        DreameVacuumMapRenderer._close_image(None)
        img = Image.new("RGBA", (2, 2))
        DreameVacuumMapRenderer._close_image(img)
        DreameVacuumMapRenderer._close_image(img)  # double close must not raise

    def test_close_image_swallows_non_pil_objects(self) -> None:
        class NotAnImage:
            pass

        DreameVacuumMapRenderer._close_image(NotAnImage())  # AttributeError caught internally

    def test_del_layer_closes_single_image_and_removes_key(self) -> None:
        img = Image.new("RGBA", (4, 4), (1, 2, 3, 4))
        cached_layers = {"a": img}
        DreameVacuumMapRenderer._del_layer(cached_layers, "a")
        assert "a" not in cached_layers
        with pytest.raises(ValueError, match="closed"):
            img.load()

    def test_del_layer_closes_dict_of_images(self) -> None:
        img_a = Image.new("RGBA", (2, 2), (1, 1, 1, 1))
        img_b = Image.new("RGBA", (2, 2), (2, 2, 2, 2))
        cached_layers = {"multi": {0: img_a, 1: img_b}}
        DreameVacuumMapRenderer._del_layer(cached_layers, "multi")
        assert "multi" not in cached_layers
        with pytest.raises(ValueError, match="closed"):
            img_a.load()
        with pytest.raises(ValueError, match="closed"):
            img_b.load()

    def test_del_layer_missing_key_is_noop(self) -> None:
        DreameVacuumMapRenderer._del_layer({}, "missing")

    def test_replace_layer_closes_old_image(self) -> None:
        old = Image.new("RGBA", (4, 4), (9, 9, 9, 9))
        new = Image.new("RGBA", (4, 4), (1, 1, 1, 1))
        cached_layers = {"k": old}
        DreameVacuumMapRenderer._replace_layer(cached_layers, "k", new)
        assert cached_layers["k"] is new
        with pytest.raises(ValueError, match="closed"):
            old.load()

    def test_combine_layers_composites_sub_layers_into_parent(self) -> None:
        sub_image = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
        cached_layers = {"sub": {0: sub_image}}
        DreameVacuumMapRenderer._combine_layers(cached_layers, (2, 2), "parent", "sub")
        assert "parent" in cached_layers
        arr = np.array(cached_layers["parent"])
        assert (arr == (255, 0, 0, 255)).all()

    def test_coords_on_line_subdivides_by_spacing(self) -> None:
        assert DreameVacuumMapRenderer._coords_on_line(0, 0, 10, 0, 5) == [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)]

    def test_coords_on_line_size_override(self) -> None:
        assert DreameVacuumMapRenderer._coords_on_line(0, 0, 10, 0, 5, size=3) == [
            (0.0, 0.0),
            (5.0, 0.0),
            (10.0, 0.0),
        ]

    def test_coords_on_line_zero_length_returns_single_point(self) -> None:
        assert DreameVacuumMapRenderer._coords_on_line(0, 0, 0, 0, 5) == [(0, 0)]

    def test_coords_on_line_zero_spacing_returns_single_point(self) -> None:
        assert DreameVacuumMapRenderer._coords_on_line(0, 0, 10, 0, 0) == [(0, 0)]


# ---------------------------------------------------------------------------
# _ShapesMixin (_shapes.py)
# ---------------------------------------------------------------------------


class TestShapesMixin:
    @staticmethod
    def _renderer() -> DreameVacuumMapRenderer:
        return DreameVacuumMapRenderer(low_resolution=True)

    def test_render_walls_draws_line_at_expected_pixel(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=1)
        layer_size = (20, 20)
        wall = Wall(5, 5, 15, 5)

        layer = renderer.render_walls([wall], (255, 0, 0, 255), layer_size, dims, 1, 1)
        arr = np.array(layer)

        p = wall.to_img(dims)
        assert tuple(arr[int(p.y0), 10]) == (255, 0, 0, 255)
        assert tuple(arr[0, 0]) == (255, 255, 255, 0)

    def test_render_areas_fills_polygon(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=1)
        layer_size = (20, 20)
        area = Area(5, 5, 5, 15, 15, 15, 15, 5)

        layer = renderer.render_areas([area], (0, 255, 0, 255), (0, 0, 255, 100), layer_size, dims, 1, 1)
        arr = np.array(layer)

        p = area.to_img(dims)
        cx, cy = int((p.x0 + p.x2) / 2), int((p.y0 + p.y2) / 2)
        assert tuple(arr[cy, cx]) == (0, 0, 255, 100)
        assert tuple(arr[0, 0]) == (255, 255, 255, 0)

    def test_render_points_fills_square_around_point(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer_size = (50, 50)
        point = Point(25, 25)

        layer = renderer.render_points([point], (255, 0, 0, 255), (0, 0, 255, 90), layer_size, dims, 1, 1)
        arr = np.array(layer)

        p = point.to_img(dims)
        assert tuple(arr[int(p.y), int(p.x)]) == (0, 0, 255, 90)
        assert tuple(arr[0, 0]) == (255, 255, 255, 0)

    def test_render_thresholds_fills_between_edges(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=30, width=30, grid_size=1)
        layer_size = (30, 30)
        wall = Wall(5, 15, 25, 15)

        layer = renderer.render_thresholds([wall], (255, 0, 0, 255), (0, 255, 0, 255), layer_size, dims, 1, 1)
        arr = np.array(layer)

        p = wall.to_img(dims)
        assert tuple(arr[int(p.y0), 15]) == (0, 255, 0, 255)
        assert tuple(arr[0, 0]) == (255, 255, 255, 0)

    def test_render_curtains_draws_dashed_line(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=350, grid_size=1)
        layer_size = (350, 50)
        wall = Wall(10, 25, 310, 25)

        layer = renderer.render_curtains([wall], (0, 0, 255, 255), layer_size, dims, 1, 1)
        arr = np.array(layer)

        assert tuple(arr[29, 10]) == (0, 0, 255, 255)
        assert tuple(arr[0, 0]) == (255, 255, 255, 0)

    def test_render_ramps_fills_polygon_and_draws_arrows(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer_size = (50, 50)
        ramp = Area(10, 10, 10, 30, 30, 30, 30, 10)

        layer = renderer.render_ramps([ramp], (255, 0, 0, 255), (0, 255, 0, 80), layer_size, dims, 1, 1, 0)
        arr = np.array(layer)

        p = ramp.to_img(dims)
        cx, cy = int((p.x0 + p.x2) / 2), int((p.y0 + p.y2) / 2)
        assert tuple(arr[cy, cx]) == (0, 255, 0, 80)
        assert tuple(arr[0, 0]) == (255, 255, 255, 0)


# ---------------------------------------------------------------------------
# _ObjectsMixin (_objects.py)
# ---------------------------------------------------------------------------


class TestObjectsMixin:
    @staticmethod
    def _renderer() -> DreameVacuumMapRenderer:
        # low_resolution=False keeps _low_memory False, so status/sleeping icon
        # overlays are actually rendered (they're skipped entirely when
        # _low_memory is True).
        return DreameVacuumMapRenderer(low_resolution=False)

    def test_render_vacuum_status_layers_differ(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer_size = (100, 100)
        robot_position = Point(25, 25, a=0)

        layer_cleaning = renderer.render_vacuum(robot_position, 1, layer_size, dims, 10, 0, 2)
        layer_charging = renderer.render_vacuum(robot_position, 2, layer_size, dims, 10, 0, 2)
        layer_warning = renderer.render_vacuum(robot_position, 10, layer_size, dims, 10, 0, 2)

        arr_cleaning = np.array(layer_cleaning)
        arr_charging = np.array(layer_charging)
        arr_warning = np.array(layer_warning)

        assert (arr_cleaning[:, :, 3] > 0).any()
        assert (arr_charging[:, :, 3] > 0).any()
        assert (arr_warning[:, :, 3] > 0).any()
        assert (arr_cleaning != arr_charging).any()
        assert (arr_charging != arr_warning).any()

    def test_render_vacuum_sleeping_icon_position_shifts_with_rotation(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer_size = (100, 100)
        robot_position = Point(25, 25, a=0)

        layer_rot0 = self._renderer().render_vacuum(robot_position, 3, layer_size, dims, 10, 0, 2)
        layer_rot90 = self._renderer().render_vacuum(robot_position, 3, layer_size, dims, 10, 90, 2)

        arr_rot0 = np.array(layer_rot0)
        arr_rot90 = np.array(layer_rot90)
        assert (arr_rot0 != arr_rot90).any()

        ys0, xs0 = np.where(arr_rot0[:, :, 3] > 0)
        ys90, xs90 = np.where(arr_rot90[:, :, 3] > 0)
        bbox_rot0 = (int(xs0.min()), int(xs0.max()), int(ys0.min()), int(ys0.max()))
        bbox_rot90 = (int(xs90.min()), int(xs90.max()), int(ys90.min()), int(ys90.max()))
        assert bbox_rot0 != bbox_rot90

    def test_render_charger_idle_vs_washing(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer_size = (100, 100)
        charger_position = Point(25, 25, a=0)

        layer_idle = renderer.render_charger(charger_position, 0, layer_size, dims, 10, 0, 2)
        assert renderer._charger_icon is not None
        arr_idle = np.array(layer_idle)
        assert (arr_idle[:, :, 3] > 0).any()

        # Freeze the washing-icon spinner clock so the rendered layer is deterministic.
        with patch("custom_components.dreame_vacuum.dreame.map_renderer._objects.time.time", return_value=0.0):
            layer_washing = renderer.render_charger(charger_position, 2, layer_size, dims, 10, 0, 2)
        arr_washing = np.array(layer_washing)

        assert (arr_washing[:, :, 3] > 0).any()
        assert (arr_idle != arr_washing).any()

    def test_render_obstacle_default_vs_ignored_variants(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer_size = (100, 100)

        obstacle_default = Obstacle(25, 25, type=ObstacleType.OBSTACLE.value, possibility=90)
        obstacle_manual = Obstacle(25, 25, type=ObstacleType.OBSTACLE.value, possibility=90, ignore_status=1)
        obstacle_auto = Obstacle(25, 25, type=ObstacleType.OBSTACLE.value, possibility=90, ignore_status=2)

        layer_default = renderer.render_obstacle(obstacle_default, layer_size, dims, 10, 0, 2)
        layer_manual = renderer.render_obstacle(obstacle_manual, layer_size, dims, 10, 0, 2)
        layer_auto = renderer.render_obstacle(obstacle_auto, layer_size, dims, 10, 0, 2)

        assert layer_default is not None
        assert layer_manual is not None
        assert layer_auto is not None

        arr_default = np.array(layer_default)
        arr_manual = np.array(layer_manual)
        arr_auto = np.array(layer_auto)

        assert (arr_default[:, :, 3] > 0).any()
        assert (arr_manual[:, :, 3] > 0).any()
        assert (arr_auto[:, :, 3] > 0).any()
        assert (arr_default != arr_manual).any()
        assert (arr_default != arr_auto).any()

    def test_render_obstacle_unknown_icon_type_returns_none(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer_size = (100, 100)
        obstacle = Obstacle(25, 25, type=ObstacleType.UNKNOWN.value, possibility=90)
        assert renderer.render_obstacle(obstacle, layer_size, dims, 10, 0, 2) is None

    def test_render_furniture_image_and_icon_paths(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer_size = (100, 100)

        furniture_image = Furniture(
            25, 25, x0=20, y0=20, width=10, height=10, type=FurnitureType.SINGLE_BED, size_type=0
        )
        layer_image = renderer.render_furniture(furniture_image, 1, layer_size, dims, 10, 0, 2)
        assert layer_image is not None
        assert (np.array(layer_image)[:, :, 3] > 0).any()

        furniture_icon = Furniture(25, 25, x0=0, y0=0, width=0, height=0, type=FurnitureType.SINGLE_BED, size_type=0)
        layer_icon = renderer.render_furniture(furniture_icon, 1, layer_size, dims, 10, 0, 2)
        assert layer_icon is not None
        assert (np.array(layer_icon)[:, :, 3] > 0).any()

        assert (np.array(layer_image) != np.array(layer_icon)).any()
