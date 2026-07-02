"""Characterization tests for ``DreameVacuumMapDataJsonRenderer``.

``map_data_json_renderer.py`` serializes a ``MapData`` snapshot into a
Valetudo-style JSON payload that gets embedded as a ``zTXt``/``tEXt`` chunk
in a PNG (via ``PIL.PngImagePlugin.PngInfo.add_text(..., zip=True)``), for
consumption by the Lovelace map card. It is pure PIL/json/zlib logic with
no Home Assistant runtime dependency.

These tests build real ``MapData``/``MapImageDimensions``/``Segment``/etc.
instances (no ``SimpleNamespace``), render them through the actual
renderer, decode the resulting PNG with Pillow, and assert on the decoded
JSON payload with exact values -- coordinates, angles, RLE-compressed
pixel runs and entity points are all computed by the real
``DreameVacuumMapDataJsonRenderer`` static helpers, not re-derived by hand.
"""

from __future__ import annotations

import io
import json

import numpy as np
from PIL import Image
import pytest

from custom_components.dreame_vacuum.dreame.const import (
    MAP_DATA_JSON_CLASS,
    MAP_DATA_JSON_PARAMETER_ACTIVE,
    MAP_DATA_JSON_PARAMETER_ACTIVE_ZONE,
    MAP_DATA_JSON_PARAMETER_AVG,
    MAP_DATA_JSON_PARAMETER_CHARGER_POSITION,
    MAP_DATA_JSON_PARAMETER_CLASS,
    MAP_DATA_JSON_PARAMETER_COMPRESSED_PIXELS,
    MAP_DATA_JSON_PARAMETER_DIMENSIONS,
    MAP_DATA_JSON_PARAMETER_ENTITIES,
    MAP_DATA_JSON_PARAMETER_FLOOR,
    MAP_DATA_JSON_PARAMETER_LAYERS,
    MAP_DATA_JSON_PARAMETER_MAX,
    MAP_DATA_JSON_PARAMETER_META_DATA,
    MAP_DATA_JSON_PARAMETER_MID,
    MAP_DATA_JSON_PARAMETER_MIN,
    MAP_DATA_JSON_PARAMETER_NAME,
    MAP_DATA_JSON_PARAMETER_NO_GO_AREA,
    MAP_DATA_JSON_PARAMETER_NO_MOP_AREA,
    MAP_DATA_JSON_PARAMETER_PATH,
    MAP_DATA_JSON_PARAMETER_PIXEL_COUNT,
    MAP_DATA_JSON_PARAMETER_PIXEL_SIZE,
    MAP_DATA_JSON_PARAMETER_PIXELS,
    MAP_DATA_JSON_PARAMETER_POINTS,
    MAP_DATA_JSON_PARAMETER_ROBOT_POSITION,
    MAP_DATA_JSON_PARAMETER_ROTATION,
    MAP_DATA_JSON_PARAMETER_SEGMENT,
    MAP_DATA_JSON_PARAMETER_SEGMENT_ID,
    MAP_DATA_JSON_PARAMETER_SIZE,
    MAP_DATA_JSON_PARAMETER_TYPE,
    MAP_DATA_JSON_PARAMETER_VERSION,
    MAP_DATA_JSON_PARAMETER_VIRTUAL_WALL,
    MAP_DATA_JSON_PARAMETER_WALL,
    MAP_DATA_JSON_PARAMETER_X,
    MAP_DATA_JSON_PARAMETER_Y,
    MAP_PARAMETER_ANGLE,
)
from custom_components.dreame_vacuum.dreame.map_data_json_renderer import (
    DreameVacuumMapDataJsonRenderer,
)
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    Area,
    MapData,
    MapImageDimensions,
    MapPixelType,
    Path,
    PathType,
    Point,
    Segment,
    Wall,
)


def _decode_payload(png_bytes: bytes) -> dict:
    """Decode the ValetudoMap JSON payload embedded in a rendered PNG."""
    image = Image.open(io.BytesIO(png_bytes))
    image.load()
    assert image.format == "PNG"
    assert MAP_DATA_JSON_CLASS in image.text
    return json.loads(image.text[MAP_DATA_JSON_CLASS])


