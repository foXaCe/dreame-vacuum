"""Unit tests for ``custom_components.dreame_vacuum.number``.

Targets ``DreameVacuumNumberEntity`` (native_value, async_set_native_value success
and failure mapping, min/max/step bounds, available, _handle_coordinator_update),
the module-level ``async_setup_entry`` / segment listener helpers, the segment
number entity, and the ``WETNESS_LEVEL_TO_ICON`` helper.

The HA pytest plugin is disabled in this project (``-p no:homeassistant``), so a
lightweight hass mock is built locally; no shared fixtures are modified.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.dreame_vacuum.dreame import (
    DeviceException,
    DreameVacuumProperty,
    InvalidValueException,
)
from custom_components.dreame_vacuum.entity import DreameVacuumNumberEntityDescription
from custom_components.dreame_vacuum.number import (
    NUMBERS,
    SEGMENT_NUMBERS,
    WETNESS_LEVEL_TO_ICON,
    DreameVacuumNumberEntity,
    DreameVacuumSegmentNumberEntity,
    async_remove_segment_numbers,
    async_setup_entry,
    async_update_segment_numbers,
)

MAC = "AA:BB:CC:DD:EE:FF"


# --------------------------------------------------------------------------- #
# Fixtures / builders                                                          #
# --------------------------------------------------------------------------- #


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.states.async_available = MagicMock(return_value=True)
    hass.config.language = "en"

    async def _run_job(target, *args):
        return target(*args)

    hass.async_add_executor_job = _run_job
    return hass


def _make_device() -> MagicMock:
    device = MagicMock()
    device.name = "Test Vacuum"
    device.mac = MAC
    device.available = True
    device.device_connected = True
    device.status = MagicMock()
    device.status.serial_number = "SN-1"
    device.info = MagicMock()
    device.info.manufacturer = "Dreame"
    device.info.model = "m"
    device.info.firmware_version = "1"
    device.info.hardware_version = "1"
    device.capability = MagicMock()
    device.get_property = MagicMock(return_value=50)
    device.set_property = MagicMock(return_value=True)
    device.set_volume = MagicMock(return_value=True)
    return device


@pytest.fixture
def device() -> MagicMock:
    return _make_device()


@pytest.fixture
def coordinator(device: MagicMock) -> MagicMock:
    coord = MagicMock()
    coord.device = device
    coord.hass = _make_hass()
    coord.last_update_success = True
    coord.async_refresh = AsyncMock()
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    return coord


VOLUME_DESC = NUMBERS[0]  # the VOLUME description


def _number(coordinator, description=VOLUME_DESC) -> DreameVacuumNumberEntity:
    ent = DreameVacuumNumberEntity(coordinator, description)
    ent.hass = coordinator.hass
    return ent


# --------------------------------------------------------------------------- #
# WETNESS_LEVEL_TO_ICON helper                                                 #
# --------------------------------------------------------------------------- #


def test_wetness_icon_none():
    assert WETNESS_LEVEL_TO_ICON(0, 26) == "mdi:water-off"
    assert WETNESS_LEVEL_TO_ICON(None, 26) == "mdi:water-off"


def test_wetness_icon_plus_when_above_max():
    assert WETNESS_LEVEL_TO_ICON(30, 26) == "mdi:water-plus"


def test_wetness_icon_minus_when_low():
    assert WETNESS_LEVEL_TO_ICON(3, 26) == "mdi:water-minus"


def test_wetness_icon_water_mid():
    assert WETNESS_LEVEL_TO_ICON(10, 26) == "mdi:water"


# --------------------------------------------------------------------------- #
# DreameVacuumNumberEntity construction                                        #
# --------------------------------------------------------------------------- #


def test_number_init_basic_attributes(coordinator):
    coordinator.device.status.volume = 40
    ent = _number(coordinator)
    assert ent._attr_unique_id == f"{MAC}_volume"
    assert ent.entity_id.startswith("number.")
    # mode comes from the description (SLIDER for VOLUME).
    assert ent._attr_mode == VOLUME_DESC.mode
    # native_value initialised from super().native_value (status.volume).
    assert ent._attr_native_value == 40
    assert ent.native_value == 40


def test_number_init_static_bounds(coordinator):
    ent = _number(coordinator)
    # VOLUME description: 0..100 step 1.
    assert ent.native_min_value == 0
    assert ent.native_max_value == 100
    assert ent.native_step == 1


def test_number_init_dynamic_bounds_from_fn(coordinator):
    coordinator.device.status.self_clean_area_min = 5
    coordinator.device.status.self_clean_area_max = 35
    # self_clean_area description (index 2) carries min/max_value_fn + value_fn.
    desc = next(d for d in NUMBERS if d.key == "self_clean_area")
    coordinator.device.status.self_clean_value = 20
    coordinator.device.status.current_map = None
    coordinator.device.status.has_saved_map = True
    ent = _number(coordinator, desc)
    assert ent._attr_native_min_value == 5
    assert ent._attr_native_max_value == 35


def test_number_init_set_fn_resolved_from_property(coordinator):
    # VOLUME has no explicit set_fn; the device exposes set_volume -> resolved.
    ent = _number(coordinator)
    assert ent._computed_set_fn is not None


# --------------------------------------------------------------------------- #
# native_value property                                                        #
# --------------------------------------------------------------------------- #


def test_number_native_value_reads_attr(coordinator):
    ent = _number(coordinator)
    ent._attr_native_value = 73
    assert ent.native_value == 73


# --------------------------------------------------------------------------- #
# async_set_native_value                                                       #
# --------------------------------------------------------------------------- #


async def test_set_value_unavailable_raises(coordinator):
    ent = _number(coordinator)
    ent.hass = coordinator.hass
    coordinator.device.device_connected = False  # -> available False
    with pytest.raises(HomeAssistantError) as err:
        await ent.async_set_native_value(10)
    assert err.value.translation_key == "entity_unavailable"


async def test_set_value_via_set_fn_success(coordinator):
    coordinator.device.status.volume = 10
    ent = _number(coordinator)
    ent.hass = coordinator.hass
    ent._attr_available = True
    await ent.async_set_native_value(55.0)
    # value is int()-cast then forwarded to the resolved set_volume.
    coordinator.device.set_volume.assert_called_once_with(55)


async def test_set_value_via_property_when_no_set_fn(coordinator):
    # Use a description with a property but a device lacking set_<prop>; falls back
    # to device.set_property(property_key, value).
    coordinator.device = _make_device()
    del coordinator.device.set_volume  # remove the auto-resolved setter
    coordinator.device.status.volume = 1
    coordinator.hass = _make_hass()
    desc = DreameVacuumNumberEntityDescription(
        property_key=DreameVacuumProperty.VOLUME,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
    )
    ent = DreameVacuumNumberEntity(coordinator, desc)
    ent.hass = coordinator.hass
    ent._attr_available = True
    assert ent._computed_set_fn is None
    await ent.async_set_native_value(30.0)
    coordinator.device.set_property.assert_called_once_with(DreameVacuumProperty.VOLUME, 30)


async def test_set_value_format_fn_applied(coordinator):
    coordinator.device.status.volume = 1
    desc = DreameVacuumNumberEntityDescription(
        property_key=DreameVacuumProperty.VOLUME,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        format_fn=lambda value, device: value * 2,
    )
    # Remove auto-setter so we hit set_property and can inspect the value.
    coordinator.device = _make_device()
    del coordinator.device.set_volume
    coordinator.device.status.volume = 1
    coordinator.hass = _make_hass()
    ent = DreameVacuumNumberEntity(coordinator, desc)
    ent.hass = coordinator.hass
    ent._attr_available = True
    await ent.async_set_native_value(21.0)
    coordinator.device.set_property.assert_called_once_with(DreameVacuumProperty.VOLUME, 42)


async def test_set_value_format_fn_returns_none_raises(coordinator):
    coordinator.device.status.volume = 1
    desc = DreameVacuumNumberEntityDescription(
        property_key=DreameVacuumProperty.VOLUME,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        format_fn=lambda value, device: None,
    )
    ent = DreameVacuumNumberEntity(coordinator, desc)
    ent.hass = coordinator.hass
    ent._attr_available = True
    with pytest.raises(HomeAssistantError) as err:
        await ent.async_set_native_value(5.0)
    assert err.value.translation_key == "invalid_value"


async def test_set_value_command_failure_maps_to_ha_error(coordinator):
    coordinator.device.status.volume = 1
    coordinator.device.set_volume = MagicMock(side_effect=InvalidValueException("nope"))
    ent = _number(coordinator)
    ent.hass = coordinator.hass
    ent._attr_available = True
    with pytest.raises(HomeAssistantError) as err:
        await ent.async_set_native_value(10.0)
    assert "nope" in str(err.value)


async def test_set_value_device_exception_available_raises(coordinator):
    coordinator.device.status.volume = 1
    coordinator.device.available = True
    coordinator.device.set_volume = MagicMock(side_effect=DeviceException("boom"))
    ent = _number(coordinator)
    ent.hass = coordinator.hass
    ent._attr_available = True
    with pytest.raises(HomeAssistantError):
        await ent.async_set_native_value(10.0)


async def test_set_value_no_setter_and_no_property_is_noop(coordinator):
    # A key-only description (no property_key) on a device without set_<key>:
    # _computed_set_fn stays None and there is no property -> method returns silently.
    coordinator.device = _make_device()
    coordinator.hass = _make_hass()

    class Status:
        pass

    coordinator.device.status = Status()
    desc = DreameVacuumNumberEntityDescription(
        key="totally_unmapped_number",
        native_min_value=0,
        native_max_value=10,
        native_step=1,
    )
    ent = DreameVacuumNumberEntity(coordinator, desc)
    ent.hass = coordinator.hass
    ent._attr_available = True
    # Should not raise and should not touch set_property.
    await ent.async_set_native_value(3.0)
    coordinator.device.set_property.assert_not_called()


# --------------------------------------------------------------------------- #
# available                                                                    #
# --------------------------------------------------------------------------- #


def test_number_available_true(coordinator):
    ent = _number(coordinator)
    ent._attr_available = True
    assert ent.available is True


def test_number_available_false_when_disconnected(coordinator):
    ent = _number(coordinator)
    coordinator.device.device_connected = False
    assert ent.available is False


# --------------------------------------------------------------------------- #
# _handle_coordinator_update                                                   #
# --------------------------------------------------------------------------- #


def test_number_handle_update_refreshes_value_and_bounds(coordinator):
    coordinator.device.status.self_clean_area_min = 1
    coordinator.device.status.self_clean_area_max = 30
    coordinator.device.status.self_clean_value = 10
    coordinator.device.status.current_map = None
    coordinator.device.status.has_saved_map = True
    desc = next(d for d in NUMBERS if d.key == "self_clean_area")
    ent = _number(coordinator, desc)
    ent.async_write_ha_state = MagicMock()

    coordinator.device.status.self_clean_area_min = 4
    coordinator.device.status.self_clean_area_max = 44
    coordinator.device.status.self_clean_value = 22
    ent._handle_coordinator_update()

    assert ent._attr_native_min_value == 4
    assert ent._attr_native_max_value == 44
    assert ent._attr_native_value == 22
    ent.async_write_ha_state.assert_called_once()


def test_number_handle_update_device_none(coordinator):
    coordinator.device.status.volume = 5
    ent = _number(coordinator)
    ent.async_write_ha_state = MagicMock()
    coordinator.device = None
    ent._handle_coordinator_update()
    ent.async_write_ha_state.assert_called_once()


# --------------------------------------------------------------------------- #
# async_setup_entry + segment listeners                                        #
# --------------------------------------------------------------------------- #


async def test_async_setup_entry_adds_numbers_and_registers_listener(coordinator):
    # Real capability object so exists_fn results are deterministic; with everything
    # falsy, only property-backed numbers without capability gates are created.
    cap = MagicMock()
    cap.self_wash_base = False
    cap.mop_clean_frequency = False
    cap.self_clean_frequency = False
    cap.camera_streaming = False
    cap.fill_light = False
    cap.wetness_level = False
    coordinator.device.capability = cap
    coordinator.device.data = {p.value: 0 for p in DreameVacuumProperty}
    coordinator.device.action_mapping = {}
    coordinator.device.auto_switch_data = {}
    coordinator.device.ai_data = {}
    coordinator.device.status.map_list = None

    entry = MagicMock()
    entry.runtime_data.coordinator = coordinator
    added = []

    def _add(new_entities):
        # async_add_entities can receive a generator or a list.
        added.extend(list(new_entities))

    await async_setup_entry(coordinator.hass, entry, _add)

    # The listener for segment numbers must be registered.
    coordinator.async_add_listener.assert_called_once()
    # At least the non-gated numbers (e.g. VOLUME, MOP_CLEANING_REMAINDER) created.
    assert any(isinstance(e, DreameVacuumNumberEntity) for e in added)


def test_async_update_segment_numbers_add_and_remove(coordinator):
    # Build a device whose map yields one segment, then remove it on a second pass.
    segment = MagicMock()
    segment.wetness_level = 5
    segment.cleaning_mode = 1
    segment.icon = "mdi:seg"
    segment.get_translated_name = MagicMock(return_value="Kitchen")

    map_data = MagicMock()
    map_data.segments = {3: segment}

    cap = MagicMock()
    cap.wetness_level = True
    coordinator.device.capability = cap
    coordinator.device.status.map_list = [1]
    coordinator.device.status.map_data_list = {0: map_data}
    coordinator.device.status.current_segments = {3: segment}

    current: dict = {}
    added_batches = []
    async_add = MagicMock(side_effect=lambda ents: added_batches.append(list(ents)))

    async_update_segment_numbers(coordinator, current, async_add)
    assert 3 in current
    assert current[3]  # at least one segment number entity
    assert added_batches
    assert added_batches[0]

    # Second pass with no segments -> removal path.
    registry = MagicMock()
    registry.entities = {}
    import custom_components.dreame_vacuum.number as number_mod

    orig_get = number_mod.entity_registry.async_get
    number_mod.entity_registry.async_get = MagicMock(return_value=registry)
    try:
        coordinator.device.status.map_list = None
        async_update_segment_numbers(coordinator, current, async_add)
    finally:
        number_mod.entity_registry.async_get = orig_get
    assert 3 not in current


def test_async_remove_segment_numbers_unregisters(coordinator):
    entity = MagicMock()
    entity.entity_id = "number.room_3_wetness_level"
    current = {3: [entity]}

    registry = MagicMock()
    registry.entities = {"number.room_3_wetness_level": object()}
    import custom_components.dreame_vacuum.number as number_mod

    orig_get = number_mod.entity_registry.async_get
    number_mod.entity_registry.async_get = MagicMock(return_value=registry)
    try:
        async_remove_segment_numbers(3, coordinator, current)
    finally:
        number_mod.entity_registry.async_get = orig_get

    registry.async_remove.assert_called_once_with("number.room_3_wetness_level")
    assert 3 not in current


# --------------------------------------------------------------------------- #
# DreameVacuumSegmentNumberEntity                                              #
# --------------------------------------------------------------------------- #


def _segment_device(coordinator, *, with_segment=True):
    segment = MagicMock()
    segment.wetness_level = 8
    segment.cleaning_mode = 1
    segment.icon = "mdi:seg-icon"
    segment.get_translated_name = MagicMock(return_value="Kitchen")

    cap = MagicMock()
    cap.wetness_level = True
    cap.mop_clean_frequency = False
    coordinator.device.capability = cap
    coordinator.device.status.current_segments = {3: segment} if with_segment else {}
    coordinator.device.status.customized_cleaning = True
    coordinator.device.status.zone_cleaning = False
    coordinator.device.status.spot_cleaning = False
    coordinator.device.status.fast_mapping = False
    coordinator.device.status.scheduled_clean = False
    coordinator.device.status.cruising = False
    coordinator.device.status.cleangenius_cleaning = False
    return segment


SEG_DESC = SEGMENT_NUMBERS[0]


def _segment(coordinator, segment_id=3) -> DreameVacuumSegmentNumberEntity:
    ent = DreameVacuumSegmentNumberEntity(coordinator, SEG_DESC, segment_id)
    ent.hass = coordinator.hass
    return ent


def test_segment_init_with_segment(coordinator):
    _segment_device(coordinator)
    ent = _segment(coordinator, 3)
    assert ent.segment_id == 3
    # The entity deep-copies the segment list; identity differs but the data matches.
    assert ent.segment is not None
    assert ent.segment.wetness_level == 8
    assert ent._attr_unique_id == f"{MAC}_room_3_wetness_level"
    assert ent.entity_id.startswith("number.")
    # value_fn(device, segment) -> segment.wetness_level
    assert ent._attr_native_value == 8
    # native_value returns _attr_native_value when a segment is present.
    assert ent.native_value == 8
    # segment_icon_fn applied.
    assert ent._attr_icon is not None


def test_segment_init_without_segment_uses_off_icon(coordinator):
    _segment_device(coordinator, with_segment=False)
    ent = _segment(coordinator, 99)  # id not in segments
    assert ent.segment is None
    assert ent.native_value is None
    # segment_icon_fn returns the off icon for a missing segment.
    assert ent._attr_icon == "mdi:water-off"


def test_segment_set_id_translation_placeholder_room(coordinator):
    _segment_device(coordinator)
    ent = _segment(coordinator, 3)
    # key != "" -> "<key>_room" translation key with the translated room name.
    assert ent._attr_translation_key.endswith("_room")
    assert ent._attr_translation_placeholders["room"] == "Kitchen"


def test_segment_set_id_unknown_room_when_no_segment(coordinator):
    _segment_device(coordinator, with_segment=False)
    ent = _segment(coordinator, 99)
    assert ent._attr_translation_placeholders["room"] == "?"


def test_segment_set_id_room_name_when_blank_name(coordinator):
    # When the description name is "" the entity uses the generic room_name key.
    segment = _segment_device(coordinator)
    desc = DreameVacuumNumberEntityDescription(
        key=DreameVacuumProperty.WETNESS_LEVEL.name.lower(),
        name="",
        native_min_value=1,
        native_max_value=32,
        native_step=1,
        value_fn=lambda device, seg: seg.wetness_level,
        segment_list_fn=lambda device: device.status.current_segments,
    )
    ent = DreameVacuumSegmentNumberEntity(coordinator, desc, 3)
    ent.hass = coordinator.hass
    assert ent._attr_translation_key == "room_name"
    assert ent._attr_translation_placeholders == {"room_id": "3"}
    # No segment_icon_fn on this description but a segment exists -> uses segment.icon.
    assert ent._attr_icon == segment.icon


def test_segment_available_true(coordinator):
    _segment_device(coordinator)
    ent = _segment(coordinator, 3)
    ent._attr_available = False  # segment_available_fn drives availability
    assert ent.available is True


def test_segment_available_false_when_disconnected(coordinator):
    _segment_device(coordinator)
    ent = _segment(coordinator, 3)
    coordinator.device.device_connected = False
    assert ent.available is False


def test_segment_available_false_when_no_segment(coordinator):
    _segment_device(coordinator, with_segment=False)
    ent = _segment(coordinator, 99)
    ent._attr_available = True
    # segment is None and _attr_available True -> available returns False.
    assert ent.available is False


def test_segment_available_fallback_attr(coordinator):
    _segment_device(coordinator)
    ent = _segment(coordinator, 3)
    # Remove the segment_available_fn so the _attr_available fallback path runs.
    object.__setattr__(ent.entity_description, "segment_available_fn", None)
    ent._attr_available = True
    assert ent.available is True


async def test_segment_set_value_unavailable_raises(coordinator):
    _segment_device(coordinator)
    ent = _segment(coordinator, 3)
    ent.hass = coordinator.hass
    coordinator.device.device_connected = False
    with pytest.raises(HomeAssistantError) as err:
        await ent.async_set_native_value(5)
    assert err.value.translation_key == "entity_unavailable"


async def test_segment_set_value_success(coordinator):
    _segment_device(coordinator)
    coordinator.device.set_segment_wetness_level = MagicMock(return_value=True)
    ent = _segment(coordinator, 3)
    ent.hass = coordinator.hass
    # Make available True via the segment_available_fn (already satisfied).
    await ent.async_set_native_value(7.0)
    coordinator.device.set_segment_wetness_level.assert_called_once_with(3, 7)


def test_segment_handle_update_device_none(coordinator):
    _segment_device(coordinator)
    ent = _segment(coordinator, 3)
    ent.async_write_ha_state = MagicMock()
    coordinator.device = None
    ent._handle_coordinator_update()
    ent.async_write_ha_state.assert_called_once()


def test_segment_handle_update_value_changes(coordinator):
    _segment_device(coordinator)
    ent = _segment(coordinator, 3)
    ent.async_write_ha_state = MagicMock()

    # Change the underlying segment value -> entity picks it up.
    new_segment = MagicMock()
    new_segment.wetness_level = 14
    new_segment.cleaning_mode = 1
    new_segment.icon = "mdi:new"
    new_segment.get_translated_name = MagicMock(return_value="Bath")
    coordinator.device.status.current_segments = {3: new_segment}

    ent._handle_coordinator_update()
    assert ent._attr_native_value == 14
    # Deep-copied -> compare by data, not identity.
    assert ent.segment is not None
    assert ent.segment.wetness_level == 14
    ent.async_write_ha_state.assert_called_once()


def test_segment_handle_update_segment_removed(coordinator):
    _segment_device(coordinator)
    ent = _segment(coordinator, 3)
    ent.async_write_ha_state = MagicMock()

    # Segment disappears -> entity clears its segment reference.
    coordinator.device.status.current_segments = {}
    ent._handle_coordinator_update()
    assert ent.segment is None
    ent.async_write_ha_state.assert_called_once()


def test_segment_native_value_none_without_segment(coordinator):
    _segment_device(coordinator, with_segment=False)
    ent = _segment(coordinator, 99)
    assert ent.native_value is None


# A segment description carrying dynamic bounds and no icon fn, to exercise the
# min/max_value_fn branches in __init__ / _handle_coordinator_update and the
# "no icon fn + no segment" fallback in _set_id.
SEG_DESC_BOUNDS = DreameVacuumNumberEntityDescription(
    key=DreameVacuumProperty.WETNESS_LEVEL.name.lower(),
    native_min_value=1,
    native_max_value=32,
    native_step=1,
    value_fn=lambda device, seg: seg.wetness_level,
    segment_list_fn=lambda device: device.status.current_segments,
    min_value_fn=lambda device: device.status.seg_min,
    max_value_fn=lambda device: device.status.seg_max,
)


def test_segment_init_dynamic_bounds(coordinator):
    _segment_device(coordinator)
    coordinator.device.status.seg_min = 2
    coordinator.device.status.seg_max = 20
    ent = DreameVacuumSegmentNumberEntity(coordinator, SEG_DESC_BOUNDS, 3)
    ent.hass = coordinator.hass
    assert ent._attr_native_min_value == 2
    assert ent._attr_native_max_value == 20


def test_segment_set_id_off_icon_when_no_iconfn_no_segment(coordinator):
    _segment_device(coordinator, with_segment=False)
    coordinator.device.status.seg_min = 1
    coordinator.device.status.seg_max = 32
    # No segment_icon_fn on SEG_DESC_BOUNDS and segment id absent -> home-off icon.
    ent = DreameVacuumSegmentNumberEntity(coordinator, SEG_DESC_BOUNDS, 99)
    ent.hass = coordinator.hass
    assert ent.segment is None
    assert ent._attr_icon == "mdi:home-off-outline"


def test_segment_handle_update_dynamic_bounds_on_change(coordinator):
    _segment_device(coordinator)
    coordinator.device.status.seg_min = 1
    coordinator.device.status.seg_max = 32
    ent = DreameVacuumSegmentNumberEntity(coordinator, SEG_DESC_BOUNDS, 3)
    ent.hass = coordinator.hass
    ent.async_write_ha_state = MagicMock()

    new_segment = MagicMock()
    new_segment.wetness_level = 11
    new_segment.cleaning_mode = 1
    new_segment.icon = "mdi:n"
    new_segment.get_translated_name = MagicMock(return_value="Hall")
    coordinator.device.status.current_segments = {3: new_segment}
    coordinator.device.status.seg_min = 3
    coordinator.device.status.seg_max = 19

    ent._handle_coordinator_update()
    assert ent._attr_native_min_value == 3
    assert ent._attr_native_max_value == 19
    assert ent._attr_native_value == 11
