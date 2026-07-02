"""Path-coverage tests for DreameVacuumMapDecoder.

Builds synthetic binary map payloads (27-byte header + pixel grid + JSON
metadata, optionally zlib-compressed/base64-encoded and AES-CBC encrypted
exactly like the real wire format) to exercise decode_map_partial,
decode_map_data_from_partial, decode_p_map_data_from_partial and the segment /
cleanset helper functions with precise, value-based assertions.
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from types import SimpleNamespace
import zlib

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import numpy as np
import pytest

from custom_components.dreame_vacuum.dreame.vacuum_types import (
    CleansetType,
    FurnitureType,
    MapFrameType,
    MapPixelType,
    ObstacleType,
    PathType,
    StartupMethod,
    TaskEndType,
)

# py_mini_racer is a HA runtime dependency not always available in test env
try:
    from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
    from custom_components.dreame_vacuum.dreame.vacuum_types import (
        Carpet,
        MapData,
        MapDataPartial,
        MapImageDimensions,
        Segment,
    )

    HAS_MAP_DECODER = True
except ImportError:
    HAS_MAP_DECODER = False

pytestmark = pytest.mark.skipif(not HAS_MAP_DECODER, reason="py_mini_racer or map_decoder deps not available")

HEADER_FMT = "<HHb11h"


# ---------------------------------------------------------------------------
# Payload builders
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
    """Pack the 27-byte binary map header (all fields little-endian int16, frame_type is 1 byte)."""
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


def make_partial(header: bytes, grid: bytes, meta: dict, timestamp_ms: int = 0) -> MapDataPartial:
    """Build a MapDataPartial directly, bypassing decode_map_partial's base64/zlib/AES layer."""
    partial = MapDataPartial()
    partial.map_id, partial.frame_id = struct.unpack_from("<HH", header, 0)
    partial.frame_type = struct.unpack_from("<b", header, 4)[0]
    partial.timestamp_ms = timestamp_ms
    partial.raw = header + grid
    partial.data_json = meta
    return partial


def build_raw_map_str(header: bytes, grid: bytes, meta: dict, key: str | None = None, iv: str | None = None) -> str:
    """Build the full base64(zlib(header+grid+json)) wire payload, optionally AES-CBC encrypted."""
    payload = header + grid + json.dumps(meta).encode("utf8")
    compressed = zlib.compress(payload)
    if key is not None:
        if iv is None:
            iv = "0123456789abcdef"
        aes_key = hashlib.sha256(key.encode()).hexdigest()[0:32].encode("utf8")
        padded = compressed + b"\x00" * ((-len(compressed)) % 16)
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv.encode("utf8")), backend=default_backend())
        encryptor = cipher.encryptor()
        out = encryptor.update(padded) + encryptor.finalize()
    else:
        out = compressed
    return base64.b64encode(out).decode("ascii")


# ---------------------------------------------------------------------------
# 1. decode_map_partial
# ---------------------------------------------------------------------------


def test_decode_map_partial_valid_payload_returns_expected_fields():
    """A well-formed base64/zlib payload decodes to the exact header + JSON metadata values."""
    header = build_header(map_id=42, frame_id=7, frame_type=MapFrameType.I.value, width=4, height=4)
    grid = bytes(16)
    raw_str = build_raw_map_str(header, grid, {"timestamp_ms": 12345, "cs": 10})

    partial = DreameVacuumMapDecoder.decode_map_partial(raw_str)

    assert partial is not None
    assert partial.map_id == 42
    assert partial.frame_id == 7
    assert partial.frame_type == MapFrameType.I.value
    assert partial.timestamp_ms == 12345
    assert partial.data_json == {"timestamp_ms": 12345, "cs": 10}
    # partial.raw is the whole decompressed blob (header + grid + trailing JSON bytes)
    assert partial.raw[: 27 + 16] == header + grid
    assert len(partial.raw) == 27 + 16 + len(json.dumps({"timestamp_ms": 12345, "cs": 10}).encode("utf8"))


def test_decode_map_partial_too_short_returns_none():
    """A payload shorter than 3 characters is rejected before any decoding attempt."""
    assert DreameVacuumMapDecoder.decode_map_partial("ab") is None
    assert DreameVacuumMapDecoder.decode_map_partial("") is None


def test_decode_map_partial_invalid_base64_returns_none():
    """Characters outside the base64 alphabet decode to an empty/garbage buffer, so zlib fails and None is returned."""
    assert DreameVacuumMapDecoder.decode_map_partial("!!!") is None


def test_decode_map_partial_header_too_small_returns_none():
    """A decompressed payload shorter than HEADER_SIZE (27) is rejected."""
    compressed = zlib.compress(b"short")
    raw_str = base64.b64encode(compressed).decode("ascii")

    assert DreameVacuumMapDecoder.decode_map_partial(raw_str) is None


def test_decode_map_partial_invalid_json_metadata_defaults_to_empty_dict():
    """Trailing bytes that aren't valid JSON leave data_json at its default {} and timestamp_ms at None."""
    header = build_header(width=0, height=0)
    payload = header + b"not-json-data"
    raw_str = base64.b64encode(zlib.compress(payload)).decode("ascii")

    partial = DreameVacuumMapDecoder.decode_map_partial(raw_str)

    assert partial is not None
    assert partial.data_json == {}
    assert partial.timestamp_ms is None


