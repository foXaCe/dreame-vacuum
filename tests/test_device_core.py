"""Characterization tests for DreameVacuumDevice orchestration logic.

Scope (deliberately distinct from test_device_handle_properties.py and
test_device_update.py):

- listen()/listen_error() subscription + unsubscription closures
- _property_changed debounce timer and _update_failed error callback
- _request_properties batching (50-item chunks)
- _update_interval dynamic polling cadence
- connect_device()/connect_cloud()/disconnect() orchestration
- _otc.info credential redaction in logs
- the two consumable-properties request paths (_task_status_changed and
  _perform_update)
- _message_callback routing (handle_properties / map_manager dispatch)

Two device-construction strategies are used, matching the codebase
convention established by the sibling test files:

- ``object.__new__`` + hand-picked attributes for pure, narrow slices of
  logic (no I/O, no real Timer/Lock machinery beyond what's needed).
- A fully constructed ``DreameVacuumDevice`` with ``DreameVacuumProtocol``
  and the lazy map module patched out, for __init__/connect_device wiring
  assertions that need the real constructor to have run.
"""

from __future__ import annotations

import logging
import sys
from threading import RLock
import time
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Native-extension stubs (turbojpeg / py_mini_racer) - see
# test_device_handle_properties.py for rationale.
# ---------------------------------------------------------------------------


def _ensure_native_stubs() -> None:
    """Install lightweight stand-ins for optional C-extension dependencies."""
    if "turbojpeg" not in sys.modules:
        tj = types.ModuleType("turbojpeg")
        tj.TurboJPEG = type("TurboJPEG", (), {"__init__": lambda self, *a, **k: None})  # type: ignore[attr-defined]
        sys.modules["turbojpeg"] = tj
    if "py_mini_racer" not in sys.modules:
        pmr = types.ModuleType("py_mini_racer")
        pmr.MiniRacer = type("MiniRacer", (), {"__init__": lambda self, *a, **k: None})  # type: ignore[attr-defined]
        sys.modules["py_mini_racer"] = pmr


_ensure_native_stubs()

import custom_components.dreame_vacuum.dreame.device as device_module
from custom_components.dreame_vacuum.dreame.device import DreameVacuumDevice
from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo
from custom_components.dreame_vacuum.dreame.device_status import DreameVacuumDeviceStatus
from custom_components.dreame_vacuum.dreame.exceptions import DeviceUpdateFailedException
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    DreameVacuumDeviceCapability,
    DreameVacuumProperty,
    DreameVacuumPropertyMapping,
    DreameVacuumTaskStatus,
)

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _build_device(
    monkeypatch,
    *,
    cloud: bool = True,
    prefer_cloud: bool = False,
    dreame_cloud: bool = False,
    connected: bool = True,
) -> tuple[DreameVacuumDevice, MagicMock, MagicMock]:
    """Construct a real DreameVacuumDevice with I/O fully mocked out.

    ``DreameVacuumProtocol`` and the lazily-imported map module are patched
    before the constructor runs so ``__init__`` executes for real (listener
    wiring, default/read-write property lists, map-manager setup) without
    touching the network or requiring numpy/PIL.
    """
    protocol_instance = MagicMock(name="protocol_instance")
    protocol_instance.cloud = MagicMock(name="cloud") if cloud else None
    protocol_instance.prefer_cloud = prefer_cloud
    protocol_instance.dreame_cloud = dreame_cloud
    protocol_instance.connected = connected
    protocol_instance.get_properties.return_value = []

    protocol_class = MagicMock(return_value=protocol_instance)
    monkeypatch.setattr(device_module, "DreameVacuumProtocol", protocol_class)

    map_manager_instance = MagicMock(name="map_manager_instance")
    fake_map_module = types.SimpleNamespace(DreameMapVacuumMapManager=MagicMock(return_value=map_manager_instance))
    monkeypatch.setattr(device_module, "_get_map_module", lambda: fake_map_module)

    device = DreameVacuumDevice("Vacuum", "192.168.1.42", "token")
    return device, protocol_instance, map_manager_instance


def _listener_device() -> DreameVacuumDevice:
    """Bare instance for listen()/listen_error()/_property_changed()/_update_failed()."""
    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    d._update_callback = None
    d._property_update_callback = {}
    d._error_callback = None
    d._callback_timer = None
    d._last_change = 0.0
    return d


def _request_props_device(ready: bool) -> DreameVacuumDevice:
    """Bare instance for _request_properties batching tests.

    When ``ready=False``, ``_handle_properties`` walks its full "not ready"
    initialization branch (capability.load + status list pruning), so real
    (but I/O-free) capability/status objects are attached rather than mocks.
    """
    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    d._ready = ready
    d.data = {}
    d._dirty_data = {}
    d._discard_timeout = 2
    d._property_update_callback = {}
    d._last_change = 0.0
    d._property_changed = MagicMock()
    d._protocol = MagicMock()
    d._map_manager = None
    # A real, known-supported model is required: capability.load() (invoked
    # from the "not ready" branch of _handle_properties) looks it up in the
    # compressed DEVICE_INFO capability table and raises otherwise.
    d.info = DreameVacuumDeviceInfo(
        {"model": "dreame.vacuum.p2028", "fw_ver": "4.5.6_0078", "mac": "AA:BB:CC:DD:EE:FF"}
    )
    d.capability = DreameVacuumDeviceCapability(d)
    d.status = DreameVacuumDeviceStatus(d)
    return d


def _interval_device(**status_overrides: object) -> DreameVacuumDevice:
    """Bare instance for the _update_interval property."""
    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    base_status = {
        "map_backup_status": False,
        "map_recovery_status": False,
        "active": False,
        "started": False,
        "running": False,
    }
    base_status.update(status_overrides)
    d.status = SimpleNamespace(**base_status)
    d._protocol = SimpleNamespace(prefer_cloud=False)
    d._last_update_failed = None
    d._last_change = 0.0
    d._map_manager = None
    return d


