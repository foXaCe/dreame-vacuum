"""Behavioural tests for dreame/vacuum_types.py.

Covers: DreameVacuumDeviceCapability.load() and its derived properties, the
map geometry primitives (Point/Path/Obstacle/Zone/Segment/Wall/Area/Furniture/
Coordinate/Carpet/Polygon/MapImageDimensions), CleaningHistory/RecoveryMapInfo
parsing, MapData.__eq__/as_dict/check_point, and the small tail dataclasses.

No mocking of vacuum_types itself: MagicMock is only used for the collaborator
``DreameVacuumDevice`` object that DreameVacuumDeviceCapability reads from.
"""

from __future__ import annotations

from datetime import datetime
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    ATTR_A,
    ATTR_ANGLE,
    ATTR_CLEANING_MODE,
    ATTR_CLEANING_ROUTE,
    ATTR_CUSTOM_MOPPING_ROUTE,
    ATTR_CUSTOM_NAME,
    ATTR_ROOM_ID,
    ATTR_TYPE,
    ATTR_WETNESS_LEVEL,
    ATTR_X,
    ATTR_Y,
    DID,
    DIID,
    PIID,
    Area,
    Carpet,
    CleaningHistory,
    CleansetType,
    CleanupMethod,
    Coordinate,
    DeviceCapability,
    DirtyData,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumDeviceCapability,
    DreameVacuumFloorMaterialDirection,
    DreameVacuumProperty,
    DreameVacuumPropertyMapping,
    DreameVacuumSegmentVisibility,
    DreameVacuumStatus,
    DreameVacuumSuctionLevel,
    DreameVacuumWaterTank,
    Furniture,
    FurnitureType,
    MapData,
    MapDataPartial,
    MapImageDimensions,
    Obstacle,
    ObstacleIgnoreStatus,
    ObstaclePictureStatus,
    ObstacleType,
    Path,
    PathType,
    Point,
    Polygon,
    RecoveryMapInfo,
    RecoveryMapType,
    RobotType,
    ScheduleTask,
    Segment,
    SegmentNeglectReason,
    Shortcut,
    ShortcutTask,
    StartupMethod,
    TaskInterruptReason,
    Wall,
    Zone,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _device_info(model: str, fw_ver: str | None = "4.5.6_0050") -> DreameVacuumDeviceInfo:
    data: dict[str, Any] = {"model": model, "mac": "AA:BB:CC:DD:EE:FF"}
    if fw_ver is not None:
        data["fw_ver"] = fw_ver
    return DreameVacuumDeviceInfo(data)


def _capability_device(
    model: str,
    fw_ver: str | None = "4.5.6_0050",
    properties: dict[Any, Any] | None = None,
    auto_switch_properties: dict[Any, Any] | None = None,
    current_map: Any = None,
    fill_light: Any = None,
    current_segments: Any = None,
    map_manager: Any = None,
) -> MagicMock:
    """A MagicMock DreameVacuumDevice with deterministic (non-auto-truthy) collaborators."""
    props = properties or {}
    switch_props = auto_switch_properties or {}
    device = MagicMock()
    device.info = _device_info(model, fw_ver)
    device.get_property = MagicMock(side_effect=lambda prop: props.get(prop))
    device.get_auto_switch_property = MagicMock(side_effect=lambda prop: switch_props.get(prop))
    device.status = SimpleNamespace(current_map=current_map, fill_light=fill_light, current_segments=current_segments)
    device._map_manager = map_manager
    return device


def _device_info_table(
    model_suffix: str,
    capability_pairs: list[list[int]],
    *,
    key_index: int | None = None,
    keys: list[str] | None = None,
) -> list[Any]:
    """Build a minimal device_info table shaped like the real (compressed) DEVICE_INFO."""
    device_entry: list[Any] = ["Test Device", 0, 0]
    if key_index is not None:
        device_entry.append(key_index)
    return [
        [device_entry],
        [capability_pairs],
        keys or [],
        {model_suffix: 0},
    ]


class _PixelGrid:
    """Minimal stand-in for the numpy pixel_type array: supports pixel_type[x, y]."""

    def __init__(self, values: dict[tuple[int, int], int]) -> None:
        self._values = values

    def __getitem__(self, key: tuple[int, int]) -> int:
        return self._values.get(key, 0)


# ===========================================================================
# PIID / DIID helpers
# ===========================================================================


def test_piid_returns_none_when_property_not_mapped():
    assert PIID(DreameVacuumProperty.BATTERY_LEVEL, {}) is None


def test_piid_returns_configured_piid():
    assert PIID(DreameVacuumProperty.BATTERY_LEVEL, DreameVacuumPropertyMapping) == 1


def test_diid_formats_siid_dot_piid():
    assert DIID(DreameVacuumProperty.BATTERY_LEVEL, DreameVacuumPropertyMapping) == "3.1"


def test_diid_returns_none_when_property_not_mapped():
    assert DIID(DreameVacuumProperty.BATTERY_LEVEL, {}) is None


def test_did_resolves_property_from_siid_piid():
    assert DID(3, 1) == DreameVacuumProperty.BATTERY_LEVEL


def test_did_returns_none_for_unknown_pair():
    assert DID(9999, 9999) is None


# ===========================================================================
# DreameVacuumDeviceCapability.load() — error paths
# ===========================================================================


