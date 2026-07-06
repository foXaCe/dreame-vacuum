"""Behavioural tests for the ``_LayersMixin`` (``_layers.py``).

Exercises ``render_objects`` (the per-layer orchestration used by
``render_map``), ``render_path``, ``_resolve_badge_overlaps`` and
``_resolve_name_overlaps`` directly, reusing the small 20x20 map fixture from
``tests/test_map_renderer.py``. Assertions target verifiable structural
properties (which ``MapRendererLayer`` keys got populated/removed from the
cache dict, image size/mode, before/after differences) rather than exact
pixel snapshots.
"""

from __future__ import annotations

import numpy as np
from PIL import Image
import pytest

from custom_components.dreame_vacuum.dreame.map_renderer._core import DreameVacuumMapRenderer
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    Area,
    Coordinate,
    Furniture,
    FurnitureType,
    MapImageDimensions,
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
from tests.test_map_renderer import _make_small_map_data


def _populate_all_optional_layers(map_data) -> None:
    """Attach one instance of every optional map-object collection.

    Coordinates stay within the fixture's 1000x1000mm grid (20 cells * 50 grid_size).
    """
    map_data.no_mopping_areas = [Area(600, 600, 600, 700, 700, 700, 700, 600)]
    map_data.no_go_areas = [Area(600, 100, 600, 200, 700, 200, 700, 100)]
    map_data.virtual_walls = [Wall(100, 600, 200, 600)]
    map_data.virtual_thresholds = [Wall(100, 650, 200, 650)]
    map_data.passable_thresholds = [Wall(100, 700, 200, 700)]
    map_data.impassable_thresholds = [Wall(100, 750, 200, 750)]
    map_data.ramps = [Area(300, 600, 300, 650, 350, 650, 350, 600)]
    map_data.curtains = [Wall(400, 600, 500, 600)]
    map_data.door_lines = [Wall(100, 800, 200, 800)]
    map_data.low_lying_areas = [
        Polygon(1, 100, 100, 100, 150, 150, 150, 150, 100, polygon=[100, 100, 150, 100, 150, 150, 100, 150])
    ]
    map_data.furnitures = {
        1: Furniture(300, 300, x0=280, y0=280, width=40, height=40, type=FurnitureType.SINGLE_BED, size_type=0)
    }
    map_data.furniture_version = 1
    map_data.active_areas = [Area(50, 50, 50, 100, 100, 100, 100, 50)]
    map_data.active_points = [Point(80, 80)]
    map_data.obstacles = {
        "1": Obstacle(150, 150, type=ObstacleType.OBSTACLE.value, possibility=90),
    }
    map_data.active_cruise_points = {1: Coordinate(200, 200, completed=False, type=0)}
    map_data.router_position = Point(400, 400)
    map_data.docked = True


