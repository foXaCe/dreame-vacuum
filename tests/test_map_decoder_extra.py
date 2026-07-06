"""Additional path-coverage tests for DreameVacuumMapDecoder.

Complements tests/test_map_decoder.py and tests/test_map_decoder_paths.py by
targeting branches those files leave uncovered: the frame_map/vslam_map
variants of ``_get_pixel_type``, defensive returns in ``_get_segment_center``
and ``extract_segment_outline``, the restored/saved-map merge branches in
``decode_map_data_from_partial``, obstacle/furniture/segment-info edge cases,
cleanset capability permutations (including the wetness-level sub-branches),
floor material, ``get_carpets``, P-frame carpet/path/obstacle bookkeeping and
``decode_cleaning_map_data``.

Uses the same binary-fixture helpers as tests/test_map_decoder_paths.py
(duplicated locally to keep this file self-contained) and the same
direct-staticmethod-call style as tests/test_map_decoder.py where a full
binary round trip isn't needed.
"""

from __future__ import annotations

import base64
import json
import struct
from types import SimpleNamespace
import zlib

import numpy as np
import pytest

from custom_components.dreame_vacuum.dreame.const import MAP_PARAMETER_NAME

try:
    from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
    from custom_components.dreame_vacuum.dreame.vacuum_types import (
        CleansetType,
        MapData,
        MapDataPartial,
        MapFrameType,
        MapImageDimensions,
        MapPixelType,
        Path,
        PathType,
        Segment,
    )

    HAS_MAP_DECODER = True
except ImportError:
    HAS_MAP_DECODER = False

pytestmark = pytest.mark.skipif(not HAS_MAP_DECODER, reason="py_mini_racer or map_decoder deps not available")

HEADER_FMT = "<HHb11h"


# ---------------------------------------------------------------------------
# Payload builders (duplicated from test_map_decoder_paths.py to keep this
# file independently editable)
# ---------------------------------------------------------------------------


def build_header(
    map_id: int = 1,
    frame_id: int = 1,
    frame_type: int = MapFrameType.I.value,
    robot: tuple[int, int, int] = (0, 0, 0),
    charger: tuple[int, int, int] = (0, 0, 0),
    grid_size: int = 50,
    width: int = 0,
    height: int = 0,
    left: int = 0,
    top: int = 0,
) -> bytes:
    return struct.pack(
        HEADER_FMT,
        map_id,
        frame_id,
        frame_type,
        robot[0],
        robot[1],
        robot[2],
        charger[0],
        charger[1],
        charger[2],
        grid_size,
        width,
        height,
        left,
        top,
    )


def make_partial(header: bytes, grid: bytes, meta: dict | None, timestamp_ms: int = 0) -> MapDataPartial:
    partial = MapDataPartial()
    partial.map_id, partial.frame_id = struct.unpack_from("<HH", header, 0)
    partial.frame_type = struct.unpack_from("<b", header, 4)[0]
    partial.timestamp_ms = timestamp_ms
    partial.raw = header + grid
    partial.data_json = meta
    return partial


def build_raw_map_str(header: bytes, grid: bytes, meta: dict) -> str:
    payload = header + grid + json.dumps(meta).encode("utf8")
    compressed = zlib.compress(payload)
    return base64.b64encode(compressed).decode("ascii")


def decode_initial_5x5() -> MapData:
    """Decode a plain 5x5 I frame with a segment-1 pixel at (2, 2), for P-frame tests."""
    width, height = 5, 5
    grid = bytearray(width * height)
    grid[2 * width + 2] = 1
    header = build_header(map_id=1, frame_id=1, robot=(100, 200, 0), charger=(50, 60, 0), width=width, height=height)
    partial = make_partial(header, bytes(grid), {})
    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)
    return map_data


def make_map_with_segments(*segment_ids: int) -> MapData:
    map_data = MapData()
    map_data.segments = {sid: Segment(sid, 0, 0, 10, 10, 5, 5) for sid in segment_ids}
    return map_data


# ---------------------------------------------------------------------------
# 1. _get_pixel_type direct calls: frame_map / vslam_map / saved_map_status branches
# ---------------------------------------------------------------------------


def test_get_pixel_type_frame_map_branches():
    """frame_map=True: mid-range segment+carpet, WALL/FLOOR/UNKNOWN sentinels, low-bit fallback, and OUTSIDE fallthrough."""
    md = MapData()
    md.frame_map = True

    assert DreameVacuumMapDecoder._get_pixel_type(md, (5 << 2) | 3, False, None) == (5, True)
    assert DreameVacuumMapDecoder._get_pixel_type(md, 63 << 2, False, None) == (MapPixelType.WALL.value, False)
    assert DreameVacuumMapDecoder._get_pixel_type(md, 62 << 2, False, None) == (MapPixelType.FLOOR.value, False)
    assert DreameVacuumMapDecoder._get_pixel_type(md, 61 << 2, False, None) == (MapPixelType.UNKNOWN.value, False)
    assert DreameVacuumMapDecoder._get_pixel_type(md, 1, False, None) == (MapPixelType.NEW_SEGMENT.value, False)
    assert DreameVacuumMapDecoder._get_pixel_type(md, 3, False, None) == (MapPixelType.NEW_SEGMENT.value, True)
    assert DreameVacuumMapDecoder._get_pixel_type(md, 2, False, None) == (MapPixelType.WALL.value, False)
    # segment_id (>>2) is 0 and low bits are 0: falls through the whole if-block to the final OUTSIDE fallback.
    assert DreameVacuumMapDecoder._get_pixel_type(md, 0, False, None) == (MapPixelType.OUTSIDE.value, False)


def test_get_pixel_type_vslam_map_branches():
    """vslam_map=True (frame_map False): segment 1/3 -> NEW_SEGMENT, 2 -> WALL, others fall through to OUTSIDE."""
    md = MapData()
    md.frame_map = False

    assert DreameVacuumMapDecoder._get_pixel_type(md, 1, True, None) == (MapPixelType.NEW_SEGMENT.value, False)
    assert DreameVacuumMapDecoder._get_pixel_type(md, 2, True, None) == (MapPixelType.WALL.value, False)
    assert DreameVacuumMapDecoder._get_pixel_type(md, 5, True, None) == (MapPixelType.OUTSIDE.value, False)