class TestDeviceCapabilityLoadErrors:
    def test_raises_when_info_is_none(self) -> None:
        device = MagicMock()
        device.info = None
        capability = DreameVacuumDeviceCapability(device)
        with pytest.raises(Exception, match="Unsupported Device"):
            capability.load(_device_info_table("r2228", []))

    def test_raises_when_model_is_none(self) -> None:
        device = MagicMock()
        device.info = DreameVacuumDeviceInfo({})
        capability = DreameVacuumDeviceCapability(device)
        with pytest.raises(Exception, match="Unsupported Device"):
            capability.load(_device_info_table("r2228", []))

    def test_raises_when_model_suffix_unknown(self) -> None:
        device = _capability_device("dreame.vacuum.zzzz9")
        capability = DreameVacuumDeviceCapability(device)
        with pytest.raises(Exception, match="Unsupported Device"):
            capability.load(_device_info_table("r2228", []))

    def test_raises_when_device_entry_wrong_length(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        table = [[["only", "two"]], [[]], [], {"r2228": 0}]
        with pytest.raises(Exception, match="Unsupported Device"):
            capability.load(table)

    def test_raises_when_device_entry_falsy(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        table = [[[]], [[]], [], {"r2228": 0}]
        with pytest.raises(Exception, match="Unsupported Device"):
            capability.load(table)

    def test_raises_when_capability_index_negative(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        table = [[["name", 0, -1]], [[]], [], {"r2228": 0}]
        with pytest.raises(Exception, match="Unsupported Device"):
            capability.load(table)

    def test_raises_when_capability_slot_is_none(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        table = [[["name", 0, 0]], [None], [], {"r2228": 0}]
        with pytest.raises(Exception, match="Device capability missing"):
            capability.load(table)

    def test_raises_when_key_index_out_of_range(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        table = _device_info_table("r2228", [], key_index=3, keys=["only-one"])
        with pytest.raises(Exception, match=r"^Device key missing!$") as exc_info:
            capability.load(table)
        assert str(exc_info.value) == "Device key missing!"

    def test_raises_when_key_is_empty_string(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        table = _device_info_table("r2228", [], key_index=0, keys=[""])
        with pytest.raises(Exception, match=r"^Device Key missing!$") as exc_info:
            capability.load(table)
        assert str(exc_info.value) == "Device Key missing!"


# ===========================================================================
# DreameVacuumDeviceCapability.load() — successful derivation
# ===========================================================================


class TestDeviceCapabilityLoadSuccess:
    def test_load_sets_key_and_version_gated_capability_flags(self) -> None:
        """A capability whose min-version is <= firmware version turns on; others stay off."""
        device = _capability_device("dreame.vacuum.r2228", fw_ver="4.5.6_0050")  # version=50
        capability = DreameVacuumDeviceCapability(device)
        table = _device_info_table(
            "r2228",
            [
                [DeviceCapability.MOP_PAD_LIFTING.value, 10],
                [DeviceCapability.GEN5.value, 100],
            ],
            key_index=0,
            keys=["secret-key"],
        )
        capability.load(table)
        assert capability.key == "secret-key"
        assert capability.mop_pad_lifting is True  # 50 >= 10
        assert capability.gen5 is False  # 50 < 100

    def test_load_without_key_index_leaves_key_none(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", []))
        assert capability.key is None

    @pytest.mark.parametrize(
        ("self_wash_base", "mop_pad_lifting_cap", "map_saving_present", "expected"),
        [
            (True, True, False, RobotType.SWEEPING_AND_MOPPING),
            (True, False, False, RobotType.MOPPING),
            (False, False, False, RobotType.LIDAR),
            (False, False, True, RobotType.VSLAM),
        ],
    )
    def test_load_derives_robot_type(
        self, self_wash_base: bool, mop_pad_lifting_cap: bool, map_saving_present: bool, expected: RobotType
    ) -> None:
        properties: dict[Any, Any] = {}
        if self_wash_base:
            properties[DreameVacuumProperty.SELF_WASH_BASE_STATUS] = 1
        if map_saving_present:
            properties[DreameVacuumProperty.MAP_SAVING] = 1
        device = _capability_device("dreame.vacuum.r2228", properties=properties)
        capability = DreameVacuumDeviceCapability(device)
        pairs = [[DeviceCapability.MOP_PAD_LIFTING.value, 0]] if mop_pad_lifting_cap else []
        capability.load(_device_info_table("r2228", pairs))
        assert capability.robot_type == expected

    def test_load_station_cleaning_requires_self_wash_base_and_gen5(self) -> None:
        device = _capability_device("dreame.vacuum.r2228", properties={DreameVacuumProperty.SELF_WASH_BASE_STATUS: 1})
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.GEN5.value, 0]]))
        assert capability.station_cleaning is True

    def test_load_station_cleaning_false_without_self_wash_base(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.GEN5.value, 0]]))
        assert capability.station_cleaning is False

    def test_load_map_object_offset_false_when_p20_in_model(self) -> None:
        # "p2028" contains the "p20" substring, which disables map_object_offset.
        device = _capability_device("dreame.vacuum.p2028")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("p2028", []))
        assert capability.lidar_navigation is True
        assert capability.map_object_offset is False

    def test_load_map_object_offset_true_without_p20_in_model(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", []))
        assert capability.map_object_offset is True

    def test_load_floor_material_requires_lifting_and_recognition_without_mop_clean_frequency(self) -> None:
        device = _capability_device("dreame.vacuum.r2228", properties={DreameVacuumProperty.CARPET_RECOGNITION: 1})
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.MOP_PAD_LIFTING.value, 0]]))
        assert capability.carpet_recognition is True
        assert capability.floor_material is True

    def test_load_floor_material_false_without_carpet_recognition(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.MOP_PAD_LIFTING.value, 0]]))
        assert capability.floor_material is False

    def test_load_detergent_true_from_detergent_left_property_even_without_capability(self) -> None:
        device = _capability_device("dreame.vacuum.r2228", properties={DreameVacuumProperty.DETERGENT_LEFT: 42})
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", []))
        assert capability.detergent is True

    def test_load_fill_light_true_for_short_numeric_camera_light(self) -> None:
        device = _capability_device(
            "dreame.vacuum.r2228", properties={DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS: "50"}
        )
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.CAMERA_STREAMING.value, 0]]))
        assert capability.camera_streaming is True
        assert capability.fill_light is True

    def test_load_fill_light_false_for_long_camera_light_value(self) -> None:
        device = _capability_device(
            "dreame.vacuum.r2228", properties={DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS: "9999999"}
        )
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.CAMERA_STREAMING.value, 0]]))
        assert capability.fill_light is False

    def test_load_fill_light_false_when_camera_light_absent(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.CAMERA_STREAMING.value, 0]]))
        assert capability.fill_light is False

    def test_load_mop_pad_swing_true_from_plus_variant(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.MOP_PAD_SWING_PLUS.value, 0]]))
        assert capability.mop_pad_swing_plus is True
        assert capability.mop_pad_swing is True

    def test_load_mop_pad_unmounting_requires_property_too(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.MOP_PAD_UNMOUNTING.value, 0]]))
        assert capability.mop_pad_unmounting is False

        device2 = _capability_device("dreame.vacuum.r2228", properties={DreameVacuumProperty.AUTO_MOUNT_MOP: 1})
        capability2 = DreameVacuumDeviceCapability(device2)
        capability2.load(_device_info_table("r2228", [[DeviceCapability.MOP_PAD_UNMOUNTING.value, 0]]))
        assert capability2.mop_pad_unmounting is True
        # mop_pad_lifting is also derived true via the "mop_pad_unmounting" OR-clause.
        assert capability2.mop_pad_lifting is True

    def test_load_drainage_requires_property_too(self) -> None:
        device = _capability_device("dreame.vacuum.r2228", properties={DreameVacuumProperty.DRAINAGE_STATUS: 1})
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.DRAINAGE.value, 0]]))
        assert capability.drainage is True

    def test_load_pet_detective_requires_property_too(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.PET_FURNITURE.value, 0]]))
        # PET_FURNITURE capability doesn't grant pet_detective; property is also missing.
        assert capability.pet_detective is False

    def test_load_task_type_requires_property_too(self) -> None:
        device = _capability_device("dreame.vacuum.r2228", properties={DreameVacuumProperty.TASK_TYPE: 1})
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.TASK_TYPE.value, 0]]))
        assert capability.task_type is True

    def test_load_mopping_settings_true_from_mopping_type_capability(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.MOPPING_TYPE.value, 0]]))
        assert capability.mopping_type is True
        assert capability.mopping_settings is True

    def test_load_segment_mopping_settings_true_from_segment_mopping_type(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.SEGMENT_MOPPING_TYPE.value, 0]]))
        assert capability.segment_mopping_type is True
        assert capability.segment_mopping_settings is True

    def test_load_wetness_true_when_mopping_settings_and_wetness_level_property(self) -> None:
        device = _capability_device("dreame.vacuum.r2228", properties={DreameVacuumProperty.WETNESS_LEVEL: 3})
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.MOPPING_TYPE.value, 0]]))
        assert capability.wetness is True

    def test_load_wetness_true_from_wetness_level_capability_alone(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.WETNESS_LEVEL.value, 0]]))
        assert capability.wetness_level is True
        assert capability.wetness is True

    def test_load_segment_slow_clean_route_stays_true_when_cleaning_route_supported(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.CLEANING_ROUTE.value, 0]]))
        assert capability.cleaning_route is True
        assert capability.segment_slow_clean_route is True

    def test_load_segment_slow_clean_route_forced_false_without_cleaning_route(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", []))
        assert capability.cleaning_route is False
        assert capability.segment_slow_clean_route is False

    def test_load_custom_mopping_route_true_when_mopping_settings_without_cleaning_route(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.MOPPING_TYPE.value, 0]]))
        assert capability.custom_mopping_route is True

    def test_load_disable_sensor_cleaning_true_when_sensor_property_missing(self) -> None:
        device = _capability_device("dreame.vacuum.r2228", properties={DreameVacuumProperty.OBSTACLE_AVOIDANCE: 1})
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.CAMERA_STREAMING.value, 0]]))
        # lidar_navigation True, camera_streaming True, but SENSOR_DIRTY_LEFT is absent.
        assert capability.disable_sensor_cleaning is True

    def test_load_disable_sensor_cleaning_false_when_all_prerequisites_met(self) -> None:
        device = _capability_device(
            "dreame.vacuum.r2228",
            properties={
                DreameVacuumProperty.SENSOR_DIRTY_LEFT: 1,
                DreameVacuumProperty.OBSTACLE_AVOIDANCE: 1,
            },
        )
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.CAMERA_STREAMING.value, 0]]))
        assert capability.disable_sensor_cleaning is False

    def test_load_mijia_branch_overrides_flags_for_xiaomi_model(self) -> None:
        device = _capability_device("xiaomi.vacuum.d110")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("d110", []))
        assert capability.mijia is True
        assert capability.wifi_map is False
        assert capability.mop_clean_frequency is True
        assert capability.self_clean_frequency is False
        assert capability.floor_material is True  # "d110" in model
        assert capability.off_peak_charging is False
        assert capability.camera_streaming is False
        assert capability.new_furnitures is False
        assert capability.fill_light is False

    def test_load_mijia_branch_floor_material_false_for_other_models(self) -> None:
        device = _capability_device("xiaomi.vacuum.b112")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("b112", []))
        assert capability.mijia is True
        assert capability.floor_material is False

    def test_load_builds_truthy_attribute_list_and_appends_dynamic_props(self) -> None:
        device = _capability_device(
            "dreame.vacuum.r2228",
            properties={DreameVacuumProperty.AUTO_SWITCH_SETTINGS: 1},
            map_manager=MagicMock(),
        )
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.MOP_PAD_LIFTING.value, 0]]))
        assert "mop_pad_lifting" in capability.list
        assert "auto_switch_settings" in capability.list
        # custom_cleaning_mode: auto_switch_settings and mop_pad_lifting are both true.
        assert "custom_cleaning_mode" in capability.list
        # map: _map_manager is not None.
        assert "map" in capability.list

    def test_load_appends_cruising_to_list_when_cruising_available(self) -> None:
        device = _capability_device("dreame.vacuum.r2228", fill_light=1)
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", [[DeviceCapability.CAMERA_STREAMING.value, 0]]))
        assert capability.camera_streaming is True
        assert "cruising" in capability.list

    def test_load_list_omits_false_flags(self) -> None:
        device = _capability_device("dreame.vacuum.r2228")
        capability = DreameVacuumDeviceCapability(device)
        capability.load(_device_info_table("r2228", []))
        assert "gen5" not in capability.list
        assert "detergent" not in capability.list


# ===========================================================================
# DreameVacuumDeviceCapability — computed properties (custom_cleaning_mode,
# cruising, mop_extend, map)
# ===========================================================================


def _bare_capability(**overrides: Any) -> DreameVacuumDeviceCapability:
    """A capability instance whose plain-attribute __init__ never touches the device."""
    capability = DreameVacuumDeviceCapability(MagicMock())
    for key, value in overrides.items():
        setattr(capability, key, value)
    return capability


class TestCustomCleaningModeProperty:
    def test_true_immediately_when_auto_switch_and_mop_pad_lifting(self) -> None:
        capability = _bare_capability(auto_switch_settings=True, mop_pad_lifting=True)
        capability._device.status.current_segments = None
        assert capability.custom_cleaning_mode is True

    def test_true_when_first_segment_has_cleaning_mode_set(self) -> None:
        capability = _bare_capability(auto_switch_settings=False, mop_pad_lifting=False)
        capability._device.status.current_segments = {1: SimpleNamespace(cleaning_mode=2)}
        assert capability.custom_cleaning_mode is True
        assert capability._custom_cleaning_mode is True

    def test_false_when_first_segment_cleaning_mode_is_none(self) -> None:
        capability = _bare_capability(auto_switch_settings=False, mop_pad_lifting=False)
        capability._device.status.current_segments = {1: SimpleNamespace(cleaning_mode=None)}
        assert capability.custom_cleaning_mode is False

    def test_falls_back_to_mop_pad_lifting_when_no_segments(self) -> None:
        capability = _bare_capability(auto_switch_settings=False, mop_pad_lifting=True)
        capability._device.status.current_segments = {}
        assert capability.custom_cleaning_mode is True
        assert capability._custom_cleaning_mode is True

        capability_false = _bare_capability(auto_switch_settings=False, mop_pad_lifting=False)
        capability_false._device.status.current_segments = {}
        assert capability_false.custom_cleaning_mode is False

    def test_caches_true_and_revalidates_against_current_segments(self) -> None:
        capability = _bare_capability(auto_switch_settings=False, mop_pad_lifting=False)
        capability._device.status.current_segments = {1: SimpleNamespace(cleaning_mode=2)}
        assert capability.custom_cleaning_mode is True  # sets the cache

        # Now segments report cleaning_mode=None: cached True is re-validated and fails.
        capability._device.status.current_segments = {2: SimpleNamespace(cleaning_mode=None)}
        assert capability.custom_cleaning_mode is False

        # Segments empty again: "not segments" short-circuits back to True.
        capability._device.status.current_segments = {}
        assert capability.custom_cleaning_mode is True


