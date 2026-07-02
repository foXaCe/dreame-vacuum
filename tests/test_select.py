"""Tests for the Dreame Vacuum select platform.

Targets ``custom_components/dreame_vacuum/select.py``:

* ``DreameVacuumSelectEntity`` — option/value resolution via ``<key>_name`` and
  ``<key>_list``, ``async_select_option`` (success / invalid option / unavailable /
  ``value_int_fn`` returning ``None``), ``value_int_fn`` casting and
  ``extra_state_attributes``.
* ``DreameVacuumSegmentSelectEntity`` — per-room option resolution, ``native_value``,
  ``available``/``enabled`` gating, ``extra_state_attributes`` and ``async_select_option``.
* ``DreameVacuumOptionNavigationMixin`` — index navigation including the empty-options
  no-op guard (must not raise ``ZeroDivisionError``).
* ``async_setup_entry`` and ``async_update_segment_selects`` — entity creation including
  the per-segment selects.

The mocks deliberately use a real object for ``device.status`` (not a bare ``MagicMock``)
because the entity wires ``<key>_name`` / ``<key>_list`` / ``set_<key>`` by probing the
status object with ``hasattr`` — a ``MagicMock`` would answer ``True`` to everything and
defeat the resolution logic under test. Availability lambdas in
``PROPERTY_AVAILABILITY`` also read plain booleans off ``status``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import async_test_home_assistant

from custom_components.dreame_vacuum import select as select_mod
from custom_components.dreame_vacuum.dreame import (
    DreameVacuumProperty,
    DreameVacuumSuctionLevel,
)
from custom_components.dreame_vacuum.dreame.const import ATTR_VALUE
from custom_components.dreame_vacuum.entity import DreameVacuumSelectEntityDescription
from custom_components.dreame_vacuum.select import (
    DreameVacuumOptionNavigationMixin,
    DreameVacuumSegmentSelectEntity,
    DreameVacuumSelectEntity,
    async_setup_entry,
    async_update_segment_selects,
)


@pytest.fixture
async def hass():
    """Provide a real HomeAssistant instance.

    ``pyproject.toml`` runs pytest with ``-p no:homeassistant`` which disables the
    plugin-provided ``hass`` fixture, so we build one locally with the same helper
    the plugin uses. This keeps the entity lifecycle (entity-id generation, registry,
    executor jobs) backed by a genuine core instead of a partial mock.
    """
    async with async_test_home_assistant() as hass_obj:
        yield hass_obj
        await hass_obj.async_stop(force=True)


# ---------------------------------------------------------------------------
# Status / device / coordinator fakes
# ---------------------------------------------------------------------------


class FakeStatus:
    """A controllable stand-in for ``device.status``.

    Every attribute accessed by the availability lambdas and by the entity's
    name/list resolution is a plain Python value so the production code sees
    real booleans / lists instead of truthy ``MagicMock`` objects.
    """

    def __init__(self, **overrides):
        # --- suction_level (property based) ---
        self.suction_level = DreameVacuumSuctionLevel.STANDARD
        self.suction_level_name = "standard"
        self.suction_level_list = ["quiet", "standard", "strong", "turbo"]

        # --- water_volume (property based) ---
        self.water_volume = 2
        self.water_volume_name = "medium"
        self.water_volume_list = ["low", "medium", "high"]

        # --- cleaning_mode (property based) ---
        self.cleaning_mode = MagicMock()  # only compared by identity in icon_fn
        self.cleaning_mode_name = "sweeping_and_mopping"
        self.cleaning_mode_list = ["sweeping", "mopping", "sweeping_and_mopping"]

        # --- booleans consulted by PROPERTY_AVAILABILITY lambdas ---
        self.started = False
        self.mopping = False
        self.sweeping = False
        self.mopping_after_sweeping = False
        self.customized_cleaning = False
        self.zone_cleaning = False
        self.spot_cleaning = False
        self.cleangenius_cleaning = False
        self.fast_mapping = False
        self.scheduled_clean = False
        self.cruising = False
        self.max_suction_power = False
        self.returning = False
        self.draining = False
        self.shortcut_task = False
        self.water_tank_or_mop_installed = True
        self.has_saved_map = True
        self.current_map = MagicMock()
        self.multi_map = True

        # --- segment-related state ---
        # current_segments is ``dict[int, Segment] | None`` in production; a
        # non-empty dict is also truthy for the availability lambdas.
        self.current_segments = {}
        self.segments = {}
        self.map_list = []
        self.map_data_list = {}
        self.selected_map = None

        for key, value in overrides.items():
            setattr(self, key, value)

    def segment_order_list(self, segment):
        """Real status exposes this as a method (not a plain ``*_list`` value)."""
        return [1, 2]

    def __getattr__(self, name):
        """Safe defaults for status fields a given test does not pin.

        Returns ``[]`` for ``*_list`` lookups (options resolvers expect an
        iterable) and ``None`` otherwise. Only invoked for attributes not set in
        ``__init__`` / overrides, so pinned values always take precedence.
        """
        if name.endswith("_list"):
            return []
        return None


class FakeCapability:
    """Capability flags defaulting to ``False`` for any unset attribute.

    The platform's ``exists_fn`` lambdas probe a wide range of capability flags;
    a defaulting object keeps unconfigured ones falsy (a ``MagicMock`` would make
    every flag truthy and wrongly enable every entity).
    """

    _DEFAULTS: ClassVar[dict[str, bool]] = {
        "customized_cleaning": True,
        "self_wash_base": False,
        "custom_cleaning_mode": True,
        "map": True,
        "multi_floor_map": True,
        "cleaning_route": False,
        "segment_mopping_settings": True,
        "segment_visibility": True,
        "floor_material": True,
        "floor_direction_cleaning": True,
    }

    def __init__(self, **overrides):
        self.__dict__.update(self._DEFAULTS)
        self.__dict__.update(overrides)

    def __getattr__(self, name):  # only called for unset attributes
        return False


def make_device(status: FakeStatus | None = None, **caps):
    """Build a device whose ``status`` is the controllable :class:`FakeStatus`."""
    device = MagicMock()
    device.name = "Test Vacuum"
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.device_connected = True
    device.available = True
    device.status = status if status is not None else FakeStatus()
    device.capability = FakeCapability(**caps)

    # default_exists_fn probes these containers; keep them real and deterministic.
    device.action_mapping = {}
    device.data = {
        DreameVacuumProperty.SUCTION_LEVEL.value: 1,
        DreameVacuumProperty.WATER_VOLUME.value: 2,
        DreameVacuumProperty.CLEANING_MODE.value: 2,
    }
    device.auto_switch_data = {}
    device.ai_data = {}

    # Setter methods used by the resolved set fns / set_property path.
    device.set_suction_level = MagicMock()
    device.set_water_volume = MagicMock()
    device.set_cleaning_mode = MagicMock()
    device.set_segment_suction_level = MagicMock()
    device.set_segment_water_volume = MagicMock()
    device.set_segment_cleaning_mode = MagicMock()
    device.set_property = MagicMock()
    device.get_property = MagicMock(return_value=7)
    return device


def make_coordinator(hass, device):
    """A coordinator double exposing exactly what the entities read."""
    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.device = device
    coordinator.last_update_success = True
    coordinator.async_add_listener = MagicMock(return_value=lambda: None)
    return coordinator


def suction_description() -> DreameVacuumSelectEntityDescription:
    """The real SUCTION_LEVEL select description from the platform."""
    return next(d for d in select_mod.SELECTS if d.property_key is DreameVacuumProperty.SUCTION_LEVEL)


def _new_entity(coordinator, description, cls=DreameVacuumSelectEntity, **kwargs):
    """Instantiate a select entity and attach hass (as HA would on add)."""
    entity = cls(coordinator, description, **kwargs)
    entity.hass = coordinator.hass
    return entity


# ---------------------------------------------------------------------------
# DreameVacuumOptionNavigationMixin
# ---------------------------------------------------------------------------


class _NavSelect(DreameVacuumOptionNavigationMixin):
    """Minimal mixin host that records selected options."""

    def __init__(self, options, current):
        self._attr_options = options
        self._attr_current_option = current
        self.selected: list[str] = []

    async def async_select_option(self, option: str) -> None:
        self.selected.append(option)
        self._attr_current_option = option


async def test_nav_select_index_wraps_modulo():
    sel = _NavSelect(["a", "b", "c"], "a")
    await sel.async_select_index(4)  # 4 % 3 -> 1
    assert sel.selected == ["b"]


async def test_nav_first_and_last():
    sel = _NavSelect(["a", "b", "c"], "b")
    await sel.async_first()
    await sel.async_last()
    assert sel.selected == ["a", "c"]


async def test_nav_next_previous_cycle_wraps():
    sel = _NavSelect(["a", "b", "c"], "c")
    await sel.async_next(cycle=True)
    assert sel.selected[-1] == "a"

    sel2 = _NavSelect(["a", "b", "c"], "a")
    await sel2.async_previous(cycle=True)
    assert sel2.selected[-1] == "c"


async def test_nav_next_no_cycle_clamps_at_end():
    sel = _NavSelect(["a", "b", "c"], "c")
    await sel.async_next(cycle=False)
    assert sel.selected == []  # already last -> clamp -> no-op


async def test_nav_previous_no_cycle_clamps_at_start():
    sel = _NavSelect(["a", "b", "c"], "a")
    await sel.async_previous(cycle=False)
    assert sel.selected == []  # already first -> clamp -> no-op


async def test_nav_offset_unknown_current_starts_at_zero():
    sel = _NavSelect(["a", "b", "c"], "x")  # current not in options -> index 0
    await sel.async_offset_index(1, cycle=False)
    assert sel.selected[-1] == "b"


async def test_nav_offset_no_cycle_moves_when_index_changes():
    sel = _NavSelect(["a", "b", "c"], "a")
    await sel.async_offset_index(1, cycle=False)
    assert sel.selected == ["b"]


async def test_nav_empty_options_is_noop_select_index():
    """Empty options must be a no-op, never a ZeroDivisionError (regression)."""
    sel = _NavSelect([], None)
    await sel.async_select_index(0)
    await sel.async_first()
    await sel.async_last()
    assert sel.selected == []


async def test_nav_empty_options_is_noop_offset_index():
    """Empty options for offset navigation must also be a no-op (regression)."""
    sel = _NavSelect([], None)
    await sel.async_offset_index(1, cycle=True)
    await sel.async_next(cycle=True)
    await sel.async_previous(cycle=False)
    assert sel.selected == []


# ---------------------------------------------------------------------------
# DreameVacuumSelectEntity
# ---------------------------------------------------------------------------


async def test_select_resolves_name_and_list(hass):
    """current_option comes from ``<key>_name``; options from ``<key>_list``."""
    device = make_device()
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_description())

    assert entity.current_option == "standard"
    assert entity.native_value == "standard"
    assert entity.options == ["quiet", "standard", "strong", "turbo"]


async def test_select_select_option_success_calls_setter(hass):
    """A valid option resolves through value_int_fn and calls set_suction_level."""
    device = make_device()
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_description())

    await entity.async_select_option("turbo")

    device.set_suction_level.assert_called_once_with(DreameVacuumSuctionLevel.TURBO.value)


async def test_select_value_int_fn_casts_to_int(hass):
    """value_int_fn maps the name to the enum int value passed to the setter."""
    device = make_device()
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_description())

    await entity.async_select_option("quiet")
    device.set_suction_level.assert_called_once_with(DreameVacuumSuctionLevel.QUIET.value)


async def test_select_invalid_option_raises(hass):
    device = make_device()
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_description())

    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("nope")
    device.set_suction_level.assert_not_called()


async def test_select_unavailable_raises(hass):
    """When the availability lambda reports False, selecting raises."""
    device = make_device(status=FakeStatus(mopping=True))  # SUCTION_LEVEL avail -> False
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_description())

    assert entity.available is False
    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("turbo")


async def test_select_value_int_fn_none_raises(hass):
    """value_int_fn returning None must raise (invalid option) and not set."""
    device = make_device()
    coordinator = make_coordinator(hass, device)
    description = DreameVacuumSelectEntityDescription(
        key="custom_none",
        options=lambda device, segment: ["a", "b"],
        value_int_fn=lambda value, device: None,
        available_fn=lambda device: True,
    )
    entity = _new_entity(coordinator, description)

    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("a")


async def test_select_set_via_property_key_when_no_setter(hass):
    """With a property_key but no set_<key> method, set_property is used."""
    device = make_device()
    # Remove the resolved setter so the property_key branch is taken.
    del device.set_suction_level
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_description())

    await entity.async_select_option("strong")
    device.set_property.assert_called_once_with(
        DreameVacuumProperty.SUCTION_LEVEL, DreameVacuumSuctionLevel.STRONG.value
    )


async def test_select_extra_state_attributes_value(hass):
    """Property-backed selects expose the raw device value under ATTR_VALUE."""
    device = make_device()
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_description())

    attrs = entity.extra_state_attributes
    assert attrs == {ATTR_VALUE: 7}  # device.get_property stub returns 7


async def test_select_options_from_explicit_callable(hass):
    """An explicit ``options`` callable wins over the ``<key>_list`` resolution."""
    device = make_device()
    coordinator = make_coordinator(hass, device)
    description = DreameVacuumSelectEntityDescription(
        key="auto_empty_frequency",
        options=lambda device, segment: ["1x", "2x", "3x"],
        value_fn=lambda value, device: "2x",
        value_int_fn=lambda value, device: int(value[0]),
        available_fn=lambda device: True,
    )
    entity = _new_entity(coordinator, description)

    assert entity.options == ["1x", "2x", "3x"]
    assert entity.current_option == "2x"

    await entity.async_select_option("3x")  # numeric int cast path


async def test_select_coordinator_update_refreshes_option(hass):
    """_handle_coordinator_update re-reads options and current_option."""
    device = make_device()
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_description())
    entity.async_write_ha_state = MagicMock()

    device.status.suction_level_name = "turbo"
    device.status.suction_level_list = ["quiet", "turbo"]
    entity._handle_coordinator_update()

    assert entity.current_option == "turbo"
    assert entity.options == ["quiet", "turbo"]


async def test_select_attrs_fn_branch(hass):
    """attrs_fn takes precedence for extra_state_attributes when provided."""
    device = make_device()
    coordinator = make_coordinator(hass, device)
    description = DreameVacuumSelectEntityDescription(
        key="selected_map",
        options=lambda device, segment: ["Map A"],
        value_fn=lambda value, device: "Map A",
        attrs_fn=lambda device: {"map_id": 11},
        available_fn=lambda device: True,
    )
    entity = _new_entity(coordinator, description)
    assert entity.extra_state_attributes == {"map_id": 11}


async def test_select_options_resolved_from_key_list(hass):
    """A key-based select (no property_key, no options) resolves ``<key>_list``."""
    device = make_device()
    # The resolver probes status for ``washing_mode_name`` / ``washing_mode_list``.
    device.status.washing_mode_name = "water_saving"
    device.status.washing_mode_list = ["water_saving", "standard", "deep"]
    device.set_washing_mode = MagicMock()
    coordinator = make_coordinator(hass, device)
    description = DreameVacuumSelectEntityDescription(
        key="washing_mode",
        value_int_fn=lambda value, device: ["water_saving", "standard", "deep"].index(value),
        available_fn=lambda device: True,
    )
    entity = _new_entity(coordinator, description)

    # Options come straight from washing_mode_list (line resolving ``<key>_list``).
    assert entity.options == ["water_saving", "standard", "deep"]
    assert entity.current_option == "water_saving"

    await entity.async_select_option("deep")
    device.set_washing_mode.assert_called_once_with(2)


async def test_select_value_int_fn_numeric_string_is_cast_to_int(hass):
    """When value_int_fn yields a numeric string, it is normalised to a plain int."""
    device = make_device()
    coordinator = make_coordinator(hass, device)
    captured: list = []
    description = DreameVacuumSelectEntityDescription(
        key="numeric_select",
        options=lambda device, segment: ["three"],
        value_fn=lambda value, device: "three",
        # Return a numeric *string* -> triggers the int() normalisation branch.
        value_int_fn=lambda value, device: "3",
        set_fn=lambda device, segment_id, value: captured.append(value),
        available_fn=lambda device: True,
    )
    entity = _new_entity(coordinator, description)

    await entity.async_select_option("three")
    # The setter must receive a plain ``int`` (cast happened), not the string.
    assert captured == [3]
    assert type(captured[0]) is int


# ---------------------------------------------------------------------------
# DreameVacuumSegmentSelectEntity
# ---------------------------------------------------------------------------


def fake_segment(**overrides):
    """Lightweight segment exposing only what the lambdas touch."""
    seg = SimpleNamespace(
        segment_id=1,
        index=0,
        type=1,
        name="Kitchen",
        custom_name="Kitchen",
        icon="mdi:home",
        suction_level=DreameVacuumSuctionLevel.STANDARD,
        water_volume=2,
        cleaning_mode=2,
        mop_pad_humidity=2,
        cleaning_times=2,
        order=1,
        floor_material=1,
        floor_material_rotated_direction=0,
        floor_material_direction=0,
        visibility=1,
        custom_mopping_route=1,
        cleaning_route=1,
    )
    seg.get_translated_name = lambda language=None: "Kitchen"
    seg.name_list = lambda segments, language=None: {"Kitchen": 1, "Bedroom": 2}
    for key, value in overrides.items():
        setattr(seg, key, value)
    return seg


def suction_segment_description() -> DreameVacuumSelectEntityDescription:
    return next(d for d in select_mod.SEGMENT_SELECTS if d.key == DreameVacuumProperty.SUCTION_LEVEL.name.lower())


def make_segment_device(segment, **caps):
    """Device whose segment_list_fn returns ``{1: segment}``."""
    status = FakeStatus(
        current_segments={1: segment},
        segments={1: segment},
        customized_cleaning=True,
        zone_cleaning=False,
        spot_cleaning=False,
        fast_mapping=False,
        scheduled_clean=False,
        cruising=False,
        cleangenius_cleaning=False,
        started=False,
        multi_map=True,
    )
    return make_device(status=status, **caps)


async def test_segment_select_resolves_value_and_options(hass):
    """Segment select reads the per-room value_fn and options list."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_segment_description(), cls=DreameVacuumSegmentSelectEntity, segment_id=1)

    assert entity.native_value == "standard"
    # SUCTION_LEVEL segment select resolves options from suction_level_list.
    assert entity.options == ["quiet", "standard", "strong", "turbo"]
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_room_1_suction_level"