def test_get_pixel_type_saved_map_status_0_and_1_branches():
    """saved_map_status in (0, 1): segment 1/3 -> NEW_SEGMENT, 2 -> WALL, any other real id -> OUTSIDE."""
    md_status0 = MapData()
    md_status0.frame_map = False
    md_status0.saved_map_status = 0
    assert DreameVacuumMapDecoder._get_pixel_type(md_status0, 1, False, None) == (
        MapPixelType.NEW_SEGMENT.value,
        False,
    )
    assert DreameVacuumMapDecoder._get_pixel_type(md_status0, 5, False, None) == (MapPixelType.OUTSIDE.value, False)

    md_status1 = MapData()
    md_status1.frame_map = False
    md_status1.saved_map_status = 1
    assert DreameVacuumMapDecoder._get_pixel_type(md_status1, 2, False, None) == (MapPixelType.WALL.value, False)


def test_get_pixel_type_segment_id_zero_falls_through_to_outside():
    """Default (non-frame_map, non-vslam, status -1) scheme with segment_id 0 falls through to the final OUTSIDE."""
    md = MapData()
    md.frame_map = False
    md.saved_map_status = -1
    assert DreameVacuumMapDecoder._get_pixel_type(md, 0, False, None) == (MapPixelType.OUTSIDE.value, False)


# ---------------------------------------------------------------------------
# 2. _get_segment_center defensive returns
# ---------------------------------------------------------------------------


def test_get_segment_center_none_dimensions_returns_none():
    """dimensions is None short-circuits before any bounds checking."""
    md = MapData()
    md.dimensions = None
    md.data = bytes(16)
    assert DreameVacuumMapDecoder._get_segment_center(md, 1, 0, True) is None


def test_get_segment_center_no_matching_pixels_returns_none():
    """A segment_id that never appears on the scanned line leaves ``lines`` empty -> final None."""
    md = MapData()
    md.dimensions = MapImageDimensions(top=0, left=0, height=4, width=4, grid_size=1)
    md.data = bytes(16)
    assert DreameVacuumMapDecoder._get_segment_center(md, 9, 1, True) is None


# ---------------------------------------------------------------------------
# 3. extract_segment_outline / _simplify_contour / _perpendicular_distance
# ---------------------------------------------------------------------------


def test_extract_segment_outline_no_pixels_found_returns_bbox():
    """A non-trivial bbox (x0<x1, y0<y1) with no pixel matching segment_id anywhere returns the raw bbox corners."""
    md = MapData()
    md.dimensions = MapImageDimensions(top=0, left=0, height=8, width=8, grid_size=10)
    md.pixel_type = np.zeros((8, 8), dtype=np.uint8)

    outline = DreameVacuumMapDecoder.extract_segment_outline(md, 9, 1, 1, 4, 4)

    assert outline == [[10, 0], [50, 0], [50, 40], [10, 40]]


def test_extract_segment_outline_dead_end_falls_back_to_bbox():
    """Two disconnected single pixels of the same segment: Moore-Neighbor tracing dead-ends immediately (no
    8-connected neighbor), so the contour never reaches 3 points and the bounding box is used instead."""
    md = MapData()
    md.dimensions = MapImageDimensions(top=0, left=0, height=8, width=8, grid_size=10)
    md.pixel_type = np.zeros((8, 8), dtype=np.uint8)
    md.pixel_type[2, 2] = 5
    md.pixel_type[5, 5] = 5

    outline = DreameVacuumMapDecoder.extract_segment_outline(md, 5, 2, 2, 5, 5)

    assert outline == [[20, 10], [60, 10], [60, 50], [20, 50]]


def test_simplify_contour_short_list_returned_unchanged():
    """Fewer than 3 points: nothing to simplify, the list is returned as-is."""
    points = [(0, 0), (1, 1)]
    assert DreameVacuumMapDecoder._simplify_contour(points, 2.0) == points


def test_perpendicular_distance_coincident_line_points():
    """When line_start == line_end, the perpendicular distance degenerates to the plain Euclidean distance."""
    distance = DreameVacuumMapDecoder._perpendicular_distance((5, 5), (1, 1), (1, 1))
    assert distance == pytest.approx((4**2 + 4**2) ** 0.5)


# ---------------------------------------------------------------------------
# 4. get_segments: bbox x0 minimization + vslam saved-map center-mismatch scan
# ---------------------------------------------------------------------------


def test_get_segments_shrinks_x0_when_later_row_has_smaller_x():
    """The bbox x0 is only set once on first sight; a later row with a smaller x must still shrink it (line 1768)."""
    md = MapData()
    md.dimensions = MapImageDimensions(top=0, left=0, height=4, width=8, grid_size=10)
    md.pixel_type = np.zeros((8, 4), dtype=np.uint8)
    md.pixel_type[5, 0] = 3  # first row: sets initial x0=5
    md.pixel_type[2, 1] = 3  # second row: x=2 < x0=5 -> must shrink x0

    segments = DreameVacuumMapDecoder.get_segments(md, False)

    seg = segments[3]
    assert (seg.x0, seg.y0, seg.x1, seg.y1) == (20, -10, 60, 10)
    assert (seg.x, seg.y) == (40, 10)


def test_get_segments_vslam_saved_map_scans_row_when_center_pixel_mismatches():
    """saved_map + vslam_map: when the naive bbox-center pixel isn't the segment, the code scans row y for a run."""
    md = MapData()
    md.dimensions = MapImageDimensions(top=0, left=0, height=6, width=10, grid_size=10)
    md.pixel_type = np.zeros((10, 6), dtype=np.uint8)
    md.saved_map = True
    for x in (1, 2):
        md.pixel_type[x, 3] = 3
    for x in (6, 7):
        md.pixel_type[x, 3] = 3

    segments = DreameVacuumMapDecoder.get_segments(md, True)

    seg = segments[3]
    assert (seg.x0, seg.y0, seg.x1, seg.y1) == (10, 20, 80, 30)
    assert (seg.x, seg.y) == (20, 30)


# ---------------------------------------------------------------------------
# 5. decode_map_data_from_partial: small metadata edge cases
# ---------------------------------------------------------------------------


def test_decode_map_data_from_partial_none_data_json_defaults_to_empty_dict():
    """partial.data_json=None is coerced to {} before any key lookups."""
    header = build_header(width=0, height=0)
    partial = make_partial(header, b"", None)

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data is not None
    assert map_data.cleaned_area is None


def test_decode_map_data_from_partial_origin_overrides_header_left_top():
    """A data_json 'origin' pair overrides the header's left/top before building dimensions."""
    header = build_header(width=2, height=2, left=5, top=5)
    partial = make_partial(header, bytes(4), {"origin": [100, 200]})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert (map_data.dimensions.left, map_data.dimensions.top) == (100, 200)


