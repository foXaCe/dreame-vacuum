"""Behavioural tests for the ``_ResourcesMixin`` (``_resources_props.py``).

Exercises ``get_resources`` (the frontend icon/image resource bundle) across
icon-set/robot-type/capability combinations, plus the ``calibration_points``,
``default_map_image``, ``disconnected_map_image`` and
``default_calibration_points`` properties. Uses the real
``DreameVacuumDeviceCapability`` dataclass (constructed with a ``MagicMock``
device, matching the pattern in ``tests/test_device_status_core.py``) with
plain boolean attributes overridden directly -- ``get_resources`` only ever
reads attributes, never device methods, except for the ``custom_cleaning_mode``
property, which is short-circuited to ``True`` via ``auto_switch_settings`` +
``mop_pad_lifting`` so it never touches the mocked device.
"""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame.map_renderer._core import DreameVacuumMapRenderer
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    DreameVacuumDeviceCapability,
    FurnitureType,
    MapData,
    MapImageDimensions,
    ObstacleType,
    RobotType,
)


def _capability(**overrides: object) -> DreameVacuumDeviceCapability:
    device = MagicMock()
    # A bare MagicMock's default __iter__ raises StopIteration as soon as
    # ``custom_cleaning_mode`` calls ``next(iter(segments.values()))``; give it
    # a real (empty) dict so that property degrades gracefully instead of
    # crashing whenever a test doesn't care about its value.
    device.status.current_segments = {}
    capability = DreameVacuumDeviceCapability(device)
    for key, value in overrides.items():
        setattr(capability, key, value)
    return capability