async def test_segment_select_option_calls_segment_setter(hass):
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_segment_description(), cls=DreameVacuumSegmentSelectEntity, segment_id=1)

    await entity.async_select_option("strong")
    device.set_segment_suction_level.assert_called_once_with(1, DreameVacuumSuctionLevel.STRONG.value)


async def test_segment_select_unavailable_raises(hass):
    """Disconnected device -> available False -> selecting raises."""
    seg = fake_segment()
    device = make_segment_device(seg)
    device.device_connected = False
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_segment_description(), cls=DreameVacuumSegmentSelectEntity, segment_id=1)

    assert entity.available is False
    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("strong")


async def test_segment_select_value_int_none_raises(hass):
    """A value_int_fn that yields None must raise on the segment entity."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    description = DreameVacuumSelectEntityDescription(
        key="order",
        options=lambda device, segment: ["not_set", "1"],
        segment_available_fn=lambda device, segment: True,
        value_fn=lambda device, segment: "1",
        value_int_fn=lambda value, self: None,
        segment_list_fn=lambda device: device.status.segments,
    )
    entity = _new_entity(coordinator, description, cls=DreameVacuumSegmentSelectEntity, segment_id=1)

    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("1")


async def test_segment_select_available_uses_segment_available_fn(hass):
    """segment_available_fn drives availability when the segment is present."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_segment_description(), cls=DreameVacuumSegmentSelectEntity, segment_id=1)

    assert entity.available is True

    # Flip a gate the lambda checks; availability must follow.
    device.status.customized_cleaning = False
    assert entity.available is False