def test_decode_map_data_from_partial_ct_numeric_sets_cleaning_time():
    """A numeric 'ct' value (not the curtains dict form) sets cleaning_time."""
    header = build_header(width=0, height=0)
    partial = make_partial(header, b"", {"ct": 456})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.cleaning_time == 456
    assert map_data.curtains is None


def test_decode_map_data_from_partial_cleanset_and_carpet_cleanset_as_json_strings():
    """cleanset/carpetcleanset are sometimes delivered as JSON-encoded strings and must be parsed."""
    header = build_header(width=0, height=0)
    meta = {
        "cleanset": json.dumps({"1": [1, 3, 1, 0]}),
        "carpetcleanset": json.dumps([[2, 1, 3, 10]]),
    }
    partial = make_partial(header, b"", meta)

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.cleanset == {"1": [1, 3, 1, 0]}
    assert map_data.carpet_cleanset == [[2, 1, 3, 10]]


def test_decode_map_data_from_partial_2x2_grid_with_nonzero_pixel_is_not_empty():
    """The 2x2 special-cased 'empty map' marker is overridden as soon as any pixel is found nonzero."""
    header = build_header(width=2, height=2)
    grid = bytes([0, 1, 0, 0])
    partial = make_partial(header, grid, {})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.empty_map is False


def test_decode_map_data_from_partial_w_frame_invalid_pixel_value_is_swallowed():
    """An out-of-range wifi pixel value raises inside MapPixelType(), caught and logged; decode still succeeds."""
    width, height = 2, 2
    grid = bytes([5, 0, 0, 0])  # 5 & 15 == 5, not a valid MapPixelType member
    header = build_header(frame_type=MapFrameType.W.value, width=width, height=height)
    partial = make_partial(header, grid, {})

    map_data, saved_map_data = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert saved_map_data is None
    assert map_data.wifi_map is True
    # empty_map was already flipped False (before the invalid enum value raised) and the pixel itself never got set.
    assert map_data.empty_map is False
    assert int(map_data.pixel_type[0, 0]) == MapPixelType.OUTSIDE.value


def test_decode_map_data_from_partial_frame_map_wall_via_low_bits():
    """fsm=1 scheme: a pixel whose high 6 bits are 0 and low bits equal 2 resolves to WALL via the low-bit fallback."""
    header = build_header(width=3, height=3)
    grid = bytearray(9)
    grid[0] = 2
    partial = make_partial(header, bytes(grid), {"fsm": 1})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert int(map_data.pixel_type[0, 0]) == MapPixelType.WALL.value


def test_decode_map_data_from_partial_ris_zero_carpet_bit_recorded():
    """ris=0 (initial scan) scheme: a pixel with low bits == 3 is both NEW_SEGMENT and a carpet pixel."""
    header = build_header(width=2, height=1)
    grid = bytes([3, 0])
    partial = make_partial(header, grid, {"ris": 0})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.carpet_pixels == [(0, 0)]
    assert int(map_data.pixel_type[0, 0]) == MapPixelType.NEW_SEGMENT.value


def test_decode_map_data_from_partial_ris_two_carpet_and_wall():
    """ris=2 scheme: a pixel with low bits == 3 is carpet+NEW_SEGMENT, a pixel == 2 is WALL."""
    header = build_header(width=2, height=1)
    grid = bytes([3, 2])
    partial = make_partial(header, grid, {"ris": 2})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.carpet_pixels == [(0, 0)]
    assert int(map_data.pixel_type[0, 0]) == MapPixelType.NEW_SEGMENT.value
    assert int(map_data.pixel_type[1, 0]) == MapPixelType.WALL.value


def test_decode_map_data_from_partial_default_scheme_carpet_bit_and_hidden_wall():
    """Default scheme (no fsm/ris/vslam): 0x40 marks a carpet pixel; a hidden segment's wall bit -> HIDDEN_WALL."""
    header = build_header(width=2, height=1)
    grid = bytes([0x41, 0x80 | 5])  # pixel0: carpet + segment 1; pixel1: wall bit + segment 5 (hidden)
    partial = make_partial(header, grid, {"delsr": [5]})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.carpet_pixels == [(0, 0)]
    assert int(map_data.pixel_type[0, 0]) == 1
    assert int(map_data.pixel_type[1, 0]) == MapPixelType.HIDDEN_WALL.value


def test_decode_map_data_from_partial_exception_is_caught_and_logged():
    """An unparsable JSON-string cleanset raises json.JSONDecodeError inside the try block; it is swallowed and the
    partially-built map_data (as far as it got) is still returned instead of propagating the exception."""
    header = build_header(width=0, height=0)
    partial = make_partial(header, b"", {"cleanset": "not-valid-json{"})

    map_data, saved_map_data = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data is not None
    assert saved_map_data is None
    # json.loads raised before the reassignment completed, so the raw string is left in place.
    assert map_data.cleanset == "not-valid-json{"


# ---------------------------------------------------------------------------
# 6. segment_info extra keys / whmp+whm / carpet_info / pointinfo-as-list
# ---------------------------------------------------------------------------


def test_decode_segment_info_extra_keys_roomid_material_direction_custom_name():
    """seg_inf entries also carry roomID, material, direction and a base64 custom display name."""
    custom_name_b64 = base64.b64encode(b"Office").decode("ascii")
    width, height = 5, 5
    grid = bytearray(width * height)
    grid[2 * width + 2] = 1
    header = build_header(width=width, height=height)
    meta = {
        "seg_inf": {
            "1": {
                "type": 1,
                "index": 0,
                "roomID": 55,
                "material": 2,
                "direction": 90,
                MAP_PARAMETER_NAME: custom_name_b64,
            }
        }
    }
    partial = make_partial(header, bytes(grid), meta)

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    seg = map_data.segments[1]
    assert seg.unique_id == 55
    assert seg.floor_material == 2
    assert seg.floor_material_direction == 90
    assert seg.custom_name == "Office"


def test_decode_whmp_and_whm_populate_router_position_and_wifi_map_data():
    """'whmp' sets router_position directly; 'whm' (only decoded when saved_map) fills wifi_map_data and inherits
    the router_position when the embedded wifi frame itself doesn't carry one."""
    wifi_header = build_header(map_id=50, frame_type=MapFrameType.W.value, width=2, height=2)
    wifi_grid = bytes([MapPixelType.WIFI_HIGH.value, 0, 0, 0])
    wifi_raw = build_raw_map_str(wifi_header, wifi_grid, {})

    header = build_header(width=0, height=0)
    meta = {"whmp": [11, 22], "whm": wifi_raw}
    partial = make_partial(header, b"", meta)

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.saved_map is True
    assert (map_data.router_position.x, map_data.router_position.y) == (11, 22)
    assert map_data.wifi_map_data is not None
    assert (map_data.wifi_map_data.router_position.x, map_data.wifi_map_data.router_position.y) == (11, 22)