def test_decode_map_partial_bad_iv_length_returns_none():
    """A key without an explicit iv defaults to iv="", an invalid CBC IV size, so decryption fails and None is returned."""
    header = build_header(map_id=1, frame_id=1, width=0, height=0)
    raw_str = base64.b64encode(zlib.compress(header + b"{}")).decode("ascii")

    assert DreameVacuumMapDecoder.decode_map_partial(raw_str, key="somekey") is None


def test_decode_map_partial_aes_encrypted_payload_decrypts_with_matching_key_and_iv():
    """A payload encrypted with AES-CBC (key derived via sha256[:32] hex, explicit iv) decodes correctly."""
    header = build_header(map_id=9, frame_id=3, width=0, height=0)
    raw_str = build_raw_map_str(header, b"", {"timestamp_ms": 555}, key="mysecretkey", iv="0123456789abcdef")

    partial = DreameVacuumMapDecoder.decode_map_partial(raw_str, iv="0123456789abcdef", key="mysecretkey")

    assert partial is not None
    assert partial.map_id == 9
    assert partial.frame_id == 3
    assert partial.data_json == {"timestamp_ms": 555}


def test_decode_map_partial_comma_separated_key_variant_decrypts():
    """Format 'a,b,c': raw_map is values[0], key is values[1], any further comma parts are ignored."""
    header = build_header(map_id=11, frame_id=2, width=0, height=0)
    encrypted_b64 = build_raw_map_str(header, b"", {"foo": "bar"}, key="topsecret", iv="fedcba9876543210")
    combined = f"{encrypted_b64},topsecret,ignored-extra-part"

    partial = DreameVacuumMapDecoder.decode_map_partial(combined, iv="fedcba9876543210")

    assert partial is not None
    assert partial.map_id == 11
    assert partial.frame_id == 2
    assert partial.data_json == {"foo": "bar"}


# ---------------------------------------------------------------------------
# 2. decode_map_data_from_partial -- I frame core paths
# ---------------------------------------------------------------------------


def test_decode_map_data_from_partial_none_partial_returns_none():
    """A None MapDataPartial short-circuits to None (not a tuple)."""
    assert DreameVacuumMapDecoder.decode_map_data_from_partial(None, False) is None


def test_decode_map_data_from_partial_raw_none_returns_none_tuple():
    """A MapDataPartial with raw=None returns the (None, None) tuple."""
    partial = MapDataPartial()
    partial.raw = None

    result = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert result == (None, None)


def test_decode_i_frame_direct_segment_scheme_builds_segments_and_dimensions():
    """A saved-style I frame (no 'ris' key) uses the direct low-6-bit segment-id scheme."""
    width, height = 5, 5
    grid = bytearray(width * height)
    for x in range(1, 4):
        grid[2 * width + x] = 1
        grid[3 * width + x] = 2
    header = build_header(
        map_id=1,
        frame_id=1,
        robot=(100, 200, 0),
        charger=(50, 60, 0),
        grid_size=50,
        width=width,
        height=height,
    )
    meta = {"seg_inf": {"1": {"type": 1, "index": 0, "nei_id": [2]}, "2": {"type": 4, "index": 0}}}
    partial = make_partial(header, bytes(grid), meta)

    map_data, saved_map_data = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert saved_map_data is None
    assert map_data.empty_map is False
    assert map_data.saved_map is True
    assert map_data.dimensions.width == 5
    assert map_data.dimensions.height == 5
    assert map_data.dimensions.grid_size == 50
    assert set(map_data.segments.keys()) == {1, 2}
    assert map_data.segments[1].type == 1
    assert map_data.segments[1].name == "Living Room"
    assert map_data.segments[1].neighbors == [2]
    assert map_data.segments[2].type == 4
    assert map_data.segments[2].name == "Kitchen"
    assert map_data.robot_position.x == 100
    assert map_data.robot_position.y == 200
    assert map_data.charger_position.x == 50
    assert map_data.charger_position.y == 60
    assert int(map_data.pixel_type[1, 2]) == 1
    assert int(map_data.pixel_type[1, 3]) == 2


def test_decode_i_frame_frame_map_pixel_scheme():
    """fsm=1 selects the frame_map pixel scheme: bits 7-2 segment id, low 2 bits carpet/new-segment/wall."""
    width, height = 3, 3
    grid = bytearray(width * height)
    grid[0] = (5 << 2) | 0  # segment 5
    grid[1] = (5 << 2) | 3  # segment 5, carpet bit
    grid[2] = 63 << 2  # WALL marker
    grid[3] = 62 << 2  # FLOOR marker
    grid[4] = 61 << 2  # UNKNOWN marker
    grid[5] = 1  # low bits == 1 -> NEW_SEGMENT
    header = build_header(width=width, height=height)
    partial = make_partial(header, bytes(grid), {"fsm": 1})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.frame_map is True
    assert int(map_data.pixel_type[0, 0]) == 5
    assert int(map_data.pixel_type[1, 0]) == 5
    assert int(map_data.pixel_type[2, 0]) == MapPixelType.WALL.value
    assert int(map_data.pixel_type[0, 1]) == MapPixelType.FLOOR.value
    assert int(map_data.pixel_type[1, 1]) == MapPixelType.UNKNOWN.value
    assert int(map_data.pixel_type[2, 1]) == MapPixelType.NEW_SEGMENT.value
    assert map_data.carpet_pixels == [(1, 0)]