def _perform_update_device(**status_overrides: object) -> DreameVacuumDevice:
    """Bare instance for the _perform_update consumable-properties branch."""
    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    d._protocol = SimpleNamespace(connected=True, cloud=None, prefer_cloud=False, dreame_cloud=False)
    d._map_initialized = True
    d._map_manager = None
    d._consumable_change = False
    d._last_settings_request = time.time()
    d._last_map_list_request = time.time()
    d._draining_complete_time = None
    d._dirty_data = {}
    d._dirty_auto_switch_data = {}
    d._dirty_ai_data = {}
    d._deferred_cloud_loaded = True
    base_status = {
        "active": False,
        "started": False,
        "washing": False,
        "running": False,
        "map_backup_status": False,
        "map_recovery_status": False,
    }
    base_status.update(status_overrides)
    d.status = SimpleNamespace(**base_status)
    d.capability = SimpleNamespace(backup_map=False, disable_sensor_cleaning=False, dnd_task=True)
    d._read_write_properties = []
    d._request_properties = MagicMock(return_value=True)
    return d


def _task_status_device(disable_sensor_cleaning: bool = False) -> DreameVacuumDevice:
    """Bare instance for the _task_status_changed consumable-properties branch."""
    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    d.data = {DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.AUTO_CLEANING.value}
    d._map_manager = None
    d.status = SimpleNamespace(
        go_to_zone=None,
        fast_mapping=False,
        cruising=False,
        cleanup_started=False,
        cleanup_completed=False,
    )
    d._previous_cleangenius = None
    d._property_update_callback = {}
    d._property_changed = MagicMock()
    d.capability = SimpleNamespace(
        new_state=True, disable_sensor_cleaning=disable_sensor_cleaning, mopping_after_sweeping=False
    )
    d._request_properties = MagicMock(return_value=True)
    d._protocol = SimpleNamespace(prefer_cloud=False, dreame_cloud=False)
    return d


def _message_device() -> DreameVacuumDevice:
    """Bare instance for _message_callback routing/redaction tests."""
    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    d._ready = True
    d._default_properties = [DreameVacuumProperty.BATTERY_LEVEL]
    d._map_manager = None
    d.available = False
    d.info = None
    d._property_changed = MagicMock()
    d._last_change = 0.0
    return d


# ===========================================================================
# listen() / listen_error()
# ===========================================================================


class TestListenGlobal:
    """listen(callback) with property=None registers/clears _update_callback."""

    def test_listen_global_sets_update_callback(self) -> None:
        d = _listener_device()
        cb = MagicMock()
        unsub = d.listen(cb)
        assert d._update_callback is cb
        assert callable(unsub)

    def test_listen_global_unsub_clears_when_still_current(self) -> None:
        d = _listener_device()
        cb = MagicMock()
        unsub = d.listen(cb)
        unsub()
        assert d._update_callback is None

    def test_listen_global_unsub_is_noop_if_callback_replaced(self) -> None:
        """Stale unsub closures must not clobber a newer registration."""
        d = _listener_device()
        cb = MagicMock()
        unsub = d.listen(cb)
        other_cb = MagicMock()
        d._update_callback = other_cb
        unsub()
        assert d._update_callback is other_cb

    def test_listen_none_wipes_everything(self) -> None:
        d = _listener_device()
        d.listen(MagicMock(), DreameVacuumProperty.BATTERY_LEVEL)
        d._update_callback = MagicMock()
        result = d.listen(None)
        assert result is None
        assert d._update_callback is None
        assert d._property_update_callback == {}


class TestListenProperty:
    """listen(callback, property) registers/removes a per-property callback."""

    def test_listen_property_registers_callback(self) -> None:
        d = _listener_device()
        cb = MagicMock()
        unsub = d.listen(cb, DreameVacuumProperty.BATTERY_LEVEL)
        did = DreameVacuumProperty.BATTERY_LEVEL.value
        assert d._property_update_callback[did] == [cb]
        assert callable(unsub)

    def test_two_callbacks_same_property_both_registered(self) -> None:
        d = _listener_device()
        cb1 = MagicMock()
        cb2 = MagicMock()
        d.listen(cb1, DreameVacuumProperty.BATTERY_LEVEL)
        d.listen(cb2, DreameVacuumProperty.BATTERY_LEVEL)
        did = DreameVacuumProperty.BATTERY_LEVEL.value
        assert d._property_update_callback[did] == [cb1, cb2]

    def test_unsub_removes_only_that_callback(self) -> None:
        d = _listener_device()
        cb1 = MagicMock()
        cb2 = MagicMock()
        unsub1 = d.listen(cb1, DreameVacuumProperty.BATTERY_LEVEL)
        d.listen(cb2, DreameVacuumProperty.BATTERY_LEVEL)
        did = DreameVacuumProperty.BATTERY_LEVEL.value
        unsub1()
        assert d._property_update_callback[did] == [cb2]

    def test_unsub_pops_key_when_last_callback_removed(self) -> None:
        d = _listener_device()
        cb = MagicMock()
        unsub = d.listen(cb, DreameVacuumProperty.BATTERY_LEVEL)
        did = DreameVacuumProperty.BATTERY_LEVEL.value
        unsub()
        assert did not in d._property_update_callback

    def test_unsub_valueerror_is_swallowed(self) -> None:
        """If the callback list was mutated externally, unsub must not raise."""
        d = _listener_device()
        cb = MagicMock()
        other_cb = MagicMock()
        unsub = d.listen(cb, DreameVacuumProperty.BATTERY_LEVEL)
        did = DreameVacuumProperty.BATTERY_LEVEL.value
        d._property_update_callback[did] = [other_cb]
        unsub()
        assert d._property_update_callback[did] == [other_cb]

    def test_unsub_noop_when_list_already_empty(self) -> None:
        d = _listener_device()
        cb = MagicMock()
        unsub = d.listen(cb, DreameVacuumProperty.BATTERY_LEVEL)
        did = DreameVacuumProperty.BATTERY_LEVEL.value
        d._property_update_callback[did].remove(cb)
        unsub()
        assert d._property_update_callback[did] == []