class TestCruisingProperty:
    def test_false_without_lidar_navigation(self) -> None:
        capability = _bare_capability(lidar_navigation=False, camera_streaming=True)
        assert capability.cruising is False

    def test_false_without_camera_streaming(self) -> None:
        capability = _bare_capability(lidar_navigation=True, camera_streaming=False)
        assert capability.cruising is False

    def test_true_when_current_map_has_predefined_points(self) -> None:
        capability = _bare_capability(lidar_navigation=True, camera_streaming=True)
        capability._device.status.current_map = SimpleNamespace(predefined_points={1: object()})
        capability._device.status.fill_light = None
        capability._device.get_property = MagicMock(return_value=None)
        assert capability.cruising is True

    def test_true_when_cruise_schedule_property_present(self) -> None:
        capability = _bare_capability(lidar_navigation=True, camera_streaming=True)
        capability._device.status.current_map = None
        capability._device.status.fill_light = None
        capability._device.get_property = MagicMock(
            side_effect=lambda prop: 1 if prop == DreameVacuumProperty.CRUISE_SCHEDULE else None
        )
        assert capability.cruising is True

    def test_true_when_fill_light_status_present(self) -> None:
        capability = _bare_capability(lidar_navigation=True, camera_streaming=True)
        capability._device.status.current_map = None
        capability._device.status.fill_light = 1
        capability._device.get_property = MagicMock(return_value=None)
        assert capability.cruising is True

    def test_false_when_nothing_indicates_cruising(self) -> None:
        capability = _bare_capability(lidar_navigation=True, camera_streaming=True)
        capability._device.status.current_map = None
        capability._device.status.fill_light = None
        capability._device.get_property = MagicMock(return_value=None)
        assert capability.cruising is False


class TestMopExtendProperty:
    def test_false_without_mop_pad_swing(self) -> None:
        capability = _bare_capability(mop_pad_swing=False)
        assert capability.mop_extend is False

    def test_false_when_auto_switch_property_missing(self) -> None:
        capability = _bare_capability(mop_pad_swing=True)
        capability._device.get_auto_switch_property = MagicMock(return_value=None)
        assert capability.mop_extend is False

    def test_true_when_both_conditions_met(self) -> None:
        capability = _bare_capability(mop_pad_swing=True)
        capability._device.get_auto_switch_property = MagicMock(
            side_effect=lambda prop: 5 if prop == DreameVacuumAutoSwitchProperty.MOP_EXTEND_FREQUENCY else None
        )
        assert capability.mop_extend is True


class TestMapProperty:
    def test_true_when_map_manager_present(self) -> None:
        capability = _bare_capability()
        capability._device._map_manager = MagicMock()
        assert capability.map is True

    def test_false_when_map_manager_absent(self) -> None:
        capability = _bare_capability()
        capability._device._map_manager = None
        assert capability.map is False


# ===========================================================================
# Point
# ===========================================================================


class TestPoint:
    def test_str_without_angle(self) -> None:
        assert str(Point(1, 2)) == "(1, 2)"

    def test_str_with_angle(self) -> None:
        assert str(Point(1, 2, 45)) == "(1, 2, a = 45)"

    def test_repr_matches_str(self) -> None:
        p = Point(1, 2, 45)
        assert repr(p) == str(p)

    def test_eq_compares_coordinates_and_angle(self) -> None:
        assert Point(1, 2, 3) == Point(1, 2, 3)
        assert Point(1, 2, 3) != Point(1, 2, 4)
        assert Point(1, 2) != Point(1, 3)

    def test_eq_with_non_point_is_not_equal(self) -> None:
        assert (Point(1, 2) == "not a point") is False
        assert Point(1, 2) != "not a point"

    def test_as_dict_without_angle(self) -> None:
        assert Point(1, 2).as_dict() == {ATTR_X: 1, ATTR_Y: 2}

    def test_as_dict_with_angle(self) -> None:
        assert Point(1, 2, 9).as_dict() == {ATTR_X: 1, ATTR_Y: 2, ATTR_A: 9}

    def test_mul_scales_coordinates_and_keeps_angle(self) -> None:
        result = Point(2, 3, 7) * 2
        assert (result.x, result.y, result.a) == (4, 6, 7)

    def test_truediv_scales_coordinates_and_keeps_angle(self) -> None:
        result = Point(4, 8, 7) / 2
        assert (result.x, result.y, result.a) == (2, 4, 7)

    def test_to_img_and_to_coord_delegate_to_dimensions(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=10)
        p = Point(50, 50)
        img = p.to_img(dims)
        assert img == dims.to_img(p)
        coord = img.to_coord(dims)
        assert coord == dims.to_coord(img)

    @pytest.mark.parametrize(
        ("degree", "expected"),
        [
            (None, (5, 5)),
            (0, (5, 5)),
        ],
    )
    def test_rotated_zero_or_none_degree_is_identity(self, degree: int | None, expected: tuple[int, int]) -> None:
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=1)
        result = Point(5, 5).rotated(dims, degree)
        assert (result.x, result.y) == expected

    def test_rotated_90_degrees_swaps_axes(self) -> None:
        # width=height=10 square: rotating (2, 3) by 90 degrees -> (3, 10 - 2) = (3, 8)
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=1)
        result = Point(2, 3).rotated(dims, 90)
        assert (result.x, result.y) == (3, 8)

    def test_rotated_180_degrees_is_two_successive_90_rotations(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=1)
        once = Point(2, 3).rotated(dims, 90)
        twice = Point(once.x, once.y).rotated(dims, 90)
        combined = Point(2, 3).rotated(dims, 180)
        assert (combined.x, combined.y) == (twice.x, twice.y)

    def test_rotated_270_degrees_is_three_successive_90_rotations(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=1)
        p = Point(2, 3)
        for _ in range(3):
            p = Point(p.x, p.y).rotated(dims, 90)
        combined = Point(2, 3).rotated(dims, 270)
        assert (combined.x, combined.y) == (p.x, p.y)

    def test_rotated_non_multiple_of_90_still_performs_one_swap(self) -> None:
        # degree=45 > 0 so the while loop body executes exactly once before degree goes negative.
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=1)
        rotated_45 = Point(2, 3).rotated(dims, 45)
        rotated_90 = Point(2, 3).rotated(dims, 90)
        assert (rotated_45.x, rotated_45.y) == (rotated_90.x, rotated_90.y)


# ===========================================================================
# Path
# ===========================================================================


class TestPath:
    def test_as_dict_includes_type_when_path_type_set(self) -> None:
        path = Path(1, 2, PathType.SWEEP)
        d = path.as_dict()
        assert d[ATTR_X] == 1
        assert d[ATTR_Y] == 2
        assert d[ATTR_TYPE] == PathType.SWEEP.value

    def test_as_dict_omits_type_when_path_type_is_none(self) -> None:
        path = Path(1, 2, None)  # type: ignore[arg-type]
        d = path.as_dict()
        assert ATTR_TYPE not in d


# ===========================================================================
# Obstacle
# ===========================================================================


class TestObstacleConstruction:
    def test_known_type_resolves_to_enum_member(self) -> None:
        obstacle = Obstacle(1, 2, ObstacleType.SOCK.value, 80)
        assert obstacle.type == ObstacleType.SOCK

    def test_unknown_type_falls_back_to_unknown(self) -> None:
        obstacle = Obstacle(1, 2, 99999, 80)
        assert obstacle.type == ObstacleType.UNKNOWN

    def test_known_picture_and_ignore_status_resolve(self) -> None:
        obstacle = Obstacle(
            1,
            2,
            ObstacleType.TOY.value,
            50,
            picture_status=ObstaclePictureStatus.UPLOADED.value,
            ignore_status=ObstacleIgnoreStatus.MANUALLY_IGNORED.value,
        )
        assert obstacle.picture_status == ObstaclePictureStatus.UPLOADED
        assert obstacle.ignore_status == ObstacleIgnoreStatus.MANUALLY_IGNORED

    def test_unknown_picture_and_ignore_status_fall_back(self) -> None:
        obstacle = Obstacle(1, 2, ObstacleType.TOY.value, 50, picture_status=777, ignore_status=888)
        assert obstacle.picture_status == ObstaclePictureStatus.UNKNOWN
        assert obstacle.ignore_status == ObstacleIgnoreStatus.UNKNOWN

    def test_id_falls_back_to_coordinate_based_id_without_object_id(self) -> None:
        obstacle = Obstacle(3, 4, ObstacleType.TOY.value, 10)
        assert obstacle.id == "0304"

    def test_id_uses_object_id_when_provided(self) -> None:
        obstacle = Obstacle(3, 4, ObstacleType.TOY.value, 10, object_id="abc123")
        assert obstacle.id == "abc123"
        assert obstacle.object_name == "abc123-None"

    def test_object_name_strips_path_and_suffix_from_file_name(self) -> None:
        obstacle = Obstacle(3, 4, ObstacleType.TOY.value, 10, file_name="/data/pics/img1-thumb.jpg")
        assert obstacle.object_name == "0304-img1"

    def test_object_name_uses_whole_file_name_without_slash(self) -> None:
        obstacle = Obstacle(3, 4, ObstacleType.TOY.value, 10, file_name="img1.jpg")
        assert obstacle.object_name == "0304-img1.jpg"


class TestObstacleAsDictAndEq:
    def test_as_dict_includes_optional_fields_when_present(self) -> None:
        obstacle = Obstacle(
            1,
            2,
            ObstacleType.SOCK.value,
            possibility=75,
            picture_status=ObstaclePictureStatus.UPLOADED.value,
            ignore_status=ObstacleIgnoreStatus.NOT_IGNORED.value,
        )
        obstacle.segment = "Living Room"
        d = obstacle.as_dict()
        assert d[ATTR_TYPE] == "Sock"
        assert d["possibility"] == 75
        assert d["picture_status"] == "Uploaded"
        assert d["ignore_status"] == "Not Ignored"
        assert d["room"] == "Living Room"

    def test_eq_compares_all_public_fields(self) -> None:
        a = Obstacle(1, 2, ObstacleType.SOCK.value, 50, object_id="x")
        b = Obstacle(1, 2, ObstacleType.SOCK.value, 50, object_id="x")
        assert a == b
        c = Obstacle(1, 2, ObstacleType.SOCK.value, 99, object_id="x")
        assert a != c

    def test_eq_with_non_obstacle_is_not_equal(self) -> None:
        # NOTE: comparing against a plain Point (rather than an unrelated type) would
        # actually succeed here: Obstacle.__eq__ returns NotImplemented for a non-Obstacle,
        # and since Obstacle *is* a Point subclass, Python then falls back to
        # Point.__eq__(point, obstacle), which only compares x/y/a and matches.
        obstacle = Obstacle(1, 2, ObstacleType.SOCK.value, 50)
        assert (obstacle == "not an obstacle") is False