def test_decode_i_frame_ris_zero_initial_scan_marks_new_segment_and_wall():
    """ris=0 (initial room scan) only distinguishes NEW_SEGMENT/WALL markers, no real segment ids."""
    width, height = 2, 3
    grid = bytearray(width * height)
    grid[0] = 1  # -> NEW_SEGMENT
    grid[1] = 2  # -> WALL
    header = build_header(width=width, height=height)
    partial = make_partial(header, bytes(grid), {"ris": 0})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert int(map_data.pixel_type[0, 0]) == MapPixelType.NEW_SEGMENT.value
    assert int(map_data.pixel_type[1, 0]) == MapPixelType.WALL.value
    assert map_data.segments == {}


def test_decode_empty_map_2x2_all_zero():
    """A 2x2 grid of all-zero pixels is the special-cased 'empty map' marker."""
    header = build_header(width=2, height=2)
    partial = make_partial(header, bytes(4), {})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.empty_map is True


def test_decode_wifi_map_w_frame():
    """A W frame decodes wifi strength markers into pixel_type and clears robot_position/data."""
    width, height = 3, 3
    grid = bytearray(width * height)
    grid[0] = MapPixelType.WIFI_HIGH.value
    grid[4] = MapPixelType.WIFI_UNREACHED.value
    grid[8] = MapPixelType.WIFI_WALL.value
    header = build_header(frame_type=MapFrameType.W.value, robot=(11, 22, 0), width=width, height=height)
    partial = make_partial(header, bytes(grid), {})

    map_data, saved_map_data = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert saved_map_data is None
    assert map_data.wifi_map is True
    assert map_data.need_optimization is True
    assert map_data.robot_position is None
    assert map_data.data is None
    assert int(map_data.pixel_type[0, 0]) == MapPixelType.WIFI_HIGH.value
    assert int(map_data.pixel_type[1, 1]) == MapPixelType.WIFI_UNREACHED.value
    assert int(map_data.pixel_type[2, 2]) == MapPixelType.WIFI_WALL.value


def test_decode_i_frame_nested_rism_saved_map_merges_combined_pixel_type():
    """An I frame with ris=2 and an embedded 'rism' saved map merges combined_pixel_type from both frames."""
    inner_width, inner_height = 4, 4
    inner_grid = bytearray(inner_width * inner_height)
    for y in (1, 2):
        for x in (1, 2):
            inner_grid[y * inner_width + x] = 1
    inner_header = build_header(map_id=100, frame_id=1, charger=(20, 20, 0), width=inner_width, height=inner_height)
    inner_meta = {"seg_inf": {"1": {"type": 2, "index": 0}}}
    inner_raw_str = build_raw_map_str(inner_header, bytes(inner_grid), inner_meta)

    outer_grid = bytearray(4 * 4)
    outer_grid[1 * 4 + 1] = 1  # mark (1,1) as freshly-cleaned NEW_SEGMENT this session
    outer_header = build_header(map_id=1, frame_id=5, robot=(10, 10, 0), charger=(20, 20, 0), width=4, height=4)
    outer_meta = {"ris": 2, "rism": inner_raw_str}
    partial = make_partial(outer_header, bytes(outer_grid), outer_meta)

    map_data, saved_map_data = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert saved_map_data is not None
    assert saved_map_data.map_id == 100
    assert map_data.saved_map_id == 100
    assert set(map_data.segments.keys()) == {1}
    assert map_data.segments[1].type == 2
    assert map_data.segments[1].name == "Primary Bedroom"
    assert map_data.dimensions.left == 0
    assert map_data.dimensions.top == 0
    assert map_data.dimensions.width == 4
    assert map_data.dimensions.height == 4
    assert map_data.robot_position.x == 10
    assert map_data.robot_position.y == 10
    assert map_data.charger_position.x == 20
    assert map_data.charger_position.y == 20
    assert map_data.combined_pixel_type.shape == (4, 4)
    assert map_data.combined_dimensions.width == 4
    assert map_data.combined_dimensions.height == 4
    assert int(map_data.combined_pixel_type[1, 1]) == 1
    assert int(map_data.combined_pixel_type[0, 0]) == 0
    assert map_data.no_go_areas is None


def test_nc_nr_flags_clear_charger_and_robot_positions():
    """data_json 'nc'/'nr' flags clear charger_position/robot_position even though the header set them."""
    header = build_header(robot=(5, 5, 0), charger=(6, 6, 0), width=0, height=0)
    partial = make_partial(header, b"", {"nc": True, "nr": True})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.charger_position is None
    assert map_data.robot_position is None


# ---------------------------------------------------------------------------
# 3. decode_map_data_from_partial -- rich metadata fields
# ---------------------------------------------------------------------------