class TestListenError:
    def test_listen_error_sets_and_unsub_clears(self) -> None:
        d = _listener_device()
        cb = MagicMock()
        unsub = d.listen_error(cb)
        assert d._error_callback is cb
        unsub()
        assert d._error_callback is None

    def test_listen_error_unsub_noop_if_replaced(self) -> None:
        d = _listener_device()
        cb = MagicMock()
        unsub = d.listen_error(cb)
        other = MagicMock()
        d._error_callback = other
        unsub()
        assert d._error_callback is other


# ===========================================================================
# _property_changed debounce / _update_failed
# ===========================================================================


class TestPropertyChangedDebounce:
    def test_delay_true_starts_timer_and_cancels_previous(self, monkeypatch) -> None:
        d = _listener_device()
        cb = MagicMock()
        d._update_callback = cb

        timer_instances: list[MagicMock] = []

        def fake_timer(interval: float, function: object) -> MagicMock:
            t = MagicMock()
            t.interval = interval
            t.function = function
            timer_instances.append(t)
            return t

        monkeypatch.setattr(device_module, "Timer", fake_timer)

        d._property_changed()

        assert len(timer_instances) == 1
        first_timer = timer_instances[0]
        first_timer.start.assert_called_once()
        assert first_timer.interval == 0.1
        assert first_timer.function is cb
        assert d._callback_timer is first_timer
        first_timer.cancel.assert_not_called()

        d._property_changed()

        first_timer.cancel.assert_called_once()
        assert len(timer_instances) == 2
        assert d._callback_timer is timer_instances[1]

    def test_delay_false_calls_callback_immediately_without_timer(self, monkeypatch) -> None:
        d = _listener_device()
        cb = MagicMock()
        d._update_callback = cb
        timer_mock = MagicMock()
        monkeypatch.setattr(device_module, "Timer", timer_mock)

        d._property_changed(delay=False)

        cb.assert_called_once_with()
        timer_mock.assert_not_called()

    def test_no_update_callback_registered_is_noop(self, monkeypatch) -> None:
        d = _listener_device()
        d._update_callback = None
        timer_mock = MagicMock()
        monkeypatch.setattr(device_module, "Timer", timer_mock)

        d._property_changed()

        timer_mock.assert_not_called()


class TestUpdateFailedCallback:
    def test_update_failed_calls_error_callback(self) -> None:
        d = _listener_device()
        err_cb = MagicMock()
        d._error_callback = err_cb
        ex = DeviceUpdateFailedException("boom")

        d._update_failed(ex)

        err_cb.assert_called_once_with(ex)

    def test_update_failed_noop_without_error_callback(self) -> None:
        d = _listener_device()
        d._error_callback = None
        # Must not raise even though nothing is registered.
        d._update_failed(RuntimeError("x"))


# ===========================================================================
# _request_properties batching
# ===========================================================================


class TestRequestPropertiesBatching:
    def test_batches_of_fifty(self) -> None:
        d = _request_props_device(ready=False)
        d._protocol.get_properties = MagicMock(return_value=[])
        properties = list(DreameVacuumPropertyMapping.keys())[:120]

        d._request_properties(properties, force_all=True)

        calls = d._protocol.get_properties.call_args_list
        assert len(calls) == 3
        sizes = [len(c.args[0]) for c in calls]
        assert sizes == [50, 50, 20]

    def test_default_properties_used_when_none_given(self) -> None:
        d = _request_props_device(ready=False)
        d._default_properties = [DreameVacuumProperty.BATTERY_LEVEL]
        d._protocol.get_properties = MagicMock(return_value=[])

        d._request_properties()

        d._protocol.get_properties.assert_called_once()
        batch = d._protocol.get_properties.call_args.args[0]
        assert len(batch) == 1
        assert batch[0]["did"] == str(DreameVacuumProperty.BATTERY_LEVEL.value)

    def test_stops_when_protocol_returns_none(self) -> None:
        d = _request_props_device(ready=False)
        properties = list(DreameVacuumPropertyMapping.keys())[:120]
        d._protocol.get_properties = MagicMock(return_value=None)

        result = d._request_properties(properties, force_all=True)

        d._protocol.get_properties.assert_called_once()
        assert result is False

    def test_ready_device_filters_properties_not_in_data(self) -> None:
        """Without force_all, a ready device only re-requests known properties."""
        d = _request_props_device(ready=True)
        d.data = {DreameVacuumProperty.BATTERY_LEVEL.value: 50}
        d._protocol.get_properties = MagicMock(return_value=[])

        d._request_properties([DreameVacuumProperty.BATTERY_LEVEL, DreameVacuumProperty.ERROR])

        batch = d._protocol.get_properties.call_args.args[0]
        assert len(batch) == 1
        assert batch[0]["did"] == str(DreameVacuumProperty.BATTERY_LEVEL.value)

    def test_results_forwarded_to_handle_properties(self) -> None:
        d = _request_props_device(ready=True)
        d.data = {DreameVacuumProperty.BATTERY_LEVEL.value: 50}
        returned = [
            {"did": str(DreameVacuumProperty.BATTERY_LEVEL.value), "siid": 0, "piid": 0, "code": 0, "value": 77}
        ]
        d._protocol.get_properties = MagicMock(return_value=returned)

        result = d._request_properties([DreameVacuumProperty.BATTERY_LEVEL])

        assert result is True
        assert d.data[DreameVacuumProperty.BATTERY_LEVEL.value] == 77


