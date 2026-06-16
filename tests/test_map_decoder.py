"""Tests for DreameVacuumMapDecoder functionality."""

from __future__ import annotations

import pytest

from custom_components.dreame_vacuum.dreame.vacuum_types import (
    MapFrameType,
    MapPixelType,
    Segment,
)

# py_mini_racer is a HA runtime dependency not always available in test env
try:
    from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder

    HAS_MAP_DECODER = True
except ImportError:
    HAS_MAP_DECODER = False


@pytest.mark.skipif(not HAS_MAP_DECODER, reason="py_mini_racer not installed")
def test_map_decoder_class_exists():
    """Test that DreameVacuumMapDecoder can be imported."""
    assert callable(DreameVacuumMapDecoder)


@pytest.mark.skipif(not HAS_MAP_DECODER, reason="py_mini_racer not installed")
def test_map_decoder_has_decode_method():
    """Test that decode_map_data_from_partial method exists."""
    assert hasattr(DreameVacuumMapDecoder, "decode_map_data_from_partial")


@pytest.mark.skipif(not HAS_MAP_DECODER, reason="py_mini_racer not installed")
def test_map_decoder_has_set_segment_cleanset():
    """Test that set_segment_cleanset static method exists."""
    assert hasattr(DreameVacuumMapDecoder, "set_segment_cleanset")
    assert callable(DreameVacuumMapDecoder.set_segment_cleanset)


@pytest.mark.skipif(not HAS_MAP_DECODER, reason="py_mini_racer not installed")
def test_map_decoder_has_set_segment_color_index():
    """Test that set_segment_color_index static method exists."""
    assert hasattr(DreameVacuumMapDecoder, "set_segment_color_index")
    assert callable(DreameVacuumMapDecoder.set_segment_color_index)


def test_map_frame_types():
    """Test that map frame types are properly defined."""
    assert MapFrameType.I is not None
    assert MapFrameType.P is not None


def test_map_pixel_types():
    """Test that pixel types are properly defined."""
    assert MapPixelType.OUTSIDE is not None
    assert MapPixelType.WALL is not None
    assert MapPixelType.FLOOR is not None


def test_segment_dataclass():
    """Test that Segment can be instantiated."""
    seg = Segment(segment_id=1)
    assert seg.segment_id == 1


# ---------------------------------------------------------------------------
# Characterisation tests for _get_pixel_type hidden_segments parameter
# ---------------------------------------------------------------------------

try:
    from custom_components.dreame_vacuum.dreame.vacuum_types import MapData

    HAS_MAP_DATA = True
except ImportError:
    HAS_MAP_DATA = False

_SKIP_PIXEL = not (HAS_MAP_DECODER and HAS_MAP_DATA)


@pytest.mark.skipif(_SKIP_PIXEL, reason="py_mini_racer or MapData not available")
def test_get_pixel_type_hidden_wall_when_segment_in_frozenset():
    """Pixel with bit-7 set whose segment is in hidden_segments → HIDDEN_WALL."""
    md = MapData()
    pixel = 0x80 | 5  # bit 7 + segment_id 5
    result, carpet = DreameVacuumMapDecoder._get_pixel_type(md, pixel, False, frozenset({5}))
    assert result == MapPixelType.HIDDEN_WALL.value
    assert carpet is False


@pytest.mark.skipif(_SKIP_PIXEL, reason="py_mini_racer or MapData not available")
def test_get_pixel_type_wall_when_segment_not_in_frozenset():
    """Pixel with bit-7 set whose segment is NOT in hidden_segments → WALL."""
    md = MapData()
    pixel = 0x80 | 5  # bit 7 + segment_id 5
    result, carpet = DreameVacuumMapDecoder._get_pixel_type(md, pixel, False, frozenset({3}))
    assert result == MapPixelType.WALL.value
    assert carpet is False


@pytest.mark.skipif(_SKIP_PIXEL, reason="py_mini_racer or MapData not available")
def test_get_pixel_type_wall_when_hidden_segments_none():
    """Pixel with bit-7 set, hidden_segments=None → WALL (no hidden logic)."""
    md = MapData()
    pixel = 0x80 | 5
    result, carpet = DreameVacuumMapDecoder._get_pixel_type(md, pixel, False, None)
    assert result == MapPixelType.WALL.value
    assert carpet is False


@pytest.mark.skipif(_SKIP_PIXEL, reason="py_mini_racer or MapData not available")
def test_get_pixel_type_wall_when_hidden_segments_omitted():
    """Default call (hidden_segments not passed) → WALL, no crash."""
    md = MapData()
    pixel = 0x80 | 5
    result, carpet = DreameVacuumMapDecoder._get_pixel_type(md, pixel)
    assert result == MapPixelType.WALL.value
    assert carpet is False


# ---------------------------------------------------------------------------
# Regression tests for _get_segment_center bounds checking
# ---------------------------------------------------------------------------

try:
    from custom_components.dreame_vacuum.dreame.vacuum_types import MapImageDimensions

    HAS_DIMS = True
except ImportError:
    HAS_DIMS = False