def _segment_grid_map_data(
    obstacle_segment_pixel: int | None,
    segment_bounds: tuple[float, float, float, float],
    grid_size: float = 1,
) -> MapData:
    """A MapData whose pixel_type/segments/dimensions support Obstacle.set_segment()."""
    md = MapData()
    md.dimensions = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=grid_size)
    x0, y0, x1, y1 = segment_bounds
    segment = Segment(segment_id=7, x0=x0, y0=y0, x1=x1, y1=y1)
    md.segments = {7: segment}
    values: dict[tuple[int, int], int] = {}
    if obstacle_segment_pixel is not None:
        values[(5, 5)] = obstacle_segment_pixel
    md.pixel_type = _PixelGrid(values)
    return md


class TestObstacleSetSegment:
    def test_noop_when_map_data_missing_pieces(self) -> None:
        obstacle = Obstacle(5, 5, ObstacleType.TOY.value, 50)
        obstacle.set_segment(None)  # type: ignore[arg-type]
        assert obstacle.segment is None

        empty_map = MapData()
        obstacle.set_segment(empty_map)
        assert obstacle.segment is None

    def test_noop_when_obstacle_pixel_out_of_bounds(self) -> None:
        md = _segment_grid_map_data(7, (0, 0, 10, 10))
        obstacle = Obstacle(-5, -5, ObstacleType.TOY.value, 50)
        obstacle.set_segment(md)
        assert obstacle.segment is None

    def test_direct_pixel_hit_assigns_segment_by_id(self) -> None:
        md = _segment_grid_map_data(7, (0, 0, 10, 10))
        md.segments[7].color_index = 3
        obstacle = Obstacle(5, 5, ObstacleType.TOY.value, 50)
        obstacle.set_segment(md)
        assert obstacle.segment == md.segments[7].name
        assert obstacle.color_index == 3

    def test_falls_back_to_bounding_box_check_when_pixel_not_a_segment_id(self) -> None:
        # Pixel value 255 (WALL) is not itself a key in md.segments, so set_segment()
        # falls back to scanning segments for one whose bounding box contains the point.
        md = _segment_grid_map_data(255, (0, 0, 10, 10))
        md.segments[7].color_index = 9
        obstacle = Obstacle(5, 5, ObstacleType.TOY.value, 50)
        obstacle.set_segment(md)
        assert obstacle.segment == md.segments[7].name
        assert obstacle.color_index == 9

    def test_segment_stays_none_when_no_bounding_box_matches(self) -> None:
        md = _segment_grid_map_data(255, (100, 100, 110, 110))
        obstacle = Obstacle(5, 5, ObstacleType.TOY.value, 50)
        obstacle.set_segment(md)
        assert obstacle.segment is None


# ===========================================================================
# Zone
# ===========================================================================


class TestZone:
    def test_str_and_repr(self) -> None:
        z = Zone(1, 2, 3, 4)
        assert str(z) == "[1, 2, 3, 4]"
        assert repr(z) == str(z)

    def test_eq(self) -> None:
        assert Zone(1, 2, 3, 4) == Zone(1, 2, 3, 4)
        assert Zone(1, 2, 3, 4) != Zone(1, 2, 3, 5)
        assert (Zone(1, 2, 3, 4) == "nope") is False

    def test_as_dict(self) -> None:
        assert Zone(1, 2, 3, 4).as_dict() == {"x0": 1, "y0": 2, "x1": 3, "y1": 4}

    def test_as_area_maps_corners_correctly(self) -> None:
        area = Zone(0, 0, 10, 20).as_area()
        assert (area.x0, area.y0) == (0, 0)
        assert (area.x1, area.y1) == (0, 20)
        assert (area.x2, area.y2) == (10, 20)
        assert (area.x3, area.y3) == (10, 0)

    def test_to_img_and_to_coord(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=1)
        zone = Zone(1, 1, 5, 5)
        img = zone.to_img(dims)
        assert isinstance(img, Zone)
        back = img.to_coord(dims)
        assert (round(back.x0), round(back.y0), round(back.x1), round(back.y1)) == (1, 1, 5, 5)

    def test_check_point_uses_bounding_box_with_margin(self) -> None:
        zone = Zone(0, 0, 10, 10)
        assert zone.check_point(5, 5, 0) is True
        assert zone.check_point(-1, 5, 0) is False
        assert zone.check_point(-1, 5, 2) is True


# ===========================================================================
# Segment
# ===========================================================================


class TestSegmentNaming:
    def test_known_type_sets_name_from_lookup(self) -> None:
        segment = Segment(segment_id=1, type=4)  # Kitchen
        assert segment.name == "Kitchen"

    def test_known_type_with_index_appends_number(self) -> None:
        segment = Segment(segment_id=1, type=4, index=1)  # second kitchen
        assert segment.name == "Kitchen 2"

    def test_custom_name_used_when_type_unknown(self) -> None:
        segment = Segment(segment_id=2, type=0, custom_name="Man Cave")
        assert segment.name == "Man Cave"

    def test_falls_back_to_room_number_without_type_or_custom_name(self) -> None:
        segment = Segment(segment_id=9, type=0)
        assert segment.name == "Room 9"

    def test_custom_name_matching_pattern_overrides_icon(self) -> None:
        segment = Segment(segment_id=1, type=0, custom_name="Garage du bas")
        assert segment.icon == "mdi:garage"

    def test_default_icon_from_type_lookup(self) -> None:
        segment = Segment(segment_id=1, type=4)  # Kitchen
        assert segment.icon == "mdi:chef-hat"

    def test_unknown_type_default_icon(self) -> None:
        segment = Segment(segment_id=1, type=999)
        assert segment.icon == "mdi:home-outline"


class TestSegmentTranslatedName:
    def test_custom_name_wins_over_translation(self) -> None:
        segment = Segment(segment_id=1, type=4, custom_name="Cuisine perso")
        assert segment.get_translated_name("fr") == "Cuisine perso"

    def test_translated_name_for_known_type_with_index(self) -> None:
        segment = Segment(segment_id=1, type=4, index=1)  # second kitchen
        assert segment.get_translated_name("fr") == "Cuisine 2"

    def test_translated_name_for_type_zero(self) -> None:
        segment = Segment(segment_id=1, type=0)
        assert segment.get_translated_name("fr") == "Pièce"

    def test_falls_back_to_english_name_for_unknown_language(self) -> None:
        segment = Segment(segment_id=1, type=4)
        assert segment.get_translated_name("xx") == segment.name

    def test_falls_back_to_english_name_when_language_none(self) -> None:
        segment = Segment(segment_id=1, type=4)
        assert segment.get_translated_name(None) == segment.name


class TestSegmentIconType:
    def test_remaps_bathroom_type_6_to_bathtub_16(self) -> None:
        segment = Segment(segment_id=1, type=6)
        assert segment.icon_type == 16

    def test_custom_name_toilet_pattern_keeps_toilet_icon_type(self) -> None:
        segment = Segment(segment_id=1, type=6, custom_name="Toilet")
        assert segment.icon_type == 6

    def test_custom_name_bathroom_pattern_forces_bathtub_type(self) -> None:
        segment = Segment(segment_id=1, type=0, custom_name="Bathroom")
        assert segment.icon_type == 16

    def test_other_types_pass_through_unchanged(self) -> None:
        segment = Segment(segment_id=1, type=4)
        assert segment.icon_type == 4


class TestSegmentMopPadHumidityAndCustomCarpetSettings:
    def test_mop_pad_humidity_mirrors_water_volume(self) -> None:
        segment = Segment(segment_id=1, water_volume=2)
        assert segment.mop_pad_humidity == 2

    def test_set_custom_carpet_settings(self) -> None:
        segment = Segment(segment_id=1)
        segment.set_custom_carpet_settings(1, 5)
        assert segment.carpet_cleaning == 1
        assert segment.carpet_settings == 5


class TestSegmentOutlineCenterLetter:
    def test_outline_uses_custom_points_when_provided(self) -> None:
        segment = Segment(segment_id=1, outline_points=[[0, 0], [0, 5], [5, 5], [5, 0]])
        assert segment.outline == [[0, 0], [0, 5], [5, 5], [5, 0]]

    def test_outline_falls_back_to_bounding_box(self) -> None:
        segment = Segment(segment_id=1, x0=0, y0=0, x1=5, y1=5)
        assert segment.outline == [[0, 0], [0, 5], [5, 5], [5, 0]]

    def test_center_returns_x_y_pair(self) -> None:
        segment = Segment(segment_id=1, x=3, y=4)
        assert segment.center == [3, 4]

    def test_letter_for_id_within_first_alphabet_pass(self) -> None:
        segment = Segment(segment_id=1)
        assert segment.letter == "A"

    def test_letter_for_id_beyond_26_wraps_with_number_suffix(self) -> None:
        segment = Segment(segment_id=27)
        assert segment.letter == "A1"


class TestSegmentNameListAndNextTypeIndex:
    def test_next_type_index_counts_consecutive_same_type_segments(self) -> None:
        other1 = Segment(segment_id=1, type=1, index=0)
        other2 = Segment(segment_id=2, type=1, index=1)
        target = Segment(segment_id=3, type=1)
        segments = {1: other1, 2: other2, 3: target}
        assert target.next_type_index(1, segments) == 2

    def test_next_type_index_zero_for_type_zero(self) -> None:
        target = Segment(segment_id=1, type=0)
        assert target.next_type_index(0, {1: target}) == 0

    def test_name_list_maps_names_to_type_codes(self) -> None:
        segment = Segment(segment_id=1, type=4)  # Kitchen
        segments = {1: segment}
        result = segment.name_list(segments)
        assert result["Kitchen"] == 4
        assert result["Living Room"] == 1

    def test_name_list_uses_translations_when_language_given(self) -> None:
        segment = Segment(segment_id=1, type=4)
        result = segment.name_list({1: segment}, language="fr")
        assert result["Cuisine"] == 4

    def test_name_list_includes_custom_name_as_room_zero(self) -> None:
        segment = Segment(segment_id=5, type=0, custom_name="Custom Room")
        result = segment.name_list({5: segment})
        assert result["Custom Room"] == 0

    def test_name_list_appends_index_suffix_for_repeated_types(self) -> None:
        """When two other segments already occupy type=1 (Living Room) indices 0 and 1,
        the generic name_list loop should suffix the next available index.
        """
        other1 = Segment(segment_id=1, type=1, index=0)
        other2 = Segment(segment_id=2, type=1, index=1)
        target = Segment(segment_id=3, type=4)
        segments = {1: other1, 2: other2, 3: target}
        result = target.name_list(segments)
        assert result["Living Room 3"] == 1


