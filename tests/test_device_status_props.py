"""Tests for _map_props.py (_MapPropsMixin) of DreameVacuumDeviceStatus.

Nearly every property in ``_map_props.py`` branches on whether ``self._map_manager``
is ``None`` (no map support / map manager not yet initialized) or configured (a real
``DreameMapVacuumMapManager``-like collaborator). This file exercises both branches of
each property using the shared ``_make_status``/``_make_capability`` helpers from
``test_device_status_core`` - a ``MagicMock`` standing in for the map manager is
sufficient since ``_map_props.py`` only ever reads its ``get_map()``, ``selected_map``,
``map_list``, ``map_data_list`` and ``cleaning_sequence`` members, while real
``MapData``/``Segment`` instances (cheap, attribute-bag classes with no I/O) are used
for the map data itself so field access matches production types exactly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.dreame_vacuum.dreame.vacuum_types import (
    CleaningHistory,
    CleanupMethod,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumProperty,
    DreameVacuumStatus,
    DreameVacuumTaskStatus,
    MapData,
    Segment,
)
from tests.test_device_status_core import _make_capability, _make_status, _not_started_properties

# ---------------------------------------------------------------------------
# multi_map / maximum_maps / mapping_available
# ---------------------------------------------------------------------------


def test_mapping_available_true_without_map_manager() -> None:
    capability = _make_capability(lidar_navigation=True)
    status = _make_status(_not_started_properties(), capability=capability)
    assert status.started is False
    assert status.fast_mapping is False
    assert status.mapping_available is True


def test_mapping_available_false_when_started() -> None:
    capability = _make_capability(lidar_navigation=True)
    status = _make_status(capability=capability)
    assert status.started is True
    assert status.mapping_available is False


def test_mapping_available_false_when_map_limit_reached() -> None:
    capability = _make_capability(lidar_navigation=True, wifi_map=False)
    capability._device._map_manager = MagicMock()  # capability.map -> True
    manager = MagicMock(map_list=[1, 2, 3])
    status = _make_status(
        _not_started_properties({DreameVacuumProperty.MULTI_FLOOR_MAP: 1}), capability=capability, map_manager=manager
    )
    assert status.multi_map is True
    assert status.maximum_maps == 3
    assert status.map_list == [1, 2, 3]
    assert status.mapping_available is False


# ---------------------------------------------------------------------------
# second_cleaning_available
# ---------------------------------------------------------------------------


def test_second_cleaning_available_false_without_capability() -> None:
    status = _make_status()
    assert status.second_cleaning_available is False


def test_second_cleaning_available_false_without_cleaning_history() -> None:
    capability = _make_capability(auto_recleaning=True)
    map_data = MapData()
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(capability=capability, map_manager=manager)
    assert status.current_map is map_data
    assert status._cleaning_history is None
    assert status.second_cleaning_available is False


def test_second_cleaning_available_false_without_object_name() -> None:
    capability = _make_capability(auto_recleaning=True)
    map_data = MapData()
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(capability=capability, map_manager=manager)
    history = CleaningHistory([], {})
    history.object_name = None
    status._cleaning_history = [history]
    assert status.second_cleaning_available is False


def test_second_cleaning_available_false_when_map_id_mismatch() -> None:
    capability = _make_capability(auto_recleaning=True)
    current_map = MapData()
    current_map.map_id = 1
    manager = MagicMock(get_map=MagicMock(return_value=current_map))
    status = _make_status(capability=capability, map_manager=manager)

    history_map_data = MapData()
    history_map_data.map_id = 2  # deliberately different from current_map.map_id
    status._history_map_data = {"history.zip": history_map_data}

    history = CleaningHistory([], {})
    history.object_name = "history.zip"
    history.neglected_segments = {1: 3}
    status._cleaning_history = [history]

    assert status.second_cleaning_available is False


def test_second_cleaning_available_true_via_neglected_segments() -> None:
    capability = _make_capability(auto_recleaning=True)
    current_map = MapData()
    current_map.map_id = 7
    manager = MagicMock(get_map=MagicMock(return_value=current_map))
    status = _make_status(capability=capability, map_manager=manager)

    history_map_data = MapData()
    history_map_data.map_id = 7
    status._history_map_data = {"history.zip": history_map_data}

    history = CleaningHistory([], {})
    history.object_name = "history.zip"
    history.neglected_segments = {1: 3}
    status._cleaning_history = [history]

    assert status.second_cleaning_available is True


def test_second_cleaning_available_true_via_cleanup_method_and_dirty_area() -> None:
    capability = _make_capability(auto_recleaning=True, mop_pad_unmounting=False)
    current_map = MapData()
    current_map.map_id = 9
    manager = MagicMock(get_map=MagicMock(return_value=current_map))
    status = _make_status(capability=capability, map_manager=manager)

    cleaning_map_data = MapData()
    cleaning_map_data.has_dirty_area = True

    history_map_data = MapData()
    history_map_data.map_id = 9
    history_map_data.cleaned_segments = {1: 1}
    history_map_data.cleaning_map_data = cleaning_map_data
    status._history_map_data = {"history.zip": history_map_data}

    history = CleaningHistory([], {})
    history.object_name = "history.zip"
    history.neglected_segments = None
    history.cleanup_method = CleanupMethod.CLEANGENIUS  # .value == 2
    history.mopping_mode = 2
    history.second_mopping = 2
    status._cleaning_history = [history]

    # mop_pad_installed falls back to water_tank_or_mop_installed (True by default: a
    # missing WATER_TANK property reads as "not NOT_INSTALLED").
    assert status.mop_pad_installed is True
    assert status.second_cleaning_available is True


def test_second_cleaning_available_false_when_cleanup_method_not_cleangenius() -> None:
    capability = _make_capability(auto_recleaning=True)
    current_map = MapData()
    current_map.map_id = 3
    manager = MagicMock(get_map=MagicMock(return_value=current_map))
    status = _make_status(capability=capability, map_manager=manager)

    history_map_data = MapData()
    history_map_data.map_id = 3
    status._history_map_data = {"history.zip": history_map_data}

    history = CleaningHistory([], {})
    history.object_name = "history.zip"
    history.neglected_segments = None
    history.cleanup_method = CleanupMethod.DEFAULT_MODE  # .value == 0, not 2
    status._cleaning_history = [history]

    assert status.second_cleaning_available is False


# ---------------------------------------------------------------------------
# custom_order / segment_order
# ---------------------------------------------------------------------------


def test_custom_order_false_without_map_manager() -> None:
    status = _make_status()
    assert status.custom_order is False
    assert status.segment_order is None


def test_custom_order_false_when_cleangenius_cleaning_without_mode_capability() -> None:
    """cleangenius_cleaning True + cleangenius_mode capability off short-circuits custom_order
    to False before it ever looks at current_segments."""
    capability = _make_capability(cleangenius=True, mop_pad_unmounting=True, cleangenius_mode=False)
    status = _make_status(
        {
            DreameVacuumProperty.MOP_PAD_INSTALLED: 0,
            DreameVacuumAutoSwitchProperty.CLEANGENIUS: 1,
        },
        capability=capability,
    )
    assert status.mop_pad_installed is True
    assert status.cleangenius_cleaning is True
    assert status.custom_order is False


def test_custom_order_true_when_a_segment_has_order() -> None:
    seg1 = Segment(1)
    seg1.order = 2
    seg2 = Segment(2)
    seg2.order = None
    map_data = MapData()
    map_data.segments = {1: seg1, 2: seg2}
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(map_manager=manager)
    assert status.current_segments == {1: seg1, 2: seg2}
    assert status.custom_order is True


def test_custom_order_false_when_no_segment_has_order() -> None:
    seg1 = Segment(1)
    seg1.order = None
    map_data = MapData()
    map_data.segments = {1: seg1}
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(map_manager=manager)
    assert status.custom_order is False


def test_segment_order_sorted_by_order_when_custom_order() -> None:
    seg1 = Segment(1)
    seg1.order = 2
    seg2 = Segment(2)
    seg2.order = 1
    map_data = MapData()
    map_data.segments = {1: seg1, 2: seg2}
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(map_manager=manager)
    assert status.segment_order == [2, 1]


def test_segment_order_none_when_segments_present_but_no_custom_order() -> None:
    """When segments exist but none carry a custom order, segment_order is None (not [] -
    the empty-list branch is reserved for the segments-are-empty case, see the test below)."""
    seg1 = Segment(1)
    seg1.order = None
    map_data = MapData()
    map_data.segments = {1: seg1}
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(map_manager=manager)
    assert status.custom_order is False
    assert status.segment_order is None


def test_segment_order_none_without_segments() -> None:
    status = _make_status()
    assert status.current_segments == {}
    assert status.segment_order is None


# ---------------------------------------------------------------------------
# has_saved_map / has_temporary_map / has_new_map
# ---------------------------------------------------------------------------


def test_has_saved_map_true_without_map_manager() -> None:
    status = _make_status()
    assert status.has_saved_map is True


def test_has_new_map_false_without_map_manager() -> None:
    status = _make_status()
    assert status.has_new_map is False


def test_has_temporary_map_false_without_map_manager() -> None:
    status = _make_status()
    assert status.has_temporary_map is False


def test_has_saved_map_true_when_status_is_two_and_no_temp_or_new_map() -> None:
    map_data = MapData()
    map_data.saved_map_status = 2
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(map_manager=manager)
    assert status.has_saved_map is True


def test_has_saved_map_false_when_temporary_map() -> None:
    map_data = MapData()
    map_data.saved_map_status = 2
    map_data.temporary_map = True
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(map_manager=manager)
    assert status.has_temporary_map is True
    assert status.has_saved_map is False


def test_has_new_map_true_when_new_map_and_not_temporary_or_empty() -> None:
    map_data = MapData()
    map_data.new_map = True
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(map_manager=manager)
    assert status.has_new_map is True


# ---------------------------------------------------------------------------
# selected_map / current_map
# ---------------------------------------------------------------------------


def test_selected_map_none_when_has_temporary_map() -> None:
    map_data = MapData()
    map_data.temporary_map = True
    manager = MagicMock(get_map=MagicMock(return_value=map_data), selected_map=map_data)
    status = _make_status(map_manager=manager)
    assert status.has_temporary_map is True
    assert status.selected_map is None


def test_selected_map_returns_manager_selected_map() -> None:
    map_data = MapData()
    selected = MapData()
    manager = MagicMock(get_map=MagicMock(return_value=map_data), selected_map=selected)
    status = _make_status(map_manager=manager)
    assert status.selected_map is selected


def test_current_map_none_without_map_manager() -> None:
    status = _make_status()
    assert status.current_map is None


# ---------------------------------------------------------------------------
# map_list / map_data_list
# ---------------------------------------------------------------------------


def test_map_list_empty_without_map_manager() -> None:
    status = _make_status()
    assert status.map_list == []


def test_map_list_returns_manager_map_list_when_multi_map() -> None:
    manager = MagicMock(map_list=[1, 2, 3])
    status = _make_status({DreameVacuumProperty.MULTI_FLOOR_MAP: 1}, map_manager=manager)
    assert status.multi_map is True
    assert status.map_list == [1, 2, 3]


def test_map_list_single_selected_map_when_not_multi_map() -> None:
    selected = MapData()
    selected.map_id = 4
    manager = MagicMock(selected_map=selected)
    status = _make_status(map_manager=manager)
    assert status.multi_map is False
    assert status.map_list == [4]


def test_map_data_list_empty_without_map_manager() -> None:
    status = _make_status()
    assert status.map_data_list == {}


def test_map_data_list_returns_manager_map_data_list_when_multi_map() -> None:
    map_data_list = {1: MapData(), 2: MapData()}
    manager = MagicMock(map_data_list=map_data_list)
    status = _make_status({DreameVacuumProperty.MULTI_FLOOR_MAP: 1}, map_manager=manager)
    assert status.multi_map is True
    assert status.map_data_list is map_data_list


def test_map_data_list_single_selected_map_when_not_multi_map() -> None:
    selected = MapData()
    selected.map_id = 8
    manager = MagicMock(selected_map=selected)
    status = _make_status(map_manager=manager)
    assert status.multi_map is False
    assert status.map_data_list == {8: selected}


# ---------------------------------------------------------------------------
# current_room
# ---------------------------------------------------------------------------


def test_current_room_none_without_lidar_navigation() -> None:
    seg = Segment(1)
    map_data = MapData()
    map_data.segments = {1: seg}
    map_data.robot_segment = 1
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    capability = _make_capability(lidar_navigation=False)
    status = _make_status(capability=capability, map_manager=manager)
    assert status.current_room is None


def test_current_room_none_without_robot_segment() -> None:
    map_data = MapData()
    map_data.segments = {1: Segment(1)}
    map_data.robot_segment = None
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    capability = _make_capability(lidar_navigation=True)
    status = _make_status(capability=capability, map_manager=manager)
    assert status.current_room is None


def test_current_room_returns_matching_segment() -> None:
    seg = Segment(3)
    map_data = MapData()
    map_data.segments = {3: seg}
    map_data.robot_segment = 3
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    capability = _make_capability(lidar_navigation=True)
    status = _make_status(capability=capability, map_manager=manager)
    assert status.current_room is seg


# ---------------------------------------------------------------------------
# cleaning_sequence / previous_cleaning_sequence
# ---------------------------------------------------------------------------


def test_cleaning_sequence_none_without_map_manager() -> None:
    status = _make_status()
    assert status.cleaning_sequence is None


def test_cleaning_sequence_returns_manager_value() -> None:
    manager = MagicMock(cleaning_sequence=[3, 1, 2])
    status = _make_status(map_manager=manager)
    assert status.cleaning_sequence == [3, 1, 2]


def test_previous_cleaning_sequence_none_without_current_map() -> None:
    status = _make_status()
    assert status.previous_cleaning_sequence is None


def test_previous_cleaning_sequence_none_when_map_id_not_recorded() -> None:
    map_data = MapData()
    map_data.map_id = 1
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(map_manager=manager)
    status._previous_cleaning_sequence = {2: [1, 2]}
    assert status.previous_cleaning_sequence is None


def test_previous_cleaning_sequence_returns_recorded_value() -> None:
    map_data = MapData()
    map_data.map_id = 5
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(map_manager=manager)
    status._previous_cleaning_sequence = {5: [2, 1, 3]}
    assert status.previous_cleaning_sequence == [2, 1, 3]


# ---------------------------------------------------------------------------
# active_segments
# ---------------------------------------------------------------------------


def test_active_segments_none_without_map() -> None:
    status = _make_status()
    assert status.active_segments is None


def test_active_segments_none_when_not_started() -> None:
    map_data = MapData()
    map_data.segments = {1: Segment(1)}
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(_not_started_properties(), map_manager=manager)
    assert status.started is False
    assert status.active_segments is None


def test_active_segments_from_segment_cleaning() -> None:
    map_data = MapData()
    map_data.active_segments = [4, 5]
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(
        {DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.SEGMENT_CLEANING_PAUSED.value}, map_manager=manager
    )
    assert status.segment_cleaning is True
    assert status.active_segments == [4, 5]


def test_active_segments_empty_when_segment_cleaning_without_active_segments() -> None:
    map_data = MapData()
    map_data.active_segments = None
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(
        {DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.SEGMENT_CLEANING_PAUSED.value}, map_manager=manager
    )
    assert status.segment_cleaning is True
    assert status.active_segments == []


def test_active_segments_all_map_segments_when_running_whole_map() -> None:
    seg = Segment(1)
    map_data = MapData()
    map_data.segments = {1: seg}
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status({DreameVacuumProperty.STATUS: DreameVacuumStatus.CLEANING.value}, map_manager=manager)
    assert status.segment_cleaning is False
    assert status.docked is False
    assert status.active_segments == [1]


def test_active_segments_empty_when_zone_cleaning() -> None:
    seg = Segment(1)
    map_data = MapData()
    map_data.segments = {1: seg}
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(
        {DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.ZONE_CLEANING.value}, map_manager=manager
    )
    assert status.zone_cleaning is True
    assert status.active_segments == []


# ---------------------------------------------------------------------------
# segment_order_list
# ---------------------------------------------------------------------------


def test_segment_order_list_empty_without_segments() -> None:
    status = _make_status()
    target = Segment(1)
    assert status.segment_order_list(target) == []


def test_segment_order_list_orders_by_segment_order() -> None:
    seg1 = Segment(1)
    seg1.order = 2
    seg2 = Segment(2)
    seg2.order = 1
    map_data = MapData()
    map_data.segments = {1: seg1, 2: seg2}
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(map_manager=manager)
    assert status.segment_order_list(seg1) == ["1", "2"]


def test_segment_order_list_appends_next_order_for_unordered_segment() -> None:
    seg1 = Segment(1)
    seg1.order = 2
    map_data = MapData()
    map_data.segments = {1: seg1}
    manager = MagicMock(get_map=MagicMock(return_value=map_data))
    status = _make_status(map_manager=manager)
    unordered = Segment(2)
    unordered.order = None
    assert status.segment_order_list(unordered) == ["2", "3"]
