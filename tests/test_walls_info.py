"""Tests for the vectorized ``walls_info`` decoder (real room boundaries).

``DreameVacuumMapDecoder._decode_walls_info`` parses the saved-map
``walls_info`` structure (real-world mm segments, grouped by room, with
doorways flagged ``type == 1``) into two flat ``Wall`` lists on the map
data — ``wall_lines`` (walls) and ``door_lines`` (doorways). The data is
decoded and kept on ``MapData`` for a future clean replacement of the
pixel wall contour; it is not rendered additively (that produced redundant
gray frames over the existing pixel walls).

The structure is the one captured live from a Dreame Aqua10 (r95285):
``{version_flag, storeys: [{rooms: [{room_id, walls: [{type, beg_pt_x,
beg_pt_y, end_pt_x, end_pt_y, normal_x, normal_y}]}]}]}``.
"""

from __future__ import annotations

import sys
import types

import pytest


def _install_native_stubs() -> None:
    if "py_mini_racer" not in sys.modules:
        pmr = types.ModuleType("py_mini_racer")
        pmr.MiniRacer = type("MiniRacer", (), {"__init__": lambda self, *a, **k: None})
        sys.modules["py_mini_racer"] = pmr


_install_native_stubs()

from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
from custom_components.dreame_vacuum.dreame.vacuum_types import MapData, Wall


def _walls_info(*rooms: dict) -> dict:
    """Wrap room dicts in the storeys envelope the robot emits."""
    return {"version_flag": 3, "storeys": [{"rooms": list(rooms)}]}


def _wall(x0: int, y0: int, x1: int, y1: int, wall_type: int = 0) -> dict:
    return {
        "type": wall_type,
        "beg_pt_x": x0,
        "beg_pt_y": y0,
        "end_pt_x": x1,
        "end_pt_y": y1,
        "normal_x": 0.0,
        "normal_y": -1.0,
    }


def test_decode_walls_info_splits_walls_and_doors() -> None:
    """type 0 segments go to wall_lines, type 1 to door_lines, in order."""
    map_data = MapData()
    walls_info = _walls_info(
        {
            "room_id": 2,
            "walls": [
                _wall(-6375, 2225, -7525, 2225, 0),
                _wall(-7525, 2225, -7525, 4825, 0),
                _wall(-7525, 4825, -6375, 4825, 1),  # doorway
            ],
        }
    )

    DreameVacuumMapDecoder._decode_walls_info(map_data, walls_info)

    assert map_data.wall_lines == [Wall(-6375, 2225, -7525, 2225), Wall(-7525, 2225, -7525, 4825)]
    assert map_data.door_lines == [Wall(-7525, 4825, -6375, 4825)]


def test_decode_walls_info_merges_multiple_rooms() -> None:
    """Segments from every room across every storey are collected."""
    map_data = MapData()
    walls_info = _walls_info(
        {"room_id": 1, "walls": [_wall(0, 0, 100, 0)]},
        {"room_id": 2, "walls": [_wall(100, 0, 100, 100)]},
    )

    DreameVacuumMapDecoder._decode_walls_info(map_data, walls_info)

    assert map_data.wall_lines == [Wall(0, 0, 100, 0), Wall(100, 0, 100, 100)]
    assert map_data.door_lines is None


def test_decode_walls_info_empty_gives_none() -> None:
    """No wall/door segments leaves both lists as None (nothing to render)."""
    map_data = MapData()
    DreameVacuumMapDecoder._decode_walls_info(map_data, _walls_info({"room_id": 1, "walls": []}))
    assert map_data.wall_lines is None
    assert map_data.door_lines is None


@pytest.mark.parametrize("bad", [None, [], "nope", 42, {"storeys": None}])
def test_decode_walls_info_tolerates_malformed_input(bad: object) -> None:
    """Malformed walls_info never raises and leaves the map untouched."""
    map_data = MapData()
    DreameVacuumMapDecoder._decode_walls_info(map_data, bad)
    assert map_data.wall_lines is None
    assert map_data.door_lines is None


def test_decode_walls_info_skips_incomplete_segments() -> None:
    """A wall missing a coordinate is skipped, the rest still decode."""
    map_data = MapData()
    walls_info = _walls_info(
        {
            "room_id": 1,
            "walls": [
                {"type": 0, "beg_pt_x": 0, "beg_pt_y": 0},  # missing end points
                _wall(0, 0, 50, 0),
            ],
        }
    )

    DreameVacuumMapDecoder._decode_walls_info(map_data, walls_info)

    assert map_data.wall_lines == [Wall(0, 0, 50, 0)]


def test_wall_lines_to_img_converts_to_pixel_space() -> None:
    """Decoded walls are real-world Wall objects convertible to image space
    via the standard to_img (same path virtual walls already use)."""
    from custom_components.dreame_vacuum.dreame.vacuum_types import MapImageDimensions

    map_data = MapData()
    DreameVacuumMapDecoder._decode_walls_info(map_data, _walls_info({"room_id": 1, "walls": [_wall(0, 0, 500, 0)]}))
    dims = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=50)
    img_wall = map_data.wall_lines[0].to_img(dims)
    # to_img must return a Wall with numeric pixel coordinates (no exception).
    assert isinstance(img_wall, Wall)
    assert all(isinstance(v, (int, float)) for v in img_wall.as_list())


def test_as_dict_includes_wall_lines_and_door_lines_when_present() -> None:
    """as_dict() exposes decoded wall/door segments to consumers (e.g. the
    companion card) under the wall_lines / door_lines attribute keys."""
    map_data = MapData()
    walls_info = _walls_info(
        {
            "room_id": 1,
            "walls": [
                _wall(0, 0, 100, 0, 0),
                _wall(100, 0, 100, 100, 1),  # doorway
            ],
        }
    )
    DreameVacuumMapDecoder._decode_walls_info(map_data, walls_info)

    d = map_data.as_dict()
    assert d["wall_lines"] == [Wall(0, 0, 100, 0)]
    assert d["door_lines"] == [Wall(100, 0, 100, 100)]


def test_as_dict_omits_wall_lines_and_door_lines_when_absent() -> None:
    """A map with no decoded wall/door segments omits both keys entirely
    (the ``is not None`` contract shared with every other geometry field)."""
    d = MapData().as_dict()
    assert "wall_lines" not in d
    assert "door_lines" not in d
