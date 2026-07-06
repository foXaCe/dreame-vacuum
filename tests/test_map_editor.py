"""Characterization tests for DreameMapVacuumMapEditor.

The editor applies optimistic in-memory edits on the MapData objects owned by
the map manager, then schedules a debounced refresh via ``threading.Timer``
before the (mocked) map manager is asked to notify listeners. These tests use
the real ``MapData``/``Segment``/``Point``/``Area``/``Wall`` classes from
``vacuum_types`` but a fully mocked map manager, and replace ``Timer`` with an
in-process fake so the debounce can be inspected/fired synchronously.
"""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock

import numpy as np
import pytest

import custom_components.dreame_vacuum.dreame.map_editor as map_editor_module
from custom_components.dreame_vacuum.dreame.map_editor import DreameMapVacuumMapEditor
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    Area,
    MapData,
    MapImageDimensions,
    Point,
    Segment,
    Wall,
)

# ---------------------------------------------------------------------------
# Fake Timer: replaces threading.Timer so refresh_map()'s debounce never
# spawns a real thread. Tests can fire() the most recent instance to
# simulate the 0.5s debounce elapsing.
# ---------------------------------------------------------------------------


class _FakeTimer:
    instances: ClassVar[list[_FakeTimer]] = []

    def __init__(self, interval: float, function: object, args: list[object] | None = None) -> None:
        self.interval = interval
        self.function = function
        self.args = list(args) if args else []
        self.started = False
        self.cancelled = False
        _FakeTimer.instances.append(self)

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        """Simulate the debounce elapsing: invoke the deferred callback."""
        if not self.cancelled:
            self.function(*self.args)


@pytest.fixture(autouse=True)
def fake_timer(monkeypatch: pytest.MonkeyPatch) -> type[_FakeTimer]:
    _FakeTimer.instances = []
    monkeypatch.setattr(map_editor_module, "Timer", _FakeTimer)
    return _FakeTimer


@pytest.fixture
def manager() -> MagicMock:
    """A MagicMock standing in for DreameMapVacuumMapManager."""
    m = MagicMock()
    m._map_data = None
    m._saved_map_data = {}
    m._selected_map_id = None
    m._capability = MagicMock()
    m._capability.carpet_cleanset_v3 = False
    m._capability.mop_clean_frequency = False
    m._capability.wetness_level = False
    m._vslam_map = False
    m._current_timestamp_ms = 12345
    return m


@pytest.fixture
def editor(manager: MagicMock) -> DreameMapVacuumMapEditor:
    return DreameMapVacuumMapEditor(manager)


def _segment(segment_id: int, **overrides: object) -> Segment:
    seg = Segment(segment_id)
    for key, value in overrides.items():
        setattr(seg, key, value)
    return seg


def _map_data(**overrides: object) -> MapData:
    md = MapData()
    for key, value in overrides.items():
        setattr(md, key, value)
    return md


# ---------------------------------------------------------------------------
# 1. set_rotation / set_active_areas / set_active_points / set_zones
# ---------------------------------------------------------------------------


