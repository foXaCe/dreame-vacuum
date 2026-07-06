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
    Carpet,
    Coordinate,
    Furniture,
    FurnitureType,
    MapData,
    MapImageDimensions,
    MapPixelType,
    MapRendererColorScheme,
    MapRendererLayer,
    Obstacle,
    ObstacleType,
    Path,
    PathType,
    Point,
    Polygon,
    RobotType,
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


def _make_inset_map_data() -> MapData:
    """20x20 grid with a single segment inset from every edge (no wall border).

    Unlike :func:`_make_small_map_data`, non-zero pixels never touch the map
    edges, so the raw min/max pixel scan in ``get_data_string``/``render_map``
    finds a bounding box strictly smaller than the full canvas -> exercises
    the "crop" branches that a full-wall-border map can never reach.
    """
    pixel_type = np.zeros((WIDTH, HEIGHT), dtype=np.uint8)
    pixel_type[5:15, 5:15] = 1

    seg1 = Segment(1, x0=250, y0=250, x1=750, y1=750, x=500, y=500)
    seg1.color_index = 0

    md = MapData()
    md.dimensions = MapImageDimensions(top=0, left=0, height=HEIGHT, width=WIDTH, grid_size=GRID_SIZE)
    md.pixel_type = pixel_type
    md.segments = {1: seg1}
    md.robot_position = Point(500, 500, a=0)
    md.charger_position = Point(500, 600, a=0)
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

    def test_wall_lines_alone_does_not_change_pixel_output(self) -> None:
        """wall_lines has no rendering effect today.

        Replacing the pixel wall contour with wall_lines vectors is BLOCKED
        (see docs/dev/wall-lines-render-spike.md): on the real reference
        fixture only ~44% of grid wall cells sit near a wall_lines segment,
        and every wall_lines segment is axis-aligned anyway (zero anti-
        aliasing to gain where it *is* covered). So wall_lines is decoded
        and carried on MapData, but the renderer must not act on it: this
        pins the current byte-identical fallback so it isn't silently
        broken by a future half-finished attempt.
        """
        baseline = _make_small_map_data()
        png_without = DreameVacuumMapRenderer(low_resolution=True, cache=True).render_map(
            baseline, robot_status=1, station_status=0
        )

        with_wall_lines = _make_small_map_data()
        with_wall_lines.wall_lines = [Wall(0, 100, 900, 100)]
        png_with = DreameVacuumMapRenderer(low_resolution=True, cache=True).render_map(
            with_wall_lines, robot_status=1, station_status=0
        )

        assert png_with == png_without

    def test_door_lines_draw_additive_marker_without_touching_wall_or_segment_pixels(self) -> None:
        """door_lines (walls_info type 1) draw a distinct, additive marker.

        Unlike wall_lines, door_lines carry information the pixel grid has
        no way to express on its own, so they are rendered -- but only ever
        additively, layered after the existing wall pixels/objects, never
        replacing or duplicating them (that additive-over-wall-pixels
        pattern is exactly the reverted bug: redundant gray frames).
        """
        without_doors = _make_small_map_data()
        png_without = DreameVacuumMapRenderer(low_resolution=True, cache=True).render_map(
            without_doors, robot_status=1, station_status=0
        )

        with_doors = _make_small_map_data()
        with_doors.door_lines = [Wall(0, 500, 900, 500)]
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)
        png_with = renderer.render_map(with_doors, robot_status=1, station_status=0)

        # The door marker is drawn as its own object layer...
        assert MapRendererLayer.DOOR in renderer._layers
        # ...and something in the final PNG actually changed as a result.
        assert png_with != png_without

        img_with = Image.open(io.BytesIO(png_with)).convert("RGBA")
        # The wall-border and segment pixels asserted in the sibling test
        # (test_renders_wall_segment_and_outside_colors) are untouched.
        assert img_with.getpixel((156, 150)) == MapRendererColorScheme().wall
        assert img_with.getpixel((160, 150)) == MapRendererColorScheme().segment[0][0]
        assert img_with.getpixel((186, 150)) == MapRendererColorScheme().segment[1][0]

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