def test_decode_carpet_info_builds_detected_carpets():
    """The legacy 'carpet_info' dict format builds detected_carpets with the ellipse flag from index 6."""
    header = build_header(width=0, height=0)
    meta = {"carpet_info": {"7": [0, 0, 10, 10, 3, 1, True]}}
    partial = make_partial(header, b"", meta)

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    carpet = map_data.detected_carpets[0]
    assert carpet.id == 7
    assert (carpet.x0, carpet.y0, carpet.x1, carpet.y1, carpet.x2, carpet.y2, carpet.x3, carpet.y3) == (
        0,
        0,
        10,
        0,
        10,
        10,
        0,
        10,
    )
    assert carpet.ellipse is True


def test_decode_pointinfo_as_single_element_list_is_unwrapped():
    """'pointinfo' is sometimes delivered as a one-element list instead of a bare dict; both forms are accepted."""
    header = build_header(width=0, height=0)
    meta = {"pointinfo": [{"spoint": [[1, 2, 1, 0]]}]}
    partial = make_partial(header, b"", meta)

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert (map_data.predefined_points[1].x, map_data.predefined_points[1].y) == (1, 2)


# ---------------------------------------------------------------------------
# 7. Obstacles / furniture edge cases
# ---------------------------------------------------------------------------


def test_decode_obstacle_neglected_room_looks_up_segment_center_and_sets_segment_name():
    """A NEGLECTED_ROOM obstacle resolves segment center coordinates, and set_segment() fills obstacle.segment."""
    width, height = 5, 5
    grid = bytearray(width * height)
    grid[2 * width + 2] = 1
    header = build_header(width=width, height=height)
    meta = {
        "seg_inf": {"1": {"type": 1, "index": 0}},
        "ai_obstacle": [[1, 0, 200, 0.5, 5000, "pic.jpg", 7, 0.1, 0.2, 0.3, 0.4, 1, 2]],
    }
    partial = make_partial(header, bytes(grid), meta)

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    obs = map_data.obstacles["1"]
    assert (obs.x, obs.y) == (map_data.segments[1].x, map_data.segments[1].y)
    assert obs.segment == "Living Room"


def test_decode_obstacle_size_seven_uses_swapped_file_name_and_key_order():
    """The size==7 (not >=8) branch builds the Obstacle with file_name/key swapped relative to the size>=8 branch."""
    header = build_header(width=0, height=0)
    meta = {"ai_obstacle": [[1.0, 2.0, 142, 0.9, 5000, "a", "b"]]}
    partial = make_partial(header, b"", meta)

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    obs = map_data.obstacles["1"]
    assert obs.object_id == 5000
    assert obs.key == "a"
    assert obs.file_name == "b"


def test_decode_obstacle_invalid_type_is_skipped():
    """An obstacle_type that isn't a known ObstacleType member is silently skipped (no obstacle registered)."""
    header = build_header(width=0, height=0)
    meta = {"ai_obstacle": [[1.0, 2.0, 99999, 0.9]]}
    partial = make_partial(header, b"", meta)

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.obstacles == {}


def test_decode_funiture_info_swaps_type_25_and_skips_invalid_type():
    """funiture_info (legacy) swaps type 25<->8; any other unknown type is silently skipped."""
    header = build_header(width=0, height=0)
    furniture_valid = [11, 25, 3, 40, 60, 0, 500, 600, 0, 45.0, 0, 0, 1.5, 2]
    furniture_invalid = [12, 9999, 3, 40, 60, 0, 500, 600, 0, 45.0, 0, 0, 1.5, 2]
    meta = {"funiture_info": [furniture_valid, furniture_invalid]}
    partial = make_partial(header, b"", meta)

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert list(map_data.saved_furnitures.keys()) == [1]
    assert map_data.saved_furnitures[1].type.value == 8


def test_decode_ai_furniture_legacy_key_flips_angle_0_and_180():
    """Only the legacy 'ai_furniture' key (not 'ai_furniture_new') swaps a 180/0 angle."""
    header = build_header(width=0, height=0)

    partial_180 = make_partial(header, b"", {"ai_furniture": [[100, 200, 1, 3, 90, 190, 20, 30, 180, 1.0]]})
    map_data_180, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial_180, False)
    assert map_data_180.furnitures[1].angle == 0

    partial_0 = make_partial(header, b"", {"ai_furniture": [[100, 200, 1, 3, 90, 190, 20, 30, 0, 1.0]]})
    map_data_0, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial_0, False)
    assert map_data_0.furnitures[1].angle == 180


# ---------------------------------------------------------------------------
# 8. Restored-map / saved-map merge branches in decode_map_data_from_partial
# ---------------------------------------------------------------------------


def test_decode_restored_map_merge_sentinel_pixel_types_and_propagated_fields():
    """restored_map=True + saved_map_status=2 with a saved map narrower than the outer canvas exercises: the
    'outside saved footprint' sentinel branch, all three restored-pixel sentinel sub-branches (wall/new-segment/
    real-segment), temporary_map/hidden_segments propagation from the saved map, the post-merge empty_map reset
    (an all-zero outer grid never flips empty_map to False), and the vslam_map need_optimization flag."""
    inner_grid = bytes([133, 63, 7, 0, 0, 0])  # row0: wall-sentinel, new-segment-sentinel, real segment 7
    inner_header = build_header(map_id=100, frame_id=1, width=3, height=2, grid_size=50)
    inner_meta = {"suw": 6, "delsr": [9, 10]}
    inner_raw = build_raw_map_str(inner_header, inner_grid, inner_meta)

    outer_grid = bytes(4 * 2)  # all-zero: outer canvas is wider (4) than the saved map (3)
    outer_header = build_header(map_id=1, frame_id=5, width=4, height=2, grid_size=50)
    outer_meta = {"ris": 2, "rpur": 1, "rism": inner_raw}
    partial = make_partial(outer_header, outer_grid, outer_meta)

    map_data, saved_map_data = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, True)

    assert saved_map_data.temporary_map is True
    assert map_data.temporary_map is True
    assert map_data.hidden_segments == [9, 10]
    assert map_data.combined_pixel_type.tolist() == [[255, 0], [253, 0], [7, 0], [0, 0]]
    assert (
        map_data.combined_dimensions.left,
        map_data.combined_dimensions.top,
        map_data.combined_dimensions.width,
        map_data.combined_dimensions.height,
    ) == (0, 0, 4, 2)
    # The all-zero outer grid never left the initial empty_map=True assumption, so it gets reset post-merge.
    assert map_data.empty_map is False
    assert map_data.restored_map is False
    assert map_data.need_optimization is False