class TestSegmentAsDict:
    def test_includes_core_fields(self) -> None:
        segment = Segment(
            segment_id=3,
            x0=0,
            y0=0,
            x1=10,
            y1=10,
            order=2,
            cleaning_times=1,
            suction_level=2,
            water_volume=1,
            type=4,
        )
        segment.color_index = 5
        segment.unique_id = "u1"
        d = segment.as_dict()
        assert d[ATTR_ROOM_ID] == 3
        assert d["order"] == 2
        assert d["cleaning_times"] == 1
        assert d["suction_level"] == 2
        assert d["water_volume"] == 1
        assert d["color_index"] == 5
        assert d["unique_id"] == "u1"

    def test_custom_outline_overrides_dict_outline_key(self) -> None:
        segment = Segment(segment_id=1, outline_points=[[1, 1], [2, 2]])
        d = segment.as_dict()
        assert d["outline"] == [[1, 1], [2, 2]]

    def test_wetness_level_included_only_for_wetness_cleanset_types(self) -> None:
        segment = Segment(segment_id=1)
        segment.wetness_level = 3
        segment.cleanset_type = CleansetType.WETNESS_LEVEL
        assert segment.as_dict()[ATTR_WETNESS_LEVEL] == 3

        segment.cleanset_type = CleansetType.WETNESS_LEVEL_MAX_15
        assert segment.as_dict()[ATTR_WETNESS_LEVEL] == 3

        segment.cleanset_type = CleansetType.NONE
        assert ATTR_WETNESS_LEVEL not in segment.as_dict()

    def test_cleaning_mode_excluded_when_cleanset_type_default(self) -> None:
        segment = Segment(segment_id=1, cleaning_mode=2)
        segment.cleanset_type = CleansetType.DEFAULT
        assert ATTR_CLEANING_MODE not in segment.as_dict()
        segment.cleanset_type = CleansetType.CLEANING_MODE
        assert segment.as_dict()[ATTR_CLEANING_MODE] == 2

    def test_custom_mopping_route_vs_cleaning_route_are_mutually_exclusive_in_dict(self) -> None:
        segment = Segment(segment_id=1)
        segment.custom_mopping_route = 1
        segment.cleaning_route = 2
        segment.cleanset_type = CleansetType.CUSTOM_MOPPING_ROUTE
        d = segment.as_dict()
        assert d[ATTR_CUSTOM_MOPPING_ROUTE] == 1
        assert ATTR_CLEANING_ROUTE not in d

        segment.cleanset_type = CleansetType.CLEANING_ROUTE
        d2 = segment.as_dict()
        assert d2[ATTR_CLEANING_ROUTE] == 2
        assert ATTR_CUSTOM_MOPPING_ROUTE not in d2

    def test_floor_material_direction_and_visibility_are_titled_enum_names(self) -> None:
        segment = Segment(segment_id=1)
        segment.floor_material = 1
        segment.floor_material_rotated_direction = DreameVacuumFloorMaterialDirection.VERTICAL.value
        segment.visibility = DreameVacuumSegmentVisibility.VISIBLE.value
        d = segment.as_dict()
        assert d["floor_material"] == 1
        assert d["floor_material_direction"] == "Vertical"
        assert d["visibility"] == "Visible"

    def test_x_y_included_when_both_present(self) -> None:
        segment = Segment(segment_id=1, x=3, y=4)
        d = segment.as_dict()
        assert d[ATTR_X] == 3
        assert d[ATTR_Y] == 4

    def test_custom_name_included_when_set(self) -> None:
        segment = Segment(segment_id=1, custom_name="Office")
        assert segment.as_dict()[ATTR_CUSTOM_NAME] == "Office"


class TestSegmentEq:
    def _base(self, **overrides: Any) -> Segment:
        kwargs = {"segment_id": 1, "x0": 0, "y0": 0, "x1": 10, "y1": 10, "type": 4}
        kwargs.update(overrides)
        return Segment(**kwargs)

    def test_equal_segments(self) -> None:
        assert self._base() == self._base()

    def test_differs_by_suction_level(self) -> None:
        assert self._base() != self._base(suction_level=3)

    def test_differs_by_neighbors(self) -> None:
        assert self._base(neighbors=[1, 2]) != self._base(neighbors=[3])

    def test_not_equal_to_non_segment(self) -> None:
        # A same-bounds Zone would trigger Zone.__eq__ via NotImplemented fallback
        # (Segment is a Zone subclass), so use a wholly unrelated type instead.
        assert (self._base() == "not a segment") is False

    def test_str_and_repr_include_room_id_and_outline(self) -> None:
        segment = self._base()
        assert "room_id: 1" in str(segment)
        assert repr(segment) == str(segment)


# ===========================================================================
# Wall
# ===========================================================================


class TestWall:
    def test_str_and_repr(self) -> None:
        wall = Wall(1, 2, 3, 4)
        assert str(wall) == "[1, 2, 3, 4]"
        assert repr(wall) == str(wall)

    def test_eq(self) -> None:
        assert Wall(1, 2, 3, 4) == Wall(1, 2, 3, 4)
        assert (Wall(1, 2, 3, 4) == "nope") is False

    def test_as_dict_and_as_list(self) -> None:
        wall = Wall(1, 2, 3, 4)
        assert wall.as_dict() == {"x0": 1, "y0": 2, "x1": 3, "y1": 4}
        assert wall.as_list() == [1, 2, 3, 4]

    def test_to_img_and_to_coord_roundtrip(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=1)
        wall = Wall(1, 1, 5, 5)
        img = wall.to_img(dims)
        back = img.to_coord(dims)
        assert (round(back.x0), round(back.y0), round(back.x1), round(back.y1)) == (1, 1, 5, 5)


# ===========================================================================
# Area
# ===========================================================================


class TestArea:
    def test_str_repr_as_dict_as_list(self) -> None:
        area = Area(0, 0, 0, 10, 10, 10, 10, 0)
        assert str(area) == "[0, 0, 0, 10, 10, 10, 10, 0]"
        assert repr(area) == str(area)
        assert area.as_dict()["x2"] == 10
        assert area.as_list() == [0, 0, 0, 10, 10, 10, 10, 0]

    def test_eq(self) -> None:
        a = Area(0, 0, 0, 10, 10, 10, 10, 0)
        b = Area(0, 0, 0, 10, 10, 10, 10, 0)
        assert a == b
        assert (a == "nope") is False
        c = Area(0, 0, 0, 10, 10, 10, 10, 5)
        assert a != c

    def test_check_size(self) -> None:
        # check_size assumes the (x0,y0)=top-left, (x1,y1)=top-right, (x2,y2)=bottom-right,
        # (x3,y3)=bottom-left corner convention (x2-x0=width, y2-y1=height). Note this is a
        # *different* corner order than Zone.as_area() produces (see test_as_area_maps_corners_correctly),
        # so check_size() on a Zone-derived Area is unreliable — a real inconsistency in this module.
        area = Area(0, 0, 10, 0, 10, 10, 0, 10)
        assert area.check_size(10) is True
        assert area.check_size(5) is False

    def test_check_point_inside_and_outside_bounds(self) -> None:
        area = Area(0, 0, 0, 10, 10, 10, 10, 0)
        assert area.check_point(5, 5, 0) is True
        assert area.check_point(-1, 5, 0) is False
        assert area.check_point(-1, 5, 2) is True

    def test_to_coord_maps_all_four_corners(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=1)
        area = Area(1, 1, 1, 5, 5, 5, 5, 1)
        img = area.to_img(dims)
        back = img.to_coord(dims)
        assert round(back.x0) == 1
        assert round(back.y2) == 5

    def test_to_img_without_angle_maps_corners_directly(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=1)
        area = Area(0, 0, 0, 4, 4, 4, 4, 0)  # angle=0 -> falsy -> "else" branch
        img = area.to_img(dims)
        assert isinstance(img, Area)

    def test_to_img_with_angle_rotates_around_center(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=20, width=20, grid_size=1)
        # A square centered at (10, 10); rotating 90 degrees should keep the same center.
        area = Area(5, 5, 5, 15, 15, 15, 15, 5, angle=90)
        img = area.to_img(dims)
        # Rotation keeps shape bounds close to a similarly-sized square around the same center.
        cx_before = (area.x0 + area.x1 + area.x2 + area.x3) / 4
        cy_before = (area.y0 + area.y1 + area.y2 + area.y3) / 4
        coord_back = img.to_coord(dims)
        cx_after = (coord_back.x0 + coord_back.x1 + coord_back.x2 + coord_back.x3) / 4
        cy_after = (coord_back.y0 + coord_back.y1 + coord_back.y2 + coord_back.y3) / 4
        assert round(cx_after) == round(cx_before)
        assert round(cy_after) == round(cy_before)


# ===========================================================================
# Furniture
# ===========================================================================