class TestRenderObjectsAllLayersEnabled:
    @staticmethod
    def _renderer() -> DreameVacuumMapRenderer:
        return DreameVacuumMapRenderer(low_resolution=False, cache=True)

    def test_all_optional_layers_populate_cached_layers(self) -> None:
        map_data = _make_small_map_data()
        _populate_all_optional_layers(map_data)
        map_data.wifi_map = False  # router layer still requires wifi_map=True to render; verified separately below.
        renderer = self._renderer()
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        result = renderer.render_objects(cached_layers, map_data, 1, 1, map_image, 2)

        assert isinstance(result, Image.Image)
        for layer in (
            MapRendererLayer.NO_MOP,
            MapRendererLayer.NO_GO,
            MapRendererLayer.WALL,
            MapRendererLayer.DOOR,
            MapRendererLayer.VIRTUAL_THRESHOLD,
            MapRendererLayer.PASSABLE_THRESHOLD,
            MapRendererLayer.IMPASSABLE_THRESHOLD,
            MapRendererLayer.RAMP,
            MapRendererLayer.CURTAIN,
            MapRendererLayer.LOW_LYING_AREA,
            MapRendererLayer.FURNITURES,
            MapRendererLayer.ACTIVE_AREA,
            MapRendererLayer.ACTIVE_POINT,
            MapRendererLayer.SEGMENTS,
            MapRendererLayer.CHARGER,
            MapRendererLayer.ROBOT,
            MapRendererLayer.OBSTACLES,
            MapRendererLayer.CRUISE_POINTS,
            MapRendererLayer.OBJECTS,
        ):
            assert layer in cached_layers, f"{layer.name} missing from cached_layers"

    def test_router_layer_requires_wifi_map(self) -> None:
        map_data = _make_small_map_data()
        map_data.router_position = Point(400, 400)
        map_data.wifi_map = True
        renderer = self._renderer()
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 0, 0, map_image, 2)
        assert MapRendererLayer.ROUTER in cached_layers

    def test_no_mop_layer_skipped_when_robot_status_at_or_above_100(self) -> None:
        map_data = _make_small_map_data()
        map_data.no_mopping_areas = [Area(600, 600, 600, 700, 700, 700, 700, 600)]
        renderer = self._renderer()
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 100, 0, map_image, 2)
        assert MapRendererLayer.NO_MOP not in cached_layers

    def test_obstacles_skip_pet_type_when_pet_config_disabled(self) -> None:
        map_data = _make_small_map_data()
        map_data.obstacles = {"1": Obstacle(150, 150, type=ObstacleType.PET.value, possibility=90)}
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, hidden_map_objects=["pet"])
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 0, 0, map_image, 2)
        # No non-pet/non-stain obstacle qualifies, and pet is disabled -> nothing rendered.
        assert MapRendererLayer.OBSTACLES not in cached_layers

    def test_stain_config_disabled_skips_stains_and_keeps_regular_obstacles(self) -> None:
        # Disabling stain rendering hides stain-type obstacles only; regular
        # obstacles (governed by config.obstacle, enabled here) keep rendering.
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, hidden_map_objects=["stain"])
        regular = _make_small_map_data()
        regular.obstacles = {"1": Obstacle(150, 150, type=ObstacleType.OBSTACLE.value, possibility=90)}
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, regular, 0, 0, map_image, 2)
        assert MapRendererLayer.OBSTACLES in cached_layers

        renderer2 = DreameVacuumMapRenderer(low_resolution=False, cache=True, hidden_map_objects=["stain"])
        stain = _make_small_map_data()
        stain.obstacles = {"1": Obstacle(150, 150, type=ObstacleType.LIQUID_STAIN.value, possibility=90)}
        cached_layers2: dict = {}
        renderer2.render_objects(cached_layers2, stain, 0, 0, map_image, 2)
        assert MapRendererLayer.OBSTACLES not in cached_layers2

    def test_obstacle_config_disabled_skips_regular_type(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, hidden_map_objects=["obstacle"])
        map_data = _make_small_map_data()
        map_data.obstacles = {"1": Obstacle(150, 150, type=ObstacleType.OBSTACLE.value, possibility=90)}
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 0, 0, map_image, 2)
        assert MapRendererLayer.OBSTACLES not in cached_layers

    def test_furniture_layer_disabled_via_config(self) -> None:
        map_data = _make_small_map_data()
        map_data.furnitures = {
            1: Furniture(300, 300, x0=280, y0=280, width=40, height=40, type=FurnitureType.SINGLE_BED, size_type=0)
        }
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, hidden_map_objects=["furniture"])
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 0, 0, map_image, 2)
        assert MapRendererLayer.FURNITURES not in cached_layers