def test_decode_core_metadata_fields():
    """A broad set of scalar/status metadata fields decode to their exact expected values."""
    header = build_header(map_id=3, frame_id=4, width=4, height=4)
    meta = {
        "mra": 90,
        "cs": 1500,
        "wm": 2,
        "cf": 1,
        "clean_finish_remain_electricity": 80,
        "customeClean": {"foo": 1},
        "oc": True,
        "l2r": True,
        "iscleanlog": True,
        "us": 1,
        "risp": 0,
        "smd": 2,
        "ctyi": 3,
        "ds": 5,
        "wt": 2,
        "multime": 3,
        "decmap": None,
        "dos": 7,
        "suw": 6,
        "tr": "M5,5L10,10l3,3",
        "sa": [[1, "x"], [2, "y"]],
        "delsr": [1, 2],
        "da2": {"areas": [[10, 40, 30, 20]]},
        "sp": [[1, 2], [3, 4]],
        "cleanset": {"1": [1, 3, 1, 0]},
        "carpetcleanset": [[2, 1, 3, 10]],
    }
    partial = make_partial(header, bytes(16), meta)

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.rotation == 90
    assert map_data.cleaned_area == 1500
    assert map_data.work_status == 2
    assert map_data.completed is True
    assert map_data.remaining_battery == 80
    assert map_data.customized_cleaning == {"foo": 1}
    assert map_data.docked is True
    assert map_data.line_to_robot is True
    assert map_data.clean_log is True
    assert map_data.recovery_map is True
    assert map_data.new_map is True
    assert map_data.startup_method == StartupMethod.SCHEDULED_ACTIVATION
    assert map_data.task_end_type == TaskEndType.ABNORMAL_DOCKING
    assert map_data.dust_collection_count == 5
    assert map_data.mop_wash_count == 2
    assert map_data.multiple_cleaning_time == 3
    assert map_data.dos == 7
    assert map_data.temporary_map is True
    assert map_data.saved_map is False
    assert [(p.x, p.y, p.path_type) for p in map_data.path] == [
        (5, 5, PathType.MOP),
        (15, 15, PathType.LINE),
        (3, 3, PathType.LINE),
    ]
    assert map_data.active_segments == [1, 2]
    assert map_data.hidden_segments == [1, 2]
    assert vars(map_data.active_areas[0]) == {
        "x0": 10,
        "y0": 20,
        "x1": 30,
        "y1": 20,
        "x2": 30,
        "y2": 40,
        "x3": 10,
        "y3": 40,
        "angle": None,
    }
    assert [(p.x, p.y) for p in map_data.active_points] == [(1, 2), (3, 4)]
    assert map_data.cleanset == {"1": [1, 3, 1, 0]}
    assert map_data.sequence is True
    assert map_data.carpet_cleanset == [[2, 1, 3, 10]]
    # multiple_cleaning_time triggers decode_cleaning_map_data, which needs a real pixel_type array
    assert map_data.cleaning_map_data is not None
    assert map_data.cleaning_map_data.has_dirty_area is False
    assert map_data.cleaning_map_data.has_cleaned_area is False


def test_decode_geometry_metadata_fields():
    """Virtual walls, thresholds, curtains, carpets, cruise points and furniture decode to exact geometry."""
    header = build_header(width=0, height=0)
    meta = {
        "vw": {
            "rect": [[10, 40, 30, 20, 5]],
            "mop": [[1, 4, 3, 2]],
            "line": [[0, 0, 10, 10]],
            "addcpt": [[1, 2, 8, 9, 7, "1", 2]],
            "nocpt": [[0, 0, 5, 5]],
        },
        "vws": {
            "vwsl": [[1, 1, 2, 2]],
            "npthrsd": [[3, 3, 4, 4]],
            "ramp": [[0, 10, 10, 0, 1]],
        },
        "ct": {"line": [[5, 5, 15, 15]]},
        "carpet_polygon": {"3": [[0, 0, 10, 0, 10, 10, 0, 10], 1, 1]},
        "sneak_areas": [{"id": 9, "roi": [0, 0, 10, 0, 10, 10, 0, 10], "type": 2, "hide": False, "ms": 1, "area": 100}],
        "pointinfo": {"spoint": [[1, 2, 1, 0]], "tpoint": [[3, 4, 0, 1]]},
        "tpointinfo": [[5, 6, 1, 2]],
        "ai_furniture_new": [[100, 200, 1, 3, 90, 190, 20, 30, 180, 1.0]],
    }
    partial = make_partial(header, b"", meta)

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    no_go = map_data.no_go_areas[0]
    assert (no_go.x0, no_go.y0, no_go.x1, no_go.y1, no_go.x2, no_go.y2, no_go.x3, no_go.y3, no_go.angle) == (
        10,
        20,
        30,
        20,
        30,
        40,
        10,
        40,
        5,
    )
    no_mop = map_data.no_mopping_areas[0]
    assert (no_mop.x0, no_mop.y0, no_mop.x1, no_mop.y1) == (1, 2, 3, 2)
    wall = map_data.virtual_walls[0]
    assert (wall.x0, wall.y0, wall.x1, wall.y1) == (0, 0, 10, 10)

    carpet = map_data.carpets[0]
    assert carpet.id == 7
    assert (carpet.x0, carpet.y0, carpet.x1, carpet.y1, carpet.x2, carpet.y2, carpet.x3, carpet.y3) == (
        1,
        2,
        8,
        2,
        8,
        9,
        1,
        9,
    )
    assert carpet.ellipse is True
    assert carpet.carpet_type == 2

    ignored = map_data.ignored_carpets[0]
    assert ignored.id == 0
    assert ignored.ellipse is False

    passable = map_data.passable_thresholds[0]
    assert (passable.x0, passable.y0, passable.x1, passable.y1) == (1, 1, 2, 2)
    assert map_data.virtual_thresholds is None
    impassable = map_data.impassable_thresholds[0]
    assert (impassable.x0, impassable.y0, impassable.x1, impassable.y1) == (3, 3, 4, 4)

    ramp = map_data.ramps[0]
    assert (ramp.x0, ramp.y0, ramp.x1, ramp.y1, ramp.angle) == (0, 0, 10, 0, 1)

    curtain = map_data.curtains[0]
    assert (curtain.x0, curtain.y0, curtain.x1, curtain.y1) == (5, 5, 15, 15)

    detected = map_data.detected_carpets[0]
    assert detected.id == 3
    assert detected.carpet_type == 1
    assert detected.polygon == [0, 0, 10, 0, 10, 10, 0, 10]

    sneak = map_data.low_lying_areas[0]
    assert sneak.id == 9
    assert sneak.type == 2
    assert sneak.hidden is False
    assert sneak.ms == 1
    assert sneak.area == 100

    predefined = map_data.predefined_points[1]
    assert (predefined.x, predefined.y, predefined.completed, predefined.type) == (1, 2, True, 0)
    cruise = map_data.active_cruise_points[1]
    assert (cruise.x, cruise.y, cruise.completed, cruise.type) == (3, 4, False, 1)
    task_cruise = map_data.task_cruise_points[1]
    assert (task_cruise.x, task_cruise.y, task_cruise.completed, task_cruise.type) == (5, 6, True, 2)

    furniture = map_data.furnitures[1]
    assert (furniture.x, furniture.y) == (100, 200)
    assert (furniture.x0, furniture.y0) == (90, 190)
    assert (furniture.width, furniture.height) == (20, 30)
    assert furniture.type == FurnitureType.SINGLE_BED
    assert furniture.angle == 180.0
    assert furniture.scale == 1.0
    assert map_data.furniture_version == 0