class TestFurniture:
    def test_computes_corners_from_origin_width_height(self) -> None:
        furniture = Furniture(x=5, y=5, x0=1, y0=1, width=10, height=4, type=FurnitureType.COFFEE_TABLE, size_type=1)
        assert (furniture.x1, furniture.y1) == (11, 1)
        assert (furniture.x2, furniture.y2) == (11, 5)
        assert (furniture.x3, furniture.y3) == (1, 5)

    def test_corners_none_when_dimensions_missing(self) -> None:
        furniture = Furniture(x=5, y=5, x0=1, y0=1, width=0, height=0, type=FurnitureType.COFFEE_TABLE, size_type=1)
        assert furniture.x1 is None
        assert furniture.y3 is None

    def test_corners_computed_when_origin_is_zero(self) -> None:
        """Regression test for a real bug: the guard used to be
        ``if x0 and y0 and width and height``, which relies on truthiness, so a
        legitimate origin of x0=0 or y0=0 was treated the same as "missing" and the
        corners silently stayed None even though width/height were set. Fixed to use
        ``is not None`` for the origin coordinates (width/height keep the truthiness
        check — 0 is the real "no dimension data" sentinel from the decoder).
        """
        furniture = Furniture(x=5, y=5, x0=0, y0=0, width=10, height=4, type=FurnitureType.COFFEE_TABLE, size_type=1)
        assert (furniture.x1, furniture.y1) == (10, 0)
        assert (furniture.x2, furniture.y2) == (10, 4)
        assert (furniture.x3, furniture.y3) == (0, 4)

    def test_as_dict_includes_corners_and_metadata(self) -> None:
        furniture = Furniture(
            x=5,
            y=5,
            x0=1,
            y0=1,
            width=10,
            height=4,
            type=FurnitureType.COFFEE_TABLE,
            size_type=1,
            angle=90,
            scale=1.5,
            segment_id=3,
        )
        d = furniture.as_dict()
        assert d[ATTR_TYPE] == "Coffee Table"
        assert d[ATTR_ROOM_ID] == 3
        assert d[ATTR_ANGLE] == 90
        assert d["scale"] == 1.5
        assert d["width"] == 10
        assert d["height"] == 4
        assert (d["x0"], d["y0"]) == (1, 1)
        assert (d["x1"], d["y1"]) == (11, 1)

    def test_eq_ignores_segment_id(self) -> None:
        a = Furniture(x=1, y=1, x0=0, y0=0, width=2, height=2, type=FurnitureType.TOILET, size_type=1)
        b = Furniture(x=1, y=1, x0=0, y0=0, width=2, height=2, type=FurnitureType.TOILET, size_type=1, segment_id=99)
        assert a == b

    def test_eq_differs_by_angle(self) -> None:
        a = Furniture(x=1, y=1, x0=0, y0=0, width=2, height=2, type=FurnitureType.TOILET, size_type=1, angle=0)
        b = Furniture(x=1, y=1, x0=0, y0=0, width=2, height=2, type=FurnitureType.TOILET, size_type=1, angle=90)
        assert a != b

    def test_eq_with_non_furniture_is_not_equal(self) -> None:
        # A plain Point would fall back to Point.__eq__ via NotImplemented (Furniture is
        # a Point subclass), so use a wholly unrelated type instead.
        furniture = Furniture(x=1, y=1, x0=0, y0=0, width=2, height=2, type=FurnitureType.TOILET, size_type=1)
        assert (furniture == "not a furniture") is False


# ===========================================================================
# Coordinate
# ===========================================================================


class TestCoordinate:
    def test_as_dict(self) -> None:
        coord = Coordinate(1, 2, completed=True, type=3)
        assert coord.as_dict() == {ATTR_X: 1, ATTR_Y: 2, ATTR_TYPE: 3, "completed": True}

    def test_eq(self) -> None:
        assert Coordinate(1, 2, True, 3) == Coordinate(1, 2, True, 3)
        assert Coordinate(1, 2, True, 3) != Coordinate(1, 2, False, 3)
        assert (Coordinate(1, 2, True, 3) == "nope") is False


# ===========================================================================
# Carpet / Polygon
# ===========================================================================


class TestCarpet:
    def test_ellipse_string_and_int_forms_normalize_to_bool(self) -> None:
        assert Carpet(1, 0, 0, 0, 10, 10, 10, 10, 0, ellipse="1").ellipse is True
        assert Carpet(1, 0, 0, 0, 10, 10, 10, 10, 0, ellipse=1).ellipse is True
        assert Carpet(1, 0, 0, 0, 10, 10, 10, 10, 0, ellipse="0").ellipse is False
        assert Carpet(1, 0, 0, 0, 10, 10, 10, 10, 0, ellipse=None).ellipse is None

    def test_eq_ignores_x1_y1_x3_y3_and_angle(self) -> None:
        """Documents current behaviour: Carpet equality only checks the x0/y0/x2/y2 diagonal."""
        a = Carpet(1, 0, 0, 1, 1, 10, 10, 9, 9)
        b = Carpet(1, 0, 0, 99, 99, 10, 10, 1, 1)
        assert a == b

    def test_eq_differs_by_carpet_type(self) -> None:
        a = Carpet(1, 0, 0, 1, 1, 10, 10, 9, 9, carpet_type=1)
        b = Carpet(1, 0, 0, 1, 1, 10, 10, 9, 9, carpet_type=2)
        assert a != b

    def test_eq_with_non_carpet_is_not_equal(self) -> None:
        carpet = Carpet(1, 0, 0, 0, 10, 10, 10, 10, 0)
        assert (carpet == Point(0, 0)) is False

    def test_set_custom_carpet_settings(self) -> None:
        carpet = Carpet(1, 0, 0, 0, 10, 10, 10, 10, 0)
        carpet.set_custom_carpet_settings(2, 5)
        assert carpet.carpet_cleaning == 2
        assert carpet.carpet_settings == 5


class TestPolygon:
    def test_eq_ignores_x1_y1_x3_y3(self) -> None:
        a = Polygon(1, 0, 0, 1, 1, 10, 10, 9, 9, polygon=[0, 0, 10, 10])
        b = Polygon(1, 0, 0, 99, 99, 10, 10, 1, 1, polygon=[0, 0, 10, 10])
        assert a == b

    def test_eq_differs_by_polygon_points(self) -> None:
        a = Polygon(1, 0, 0, 1, 1, 10, 10, 9, 9, polygon=[0, 0, 10, 10])
        b = Polygon(1, 0, 0, 1, 1, 10, 10, 9, 9, polygon=[0, 0, 5, 5])
        assert a != b

    def test_eq_differs_by_hidden_or_type(self) -> None:
        a = Polygon(1, 0, 0, 1, 1, 10, 10, 9, 9, polygon=[], type=0, hidden=None)
        b = Polygon(1, 0, 0, 1, 1, 10, 10, 9, 9, polygon=[], type=1, hidden=2)
        assert a != b

    def test_eq_with_non_polygon_is_not_equal(self) -> None:
        polygon = Polygon(1, 0, 0, 1, 1, 10, 10, 9, 9, polygon=[])
        assert (polygon == Point(0, 0)) is False


# ===========================================================================
# MapImageDimensions
# ===========================================================================


class TestMapImageDimensions:
    def test_to_img_applies_scale_padding_and_crop(self) -> None:
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=1)
        dims.scale = 2
        dims.padding = [3, 4, 0, 0]
        dims.crop = [1, 1, 0, 0]
        img = dims.to_img(Point(2, 3))
        # x: ((2-0)/1)*2 + 3 - 1 = 6 ; y: (((10*1-1)-(3-0))/1)*2 + 4 - 1 = 6*2+3 = 15
        assert (img.x, img.y) == (6, 15)

    def test_to_coord_ignores_scale_padding_and_crop(self) -> None:
        """to_coord always returns raw grid-cell coordinates: unlike to_img it never
        applies ``scale``/``padding``/``crop``.
        """
        dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=1)
        dims.scale = 2
        dims.padding = [3, 4, 0, 0]
        dims.crop = [1, 1, 0, 0]
        coord = dims.to_coord(Point(2, 3))
        # x: (2-0)/1 = 2 ; y: ((10*1-1)-(3-0))/1 = 6
        assert (coord.x, coord.y) == (2, 6)

    def test_to_img_without_offset_adjusts_when_not_grid_aligned(self) -> None:
        dims = MapImageDimensions(top=5, left=5, height=20, width=20, grid_size=10)  # 5 % 10 != 0
        point = Point(150, 250)
        with_offset = dims.to_img(point, offset=True)
        without_offset = dims.to_img(point, offset=False)
        assert (with_offset.x, with_offset.y) != (without_offset.x, without_offset.y)

    def test_to_coord_without_offset_adjusts_when_not_grid_aligned(self) -> None:
        dims = MapImageDimensions(top=5, left=5, height=20, width=20, grid_size=10)
        point = Point(150, 250)
        with_offset = dims.to_coord(point, offset=True)
        without_offset = dims.to_coord(point, offset=False)
        assert (with_offset.x, with_offset.y) != (without_offset.x, without_offset.y)

    def test_eq_compares_geometry_fields_only(self) -> None:
        a = MapImageDimensions(top=1, left=2, height=3, width=4, grid_size=5)
        b = MapImageDimensions(top=1, left=2, height=3, width=4, grid_size=5)
        assert a == b
        c = MapImageDimensions(top=1, left=2, height=3, width=4, grid_size=6)
        assert a != c
        assert (a == "nope") is False


# ===========================================================================
# CleaningHistory
# ===========================================================================


def _hist(prop: DreameVacuumProperty, value: Any, key: str = "value") -> dict[str, Any]:
    return {"piid": PIID(prop, DreameVacuumPropertyMapping), key: value}