class TestRenderObjectsLayerDeletion:
    """Two-pass scenario: populate every optional layer, then clear the data.

    The renderer must be cache-enabled and reuse the same ``cached_layers``
    dict so the ``elif self._cache and cached_layers.get(layer): _del_layer``
    branches fire on the second pass.
    """

    @staticmethod
    def _renderer() -> DreameVacuumMapRenderer:
        return DreameVacuumMapRenderer(low_resolution=False, cache=True)

    def test_layers_removed_once_their_source_data_is_cleared(self) -> None:
        renderer = self._renderer()
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}

        populated = _make_small_map_data()
        _populate_all_optional_layers(populated)
        renderer._map_data = populated
        renderer.render_objects(cached_layers, populated, 1, 1, map_image, 2)
        assert MapRendererLayer.NO_MOP in cached_layers
        assert MapRendererLayer.FURNITURES in cached_layers
        assert MapRendererLayer.OBSTACLES in cached_layers
        assert MapRendererLayer.CRUISE_POINTS in cached_layers

        cleared = _make_small_map_data()
        cleared.docked = False
        renderer._map_data = populated
        renderer.render_objects(cached_layers, cleared, 1, 1, map_image, 2)

        for layer in (
            MapRendererLayer.NO_MOP,
            MapRendererLayer.NO_GO,
            MapRendererLayer.WALL,
            MapRendererLayer.DOOR,
            MapRendererLayer.VIRTUAL_THRESHOLD,
            MapRendererLayer.PASSABLE_THRESHOLD,
            MapRendererLayer.IMPASSABLE_THRESHOLD,
            MapRendererLayer.RAMP,
            MapRendererLayer.CURTAIN,
            MapRendererLayer.LOW_LYING_AREA,
            MapRendererLayer.FURNITURES,
            MapRendererLayer.ACTIVE_AREA,
            MapRendererLayer.ACTIVE_POINT,
            MapRendererLayer.OBSTACLES,
            MapRendererLayer.CRUISE_POINTS,
        ):
            assert layer not in cached_layers, f"{layer.name} should have been removed"


class TestDoorLinesLayer:
    """``MapRendererLayer.DOOR`` (walls_info door_lines, rendered independently
    of any wall_lines pixel replacement -- see docs/dev/wall-lines-render-spike.md).
    """

    @staticmethod
    def _renderer(**kwargs: object) -> DreameVacuumMapRenderer:
        return DreameVacuumMapRenderer(low_resolution=False, cache=True, **kwargs)

    def test_door_layer_present_when_door_lines_populated(self) -> None:
        map_data = _make_small_map_data()
        map_data.door_lines = [Wall(100, 800, 200, 800)]
        renderer = self._renderer()
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 1, 1, map_image, 2)
        assert MapRendererLayer.DOOR in cached_layers

    def test_door_layer_absent_when_door_lines_empty(self) -> None:
        map_data = _make_small_map_data()
        map_data.door_lines = None
        renderer = self._renderer()
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 1, 1, map_image, 2)
        assert MapRendererLayer.DOOR not in cached_layers

    def test_door_layer_hidden_via_config(self) -> None:
        map_data = _make_small_map_data()
        map_data.door_lines = [Wall(100, 800, 200, 800)]
        renderer = self._renderer(hidden_map_objects=["door"])
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 1, 1, map_image, 2)
        assert MapRendererLayer.DOOR not in cached_layers

    def test_door_line_color_is_distinct_from_wall_color_in_every_built_in_scheme(self) -> None:
        from custom_components.dreame_vacuum.dreame.vacuum_types import MAP_COLOR_SCHEME_LIST

        for name, scheme in MAP_COLOR_SCHEME_LIST.items():
            door_color = DreameVacuumMapRenderer._door_line_color(scheme.wall)
            assert door_color != tuple(scheme.wall), f"{name}: door colour must differ from wall colour"
            assert len(door_color) == 4