async def test_segment_select_missing_segment_unavailable(hass):
    """An unknown segment_id leaves segment=None -> not available, options empty."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_segment_description(), cls=DreameVacuumSegmentSelectEntity, segment_id=99)

    assert entity.segment is None
    assert entity.options == []
    assert entity.available is False


async def test_segment_select_extra_state_attributes_value_int(hass):
    """Without attrs_fn/property_key, attributes expose value_int_fn(native_value)."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_segment_description(), cls=DreameVacuumSegmentSelectEntity, segment_id=1)

    attrs = entity.extra_state_attributes
    assert attrs == {ATTR_VALUE: DreameVacuumSuctionLevel.STANDARD.value}


async def test_segment_select_extra_state_attributes_attrs_fn(hass):
    """The room-name select description supplies attrs via attrs_fn(segment)."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    name_desc = next(d for d in select_mod.SEGMENT_SELECTS if d.key == "name")
    entity = _new_entity(coordinator, name_desc, cls=DreameVacuumSegmentSelectEntity, segment_id=1)

    attrs = entity.extra_state_attributes
    assert attrs == {"room_id": 1, "index": 0, "type": 1}


async def test_segment_name_select_native_value_translated(hass):
    """The room-name select returns the translated room name as native_value."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    name_desc = next(d for d in select_mod.SEGMENT_SELECTS if d.key == "name")
    entity = _new_entity(coordinator, name_desc, cls=DreameVacuumSegmentSelectEntity, segment_id=1)

    assert entity.native_value == "Kitchen"
    # The translated name_list path is used for options.
    assert set(entity.options) == {"Kitchen", "Bedroom"}


