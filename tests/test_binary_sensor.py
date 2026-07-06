"""Tests for Dreame Vacuum binary sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.binary_sensor import (
    BINARY_SENSORS,
    DreameVacuumBinarySensorEntity,
    async_setup_entry,
)
from custom_components.dreame_vacuum.dreame import DreameVacuumProperty
from custom_components.dreame_vacuum.entity import DreameVacuumBinarySensorEntityDescription


@pytest.fixture
def device() -> MagicMock:
    """Return a rich device mock suitable for entity construction.

    ``data``/``action_mapping``/``auto_switch_data``/``ai_data`` are real
    containers so ``default_exists_fn`` resolves property-based descriptions,
    and ``status`` carries the concrete fields the binary sensors read.
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
    status.charging = False
    status.docked = True
    return device


@pytest.fixture
def coordinator(device: MagicMock) -> MagicMock:
    """Return a coordinator mock wired to a fake hass for entity_id generation.

    The pytest-homeassistant plugin is disabled (``-p no:homeassistant`` in
    pyproject), so no real ``hass`` fixture exists. ``async_generate_entity_id``
    only needs ``hass.states.async_available`` to report the candidate id as free.
    """
    hass = MagicMock()
    hass.states.async_available.return_value = True
    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.device = device
    coordinator.last_update_success = True
    return coordinator


def _make_entity(coordinator: MagicMock) -> DreameVacuumBinarySensorEntity:
    return DreameVacuumBinarySensorEntity(coordinator, BINARY_SENSORS[0])


def _make_entity_for_key(coordinator: MagicMock, key: str) -> DreameVacuumBinarySensorEntity:
    description = next(d for d in BINARY_SENSORS if d.key == key)
    return DreameVacuumBinarySensorEntity(coordinator, description)


def test_only_charging_state_defined() -> None:
    """The platform exposes charging_state plus the station diagnostic sensors."""
    assert len(BINARY_SENSORS) == 5
    assert BINARY_SENSORS[0].key == "charging_state"
    assert {d.key for d in BINARY_SENSORS} == {
        "charging_state",
        "dust_bag_dry_status",
        "station_clean_status",
        "mechanical_foot_status",
        "station_ota_status",
    }


def test_is_on_reflects_charging_true(coordinator: MagicMock, device: MagicMock) -> None:
    """is_on follows device.status.charging via value_fn."""
    device.status.charging = True
    entity = _make_entity(coordinator)
    assert entity.is_on is True


def test_is_on_reflects_charging_false(coordinator: MagicMock, device: MagicMock) -> None:
    """is_on is False when the robot is not charging."""
    device.status.charging = False
    entity = _make_entity(coordinator)
    assert entity.is_on is False


def test_is_on_returns_bool(coordinator: MagicMock, device: MagicMock) -> None:
    """is_on always coerces to a plain bool (value_fn path)."""
    device.status.charging = 1
    entity = _make_entity(coordinator)
    result = entity.is_on
    assert isinstance(result, bool)
    assert result is True


def test_icon_charging(coordinator: MagicMock, device: MagicMock) -> None:
    """Charging -> plugged battery icon."""
    device.status.charging = True
    device.status.docked = True
    entity = _make_entity(coordinator)
    assert entity.icon == "mdi:power-plug-battery"


def test_icon_docked_not_charging(coordinator: MagicMock, device: MagicMock) -> None:
    """Docked but not charging -> plugged (idle) icon."""
    device.status.charging = False
    device.status.docked = True
    entity = _make_entity(coordinator)
    assert entity.icon == "mdi:power-plug"


def test_icon_not_docked(coordinator: MagicMock, device: MagicMock) -> None:
    """Off the dock -> unplugged icon."""
    device.status.charging = False
    device.status.docked = False
    entity = _make_entity(coordinator)
    assert entity.icon == "mdi:power-plug-off"


def test_device_class(coordinator: MagicMock) -> None:
    """The charging_state sensor reports the BATTERY_CHARGING device class."""
    entity = _make_entity(coordinator)
    assert entity.device_class == "battery_charging"


def test_available_true(coordinator: MagicMock, device: MagicMock) -> None:
    """Entity is available while the device is connected."""
    device.device_connected = True
    entity = _make_entity(coordinator)
    assert entity.available is True


def test_available_false_when_disconnected(coordinator: MagicMock, device: MagicMock) -> None:
    """Entity is unavailable once the device is disconnected."""
    entity = _make_entity(coordinator)
    device.device_connected = False
    assert entity.available is False


def test_unique_id(coordinator: MagicMock) -> None:
    """unique_id is the MAC plus the computed key."""
    entity = _make_entity(coordinator)
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_charging_state"


