"""Exhaustive unit tests for ``coordinator.py``.

These tests exercise the ``DreameVacuumDataUpdateCoordinator`` end to end without
any network access: the heavy ``DreameVacuumDevice`` is always replaced by a rich
``MagicMock`` (either by patching the symbol the coordinator imports, for the
``__init__`` path, or by assigning ``coord._device`` directly for the targeted
method tests built via ``object.__new__``).

No source file under ``custom_components/**`` is modified. Fixtures are local to
this module per the test brief.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components import persistent_notification
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
)
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import pytest

from custom_components.dreame_vacuum.const import (
    CONF_AUTH_KEY,
    CONF_HIDDEN_MAP_OBJECTS,
    CONF_MAP_OBJECTS,
    CONF_VERSION,
    CONSUMABLE_MAIN_BRUSH,
    DOMAIN,
    EVENT_INFORMATION,
    EVENT_WARNING,
    MAP_OBJECTS,
    NOTIFICATION_ID_CLEANING_PAUSED,
    NOTIFICATION_ID_CLEANUP_COMPLETED,
    NOTIFICATION_ID_CONSUMABLE,
    NOTIFICATION_ID_DRAINAGE_STATUS,
    NOTIFICATION_ID_DUST_COLLECTION,
    NOTIFICATION_ID_ERROR,
    NOTIFICATION_ID_INFORMATION,
    NOTIFICATION_ID_LOW_WATER,
    NOTIFICATION_ID_REPLACE_TEMPORARY_MAP,
    NOTIFICATION_ID_WARNING,
)
from custom_components.dreame_vacuum.coordinator import DreameVacuumDataUpdateCoordinator
from custom_components.dreame_vacuum.dreame import VERSION, DreameVacuumProperty
from custom_components.dreame_vacuum.dreame.exceptions import RateLimitError

# Path to the symbol that ``__init__`` instantiates; patching it keeps the
# coordinator construction fully offline.
_DEVICE_PATH = "custom_components.dreame_vacuum.coordinator.DreameVacuumDevice"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _make_status(**overrides) -> MagicMock:
    """Return a status mock with sensible, all-clear defaults."""
    status = MagicMock()
    status.auto_emptying_not_performed = False
    status.cleaning_paused = False
    status.battery_level = 100
    status.dnd_remaining = 0
    status.cleanup_completed = False
    status.fast_mapping = False
    status.cruising = False
    status.job = {"status": "completed"}
    status.has_warning = False
    status.has_error = False
    status.error = SimpleNamespace(value=0)
    status.error_description = ["No error", ""]
    status.error_image = None
    status.has_temporary_map = False
    status.multi_map = False
    status.low_water_warning = SimpleNamespace(value=0)
    status.low_water = False
    status.low_water_warning_name_description = ["No warning", ""]
    status.draining_complete = False
    status.drainage_status = SimpleNamespace(value=0)
    status.washing = False
    status.started = False
    for key, value in overrides.items():
        setattr(status, key, value)
    return status


def _make_capability(**overrides) -> MagicMock:
    cap = MagicMock()
    cap.disable_sensor_cleaning = True
    cap.self_wash_base = False
    cap.deodorizer = False
    cap.wheel = False
    cap.scale_inhibitor = False
    for key, value in overrides.items():
        setattr(cap, key, value)
    return cap


def _make_device(**overrides) -> MagicMock:
    """Return a rich device mock that never touches the network."""
    device = MagicMock()
    device.name = "Test Vacuum"
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.host = "192.168.1.100"
    device.token = "a" * 32
    device.available = True
    device.device_connected = True
    device.cloud_connected = True
    device.disconnected = False
    device.auth_failed = False
    device.cloud_auth_key = None
    device.status = _make_status()
    device.capability = _make_capability()
    device.update = MagicMock()
    device.listen = MagicMock()
    device.listen_error = MagicMock()
    device.schedule_update = MagicMock()
    device.disconnect = MagicMock()
    device.clear_warning = MagicMock()
    device.get_property = MagicMock(return_value=50)
    device.consumable_life_warning_description = MagicMock(return_value=None)
    device.status.consumable_life_warning_description = MagicMock(return_value=None)
    for key, value in overrides.items():
        setattr(device, key, value)
    return device


def _fake_hass() -> MagicMock:
    """A MagicMock hass that runs executor jobs inline.

    This project runs with ``-p no:homeassistant`` (see pyproject.toml), so the
    real ``hass`` fixture is unavailable and every test uses a MagicMock hass —
    matching ``tests/test_config_flow.py``. ``async_add_executor_job`` executes
    the target inline so blocking device calls (``update``, ``clear_warning``)
    actually run; ``call_soon_threadsafe`` is a MagicMock so deferred scheduling
    can be asserted synchronously.
    """
    hass = MagicMock()
    hass.config.language = "en"
    hass.loop.call_soon_threadsafe = MagicMock()
    hass.async_create_task = MagicMock()

    async def _run_executor_job(func, *args):
        return func(*args)

    hass.async_add_executor_job = AsyncMock(side_effect=_run_executor_job)
    return hass


@pytest.fixture
def coord_entry():
    """A config-entry-like object matching the coordinator's expectations.

    A lightweight stand-in (not a real MockConfigEntry, which needs a real hass)
    that exposes ``.data`` / ``.options`` dicts the coordinator reads, plus an
    ``entry_id``. Option migration writes are routed through
    ``hass.config_entries.async_update_entry`` which the tests stub.
    """
    return SimpleNamespace(
        data={
            CONF_NAME: "Test Vacuum",
            CONF_HOST: "192.168.1.100",
            CONF_TOKEN: "a" * 32,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "password",
            "country": "eu",
            "mac": "AA:BB:CC:DD:EE:FF",
            "did": "123456789",
            "account_type": "dreame",
        },
        options={"notify": True},
        entry_id="entry123",
        unique_id="aa:bb:cc:dd:ee:ff",
    )


def _bare_coordinator(device: MagicMock | None = None, *, notify=True) -> DreameVacuumDataUpdateCoordinator:
    """Construct a coordinator instance without running the heavy __init__.

    Mirrors the ``_coordinator()`` helper already used in
    ``test_passe2_passe3_fixes.py`` but with a richer hass + device so that the
    notification / event paths can be exercised. ``hass.loop.call_soon_threadsafe``
    is a plain MagicMock so deferred calls can be asserted synchronously.
    """
    coord: DreameVacuumDataUpdateCoordinator = object.__new__(DreameVacuumDataUpdateCoordinator)
    coord.hass = _fake_hass()
    coord.update_interval = timedelta(seconds=300)
    coord._default_update_interval = timedelta(seconds=300)
    coord._device = device if device is not None else _make_device()
    coord._token = "a" * 32
    coord._host = "192.168.1.100"
    coord._auth_key = None
    coord._entry = MagicMock()
    coord._entry.data = {
        CONF_HOST: "192.168.1.100",
        CONF_TOKEN: "a" * 32,
        CONF_PASSWORD: "password",
    }
    coord._entry.entry_id = "entry123"
    coord._notify = notify
    coord._ready = False
    coord._available = False
    coord._has_warning = False
    coord._has_temporary_map = None
    coord._low_water = False
    coord._drainage_status = None
    coord._washing = None
    return coord


# --------------------------------------------------------------------------- #
# __init__ / option migration
# --------------------------------------------------------------------------- #
#
# The parent ``DataUpdateCoordinator.__init__`` requires HA's frame helper, which
# is only set up by the (disabled) real ``hass`` fixture. We therefore stub the
# parent constructor with a no-op that records the call and assigns ``self.hass``,
# leaving the coordinator's OWN __init__ body (migration + device construction +
# listener registration + dispatcher connect) to run for real against a MagicMock
# hass — consistent with the rest of this suite.


class _ParentInit:
    """Context manager patching DataUpdateCoordinator.__init__ to a recording stub."""

    def __init__(self, hass):
        self._hass = hass
        self.calls = []

    def __enter__(self):
        outer = self

        def _stub(self, hass, *args, **kwargs):
            self.hass = outer._hass
            outer.calls.append(kwargs)

        self._patch = patch.object(DataUpdateCoordinator, "__init__", _stub)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        return False


def _build_coordinator(hass, entry, device):
    with _ParentInit(hass) as parent, patch(_DEVICE_PATH, return_value=device) as device_cls:
        coordinator = DreameVacuumDataUpdateCoordinator(hass, entry=entry)
    return coordinator, parent, device_cls


def test_init_registers_listeners_and_dispatcher(coord_entry):
    """The constructor wires the device listeners, the error listener and the
    persistent-notification dispatcher; no migration runs when version matches."""
    hass = _fake_hass()
    coord_entry.options = {**coord_entry.options, CONF_VERSION: VERSION}
    device = _make_device()

    coordinator, parent, device_cls = _build_coordinator(hass, coord_entry, device)

    # Device constructed exactly once with the entry's name as first positional arg.
    device_cls.assert_called_once()
    assert device_cls.call_args.args[0] == "Test Vacuum"

    # 7 per-property listens + 1 push listen = 8 listen calls.
    assert device.listen.call_count == 8
    device.listen_error.assert_called_once_with(coordinator.set_update_error)
    listened_props = [c.args[1] for c in device.listen.call_args_list if len(c.args) > 1]
    assert DreameVacuumProperty.DUST_COLLECTION in listened_props
    assert DreameVacuumProperty.ERROR in listened_props

    # Version already current -> no option-migration write.
    hass.config_entries.async_update_entry.assert_not_called()

    # The slow safety-net poll interval is passed to the parent constructor.
    assert parent.calls[0]["update_interval"] == timedelta(seconds=300)
    assert coordinator.device is device
    assert coordinator._unsub_dispatcher is not None


def test_init_migrates_map_objects_to_hidden(coord_entry):
    """Legacy CONF_MAP_OBJECTS with a stale version is converted to
    CONF_HIDDEN_MAP_OBJECTS and the current version is stamped, via a single
    async_update_entry call."""
    hass = _fake_hass()
    coord_entry.options = {"notify": True, CONF_MAP_OBJECTS: ["color"]}  # only "color" visible
    device = _make_device()

    _build_coordinator(hass, coord_entry, device)

    hass.config_entries.async_update_entry.assert_called_once()
    written = hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert written[CONF_VERSION] == VERSION
    assert CONF_MAP_OBJECTS not in written
    assert CONF_HIDDEN_MAP_OBJECTS in written
    # color was visible -> not hidden; curtain/ramp are never auto-hidden.
    assert "color" not in written[CONF_HIDDEN_MAP_OBJECTS]
    assert "curtain" not in written[CONF_HIDDEN_MAP_OBJECTS]
    assert "ramp" not in written[CONF_HIDDEN_MAP_OBJECTS]
    assert "name" in written[CONF_HIDDEN_MAP_OBJECTS]  # genuinely omitted -> hidden
    expected_hidden = {k for k in MAP_OBJECTS if k not in ("color", "curtain", "ramp")}
    assert set(written[CONF_HIDDEN_MAP_OBJECTS]) == expected_hidden


def test_init_migration_skipped_when_hidden_already_present(coord_entry):
    """If CONF_HIDDEN_MAP_OBJECTS already exists, the legacy CONF_MAP_OBJECTS is
    left untouched (the conversion guard short-circuits) but the version is still
    stamped."""
    hass = _fake_hass()
    coord_entry.options = {
        "notify": True,
        CONF_MAP_OBJECTS: ["color"],
        CONF_HIDDEN_MAP_OBJECTS: ["name"],
    }
    _build_coordinator(hass, coord_entry, _make_device())

    written = hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert written[CONF_VERSION] == VERSION
    # Conversion did not run: legacy key preserved, hidden list unchanged.
    assert written[CONF_MAP_OBJECTS] == ["color"]
    assert written[CONF_HIDDEN_MAP_OBJECTS] == ["name"]


def test_init_version_bump_without_map_objects(coord_entry):
    """A stale version with no legacy map objects just stamps the version (no
    CONF_HIDDEN_MAP_OBJECTS is fabricated)."""
    hass = _fake_hass()
    coord_entry.options = {"notify": True, CONF_VERSION: "v0.0.0-old"}
    _build_coordinator(hass, coord_entry, _make_device())

    written = hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert written[CONF_VERSION] == VERSION
    assert CONF_HIDDEN_MAP_OBJECTS not in written


def test_init_reads_auth_key_and_notify_from_entry(coord_entry):
    """auth_key and notify options are captured off the entry at construction."""
    hass = _fake_hass()
    coord_entry.data = {**coord_entry.data, CONF_AUTH_KEY: "stored-key"}
    coord_entry.options = {"notify": ["error"], CONF_VERSION: VERSION}

    coordinator, _, _ = _build_coordinator(hass, coord_entry, _make_device())

    assert coordinator._auth_key == "stored-key"
    assert coordinator._notify == ["error"]


def test_init_passes_all_credentials_to_device(coord_entry):
    """The device is constructed with host/token/mac/username/password/country/
    prefer_cloud/account_type/did/auth_key drawn from the entry."""
    hass = _fake_hass()
    coord_entry.options = {"notify": True, CONF_VERSION: VERSION}
    device = _make_device()
    _, _, device_cls = _build_coordinator(hass, coord_entry, device)

    args = device_cls.call_args.args
    # name, host, token, mac, username, password, country, prefer_cloud,
    # account_type, did, auth_key
    assert args[0] == "Test Vacuum"
    assert args[1] == "192.168.1.100"  # host
    assert args[2] == "a" * 32  # token
    assert args[3] == "AA:BB:CC:DD:EE:FF"  # mac
    assert args[4] == "test@example.com"  # username
    assert args[6] == "eu"  # country
    assert args[8] == "dreame"  # account_type
    assert args[9] == "123456789"  # did


# --------------------------------------------------------------------------- #
# _async_update_data
# --------------------------------------------------------------------------- #


async def test_update_data_success_returns_device():
    coord = _bare_coordinator()
    coord._device.disconnected = False
    coord._device.auth_failed = False
    with patch.object(DreameVacuumDataUpdateCoordinator, "async_set_updated_data") as set_data:
        result = await coord._async_update_data()
    assert result is coord._device
    coord._device.update.assert_called_once()  # ran via executor (AsyncMock awaited)
    coord._device.schedule_update.assert_called_once()
    set_data.assert_called_once()


async def test_update_data_restores_default_interval_after_backoff():
    coord = _bare_coordinator()
    coord.update_interval = timedelta(seconds=90)  # was backed off
    with patch.object(DreameVacuumDataUpdateCoordinator, "async_set_updated_data"):
        await coord._async_update_data()
    assert coord.update_interval == coord._default_update_interval


async def test_update_data_device_none_raises_update_failed():
    coord = _bare_coordinator()
    coord._device = None
    with pytest.raises(UpdateFailed, match="not initialized"):
        await coord._async_update_data()


async def test_update_data_auth_failed_raises_config_entry_auth_failed():
    coord = _bare_coordinator()
    coord._device.disconnected = False
    coord._device.auth_failed = True
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()
    # The listener is torn down and the device disconnected before raising.
    coord._device.listen.assert_called_once_with(None)
    coord._device.disconnect.assert_called_once()


async def test_update_data_disconnected_after_update_raises_update_failed():
    coord = _bare_coordinator()
    coord._device.disconnected = True
    with pytest.raises(UpdateFailed, match="disconnected during update"):
        await coord._async_update_data()


async def test_update_data_rate_limit_backs_off_interval():
    coord = _bare_coordinator()
    coord.hass.async_add_executor_job = AsyncMock(side_effect=RateLimitError(retry_after=120))
    with pytest.raises(UpdateFailed, match="Rate limited"):
        await coord._async_update_data()
    assert coord.update_interval == timedelta(seconds=120)
    assert coord._device is not None  # device preserved


async def test_update_data_generic_error_keeps_device_and_wraps():
    coord = _bare_coordinator()
    coord._device.auth_failed = False
    coord.hass.async_add_executor_job = AsyncMock(side_effect=RuntimeError("boom"))
    device = coord._device
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert coord._device is device  # NOT destroyed on transient error


async def test_update_data_generic_error_with_auth_failed_becomes_config_entry_auth_failed():
    coord = _bare_coordinator()
    coord._device.auth_failed = True
    coord.hass.async_add_executor_job = AsyncMock(side_effect=RuntimeError("network blip"))
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()


async def test_update_data_config_entry_auth_failed_propagates_unwrapped():
    """A ConfigEntryAuthFailed raised inside the try-body must re-raise as-is,
    not be re-wrapped by the generic handler."""
    coord = _bare_coordinator()
    coord.hass.async_add_executor_job = AsyncMock(side_effect=ConfigEntryAuthFailed("direct"))
    with pytest.raises(ConfigEntryAuthFailed, match="direct"):
        await coord._async_update_data()


# --------------------------------------------------------------------------- #
# async_set_updated_data
# --------------------------------------------------------------------------- #


def test_set_updated_data_noop_without_status():
    coord = _bare_coordinator()
    coord._device.status = None
    with patch.object(DataUpdateCoordinator, "async_set_updated_data") as parent:
        coord.async_set_updated_data()
    parent.assert_not_called()


def test_set_updated_data_noop_without_device():
    coord = _bare_coordinator()
    coord._device = None
    with patch.object(DataUpdateCoordinator, "async_set_updated_data") as parent:
        coord.async_set_updated_data()
    parent.assert_not_called()


def test_set_updated_data_captures_host_token_and_purges_password():
    coord = _bare_coordinator()
    coord._device.host = "10.0.0.5"  # changed host
    coord._device.token = "b" * 32  # changed token
    coord._device.cloud_auth_key = "new-auth-key"
    coord._device.available = True
    coord.hass.config_entries.async_update_entry = MagicMock()

    with patch.object(DataUpdateCoordinator, "async_set_updated_data") as parent:
        coord.async_set_updated_data()

    assert coord._host == "10.0.0.5"
    assert coord._token == "b" * 32
    assert coord._auth_key == "new-auth-key"
    # Two update_entry calls: host/token, then auth_key (with password purge).
    assert coord.hass.config_entries.async_update_entry.call_count == 2
    last_data = coord.hass.config_entries.async_update_entry.call_args_list[-1].kwargs["data"]
    assert last_data[CONF_AUTH_KEY] == "new-auth-key"
    assert CONF_PASSWORD not in last_data  # purged
    parent.assert_called_once_with(coord._device)
    assert coord._ready is True


def test_set_updated_data_no_host_change_no_entry_update():
    coord = _bare_coordinator()
    # host/token unchanged, no cloud auth key -> no entry writes.
    coord._device.host = "192.168.1.100"
    coord._device.token = "a" * 32
    coord._device.cloud_auth_key = None
    coord.hass.config_entries.async_update_entry = MagicMock()
    with patch.object(DataUpdateCoordinator, "async_set_updated_data"):
        coord.async_set_updated_data()
    coord.hass.config_entries.async_update_entry.assert_not_called()


def test_set_updated_data_auth_key_without_password_in_entry():
    """When the entry has no stored password, the auth-key capture still writes
    the key but does not attempt to pop a missing password."""
    coord = _bare_coordinator()
    coord._entry.data = {CONF_HOST: "192.168.1.100", CONF_TOKEN: "a" * 32}  # no password
    coord._device.host = "192.168.1.100"
    coord._device.token = "a" * 32
    coord._device.cloud_auth_key = "k"
    coord.hass.config_entries.async_update_entry = MagicMock()
    with patch.object(DataUpdateCoordinator, "async_set_updated_data"):
        coord.async_set_updated_data()
    coord.hass.config_entries.async_update_entry.assert_called_once()
    data = coord.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert data[CONF_AUTH_KEY] == "k"


def test_set_updated_data_reauth_schedule_when_ready_and_auth_failed():
    """Once ready, a device that has since auth-failed triggers a reload (reauth)
    and returns before publishing data."""
    coord = _bare_coordinator()
    coord._ready = True
    coord._device.auth_failed = True
    coord.hass.config_entries.async_schedule_reload = MagicMock()
    with patch.object(DataUpdateCoordinator, "async_set_updated_data") as parent:
        coord.async_set_updated_data()
    coord.hass.config_entries.async_schedule_reload.assert_called_once_with("entry123")
    parent.assert_not_called()


def test_set_updated_data_logs_availability_transition():
    coord = _bare_coordinator()
    coord._ready = True
    coord._device.auth_failed = False
    coord._available = False
    coord._device.available = True
    with patch.object(DataUpdateCoordinator, "async_set_updated_data") as parent:
        coord.async_set_updated_data()
    assert coord._available is True
    parent.assert_called_once_with(coord._device)


def test_set_updated_data_fires_temporary_map_change():
    """A change in has_temporary_map drives the temporary-map notification path."""
    coord = _bare_coordinator()
    coord._ready = True
    coord._device.auth_failed = False
    coord._has_temporary_map = False
    coord._device.status.has_temporary_map = True
    coord._device.status.multi_map = False
    with patch.object(DataUpdateCoordinator, "async_set_updated_data"):
        coord.async_set_updated_data()
    assert coord._has_temporary_map is True
    # The temporary-map handler scheduled a create-notification + fired an event.
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 1


# --------------------------------------------------------------------------- #
# set_updated_data / set_update_error / async_set_update_error (thread bridges)
# --------------------------------------------------------------------------- #


def test_set_updated_data_bridge_defers_to_loop():
    coord = _bare_coordinator()
    sentinel = object()
    coord.set_updated_data(sentinel)
    coord.hass.loop.call_soon_threadsafe.assert_called_once_with(coord.async_set_updated_data, sentinel)


def test_set_update_error_bridge_defers_to_loop():
    coord = _bare_coordinator()
    err = RuntimeError("x")
    coord.set_update_error(err)
    coord.hass.loop.call_soon_threadsafe.assert_called_once_with(coord.async_set_update_error, err)


def test_async_set_update_error_publishes_when_was_available():
    coord = _bare_coordinator()
    coord._available = True
    coord._device.available = False  # now unavailable
    err = RuntimeError("down")
    with patch.object(DataUpdateCoordinator, "async_set_update_error") as parent:
        coord.async_set_update_error(err)
    assert coord._available is False
    parent.assert_called_once_with(err)


def test_async_set_update_error_noop_when_already_unavailable():
    coord = _bare_coordinator()
    coord._available = False
    with patch.object(DataUpdateCoordinator, "async_set_update_error") as parent:
        coord.async_set_update_error(RuntimeError("x"))
    parent.assert_not_called()


def test_async_set_update_error_stays_available_when_still_available():
    coord = _bare_coordinator()
    coord._available = True
    coord._device.available = True  # still up
    with patch.object(DataUpdateCoordinator, "async_set_update_error") as parent:
        coord.async_set_update_error(RuntimeError("x"))
    assert coord._available is True
    parent.assert_called_once()


# --------------------------------------------------------------------------- #
# cleanup
# --------------------------------------------------------------------------- #


def test_cleanup_unsubscribes_and_tears_down_device():
    coord = _bare_coordinator()
    unsub = MagicMock()
    coord._unsub_dispatcher = unsub
    coord._shared_proxy_renderer = object()
    device = coord._device
    coord.cleanup()
    unsub.assert_called_once()
    assert coord._unsub_dispatcher is None
    device.listen.assert_called_once_with(None)
    device.disconnect.assert_called_once()
    assert coord._device is None
    assert coord._shared_proxy_renderer is None


def test_cleanup_is_idempotent_without_dispatcher_or_device():
    coord = _bare_coordinator()
    coord._unsub_dispatcher = None
    coord._device = None
    coord.cleanup()  # must not raise
    assert coord._device is None


# --------------------------------------------------------------------------- #
# _notification_dismiss_listener  (deferred clear_warning via executor)
# --------------------------------------------------------------------------- #


def _notifications_without(coord, *ids) -> dict:
    """hass.data[persistent_notification.DOMAIN] missing the given notification keys."""
    return {}  # empty mapping -> every "<id> not in notifications" is True


def test_dismiss_listener_ignores_non_removed_updates():
    coord = _bare_coordinator()
    coord._has_warning = True
    coord.async_set_updated_data = MagicMock()
    coord._notification_dismiss_listener(persistent_notification.UpdateType.ADDED, None)
    coord.hass.async_create_task.assert_not_called()


def test_dismiss_listener_ignores_when_device_gone():
    coord = _bare_coordinator()
    coord._device = None
    coord._has_warning = True
    coord._notification_dismiss_listener(persistent_notification.UpdateType.REMOVED, None)
    coord.hass.async_create_task.assert_not_called()


def test_dismiss_listener_clears_warning_off_event_loop():
    """When the warning notification was removed by the user, clear_warning must be
    scheduled via async_create_task (which awaits the executor job), never run inline."""
    coord = _bare_coordinator(notify=True)
    coord._has_warning = True
    coord._device.status.has_warning = False
    coord.hass.data = {persistent_notification.DOMAIN: {}}  # warning id absent
    coord._notification_dismiss_listener(persistent_notification.UpdateType.REMOVED, None)
    # A clear-warning task was scheduled.
    assert coord.hass.async_create_task.call_count == 1
    assert coord.hass.async_create_task.call_args.kwargs["name"] == f"{DOMAIN}_clear_warning"
    # has_warning was refreshed from the device.
    assert coord._has_warning is False


async def test_async_clear_warning_uses_executor_job():
    """The coroutine scheduled by the dismiss listener offloads the blocking
    clear_warning() to the executor (it performs network I/O)."""
    coord = _bare_coordinator()
    await coord._async_clear_warning()
    coord.hass.async_add_executor_job.assert_awaited_once_with(coord._device.clear_warning)


def test_dismiss_listener_clears_low_water():
    coord = _bare_coordinator(notify=True)
    coord._low_water = True
    coord._device.status.low_water = False
    coord.hass.data = {persistent_notification.DOMAIN: {}}
    coord._notification_dismiss_listener(persistent_notification.UpdateType.REMOVED, None)
    assert coord.hass.async_create_task.call_count == 1
    assert coord._low_water is False


def test_dismiss_listener_clears_drainage_status():
    coord = _bare_coordinator(notify=True)
    coord._drainage_status = True
    coord._device.status.draining_complete = False
    coord.hass.data = {persistent_notification.DOMAIN: {}}
    coord._notification_dismiss_listener(persistent_notification.UpdateType.REMOVED, None)
    assert coord.hass.async_create_task.call_count == 1
    assert coord._drainage_status is False


def test_dismiss_listener_respects_notify_list_filter():
    """When notify is a list lacking the warning category, the dismiss listener
    refreshes the flag but does NOT schedule clear_warning."""
    coord = _bare_coordinator(notify=["error"])  # no NOTIFICATION_ID_WARNING
    coord._has_warning = True
    coord._device.status.has_warning = False
    coord.hass.data = {persistent_notification.DOMAIN: {}}
    coord._notification_dismiss_listener(persistent_notification.UpdateType.REMOVED, None)
    coord.hass.async_create_task.assert_not_called()
    assert coord._has_warning is False


def test_dismiss_listener_noop_when_notification_still_present():
    """If the warning notification is still present, nothing is cleared."""
    coord = _bare_coordinator(notify=True)
    coord._has_warning = True
    key = f"{DOMAIN}_{coord._device.mac}_{NOTIFICATION_ID_WARNING}"
    coord.hass.data = {persistent_notification.DOMAIN: {key: object()}}
    coord._notification_dismiss_listener(persistent_notification.UpdateType.REMOVED, None)
    coord.hass.async_create_task.assert_not_called()
    assert coord._has_warning is True  # untouched


# --------------------------------------------------------------------------- #
# _fire_event
# --------------------------------------------------------------------------- #


def test_fire_event_includes_entity_id_and_payload():
    coord = _bare_coordinator()
    coord._fire_event(EVENT_WARNING, {EVENT_WARNING: "boom", "code": 7})
    args = coord.hass.loop.call_soon_threadsafe.call_args.args
    assert args[0] is coord.hass.bus.async_fire
    assert args[1] == f"{DOMAIN}_{EVENT_WARNING}"
    payload = args[2]
    assert payload["entity_id"] == "vacuum.test_vacuum"
    assert payload[EVENT_WARNING] == "boom"
    assert payload["code"] == 7


def test_fire_event_without_data():
    coord = _bare_coordinator()
    coord._fire_event(EVENT_INFORMATION, None)
    args = coord.hass.loop.call_soon_threadsafe.call_args.args
    assert set(args[2].keys()) == {"entity_id"}


# --------------------------------------------------------------------------- #
# Notification property-change listeners
# --------------------------------------------------------------------------- #


def test_dust_collection_changed_creates_and_clears():
    coord = _bare_coordinator()
    coord._device.status.auto_emptying_not_performed = True
    coord._dust_collection_changed()
    # Event fired + persistent notification create scheduled.
    assert coord.hass.loop.call_soon_threadsafe.call_count == 2

    coord.hass.loop.call_soon_threadsafe.reset_mock()
    coord._device.status.auto_emptying_not_performed = False
    coord._dust_collection_changed()
    # Just the dismissal.
    assert coord.hass.loop.call_soon_threadsafe.call_count == 1


def test_cleaning_paused_changed_low_battery():
    coord = _bare_coordinator()
    coord._device.status.cleaning_paused = True
    coord._device.status.battery_level = 50  # < 80 branch
    coord._cleaning_paused_changed()
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2  # event + create


def test_cleaning_paused_changed_high_battery_with_dnd_timer():
    coord = _bare_coordinator()
    coord._device.status.cleaning_paused = True
    coord._device.status.battery_level = 90  # >= 80
    coord._device.status.dnd_remaining = 3700  # 1h 1min -> exercises math + timer message
    coord._cleaning_paused_changed()
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2


def test_cleaning_paused_changed_high_battery_no_dnd():
    coord = _bare_coordinator()
    coord._device.status.cleaning_paused = True
    coord._device.status.battery_level = 95
    coord._device.status.dnd_remaining = 0  # falsy -> skip timer branch
    coord._cleaning_paused_changed()
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2


def test_cleaning_paused_changed_resumed_dismisses():
    coord = _bare_coordinator()
    coord._device.status.cleaning_paused = False
    coord._cleaning_paused_changed()
    coord.hass.loop.call_soon_threadsafe.assert_called_once()  # dismiss only


def test_task_status_changed_cleanup_completed_runs_consumable_check():
    coord = _bare_coordinator()
    coord._device.status.cleanup_completed = True
    with patch.object(coord, "_check_consumables") as check:
        coord._task_status_changed(previous_value=2)
    check.assert_called_once()
    # task-status event + cleanup-completed notification scheduled.
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2


def test_task_status_changed_started_from_idle_fires_event():
    coord = _bare_coordinator()
    coord._device.status.cleanup_completed = False
    coord._device.status.fast_mapping = False
    coord._device.status.cruising = False
    coord._task_status_changed(previous_value=0)  # idle -> active
    coord.hass.loop.call_soon_threadsafe.assert_called_once()  # task-status event


def test_task_status_changed_started_fast_mapping_no_event():
    coord = _bare_coordinator()
    coord._device.status.cleanup_completed = False
    coord._device.status.fast_mapping = True  # suppresses the event
    coord._task_status_changed(previous_value=0)
    coord.hass.loop.call_soon_threadsafe.assert_not_called()


def test_task_status_changed_first_observation_checks_consumables():
    coord = _bare_coordinator()
    with patch.object(coord, "_check_consumables") as check:
        coord._task_status_changed(previous_value=None)  # first time
    check.assert_called_once()


def test_error_changed_warning_with_image_and_long_description():
    coord = _bare_coordinator()
    coord._device.status.has_warning = True
    coord._device.status.has_error = False
    coord._device.status.error = SimpleNamespace(value=11)
    coord._device.status.error_description = ["Wheels are suspended", "Please reposition the robot and restart."]
    coord._device.status.error_image = "BASE64IMG"
    coord._error_changed()
    assert coord._has_warning is True
    # warning event + create notification.
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2


def test_error_changed_clears_previous_warning():
    coord = _bare_coordinator()
    coord._has_warning = True  # had a warning before
    coord._device.status.has_warning = False
    coord._device.status.has_error = False
    coord._error_changed()
    assert coord._has_warning is False
    coord.hass.loop.call_soon_threadsafe.assert_called_once()  # dismissal


def test_error_changed_error_path_with_image():
    coord = _bare_coordinator()
    coord._device.status.has_warning = False
    coord._device.status.has_error = True
    coord._device.status.error = SimpleNamespace(value=42)
    coord._device.status.error_description = ["Dust bin not installed", "Please install the dust bin and filter."]
    coord._device.status.error_image = "IMG"
    coord._error_changed()
    # error event + create notification (id suffixed by error value).
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2


def test_has_temporary_map_changed_present_multi_map():
    coord = _bare_coordinator()
    coord._device.status.has_temporary_map = True
    coord._device.status.multi_map = True
    coord._has_temporary_map_changed()
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2  # event + create


def test_has_temporary_map_changed_absent():
    coord = _bare_coordinator()
    coord._device.status.has_temporary_map = False
    coord._has_temporary_map_changed()
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2  # event + dismiss


def test_low_water_warning_changed_fires_and_creates():
    coord = _bare_coordinator()
    coord._device.status.low_water_warning = SimpleNamespace(value=2)
    coord._device.status.low_water_warning_name_description = [
        "Clean water tank empty",
        "Please check the clean water tank.",
    ]
    coord._device.status.low_water = True
    coord._low_water_warning_changed(previous_value=0)
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2
    assert coord._low_water is True


def test_low_water_warning_changed_clears_when_resolved():
    coord = _bare_coordinator()
    coord._low_water = True  # had a low-water warning
    coord._device.status.low_water_warning = SimpleNamespace(value=0)
    coord._device.status.low_water = False
    coord._low_water_warning_changed(previous_value=2)
    coord.hass.loop.call_soon_threadsafe.assert_called_once()  # dismissal
    assert coord._low_water is False


def test_low_water_warning_changed_short_description_no_body():
    """value>1 with a <=2 char body skips the body-append branch but still notifies."""
    coord = _bare_coordinator()
    coord._device.status.low_water_warning = SimpleNamespace(value=2)
    coord._device.status.low_water_warning_name_description = ["Title", ""]
    coord._device.status.low_water = True
    coord._low_water_warning_changed(previous_value=1)
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2


def test_drainage_status_changed_success():
    coord = _bare_coordinator()
    coord._device.status.draining_complete = True
    coord._device.status.drainage_status = SimpleNamespace(value=2)  # success
    coord._drainage_status_changed()
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2
    assert coord._drainage_status is True


def test_drainage_status_changed_failure():
    coord = _bare_coordinator()
    coord._device.status.draining_complete = True
    coord._device.status.drainage_status = SimpleNamespace(value=1)  # not 2 -> failure branch
    coord._drainage_status_changed()
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2


def test_drainage_status_changed_clears_when_done():
    coord = _bare_coordinator()
    coord._drainage_status = True
    coord._device.status.draining_complete = False
    coord._drainage_status_changed()
    coord.hass.loop.call_soon_threadsafe.assert_called_once()  # dismissal
    assert coord._drainage_status is False


def test_self_wash_base_status_changed_triggers_consumables():
    coord = _bare_coordinator()
    coord._washing = False
    coord._device.status.washing = True  # changed
    coord._device.status.started = True
    with patch.object(coord, "_check_consumables") as check:
        coord._self_wash_base_status_changed()
    check.assert_called_once()
    assert coord._washing is True


def test_self_wash_base_status_changed_no_trigger_when_unchanged():
    coord = _bare_coordinator()
    coord._washing = True
    coord._device.status.washing = True  # unchanged
    coord._device.status.started = True
    with patch.object(coord, "_check_consumables") as check:
        coord._self_wash_base_status_changed()
    check.assert_not_called()


def test_self_wash_base_status_changed_initial_none():
    coord = _bare_coordinator()
    coord._washing = None  # first observation -> only records, no check
    coord._device.status.washing = True
    with patch.object(coord, "_check_consumables") as check:
        coord._self_wash_base_status_changed()
    check.assert_not_called()
    assert coord._washing is True


# --------------------------------------------------------------------------- #
# _check_consumable / _check_consumables / repair issues
# --------------------------------------------------------------------------- #


def test_check_consumable_ok_clears_repair_issue():
    coord = _bare_coordinator()
    coord._device.status.consumable_life_warning_description = MagicMock(return_value=None)
    coord.hass.loop.call_soon_threadsafe = MagicMock()
    coord._check_consumable(CONSUMABLE_MAIN_BRUSH, "replace_main_brush", DreameVacuumProperty.MAIN_BRUSH_LEFT)
    # Only the async_delete_issue is scheduled via call_soon_threadsafe.
    coord.hass.loop.call_soon_threadsafe.assert_called_once()


def test_check_consumable_warning_fires_event_and_notifies():
    coord = _bare_coordinator()
    coord._device.status.consumable_life_warning_description = MagicMock(
        return_value=["Main brush", "Replace the main brush."]
    )
    coord._device.get_property = MagicMock(return_value=15)  # > 0 -> no repair issue
    with patch("custom_components.dreame_vacuum.dreame.resources.CONSUMABLE_IMAGE", {CONSUMABLE_MAIN_BRUSH: "IMG"}):
        coord._check_consumable(CONSUMABLE_MAIN_BRUSH, "replace_main_brush", DreameVacuumProperty.MAIN_BRUSH_LEFT)
    # create notification + consumable event scheduled.
    assert coord.hass.loop.call_soon_threadsafe.call_count >= 2


def test_check_consumable_depleted_creates_repair_issue():
    coord = _bare_coordinator()
    coord._device.status.consumable_life_warning_description = MagicMock(return_value=["Main brush", "Worn out."])
    coord._device.get_property = MagicMock(return_value=0)  # depleted -> repair issue created
    with patch("custom_components.dreame_vacuum.dreame.resources.CONSUMABLE_IMAGE", {}):
        coord._check_consumable(CONSUMABLE_MAIN_BRUSH, "replace_main_brush", DreameVacuumProperty.MAIN_BRUSH_LEFT)
    # notification + event + create-issue => 3 scheduled deferrals.
    assert coord.hass.loop.call_soon_threadsafe.call_count == 3


def test_check_consumables_runs_full_matrix_with_all_capabilities():
    """With every optional capability on, _check_consumables exercises all branches."""
    coord = _bare_coordinator()
    coord._device.capability = _make_capability(
        disable_sensor_cleaning=False,
        self_wash_base=True,
        deodorizer=True,
        wheel=True,
        scale_inhibitor=True,
    )
    coord._device.status.consumable_life_warning_description = MagicMock(return_value=None)
    calls = []
    with patch.object(coord, "_check_consumable", side_effect=lambda *a: calls.append(a[0])):
        coord._check_consumables()
    # 4 base + sensor + mop + squeegee + 2 tanks + silver/detergent + deodorizer + wheel + scale.
    assert len(calls) == 14


def test_check_consumables_minimal_capabilities():
    coord = _bare_coordinator()
    coord._device.capability = _make_capability()  # all optionals off, sensor cleaning disabled
    calls = []
    with patch.object(coord, "_check_consumable", side_effect=lambda *a: calls.append(a[0])):
        coord._check_consumables()
    # 4 base + mop + squeegee + 2 dirty-water tanks = 8 (no sensor, no wash-base, etc.)
    assert len(calls) == 8


# --------------------------------------------------------------------------- #
# _create_persistent_notification  (notify gating)
# --------------------------------------------------------------------------- #


def test_create_notification_skipped_when_disconnected():
    coord = _bare_coordinator(notify=True)
    coord._device.disconnected = True
    coord._create_persistent_notification("body", NOTIFICATION_ID_WARNING)
    coord.hass.loop.call_soon_threadsafe.assert_not_called()


def test_create_notification_skipped_when_notify_false():
    coord = _bare_coordinator(notify=False)
    coord._device.disconnected = False
    coord._device.device_connected = True
    coord._create_persistent_notification("body", NOTIFICATION_ID_WARNING)
    coord.hass.loop.call_soon_threadsafe.assert_not_called()


def test_create_notification_bool_notify_schedules():
    coord = _bare_coordinator(notify=True)
    coord._device.disconnected = False
    coord._device.device_connected = True
    coord._create_persistent_notification("body", NOTIFICATION_ID_WARNING)
    coord.hass.loop.call_soon_threadsafe.assert_called_once()


def test_create_notification_list_cleanup_completed_allowed_and_unique():
    coord = _bare_coordinator(notify=[NOTIFICATION_ID_CLEANUP_COMPLETED])
    coord._device.disconnected = False
    coord._device.device_connected = True
    coord._create_persistent_notification("done", NOTIFICATION_ID_CLEANUP_COMPLETED)
    coord.hass.loop.call_soon_threadsafe.assert_called_once()
    # The generated notification id is time-suffixed (unique).
    notif_id = coord.hass.loop.call_soon_threadsafe.call_args.args[-1]
    assert notif_id.startswith(f"{DOMAIN}_{coord._device.mac}_{NOTIFICATION_ID_CLEANUP_COMPLETED}_")


def test_create_notification_list_cleanup_completed_filtered_out():
    coord = _bare_coordinator(notify=[NOTIFICATION_ID_ERROR])  # cleanup not allowed
    coord._device.disconnected = False
    coord._device.device_connected = True
    coord._create_persistent_notification("done", NOTIFICATION_ID_CLEANUP_COMPLETED)
    coord.hass.loop.call_soon_threadsafe.assert_not_called()


def test_create_notification_list_warning_and_low_water_gate():
    coord = _bare_coordinator(notify=[NOTIFICATION_ID_WARNING])
    coord._device.disconnected = False
    coord._device.device_connected = True
    coord._create_persistent_notification("w", NOTIFICATION_ID_WARNING)
    coord._create_persistent_notification("lw", NOTIFICATION_ID_LOW_WATER)
    assert coord.hass.loop.call_soon_threadsafe.call_count == 2

    coord2 = _bare_coordinator(notify=[NOTIFICATION_ID_ERROR])  # warning not allowed
    coord2._device.disconnected = False
    coord2._device.device_connected = True
    coord2._create_persistent_notification("w", NOTIFICATION_ID_WARNING)
    coord2.hass.loop.call_soon_threadsafe.assert_not_called()


def test_create_notification_list_error_gate():
    coord = _bare_coordinator(notify=[NOTIFICATION_ID_ERROR])
    coord._device.disconnected = False
    coord._device.device_connected = True
    coord._create_persistent_notification("e", f"{NOTIFICATION_ID_ERROR}_5")
    coord.hass.loop.call_soon_threadsafe.assert_called_once()

    coord2 = _bare_coordinator(notify=[NOTIFICATION_ID_WARNING])  # error not allowed
    coord2._device.disconnected = False
    coord2._device.device_connected = True
    coord2._create_persistent_notification("e", f"{NOTIFICATION_ID_ERROR}_5")
    coord2.hass.loop.call_soon_threadsafe.assert_not_called()


def test_create_notification_list_information_gate():
    coord = _bare_coordinator(notify=[NOTIFICATION_ID_INFORMATION])
    coord._device.disconnected = False
    coord._device.device_connected = True
    coord._create_persistent_notification("d", NOTIFICATION_ID_DUST_COLLECTION)
    coord._create_persistent_notification("p", NOTIFICATION_ID_CLEANING_PAUSED)
    assert coord.hass.loop.call_soon_threadsafe.call_count == 2

    coord2 = _bare_coordinator(notify=[NOTIFICATION_ID_ERROR])  # information not allowed
    coord2._device.disconnected = False
    coord2._device.device_connected = True
    coord2._create_persistent_notification("d", NOTIFICATION_ID_DUST_COLLECTION)
    coord2.hass.loop.call_soon_threadsafe.assert_not_called()


def test_create_notification_list_consumable_gate():
    coord = _bare_coordinator(notify=[NOTIFICATION_ID_CONSUMABLE])
    coord._device.disconnected = False
    coord._device.device_connected = True
    coord._create_persistent_notification("c", "replace_main_brush")  # arbitrary consumable id
    coord.hass.loop.call_soon_threadsafe.assert_called_once()

    coord2 = _bare_coordinator(notify=[NOTIFICATION_ID_ERROR])  # consumable not allowed
    coord2._device.disconnected = False
    coord2._device.device_connected = True
    coord2._create_persistent_notification("c", "replace_main_brush")
    coord2.hass.loop.call_soon_threadsafe.assert_not_called()


def test_create_notification_list_temporary_map_and_drainage_bypass_consumable_gate():
    """REPLACE_TEMPORARY_MAP and DRAINAGE_STATUS are never gated by the consumable
    category (they fall through the elif chain) and are scheduled directly."""
    coord = _bare_coordinator(notify=[NOTIFICATION_ID_ERROR])  # only error allowed
    coord._device.disconnected = False
    coord._device.device_connected = True
    coord._create_persistent_notification("tm", NOTIFICATION_ID_REPLACE_TEMPORARY_MAP)
    coord._create_persistent_notification("dr", NOTIFICATION_ID_DRAINAGE_STATUS)
    assert coord.hass.loop.call_soon_threadsafe.call_count == 2


def test_remove_persistent_notification_schedules_dismiss():
    coord = _bare_coordinator()
    coord._remove_persistent_notification(NOTIFICATION_ID_WARNING)
    coord.hass.loop.call_soon_threadsafe.assert_called_once()
    args = coord.hass.loop.call_soon_threadsafe.call_args.args
    assert args[0] is persistent_notification.async_dismiss
    assert args[-1] == f"{DOMAIN}_{coord._device.mac}_{NOTIFICATION_ID_WARNING}"


# --------------------------------------------------------------------------- #
# device property
# --------------------------------------------------------------------------- #


def test_device_property_returns_underlying_device():
    coord = _bare_coordinator()
    assert coord.device is coord._device