class TestCleaningHistory:
    def test_parses_known_status_suction_and_water_tank(self) -> None:
        history = CleaningHistory(
            [
                _hist(DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value),
                _hist(DreameVacuumProperty.SUCTION_LEVEL, DreameVacuumSuctionLevel.STRONG.value),
                _hist(DreameVacuumProperty.WATER_TANK, DreameVacuumWaterTank.INSTALLED.value),
                _hist(DreameVacuumProperty.CLEANING_TIME, 120),
                _hist(DreameVacuumProperty.CLEANED_AREA, 15),
            ],
            DreameVacuumPropertyMapping,
        )
        assert history.status == DreameVacuumStatus.CLEANING
        assert history.suction_level == DreameVacuumSuctionLevel.STRONG
        assert history.water_tank_or_mop == DreameVacuumWaterTank.INSTALLED
        assert history.cleaning_time == 120
        assert history.cleaned_area == 15

    def test_unknown_status_suction_and_water_tank_fall_back(self) -> None:
        history = CleaningHistory(
            [
                _hist(DreameVacuumProperty.STATUS, 987654),
                _hist(DreameVacuumProperty.SUCTION_LEVEL, 987654),
                _hist(DreameVacuumProperty.WATER_TANK, 987654),
            ],
            DreameVacuumPropertyMapping,
        )
        assert history.status == DreameVacuumStatus.UNKNOWN
        assert history.suction_level == DreameVacuumSuctionLevel.UNKNOWN
        assert history.water_tank_or_mop == DreameVacuumWaterTank.UNKNOWN

    def test_parses_start_time_as_datetime(self) -> None:
        history = CleaningHistory(
            [_hist(DreameVacuumProperty.CLEANING_START_TIME, 1700000000)], DreameVacuumPropertyMapping
        )
        assert history.date == datetime.fromtimestamp(1700000000)

    def test_file_name_with_comma_splits_object_name_and_key(self) -> None:
        history = CleaningHistory(
            [_hist(DreameVacuumProperty.CLEAN_LOG_FILE_NAME, "obj-1,key-1")], DreameVacuumPropertyMapping
        )
        assert history.object_name == "obj-1"
        assert history.key == "key-1"

    def test_file_name_without_comma_is_used_as_is(self) -> None:
        history = CleaningHistory(
            [_hist(DreameVacuumProperty.CLEAN_LOG_FILE_NAME, "solofile")], DreameVacuumPropertyMapping
        )
        assert history.object_name == "solofile"
        assert history.key is None

    def test_completed_flag_and_val_key_fallback(self) -> None:
        history = CleaningHistory(
            [_hist(DreameVacuumProperty.CLEAN_LOG_STATUS, 1, key="val")], DreameVacuumPropertyMapping
        )
        assert history.completed is True

    def test_map_index_and_map_name_and_cruise_type(self) -> None:
        history = CleaningHistory(
            [
                _hist(DreameVacuumProperty.MAP_INDEX, 2),
                _hist(DreameVacuumProperty.MAP_NAME, "Floor 1"),
                _hist(DreameVacuumProperty.CRUISE_TYPE, 1),
            ],
            DreameVacuumPropertyMapping,
        )
        assert history.map_index == 2
        assert history.map_name == "Floor 1"
        assert history.cruise_type == 1

    def test_cleaning_properties_parses_cmc_and_simple_fields(self) -> None:
        props = json.dumps(
            {
                "cmc": CleanupMethod.CUSTOMIZED_CLEANING.value,
                "ismultiple": 1,
                "ctyo": 2,
                "mooClean": 1,
                "multime": "3",
                "pet": 1,
                "cleanagain": 0,
            }
        )
        history = CleaningHistory([_hist(DreameVacuumProperty.CLEANING_PROPERTIES, props)], DreameVacuumPropertyMapping)
        assert history.cleanup_method == CleanupMethod.CUSTOMIZED_CLEANING
        assert history.second_cleaning == 1
        assert history.second_mopping == 2
        assert history.mopping_mode == 1
        assert history.multiple_cleaning_time == "3"
        assert history.pet_focused_cleaning == 1
        assert history.clean_again == 0

    def test_cleaning_properties_unknown_cmc_falls_back_to_other(self) -> None:
        props = json.dumps({"cmc": 555})
        history = CleaningHistory([_hist(DreameVacuumProperty.CLEANING_PROPERTIES, props)], DreameVacuumPropertyMapping)
        assert history.cleanup_method == CleanupMethod.OTHER

    def test_cleaning_properties_abnormal_end_parses_task_interrupt_reason(self) -> None:
        props = json.dumps({"abnormal_end": json.dumps([TaskInterruptReason.ROBOT_LIFTED.value, 0])})
        history = CleaningHistory([_hist(DreameVacuumProperty.CLEANING_PROPERTIES, props)], DreameVacuumPropertyMapping)
        assert history.task_interrupt_reason == TaskInterruptReason.ROBOT_LIFTED

    def test_cleaning_properties_abnormal_end_unknown_reason_falls_back(self) -> None:
        props = json.dumps({"abnormal_end": json.dumps([999999, 0])})
        history = CleaningHistory([_hist(DreameVacuumProperty.CLEANING_PROPERTIES, props)], DreameVacuumPropertyMapping)
        assert history.task_interrupt_reason == TaskInterruptReason.UNKNOWN

    def test_cleaning_properties_area_clean_detail_parses_neglected_segments(self) -> None:
        detail = json.dumps([[1, SegmentNeglectReason.BLOCKED_BY_CARPET.value], [2, 999999]])
        props = json.dumps({"area_clean_detail": detail})
        history = CleaningHistory([_hist(DreameVacuumProperty.CLEANING_PROPERTIES, props)], DreameVacuumPropertyMapping)
        # Segment 2's reason code isn't a valid SegmentNeglectReason, so it's dropped.
        assert history.neglected_segments == {1: SegmentNeglectReason.BLOCKED_BY_CARPET}

    def test_cleaning_properties_area_clean_detail_single_char_is_ignored(self) -> None:
        props = json.dumps({"area_clean_detail": "[]"[:1]})
        history = CleaningHistory([_hist(DreameVacuumProperty.CLEANING_PROPERTIES, props)], DreameVacuumPropertyMapping)
        assert history.neglected_segments is None


# ===========================================================================
# RecoveryMapInfo
# ===========================================================================


class TestRecoveryMapInfo:
    def test_constructs_fields_and_resolves_known_map_type(self) -> None:
        info = RecoveryMapInfo(
            map_id=1,
            date=1700000000.0,
            raw_map="raw",
            map_object_name="obj",
            object_name="name",
            map_type=RecoveryMapType.BACKUP.value,
        )
        assert info.date == datetime.fromtimestamp(1700000000.0)
        assert info.map_type == RecoveryMapType.BACKUP
        assert info.map_data is None
        assert info.map_name is None

    def test_unknown_map_type_falls_back_to_unknown(self) -> None:
        info = RecoveryMapInfo(1, 1700000000.0, "raw", "obj", "name", map_type=999999)
        assert info.map_type == RecoveryMapType.UNKNOWN

    def test_date_none_when_timestamp_falsy(self) -> None:
        info = RecoveryMapInfo(1, None, "raw", "obj", "name", map_type=0)
        assert info.date is None

    def test_as_dict_with_date_present(self) -> None:
        info = RecoveryMapInfo(1, 1700000000.0, "raw", "obj", "name", map_type=RecoveryMapType.ORIGINAL.value)
        d = info.as_dict()
        assert d is not None
        assert d["map_type"] == "Original"
        assert d["object_name"] == "name"

    def test_as_dict_returns_none_without_date(self) -> None:
        info = RecoveryMapInfo(1, None, "raw", "obj", "name", map_type=0)
        assert info.as_dict() is None

    def test_eq_compares_date_map_id_and_object_name(self) -> None:
        """Regression test for a real bug: __eq__'s body used to be written as an
        "is different" check (``or``-chain of ``!=``) rather than negated like every
        sibling class in this module, so identical instances compared unequal and
        differing instances compared equal. Fixed to normal equality semantics.
        """
        a = RecoveryMapInfo(1, 1700000000.0, "raw", "obj", "name", map_type=0)
        b = RecoveryMapInfo(1, 1700000000.0, "raw", "obj", "name", map_type=0)
        assert (a == b) is True  # identical instances compare equal

        c = RecoveryMapInfo(2, 1700000000.0, "raw", "obj", "different-name", map_type=0)
        assert (a == c) is False  # differing instances compare unequal

    def test_eq_with_non_recovery_map_info_is_not_equal(self) -> None:
        info = RecoveryMapInfo(1, 1700000000.0, "raw", "obj", "name", map_type=0)
        assert (info == Point(0, 0)) is False

    def test_dict_property_reflects_fields_when_date_present(self) -> None:
        info = RecoveryMapInfo(1, 1700000000.0, "raw", "map-obj", "name", map_type=0)
        assert info.__dict__ == {
            "date": info.date,
            "map_id": 1,
            "object_name": "name",
            "map_object_name": "map-obj",
        }

    def test_dict_property_empty_without_date(self) -> None:
        info = RecoveryMapInfo(1, None, "raw", "obj", "name", map_type=0)
        assert info.__dict__ == {}


class TestMapDataPartial:
    def test_defaults(self) -> None:
        partial = MapDataPartial()
        assert partial.map_id is None
        assert partial.frame_id is None
        assert partial.frame_type is None
        assert partial.timestamp_ms is None
        assert partial.raw is None
        assert partial.data_json == {}


# ===========================================================================
# MapData — __eq__
# ===========================================================================


def _map_data(**overrides: Any) -> MapData:
    md = MapData()
    for key, value in overrides.items():
        setattr(md, key, value)
    return md


class TestMapDataEq:
    def test_not_equal_to_non_map_data(self) -> None:
        assert (_map_data() == Point(0, 0)) is False

    def test_default_instances_are_equal(self) -> None:
        assert _map_data() == _map_data()

    @pytest.mark.parametrize(
        "field",
        [
            "map_id",
            "custom_name",
            "rotation",
            "work_status",
            "no_go_areas",
            "no_mopping_areas",
            "carpets",
            "ignored_carpets",
            "detected_carpets",
            "virtual_walls",
            "virtual_thresholds",
            "passable_thresholds",
            "impassable_thresholds",
            "ramps",
            "low_lying_areas",
            "curtains",
            "docked",
            "active_segments",
            "active_areas",
            "active_points",
            "active_cruise_points",
            "clean_log",
            "saved_map_status",
            "restored_map",
            "frame_map",
            "temporary_map",
            "saved_map",
            "new_map",
            "cleanset",
            "sequence",
            "carpet_cleanset",
            "furnitures",
            "saved_furnitures",
            "obstacles",
            "predefined_points",
            "hidden_segments",
        ],
    )
    def test_differs_when_single_field_changes(self, field: str) -> None:
        a = _map_data(**{field: "value-a"})
        b = _map_data(**{field: "value-b"})
        assert a != b

    def test_differs_by_robot_position(self) -> None:
        a = _map_data(robot_position=Point(1, 1))
        b = _map_data(robot_position=Point(2, 2))
        assert a != b
        assert _map_data(robot_position=Point(1, 1)) == _map_data(robot_position=Point(1, 1))

    def test_differs_by_charger_position(self) -> None:
        a = _map_data(charger_position=Point(1, 1))
        b = _map_data(charger_position=Point(2, 2))
        assert a != b

    def test_differs_by_router_position(self) -> None:
        a = _map_data(router_position=Point(1, 1))
        b = _map_data(router_position=Point(2, 2))
        assert a != b

    def test_equal_when_all_compared_fields_match(self) -> None:
        common = {
            "map_id": 1,
            "custom_name": "Home",
            "rotation": 0,
            "robot_position": Point(1, 1),
            "charger_position": Point(0, 0),
        }
        assert _map_data(**common) == _map_data(**common)