_SKIP_CENTER = not (HAS_MAP_DECODER and HAS_MAP_DATA and HAS_DIMS)


def _make_map_4x4(segment_id: int = 7) -> "MapData":
    """Build a minimal 4x4 MapData with segment_id at (row=1,col=2) and (row=2,col=2)."""
    md = MapData()
    md.dimensions = MapImageDimensions(top=0, left=0, height=4, width=4, grid_size=1)
    data = [0] * 16
    data[1 * 4 + 2] = segment_id  # row 1, col 2
    data[2 * 4 + 2] = segment_id  # row 2, col 2
    md.data = bytes(data)
    return md


@pytest.mark.skipif(_SKIP_CENTER, reason="py_mini_racer, MapData, or MapImageDimensions not available")
def test_get_segment_center_negative_center_returns_none():
    """center=-1 must return None (silent negative-index read before fix)."""
    md = _make_map_4x4()
    assert DreameVacuumMapDecoder._get_segment_center(md, 7, -1, True) is None


@pytest.mark.skipif(_SKIP_CENTER, reason="py_mini_racer, MapData, or MapImageDimensions not available")
def test_get_segment_center_center_equals_limit_returns_none():
    """center==width (vertical=True) is out-of-bounds → None."""
    md = _make_map_4x4()
    assert DreameVacuumMapDecoder._get_segment_center(md, 7, 4, True) is None


@pytest.mark.skipif(_SKIP_CENTER, reason="py_mini_racer, MapData, or MapImageDimensions not available")
def test_get_segment_center_center_far_out_of_bounds_returns_none():
    """center=100 far exceeds dims → None."""
    md = _make_map_4x4()
    assert DreameVacuumMapDecoder._get_segment_center(md, 7, 100, False) is None


@pytest.mark.skipif(_SKIP_CENTER, reason="py_mini_racer, MapData, or MapImageDimensions not available")
def test_get_segment_center_truncated_data_returns_none():
    """data shorter than width*height (4x4=16) → None even with valid center."""
    md = _make_map_4x4()
    md.data = bytes(8)  # truncated: only 8 bytes for a 16-pixel grid
    assert DreameVacuumMapDecoder._get_segment_center(md, 7, 2, True) is None


@pytest.mark.skipif(_SKIP_CENTER, reason="py_mini_racer, MapData, or MapImageDimensions not available")
def test_get_segment_center_nominal_returns_int():
    """Valid 4x4 grid with segment_id=7 at column 2 → returns 2 (characterised value)."""
    md = _make_map_4x4()
    result = DreameVacuumMapDecoder._get_segment_center(md, 7, 2, False)
    assert result == 2


# ---------------------------------------------------------------------------
# Regression test for UnboundLocalError x/y in simple AI obstacle branch
# ---------------------------------------------------------------------------

try:
    from custom_components.dreame_vacuum.dreame.vacuum_types import MapDataPartial, ObstacleType

    HAS_PARTIAL = True
except ImportError:
    HAS_PARTIAL = False

_SKIP_OBSTACLE = not (HAS_MAP_DECODER and HAS_PARTIAL)


@pytest.mark.skipif(_SKIP_OBSTACLE, reason="py_mini_racer or MapDataPartial not available")
def test_simple_ai_obstacle_uses_own_coordinates():
    """Simple AI obstacle (size==5, id<1000) must use obstacle_x/obstacle_y.

    Before the fix, the ``else`` branch referenced ``x``/``y`` (locals only
    bound in path/pixel loops).  A frame with width=height=0 skips all pixel
    loops so ``x``/``y`` are never assigned → UnboundLocalError, swallowed by
    the catch-all, resulting in zero obstacles.  After the fix the obstacle is
    registered with the correct coordinates.
    """
    partial = MapDataPartial()
    partial.map_id = 1
    partial.frame_id = 1
    partial.frame_type = MapFrameType.I.value  # 73
    partial.timestamp_ms = 0
    # Header all-zero → width=0, height=0 at offsets 19/21 (int16-LE)
    # 32 bytes > HEADER_SIZE(27) so raw is long enough to read all offsets
    partial.raw = bytes(32)
    # size==5 → branches "size >= 7" is False → else branch
    # type 142 == ObstacleType.OBSTACLE; id=5 (float(5)<1000); prob 0.9
    partial.data_json = {"ai_obstacle": [[1.5, 2.5, 142, 0.9, 5]]}

    result = DreameVacuumMapDecoder.decode_map_data_from_partial(partial, False)
    map_data, _ = result

    assert map_data is not None
    assert map_data.obstacles is not None
    assert "1" in map_data.obstacles, (
        "Obstacle not registered — likely x/y UnboundLocalError was swallowed"
    )
    obstacle = map_data.obstacles["1"]
    assert obstacle.x == 1.5, f"Expected x=1.5, got {obstacle.x}"
    assert obstacle.y == 2.5, f"Expected y=2.5, got {obstacle.y}"
    assert obstacle.type == ObstacleType.OBSTACLE, f"Expected OBSTACLE, got {obstacle.type}"