async def test_segment_select_navigation_empty_options_noop(hass):
    """A segment select with no resolved segment has empty options -> nav no-op."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_segment_description(), cls=DreameVacuumSegmentSelectEntity, segment_id=42)
    entity.async_write_ha_state = MagicMock()

    assert entity.options == []
    # Must not raise ZeroDivisionError.
    await entity.async_first()
    await entity.async_next(cycle=True)
    device.set_segment_suction_level.assert_not_called()


async def test_segment_select_enabled_multi_map_true(hass):
    """enabled is True when the segment exists for the entity."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_segment_description(), cls=DreameVacuumSegmentSelectEntity, segment_id=1)
    entity.registry_entry = None

    assert entity.enabled is True


async def test_segment_select_enabled_false_single_map_missing_segment(hass):
    """Single-map device + missing segment + available attr -> enabled False."""
    seg = fake_segment()
    device = make_segment_device(seg)
    device.status.multi_map = False
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_segment_description(), cls=DreameVacuumSegmentSelectEntity, segment_id=7)
    entity.registry_entry = None
    entity._attr_available = True
    # segments is populated (so truthy) but segment 7 is absent.
    assert entity.segments
    assert 7 not in entity.segments
    assert entity.enabled is False


async def test_segment_select_handle_update_segment_removed(hass):
    """When the segment disappears from the device, options reset and segment clears."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_segment_description(), cls=DreameVacuumSegmentSelectEntity, segment_id=1)
    entity.async_write_ha_state = MagicMock()

    assert entity.segment is not None
    # Segment 1 vanishes from the device (SUCTION_LEVEL reads current_segments).
    device.status.current_segments = {}
    entity._handle_coordinator_update()

    assert entity.segment is None
    assert entity.options == []


async def test_segment_select_handle_update_segment_changed(hass):
    """A changed segment refreshes current_option and options."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_segment_description(), cls=DreameVacuumSegmentSelectEntity, segment_id=1)
    entity.async_write_ha_state = MagicMock()

    new_seg = fake_segment(suction_level=DreameVacuumSuctionLevel.TURBO)
    device.status.current_segments = {1: new_seg}
    entity._handle_coordinator_update()

    assert entity.native_value == "turbo"


