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
from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame.device_map_ops import DreameVacuumDeviceMapMixin
from custom_components.dreame_vacuum.dreame.exceptions import (
    InvalidActionException,
    InvalidValueException,
)
from custom_components.dreame_vacuum.dreame.vacuum_types import (
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