class TestChargerLayerOffsets:
    def test_mijia_icon_set_applies_lidar_offset(self) -> None:
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, icon_set="Mijia")
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 0, 0, map_image, 2)
        assert MapRendererLayer.CHARGER in cached_layers

    def test_material_icon_set_charger_renders_with_color_tint(self) -> None:
        # The Material (icon_set==3) branch tints the charger icon through
        # ``_set_icon_color`` with a full RGBA colour, so the charger layer
        # renders instead of crashing on an RGB/RGBA shape mismatch.
        map_data = _make_small_map_data()
        renderer = DreameVacuumMapRenderer(
            low_resolution=False, cache=True, icon_set="Material", robot_type=RobotType.VSLAM
        )
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 0, 0, map_image, 2)
        assert MapRendererLayer.CHARGER in cached_layers

    def test_charger_layer_removed_when_disabled(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, _make_small_map_data(), 0, 0, map_image, 2)
        assert MapRendererLayer.CHARGER in cached_layers

        renderer2 = DreameVacuumMapRenderer(low_resolution=False, cache=True, hidden_map_objects=["charger"])
        renderer2._map_data = _make_small_map_data()
        renderer2.render_objects(cached_layers, _make_small_map_data(), 0, 0, map_image, 2)
        assert MapRendererLayer.CHARGER not in cached_layers


class TestRobotLayerDocked:
    @pytest.mark.parametrize("angle", [0, 90, 180, 270])
    def test_docked_charger_angle_snaps_robot_position(self, angle: int) -> None:
        map_data = _make_small_map_data()
        map_data.docked = True
        map_data.charger_position = Point(500, 500, a=angle)
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 1, 0, map_image, 2)
        assert MapRendererLayer.ROBOT in cached_layers

    def test_docked_vslam_uses_wide_offset(self) -> None:
        map_data = _make_small_map_data()
        map_data.docked = True
        map_data.charger_position = Point(500, 500, a=0)
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, robot_type=RobotType.VSLAM)
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 1, 0, map_image, 2)
        assert MapRendererLayer.ROBOT in cached_layers

    def test_docked_sweeping_and_mopping_uses_narrower_offset(self) -> None:
        map_data = _make_small_map_data()
        map_data.docked = True
        map_data.charger_position = Point(500, 500, a=0)
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, robot_type=RobotType.SWEEPING_AND_MOPPING)
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, map_data, 1, 0, map_image, 2)
        assert MapRendererLayer.ROBOT in cached_layers

    def test_robot_layer_removed_when_no_robot_position(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, _make_small_map_data(), 1, 0, map_image, 2)
        assert MapRendererLayer.ROBOT in cached_layers

        without_robot = _make_small_map_data()
        without_robot.robot_position = None
        renderer._map_data = _make_small_map_data()
        renderer.render_objects(cached_layers, without_robot, 1, 0, map_image, 2)
        assert MapRendererLayer.ROBOT not in cached_layers

    def test_robot_layer_removed_for_saved_map(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        cached_layers: dict = {}
        renderer.render_objects(cached_layers, _make_small_map_data(), 1, 0, map_image, 2)
        assert MapRendererLayer.ROBOT in cached_layers

        saved = _make_small_map_data()
        saved.saved_map = True
        renderer._map_data = _make_small_map_data()
        renderer.render_objects(cached_layers, saved, 1, 0, map_image, 2)
        assert MapRendererLayer.ROBOT not in cached_layers


class TestComposeObjectLayers:
    def test_no_changes_and_no_cached_objects_returns_map_image_unchanged(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)
        map_image = Image.new("RGBA", (10, 10), (1, 2, 3, 4))
        result = renderer._compose_object_layers({}, [], [], (10, 10), map_image)
        assert result is map_image

    def test_thumbnail_resize_applied_when_layer_size_differs_from_map_image(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)
        cached_layers = {MapRendererLayer.SEGMENTS: Image.new("RGBA", (40, 40), (9, 9, 9, 200))}
        map_image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        result = renderer._compose_object_layers(
            cached_layers, [MapRendererLayer.SEGMENTS], [MapRendererLayer.SEGMENTS], (40, 40), map_image
        )
        assert result.size == (10, 10)
        assert cached_layers[MapRendererLayer.OBJECTS].size == (10, 10)


class TestRenderPathDirect:
    @staticmethod
    def _renderer(low_memory: bool = False) -> DreameVacuumMapRenderer:
        return DreameVacuumMapRenderer(low_resolution=low_memory)

    def test_sweep_only_path_draws_line_and_end_caps(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=50)
        path = [Path(100, 100, PathType.SWEEP), Path(500, 500, PathType.LINE)]
        layer = renderer.render_path(path, (255, 0, 0, 255), (0, 0, 255, 255), (100, 100), None, dims, 2, 1)
        assert (np.array(layer)[:, :, 3] > 0).any()

    def test_mop_path_with_mask_uses_masked_paste(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=50)
        path = [Path(100, 100, PathType.MOP), Path(500, 500, PathType.LINE)]
        mask = Image.new("L", (100, 100), 255)
        layer = renderer.render_path(path, (255, 0, 0, 255), (0, 0, 255, 255), (100, 100), mask, dims, 2, 1)
        assert (np.array(layer)[:, :, 3] > 0).any()

    def test_low_memory_treats_every_segment_as_sweep(self) -> None:
        renderer = self._renderer(low_memory=True)
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=50)
        path = [Path(100, 100, PathType.MOP), Path(500, 500, PathType.LINE)]
        layer = renderer.render_path(path, (255, 0, 0, 255), (0, 0, 255, 255), (100, 100), None, dims, 2, 1)
        assert (np.array(layer)[:, :, 3] > 0).any()

    def test_sweep_and_mop_path_draws_both_layers(self) -> None:
        renderer = self._renderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=50)
        path = [Path(100, 100, PathType.SWEEP_AND_MOP), Path(500, 500, PathType.LINE), Path(600, 600, PathType.LINE)]
        mask = Image.new("L", (100, 100), 255)
        layer = renderer.render_path(path, (255, 0, 0, 255), (0, 0, 255, 255), (100, 100), mask, dims, 2, 1)
        assert (np.array(layer)[:, :, 3] > 0).any()