# ===========================================================================
# MapData — as_dict / check_point
# ===========================================================================


class TestMapDataAsDict:
    def test_empty_map_data_produces_empty_dict(self) -> None:
        assert _map_data().as_dict() == {}

    def test_prefers_optimized_charger_position(self) -> None:
        md = _map_data(charger_position=Point(1, 1), optimized_charger_position=Point(2, 2))
        assert md.as_dict()["charger_position"] == Point(2, 2)

    def test_falls_back_to_raw_charger_position(self) -> None:
        md = _map_data(charger_position=Point(1, 1))
        assert md.as_dict()["charger_position"] == Point(1, 1)

    def test_router_position_included_when_truthy(self) -> None:
        md = _map_data(router_position=Point(3, 4))
        assert md.as_dict()["router_position"] == Point(3, 4)

    def test_rooms_included_only_for_saved_or_restored_maps(self) -> None:
        segment = Segment(segment_id=1, type=4)
        md = _map_data(segments={1: segment}, saved_map=True)
        assert "rooms" in md.as_dict()

        md2 = _map_data(segments={1: segment}, saved_map=False, saved_map_status=0, restored_map=False)
        assert "rooms" not in md2.as_dict()

    def test_robot_position_excluded_for_saved_maps(self) -> None:
        md = _map_data(robot_position=Point(1, 1), saved_map=True)
        assert "vacuum_position" not in md.as_dict()

        md2 = _map_data(robot_position=Point(1, 1), saved_map=False)
        assert md2.as_dict()["vacuum_position"] == Point(1, 1)

    def test_active_fields_excluded_for_saved_maps(self) -> None:
        md = _map_data(
            saved_map=True,
            active_areas=[Area(0, 0, 0, 1, 1, 1, 1, 0)],
            active_segments=[1],
            active_points=[Point(1, 1)],
            active_cruise_points={1: Coordinate(1, 1, True, 0)},
        )
        d = md.as_dict()
        assert "active_areas" not in d
        assert "active_segments" not in d
        assert "active_points" not in d
        assert "active_cruise_points" not in d

    def test_active_and_geometry_fields_included_for_live_maps(self) -> None:
        """A non-saved map with every geometry/list field populated: exercises every
        remaining "if self.X is not None" assignment branch of as_dict() in one pass.
        """
        area = Area(0, 0, 0, 1, 1, 1, 1, 0)
        wall = Wall(0, 0, 1, 1)
        carpet = Carpet(1, 0, 0, 0, 1, 1, 1, 1, 0)
        polygon = Polygon(1, 0, 0, 0, 1, 1, 1, 1, 0, polygon=[0, 0, 1, 1])
        md = _map_data(
            saved_map=False,
            custom_name="Home",
            map_id=5,
            saved_map_id=6,
            map_name="Floor 1",
            rotation=90,
            active_areas=[area],
            active_segments=[1],
            active_points=[Point(1, 1)],
            active_cruise_points={1: Coordinate(1, 1, True, 0)},
            virtual_walls=[wall],
            virtual_thresholds=[wall],
            passable_thresholds=[wall],
            impassable_thresholds=[wall],
            ramps=[area],
            low_lying_areas=[polygon],
            no_go_areas=[area],
            no_mopping_areas=[area],
            carpets=[carpet],
            ignored_carpets=[carpet],
            detected_carpets=[carpet],
            curtains=[wall],
            empty_map=False,
        )
        d = md.as_dict()
        assert d[ATTR_CUSTOM_NAME] == "Home"
        assert d["map_id"] == 5
        assert d["saved_map_id"] == 6
        assert d["map_name"] == "Floor 1"
        assert d["rotation"] == 90
        assert d["active_areas"] == [area]
        assert d["active_segments"] == [1]
        assert d["active_points"] == [Point(1, 1)]
        assert d["active_cruise_points"] == {1: Coordinate(1, 1, True, 0)}
        assert d["virtual_walls"] == [wall]
        assert d["virtual_thresholds"] == [wall]
        assert d["passable_thresholds"] == [wall]
        assert d["impassable_thresholds"] == [wall]
        assert d["ramps"] == [area]
        assert d["low_lying_areas"] == [polygon]
        assert d["no_go_areas"] == [area]
        assert d["no_mopping_areas"] == [area]
        assert d["carpets"] == [carpet]
        assert d["ignored_carpets"] == [carpet]
        assert d["detected_carpets"] == [carpet]
        assert d["curtains"] == [wall]
        assert d["is_empty"] is False

    def test_predefined_points_included_as_list_when_truthy(self) -> None:
        point = Coordinate(1, 1, True, 0)
        md = _map_data(predefined_points={1: point})
        assert md.as_dict()["predefined_points"] == [point]

    def test_last_updated_converted_to_datetime(self) -> None:
        md = _map_data(last_updated=1700000000.0)
        assert md.as_dict()["updated_at"] == datetime.fromtimestamp(1700000000.0)

    def test_startup_method_name_is_titled(self) -> None:
        md = _map_data(startup_method=StartupMethod.THROUGH_APP)
        assert md.as_dict()["startup_method"] == "Through App"

    def test_saved_furnitures_preferred_over_furnitures_when_saved_map(self) -> None:
        saved = {1: Furniture(1, 1, 0, 0, 2, 2, FurnitureType.TOILET, 1)}
        live = {2: Furniture(2, 2, 0, 0, 2, 2, FurnitureType.TOILET, 1)}
        md = _map_data(saved_furnitures=saved, furnitures=live, saved_map=True)
        assert md.as_dict()["furnitures"] == list(saved.values())

    def test_furnitures_used_when_not_a_saved_map(self) -> None:
        live = {2: Furniture(2, 2, 0, 0, 2, 2, FurnitureType.TOILET, 1)}
        md = _map_data(saved_furnitures=None, furnitures=live, saved_map=False)
        assert md.as_dict()["furnitures"] == list(live.values())

    def test_recovery_map_list_serialized_in_reverse_order(self) -> None:
        first = RecoveryMapInfo(1, 1700000000.0, "raw", "obj1", "name1", map_type=0)
        second = RecoveryMapInfo(2, 1700000100.0, "raw", "obj2", "name2", map_type=0)
        md = _map_data(recovery_map_list=[first, second])
        serialized = md.as_dict()["recovery_map_list"]
        assert serialized[0]["object_name"] == "name2"
        assert serialized[1]["object_name"] == "name1"

    def test_dust_collection_and_mop_wash_counts_included_when_truthy(self) -> None:
        md = _map_data(dust_collection_count=3, mop_wash_count=2)
        d = md.as_dict()
        assert d["dust_collection_count"] == 3
        assert d["mop_wash_count"] == 2

    def test_frame_id_and_map_index_and_obstacles_included_when_truthy(self) -> None:
        obstacle = Obstacle(1, 1, ObstacleType.SOCK.value, 10)
        md = _map_data(frame_id=5, map_index=2, obstacles={obstacle.id: obstacle})
        d = md.as_dict()
        assert d["frame_id"] == 5
        assert d["map_index"] == 2
        assert d["obstacles"] == {obstacle.id: obstacle}


class TestMapDataCheckPoint:
    def test_false_without_dimensions_or_pixel_type(self) -> None:
        assert _map_data().check_point(1, 1) is False

    def test_false_when_relative_coordinates_out_of_bounds(self) -> None:
        md = _map_data(
            dimensions=MapImageDimensions(top=0, left=0, height=5, width=5, grid_size=1),
            pixel_type=_PixelGrid({}),
        )
        assert md.check_point(-1, -1) is False

    def test_true_for_cleaned_or_dirty_pixel_values(self) -> None:
        md = _map_data(
            dimensions=MapImageDimensions(top=0, left=0, height=5, width=5, grid_size=1),
            pixel_type=_PixelGrid({(2, 2): 5}),
        )
        assert md.check_point(2, 2, absolute=True) is True

    def test_false_for_wall_or_outside_pixel_values(self) -> None:
        md = _map_data(
            dimensions=MapImageDimensions(top=0, left=0, height=5, width=5, grid_size=1),
            pixel_type=_PixelGrid({(2, 2): 255}),
        )
        assert md.check_point(2, 2, absolute=True) is False

    def test_relative_coordinates_are_converted_using_dimensions(self) -> None:
        md = _map_data(
            dimensions=MapImageDimensions(top=10, left=10, height=5, width=5, grid_size=1),
            pixel_type=_PixelGrid({(2, 2): 5}),
        )
        assert md.check_point(12, 12, absolute=False) is True


# ===========================================================================
# Tail dataclasses
# ===========================================================================


def test_dirty_data_defaults():
    data = DirtyData()
    assert data.value is None
    assert data.previous_value is None
    assert data.update_time is None


def test_shortcut_as_dict_round_trips_dataclass_fields():
    task = ShortcutTask(segment_id=1, suction_level=2, water_volume=3, cleaning_times=1, cleaning_mode=0)
    shortcut = Shortcut(id=1, name="Quick Clean", map_id=1, running=True, tasks=[[task]])
    d = shortcut.as_dict()
    assert d["id"] == 1
    assert d["name"] == "Quick Clean"
    assert d["tasks"] == [
        [{"segment_id": 1, "suction_level": 2, "water_volume": 3, "cleaning_times": 1, "cleaning_mode": 0}]
    ]


def test_shortcut_task_as_dict():
    task = ShortcutTask(segment_id=2, suction_level=1)
    assert task.as_dict() == {
        "segment_id": 2,
        "suction_level": 1,
        "water_volume": None,
        "cleaning_times": None,
        "cleaning_mode": None,
    }


def test_schedule_task_as_dict():
    task = ScheduleTask(id=1, enabled=True, time="08:00", repeats="1,2,3")
    d = task.as_dict()
    assert d["id"] == 1
    assert d["enabled"] is True
    assert d["time"] == "08:00"
    assert d["repeats"] == "1,2,3"