def test_is_on_reads_property_when_no_value_fn(coordinator: MagicMock, device: MagicMock) -> None:
    """With a property_key and no value_fn, is_on coerces get_property() to bool.

    Exercises the property_key read branch and the bool(value) fallback of is_on
    using a synthetic description (the shipped one always sets value_fn).
    """
    description = DreameVacuumBinarySensorEntityDescription(
        key="synthetic_water_tank",
        property_key=DreameVacuumProperty.WATER_TANK,
    )
    device.get_property.return_value = 1
    entity = DreameVacuumBinarySensorEntity(coordinator, description)
    assert entity.is_on is True
    device.get_property.assert_called_with(DreameVacuumProperty.WATER_TANK)


def test_is_on_property_false(coordinator: MagicMock, device: MagicMock) -> None:
    """bool(value) fallback returns False for a falsy property value."""
    description = DreameVacuumBinarySensorEntityDescription(
        key="synthetic_water_tank",
        property_key=DreameVacuumProperty.WATER_TANK,
    )
    device.get_property.return_value = 0
    entity = DreameVacuumBinarySensorEntity(coordinator, description)
    assert entity.is_on is False


async def test_async_setup_entry_adds_entities(coordinator: MagicMock) -> None:
    """async_setup_entry adds one entity per existing description."""
    entry = MagicMock()
    entry.runtime_data.coordinator = coordinator
    added: list = []

    def _add(entities) -> None:
        added.extend(entities)

    await async_setup_entry(coordinator.hass, entry, _add)

    assert len(added) == 5
    assert isinstance(added[0], DreameVacuumBinarySensorEntity)
    assert added[0].entity_description.key == "charging_state"
    assert {entity.entity_description.key for entity in added} == {
        "charging_state",
        "dust_bag_dry_status",
        "station_clean_status",
        "mechanical_foot_status",
        "station_ota_status",
    }


@pytest.mark.parametrize(
    ("key", "prop", "device_class"),
    [
        ("dust_bag_dry_status", DreameVacuumProperty.DUST_BAG_DRY_STATUS, "running"),
        ("station_clean_status", DreameVacuumProperty.STATION_CLEAN_STATUS, "running"),
        ("mechanical_foot_status", DreameVacuumProperty.MECHANICAL_FOOT_STATUS, None),
        ("station_ota_status", DreameVacuumProperty.STATION_OTA_STATUS, "running"),
    ],
)
def test_station_sensor_is_on_reflects_property_value(
    coordinator: MagicMock,
    device: MagicMock,
    key: str,
    prop: DreameVacuumProperty,
    device_class: str | None,
) -> None:
    """Each station diagnostic sensor follows its mapped property's truthiness."""
    device.get_property.side_effect = lambda p, _prop=prop: 1 if p == _prop else 0
    entity = _make_entity_for_key(coordinator, key)
    assert entity.is_on is True
    assert isinstance(entity.is_on, bool)
    assert entity.device_class == device_class


@pytest.mark.parametrize(
    "key",
    [
        "dust_bag_dry_status",
        "station_clean_status",
        "mechanical_foot_status",
        "station_ota_status",
    ],
)
def test_station_sensor_is_off_when_property_zero(
    coordinator: MagicMock,
    device: MagicMock,
    key: str,
) -> None:
    """The sensor reads False when its mapped property value is 0."""
    device.get_property.return_value = 0
    entity = _make_entity_for_key(coordinator, key)
    assert entity.is_on is False


@pytest.mark.parametrize(
    "key",
    [
        "dust_bag_dry_status",
        "station_clean_status",
        "mechanical_foot_status",
        "station_ota_status",
    ],
)
def test_station_sensor_disabled_by_default(coordinator: MagicMock, key: str) -> None:
    """The new station diagnostic sensors are opt-in (disabled by default)."""
    entity = _make_entity_for_key(coordinator, key)
    assert entity.entity_description.entity_registry_enabled_default is False
    assert entity.entity_description.entity_category == "diagnostic"


@pytest.mark.parametrize(
    ("key", "expected_unique_id"),
    [
        ("dust_bag_dry_status", "AA:BB:CC:DD:EE:FF_dust_bag_dry_status"),
        ("station_clean_status", "AA:BB:CC:DD:EE:FF_station_clean_status"),
        ("mechanical_foot_status", "AA:BB:CC:DD:EE:FF_mechanical_foot_status"),
        ("station_ota_status", "AA:BB:CC:DD:EE:FF_station_ota_status"),
    ],
)
def test_station_sensor_unique_id(coordinator: MagicMock, key: str, expected_unique_id: str) -> None:
    """unique_id is the MAC plus the station diagnostic sensor's key."""
    entity = _make_entity_for_key(coordinator, key)
    assert entity.unique_id == expected_unique_id
