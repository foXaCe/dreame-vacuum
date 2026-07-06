"""Characterization tests for the deep I-frame branches of DreameMapVacuumMapManager._add_map_data.

These target the parts of the I-frame handling that the queue-focused suite
(test_map_manager_queue.py) does not exercise:
- merging an I frame's embedded saved_map_data into self._saved_map_data
- vslam-specific segment/robot_position restoration
- the _updated_frame_id "optimistic edit" carry-over window
- the need_optimization carry-over shortcut

DreameVacuumMapDecoder.decode_map_data_from_partial is monkeypatched so each test
controls exactly what a "decoded" I frame + embedded saved map looks like.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
from custom_components.dreame_vacuum.dreame.map_manager import DreameMapVacuumMapManager
from custom_components.dreame_vacuum.dreame.vacuum_types import MapData, MapDataPartial, MapFrameType, Point


@pytest.fixture
def protocol() -> MagicMock:
    proto = MagicMock()
    proto.dreame_cloud = False
    proto.cloud = MagicMock()
    proto.cloud.dreame_cloud = False
    proto.cloud.logged_in = True
    proto.cloud.connected = True
    return proto


@pytest.fixture
def manager(protocol: MagicMock) -> DreameMapVacuumMapManager:
    mgr = DreameMapVacuumMapManager(protocol)
    mgr._change_callback = MagicMock()
    mgr._update_callback = MagicMock()
    return mgr


def _partial(map_id: int, frame_id: int, timestamp_ms: int) -> MapDataPartial:
    p = MapDataPartial()
    p.map_id = map_id
    p.frame_id = frame_id
    p.frame_type = MapFrameType.I.value
    p.timestamp_ms = timestamp_ms
    return p


def _map(map_id: int, frame_id: int, timestamp_ms: int, **overrides: object) -> MapData:
    md = MapData()
    md.map_id = map_id
    md.frame_id = frame_id
    md.frame_type = MapFrameType.I.value
    md.timestamp_ms = timestamp_ms
    for key, value in overrides.items():
        setattr(md, key, value)
    return md


# ---------------------------------------------------------------------------
# Embedded saved_map_data merge into self._saved_map_data
# ---------------------------------------------------------------------------


def test_iframe_saved_map_updates_existing_entry_and_copies_display_fields(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    An I frame whose embedded saved_map_data matches a known map_id updates that entry:
    display fields (name/rotation/index/recovery list) are copied FROM the existing
    entry (the device does not know about user-set custom names), and a real content
    change schedules a map-list refresh on non dreame_cloud devices.
    """
    manager._latest_map_id = 1
    existing = _map(
        map_id=5,
        frame_id=0,
        timestamp_ms=100,
        custom_name="Kitchen",
        map_name="Kitchen",
        rotation=90,
        map_index=2,
        recovery_map_list=["existing_recovery"],
        work_status=1,
    )
    manager._saved_map_data = {5: existing}
    manager.request_next_map_list = MagicMock()

    saved_map_data = _map(map_id=5, frame_id=0, timestamp_ms=200, saved_map=True, work_status=2)  # content differs
    # map_data.saved_map=True short-circuits the "changed" detection block entirely,
    # isolating this test to the saved_map_data merge logic only.
    top_map_data = _map(map_id=1, frame_id=0, timestamp_ms=200, saved_map=True)
    monkeypatch.setattr(
        DreameVacuumMapDecoder,
        "decode_map_data_from_partial",
        MagicMock(return_value=(top_map_data, saved_map_data)),
    )

    result = manager._add_map_data(_partial(map_id=1, frame_id=0, timestamp_ms=200))

    assert result is True
    updated = manager._saved_map_data[5]
    assert updated.custom_name == "Kitchen"
    assert updated.map_name == "Kitchen"
    assert updated.rotation == 90
    assert updated.map_index == 2
    assert updated.recovery_map_list == ["existing_recovery"]
    assert updated.timestamp_ms == 200
    assert top_map_data.temporary_map is False
    assert manager._selected_map_id == 5
    manager.request_next_map_list.assert_called_once()
    # map_data.saved_map=True means the *live* map tracking must stay untouched.
    assert manager._map_data is None
    assert manager._current_frame_id is None


