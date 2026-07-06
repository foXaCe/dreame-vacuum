"""Characterization tests for the lifecycle/orchestration layer of DreameMapVacuumMapManager.

Covers:
- handle_properties (push-property parsing, mirrors _request_i_map's OLD_MAP_DATA parsing)
- get_map, listen/listen_error, _map_data_updated/_map_data_changed, _update_task
- schedule_update (threading.Timer bookkeeping)
- update() -- the main polling state machine (every branch is mocked-isolated via a
  "quiet" baseline fixture that makes every branch a no-op unless a test deliberately
  overrides just the state needed to trigger the one branch under test)
- set_capability / set_update_interval / set_device_running / set_device_docked
- request_map_list (remaining branches) / request_recovery_map_list / _refresh_recovery_map_list
- the trivial read-only properties (ready, map_list, map_data_list, selected_map, cleaning_sequence)

The protocol/cloud layer is fully mocked (MagicMock); no network I/O and no real
threading.Timer/sleep occurs (both are monkeypatched away).
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame import map_manager as map_manager_module
from custom_components.dreame_vacuum.dreame.const import MAP_PARAMETER_VALUE
from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
from custom_components.dreame_vacuum.dreame.map_manager import DreameMapVacuumMapManager
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    PIID,
    DreameVacuumProperty,
    MapData,
    RecoveryMapInfo,
)


@pytest.fixture
def protocol() -> MagicMock:
    proto = MagicMock()
    proto.dreame_cloud = False
    proto.cloud = MagicMock()
    proto.cloud.dreame_cloud = False
    proto.cloud.logged_in = True
    proto.cloud.connected = True
    return proto


@pytest.fixture
def manager(protocol: MagicMock) -> DreameMapVacuumMapManager:
    return DreameMapVacuumMapManager(protocol)


def _out_entry(prop: DreameVacuumProperty, value: str) -> dict[str, object]:
    return {"piid": PIID(prop), MAP_PARAMETER_VALUE: value}


# ---------------------------------------------------------------------------
# handle_properties
# ---------------------------------------------------------------------------


def test_handle_properties_noop_when_not_ready(manager: DreameMapVacuumMapManager) -> None:
    manager._ready = False
    manager._add_cloud_map_data = MagicMock()

    manager.handle_properties([_out_entry(DreameVacuumProperty.OBJECT_NAME, "obj")])

    manager._add_cloud_map_data.assert_not_called()


def test_handle_properties_object_name_clears_pending_map_request_time(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._ready = True
    manager._map_request_time = 999
    manager._add_cloud_map_data = MagicMock()

    manager.handle_properties([_out_entry(DreameVacuumProperty.OBJECT_NAME, "obj_name")])

    assert manager._map_request_time is None
    manager._add_cloud_map_data.assert_called_once()
    args = manager._add_cloud_map_data.call_args.args
    assert args[0] is None
    assert args[1] == "obj_name"


def test_handle_properties_raw_map_data_is_decoded_and_forwarded(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._ready = True
    sentinel_partial = object()
    manager._decode_map_partial = MagicMock(return_value=sentinel_partial)
    manager._add_cloud_map_data = MagicMock()

    manager.handle_properties([_out_entry(DreameVacuumProperty.MAP_DATA, "raw_bytes")])

    manager._decode_map_partial.assert_called_once()
    assert manager._decode_map_partial.call_args.args[0] == "raw_bytes"
    args = manager._add_cloud_map_data.call_args.args
    assert args[0] == [sentinel_partial]
    assert args[1] is None


def test_handle_properties_old_map_data_raw_variant(manager: DreameMapVacuumMapManager) -> None:
    manager._ready = True
    manager._decode_map_partial = MagicMock(return_value=object())
    manager._add_cloud_map_data = MagicMock()

    manager.handle_properties([_out_entry(DreameVacuumProperty.OLD_MAP_DATA, "0,raw_payload")])

    manager._decode_map_partial.assert_called_once()
    assert manager._decode_map_partial.call_args.args[0] == "raw_payload"


def test_handle_properties_old_map_data_object_name_variant_with_extra_segment(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._ready = True
    manager._add_cloud_map_data = MagicMock()

    manager.handle_properties([_out_entry(DreameVacuumProperty.OLD_MAP_DATA, "1,object_name,extra")])

    args = manager._add_cloud_map_data.call_args.args
    assert args[1] == "object_name,extra"


def test_handle_properties_old_map_data_ignored_when_object_name_already_seen(
    manager: DreameMapVacuumMapManager,
) -> None:
    """OLD_MAP_DATA is only a fallback: an OBJECT_NAME/MAP_DATA entry earlier in the batch wins."""
    manager._ready = True
    manager._add_cloud_map_data = MagicMock()

    manager.handle_properties(
        [
            _out_entry(DreameVacuumProperty.OBJECT_NAME, "primary_obj"),
            _out_entry(DreameVacuumProperty.OLD_MAP_DATA, "1,ignored_obj"),
        ]
    )

    args = manager._add_cloud_map_data.call_args.args
    assert args[1] == "primary_obj"


def test_handle_properties_empty_values_are_ignored_entirely(manager: DreameMapVacuumMapManager) -> None:
    manager._ready = True
    manager._add_cloud_map_data = MagicMock()

    manager.handle_properties([_out_entry(DreameVacuumProperty.OBJECT_NAME, "")])

    manager._add_cloud_map_data.assert_not_called()


# ---------------------------------------------------------------------------
# get_map / listen / listen_error / _map_data_updated / _map_data_changed / _update_task
# ---------------------------------------------------------------------------


def test_get_map_default_returns_live_map_data(manager: DreameMapVacuumMapManager) -> None:
    live = MapData()
    manager._map_data = live

    assert manager.get_map() is live


def test_get_map_by_index_returns_saved_map(manager: DreameMapVacuumMapManager) -> None:
    saved = MapData()
    manager._map_list = [10, 20]
    manager._saved_map_data = {10: MapData(), 20: saved}

    assert manager.get_map(2) is saved


def test_get_map_by_index_out_of_range_returns_none(manager: DreameMapVacuumMapManager) -> None:
    manager._map_list = [10]

    assert manager.get_map(5) is None


def test_listen_registers_both_callbacks(manager: DreameMapVacuumMapManager) -> None:
    change_cb = MagicMock()
    update_cb = MagicMock()

    manager.listen(change_cb, update_cb)

    assert manager._change_callback is change_cb
    assert manager._update_callback is update_cb


def test_listen_error_registers_callback(manager: DreameMapVacuumMapManager) -> None:
    error_cb = MagicMock()

    manager.listen_error(error_cb)

    assert manager._error_callback is error_cb


def test_map_data_updated_invokes_registered_callback(manager: DreameMapVacuumMapManager) -> None:
    manager._update_callback = MagicMock()

    manager._map_data_updated()

    manager._update_callback.assert_called_once()


def test_map_data_updated_is_noop_without_callback(manager: DreameMapVacuumMapManager) -> None:
    manager._update_callback = None

    manager._map_data_updated()  # must not raise


def test_map_data_changed_invokes_registered_callback_with_flag(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._change_callback = MagicMock()

    manager._map_data_changed(True)

    manager._change_callback.assert_called_once_with(True)


def test_update_task_runs_update_cancels_existing_timer_and_reschedules(
    manager: DreameMapVacuumMapManager,
) -> None:
    old_timer = MagicMock()
    manager._update_timer = old_timer
    manager.update = MagicMock()
    manager.schedule_update = MagicMock()
    manager._update_interval = 10

    manager._update_task()

    old_timer.cancel.assert_called_once()
    assert manager._update_timer is None
    manager.update.assert_called_once()
    manager.schedule_update.assert_called_once()
    # The wait passed is close to the configured interval (elapsed time is negligible here).
    wait_arg = manager.schedule_update.call_args.args[0]
    assert 9 <= wait_arg <= 10


# ---------------------------------------------------------------------------
# schedule_update
# ---------------------------------------------------------------------------


def test_schedule_update_creates_timer_with_explicit_wait(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    timer_instance = MagicMock()
    timer_cls = MagicMock(return_value=timer_instance)
    monkeypatch.setattr(map_manager_module.threading, "Timer", timer_cls)

    manager.schedule_update(5)

    timer_cls.assert_called_once_with(5, manager._update_task)
    timer_instance.start.assert_called_once()
    assert manager._update_timer is timer_instance


def test_schedule_update_defaults_to_update_interval_when_wait_is_none(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    timer_cls = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(map_manager_module.threading, "Timer", timer_cls)
    manager._update_interval = 42

    manager.schedule_update()

    timer_cls.assert_called_once_with(42, manager._update_task)


def test_schedule_update_cancels_previous_timer_first(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_timer = MagicMock()
    manager._update_timer = old_timer
    monkeypatch.setattr(map_manager_module.threading, "Timer", MagicMock(return_value=MagicMock()))

    manager.schedule_update(1)

    old_timer.cancel.assert_called_once()


def test_schedule_update_negative_wait_skips_new_timer(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    timer_cls = MagicMock()
    monkeypatch.setattr(map_manager_module.threading, "Timer", timer_cls)

    manager.schedule_update(-1)

    timer_cls.assert_not_called()
    assert manager._update_timer is None


def test_schedule_update_skips_new_timer_when_disconnected(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager._disconnected = True
    timer_cls = MagicMock()
    monkeypatch.setattr(map_manager_module.threading, "Timer", timer_cls)

    manager.schedule_update(5)

    timer_cls.assert_not_called()


# ---------------------------------------------------------------------------
# update(): a "quiet" baseline makes every branch inert unless deliberately triggered
# ---------------------------------------------------------------------------


@pytest.fixture
def quiet_manager(manager: DreameMapVacuumMapManager) -> DreameMapVacuumMapManager:
    """A manager whose update() call is a complete no-op from this baseline state."""
    manager._protocol.dreame_cloud = True
    manager._protocol.cloud.connected = True
    manager._device_running = False
    manager._available = True
    manager._connected = True
    manager._map_list_object_name = None
    manager._need_map_list_request = None
    manager._recovery_map_list_object_name = None
    manager._need_recovery_map_list_request = False
    manager._need_new_map = False
    manager._map_request_time = None
    manager._need_map_request = False
    live = MagicMock()
    live.empty_map = False
    live.last_updated = time.time()
    manager._map_data = live
    # Mock every side-effecting collaborator so an unexpected branch firing is obvious.
    manager.request_map_list = MagicMock()
    manager.request_recovery_map_list = MagicMock()
    manager.request_new_map = MagicMock()
    manager._request_current_map = MagicMock(return_value=True)
    manager._request_map_from_cloud = MagicMock(return_value=True)
    manager._request_map = MagicMock()
    manager._change_callback = MagicMock()
    return manager


def test_update_returns_immediately_when_lock_already_held(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._update_lock.acquire()
    try:
        quiet_manager._ready = False
        quiet_manager.update()
        assert quiet_manager._ready is False  # body (incl. `finally`) never ran
        quiet_manager.request_map_list.assert_not_called()
    finally:
        quiet_manager._update_lock.release()


def test_update_baseline_is_truly_inert(quiet_manager: DreameMapVacuumMapManager) -> None:
    """Sanity check for the fixture itself: nothing fires from the quiet baseline."""
    quiet_manager.update()

    quiet_manager.request_map_list.assert_not_called()
    quiet_manager.request_recovery_map_list.assert_not_called()
    quiet_manager.request_new_map.assert_not_called()
    quiet_manager._request_current_map.assert_not_called()
    quiet_manager._request_map.assert_not_called()
    assert quiet_manager._ready is True


@pytest.mark.parametrize(
    ("need_map_list_request", "device_running", "should_call"),
    [
        (None, False, True),  # object_name set + never requested yet
        (True, False, True),  # explicitly flagged + idle
        (True, True, False),  # flagged but currently cleaning: wait
        (False, False, False),  # nothing pending
    ],
)
def test_update_map_list_request_dispatch_conditions(
    quiet_manager: DreameMapVacuumMapManager,
    need_map_list_request: bool | None,
    device_running: bool,
    should_call: bool,
) -> None:
    quiet_manager._map_list_object_name = "list_obj"
    quiet_manager._need_map_list_request = need_map_list_request
    quiet_manager._device_running = device_running

    quiet_manager.update()

    assert quiet_manager.request_map_list.called is should_call


def test_update_requests_recovery_map_list_when_flagged(quiet_manager: DreameMapVacuumMapManager) -> None:
    quiet_manager._recovery_map_list_object_name = "recovery_obj"
    quiet_manager._need_recovery_map_list_request = True

    quiet_manager.update()

    quiet_manager.request_recovery_map_list.assert_called_once()


def test_update_requests_new_map_and_clears_flag(quiet_manager: DreameMapVacuumMapManager) -> None:
    quiet_manager._need_new_map = True

    quiet_manager.update()

    quiet_manager.request_new_map.assert_called_once()
    assert quiet_manager._need_new_map is False


def test_update_map_request_success_calls_current_map_with_saved_time(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._map_request_time = 555
    quiet_manager._map_request_count = 0

    quiet_manager.update()

    quiet_manager._request_current_map.assert_called_once_with(555)
    assert quiet_manager._map_request_count == 1


def test_update_map_request_gives_up_after_six_attempts(quiet_manager: DreameMapVacuumMapManager) -> None:
    quiet_manager._need_map_request = True
    quiet_manager._map_request_count = 5  # becomes 6 on this call -> gives up

    quiet_manager.update()

    quiet_manager._request_current_map.assert_not_called()
    assert quiet_manager._map_request_time is None
    assert quiet_manager._need_map_request is False


def test_update_map_request_falls_back_to_cloud_object_name_on_third_dreame_cloud_attempt(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._need_map_request = True
    quiet_manager._map_request_count = 1  # becomes 2 on this call
    quiet_manager._map_data = None
    quiet_manager._request_current_map = MagicMock(return_value=False)
    quiet_manager._protocol.cloud.get_properties = MagicMock(
        return_value=[{MAP_PARAMETER_VALUE: "cloud_obj", "updateDate": 4321}]
    )
    quiet_manager._add_cloud_map_data = MagicMock()

    quiet_manager.update()

    quiet_manager._add_cloud_map_data.assert_called_once_with(None, "cloud_obj", 4321)


def test_update_local_polling_requests_current_map_when_no_map_data_yet(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._protocol.dreame_cloud = False
    quiet_manager._map_data = None
    quiet_manager._protocol.cloud.logged_in = True

    quiet_manager.update()

    quiet_manager._request_current_map.assert_called_once_with()


def test_update_local_polling_requests_current_map_when_stale_while_running(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._protocol.dreame_cloud = False
    quiet_manager._device_running = True
    quiet_manager._current_timestamp_ms = 0  # "ages" ago
    quiet_manager._protocol.cloud.logged_in = True

    quiet_manager.update()

    quiet_manager._request_current_map.assert_called_once_with()


def test_update_local_polling_polls_cloud_when_map_fresh_and_idle(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._protocol.dreame_cloud = False
    quiet_manager._current_timestamp_ms = int(time.time() * 1000)
    quiet_manager._device_running = False

    quiet_manager.update()

    quiet_manager._request_map_from_cloud.assert_called_once()
    quiet_manager._request_current_map.assert_not_called()


def test_update_local_polling_retries_once_then_gives_up_and_schedules_retry(
    quiet_manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleep_mock = MagicMock()
    monkeypatch.setattr(map_manager_module, "sleep", sleep_mock)
    quiet_manager._protocol.dreame_cloud = False
    quiet_manager._current_timestamp_ms = int(time.time() * 1000)
    quiet_manager._device_running = True
    quiet_manager._request_map_from_cloud = MagicMock(return_value=False)
    quiet_manager.schedule_update = MagicMock()

    quiet_manager.update()

    sleep_mock.assert_called_once_with(1)
    assert quiet_manager._request_map_from_cloud.call_count == 2
    quiet_manager.schedule_update.assert_called_once_with(1)


def test_update_local_polling_retry_succeeds_and_does_not_reschedule(
    quiet_manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleep_mock = MagicMock()
    monkeypatch.setattr(map_manager_module, "sleep", sleep_mock)
    quiet_manager._protocol.dreame_cloud = False
    quiet_manager._current_timestamp_ms = int(time.time() * 1000)
    quiet_manager._device_running = True
    quiet_manager._request_map_from_cloud = MagicMock(side_effect=[False, True])
    quiet_manager.schedule_update = MagicMock()

    quiet_manager.update()

    sleep_mock.assert_called_once_with(1)
    quiet_manager.schedule_update.assert_not_called()


def test_update_dreame_cloud_requests_current_map_when_no_map_data(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._map_data = None

    quiet_manager.update()

    quiet_manager._request_current_map.assert_called_once_with()


def test_update_dreame_cloud_requests_full_map_when_stale_and_running(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._device_running = True
    quiet_manager._map_data.last_updated = time.time() - 120  # > 60s stale

    quiet_manager.update()

    quiet_manager._request_map.assert_called_once()
    quiet_manager._request_current_map.assert_not_called()


def test_update_dreame_cloud_requests_current_map_when_empty_map_and_running(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._device_running = True
    quiet_manager._map_data.empty_map = True
    quiet_manager._map_data.last_updated = time.time()

    quiet_manager.update()

    quiet_manager._request_current_map.assert_called_once_with()
    quiet_manager._request_map.assert_not_called()


def test_update_dreame_cloud_reconnect_flips_connected_and_notifies(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._connected = False

    quiet_manager.update()

    assert quiet_manager._connected is True
    quiet_manager._change_callback.assert_any_call(False)


def test_update_dreame_cloud_disconnect_flips_connected_and_notifies(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._protocol.cloud.connected = False

    quiet_manager.update()

    assert quiet_manager._connected is False
    quiet_manager._change_callback.assert_any_call(False)


def test_update_flips_available_true_and_notifies_on_first_successful_pass(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._available = False

    quiet_manager.update()

    assert quiet_manager._available is True
    quiet_manager._change_callback.assert_any_call(False)


def test_update_exception_marks_unavailable_and_invokes_error_callback(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._map_list_object_name = "obj"
    quiet_manager._need_map_list_request = None
    quiet_manager.request_map_list = MagicMock(side_effect=RuntimeError("boom"))
    error_cb = MagicMock()
    quiet_manager.listen_error(error_cb)
    assert quiet_manager._available is True

    quiet_manager.update()

    assert quiet_manager._available is False
    error_cb.assert_called_once()
    assert quiet_manager._ready is True  # `finally` still ran


def test_update_exception_while_already_unavailable_skips_error_callback(
    quiet_manager: DreameMapVacuumMapManager,
) -> None:
    quiet_manager._available = False
    quiet_manager._map_list_object_name = "obj"
    quiet_manager._need_map_list_request = None
    quiet_manager.request_map_list = MagicMock(side_effect=RuntimeError("boom"))
    error_cb = MagicMock()
    quiet_manager.listen_error(error_cb)

    quiet_manager.update()

    error_cb.assert_not_called()
    assert quiet_manager._ready is True


# ---------------------------------------------------------------------------
# set_capability / set_update_interval / set_device_running / set_device_docked
# ---------------------------------------------------------------------------


def test_set_capability_noop_for_none(manager: DreameMapVacuumMapManager) -> None:
    manager.set_capability(None)

    assert manager._capability is None
    assert manager._vslam_map is False


def test_set_capability_lidar_navigation_keeps_lidar_mode(manager: DreameMapVacuumMapManager) -> None:
    capability = MagicMock(lidar_navigation=True, key="iv_key")

    manager.set_capability(capability)

    assert manager._capability is capability
    assert manager._vslam_map is False
    assert manager._aes_iv == "iv_key"


def test_set_capability_non_lidar_enables_vslam_mode(manager: DreameMapVacuumMapManager) -> None:
    capability = MagicMock(lidar_navigation=False, key="iv_key2")

    manager.set_capability(capability)

    assert manager._vslam_map is True
    assert manager._aes_iv == "iv_key2"


def test_set_update_interval_changes_and_reschedules(manager: DreameMapVacuumMapManager) -> None:
    manager.schedule_update = MagicMock()
    manager._update_interval = 10

    manager.set_update_interval(30)

    assert manager._update_interval == 30
    manager.schedule_update.assert_called_once_with()


def test_set_update_interval_unchanged_value_is_noop(manager: DreameMapVacuumMapManager) -> None:
    manager.schedule_update = MagicMock()
    manager._update_interval = 10

    manager.set_update_interval(10)

    manager.schedule_update.assert_not_called()


def test_set_device_running_updates_running_flag(manager: DreameMapVacuumMapManager) -> None:
    manager.schedule_update = MagicMock()

    manager.set_device_running(True, False)

    assert manager._device_running is True


def test_set_device_running_docked_non_vslam_requests_full_map(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager.schedule_update = MagicMock()
    manager._vslam_map = False
    manager._request_map = MagicMock()

    manager.set_device_running(False, True)

    manager._request_map.assert_called_once()
    assert manager._device_docked is True
    manager.schedule_update.assert_called_once_with(2)


def test_set_device_running_docked_vslam_saved_map_status_restores_layout(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager.schedule_update = MagicMock()
    manager._vslam_map = True
    saved = MapData()
    saved.segments = {"1": "room"}
    saved.data = "saved_data"
    saved.pixel_type = "saved_pixel"
    saved.dimensions = "saved_dims"
    saved.charger_position = "saved_charger"
    saved.no_go_areas = ["ng"]
    saved.no_mopping_areas = ["nm"]
    saved.virtual_walls = ["vw"]
    manager._selected_map_id = 5
    manager._saved_map_data = {5: saved}

    live = MapData()
    live.saved_map_status = 1
    manager._map_data = live
    manager._change_callback = MagicMock()

    manager.set_device_running(False, True)

    assert live.segments == {"1": "room"}
    assert live.data == "saved_data"
    assert live.docked is True
    assert live.path is None
    assert live.need_optimization is False
    assert live.saved_map_status == 2
    assert live.robot_position == live.charger_position
    manager._change_callback.assert_called_once_with(False)


def test_set_device_running_docked_unchanged_skips_all_side_effects(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager.schedule_update = MagicMock()
    manager._device_docked = True
    manager._request_map = MagicMock()

    manager.set_device_running(True, True)  # docked stays True -> no change

    manager._request_map.assert_not_called()
    manager.schedule_update.assert_not_called()


def test_set_device_docked_schedules_update_on_change(manager: DreameMapVacuumMapManager) -> None:
    manager.schedule_update = MagicMock()
    manager._device_docked = False

    manager.set_device_docked(True)

    assert manager._device_docked is True
    manager.schedule_update.assert_called_once_with(2)


def test_set_device_docked_unchanged_skips_reschedule(manager: DreameMapVacuumMapManager) -> None:
    manager.schedule_update = MagicMock()
    manager._device_docked = True

    manager.set_device_docked(True)

    manager.schedule_update.assert_not_called()


# ---------------------------------------------------------------------------
# request_map_list: remaining branches not covered by test_map_manager.py
# ---------------------------------------------------------------------------


def test_request_map_list_noop_without_object_name(manager: DreameMapVacuumMapManager) -> None:
    manager._map_list_object_name = None
    manager._get_interim_file_data = MagicMock()

    manager.request_map_list()

    manager._get_interim_file_data.assert_not_called()


def test_request_map_list_noop_when_not_logged_in(manager: DreameMapVacuumMapManager) -> None:
    manager._map_list_object_name = "list_obj"
    manager._protocol.cloud.logged_in = False
    manager._get_interim_file_data = MagicMock()

    manager.request_map_list()

    manager._get_interim_file_data.assert_not_called()


def test_request_map_list_swallows_fetch_exception(manager: DreameMapVacuumMapManager) -> None:
    manager._map_list_object_name = "list_obj"
    manager._get_interim_file_data = MagicMock(side_effect=RuntimeError("network down"))

    manager.request_map_list()  # must not raise


def test_request_map_list_noop_when_response_is_falsy(manager: DreameMapVacuumMapManager) -> None:
    manager._map_list_object_name = "list_obj"
    manager._get_interim_file_data = MagicMock(return_value=None)

    manager.request_map_list()  # must not raise; _need_map_list_request untouched
    assert manager._need_map_list_request is None


def test_request_map_list_swallows_invalid_json(manager: DreameMapVacuumMapManager) -> None:
    manager._map_list_object_name = "list_obj"
    manager._get_interim_file_data = MagicMock(return_value=b"not valid json {")

    manager.request_map_list()  # must not raise


def test_request_map_list_fetches_rismobj_referenced_map_successfully(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager._map_list_object_name = "list_obj"
    payload = {
        "server": 1,
        "mapstr": [{"rismobj": "rism_obj_1", "name": "Bedroom"}],
        "curr_id": 4,
    }

    def fake_fetch(object_name: str = "", timestamp: object = None) -> object:
        if object_name == "list_obj":
            return json.dumps(payload).encode()
        assert object_name == "rism_obj_1"
        return b"raw_saved_map"

    manager._get_interim_file_data = MagicMock(side_effect=fake_fetch)
    good_map = MapData()
    good_map.map_id = 4
    good_map.wifi_map_data = None
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_saved_map", MagicMock(return_value=good_map))

    manager.request_map_list()

    assert manager._saved_map_data[4].map_name == "Bedroom"


def test_request_map_list_existing_map_unchanged_keeps_object_and_does_not_flag_change(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A decoded saved map identical (per MapData.__eq__) to what's already stored is left alone."""
    manager._map_list_object_name = "list_obj"
    existing = MapData()
    existing.map_id = 2
    existing.wifi_map_data = None
    existing.custom_name = "Kitchen"
    existing.object_name = "obj2"  # set by a previous pass the same way the payload below sets it
    manager._saved_map_data = {2: existing}
    # Matches the payload's curr_id below, so the "selected map id changed" trigger
    # (a separate `changed=True` source, unrelated to per-map content) does not fire
    # and this test can isolate the per-map content-equality check in question.
    manager._selected_map_id = 2

    decoded = MapData()
    decoded.map_id = 2
    decoded.wifi_map_data = None
    decoded.custom_name = "Kitchen"

    payload = {"mapstr": [{"map": "raw", "mapobj": "obj2", "name": "Kitchen"}], "curr_id": 2}
    manager._get_interim_file_data = MagicMock(return_value=json.dumps(payload).encode())
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_saved_map", MagicMock(return_value=decoded))
    manager._refresh_map_list = MagicMock()

    manager.request_map_list()

    # _refresh_map_list() is only invoked when something changed; here nothing did.
    manager._refresh_map_list.assert_not_called()
    assert manager._saved_map_data[2] is existing