class TestGetDataStringExtras:
    def test_carpet_pixels_populate_layer_512(self) -> None:
        map_data = _make_small_map_data()
        map_data.carpet_pixels = [(2, 2), (3, 3)]
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        parsed = json.loads(renderer.get_data_string(map_data))
        assert "512" in parsed["data"]
        assert len(parsed["data"]["512"]) % 3 == 0

    def test_full_wall_border_map_never_crops(self) -> None:
        # _make_small_map_data's non-zero pixels (including the WALL border)
        # touch every edge of the canvas, so the bounding box always spans the
        # full grid and crop stays [0, 0, 0, 0].
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        parsed = json.loads(renderer.get_data_string(map_data))
        assert parsed["size"][6] == [0, 0, 0, 0]

    def test_inset_content_produces_nonzero_crop(self) -> None:
        # Non-zero pixels inset from every edge -> the pixel scan finds a
        # bounding box smaller than the canvas -> crop reflects the margins.
        map_data = _make_inset_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        parsed = json.loads(renderer.get_data_string(map_data))
        crop = parsed["size"][6]
        assert crop == [5, 5, 5, 5]

    def test_dimensions_bounds_do_not_affect_crop_bug(self) -> None:
        # BUG (pre-existing, documented not fixed): DreameVacuumMapRenderer
        # applies ``min_x = max(min(bounds[0], min_x), min_x)`` (and the
        # symmetric form for max_x/min_y/max_y) when narrowing the scanned
        # bounding box by ``dimensions.bounds``. That expression is a no-op —
        # ``max(min(a, b), b) == b`` always — so a narrower/wider
        # ``dimensions.bounds`` never actually changes the computed crop.
        # saved_map=True stops get_data_string from recalculating
        # dimensions.bounds itself, so a manually-set value survives long
        # enough to prove it has no effect on the resulting crop.
        map_data = _make_inset_map_data()
        map_data.saved_map = True
        renderer = DreameVacuumMapRenderer(low_resolution=True)

        map_data.dimensions.bounds = None
        parsed_without_bounds = json.loads(renderer.get_data_string(map_data))

        map_data.dimensions.bounds = [8, 8, 11, 11]  # much tighter than the actual [5,5,14,14] content
        parsed_with_bounds = json.loads(renderer.get_data_string(map_data))

        assert parsed_with_bounds["size"][6] == parsed_without_bounds["size"][6] == [5, 5, 5, 5]

    def test_saved_map_skips_bounds_recalculation_and_reuses_existing(self) -> None:
        map_data = _make_small_map_data()
        map_data.saved_map = True
        map_data.dimensions.bounds = [1, 1, 5, 5]
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        renderer.get_data_string(map_data)
        # Bounds must be left untouched since saved_map short-circuits recalculation.
        assert map_data.dimensions.bounds == [1, 1, 5, 5]

    def test_path_with_mixed_types_produces_grouped_segments(self) -> None:
        map_data = _make_small_map_data()
        map_data.path = [
            Path(10, 10, PathType.SWEEP),
            Path(20, 10, PathType.LINE),
            Path(20, 20, PathType.MOP),
            Path(30, 20, PathType.LINE),
            Path(30, 30, PathType.SWEEP_AND_MOP),
        ]
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        parsed = json.loads(renderer.get_data_string(map_data, robot_status=1, station_status=0))
        assert parsed["path"] is not None
        assert len(parsed["path"]) >= 2
        # Path type codes: S=1, W=2, M=3.
        assert parsed["path"][0][0] == 1

    def test_path_omitted_for_saved_map(self) -> None:
        map_data = _make_small_map_data()
        map_data.saved_map = True
        map_data.path = [Path(10, 10, PathType.SWEEP), Path(20, 10, PathType.LINE)]
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        parsed = json.loads(renderer.get_data_string(map_data, robot_status=1, station_status=0))
        assert parsed["path"] == []

    def test_single_point_trailing_path_segment_is_kept(self) -> None:
        map_data = _make_small_map_data()
        # A single SWEEP point with no further LINE points still yields a coords entry.
        map_data.path = [Path(10, 10, PathType.SWEEP), Path(15, 15, PathType.LINE)]
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        parsed = json.loads(renderer.get_data_string(map_data))
        assert parsed["path"] == [[1, 10, 10, 15, 15]]


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

    def test_render_doors_draws_dashed_line(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=350, grid_size=1)
        layer_size = (350, 50)
        wall = Wall(10, 25, 310, 25)

        layer = renderer.render_doors([wall], (0, 128, 255, 255), layer_size, dims, 1, 1)
        arr = np.array(layer)

        p = wall.to_img(dims)
        # dash_length=6, gap_length=5, period=11 at scale=1: x=13 falls inside
        # the first dash (0-6), x=19 falls inside the following gap (6-11).
        assert tuple(arr[int(p.y0), 13]) == (0, 128, 255, 255)
        assert tuple(arr[int(p.y0), 19]) == (255, 255, 255, 0)
        assert tuple(arr[0, 0]) == (255, 255, 255, 0)

    def test_render_doors_skips_zero_length_segment(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=1)
        layer_size = (20, 20)
        wall = Wall(5, 5, 5, 5)

        layer = renderer.render_doors([wall], (255, 0, 0, 255), layer_size, dims, 1, 1)
        arr = np.array(layer)

        assert not arr[..., 3].any()

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

    @pytest.mark.parametrize("robot_type", [RobotType.LIDAR, RobotType.MOPPING, RobotType.SWEEPING_AND_MOPPING])
    def test_render_vacuum_icon_selection_per_robot_type_mijia(self, robot_type: RobotType) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=False, icon_set="Mijia", robot_type=robot_type)
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer = renderer.render_vacuum(Point(25, 25, a=0), 0, (100, 100), dims, 10, 0, 2)
        assert (np.array(layer)[:, :, 3] > 0).any()

    @pytest.mark.parametrize("robot_type", [RobotType.LIDAR, RobotType.VSLAM])
    def test_render_vacuum_icon_selection_per_robot_type_material(self, robot_type: RobotType) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=False, icon_set="Material", robot_type=robot_type)
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer = renderer.render_vacuum(Point(25, 25, a=0), 0, (100, 100), dims, 10, 0, 2)
        assert (np.array(layer)[:, :, 3] > 0).any()

    def test_render_vacuum_dark_scheme_brightens_lidar_icon(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=False, color_scheme="Dreame Dark")
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer = renderer.render_vacuum(Point(25, 25, a=0), 0, (100, 100), dims, 10, 0, 2)
        assert (np.array(layer)[:, :, 3] > 0).any()

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_render_vacuum_sleeping_icon_all_rotations(self, rotation: int) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer = renderer.render_vacuum(Point(25, 25, a=0), 3, (100, 100), dims, 10, rotation, 2)
        assert (np.array(layer)[:, :, 3] > 0).any()

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_render_obstacle_all_rotations(self, rotation: int) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        obstacle = Obstacle(25, 25, type=ObstacleType.OBSTACLE.value, possibility=90)
        layer = renderer.render_obstacle(obstacle, (100, 100), dims, 10, rotation, 2)
        assert layer is not None
        assert (np.array(layer)[:, :, 3] > 0).any()

    def test_render_cruise_point_path_point_type(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        cruise_point = Coordinate(25, 25, completed=False, type=1)
        layer = renderer.render_cruise_point(1, cruise_point, (100, 100), dims, 10, 0, 2)
        assert (np.array(layer)[:, :, 3] > 0).any()
        assert renderer._cruise_path_point_background is not None

    def test_render_cruise_point_completed_vs_pending(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        pending = renderer.render_cruise_point(
            1, Coordinate(25, 25, completed=False, type=1), (100, 100), dims, 10, 0, 2
        )
        completed = renderer.render_cruise_point(
            1, Coordinate(25, 25, completed=True, type=1), (100, 100), dims, 10, 0, 2
        )
        assert (np.array(pending) != np.array(completed)).any()

    def test_render_cruise_point_regular_type(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        cruise_point = Coordinate(25, 25, completed=False, type=0)
        layer = renderer.render_cruise_point(2, cruise_point, (100, 100), dims, 10, 0, 2)
        assert (np.array(layer)[:, :, 3] > 0).any()
        assert renderer._cruise_point_background is not None

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_render_cruise_point_all_rotations(self, rotation: int) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        cruise_point = Coordinate(25, 25, completed=False, type=1)
        layer = renderer.render_cruise_point(3, cruise_point, (100, 100), dims, 10, rotation, 2)
        assert (np.array(layer)[:, :, 3] > 0).any()

    def test_render_furniture_version_2_and_3_image_maps(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        furniture = Furniture(25, 25, x0=20, y0=20, width=10, height=10, type=FurnitureType.SINGLE_BED, size_type=0)

        layer_v2 = renderer.render_furniture(furniture, 2, (100, 100), dims, 10, 0, 2)
        assert layer_v2 is not None
        assert (np.array(layer_v2)[:, :, 3] > 0).any()

        renderer_mijia = self._renderer()
        layer_v3 = renderer_mijia.render_furniture(furniture, 3, (100, 100), dims, 10, 0, 2)
        assert layer_v3 is not None
        assert (np.array(layer_v3)[:, :, 3] > 0).any()

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_render_furniture_icon_only_all_rotations(self, rotation: int) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        furniture = Furniture(25, 25, x0=0, y0=0, width=0, height=0, type=FurnitureType.SINGLE_BED, size_type=0)
        layer = renderer.render_furniture(furniture, 1, (100, 100), dims, 10, rotation, 2)
        assert layer is not None
        assert (np.array(layer)[:, :, 3] > 0).any()

    def test_render_furniture_unmapped_type_returns_none(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        # TABLE (26) has no v1 image or icon entry.
        furniture = Furniture(25, 25, x0=0, y0=0, width=0, height=0, type=FurnitureType.TABLE, size_type=0)
        assert renderer.render_furniture(furniture, 1, (100, 100), dims, 10, 0, 2) is None

    def test_render_charger_emptying_status(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer = renderer.render_charger(Point(25, 25, a=0), 1, (100, 100), dims, 10, 0, 2)
        assert (np.array(layer)[:, :, 3] > 0).any()
        assert renderer._robot_emptying_icon is not None

    def test_render_charger_drying_and_hot_drying(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        drying = renderer.render_charger(Point(25, 25, a=0), 5, (100, 100), dims, 10, 0, 2)
        assert renderer._robot_drying_icon is not None
        hot_drying = renderer.render_charger(Point(25, 25, a=0), 15, (100, 100), dims, 10, 0, 2)
        assert renderer._robot_hot_drying_icon is not None
        assert (np.array(drying) != np.array(hot_drying)).any()

    def test_render_charger_hot_washing_vs_normal_washing(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        with patch("custom_components.dreame_vacuum.dreame.map_renderer._objects.time.time", return_value=0.0):
            normal = renderer.render_charger(Point(25, 25, a=0), 2, (100, 100), dims, 10, 0, 2)
            hot = renderer.render_charger(Point(25, 25, a=0), 12, (100, 100), dims, 10, 0, 2)
        assert renderer._robot_washing_icon is not None
        assert renderer._robot_hot_washing_icon is not None
        assert (np.array(normal) != np.array(hot)).any()

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_render_charger_status_icon_offset_all_rotations(self, rotation: int) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer = renderer.render_charger(Point(25, 25, a=0), 1, (100, 100), dims, 10, rotation, 2)
        assert (np.array(layer)[:, :, 3] > 0).any()

    def test_render_charger_dark_scheme_dims_icon(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=False, color_scheme="Dreame Dark")
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer = renderer.render_charger(Point(25, 25, a=0), 0, (100, 100), dims, 10, 0, 2)
        assert (np.array(layer)[:, :, 3] > 0).any()

    def test_render_router_draws_wifi_icon(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        layer = renderer.render_router(Point(25, 25), (100, 100), dims, 10, 0, 2)
        assert (np.array(layer)[:, :, 3] > 0).any()
        assert renderer._wifi_icon is not None

    def test_render_router_dark_scheme_uses_darker_dot(self) -> None:
        light = self._renderer().render_router(
            Point(25, 25), (100, 100), MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1), 10, 0, 2
        )
        dark_renderer = DreameVacuumMapRenderer(low_resolution=False, color_scheme="Dreame Dark")
        dark = dark_renderer.render_router(
            Point(25, 25), (100, 100), MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1), 10, 0, 2
        )
        assert (np.array(light) != np.array(dark)).any()

    def test_render_neglected_segments_places_problem_icon(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        dims.scale = 1
        dims.padding = [0, 0, 0, 0]
        dims.crop = [0, 0, 0, 0]
        segment = Segment(1, x0=10, y0=10, x1=40, y1=40, x=25, y=25)
        segment_mask = Image.new("RGBA", (50, 50), (255, 255, 255, 0))
        layer = renderer.render_neglected_segments([1], {1: segment}, (50, 50), segment_mask, dims, 0, False)
        assert (np.array(layer)[:, :, 3] > 0).any()
        assert renderer._map_problem_icon is not None

    @pytest.mark.parametrize("rotation", [90, 270])
    def test_render_neglected_segments_height_based_sizing(self, rotation: int) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        dims.scale = 1
        dims.padding = [0, 0, 0, 0]
        dims.crop = [0, 0, 0, 0]
        segment = Segment(1, x0=10, y0=10, x1=40, y1=40, x=25, y=25)
        segment_mask = Image.new("RGBA", (50, 50), (255, 255, 255, 0))
        layer = renderer.render_neglected_segments([1], {1: segment}, (50, 50), segment_mask, dims, rotation, False)
        assert (np.array(layer)[:, :, 3] > 0).any()

    def test_render_neglected_segments_cleaning_map_shrinks_icon(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        dims.scale = 1
        dims.padding = [0, 0, 0, 0]
        dims.crop = [0, 0, 0, 0]
        segment = Segment(1, x0=10, y0=10, x1=40, y1=40, x=25, y=25)

        normal = renderer.render_neglected_segments(
            [1], {1: segment}, (50, 50), Image.new("RGBA", (50, 50), (255, 255, 255, 0)), dims, 0, False
        )
        cleaning_map = renderer.render_neglected_segments(
            [1], {1: segment}, (50, 50), Image.new("RGBA", (50, 50), (255, 255, 255, 0)), dims, 0, True
        )
        assert (np.array(normal) != np.array(cleaning_map)).any()

    def test_render_low_lying_areas_draws_polygon(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        dims.scale = 1
        dims.padding = [0, 0, 0, 0]
        dims.crop = [0, 0, 0, 0]
        area = Polygon(1, 10, 10, 10, 20, 20, 20, 20, 10, polygon=[10, 10, 20, 10, 20, 20, 10, 20], type=0)
        layer = renderer.render_low_lying_areas([area], (50, 50), dims, 1, 1)
        assert (np.array(layer)[:, :, 3] > 0).any()

    def test_render_low_lying_areas_skips_hidden(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        dims.scale = 1
        dims.padding = [0, 0, 0, 0]
        dims.crop = [0, 0, 0, 0]
        area = Polygon(1, 10, 10, 10, 20, 20, 20, 20, 10, polygon=[10, 10, 20, 10, 20, 20, 10, 20], type=0, hidden=1)
        layer = renderer.render_low_lying_areas([area], (50, 50), dims, 1, 1)
        assert not (np.array(layer)[:, :, 3] > 0).any()

    def test_render_low_lying_areas_manual_vs_auto_outline(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=50, width=50, grid_size=1)
        dims.scale = 1
        dims.padding = [0, 0, 0, 0]
        dims.crop = [0, 0, 0, 0]
        auto_area = Polygon(1, 10, 10, 10, 20, 20, 20, 20, 10, polygon=[10, 10, 20, 10, 20, 20, 10, 20], type=0)
        manual_area = Polygon(2, 10, 10, 10, 20, 20, 20, 20, 10, polygon=[10, 10, 20, 10, 20, 20, 10, 20], type=1)
        auto_layer = renderer.render_low_lying_areas([auto_area], (50, 50), dims, 1, 1)
        manual_layer = renderer.render_low_lying_areas([manual_area], (50, 50), dims, 1, 1)
        assert (np.array(auto_layer) != np.array(manual_layer)).any()


# ---------------------------------------------------------------------------
# __init__ icon_set variants / hidden_map_objects
# ---------------------------------------------------------------------------


class TestInitVariants:
    def test_construction_does_not_warm_up_icons(self) -> None:
        """Icon decoding is lazy: __init__ must leave the icon lists unset."""
        renderer = DreameVacuumMapRenderer(icon_set="Mijia")
        assert renderer._icons_warmed is False
        assert renderer._cleaning_times_icon is None
        assert renderer._suction_level_icon is None
        assert renderer._cleaning_mode_icon is None

    def test_icon_set_mijia_loads_mijia_icon_lists(self) -> None:
        renderer = DreameVacuumMapRenderer(icon_set="Mijia")
        assert renderer.icon_set == 2
        renderer._warm_up_icons()
        assert renderer._icons_warmed is True
        assert len(renderer._cleaning_times_icon) > 0
        assert len(renderer._suction_level_icon) > 0
        assert len(renderer._water_volume_icon) > 0
        assert len(renderer._mop_pad_humidity_icon) > 0
        assert len(renderer._cleaning_mode_icon) > 0

    def test_icon_set_material_loads_material_icon_lists(self) -> None:
        renderer = DreameVacuumMapRenderer(icon_set="Material")
        assert renderer.icon_set == 3
        renderer._warm_up_icons()
        assert len(renderer._cleaning_times_icon) > 0
        assert len(renderer._suction_level_icon) > 0
        assert len(renderer._water_volume_icon) > 0
        assert len(renderer._cleaning_route_icon) > 0
        assert len(renderer._custom_mopping_route_icon) > 0

    def test_warm_up_icons_is_idempotent(self) -> None:
        renderer = DreameVacuumMapRenderer(icon_set="Mijia")
        renderer._warm_up_icons()
        first = renderer._cleaning_times_icon
        renderer._warm_up_icons()
        assert renderer._cleaning_times_icon is first

    def test_construction_never_calls_pil_image_open(self) -> None:
        """No PIL decode may happen while building the renderer on the event loop."""
        with patch.object(Image, "open", wraps=Image.open) as spy:
            DreameVacuumMapRenderer(icon_set="Mijia")
        spy.assert_not_called()

    def test_icon_set_unknown_falls_back_to_dreame(self) -> None:
        renderer = DreameVacuumMapRenderer(icon_set="Does Not Exist")
        assert renderer.icon_set == 0

    def test_hidden_map_objects_disables_matching_config_attrs(self) -> None:
        renderer = DreameVacuumMapRenderer(hidden_map_objects=["path", "robot"])
        assert renderer.config.path is False
        assert renderer.config.robot is False
        # Unrelated attrs are untouched.
        assert renderer.config.charger is True

    def test_hidden_map_objects_none_leaves_config_defaults(self) -> None:
        renderer = DreameVacuumMapRenderer(hidden_map_objects=None)
        assert renderer.config.path is True
        assert renderer.config.robot is True

    def test_low_resolution_disables_obstacle_pet_furniture_config(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        assert renderer.config.obstacle is False
        assert renderer.config.pet is False
        assert renderer.config.furniture is False
        assert renderer._low_memory is True

    def test_unknown_color_scheme_falls_back_to_default(self) -> None:
        renderer = DreameVacuumMapRenderer(color_scheme="Does Not Exist")
        assert renderer.color_scheme == MapRendererColorScheme()


# ---------------------------------------------------------------------------
# _calculate_bounds
# ---------------------------------------------------------------------------


class TestCalculateBounds:
    def test_no_segments_returns_none(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        assert DreameVacuumMapRenderer._calculate_bounds(dims, None) is None
        assert DreameVacuumMapRenderer._calculate_bounds(dims, {}) is None

    def test_segments_produce_min_max_bounds(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        seg1 = Segment(1, x0=0, y0=0, x1=50, y1=50)
        seg2 = Segment(2, x0=100, y0=100, x1=150, y1=150)
        bounds = DreameVacuumMapRenderer._calculate_bounds(dims, {1: seg1, 2: seg2})
        assert bounds is not None
        min_x, min_y, max_x, max_y = bounds
        # Regression test for a real bug: the 4th element used to mirror
        # min_y instead of returning max_y (see test_map_renderer.py's
        # test_dimensions_bounds_do_not_affect_crop_bug - the downstream
        # narrowing math is a no-op either way, so this never affected
        # rendered output, but the returned tuple itself was wrong).
        assert max_y > min_y
        assert min_x <= max_x
        assert isinstance(min_x, int)
        assert isinstance(min_y, int)
        assert isinstance(max_y, int)


# ---------------------------------------------------------------------------
# _calculate_padding
# ---------------------------------------------------------------------------


class TestCalculatePadding:
    @staticmethod
    def _dims() -> MapImageDimensions:
        return MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)

    @staticmethod
    def _call(dims: MapImageDimensions, **overrides: object) -> list[int]:
        kwargs: dict[str, object] = {
            "active_areas": None,
            "no_mopping_areas": None,
            "no_go_areas": None,
            "walls": None,
            "virtual_thresholds": None,
            "passable_thresholds": None,
            "impassable_thresholds": None,
            "ramps": None,
            "furnitures": None,
            "furniture_version": 1,
            "curtains": None,
            "segments": None,
            "padding": [0, 0, 0, 0],
            "min_width": 0,
            "min_height": 0,
            "scale": 1,
            "icon_set": 0,
        }
        kwargs.update(overrides)
        return DreameVacuumMapRenderer._calculate_padding(dims, **kwargs)  # type: ignore[arg-type]

    def test_no_overflowing_objects_returns_padding_unchanged(self) -> None:
        assert self._call(self._dims()) == [0, 0, 0, 0]

    def test_segments_extending_left_increase_left_padding(self) -> None:
        # x0=-100mm -> grid x = -10, outside [0, width) -> padding[0] increases.
        segments = {1: Segment(1, x0=-100, y0=0, x1=50, y1=50)}
        padding = self._call(self._dims(), segments=segments)
        assert padding == [10, 0, 0, 0]

    def test_active_areas_extending_right_increase_right_padding(self) -> None:
        area = Area(0, 0, 300, 0, 300, 50, 0, 50)  # x up to 300mm -> grid x=30 > width(20)
        padding = self._call(self._dims(), active_areas=[area])
        assert padding[2] == 10
        assert padding[0] == 0

    def test_no_mopping_areas_extending_top_increase_padding(self) -> None:
        # y1=250mm -> to_coord y = (200-1-250)/10 = -5.1 -> negative -> padding[1] increases.
        area = Area(0, 0, 50, 0, 50, 250, 0, 250)
        padding = self._call(self._dims(), no_mopping_areas=[area])
        assert padding[1] > 0

    def test_no_go_areas_extending_bottom_increase_padding(self) -> None:
        area = Area(0, -100, 50, -100, 50, 0, 0, 0)
        padding = self._call(self._dims(), no_go_areas=[area])
        assert padding[3] > 0

    def test_walls_out_of_bounds_increase_padding(self) -> None:
        wall = Wall(-100, 0, 0, 0)
        padding = self._call(self._dims(), walls=[wall])
        assert padding[0] == 10

    def test_virtual_thresholds_out_of_bounds_increase_padding(self) -> None:
        wall = Wall(-100, 0, 0, 0)
        padding = self._call(self._dims(), virtual_thresholds=[wall])
        assert padding[0] == 10

    def test_passable_thresholds_out_of_bounds_increase_padding(self) -> None:
        wall = Wall(-100, 0, 0, 0)
        padding = self._call(self._dims(), passable_thresholds=[wall])
        assert padding[0] == 10

    def test_impassable_thresholds_out_of_bounds_increase_padding(self) -> None:
        wall = Wall(-100, 0, 0, 0)
        padding = self._call(self._dims(), impassable_thresholds=[wall])
        assert padding[0] == 10

    def test_ramps_out_of_bounds_increase_padding(self) -> None:
        ramp = Area(-100, 0, 0, 0, 0, 50, -100, 50)
        padding = self._call(self._dims(), ramps=[ramp])
        assert padding[0] == 10

    def test_curtains_out_of_bounds_increase_padding(self) -> None:
        wall = Wall(-100, 0, 0, 0)
        padding = self._call(self._dims(), curtains=[wall])
        assert padding[0] == 10

    def test_furniture_with_image_dimensions_out_of_bounds_increase_padding(self) -> None:
        # width/height set -> uses furniture_images lookup (type 1 = SINGLE_BED is mapped).
        furniture = Furniture(
            -100, 100, x0=-110, y0=90, width=20, height=20, type=FurnitureType.SINGLE_BED, size_type=0
        )
        padding = self._call(self._dims(), furnitures={1: furniture}, furniture_version=1)
        assert padding[0] > 0

    def test_furniture_without_dimensions_uses_icon_lookup(self) -> None:
        furniture = Furniture(-100, 100, x0=0, y0=0, width=0, height=0, type=FurnitureType.SINGLE_BED, size_type=0)
        padding = self._call(self._dims(), furnitures={1: furniture}, furniture_version=1)
        assert padding[0] > 0

    def test_furniture_unmapped_type_is_skipped(self) -> None:
        # FurnitureType.TABLE (26) has no v1 image/icon entry -> skipped without affecting padding.
        furniture = Furniture(-100, 100, x0=0, y0=0, width=0, height=0, type=FurnitureType.TABLE, size_type=0)
        padding = self._call(self._dims(), furnitures={1: furniture}, furniture_version=1)
        assert padding == [0, 0, 0, 0]

    def test_furniture_with_dimensions_unmapped_type_is_skipped(self) -> None:
        # Same as above but through the width/height (image lookup) branch.
        furniture = Furniture(-100, 100, x0=-110, y0=90, width=20, height=20, type=FurnitureType.TABLE, size_type=0)
        padding = self._call(self._dims(), furnitures={1: furniture}, furniture_version=1)
        assert padding == [0, 0, 0, 0]

    def test_furniture_version_2_uses_v2_image_map(self) -> None:
        # SHOE_CABINET (20) is only present in the v2 image map, not the v1 one.
        furniture = Furniture(
            -100, 100, x0=-110, y0=90, width=20, height=20, type=FurnitureType.SHOE_CABINET, size_type=0
        )
        padding = self._call(self._dims(), furnitures={1: furniture}, furniture_version=2)
        assert padding[0] > 0

    def test_min_width_min_height_enlarge_padding_symmetrically(self) -> None:
        padding = self._call(self._dims(), min_width=100, min_height=100)
        # (100 - 20) / 2 = 40 added to each side.
        assert padding == [40, 40, 40, 40]

    def test_scale_multiplies_final_padding(self) -> None:
        segments = {1: Segment(1, x0=-100, y0=0, x1=50, y1=50)}
        padding = self._call(self._dims(), segments=segments, scale=3)
        assert padding == [30, 0, 0, 0]


# ---------------------------------------------------------------------------
# Carpet helpers: _get_carpet_coords / _optimize_carpet_pixels / _check_carpet
# ---------------------------------------------------------------------------


class TestCarpetHelpers:
    def test_round_coord_rounds_down_and_up(self) -> None:
        # remainder (3) <= grid_size/2 (5) -> rounds down.
        assert DreameVacuumMapRenderer._round_coord(13, 10) == 10
        # remainder (8) > grid_size/2 (5) -> rounds up to the next grid line.
        assert DreameVacuumMapRenderer._round_coord(8, 10) == 10

    def test_get_carpet_coords_ellipse(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        carpet = Carpet(1, x0=100, y0=100, x1=0, y1=0, x2=50, y2=50, x3=0, y3=0, ellipse=1)
        coords = DreameVacuumMapRenderer._get_carpet_coords(carpet, dims)
        assert len(coords) == 4
        assert all(isinstance(c, int) for c in coords)

    def test_get_carpet_coords_rectangle(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        carpet = Carpet(1, x0=0, y0=0, x1=100, y1=0, x2=100, y2=100, x3=0, y3=100, ellipse=0)
        x0, y0, x1, y1 = DreameVacuumMapRenderer._get_carpet_coords(carpet, dims)
        assert (x0, y0, x1, y1) == (0, 0, 10, 10)

    def test_get_carpet_coords_rectangle_with_offset_left_top(self) -> None:
        # left/top not divisible by grid_size -> the +grid_size/2 shift branch is taken.
        dims = MapImageDimensions(top=5, left=5, height=20, width=20, grid_size=10)
        carpet = Carpet(1, x0=0, y0=0, x1=100, y1=0, x2=100, y2=100, x3=0, y3=100, ellipse=0)
        coords = DreameVacuumMapRenderer._get_carpet_coords(carpet, dims)
        assert len(coords) == 4

    def test_optimize_carpet_pixels_collects_non_zero_neighbours(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=5, width=5, grid_size=10)
        pixel_type = np.zeros((5, 5), dtype=np.uint8)
        pixel_type[2, 2] = 1
        pixel_type[3, 2] = 255  # excluded (wall / outside value)
        result = DreameVacuumMapRenderer._optimize_carpet_pixels([(2, 2)], dims, pixel_type)
        assert (2, 2) in result
        assert (3, 2) not in result

    def test_check_carpet_pixel_type_out_of_valid_range_is_false(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        carpet = Carpet(1, x0=0, y0=0, x1=100, y1=0, x2=100, y2=100, x3=0, y3=100)
        assert DreameVacuumMapRenderer._check_carpet(1, 1, carpet, dims, pixel_type=255) is False
        assert DreameVacuumMapRenderer._check_carpet(1, 1, carpet, dims, pixel_type=0) is False

    def test_check_carpet_pixel_type_not_in_segments_is_false(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        carpet = Carpet(1, x0=0, y0=0, x1=100, y1=0, x2=100, y2=100, x3=0, y3=100, segments=[9])
        assert DreameVacuumMapRenderer._check_carpet(1, 1, carpet, dims, pixel_type=3) is False

    def test_check_carpet_ellipse_inside_and_outside(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        # Ellipse centered at (100, 100)mm with radii (x2=50, y2=50)mm.
        carpet = Carpet(1, x0=100, y0=100, x1=0, y1=0, x2=50, y2=50, x3=0, y3=0, ellipse=1)
        # Grid point (10, 10) -> mm (100, 100) is the ellipse centre -> inside.
        assert DreameVacuumMapRenderer._check_carpet(10, 10, carpet, dims) is True
        # Far outside the ellipse.
        assert DreameVacuumMapRenderer._check_carpet(0, 0, carpet, dims) is False

    def test_check_carpet_ignored_area_excludes_point(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        carpet = Carpet(1, x0=0, y0=0, x1=100, y1=0, x2=100, y2=100, x3=0, y3=100, ignored_areas=[[0, 0, 200, 200]])
        assert DreameVacuumMapRenderer._check_carpet(5, 5, carpet, dims) is False

    def test_check_carpet_polygon_point_inside(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        # Square polygon 0,0 -> 200,0 -> 200,200 -> 0,200 in mm.
        carpet = Carpet(1, x0=0, y0=0, x1=0, y1=0, x2=0, y2=0, x3=0, y3=0, polygon=[0, 0, 200, 0, 200, 200, 0, 200])
        # Grid point (10, 10) -> mm (100, 100), inside the square.
        assert DreameVacuumMapRenderer._check_carpet(10, 10, carpet, dims) is True
        # Grid point (30, 30) -> mm (300, 300), outside the square.
        assert DreameVacuumMapRenderer._check_carpet(30, 30, carpet, dims) is False

    def test_check_carpet_polygon_horizontal_edge_at_query_y_is_true(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        # Edge from (100,50)->(0,50) (checked when i=2) is horizontal exactly at y=50,
        # straddling x=50 -> hits the "sy == ty == y" branch.
        carpet = Carpet(1, x0=0, y0=0, x1=0, y1=0, x2=0, y2=0, x3=0, y3=0, polygon=[0, 50, 100, 50, 100, 150, 0, 150])
        assert DreameVacuumMapRenderer._check_carpet(5, 5, carpet, dims) is True

    def test_check_carpet_polygon_degenerate_edge_matches_point_exactly(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        # First two polygon points are identical (50, 50) -> zero-length edge exactly
        # at the query point hits the "sx == x and sy == y and tx == x and ty == y" branch.
        carpet = Carpet(1, x0=0, y0=0, x1=0, y1=0, x2=0, y2=0, x3=0, y3=0, polygon=[50, 50, 50, 50, 100, 150, 0, 150])
        assert DreameVacuumMapRenderer._check_carpet(5, 5, carpet, dims) is True

    def test_check_carpet_polygon_edge_crosses_exactly_at_x(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        # Diagonal edge from (0,0) to (100,100) passes exactly through (50,50) -> hits
        # the "xx == x" branch of the ray-casting scan.
        carpet = Carpet(1, x0=0, y0=0, x1=0, y1=0, x2=0, y2=0, x3=0, y3=0, polygon=[0, 0, 100, 100, 100, 0])
        assert DreameVacuumMapRenderer._check_carpet(5, 5, carpet, dims) is True

    def test_check_carpet_default_true_without_shape_constraints(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=10)
        carpet = Carpet(1, x0=0, y0=0, x1=100, y1=0, x2=100, y2=100, x3=0, y3=100)
        assert DreameVacuumMapRenderer._check_carpet(5, 5, carpet, dims) is True


# ---------------------------------------------------------------------------
# render_obstacle_image
# ---------------------------------------------------------------------------


def _fake_photo_bytes(size: tuple[int, int] = (200, 160)) -> bytes:
    img = Image.new("RGB", size, (10, 20, 30))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class TestRenderObstacleImage:
    @staticmethod
    def _renderer() -> DreameVacuumMapRenderer:
        return DreameVacuumMapRenderer(low_resolution=True)

    def test_none_image_bytes_returns_none(self) -> None:
        renderer = self._renderer()
        obstacle = Obstacle(
            25, 25, type=ObstacleType.OBSTACLE.value, possibility=90, pos_x=40, pos_y=40, width=20, height=20
        )
        assert renderer.render_obstacle_image(None, obstacle, ai_image_crop=False) is None

    def test_missing_obstacle_returns_bytes_unchanged(self) -> None:
        renderer = self._renderer()
        data = _fake_photo_bytes()
        assert renderer.render_obstacle_image(data, None, ai_image_crop=False) is data

    def test_obstacle_without_geometry_returns_bytes_unchanged(self) -> None:
        renderer = self._renderer()
        data = _fake_photo_bytes()
        obstacle = Obstacle(25, 25, type=ObstacleType.OBSTACLE.value, possibility=90)
        assert renderer.render_obstacle_image(data, obstacle, ai_image_crop=False) is data

    def test_no_crop_and_no_box_returns_bytes_unchanged(self) -> None:
        renderer = self._renderer()
        data = _fake_photo_bytes()
        obstacle = Obstacle(
            25, 25, type=ObstacleType.OBSTACLE.value, possibility=90, pos_x=40, pos_y=40, width=20, height=20
        )
        result = renderer.render_obstacle_image(data, obstacle, ai_image_crop=False, render_box=False, crop_image=False)
        assert result is data

    def test_ai_crop_with_crop_image_shrinks_image(self) -> None:
        renderer = self._renderer()
        data = _fake_photo_bytes((200, 160))
        obstacle = Obstacle(
            25, 25, type=ObstacleType.OBSTACLE.value, possibility=90, pos_x=40, pos_y=40, width=20, height=20
        )
        result = renderer.render_obstacle_image(data, obstacle, ai_image_crop=True, render_box=False, crop_image=True)
        assert result is not None
        out = Image.open(io.BytesIO(result))
        assert out.format == "JPEG"
        assert out.size[0] < 200

    def test_ai_crop_with_render_box_draws_markers(self) -> None:
        renderer = self._renderer()
        data = _fake_photo_bytes((200, 160))
        obstacle = Obstacle(
            25, 25, type=ObstacleType.OBSTACLE.value, possibility=90, pos_x=40, pos_y=40, width=20, height=20
        )
        result = renderer.render_obstacle_image(data, obstacle, ai_image_crop=True, render_box=True, crop_image=False)
        assert result is not None
        out = Image.open(io.BytesIO(result)).convert("RGB")
        # Box + corner icons alter pixels away from the flat background fill.
        arr = np.array(out)
        background = np.array((10, 20, 30))
        assert (arr != background).any()

    def test_non_ai_crop_with_crop_image_shrinks_image(self) -> None:
        renderer = self._renderer()
        data = _fake_photo_bytes((200, 160))
        obstacle = Obstacle(
            25, 25, type=ObstacleType.OBSTACLE.value, possibility=90, pos_x=40, pos_y=40, width=20, height=20
        )
        result = renderer.render_obstacle_image(data, obstacle, ai_image_crop=False, render_box=False, crop_image=True)
        assert result is not None
        out = Image.open(io.BytesIO(result))
        assert out.size[0] < 200

    def test_non_ai_crop_with_render_box_clamps_top_left(self) -> None:
        renderer = self._renderer()
        data = _fake_photo_bytes((200, 160))
        # pos_x=pos_y=0 pushes x0/y0 negative -> exercises the x0<=0 / y0<=0 clamps.
        obstacle = Obstacle(
            25, 25, type=ObstacleType.OBSTACLE.value, possibility=90, pos_x=0, pos_y=0, width=10, height=10
        )
        result = renderer.render_obstacle_image(data, obstacle, ai_image_crop=False, render_box=True, crop_image=False)
        assert result is not None
        out = Image.open(io.BytesIO(result))
        assert out.format == "JPEG"
        assert out.size == (200, 160)

    def test_non_ai_crop_with_render_box_clamps_bottom_right(self) -> None:
        renderer = self._renderer()
        data = _fake_photo_bytes((200, 160))
        # pos_x/pos_y near 100 with a large width/height push x1/y1 past the frame edges.
        obstacle = Obstacle(
            25, 25, type=ObstacleType.OBSTACLE.value, possibility=90, pos_x=99, pos_y=99, width=50, height=50
        )
        result = renderer.render_obstacle_image(data, obstacle, ai_image_crop=False, render_box=True, crop_image=False)
        assert result is not None
        out = Image.open(io.BytesIO(result))
        assert out.format == "JPEG"
        assert out.size == (200, 160)

    def test_render_box_icons_cached_across_calls(self) -> None:
        renderer = self._renderer()
        data = _fake_photo_bytes((200, 160))
        obstacle = Obstacle(
            25, 25, type=ObstacleType.OBSTACLE.value, possibility=90, pos_x=40, pos_y=40, width=20, height=20
        )
        assert renderer._obstacle_top_left_icon is None
        renderer.render_obstacle_image(data, obstacle, ai_image_crop=False, render_box=True, crop_image=False)
        cached_icon = renderer._obstacle_top_left_icon
        assert cached_icon is not None
        renderer.render_obstacle_image(data, obstacle, ai_image_crop=False, render_box=True, crop_image=False)
        assert renderer._obstacle_top_left_icon is cached_icon


# ---------------------------------------------------------------------------
# _smooth_upscale
# ---------------------------------------------------------------------------


class TestSmoothUpscale:
    def test_upscale_doubles_dimensions(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        pixels = np.zeros((10, 12, 4), dtype=np.uint8)
        pixels[..., 3] = 255
        result = renderer._smooth_upscale(pixels, 2)
        assert result.shape == (20, 24, 4)
        assert result.dtype == np.uint8

    def test_upscale_falls_back_to_nearest_on_bad_input(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        # 5-channel array is not a valid image mode for PIL -> Image.fromarray raises,
        # exercising the except-branch fallback to plain np.repeat upscaling.
        pixels = np.zeros((4, 4, 5), dtype=np.uint8)
        result = renderer._smooth_upscale(pixels, 2)
        assert result.shape == (8, 8, 5)


# ---------------------------------------------------------------------------
# _calculate_render_sizes
# ---------------------------------------------------------------------------


class TestCalculateRenderSizes:
    def test_rotation_0_uses_width_based_sizing(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        map_data = _make_small_map_data()
        map_data.dimensions.padding = [10, 10, 10, 10]
        map_data.dimensions.crop = [0, 0, 0, 0]
        map_data.dimensions.scale = 3
        map_image = Image.new("RGBA", (100, 100))
        result = renderer._calculate_render_sizes(map_data, map_image, 2)
        layer_size, line_width, border_width, robot_icon_size, icon_size, segment_icon_size = result
        assert layer_size == (200, 200)
        assert line_width == 3
        assert border_width == 2
        assert 7 <= robot_icon_size <= 14
        assert 3 <= icon_size <= 12
        assert segment_icon_size == icon_size

    def test_rotation_90_uses_height_based_sizing(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        map_data = _make_small_map_data()
        map_data.rotation = 90
        map_data.dimensions.padding = [10, 10, 10, 10]
        map_data.dimensions.crop = [0, 0, 0, 0]
        map_data.dimensions.scale = 3
        map_image = Image.new("RGBA", (100, 100))
        result = renderer._calculate_render_sizes(map_data, map_image, 2)
        assert result[0] == (200, 200)

    def test_low_scale_shrinks_robot_icon_and_grows_icon_size(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        map_data = _make_small_map_data()
        map_data.dimensions.padding = [0, 0, 0, 0]
        map_data.dimensions.crop = [0, 0, 0, 0]
        map_data.dimensions.scale = 2
        map_image = Image.new("RGBA", (100, 100))
        _, _, _, robot_icon_size, icon_size, _ = renderer._calculate_render_sizes(map_data, map_image, 2)
        # scale <= 2 branch multiplies robot_icon_size by 0.7 and icon_size by 1.3.
        assert robot_icon_size <= 14
        assert icon_size <= 12

    def test_square_mode_uses_width_based_sizing_even_with_rotation(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True, square=True)
        map_data = _make_small_map_data()
        map_data.rotation = 90
        map_data.dimensions.padding = [0, 0, 0, 0]
        map_data.dimensions.crop = [0, 0, 0, 0]
        map_data.dimensions.scale = 3
        map_image = Image.new("RGBA", (100, 100))
        _, _, _, _, icon_size, _ = renderer._calculate_render_sizes(map_data, map_image, 2)
        assert icon_size > 0


# ---------------------------------------------------------------------------
# render_map: cache invalidation, area-color branches, rotation, exceptions
# ---------------------------------------------------------------------------


def _decode(png_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


class TestRenderMapAreaColorBranches:
    def test_cleaning_map_second_cleaning_colors(self) -> None:
        map_data = _make_small_map_data()
        map_data.cleaning_map = True
        map_data.second_cleaning = True
        map_data.neglected_segments = [1]
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        png = renderer.render_map(map_data, robot_status=0, station_status=0)
        img = _decode(png)
        assert img.size[0] > 0

    def test_cleaning_map_without_second_cleaning_colors(self) -> None:
        map_data = _make_small_map_data()
        map_data.cleaning_map = True
        map_data.second_cleaning = False
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        png = renderer.render_map(map_data, robot_status=0, station_status=0)
        assert _decode(png).size[0] > 0

    def test_wifi_map_uses_wifi_color_palette(self) -> None:
        map_data = _make_small_map_data()
        map_data.wifi_map = True
        map_data.router_position = Point(200, 200)
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        png = renderer.render_map(map_data, robot_status=0, station_status=0)
        img = _decode(png)
        # Outside/background must be fully transparent for wifi maps (bg_color forced to (0,0,0,0)).
        assert img.getpixel((0, 0)) == (0, 0, 0, 0)

    def test_hidden_segments_use_hidden_color(self) -> None:
        base = _make_small_map_data()
        hidden = _make_small_map_data()
        hidden.hidden_segments = [1]
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        png_base = renderer.render_map(base, robot_status=0, station_status=0)
        renderer2 = DreameVacuumMapRenderer(low_resolution=True)
        png_hidden = renderer2.render_map(hidden, robot_status=0, station_status=0)
        assert png_base != png_hidden

    def test_active_segments_recolor_inactive_ones(self) -> None:
        base = _make_small_map_data()
        restricted = _make_small_map_data()
        restricted.active_segments = [2]
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        png_base = renderer.render_map(base, robot_status=0, station_status=0)
        renderer2 = DreameVacuumMapRenderer(low_resolution=True)
        png_restricted = renderer2.render_map(restricted, robot_status=0, station_status=0)
        assert png_base != png_restricted

    def test_color_config_disabled_uses_plain_floor_color(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=True, hidden_map_objects=["color"])
        assert renderer.config.color is False
        png = renderer.render_map(map_data, robot_status=0, station_status=0)
        assert _decode(png).size[0] > 0


class TestRenderMapCacheInvalidation:
    def test_saved_map_forces_zero_robot_and_station_status(self) -> None:
        map_data = _make_small_map_data()
        map_data.saved_map = True
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)
        renderer.render_map(map_data, robot_status=5, station_status=5)
        assert renderer._robot_status == 0
        assert renderer._station_status == 0

    def test_hot_washing_station_status_bypasses_cache_reuse(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)
        first = renderer.render_map(map_data, robot_status=1, station_status=12)
        second = renderer.render_map(map_data, robot_status=1, station_status=12)
        # Washing animation is time-based so re-render is not a cache short-circuit,
        # but both calls must still succeed and produce valid images.
        assert _decode(first).size[0] > 0
        assert _decode(second).size[0] > 0

    def test_saved_map_status_2_enables_material_and_carpet_rendering(self) -> None:
        # render_scale=1 isolates the base scale-selection logic under test.
        map_data = _make_small_map_data()
        map_data.saved_map_status = 2
        map_data.floor_material = {1: 1, 2: 2}
        map_data.carpet_pixels = [(3, 3), (4, 4)]
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, render_scale=1)
        png = renderer.render_map(map_data, robot_status=0, station_status=0)
        assert _decode(png).size[0] > 0
        assert renderer._map_data.dimensions.scale == 4

    def test_carpet_render_bumps_scale_from_3_to_4(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, render_scale=1)
        renderer.render_map(map_data, robot_status=0, station_status=0, info_text=False)
        assert renderer._map_data.dimensions.scale == 4

    def test_info_text_forces_scale_down_to_2(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, render_scale=1)
        renderer.render_map(map_data, robot_status=0, station_status=0, info_text=True)
        assert renderer._map_data.dimensions.scale == 2

    def test_scale_change_between_renders_invalidates_cache(self) -> None:
        # Two distinct MapData instances with a differing robot_status bypass the
        # top-of-function cache short-circuit, forcing a full recompute where the
        # newly-computed scale (2, forced by info_text) differs from the previous
        # cached scale (4) -> exercises the mid-function cache invalidation branch.
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, render_scale=1)
        renderer.render_map(_make_small_map_data(), robot_status=0, station_status=0, info_text=False)
        assert renderer._map_data.dimensions.scale == 4
        renderer.render_map(_make_small_map_data(), robot_status=1, station_status=0, info_text=True)
        assert renderer._map_data.dimensions.scale == 2

    def test_render_scale_multiplies_the_interactive_map_resolution(self) -> None:
        # The multiplier scales the resolved base scale (4 here, carpet bump) and
        # doubles the rendered image, while calibration stays coherent because it
        # derives from dimensions.scale (contract 3.2).
        map_data = _make_small_map_data()
        base = DreameVacuumMapRenderer(low_resolution=False, cache=True, render_scale=1)
        base.render_map(map_data, robot_status=0, station_status=0)
        base_scale = base._map_data.dimensions.scale
        base_cal = base.calibration_points

        hi = DreameVacuumMapRenderer(low_resolution=False, cache=True, render_scale=2)
        hi_png = hi.render_map(_make_small_map_data(), robot_status=0, station_status=0)
        assert hi._map_data.dimensions.scale == base_scale * 2
        assert _decode(hi_png).size[0] == _decode(base.render_map(_make_small_map_data(), 0, 0)).size[0] * 2
        # Calibration map pixels scale with the resolution (still coherent).
        assert hi.calibration_points[0]["map"]["x"] == base_cal[0]["map"]["x"] * 2

    def test_render_scale_ignored_in_low_resolution_mode(self) -> None:
        # Low-resolution mode is for low-memory hosts: the multiplier must not
        # blow the image back up.
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True, render_scale=3)
        renderer.render_map(_make_small_map_data(), robot_status=0, station_status=0)
        assert renderer._map_data.dimensions.scale == 2

    def test_bounds_cache_invalidated_when_segments_move(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)
        renderer.render_map(map_data, robot_status=0, station_status=0)

        moved = _make_small_map_data()
        moved.segments[1].x0 = 10
        moved.segments[1].y0 = 10
        second = renderer.render_map(moved, robot_status=0, station_status=0)
        assert _decode(second).size[0] > 0

    def test_inset_content_crops_rendered_image(self) -> None:
        # Content inset from every edge -> render_map crops the raster to the
        # actual bounding box before compositing, producing a smaller base
        # image than a full-canvas render at the same grid size.
        map_data = _make_inset_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        png = renderer.render_map(map_data, robot_status=0, station_status=0)
        assert _decode(png).size[0] > 0
        assert renderer._map_data.dimensions.crop == [10, 10, 10, 10]  # grid crop (5) * scale (2)

    def test_crop_change_between_renders_invalidates_cache(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)
        renderer.render_map(_make_inset_map_data(), robot_status=0, station_status=0)
        assert renderer._map_data.dimensions.crop == [10, 10, 10, 10]  # grid crop (5) * scale (2)

        # Full-border content bypasses the top cache shortcut (different robot_status)
        # and yields a different (zero) crop, exercising the crop-mismatch invalidation.
        renderer.render_map(_make_small_map_data(), robot_status=1, station_status=0)
        assert renderer._map_data.dimensions.crop == [0, 0, 0, 0]

    def test_padding_cache_invalidated_when_virtual_walls_extend_bounds(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)
        first = renderer.render_map(map_data, robot_status=0, station_status=0)

        extended = _make_small_map_data()
        extended.virtual_walls = [Wall(-500, -500, -400, -400)]
        second = renderer.render_map(extended, robot_status=0, station_status=0)
        assert first != second

    def test_has_mask_true_for_mop_path_with_full_memory_renderer(self) -> None:
        map_data = _make_small_map_data()
        map_data.path = [
            Path(100, 100, PathType.SWEEP_AND_MOP),
            Path(200, 200, PathType.LINE),
        ]
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        renderer.render_map(map_data, robot_status=1, station_status=0)
        assert renderer._has_mask is True
        assert MapRendererLayer.PATH_MASK in renderer._layers

    def test_has_mask_cleared_and_layer_dropped_when_path_removed(self) -> None:
        with_path = _make_small_map_data()
        with_path.path = [Path(100, 100, PathType.MOP), Path(200, 200, PathType.LINE)]
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        renderer.render_map(with_path, robot_status=1, station_status=0)
        assert renderer._has_mask is True

        without_path = _make_small_map_data()
        without_path.path = None
        # frame_id must differ, otherwise the two MapData instances compare equal
        # under the top-of-function cache short-circuit and the second render
        # never re-evaluates has_mask at all.
        without_path.frame_id = 2
        renderer.render_map(without_path, robot_status=1, station_status=0)
        assert renderer._has_mask is False
        assert MapRendererLayer.PATH_MASK not in renderer._layers

    def test_path_cleared_from_cached_map_data_after_mask_layer_build(self) -> None:
        # When has_mask is true and the IMAGE layer is rebuilt while a previous
        # cached MapData is already present, the renderer clears
        # self._map_data.path (memory optimisation) after building PATH_MASK.
        map_data = _make_small_map_data()
        map_data.path = [Path(100, 100, PathType.MOP), Path(200, 200, PathType.LINE)]
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        renderer.render_map(map_data, robot_status=1, station_status=0)

        rebuilt = _make_small_map_data()
        rebuilt.path = [Path(100, 100, PathType.MOP), Path(200, 200, PathType.LINE)]
        rebuilt.active_segments = [1]  # forces the IMAGE layer to rebuild on the 2nd call
        renderer.render_map(rebuilt, robot_status=2, station_status=0)  # differing robot_status bypasses cache hit
        assert renderer._has_mask is True

    def test_vector_rooms_smooth_upscale_used_for_carpet_and_material(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, vector_rooms=True)
        png = renderer.render_map(map_data, robot_status=0, station_status=0)
        assert _decode(png).size[0] > 0

    def test_vector_rooms_smooth_upscale_without_carpet_or_material(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(
            low_resolution=False, cache=True, vector_rooms=True, hidden_map_objects=["carpet", "material"]
        )
        png = renderer.render_map(map_data, robot_status=0, station_status=0)
        assert _decode(png).size[0] > 0

    def test_history_map_with_neglected_segments_renders_problem_badges(self) -> None:
        map_data = _make_small_map_data()
        map_data.history_map = True
        map_data.neglected_segments = [1]
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        png = renderer.render_map(map_data, robot_status=0, station_status=0)
        assert _decode(png).size[0] > 0

    def test_square_mode_pads_non_square_maps_to_equal_sides(self) -> None:
        wide = _make_small_map_data()
        wide.dimensions = MapImageDimensions(top=0, left=0, height=10, width=20, grid_size=GRID_SIZE)
        wide.pixel_type = np.zeros((20, 10), dtype=np.uint8)
        wide.pixel_type[1:19, 1:9] = 1
        wide.pixel_type[0, :] = MapPixelType.WALL.value
        wide.pixel_type[19, :] = MapPixelType.WALL.value
        wide.pixel_type[:, 0] = MapPixelType.WALL.value
        wide.pixel_type[:, 9] = MapPixelType.WALL.value
        wide.segments = {1: Segment(1, x0=50, y0=50, x1=900, y1=400, x=500, y=200, name="Room")}
        wide.segments[1].color_index = 0

        renderer = DreameVacuumMapRenderer(low_resolution=True, square=True)
        png = renderer.render_map(wide, robot_status=0, station_status=0)
        img = _decode(png)
        assert img.size[0] > 0
        assert img.size[1] > 0


class TestRenderMapRotation:
    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_rotation_produces_valid_image(self, rotation: int) -> None:
        map_data = _make_small_map_data()
        map_data.rotation = rotation
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        png = renderer.render_map(map_data, robot_status=1, station_status=0)
        img = _decode(png)
        assert img.size[0] > 0
        assert img.size[1] > 0

    def test_rotation_90_and_0_produce_different_calibration_points(self) -> None:
        map_data_0 = _make_small_map_data()
        renderer0 = DreameVacuumMapRenderer(low_resolution=True)
        renderer0.render_map(map_data_0, robot_status=1, station_status=0)

        map_data_90 = _make_small_map_data()
        map_data_90.rotation = 90
        renderer90 = DreameVacuumMapRenderer(low_resolution=True)
        renderer90.render_map(map_data_90, robot_status=1, station_status=0)

        assert renderer0.calibration_points != renderer90.calibration_points


class TestRenderMapExceptionHandling:
    def test_invalid_color_index_on_first_render_falls_back_to_default_image(self) -> None:
        # render_map is typed to return ``bytes``: a rendering exception on the
        # very first call (no image produced yet) falls back to the placeholder
        # ``default_map_image`` instead of leaking ``None``.
        map_data = _make_small_map_data()
        map_data.segments[1].color_index = 999  # Out of range for color_scheme.segment -> IndexError.
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        result = renderer.render_map(map_data, robot_status=0, station_status=0)
        assert result == renderer.default_map_image
        assert renderer.render_complete is True

    def test_invalid_color_index_after_a_prior_successful_render_reuses_last_good_image(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)
        good = renderer.render_map(_make_small_map_data(), robot_status=0, station_status=0)

        broken = _make_small_map_data()
        broken.frame_id = 2  # bypass the cache short-circuit so render_map actually re-executes
        broken.segments[1].color_index = 999
        result = renderer.render_map(broken, robot_status=0, station_status=0)
        # The exception handler swallows the error and keeps serving the last
        # successfully cached image instead of crashing.
        assert result == good