def _entities_by_type(payload: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for entity in payload[MAP_DATA_JSON_PARAMETER_ENTITIES]:
        grouped.setdefault(entity[MAP_DATA_JSON_PARAMETER_TYPE], []).append(entity)
    return grouped


def _layers_by_type(payload: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for layer in payload[MAP_DATA_JSON_PARAMETER_LAYERS]:
        grouped.setdefault(layer[MAP_DATA_JSON_PARAMETER_TYPE], []).append(layer)
    return grouped


def _build_grid_map_data() -> MapData:
    """4x4 grid: wall border, two 1-pixel segments, a 2-pixel floor patch."""
    md = MapData()
    md.empty_map = False
    md.frame_id = 1
    md.map_id = 1
    md.saved_map_status = None
    md.rotation = 0
    md.dimensions = MapImageDimensions(top=0, left=0, height=4, width=4, grid_size=10)

    pixel_type = np.full((4, 4), MapPixelType.WALL.value, dtype=np.uint8)
    pixel_type[1, 1] = 1  # segment 1
    pixel_type[2, 1] = 2  # segment 2
    pixel_type[1, 2] = MapPixelType.FLOOR.value
    pixel_type[2, 2] = MapPixelType.UNKNOWN.value
    md.pixel_type = pixel_type
    md.data = b"somedata"

    md.segments = {
        1: Segment(1, x0=-10, y0=-10, x1=10, y1=10, custom_name="Living Room"),
        2: Segment(2, x0=10, y0=10, x1=30, y1=30, custom_name="Kitchen"),
    }
    md.active_segments = None
    md.active_areas = None
    md.active_points = None

    md.robot_position = Point(0, 0, 0)
    md.charger_position = Point(100, 100, 90)
    md.no_mopping_areas = [Area(-100, -100, 100, -100, 100, 100, -100, 100)]
    md.no_go_areas = [Area(-200, -200, 200, -200, 200, 200, -200, 200)]
    md.virtual_walls = [Wall(-50, -50, 50, 50)]
    md.path = [
        Path(0, 0, PathType.LINE),
        Path(10, 10, PathType.LINE),
        Path(20, 20, PathType.SWEEP),
        Path(30, 30, PathType.LINE),
    ]
    return md


# --------------------------------------------------------------------------- #
# Static helpers
# --------------------------------------------------------------------------- #


class TestConvertCoordinates:
    @pytest.mark.parametrize(
        ("x", "y", "expected"),
        [
            (0, 0, [3277, 3277]),
            (100, 200, [3287, 3257]),
            (-32768, -32768, [0, 6554]),
            (32767, 32767, [6554, 0]),
            (5, 5, [3277, 3277]),
        ],
    )
    def test_convert_coordinates(self, x: float, y: float, expected: list[int]) -> None:
        assert DreameVacuumMapDataJsonRenderer._convert_coordinates(x, y) == expected


class TestConvertAngle:
    @pytest.mark.parametrize(
        ("angle", "expected"),
        [
            (0, 90),
            (90, 0),
            (180, 270),
            (270, 180),
            (359, 91),
            (1, 89),
            (179, 271),
            (181, 269),
        ],
    )
    def test_convert_angle(self, angle: int, expected: int) -> None:
        assert DreameVacuumMapDataJsonRenderer._convert_angle(angle) == expected


class TestCoordinateTupleSort:
    def test_b_has_greater_y_returns_negative_one(self) -> None:
        assert DreameVacuumMapDataJsonRenderer._coordinate_tuple_sort([0, 0], [0, 1]) == -1

    def test_equal_y_b_has_greater_x_returns_one(self) -> None:
        assert DreameVacuumMapDataJsonRenderer._coordinate_tuple_sort([0, 0], [1, 0]) == 1

    def test_identical_points_returns_zero(self) -> None:
        assert DreameVacuumMapDataJsonRenderer._coordinate_tuple_sort([0, 0], [0, 0]) == 0

    def test_b_has_greater_y_even_when_a_has_greater_x(self) -> None:
        assert DreameVacuumMapDataJsonRenderer._coordinate_tuple_sort([5, 5], [1, 9]) == -1


class TestToBuffer:
    def test_round_trips_text_chunk(self) -> None:
        image = Image.new("RGBA", (2, 2))
        data = DreameVacuumMapDataJsonRenderer._to_buffer(image, '{"a":1}')

        decoded = Image.open(io.BytesIO(data))
        decoded.load()

        assert decoded.format == "PNG"
        assert decoded.size == (2, 2)
        assert decoded.text[MAP_DATA_JSON_CLASS] == '{"a":1}'


# --------------------------------------------------------------------------- #
# default_map_image / disconnected_map_image
# --------------------------------------------------------------------------- #


class TestDefaultMapImage:
    def test_default_map_image_is_valid_png_with_payload(self) -> None:
        renderer = DreameVacuumMapDataJsonRenderer()
        payload = _decode_payload(renderer.default_map_image)

        assert payload[MAP_DATA_JSON_PARAMETER_CLASS] == MAP_DATA_JSON_CLASS
        assert set(payload.keys()) == {
            MAP_DATA_JSON_PARAMETER_CLASS,
            MAP_DATA_JSON_PARAMETER_SIZE,
            MAP_DATA_JSON_PARAMETER_PIXEL_SIZE,
            MAP_DATA_JSON_PARAMETER_LAYERS,
            MAP_DATA_JSON_PARAMETER_ENTITIES,
            MAP_DATA_JSON_PARAMETER_META_DATA,
        }

    def test_disconnected_map_image_equals_default_map_image(self) -> None:
        renderer = DreameVacuumMapDataJsonRenderer()
        assert renderer.disconnected_map_image == renderer.default_map_image

    def test_default_map_image_deterministic_bytes(self) -> None:
        renderer = DreameVacuumMapDataJsonRenderer()
        assert renderer.default_map_image == renderer.default_map_image


class TestRenderMapEmptyOrMissing:
    def test_render_map_none_returns_default_image(self) -> None:
        renderer = DreameVacuumMapDataJsonRenderer()
        assert renderer.render_map(None) == renderer.default_map_image

    def test_render_map_empty_map_returns_default_image(self) -> None:
        renderer = DreameVacuumMapDataJsonRenderer()
        md = MapData()
        md.empty_map = True
        assert renderer.render_map(md) == renderer.default_map_image


# --------------------------------------------------------------------------- #
# Regression test: KeyError fix (commit a7e0940)
# --------------------------------------------------------------------------- #


class TestKeyErrorRegression:
    def test_render_map_first_frame_without_dimensions_does_not_raise_keyerror(self) -> None:
        """First-ever render on a fresh renderer with dimensions=None must not KeyError.

        Before the fix, line 604 did ``self._layers[MapRendererLayer.IMAGE]``
        (a bare dict subscript). On the very first frame, if
        ``map_data.dimensions`` is falsy the pixel-walk block that
        populates that key never runs, so ``self._layers`` stays ``{}``
        and the subscript raised ``KeyError``. It is now
        ``self._layers.get(MapRendererLayer.IMAGE)``.
        """
        renderer = DreameVacuumMapDataJsonRenderer()
        md = MapData()
        md.empty_map = False
        md.frame_id = 1
        md.map_id = 1
        md.rotation = 0
        md.dimensions = None

        png_bytes = renderer.render_map(md)  # must not raise KeyError

        payload = _decode_payload(png_bytes)
        assert payload[MAP_DATA_JSON_PARAMETER_LAYERS] == []


# --------------------------------------------------------------------------- #
# Full render_map scenario
# --------------------------------------------------------------------------- #


class TestRenderMapFullScenario:
    def test_render_map_full_grid_payload(self) -> None:
        renderer = DreameVacuumMapDataJsonRenderer()
        md = _build_grid_map_data()

        png_bytes = renderer.render_map(md, robot_status=1, station_status=0)
        payload = _decode_payload(png_bytes)

        assert payload[MAP_DATA_JSON_PARAMETER_CLASS] == MAP_DATA_JSON_CLASS
        assert payload[MAP_DATA_JSON_PARAMETER_SIZE] == {
            MAP_DATA_JSON_PARAMETER_X: 6554,
            MAP_DATA_JSON_PARAMETER_Y: 6554,
        }
        assert payload[MAP_DATA_JSON_PARAMETER_PIXEL_SIZE] == 1
        assert payload[MAP_DATA_JSON_PARAMETER_META_DATA] == {
            MAP_DATA_JSON_PARAMETER_VERSION: 2,
            MAP_DATA_JSON_PARAMETER_ROTATION: 0,
        }

        entities = _entities_by_type(payload)

        robot = entities[MAP_DATA_JSON_PARAMETER_ROBOT_POSITION]
        assert len(robot) == 1
        assert robot[0][MAP_DATA_JSON_PARAMETER_POINTS] == [3277, 3277]
        assert robot[0][MAP_DATA_JSON_PARAMETER_META_DATA] == {MAP_PARAMETER_ANGLE: 90}

        charger = entities[MAP_DATA_JSON_PARAMETER_CHARGER_POSITION]
        assert len(charger) == 1
        assert charger[0][MAP_DATA_JSON_PARAMETER_POINTS] == [3287, 3267]
        assert charger[0][MAP_DATA_JSON_PARAMETER_META_DATA] == {MAP_PARAMETER_ANGLE: 0}

        no_mop = entities[MAP_DATA_JSON_PARAMETER_NO_MOP_AREA]
        assert len(no_mop) == 1
        assert no_mop[0][MAP_DATA_JSON_PARAMETER_POINTS] == [3267, 3287, 3287, 3287, 3287, 3267, 3267, 3267]

        no_go = entities[MAP_DATA_JSON_PARAMETER_NO_GO_AREA]
        assert len(no_go) == 1
        assert no_go[0][MAP_DATA_JSON_PARAMETER_POINTS] == [3257, 3297, 3297, 3297, 3297, 3257, 3257, 3257]

        wall_entity = entities[MAP_DATA_JSON_PARAMETER_VIRTUAL_WALL]
        assert len(wall_entity) == 1
        assert wall_entity[0][MAP_DATA_JSON_PARAMETER_POINTS] == [3272, 3282, 3282, 3272]

        paths = entities[MAP_DATA_JSON_PARAMETER_PATH]
        assert len(paths) == 2
        # First LINE run (0,0)->(10,10) got flushed when the SWEEP point was hit.
        assert paths[0][MAP_DATA_JSON_PARAMETER_POINTS] == [3277, 3277, 3278, 3276]
        # Second (final) run (20,20)->(30,30), flushed unconditionally after the loop.
        assert paths[1][MAP_DATA_JSON_PARAMETER_POINTS] == [3279, 3275, 3280, 3274]

        layers = _layers_by_type(payload)
        assert set(layers.keys()) == {
            MAP_DATA_JSON_PARAMETER_FLOOR,
            MAP_DATA_JSON_PARAMETER_WALL,
            MAP_DATA_JSON_PARAMETER_SEGMENT,
        }

        floor = layers[MAP_DATA_JSON_PARAMETER_FLOOR][0]
        assert floor[MAP_DATA_JSON_PARAMETER_PIXELS] == []
        assert floor[MAP_DATA_JSON_PARAMETER_COMPRESSED_PIXELS] == [3278, 3275, 2]
        assert floor[MAP_DATA_JSON_PARAMETER_DIMENSIONS] == {
            MAP_DATA_JSON_PARAMETER_X: {
                MAP_DATA_JSON_PARAMETER_MIN: 3278,
                MAP_DATA_JSON_PARAMETER_MAX: 3279,
                MAP_DATA_JSON_PARAMETER_MID: 3278,
                MAP_DATA_JSON_PARAMETER_AVG: 3278,
            },
            MAP_DATA_JSON_PARAMETER_Y: {
                MAP_DATA_JSON_PARAMETER_MIN: 3275,
                MAP_DATA_JSON_PARAMETER_MAX: 3275,
                MAP_DATA_JSON_PARAMETER_MID: 3275,
                MAP_DATA_JSON_PARAMETER_AVG: 3275,
            },
            MAP_DATA_JSON_PARAMETER_PIXEL_COUNT: 2.0,
        }

        wall_layer = layers[MAP_DATA_JSON_PARAMETER_WALL][0]
        assert wall_layer[MAP_DATA_JSON_PARAMETER_PIXELS] == []
        assert wall_layer[MAP_DATA_JSON_PARAMETER_COMPRESSED_PIXELS] == [
            3277,
            3274,
            4,
            3277,
            3275,
            1,
            3280,
            3275,
            1,
            3277,
            3276,
            1,
            3280,
            3276,
            1,
            3277,
            3277,
            4,
        ]
        assert wall_layer[MAP_DATA_JSON_PARAMETER_DIMENSIONS] == {
            MAP_DATA_JSON_PARAMETER_X: {
                MAP_DATA_JSON_PARAMETER_MIN: 3277,
                MAP_DATA_JSON_PARAMETER_MAX: 3280,
                MAP_DATA_JSON_PARAMETER_MID: 3278,
                MAP_DATA_JSON_PARAMETER_AVG: 3278,
            },
            MAP_DATA_JSON_PARAMETER_Y: {
                MAP_DATA_JSON_PARAMETER_MIN: 3274,
                MAP_DATA_JSON_PARAMETER_MAX: 3277,
                MAP_DATA_JSON_PARAMETER_MID: 3276,
                MAP_DATA_JSON_PARAMETER_AVG: 3276,
            },
            MAP_DATA_JSON_PARAMETER_PIXEL_COUNT: 12.0,
        }

        segments_by_id = {
            layer[MAP_DATA_JSON_PARAMETER_META_DATA][MAP_DATA_JSON_PARAMETER_SEGMENT_ID]: layer
            for layer in layers[MAP_DATA_JSON_PARAMETER_SEGMENT]
        }
        assert set(segments_by_id.keys()) == {1, 2}

        seg1 = segments_by_id[1]
        assert seg1[MAP_DATA_JSON_PARAMETER_COMPRESSED_PIXELS] == [3278, 3276, 1]
        assert seg1[MAP_DATA_JSON_PARAMETER_META_DATA] == {
            MAP_DATA_JSON_PARAMETER_SEGMENT_ID: 1,
            MAP_DATA_JSON_PARAMETER_ACTIVE: False,
            MAP_DATA_JSON_PARAMETER_NAME: "Living Room",
        }
        assert seg1[MAP_DATA_JSON_PARAMETER_DIMENSIONS] == {
            MAP_DATA_JSON_PARAMETER_X: {
                MAP_DATA_JSON_PARAMETER_MIN: 3278,
                MAP_DATA_JSON_PARAMETER_MAX: 3278,
                MAP_DATA_JSON_PARAMETER_MID: 3278,
                MAP_DATA_JSON_PARAMETER_AVG: 3278,
            },
            MAP_DATA_JSON_PARAMETER_Y: {
                MAP_DATA_JSON_PARAMETER_MIN: 3276,
                MAP_DATA_JSON_PARAMETER_MAX: 3276,
                MAP_DATA_JSON_PARAMETER_MID: 3276,
                MAP_DATA_JSON_PARAMETER_AVG: 3276,
            },
            MAP_DATA_JSON_PARAMETER_PIXEL_COUNT: 1.0,
        }

        seg2 = segments_by_id[2]
        assert seg2[MAP_DATA_JSON_PARAMETER_COMPRESSED_PIXELS] == [3279, 3276, 1]
        assert seg2[MAP_DATA_JSON_PARAMETER_META_DATA] == {
            MAP_DATA_JSON_PARAMETER_SEGMENT_ID: 2,
            MAP_DATA_JSON_PARAMETER_ACTIVE: False,
            MAP_DATA_JSON_PARAMETER_NAME: "Kitchen",
        }


# --------------------------------------------------------------------------- #
# Active areas / active points
# --------------------------------------------------------------------------- #


class TestActiveAreasAndPoints:
    def test_active_areas_and_active_points_entities(self) -> None:
        renderer = DreameVacuumMapDataJsonRenderer()
        md = MapData()
        md.empty_map = False
        md.frame_id = 1
        md.map_id = 1
        md.rotation = 0
        md.dimensions = MapImageDimensions(top=0, left=0, height=4, width=4, grid_size=10)
        md.pixel_type = np.full((4, 4), MapPixelType.WALL.value, dtype=np.uint8)
        md.data = b"x"
        md.segments = None
        md.active_segments = None
        md.active_areas = [Area(-5, -5, 5, -5, 5, 5, -5, 5)]
        md.active_points = [Point(1000, 1000)]
        md.robot_position = None
        md.charger_position = None
        md.no_mopping_areas = None
        md.no_go_areas = None
        md.virtual_walls = None
        md.path = None

        payload = _decode_payload(renderer.render_map(md))
        active_zone_entities = _entities_by_type(payload)[MAP_DATA_JSON_PARAMETER_ACTIVE_ZONE]

        assert len(active_zone_entities) == 2
        # active_areas: Area(-5,-5,5,-5,5,5,-5,5) corners converted directly.
        assert active_zone_entities[0][MAP_DATA_JSON_PARAMETER_POINTS] == [
            3276,
            3278,
            3277,
            3278,
            3277,
            3277,
            3276,
            3277,
        ]
        # active_points: Point(1000, 1000) expanded to a square of
        # half-size 15*grid_size (15*10=150) then converted.
        assert active_zone_entities[1][MAP_DATA_JSON_PARAMETER_POINTS] == [
            3362,
            3192,
            3392,
            3192,
            3392,
            3162,
            3362,
            3162,
        ]


# --------------------------------------------------------------------------- #
# Segment/floor folding based on active_segments and falsy map_data.segments
# --------------------------------------------------------------------------- #


class TestActiveSegmentFolding:
    def test_segment_not_in_active_segments_folds_into_floor(self) -> None:
        renderer = DreameVacuumMapDataJsonRenderer()
        md = MapData()
        md.empty_map = False
        md.frame_id = 1
        md.map_id = 1
        md.rotation = 0
        md.dimensions = MapImageDimensions(top=0, left=0, height=1, width=2, grid_size=10)
        pixel_type = np.zeros((2, 1), dtype=np.uint8)
        pixel_type[0, 0] = 5
        pixel_type[1, 0] = MapPixelType.FLOOR.value
        md.pixel_type = pixel_type
        md.data = b"x"
        md.segments = None
        md.active_segments = [7]  # segment id 5 is NOT active -> folded into floor

        payload = _decode_payload(renderer.render_map(md))
        layers = payload[MAP_DATA_JSON_PARAMETER_LAYERS]

        assert len(layers) == 1
        assert layers[0][MAP_DATA_JSON_PARAMETER_TYPE] == MAP_DATA_JSON_PARAMETER_FLOOR
        assert layers[0][MAP_DATA_JSON_PARAMETER_COMPRESSED_PIXELS] == [3277, 3277, 2]
        assert layers[0][MAP_DATA_JSON_PARAMETER_DIMENSIONS][MAP_DATA_JSON_PARAMETER_PIXEL_COUNT] == 2.0

    def test_segments_falsy_forces_segment_id_to_one_and_merges(self) -> None:
        renderer = DreameVacuumMapDataJsonRenderer()
        md = MapData()
        md.empty_map = False
        md.frame_id = 1
        md.map_id = 1
        md.rotation = 0
        md.dimensions = MapImageDimensions(top=0, left=0, height=1, width=2, grid_size=10)
        pixel_type = np.zeros((2, 1), dtype=np.uint8)
        pixel_type[0, 0] = 5
        pixel_type[1, 0] = 9
        md.pixel_type = pixel_type
        md.data = b"x"
        md.segments = None  # falsy -> every segment pixel forced to segment_id 1
        md.active_segments = None

        payload = _decode_payload(renderer.render_map(md))
        layers = payload[MAP_DATA_JSON_PARAMETER_LAYERS]

        assert len(layers) == 1
        layer = layers[0]
        assert layer[MAP_DATA_JSON_PARAMETER_TYPE] == MAP_DATA_JSON_PARAMETER_SEGMENT
        assert layer[MAP_DATA_JSON_PARAMETER_META_DATA][MAP_DATA_JSON_PARAMETER_SEGMENT_ID] == 1
        assert layer[MAP_DATA_JSON_PARAMETER_META_DATA][MAP_DATA_JSON_PARAMETER_NAME] is None
        assert layer[MAP_DATA_JSON_PARAMETER_COMPRESSED_PIXELS] == [3277, 3277, 2]
        assert layer[MAP_DATA_JSON_PARAMETER_DIMENSIONS][MAP_DATA_JSON_PARAMETER_PIXEL_COUNT] == 2.0


# --------------------------------------------------------------------------- #
# Path LINE-run merging vs non-LINE flushing
# --------------------------------------------------------------------------- #


class TestPathMerging:
    def test_line_run_merges_and_non_line_flushes(self) -> None:
        renderer = DreameVacuumMapDataJsonRenderer()
        md = MapData()
        md.empty_map = False
        md.frame_id = 1
        md.map_id = 1
        md.rotation = 0
        md.dimensions = None
        md.segments = None
        md.active_segments = None
        md.active_areas = None
        md.active_points = None
        md.robot_position = None
        md.charger_position = None
        md.no_mopping_areas = None
        md.no_go_areas = None
        md.virtual_walls = None
        md.path = [
            Path(0, 0, PathType.LINE),
            Path(50, 50, PathType.SWEEP),
            Path(100, 100, PathType.SWEEP),
            Path(300, 300, PathType.LINE),
        ]

        payload = _decode_payload(renderer.render_map(md))
        paths = _entities_by_type(payload)[MAP_DATA_JSON_PARAMETER_PATH]

        # Two consecutive SWEEP points each flush an (empty) run, then the
        # trailing LINE run (100,100)->(300,300) is flushed unconditionally.
        assert len(paths) == 3
        assert paths[0][MAP_DATA_JSON_PARAMETER_POINTS] == []
        assert paths[1][MAP_DATA_JSON_PARAMETER_POINTS] == []
        assert paths[2][MAP_DATA_JSON_PARAMETER_POINTS] == [3287, 3267, 3307, 3247]


# --------------------------------------------------------------------------- #
# Cache-reuse behaviour
# --------------------------------------------------------------------------- #


class TestRenderMapCaching:
    def test_unchanged_map_data_reuses_cached_payload(self) -> None:
        renderer = DreameVacuumMapDataJsonRenderer()
        md = _build_grid_map_data()

        first = renderer.render_map(md)
        second = renderer.render_map(md)

        payload_first = _decode_payload(first)
        payload_second = _decode_payload(second)
        assert payload_first == payload_second
        # PNG encoding of the same image + same text chunk is deterministic here.
        assert first == second

    def test_changed_robot_position_produces_new_entity(self) -> None:
        renderer = DreameVacuumMapDataJsonRenderer()
        md = _build_grid_map_data()
        first_payload = _decode_payload(renderer.render_map(md))

        md2 = _build_grid_map_data()
        md2.frame_id = 2
        md2.robot_position = Point(500, 500, 0)

        second_payload = _decode_payload(renderer.render_map(md2))

        first_robot = _entities_by_type(first_payload)[MAP_DATA_JSON_PARAMETER_ROBOT_POSITION][0]
        second_robot = _entities_by_type(second_payload)[MAP_DATA_JSON_PARAMETER_ROBOT_POSITION][0]

        assert first_robot[MAP_DATA_JSON_PARAMETER_POINTS] == [3277, 3277]
        assert second_robot[MAP_DATA_JSON_PARAMETER_POINTS] == [3327, 3227]
        assert first_robot != second_robot