async def test_segment_select_handle_update_device_none(hass):
    """If the device is gone, update simply writes state and returns."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    entity = _new_entity(coordinator, suction_segment_description(), cls=DreameVacuumSegmentSelectEntity, segment_id=1)
    entity.async_write_ha_state = MagicMock()

    coordinator.device = None
    entity._handle_coordinator_update()
    entity.async_write_ha_state.assert_called_once()


async def test_segment_select_property_key_resolves_setter_options_and_attrs(hass):
    """A property_key-backed segment select wires set_segment_<prop> / <prop>_list / ATTR_VALUE."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    # property_key with no explicit set_fn/options/value_fn -> resolution kicks in.
    description = DreameVacuumSelectEntityDescription(
        property_key=DreameVacuumProperty.SUCTION_LEVEL,
        value_fn=lambda device, segment: "standard",
        value_int_fn=lambda value, self: DreameVacuumSuctionLevel[value.upper()].value,
        segment_available_fn=lambda device, segment: True,
        segment_list_fn=lambda device: device.status.current_segments,
    )
    entity = _new_entity(coordinator, description, cls=DreameVacuumSegmentSelectEntity, segment_id=1)

    # Options resolved from suction_level_list via the property_key branch.
    assert entity.options == ["quiet", "standard", "strong", "turbo"]

    # extra_state_attributes uses the property_key branch -> raw device value.
    assert entity.extra_state_attributes == {ATTR_VALUE: 7}

    # Selecting resolves set_segment_suction_level via the property_key branch.
    await entity.async_select_option("turbo")
    device.set_segment_suction_level.assert_called_once_with(1, DreameVacuumSuctionLevel.TURBO.value)