def test_request_map_list_removes_maps_no_longer_present(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager._map_list_object_name = "list_obj"
    stale = MapData()
    stale.map_id = 99
    manager._saved_map_data = {99: stale}

    # curr_id must differ from the stale map: a still-"selected" map is explicitly
    # protected from deletion even when absent from the list (see the companion test
    # test_request_map_list_updates_selected_map_id_and_notifies for that case).
    payload = {"mapstr": [], "curr_id": 1}
    manager._get_interim_file_data = MagicMock(return_value=json.dumps(payload).encode())

    manager.request_map_list()

    assert 99 not in manager._saved_map_data


def test_request_map_list_updates_selected_map_id_and_notifies(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager._map_list_object_name = "list_obj"
    existing = MapData()
    existing.map_id = 3
    manager._saved_map_data = {3: existing}
    manager._selected_map_id = None
    manager._map_data = MagicMock()  # a live map exists -> triggers _map_data_changed(True)
    manager._change_callback = MagicMock()
    manager.request_next_recovery_map_list = MagicMock()

    payload = {"mapstr": [], "curr_id": 3}
    manager._get_interim_file_data = MagicMock(return_value=json.dumps(payload).encode())

    manager.request_map_list()

    assert manager._selected_map_id == 3
    manager._change_callback.assert_called_once_with(True)
    manager.request_next_recovery_map_list.assert_called_once()


def test_request_map_list_existing_non_selected_map_is_fully_replaced_with_wifi_sync(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    For an existing map that is NOT the selected+live one, a real content change fully
    replaces the stored object (unlike the selected+live special case), and a
    wifi_map_data sub-object's last_updated is kept in sync with its parent.
    """
    manager._map_list_object_name = "list_obj"
    existing = MapData()
    existing.map_id = 2
    existing.wifi_map_data = None
    manager._saved_map_data = {2: existing}
    manager._selected_map_id = None  # not selected -> takes the "replace" branch
    manager._map_data = None

    wifi_sub_map = MapData()
    decoded = MapData()
    decoded.map_id = 2
    decoded.wifi_map_data = wifi_sub_map
    decoded.custom_name = "Changed"  # forces inequality -> "changed" path

    payload = {"mapstr": [{"map": "raw", "mapobj": "obj2", "name": "Changed"}], "curr_id": 2}
    manager._get_interim_file_data = MagicMock(return_value=json.dumps(payload).encode())
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_saved_map", MagicMock(return_value=decoded))

    manager.request_map_list()

    assert manager._saved_map_data[2] is decoded
    assert wifi_sub_map.last_updated == decoded.last_updated


def test_request_map_list_new_map_with_wifi_map_data_syncs_timestamp(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A brand new saved map entry with a wifi_map_data sub-object gets it timestamp-synced too."""
    manager._map_list_object_name = "list_obj"
    manager._saved_map_data = {}

    wifi_sub_map = MapData()
    decoded = MapData()
    decoded.map_id = 9
    decoded.wifi_map_data = wifi_sub_map

    payload = {"mapstr": [{"map": "raw", "mapobj": "obj9"}], "curr_id": 9}
    manager._get_interim_file_data = MagicMock(return_value=json.dumps(payload).encode())
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_saved_map", MagicMock(return_value=decoded))

    manager.request_map_list()

    assert manager._saved_map_data[9] is decoded
    assert wifi_sub_map.last_updated == decoded.last_updated


def test_request_map_list_updating_selected_map_only_merges_custom_name_and_rotation(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    BUG (documented, not fixed per task instructions): for the currently selected+live
    map, request_map_list() computes `saved_map_data.cleanset = self._map_data.cleanset`
    (map_manager.py line 1381), apparently intending the live cleanset to be persisted.
    But the storage branch actually taken for this exact case (map_data is not None and
    selected_map_id == map_id, lines 1392-1396) never stores that `saved_map_data` object
    at all -- it only copies `custom_name` and `rotation` onto the *existing* stored
    object. The cleanset computed at line 1381 is therefore dead: the live map's cleanset
    is never written back into _saved_map_data for the selected map through this path.
    This test pins the actual (buggy) behavior: the OLD stored cleanset survives
    untouched, even though the code visibly tried to sync in the live one.
    """
    manager._map_list_object_name = "list_obj"
    existing = MapData()
    existing.map_id = 2
    existing.wifi_map_data = None
    existing.cleanset = "OLD_CLEANSET"
    manager._saved_map_data = {2: existing}
    manager._selected_map_id = 2
    live = MagicMock()
    live.cleanset = "LIVE_CLEANSET"
    manager._map_data = live

    decoded = MapData()
    decoded.map_id = 2
    decoded.wifi_map_data = None
    decoded.cleanset = "DECODED_CLEANSET"
    decoded.custom_name = "Changed Name"  # forces inequality -> "changed" path taken

    payload = {"mapstr": [{"map": "raw", "mapobj": "obj2"}], "curr_id": 2}
    manager._get_interim_file_data = MagicMock(return_value=json.dumps(payload).encode())
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_saved_map", MagicMock(return_value=decoded))

    manager.request_map_list()

    # custom_name IS merged (the one field the else-branch actually copies)...
    assert manager._saved_map_data[2].custom_name == "Changed Name"
    # ...but cleanset stays stuck at its old value instead of picking up the live one.
    assert manager._saved_map_data[2].cleanset == "OLD_CLEANSET"


# ---------------------------------------------------------------------------
# request_recovery_map_list
# ---------------------------------------------------------------------------


def test_request_recovery_map_list_noop_without_object_name(manager: DreameMapVacuumMapManager) -> None:
    manager._recovery_map_list_object_name = None
    manager._get_file_url = MagicMock()

    manager.request_recovery_map_list()

    manager._get_file_url.assert_not_called()


def test_request_recovery_map_list_vslam_devices_skip_fetch_entirely(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._recovery_map_list_object_name = "recovery_obj"
    manager._vslam_map = True
    manager._need_recovery_map_list_request = True
    manager._get_file_url = MagicMock()

    manager.request_recovery_map_list()

    manager._get_file_url.assert_not_called()
    assert manager._need_recovery_map_list_request is False


def test_request_recovery_map_list_noop_when_no_url(manager: DreameMapVacuumMapManager) -> None:
    manager._recovery_map_list_object_name = "recovery_obj"
    manager._need_recovery_map_list_request = True
    manager._get_file_url = MagicMock(return_value=None)

    manager.request_recovery_map_list()

    assert manager._need_recovery_map_list_request is True  # untouched: never got past the URL fetch


def test_request_recovery_map_list_clears_flag_even_if_file_fetch_fails(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._recovery_map_list_object_name = "recovery_obj"
    manager._need_recovery_map_list_request = True
    manager._get_file_url = MagicMock(return_value="http://recovery")
    manager._protocol.cloud.get_file = MagicMock(return_value=None)

    manager.request_recovery_map_list()

    assert manager._need_recovery_map_list_request is False


def test_request_recovery_map_list_swallows_invalid_json(manager: DreameMapVacuumMapManager) -> None:
    manager._recovery_map_list_object_name = "recovery_obj"
    manager._get_file_url = MagicMock(return_value="http://recovery")
    manager._protocol.cloud.get_file = MagicMock(return_value=b"not json {")

    manager.request_recovery_map_list()  # must not raise


def test_request_recovery_map_list_ignores_entries_for_unknown_map_ids(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._recovery_map_list_object_name = "recovery_obj"
    manager._map_list = [1]  # map_id 99 below is unknown
    manager._get_file_url = MagicMock(return_value="http://recovery")
    payload = [{"id": 99, "info": [{"time": 123, "objname": "x"}]}]
    manager._protocol.cloud.get_file = MagicMock(return_value=json.dumps(payload).encode())

    manager.request_recovery_map_list()  # must not raise / touch _saved_map_data[99] (absent)


def test_request_recovery_map_list_updates_changed_entry_and_notifies(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._recovery_map_list_object_name = "recovery_obj"
    manager._map_list = [1]
    manager._connected = True
    saved = MagicMock(recovery_map_list=None)
    manager._saved_map_data = {1: saved}
    manager._change_callback = MagicMock()
    manager._get_file_url = MagicMock(return_value="http://recovery")
    payload = [
        {
            "id": 1,
            "info": [
                {"time": 111, "thb": "thumb", "rismobj": "r1", "objname": "o1", "first": 1},
            ],
        }
    ]
    manager._protocol.cloud.get_file = MagicMock(return_value=json.dumps(payload).encode())

    manager.request_recovery_map_list()

    assert saved.recovery_map_list is not None
    assert len(saved.recovery_map_list) == 1
    manager._change_callback.assert_called_once_with(True)


def test_request_recovery_map_list_sorts_by_map_type_when_more_than_two_entries(
    manager: DreameMapVacuumMapManager,
) -> None:
    """More than 2 recovery entries for one map triggers a sort-by-map_type pass."""
    manager._recovery_map_list_object_name = "recovery_obj"
    manager._map_list = [1]
    manager._connected = True
    saved = MagicMock(recovery_map_list=None)
    manager._saved_map_data = {1: saved}
    manager._get_file_url = MagicMock(return_value="http://recovery")
    payload = [
        {
            "id": 1,
            "info": [
                {"time": 1, "objname": "o1", "first": 1},  # ORIGINAL (map_type=1)
                {"time": 2, "objname": "o2", "first": 2},  # BACKUP (map_type=2)
                {"time": 3, "objname": "o3", "first": 0},  # EDITED (map_type=0)
            ],
        }
    ]
    manager._protocol.cloud.get_file = MagicMock(return_value=json.dumps(payload).encode())

    manager.request_recovery_map_list()

    assert [int(entry.map_type) for entry in saved.recovery_map_list] == [0, 1, 2]


def test_request_recovery_map_list_unchanged_entry_skips_notification(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._recovery_map_list_object_name = "recovery_obj"
    manager._map_list = [1]

    existing_entry = RecoveryMapInfo(1, 111, None, None, "o1", 1)
    saved = MagicMock(recovery_map_list=[existing_entry])
    manager._saved_map_data = {1: saved}
    manager._change_callback = MagicMock()
    manager._get_file_url = MagicMock(return_value="http://recovery")
    payload = [{"id": 1, "info": [{"time": 111, "objname": "o1", "first": 1}]}]
    manager._protocol.cloud.get_file = MagicMock(return_value=json.dumps(payload).encode())

    manager.request_recovery_map_list()

    manager._change_callback.assert_not_called()


# ---------------------------------------------------------------------------
# _refresh_recovery_map_list
# ---------------------------------------------------------------------------


def test_refresh_recovery_map_list_names_and_indexes_entries_in_map_id_order(
    manager: DreameMapVacuumMapManager,
) -> None:
    entry_a = RecoveryMapInfo(1, None, None, None, "o1", 1)  # ORIGINAL
    entry_b = RecoveryMapInfo(1, None, None, None, "o2", 2)  # BACKUP
    map_with_custom_name = MagicMock(custom_name="Kitchen", recovery_map_list=[entry_a, entry_b])
    map_without_custom_name = MagicMock(custom_name=None, recovery_map_list=[])
    manager._saved_map_data = {1: map_with_custom_name, 2: map_without_custom_name}

    manager._refresh_recovery_map_list()

    assert entry_a.map_index == 1
    assert entry_a.map_name == "Kitchen Recovery Map 1 (Original)"
    assert entry_b.map_index == 2
    assert entry_b.map_name == "Kitchen Recovery Map 2 (Backup)"


def test_refresh_recovery_map_list_uses_generic_name_without_custom_name(
    manager: DreameMapVacuumMapManager,
) -> None:
    entry = RecoveryMapInfo(5, None, None, None, "o1", 0)  # EDITED
    saved = MagicMock(custom_name=None, recovery_map_list=[entry])
    manager._saved_map_data = {5: saved}

    manager._refresh_recovery_map_list()

    assert entry.map_name == "Recovery Map 1 (Edited)"


# ---------------------------------------------------------------------------
# Trivial read-only properties
# ---------------------------------------------------------------------------


def test_ready_property_reflects_internal_flag(manager: DreameMapVacuumMapManager) -> None:
    assert manager.ready is False
    manager._ready = True
    assert manager.ready is True


def test_map_list_property_returns_saved_map_data_keys(manager: DreameMapVacuumMapManager) -> None:
    manager._saved_map_data = {3: MapData(), 7: MapData()}

    assert sorted(manager.map_list) == [3, 7]


def test_map_data_list_property_returns_the_saved_map_dict(manager: DreameMapVacuumMapManager) -> None:
    manager._saved_map_data = {1: MapData()}

    assert manager.map_data_list is manager._saved_map_data


def test_selected_map_property_prefers_explicit_selected_map_id(manager: DreameMapVacuumMapManager) -> None:
    manager._map_data = MagicMock()
    target = MapData()
    manager._selected_map_id = 2
    manager._saved_map_data = {2: target, 5: MapData()}

    assert manager.selected_map is target


def test_selected_map_property_falls_back_to_sole_map_in_map_list(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._map_data = MagicMock()
    target = MapData()
    manager._selected_map_id = None
    manager._map_list = [9]
    manager._saved_map_data = {9: target}

    assert manager.selected_map is target


def test_selected_map_property_none_without_live_map_data(manager: DreameMapVacuumMapManager) -> None:
    manager._map_data = None
    manager._selected_map_id = 2
    manager._saved_map_data = {2: MapData()}

    assert manager.selected_map is None


def test_cleaning_sequence_property_filters_and_sorts_by_order(manager: DreameMapVacuumMapManager) -> None:
    live = MapData()
    live.segments = {
        1: MagicMock(order=2),
        2: MagicMock(order=None),  # excluded: falsy order
        3: MagicMock(order=1),
        4: MagicMock(order=0),  # excluded: falsy order (0)
    }
    manager._map_data = live

    assert manager.cleaning_sequence == [3, 1]


def test_cleaning_sequence_property_empty_without_segments(manager: DreameMapVacuumMapManager) -> None:
    manager._map_data = None

    assert manager.cleaning_sequence == []