# ===========================================================================
# _update_interval dynamic cadence
# ===========================================================================


class TestUpdateInterval:
    def test_map_backup_status_wins_over_everything(self) -> None:
        d = _interval_device(map_backup_status=True)
        d._last_update_failed = time.time()
        assert d._update_interval == 2

    def test_map_recovery_status_wins_over_everything(self) -> None:
        d = _interval_device(map_recovery_status=True)
        assert d._update_interval == 2

    def test_last_update_failed_recent_returns_five(self) -> None:
        d = _interval_device()
        d._last_update_failed = time.time() - 30
        assert d._update_interval == 5

    def test_last_update_failed_medium_age_returns_ten(self) -> None:
        d = _interval_device()
        d._last_update_failed = time.time() - 120
        assert d._update_interval == 10

    def test_last_update_failed_old_returns_thirty(self) -> None:
        d = _interval_device()
        d._last_update_failed = time.time() - 400
        assert d._update_interval == 30

    def test_recent_change_active_returns_three(self) -> None:
        d = _interval_device(active=True)
        d._last_change = time.time()
        assert d._update_interval == 3

    def test_recent_change_inactive_prefer_cloud_false_returns_three(self) -> None:
        d = _interval_device(active=False)
        d._protocol.prefer_cloud = False
        d._last_change = time.time()
        assert d._update_interval == 3

    def test_recent_change_inactive_prefer_cloud_true_returns_five(self) -> None:
        d = _interval_device(active=False)
        d._protocol.prefer_cloud = True
        d._last_change = time.time()
        assert d._update_interval == 5

    def test_active_old_change_running_returns_three(self) -> None:
        d = _interval_device(active=True, running=True)
        d._last_change = time.time() - 1000
        assert d._update_interval == 3

    def test_started_old_change_not_running_prefer_cloud_false_returns_three(self) -> None:
        d = _interval_device(active=False, started=True, running=False)
        d._protocol.prefer_cloud = False
        d._last_change = time.time() - 1000
        assert d._update_interval == 3

    def test_active_old_change_not_running_prefer_cloud_true_returns_five(self) -> None:
        d = _interval_device(active=True, running=False)
        d._protocol.prefer_cloud = True
        d._last_change = time.time() - 1000
        assert d._update_interval == 5

    def test_idle_no_map_manager_prefer_cloud_false_returns_thirty(self) -> None:
        d = _interval_device(active=False, started=False)
        d._protocol.prefer_cloud = False
        d._last_change = time.time() - 1000
        d._map_manager = None
        assert d._update_interval == 30

    def test_idle_no_map_manager_prefer_cloud_true_returns_sixty(self) -> None:
        d = _interval_device(active=False, started=False)
        d._protocol.prefer_cloud = True
        d._last_change = time.time() - 1000
        d._map_manager = None
        assert d._update_interval == 60

    def test_idle_with_map_manager_uses_min_prefer_cloud_false(self, monkeypatch) -> None:
        d = _interval_device(active=False, started=False)
        d._protocol.prefer_cloud = False
        d._last_change = time.time() - 1000
        d._map_manager = MagicMock()
        monkeypatch.setattr(DreameVacuumDevice, "_map_update_interval", property(lambda self: 45))
        assert d._update_interval == 30  # min(45, 30)

    def test_idle_with_map_manager_uses_min_prefer_cloud_true(self, monkeypatch) -> None:
        d = _interval_device(active=False, started=False)
        d._protocol.prefer_cloud = True
        d._last_change = time.time() - 1000
        d._map_manager = MagicMock()
        monkeypatch.setattr(DreameVacuumDevice, "_map_update_interval", property(lambda self: 45))
        assert d._update_interval == 45  # min(45, 60)


# ===========================================================================
# connect_device() / connect_cloud() / disconnect()
# ===========================================================================


class TestConnectDevice:
    def test_nominal_path_consumes_info_and_marks_ready(self, monkeypatch) -> None:
        device, protocol_instance, map_manager_instance = _build_device(monkeypatch, cloud=True)
        info = {"model": "dreame.vacuum.p2028", "fw_ver": "4.5.6_0078", "mac": "AA:BB:CC:DD:EE:FF"}
        protocol_instance.connect.return_value = info

        device.connect_device()

        protocol_instance.connect.assert_called_once_with(device._message_callback, device._connected_callback)
        assert device.info is not None
        assert device.info.model == "dreame.vacuum.p2028"
        assert device.mac == "AA:BB:CC:DD:EE:FF"
        assert device._ready is True
        assert device.available is True
        assert device._full_properties_loaded is True
        map_manager_instance.set_capability.assert_called_once_with(device.capability)
        map_manager_instance.schedule_update.assert_called_once_with(2)

    def test_no_info_leaves_device_not_ready(self, monkeypatch) -> None:
        device, protocol_instance, _map_manager = _build_device(monkeypatch, cloud=True)
        protocol_instance.connect.return_value = None

        device.connect_device()

        assert device._ready is False
        assert device.info is None
        assert device.available is False

    def test_already_ready_notifies_property_changed_without_delay(self, monkeypatch) -> None:
        device, protocol_instance, _map_manager = _build_device(monkeypatch, cloud=True)
        protocol_instance.connect.return_value = {"model": "m", "fw_ver": "1_2", "mac": "11:22:33:44:55:66"}
        device._ready = True
        calls: list[bool] = []
        device._property_changed = lambda delay=True: calls.append(delay)

        device.connect_device()

        assert calls == [False]


