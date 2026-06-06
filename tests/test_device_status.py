"""Tests for DreameVacuumDeviceStatus properties and attributes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame.device_status import (
    _BOOLEAN_PROPERTIES,
    DreameVacuumDeviceStatus,
)
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    DreameVacuumChargingStatus,
    DreameVacuumDeviceCapability,
    DreameVacuumErrorCode,
    DreameVacuumProperty,
    DreameVacuumState,
    DreameVacuumStatus,
    DreameVacuumTaskStatus,
    DreameVacuumTaskType,
)


@pytest.fixture
def mock_device_for_status():
    """Create a mock device suitable for DreameVacuumDeviceStatus."""
    device = MagicMock()

    # Basic property storage
    properties = {
        DreameVacuumProperty.STATE.name: DreameVacuumState.IDLE.value,
        DreameVacuumProperty.STATUS.name: DreameVacuumStatus.STANDBY.value,
        DreameVacuumProperty.ERROR.name: DreameVacuumErrorCode.NO_ERROR.value,
        DreameVacuumProperty.BATTERY_LEVEL.name: 100,
        DreameVacuumProperty.CHARGING_STATUS.name: DreameVacuumChargingStatus.CHARGING.value,
        DreameVacuumProperty.TASK_STATUS.name: DreameVacuumTaskStatus.COMPLETED.value,
        DreameVacuumProperty.TASK_TYPE.name: DreameVacuumTaskType.STANDARD_CLEANING.value,
        DreameVacuumProperty.CLEANED_AREA.name: 0,
        DreameVacuumProperty.CLEANING_TIME.name: 0,
        DreameVacuumProperty.SUCTION_LEVEL.name: 1,
        DreameVacuumProperty.CLEANING_MODE.name: 0,
    }

    def get_property(prop_name):
        return properties.get(prop_name)

    device.get_property = MagicMock(side_effect=get_property)

    # Mock capability
    capability = MagicMock(spec=DreameVacuumDeviceCapability)
    capability.lidar_navigation = True
    capability.self_wash_base = False
    capability.auto_empty_base = False
    capability.camera_streaming = False
    capability.dnd_task = False
    capability.carpet_recognition = True
    capability.auto_carpet_cleaning = False
    capability.mop_pad_lifting_plus = False
    capability.mop_pad_unmounting = False
    capability.auto_empty_mode = False
    capability.detergent = False
    capability.smart_mop_washing = False
    capability.clean_carpets_first = False
    capability.drainage = False
    capability.hot_washing = False
    capability.auto_switch_settings = False
    capability.large_particles_boost = False
    capability.max_suction_power = False
    capability.uv_sterilization = False
    capability.custom_cleaning_mode = False
    capability.cleaning_route = False
    capability.cleangenius = False
    capability.cleangenius_mode = False
    capability.water_temperature = False
    capability.silent_drying = False
    capability.hair_compression = False
    capability.side_brush_carpet_rotate = False
    capability.auto_lds_lifting = False
    capability.dnd_functions = False
    capability.custom_mopping_route = False
    capability.self_clean_frequency = False
    capability.floor_direction_cleaning = False
    capability.intensive_carpet_cleaning = False
    capability.mop_extend = False
    capability.mop_pad_swing = False
    capability.mop_pad_swing_plus = False
    capability.auto_recleaning = False
    capability.auto_rewashing = False
    capability.mop_clean_frequency = False
    capability.backup_map = False
    capability.disable_sensor_cleaning = False
    capability.embedded_tank = False
    capability.shortcuts = False
    capability.off_peak_charging = False
    capability.deodorizer = False
    capability.wheel = False
    capability.scale_inhibitor = False
    capability.cruising = False
    capability.mop_washing_with_detergent = False
    capability.ultra_clean_mode = False
    capability.list = []
    device.capability = capability

    return device


def test_boolean_properties_is_frozenset():
    """Test that _BOOLEAN_PROPERTIES is a frozenset for O(1) lookup."""
    assert isinstance(_BOOLEAN_PROPERTIES, frozenset)
    assert len(_BOOLEAN_PROPERTIES) > 0


def test_boolean_properties_contains_expected():
    """Test that expected properties are in the boolean set."""
    assert DreameVacuumProperty.CHILD_LOCK in _BOOLEAN_PROPERTIES
    assert DreameVacuumProperty.CARPET_BOOST in _BOOLEAN_PROPERTIES
    assert DreameVacuumProperty.RESUME_CLEANING in _BOOLEAN_PROPERTIES


def test_device_status_class_exists():
    """Test that DreameVacuumDeviceStatus can be imported."""
    assert callable(DreameVacuumDeviceStatus)


def test_build_property_list_exists():
    """Test that _build_property_list method exists."""
    assert hasattr(DreameVacuumDeviceStatus, "_build_property_list")


def test_format_property_value_exists():
    """Test that _format_property_value method exists."""
    assert hasattr(DreameVacuumDeviceStatus, "_format_property_value")


def test_add_state_attributes_exists():
    """Test that _add_state_attributes method exists."""
    assert hasattr(DreameVacuumDeviceStatus, "_add_state_attributes")