def test_set_rotation_updates_saved_map_only_when_not_selected(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    saved = _map_data(rotation=0, segments=None)
    manager._saved_map_data = {5: saved}
    manager._map_data = None  # nothing currently selected

    editor.set_rotation(5, 90)

    assert saved.rotation == 90
    # Only the saved-map refresh fires; no "current map" refresh.
    assert len(_FakeTimer.instances) == 1
    assert _FakeTimer.instances[0].args == [5]
    _FakeTimer.instances[0].fire()
    manager._map_data_updated.assert_called_once()


def test_set_rotation_also_updates_selected_current_map(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    saved = _map_data(rotation=0, segments=None)
    current = _map_data(rotation=0, segments=None)
    manager._saved_map_data = {5: saved}
    manager._map_data = current
    manager._selected_map_id = 5

    editor.set_rotation(5, 270)

    assert saved.rotation == 270
    assert current.rotation == 270
    # First Timer (no map_id) is cancelled by the second refresh_map(map_id) call.
    assert len(_FakeTimer.instances) == 2
    assert _FakeTimer.instances[0].args == [None]
    assert _FakeTimer.instances[0].cancelled is True
    assert _FakeTimer.instances[1].args == [5]
    assert _FakeTimer.instances[1].cancelled is False


def test_set_rotation_noop_when_map_id_unknown(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    manager._saved_map_data = {}

    editor.set_rotation(99, 90)

    assert _FakeTimer.instances == []


def test_set_active_areas_sorts_coordinates_and_clears_cruise_points(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    map_data = _map_data(frame_id=7, active_cruise_points={1: object()})
    manager._map_data = map_data

    editor.set_active_areas([[10, 20, 0, 0]])

    assert map_data.active_cruise_points is None
    assert map_data.active_areas == [Area(0, 0, 10, 0, 10, 20, 0, 20)]
    assert manager._updated_frame_id == 7
    assert len(_FakeTimer.instances) == 1
    assert _FakeTimer.instances[0].args == [None]


def test_set_active_areas_noop_without_map_data(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    manager._map_data = None

    editor.set_active_areas([[0, 0, 1, 1]])

    assert _FakeTimer.instances == []


def test_set_active_points_builds_point_list(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    map_data = _map_data(frame_id=3)
    manager._map_data = map_data

    editor.set_active_points([[5, 6], [7, 8]])

    assert map_data.active_points == [Point(5, 6), Point(7, 8)]
    assert manager._updated_frame_id == 3
    assert len(_FakeTimer.instances) == 1


def test_set_zones_builds_walls_and_areas_and_syncs_saved_map(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    map_data = _map_data(frame_id=1)
    saved = _map_data()
    manager._map_data = map_data
    manager._selected_map_id = 9
    manager._saved_map_data = {9: saved}

    editor.set_zones(
        virtual_walls=[[0, 0, 10, 0]],
        no_go_areas=[[0, 0, 5, 5]],
        no_mopping_areas=[[1, 1, 4, 9]],
    )

    assert map_data.virtual_walls == [Wall(0, 0, 10, 0)]
    assert map_data.no_go_areas == [Area(0, 0, 5, 0, 5, 5, 0, 5)]
    assert map_data.no_mopping_areas == [Area(1, 1, 4, 1, 4, 9, 1, 9)]
    assert saved.no_go_areas == map_data.no_go_areas
    assert saved.no_mopping_areas == map_data.no_mopping_areas
    assert saved.virtual_walls == map_data.virtual_walls
    assert manager._updated_frame_id == 1
    # One refresh for the saved map, one for the current map.
    assert len(_FakeTimer.instances) == 2
    assert _FakeTimer.instances[0].args == [9]
    assert _FakeTimer.instances[1].args == [None]


def test_set_zones_empty_inputs_clear_lists(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    map_data = _map_data(frame_id=1, virtual_walls=[Wall(0, 0, 1, 1)])
    manager._map_data = map_data
    # Selected, but absent from _saved_map_data -> mutation happens without a
    # saved-map sync/refresh.
    manager._selected_map_id = 1
    manager._saved_map_data = {}

    editor.set_zones(virtual_walls=None, no_go_areas=None, no_mopping_areas=None)

    assert map_data.virtual_walls == []
    assert map_data.no_go_areas == []
    assert map_data.no_mopping_areas == []
    assert len(_FakeTimer.instances) == 1
    assert _FakeTimer.instances[0].args == [None]


def test_set_zones_noop_without_selected_map(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    manager._map_data = _map_data()
    manager._selected_map_id = None
    manager._map_data.no_go_areas = None

    # _selected_map_id is falsy -> function returns before any mutation.
    editor.set_zones([], [], [])

    assert manager._map_data.no_go_areas is None
    assert _FakeTimer.instances == []


# ---------------------------------------------------------------------------
# 2. Segments: set_segment_name, set_segment_order, cleanset per-room setters,
#    set_segment_floor_material
# ---------------------------------------------------------------------------


def test_set_segment_name_custom_name(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    seg = _segment(1, type=0, custom_name=None)
    saved_seg = _segment(1, type=0, custom_name=None)
    map_data = _map_data(frame_id=4, segments={1: seg})
    saved = _map_data(segments={1: saved_seg})
    manager._map_data = map_data
    manager._selected_map_id = 2
    manager._saved_map_data = {2: saved}

    result = editor.set_segment_name(1, 0, "Kitchen")

    assert seg.custom_name == "Kitchen"
    assert seg.index == 0
    assert saved_seg.custom_name == "Kitchen"
    assert result is not None
    entry = result[1]
    assert entry["type"] == 0
    assert entry["index"] == 0
    import base64

    assert entry["name"] == base64.b64encode(b"Kitchen").decode("utf-8")
    assert manager._updated_frame_id == 4
    assert len(_FakeTimer.instances) == 2
    assert _FakeTimer.instances[0].args == [2]
    assert _FakeTimer.instances[1].args == [None]


def test_set_segment_name_predefined_type_computes_index(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    seg1 = _segment(1, type=1, index=0, custom_name=None)
    seg2 = _segment(2, type=0, custom_name=None)
    map_data = _map_data(segments={1: seg1, 2: seg2})
    saved = _map_data(segments={2: _segment(2, type=0, custom_name=None)})
    manager._map_data = map_data
    manager._selected_map_id = 3
    manager._saved_map_data = {3: saved}

    result = editor.set_segment_name(2, 1, None)

    assert seg2.type == 1
    assert seg2.custom_name is None
    # segment 1 already occupies index 0 for type 1, so segment 2 gets index 1.
    assert seg2.index == 1
    assert result is not None
    assert result[2] == {"type": 1, "index": 1}


def test_set_segment_name_returns_none_when_unchanged(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    seg = _segment(1, type=0, custom_name="Office")
    map_data = _map_data(segments={1: seg})
    manager._map_data = map_data
    manager._selected_map_id = 1
    manager._saved_map_data = {1: map_data}

    result = editor.set_segment_name(1, 0, "Office")

    assert result is None
    assert _FakeTimer.instances == []


def test_set_segment_name_returns_none_for_unknown_segment(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    map_data = _map_data(segments={1: _segment(1)})
    manager._map_data = map_data
    manager._selected_map_id = 1

    assert editor.set_segment_name(99, 0, "X") is None


def test_set_segment_name_returns_none_for_temporary_map(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    map_data = _map_data(segments={1: _segment(1)}, temporary_map=True)
    manager._map_data = map_data
    manager._selected_map_id = 1

    assert editor.set_segment_name(1, 0, "X") is None


def test_set_segment_name_includes_unique_id(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    seg = _segment(1, type=0, custom_name=None, unique_id="abc-123")
    map_data = _map_data(segments={1: seg})
    saved = _map_data(segments={1: _segment(1, type=0, custom_name=None)})
    manager._map_data = map_data
    manager._selected_map_id = 1
    manager._saved_map_data = {1: saved}

    result = editor.set_segment_name(1, 0, "Bath")

    assert result[1]["roomID"] == "abc-123"


def test_set_segment_order_assigns_and_reindexes(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    seg1 = _segment(1, order=None)
    seg2 = _segment(2, order=None)
    map_data = _map_data(
        segments={1: seg1, 2: seg2},
        cleanset={"1": [1, 3, 1, 0], "2": [1, 3, 1, 0]},
    )
    manager._map_data = map_data
    manager.cleaning_sequence = [1, 2]
    manager._selected_map_id = 1
    manager._saved_map_data = {1: map_data}

    result = editor.set_segment_order(2, 1)

    assert seg2.order == 1
    assert map_data.cleanset["2"][3] == 1
    assert map_data.cleanset["1"][3] == 0
    assert result == [1, 2]
    assert manager._saved_map_data[1].cleanset == map_data.cleanset


def test_set_segment_order_reset_to_zero(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    seg1 = _segment(1, order=2)
    map_data = _map_data(segments={1: seg1}, cleanset={"1": [1, 3, 1, 2]})
    manager._map_data = map_data
    manager.cleaning_sequence = [1]

    editor.set_segment_order(1, 0)

    assert seg1.order == 0
    assert map_data.cleanset["1"][3] == 0


def test_set_segment_order_returns_none_for_unknown_segment(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    map_data = _map_data(segments={1: _segment(1)})
    manager._map_data = map_data

    assert editor.set_segment_order(99, 1) is None


def test_cleanset_defaults_and_incremental_extra_fields(editor: DreameMapVacuumMapEditor) -> None:
    seg1 = _segment(1, suction_level=2, water_volume=1, cleaning_times=2)
    seg2 = _segment(
        2,
        suction_level=3,
        water_volume=None,
        cleaning_times=None,
        wetness_level=10,
        cleaning_mode=1,
        mopping_settings=5,
    )
    map_data = _map_data(segments={1: seg1, 2: seg2})

    result = editor.cleanset(map_data)

    assert result == [[1, 2, 2, 2], [2, 3, 10, 1, 1, 5]]
    # Defaults were applied in-place for segment 2.
    assert seg2.water_volume == 2
    assert seg2.cleaning_times == 1


def test_set_segment_suction_level_updates_cleanset_and_saved_map(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    seg = _segment(1, suction_level=1)
    map_data = _map_data(segments={1: seg}, cleanset={"1": [1, 3, 1, 0]})
    manager._map_data = map_data
    manager._selected_map_id = 1
    manager._saved_map_data = {1: map_data}

    result = editor.set_segment_suction_level(1, 3)

    assert seg.suction_level == 3
    assert map_data.cleanset["1"][0] == 3
    assert result == [[1, 3, 3, 1]]
    assert len(_FakeTimer.instances) == 1


def test_set_segment_suction_level_no_refresh_returns_none(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    seg = _segment(1, suction_level=1)
    map_data = _map_data(segments={1: seg}, cleanset={"1": [1, 3, 1, 0]})
    manager._map_data = map_data

    result = editor.set_segment_suction_level(1, 3, refresh_map=False)

    assert seg.suction_level == 3
    assert result is None
    assert _FakeTimer.instances == []


def test_set_segment_water_volume_updates_mopping_settings_when_custom_route(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    seg = _segment(1, water_volume=1, custom_mopping_route=-1, mopping_settings=0)
    map_data = _map_data(segments={1: seg}, cleanset={"1": [1, 3, 1, 0, 2, 0]})
    manager._map_data = map_data

    result = editor.set_segment_water_volume(1, 3)

    assert seg.water_volume == 3
    assert map_data.cleanset["1"][1] == 4
    assert result is not None


def test_set_segment_cleaning_times_updates_cleanset(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    seg = _segment(1, cleaning_times=1)
    map_data = _map_data(segments={1: seg}, cleanset={"1": [1, 3, 1, 0]})
    manager._map_data = map_data

    result = editor.set_segment_cleaning_times(1, 3)

    assert seg.cleaning_times == 3
    assert map_data.cleanset["1"][2] == 3
    assert result == [[1, 1, 3, 3]]


def test_set_segment_cleaning_times_noop_for_temporary_map(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    seg = _segment(1, cleaning_times=1)
    map_data = _map_data(segments={1: seg}, cleanset={"1": [1, 3, 1, 0]}, temporary_map=True)
    manager._map_data = map_data

    assert editor.set_segment_cleaning_times(1, 3) is None
    assert seg.cleaning_times == 1


def test_set_segment_floor_material_updates_segment_and_returns_all_segments(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    seg1 = _segment(1, floor_material=None, floor_material_direction=None)
    seg2 = _segment(2, floor_material=2, floor_material_direction=None)
    map_data = _map_data(segments={1: seg1, 2: seg2}, rotation=0)
    manager._map_data = map_data
    manager._selected_map_id = None

    result = editor.set_segment_floor_material(1, 1, direction=90)

    assert seg1.floor_material == 1
    assert seg1.floor_material_direction == 90
    assert result == {
        "1": {"material": 1, "direction": 90},
        "2": {"material": 2},
    }


def test_set_segment_floor_material_direction_forced_none_when_material_not_1(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    seg = _segment(1, floor_material=None, floor_material_direction=None)
    map_data = _map_data(segments={1: seg}, rotation=0)
    manager._map_data = map_data

    editor.set_segment_floor_material(1, 2, direction=90)

    assert seg.floor_material == 2
    assert seg.floor_material_direction is None


def test_set_segment_floor_material_direction_flipped_for_rotated_map(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    seg = _segment(1, floor_material=None, floor_material_direction=None)
    map_data = _map_data(segments={1: seg}, rotation=90)
    manager._map_data = map_data

    editor.set_segment_floor_material(1, 1, direction=0)

    # direction=0 (falsy) with rotation 90/270 flips to 90.
    assert seg.floor_material_direction == 90


def test_set_segment_floor_material_syncs_saved_map_entry(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    seg = _segment(1, floor_material=None, floor_material_direction=None)
    saved_seg = _segment(1, floor_material=None, floor_material_direction=None)
    map_data = _map_data(segments={1: seg}, rotation=0)
    saved = _map_data(segments={1: saved_seg}, floor_material={})
    manager._map_data = map_data
    manager._selected_map_id = 5
    manager._saved_map_data = {5: saved}

    editor.set_segment_floor_material(1, 1, direction=None)

    assert saved_seg.floor_material == 1
    # A saved-map refresh must have been scheduled in addition to the main one.
    assert len(_FakeTimer.instances) == 2
    assert _FakeTimer.instances[0].args == [5]
    assert _FakeTimer.instances[1].args == [None]


def test_set_segment_floor_material_returns_empty_dict_when_no_map(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    manager._map_data = None

    assert editor.set_segment_floor_material(1, 1) == {}


# ---------------------------------------------------------------------------
# 3. merge_segments / split_segments on a small numpy grid
# ---------------------------------------------------------------------------


def _build_two_segment_map() -> MapData:
    """A 4x2 pixel grid with segment 1 on the left half and 2 on the right."""
    dims = MapImageDimensions(top=0, left=0, height=2, width=4, grid_size=1)
    pixel_type = np.zeros((4, 2), dtype=np.uint8)
    pixel_type[0, 0] = 1
    pixel_type[1, 0] = 1
    pixel_type[2, 0] = 2
    pixel_type[3, 0] = 2
    pixel_type[0, 1] = 1
    pixel_type[1, 1] = 1
    pixel_type[2, 1] = 2
    pixel_type[3, 1] = 2

    seg1 = Segment(1, x0=0, y0=0, x1=1, y1=1, neighbors=[2])
    seg2 = Segment(2, x0=2, y0=0, x1=3, y1=1, neighbors=[1])

    return _map_data(
        dimensions=dims,
        pixel_type=pixel_type,
        data=bytes([1, 1, 2, 2, 1, 1, 2, 2]),
        segments={1: seg1, 2: seg2},
        hidden_segments=[2],
        saved_map=False,
    )


def test_merge_segments_relabels_pixels_and_removes_source_segment(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    map_data = _build_two_segment_map()
    manager._saved_map_data = {1: map_data}
    manager._map_data = None  # keep the test focused on the saved-map mutation

    editor.merge_segments(1, [1, 2])

    assert map_data.data == bytes([1, 1, 1, 1, 1, 1, 1, 1])
    assert np.array_equal(map_data.pixel_type, np.ones((4, 2), dtype=np.uint8))
    assert list(map_data.segments.keys()) == [1]
    assert map_data.segments[1].neighbors == []
    assert map_data.hidden_segments == []
    assert map_data.segments[1].color_index == 0
    assert len(_FakeTimer.instances) == 1
    assert _FakeTimer.instances[0].args == [1]


def test_merge_segments_refreshes_current_map_when_selected(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    map_data = _build_two_segment_map()
    manager._saved_map_data = {1: map_data}
    manager._map_data = map_data
    manager._selected_map_id = 1
    editor.set_current_map = MagicMock()  # isolate: set_current_map has its own dedicated tests

    editor.merge_segments(1, [1, 2])

    editor.set_current_map.assert_called_once_with(1)


def test_merge_segments_rejects_non_neighboring_segments(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    map_data = _build_two_segment_map()
    map_data.segments[1].neighbors = []  # no longer neighbors
    manager._saved_map_data = {1: map_data}

    editor.merge_segments(1, [1, 2])

    # Nothing changed: pixel data untouched, both segments still present.
    assert map_data.data == bytes([1, 1, 2, 2, 1, 1, 2, 2])
    assert set(map_data.segments.keys()) == {1, 2}
    assert _FakeTimer.instances == []


def test_merge_segments_noop_when_map_id_unknown(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    manager._saved_map_data = {}

    editor.merge_segments(1, [1, 2])

    assert _FakeTimer.instances == []


def test_merge_segments_noop_when_not_two_segments(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    map_data = _build_two_segment_map()
    manager._saved_map_data = {1: map_data}

    editor.merge_segments(1, [1])

    assert _FakeTimer.instances == []


def test_split_segments_refreshes_saved_map(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    map_data = _map_data(segments={1: _segment(1)})
    manager._saved_map_data = {1: map_data}
    manager._map_data = None

    editor.split_segments(1, 1, [0, 0, 1, 1])

    assert len(_FakeTimer.instances) == 1
    assert _FakeTimer.instances[0].args == [1]


def test_split_segments_updates_current_map_when_selected(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    map_data = _map_data(segments={1: _segment(1)})
    manager._saved_map_data = {1: map_data}
    manager._map_data = map_data
    manager._selected_map_id = 1
    editor.set_current_map = MagicMock()

    editor.split_segments(1, 1, [0, 0, 1, 1])

    editor.set_current_map.assert_called_once_with(1)
    assert len(_FakeTimer.instances) == 1


def test_split_segments_noop_when_map_id_unknown(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    manager._saved_map_data = {}

    editor.split_segments(99, 1, [0, 0, 1, 1])

    assert _FakeTimer.instances == []


# ---------------------------------------------------------------------------
# set_current_map (used internally by delete_map/merge_segments/split_segments)
# ---------------------------------------------------------------------------


def test_set_current_map_builds_optimistic_copy(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    saved = _map_data(
        segments=None,
        cleanset=None,
        carpet_cleanset=None,
        frame_id=99,
        map_name="Kitchen",
        custom_name="Kitchen",
    )
    manager._saved_map_data = {5: saved}
    manager._map_data = _map_data(docked=True)
    manager._current_timestamp_ms = 55555

    editor.set_current_map(5)

    new_map = manager._map_data
    assert new_map is not saved  # deep copy
    assert new_map.docked is True
    assert new_map.timestamp_ms == 55555
    assert new_map.frame_id is None
    assert new_map.map_name is None
    assert new_map.saved_map_id == 5
    assert new_map.custom_name is None
    assert new_map.saved_map is False
    assert new_map.restored_map is True
    assert new_map.temporary_map is False
    assert new_map.empty_map is False
    assert new_map.saved_map_status == 2
    assert manager._current_frame_id is None
    assert manager._current_map_id == 5
    assert manager._selected_map_id == 5
    assert len(_FakeTimer.instances) == 2
    assert _FakeTimer.instances[0].args == [None]
    assert _FakeTimer.instances[1].args == [5]


def test_set_current_map_noop_for_unknown_map_id(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    manager._saved_map_data = {}
    original = manager._map_data

    editor.set_current_map(42)

    assert manager._map_data is original
    assert _FakeTimer.instances == []


# ---------------------------------------------------------------------------
# 4. delete_map
# ---------------------------------------------------------------------------


def test_delete_map_all_maps_when_no_id_given(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    manager._map_data = _map_data(temporary_map=False)
    manager._saved_map_data = {1: _map_data(), 2: _map_data()}

    editor.delete_map(None)

    assert manager._map_data is None
    assert manager._selected_map_id is None
    assert manager._updated_frame_id is None
    assert manager._saved_map_data == {}
    manager._refresh_map_list.assert_called_once()
    manager.request_next_map_list.assert_called_once()


def test_delete_map_noop_for_temporary_current_map(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    manager._map_data = _map_data(temporary_map=True)
    manager._saved_map_data = {1: _map_data()}

    editor.delete_map(None)

    assert manager._saved_map_data == {1: manager._saved_map_data[1]}
    manager.request_next_map_list.assert_not_called()


def test_delete_map_unknown_id_schedules_update_only(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    manager._map_data = None
    manager._saved_map_data = {1: _map_data()}

    editor.delete_map(99)

    manager.schedule_update.assert_called_once_with(2)
    manager.request_next_map_list.assert_not_called()
    assert manager._saved_map_data == {1: manager._saved_map_data[1]}


def test_delete_map_selected_map_with_multiple_maps_switches_current(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    map_a = _map_data(segments=None)
    map_b = _map_data(segments=None)
    manager._map_data = _map_data(temporary_map=False)
    manager._saved_map_data = {5: map_a, 7: map_b}
    manager._selected_map_id = 5
    manager._map_list = [5, 7]
    editor.set_current_map = MagicMock()

    editor.delete_map(5)

    manager._refresh_map_list.assert_called_once()
    editor.set_current_map.assert_called_once_with(7)
    manager.request_next_map_list.assert_called_once()


def test_delete_map_selected_map_single_map_clears_state(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    map_a = _map_data(segments=None)
    manager._map_data = _map_data(temporary_map=False)
    manager._saved_map_data = {5: map_a}
    manager._selected_map_id = 5
    manager._map_list = [5]

    editor.delete_map(5)

    assert manager._saved_map_data == {}
    assert manager._map_data is None
    assert manager._updated_frame_id is None
    assert manager._selected_map_id is None
    manager._refresh_map_list.assert_called_once()
    manager.request_next_map_list.assert_called_once()


def test_delete_map_non_selected_map_simple_delete(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    map_a = _map_data(segments=None)
    map_b = _map_data(segments=None)
    manager._map_data = _map_data(temporary_map=False)
    manager._saved_map_data = {5: map_a, 7: map_b}
    manager._selected_map_id = 5

    editor.delete_map(7)

    assert manager._saved_map_data == {5: map_a}
    manager._refresh_map_list.assert_called_once()
    manager.request_next_map_list.assert_called_once()


# ---------------------------------------------------------------------------
# 5. cancel_pending()
# ---------------------------------------------------------------------------


def test_cancel_pending_cancels_active_timer(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    map_data = _map_data()
    manager._map_data = map_data

    editor.refresh_map()
    timer = _FakeTimer.instances[-1]
    assert timer.cancelled is False

    editor.cancel_pending()

    assert timer.cancelled is True
    assert editor._refresh_timer is None
    # The timer never fired, so no update should have propagated.
    manager._map_data_updated.assert_not_called()


def test_cancel_pending_safe_when_no_timer_pending(editor: DreameMapVacuumMapEditor) -> None:
    assert editor._refresh_timer is None
    editor.cancel_pending()  # must not raise
    assert editor._refresh_timer is None


# ---------------------------------------------------------------------------
# 6. refresh_map -> manager._map_data_updated()
# ---------------------------------------------------------------------------


def test_refresh_map_fires_map_data_updated_for_current_map(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    map_data = _map_data()
    manager._map_data = map_data

    editor.refresh_map()

    assert len(_FakeTimer.instances) == 1
    _FakeTimer.instances[0].fire()

    manager._map_data_updated.assert_called_once()
    assert map_data.last_updated is not None


def test_refresh_map_fires_map_data_updated_for_saved_map(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    saved = _map_data()
    manager._saved_map_data = {3: saved}

    editor.refresh_map(3)

    _FakeTimer.instances[0].fire()

    manager._map_data_updated.assert_called_once()
    assert saved.last_updated is not None


def test_refresh_map_debounces_rapid_successive_calls(editor: DreameMapVacuumMapEditor, manager: MagicMock) -> None:
    manager._map_data = _map_data()

    editor.refresh_map()
    editor.refresh_map()
    editor.refresh_map()

    # Every call cancels the previous pending timer.
    assert len(_FakeTimer.instances) == 3
    assert _FakeTimer.instances[0].cancelled is True
    assert _FakeTimer.instances[1].cancelled is True
    assert _FakeTimer.instances[2].cancelled is False


def test_refresh_map_with_unknown_saved_map_id_does_not_update(
    editor: DreameMapVacuumMapEditor, manager: MagicMock
) -> None:
    manager._saved_map_data = {}

    editor.refresh_map(123)
    _FakeTimer.instances[0].fire()

    manager._map_data_updated.assert_not_called()