class TestConnectCloud:
    def test_no_cloud_configured_is_noop(self, monkeypatch) -> None:
        device, protocol_instance, _map_manager = _build_device(monkeypatch, cloud=False)
        # Should not raise even though protocol.cloud is None.
        device.connect_cloud()

    def test_login_failure_sets_auth_failed_and_notifies(self, monkeypatch) -> None:
        device, protocol_instance, map_manager_instance = _build_device(monkeypatch, cloud=True)
        protocol_instance.cloud.logged_in = False
        protocol_instance.cloud.auth_failed = True
        calls: list[bool] = []
        device._property_changed = lambda delay=True: calls.append(delay)

        device.connect_cloud()

        protocol_instance.cloud.login.assert_called_once()
        assert device.auth_failed is True
        assert calls == [False]
        map_manager_instance.schedule_update.assert_called_once_with(-1)

    def test_successful_login_refreshes_credentials(self, monkeypatch) -> None:
        device, protocol_instance, map_manager_instance = _build_device(monkeypatch, cloud=True, dreame_cloud=False)
        # connect_cloud() only attempts login while not already logged in; the
        # mocked login() call flips the flag, mirroring the real cloud client.
        protocol_instance.cloud.logged_in = False
        protocol_instance.connected = True
        # get_info() returns (token, host) — see DreameVacuumDevice.connect_cloud:
        # `self.token, self.host = self._protocol.cloud.get_info(self.mac)`.
        protocol_instance.cloud.get_info.return_value = ("new_token", "new_host")

        def _fake_login() -> None:
            protocol_instance.cloud.logged_in = True

        protocol_instance.cloud.login.side_effect = _fake_login

        device.connect_cloud()

        protocol_instance.cloud.login.assert_called_once()
        map_manager_instance.schedule_update.assert_called_once_with(5)
        protocol_instance.cloud.get_info.assert_called_once_with(device.mac)
        assert device.token == "new_token"
        assert device.host == "new_host"
        protocol_instance.set_credentials.assert_called_once_with(
            "new_host", "new_token", device.mac, device.account_type
        )


