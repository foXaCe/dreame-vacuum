"""Behavioural tests for the Dreame Vacuum ``vacuum`` platform.

These tests drive the :class:`DreameVacuum` entity directly with a richly
populated mock coordinator / device, exercising:

* the state-code mapping (``STATE_CODE_TO_STATE``) and ``activity`` property,
* the dynamic icon selection in ``_set_attrs``,
* the ``supported_features`` / ``fan_speed`` / ``fan_speed_list`` toggling,
* ``available`` / ``extra_state_attributes`` / ``device_info``,
* every command + service method, covering both the happy path and the
  error paths funnelled through ``_try_command`` (``HomeAssistantError``),
* the fan-speed validation branches (invalid int, unknown string,
  cruising / customized-cleaning guards).

The device is fully mocked - no network, no real Home Assistant runtime. The
only piece of HA wired in is a fake ``hass`` whose ``async_add_executor_job``
runs the supplied callable synchronously, so ``_try_command`` behaves exactly
as in production while staying deterministic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.vacuum import VacuumEntityFeature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
import pytest

from custom_components.dreame_vacuum import vacuum as vacuum_module
from custom_components.dreame_vacuum.const import (
    CONSUMABLE_FILTER,
    CONSUMABLE_MAIN_BRUSH,
    DOMAIN,
    FAN_SPEED_SILENT,
    FAN_SPEED_STANDARD,
    FAN_SPEED_STRONG,
    FAN_SPEED_TURBO,
)
from custom_components.dreame_vacuum.dreame import (
    DeviceException,
    DeviceUpdateFailedException,
    DreameVacuumAction,
    DreameVacuumState,
    DreameVacuumSuctionLevel,
)
from custom_components.dreame_vacuum.dreame.const import (
    STATE_CLEANING,
    STATE_DOCKED,
    STATE_ERROR,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_RETURNING,
    STATE_UNKNOWN,
)
from custom_components.dreame_vacuum.dreame.exceptions import (
    InvalidActionException,
    InvalidValueException,
)
from custom_components.dreame_vacuum.vacuum import (
    CONSUMABLE_RESET_ACTION,
    STATE_CODE_TO_STATE,
    SUCTION_LEVEL_TO_FAN_SPEED,
    DreameVacuum,
    async_setup_entry,
)

# All the boolean status flags read by ``_set_attrs`` to pick an icon / decide
# whether the FAN_SPEED feature is offered. Default them all to ``False`` so a
# test only has to flip the one flag it cares about.
_STATUS_BOOL_FLAGS = (
    "has_error",
    "has_warning",
    "low_water",
    "draining_complete",
    "returning_to_wash",
    "washing",
    "paused",
    "washing_paused",
    "returning_to_wash_paused",
    "drying",
    "sleeping",
    "charging",
    "docked",
    "cruising",
    "started",
    "customized_cleaning",
    "zone_cleaning",
    "spot_cleaning",
    "scheduled_clean",
)


def _build_coordinator() -> MagicMock:
    """Return a MagicMock coordinator with a fully populated device.status."""
    coordinator = MagicMock()
    device = coordinator.device
    device.name = "Test Vacuum"
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.available = True
    device.device_connected = True

    status = device.status
    for flag in _STATUS_BOOL_FLAGS:
        setattr(status, flag, False)
    status.suction_level = DreameVacuumSuctionLevel.STANDARD
    status.state = DreameVacuumState.SWEEPING
    status.attributes = {"sensor": "value"}
    status.serial_number = "SN-123"
    status.selected_map = None
    status.map_data_list = None

    # info block consumed by device_info
    device.info.manufacturer = "Dreame"
    device.info.model = "dreame.vacuum.test"
    device.info.firmware_version = "1.2.3"
    device.info.hardware_version = "rev-a"

    return coordinator


def _fake_hass() -> MagicMock:
    """Return a fake hass whose executor runs callables synchronously."""
    hass = MagicMock()

    async def _run(func):
        return func()

    hass.async_add_executor_job = AsyncMock(side_effect=_run)
    return hass


def _make_entity(coordinator: MagicMock | None = None) -> DreameVacuum:
    """Instantiate the entity and wire a fake hass for ``_try_command``."""
    if coordinator is None:
        coordinator = _build_coordinator()
    entity = DreameVacuum(coordinator)
    entity.hass = _fake_hass()
    return entity


@pytest.fixture
def coordinator() -> MagicMock:
    """A ready-to-use mock coordinator."""
    return _build_coordinator()


@pytest.fixture
def entity(coordinator: MagicMock) -> DreameVacuum:
    """A ready-to-use entity backed by the coordinator fixture."""
    return _make_entity(coordinator)


# ---------------------------------------------------------------------------
# Basic attributes / construction
# ---------------------------------------------------------------------------


def test_unique_id_and_device_class(entity: DreameVacuum, coordinator: MagicMock) -> None:
    """Unique id is ``<mac>_dreame_vacuum`` and device_class is the domain."""
    assert entity.unique_id == f"{coordinator.device.mac}_{DOMAIN}"
    assert entity._attr_device_class == DOMAIN
    # has_entity_name + name=None => inherits device name.
    assert entity._attr_name is None


def test_base_supported_features(entity: DreameVacuum) -> None:
    """The static feature set always advertises the core capabilities."""
    features = entity.supported_features
    for feature in (
        VacuumEntityFeature.SEND_COMMAND,
        VacuumEntityFeature.LOCATE,
        VacuumEntityFeature.STATE,
        VacuumEntityFeature.MAP,
        VacuumEntityFeature.START,
        VacuumEntityFeature.PAUSE,
        VacuumEntityFeature.STOP,
        VacuumEntityFeature.RETURN_HOME,
    ):
        assert features & feature


def test_extra_state_attributes_passthrough(entity: DreameVacuum, coordinator: MagicMock) -> None:
    """``extra_state_attributes`` mirrors ``device.status.attributes``."""
    assert entity.extra_state_attributes == {"sensor": "value"}
    coordinator.device.status.attributes = {"other": 1}
    entity._set_attrs()
    assert entity.extra_state_attributes == {"other": 1}


def test_device_info(entity: DreameVacuum) -> None:
    """``device_info`` carries identifiers, connections and the info block."""
    info = entity.device_info
    assert info is not None
    assert (DOMAIN, "AA:BB:CC:DD:EE:FF") in info["identifiers"]
    assert info["name"] == "Test Vacuum"
    assert info["serial_number"] == "SN-123"
    assert info["manufacturer"] == "Dreame"
    assert info["model"] == "dreame.vacuum.test"
    assert info["sw_version"] == "1.2.3"
    assert info["hw_version"] == "rev-a"


def test_set_attrs_noop_when_status_missing(coordinator: MagicMock) -> None:
    """``_set_attrs`` returns early (no crash) when status is None."""
    entity = _make_entity(coordinator)
    coordinator.device.status = None
    # Must not raise even though every status attribute is now gone.
    entity._set_attrs()


# ---------------------------------------------------------------------------
# State mapping & activity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (DreameVacuumState.SWEEPING, STATE_CLEANING),
        (DreameVacuumState.IDLE, STATE_IDLE),
        (DreameVacuumState.PAUSED, STATE_PAUSED),
        (DreameVacuumState.ERROR, STATE_ERROR),
        (DreameVacuumState.RETURNING, STATE_RETURNING),
        (DreameVacuumState.CHARGING, STATE_DOCKED),
        (DreameVacuumState.MOPPING, STATE_CLEANING),
        (DreameVacuumState.DRYING, STATE_DOCKED),
        (DreameVacuumState.SWEEPING_AND_MOPPING, STATE_CLEANING),
        (DreameVacuumState.WASHING_PAUSED, STATE_PAUSED),
    ],
)
def test_state_code_to_state_mapping(coordinator: MagicMock, state: DreameVacuumState, expected: str) -> None:
    """Each device state maps to the documented HA vacuum state."""
    coordinator.device.status.state = state
    entity = _make_entity(coordinator)
    assert entity._vacuum_state == expected
    assert STATE_CODE_TO_STATE[state] == expected


def test_activity_known_state(coordinator: MagicMock) -> None:
    """A mapped state surfaces through ``activity`` (string-comparable)."""
    coordinator.device.status.state = DreameVacuumState.SWEEPING
    entity = _make_entity(coordinator)
    activity = entity.activity
    assert activity is not None
    # ``activity`` is either the VacuumActivity enum (HA >= 2024.12) or the raw
    # string fallback; both compare equal to the cleaning state value.
    assert str(getattr(activity, "value", activity)) == STATE_CLEANING


def test_activity_unknown_state_is_none(coordinator: MagicMock) -> None:
    """An unknown device state yields ``activity == None``."""
    coordinator.device.status.state = DreameVacuumState.UNKNOWN
    entity = _make_entity(coordinator)
    assert entity._vacuum_state == STATE_UNKNOWN
    assert entity.activity is None


def test_activity_unmapped_state_is_none(coordinator: MagicMock) -> None:
    """A state absent from the map falls back to unknown -> activity None."""
    bogus = MagicMock()  # not a key in STATE_CODE_TO_STATE
    coordinator.device.status.state = bogus
    entity = _make_entity(coordinator)
    assert entity._vacuum_state == STATE_UNKNOWN
    assert entity.activity is None


def test_activity_without_activity_class(coordinator: MagicMock) -> None:
    """When VacuumActivity is unavailable, activity returns the raw string.

    On HA versions without ``VacuumActivity`` the entity falls back to setting
    ``_attr_state`` directly. Modern HA flags that via ``report_usage`` (a
    deprecation telemetry call that needs the frame helper); we silence that
    single telemetry hook so the legacy code path itself can run.
    """
    coordinator.device.status.state = DreameVacuumState.IDLE
    entity = _make_entity(coordinator)
    entity._activity_class = None  # simulate older HA without VacuumActivity
    assert entity.activity == STATE_IDLE
    # And _attr_state is populated on that code path.
    with patch("homeassistant.components.vacuum.report_usage"):
        entity._set_attrs()
    assert entity._attr_state == STATE_IDLE


def test_activity_invalid_value_returns_none(coordinator: MagicMock) -> None:
    """If the activity class rejects the value, ``activity`` returns None."""
    entity = _make_entity(coordinator)
    entity._vacuum_state = "not-a-real-activity"

    class _Strict:
        def __init__(self, value):
            raise ValueError(value)

    entity._activity_class = _Strict
    assert entity.activity is None


# ---------------------------------------------------------------------------
# Icon selection (every branch in _set_attrs)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flag", "icon"),
    [
        ("has_error", "mdi:alert-octagon"),
        ("has_warning", "mdi:robot-vacuum-alert"),
        ("low_water", "mdi:robot-vacuum-alert"),
        ("draining_complete", "mdi:robot-vacuum-alert"),
        ("returning_to_wash", "mdi:water-circle"),
        ("washing", "mdi:water-sync"),
        ("paused", "mdi:pause-circle"),
        ("washing_paused", "mdi:pause-circle"),
        ("returning_to_wash_paused", "mdi:pause-circle"),
        ("drying", "mdi:hair-dryer"),
        ("sleeping", "mdi:sleep"),
        ("charging", "mdi:lightning-bolt-circle"),
        ("docked", "mdi:ev-station"),
        ("cruising", "mdi:map-marker-path"),
    ],
)
def test_icon_for_status_flag(coordinator: MagicMock, flag: str, icon: str) -> None:
    """Each status flag drives the expected MDI icon."""
    setattr(coordinator.device.status, flag, True)
    entity = _make_entity(coordinator)
    assert entity._attr_icon == icon


def test_icon_default(entity: DreameVacuum) -> None:
    """With no special flag set, the default robot icon is used."""
    assert entity._attr_icon == "mdi:robot-vacuum"


# ---------------------------------------------------------------------------
# Fan speed / supported features toggling
# ---------------------------------------------------------------------------


def test_fan_speed_available_by_default(entity: DreameVacuum) -> None:
    """When not in customized cleaning, FAN_SPEED is offered with a full list."""
    assert entity.supported_features & VacuumEntityFeature.FAN_SPEED
    assert entity.fan_speed == FAN_SPEED_STANDARD
    assert entity.fan_speed_list == [
        FAN_SPEED_SILENT,
        FAN_SPEED_STANDARD,
        FAN_SPEED_STRONG,
        FAN_SPEED_TURBO,
    ]


def test_fan_speed_unknown_suction_level(coordinator: MagicMock) -> None:
    """An unmapped suction level falls back to the unknown sentinel."""
    coordinator.device.status.suction_level = DreameVacuumSuctionLevel.UNKNOWN
    entity = _make_entity(coordinator)
    assert entity.fan_speed == STATE_UNKNOWN


def test_fan_speed_removed_during_customized_cleaning(coordinator: MagicMock) -> None:
    """Customized cleaning (not zone/spot) removes FAN_SPEED and clears the list."""
    status = coordinator.device.status
    status.started = True
    status.customized_cleaning = True
    status.zone_cleaning = False
    status.spot_cleaning = False
    entity = _make_entity(coordinator)
    assert not (entity.supported_features & VacuumEntityFeature.FAN_SPEED)
    assert entity.fan_speed is None
    assert entity.fan_speed_list == []


def test_fan_speed_kept_during_zone_cleaning(coordinator: MagicMock) -> None:
    """Zone cleaning keeps FAN_SPEED even while customized cleaning is on."""
    status = coordinator.device.status
    status.started = True
    status.customized_cleaning = True
    status.zone_cleaning = True
    entity = _make_entity(coordinator)
    assert entity.supported_features & VacuumEntityFeature.FAN_SPEED


def test_fan_speed_removed_during_scheduled_clean(coordinator: MagicMock) -> None:
    """A scheduled clean removes the FAN_SPEED feature."""
    coordinator.device.status.scheduled_clean = True
    entity = _make_entity(coordinator)
    assert not (entity.supported_features & VacuumEntityFeature.FAN_SPEED)


def test_fan_speed_flag_not_sticky(coordinator: MagicMock) -> None:
    """B7 guard: flipping out of customized cleaning restores FAN_SPEED."""
    status = coordinator.device.status
    status.started = True
    status.customized_cleaning = True
    entity = _make_entity(coordinator)
    assert not (entity.supported_features & VacuumEntityFeature.FAN_SPEED)

    # Leave customized cleaning and re-run the attribute refresh.
    status.started = False
    status.customized_cleaning = False
    entity._set_attrs()
    assert entity.supported_features & VacuumEntityFeature.FAN_SPEED


# ---------------------------------------------------------------------------
# async_set_fan_speed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Silent", DreameVacuumSuctionLevel.QUIET),
        ("standard", DreameVacuumSuctionLevel.STANDARD),
        ("STRONG", DreameVacuumSuctionLevel.STRONG),
        ("Turbo", DreameVacuumSuctionLevel.TURBO),
    ],
)
async def test_set_fan_speed_by_name(coordinator: MagicMock, value: str, expected: DreameVacuumSuctionLevel) -> None:
    """A known fan-speed name is translated to the suction level enum."""
    entity = _make_entity(coordinator)
    await entity.async_set_fan_speed(value)
    coordinator.device.set_suction_level.assert_called_once_with(expected)


async def test_set_fan_speed_numeric_string(coordinator: MagicMock) -> None:
    """A numeric string is coerced to int then validated against the enum."""
    entity = _make_entity(coordinator)
    await entity.async_set_fan_speed("2")
    coordinator.device.set_suction_level.assert_called_once_with(2)


async def test_set_fan_speed_int(coordinator: MagicMock) -> None:
    """A valid int suction level is forwarded as-is."""
    entity = _make_entity(coordinator)
    await entity.async_set_fan_speed(3)
    coordinator.device.set_suction_level.assert_called_once_with(3)


async def test_set_fan_speed_int_out_of_range(entity: DreameVacuum) -> None:
    """An int outside the enum raises HomeAssistantError (invalid_fan_speed)."""
    with pytest.raises(HomeAssistantError) as exc:
        await entity.async_set_fan_speed(99)
    assert exc.value.translation_key == "invalid_fan_speed"


async def test_set_fan_speed_unknown_string(entity: DreameVacuum) -> None:
    """An unrecognised string raises HomeAssistantError (not recognized)."""
    with pytest.raises(HomeAssistantError) as exc:
        await entity.async_set_fan_speed("hyperdrive")
    assert exc.value.translation_key == "fan_speed_not_recognized"


async def test_set_fan_speed_blocked_when_cruising(coordinator: MagicMock) -> None:
    """Setting fan speed while cruising raises the cruising error."""
    coordinator.device.status.cruising = True
    entity = _make_entity(coordinator)
    with pytest.raises(HomeAssistantError) as exc:
        await entity.async_set_fan_speed("turbo")
    assert exc.value.translation_key == "fan_speed_cruising"
    coordinator.device.set_suction_level.assert_not_called()


async def test_set_fan_speed_blocked_during_customized_cleaning(coordinator: MagicMock) -> None:
    """Setting fan speed during customized cleaning raises the customized error."""
    status = coordinator.device.status
    status.started = True
    status.customized_cleaning = True
    status.zone_cleaning = False
    status.spot_cleaning = False
    entity = _make_entity(coordinator)
    with pytest.raises(HomeAssistantError) as exc:
        await entity.async_set_fan_speed("turbo")
    assert exc.value.translation_key == "fan_speed_customized_cleaning"


# ---------------------------------------------------------------------------
# available
# ---------------------------------------------------------------------------


def test_available_true(entity: DreameVacuum) -> None:
    """Available when the entity flag is set and the device is connected."""
    entity._attr_available = True
    assert entity.available is True


def test_available_false_when_disconnected(coordinator: MagicMock) -> None:
    """Not available when the device reports it is disconnected."""
    coordinator.device.device_connected = False
    entity = _make_entity(coordinator)
    entity._attr_available = True
    assert entity.available is False


def test_available_false_when_device_none(coordinator: MagicMock) -> None:
    """Not available when there is no device at all."""
    entity = _make_entity(coordinator)
    type(coordinator).device = property(lambda self: None)
    try:
        assert entity.available is False
    finally:
        del type(coordinator).device


# ---------------------------------------------------------------------------
# Coordinator update hook
# ---------------------------------------------------------------------------


def test_handle_coordinator_update_refreshes_attrs(coordinator: MagicMock) -> None:
    """The coordinator callback re-runs ``_set_attrs`` and writes state."""
    entity = _make_entity(coordinator)
    entity.async_write_ha_state = MagicMock()

    coordinator.device.status.state = DreameVacuumState.ERROR
    coordinator.device.status.has_error = True
    entity._handle_coordinator_update()

    assert entity._vacuum_state == STATE_ERROR
    assert entity._attr_icon == "mdi:alert-octagon"
    entity.async_write_ha_state.assert_called_once()


# ---------------------------------------------------------------------------
# Simple commands (happy path) routed through _try_command
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "device_attr"),
    [
        ("async_locate", "locate"),
        ("async_start", "start"),
        ("async_start_pause", "start_pause"),
        ("async_stop", "stop"),
        ("async_pause", "pause"),
        ("async_return_to_base", "return_to_base"),
        ("async_request_map", "request_map"),
        ("async_save_temporary_map", "save_temporary_map"),
        ("async_discard_temporary_map", "discard_temporary_map"),
    ],
)
async def test_simple_command_calls_device(coordinator: MagicMock, method: str, device_attr: str) -> None:
    """Each no-arg command forwards to the matching device method."""
    entity = _make_entity(coordinator)
    await getattr(entity, method)()
    getattr(coordinator.device, device_attr).assert_called_once()


async def test_send_command(coordinator: MagicMock) -> None:
    """send_command forwards the command + params to the device."""
    entity = _make_entity(coordinator)
    await entity.async_send_command("app_segment_clean", params=[1, 2])
    coordinator.device.send_command.assert_called_once_with("app_segment_clean", [1, 2])


# ---------------------------------------------------------------------------
# _try_command error handling
# ---------------------------------------------------------------------------


async def test_try_command_device_not_connected(coordinator: MagicMock) -> None:
    """A disconnected device raises device_not_available before calling."""
    coordinator.device.device_connected = False
    entity = _make_entity(coordinator)
    with pytest.raises(HomeAssistantError) as exc:
        await entity.async_start()
    assert exc.value.translation_key == "device_not_available"
    coordinator.device.start.assert_not_called()


async def test_try_command_invalid_action_raises(coordinator: MagicMock) -> None:
    """InvalidActionException is converted to HomeAssistantError."""
    coordinator.device.start.side_effect = InvalidActionException("bad action")
    entity = _make_entity(coordinator)
    with pytest.raises(HomeAssistantError, match="bad action"):
        await entity.async_start()


async def test_try_command_invalid_value_raises(coordinator: MagicMock) -> None:
    """InvalidValueException is converted to HomeAssistantError."""
    coordinator.device.start.side_effect = InvalidValueException("bad value")
    entity = _make_entity(coordinator)
    with pytest.raises(HomeAssistantError, match="bad value"):
        await entity.async_start()


async def test_try_command_device_exception_available_raises(coordinator: MagicMock) -> None:
    """A DeviceException raises when the device still reports available."""
    coordinator.device.available = True
    coordinator.device.start.side_effect = DeviceException("network down")
    entity = _make_entity(coordinator)
    with pytest.raises(HomeAssistantError, match="network down"):
        await entity.async_start()


async def test_try_command_device_update_failed_available_raises(coordinator: MagicMock) -> None:
    """A DeviceUpdateFailedException raises when the device is available."""
    coordinator.device.available = True
    coordinator.device.start.side_effect = DeviceUpdateFailedException("update failed")
    entity = _make_entity(coordinator)
    with pytest.raises(HomeAssistantError, match="update failed"):
        await entity.async_start()


async def test_try_command_device_exception_unavailable_swallowed(coordinator: MagicMock) -> None:
    """A DeviceException is swallowed (returns False) when device unavailable."""
    coordinator.device.available = False
    coordinator.device.start.side_effect = DeviceException("offline")
    entity = _make_entity(coordinator)
    # Must NOT raise.
    await entity.async_start()


# ---------------------------------------------------------------------------
# Cleaning services with positional / list arguments
# ---------------------------------------------------------------------------


async def test_clean_zone(coordinator: MagicMock) -> None:
    """clean_zone forwards zone + repeats + suction + water to the device."""
    entity = _make_entity(coordinator)
    await entity.async_clean_zone([[0, 0, 10, 10]], repeats=2, suction_level=1, water_volume=2)
    coordinator.device.clean_zone.assert_called_once_with([[0, 0, 10, 10]], 2, 1, 2)


async def test_clean_zone_defaults(coordinator: MagicMock) -> None:
    """clean_zone uses default repeats=1 and empty suction/water."""
    entity = _make_entity(coordinator)
    await entity.async_clean_zone([0, 0, 10, 10])
    coordinator.device.clean_zone.assert_called_once_with([0, 0, 10, 10], 1, "", "")


async def test_clean_segment(coordinator: MagicMock) -> None:
    """clean_segment forwards the segment list and options."""
    entity = _make_entity(coordinator)
    await entity.async_clean_segment([1, 2], repeats=3, suction_level=2, water_volume=1)
    coordinator.device.clean_segment.assert_called_once_with([1, 2], 3, 2, 1)


async def test_clean_spot(coordinator: MagicMock) -> None:
    """clean_spot forwards the points and options."""
    entity = _make_entity(coordinator)
    await entity.async_clean_spot([[5, 5]], repeats=1, suction_level=0, water_volume=0)
    coordinator.device.clean_spot.assert_called_once_with([[5, 5]], 1, 0, 0)


async def test_clean_zone_propagates_device_error(coordinator: MagicMock) -> None:
    """An invalid-zone exception bubbles up as HomeAssistantError."""
    coordinator.device.clean_zone.side_effect = InvalidActionException("Invalid zone coordinates: []")
    entity = _make_entity(coordinator)
    with pytest.raises(HomeAssistantError, match="Invalid zone coordinates"):
        await entity.async_clean_zone([])


async def test_goto(coordinator: MagicMock) -> None:
    """goto forwards the coordinates when both are provided."""
    entity = _make_entity(coordinator)
    await entity.async_goto(100, 200)
    coordinator.device.go_to.assert_called_once_with(100, 200)


async def test_goto_skips_on_empty(coordinator: MagicMock) -> None:
    """goto does nothing when a coordinate is the empty string."""
    entity = _make_entity(coordinator)
    await entity.async_goto("", 200)
    coordinator.device.go_to.assert_not_called()


async def test_goto_skips_on_none(coordinator: MagicMock) -> None:
    """goto does nothing when a coordinate is None."""
    entity = _make_entity(coordinator)
    await entity.async_goto(None, None)
    coordinator.device.go_to.assert_not_called()


async def test_follow_path(coordinator: MagicMock) -> None:
    """follow_path forwards the points list."""
    entity = _make_entity(coordinator)
    await entity.async_follow_path([[1, 1], [2, 2]])
    coordinator.device.follow_path.assert_called_once_with([[1, 1], [2, 2]])


async def test_start_shortcut(coordinator: MagicMock) -> None:
    """start_shortcut forwards the shortcut id."""
    entity = _make_entity(coordinator)
    await entity.async_start_shortcut(7)
    coordinator.device.start_shortcut.assert_called_once_with(7)


# ---------------------------------------------------------------------------
# Zone / carpet / threshold / predefined points setters
# ---------------------------------------------------------------------------


async def test_set_restricted_zone(coordinator: MagicMock) -> None:
    """set_restricted_zone forwards walls/zones/no-mops."""
    entity = _make_entity(coordinator)
    await entity.async_set_restricted_zone(walls=[[1, 1, 2, 2]], zones=[[3, 3, 4, 4]], no_mops=[[5, 5, 6, 6]])
    coordinator.device.set_restricted_zone.assert_called_once_with([[1, 1, 2, 2]], [[3, 3, 4, 4]], [[5, 5, 6, 6]])


async def test_set_carpet_area(coordinator: MagicMock) -> None:
    """set_carpet_area forwards carpet + ignored-carpet arrays."""
    entity = _make_entity(coordinator)
    await entity.async_set_carpet_area(carpets=[[1, 1, 2, 2]], ignored_carpets=[[3, 3, 4, 4]])
    coordinator.device.set_carpet_area.assert_called_once_with([[1, 1, 2, 2]], [[3, 3, 4, 4]])


async def test_set_virtual_threshold(coordinator: MagicMock) -> None:
    """set_virtual_threshold forwards the threshold array."""
    entity = _make_entity(coordinator)
    await entity.async_set_virtual_threshold([[1, 2, 3, 4]])
    coordinator.device.set_virtual_threshold.assert_called_once_with([[1, 2, 3, 4]])


async def test_set_predefined_points(coordinator: MagicMock) -> None:
    """set_predefined_points forwards the point list."""
    entity = _make_entity(coordinator)
    await entity.async_set_predefined_points([[1, 1], [2, 2]])
    coordinator.device.set_predefined_points.assert_called_once_with([[1, 1], [2, 2]])


async def test_remote_control_move_step(coordinator: MagicMock) -> None:
    """remote_control_move_step forwards rotation/velocity/prompt."""
    entity = _make_entity(coordinator)
    await entity.async_remote_control_move_step(rotation=10, velocity=20, prompt=True)
    coordinator.device.remote_control_move_step.assert_called_once_with(10, 20, True)


# ---------------------------------------------------------------------------
# Map management services
# ---------------------------------------------------------------------------


async def test_select_map(coordinator: MagicMock) -> None:
    """select_map forwards the map id."""
    entity = _make_entity(coordinator)
    await entity.async_select_map(2)
    coordinator.device.set_selected_map.assert_called_once_with(2)


async def test_delete_map(coordinator: MagicMock) -> None:
    """delete_map forwards the (optional) map id."""
    entity = _make_entity(coordinator)
    await entity.async_delete_map(3)
    coordinator.device.delete_map.assert_called_once_with(3)


async def test_delete_map_default(coordinator: MagicMock) -> None:
    """delete_map passes None when no id is supplied."""
    entity = _make_entity(coordinator)
    await entity.async_delete_map()
    coordinator.device.delete_map.assert_called_once_with(None)


async def test_replace_temporary_map(coordinator: MagicMock) -> None:
    """replace_temporary_map forwards the map id."""
    entity = _make_entity(coordinator)
    await entity.async_replace_temporary_map(4)
    coordinator.device.replace_temporary_map.assert_called_once_with(4)


async def test_rename_map(coordinator: MagicMock) -> None:
    """rename_map forwards the id and the new name."""
    entity = _make_entity(coordinator)
    await entity.async_rename_map(1, "Living room")
    coordinator.device.rename_map.assert_called_once_with(1, "Living room")


async def test_restore_map(coordinator: MagicMock) -> None:
    """restore_map forwards the recovery index and map id."""
    entity = _make_entity(coordinator)
    await entity.async_restore_map(2, 1)
    coordinator.device.restore_map.assert_called_once_with(2, 1)


async def test_restore_map_skips_on_empty(coordinator: MagicMock) -> None:
    """restore_map is a no-op when the recovery index is empty/falsy."""
    entity = _make_entity(coordinator)
    await entity.async_restore_map("")
    coordinator.device.restore_map.assert_not_called()


async def test_restore_map_from_file(coordinator: MagicMock) -> None:
    """restore_map_from_file forwards the URL and map id."""
    entity = _make_entity(coordinator)
    await entity.async_restore_map_from_file("http://example.com/m.bin", 1)
    coordinator.device.restore_map_from_file.assert_called_once_with("http://example.com/m.bin", 1)


async def test_restore_map_from_file_skips_on_empty(coordinator: MagicMock) -> None:
    """restore_map_from_file is a no-op when the URL is empty."""
    entity = _make_entity(coordinator)
    await entity.async_restore_map_from_file("")
    coordinator.device.restore_map_from_file.assert_not_called()


async def test_backup_map(coordinator: MagicMock) -> None:
    """backup_map forwards the (optional) map id."""
    entity = _make_entity(coordinator)
    await entity.async_backup_map(5)
    coordinator.device.backup_map.assert_called_once_with(5)


# ---------------------------------------------------------------------------
# Segment services
# ---------------------------------------------------------------------------


async def test_rename_segment(coordinator: MagicMock) -> None:
    """rename_segment forwards id, the fixed 0, and the name."""
    entity = _make_entity(coordinator)
    await entity.async_rename_segment(2, "Kitchen")
    coordinator.device.set_segment_name.assert_called_once_with(2, 0, "Kitchen")


async def test_rename_segment_skips_on_empty(coordinator: MagicMock) -> None:
    """rename_segment is a no-op with an empty name."""
    entity = _make_entity(coordinator)
    await entity.async_rename_segment(2, "")
    coordinator.device.set_segment_name.assert_not_called()


async def test_merge_segments(coordinator: MagicMock) -> None:
    """merge_segments forwards map id and the two segments."""
    entity = _make_entity(coordinator)
    await entity.async_merge_segments(map_id=1, segments=[2, 3])
    coordinator.device.merge_segments.assert_called_once_with(1, [2, 3])


async def test_merge_segments_skips_on_none(coordinator: MagicMock) -> None:
    """merge_segments is a no-op when segments is None."""
    entity = _make_entity(coordinator)
    await entity.async_merge_segments(map_id=1, segments=None)
    coordinator.device.merge_segments.assert_not_called()


async def test_split_segments(coordinator: MagicMock) -> None:
    """split_segments forwards map id, segment and line."""
    entity = _make_entity(coordinator)
    await entity.async_split_segments(map_id=1, segment=2, line=[0, 0, 5, 5])
    coordinator.device.split_segments.assert_called_once_with(1, 2, [0, 0, 5, 5])


async def test_split_segments_skips_on_missing(coordinator: MagicMock) -> None:
    """split_segments is a no-op when segment or line is missing."""
    entity = _make_entity(coordinator)
    await entity.async_split_segments(map_id=1, segment=None, line=None)
    coordinator.device.split_segments.assert_not_called()


# ---------------------------------------------------------------------------
# Cleaning sequence / custom cleaning
# ---------------------------------------------------------------------------


async def test_set_cleaning_sequence(coordinator: MagicMock) -> None:
    """set_cleaning_sequence forwards the order list."""
    entity = _make_entity(coordinator)
    await entity.async_set_cleaning_sequence([3, 1, 2])
    coordinator.device.set_cleaning_sequence.assert_called_once_with([3, 1, 2])


async def test_set_cleaning_sequence_skips_on_empty(coordinator: MagicMock) -> None:
    """set_cleaning_sequence is a no-op for an empty string."""
    entity = _make_entity(coordinator)
    await entity.async_set_cleaning_sequence("")
    coordinator.device.set_cleaning_sequence.assert_not_called()


async def test_set_custom_cleaning(coordinator: MagicMock) -> None:
    """set_custom_cleaning forwards every per-segment parameter."""
    entity = _make_entity(coordinator)
    await entity.async_set_custom_cleaning(
        segment_id=[1, 2],
        suction_level=[1, 2],
        water_volume=[1, 2],
        repeats=[1, 1],
        cleaning_mode=[0, 0],
        custom_mopping_route=[0, 0],
        cleaning_route=[1, 1],
        wetness_level=[5, 5],
    )
    coordinator.device.set_custom_cleaning.assert_called_once_with(
        [1, 2], [1, 2], [1, 2], [1, 1], [0, 0], [0, 0], [1, 1], [5, 5]
    )


async def test_set_custom_cleaning_skips_when_incomplete(coordinator: MagicMock) -> None:
    """set_custom_cleaning is a no-op if a required list is empty."""
    entity = _make_entity(coordinator)
    await entity.async_set_custom_cleaning(
        segment_id="",
        suction_level=[1],
        water_volume=[1],
        repeats=[1],
    )
    coordinator.device.set_custom_cleaning.assert_not_called()


async def test_set_custom_carpet_cleaning(coordinator: MagicMock) -> None:
    """set_custom_carpet_cleaning forwards id/type/cleaning/settings."""
    entity = _make_entity(coordinator)
    await entity.async_set_custom_carpet_cleaning(id=1, type=2, carpet_cleaning=1, carpet_settings=["a", "b"])
    coordinator.device.set_custom_carpet_cleaning.assert_called_once_with(1, 2, 1, ["a", "b"])


async def test_set_custom_carpet_cleaning_skips_when_incomplete(coordinator: MagicMock) -> None:
    """set_custom_carpet_cleaning is a no-op when id or type is empty."""
    entity = _make_entity(coordinator)
    await entity.async_set_custom_carpet_cleaning(id="", type=2)
    coordinator.device.set_custom_carpet_cleaning.assert_not_called()


# ---------------------------------------------------------------------------
# Property / action / misc services
# ---------------------------------------------------------------------------


async def test_set_property(coordinator: MagicMock) -> None:
    """set_property forwards key + value when both are present."""
    entity = _make_entity(coordinator)
    await entity.async_set_property("some_key", 5)
    coordinator.device.set_property_value.assert_called_once_with("some_key", 5)


async def test_set_property_skips_on_empty(coordinator: MagicMock) -> None:
    """set_property is a no-op for an empty value."""
    entity = _make_entity(coordinator)
    await entity.async_set_property("some_key", "")
    coordinator.device.set_property_value.assert_not_called()


async def test_call_action(coordinator: MagicMock) -> None:
    """call_action forwards key + value."""
    entity = _make_entity(coordinator)
    await entity.async_call_action("action_key", "payload")
    coordinator.device.call_action_value.assert_called_once_with("action_key", "payload")


async def test_call_action_default_value(coordinator: MagicMock) -> None:
    """call_action passes a default None value."""
    entity = _make_entity(coordinator)
    await entity.async_call_action("action_key")
    coordinator.device.call_action_value.assert_called_once_with("action_key", None)


async def test_call_action_skips_on_empty_key(coordinator: MagicMock) -> None:
    """call_action is a no-op for an empty key."""
    entity = _make_entity(coordinator)
    await entity.async_call_action("")
    coordinator.device.call_action_value.assert_not_called()


async def test_install_voice_pack(coordinator: MagicMock) -> None:
    """install_voice_pack forwards lang/url/md5/size."""
    entity = _make_entity(coordinator)
    await entity.async_install_voice_pack("fr", "http://x/y", "deadbeef", 1024)
    coordinator.device.install_voice_pack.assert_called_once_with("fr", "http://x/y", "deadbeef", 1024)


async def test_rename_shortcut(coordinator: MagicMock) -> None:
    """rename_shortcut forwards id + name."""
    entity = _make_entity(coordinator)
    await entity.async_rename_shortcut(1, "Quick clean")
    coordinator.device.rename_shortcut.assert_called_once_with(1, "Quick clean")


async def test_rename_shortcut_skips_on_empty(coordinator: MagicMock) -> None:
    """rename_shortcut is a no-op for an empty name."""
    entity = _make_entity(coordinator)
    await entity.async_rename_shortcut(1, "")
    coordinator.device.rename_shortcut.assert_not_called()


async def test_set_obstacle_ignore(coordinator: MagicMock) -> None:
    """set_obstacle_ignore forwards x/y/flag."""
    entity = _make_entity(coordinator)
    await entity.async_set_obstacle_ignore(1.5, 2.5, True)
    coordinator.device.set_obstacle_ignore.assert_called_once_with(1.5, 2.5, True)


async def test_set_obstacle_ignore_skips_on_empty(coordinator: MagicMock) -> None:
    """set_obstacle_ignore is a no-op when a coordinate is empty."""
    entity = _make_entity(coordinator)
    await entity.async_set_obstacle_ignore("", 2.5, True)
    coordinator.device.set_obstacle_ignore.assert_not_called()


async def test_set_router_position(coordinator: MagicMock) -> None:
    """set_router_position forwards x/y."""
    entity = _make_entity(coordinator)
    await entity.async_set_router_position(10, 20)
    coordinator.device.set_router_position.assert_called_once_with(10, 20)


async def test_set_router_position_skips_on_empty(coordinator: MagicMock) -> None:
    """set_router_position is a no-op when a coordinate is empty."""
    entity = _make_entity(coordinator)
    await entity.async_set_router_position(10, "")
    coordinator.device.set_router_position.assert_not_called()


# ---------------------------------------------------------------------------
# Consumable reset
# ---------------------------------------------------------------------------


async def test_reset_consumable(coordinator: MagicMock) -> None:
    """reset_consumable maps the consumable to the reset action."""
    entity = _make_entity(coordinator)
    await entity.async_reset_consumable(CONSUMABLE_MAIN_BRUSH)
    coordinator.device.call_action.assert_called_once_with(DreameVacuumAction.RESET_MAIN_BRUSH)


async def test_reset_consumable_filter(coordinator: MagicMock) -> None:
    """reset_consumable maps the filter consumable to its action."""
    entity = _make_entity(coordinator)
    await entity.async_reset_consumable(CONSUMABLE_FILTER)
    coordinator.device.call_action.assert_called_once_with(DreameVacuumAction.RESET_FILTER)


async def test_reset_consumable_unknown_is_noop(coordinator: MagicMock) -> None:
    """An unknown consumable resets nothing (no matching action)."""
    entity = _make_entity(coordinator)
    await entity.async_reset_consumable("not_a_consumable")
    coordinator.device.call_action.assert_not_called()


def test_consumable_reset_action_table_consistency() -> None:
    """Every value in the reset table is a DreameVacuumAction."""
    assert CONSUMABLE_MAIN_BRUSH in CONSUMABLE_RESET_ACTION
    for action in CONSUMABLE_RESET_ACTION.values():
        assert isinstance(action, DreameVacuumAction)


# ---------------------------------------------------------------------------
# Segment helpers (_get_segments / async_get_segments / async_clean_segments)
# ---------------------------------------------------------------------------


def _make_segment(name: str, visibility: bool = True) -> MagicMock:
    seg = MagicMock()
    seg.name = name
    seg.visibility = visibility
    return seg


def _make_map_data(map_index: int, map_name: str, segments: dict) -> MagicMock:
    md = MagicMock()
    md.map_index = map_index
    md.map_name = map_name
    md.segments = segments
    return md


async def test_get_segments_empty_when_no_map(coordinator: MagicMock) -> None:
    """_get_segments returns [] when there is no map data."""
    coordinator.device.status.map_data_list = None
    entity = _make_entity(coordinator)
    assert await entity.async_get_segments() == []


async def test_get_segments_lists_visible_segments(coordinator: MagicMock) -> None:
    """_get_segments yields composite ids and skips hidden / index-less maps."""
    visible = _make_segment("Kitchen", visibility=True)
    hidden = _make_segment("Closet", visibility=False)
    good_map = _make_map_data(0, "Ground floor", {1: visible, 2: hidden})
    # A map with no index must be skipped entirely.
    indexless_map = _make_map_data(None, "Pending", {9: _make_segment("X")})
    coordinator.device.status.map_data_list = {0: good_map, 1: indexless_map}

    entity = _make_entity(coordinator)
    segments = await entity.async_get_segments()

    assert len(segments) == 1
    assert segments[0].id == "0_1"
    assert segments[0].name == "Kitchen"
    assert segments[0].group == "Ground floor"


def test_get_segments_skips_map_without_segments(coordinator: MagicMock) -> None:
    """A map whose segments attribute is None is skipped."""
    empty_map = _make_map_data(0, "Empty", None)
    coordinator.device.status.map_data_list = {0: empty_map}
    entity = _make_entity(coordinator)
    assert entity._get_segments() == []


async def test_clean_segments_filters_by_selected_map(coordinator: MagicMock) -> None:
    """async_clean_segments only cleans segments from the selected map."""
    selected = MagicMock()
    selected.map_index = 0
    coordinator.device.status.selected_map = selected
    entity = _make_entity(coordinator)

    # "0_1" belongs to the selected map, "1_2" does not -> only 1 is cleaned.
    await entity.async_clean_segments(["0_1", "1_2", "0_3"])
    coordinator.device.clean_segment.assert_called_once_with([1, 3])


async def test_clean_segments_no_selected_map(coordinator: MagicMock) -> None:
    """async_clean_segments is a no-op when no map is selected."""
    coordinator.device.status.selected_map = None
    entity = _make_entity(coordinator)
    await entity.async_clean_segments(["0_1"])
    coordinator.device.clean_segment.assert_not_called()


async def test_clean_segments_selected_map_without_index(coordinator: MagicMock) -> None:
    """async_clean_segments is a no-op when the selected map has no index."""
    selected = MagicMock()
    selected.map_index = None
    coordinator.device.status.selected_map = selected
    entity = _make_entity(coordinator)
    await entity.async_clean_segments(["0_1"])
    coordinator.device.clean_segment.assert_not_called()


async def test_clean_segments_none_match(coordinator: MagicMock) -> None:
    """async_clean_segments cleans nothing when no id matches the selected map."""
    selected = MagicMock()
    selected.map_index = 0
    coordinator.device.status.selected_map = selected
    entity = _make_entity(coordinator)
    await entity.async_clean_segments(["1_5", "2_6"])
    coordinator.device.clean_segment.assert_not_called()


# ---------------------------------------------------------------------------
# Module-level lookup tables
# ---------------------------------------------------------------------------


def test_suction_level_to_fan_speed_table() -> None:
    """The suction-level table maps every level to its fan-speed label."""
    assert SUCTION_LEVEL_TO_FAN_SPEED == {
        DreameVacuumSuctionLevel.QUIET: FAN_SPEED_SILENT,
        DreameVacuumSuctionLevel.STANDARD: FAN_SPEED_STANDARD,
        DreameVacuumSuctionLevel.STRONG: FAN_SPEED_STRONG,
        DreameVacuumSuctionLevel.TURBO: FAN_SPEED_TURBO,
    }


# ---------------------------------------------------------------------------
# async_setup_entry — service registration + entity creation
# ---------------------------------------------------------------------------


async def test_async_setup_entry_registers_services_and_entity(coordinator: MagicMock) -> None:
    """Setup registers every entity service and adds a single DreameVacuum.

    ``async_setup_entry`` reads the current platform from a ContextVar and calls
    ``async_register_entity_service`` once per custom service. We swap in a mock
    platform, drive setup, and assert on the registrations + the entity added.
    """
    entry = MagicMock()
    entry.runtime_data.coordinator = coordinator

    platform = MagicMock()
    async_add_entities = MagicMock()
    hass = MagicMock()

    token = entity_platform.current_platform.set(platform)
    try:
        await async_setup_entry(hass, entry, async_add_entities)
    finally:
        entity_platform.current_platform.reset(token)

    # One registration per service declared in the platform module.
    assert platform.async_register_entity_service.call_count == 34

    # A handful of the registered service names, to anchor the mapping.
    registered = {call.args[0] for call in platform.async_register_entity_service.call_args_list}
    for service in (
        "vacuum_clean_zone",
        "vacuum_clean_segment",
        "vacuum_goto",
        "vacuum_merge_segments",
        "vacuum_set_property",
        "vacuum_call_action",
    ):
        assert service in registered

    # Exactly one entity is added, and it is our DreameVacuum.
    async_add_entities.assert_called_once()
    added = async_add_entities.call_args.args[0]
    assert len(added) == 1
    assert isinstance(added[0], DreameVacuum)


# ---------------------------------------------------------------------------
# VacuumActivity import fallback (older HA without the enum)
# ---------------------------------------------------------------------------


def test_activity_class_none_when_import_fails(coordinator: MagicMock) -> None:
    """If importing VacuumActivity fails, ``_activity_class`` is left None.

    Only the ``homeassistant.components.vacuum`` import is forced to fail (so
    other imports keep working). With no activity class, construction's
    ``_set_attrs`` takes the legacy ``_attr_state`` assignment which trips HA's
    ``report_usage`` telemetry (needs the frame helper); silence that hook too.
    """
    real_import_module = vacuum_module.importlib.import_module

    def _selective_import(name, *args, **kwargs):
        if name == "homeassistant.components.vacuum":
            raise ImportError(name)
        return real_import_module(name, *args, **kwargs)

    with (
        patch("homeassistant.components.vacuum.report_usage"),
        patch.object(vacuum_module.importlib, "import_module", side_effect=_selective_import),
    ):
        entity = DreameVacuum(coordinator)
    assert entity._activity_class is None


# ---------------------------------------------------------------------------
# _check_segments_changed (CLEAN_AREA path, HA >= 2025)
# ---------------------------------------------------------------------------
#
# ``_check_segments_changed`` records a baseline set of cleanable segment ids the
# first time a map is seen and raises a repair issue whenever the set changes
# afterwards. The ``CLEAN_AREA``-gated call lives in ``_handle_coordinator_update``
# (only active on HA builds that expose ``VacuumEntityFeature.CLEAN_AREA``).


def _entity_with_segment_check(coordinator: MagicMock) -> DreameVacuum:
    """Entity whose issue-creation hook is mocked to isolate the detection logic."""
    entity = _make_entity(coordinator)
    entity.async_create_segments_issue = MagicMock()
    return entity


def test_check_segments_changed_records_baseline_first_time(coordinator: MagicMock) -> None:
    """First sighting records the baseline set and raises no issue."""
    seg = _make_segment("Kitchen")
    coordinator.device.status.map_data_list = {0: _make_map_data(0, "Floor", {1: seg})}
    entity = _entity_with_segment_check(coordinator)
    assert entity.last_seen_segments is None

    entity._check_segments_changed()

    assert entity.last_seen_segments == {"0_1"}
    entity.async_create_segments_issue.assert_not_called()


def test_check_segments_changed_noop_when_no_segments(coordinator: MagicMock) -> None:
    """No map / no visible segments -> no baseline recorded, no issue."""
    coordinator.device.status.map_data_list = None
    entity = _entity_with_segment_check(coordinator)

    entity._check_segments_changed()

    assert entity.last_seen_segments is None
    entity.async_create_segments_issue.assert_not_called()


def test_check_segments_changed_noop_when_unchanged(coordinator: MagicMock) -> None:
    """Identical segment ids before/after -> no repair issue is raised."""
    seg = _make_segment("Kitchen")
    coordinator.device.status.map_data_list = {0: _make_map_data(0, "Floor", {1: seg})}
    entity = _entity_with_segment_check(coordinator)
    entity.last_seen_segments = {"0_1"}

    entity._check_segments_changed()

    entity.async_create_segments_issue.assert_not_called()
    assert entity.last_seen_segments == {"0_1"}


def test_check_segments_changed_creates_issue_on_change(coordinator: MagicMock) -> None:
    """Differing segment ids -> a repair issue is created and the baseline updates."""
    seg = _make_segment("Kitchen")
    coordinator.device.status.map_data_list = {0: _make_map_data(0, "Floor", {1: seg})}
    entity = _entity_with_segment_check(coordinator)
    entity.last_seen_segments = {"0_99"}

    entity._check_segments_changed()

    entity.async_create_segments_issue.assert_called_once()
    assert entity.last_seen_segments == {"0_1"}


def test_handle_coordinator_update_runs_segment_check_when_enabled(coordinator: MagicMock) -> None:
    """With CLEAN_AREA enabled the update hook routes through the segment check."""
    seg = _make_segment("Kitchen")
    coordinator.device.status.map_data_list = {0: _make_map_data(0, "Floor", {1: seg})}
    entity = _entity_with_segment_check(coordinator)
    entity.last_seen_segments = {"0_99"}
    entity.async_write_ha_state = MagicMock()

    # Force the CLEAN_AREA feature flag truthy so the gated branch executes.
    with patch.object(vacuum_module, "CLEAN_AREA_ENTITY_FEATURE", 1):
        entity._handle_coordinator_update()

    entity.async_create_segments_issue.assert_called_once()
    entity.async_write_ha_state.assert_called_once()


def test_handle_coordinator_update_skips_segment_check_when_disabled(coordinator: MagicMock) -> None:
    """With CLEAN_AREA absent (==0) the segment check is not invoked."""
    entity = _entity_with_segment_check(coordinator)
    entity._check_segments_changed = MagicMock()
    entity.async_write_ha_state = MagicMock()

    with patch.object(vacuum_module, "CLEAN_AREA_ENTITY_FEATURE", 0):
        entity._handle_coordinator_update()

    entity._check_segments_changed.assert_not_called()
    entity.async_write_ha_state.assert_called_once()


def test_async_create_segments_issue_calls_issue_registry(coordinator: MagicMock) -> None:
    """async_create_segments_issue raises a WARNING repair issue via the registry."""
    entity = _make_entity(coordinator)
    entity.hass = MagicMock()

    with patch.object(vacuum_module, "async_create_issue") as mock_create:
        entity.async_create_segments_issue()

    mock_create.assert_called_once()
    _args, kwargs = mock_create.call_args
    assert kwargs["translation_key"] == "segments_changed"
    assert kwargs["severity"] == vacuum_module.IssueSeverity.WARNING
    assert "device_name" in kwargs["translation_placeholders"]


class Segment_double:
    """Minimal stand-in carrying just the ``id`` attribute read by the check."""

    def __init__(self, seg_id: str) -> None:
        self.id = seg_id