def test_decode_restored_map_without_saved_map_status_2_uses_saved_pixel_type_directly():
    """restored_map=True but saved_map_status != 2 takes the 'else' merge path: combined_pixel_type/dimensions are
    the saved map's own values directly, with no per-pixel reconciliation loop."""
    inner_grid = bytes([5, 0, 0, 0])
    inner_header = build_header(map_id=200, frame_id=1, width=2, height=2, grid_size=50)
    inner_raw = build_raw_map_str(inner_header, inner_grid, {})

    outer_header = build_header(map_id=2, frame_id=1, width=0, height=0, grid_size=50)
    partial = make_partial(outer_header, b"", {"rpur": 1, "rism": inner_raw})

    map_data, saved_map_data = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    # The outer frame has no grid of its own (width=height=0), so empty_map never leaves its initial True
    # assumption and the post-merge empty_map reset flips restored_map back to False (see the other restored-map
    # test for the "kept True" case with a real, non-empty outer grid).
    assert map_data.restored_map is False
    assert map_data.combined_pixel_type is saved_map_data.pixel_type
    assert map_data.combined_dimensions is saved_map_data.dimensions
    assert map_data.carpet_pixels == saved_map_data.carpet_pixels


def test_decode_saved_map_segment_info_only_merge_when_not_restoring():
    """When the outer condition (restored/recovery/status2-with-empty-or-non-frame_map) is false, only per-field
    segment attributes are merged into the EXISTING outer segments dict (no wholesale segments/pixel-type copy);
    with saved_map_status==2 the segment's x/y are also copied over."""
    inner_grid = bytearray(3 * 3)
    inner_grid[0] = 5  # top-left pixel = segment 5
    inner_header = build_header(map_id=300, frame_id=1, width=3, height=3, grid_size=50)
    inner_meta = {"seg_inf": {"5": {"type": 3, "index": 2, "nei_id": [7], "roomID": 42}}}
    inner_raw = build_raw_map_str(inner_header, bytes(inner_grid), inner_meta)

    outer_grid = bytearray(3 * 3)
    outer_grid[8] = 5 << 2  # bottom-right pixel = segment 5 via the frame_map inline scheme
    outer_header = build_header(map_id=3, frame_id=1, width=3, height=3, grid_size=50)
    # frame_map=True makes condition663 false even though saved_map_status==2, landing in the else(753) branch.
    outer_meta = {"fsm": 1, "ris": 2, "rism": inner_raw}
    partial = make_partial(outer_header, bytes(outer_grid), outer_meta)

    map_data, saved_map_data = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert list(map_data.segments.keys()) == [5]
    seg = map_data.segments[5]
    assert seg.type == 3
    assert seg.index == 2
    assert seg.neighbors == [7]
    assert seg.unique_id == 42
    # x/y were computed independently by the outer's own frame_map decode, then overwritten by the saved map's.
    assert (seg.x, seg.y) == (saved_map_data.segments[5].x, saved_map_data.segments[5].y)


# ---------------------------------------------------------------------------
# 9. set_segment_cleanset: capability permutations + wetness-level sub-branches
# ---------------------------------------------------------------------------


def test_set_segment_cleanset_segment_mopping_type_and_mop_pad_lifting_defaults():
    """default_cleanset gains different extra fields depending on which single capability flag is set."""
    map_data = make_map_with_segments(1)
    capability = SimpleNamespace(
        cleaning_route=False,
        segment_mopping_type=True,
        segment_mopping_settings=False,
        mop_pad_lifting=False,
        wetness_level=False,
        mop_clean_frequency=False,
        custom_cleaning_mode=False,
    )
    cleanset: dict = {}
    DreameVacuumMapDecoder.set_segment_cleanset(map_data, cleanset, capability)
    assert cleanset == {"1": [1, 3, 1, 0, 2, 2]}

    map_data2 = make_map_with_segments(1)
    capability2 = SimpleNamespace(
        cleaning_route=False,
        segment_mopping_type=False,
        segment_mopping_settings=False,
        mop_pad_lifting=True,
        wetness_level=False,
        mop_clean_frequency=False,
        custom_cleaning_mode=False,
    )
    cleanset2: dict = {}
    DreameVacuumMapDecoder.set_segment_cleanset(map_data2, cleanset2, capability2)
    assert cleanset2 == {"1": [1, 3, 1, 0, 2]}


def test_set_segment_cleanset_empty_dict_cleanset_type_elif_chain():
    """With an empty cleanset dict and no wetness_level/cleaning_route capability, cleanset_type falls through to
    segment_mopping_settings -> CUSTOM_MOPPING_ROUTE, or custom_cleaning_mode -> CLEANING_MODE."""
    map_data = make_map_with_segments(1)
    capability = SimpleNamespace(
        cleaning_route=False,
        segment_mopping_type=False,
        segment_mopping_settings=True,
        mop_pad_lifting=False,
        wetness_level=False,
        mop_clean_frequency=False,
        custom_cleaning_mode=False,
    )
    DreameVacuumMapDecoder.set_segment_cleanset(map_data, {}, capability)
    assert map_data.segments[1].cleanset_type == CleansetType.CUSTOM_MOPPING_ROUTE

    map_data2 = make_map_with_segments(1)
    capability2 = SimpleNamespace(
        cleaning_route=False,
        segment_mopping_type=False,
        segment_mopping_settings=False,
        mop_pad_lifting=False,
        wetness_level=False,
        mop_clean_frequency=False,
        custom_cleaning_mode=True,
    )
    DreameVacuumMapDecoder.set_segment_cleanset(map_data2, {}, capability2)
    assert map_data2.segments[1].cleanset_type == CleansetType.CLEANING_MODE