class TestResolveOverlaps:
    def test_badge_overlap_flips_close_segments(self) -> None:
        renderer = DreameVacuumMapRenderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=50)
        # Two segments with badge centres very close together (within the flip threshold).
        segments = {
            1: Segment(1, x0=0, y0=0, x1=100, y1=100, x=100, y=100),
            2: Segment(2, x0=0, y0=0, x1=100, y1=100, x=105, y=105),
        }
        flipped = renderer._resolve_badge_overlaps(segments, dims, 10, 0)
        assert flipped  # at least one segment id got flipped

    def test_badge_overlap_no_flip_when_far_apart(self) -> None:
        renderer = DreameVacuumMapRenderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=50)
        segments = {
            1: Segment(1, x0=0, y0=0, x1=100, y1=100, x=100, y=100),
            2: Segment(2, x0=0, y0=0, x1=100, y1=100, x=900, y=900),
        }
        # size=1 -> threshold (size*5=5 grid units) well below the ~22-unit
        # separation between these two badge centres.
        flipped = renderer._resolve_badge_overlaps(segments, dims, 1, 0)
        assert flipped == {}

    def test_badge_overlap_skips_segments_without_center(self) -> None:
        renderer = DreameVacuumMapRenderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=50)
        segments = {1: Segment(1, x0=0, y0=0, x1=100, y1=100)}  # x/y left as None
        assert renderer._resolve_badge_overlaps(segments, dims, 10, 0) == {}

    @pytest.mark.parametrize("rotation", [90, 180, 270])
    def test_badge_overlap_offsets_follow_rotation(self, rotation: int) -> None:
        renderer = DreameVacuumMapRenderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=50)
        segments = {
            1: Segment(1, x0=0, y0=0, x1=100, y1=100, x=100, y=100),
            2: Segment(2, x0=0, y0=0, x1=100, y1=100, x=105, y=105),
        }
        flipped = renderer._resolve_badge_overlaps(segments, dims, 10, rotation)
        assert flipped

    def test_name_overlap_pushes_close_segments_apart(self) -> None:
        renderer = DreameVacuumMapRenderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=50)
        segments = {
            1: Segment(1, x0=0, y0=0, x1=100, y1=100, x=100, y=100),
            2: Segment(2, x0=0, y0=0, x1=100, y1=100, x=105, y=105),
        }
        offsets = renderer._resolve_name_overlaps(segments, dims, 10, 0)
        assert 1 in offsets or 2 in offsets

    def test_name_overlap_identical_centers_uses_default_direction(self) -> None:
        renderer = DreameVacuumMapRenderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=50)
        # Exactly identical centres -> dist == 0 -> the (dx, dy) = (0, -1) default branch.
        segments = {
            1: Segment(1, x0=0, y0=0, x1=100, y1=100, x=100, y=100),
            2: Segment(2, x0=0, y0=0, x1=100, y1=100, x=100, y=100),
        }
        offsets = renderer._resolve_name_overlaps(segments, dims, 10, 0)
        assert offsets

    def test_name_overlap_no_shift_when_far_apart(self) -> None:
        renderer = DreameVacuumMapRenderer()
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=50)
        segments = {
            1: Segment(1, x0=0, y0=0, x1=100, y1=100, x=100, y=100),
            2: Segment(2, x0=0, y0=0, x1=100, y1=100, x=900, y=900),
        }
        # size=1 -> threshold (size*3.5=3.5 grid units) well below the ~22-unit separation.
        assert renderer._resolve_name_overlaps(segments, dims, 1, 0) == {}


