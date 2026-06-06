"""Tests for the Dreame Vacuum switch platform.

Covers entity construction, ``is_on``/``native_value``, ``async_turn_on`` /
``async_turn_off`` (success and failure -> ``HomeAssistantError``), ``available``,
the resolved per-key/per-property setter, computed ``format_fn`` handling, the
explicit ``set_fn`` switches, the coordinator update callback and
``async_setup_entry`` wiring.

Important: ``device``/``device.status`` are ``MagicMock`` objects, so every
``set_<key>`` method and ``status.<key>`` attribute auto-exists. Therefore the
entity resolves its getter to ``device.status.<key>`` and its setter to
``device.set_<key>``; the tests assert against those (which is what the real code
invokes for these descriptions). The bare ``device.set_property`` fallback is
covered separately with a spec-limited device that lacks the dedicated setter.

Local fixtures only; ``tests/conftest.py`` is not modified.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.dreame_vacuum import switch as switch_mod
from custom_components.dreame_vacuum.dreame import (
    DeviceException,
    DeviceUpdateFailedException,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumProperty,
    InvalidActionException,
    InvalidValueException,
)
from custom_components.dreame_vacuum.switch import (
    SWITCHES,
    DreameVacuumSwitchEntity,
    async_setup_entry,
)


@pytest.fixture
def hass() -> MagicMock:
    """Return a lightweight fake hass.

    The real ``hass`` fixture is unavailable (the suite runs with
    ``-p no:homeassistant``). Only the surface used by the entities is faked:
    ``states.async_available`` for ``async_generate_entity_id`` and an executor
    that runs the callable synchronously for ``_try_command``.
    """
    fake = MagicMock()
    fake.states.async_available = MagicMock(return_value=True)

    async def _exec(func, *args, **kwargs):
        return func(*args, **kwargs)

    fake.async_add_executor_job = AsyncMock(side_effect=_exec)
    return fake


def _segment(order: int = 1) -> SimpleNamespace:
    return SimpleNamespace(order=order)


def _make_status() -> MagicMock:
    """Return a status mock with concrete values for availability/value lambdas."""
    status = MagicMock()
    status.started = False
    status.carpet_recognition = True
    status.carpet_avoidance = False
    status.has_temporary_map = False
    status.has_saved_map = True
    status.current_map = None
    status.cleangenius_cleaning = False
    status.water_tank_or_mop_installed = True
    status.multi_map = True
    status.ai_obstacle_detection = True
    status.ai_pet_detection = True
    status.ai_fluid_detection = True
    status.self_clean = True
    status.self_clean_value = 20
    status.smart_drying = False
    status.mopping = False
    status.fast_mapping = False
    status.scheduled_clean = False
    status.cruising = False
    status.draining = False
    status.self_repairing = False
    status.stream_session = object()
    # Value attributes for switches whose getter resolves to status.<key>
    status.child_lock = 1
    status.carpet_boost = 1
    status.voice_assistant = 1
    status.custom_order = True
    # cleaning_sequence / self_clean_by_zone helpers
    status.previous_cleaning_sequence = [2, 1]
    status.current_segments = {1: _segment(1), 2: _segment(2)}
    status.previous_self_clean_area = 15
    status.camera_light_brightness = 40
    return status


def _make_capability() -> MagicMock:
    """Return a capability mock; relevant flags pinned, rest truthy."""
    capability = MagicMock()
    capability.carpet_recognition = True
    capability.mop_extend = True
    return capability


def make_coordinator(hass) -> tuple[MagicMock, MagicMock]:
    """Build a coordinator + device mock."""
    device = MagicMock()
    device.name = "Test Vacuum"
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.available = True
    device.device_connected = True
    device.status = _make_status()
    device.capability = _make_capability()
    device.data = {p.value: 0 for p in DreameVacuumProperty}
    device.action_mapping = {}
    device.auto_switch_data = {p.name: 0 for p in DreameVacuumAutoSwitchProperty}
    device.ai_data = {}
    device.get_property = MagicMock(return_value=1)
    device.set_property = MagicMock()

    coordinator = MagicMock()
    coordinator.device = device
    coordinator.hass = hass
    return coordinator, device


def get_description(*, property_key=None, key=None):
    """Return the switch description matching a property_key or a key."""
    for desc in SWITCHES:
        if property_key is not None and getattr(desc, "property_key", None) == property_key:
            return desc
        if key is not None and desc.key == key:
            return desc
    raise AssertionError(f"description not found for {property_key or key}")


def build_entity(hass, *, property_key=None, key=None):
    """Instantiate a switch entity with hass attached."""
    coordinator, device = make_coordinator(hass)
    desc = get_description(property_key=property_key, key=key)
    entity = DreameVacuumSwitchEntity(coordinator, desc)
    entity.hass = hass
    return entity, device, coordinator


# ---------------------------------------------------------------------------
# Construction / native_value / is_on
# ---------------------------------------------------------------------------


async def test_construction_sets_unique_id_and_entity_id(hass):
    entity, _device, _coord = build_entity(hass, property_key=DreameVacuumProperty.CHILD_LOCK)
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_child_lock"
    assert entity.entity_id.startswith("switch.")
    assert entity.entity_description.property_key is DreameVacuumProperty.CHILD_LOCK


async def test_is_on_true_when_status_truthy(hass):
    coordinator, device = make_coordinator(hass)
    device.status.child_lock = 1
    desc = get_description(property_key=DreameVacuumProperty.CHILD_LOCK)
    entity = DreameVacuumSwitchEntity(coordinator, desc)
    entity.hass = hass
    assert entity.native_value == 1
    assert entity.is_on is True


async def test_is_on_false_when_status_zero(hass):
    coordinator, device = make_coordinator(hass)
    device.status.child_lock = 0
    desc = get_description(property_key=DreameVacuumProperty.CHILD_LOCK)
    entity = DreameVacuumSwitchEntity(coordinator, desc)
    entity.hass = hass
    assert entity.is_on is False


async def test_is_on_none_when_status_none(hass):
    coordinator, device = make_coordinator(hass)
    device.status.child_lock = None
    desc = get_description(property_key=DreameVacuumProperty.CHILD_LOCK)
    entity = DreameVacuumSwitchEntity(coordinator, desc)
    entity.hass = hass
    assert entity.is_on is None


async def test_explicit_value_fn_resume_cleaning(hass):
    # RESUME_CLEANING uses value_fn=lambda value, device: bool(value);
    # value comes from get_property(property_key).
    coordinator, device = make_coordinator(hass)
    device.get_property.return_value = 5
    desc = get_description(property_key=DreameVacuumProperty.RESUME_CLEANING)
    entity = DreameVacuumSwitchEntity(coordinator, desc)
    entity.hass = hass
    assert entity.native_value is True
    assert entity.is_on is True


async def test_explicit_value_fn_self_clean_by_zone(hass):
    # value_fn=lambda value, device: bool(not device.status.self_clean_value)
    coordinator, device = make_coordinator(hass)
    device.status.self_clean_value = 0
    desc = get_description(key="self_clean_by_zone")
    entity = DreameVacuumSwitchEntity(coordinator, desc)
    entity.hass = hass
    assert entity.native_value is True  # not 0 -> True


# ---------------------------------------------------------------------------
# available
# ---------------------------------------------------------------------------


async def test_available_true_simple(hass):
    # CHILD_LOCK has no availability lambda -> _attr_available default True.
    entity, _device, _coord = build_entity(hass, property_key=DreameVacuumProperty.CHILD_LOCK)
    assert entity.available is True


async def test_available_false_when_disconnected(hass):
    entity, device, _coord = build_entity(hass, property_key=DreameVacuumProperty.CHILD_LOCK)
    device.device_connected = False
    assert entity.available is False


async def test_available_false_when_device_none(hass):
    entity, _device, coordinator = build_entity(hass, property_key=DreameVacuumProperty.CHILD_LOCK)
    coordinator.device = None
    assert entity.available is False


async def test_available_uses_availability_lambda(hass):
    # CARPET_BOOST availability lambda toggled via status.carpet_recognition.
    entity, device, _coord = build_entity(hass, property_key=DreameVacuumProperty.CARPET_BOOST)
    device.capability.carpet_recognition = True
    device.status.carpet_recognition = True
    device.status.carpet_avoidance = False
    assert entity.available is True
    device.status.carpet_recognition = False
    assert entity.available is False


async def test_available_explicit_available_fn(hass):
    # CLEAN_CARPETS_FIRST has an explicit availability lambda in PROPERTY_AVAILABILITY.
    entity, device, _coord = build_entity(hass, property_key=DreameVacuumProperty.CLEAN_CARPETS_FIRST)
    device.status.carpet_recognition = True
    device.status.carpet_avoidance = False
    assert entity.available is True
    device.status.carpet_avoidance = True
    assert entity.available is False


# ---------------------------------------------------------------------------
# async_turn_on / async_turn_off (success path -> resolved set_<key>)
# ---------------------------------------------------------------------------


async def test_turn_on_calls_resolved_setter(hass):
    entity, device, _coord = build_entity(hass, property_key=DreameVacuumProperty.CHILD_LOCK)
    await entity.async_turn_on()
    device.set_child_lock.assert_called_once_with(1)
    device.set_property.assert_not_called()


async def test_turn_off_calls_resolved_setter(hass):
    entity, device, _coord = build_entity(hass, property_key=DreameVacuumProperty.CHILD_LOCK)
    await entity.async_turn_off()
    device.set_child_lock.assert_called_once_with(0)


async def test_format_fn_applied_on_set(hass):
    # VOICE_ASSISTANT format_fn=int(value); turn_on -> int(1) == 1.
    entity, device, _coord = build_entity(hass, property_key=DreameVacuumProperty.VOICE_ASSISTANT)
    await entity.async_turn_on()
    device.set_voice_assistant.assert_called_once_with(1)


async def test_format_fn_stain_avoidance_maps_to_two(hass):
    # STAIN_AVOIDANCE format_fn = 2 if value else 1.
    entity, device, _coord = build_entity(hass, property_key=DreameVacuumAutoSwitchProperty.STAIN_AVOIDANCE)
    await entity.async_turn_on()
    device.set_stain_avoidance.assert_called_once_with(2)
    device.set_stain_avoidance.reset_mock()
    await entity.async_turn_off()
    device.set_stain_avoidance.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# explicit set_fn switches (cleaning_sequence / self_clean_by_zone)
# ---------------------------------------------------------------------------


async def test_explicit_set_fn_cleaning_sequence_on(hass):
    entity, device, _coord = build_entity(hass, key="cleaning_sequence")
    await entity.async_turn_on()
    device.set_cleaning_sequence.assert_called_once_with([2, 1])


async def test_explicit_set_fn_cleaning_sequence_on_sorted_fallback(hass):
    # No previous sequence -> sorted(current_segments.keys()).
    coordinator, device = make_coordinator(hass)
    device.status.previous_cleaning_sequence = None
    desc = get_description(key="cleaning_sequence")
    entity = DreameVacuumSwitchEntity(coordinator, desc)
    entity.hass = hass
    await entity.async_turn_on()
    device.set_cleaning_sequence.assert_called_once_with([1, 2])


async def test_explicit_set_fn_cleaning_sequence_off(hass):
    entity, device, _coord = build_entity(hass, key="cleaning_sequence")
    await entity.async_turn_off()
    device.set_cleaning_sequence.assert_called_once_with([])


async def test_explicit_set_fn_self_clean_by_zone_off(hass):
    # turn_off -> state 0 -> format_fn returns previous_self_clean_area (15).
    entity, device, _coord = build_entity(hass, key="self_clean_by_zone")
    await entity.async_turn_off()
    device.set_self_clean_value.assert_called_once_with(15)


async def test_explicit_set_fn_self_clean_by_zone_on(hass):
    # turn_on -> state 1 -> format_fn returns 0.
    entity, device, _coord = build_entity(hass, key="self_clean_by_zone")
    await entity.async_turn_on()
    device.set_self_clean_value.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# bare set_property fallback (device lacks a dedicated setter)
# ---------------------------------------------------------------------------


def _device_without_setter(hass):
    """A device whose only callables are get_property/set_property (spec-limited)."""
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
    device.status = MagicMock(spec=[])  # no status.<key> attributes
    device.capability = _make_capability()
    device.data = {p.value: 0 for p in DreameVacuumProperty}
    device.action_mapping = {}
    device.auto_switch_data = {}
    device.ai_data = {}
    device.get_property = MagicMock(return_value=1)
    device.set_property = MagicMock()
    coordinator = MagicMock()
    coordinator.device = device
    coordinator.hass = hass
    return coordinator, device


async def test_bare_set_property_path(hass):
    # status has no child_lock attr and device has no set_child_lock -> both the
    # value getter and the setter fall back to property-based access.
    coordinator, device = _device_without_setter(hass)
    desc = get_description(property_key=DreameVacuumProperty.CHILD_LOCK)
    entity = DreameVacuumSwitchEntity(coordinator, desc)
    entity.hass = hass
    await entity.async_turn_on()
    device.set_property.assert_called_once_with(DreameVacuumProperty.CHILD_LOCK, 1)


async def test_bare_set_property_failure_raises(hass):
    coordinator, device = _device_without_setter(hass)
    device.set_property.side_effect = InvalidValueException("bad")
    desc = get_description(property_key=DreameVacuumProperty.CHILD_LOCK)
    entity = DreameVacuumSwitchEntity(coordinator, desc)
    entity.hass = hass
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()


# ---------------------------------------------------------------------------
# async_set_state failures
# ---------------------------------------------------------------------------


async def test_turn_on_raises_when_unavailable(hass):
    entity, device, _coord = build_entity(hass, property_key=DreameVacuumProperty.CHILD_LOCK)
    device.device_connected = False
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()


class _AlwaysAvailableSwitch(DreameVacuumSwitchEntity):
    """Switch whose ``available`` is forced True to exercise ``_try_command`` guards."""

    @property
    def available(self) -> bool:  # type: ignore[override]
        return True


async def test_try_command_guard_raises_when_device_not_connected(hass):
    coordinator, device = make_coordinator(hass)
    desc = get_description(property_key=DreameVacuumProperty.CHILD_LOCK)
    entity = _AlwaysAvailableSwitch(coordinator, desc)
    entity.hass = hass
    device.device_connected = False
    with pytest.raises(HomeAssistantError):
        await entity.async_set_state(1)
    device.set_child_lock.assert_not_called()


@pytest.mark.parametrize("exc", [InvalidActionException("bad"), InvalidValueException("bad")])
async def test_set_state_invalid_exception_becomes_ha_error(hass, exc):
    entity, device, _coord = build_entity(hass, property_key=DreameVacuumProperty.CHILD_LOCK)
    device.set_child_lock.side_effect = exc
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()


async def test_set_state_device_exception_raises_when_available(hass):
    entity, device, _coord = build_entity(hass, property_key=DreameVacuumProperty.CHILD_LOCK)
    device.available = True
    device.set_child_lock.side_effect = DeviceException("boom")
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()


async def test_set_state_device_exception_swallowed_when_unavailable(hass):
    # When the device became unavailable, the DeviceException is swallowed.
    entity, device, _coord = build_entity(hass, property_key=DreameVacuumProperty.CHILD_LOCK)
    device.available = False
    device.set_child_lock.side_effect = DeviceUpdateFailedException("offline")
    await entity.async_turn_on()  # must not raise
    device.set_child_lock.assert_called_once()


# ---------------------------------------------------------------------------
# coordinator update callback
# ---------------------------------------------------------------------------


async def test_handle_coordinator_update_recomputes_is_on(hass):
    entity, device, _coord = build_entity(hass, property_key=DreameVacuumProperty.CHILD_LOCK)
    entity.async_write_ha_state = MagicMock()
    device.status.child_lock = 0
    entity._handle_coordinator_update()
    assert entity.is_on is False
    device.status.child_lock = 1
    entity._handle_coordinator_update()
    assert entity.is_on is True
    entity.async_write_ha_state.assert_called()


async def test_handle_coordinator_update_device_none(hass):
    entity, _device, coordinator = build_entity(hass, property_key=DreameVacuumProperty.CHILD_LOCK)
    entity.async_write_ha_state = MagicMock()
    coordinator.device = None
    entity._handle_coordinator_update()
    entity.async_write_ha_state.assert_called_once()


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------


async def test_async_setup_entry_adds_entities(hass):
    coordinator, _device = make_coordinator(hass)
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    added: list = []
    await async_setup_entry(hass, entry, lambda gen: added.extend(list(gen)))
    assert len(added) > 0
    assert all(isinstance(e, DreameVacuumSwitchEntity) for e in added)


async def test_async_setup_entry_respects_exists_fn(hass):
    # OFF_PEAK_CHARGING only exists when capability.off_peak_charging is set.
    coordinator, device = make_coordinator(hass)
    device.capability.off_peak_charging = False
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    added: list = []
    await async_setup_entry(hass, entry, lambda gen: added.extend(list(gen)))
    prop_keys = {getattr(e.entity_description, "property_key", None) for e in added}
    assert DreameVacuumProperty.OFF_PEAK_CHARGING not in prop_keys


def test_switches_tuple_is_non_empty():
    assert len(SWITCHES) > 0
    assert switch_mod.PARALLEL_UPDATES == 1
