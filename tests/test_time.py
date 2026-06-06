"""Tests for the Dreame Vacuum time platform.

Covers ``native_value`` parsing (valid / invalid / empty -> None), the coordinator
update callback (including the ``device is None`` short-circuit), ``async_set_value``
success and every failure branch (unavailable, ``None`` value, command error,
``not_implemented``) and ``async_setup_entry``.

``device``/``device.status`` are ``MagicMock`` objects, so the time entity resolves
its getter to ``device.status.<key>`` and its setter to ``device.set_<key>``; tests
assert against those.

Local fixtures only; ``tests/conftest.py`` is not modified.
"""

from __future__ import annotations

from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.dreame_vacuum import time as time_mod
from custom_components.dreame_vacuum.dreame import (
    DeviceException,
    DeviceUpdateFailedException,
    InvalidActionException,
    InvalidValueException,
)
from custom_components.dreame_vacuum.time import (
    TIMES,
    DreameVacuumTimeEntity,
    async_setup_entry,
)


@pytest.fixture
def hass() -> MagicMock:
    """Lightweight fake hass (real fixture unavailable under ``-p no:homeassistant``)."""
    fake = MagicMock()
    fake.states.async_available = MagicMock(return_value=True)

    async def _exec(func, *args, **kwargs):
        return func(*args, **kwargs)

    fake.async_add_executor_job = AsyncMock(side_effect=_exec)
    return fake


def _make_status(dnd_start="22:30") -> MagicMock:
    status = MagicMock()
    status.dnd = True
    status.off_peak_charging = True
    status.dnd_start = dnd_start
    status.dnd_end = "08:00"
    status.off_peak_charging_start = "01:00"
    status.off_peak_charging_end = "06:00"
    return status


def make_coordinator(hass, *, dnd_start="22:30") -> tuple[MagicMock, MagicMock]:
    device = MagicMock()
    device.name = "Test Vacuum"
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.available = True
    device.device_connected = True
    device.status = _make_status(dnd_start=dnd_start)
    device.capability = MagicMock()
    device.capability.dnd = True
    device.capability.off_peak_charging = True
    device.data = {}
    device.action_mapping = {}
    device.auto_switch_data = {}
    device.ai_data = {}
    device.get_property = MagicMock(return_value=None)
    device.set_property = MagicMock()
    coordinator = MagicMock()
    coordinator.device = device
    coordinator.hass = hass
    return coordinator, device


def get_description(key):
    for desc in TIMES:
        if desc.key == key:
            return desc
    raise AssertionError(f"description not found for {key}")


def build_entity(hass, key="dnd_start", *, dnd_start="22:30"):
    coordinator, device = make_coordinator(hass, dnd_start=dnd_start)
    desc = get_description(key)
    entity = DreameVacuumTimeEntity(coordinator, desc)
    entity.hass = hass
    return entity, device, coordinator


# ---------------------------------------------------------------------------
# construction / native_value parsing
# ---------------------------------------------------------------------------


async def test_construction_unique_id_and_entity_id(hass):
    entity, _device, _coord = build_entity(hass, "dnd_start")
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_dnd_start"
    assert entity.entity_id.startswith("time.")


async def test_native_value_parses_hh_mm(hass):
    entity, _device, _coord = build_entity(hass, "dnd_start", dnd_start="22:30")
    assert entity.native_value == time(22, 30, 0)


async def test_native_value_none_when_empty(hass):
    entity, _device, _coord = build_entity(hass, "dnd_start", dnd_start="")
    assert entity.native_value is None


async def test_native_value_none_when_invalid(hass):
    # A non numeric value triggers the ValueError branch -> None.
    entity, _device, _coord = build_entity(hass, "dnd_start", dnd_start="not-a-time")
    assert entity.native_value is None


async def test_native_value_none_when_missing_minutes(hass):
    # Only an hour part -> IndexError branch -> None.
    entity, _device, _coord = build_entity(hass, "dnd_start", dnd_start="22")
    assert entity.native_value is None


