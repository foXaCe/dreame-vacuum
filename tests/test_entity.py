"""Unit tests for ``custom_components.dreame_vacuum.entity``.

Targets the base ``DreameVacuumEntity`` (availability, device_info, native_value,
extra_state_attributes incl. the value_int_fn try/except guard, _try_command error
mapping, _handle_coordinator_update and _set_id) plus the description helpers
(default_exists_fn and the set/value/segment resolvers).

No source files are modified; these are local, self-contained fixtures.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.entity import UNDEFINED
import pytest

from custom_components.dreame_vacuum.const import DOMAIN
from custom_components.dreame_vacuum.dreame import (
    DeviceException,
    DeviceUpdateFailedException,
    DreameVacuumAction,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumProperty,
    DreameVacuumStrAIProperty,
    InvalidActionException,
    InvalidValueException,
)
from custom_components.dreame_vacuum.dreame.const import ATTR_VALUE
from custom_components.dreame_vacuum.entity import (
    DreameVacuumEntity,
    DreameVacuumEntityDescription,
    DreameVacuumNumberEntityDescription,
    default_exists_fn,
)

MAC = "AA:BB:CC:DD:EE:FF"


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


def _make_device() -> MagicMock:
    """Build a rich mock device.

    ``status`` is a plain MagicMock so ``hasattr(device.status, <anything>)`` is
    True; this drives the auto-resolution of value/set functions in the base class.
    """
    device = MagicMock()
    device.name = "Test Vacuum"
    device.mac = MAC
    device.available = True
    device.device_connected = True

    device.status = MagicMock()
    device.status.serial_number = "SN-123"

    # ``info`` populated by default; tests that need it absent set it to None.
    device.info = MagicMock()
    device.info.manufacturer = "Dreame"
    device.info.model = "dreame.vacuum.test"
    device.info.firmware_version = "1.2.3"
    device.info.hardware_version = "hw-1"

    device.capability = MagicMock()

    device.get_property = MagicMock(return_value=42)
    device.set_property = MagicMock(return_value=True)
    return device


def _make_hass() -> MagicMock:
    """Minimal hass mock.

    The HA pytest plugin is disabled in this project (``-p no:homeassistant``),
    so there is no ``hass`` fixture. ``async_generate_entity_id`` only needs
    ``hass.states.async_available`` to return a truthy value (loop exits on the
    first try) and ``hass.config.language`` for translated segment names.
    """
    hass = MagicMock()
    hass.states.async_available = MagicMock(return_value=True)
    hass.config.language = "en"

    async def _run_job(target, *args):
        # Mirror hass.async_add_executor_job: run the (already-bound) callable and
        # surface any exception it raises so _try_command can map it.
        return target(*args)

    hass.async_add_executor_job = _run_job
    return hass


@pytest.fixture
def device() -> MagicMock:
    return _make_device()


@pytest.fixture
def coordinator(device: MagicMock) -> MagicMock:
    """Coordinator mock backed by a lightweight hass mock."""
    coord = MagicMock()
    coord.device = device
    coord.hass = _make_hass()
    coord.last_update_success = True
    coord.async_refresh = AsyncMock()
    # CoordinatorEntity.__init__ registers a listener -> needs a real callable.
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    return coord


def _entity(coordinator: MagicMock, description: DreameVacuumEntityDescription) -> DreameVacuumEntity:
    ent = DreameVacuumEntity(coordinator, description)
    ent.hass = coordinator.hass
    return ent


# --------------------------------------------------------------------------- #
# default_exists_fn                                                            #
# --------------------------------------------------------------------------- #


def test_default_exists_fn_property_key_none_is_true():
    desc = MagicMock(action_key=None, property_key=None)
    assert default_exists_fn(desc, MagicMock()) is True


def test_default_exists_fn_action_key_in_mapping():
    device = MagicMock()
    device.action_mapping = {DreameVacuumAction.START: object()}
    desc = MagicMock(action_key=DreameVacuumAction.START, property_key=object())
    assert default_exists_fn(desc, device) is True


def test_default_exists_fn_property_in_data():
    device = MagicMock()
    device.action_mapping = {}
    device.data = {DreameVacuumProperty.VOLUME.value: 10}
    desc = MagicMock(action_key=None, property_key=DreameVacuumProperty.VOLUME)
    assert default_exists_fn(desc, device) is True


def test_default_exists_fn_autoswitch_in_data():
    prop = next(iter(DreameVacuumAutoSwitchProperty))
    device = MagicMock()
    device.action_mapping = {}
    device.data = {}
    device.auto_switch_data = {prop.name: 1}
    desc = MagicMock(action_key=None, property_key=prop)
    assert default_exists_fn(desc, device) is True


def test_default_exists_fn_ai_property_in_data():
    prop = next(iter(DreameVacuumStrAIProperty))
    device = MagicMock()
    device.action_mapping = {}
    device.data = {}
    device.auto_switch_data = {}
    device.ai_data = {prop.name: 1}
    desc = MagicMock(action_key=None, property_key=prop)
    assert default_exists_fn(desc, device) is True


def test_default_exists_fn_false_when_nothing_matches():
    device = MagicMock()
    device.action_mapping = {}
    device.data = {}
    device.auto_switch_data = {}
    device.ai_data = {}
    # A property absent from data with everything else empty -> not exists.
    desc = MagicMock(action_key=None, property_key=DreameVacuumProperty.VOLUME)
    # VOLUME.value not in empty data dict.
    assert default_exists_fn(desc, device) is False


# --------------------------------------------------------------------------- #
# __init__: key / name / value_fn / available_fn computation                  #
# --------------------------------------------------------------------------- #


def test_init_none_description_sets_no_entity_description(coordinator):
    ent = DreameVacuumEntity(coordinator, None)
    # entity_description attribute is never assigned when description is None.
    assert not hasattr(ent, "entity_description")


def test_init_key_from_property_to_name_mapping(coordinator):
    # VOLUME has a PROPERTY_TO_NAME entry -> key "volume", translation key set.
    ent = _entity(coordinator, DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME))
    assert ent._computed_key == "volume"
    assert ent._attr_translation_key == "volume"
    assert ent._attr_unique_id == f"{MAC}_volume"


def test_init_explicit_key_used_verbatim(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="self_clean_area"))
    assert ent._computed_key == "self_clean_area"


def test_init_name_capitalised_from_key(coordinator):
    # No PROPERTY_TO_NAME entry and name UNDEFINED -> name derived from key.
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="my_thing", name=UNDEFINED))
    assert ent._computed_name == "My thing"


def test_init_explicit_name_sets_key_from_name(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(name="Cool Thing"))
    assert ent._computed_name == "Cool Thing"
    assert ent._computed_key == "cool_thing"


def test_init_action_key_lower_when_no_mapping(coordinator):
    # Pick an action that is not present in ACTION_TO_NAME so the lower() branch runs.
    from custom_components.dreame_vacuum.dreame import ACTION_TO_NAME

    action = next(a for a in DreameVacuumAction if a not in ACTION_TO_NAME)
    ent = _entity(coordinator, DreameVacuumEntityDescription(action_key=action))
    assert ent._computed_key == action.name.lower()


def test_init_value_fn_resolved_from_status_attribute(coordinator):
    # property VOLUME -> _computed_value_fn returns device.status.volume.
    coordinator.device.status.volume = 77
    ent = _entity(coordinator, DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME))
    assert ent._computed_value_fn is not None
    assert ent._computed_value_fn(None, coordinator.device) == 77


def test_init_explicit_value_fn_preserved(coordinator):
    def fn(value, dev):
        return "explicit"

    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x", value_fn=fn))
    assert ent._computed_value_fn is fn


def test_init_value_fn_none_when_status_missing_attribute(coordinator):
    # Use a real object for status without the attribute so hasattr is False.
    class Status:
        pass

    coordinator.device.status = Status()
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="does_not_exist"))
    assert ent._computed_value_fn is None


def test_init_available_fn_from_property_availability(coordinator):
    # WETNESS_LEVEL is present in PROPERTY_AVAILABILITY.
    ent = _entity(coordinator, DreameVacuumEntityDescription(property_key=DreameVacuumProperty.WETNESS_LEVEL))
    assert ent._computed_available_fn is not None


def test_init_available_fn_none_for_property_without_availability(coordinator):
    # VOLUME is NOT in PROPERTY_AVAILABILITY.
    ent = _entity(coordinator, DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME))
    assert ent._computed_available_fn is None


def test_init_available_fn_from_action_availability(coordinator):
    from custom_components.dreame_vacuum.dreame import ACTION_AVAILABILITY

    name = next(iter(ACTION_AVAILABILITY))
    action = next(a for a in DreameVacuumAction if a.name == name)
    ent = _entity(coordinator, DreameVacuumEntityDescription(action_key=action))
    assert ent._computed_available_fn is ACTION_AVAILABILITY[name]


def test_init_available_fn_from_computed_key_property(coordinator):
    from custom_components.dreame_vacuum.dreame import PROPERTY_AVAILABILITY

    # Use a key that matches a PROPERTY_AVAILABILITY entry but pass it as a plain key.
    key = DreameVacuumProperty.WETNESS_LEVEL.name  # availability keyed by .name
    ent = _entity(coordinator, DreameVacuumEntityDescription(key=key))
    assert ent._computed_available_fn is PROPERTY_AVAILABILITY[key]


def test_init_available_fn_from_computed_key_action(coordinator):
    from custom_components.dreame_vacuum.dreame import ACTION_AVAILABILITY, PROPERTY_AVAILABILITY

    key = next(k for k in ACTION_AVAILABILITY if k not in PROPERTY_AVAILABILITY)
    ent = _entity(coordinator, DreameVacuumEntityDescription(key=key))
    assert ent._computed_available_fn is ACTION_AVAILABILITY[key]


def test_init_explicit_available_fn_preserved(coordinator):
    def fn(dev):
        return True

    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x", available_fn=fn))
    assert ent._computed_available_fn is fn


# --------------------------------------------------------------------------- #
# _set_id                                                                      #
# --------------------------------------------------------------------------- #


def test_set_id_icon_fn(coordinator):
    coordinator.device.status.volume = 5
    ent = _entity(
        coordinator,
        DreameVacuumEntityDescription(
            property_key=DreameVacuumProperty.VOLUME,
            icon_fn=lambda value, device: f"mdi:icon-{value}",
        ),
    )
    assert ent._attr_icon == "mdi:icon-5"


def test_set_id_static_icon(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x", icon="mdi:static"))
    assert ent._attr_icon == "mdi:static"


def test_set_id_native_unit_of_measurement_absent(coordinator):
    ent = _entity(
        coordinator,
        DreameVacuumEntityDescription(key="x", icon="mdi:y"),
    )
    # Base EntityDescription has no native_unit_of_measurement -> not set.
    assert not hasattr(ent, "_attr_native_unit_of_measurement")


def test_set_id_native_unit_of_measurement_applied(coordinator):
    # A NumberEntityDescription DOES carry native_unit_of_measurement; when set it
    # is copied onto the entity by _set_id.
    ent = _entity(
        coordinator,
        DreameVacuumNumberEntityDescription(key="x", native_unit_of_measurement="%"),
    )
    assert ent._attr_native_unit_of_measurement == "%"


def test_set_id_name_fn_sets_attr_name(coordinator):
    coordinator.device.status.volume = 9
    ent = _entity(
        coordinator,
        DreameVacuumEntityDescription(
            property_key=DreameVacuumProperty.VOLUME,
            name_fn=lambda value, device: f"Name {value}",
        ),
    )
    assert ent._attr_name == "Name 9"


def test_set_id_noop_without_entity_description(coordinator):
    ent = DreameVacuumEntity(coordinator, None)
    # entity_description not set; manually exercising _set_id must be guarded.
    ent.entity_description = None
    ent._set_id()  # must not raise


# --------------------------------------------------------------------------- #
# device_info                                                                 #
# --------------------------------------------------------------------------- #


def test_device_info_none_when_no_mac(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    coordinator.device.mac = ""
    assert ent.device_info is None


def test_device_info_full_with_info(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    info = ent.device_info
    assert info is not None
    assert (CONNECTION_NETWORK_MAC, MAC) in info["connections"]
    assert (DOMAIN, MAC) in info["identifiers"]
    assert info["name"] == "Test Vacuum"
    assert info["serial_number"] == "SN-123"
    assert info["manufacturer"] == "Dreame"
    assert info["model"] == "dreame.vacuum.test"
    assert info["sw_version"] == "1.2.3"
    assert info["hw_version"] == "hw-1"


def test_device_info_without_info_block(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    coordinator.device.info = None
    info = ent.device_info
    assert info is not None
    assert "manufacturer" not in info
    assert "model" not in info


def test_device_info_serial_none_when_no_status(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    coordinator.device.status = None
    info = ent.device_info
    assert info is not None
    assert info["serial_number"] is None


# --------------------------------------------------------------------------- #
# available                                                                   #
# --------------------------------------------------------------------------- #


def test_available_false_when_device_none(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    coordinator.device = None
    assert ent.available is False


def test_available_false_when_not_connected(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    coordinator.device.device_connected = False
    assert ent.available is False


def test_available_uses_computed_available_fn(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x", available_fn=lambda dev: False))
    assert ent.available is False
    ent2 = _entity(coordinator, DreameVacuumEntityDescription(key="y", available_fn=lambda dev: True))
    assert ent2.available is True


def test_available_falls_back_to_attr_available(coordinator):
    # VOLUME has no availability fn -> _attr_available is used.
    ent = _entity(coordinator, DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME))
    ent._attr_available = True
    assert ent.available is True
    ent._attr_available = False
    assert ent.available is False


# --------------------------------------------------------------------------- #
# native_value                                                                #
# --------------------------------------------------------------------------- #


def test_native_value_via_computed_value_fn(coordinator):
    coordinator.device.status.volume = 33
    ent = _entity(coordinator, DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME))
    assert ent.native_value == 33


def test_native_value_property_only_no_value_fn(coordinator):
    # property_key set, but status has no matching attribute -> value_fn is None and
    # native_value returns the raw get_property result.
    class Status:
        pass

    coordinator.device.status = Status()
    coordinator.device.get_property = MagicMock(return_value=99)
    ent = _entity(coordinator, DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME))
    assert ent._computed_value_fn is None
    assert ent.native_value == 99
    coordinator.device.get_property.assert_called_with(DreameVacuumProperty.VOLUME)


def test_native_value_none_when_no_property_no_value_fn(coordinator):
    class Status:
        pass

    coordinator.device.status = Status()
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="absent_key"))
    assert ent.native_value is None


# --------------------------------------------------------------------------- #
# extra_state_attributes                                                       #
# --------------------------------------------------------------------------- #


def test_extra_state_attributes_attrs_fn(coordinator):
    ent = _entity(
        coordinator,
        DreameVacuumEntityDescription(key="x", attrs_fn=lambda device: {"foo": "bar"}),
    )
    assert ent.extra_state_attributes == {"foo": "bar"}


def test_extra_state_attributes_value_fn_with_property(coordinator):
    coordinator.device.get_property = MagicMock(return_value=55)
    ent = _entity(
        coordinator,
        DreameVacuumEntityDescription(
            property_key=DreameVacuumProperty.VOLUME,
            value_fn=lambda value, device: value,
        ),
    )
    assert ent.extra_state_attributes == {ATTR_VALUE: 55}


def test_extra_state_attributes_value_int_fn_ok(coordinator):
    class Status:
        pass

    coordinator.device.status = Status()
    coordinator.device.get_property = MagicMock(return_value=None)
    ent = _entity(
        coordinator,
        DreameVacuumEntityDescription(
            key="no_prop",
            value_int_fn=lambda native, entity: 7,
        ),
    )
    assert ent.extra_state_attributes == {ATTR_VALUE: 7}


@pytest.mark.parametrize("exc", [ValueError, KeyError, AttributeError, TypeError])
def test_extra_state_attributes_value_int_fn_guarded(coordinator, exc):
    """The try/except guard: value_int_fn raising must not break the entity."""

    def raising(native, entity):
        raise exc("boom")

    ent = _entity(
        coordinator,
        DreameVacuumEntityDescription(key="no_prop", value_int_fn=raising),
    )
    # Must swallow the exception and return None instead of propagating.
    assert ent.extra_state_attributes is None


def test_extra_state_attributes_value_int_fn_unexpected_exception_propagates(coordinator):
    """A non-listed exception type must still propagate (guard is selective)."""

    def raising(native, entity):
        raise RuntimeError("unexpected")

    ent = _entity(
        coordinator,
        DreameVacuumEntityDescription(key="no_prop", value_int_fn=raising),
    )
    with pytest.raises(RuntimeError):
        _ = ent.extra_state_attributes


def test_extra_state_attributes_none_when_no_fns(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    assert ent.extra_state_attributes is None


# --------------------------------------------------------------------------- #
# _try_command                                                                 #
# --------------------------------------------------------------------------- #


async def test_try_command_success(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    ent.hass = coordinator.hass
    func = MagicMock()
    result = await ent._try_command("err %s", func, 1, kw=2)
    assert result is True
    func.assert_called_once_with(1, kw=2)


async def test_try_command_raises_when_not_connected(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    coordinator.device.device_connected = False
    with pytest.raises(HomeAssistantError) as err:
        await ent._try_command("err %s", MagicMock())
    assert err.value.translation_key == "device_not_available"


@pytest.mark.parametrize("exc_cls", [InvalidActionException, InvalidValueException])
async def test_try_command_invalid_exception_to_ha_error(coordinator, exc_cls):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    ent.hass = coordinator.hass

    def func():
        raise exc_cls("bad value")

    with pytest.raises(HomeAssistantError) as err:
        await ent._try_command("err %s", func)
    assert err.value.translation_key == "invalid_command"
    assert err.value.translation_placeholders == {"error": "bad value"}


@pytest.mark.parametrize("exc_cls", [DeviceException, DeviceUpdateFailedException])
async def test_try_command_device_exception_available_raises(coordinator, exc_cls):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    ent.hass = coordinator.hass
    coordinator.device.available = True

    def func():
        raise exc_cls("device boom")

    with pytest.raises(HomeAssistantError) as err:
        await ent._try_command("err %s", func)
    assert err.value.translation_key == "command_failed"
    assert err.value.translation_placeholders == {"error": "device boom"}


@pytest.mark.parametrize("exc_cls", [DeviceException, DeviceUpdateFailedException])
async def test_try_command_device_exception_unavailable_returns_false(coordinator, exc_cls):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    ent.hass = coordinator.hass
    coordinator.device.available = False

    def func():
        raise exc_cls("device boom")

    result = await ent._try_command("err %s", func)
    assert result is False


# --------------------------------------------------------------------------- #
# _handle_coordinator_update                                                   #
# --------------------------------------------------------------------------- #


def test_handle_coordinator_update_device_none(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    ent.async_write_ha_state = MagicMock()
    coordinator.device = None
    ent._handle_coordinator_update()
    ent.async_write_ha_state.assert_called_once()


def test_handle_coordinator_update_with_device(coordinator):
    coordinator.device.status.volume = 1
    ent = _entity(
        coordinator,
        DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME, icon="mdi:x"),
    )
    ent.async_write_ha_state = MagicMock()
    ent._handle_coordinator_update()
    # _set_id ran (icon applied) and state written.
    assert ent._attr_icon == "mdi:x"
    ent.async_write_ha_state.assert_called_once()


# --------------------------------------------------------------------------- #
# _generate_entity_id                                                          #
# --------------------------------------------------------------------------- #


def test_generate_entity_id_sets_entity_id(coordinator):
    from homeassistant.components.number import ENTITY_ID_FORMAT

    ent = _entity(coordinator, DreameVacuumEntityDescription(key="my_key"))
    ent._generate_entity_id(ENTITY_ID_FORMAT)
    assert ent.entity_id.startswith("number.")
    assert "my_key" in ent.entity_id


def test_generate_entity_id_noop_without_key(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="my_key"))
    ent._computed_key = None
    # No key -> entity_id not regenerated (no exception).
    ent.entity_id = "number.preset"
    from homeassistant.components.number import ENTITY_ID_FORMAT

    ent._generate_entity_id(ENTITY_ID_FORMAT)
    assert ent.entity_id == "number.preset"


# --------------------------------------------------------------------------- #
# device property accessor                                                     #
# --------------------------------------------------------------------------- #


def test_device_property_returns_coordinator_device(coordinator):
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    assert ent.device is coordinator.device


# --------------------------------------------------------------------------- #
# resolver helpers (_resolve_set_fn / _resolve_value_fn / _resolve_segment*)   #
# --------------------------------------------------------------------------- #


def test_resolve_set_fn_explicit(coordinator):
    def fn(dev, value):
        return None

    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    desc = DreameVacuumEntityDescription(key="x")
    object.__setattr__(desc, "set_fn", fn)
    assert ent._resolve_set_fn(coordinator, desc) is fn


def test_resolve_set_fn_from_device_method(coordinator):
    # Real object device with a ``set_volume`` method; everything else minimal.
    class Dev:
        def __init__(self):
            self.mac = MAC
            self.name = "n"
            self.status = MagicMock()
            self.called_with = None

        def set_volume(self, value):
            self.called_with = value

    dev = Dev()
    coordinator.device = dev
    ent = _entity(coordinator, DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME))
    desc = DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME)
    object.__setattr__(desc, "set_fn", None)
    resolved = ent._resolve_set_fn(coordinator, desc)
    assert resolved is not None
    resolved(dev, 12)
    assert dev.called_with == 12


def test_resolve_set_fn_returns_none_when_no_method(coordinator):
    class Dev:
        mac = MAC
        name = "n"
        status = MagicMock()

    coordinator.device = Dev()
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="nonexistent_setter"))
    desc = DreameVacuumEntityDescription(key="nonexistent_setter")
    object.__setattr__(desc, "set_fn", None)
    assert ent._resolve_set_fn(coordinator, desc) is None


def test_resolve_value_fn_with_suffix(coordinator):
    # status has ``volume_name`` -> resolver returns getter for it.
    coordinator.device.status.volume_name = "loud"
    ent = _entity(coordinator, DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME))
    desc = DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME)
    object.__setattr__(desc, "value_fn", None)
    resolved = ent._resolve_value_fn(coordinator, desc, suffix="_name")
    assert resolved is not None
    assert resolved(None, coordinator.device) == "loud"


def test_resolve_value_fn_explicit(coordinator):
    def fn(value, dev):
        return 1

    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    desc = DreameVacuumEntityDescription(key="x")
    object.__setattr__(desc, "value_fn", fn)
    assert ent._resolve_value_fn(coordinator, desc) is fn


def test_resolve_value_fn_none_when_status_missing(coordinator):
    class Status:
        pass

    coordinator.device.status = Status()
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="missing_attr"))
    desc = DreameVacuumEntityDescription(key="missing_attr")
    object.__setattr__(desc, "value_fn", None)
    assert ent._resolve_value_fn(coordinator, desc) is None


def test_resolve_segment_set_fn_from_device_method(coordinator):
    class Dev:
        def __init__(self):
            self.mac = MAC
            self.name = "n"
            self.status = MagicMock()
            self.seg = None

        def set_segment_volume(self, segment_id, value):
            self.seg = (segment_id, value)

    dev = Dev()
    coordinator.device = dev
    ent = _entity(coordinator, DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME))
    desc = DreameVacuumEntityDescription(property_key=DreameVacuumProperty.VOLUME)
    object.__setattr__(desc, "set_fn", None)
    resolved = ent._resolve_segment_set_fn(coordinator, desc)
    assert resolved is not None
    resolved(dev, 3, 18)
    assert dev.seg == (3, 18)


def test_resolve_segment_set_fn_explicit(coordinator):
    def fn(dev, seg, value):
        return None

    ent = _entity(coordinator, DreameVacuumEntityDescription(key="x"))
    desc = DreameVacuumEntityDescription(key="x")
    object.__setattr__(desc, "set_fn", fn)
    assert ent._resolve_segment_set_fn(coordinator, desc) is fn


def test_resolve_segment_set_fn_none_when_no_method(coordinator):
    class Dev:
        mac = MAC
        name = "n"
        status = MagicMock()

    coordinator.device = Dev()
    ent = _entity(coordinator, DreameVacuumEntityDescription(key="no_segment_setter"))
    desc = DreameVacuumEntityDescription(key="no_segment_setter")
    object.__setattr__(desc, "set_fn", None)
    assert ent._resolve_segment_set_fn(coordinator, desc) is None