def test_set_segment_cleanset_explicit_entry_with_capability_resolves_wetness_level():
    """A non-empty cleanset with a capability object resolves cleanset_type via the for-loop's capability branch
    (not the len(v)>4 fallback used when capability is None), then decodes the wetness-level sub-branches where
    the split mopping-settings' middle/high nibbles are both zero."""
    map_data = make_map_with_segments(1, 2, 3)
    cleanset = {
        "1": [1, 30, 1, 0, 2, 5],  # item[1]=30 (>26) -> water_volume 3
        "2": [1, 3, 1, 0, 2, 5],  # item[1]=3 (<6) -> water_volume 1
        "3": [1, 10, 1, 0, 2, 5],  # item[1]=10 (else) -> water_volume 2
    }
    capability = SimpleNamespace(
        cleaning_route=False,
        segment_mopping_type=False,
        segment_mopping_settings=False,
        mop_pad_lifting=False,
        wetness_level=True,
        mop_clean_frequency=False,
        custom_cleaning_mode=False,
    )

    DreameVacuumMapDecoder.set_segment_cleanset(map_data, cleanset, capability)

    for sid in (1, 2, 3):
        assert map_data.segments[sid].cleanset_type == CleansetType.WETNESS_LEVEL
    assert (map_data.segments[1].water_volume, map_data.segments[1].wetness_level) == (3, 30)
    assert (map_data.segments[2].water_volume, map_data.segments[2].wetness_level) == (1, 3)
    assert (map_data.segments[3].water_volume, map_data.segments[3].wetness_level) == (2, 10)


def test_set_segment_cleanset_wetness_level_water_volume_1_and_3_elif_branches():
    """When the mopping-settings split does NOT give middle/high nibbles of zero, wetness_level is instead derived
    from the already-resolved water_volume (1 -> 5, 3 -> 27)."""
    map_data = make_map_with_segments(1, 2)
    cleanset = {
        "1": [1, 1, 1, 0, 2, DreameVacuumMapDecoder.combine_mopping_settings([0, 0, 1])],
        "2": [1, 1, 1, 0, 2, DreameVacuumMapDecoder.combine_mopping_settings([0, 0, 3])],
    }
    capability = SimpleNamespace(
        cleaning_route=False,
        segment_mopping_type=False,
        segment_mopping_settings=False,
        mop_pad_lifting=False,
        wetness_level=True,
        mop_clean_frequency=False,
        custom_cleaning_mode=False,
    )

    DreameVacuumMapDecoder.set_segment_cleanset(map_data, cleanset, capability)

    assert (map_data.segments[1].water_volume, map_data.segments[1].wetness_level) == (1, 5)
    assert (map_data.segments[2].water_volume, map_data.segments[2].wetness_level) == (3, 27)


def test_set_segment_cleanset_wetness_level_max_15_variants():
    """WETNESS_LEVEL_MAX_15 (wetness_level + mop_clean_frequency): the zero-nibble branch (>14/<6/else thresholds
    at 15 rather than 27) and the water_volume==1/3/else elif chain (wetness 5/15/10)."""
    map_data_zero_branch = make_map_with_segments(1, 2, 3)
    cleanset_zero_branch = {
        "1": [1, 30, 1, 0, 2, 5],  # >14 -> water_volume 3
        "2": [1, 3, 1, 0, 2, 5],  # <6 -> water_volume 1
        "3": [1, 10, 1, 0, 2, 5],  # else -> water_volume 2
    }
    capability = SimpleNamespace(
        cleaning_route=False,
        segment_mopping_type=False,
        segment_mopping_settings=False,
        mop_pad_lifting=False,
        wetness_level=True,
        mop_clean_frequency=True,
        custom_cleaning_mode=False,
    )
    DreameVacuumMapDecoder.set_segment_cleanset(map_data_zero_branch, cleanset_zero_branch, capability)
    for sid in (1, 2, 3):
        assert map_data_zero_branch.segments[sid].cleanset_type == CleansetType.WETNESS_LEVEL_MAX_15
    assert (map_data_zero_branch.segments[1].water_volume, map_data_zero_branch.segments[1].wetness_level) == (3, 30)
    assert (map_data_zero_branch.segments[2].water_volume, map_data_zero_branch.segments[2].wetness_level) == (1, 3)
    assert (map_data_zero_branch.segments[3].water_volume, map_data_zero_branch.segments[3].wetness_level) == (2, 10)

    map_data_wv_branch = make_map_with_segments(1, 2, 3)
    cleanset_wv_branch = {
        "1": [1, 1, 1, 0, 2, 546],  # values=[2,2,2] -> water_volume 2 -> else -> wetness 10
        "2": [1, 1, 1, 0, 2, DreameVacuumMapDecoder.combine_mopping_settings([0, 0, 1])],  # water_volume1->wetness5
        "3": [1, 1, 1, 0, 2, DreameVacuumMapDecoder.combine_mopping_settings([0, 0, 3])],  # water_volume3->wetness15
    }
    DreameVacuumMapDecoder.set_segment_cleanset(map_data_wv_branch, cleanset_wv_branch, capability)
    assert (map_data_wv_branch.segments[1].water_volume, map_data_wv_branch.segments[1].wetness_level) == (2, 10)
    assert (map_data_wv_branch.segments[2].water_volume, map_data_wv_branch.segments[2].wetness_level) == (1, 5)
    assert (map_data_wv_branch.segments[3].water_volume, map_data_wv_branch.segments[3].wetness_level) == (3, 15)


# ---------------------------------------------------------------------------
# 10. set_segment_floor_material / set_segment_color_index / get_carpets
# ---------------------------------------------------------------------------


def test_set_segment_floor_material_high_material_forced_to_zero():
    """material > 7 is always forced to 0; material in (4, 7] without both carpet_type+carpet_material capability
    is also forced to 0 even though it's within the 'valid' range."""
    map_data = MapData()
    map_data.rotation = 0
    seg_too_high = Segment(1, 0, 0, 20, 10, 10, 5)
    seg_too_high.floor_material = 8
    seg_missing_capability = Segment(2, 0, 0, 20, 10, 10, 5)
    seg_missing_capability.floor_material = 6
    seg_with_capability = Segment(3, 0, 0, 20, 10, 10, 5)
    seg_with_capability.floor_material = 6
    map_data.segments = {1: seg_too_high, 2: seg_missing_capability, 3: seg_with_capability}

    fm1: dict = {}
    DreameVacuumMapDecoder.set_segment_floor_material(map_data, 1, fm1, None)
    fm2: dict = {}
    DreameVacuumMapDecoder.set_segment_floor_material(
        map_data, 2, fm2, SimpleNamespace(carpet_type=False, carpet_material=True)
    )
    fm3: dict = {}
    DreameVacuumMapDecoder.set_segment_floor_material(
        map_data, 3, fm3, SimpleNamespace(carpet_type=True, carpet_material=True)
    )

    assert fm1 == {1: 0}
    assert fm2 == {2: 0}
    assert fm3 == {3: 6}