async def test_segment_select_value_int_numeric_string_cast(hass):
    """Segment select casts a numeric string returned by value_int_fn to a plain int."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    captured: list = []
    description = DreameVacuumSelectEntityDescription(
        key="cleaning_times",
        value_fn=lambda device, segment: "2x",
        value_int_fn=lambda value, self: "2",  # numeric string -> int() branch
        set_fn=lambda device, segment_id, value: captured.append((segment_id, value)),
        segment_available_fn=lambda device, segment: True,
        segment_list_fn=lambda device: device.status.current_segments,
    )
    entity = _new_entity(coordinator, description, cls=DreameVacuumSegmentSelectEntity, segment_id=1)

    await entity.async_select_option("2x")
    assert captured == [(1, 2)]
    assert type(captured[0][1]) is int


async def test_segment_select_available_falls_back_to_attr_available(hass):
    """With no segment_available_fn, availability is the plain _attr_available."""
    seg = fake_segment()
    device = make_segment_device(seg)
    coordinator = make_coordinator(hass, device)
    description = DreameVacuumSelectEntityDescription(
        key="suction_level",
        value_fn=lambda device, segment: "standard",
        segment_list_fn=lambda device: device.status.current_segments,
    )
    entity = _new_entity(coordinator, description, cls=DreameVacuumSegmentSelectEntity, segment_id=1)
    # segment is present, segment_available_fn is None -> returns _attr_available.
    entity._attr_available = True
    assert entity.available is True
    entity._attr_available = False
    assert entity.available is False


# ---------------------------------------------------------------------------
# async_setup_entry / async_update_segment_selects
# ---------------------------------------------------------------------------


async def test_async_setup_entry_creates_entities(hass):
    """async_setup_entry adds plain selects and wires the segment listener."""
    seg = fake_segment()
    map_obj = SimpleNamespace(segments={1: seg}, map_name="Map A", map_id=1, map_index=0)
    status = FakeStatus(
        map_list=[map_obj],
        map_data_list={1: map_obj},
        segments={1: seg},
        current_segments={1: seg},
    )
    device = make_device(status=status)
    coordinator = make_coordinator(hass, device)

    entry = MagicMock()
    entry.runtime_data.coordinator = coordinator

    added: list = []

    def _add(entities, *args, **kwargs):
        entities = list(entities)
        added.extend(entities)
        for ent in entities:
            ent.hass = hass

    await async_setup_entry(hass, entry, _add)

    # Plain selects were created.
    assert any(isinstance(e, DreameVacuumSelectEntity) for e in added)
    # Per-segment selects were created via the listener.
    assert any(isinstance(e, DreameVacuumSegmentSelectEntity) for e in added)
    # Navigation services are registered from async_setup (tests/test_services.py).
    coordinator.async_add_listener.assert_called_once()


async def test_async_update_segment_selects_add_then_remove(hass):
    """Segment selects are created for new rooms and removed when rooms disappear."""
    seg = fake_segment()
    map_obj = SimpleNamespace(segments={1: seg})
    status = FakeStatus(map_list=[map_obj], map_data_list={1: map_obj}, segments={1: seg})
    device = make_device(status=status)
    coordinator = make_coordinator(hass, device)
    coordinator.hass = hass

    added: list = []

    def _add(entities, *args, **kwargs):
        ents = list(entities)
        for ent in ents:
            ent.hass = hass
        added.extend(ents)

    current: dict[str, list] = {}
    async_update_segment_selects(coordinator, current, _add)

    assert 1 in current
    assert added  # entities created for room 1
    assert all(isinstance(e, DreameVacuumSegmentSelectEntity) for e in added)

    # Register one entity so async_remove_segment_selects exercises the registry path.
    registry = er.async_get(hass)
    entity = current[1][0]
    registry.async_get_or_create(
        "select",
        "dreame_vacuum",
        entity.unique_id,
        suggested_object_id="room_1_suction_level",
    )
    entity.entity_id = registry.async_get_entity_id("select", "dreame_vacuum", entity.unique_id)

    # Now the device reports no maps -> the previously-added room must be removed.
    device.status.map_list = []
    device.status.map_data_list = {}
    async_update_segment_selects(coordinator, current, _add)

    assert 1 not in current