def test_iframe_saved_map_unchanged_content_skips_map_list_refresh(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the embedded saved_map_data is identical to what's already stored, no refresh is scheduled."""
    manager._latest_map_id = 1
    existing = _map(map_id=5, frame_id=0, timestamp_ms=100, saved_map=True, work_status=1, segments=None)
    manager._saved_map_data = {5: existing}
    manager.request_next_map_list = MagicMock()

    # Same work_status and segments as `existing` -> content-equal -> "not changed" path.
    saved_map_data = _map(map_id=5, frame_id=0, timestamp_ms=200, saved_map=True, work_status=1, segments=None)
    top_map_data = _map(map_id=1, frame_id=0, timestamp_ms=200, saved_map=True)
    monkeypatch.setattr(
        DreameVacuumMapDecoder,
        "decode_map_data_from_partial",
        MagicMock(return_value=(top_map_data, saved_map_data)),
    )

    manager._add_map_data(_partial(map_id=1, frame_id=0, timestamp_ms=200))

    manager.request_next_map_list.assert_not_called()
    # Timestamp/custom fields are only copied on the "changed" path, so the original
    # existing entry object is left in place untouched.
    assert manager._saved_map_data[5] is existing


@pytest.mark.parametrize("device_running", [False, True])
def test_iframe_saved_map_new_entry_registers_and_refreshes_list(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch, device_running: bool
) -> None:
    """
    A brand new (non-temporary) saved map not yet known is added to _saved_map_data and
    the map list is refreshed; request_next_map_list() is used while cleaning is running,
    request_map_list() while idle (both non dreame_cloud paths).
    """
    manager._latest_map_id = 1
    manager._saved_map_data = {}
    manager._map_list = []
    manager._device_running = device_running
    manager.request_next_map_list = MagicMock()
    manager.request_map_list = MagicMock()

    saved_map_data = _map(map_id=7, frame_id=0, timestamp_ms=200, saved_map=True)
    top_map_data = _map(map_id=1, frame_id=0, timestamp_ms=200, saved_map=True, temporary_map=False)
    monkeypatch.setattr(
        DreameVacuumMapDecoder,
        "decode_map_data_from_partial",
        MagicMock(return_value=(top_map_data, saved_map_data)),
    )

    manager._add_map_data(_partial(map_id=1, frame_id=0, timestamp_ms=200))

    assert manager._saved_map_data[7] is saved_map_data
    assert manager._map_list == [7]  # populated by the real _refresh_map_list() call
    if device_running:
        manager.request_next_map_list.assert_called_once()
        manager.request_map_list.assert_not_called()
    else:
        manager.request_map_list.assert_called_once()
        manager.request_next_map_list.assert_not_called()


def test_iframe_saved_map_new_entry_notifies_live_map_and_propagates_wifi_timestamp(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Registering a brand new saved map while a *live* map is already being tracked fires
    _map_data_changed() (the room list shown for the live map may now include this map),
    and a wifi_map_data sub-object's last_updated is kept in sync with its parent.
    """
    manager._latest_map_id = 1
    manager._saved_map_data = {}
    manager._map_list = []
    manager._device_running = False
    manager.request_map_list = MagicMock()
    live_map = _map(map_id=1, frame_id=3, timestamp_ms=100)
    manager._map_data = live_map  # a live map is already being displayed
    # Keep current_frame_id/timestamp consistent with the live map so the unrelated
    # "stale map_data" tail cleanup (current_frame_id is None) does not also fire and
    # cause a second, unrelated _map_data_changed() call.
    manager._current_map_id = 1
    manager._current_frame_id = 3
    manager._current_timestamp_ms = 100

    wifi_sub_map = _map(map_id=7, frame_id=0, timestamp_ms=1)
    saved_map_data = _map(map_id=7, frame_id=0, timestamp_ms=200, saved_map=True, wifi_map_data=wifi_sub_map)
    top_map_data = _map(map_id=1, frame_id=0, timestamp_ms=200, saved_map=True, temporary_map=False)
    monkeypatch.setattr(
        DreameVacuumMapDecoder,
        "decode_map_data_from_partial",
        MagicMock(return_value=(top_map_data, saved_map_data)),
    )

    manager._add_map_data(_partial(map_id=1, frame_id=0, timestamp_ms=200))

    assert manager._saved_map_data[7] is saved_map_data
    manager._change_callback.assert_called_once_with(False)
    assert wifi_sub_map.last_updated == saved_map_data.last_updated


def test_iframe_saved_map_existing_entry_update_propagates_wifi_timestamp(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Updating a known saved map also refreshes its wifi_map_data sub-object's last_updated."""
    manager._latest_map_id = 1
    existing = _map(map_id=5, frame_id=0, timestamp_ms=100, saved_map=True, work_status=1)
    manager._saved_map_data = {5: existing}
    manager.request_next_map_list = MagicMock()

    wifi_sub_map = _map(map_id=5, frame_id=0, timestamp_ms=1)
    saved_map_data = _map(
        map_id=5, frame_id=0, timestamp_ms=200, saved_map=True, work_status=2, wifi_map_data=wifi_sub_map
    )
    top_map_data = _map(map_id=1, frame_id=0, timestamp_ms=200, saved_map=True)
    monkeypatch.setattr(
        DreameVacuumMapDecoder,
        "decode_map_data_from_partial",
        MagicMock(return_value=(top_map_data, saved_map_data)),
    )

    manager._add_map_data(_partial(map_id=1, frame_id=0, timestamp_ms=200))

    assert wifi_sub_map.last_updated == manager._saved_map_data[5].last_updated


def test_iframe_map_index_copied_from_known_saved_map_id(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live (non-saved) frame that references a known saved_map_id inherits that map's display index."""
    manager._latest_map_id = 1
    manager._saved_map_data = {5: _map(map_id=5, frame_id=0, timestamp_ms=1, map_index=3)}

    top_map_data = _map(
        map_id=1,
        frame_id=0,
        timestamp_ms=200,
        saved_map=False,
        saved_map_id=5,
        work_status=7,  # forces `changed` True regardless
    )
    monkeypatch.setattr(
        DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(top_map_data, None))
    )

    manager._add_map_data(_partial(map_id=1, frame_id=0, timestamp_ms=200))

    assert manager._map_data.map_index == 3


def test_iframe_saved_map_temporary_and_unknown_is_ignored(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A temporary map (not yet promoted to a saved map) that's also unknown is simply skipped."""
    manager._latest_map_id = 1
    manager._saved_map_data = {}
    manager.request_next_map_list = MagicMock()
    manager.request_map_list = MagicMock()

    saved_map_data = _map(map_id=9, frame_id=0, timestamp_ms=200, saved_map=True)
    top_map_data = _map(map_id=1, frame_id=0, timestamp_ms=200, saved_map=True, temporary_map=True)
    monkeypatch.setattr(
        DreameVacuumMapDecoder,
        "decode_map_data_from_partial",
        MagicMock(return_value=(top_map_data, saved_map_data)),
    )

    manager._add_map_data(_partial(map_id=1, frame_id=0, timestamp_ms=200))

    assert manager._saved_map_data == {}
    manager.request_next_map_list.assert_not_called()
    manager.request_map_list.assert_not_called()


# ---------------------------------------------------------------------------
# vslam-specific handling (only reachable when `not map_data.saved_map`)
# ---------------------------------------------------------------------------


def test_iframe_vslam_docked_saved_map_restores_segments_from_saved_map(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A vslam device reporting saved_map_status==1 while docked overlays the room layout
    from the accompanying saved_map_data onto the live map (the live scan doesn't carry
    segment boundaries in this mode).
    """
    manager._vslam_map = True
    manager._device_docked = True
    manager._latest_map_id = 1

    saved_map_data = _map(
        map_id=1,
        frame_id=0,
        timestamp_ms=50,
        segments={"1": "room"},
        data="saved_data",
        pixel_type="saved_pixels",
        dimensions="saved_dims",
        charger_position=Point(0, 0),
        no_go_areas=["ng"],
        no_mopping_areas=["nm"],
        virtual_walls=["vw"],
    )
    top_map_data = _map(
        map_id=1,
        frame_id=1,
        timestamp_ms=200,
        saved_map=False,
        saved_map_status=1,
        work_status=42,  # forces content inequality vs a fresh MapData() so `changed` stays True
    )
    monkeypatch.setattr(
        DreameVacuumMapDecoder,
        "decode_map_data_from_partial",
        MagicMock(return_value=(top_map_data, saved_map_data)),
    )

    result = manager._add_map_data(_partial(map_id=1, frame_id=1, timestamp_ms=200))

    assert result is True
    applied = manager._map_data
    assert applied.segments == {"1": "room"}
    assert applied.data == "saved_data"
    assert applied.pixel_type == "saved_pixels"
    assert applied.dimensions == "saved_dims"
    assert applied.no_go_areas == ["ng"]
    assert applied.no_mopping_areas == ["nm"]
    assert applied.virtual_walls == ["vw"]
    assert applied.docked is True
    assert applied.path is None
    assert applied.need_optimization is False
    assert applied.saved_map_status == 2
    manager._change_callback.assert_called_once_with(False)


def test_iframe_vslam_restored_map_inherits_previous_robot_position(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A vslam restored_map frame with no robot_position of its own, arriving while the robot
    isn't docked, inherits the last known robot_position from the previously tracked map
    (rather than showing the robot as vanished).
    """
    manager._vslam_map = True
    manager._device_docked = False
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 5
    manager._current_timestamp_ms = 1000
    manager._map_data = _map(map_id=1, frame_id=5, timestamp_ms=1000, robot_position=Point(3, 3))

    new_map = _map(
        map_id=1,
        frame_id=6,
        timestamp_ms=2000,
        saved_map=False,
        saved_map_status=None,
        robot_position=None,
        restored_map=True,
        docked=False,
        work_status=7,  # forces `changed` True regardless of carry-over subtleties
    )
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(new_map, None)))

    result = manager._add_map_data(_partial(map_id=1, frame_id=6, timestamp_ms=2000))

    assert result is True
    assert manager._map_data.robot_position == Point(3, 3)


# ---------------------------------------------------------------------------
# _updated_frame_id: optimistic-edit carry-over window
# ---------------------------------------------------------------------------


def test_iframe_within_updated_frame_id_window_carries_over_optimistic_edits(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A fresh I frame arriving while an optimistic local edit is still "in flight"
    (_updated_frame_id set) and the previous map is in the "active cleaning" state
    (saved_map_status == 2) has its transient cleaning-session fields overwritten by
    whatever the editor last applied, instead of reverting to the device's stale view.
    """
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 5
    manager._current_timestamp_ms = 1000
    manager._updated_frame_id = 6  # optimistic edit applied "as of" frame 6

    old_map = _map(
        map_id=1,
        frame_id=5,
        timestamp_ms=1000,
        empty_map=False,
        saved_map_status=2,
        active_segments=["A"],
        active_areas=["B"],
        active_points=["C"],
        active_cruise_points=["D"],
        path=["P"],
        segments={"s": 1},
        floor_material={"f": 1},
        hidden_segments=[1],
        cleanset="CS",
        carpet_cleanset="CC",
        work_status=1,
    )
    manager._map_data = old_map

    new_map = _map(
        map_id=1,
        frame_id=7,  # <= updated_frame_id(6) + 1 -> still within the carry-over window
        timestamp_ms=2000,
        active_segments=["NEW"],
        path=["NEW_PATH"],
        cleanset="NEW_CS",
        work_status=99,  # differs from old_map -> guarantees `changed` stays True either way
    )
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(new_map, None)))

    result = manager._add_map_data(_partial(map_id=1, frame_id=7, timestamp_ms=2000))

    assert result is True
    applied = manager._map_data
    assert applied.active_segments == ["A"]
    assert applied.active_areas == ["B"]
    assert applied.active_points == ["C"]
    assert applied.active_cruise_points == ["D"]
    assert applied.path == ["P"]
    assert applied.segments == {"s": 1}
    assert applied.floor_material == {"f": 1}
    assert applied.hidden_segments == [1]
    assert applied.cleanset == "CS"
    assert applied.carpet_cleanset == "CC"
    assert manager._current_frame_id == 7
    manager._change_callback.assert_called_once_with(False)


def test_iframe_beyond_updated_frame_id_window_clears_it_without_carry_over(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A frame_id further ahead than updated_frame_id+1 drops the optimistic-edit window entirely."""
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 5
    manager._current_timestamp_ms = 1000
    manager._updated_frame_id = 2  # window closes at frame 3

    old_map = _map(map_id=1, frame_id=5, timestamp_ms=1000, active_segments=["A"], work_status=1)
    manager._map_data = old_map

    new_map = _map(map_id=1, frame_id=10, timestamp_ms=2000, active_segments=["NEW"], work_status=2)
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(new_map, None)))

    manager._add_map_data(_partial(map_id=1, frame_id=10, timestamp_ms=2000))

    assert manager._updated_frame_id is None
    assert manager._map_data.active_segments == ["NEW"]  # NOT carried over


def test_iframe_updated_frame_id_window_but_wrong_status_forces_empty_map(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Within the carry-over window but the previous map isn't in an "active session" state
    (saved_map_status != 2, and not the vslam saved_map_status==1 special case): the new
    frame is forced to empty_map=True and treated as unchanged (no notification), rather
    than showing a half-formed map.
    """
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 5
    manager._current_timestamp_ms = 1000
    manager._updated_frame_id = 6
    manager._vslam_map = False

    old_map = _map(map_id=1, frame_id=5, timestamp_ms=1000, empty_map=False, saved_map_status=0)
    manager._map_data = old_map

    new_map = _map(map_id=1, frame_id=7, timestamp_ms=2000, empty_map=False)
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(new_map, None)))

    manager._add_map_data(_partial(map_id=1, frame_id=7, timestamp_ms=2000))

    assert manager._map_data.empty_map is True
    manager._change_callback.assert_not_called()


# ---------------------------------------------------------------------------
# need_optimization carry-over shortcut
# ---------------------------------------------------------------------------


def test_iframe_need_optimization_carries_over_previous_optimized_pixel_data(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    When the new frame is content-identical to the previous one (per MapData.__eq__) but
    flags need_optimization while the previous frame had already been optimized, the
    manager reuses the previous optimized_pixel_type/dimensions/charger_position instead
    of paying for another optimization pass.
    """
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 5
    manager._current_timestamp_ms = 1000
    manager._updated_frame_id = None  # keep the optimistic-edit window out of the way

    old_map = _map(
        map_id=1,
        frame_id=5,
        timestamp_ms=1000,
        need_optimization=False,
        optimized_pixel_type="OLD_PIXELS",
        optimized_dimensions="OLD_DIMS",
        optimized_charger_position="OLD_CHARGER",
    )
    manager._map_data = old_map

    # Content-equal to old_map (all MapData.__eq__ fields default/None on both, map_id
    # matches) but a different frame_id, so the outer "changed-or-frame-moved" gate opens
    # even though the recomputed `changed` stays False.
    new_map = _map(map_id=1, frame_id=6, timestamp_ms=2000, need_optimization=True)
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(new_map, None)))

    manager._add_map_data(_partial(map_id=1, frame_id=6, timestamp_ms=2000))

    applied = manager._map_data
    assert applied.need_optimization is False
    assert applied.optimized_pixel_type == "OLD_PIXELS"
    assert applied.optimized_dimensions == "OLD_DIMS"
    assert applied.optimized_charger_position == "OLD_CHARGER"
    # Genuinely unchanged content -> no notification fired.
    manager._change_callback.assert_not_called()