def test_decode_legacy_funiture_info_format():
    """The legacy 'funiture_info' payload (furniture_version=1) swaps type 8<->25 and reads absolute rect fields."""
    header = build_header(width=0, height=0)
    furniture = [11, 8, 3, 40, 60, 0, 500, 600, 0, 45.0, 0, 0, 1.5, 2]
    partial = make_partial(header, b"", {"funiture_info": [furniture]})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    assert map_data.furniture_version == 1
    f = map_data.saved_furnitures[1]
    assert (f.x, f.y) == (500, 600)
    assert (f.x0, f.y0) == (480, 570)
    assert (f.width, f.height) == (40, 60)
    assert f.type == FurnitureType.ROUND_COFFEE_TABLE  # type 8 swapped to 25
    assert f.size_type == 2
    assert f.angle == 45.0
    assert f.scale == 1.5
    assert f.furniture_id == 11
    assert f.segment_id == 3


def test_decode_obstacle_neglected_room_resolves_segment_center():
    """A NEGLECTED_ROOM obstacle (type 200) reads its segment id from x and zeroes x/y/possibility."""
    header = build_header(width=0, height=0)
    obstacle = [1, 0, 200, 0.5, 5000, "pic.jpg", 7, 0.1, 0.2, 0.3, 0.4, 1, 2]
    partial = make_partial(header, b"", {"ai_obstacle": [obstacle]})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    obs = map_data.obstacles["1"]
    assert obs.type == ObstacleType.NEGLECTED_ROOM
    assert obs.x == 0
    assert obs.y == 0
    assert obs.possibility is None
    assert obs.object_id == 5000
    assert obs.file_name == "pic.jpg"
    assert obs.key == 7
    assert (obs.pos_x, obs.pos_y, obs.width, obs.height) == (10.0, 20.0, 30.0, 40.0)
    assert obs.picture_status == 1
    assert obs.ignore_status == 2


def test_get_segments_outline_simplified_for_large_segment():
    """A 2D segment large enough to need Moore-Neighbor tracing gets a Douglas-Peucker simplified outline."""
    width, height = 12, 12
    grid = bytearray(width * height)
    for y in range(2, 9):
        for x in range(2, 9):
            grid[y * width + x] = 1
    grid[5 * width + 5] = 0  # notch to make the contour non-trivial
    header = build_header(width=width, height=height, grid_size=50)
    partial = make_partial(header, bytes(grid), {})

    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)

    segment = map_data.segments[1]
    assert (segment.x0, segment.y0, segment.x1, segment.y1) == (100, 50, 450, 400)
    assert segment.outline == [[100, 100], [400, 100], [400, 400], [100, 400], [100, 150]]


# ---------------------------------------------------------------------------
# 4. decode_p_map_data_from_partial (delta frames)
# ---------------------------------------------------------------------------


def _decode_initial_5x5_map() -> MapData:
    width, height = 5, 5
    grid = bytearray(width * height)
    for x in range(1, 4):
        grid[2 * width + x] = 1
    header = build_header(map_id=1, frame_id=1, robot=(100, 200, 0), charger=(50, 60, 0), width=width, height=height)
    partial = make_partial(header, bytes(grid), {})
    map_data, _ = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)
    return map_data


def test_decode_p_frame_wrong_frame_type_returns_none():
    """A partial that isn't a P frame is rejected immediately."""
    header = build_header(frame_type=MapFrameType.I.value, width=0, height=0)
    partial = make_partial(header, b"", {})

    assert DreameVacuumMapDecoder.decode_p_map_data_from_partial(partial, MapData(), False) is None


def test_decode_p_frame_none_current_map_data_returns_none():
    """A P frame with no existing current_map_data to merge into returns None."""
    header = build_header(frame_type=MapFrameType.P.value, width=0, height=0)
    partial = make_partial(header, b"", {})

    assert DreameVacuumMapDecoder.decode_p_map_data_from_partial(partial, None, False) is None


