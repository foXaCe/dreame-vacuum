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
