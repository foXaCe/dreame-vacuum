"""Tests for Dreame Vacuum sensors."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame import DreameVacuumProperty
from custom_components.dreame_vacuum.sensor import (
    SENSORS,
    DreameVacuumSensorEntity,
    async_setup_entry,
)


def _find(*, key: str | None = None, property_key: DreameVacuumProperty | None = None):
    """Return the shipped sensor description matching key or property_key."""
    for desc in SENSORS:
        if key is not None and desc.key == key:
            return desc
        if property_key is not None and desc.property_key is property_key and not desc.key:
            return desc
    raise AssertionError(f"sensor description not found: key={key} property_key={property_key}")


@pytest.fixture
def device() -> MagicMock:
    """Return a device mock rich enough to build and render every sensor.

    ``data`` holds every property value so ``default_exists_fn`` resolves the
    property-based descriptions; the numeric status fields below feed the
    comparison-based icon callbacks (battery level, low-water warning).
    """
    device = MagicMock()
    device.name = "Test Vacuum"
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.device_connected = True
    device.available = True
    device.data = {prop.value: 0 for prop in DreameVacuumProperty}
    device.action_mapping = {}
    device.auto_switch_data = {}
    device.ai_data = {}

    status = device.status
    status.battery_level = 80
    status.charging = False
    status.low_water_warning.value = 0
    # Concrete flags read by availability callbacks (e.g. CLEANED_AREA).
    status.fast_mapping = False
    status.cruising = False
    return device


@pytest.fixture
def coordinator(device: MagicMock) -> MagicMock:
    """Coordinator mock with a fake hass (real one is disabled in this suite)."""
    hass = MagicMock()
    hass.states.async_available.return_value = True
    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.device = device
    coordinator.last_update_success = True
    return coordinator


def _build(coordinator: MagicMock, description) -> DreameVacuumSensorEntity:
    return DreameVacuumSensorEntity(coordinator, description)


# --- descriptions / registry ---------------------------------------------------


def test_sensors_non_empty() -> None:
    """The platform defines a non-trivial set of sensors."""
    assert len(SENSORS) > 20


def test_sensor_keys_unique_per_mac() -> None:
    """Computed unique_ids must not collide across the shipped descriptions."""
    device = MagicMock()
    device.name = "V"
    device.mac = "MAC"
    device.data = {prop.value: 0 for prop in DreameVacuumProperty}
    device.action_mapping = {}
    device.auto_switch_data = {}
    device.ai_data = {}
    device.status.battery_level = 50
    device.status.charging = False
    device.status.low_water_warning.value = 0
    hass = MagicMock()
    hass.states.async_available.return_value = True
    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.device = device
    coordinator.last_update_success = True

    ids = [DreameVacuumSensorEntity(coordinator, d).unique_id for d in SENSORS if d.exists_fn(d, device)]
    assert len(ids) == len(set(ids)), "duplicate unique_id among sensors"


# --- async_setup_entry ----------------------------------------------------------


async def test_async_setup_entry_creates_entities(coordinator: MagicMock, device: MagicMock) -> None:
    """async_setup_entry instantiates one entity per existing description.

    Building every entity exercises __init__ and _set_id (icon_fn/value_fn) for
    the whole SENSORS table.
    """
    entry = MagicMock()
    entry.runtime_data.coordinator = coordinator
    added: list = []

    await async_setup_entry(coordinator.hass, entry, lambda e: added.extend(e))

    expected = [d for d in SENSORS if d.exists_fn(d, device)]
    assert len(added) == len(expected)
    assert added, "expected at least one sensor entity"
    assert all(isinstance(e, DreameVacuumSensorEntity) for e in added)


async def test_async_setup_entry_filters_non_existing(coordinator: MagicMock, device: MagicMock) -> None:
    """A description whose capability gate is off is filtered out.

    ``mop_pad`` requires ``self_wash_base``; turning that capability off must
    drop it from the created set.
    """
    device.capability.self_wash_base = False
    entry = MagicMock()
    entry.runtime_data.coordinator = coordinator
    added: list = []

    await async_setup_entry(coordinator.hass, entry, lambda e: added.extend(e))

    keys = {e.entity_description.key for e in added}
    assert "mop_pad" not in keys


# --- native_value ---------------------------------------------------------------


def test_native_value_property_with_computed_fn(coordinator: MagicMock, device: MagicMock) -> None:
    """A plain property sensor reads the '<prop>_name' display getter on status.

    The sensor entity resolves its value function with the '_name' suffix, so
    CLEANED_AREA reads ``status.cleaned_area_name``.
    """
    device.status.cleaned_area_name = 42
    entity = _build(coordinator, _find(property_key=DreameVacuumProperty.CLEANED_AREA))
    assert entity.native_value == 42


def test_native_value_uses_name_variant(coordinator: MagicMock, device: MagicMock) -> None:
    """Sensors prefer the '<prop>_name' display variant when present.

    STATE exposes ``status.state_name``; the sensor entity overrides its value
    function to target it.
    """
    device.status.state_name = "cleaning"
    entity = _build(coordinator, _find(property_key=DreameVacuumProperty.STATE))
    assert entity.native_value == "cleaning"


def test_native_value_custom_value_fn_firmware(coordinator: MagicMock, device: MagicMock) -> None:
    """The firmware_version sensor returns device.info.version."""
    device.info.version = "9.8.7"
    entity = _build(coordinator, _find(key="firmware_version"))
    assert entity.native_value == "9.8.7"


def test_native_value_current_room(coordinator: MagicMock, device: MagicMock) -> None:
    """current_room returns the room name from status."""
    device.status.current_room.name = "Kitchen"
    entity = _build(coordinator, _find(key="current_room"))
    assert entity.native_value == "Kitchen"


def test_native_value_first_cleaning_date_timestamp(coordinator: MagicMock, device: MagicMock) -> None:
    """FIRST_CLEANING_DATE converts a unix timestamp into a datetime."""
    desc = _find(property_key=DreameVacuumProperty.FIRST_CLEANING_DATE)
    device.get_property.return_value = 1_700_000_000
    entity = _build(coordinator, desc)
    value = entity.native_value
    assert isinstance(value, datetime)
    assert value == datetime.fromtimestamp(1_700_000_000, tz=datetime.now().astimezone().tzinfo)


def test_native_value_first_cleaning_date_none(coordinator: MagicMock, device: MagicMock) -> None:
    """FIRST_CLEANING_DATE returns None when no timestamp is reported."""
    desc = _find(property_key=DreameVacuumProperty.FIRST_CLEANING_DATE)
    device.get_property.return_value = 0
    entity = _build(coordinator, desc)
    assert entity.native_value is None


# --- icon callbacks -------------------------------------------------------------


def test_icon_relocation_status(coordinator: MagicMock, device: MagicMock) -> None:
    """Relocation icon falls back to the default marker for an unknown status."""
    from custom_components.dreame_vacuum.dreame import DreameVacuumRelocationStatus

    device.status.relocation_status = DreameVacuumRelocationStatus.SUCCESS
    entity = _build(coordinator, _find(property_key=DreameVacuumProperty.RELOCATION_STATUS))
    assert entity.icon == "mdi:map-marker-check"


def test_icon_water_tank_installed(coordinator: MagicMock, device: MagicMock) -> None:
    """Water tank icon switches on installation state."""
    desc = _find(property_key=DreameVacuumProperty.WATER_TANK)
    device.status.water_tank_or_mop_installed = True
    entity = _build(coordinator, desc)
    assert entity.icon == "mdi:water-pump"
    device.status.water_tank_or_mop_installed = False
    entity2 = _build(coordinator, desc)
    assert entity2.icon == "mdi:water-pump-off"


def test_icon_dust_collection(coordinator: MagicMock, device: MagicMock) -> None:
    """Dust collection icon reflects whether collection is active."""
    desc = _find(property_key=DreameVacuumProperty.DUST_COLLECTION)
    device.status.dust_collection = True
    assert _build(coordinator, desc).icon == "mdi:delete-sweep"
    device.status.dust_collection = False
    assert _build(coordinator, desc).icon == "mdi:delete-off"


def test_icon_battery_level(coordinator: MagicMock, device: MagicMock) -> None:
    """Battery icon is derived from the battery level / charging state."""
    device.status.battery_level = 100
    device.status.charging = False
    entity = _build(coordinator, _find(property_key=DreameVacuumProperty.BATTERY_LEVEL))
    assert entity.icon == "mdi:battery"


def test_icon_low_water_warning(coordinator: MagicMock, device: MagicMock) -> None:
    """Low-water icon trips to alert above warning level 1."""
    desc = _find(property_key=DreameVacuumProperty.LOW_WATER_WARNING)
    device.status.low_water_warning.value = 2
    assert _build(coordinator, desc).icon == "mdi:water-alert"
    device.status.low_water_warning.value = 0
    assert _build(coordinator, desc).icon == "mdi:water-check"


def test_icon_error_states(coordinator: MagicMock, device: MagicMock) -> None:
    """Error icon distinguishes error / warning / healthy."""
    desc = _find(property_key=DreameVacuumProperty.ERROR)
    device.status.has_error = True
    device.status.has_warning = False
    assert _build(coordinator, desc).icon == "mdi:alert-circle-outline"
    device.status.has_error = False
    device.status.has_warning = True
    assert _build(coordinator, desc).icon == "mdi:alert-outline"
    device.status.has_warning = False
    assert _build(coordinator, desc).icon == "mdi:check-circle-outline"


# --- extra_state_attributes -----------------------------------------------------


def test_error_extra_state_attributes(coordinator: MagicMock, device: MagicMock) -> None:
    """The error sensor exposes value/faults/description attributes."""
    desc = _find(property_key=DreameVacuumProperty.ERROR)
    device.status.error = "blocked"
    device.status.faults = ["f1"]
    device.status.error_description = ["wheel jammed", "extra"]
    entity = _build(coordinator, desc)
    attrs = entity.extra_state_attributes
    assert attrs["faults"] == ["f1"]
    assert attrs["description"] == "wheel jammed"


# --- availability ---------------------------------------------------------------


def test_available_true(coordinator: MagicMock, device: MagicMock) -> None:
    """A sensor with no availability override is available while connected."""
    entity = _build(coordinator, _find(property_key=DreameVacuumProperty.CLEANED_AREA))
    assert entity.available is True


def test_available_false_when_disconnected(coordinator: MagicMock, device: MagicMock) -> None:
    """Disconnecting the device makes the sensor unavailable."""
    entity = _build(coordinator, _find(property_key=DreameVacuumProperty.CLEANED_AREA))
    device.device_connected = False
    assert entity.available is False


def test_available_fn_mapping_time(coordinator: MagicMock, device: MagicMock) -> None:
    """The mapping_time sensor is only available during fast mapping."""
    desc = _find(key="mapping_time")
    device.status.fast_mapping = True
    assert _build(coordinator, desc).available is True
    device.status.fast_mapping = False
    assert _build(coordinator, desc).available is False