def test_set_segment_color_index_no_segments_is_a_no_op():
    """An empty/None segments dict returns immediately without raising."""
    map_data = MapData()
    assert map_data.segments is None
    DreameVacuumMapDecoder.set_segment_color_index(map_data)
    assert map_data.segments is None


def test_get_carpets_same_offset_returns_saved_carpet_pixels_unchanged():
    """When the saved map shares the exact same top-left as the current map, no offset filtering is needed and the
    saved carpet_pixels list is returned as-is."""
    map_data = MapData()
    map_data.dimensions = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=50)
    saved_map_data = MapData()
    saved_map_data.dimensions = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=50)
    saved_map_data.carpet_pixels = [(1, 1), (2, 2)]

    result = DreameVacuumMapDecoder.get_carpets(map_data, saved_map_data)

    assert result is saved_map_data.carpet_pixels


# ---------------------------------------------------------------------------
# 11. P-frame carpet-pixel bookkeeping / path append / obstacle segment refresh
# ---------------------------------------------------------------------------


def test_decode_p_frame_removes_stale_carpet_pixel_when_bit_clears():
    """A P-frame update whose merged pixel no longer carries the carpet bit removes that coordinate from the
    existing carpet_pixels list, leaving unrelated entries untouched."""
    current_map_data = decode_initial_5x5()
    current_map_data.carpet_pixels = [(2, 2), (4, 4)]
    grid = bytearray(5 * 5)
    grid[2 * 5 + 2] = 1  # segment pixel with no carpet bit
    header = build_header(map_id=1, frame_id=2, frame_type=MapFrameType.P.value, width=5, height=5)
    partial = make_partial(header, bytes(grid), {})

    result = DreameVacuumMapDecoder.decode_p_map_data_from_partial(partial, current_map_data, False)

    assert result.carpet_pixels == [(4, 4)]


def test_decode_p_frame_initializes_and_appends_new_carpet_pixel():
    """When carpet_pixels starts at None, the first carpet pixel found in a P-frame update both initializes the
    list and appends the new coordinate."""
    current_map_data = decode_initial_5x5()
    assert current_map_data.carpet_pixels is None
    grid = bytearray(5 * 5)
    grid[3 * 5 + 3] = 3  # low bits == 3: carpet bit set, segment_id 3
    header = build_header(map_id=1, frame_id=2, frame_type=MapFrameType.P.value, width=5, height=5)
    partial = make_partial(header, bytes(grid), {})

    result = DreameVacuumMapDecoder.decode_p_map_data_from_partial(partial, current_map_data, False)

    assert result.carpet_pixels == [(3, 3)]


def test_decode_p_frame_vslam_map_sets_need_optimization():
    """A P-frame merge with vslam_map=True flags the map as needing optimization."""
    current_map_data = decode_initial_5x5()
    grid = bytearray(5 * 5)
    grid[0] = 5
    header = build_header(map_id=1, frame_id=2, frame_type=MapFrameType.P.value, width=5, height=5)
    partial = make_partial(header, bytes(grid), {})

    result = DreameVacuumMapDecoder.decode_p_map_data_from_partial(partial, current_map_data, True)

    assert result.need_optimization is True


def test_decode_p_frame_appends_path_to_existing_path_list():
    """When current_map_data already has a path, the P-frame's new path points are appended (not replaced)."""
    current_map_data = decode_initial_5x5()
    current_map_data.path = [Path(0, 0, PathType.LINE)]
    header = build_header(map_id=1, frame_id=2, frame_type=MapFrameType.P.value, width=0, height=0)
    partial = make_partial(header, b"", {"tr": "L5,5"})

    result = DreameVacuumMapDecoder.decode_p_map_data_from_partial(partial, current_map_data, False)

    assert [(p.x, p.y) for p in result.path] == [(0, 0), (5, 5)]


def test_decode_p_frame_refreshes_obstacle_segments():
    """After merging, existing obstacles have set_segment() re-run against the (possibly updated) current map."""
    current_map_data = decode_initial_5x5()
    header = build_header(map_id=1, frame_id=2, frame_type=MapFrameType.P.value, width=0, height=0)
    partial = make_partial(header, b"", {"ai_obstacle": [[100, 100, 142, 0.9]]})

    result = DreameVacuumMapDecoder.decode_p_map_data_from_partial(partial, current_map_data, False)

    assert result.obstacles["1"].segment is not None


# ---------------------------------------------------------------------------
# 12. decode_cleaning_map_data
# ---------------------------------------------------------------------------


def test_decode_cleaning_map_data_invalid_cleaning_map_str_returns_none():
    """A cleaning_map_str that fails to decode (garbage base64/zlib) returns None immediately."""
    map_data = decode_initial_5x5()
    assert DreameVacuumMapDecoder.decode_cleaning_map_data(map_data, "!!!") is None


def test_decode_cleaning_map_data_without_cleaning_map_str_falls_back_to_map_data_header():
    """With no cleaning_map_str, the cleaning map's header fields are copied straight from map_data."""
    map_data = decode_initial_5x5()

    cleaning_map = DreameVacuumMapDecoder.decode_cleaning_map_data(map_data, None)

    assert cleaning_map.map_id == map_data.map_id
    assert cleaning_map.frame_id == map_data.frame_id
    assert cleaning_map.history_map is True
    assert cleaning_map.cleaning_map is True


def test_decode_cleaning_map_data_with_real_payload_marks_dirty_pixels():
    """A real cleaning_map_str payload is decoded and merged: cleaned_segments comes from 'CleanArea', dirty/clean
    markers are written into the cleaning map's own pixel_type copy, and a docked robot with no robot_position
    inherits the charger position."""
    width, height = 4, 4
    grid = bytearray(width * height)
    grid[2 * width + 2] = 1  # matches the cleaning marker location below
    header = build_header(width=width, height=height)
    partial = make_partial(header, bytes(grid), {"seg_inf": {"1": {"type": 1, "index": 0}}})
    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)
    map_data.docked = True
    map_data.robot_position = None
    map_data.charger_position = None

    clean_header = build_header(map_id=9, frame_id=9, width=width, height=height)
    clean_grid = bytearray(width * height)
    clean_grid[2 * width + 2] = 1  # value & 0x03 == 1 -> dirty marker
    clean_raw_str = build_raw_map_str(clean_header, bytes(clean_grid), {"CleanArea": [[1, 2]]})

    cleaning_map = DreameVacuumMapDecoder.decode_cleaning_map_data(map_data, clean_raw_str)

    assert cleaning_map.map_id == 9
    assert cleaning_map.cleaned_segments == [[1, 2]]
    assert cleaning_map.has_dirty_area is True
    assert cleaning_map.has_cleaned_area is False
    assert int(cleaning_map.pixel_type[2, 2]) == MapPixelType.DIRTY_AREA.value
    assert cleaning_map.docked is True