async def test_off_peak_charging_time_parsing(hass):
    entity, _device, _coord = build_entity(hass, "off_peak_charging_start", dnd_start="22:30")
    assert entity.native_value == time(1, 0, 0)


# ---------------------------------------------------------------------------
# _handle_coordinator_update
# ---------------------------------------------------------------------------


async def test_handle_coordinator_update_reparses_value(hass):
    entity, device, _coord = build_entity(hass, "dnd_start", dnd_start="22:30")
    entity.async_write_ha_state = MagicMock()
    device.status.dnd_start = "07:45"
    entity._handle_coordinator_update()
    assert entity.native_value == time(7, 45, 0)
    entity.async_write_ha_state.assert_called_once()


async def test_handle_coordinator_update_invalid_sets_none(hass):
    entity, device, _coord = build_entity(hass, "dnd_start", dnd_start="22:30")
    entity.async_write_ha_state = MagicMock()
    device.status.dnd_start = "bad:value:here:99"
    entity._handle_coordinator_update()
    assert entity.native_value is None


async def test_handle_coordinator_update_empty_sets_none(hass):
    entity, device, _coord = build_entity(hass, "dnd_start", dnd_start="22:30")
    entity.async_write_ha_state = MagicMock()
    device.status.dnd_start = None
    entity._handle_coordinator_update()
    assert entity.native_value is None


async def test_handle_coordinator_update_device_none(hass):
    entity, _device, coordinator = build_entity(hass, "dnd_start")
    entity.async_write_ha_state = MagicMock()
    coordinator.device = None
    entity._handle_coordinator_update()
    entity.async_write_ha_state.assert_called_once()


# ---------------------------------------------------------------------------
# async_set_value success
# ---------------------------------------------------------------------------


async def test_set_value_calls_resolved_setter(hass):
    entity, device, _coord = build_entity(hass, "dnd_start")
    await entity.async_set_value(time(23, 15))
    device.set_dnd_start.assert_called_once_with("23:15")
    device.set_property.assert_not_called()


async def test_set_value_formats_midnight(hass):
    entity, device, _coord = build_entity(hass, "dnd_end")
    await entity.async_set_value(time(0, 0))
    device.set_dnd_end.assert_called_once_with("00:00")


async def test_set_value_off_peak(hass):
    entity, device, _coord = build_entity(hass, "off_peak_charging_end")
    await entity.async_set_value(time(6, 30))
    device.set_off_peak_charging_end.assert_called_once_with("06:30")


# ---------------------------------------------------------------------------
# async_set_value: bare set_property fallback
# ---------------------------------------------------------------------------


def _device_without_setter(hass, property_key):
    device = MagicMock(
        spec=[
            "name",
            "mac",
            "available",
            "device_connected",
            "status",
            "capability",
            "data",
            "action_mapping",
            "auto_switch_data",
            "ai_data",
            "get_property",
            "set_property",
        ]
    )
    device.name = "Test Vacuum"
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.available = True
    device.device_connected = True
    device.status = MagicMock(spec=[])
    device.capability = MagicMock()
    device.capability.dnd = True
    device.data = {}
    device.action_mapping = {}
    device.auto_switch_data = {}
    device.ai_data = {}
    device.get_property = MagicMock(return_value=None)
    device.set_property = MagicMock()
    coordinator = MagicMock()
    coordinator.device = device
    coordinator.hass = hass
    return coordinator, device


def _time_description_with_property(property_key):
    return time_mod.DreameVacuumTimeEntityDescription(
        key="dnd_start",
        name="DnD start",
        property_key=property_key,
    )


async def test_set_value_bare_property_path(hass):
    # No status.dnd_start attr and no set_dnd_start -> set_property("HH:MM").
    from custom_components.dreame_vacuum.dreame import DreameVacuumProperty

    coordinator, device = _device_without_setter(hass, DreameVacuumProperty.DND_START)
    desc = _time_description_with_property(DreameVacuumProperty.DND_START)
    entity = DreameVacuumTimeEntity(coordinator, desc)
    entity.hass = hass
    await entity.async_set_value(time(9, 5))
    device.set_property.assert_called_once_with(DreameVacuumProperty.DND_START, "09:05")


