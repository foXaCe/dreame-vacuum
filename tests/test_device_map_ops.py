"""Characterization tests for DreameVacuumDeviceMapMixin (device_map_ops.py).

The mixin is assembled onto DreameVacuumDevice at runtime; it depends on a
shared surface (``status``, ``capability``, ``_map_manager``, ``_protocol``,
helper methods such as ``call_action``/``get_property``/``schedule_update``)
declared for type-checking only in ``_device_base.DreameVacuumDeviceState``
(an empty class at runtime). These tests build a minimal concrete host that
inherits the mixin and stubs that shared surface with MagicMocks / plain
values, so the mixin's own logic (delegation to the map manager's editor,
payload construction, validation) can be exercised and asserted precisely.
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame.device_map_ops import DreameVacuumDeviceMapMixin
from custom_components.dreame_vacuum.dreame.exceptions import (
    InvalidActionException,
    InvalidValueException,
)
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    CleanupMethod,
    DreameVacuumAction,
    DreameVacuumCleaningMode,
    DreameVacuumMapBackupStatus,
    DreameVacuumMapRecoveryStatus,
    DreameVacuumProperty,
    MapData,
    MapImageDimensions,
    Obstacle,
    ObstacleType,
    RobotType,
    Segment,
)


class _MapOpsHost(DreameVacuumDeviceMapMixin):
    """Minimal concrete host exercising DreameVacuumDeviceMapMixin in isolation."""

    def __init__(self) -> None:
        self._map_manager = MagicMock()
        self._map_manager.editor = MagicMock()
        self._map_manager.optimizer = MagicMock()
        self._map_manager.selected_map = None
        self._map_manager.ready = True
        self._map_manager.cleaning_sequence = []

        self._protocol = MagicMock()
        self._protocol.dreame_cloud = False
        self._protocol.prefer_cloud = False

        self.status = MagicMock()
        self.capability = MagicMock()

        self.property_mapping: dict[object, dict[str, int]] = {}
        self.action_mapping = {
            DreameVacuumAction.UPDATE_MAP_DATA: {"siid": 9, "aiid": 1},
        }

        self._last_change = 0.0
        self._last_map_request = 0.0
        self._last_map_change_time: float | None = None
        self._last_map_list_request = 0
        self._map_select_time: float | None = None
        self._update_interval = 5
        self._map_update_interval = 5

        self.get_property = MagicMock(return_value=None)
        self.set_property = MagicMock(return_value=True)
        self.call_action = MagicMock(return_value={"code": 0})
        self.schedule_update = MagicMock()
        self._update_property = MagicMock()
        self._property_changed = MagicMock()
        self._request_properties = MagicMock(return_value=True)
        self._restore_go_to_zone = MagicMock()
        self.recovery_map_file = MagicMock(return_value=(b"filedata", "http://example.com/map", "obj-name"))


@pytest.fixture
def host() -> _MapOpsHost:
    h = _MapOpsHost()

    # Sensible "modern lidar device" defaults; individual tests override as needed.
    h.status.has_temporary_map = False
    h.status.started = False
    h.status.multi_map = False
    h.status.map_data_list = {}
    h.status.current_map = None
    h.status.selected_map = None
    h.status.segments = None
    h.status.has_saved_map = True
    h.status.docked = False
    h.status.zone_cleaning = False
    h.status.spot_cleaning = False
    h.status.segment_cleaning = False
    h.status.cruising = False
    h.status.custom_order = False
    h.status.customized_cleaning = False
    h.status.cleangenius_cleaning = False
    h.status.go_to_zone = False
    h.status.map_recovery_status = None
    h.status.map_backup_status = None
    h.status._previous_cleaning_sequence = {}
    h.status._capability = MagicMock()
    h.status._capability.cruising = False

    h.capability.customized_cleaning = True
    h.capability.map = True
    h.capability.lidar_navigation = True
    h.capability.map_object_offset = False
    h.capability.wetness_level = False
    h.capability.custom_cleaning_mode = False
    h.capability.segment_mopping_settings = False
    h.capability.cleaning_route = False
    h.capability.segment_slow_clean_route = False
    h.capability.carpet_recognition = True
    h.capability.carpet_cleanset_v3 = False
    h.capability.carpet_material = False
    h.capability.floor_material = False
    h.capability.cruising = False
    h.capability.backup_map = True
    h.capability.new_furnitures = False
    h.capability.camera_streaming = False
    h.capability.fluid_detection = False
    h.capability.self_wash_base = False
    h.capability.mop_pad_lifting = False
    h.capability.mijia = False
    h.capability.robot_type = RobotType.LIDAR

    return h


def _dims(**overrides: object) -> MapImageDimensions:
    d = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=50)
    for key, value in overrides.items():
        setattr(d, key, value)
    return d


def _area(x0: float, y0: float, x1: float, y1: float) -> Any:
    from custom_components.dreame_vacuum.dreame.vacuum_types import Area

    return Area(x0, y0, x1, y0, x1, y1, x0, y1)


def _base_map_data(**overrides: object) -> MapData:
    md = MapData()
    md.dimensions = _dims()
    md.need_optimization = False
    md.optimized_pixel_type = None
    md.optimized_dimensions = None
    md.optimized_charger_position = None
    md.combined_pixel_type = None
    md.combined_dimensions = None
    md.wifi_map = False
    md.furniture_version = None
    md.history_map = False
    md.saved_map = False
    md.recovery_map = False
    md.saved_map_status = None
    md.active_areas = None
    md.active_points = None
    md.active_segments = None
    md.active_cruise_points = None
    md.predefined_points = None
    md.obstacles = None
    md.furnitures = None
    md.line_to_robot = False
    md.path = None
    md.cleanset = None
    md.customized_cleaning = None
    md.cleanup_method = None
    md.segments = None
    md.robot_position = None
    md.charger_position = None
    md.docked = False
    md.robot_segment = None
    md.task_cruise_points = None
    md.fast_mapping = False
    for key, value in overrides.items():
        setattr(md, key, value)
    return md


# ---------------------------------------------------------------------------
# 1. get_map_for_render
# ---------------------------------------------------------------------------


def test_get_map_for_render_returns_none_for_falsy_input(host: _MapOpsHost) -> None:
    assert host.get_map_for_render(None) is None


def test_get_map_for_render_optimizes_when_flagged(host: _MapOpsHost) -> None:
    original = _base_map_data(need_optimization=True, saved_map_status=1)
    optimized = _base_map_data(need_optimization=True)
    host._map_manager.optimizer.optimize = MagicMock(return_value=optimized)
    host._map_manager.selected_map = "should-not-be-used"

    result = host.get_map_for_render(original)

    host._map_manager.optimizer.optimize.assert_called_once_with(original, None)
    assert result is not None
    assert result is not optimized  # get_map_for_render deep-copies before returning
    assert optimized.need_optimization is False


def test_get_map_for_render_optimizes_with_selected_map_when_status_2(host: _MapOpsHost) -> None:
    original = _base_map_data(need_optimization=True, saved_map_status=2)
    optimized = _base_map_data(need_optimization=True)
    host._map_manager.optimizer.optimize = MagicMock(return_value=optimized)
    host._map_manager.selected_map = "the-selected-map"

    host.get_map_for_render(original)

    host._map_manager.optimizer.optimize.assert_called_once_with(original, "the-selected-map")


def test_get_map_for_render_baseline_propagation(host: _MapOpsHost) -> None:
    map_data = _base_map_data()

    result = host.get_map_for_render(map_data)

    assert result is not None
    assert result is not map_data  # deep copy
    # capability.map_object_offset is False -> top is shifted up by one grid cell.
    assert result.dimensions.top == -50
    # Not segment-cleaning / not cruising -> those "last active X" fields are cleared.
    assert result.active_segments is None
    assert result.active_cruise_points is None
    # Not customized_cleaning -> cleanset nulled out for rendering.
    assert result.cleanset is None


def test_get_map_for_render_map_object_offset_shifts_left_and_top(host: _MapOpsHost) -> None:
    host.capability.map_object_offset = True
    map_data = _base_map_data()

    result = host.get_map_for_render(map_data)

    assert result.dimensions.top == -25
    assert result.dimensions.left == -25


def test_get_map_for_render_wifi_map_returns_early(host: _MapOpsHost) -> None:
    map_data = _base_map_data(wifi_map=True, active_segments=[1, 2])
    host.status.segment_cleaning = False  # would normally clear active_segments

    result = host.get_map_for_render(map_data)

    assert result.wifi_map is True
    # Early return happens before the "clear stale active_segments" logic.
    assert result.active_segments == [1, 2]


def test_get_map_for_render_saved_vslam_map_copies_from_selected_map(host: _MapOpsHost) -> None:
    host.capability.lidar_navigation = False
    host.status.docked = True
    host.status.started = False

    selected_segments = {1: Segment(1)}
    selected = _base_map_data(
        segments=selected_segments,
        data=b"selected-data",
        pixel_type="selected-pixel-type",
        dimensions=_dims(top=100, left=100),
        charger_position=None,
        no_go_areas=["ngo"],
        no_mopping_areas=["nma"],
        virtual_walls=["vw"],
    )
    host._map_manager.selected_map = selected

    map_data = _base_map_data(saved_map_status=1)

    result = host.get_map_for_render(map_data)

    assert set(result.segments.keys()) == {1}
    assert result.data == b"selected-data"
    assert result.pixel_type == "selected-pixel-type"
    assert result.dimensions.top == 100 - 50  # copied, then shifted by grid_size offset logic
    assert result.no_go_areas == ["ngo"]
    assert result.no_mopping_areas == ["nma"]
    assert result.virtual_walls == ["vw"]
    assert result.docked is True
    assert result.path is None
    assert result.need_optimization is False
    assert result.saved_map_status == 2


def test_get_map_for_render_filters_obstacles(host: _MapOpsHost) -> None:
    host.status.ai_pet_detection = 0
    host.capability.fluid_detection = True
    host.status.ai_fluid_detection = False

    pet = Obstacle(1, 1, ObstacleType.PET.value, 90, picture_status=2)
    stain = Obstacle(2, 2, ObstacleType.LIQUID_STAIN.value, 80, picture_status=2)
    disabled_picture = Obstacle(3, 3, ObstacleType.OBSTACLE.value, 70, picture_status=0)
    kept = Obstacle(4, 4, ObstacleType.OBSTACLE.value, 60, picture_status=2)
    map_data = _base_map_data(obstacles={"1": pet, "2": stain, "3": disabled_picture, "4": kept})

    result = host.get_map_for_render(map_data)

    assert set(result.obstacles.keys()) == {"4"}


def test_get_map_for_render_derives_charger_position_from_robot_position(host: _MapOpsHost) -> None:
    from custom_components.dreame_vacuum.dreame.vacuum_types import Point

    host.status.docked = True
    host.status.multi_map = False
    host.capability.robot_type = RobotType.LIDAR
    robot_position = Point(1, 2, a=10)
    map_data = _base_map_data(robot_position=robot_position, charger_position=None, docked=True)

    result = host.get_map_for_render(map_data)

    assert result.charger_position is not None
    assert result.charger_position.x == 1
    assert result.charger_position.y == 2
    assert result.charger_position.a == 190


def test_get_map_for_render_saved_map_clears_transient_fields(host: _MapOpsHost) -> None:
    map_data = _base_map_data(
        saved_map=True,
        active_areas=["a"],
        active_points=["p"],
        active_segments=[1],
        active_cruise_points={1: "c"},
        path=["p"],
        cleanset={"1": [1]},
    )

    result = host.get_map_for_render(map_data)

    assert result.active_areas is None
    assert result.active_points is None
    assert result.active_segments is None
    assert result.active_cruise_points is None
    assert result.path is None
    assert result.cleanset is None


# ---------------------------------------------------------------------------
# 2. Map property change callbacks (lines ~40-165)
# ---------------------------------------------------------------------------


def test_map_property_changed_refreshes_when_previous_value_known(host: _MapOpsHost) -> None:
    host._map_property_changed(previous_property="old")

    host._map_manager.editor.refresh_map.assert_called_once_with()


def test_map_property_changed_noop_on_first_value(host: _MapOpsHost) -> None:
    host._map_property_changed(previous_property=None)

    host._map_manager.editor.refresh_map.assert_not_called()


def test_map_list_changed_sets_object_name_from_object_name_key(host: _MapOpsHost) -> None:
    host.get_property = MagicMock(return_value=json.dumps({"object_name": "obj123", "md5": "abc"}))

    host._map_list_changed()

    host._map_manager.set_map_list_object_name.assert_called_once_with("obj123", "abc")


def test_map_list_changed_falls_back_to_obj_name_key(host: _MapOpsHost) -> None:
    host.get_property = MagicMock(return_value=json.dumps({"obj_name": "legacy-obj"}))

    host._map_list_changed()

    host._map_manager.set_map_list_object_name.assert_called_once_with("legacy-obj", None)


def test_map_list_changed_resets_last_request_when_object_name_missing(host: _MapOpsHost) -> None:
    host._last_map_list_request = 999
    host.get_property = MagicMock(return_value=json.dumps({}))

    host._map_list_changed()

    assert host._last_map_list_request == 0
    host._map_manager.set_map_list_object_name.assert_not_called()


def test_map_list_changed_swallows_invalid_json(host: _MapOpsHost) -> None:
    host.get_property = MagicMock(return_value="not-json{{{")

    host._map_list_changed()  # must not raise

    host._map_manager.set_map_list_object_name.assert_not_called()


def test_map_list_changed_noop_when_property_empty(host: _MapOpsHost) -> None:
    host.get_property = MagicMock(return_value="")

    host._map_list_changed()

    host._map_manager.set_map_list_object_name.assert_not_called()


def test_recovery_map_list_changed_sets_object_name(host: _MapOpsHost) -> None:
    host.get_property = MagicMock(return_value=json.dumps({"object_name": "rec-obj"}))

    host._recovery_map_list_changed()

    host._map_manager.set_recovery_map_list_object_name.assert_called_once_with("rec-obj")


def test_recovery_map_list_changed_swallows_invalid_json(host: _MapOpsHost) -> None:
    host.get_property = MagicMock(return_value="{not valid")

    host._recovery_map_list_changed()  # must not raise

    host._map_manager.set_recovery_map_list_object_name.assert_not_called()


def test_map_recovery_status_changed_success_triggers_requests(host: _MapOpsHost) -> None:
    host._protocol.dreame_cloud = False
    host._last_map_list_request = 123
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.SUCCESS.value

    host._map_recovery_status_changed(previous_map_recovery_status=DreameVacuumMapRecoveryStatus.RUNNING.value)

    assert host._last_map_list_request == 0
    host._map_manager.request_next_map.assert_called_once_with()
    host._map_manager.request_next_recovery_map_list.assert_called_once_with()
    host._request_properties.assert_called_once_with([DreameVacuumProperty.MAP_RECOVERY_STATUS])


def test_map_recovery_status_changed_running_skips_request_properties(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.RUNNING.value

    host._map_recovery_status_changed(previous_map_recovery_status=DreameVacuumMapRecoveryStatus.RUNNING.value)

    host._request_properties.assert_not_called()
    host._map_manager.request_next_map.assert_not_called()


def test_map_recovery_status_changed_noop_without_previous(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.SUCCESS.value

    host._map_recovery_status_changed(previous_map_recovery_status=None)

    host._map_manager.request_next_map.assert_not_called()
    host._request_properties.assert_not_called()


def test_map_backup_status_changed_success_triggers_recovery_list_request(host: _MapOpsHost) -> None:
    host._protocol.dreame_cloud = False
    host._last_map_list_request = 42
    host.status.map_backup_status = DreameVacuumMapBackupStatus.SUCCESS.value

    host._map_backup_status_changed(previous_map_backup_status=DreameVacuumMapBackupStatus.RUNNING.value)

    assert host._last_map_list_request == 0
    host._map_manager.request_next_recovery_map_list.assert_called_once_with()
    host._request_properties.assert_called_once()


def test_map_updated_touches_last_change_time_and_notifies(host: _MapOpsHost) -> None:
    host._last_map_change_time = None

    host._map_updated()

    assert host._last_map_change_time is not None
    host._property_changed.assert_called_once_with()


def test_map_changed_clears_select_time_and_notifies_when_ready(host: _MapOpsHost) -> None:
    host.status.current_map = None
    host._map_select_time = 123.0
    host._map_manager.ready = True

    host._map_changed(saved_map=False)

    assert host._map_select_time is None
    assert host._last_map_change_time is not None
    host._property_changed.assert_called_once_with()


def test_map_changed_saved_map_does_not_touch_last_change_time(host: _MapOpsHost) -> None:
    host.status.current_map = None
    host._last_map_change_time = 1.0

    host._map_changed(saved_map=True)

    assert host._last_map_change_time == 1.0


def test_map_changed_sets_go_to_zone_when_zone_cleaning_area_matches(host: _MapOpsHost) -> None:
    from custom_components.dreame_vacuum.dreame.vacuum_types import Area

    host.status.started = True
    host.status.go_to_zone = None
    host.status.zone_cleaning = True
    host.status._capability.cruising = False
    host.capability.self_wash_base = False
    host.capability.mop_pad_lifting = False
    host.status.cleaning_mode = DreameVacuumCleaningMode.MOPPING
    host.status.water_tank_or_mop_installed = False
    host.status.docked = False
    host.status.robot_position = None

    dims = _dims(grid_size=50)
    area = Area(0, 0, 100, 0, 100, 100, 0, 100)  # 100x100 == grid_size(50)*2 -> check_size passes
    map_data = _base_map_data(dimensions=dims, active_areas=[area], robot_position=None)
    host.status.current_map = map_data

    host._map_changed(saved_map=False)

    assert host.status.go_to_zone is not False
    assert host.status.go_to_zone.x == 50
    assert host.status.go_to_zone.y == 50
    assert host.status.go_to_zone.cleaning_mode == DreameVacuumCleaningMode.SWEEPING.value
    host._map_manager.editor.set_active_areas.assert_called_once_with([])


def test_map_changed_sets_go_to_zone_false_when_area_size_mismatch(host: _MapOpsHost) -> None:
    from custom_components.dreame_vacuum.dreame.vacuum_types import Area

    host.status.started = True
    host.status.go_to_zone = None
    host.status.zone_cleaning = True
    host.status._capability.cruising = False
    dims = _dims(grid_size=50)
    # Size does not match grid_size*2 == 100.
    area = Area(0, 0, 10, 0, 10, 10, 0, 10)
    map_data = _base_map_data(dimensions=dims, active_areas=[area])
    host.status.current_map = map_data

    host._map_changed(saved_map=False)

    assert host.status.go_to_zone is False
    host._map_manager.editor.set_active_areas.assert_not_called()


def test_map_changed_restores_go_to_zone_when_robot_within_bounds(host: _MapOpsHost) -> None:
    from custom_components.dreame_vacuum.dreame.vacuum_types import GoToZoneSettings, Point

    host.status.started = True
    host.status.go_to_zone = GoToZoneSettings(x=50, y=50, size=10)
    host.status.zone_cleaning = False
    robot_position = Point(52, 51)
    map_data = _base_map_data(robot_position=robot_position)
    host.status.current_map = map_data

    host._map_changed(saved_map=False)

    host._restore_go_to_zone.assert_called_once_with(True)


def test_map_changed_schedules_update_on_dock_state_mismatch_with_prefer_cloud(host: _MapOpsHost) -> None:
    host.status.started = True
    host.status.go_to_zone = False
    host.status.docked = True
    host._protocol.prefer_cloud = True
    map_data = _base_map_data(docked=False)
    host.status.current_map = map_data

    host._map_changed(saved_map=False)

    host.schedule_update.assert_called_once_with(host._update_interval, True)


# ---------------------------------------------------------------------------
# 3. CRUD maps: rename_map, set_map_rotation, set_selected_map, delete_map
# ---------------------------------------------------------------------------


def test_rename_map_delegates_to_editor_and_sends_payload(host: _MapOpsHost) -> None:
    host.status.map_data_list = {5: MagicMock()}

    host.rename_map(5, "Kitchen")

    host._map_manager.editor.set_map_name.assert_called_once_with(5, "Kitchen")
    host._protocol.action_async.assert_called_once()
    _callback, siid, aiid, payload = host._protocol.action_async.call_args.args
    assert siid == 9
    assert aiid == 1
    sent = json.loads(payload[0]["value"])
    assert sent == {"nrism": {"5": {"name": "Kitchen"}}}


def test_rename_map_none_name_becomes_empty_string(host: _MapOpsHost) -> None:
    host.status.map_data_list = {5: MagicMock()}

    host.rename_map(5, None)

    host._map_manager.editor.set_map_name.assert_called_once_with(5, "")
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent["nrism"]["5"]["name"] is None


def test_rename_map_raises_when_temporary_map_present(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    with pytest.raises(InvalidActionException, match="temporary map"):
        host.rename_map(5, "Kitchen")


def test_rename_map_raises_when_map_not_found(host: _MapOpsHost) -> None:
    host.status.map_data_list = {1: MagicMock()}

    with pytest.raises(InvalidActionException, match="Map not found"):
        host.rename_map(5, "Kitchen")


def test_set_map_rotation_delegates_with_explicit_map_id(host: _MapOpsHost) -> None:
    host.set_map_rotation(90, map_id=3)

    host._map_manager.editor.set_rotation.assert_called_once_with(3, 90)
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"smra": {"3": {"ra": 90}}}


def test_set_map_rotation_clamps_out_of_range_value(host: _MapOpsHost) -> None:
    host.set_map_rotation(400, map_id=3)

    host._map_manager.editor.set_rotation.assert_called_once_with(3, 0)


def test_set_map_rotation_derives_map_id_from_selected_map(host: _MapOpsHost) -> None:
    host.status.selected_map = MagicMock(map_id=7)

    host.set_map_rotation(90)

    host._map_manager.editor.set_rotation.assert_called_once_with(7, 90)


def test_set_map_rotation_none_rotation_is_noop(host: _MapOpsHost) -> None:
    result = host.set_map_rotation(None)

    assert result is None
    host._map_manager.editor.set_rotation.assert_not_called()


def test_set_map_rotation_raises_when_temporary_map_present(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    with pytest.raises(InvalidActionException, match="temporary map"):
        host.set_map_rotation(90, map_id=1)


def test_set_selected_map_delegates_to_editor_and_manager(host: _MapOpsHost) -> None:
    host.status.map_data_list = {4: MagicMock()}
    host._protocol.dreame_cloud = False

    result = host.set_selected_map(4)

    host._map_manager.editor.set_selected_map.assert_called_once_with(4)
    assert host._map_select_time is not None
    host._map_manager.request_next_map.assert_called_once_with(True)
    host._map_manager.request_next_map_list.assert_called_once_with()
    assert result == host.call_action.return_value


def test_set_selected_map_raises_when_map_not_found(host: _MapOpsHost) -> None:
    host.status.map_data_list = {1: MagicMock()}

    with pytest.raises(InvalidActionException, match="Map not found"):
        host.set_selected_map(4)


def test_delete_map_raises_when_temporary_map_present(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    with pytest.raises(InvalidActionException, match="temporary map"):
        host.delete_map()


def test_delete_map_raises_when_started(host: _MapOpsHost) -> None:
    host.status.started = True

    with pytest.raises(InvalidActionException, match="running"):
        host.delete_map()


def test_delete_map_raises_when_id_not_found(host: _MapOpsHost) -> None:
    host.status.map_data_list = {1: MagicMock()}

    with pytest.raises(InvalidActionException, match="Map not found"):
        host.delete_map(5)


def test_delete_map_multi_map_derives_id_from_selected_map(host: _MapOpsHost) -> None:
    host.status.multi_map = True
    host.status.map_data_list = {7: MagicMock()}
    host._map_manager.selected_map = MagicMock(map_id=7)

    host.delete_map(0)  # 0 is treated as "no explicit id"

    host._map_manager.editor.delete_map.assert_called_once_with(7)


def test_delete_map_multi_map_with_explicit_id(host: _MapOpsHost) -> None:
    host.status.multi_map = True
    host.status.map_data_list = {9: MagicMock()}

    host.delete_map(9)

    host._map_manager.editor.delete_map.assert_called_once_with(9)
    # delete_map() delegates to update_map_data() (synchronous), not the async variant.
    _action, payload = host.call_action.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"cm": {}, "mapid": 9}


def test_delete_map_single_map_matching_selected_calls_delete_without_args(host: _MapOpsHost) -> None:
    host.status.multi_map = False
    host.status.map_data_list = {9: MagicMock()}
    host._map_manager.selected_map = MagicMock(map_id=9)

    host.delete_map(9)

    host._map_manager.editor.delete_map.assert_called_once_with()


def test_delete_map_single_map_mismatched_selected_calls_delete_with_id(host: _MapOpsHost) -> None:
    host.status.multi_map = False
    host.status.map_data_list = {9: MagicMock()}
    host._map_manager.selected_map = MagicMock(map_id=3)

    host.delete_map(9)

    host._map_manager.editor.delete_map.assert_called_once_with(9)


# ---------------------------------------------------------------------------
# 4. set_cleaning_sequence, set_custom_cleaning
# ---------------------------------------------------------------------------


def test_set_cleaning_sequence_raises_when_unsupported(host: _MapOpsHost) -> None:
    host.capability.customized_cleaning = False

    with pytest.raises(InvalidActionException, match="not supported"):
        host.set_cleaning_sequence([1, 2])


def test_set_cleaning_sequence_raises_when_temporary_map(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    with pytest.raises(InvalidActionException, match="temporary map"):
        host.set_cleaning_sequence([1, 2])


def test_set_cleaning_sequence_raises_when_started(host: _MapOpsHost) -> None:
    host.status.started = True

    with pytest.raises(InvalidActionException, match="running"):
        host.set_cleaning_sequence([1, 2])


def test_set_cleaning_sequence_raises_for_unknown_segment(host: _MapOpsHost) -> None:
    host.status.segments = {1: Segment(1), 2: Segment(2)}

    with pytest.raises(InvalidValueException, match="Segment not found"):
        host.set_cleaning_sequence([1, 99])


def test_set_cleaning_sequence_happy_path_delegates_to_editor(host: _MapOpsHost) -> None:
    host.status.segments = {1: Segment(1), 2: Segment(2)}
    map_data = MapData()
    map_data.segments = {1: Segment(1), 2: Segment(2)}
    map_data.temporary_map = False
    host.status.current_map = map_data
    host._map_manager.editor.set_cleaning_sequence = MagicMock(return_value=[2, 1])

    host.set_cleaning_sequence([2, 1])

    host._map_manager.editor.set_cleaning_sequence.assert_called_once_with([2, 1])
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"cleanOrder": [2, 1]}


def test_set_cleaning_sequence_empty_saves_previous_sequence(host: _MapOpsHost) -> None:
    map_data = MapData()
    map_data.segments = {1: Segment(1)}
    map_data.temporary_map = False
    map_data.map_id = 5
    host.status.current_map = map_data
    host._map_manager.cleaning_sequence = [1, 2]
    host._map_manager.editor.set_cleaning_sequence = MagicMock(return_value=[])

    host.set_cleaning_sequence(None)

    assert host.status._previous_cleaning_sequence[5] == [1, 2]
    host._map_manager.editor.set_cleaning_sequence.assert_called_once_with([])


def test_set_custom_cleaning_raises_when_unsupported(host: _MapOpsHost) -> None:
    host.capability.customized_cleaning = False

    with pytest.raises(InvalidActionException, match="not supported"):
        host.set_custom_cleaning([1], [1], [1], [1])


def test_set_custom_cleaning_raises_when_temporary_map(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    with pytest.raises(InvalidActionException, match="temporary map"):
        host.set_custom_cleaning([1], [1], [1], [1])


def test_set_custom_cleaning_raises_when_started(host: _MapOpsHost) -> None:
    host.status.started = True

    with pytest.raises(InvalidActionException, match="running"):
        host.set_custom_cleaning([1], [1], [1], [1])


def test_set_custom_cleaning_raises_invalid_suction_level(host: _MapOpsHost) -> None:
    with pytest.raises(InvalidActionException, match="Invalid suction level"):
        host.set_custom_cleaning([1], [9], [1], [1])


def test_set_custom_cleaning_raises_invalid_water_volume(host: _MapOpsHost) -> None:
    with pytest.raises(InvalidActionException, match="Invalid water volume"):
        host.set_custom_cleaning([1], [1], [9], [1])


def test_set_custom_cleaning_raises_invalid_cleaning_times(host: _MapOpsHost) -> None:
    with pytest.raises(InvalidActionException, match="Invalid cleaning times"):
        host.set_custom_cleaning([1], [1], [1], [9])


def test_set_custom_cleaning_raises_invalid_cleaning_mode(host: _MapOpsHost) -> None:
    with pytest.raises(InvalidActionException, match="Invalid cleaning mode"):
        host.set_custom_cleaning([1], [1], [1], [1], cleaning_mode=[9])


def test_set_custom_cleaning_custom_mopping_route_unsupported(host: _MapOpsHost) -> None:
    host.capability.segment_mopping_settings = False

    with pytest.raises(InvalidActionException, match="Custom mopping route is not supported"):
        host.set_custom_cleaning([1], [1], [1], [1], custom_mopping_route=[0])


def test_set_custom_cleaning_cleaning_route_unsupported(host: _MapOpsHost) -> None:
    host.capability.cleaning_route = False

    with pytest.raises(InvalidActionException, match="Cleaning route is not supported"):
        host.set_custom_cleaning([1], [1], [1], [1], cleaning_route=[1])


def test_set_custom_cleaning_wetness_level_unsupported(host: _MapOpsHost) -> None:
    host.capability.wetness_level = False

    with pytest.raises(InvalidActionException, match="Wetness level is not supported"):
        host.set_custom_cleaning([1], [1], [1], [1], wetness_level=[10])


def test_set_custom_cleaning_raises_when_no_saved_map(host: _MapOpsHost) -> None:
    host.capability.map = True
    host.status.has_saved_map = False

    with pytest.raises(InvalidActionException, match="Cannot edit customized cleaning parameters on current map"):
        host.set_custom_cleaning([1], [1], [1], [1])


def test_set_custom_cleaning_raises_when_segment_id_missing(host: _MapOpsHost) -> None:
    host.capability.map = True
    host.status.has_saved_map = True
    host.status.current_map = MapData()

    with pytest.raises(InvalidActionException, match="Segment ID is required"):
        host.set_custom_cleaning([], [], [], [])


def test_set_custom_cleaning_raises_for_invalid_segment_id(host: _MapOpsHost) -> None:
    host.capability.map = True
    host.status.has_saved_map = True
    host.status.current_map = MapData()
    host.status.segments = {1: Segment(1)}

    with pytest.raises(InvalidActionException, match="Invalid Segment ID"):
        host.set_custom_cleaning([99], [1], [1], [1])


def test_set_custom_cleaning_happy_path_delegates_per_segment(host: _MapOpsHost) -> None:
    host.capability.map = True
    host.status.has_saved_map = True
    current_map = MapData()
    host.status.current_map = current_map
    host.status.segments = {1: Segment(1), 2: Segment(2)}
    host.capability.wetness_level = False
    host.capability.custom_cleaning_mode = False
    host.capability.segment_mopping_settings = False
    host.capability.cleaning_route = False
    host._map_manager.editor.cleanset = MagicMock(return_value=[[1, 2, 1, 0]])

    result = host.set_custom_cleaning([1, 2], [2, 3], [1, 2], [1, 3])

    host._map_manager.editor.set_segment_suction_level.assert_any_call(1, 2, False)
    host._map_manager.editor.set_segment_suction_level.assert_any_call(2, 3, False)
    host._map_manager.editor.set_segment_water_volume.assert_any_call(1, 1, False)
    host._map_manager.editor.set_segment_water_volume.assert_any_call(2, 2, False)
    host._map_manager.editor.set_segment_cleaning_times.assert_any_call(1, 1, False)
    host._map_manager.editor.set_segment_cleaning_times.assert_any_call(2, 3, False)
    host._map_manager.editor.refresh_map.assert_called_once_with()
    host._map_manager.editor.cleanset.assert_called_once_with(current_map)
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"customeClean": [[1, 2, 1, 0]]}
    assert result is None  # update_map_data_async always returns None


def test_set_custom_cleaning_uses_wetness_level_when_capability_supports_it(host: _MapOpsHost) -> None:
    host.capability.map = True
    host.status.has_saved_map = True
    host.status.current_map = MapData()
    host.status.segments = {1: Segment(1)}
    host.capability.wetness_level = True
    host._map_manager.editor.cleanset = MagicMock(return_value=[])

    host.set_custom_cleaning([1], [2], [1], [1], wetness_level=[15])

    host._map_manager.editor.set_segment_wetness_level.assert_called_once_with(1, 15, False)
    host._map_manager.editor.set_segment_water_volume.assert_not_called()


def test_set_custom_cleaning_legacy_path_missing_parameters(host: _MapOpsHost) -> None:
    host.capability.map = False

    with pytest.raises(InvalidActionException, match="Missing parameters"):
        host.set_custom_cleaning(None, None, None, None)


# ---------------------------------------------------------------------------
# 5. Zones: set_restricted_zone, set_virtual_threshold, set_carpet_area
# ---------------------------------------------------------------------------


def test_set_restricted_zone_delegates_and_builds_payload(host: _MapOpsHost) -> None:
    current_map = MagicMock()
    current_map.saved_map_status = 2
    host.status.current_map = current_map

    host.set_restricted_zone(walls=[[0, 0, 1, 1]], zones=[[0, 0, 2, 2]], no_mops=[[0, 0, 3, 3]])

    host._map_manager.editor.set_zones.assert_called_once_with([[0, 0, 1, 1]], [[0, 0, 2, 2]], [[0, 0, 3, 3]])
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"vw": {"line": [[0, 0, 1, 1]], "rect": [[0, 0, 2, 2]], "mop": [[0, 0, 3, 3]]}}


def test_set_restricted_zone_marks_temp_when_saved_map_status_not_2(host: _MapOpsHost) -> None:
    current_map = MagicMock()
    current_map.saved_map_status = 1
    host.status.current_map = current_map

    host.set_restricted_zone()

    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent["vw"]["temp"] == {}
    host._map_manager.editor.set_zones.assert_called_once_with([], [], [])


def test_set_virtual_threshold_raises_when_unsupported(host: _MapOpsHost) -> None:
    current_map = MagicMock()
    current_map.virtual_thresholds = None
    current_map.passable_thresholds = None
    host.status.current_map = current_map
    host.capability.floor_material = False

    with pytest.raises(InvalidActionException, match="not supported"):
        host.set_virtual_threshold([[0, 0, 1, 1]])


def test_set_virtual_threshold_raises_when_not_saved_map(host: _MapOpsHost) -> None:
    current_map = MagicMock()
    current_map.virtual_thresholds = [[0, 0, 1, 1]]
    host.status.current_map = current_map
    host.status.has_saved_map = False

    with pytest.raises(InvalidActionException, match="Cannot edit virtual thresholds"):
        host.set_virtual_threshold([[0, 0, 1, 1]])


def test_set_virtual_threshold_happy_path(host: _MapOpsHost) -> None:
    current_map = MagicMock()
    current_map.virtual_thresholds = []
    host.status.current_map = current_map
    host.status.has_saved_map = True

    host.set_virtual_threshold([[0, 0, 1, 1]])

    host._map_manager.editor.set_virtual_thresholds.assert_called_once_with([[0, 0, 1, 1]])
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"vws": {"vwsl": [[0, 0, 1, 1]]}}


def test_set_carpet_area_delegates_with_indexed_carpets(host: _MapOpsHost) -> None:
    current_map = MagicMock()
    current_map.carpets = []
    current_map.detected_carpets = None
    current_map.ignored_carpets = None
    host.status.current_map = current_map
    host.status.has_saved_map = True

    carpets = [[0, 0, 10, 10], [10, 10, 20, 20]]
    host.set_carpet_area(carpets=carpets, ignored_carpets=[])

    # Each carpet gets its 1-based index appended.
    assert carpets[0] == [0, 0, 10, 10, 1]
    assert carpets[1] == [10, 10, 20, 20, 2]
    host._map_manager.editor.set_carpets.assert_called_once_with(carpets, [])
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"cpt": {"addcpt": carpets, "nocpt": []}}


def test_set_carpet_area_raises_when_unsupported(host: _MapOpsHost) -> None:
    current_map = MagicMock()
    current_map.carpets = None
    current_map.detected_carpets = None
    current_map.ignored_carpets = None
    host.status.current_map = current_map

    with pytest.raises(InvalidActionException, match="Carpets are not supported"):
        host.set_carpet_area(carpets=[], ignored_carpets=[])


def test_set_carpet_area_raises_when_not_saved_map(host: _MapOpsHost) -> None:
    current_map = MagicMock()
    current_map.carpets = []
    host.status.current_map = current_map
    host.status.has_saved_map = False

    with pytest.raises(InvalidActionException, match="Cannot edit carpets on current map"):
        host.set_carpet_area(carpets=[], ignored_carpets=[])


def test_set_carpet_area_without_map_manager_checks_capability(host: _MapOpsHost) -> None:
    host._map_manager = None
    host.capability.carpet_recognition = False

    with pytest.raises(InvalidActionException, match="Carpets are not supported"):
        host.set_carpet_area(carpets=[], ignored_carpets=[])


# ---------------------------------------------------------------------------
# 6. _recovery_map_list_changed additional branches
# ---------------------------------------------------------------------------


def test_recovery_map_list_changed_falls_back_to_obj_name_key(host: _MapOpsHost) -> None:
    host.get_property = MagicMock(return_value=json.dumps({"obj_name": "legacy-obj"}))

    host._recovery_map_list_changed()

    host._map_manager.set_recovery_map_list_object_name.assert_called_once_with("legacy-obj")


def test_recovery_map_list_changed_resets_last_request_when_object_name_missing(host: _MapOpsHost) -> None:
    host._last_map_list_request = 999
    host.get_property = MagicMock(return_value=json.dumps({}))

    host._recovery_map_list_changed()

    assert host._last_map_list_request == 0
    host._map_manager.set_recovery_map_list_object_name.assert_not_called()


# ---------------------------------------------------------------------------
# 7. _map_changed additional branches
# ---------------------------------------------------------------------------


def test_map_changed_sweeping_with_water_tank_becomes_sweeping_and_mopping(host: _MapOpsHost) -> None:

    host.status.started = True
    host.status.go_to_zone = None
    host.status.zone_cleaning = True
    host.status._capability.cruising = False
    host.capability.self_wash_base = False
    host.capability.mop_pad_lifting = False
    host.status.cleaning_mode = DreameVacuumCleaningMode.SWEEPING
    host.status.water_tank_or_mop_installed = True
    host.status.docked = False
    host.status.robot_position = None

    dims = _dims(grid_size=50)
    area = _area(0, 0, 100, 100)
    map_data = _base_map_data(dimensions=dims, active_areas=[area], robot_position=None)
    host.status.current_map = map_data

    host._map_changed(saved_map=False)

    assert host.status.go_to_zone.cleaning_mode == DreameVacuumCleaningMode.SWEEPING_AND_MOPPING.value


def test_map_changed_sets_go_to_zone_false_when_no_active_areas(host: _MapOpsHost) -> None:
    host.status.started = True
    host.status.go_to_zone = None
    host.status.zone_cleaning = True
    host.status._capability.cruising = False
    map_data = _base_map_data(dimensions=_dims(), active_areas=None)
    host.status.current_map = map_data

    host._map_changed(saved_map=False)

    assert host.status.go_to_zone is False


# ---------------------------------------------------------------------------
# 8. get_map_for_render: non-history-map remaining branches
# ---------------------------------------------------------------------------


def test_get_map_for_render_uses_optimized_pixel_type_and_charger_position(host: _MapOpsHost) -> None:
    from custom_components.dreame_vacuum.dreame.vacuum_types import Point

    optimized_charger = Point(9, 9)
    map_data = _base_map_data(
        optimized_pixel_type="optimized-pixels",
        optimized_dimensions=_dims(top=5, left=5),
        optimized_charger_position=optimized_charger,
    )

    result = host.get_map_for_render(map_data)

    assert result.pixel_type == "optimized-pixels"
    assert result.charger_position == optimized_charger


def test_get_map_for_render_uses_combined_pixel_type(host: _MapOpsHost) -> None:
    map_data = _base_map_data(
        combined_pixel_type="combined-pixels",
        combined_dimensions=_dims(top=1, left=1),
    )

    result = host.get_map_for_render(map_data)

    assert result.pixel_type == "combined-pixels"


def test_get_map_for_render_upgrades_furniture_version(host: _MapOpsHost) -> None:
    host.capability.new_furnitures = True
    host.capability.mijia = True
    map_data = _base_map_data(furniture_version=1)

    result = host.get_map_for_render(map_data)

    assert result.furniture_version == 3


def test_get_map_for_render_upgrades_furniture_version_non_mijia(host: _MapOpsHost) -> None:
    host.capability.new_furnitures = True
    host.capability.mijia = False
    map_data = _base_map_data(furniture_version=1)

    result = host.get_map_for_render(map_data)

    assert result.furniture_version == 2


def test_get_map_for_render_started_clears_active_areas_and_points(host: _MapOpsHost) -> None:
    host.status.started = True
    host.status.zone_cleaning = False
    host.status.go_to_zone = False
    host.status.spot_cleaning = False
    host.status.task_status = None
    map_data = _base_map_data(active_areas=["a"], active_points=["p"], history_map=False)

    result = host.get_map_for_render(map_data)

    assert result.active_areas is None
    assert result.active_points is None


def test_get_map_for_render_camera_streaming_initializes_predefined_points(host: _MapOpsHost) -> None:
    host.capability.camera_streaming = True
    map_data = _base_map_data(predefined_points=None, history_map=False)

    result = host.get_map_for_render(map_data)

    assert result.predefined_points == []


def test_get_map_for_render_go_to_zone_sets_active_cruise_point_and_clears_areas(host: _MapOpsHost) -> None:
    from custom_components.dreame_vacuum.dreame.vacuum_types import Coordinate, GoToZoneSettings

    host.status._capability.cruising = False
    host.status.go_to_zone = GoToZoneSettings(x=10, y=20, size=5)
    map_data = _base_map_data(active_areas=["a"], path=["p"])

    result = host.get_map_for_render(map_data)

    assert result.active_cruise_points == {1: Coordinate(10, 20, False, 0)}
    assert result.active_areas is None
    assert result.path is None


def test_get_map_for_render_zone_cleaning_area_becomes_cruise_point(host: _MapOpsHost) -> None:
    from custom_components.dreame_vacuum.dreame.vacuum_types import Coordinate

    host.status.started = True
    host.status.go_to_zone = False
    host.status.zone_cleaning = True
    dims = _dims(grid_size=50)
    area = _area(0, 0, 100, 100)  # matches grid_size * 2 = 100
    map_data = _base_map_data(dimensions=dims, active_areas=[area])

    result = host.get_map_for_render(map_data)

    assert result.active_cruise_points == {1: Coordinate(50, 50, False, 0)}
    assert result.active_areas is None
    assert result.path is None


def test_get_map_for_render_area_check_size_without_zone_cleaning_clears_without_cruise_point(
    host: _MapOpsHost,
) -> None:
    host.status.started = False
    dims = _dims(grid_size=50)
    area = _area(0, 0, 100, 100)
    map_data = _base_map_data(dimensions=dims, active_areas=[area])

    result = host.get_map_for_render(map_data)

    assert result.active_cruise_points is None
    assert result.active_areas is None
    assert result.path is None


def test_get_map_for_render_clears_segments_when_zone_cleaning_with_active_areas(host: _MapOpsHost) -> None:
    host.status.zone_cleaning = True
    host.status.go_to_zone = False
    dims = _dims(grid_size=50)
    area = _area(0, 0, 10, 10)  # too small -> check_size(100) fails, area is untouched
    map_data = _base_map_data(dimensions=dims, active_areas=[area], segments={1: Segment(1)})

    result = host.get_map_for_render(map_data)

    assert result.segments is None
    assert result.active_areas == [area]


def test_get_map_for_render_clears_furnitures_when_detection_disabled(host: _MapOpsHost) -> None:
    host.status.ai_furniture_detection = 0
    map_data = _base_map_data(furnitures={"1": "f"})

    result = host.get_map_for_render(map_data)

    assert result.furnitures == {}


def test_get_map_for_render_appends_robot_position_when_line_to_robot(host: _MapOpsHost) -> None:
    from custom_components.dreame_vacuum.dreame.vacuum_types import Path, PathType, Point

    robot_position = Point(5, 6)
    map_data = _base_map_data(
        line_to_robot=True,
        path=[Path(1, 1, PathType.LINE)],
        robot_position=robot_position,
    )

    result = host.get_map_for_render(map_data)

    assert len(result.path) == 2
    appended = result.path[-1]
    assert appended.x == 5
    assert appended.y == 6
    assert appended.path_type == PathType.LINE


def test_get_map_for_render_sets_default_cleanset_when_customized_cleaning_enabled(host: _MapOpsHost) -> None:
    host.status.customized_cleaning = True
    host.status.cruising = False
    host.status.cleangenius_cleaning = False
    map_data = _base_map_data(cleanset=None, saved_map=False, recovery_map=False, segments={1: Segment(1)})

    result = host.get_map_for_render(map_data)

    assert result.cleanset is True


def test_get_map_for_render_cleaning_route_capability_clears_custom_mopping_route(host: _MapOpsHost) -> None:
    seg = Segment(1)
    seg.custom_mopping_route = 3
    host.capability.cleaning_route = True
    host.status.custom_order = True
    map_data = _base_map_data(segments={1: seg}, saved_map=False, recovery_map=False)

    result = host.get_map_for_render(map_data)

    assert result.segments[1].custom_mopping_route is None


def test_get_map_for_render_vslam_saved_map_status_upgraded_when_docked(host: _MapOpsHost) -> None:
    host.capability.lidar_navigation = False
    host.status.docked = False
    host.status.started = True  # avoids the earlier vslam saved-map-copy branch
    map_data = _base_map_data(saved_map=False, recovery_map=False, saved_map_status=1, docked=True)

    result = host.get_map_for_render(map_data)

    assert result.saved_map_status == 2


def test_get_map_for_render_clears_robot_position_when_matching_charger_and_not_docked(host: _MapOpsHost) -> None:
    from custom_components.dreame_vacuum.dreame.vacuum_types import Point

    host.status.docked = False
    host.status.started = False
    charger = Point(5, 5)
    robot = Point(5, 5)
    map_data = _base_map_data(
        docked=True, robot_position=robot, charger_position=charger, saved_map=False, recovery_map=False
    )

    result = host.get_map_for_render(map_data)

    assert result.docked is False
    assert result.robot_position is None


def test_get_map_for_render_derives_robot_position_from_charger_when_docked(host: _MapOpsHost) -> None:
    from custom_components.dreame_vacuum.dreame.vacuum_types import Point

    host.status.fast_mapping = False
    charger = Point(7, 8)
    map_data = _base_map_data(
        docked=True, robot_position=None, charger_position=charger, saved_map=False, recovery_map=False
    )

    result = host.get_map_for_render(map_data)

    assert result.robot_position is not None
    assert result.robot_position.x == 7
    assert result.robot_position.y == 8


# ---------------------------------------------------------------------------
# 9. get_map_for_render: history_map=True branch (completely separate path)
# ---------------------------------------------------------------------------


def test_get_map_for_render_history_map_sets_task_cruise_point_completed_from_robot_position(
    host: _MapOpsHost,
) -> None:
    from custom_components.dreame_vacuum.dreame.vacuum_types import Coordinate, Point

    dims = _dims(grid_size=50)
    area = _area(0, 0, 100, 100)
    map_data = _base_map_data(
        history_map=True,
        dimensions=dims,
        active_areas=[area],
        completed=False,
        robot_position=Point(50, 50),
        customized_cleaning=1,
        cleanup_method=None,
        task_cruise_points=None,
    )
    host.capability.camera_streaming = False

    result = host.get_map_for_render(map_data)

    assert result.active_areas is None
    # A later, independent check in the same history-map branch converts the
    # freshly-built task_cruise_points dict into active_cruise_points and
    # flips task_cruise_points to the sentinel value True.
    assert result.task_cruise_points is True
    assert result.active_cruise_points == {1: Coordinate(50, 50, False, 0)}
    assert result.completed is True


def test_get_map_for_render_history_map_completed_false_when_robot_outside_area(host: _MapOpsHost) -> None:
    from custom_components.dreame_vacuum.dreame.vacuum_types import Point

    dims = _dims(grid_size=50)
    area = _area(0, 0, 100, 100)
    map_data = _base_map_data(
        history_map=True,
        dimensions=dims,
        active_areas=[area],
        completed=False,
        robot_position=Point(10000, 10000),
        customized_cleaning=1,
        cleanup_method=None,
        task_cruise_points=None,
    )
    host.capability.camera_streaming = False

    result = host.get_map_for_render(map_data)

    assert result.completed is False


def test_get_map_for_render_history_map_completed_true_without_robot_position(host: _MapOpsHost) -> None:
    dims = _dims(grid_size=50)
    area = _area(0, 0, 100, 100)
    map_data = _base_map_data(
        history_map=True,
        dimensions=dims,
        active_areas=[area],
        completed=False,
        robot_position=None,
        customized_cleaning=1,
        cleanup_method=None,
        task_cruise_points=None,
    )
    host.capability.camera_streaming = False

    result = host.get_map_for_render(map_data)

    assert result.completed is True


def test_get_map_for_render_history_map_task_cruise_points_truthy_clears_related_fields(host: _MapOpsHost) -> None:
    map_data = _base_map_data(
        history_map=True,
        dimensions=_dims(),
        active_areas=None,
        task_cruise_points={1: "x"},
        path=["p"],
        no_mopping_areas=["a"],
        cleanset={"1": [1]},
        furnitures={"1": "f"},
        customized_cleaning=1,
        cleanup_method=None,
    )
    host.capability.camera_streaming = True  # skip the area-check sub-branch entirely

    result = host.get_map_for_render(map_data)

    assert result.active_cruise_points == {1: "x"}
    assert result.task_cruise_points is True
    assert result.active_areas is None
    assert result.path is None
    assert result.no_mopping_areas is None
    assert result.cleanset is None
    assert result.furnitures == {}


def test_get_map_for_render_history_map_segments_cleared_when_active_areas_present(host: _MapOpsHost) -> None:
    map_data = _base_map_data(
        history_map=True,
        dimensions=_dims(),
        active_areas=["a"],
        active_points=None,
        segments={1: Segment(1)},
        customized_cleaning=1,
        cleanup_method=None,
        task_cruise_points=None,
    )
    host.capability.camera_streaming = True

    result = host.get_map_for_render(map_data)

    assert result.segments is None


def test_get_map_for_render_history_map_clears_cleanset_when_not_customized(host: _MapOpsHost) -> None:
    map_data = _base_map_data(
        history_map=True,
        dimensions=_dims(),
        active_areas=None,
        active_points=None,
        segments=None,
        customized_cleaning=0,
        cleanup_method=None,
        cleanset={"1": [1]},
        task_cruise_points=None,
    )
    host.capability.camera_streaming = True

    result = host.get_map_for_render(map_data)

    assert result.cleanset is None


def test_get_map_for_render_history_map_cleanup_method_customized_cleaning_keeps_cleanset(host: _MapOpsHost) -> None:
    map_data = _base_map_data(
        history_map=True,
        dimensions=_dims(),
        active_areas=None,
        active_points=None,
        segments=None,
        customized_cleaning=1,
        cleanup_method=CleanupMethod.CUSTOMIZED_CLEANING,
        cleanset={"1": [1]},
        task_cruise_points=None,
    )
    host.capability.camera_streaming = True

    result = host.get_map_for_render(map_data)

    assert result.cleanset == {"1": [1]}


def test_get_map_for_render_history_map_sequence_false_for_cleangenius_cleanup(host: _MapOpsHost) -> None:
    seg = Segment(1)
    map_data = _base_map_data(
        history_map=True,
        dimensions=_dims(),
        active_areas=None,
        active_points=None,
        segments={1: seg},
        customized_cleaning=1,
        cleanup_method=CleanupMethod.CLEANGENIUS,
        task_cruise_points=None,
        active_segments=None,
    )
    host.capability.camera_streaming = True
    host.capability.cleangenius_mode = False
    host.capability.cleaning_route = False

    result = host.get_map_for_render(map_data)

    assert result.sequence is False


def test_get_map_for_render_history_map_reindexes_active_segments_order(host: _MapOpsHost) -> None:
    seg1 = Segment(1, order=1)
    seg2 = Segment(2, order=2)
    seg3 = Segment(3, order=3)
    seg1.custom_mopping_route = 5
    map_data = _base_map_data(
        history_map=True,
        dimensions=_dims(),
        active_areas=None,
        active_points=None,
        segments={1: seg1, 2: seg2, 3: seg3},
        customized_cleaning=1,
        cleanup_method=None,
        task_cruise_points=None,
        active_segments=[1, 3],
    )
    host.capability.camera_streaming = True
    host.capability.cleangenius_mode = False
    host.capability.cleaning_route = True

    result = host.get_map_for_render(map_data)

    assert result.sequence is True
    assert result.segments[1].order == 1
    assert result.segments[3].order == 2
    assert result.segments[2].order is None
    assert result.segments[1].custom_mopping_route is None  # cleaning_route capability resets it


# ---------------------------------------------------------------------------
# 10. get_map / update_map / request_map / update_map_data(_async)
# ---------------------------------------------------------------------------


def test_get_map_multi_map_delegates_to_manager(host: _MapOpsHost) -> None:
    host.status.multi_map = True
    host._map_manager.get_map = MagicMock(return_value="mapdata")

    assert host.get_map(3) == "mapdata"
    host._map_manager.get_map.assert_called_once_with(3)


def test_get_map_index_1_returns_selected_map(host: _MapOpsHost) -> None:
    host.status.multi_map = False
    host._map_manager.selected_map = "selected"

    assert host.get_map(1) == "selected"


def test_get_map_index_0_returns_current_map(host: _MapOpsHost) -> None:
    host.status.multi_map = False
    host.status.current_map = "current"

    assert host.get_map(0) == "current"


def test_get_map_without_manager_returns_none(host: _MapOpsHost) -> None:
    host._map_manager = None

    assert host.get_map(0) is None


def test_update_map_triggers_manager_when_stale(host: _MapOpsHost) -> None:
    host._last_map_request = 0.0

    host.update_map()

    host._map_manager.set_update_interval.assert_called_once_with(host._map_update_interval)
    host._map_manager.schedule_update.assert_called_once_with(0.01)
    assert host._last_change > 0


def test_update_map_skips_manager_when_recent(host: _MapOpsHost) -> None:
    host._last_map_request = time.time()

    host.update_map()

    host._map_manager.set_update_interval.assert_not_called()


def test_request_map_delegates_to_manager(host: _MapOpsHost) -> None:
    host._map_manager.request_new_map = MagicMock(return_value={"ok": True})

    assert host.request_map() == {"ok": True}


def test_request_map_falls_back_to_action_without_manager(host: _MapOpsHost) -> None:
    host._map_manager = None

    result = host.request_map()

    host.call_action.assert_called_once()
    action, payload = host.call_action.call_args.args
    assert action == DreameVacuumAction.REQUEST_MAP
    assert payload[0]["value"] == '{"frame_type":"I"}'
    assert result == host.call_action.return_value


def test_update_map_data_async_schedules_updates_and_sends_payload(host: _MapOpsHost) -> None:
    result = host.update_map_data_async({"foo": "bar"})

    assert result is None
    host._map_manager.schedule_update.assert_called_once_with(10)
    host._property_changed.assert_called_once_with(False)
    host._protocol.action_async.assert_called_once()


def test_update_map_data_async_callback_success_dreame_cloud_requests_map_list(host: _MapOpsHost) -> None:
    host._protocol.dreame_cloud = True

    host.update_map_data_async({"foo": "bar"})
    callback = host._protocol.action_async.call_args.args[0]

    callback({"code": 0})

    host.schedule_update.assert_called_with(5)
    host._map_manager.schedule_update.assert_called_with(3)
    host._map_manager.request_next_map_list.assert_called_once()
    host._map_manager.request_next_map.assert_not_called()


def test_update_map_data_async_callback_success_non_cloud_requests_next_map(host: _MapOpsHost) -> None:
    host._protocol.dreame_cloud = False
    host._last_map_list_request = 999

    host.update_map_data_async({"foo": "bar"})
    callback = host._protocol.action_async.call_args.args[0]

    callback({"code": 0})

    host._map_manager.request_next_map.assert_called_once_with(True)
    host._map_manager.request_next_map_list.assert_called_once()
    assert host._last_map_list_request == 0


def test_update_map_data_async_callback_failure_still_schedules_update(host: _MapOpsHost) -> None:
    host.update_map_data_async({"foo": "bar"})
    callback = host._protocol.action_async.call_args.args[0]

    callback({"code": 1})  # non-zero -> error-log branch

    host.schedule_update.assert_called_with(5)


def test_update_map_data_async_callback_without_map_manager(host: _MapOpsHost) -> None:
    host.update_map_data_async({"foo": "bar"})
    callback = host._protocol.action_async.call_args.args[0]
    host._map_manager = None

    callback({"code": 0})  # must not raise

    host.schedule_update.assert_called_with(5)


def test_update_map_data_dreame_cloud_schedules_manager_update(host: _MapOpsHost) -> None:
    host._protocol.dreame_cloud = True

    host.update_map_data({"foo": "bar"})

    host._map_manager.schedule_update.assert_any_call(3)
    host._map_manager.request_next_map_list.assert_called_once()
    host._map_manager.request_next_map.assert_not_called()


# ---------------------------------------------------------------------------
# 11. set_carpet_area / set_virtual_threshold: None-default branches and
#     no-map-manager fallbacks
# ---------------------------------------------------------------------------


def test_set_carpet_area_defaults_none_to_empty_lists(host: _MapOpsHost) -> None:
    current_map = MagicMock()
    current_map.carpets = []
    current_map.detected_carpets = None
    current_map.ignored_carpets = None
    host.status.current_map = current_map
    host.status.has_saved_map = True

    host.set_carpet_area()  # carpets=None, ignored_carpets=None by default

    host._map_manager.editor.set_carpets.assert_called_once_with([], [])


def test_set_virtual_threshold_defaults_none_to_empty_list(host: _MapOpsHost) -> None:
    current_map = MagicMock()
    current_map.virtual_thresholds = []
    current_map.passable_thresholds = None
    host.status.current_map = current_map
    host.status.has_saved_map = True

    host.set_virtual_threshold()

    host._map_manager.editor.set_virtual_thresholds.assert_called_once_with([])


def test_set_virtual_threshold_without_map_manager_raises_when_unsupported(host: _MapOpsHost) -> None:
    host._map_manager = None
    host.get_property = MagicMock(return_value=None)

    with pytest.raises(InvalidActionException, match="not supported"):
        host.set_virtual_threshold([[0, 0, 1, 1]])


def test_set_virtual_threshold_without_map_manager_succeeds_when_property_present(host: _MapOpsHost) -> None:
    host._map_manager = None
    host.get_property = MagicMock(return_value="1")

    host.set_virtual_threshold([[0, 0, 1, 1]])  # must not raise

    host._protocol.action_async.assert_called_once()


# ---------------------------------------------------------------------------
# 12. set_predefined_points
# ---------------------------------------------------------------------------


def test_set_predefined_points_raises_when_unsupported(host: _MapOpsHost) -> None:
    host.capability.cruising = False

    with pytest.raises(InvalidActionException, match="not supported"):
        host.set_predefined_points([[1, 2]])


def test_set_predefined_points_raises_when_started(host: _MapOpsHost) -> None:
    host.capability.cruising = True
    host.status.started = True

    with pytest.raises(InvalidActionException, match="running"):
        host.set_predefined_points([[1, 2]])


def test_set_predefined_points_raises_when_point_outside_map(host: _MapOpsHost) -> None:
    host.capability.cruising = True
    host.status.started = False
    current_map = MagicMock()
    current_map.check_point = MagicMock(return_value=False)
    host.status.current_map = current_map

    with pytest.raises(InvalidActionException, match="not inside the map"):
        host.set_predefined_points([[1, 2]])


def test_set_predefined_points_delegates_and_truncates_to_20(host: _MapOpsHost) -> None:
    host.capability.cruising = True
    host.status.started = False
    host.status.current_map = None
    host.status.has_saved_map = True

    points = [[i, i] for i in range(25)]
    host.set_predefined_points(points)

    called_points = host._map_manager.editor.set_predefined_points.call_args.args[0]
    assert len(called_points) == 20
    assert called_points[0] == [0, 0, 0, 1]
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert len(sent["spoint"]) == 20
    assert sent["tpoint"] == []


def test_set_predefined_points_raises_when_no_saved_map(host: _MapOpsHost) -> None:
    host.capability.cruising = True
    host.status.started = False
    current_map = MagicMock()
    current_map.check_point = MagicMock(return_value=True)
    host.status.current_map = current_map
    host.status.has_saved_map = False

    with pytest.raises(InvalidActionException, match="Cannot edit predefined points"):
        host.set_predefined_points([[1, 2]])


def test_set_predefined_points_default_none_becomes_empty_list(host: _MapOpsHost) -> None:
    host.capability.cruising = True
    host.status.started = False
    host.status.current_map = None

    host.set_predefined_points()  # points=None

    host._map_manager.editor.set_predefined_points.assert_called_once_with([])


# ---------------------------------------------------------------------------
# 13. save/discard/replace temporary map (mixin level)
# ---------------------------------------------------------------------------


def test_save_temporary_map_delegates_and_sends_cw5(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    host.save_temporary_map()

    host._map_manager.editor.save_temporary_map.assert_called_once_with()
    _action, payload = host.call_action.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"cw": 5}


def test_save_temporary_map_noop_without_temporary_map(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = False

    assert host.save_temporary_map() is None
    host._map_manager.editor.save_temporary_map.assert_not_called()


def test_discard_temporary_map_delegates_and_sends_cw0(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    host.discard_temporary_map()

    host._map_manager.editor.discard_temporary_map.assert_called_once_with()
    _action, payload = host.call_action.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"cw": 0}


def test_discard_temporary_map_noop_without_temporary_map(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = False

    assert host.discard_temporary_map() is None
    host._map_manager.editor.discard_temporary_map.assert_not_called()


def test_replace_temporary_map_raises_when_multi_map_enabled(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True
    host.status.multi_map = True

    with pytest.raises(InvalidActionException, match="multi floor map"):
        host.replace_temporary_map()


def test_replace_temporary_map_delegates_with_map_id(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True
    host.status.multi_map = False

    host.replace_temporary_map(map_id=7)

    host._map_manager.editor.replace_temporary_map.assert_called_once_with(7)
    _action, payload = host.call_action.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"cw": 1, "mapid": 7}


def test_replace_temporary_map_without_map_id_omits_mapid(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True
    host.status.multi_map = False

    host.replace_temporary_map()

    _action, payload = host.call_action.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"cw": 1}


def test_replace_temporary_map_noop_without_temporary_map(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = False

    assert host.replace_temporary_map() is None


# ---------------------------------------------------------------------------
# 14. restore_map_from_file
# ---------------------------------------------------------------------------


def test_restore_map_from_file_rejects_non_http_url(host: _MapOpsHost) -> None:
    with pytest.raises(InvalidActionException, match="must be http"):
        host.restore_map_from_file("not-a-url")


def test_restore_map_from_file_raises_when_unsupported(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = None

    with pytest.raises(InvalidActionException, match="not supported"):
        host.restore_map_from_file("http://example.com/map")


def test_restore_map_from_file_raises_when_already_running(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.RUNNING.value

    with pytest.raises(InvalidActionException, match="in progress"):
        host.restore_map_from_file("http://example.com/map")


def test_restore_map_from_file_raises_when_map_id_required(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    host.status.selected_map = None

    with pytest.raises(InvalidActionException, match="Map ID is required"):
        host.restore_map_from_file("http://example.com/map")


def test_restore_map_from_file_raises_when_map_not_in_list(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    host.status.map_data_list = {1: MagicMock()}

    with pytest.raises(InvalidActionException, match="Map not found"):
        host.restore_map_from_file("http://example.com/map.bin", map_id=5)


def test_restore_map_from_file_raises_when_started(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    host.status.map_data_list = {}
    host.status.started = True

    with pytest.raises(InvalidActionException, match="running"):
        host.restore_map_from_file("http://example.com/map.bin", map_id=5)


def test_restore_map_from_file_derives_map_id_from_selected_map_and_sends_property(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    host.status.selected_map = MagicMock(map_id=5)
    host.status.map_data_list = {5: MagicMock()}
    host.status.started = False
    host.property_mapping = {DreameVacuumProperty.MAP_RECOVERY: {"siid": 9, "piid": 2}}
    host._protocol.set_property = MagicMock(return_value=[{"code": 0}])

    result = host.restore_map_from_file("http://example.com/map.bin")

    host._protocol.set_property.assert_called_once()
    siid, piid, value = host._protocol.set_property.call_args.args
    assert siid == 9
    assert piid == 2
    sent = json.loads(value)
    assert sent == {"map_id": 5, "map_url": "http://example.com/map.bin"}
    host._update_property.assert_any_call(
        DreameVacuumProperty.MAP_RECOVERY_STATUS, DreameVacuumMapRecoveryStatus.RUNNING.value
    )
    assert result == [{"code": 0}]


def test_restore_map_from_file_raises_and_reverts_status_on_failure(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    host.status.map_data_list = {}
    host.status.started = False
    host.property_mapping = {DreameVacuumProperty.MAP_RECOVERY: {"siid": 9, "piid": 2}}
    host._protocol.set_property = MagicMock(return_value=[{"code": 1}])

    with pytest.raises(InvalidActionException, match="failed"):
        host.restore_map_from_file("http://example.com/map.bin", map_id=5)

    host._update_property.assert_any_call(
        DreameVacuumProperty.MAP_RECOVERY_STATUS, DreameVacuumMapRecoveryStatus.IDLE.value
    )


# ---------------------------------------------------------------------------
# 15. restore_map (mixin level, orchestrates restore_map_from_file)
# ---------------------------------------------------------------------------


def test_restore_map_raises_when_unsupported(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = None

    with pytest.raises(InvalidActionException, match="not supported"):
        host.restore_map(1)


def test_restore_map_raises_without_map_manager(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    host._map_manager = None

    with pytest.raises(InvalidActionException, match="cloud connection"):
        host.restore_map(1)


def test_restore_map_raises_when_already_running(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.RUNNING.value

    with pytest.raises(InvalidActionException, match="in progress"):
        host.restore_map(1)


def test_restore_map_raises_when_started(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    host.status.started = True

    with pytest.raises(InvalidActionException, match="running"):
        host.restore_map(1)


def test_restore_map_raises_when_temporary_map_present(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    host.status.has_temporary_map = True

    with pytest.raises(InvalidActionException, match="temporary map"):
        host.restore_map(1)


def test_restore_map_raises_when_map_not_found(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    host.status.selected_map = None
    host.status.map_data_list = {}

    with pytest.raises(InvalidActionException, match="Map not found"):
        host.restore_map(1, map_id=None)


def test_restore_map_raises_when_recovery_index_invalid(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    map_entry = MagicMock(recovery_map_list=[])
    host.status.map_data_list = {5: map_entry}

    with pytest.raises(InvalidActionException, match="Invalid recovery map index"):
        host.restore_map(1, map_id=5)


def test_restore_map_raises_when_object_name_missing(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    recovery_info = MagicMock(object_name="")
    map_entry = MagicMock(recovery_map_list=[recovery_info])
    host.status.map_data_list = {5: map_entry}

    with pytest.raises(InvalidActionException, match="Invalid recovery map object name"):
        host.restore_map(1, map_id=5)


def test_restore_map_raises_when_file_url_missing(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    recovery_info = MagicMock(object_name="obj")
    map_entry = MagicMock(recovery_map_list=[recovery_info])
    host.status.map_data_list = {5: map_entry}
    host.recovery_map_file = MagicMock(return_value=(b"data", None, "obj"))

    with pytest.raises(InvalidActionException, match="Failed get recovery map file url"):
        host.restore_map(1, map_id=5)


def test_restore_map_raises_when_file_download_fails(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    recovery_info = MagicMock(object_name="obj")
    map_entry = MagicMock(recovery_map_list=[recovery_info])
    host.status.map_data_list = {5: map_entry}
    host.recovery_map_file = MagicMock(return_value=(None, "http://x", "obj"))

    with pytest.raises(InvalidActionException, match="Failed to download recovery map file"):
        host.restore_map(1, map_id=5)


def test_restore_map_success_delegates_to_editor(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    recovery_info = MagicMock(object_name="obj")
    map_entry = MagicMock(recovery_map_list=[recovery_info])
    host.status.map_data_list = {5: map_entry}
    host.recovery_map_file = MagicMock(return_value=(b"data", "http://x", "obj"))
    host.restore_map_from_file = MagicMock(return_value=[{"code": 0}])

    result = host.restore_map(1, map_id=5)

    host.restore_map_from_file.assert_called_once_with("http://x", 5)
    host._map_manager.editor.restore_map.assert_called_once_with(recovery_info)
    assert result == [{"code": 0}]


def test_restore_map_does_not_call_editor_when_restore_from_file_fails(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    recovery_info = MagicMock(object_name="obj")
    map_entry = MagicMock(recovery_map_list=[recovery_info])
    host.status.map_data_list = {5: map_entry}
    host.recovery_map_file = MagicMock(return_value=(b"data", "http://x", "obj"))
    host.restore_map_from_file = MagicMock(return_value=[{"code": 1}])

    result = host.restore_map(1, map_id=5)

    host._map_manager.editor.restore_map.assert_not_called()
    assert result == [{"code": 1}]


def test_restore_map_derives_map_id_from_selected_map(host: _MapOpsHost) -> None:
    host.status.map_recovery_status = DreameVacuumMapRecoveryStatus.IDLE.value
    host.status.selected_map = MagicMock(map_id=5)
    recovery_info = MagicMock(object_name="obj")
    map_entry = MagicMock(recovery_map_list=[recovery_info])
    host.status.map_data_list = {5: map_entry}
    host.recovery_map_file = MagicMock(return_value=(b"data", "http://x", "obj"))
    host.restore_map_from_file = MagicMock(return_value=[{"code": 0}])

    host.restore_map(1)

    host.restore_map_from_file.assert_called_once_with("http://x", 5)


# ---------------------------------------------------------------------------
# 16. backup_map
# ---------------------------------------------------------------------------


def test_backup_map_raises_when_unsupported(host: _MapOpsHost) -> None:
    host.capability.backup_map = False

    with pytest.raises(InvalidActionException, match="not supported"):
        host.backup_map()


def test_backup_map_raises_when_already_running(host: _MapOpsHost) -> None:
    host.status.map_backup_status = DreameVacuumMapBackupStatus.RUNNING.value

    with pytest.raises(InvalidActionException, match="in progress"):
        host.backup_map()


def test_backup_map_raises_when_map_id_required(host: _MapOpsHost) -> None:
    host.status.selected_map = None

    with pytest.raises(InvalidActionException, match="Map ID is required"):
        host.backup_map()


def test_backup_map_raises_when_map_not_found(host: _MapOpsHost) -> None:
    host.status.map_data_list = {1: MagicMock()}

    with pytest.raises(InvalidActionException, match="Map not found"):
        host.backup_map(map_id=5)


def test_backup_map_success_updates_status(host: _MapOpsHost) -> None:
    host.status.map_data_list = {5: MagicMock()}
    host.call_action = MagicMock(return_value={"code": 0})

    result = host.backup_map(map_id=5)

    host.call_action.assert_called_once()
    action, payload = host.call_action.call_args.args
    assert action == DreameVacuumAction.BACKUP_MAP
    assert payload[0]["value"] == "5"
    host.schedule_update.assert_called_once_with(3, True)
    host._update_property.assert_called_once_with(
        DreameVacuumProperty.MAP_BACKUP_STATUS, DreameVacuumMapBackupStatus.RUNNING.value
    )
    assert result == {"code": 0}


def test_backup_map_derives_map_id_from_selected_map(host: _MapOpsHost) -> None:
    host.status.selected_map = MagicMock(map_id=9)
    host.status.map_data_list = {9: MagicMock()}
    host.call_action = MagicMock(return_value={"code": 1})  # non-zero -> status not updated

    host.backup_map()

    action, payload = host.call_action.call_args.args
    assert payload[0]["value"] == "9"
    host._update_property.assert_not_called()


# ---------------------------------------------------------------------------
# 17. merge_segments / split_segments
# ---------------------------------------------------------------------------


def test_merge_segments_raises_when_temporary_map(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    with pytest.raises(InvalidActionException, match="temporary map"):
        host.merge_segments(1, [1, 2])


def test_merge_segments_noop_when_segments_falsy(host: _MapOpsHost) -> None:
    assert host.merge_segments(1, None) is None
    assert host.merge_segments(1, []) is None


def test_merge_segments_derives_map_id_from_selected_map(host: _MapOpsHost) -> None:
    host.capability.lidar_navigation = True
    host._map_manager.selected_map = MagicMock(map_id=7)

    host.merge_segments("", [1, 2])

    host._map_manager.editor.merge_segments.assert_called_once_with(7, [1, 2])
    _action, payload = host.call_action.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"msr": [1, 2], "mapid": 7}


def test_merge_segments_defaults_to_zero_without_lidar_navigation(host: _MapOpsHost) -> None:
    host.capability.lidar_navigation = False

    host.merge_segments(None, [1, 2])

    host._map_manager.editor.merge_segments.assert_called_once_with(0, [1, 2])
    _action, payload = host.call_action.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"msr": [1, 2]}  # mapid omitted since map_id is falsy (0)


def test_merge_segments_raises_when_map_id_required(host: _MapOpsHost) -> None:
    host._map_manager = None
    host.capability.lidar_navigation = True

    with pytest.raises(InvalidActionException, match="Map ID is required"):
        host.merge_segments(None, [1, 2])


def test_merge_segments_with_explicit_map_id(host: _MapOpsHost) -> None:
    host.merge_segments(3, [4, 5])

    host._map_manager.editor.merge_segments.assert_called_once_with(3, [4, 5])


def test_split_segments_raises_when_temporary_map(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    with pytest.raises(InvalidActionException, match="temporary map"):
        host.split_segments(1, 2, [0, 0, 1, 1])


def test_split_segments_noop_when_missing_params(host: _MapOpsHost) -> None:
    assert host.split_segments(1, None, [0, 0]) is None
    assert host.split_segments(1, 2, None) is None


def test_split_segments_appends_segment_to_line_and_sends_payload(host: _MapOpsHost) -> None:
    host.capability.lidar_navigation = True
    host._map_manager.selected_map = MagicMock(map_id=4)

    host.split_segments(None, 7, [0, 0, 1, 1])

    host._map_manager.editor.split_segments.assert_called_once_with(4, 7, [0, 0, 1, 1, 7])
    _action, payload = host.call_action.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"dsrid": [0, 0, 1, 1, 7], "mapid": 4}


def test_split_segments_defaults_to_zero_without_lidar_navigation(host: _MapOpsHost) -> None:
    host.capability.lidar_navigation = False

    host.split_segments(None, 3, [1, 1, 2, 2])

    host._map_manager.editor.split_segments.assert_called_once_with(0, 3, [1, 1, 2, 2, 3])
    _action, payload = host.call_action.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"dsrid": [1, 1, 2, 2, 3]}


def test_split_segments_raises_when_map_id_required(host: _MapOpsHost) -> None:
    host._map_manager = None
    host.capability.lidar_navigation = True

    with pytest.raises(InvalidActionException, match="Map ID is required"):
        host.split_segments(None, 3, [0, 0])


def test_split_segments_empty_string_map_id_treated_as_none(host: _MapOpsHost) -> None:
    host.capability.lidar_navigation = False

    host.split_segments("", 3, [1, 1])

    host._map_manager.editor.split_segments.assert_called_once_with(0, 3, [1, 1, 3])


# ---------------------------------------------------------------------------
# 18. set_cleaning_sequence / set_cleanset additional branches
# ---------------------------------------------------------------------------


def test_set_cleaning_sequence_empty_clears_existing_previous_entry(host: _MapOpsHost) -> None:
    map_data = MapData()
    map_data.segments = {1: Segment(1)}
    map_data.temporary_map = False
    map_data.map_id = 5
    host.status.current_map = map_data
    host.status._previous_cleaning_sequence = {5: [1, 2]}
    host._map_manager.cleaning_sequence = []  # falsy -> skip the "if current" branch
    host._map_manager.editor.set_cleaning_sequence = MagicMock(return_value=[])

    host.set_cleaning_sequence(None)

    assert 5 not in host.status._previous_cleaning_sequence


def test_set_cleanset_raises_when_temporary_map(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    with pytest.raises(InvalidActionException, match="temporary map"):
        host.set_cleanset({"1": [1]})


def test_set_cleanset_returns_none_when_cleanset_is_none(host: _MapOpsHost) -> None:
    assert host.set_cleanset(None) is None


# ---------------------------------------------------------------------------
# 19. set_custom_cleaning: remaining validation branches and per-segment
#     delegation, plus a real UnboundLocalError bug in the legacy path
# ---------------------------------------------------------------------------


def test_set_custom_cleaning_raises_invalid_custom_mopping_route_value(host: _MapOpsHost) -> None:
    host.capability.segment_mopping_settings = True
    host.capability.cleaning_route = False

    with pytest.raises(InvalidActionException, match="Invalid custom mopping route"):
        host.set_custom_cleaning([1], [1], [1], [1], custom_mopping_route=[5])


def test_set_custom_cleaning_raises_invalid_cleaning_route_value(host: _MapOpsHost) -> None:
    host.capability.cleaning_route = True

    with pytest.raises(InvalidActionException, match="Invalid cleaning route"):
        host.set_custom_cleaning([1], [1], [1], [1], cleaning_route=[99])


def test_set_custom_cleaning_raises_invalid_wetness_level_value(host: _MapOpsHost) -> None:
    host.capability.wetness_level = True

    with pytest.raises(InvalidActionException, match="Invalid wetness level"):
        host.set_custom_cleaning([1], [1], [1], [1], wetness_level=[99])


def test_set_custom_cleaning_delegates_cleaning_mode_per_segment(host: _MapOpsHost) -> None:
    host.capability.map = True
    host.status.has_saved_map = True
    current_map = MapData()
    host.status.current_map = current_map
    host.status.segments = {1: Segment(1)}
    host.capability.custom_cleaning_mode = True
    host._map_manager.editor.cleanset = MagicMock(return_value=[])

    host.set_custom_cleaning([1], [2], [1], [1], cleaning_mode=[1])

    host._map_manager.editor.set_segment_cleaning_mode.assert_called_once_with(1, 1, False)


def test_set_custom_cleaning_delegates_custom_mopping_route_per_segment(host: _MapOpsHost) -> None:
    host.capability.map = True
    host.status.has_saved_map = True
    current_map = MapData()
    host.status.current_map = current_map
    host.status.segments = {1: Segment(1)}
    host.capability.segment_mopping_settings = True
    host.capability.cleaning_route = False
    host._map_manager.editor.cleanset = MagicMock(return_value=[])

    host.set_custom_cleaning([1], [2], [1], [1], custom_mopping_route=[0])

    host._map_manager.editor.set_segment_custom_mopping_route.assert_called_once_with(1, 0, False)


def test_set_custom_cleaning_delegates_cleaning_route_per_segment(host: _MapOpsHost) -> None:
    host.capability.map = True
    host.status.has_saved_map = True
    current_map = MapData()
    host.status.current_map = current_map
    host.status.segments = {1: Segment(1)}
    host.capability.segment_mopping_settings = False
    host.capability.cleaning_route = True
    host._map_manager.editor.cleanset = MagicMock(return_value=[])

    host.set_custom_cleaning([1], [2], [1], [1], cleaning_route=[2])

    host._map_manager.editor.set_segment_cleaning_route.assert_called_once_with(1, 2, False)


def test_set_custom_cleaning_legacy_path_crashes_on_unbound_segments(host: _MapOpsHost) -> None:
    """Documents a real bug: when capability.map is False (or current_map is
    falsy), the function falls through to the legacy cleanset-building
    branch, which references the local variable `segments` -- but that
    variable is only ever assigned inside the
    `if self.capability.map: if current_map:` block above, which always
    `return`s before falling through. So any invocation that reaches the
    legacy branch with a fully-populated parameter set (the only way to
    reach the `if segments:` check) crashes with UnboundLocalError instead
    of building the legacy cleanset. This makes the "legacy" code path (the
    one meant for devices without map support) permanently dead/unreachable
    in its current form."""
    host.capability.map = False
    host.capability.custom_cleaning_mode = False
    host.capability.wetness_level = False

    with pytest.raises(UnboundLocalError):
        host.set_custom_cleaning([1, 2], [1, 2], [1, 2], [1, 2])


def test_set_custom_cleaning_legacy_raises_when_cleaning_mode_unsupported(host: _MapOpsHost) -> None:
    """The has_cleaning_mode/custom_cleaning_mode mismatch checks in the
    legacy branch raise before the `segments` variable is ever touched, so
    unlike the rest of that branch they are safely reachable."""
    host.capability.custom_cleaning_mode = False

    with pytest.raises(InvalidActionException, match="not supported by the device"):
        host.set_custom_cleaning([1], [1], [1], [1], cleaning_mode=[1])


def test_set_custom_cleaning_legacy_raises_when_cleaning_mode_required(host: _MapOpsHost) -> None:
    host.capability.custom_cleaning_mode = True

    with pytest.raises(InvalidActionException, match="Cleaning mode is required"):
        host.set_custom_cleaning([1], [1], [1], [1])


# ---------------------------------------------------------------------------
# 20. set_custom_carpet_cleaning
# ---------------------------------------------------------------------------


def test_set_custom_carpet_cleaning_raises_when_unsupported(host: _MapOpsHost) -> None:
    host.capability.carpet_recognition = False

    with pytest.raises(InvalidActionException, match="not supported"):
        host.set_custom_carpet_cleaning(1, 0)


def test_set_custom_carpet_cleaning_raises_when_settings_unsupported(host: _MapOpsHost) -> None:
    host.capability.carpet_cleanset_v3 = False

    with pytest.raises(InvalidActionException, match="Custom carpet settings"):
        host.set_custom_carpet_cleaning(1, 0, carpet_settings=["clean_carpets_first"])


def test_set_custom_carpet_cleaning_raises_when_id_or_type_missing(host: _MapOpsHost) -> None:
    with pytest.raises(InvalidActionException, match="Missing id or type"):
        host.set_custom_carpet_cleaning(None, 0)
    with pytest.raises(InvalidActionException, match="Missing id or type"):
        host.set_custom_carpet_cleaning(1, None)


def test_set_custom_carpet_cleaning_raises_when_temporary_map(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    with pytest.raises(InvalidActionException, match="temporary map"):
        host.set_custom_carpet_cleaning(1, 0)


def test_set_custom_carpet_cleaning_raises_when_type_list_too_short(host: _MapOpsHost) -> None:
    with pytest.raises(InvalidActionException, match="Missing carpet type"):
        host.set_custom_carpet_cleaning([1, 2], [0])


def test_set_custom_carpet_cleaning_raises_when_cleaning_list_too_short(host: _MapOpsHost) -> None:
    with pytest.raises(InvalidActionException, match="Missing carpet cleaning"):
        host.set_custom_carpet_cleaning([1, 2], 0, carpet_cleaning=[1])


def test_set_custom_carpet_cleaning_raises_for_invalid_type(host: _MapOpsHost) -> None:
    with pytest.raises(InvalidActionException, match="Invalid type"):
        host.set_custom_carpet_cleaning(1, 5)


def test_set_custom_carpet_cleaning_raises_for_room_carpet_when_unsupported(host: _MapOpsHost) -> None:
    host.capability.carpet_material = False

    with pytest.raises(InvalidActionException, match="Room carpets are not supported"):
        host.set_custom_carpet_cleaning(1, 2)


def test_set_custom_carpet_cleaning_raises_for_out_of_range_setting(host: _MapOpsHost) -> None:
    with pytest.raises(InvalidActionException, match="Invalid carpet cleaning setting"):
        host.set_custom_carpet_cleaning(1, 0, carpet_cleaning=99)


def test_set_custom_carpet_cleaning_raises_for_unsupported_setting_4(host: _MapOpsHost) -> None:
    host.capability.mop_pad_lifting_plus = False
    host.capability.auto_carpet_cleaning = False
    host.capability.carpet_crossing = False

    with pytest.raises(InvalidActionException, match="not supported on this device"):
        host.set_custom_carpet_cleaning(1, 0, carpet_cleaning=4)


def test_set_custom_carpet_cleaning_raises_for_unsupported_setting_6(host: _MapOpsHost) -> None:
    host.capability.mop_pad_lifting_plus = False
    host.capability.auto_carpet_cleaning = False

    with pytest.raises(InvalidActionException, match="not supported on this device"):
        host.set_custom_carpet_cleaning(1, 0, carpet_cleaning=6)


def test_set_custom_carpet_cleaning_none_setting_defaults_to_minus_one(host: _MapOpsHost) -> None:
    host.capability.map = False

    host.set_custom_carpet_cleaning(1, 0, carpet_cleaning=None)

    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"carpetcleanset": [[0, 1, -1]]}


def test_set_custom_carpet_cleaning_v3_settings_bitmask(host: _MapOpsHost) -> None:
    host.capability.carpet_cleanset_v3 = True
    host.capability.clean_carpets_first = True
    host.capability.intensive_carpet_cleaning = True
    host.capability.side_brush_carpet_rotate = False
    host.capability.map = False
    host.get_property = MagicMock(return_value="1")  # CARPET_BOOST present

    host.set_custom_carpet_cleaning(
        1, 0, carpet_cleaning=2, carpet_settings=["clean_carpets_first", "carpet_boost", "intensive_carpet_cleaning"]
    )

    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    # bit0 clean_carpets_first + bit1 carpet_boost + bit2 intensive = 7
    assert sent == {"carpetcleanset": [[0, 1, 2, 7]]}


def test_set_custom_carpet_cleaning_v3_minus_one_setting_uses_minus_one(host: _MapOpsHost) -> None:
    host.capability.carpet_cleanset_v3 = True
    host.capability.map = False

    host.set_custom_carpet_cleaning(1, 0, carpet_cleaning=0)

    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"carpetcleanset": [[0, 1, -1, -1]]}


def test_set_custom_carpet_cleaning_v3_settings_as_list_of_lists_per_carpet(host: _MapOpsHost) -> None:
    host.capability.carpet_cleanset_v3 = True
    host.capability.map = False
    host.capability.clean_carpets_first = True
    host.capability.side_brush_carpet_rotate = True
    host.get_property = MagicMock(return_value=None)  # CARPET_BOOST absent

    host.set_custom_carpet_cleaning(
        [1, 2],
        [0, 0],
        carpet_cleaning=[2, 2],
        carpet_settings=[["clean_carpets_first"], ["side_brush_carpet_rotate"]],
    )

    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"carpetcleanset": [[0, 1, 2, 1], [0, 2, 2, 8]]}


def test_set_custom_carpet_cleaning_v3_settings_list_shorter_than_ids_defaults_to_none(host: _MapOpsHost) -> None:
    """When carpet_settings is a list-of-lists shorter than id, the ids past
    the end get enabled_settings=None, which forces settings=-1 for them."""
    host.capability.carpet_cleanset_v3 = True
    host.capability.map = False

    host.set_custom_carpet_cleaning(
        [1, 2],
        [0, 0],
        carpet_cleaning=[2, 2],
        carpet_settings=[["clean_carpets_first"]],
    )

    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent["carpetcleanset"][1] == [0, 2, 2, -1]


def test_set_custom_carpet_cleaning_multiple_ids_with_list_params(host: _MapOpsHost) -> None:
    host.capability.map = False

    host.set_custom_carpet_cleaning([1, 2], [0, 1], carpet_cleaning=[2, 3])

    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"carpetcleanset": [[0, 1, 2], [1, 2, 3]]}


def test_set_custom_carpet_cleaning_map_capability_raises_when_carpet_cleanset_none(host: _MapOpsHost) -> None:
    host.capability.map = True
    current_map = MagicMock()
    current_map.carpet_cleanset = None
    host.status.current_map = current_map

    with pytest.raises(InvalidActionException, match="Cannot set custom carpet cleaning"):
        host.set_custom_carpet_cleaning(1, 0)


def test_set_custom_carpet_cleaning_map_capability_raises_when_carpet_not_found(host: _MapOpsHost) -> None:
    host.capability.map = True
    current_map = MagicMock()
    current_map.carpet_cleanset = [[0, 1, -1]]
    host.status.current_map = current_map
    host._map_manager.editor.set_custom_carpet_cleaning = MagicMock(return_value=[])

    with pytest.raises(InvalidActionException, match="Cannot find selected carpet"):
        host.set_custom_carpet_cleaning(1, 0)


def test_set_custom_carpet_cleaning_map_capability_delegates_to_editor(host: _MapOpsHost) -> None:
    host.capability.map = True
    current_map = MagicMock()
    current_map.carpet_cleanset = [[0, 1, -1]]
    host.status.current_map = current_map
    host._map_manager.editor.set_custom_carpet_cleaning = MagicMock(return_value=[[0, 1, 2]])

    host.set_custom_carpet_cleaning(1, 0, carpet_cleaning=2)

    host._map_manager.editor.set_custom_carpet_cleaning.assert_called_once_with([[0, 1, 2]])
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"carpetcleanset": [[0, 1, 2]]}


def test_set_custom_carpet_cleaning_returns_none_for_empty_id_list(host: _MapOpsHost) -> None:
    assert host.set_custom_carpet_cleaning([], 0) is None


# ---------------------------------------------------------------------------
# 21. set_hidden_segments
# ---------------------------------------------------------------------------


def test_set_hidden_segments_raises_when_temporary_map(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    with pytest.raises(InvalidActionException, match="temporary map"):
        host.set_hidden_segments([1])


def test_set_hidden_segments_raises_when_started(host: _MapOpsHost) -> None:
    host.status.started = True

    with pytest.raises(InvalidActionException, match="running"):
        host.set_hidden_segments([1])


def test_set_hidden_segments_raises_for_unknown_segment(host: _MapOpsHost) -> None:
    host.status.segments = {1: Segment(1)}

    with pytest.raises(InvalidValueException, match="Segment not found"):
        host.set_hidden_segments([99])


def test_set_hidden_segments_defaults_empty_and_sends_payload(host: _MapOpsHost) -> None:
    host.status.segments = {1: Segment(1)}

    host.set_hidden_segments("")

    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"delsr": []}


def test_set_hidden_segments_sends_valid_ids(host: _MapOpsHost) -> None:
    host.status.segments = {1: Segment(1), 2: Segment(2)}

    host.set_hidden_segments([1])

    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"delsr": [1]}


# ---------------------------------------------------------------------------
# 22. set_segment_name / set_segment_order (mixin level)
# ---------------------------------------------------------------------------


def test_set_segment_name_raises_when_temporary_map(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    with pytest.raises(InvalidActionException, match="temporary map"):
        host.set_segment_name(1, 0, "Kitchen")


def test_set_segment_name_sends_payload_with_map_id_and_auto_rename(host: _MapOpsHost) -> None:
    host._map_manager.editor.set_segment_name = MagicMock(return_value={1: {"type": 0}})
    host.status.current_map = MagicMock(map_id=5)
    host.capability.auto_rename_segment = True

    host.set_segment_name(1, 0, "Kitchen")

    host._map_manager.editor.set_segment_name.assert_called_once_with(1, 0, "Kitchen")
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"nsr": {"1": {"type": 0}}, "mapid": 5, "autonsr": True}


def test_set_segment_name_returns_none_when_editor_reports_no_change(host: _MapOpsHost) -> None:
    host._map_manager.editor.set_segment_name = MagicMock(return_value=None)

    assert host.set_segment_name(1, 0, "Kitchen") is None


def test_set_segment_order_defaults_non_numeric_order_to_zero(host: _MapOpsHost) -> None:
    host._map_manager.editor.set_segment_order = MagicMock(return_value=[1, 2])

    host.set_segment_order(1, "abc")

    host._map_manager.editor.set_segment_order.assert_called_once_with(1, 0)


def test_set_segment_order_passes_through_numeric_order(host: _MapOpsHost) -> None:
    host._map_manager.editor.set_segment_order = MagicMock(return_value=[2, 1])

    host.set_segment_order(2, 5)

    host._map_manager.editor.set_segment_order.assert_called_once_with(2, 5)
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"cleanOrder": [2, 1]}


def test_set_segment_order_noop_without_map_manager(host: _MapOpsHost) -> None:
    host._map_manager = None

    assert host.set_segment_order(1, 5) is None


def test_set_segment_order_noop_when_temporary_map(host: _MapOpsHost) -> None:
    host.status.has_temporary_map = True

    assert host.set_segment_order(1, 5) is None


# ---------------------------------------------------------------------------
# 23. per-segment cleanset setters (mixin level)
# ---------------------------------------------------------------------------


def test_set_segment_suction_level_delegates(host: _MapOpsHost) -> None:
    host._map_manager.editor.set_segment_suction_level = MagicMock(return_value=[[1, 2, 1, 0]])

    host.set_segment_suction_level(1, 2)

    host._map_manager.editor.set_segment_suction_level.assert_called_once_with(1, 2)
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"customeClean": [[1, 2, 1, 0]]}


def test_set_segment_suction_level_noop_without_map_manager(host: _MapOpsHost) -> None:
    host._map_manager = None

    assert host.set_segment_suction_level(1, 2) is None


def test_set_segment_water_volume_noop_when_self_wash_base(host: _MapOpsHost) -> None:
    host.capability.self_wash_base = True

    assert host.set_segment_water_volume(1, 2) is None


def test_set_segment_water_volume_plain_delegates_to_water_volume_setter(host: _MapOpsHost) -> None:
    host.capability.self_wash_base = False
    host.capability.wetness_level = False
    host._map_manager.editor.set_segment_water_volume = MagicMock(return_value=[[1, 3, 1, 0]])

    host.set_segment_water_volume(1, 2)

    host._map_manager.editor.set_segment_water_volume.assert_called_once_with(1, 2)


def test_set_segment_water_volume_wetness_level_no_mop_clean_frequency_mapping(host: _MapOpsHost) -> None:
    host.capability.self_wash_base = False
    host.capability.wetness_level = True
    host.capability.mop_clean_frequency = False
    host._map_manager.editor.set_segment_wetness_level = MagicMock(return_value=[])

    host.set_segment_water_volume(1, 1)
    host._map_manager.editor.set_segment_wetness_level.assert_called_once_with(1, 5)

    host.set_segment_water_volume(1, 3)
    host._map_manager.editor.set_segment_wetness_level.assert_called_with(1, 27)

    host.set_segment_water_volume(1, 2)
    host._map_manager.editor.set_segment_wetness_level.assert_called_with(1, 16)


def test_set_segment_water_volume_wetness_level_with_mop_clean_frequency_mapping(host: _MapOpsHost) -> None:
    host.capability.self_wash_base = False
    host.capability.wetness_level = True
    host.capability.mop_clean_frequency = True
    host._map_manager.editor.set_segment_wetness_level = MagicMock(return_value=[])

    host.set_segment_water_volume(1, 1)
    host._map_manager.editor.set_segment_wetness_level.assert_called_once_with(1, 5)

    host.set_segment_water_volume(1, 3)
    host._map_manager.editor.set_segment_wetness_level.assert_called_with(1, 15)

    host.set_segment_water_volume(1, 2)
    host._map_manager.editor.set_segment_wetness_level.assert_called_with(1, 10)


def test_set_segment_mop_pad_humidity_noop_without_self_wash_base(host: _MapOpsHost) -> None:
    host.capability.self_wash_base = False

    assert host.set_segment_mop_pad_humidity(1, 2) is None


def test_set_segment_mop_pad_humidity_plain_delegates_to_water_volume_setter(host: _MapOpsHost) -> None:
    host.capability.self_wash_base = True
    host.capability.wetness_level = False
    host._map_manager.editor.set_segment_water_volume = MagicMock(return_value=[])

    host.set_segment_mop_pad_humidity(1, 2)

    host._map_manager.editor.set_segment_water_volume.assert_called_once_with(1, 2)


def test_set_segment_mop_pad_humidity_wetness_level_no_mop_clean_frequency_mapping(host: _MapOpsHost) -> None:
    host.capability.self_wash_base = True
    host.capability.wetness_level = True
    host.capability.mop_clean_frequency = False
    host._map_manager.editor.set_segment_wetness_level = MagicMock(return_value=[])

    host.set_segment_mop_pad_humidity(1, 1)
    host._map_manager.editor.set_segment_wetness_level.assert_called_once_with(1, 5)

    host.set_segment_mop_pad_humidity(1, 3)
    host._map_manager.editor.set_segment_wetness_level.assert_called_with(1, 27)

    host.set_segment_mop_pad_humidity(1, 2)
    host._map_manager.editor.set_segment_wetness_level.assert_called_with(1, 16)


def test_set_segment_mop_pad_humidity_wetness_level_with_mop_clean_frequency_mapping(host: _MapOpsHost) -> None:
    host.capability.self_wash_base = True
    host.capability.wetness_level = True
    host.capability.mop_clean_frequency = True
    host._map_manager.editor.set_segment_wetness_level = MagicMock(return_value=[])

    host.set_segment_mop_pad_humidity(1, 1)
    host._map_manager.editor.set_segment_wetness_level.assert_called_once_with(1, 2)

    host.set_segment_mop_pad_humidity(1, 3)
    host._map_manager.editor.set_segment_wetness_level.assert_called_with(1, 14)

    host.set_segment_mop_pad_humidity(1, 2)
    host._map_manager.editor.set_segment_wetness_level.assert_called_with(1, 8)


def test_set_segment_wetness_level_delegates_when_supported(host: _MapOpsHost) -> None:
    host.capability.wetness_level = True
    host._map_manager.editor.set_segment_wetness_level = MagicMock(return_value=[])

    host.set_segment_wetness_level(1, "20")

    host._map_manager.editor.set_segment_wetness_level.assert_called_once_with(1, 20)


def test_set_segment_wetness_level_noop_when_unsupported(host: _MapOpsHost) -> None:
    host.capability.wetness_level = False

    assert host.set_segment_wetness_level(1, 20) is None


def test_set_segment_cleaning_mode_delegates(host: _MapOpsHost) -> None:
    host._map_manager.editor.set_segment_cleaning_mode = MagicMock(return_value=[])

    host.set_segment_cleaning_mode(1, 2)

    host._map_manager.editor.set_segment_cleaning_mode.assert_called_once_with(1, 2)


def test_set_segment_cleaning_mode_noop_without_map_manager(host: _MapOpsHost) -> None:
    host._map_manager = None

    assert host.set_segment_cleaning_mode(1, 2) is None


def test_set_segment_custom_mopping_route_delegates_when_supported(host: _MapOpsHost) -> None:
    host.capability.self_wash_base = True
    host.capability.custom_mopping_route = True
    host._map_manager.editor.set_segment_custom_mopping_route = MagicMock(return_value=[])

    host.set_segment_custom_mopping_route(1, 2)

    host._map_manager.editor.set_segment_custom_mopping_route.assert_called_once_with(1, 2)


def test_set_segment_custom_mopping_route_noop_when_unsupported(host: _MapOpsHost) -> None:
    host.capability.self_wash_base = False

    assert host.set_segment_custom_mopping_route(1, 2) is None


def test_set_segment_cleaning_route_delegates_when_supported(host: _MapOpsHost) -> None:
    host.capability.self_wash_base = True
    host.capability.cleaning_route = True
    host._map_manager.editor.set_segment_cleaning_route = MagicMock(return_value=[])

    host.set_segment_cleaning_route(1, 3)

    host._map_manager.editor.set_segment_cleaning_route.assert_called_once_with(1, 3)


def test_set_segment_cleaning_route_noop_when_unsupported(host: _MapOpsHost) -> None:
    host.capability.self_wash_base = False

    assert host.set_segment_cleaning_route(1, 3) is None


def test_set_segment_cleaning_times_raises_when_started(host: _MapOpsHost) -> None:
    host.status.started = True

    with pytest.raises(InvalidActionException, match="running"):
        host.set_segment_cleaning_times(1, 2)


def test_set_segment_cleaning_times_delegates(host: _MapOpsHost) -> None:
    host._map_manager.editor.set_segment_cleaning_times = MagicMock(return_value=[])

    host.set_segment_cleaning_times(1, 2)

    host._map_manager.editor.set_segment_cleaning_times.assert_called_once_with(1, 2)


def test_set_segment_cleaning_times_noop_without_map_manager(host: _MapOpsHost) -> None:
    host._map_manager = None

    assert host.set_segment_cleaning_times(1, 2) is None


def test_set_segment_floor_material_raises_for_unsupported_carpet_material(host: _MapOpsHost) -> None:
    host.capability.carpet_material = False
    host.capability.carpet_type = False

    with pytest.raises(InvalidActionException, match="not supported"):
        host.set_segment_floor_material(1, 6)


def test_set_segment_floor_material_forces_direction_none_without_floor_direction_cleaning(
    host: _MapOpsHost,
) -> None:
    host.capability.floor_direction_cleaning = False
    host._map_manager.editor.set_segment_floor_material = MagicMock(return_value={})

    host.set_segment_floor_material(1, 1, direction=90)

    host._map_manager.editor.set_segment_floor_material.assert_called_once_with(1, 1, None)


def test_set_segment_floor_material_forces_direction_none_for_non_wood_material(host: _MapOpsHost) -> None:
    host.capability.floor_direction_cleaning = True
    host._map_manager.editor.set_segment_floor_material = MagicMock(return_value={})

    host.set_segment_floor_material(1, 2, direction=90)

    host._map_manager.editor.set_segment_floor_material.assert_called_once_with(1, 2, None)


def test_set_segment_floor_material_derives_direction_from_segment_when_not_given(host: _MapOpsHost) -> None:
    host.capability.floor_direction_cleaning = True
    seg = Segment(1)
    seg.floor_material_rotated_direction = 45
    host.status.segments = {1: seg}
    host._map_manager.editor.set_segment_floor_material = MagicMock(return_value={})

    host.set_segment_floor_material(1, 1, direction=None)

    host._map_manager.editor.set_segment_floor_material.assert_called_once_with(1, 1, 45)


def test_set_segment_floor_material_derives_direction_from_map_rotation_when_no_segment_direction(
    host: _MapOpsHost,
) -> None:
    host.capability.floor_direction_cleaning = True
    seg = Segment(1)
    seg.floor_material_rotated_direction = None
    host.status.segments = {1: seg}
    host.status.current_map = MagicMock(rotation=0)
    host._map_manager.editor.set_segment_floor_material = MagicMock(return_value={})

    host.set_segment_floor_material(1, 1, direction=None)

    host._map_manager.editor.set_segment_floor_material.assert_called_once_with(1, 1, 0)


def test_set_segment_floor_material_derives_direction_90_for_other_rotations(host: _MapOpsHost) -> None:
    host.capability.floor_direction_cleaning = True
    host.status.segments = None
    host.status.current_map = MagicMock(rotation=180)
    host._map_manager.editor.set_segment_floor_material = MagicMock(return_value={})

    host.set_segment_floor_material(1, 1, direction=None)

    host._map_manager.editor.set_segment_floor_material.assert_called_once_with(1, 1, 90)


def test_set_segment_floor_material_sends_map_id_when_selected(host: _MapOpsHost) -> None:
    host.status.selected_map = MagicMock(map_id=8)
    host.capability.floor_direction_cleaning = False
    host._map_manager.editor.set_segment_floor_material = MagicMock(return_value={"1": {"material": 1}})

    host.set_segment_floor_material(1, 1)

    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"nsm": {"1": {"material": 1}}, "map_id": 8}


def test_set_segment_floor_material_noop_without_map_manager(host: _MapOpsHost) -> None:
    host._map_manager = None

    assert host.set_segment_floor_material(1, 1) is None


def test_set_segment_floor_material_direction_delegates_when_supported(host: _MapOpsHost) -> None:
    host.capability.floor_direction_cleaning = True
    host.status.selected_map = MagicMock(map_id=3)
    host._map_manager.editor.set_segment_floor_material = MagicMock(
        return_value={"1": {"material": 1, "direction": 90}}
    )

    host.set_segment_floor_material_direction(1, 90)

    host._map_manager.editor.set_segment_floor_material.assert_called_once_with(1, 1, 90)
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"nsm": {"1": {"material": 1, "direction": 90}}, "map_id": 3}


def test_set_segment_floor_material_direction_noop_when_unsupported(host: _MapOpsHost) -> None:
    host.capability.floor_direction_cleaning = False

    assert host.set_segment_floor_material_direction(1, 90) is None


def test_set_segment_visibility_delegates_when_supported(host: _MapOpsHost) -> None:
    host.capability.segment_visibility = True
    host._map_manager.editor.set_segment_visibility = MagicMock(return_value=[2])

    host.set_segment_visibility(2, 0)

    host._map_manager.editor.set_segment_visibility.assert_called_once_with(2, 0)
    _callback, _siid, _aiid, payload = host._protocol.action_async.call_args.args
    sent = json.loads(payload[0]["value"])
    assert sent == {"delsr": [2]}


def test_set_segment_visibility_noop_when_unsupported(host: _MapOpsHost) -> None:
    host.capability.segment_visibility = False

    assert host.set_segment_visibility(2, 0) is None