def test_decode_p_frame_merges_same_size_update():
    """A same-size P frame adds a new segment pixel and a wall pixel, leaving unrelated pixels untouched."""
    current_map_data = _decode_initial_5x5_map()
    assert int(current_map_data.pixel_type[1, 2]) == 1
    assert int(current_map_data.pixel_type[0, 0]) == 0
    assert int(current_map_data.pixel_type[4, 4]) == 0

    grid = bytearray(5 * 5)
    grid[0 * 5 + 0] = 5  # new segment 5
    grid[4 * 5 + 4] = 0x80  # wall bit set
    header = build_header(
        map_id=1,
        frame_id=2,
        frame_type=MapFrameType.P.value,
        robot=(110, 210, 90),
        charger=(50, 60, 0),
        width=5,
        height=5,
    )
    partial = make_partial(header, bytes(grid), {"oc": False})

    result = DreameVacuumMapDecoder.decode_p_map_data_from_partial(partial, current_map_data, False)

    assert result is current_map_data
    assert result.frame_id == 2
    assert (result.robot_position.x, result.robot_position.y, result.robot_position.a) == (110, 210, 90)
    assert (result.dimensions.left, result.dimensions.top, result.dimensions.width, result.dimensions.height) == (
        0,
        0,
        5,
        5,
    )
    assert int(result.pixel_type[0, 0]) == 5
    assert int(result.pixel_type[4, 4]) == MapPixelType.WALL.value
    assert int(result.pixel_type[1, 2]) == 1  # unchanged from the I frame


def test_decode_p_frame_extends_canvas_and_shifts_old_data():
    """A P frame whose dimensions extend past the current canvas grows the buffer and shifts old pixel data."""
    current_map_data = _decode_initial_5x5_map()

    grid = bytearray(6 * 5)
    grid[0 * 6 + 0] = 9
    header = build_header(
        map_id=1, frame_id=3, frame_type=MapFrameType.P.value, grid_size=50, width=6, height=5, left=-50
    )
    partial = make_partial(header, bytes(grid), {})

    result = DreameVacuumMapDecoder.decode_p_map_data_from_partial(partial, current_map_data, False)

    assert (result.dimensions.left, result.dimensions.top, result.dimensions.width, result.dimensions.height) == (
        -50,
        0,
        6,
        5,
    )
    assert int(result.pixel_type[0, 0]) == 9
    assert int(result.pixel_type[2, 2]) == 1  # old segment-1 pixel shifted right by one cell


# ---------------------------------------------------------------------------
# 5. get_segments / _get_segment_center completions
# ---------------------------------------------------------------------------


def test_get_segments_direct_call_computes_bbox_and_center():
    """Calling get_segments directly on a hand-built pixel_type array yields exact bbox/center map coordinates."""
    map_data = MapData()
    map_data.dimensions = MapImageDimensions(top=0, left=0, height=4, width=4, grid_size=10)
    map_data.pixel_type = np.zeros((4, 4), dtype=np.uint8)
    map_data.pixel_type[1, 1] = 3
    map_data.pixel_type[2, 1] = 3
    map_data.saved_map_status = -1

    segments = DreameVacuumMapDecoder.get_segments(map_data, False)

    assert set(segments.keys()) == {3}
    seg = segments[3]
    assert (seg.x0, seg.y0, seg.x1, seg.y1) == (10, 0, 30, 10)
    assert (seg.x, seg.y) == (20, 10)


def test_get_segment_center_selects_widest_line_among_multiple():
    """When multiple disjoint runs of the segment id exist in the scan line, the widest one is used for the center."""
    map_data = MapData()
    map_data.dimensions = MapImageDimensions(top=0, left=0, height=12, width=1, grid_size=1)
    data = bytearray(12)
    data[0] = 4
    data[1] = 4  # short run: rows 0-1
    data[6] = 4
    data[7] = 4
    data[8] = 4
    data[9] = 4  # long run: rows 6-9 (separated by a 4-row zero gap)
    map_data.data = bytes(data)

    result = DreameVacuumMapDecoder._get_segment_center(map_data, 4, 0, True)

    assert result == 8


# ---------------------------------------------------------------------------
# 6. set_segment_cleanset
# ---------------------------------------------------------------------------


def _make_map_with_segments(*segment_ids: int) -> MapData:
    map_data = MapData()
    map_data.segments = {sid: Segment(sid, 0, 0, 10, 10, 5, 5) for sid in segment_ids}
    return map_data


def _dump_cleanset(segment: Segment) -> dict:
    return {
        "cleanset_type": segment.cleanset_type,
        "suction_level": segment.suction_level,
        "water_volume": segment.water_volume,
        "cleaning_times": segment.cleaning_times,
        "order": segment.order,
        "cleaning_mode": segment.cleaning_mode,
        "mopping_settings": segment.mopping_settings,
        "custom_mopping_route": segment.custom_mopping_route,
        "cleaning_route": segment.cleaning_route,
        "wetness_level": segment.wetness_level,
    }