class TestDisconnectCleanup:
    def test_disconnect_cancels_timers_purges_state_and_notifies(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d.disconnected = False
        d._timer_lock = RLock()
        update_timer = MagicMock()
        callback_timer = MagicMock()
        d._update_timer = update_timer
        d._callback_timer = callback_timer
        d._protocol = MagicMock()
        d._map_manager = MagicMock()
        update_cb = MagicMock()
        d._update_callback = update_cb

        d.disconnect()

        assert d.disconnected is True
        update_timer.cancel.assert_called_once()
        assert d._update_timer is None
        callback_timer.cancel.assert_called_once()
        assert d._callback_timer is None
        d._protocol.disconnect.assert_called_once()
        d._map_manager.disconnect.assert_called_once()
        # _property_changed(False) -> immediate callback invocation, no new Timer.
        update_cb.assert_called_once_with()

    def test_disconnect_without_map_manager_does_not_crash(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d.disconnected = False
        d._timer_lock = RLock()
        d._update_timer = None
        d._callback_timer = None
        d._protocol = MagicMock()
        d._map_manager = None
        d._update_callback = None

        d.disconnect()

        assert d.disconnected is True
        d._protocol.disconnect.assert_called_once()


# ===========================================================================
# schedule_update()
# ===========================================================================


def _schedule_update_device() -> DreameVacuumDevice:
    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    d._timer_lock = RLock()
    d._update_timer = None
    d.disconnected = False
    d.status = SimpleNamespace(
        map_backup_status=False, map_recovery_status=False, active=False, started=False, running=False
    )
    d._protocol = SimpleNamespace(prefer_cloud=False)
    d._last_update_failed = None
    d._last_change = 0.0
    d._map_manager = None
    return d


class TestScheduleUpdate:
    def test_creates_timer_with_default_interval_and_update_task(self, monkeypatch) -> None:
        d = _schedule_update_device()
        created: dict[str, object] = {}

        def fake_timer(wait: float, fn: object) -> MagicMock:
            created["wait"] = wait
            created["fn"] = fn
            return MagicMock()

        monkeypatch.setattr(device_module, "Timer", fake_timer)

        d.schedule_update()

        assert created["wait"] == 30  # idle, no map manager, prefer_cloud False
        # Bound methods compare equal (same __self__/__func__) but are not `is`
        # identical across separate attribute accesses.
        assert created["fn"] == d._update_task
        assert d._update_timer is not None

    def test_force_request_properties_uses_action_update_task(self, monkeypatch) -> None:
        d = _schedule_update_device()
        created: dict[str, object] = {}

        def fake_timer(wait: float, fn: object) -> MagicMock:
            created["fn"] = fn
            return MagicMock()

        monkeypatch.setattr(device_module, "Timer", fake_timer)

        d.schedule_update(5, force_request_properties=True)

        assert created["fn"] == d._action_update_task

    def test_cancels_existing_timer_before_scheduling_new_one(self, monkeypatch) -> None:
        d = _schedule_update_device()
        old_timer = MagicMock()
        d._update_timer = old_timer
        monkeypatch.setattr(device_module, "Timer", MagicMock(return_value=MagicMock()))

        d.schedule_update(5)

        old_timer.cancel.assert_called_once()

    def test_negative_wait_cancels_but_does_not_create_new_timer(self, monkeypatch) -> None:
        d = _schedule_update_device()
        old_timer = MagicMock()
        d._update_timer = old_timer
        timer_mock = MagicMock()
        monkeypatch.setattr(device_module, "Timer", timer_mock)

        d.schedule_update(-1)

        timer_mock.assert_not_called()
        assert d._update_timer is None

    def test_disconnected_device_never_arms_a_new_timer(self, monkeypatch) -> None:
        d = _schedule_update_device()
        d.disconnected = True
        timer_mock = MagicMock()
        monkeypatch.setattr(device_module, "Timer", timer_mock)

        d.schedule_update(5)

        timer_mock.assert_not_called()


# ===========================================================================
# _otc.info credential redaction
# ===========================================================================


class TestOtcInfoRedaction:
    def test_otc_info_message_does_not_log_credentials(self, caplog) -> None:
        d = _message_device()
        secret_token = "SUPER_SECRET_TOKEN_0xDEADBEEF"
        secret_ip = "10.20.30.40"
        secret_bssid = "AA:BB:CC:DD:EE:FF"
        msg = {
            "method": "_otc.info",
            "params": {"token": secret_token, "localIp": secret_ip, "bssid": secret_bssid},
        }

        with caplog.at_level(logging.DEBUG):
            d._message_callback(msg)

        assert secret_token not in caplog.text
        assert secret_ip not in caplog.text
        assert secret_bssid not in caplog.text
        # Functionality is preserved: info is still consumed.
        assert d.info is not None
        assert d.info.data == msg["params"]

    def test_otc_info_triggers_property_changed_when_ready(self) -> None:
        d = _message_device()
        msg = {"method": "_otc.info", "params": {"token": "x"}}

        d._message_callback(msg)

        d._property_changed.assert_called_once_with()

    def test_otc_info_same_info_does_not_retrigger(self) -> None:
        d = _message_device()
        msg = {"method": "_otc.info", "params": {"token": "x"}}
        d._message_callback(msg)
        d._property_changed.reset_mock()

        d._message_callback(msg)

        # New DreameVacuumDeviceInfo instance but data-equal? DreameVacuumDeviceInfo
        # has no custom __eq__, so identity comparison makes this a "change" again.
        # This documents current behavior rather than asserting an ideal one.
        assert d._property_changed.called


# ===========================================================================
# _message_callback routing
# ===========================================================================


class TestMessageCallbackOrchestration:
    def test_properties_changed_forwards_transformed_list_to_handle_properties(self) -> None:
        d = _message_device()
        d._handle_properties = MagicMock(return_value=True)
        msg = {
            "method": "properties_changed",
            "params": [{"siid": 3, "piid": 1, "code": 0, "value": 42}],
        }

        d._message_callback(msg)

        d._handle_properties.assert_called_once()
        (properties_arg,), _kwargs = d._handle_properties.call_args
        assert properties_arg[0]["did"] == str(DreameVacuumProperty.BATTERY_LEVEL.value)
        assert properties_arg[0]["code"] == 0
        assert d.available is True

    def test_map_properties_routed_to_map_manager(self) -> None:
        d = _message_device()
        d._default_properties = []
        map_manager = MagicMock()
        d._map_manager = map_manager
        d._handle_properties = MagicMock(return_value=False)
        msg = {
            "method": "properties_changed",
            "params": [{"siid": 6, "piid": 3, "code": 0, "value": "mapdata"}],  # OBJECT_NAME
        }

        d._message_callback(msg)

        map_manager.handle_properties.assert_called_once()
        routed = map_manager.handle_properties.call_args.args[0]
        assert routed[0]["siid"] == 6
        # Non-default, non-map properties never reach _handle_properties.
        d._handle_properties.assert_called_once_with([])

    def test_malformed_message_missing_method_or_params_does_not_crash(self) -> None:
        d = _message_device()
        d._message_callback({"method": "properties_changed"})  # no params
        assert d.available is False
        d._message_callback({"params": []})  # no method
        assert d.available is False
        d._message_callback({})
        assert d.available is False

    def test_non_dict_message_does_not_crash(self) -> None:
        d = _message_device()
        # Falls through the isinstance(dict) guard, then "method" in message
        # is a (harmless) substring test against the string itself.
        d._message_callback("not-a-dict-payload")
        assert d.available is False

    def test_not_ready_short_circuits_before_any_processing(self) -> None:
        d = _message_device()
        d._ready = False
        d._handle_properties = MagicMock()
        d._message_callback({"method": "properties_changed", "params": []})
        d._handle_properties.assert_not_called()
        assert d.available is False


# ===========================================================================
# Consumable properties — two request paths
# ===========================================================================


class TestConsumablePropertiesViaTaskStatusChanged:
    """~device.py:966-1032 — consumables refreshed when a task completes."""

    def test_completed_task_requests_consumables_including_sensor(self) -> None:
        d = _task_status_device(disable_sensor_cleaning=False)

        d._task_status_changed(DreameVacuumTaskStatus.COMPLETED.value)

        props = d._request_properties.call_args.args[0]
        assert DreameVacuumProperty.MAIN_BRUSH_TIME_LEFT in props
        assert DreameVacuumProperty.MAIN_BRUSH_LEFT in props
        assert DreameVacuumProperty.SENSOR_DIRTY_LEFT in props
        assert DreameVacuumProperty.SENSOR_DIRTY_TIME_LEFT in props

    def test_completed_task_excludes_sensor_when_capability_disabled(self) -> None:
        d = _task_status_device(disable_sensor_cleaning=True)

        d._task_status_changed(DreameVacuumTaskStatus.COMPLETED.value)

        props = d._request_properties.call_args.args[0]
        assert DreameVacuumProperty.MAIN_BRUSH_LEFT in props
        assert DreameVacuumProperty.SENSOR_DIRTY_LEFT not in props
        assert DreameVacuumProperty.SENSOR_DIRTY_TIME_LEFT not in props

    def test_completed_task_resets_cleaning_time_and_area(self) -> None:
        d = _task_status_device()

        d._task_status_changed(DreameVacuumTaskStatus.COMPLETED.value)

        assert d.data[DreameVacuumProperty.CLEANING_TIME.value] == 0
        assert d.data[DreameVacuumProperty.CLEANED_AREA.value] == 0

    def test_non_completed_transition_does_not_request_properties(self) -> None:
        d = _task_status_device()
        # Neither previous nor current status is COMPLETED.
        d.data[DreameVacuumProperty.TASK_STATUS.value] = DreameVacuumTaskStatus.AUTO_CLEANING_PAUSED.value

        d._task_status_changed(DreameVacuumTaskStatus.SEGMENT_CLEANING.value)

        d._request_properties.assert_not_called()


class TestConsumablePropertiesViaPerformUpdate:
    """~device.py:1949-2009 — consumables requested via _consumable_change / washing."""

    def test_consumable_change_flag_requests_full_consumable_list(self) -> None:
        d = _perform_update_device()
        d._consumable_change = True
        d.capability.disable_sensor_cleaning = False

        d._perform_update()

        props = d._request_properties.call_args.args[0]
        assert DreameVacuumProperty.MAIN_BRUSH_LEFT in props
        assert DreameVacuumProperty.SENSOR_DIRTY_LEFT in props

    def test_consumable_change_flag_excludes_sensor_when_disabled(self) -> None:
        d = _perform_update_device()
        d._consumable_change = True
        d.capability.disable_sensor_cleaning = True

        d._perform_update()

        props = d._request_properties.call_args.args[0]
        assert DreameVacuumProperty.MAIN_BRUSH_LEFT in props
        assert DreameVacuumProperty.SENSOR_DIRTY_LEFT not in props

    def test_consumable_change_flag_reset_after_update(self) -> None:
        d = _perform_update_device()
        d._consumable_change = True

        d._perform_update()

        assert d._consumable_change is False

    def test_washing_without_consumable_change_requests_washing_subset_only(self) -> None:
        d = _perform_update_device(washing=True)
        d._consumable_change = False
        d._last_settings_request = 0  # force the settings-request window open

        d._perform_update()

        props = d._request_properties.call_args.args[0]
        assert DreameVacuumProperty.DETERGENT_LEFT in props
        assert DreameVacuumProperty.SQUEEGEE_LEFT in props
        # The full consumable_change list (e.g. MAIN_BRUSH_LEFT) is not requested.
        assert DreameVacuumProperty.MAIN_BRUSH_LEFT not in props

    def test_not_washing_and_no_consumable_change_requests_neither_subset(self) -> None:
        d = _perform_update_device(washing=False)
        d._consumable_change = False
        d._last_settings_request = 0

        d._perform_update()

        props = d._request_properties.call_args.args[0]
        assert DreameVacuumProperty.MAIN_BRUSH_LEFT not in props
        assert DreameVacuumProperty.DETERGENT_LEFT not in props


# ===========================================================================
# Miscellaneous pure orchestration helpers
# ===========================================================================


class TestGroupValueHelpers:
    def test_split_group_value_without_mop_pad_lifting(self) -> None:
        # value=0b1_00000010_00000001 -> byte0=1, byte1=2, byte2=1
        value = (1 << 16) | (2 << 8) | 1
        result = DreameVacuumDevice.split_group_value(value, mop_pad_lifting=False)
        assert result == [1, 2, 1]

    def test_split_group_value_with_mop_pad_lifting_keeps_two_low_bits(self) -> None:
        value = (1 << 16) | (2 << 8) | 3
        result = DreameVacuumDevice.split_group_value(value, mop_pad_lifting=True)
        assert result[0] == 3  # value & 0x03

    def test_split_group_value_none_returns_none(self) -> None:
        assert DreameVacuumDevice.split_group_value(None) is None

    def test_combine_group_value_roundtrips_split(self) -> None:
        original = (1 << 16) | (2 << 8) | 1
        split = DreameVacuumDevice.split_group_value(original, mop_pad_lifting=False)
        assert DreameVacuumDevice.combine_group_value(split) == original

    def test_combine_group_value_empty_returns_zero(self) -> None:
        assert DreameVacuumDevice.combine_group_value([]) == 0
        assert DreameVacuumDevice.combine_group_value(None) == 0


class TestSimpleProperties:
    def test_name_returns_configured_name(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d._name = "Living Room Vacuum"
        assert d.name == "Living Room Vacuum"

    def test_device_connected_reflects_protocol_connected(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d._protocol = SimpleNamespace(connected=True)
        assert d.device_connected is True
        d._protocol.connected = False
        assert d.device_connected is False

    def test_cloud_connected_false_without_cloud(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d._protocol = SimpleNamespace(cloud=None, prefer_cloud=False, connected=True)
        assert d.cloud_connected is False

    def test_cloud_connected_true_when_cloud_connected_and_not_prefer_cloud(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d._protocol = SimpleNamespace(cloud=SimpleNamespace(connected=True), prefer_cloud=False, connected=False)
        assert d.cloud_connected is True

    def test_cloud_connected_requires_device_connected_when_prefer_cloud(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d._protocol = SimpleNamespace(cloud=SimpleNamespace(connected=True), prefer_cloud=True, connected=False)
        assert d.cloud_connected is False
        d._protocol.connected = True
        assert d.cloud_connected is True

    def test_cloud_auth_key_none_without_cloud(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d._protocol = SimpleNamespace(cloud=None)
        assert d.cloud_auth_key is None

    def test_cloud_auth_key_delegates_to_cloud(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d._protocol = SimpleNamespace(cloud=SimpleNamespace(auth_key="abc123"))
        assert d.cloud_auth_key == "abc123"


# ===========================================================================
# __init__ wiring (full constructor, protocol + map module mocked)
# ===========================================================================


class TestConstruction:
    def test_full_construction_wires_protocol_and_map_manager(self, monkeypatch) -> None:
        device, protocol_instance, map_manager_instance = _build_device(monkeypatch, cloud=True)

        assert device._protocol is protocol_instance
        assert device._map_manager is map_manager_instance
        map_manager_instance.listen.assert_called_once_with(device._map_changed, device._map_updated)
        map_manager_instance.listen_error.assert_called_once_with(device._update_failed)
        assert isinstance(device.status, DreameVacuumDeviceStatus)
        assert isinstance(device.capability, DreameVacuumDeviceCapability)

    def test_construction_without_cloud_skips_map_manager(self, monkeypatch) -> None:
        device, _protocol_instance, _map_manager_instance = _build_device(monkeypatch, cloud=False)
        assert device._map_manager is None

    def test_default_properties_excludes_write_only_response_only_props(self, monkeypatch) -> None:
        device, _protocol_instance, _map_manager_instance = _build_device(monkeypatch, cloud=False)
        assert DreameVacuumProperty.BATTERY_LEVEL in device._default_properties
        assert DreameVacuumProperty.TAKE_PHOTO not in device._default_properties
        assert DreameVacuumProperty.MAP_DATA not in device._default_properties

    def test_task_status_listener_registered_at_construction(self, monkeypatch) -> None:
        device, _protocol_instance, _map_manager_instance = _build_device(monkeypatch, cloud=False)
        did = DreameVacuumProperty.TASK_STATUS.value
        assert device._task_status_changed in device._property_update_callback[did]


class TestConnectedCallback:
    def test_not_ready_is_noop(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d._ready = False
        d._connected_callback()
        assert not hasattr(d, "available") or d.available is False

    def test_ready_marks_available_schedules_update_and_notifies(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d._ready = True
        d.available = False
        scheduled: list[tuple[object, ...]] = []
        d.schedule_update = lambda *args: scheduled.append(args)
        d._property_changed = MagicMock()

        d._connected_callback()

        assert d.available is True
        assert scheduled == [(2, True)]
        d._property_changed.assert_called_once_with()


# ---------------------------------------------------------------------------
# Warm-boot initial property load (persisted inventory)
# ---------------------------------------------------------------------------


def _warm_boot_device(inventory, *, model="dreame.vacuum.test", firmware="1.0"):
    from types import SimpleNamespace

    import custom_components.dreame_vacuum.dreame.device as device_module

    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    d.info = SimpleNamespace(model=model, firmware_version=firmware)
    d.disconnected = False
    d.data = {}
    d._property_inventory = inventory
    d._pending_properties = set()
    d._inventory_callback = MagicMock()
    d._full_properties_loaded = False
    d._property_changed = MagicMock()
    d._request_properties = MagicMock(return_value=True)
    d._default_properties = list(DreameVacuumPropertyMapping.keys())
    return d, device_module


class TestWarmBootInitialLoad:
    def test_without_inventory_full_sync_load_and_publish(self) -> None:
        d, _ = _warm_boot_device(None)
        d.data = {DreameVacuumProperty.BATTERY_LEVEL.value: 90}

        d._request_initial_properties()

        d._request_properties.assert_called_once_with(force_all=True)
        assert d._full_properties_loaded is True
        assert d._pending_properties == set()
        inv = d._inventory_callback.call_args.args[0]
        assert inv["model"] == "dreame.vacuum.test"
        assert DreameVacuumProperty.BATTERY_LEVEL.value in inv["present"]
        assert DreameVacuumProperty.BATTERY_LEVEL.value not in inv["absent"]

    def test_firmware_mismatch_falls_back_to_full_load(self) -> None:
        inventory = {"model": "dreame.vacuum.test", "firmware": "0.9", "present": [1], "absent": []}
        d, _ = _warm_boot_device(inventory)

        d._request_initial_properties()

        d._request_properties.assert_called_once_with(force_all=True)

    def test_matching_inventory_splits_priority_and_defers_rest(self, monkeypatch) -> None:
        mapped = [p.value for p in DreameVacuumPropertyMapping if "aiid" not in DreameVacuumPropertyMapping[p]]
        inventory = {"model": "dreame.vacuum.test", "firmware": "1.0", "present": mapped, "absent": []}
        d, device_module = _warm_boot_device(inventory)

        started = {}

        class _InlineThread:
            def __init__(self, target=None, args=(), daemon=None):
                started["target"], started["args"] = target, args

            def start(self):
                started["target"](*started["args"])

        monkeypatch.setattr(device_module, "Thread", _InlineThread)

        d._request_initial_properties()

        # Premier appel synchrone : uniquement les propriétés prioritaires.
        first_call = d._request_properties.call_args_list[0]
        priority_values = {p.value for p in first_call.args[0]}
        assert priority_values <= set(device_module._PRIORITY_BOOT_DIDS)
        assert first_call.kwargs == {"force_all": True}

        # Le différé couvre tout le reste des présents, par lots de <= 50.
        deferred_calls = d._request_properties.call_args_list[1:]
        deferred_values = [p.value for c in deferred_calls for p in c.args[0]]
        expected_deferred = [v for v in mapped if v not in device_module._PRIORITY_BOOT_DIDS]
        assert sorted(deferred_values) == sorted(expected_deferred)
        assert all(len(c.args[0]) <= 50 for c in deferred_calls)

        # Fin de chargement : plus rien en attente, inventaire republié.
        assert d._pending_properties == set()
        assert d._full_properties_loaded is True
        d._inventory_callback.assert_called_once()

    def test_deferred_failure_never_leaves_entities_gated(self, monkeypatch) -> None:
        mapped = [p.value for p in DreameVacuumPropertyMapping if "aiid" not in DreameVacuumPropertyMapping[p]]
        inventory = {"model": "dreame.vacuum.test", "firmware": "1.0", "present": mapped, "absent": []}
        d, device_module = _warm_boot_device(inventory)

        calls = {"n": 0}

        def _req(props=None, force_all=False):
            calls["n"] += 1
            if calls["n"] == 2:  # premier lot différé
                from custom_components.dreame_vacuum.dreame.exceptions import DeviceException

                raise DeviceException("boom")
            return True

        d._request_properties = MagicMock(side_effect=_req)

        class _InlineThread:
            def __init__(self, target=None, args=(), daemon=None):
                self._t, self._a = target, args

            def start(self):
                self._t(*self._a)

        monkeypatch.setattr(device_module, "Thread", _InlineThread)

        d._request_initial_properties()

        assert d._pending_properties == set()
        d._property_changed.assert_called_with(False)