# ---------------------------------------------------------------------------
# async_set_value failures
# ---------------------------------------------------------------------------


async def test_set_value_raises_when_unavailable(hass):
    entity, device, _coord = build_entity(hass, "dnd_start")
    device.device_connected = False
    with pytest.raises(HomeAssistantError):
        await entity.async_set_value(time(10, 0))


async def test_set_value_raises_when_none(hass):
    entity, _device, _coord = build_entity(hass, "dnd_start")
    with pytest.raises(HomeAssistantError):
        await entity.async_set_value(None)


@pytest.mark.parametrize("exc", [InvalidActionException("bad"), InvalidValueException("bad")])
async def test_set_value_command_error_raises(hass, exc):
    entity, device, _coord = build_entity(hass, "dnd_start")
    device.set_dnd_start.side_effect = exc
    with pytest.raises(HomeAssistantError):
        await entity.async_set_value(time(10, 0))


async def test_set_value_device_exception_raises_when_available(hass):
    entity, device, _coord = build_entity(hass, "dnd_start")
    device.available = True
    device.set_dnd_start.side_effect = DeviceException("boom")
    with pytest.raises(HomeAssistantError):
        await entity.async_set_value(time(10, 0))


async def test_set_value_device_exception_swallowed_when_unavailable(hass):
    entity, device, _coord = build_entity(hass, "dnd_start")
    device.available = False
    device.set_dnd_start.side_effect = DeviceUpdateFailedException("offline")
    await entity.async_set_value(time(10, 0))  # must not raise
    device.set_dnd_start.assert_called_once()


async def test_set_value_not_implemented_branch(hass):
    # An entity with neither a resolvable setter nor a property_key must raise
    # the ``not_implemented`` HomeAssistantError.
    coordinator, device = _device_without_setter(hass, None)
    desc = time_mod.DreameVacuumTimeEntityDescription(
        key="dnd_start",
        name="DnD start",
        available_fn=lambda d: True,
    )
    entity = DreameVacuumTimeEntity(coordinator, desc)
    entity.hass = hass
    # No set_dnd_start on the spec-limited device and property_key is None.
    assert entity._computed_set_fn is None
    with pytest.raises(HomeAssistantError):
        await entity.async_set_value(time(10, 0))
    device.set_property.assert_not_called()


# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------


async def test_available_follows_dnd_status(hass):
    entity, device, _coord = build_entity(hass, "dnd_start")
    device.status.dnd = True
    assert entity.available is True
    device.status.dnd = False
    assert entity.available is False


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------


async def test_async_setup_entry_adds_all_when_supported(hass):
    coordinator, _device = make_coordinator(hass)
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    added: list = []
    await async_setup_entry(hass, entry, lambda gen: added.extend(list(gen)))
    assert len(added) == len(TIMES)
    assert all(isinstance(e, DreameVacuumTimeEntity) for e in added)


async def test_async_setup_entry_filters_off_peak(hass):
    coordinator, device = make_coordinator(hass)
    device.capability.off_peak_charging = False
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    added: list = []
    await async_setup_entry(hass, entry, lambda gen: added.extend(list(gen)))
    keys = {e.entity_description.key for e in added}
    assert "off_peak_charging_start" not in keys
    assert "dnd_start" in keys


async def test_async_setup_entry_filters_dnd(hass):
    coordinator, device = make_coordinator(hass)
    device.capability.dnd = False
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    added: list = []
    await async_setup_entry(hass, entry, lambda gen: added.extend(list(gen)))
    keys = {e.entity_description.key for e in added}
    assert "dnd_start" not in keys
    assert "off_peak_charging_start" in keys


def test_times_tuple_non_empty():
    assert len(TIMES) > 0
    assert time_mod.PARALLEL_UPDATES == 1