class TestRobotIconDataUri:
    """``robot_icon_data_uri`` exposes the base robot body icon for the card overlay."""

    def test_returns_valid_png_data_uri_and_caches(self) -> None:
        import base64
        from io import BytesIO

        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        uri = renderer.robot_icon_data_uri()

        assert uri is not None
        assert uri.startswith("data:image/png;base64,")
        image = Image.open(BytesIO(base64.b64decode(uri.split(",", 1)[1])))
        assert image.format == "PNG"
        assert image.mode == "RGBA"
        assert image.size[0] > 0
        assert image.size[1] > 0
        # Cached: a second call returns the very same string object.
        assert renderer.robot_icon_data_uri() is uri

    def test_available_even_when_robot_hidden_from_png(self) -> None:
        # The icon must be exposed independently of whether the robot is baked
        # into the PNG, so the card overlay can use it when robot_in_map=false.
        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True, hidden_map_objects=["robot"])
        assert renderer.config.robot is False
        assert renderer.robot_icon_data_uri() is not None

    def test_lit_variant_differs_from_base_and_caches_separately(self) -> None:
        import base64
        from io import BytesIO

        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        base = renderer.robot_icon_data_uri(light_on=False)
        lit = renderer.robot_icon_data_uri(light_on=True)

        assert base is not None
        assert lit is not None
        # The "fill light on" glow variant is a different image from the base body.
        assert lit != base
        assert lit.startswith("data:image/png;base64,")
        image = Image.open(BytesIO(base64.b64decode(lit.split(",", 1)[1])))
        assert image.format == "PNG"
        assert image.mode == "RGBA"
        # Same canvas size as the base body -> the robot does not resize when lit.
        base_image = Image.open(BytesIO(base64.b64decode(base.split(",", 1)[1])))
        assert image.size == base_image.size
        # Each variant is cached independently.
        assert renderer.robot_icon_data_uri(light_on=True) is lit
        assert renderer.robot_icon_data_uri(light_on=False) is base

    def test_lit_variant_preserves_alpha_and_footprint(self) -> None:
        """Regression for the "all-white blob" bug (Plan 021).

        The previous implementation ran ``ImageEnhance.Brightness`` on the
        whole RGBA image (which multiplies the alpha channel too, turning a
        translucent halo opaque) and layered a blurred "bloom" underneath
        (expanding the lit area beyond the body's own footprint). Both are
        gone: the lit variant must have the exact same alpha channel as the
        base (same footprint, same translucency) and only the RGB channels
        may differ.
        """
        import base64
        from io import BytesIO

        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        base = renderer.robot_icon_data_uri(light_on=False)
        lit = renderer.robot_icon_data_uri(light_on=True)
        assert base is not None
        assert lit is not None

        base_arr = np.array(Image.open(BytesIO(base64.b64decode(base.split(",", 1)[1]))).convert("RGBA"))
        lit_arr = np.array(Image.open(BytesIO(base64.b64decode(lit.split(",", 1)[1]))).convert("RGBA"))

        # Alpha channel strictly identical -- no bloom, no opaque halo.
        assert np.array_equal(base_arr[:, :, 3], lit_arr[:, :, 3])
        # Same set of opaque pixels (redundant with the above, spelled out
        # explicitly per the footprint requirement).
        assert np.array_equal(base_arr[:, :, 3] > 0, lit_arr[:, :, 3] > 0)
        # RGB channels differ (the warm tint is visible).
        assert not np.array_equal(base_arr[:, :, :3], lit_arr[:, :, :3])