def test_set_segment_cleanset_none_clears_all_fields():
    """cleanset=None sets cleanset_type=NONE and clears every cleaning-related segment attribute."""
    map_data = _make_map_with_segments(1)

    DreameVacuumMapDecoder.set_segment_cleanset(map_data, None, None)

    assert _dump_cleanset(map_data.segments[1]) == {
        "cleanset_type": CleansetType.NONE,
        "suction_level": None,
        "water_volume": None,
        "cleaning_times": None,
        "order": None,
        "cleaning_mode": None,
        "mopping_settings": None,
        "custom_mopping_route": None,
        "cleaning_route": None,
        "wetness_level": None,
    }


def test_set_segment_cleanset_default_empty_dict_no_capability():
    """An empty cleanset dict with no capability falls back to the hardcoded default_cleanset [1,3,1,0]."""
    map_data = _make_map_with_segments(1)
    cleanset: dict = {}

    DreameVacuumMapDecoder.set_segment_cleanset(map_data, cleanset, None)

    assert cleanset == {"1": [1, 3, 1, 0]}
    dumped = _dump_cleanset(map_data.segments[1])
    assert dumped["cleanset_type"] == CleansetType.DEFAULT
    assert dumped["suction_level"] == 1
    assert dumped["water_volume"] == 2
    assert dumped["cleaning_times"] == 1
    assert dumped["order"] == 0
    assert dumped["cleaning_mode"] is None


def test_set_segment_cleanset_cleaning_route_capability():
    """capability.cleaning_route=True extends default_cleanset and resolves CLEANING_ROUTE mopping settings."""
    map_data = _make_map_with_segments(1)
    capability = SimpleNamespace(
        cleaning_route=True,
        segment_mopping_type=False,
        segment_mopping_settings=False,
        mop_pad_lifting=False,
        wetness_level=False,
        mop_clean_frequency=False,
        custom_cleaning_mode=False,
    )
    cleanset: dict = {}

    DreameVacuumMapDecoder.set_segment_cleanset(map_data, cleanset, capability)

    assert cleanset == {"1": [1, 3, 1, 0, 2, 33]}
    dumped = _dump_cleanset(map_data.segments[1])
    assert dumped["cleanset_type"] == CleansetType.CLEANING_ROUTE
    assert dumped["water_volume"] == 2
    assert dumped["cleaning_mode"] == 2
    assert dumped["mopping_settings"] == 33
    assert dumped["custom_mopping_route"] == 0
    assert dumped["cleaning_route"] == 1
    assert dumped["wetness_level"] is None


def test_set_segment_cleanset_wetness_level_capability():
    """capability.wetness_level (without mop_clean_frequency) resolves WETNESS_LEVEL settings from mopping_settings."""
    map_data = _make_map_with_segments(1)
    capability = SimpleNamespace(
        cleaning_route=False,
        segment_mopping_type=False,
        segment_mopping_settings=True,
        mop_pad_lifting=False,
        wetness_level=True,
        mop_clean_frequency=False,
        custom_cleaning_mode=False,
    )
    cleanset: dict = {}

    DreameVacuumMapDecoder.set_segment_cleanset(map_data, cleanset, capability)

    assert cleanset == {"1": [1, 16, 1, 0, 2, 546]}
    dumped = _dump_cleanset(map_data.segments[1])
    assert dumped["cleanset_type"] == CleansetType.WETNESS_LEVEL
    assert dumped["water_volume"] == 2
    assert dumped["cleaning_mode"] == 2
    assert dumped["mopping_settings"] == 546
    assert dumped["custom_mopping_route"] == 0
    assert dumped["cleaning_route"] == 1
    assert dumped["wetness_level"] == 16


def test_set_segment_cleanset_explicit_cleaning_mode_entry():
    """An explicit per-segment cleanset entry with v[5]>0 resolves cleanset_type from the data, not the default."""
    map_data = _make_map_with_segments(5)
    cleanset = {"5": [1, 2, 1, 0, 3, 10]}

    DreameVacuumMapDecoder.set_segment_cleanset(map_data, cleanset, None)

    dumped = _dump_cleanset(map_data.segments[5])
    assert dumped["cleanset_type"] == CleansetType.CLEANING_MODE
    assert dumped["suction_level"] == 1
    assert dumped["water_volume"] == 1
    assert dumped["cleaning_times"] == 1
    assert dumped["order"] == 0
    assert dumped["cleaning_mode"] == 3
    assert dumped["mopping_settings"] is None


# ---------------------------------------------------------------------------
# 7. set_carpet_cleanset / get_carpets
# ---------------------------------------------------------------------------


def test_get_carpets_applies_offset_and_filters_out_of_range():
    """get_carpets shifts saved-map carpet pixel coordinates by the dimension offset and drops out-of-range/zero ones."""
    map_data = MapData()
    map_data.dimensions = MapImageDimensions(top=0, left=0, height=10, width=10, grid_size=50)
    map_data.pixel_type = np.zeros((10, 10), dtype=np.uint8)
    map_data.pixel_type[4, 4] = 7

    saved_map_data = MapData()
    saved_map_data.dimensions = MapImageDimensions(top=-50, left=-50, height=10, width=10, grid_size=50)
    saved_map_data.carpet_pixels = [(0, 0), (5, 5), (20, 20)]

    result = DreameVacuumMapDecoder.get_carpets(map_data, saved_map_data)

    assert result == [(4, 4)]


