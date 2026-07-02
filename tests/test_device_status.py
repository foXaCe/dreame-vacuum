"""Tests for DreameVacuumDeviceStatus properties and attributes."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.dreame_vacuum.dreame.device_status import (
    _BOOLEAN_PROPERTIES,
    DreameVacuumDeviceStatus,
)
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    DreameVacuumProperty,
    DreameVacuumSuctionLevel,
    DreameVacuumWaterTank,
)


def _make_status(properties: dict) -> DreameVacuumDeviceStatus:
    """Build a DreameVacuumDeviceStatus backed by a controlled property map.

    ``device_status.py`` reads properties via ``self._device.get_property(prop)``
    where ``prop`` is the ``DreameVacuumProperty`` enum member itself, so the
    dict must be keyed the same way.
    """
    device = MagicMock()
    device.get_property = MagicMock(side_effect=lambda prop: properties.get(prop))
    return DreameVacuumDeviceStatus(device)


def test_boolean_properties_is_frozenset():
    """Test that _BOOLEAN_PROPERTIES is a frozenset for O(1) lookup."""
    assert isinstance(_BOOLEAN_PROPERTIES, frozenset)
    assert len(_BOOLEAN_PROPERTIES) > 0


def test_boolean_properties_contains_expected():
    """Test that expected properties are in the boolean set."""
    assert DreameVacuumProperty.CHILD_LOCK in _BOOLEAN_PROPERTIES
    assert DreameVacuumProperty.CARPET_BOOST in _BOOLEAN_PROPERTIES
    assert DreameVacuumProperty.RESUME_CLEANING in _BOOLEAN_PROPERTIES


def test_suction_level_returns_enum_for_valid_value():
    """A known SUCTION_LEVEL property value resolves to its enum member."""
    status = _make_status({DreameVacuumProperty.SUCTION_LEVEL: DreameVacuumSuctionLevel.STRONG.value})
    assert status.suction_level == DreameVacuumSuctionLevel.STRONG


def test_suction_level_unknown_for_missing_value():
    """A missing/unset SUCTION_LEVEL property resolves to UNKNOWN."""
    status = _make_status({})
    assert status.suction_level == DreameVacuumSuctionLevel.UNKNOWN


def test_battery_level_returns_raw_property_value():
    """battery_level passes the raw device property value through untouched."""
    status = _make_status({DreameVacuumProperty.BATTERY_LEVEL: 87})
    assert status.battery_level == 87


def test_water_tank_installed_for_value_three():
    """A raw WATER_TANK value of 3 always reports INSTALLED, regardless of enum mapping."""
    status = _make_status({DreameVacuumProperty.WATER_TANK: 3})
    assert status.water_tank == DreameVacuumWaterTank.INSTALLED


def test_water_tank_unknown_when_property_missing():
    """A missing WATER_TANK property resolves to UNKNOWN."""
    status = _make_status({})
    assert status.water_tank == DreameVacuumWaterTank.UNKNOWN