class TestRobotBeamIconDataUri:
    """``robot_beam_icon_data_uri`` exposes the forward fill-light beam asset.

    Served as a separate attribute from the body icon (Plan 021): the card
    draws it behind the body while the fill light is on, instead of the old
    approach of whitening the body itself (which produced an unreadable blob
    on the already near-white mop/sweeping-and-mopping bodies).
    """

    def test_returns_valid_png_data_uri_and_caches(self) -> None:
        import base64
        from io import BytesIO

        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        uri = renderer.robot_beam_icon_data_uri()

        assert uri is not None
        assert uri.startswith("data:image/png;base64,")
        image = Image.open(BytesIO(base64.b64decode(uri.split(",", 1)[1])))
        assert image.format == "PNG"
        assert image.mode == "RGBA"
        # Cached: a second call returns the very same string object.
        assert renderer.robot_beam_icon_data_uri() is uri

    def test_native_orientation_apex_left_opening_toward_plus_x(self) -> None:
        """Empirical orientation check (see the method's docstring).

        The underlying ``MAP_ROBOT_CLEANING_DIRECTION_IMAGE`` asset was
        decoded and its opaque-pixel column histogram inspected directly: the
        cone's apex (narrow, near-robot side) sits in the leftmost columns
        (~1400 opaque px in the left third) while its wide, fading base sits
        in the rightmost columns (~6800 opaque px in the right third) --
        i.e. it already points toward +x at heading 0 with no rotation
        needed, matching the "heading 0 == +x" contract shared with the body
        icon.
        """
        import base64
        from io import BytesIO

        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        uri = renderer.robot_beam_icon_data_uri()
        assert uri is not None
        arr = np.array(Image.open(BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGBA"))
        opaque = arr[:, :, 3] > 0
        width = opaque.shape[1]
        col_counts = opaque.sum(axis=0)
        left_third = col_counts[: width // 3].sum()
        right_third = col_counts[-(width // 3) :].sum()
        # Apex (narrow) on the left, wide/fading base on the right.
        assert left_third < right_third

    def test_warm_tint_applied(self) -> None:
        """Opaque pixels are pushed warm (red/green up, blue cut) vs. the
        plain white native cone, so the beam reads as a light glow rather
        than the neutral "cleaning direction" indicator it's borrowed from.
        """
        import base64
        from io import BytesIO

        renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
        uri = renderer.robot_beam_icon_data_uri()
        assert uri is not None
        arr = np.array(Image.open(BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGBA"))
        opaque = arr[:, :, 3] > 0
        assert (arr[opaque, 0] >= arr[opaque, 2]).all()  # red pushed at/above blue
        assert arr[opaque, 2].mean() < 200  # blue visibly cut vs. the native 255