# ---------------------------------------------------------------------------
# 13. Remaining saved-map merge stragglers found after the first coverage pass
# ---------------------------------------------------------------------------


def test_decode_restored_map_merge_copies_wall_sentinel_from_outer_own_pixel_type():
    """When the saved-map cell has no segment (segment_id == 0), the if/elif at 722/729 falls to the 'clean_value'
    branch even for restored_map=True; a WALL (255) value in the outer frame's own pixel_type is copied through."""
    inner_header = build_header(map_id=50, width=1, height=1, grid_size=50)
    inner_raw = build_raw_map_str(inner_header, bytes([0]), {})  # single zero pixel: segment_id always 0

    outer_header = build_header(map_id=1, width=1, height=1, grid_size=50)
    partial = make_partial(outer_header, bytes([2]), {"ris": 2, "rism": inner_raw})  # segment_id=2 -> WALL

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.combined_pixel_type.tolist() == [[255]]


def test_decode_saved_map_segments_none_with_status_0_creates_empty_dict():
    """else(753) branch: when the outer frame never built its own segments (None) and saved_map_status is 0/1,
    an empty segments dict is created before attempting the per-key merge."""
    inner_header = build_header(map_id=60, width=2, height=2, grid_size=50)
    inner_meta = {"seg_inf": {"1": {"type": 1, "index": 0}}}
    inner_raw = build_raw_map_str(inner_header, bytes([1, 0, 0, 0]), inner_meta)

    outer_header = build_header(map_id=2, width=0, height=0, grid_size=50)
    partial = make_partial(outer_header, b"", {"ris": 0, "rism": inner_raw})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.segments == {}


def test_decode_saved_map_propagates_charger_furniture_and_robot_fallback():
    """docked + no charger_position/robot_position pulls the charger from the saved map (790), furnitures/version
    are copied when saved_map_status==2 (806-807), and the freshly-propagated charger then seeds robot_position
    (822) since the map isn't itself a saved map and the robot is docked."""
    inner_header = build_header(map_id=70, charger=(77, 88, 0), width=2, height=2, grid_size=50)
    inner_meta = {"funiture_info": [[11, 8, 3, 40, 60, 0, 500, 600, 0, 45.0, 0, 0, 1.5, 2]]}
    inner_raw = build_raw_map_str(inner_header, bytes([2, 0, 0, 0]), inner_meta)

    outer_header = build_header(map_id=3, charger=(0, 0, 0), width=2, height=2, grid_size=50)
    outer_meta = {"ris": 2, "oc": 1, "nc": True, "nr": True, "rism": inner_raw}
    partial = make_partial(outer_header, bytes([2, 0, 0, 0]), outer_meta)

    map_data, saved_map_data = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert (map_data.charger_position.x, map_data.charger_position.y) == (77, 88)
    assert map_data.furnitures is saved_map_data.saved_furnitures
    assert map_data.furniture_version == 1
    assert (map_data.robot_position.x, map_data.robot_position.y) == (77, 88)


def test_decode_p_frame_propagates_detected_carpets_cruise_points_and_low_lying_areas():
    """A P-frame carrying carpet_info / pointinfo.tpoint / sneak_areas keys refreshes the corresponding
    current_map_data fields wholesale."""
    current_map_data = decode_initial_5x5()
    header = build_header(map_id=1, frame_id=2, frame_type=MapFrameType.P.value, width=0, height=0)
    meta = {
        "carpet_info": {"7": [0, 0, 10, 10, 3, 1, True]},
        "pointinfo": {"tpoint": [[3, 4, 0, 1]]},
        "sneak_areas": [{"id": 9, "roi": [0, 0, 10, 0, 10, 10, 0, 10], "type": 2, "hide": False, "ms": 1, "area": 100}],
    }
    partial = make_partial(header, b"", meta)

    result = DreameVacuumMapDecoder.decode_p_map_data_from_partial(partial, current_map_data, False)

    assert result.detected_carpets[0].id == 7
    assert (result.active_cruise_points[1].x, result.active_cruise_points[1].y) == (3, 4)
    assert result.low_lying_areas[0].id == 9


def test_decode_p_frame_assigns_path_directly_when_current_path_is_none():
    """When current_map_data.path starts out None (no prior path yet), the new P-frame path is assigned directly
    rather than extended."""
    current_map_data = decode_initial_5x5()
    assert current_map_data.path is None
    header = build_header(map_id=1, frame_id=2, frame_type=MapFrameType.P.value, width=0, height=0)
    partial = make_partial(header, b"", {"tr": "L5,5"})

    result = DreameVacuumMapDecoder.decode_p_map_data_from_partial(partial, current_map_data, False)

    assert [(p.x, p.y) for p in result.path] == [(5, 5)]


def test_set_segment_cleanset_for_loop_cleaning_route_and_segment_mopping_settings():
    """The non-empty-cleanset for-loop's capability elif chain resolves CLEANING_ROUTE and CUSTOM_MOPPING_ROUTE
    when wetness_level is off but cleaning_route / segment_mopping_settings is on, respectively."""
    map_data_route = make_map_with_segments(1)
    capability_route = SimpleNamespace(
        wetness_level=False,
        cleaning_route=True,
        segment_mopping_settings=False,
        segment_mopping_type=False,
        mop_pad_lifting=False,
        mop_clean_frequency=False,
        custom_cleaning_mode=False,
    )
    DreameVacuumMapDecoder.set_segment_cleanset(map_data_route, {"1": [1, 3, 1, 0, 2, 5]}, capability_route)
    assert map_data_route.segments[1].cleanset_type == CleansetType.CLEANING_ROUTE

    map_data_custom = make_map_with_segments(1)
    capability_custom = SimpleNamespace(
        wetness_level=False,
        cleaning_route=False,
        segment_mopping_settings=True,
        segment_mopping_type=False,
        mop_pad_lifting=False,
        mop_clean_frequency=False,
        custom_cleaning_mode=False,
    )
    DreameVacuumMapDecoder.set_segment_cleanset(map_data_custom, {"1": [1, 3, 1, 0, 2, 5]}, capability_custom)
    assert map_data_custom.segments[1].cleanset_type == CleansetType.CUSTOM_MOPPING_ROUTE
