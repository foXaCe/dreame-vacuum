"""Tests for the recorder integration platform (exclude_attributes)."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.dreame_vacuum.dreame.const import ATTR_ROOMS, ATTR_STATUS
from custom_components.dreame_vacuum.dreame.vacuum_types import ATTR_MAP_ID
from custom_components.dreame_vacuum.recorder import (
    CAMERA_UNRECORDED_ATTRIBUTES,
    VACUUM_UNRECORDED_ATTRIBUTES,
    exclude_attributes,
)


def test_exclude_attributes_returns_union_of_camera_and_vacuum_sets() -> None:
    result = exclude_attributes(MagicMock())
    assert result == set(CAMERA_UNRECORDED_ATTRIBUTES) | set(VACUUM_UNRECORDED_ATTRIBUTES)


def test_exclude_attributes_returns_a_plain_set() -> None:
    result = exclude_attributes(MagicMock())
    assert isinstance(result, set)


def test_exclude_attributes_contains_known_camera_and_vacuum_attributes() -> None:
    result = exclude_attributes(MagicMock())
    # A large-map-data camera attribute that must never hit the recorder DB.
    assert ATTR_MAP_ID in result
    assert ATTR_ROOMS in result
    # Vectorized wall/door geometry from the saved map — large map data too.
    assert "wall_lines" in result
    assert "door_lines" in result
    # Data-URI icons served through camera attributes (several KB each).
    assert "robot_icon" in result
    assert "robot_beam_icon" in result
    # A vacuum attribute duplicated by a dedicated sensor entity.
    assert ATTR_STATUS in result
    assert "battery_level" in result
    # Structured schedule/DND state — bulky and duplicated by dedicated entities.
    assert "schedule" in result
    assert "dnd" in result


def test_exclude_attributes_does_not_depend_on_hass_argument() -> None:
    """The function is a pure lookup; passing distinct mocks yields the same result."""
    assert exclude_attributes(MagicMock()) == exclude_attributes(MagicMock())