def test_set_carpet_cleanset_applies_to_segment_and_carpet_lists():
    """setting[0]==2 targets a segment's carpet settings, setting[0]==0/other targets detected_carpets/carpets."""
    map_data = MapData()
    map_data.segments = {2: Segment(2, 0, 0, 10, 10, 5, 5)}
    map_data.detected_carpets = [Carpet(1, 0, 0, 10, 0, 10, 10, 0, 10)]
    map_data.carpets = [Carpet(4, 0, 0, 10, 0, 10, 10, 0, 10)]
    capability = SimpleNamespace(carpet_material=True)
    cleanset = [[2, 2, 5, 9], [0, 1, 3, None], [1, 4, 2]]

    DreameVacuumMapDecoder.set_carpet_cleanset(map_data, cleanset, capability)

    assert (map_data.segments[2].carpet_cleaning, map_data.segments[2].carpet_settings) == (5, 9)
    assert (map_data.detected_carpets[0].carpet_cleaning, map_data.detected_carpets[0].carpet_settings) == (3, None)
    assert (map_data.carpets[0].carpet_cleaning, map_data.carpets[0].carpet_settings) == (2, None)


# ---------------------------------------------------------------------------
# 8. floor material / color index / mopping-settings helpers
# ---------------------------------------------------------------------------


def test_set_floor_material_and_segment_floor_material():
    """set_floor_material resolves the floor_material dict entry and the rotated direction for a low material code."""
    map_data = MapData()
    map_data.rotation = 0
    segment = Segment(3, 0, 0, 20, 10, 10, 5)
    segment.floor_material = 2
    segment.floor_material_direction = 90
    map_data.segments = {3: segment}
    capability = SimpleNamespace(carpet_type=True, carpet_material=True)

    DreameVacuumMapDecoder.set_floor_material(map_data, capability)

    assert map_data.floor_material == {3: 3}
    assert segment.floor_material_rotated_direction == 90


def test_set_segment_color_index_assigns_sequential_indices():
    """Color indices are assigned in sorted segment-id order, wrapping modulo 16."""
    map_data = MapData()
    map_data.segments = {5: Segment(5, 0, 0, 1, 1), 2: Segment(2, 0, 0, 1, 1), 9: Segment(9, 0, 0, 1, 1)}

    DreameVacuumMapDecoder.set_segment_color_index(map_data)

    assert {sid: seg.color_index for sid, seg in map_data.segments.items()} == {2: 0, 5: 1, 9: 2}


def test_split_and_combine_mopping_settings_round_trip():
    """split_mopping_settings/combine_mopping_settings are exact inverses for a packed 12-bit value."""
    values = DreameVacuumMapDecoder.split_mopping_settings(0x321)

    assert values == [1, 2, 3]
    assert DreameVacuumMapDecoder.combine_mopping_settings(values) == 0x321


def test_split_mopping_settings_none_and_combine_edge_cases():
    """split_mopping_settings(None) returns None; combine_mopping_settings tolerates empty/None input."""
    assert DreameVacuumMapDecoder.split_mopping_settings(None) is None
    assert DreameVacuumMapDecoder.combine_mopping_settings([]) == 0
    assert DreameVacuumMapDecoder.combine_mopping_settings(None) == 0


# ---------------------------------------------------------------------------
# 9. small static helpers
# ---------------------------------------------------------------------------


def test_read_int_8_le_and_read_int_16():
    """_read_int_8_le reads a signed little-endian byte; _read_int_16 reads a signed big-endian short."""
    assert DreameVacuumMapDecoder._read_int_8_le(b"\xff", 0) == -1
    assert DreameVacuumMapDecoder._read_int_16(b"\x01\x02", 0) == 258


def test_compare_segment_neighbors_and_compare_colors():
    """_compare_segment_neighbors orders by neighbor count first, then segment id; _compare_colors by [1] then [0]."""
    seg_a = Segment(1)
    seg_a.neighbors = [1, 2, 3]
    seg_b = Segment(2)
    seg_b.neighbors = [1]
    seg_c = Segment(9)
    seg_c.neighbors = [9, 9, 9]

    assert DreameVacuumMapDecoder._compare_segment_neighbors(seg_a, seg_b) == -2
    # seg_a and seg_c both have 3 neighbors -> tie-break falls back to segment_id difference
    assert DreameVacuumMapDecoder._compare_segment_neighbors(seg_a, seg_c) == 1 - 9
    assert DreameVacuumMapDecoder._compare_colors([1, 5], [2, 5]) == -1
    assert DreameVacuumMapDecoder._compare_colors([1, 5], [2, 9]) == -4


# ---------------------------------------------------------------------------
# 10. decode_map / decode_saved_map wrappers
# ---------------------------------------------------------------------------


def test_decode_map_wrapper_round_trip():
    """decode_map() chains decode_map_partial + decode_map_data_from_partial and returns a (MapData, None) tuple."""
    header = build_header(map_id=77, frame_id=8, width=2, height=2)
    raw_str = build_raw_map_str(header, bytes(4), {"timestamp_ms": 999})

    map_data, saved_map_data = DreameVacuumMapDecoder.decode_map(raw_str, False)

    assert map_data.map_id == 77
    assert map_data.frame_id == 8
    assert saved_map_data is None


def test_decode_saved_map_wrapper_returns_map_data_only():
    """decode_saved_map() returns just the first element of decode_map()'s tuple."""
    header = build_header(map_id=88, frame_id=1, width=2, height=2)
    raw_str = build_raw_map_str(header, bytes(4), {})

    map_data = DreameVacuumMapDecoder.decode_saved_map(raw_str, False)

    assert map_data.map_id == 88