class TestGetResourcesBaseFields:
    def test_minimal_capability_returns_core_resource_fields(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability())
        assert resources.icon_set == 0
        assert resources.robot_type == RobotType.LIDAR.value
        assert resources.robot
        assert resources.charger
        assert resources.segment
        assert resources.font
        # Capability-gated fields stay unset when the capability is minimal.
        assert resources.repeats is None
        assert resources.washing is None
        assert resources.emptying is None
        assert resources.wifi is None
        assert resources.obstacle is None
        assert resources.furniture is None

    @pytest.mark.parametrize(
        ("icon_set_name", "expected"),
        [("Dreame", 0), ("Dreame Old", 1), ("Mijia", 2), ("Material", 3)],
    )
    def test_icon_set_selects_matching_segment_icon_bundle(self, icon_set_name: str, expected: int) -> None:
        renderer = DreameVacuumMapRenderer(icon_set=icon_set_name, robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability())
        assert resources.icon_set == expected
        assert isinstance(resources.segment, dict)
        assert len(resources.segment) > 0
        for entry in resources.segment.values():
            assert set(entry.keys()) == {"name", "icon", "mdi"}

    @pytest.mark.parametrize("robot_type", [RobotType.LIDAR, RobotType.MOPPING, RobotType.VSLAM])
    def test_mijia_icon_set_robot_image_per_robot_type(self, robot_type: RobotType) -> None:
        renderer = DreameVacuumMapRenderer(icon_set="Mijia", robot_type=robot_type)
        resources = renderer.get_resources(_capability())
        assert resources.robot_type == robot_type.value
        assert resources.robot

    @pytest.mark.parametrize(
        "robot_type", [RobotType.LIDAR, RobotType.MOPPING, RobotType.SWEEPING_AND_MOPPING, RobotType.VSLAM]
    )
    def test_dreame_icon_set_robot_image_per_robot_type(self, robot_type: RobotType) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=robot_type)
        resources = renderer.get_resources(_capability())
        assert resources.robot

    def test_material_icon_set_vslam_uses_light_image(self) -> None:
        renderer = DreameVacuumMapRenderer(icon_set="Material", robot_type=RobotType.VSLAM)
        resources = renderer.get_resources(_capability())
        assert resources.robot

    @pytest.mark.parametrize("icon_set_name", ["Mijia", "Material"])
    def test_charger_image_per_icon_set(self, icon_set_name: str) -> None:
        renderer = DreameVacuumMapRenderer(icon_set=icon_set_name, robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability())
        assert resources.charger

    def test_vslam_dreame_charger_uses_vslam_image(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.VSLAM)
        resources = renderer.get_resources(_capability())
        assert resources.charger

    def test_icon_set_string_override_takes_precedence(self) -> None:
        renderer = DreameVacuumMapRenderer(icon_set="Dreame", robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(), icon_set="2")
        assert resources.icon_set == 2

    def test_non_decimal_icon_set_override_falls_back_to_renderer_default(self) -> None:
        renderer = DreameVacuumMapRenderer(icon_set="Material", robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(), icon_set="not-a-number")
        assert resources.icon_set == 3

    def test_as_json_returns_parseable_payload_with_expected_keys(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        payload = renderer.get_resources(_capability(), as_json=True)
        assert isinstance(payload, str)
        parsed = json.loads(payload)
        assert parsed["icon_set"] == 0
        assert "robot" in parsed
        assert "segment" in parsed


class TestGetResourcesCapabilityGatedFields:
    def test_customized_cleaning_without_custom_mode_adds_only_base_icons(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(customized_cleaning=True))
        assert resources.repeats
        assert resources.suction_level
        assert resources.water_volume
        assert resources.mop_pad_humidity
        assert resources.cleaning_mode is None

    def test_customized_cleaning_with_cleaning_route_adds_cleaning_route(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        capability = _capability(
            customized_cleaning=True,
            auto_switch_settings=True,
            mop_pad_lifting=True,  # short-circuits custom_cleaning_mode True without touching the device
            cleaning_route=True,
        )
        resources = renderer.get_resources(capability)
        assert resources.cleaning_mode
        assert resources.cleaning_route
        assert resources.custom_mopping_route is None

    def test_customized_cleaning_with_segment_mopping_settings_adds_custom_route(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        capability = _capability(
            customized_cleaning=True,
            auto_switch_settings=True,
            mop_pad_lifting=True,
            cleaning_route=False,
            segment_mopping_settings=True,
        )
        resources = renderer.get_resources(capability)
        assert resources.cleaning_mode
        assert resources.custom_mopping_route
        assert resources.cleaning_route is None

    def test_material_icon_set_customized_cleaning_uses_material_icons(self) -> None:
        renderer = DreameVacuumMapRenderer(icon_set="Material", robot_type=RobotType.LIDAR)
        capability = _capability(
            customized_cleaning=True, auto_switch_settings=True, mop_pad_lifting=True, cleaning_route=True
        )
        resources = renderer.get_resources(capability)
        assert resources.suction_level
        assert resources.cleaning_route

    def test_mijia_icon_set_customized_cleaning_uses_mijia_icons(self) -> None:
        renderer = DreameVacuumMapRenderer(icon_set="Mijia", robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(customized_cleaning=True))
        assert resources.suction_level
        assert resources.mop_pad_humidity

    def test_self_wash_base_adds_washing_and_drying(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(self_wash_base=True))
        assert resources.washing
        assert resources.drying
        assert resources.hot_washing is None
        assert resources.hot_drying is None

    def test_self_wash_base_with_hot_washing_adds_hot_variants(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(self_wash_base=True, hot_washing=True))
        assert resources.hot_washing
        assert resources.hot_drying

    def test_auto_empty_base_adds_emptying_icon(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(auto_empty_base=True))
        assert resources.emptying

    def test_wifi_map_adds_wifi_icon(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(wifi_map=True))
        assert resources.wifi


class TestGetResourcesCameraStreaming:
    def test_camera_streaming_adds_obstacle_and_backgrounds(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(camera_streaming=True))
        assert resources.cruise_path_point_background
        assert resources.obstacle_background
        assert resources.obstacle_hidden_background
        assert isinstance(resources.obstacle, dict)
        assert ObstacleType.OBSTACLE.value in resources.obstacle
        for entry in resources.obstacle.values():
            assert "name" in entry

    def test_camera_streaming_v1_furniture_dict_default(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(camera_streaming=True))
        assert isinstance(resources.furniture, dict)
        # v1 dict keyed by FurnitureType value; SINGLE_BED must be present.
        assert FurnitureType.SINGLE_BED.value in resources.furniture
        entry = resources.furniture[FurnitureType.SINGLE_BED.value]
        assert set(entry.keys()) == {"name", "icon", "image", "dimensions"}

    def test_camera_streaming_without_pet_furniture_excludes_pet_types(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(camera_streaming=True, pet_furniture=False))
        assert FurnitureType.LITTER_BOX.value not in resources.furniture
        assert FurnitureType.PET_BED.value not in resources.furniture

    def test_camera_streaming_with_pet_furniture_includes_pet_types(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(camera_streaming=True, pet_furniture=True, new_furnitures=True))
        assert FurnitureType.LITTER_BOX.value in resources.furniture

    def test_camera_streaming_without_extended_furnitures_excludes_high_value_types(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(_capability(camera_streaming=True, extended_furnitures=False))
        assert all(k <= 13 for k in resources.furniture)

    def test_camera_streaming_new_furnitures_uses_v2_dict(self) -> None:
        renderer = DreameVacuumMapRenderer(robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(
            _capability(camera_streaming=True, new_furnitures=True, extended_furnitures=True)
        )
        # v2 dict supports higher-numbered types absent from the v1 dict (e.g. WARDROBE=21).
        assert FurnitureType.WARDROBE.value in resources.furniture

    def test_camera_streaming_new_furnitures_mijia_uses_mijia_v2_dict(self) -> None:
        renderer = DreameVacuumMapRenderer(icon_set="Mijia", robot_type=RobotType.LIDAR)
        resources = renderer.get_resources(
            _capability(camera_streaming=True, new_furnitures=True, extended_furnitures=True, mijia=True)
        )
        assert FurnitureType.WARDROBE.value in resources.furniture


class TestCalibrationAndPlaceholderImages:
    def test_calibration_points_none_before_any_render(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        assert renderer.calibration_points is None

    def test_default_calibration_points_is_a_three_point_identity_grid(self) -> None:
        renderer = DreameVacuumMapRenderer(low_resolution=True)
        points = renderer.default_calibration_points
        assert len(points) == 3
        for point in points:
            assert set(point.keys()) == {"vacuum", "map"}
            assert point["map"] == {"x": 0, "y": 0}

    def test_default_map_image_is_valid_png(self) -> None:
        from PIL import Image

        renderer = DreameVacuumMapRenderer(low_resolution=True)
        data = renderer.default_map_image
        img = Image.open(io.BytesIO(data))
        assert img.format == "PNG"

    def test_disconnected_map_image_is_blurred_variant_of_last_render(self) -> None:
        from PIL import Image

        renderer = DreameVacuumMapRenderer(low_resolution=True, cache=True)

        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=50)
        map_data = MapData()
        map_data.dimensions = dims
        map_data.empty_map = False
        map_data.rotation = 0
        map_data.map_id = 1
        map_data.frame_id = 1
        import numpy as np

        map_data.pixel_type = np.zeros((20, 20), dtype="uint8")
        map_data.pixel_type[5:15, 5:15] = 254
        map_data.segments = None
        map_data.saved_map = False

        renderer.render_map(map_data, robot_status=0, station_status=0)
        first = renderer.disconnected_map_image
        second = renderer.disconnected_map_image
        assert first is second  # cached
        img = Image.open(io.BytesIO(first))
        assert img.format == "PNG"

    def test_disconnected_map_image_low_resolution_uses_smaller_blur_radius(self) -> None:
        # Sanity check both resolutions still produce decodable images (the
        # blur radius itself (7 vs 13) isn't independently observable from
        # the public API without image-processing heuristics).
        from PIL import Image

        for low_res in (True, False):
            renderer = DreameVacuumMapRenderer(low_resolution=low_res)
            data = renderer.disconnected_map_image
            img = Image.open(io.BytesIO(data))
            assert img.format == "PNG"
