"""Characterization tests for the request/response plumbing of DreameMapVacuumMapManager.

Covers the device- and cloud-facing request helpers that populate map data:
- _request_map_from_cloud (polling model / bootstrap timestamps, connectivity flips)
- _request_map / _request_i_map (device action payloads and response parsing)
- _request_missing_p_map / _request_next_p_map (P frame gap-filling, throttling)
- _request_current_map / request_new_map / request_next_map
- request_next_map_list / request_next_recovery_map_list
- set_map_list_object_name / set_recovery_map_list_object_name

The protocol/cloud layer is fully mocked (MagicMock); no network I/O occurs.
DreameVacuumMapDecoder and the manager's own sibling helpers are monkeypatched
so each test isolates the single method under test.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame.const import (
    MAP_PARAMETER_CODE,
    MAP_PARAMETER_OUT,
    MAP_PARAMETER_VALUE,
)
from custom_components.dreame_vacuum.dreame.map_manager import DreameMapVacuumMapManager
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    DIID,
    PIID,
    DreameVacuumProperty,
    MapFrameType,
)


@pytest.fixture
def protocol() -> MagicMock:
    """Return a MagicMock standing in for DreameVacuumProtocol."""
    proto = MagicMock()
    proto.dreame_cloud = False
    proto.cloud = MagicMock()
    proto.cloud.dreame_cloud = False
    proto.cloud.logged_in = True
    proto.cloud.connected = True
    proto.cloud.object_name = "model/uid/did/0"
    return proto


@pytest.fixture
def manager(protocol: MagicMock) -> DreameMapVacuumMapManager:
    """Return a DreameMapVacuumMapManager wired to the mocked protocol."""
    return DreameMapVacuumMapManager(protocol)


# ---------------------------------------------------------------------------
# _request_map_from_cloud
# ---------------------------------------------------------------------------


def test_request_map_from_cloud_short_circuits_for_dreame_cloud_devices(
    manager: DreameMapVacuumMapManager,
) -> None:
    """Dreame-cloud devices push map data themselves; polling must be skipped entirely."""
    manager._protocol.cloud.dreame_cloud = True

    result = manager._request_map_from_cloud()

    assert result is True
    manager._protocol.cloud.get_device_property.assert_not_called()


def test_request_map_from_cloud_uses_current_timestamp_as_start_time(
    manager: DreameMapVacuumMapManager,
) -> None:
    """When a current map timestamp is known, it seeds the cloud poll start time (floor of seconds)."""
    manager._current_timestamp_ms = 123456789  # -> floor(123456789/1000) = 123456
    manager._protocol.cloud.get_device_property = MagicMock(return_value=[])
    manager._add_cloud_map_data = MagicMock()

    result = manager._request_map_from_cloud()

    assert result is False
    first_call_args = manager._protocol.cloud.get_device_property.call_args_list[0].args
    assert first_call_args[0] == DIID(DreameVacuumProperty.MAP_DATA)
    assert first_call_args[2] == 123456
    assert manager._latest_map_data_time == 123456
    assert manager._latest_object_name_time == 123456


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("_latest_object_name_time", 555, 555),
        ("_map_request_time", 777, 777),
        ("_last_robot_time", 8_000, 8),  # last_robot_time is in ms, converted to seconds
    ],
)
def test_request_map_from_cloud_falls_back_when_no_current_timestamp(
    manager: DreameMapVacuumMapManager, field: str, value: int, expected: int
) -> None:
    """Without a current timestamp, the start time falls back through known watermarks in priority order."""
    setattr(manager, field, value)
    manager._protocol.cloud.get_device_property = MagicMock(return_value=[])
    manager._add_cloud_map_data = MagicMock()

    manager._request_map_from_cloud()

    first_call_args = manager._protocol.cloud.get_device_property.call_args_list[0].args
    assert first_call_args[2] == expected


def test_request_map_from_cloud_flips_connected_false_and_notifies_on_cloud_disconnect(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A cloud disconnect flips _connected and fires the change callback, short-circuiting before object_name."""
    manager._protocol.cloud.connected = False
    manager._protocol.cloud.get_device_property = MagicMock(return_value=[])
    manager._change_callback = MagicMock()
    assert manager._connected is True

    result = manager._request_map_from_cloud()

    assert result is False
    assert manager._connected is False
    manager._change_callback.assert_called_once_with(False)
    # Only the map_data property should have been fetched; bail out before object_name.
    assert manager._protocol.cloud.get_device_property.call_count == 1


def test_request_map_from_cloud_flips_connected_true_and_notifies_on_reconnect(
    manager: DreameMapVacuumMapManager,
) -> None:
    """Reconnecting after a prior disconnect flips _connected back and fires the change callback."""
    manager._connected = False
    manager._protocol.cloud.connected = True
    manager._protocol.cloud.get_device_property = MagicMock(return_value=[])
    manager._change_callback = MagicMock()

    manager._request_map_from_cloud()

    assert manager._connected is True
    manager._change_callback.assert_called_once_with(False)


def test_request_map_from_cloud_treats_none_results_as_empty_and_calls_add_cloud_map_data(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A None result from the cloud (fetch failure) is treated as an empty list, not a crash."""
    manager._protocol.cloud.get_device_property = MagicMock(return_value=None)
    manager._add_cloud_map_data = MagicMock()

    result = manager._request_map_from_cloud()

    assert result is False
    manager._add_cloud_map_data.assert_called_once_with(None, None, None)


def test_request_map_from_cloud_decodes_partial_map_entries_in_order(
    manager: DreameMapVacuumMapManager,
) -> None:
    """Each map_data cloud row is decoded via _decode_map_partial with its ms-scaled timestamp."""
    map_data_result = [
        {MAP_PARAMETER_VALUE: json.dumps(["raw_map_1"]), "time": 100},
        {MAP_PARAMETER_VALUE: json.dumps(["raw_map_2"]), "time": 200},
    ]
    manager._protocol.cloud.get_device_property = MagicMock(
        side_effect=[map_data_result, []],
    )
    sentinel_1, sentinel_2 = object(), object()
    manager._decode_map_partial = MagicMock(side_effect=[sentinel_1, sentinel_2])
    manager._add_cloud_map_data = MagicMock()

    result = manager._request_map_from_cloud()

    assert result is True
    manager._decode_map_partial.assert_any_call("raw_map_1", 100 * 1000)
    manager._decode_map_partial.assert_any_call("raw_map_2", 200 * 1000)
    assert manager._decode_map_partial.call_count == 2
    # Watermark advances from the FIRST row's time, not the last.
    assert manager._latest_map_data_time == 101
    manager._add_cloud_map_data.assert_called_once_with([sentinel_1, sentinel_2], None, None)


def test_request_map_from_cloud_falls_back_to_val_key_when_value_missing(
    manager: DreameMapVacuumMapManager,
) -> None:
    """Some cloud payloads use the short 'val' key instead of 'value'; both must be supported."""
    map_data_result = [{"val": json.dumps(["raw_map"]), "time": 42}]
    manager._protocol.cloud.get_device_property = MagicMock(side_effect=[map_data_result, []])
    manager._decode_map_partial = MagicMock(return_value=object())
    manager._add_cloud_map_data = MagicMock()

    manager._request_map_from_cloud()

    manager._decode_map_partial.assert_called_once_with("raw_map", 42 * 1000)


def test_request_map_from_cloud_single_object_name_entry_is_used(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A single object_name row yields a usable object_name plus an advanced time watermark."""
    object_name_result = [{MAP_PARAMETER_VALUE: json.dumps(["object/name/here"]), "time": 10}]
    manager._protocol.cloud.get_device_property = MagicMock(side_effect=[[], object_name_result])
    manager._add_cloud_map_data = MagicMock()

    result = manager._request_map_from_cloud()

    assert result is True
    assert manager._latest_object_name_time == 11
    manager._add_cloud_map_data.assert_called_once_with(None, "object/name/here", 10 * 1000)


def test_request_map_from_cloud_multiple_object_name_entries_are_ambiguous_and_skipped(
    manager: DreameMapVacuumMapManager,
) -> None:
    """More than one pending object_name row is ambiguous: no object_name is extracted, but the watermark still advances."""
    object_name_result = [
        {MAP_PARAMETER_VALUE: json.dumps(["obj1"]), "time": 10},
        {MAP_PARAMETER_VALUE: json.dumps(["obj2"]), "time": 20},
    ]
    manager._protocol.cloud.get_device_property = MagicMock(side_effect=[[], object_name_result])
    manager._add_cloud_map_data = MagicMock()

    result = manager._request_map_from_cloud()

    assert result is False
    assert manager._latest_object_name_time == 11
    manager._add_cloud_map_data.assert_called_once_with(None, None, None)


# ---------------------------------------------------------------------------
# _request_map
# ---------------------------------------------------------------------------


def test_request_map_sends_i_frame_payload_by_default(manager: DreameMapVacuumMapManager) -> None:
    """With no explicit parameters, _request_map asks for a fresh I frame."""
    manager._protocol.action = MagicMock(return_value={MAP_PARAMETER_CODE: 0, MAP_PARAMETER_OUT: []})

    result = manager._request_map()

    assert result == {MAP_PARAMETER_CODE: 0, MAP_PARAMETER_OUT: []}
    (_siid, _aiid, payload, _timeout), _kwargs = manager._protocol.action.call_args
    sent_value = json.loads(payload[0][MAP_PARAMETER_VALUE])
    assert sent_value == {"frame_type": MapFrameType.I.name}


def test_request_map_returns_none_and_logs_when_protocol_raises(
    manager: DreameMapVacuumMapManager,
) -> None:
    """An exception from the protocol layer is swallowed; the caller gets None instead of a crash."""
    manager._protocol.action = MagicMock(side_effect=RuntimeError("bus error"))

    result = manager._request_map()

    assert result is None


# ---------------------------------------------------------------------------
# _request_i_map
# ---------------------------------------------------------------------------


def _out_entry(prop: DreameVacuumProperty, value: str) -> dict[str, object]:
    return {"piid": PIID(prop), MAP_PARAMETER_VALUE: value}


def test_request_i_map_requests_new_map_when_i_map_not_available(
    manager: DreameMapVacuumMapManager,
) -> None:
    """When an I map cannot be requested directly and this isn't a dreame_cloud device, fall back to request_new_map()."""
    manager._map_data = MagicMock(saved_map_status=1, empty_map=False, restored_map=False, temporary_map=False)
    manager._protocol.dreame_cloud = False
    manager.request_new_map = MagicMock()

    result = manager._request_i_map()

    assert result is False
    manager.request_new_map.assert_called_once()


def test_request_i_map_parses_object_name_and_stores_map(manager: DreameMapVacuumMapManager) -> None:
    """A successful response carrying OBJECT_NAME triggers _add_map_data_file with the robot time."""
    manager._request_map = MagicMock(
        return_value={
            MAP_PARAMETER_CODE: 0,
            MAP_PARAMETER_OUT: [
                _out_entry(DreameVacuumProperty.ROBOT_TIME, "5000"),
                _out_entry(DreameVacuumProperty.OBJECT_NAME, "object/1"),
            ],
        }
    )
    manager._add_map_data_file = MagicMock()

    result = manager._request_i_map()

    assert result is True
    manager._add_map_data_file.assert_called_once_with("object/1", 5000)
    assert manager._last_robot_time == 5000
    # ROBOT_TIME with start_time=None sets bootstrap request bookkeeping.
    assert manager._map_request_count == 1


def test_request_i_map_parses_raw_map_data_when_no_object_name(
    manager: DreameMapVacuumMapManager,
) -> None:
    """MAP_DATA present without OBJECT_NAME falls back to _add_raw_map_data."""
    manager._request_map = MagicMock(
        return_value={
            MAP_PARAMETER_CODE: 0,
            MAP_PARAMETER_OUT: [_out_entry(DreameVacuumProperty.MAP_DATA, "raw_map_payload")],
        }
    )
    manager._add_raw_map_data = MagicMock()

    result = manager._request_i_map()

    assert result is True
    manager._add_raw_map_data.assert_called_once_with("raw_map_payload", None)


def test_request_i_map_old_map_data_object_name_variant(manager: DreameMapVacuumMapManager) -> None:
    """OLD_MAP_DATA with a non-zero prefix carries an object name (and optional 3rd segment)."""
    manager._request_map = MagicMock(
        return_value={
            MAP_PARAMETER_CODE: 0,
            MAP_PARAMETER_OUT: [_out_entry(DreameVacuumProperty.OLD_MAP_DATA, "1,object_name,extra_key")],
        }
    )
    manager._add_map_data_file = MagicMock()

    result = manager._request_i_map()

    assert result is True
    manager._add_map_data_file.assert_called_once_with("object_name,extra_key", None)


def test_request_i_map_old_map_data_raw_variant(manager: DreameMapVacuumMapManager) -> None:
    """OLD_MAP_DATA with a '0' prefix carries raw map bytes directly."""
    manager._request_map = MagicMock(
        return_value={
            MAP_PARAMETER_CODE: 0,
            MAP_PARAMETER_OUT: [_out_entry(DreameVacuumProperty.OLD_MAP_DATA, "0,raw_bytes_here")],
        }
    )
    manager._add_raw_map_data = MagicMock()

    result = manager._request_i_map()

    assert result is True
    manager._add_raw_map_data.assert_called_once_with("raw_bytes_here", None)


def test_request_i_map_returns_false_when_no_map_and_no_object_name(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A code==0 response with neither OBJECT_NAME nor MAP_DATA/OLD_MAP_DATA yields False."""
    manager._request_map = MagicMock(
        return_value={
            MAP_PARAMETER_CODE: 0,
            MAP_PARAMETER_OUT: [_out_entry(DreameVacuumProperty.ROBOT_TIME, "123")],
        }
    )

    result = manager._request_i_map()

    assert result is False


def test_request_i_map_falls_back_to_cloud_poll_on_error_code(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A non-zero response code triggers the cloud polling fallback and returns False."""
    manager._request_map = MagicMock(return_value={MAP_PARAMETER_CODE: -1, MAP_PARAMETER_OUT: []})
    manager._request_map_from_cloud = MagicMock(return_value=True)

    result = manager._request_i_map()

    assert result is False
    manager._request_map_from_cloud.assert_called_once()


def test_request_i_map_sends_start_time_when_provided(manager: DreameMapVacuumMapManager) -> None:
    """A start_time argument is embedded in the request payload."""
    manager._request_map = MagicMock(return_value=None)

    manager._request_i_map(start_time=999)

    sent_params = manager._request_map.call_args.args[0]
    assert sent_params["time"] == 999


# ---------------------------------------------------------------------------
# _request_missing_p_map
# ---------------------------------------------------------------------------


def test_request_missing_p_map_returns_false_without_current_map(
    manager: DreameMapVacuumMapManager,
) -> None:
    """With no current map data at all, there is nothing to fill a gap in."""
    manager._map_data = None

    assert manager._request_missing_p_map() is False


def test_request_missing_p_map_returns_false_when_queue_empty(
    manager: DreameMapVacuumMapManager,
) -> None:
    """An empty partial-map queue means there is no gap to request."""
    manager._map_data = MagicMock()
    manager._latest_map_timestamp_ms = None  # forces _partial_map_queue_size() == 0

    assert manager._request_missing_p_map() is False


def test_request_missing_p_map_is_throttled_within_three_seconds(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A repeat request for the same map_id/frame_id within 3 seconds is suppressed."""
    manager._map_data = MagicMock()
    manager._current_map_id = 7
    manager._current_frame_id = 3
    manager._latest_map_id = 7
    manager._latest_map_timestamp_ms = 1000
    manager._map_data_queue = {7: {4: object()}}
    manager._last_p_request_map_id = 7
    manager._last_p_request_frame_id = 4
    manager._last_p_request_time = time.time()
    manager._request_map = MagicMock()

    result = manager._request_missing_p_map()

    assert result is False
    manager._request_map.assert_not_called()


def test_request_missing_p_map_sends_request_and_updates_throttle_state(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A genuine gap triggers a P-frame request for current_frame_id+1 and records throttle bookkeeping."""
    manager._map_data = MagicMock()
    manager._current_map_id = 7
    manager._current_frame_id = 3
    manager._latest_map_id = 7
    manager._latest_map_timestamp_ms = 1000
    manager._map_data_queue = {7: {5: object()}}
    manager._request_map = MagicMock(return_value={MAP_PARAMETER_CODE: 0, MAP_PARAMETER_OUT: []})

    result = manager._request_missing_p_map()

    assert result is True
    sent_params = manager._request_map.call_args.args[0]
    assert sent_params["map_id"] == 7
    assert sent_params["frame_id"] == 4
    assert sent_params["frame_type"] == MapFrameType.P.name
    assert manager._last_p_request_map_id == 7
    assert manager._last_p_request_frame_id == 4


# ---------------------------------------------------------------------------
# _request_next_p_map: vslam fallback (uncovered branch in existing suite)
# ---------------------------------------------------------------------------


def test_request_next_p_map_requests_new_map_when_vslam_and_no_data_returned(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A vslam device that gets neither raw map nor object name back must request a brand-new map."""
    manager._vslam_map = True
    manager._request_map = MagicMock(return_value={MAP_PARAMETER_CODE: 0, MAP_PARAMETER_OUT: []})
    manager.request_new_map = MagicMock()

    result = manager._request_next_p_map(1, 2)

    assert result is False
    manager.request_new_map.assert_called_once()


def test_request_next_p_map_parses_raw_map_data_and_robot_time(
    manager: DreameMapVacuumMapManager,
) -> None:
    """MAP_DATA + ROBOT_TIME in the response feeds _add_raw_map_data with the parsed timestamp."""
    manager._request_map = MagicMock(
        return_value={
            MAP_PARAMETER_CODE: 0,
            MAP_PARAMETER_OUT: [
                _out_entry(DreameVacuumProperty.ROBOT_TIME, "4200"),
                _out_entry(DreameVacuumProperty.MAP_DATA, "lost_p_map_payload"),
            ],
        }
    )
    manager._add_raw_map_data = MagicMock()

    result = manager._request_next_p_map(1, 2)

    assert result is True
    manager._add_raw_map_data.assert_called_once_with("lost_p_map_payload", 4200)


# ---------------------------------------------------------------------------
# _request_current_map
# ---------------------------------------------------------------------------


def test_request_current_map_uses_i_map_when_available(manager: DreameMapVacuumMapManager) -> None:
    """When an I map can be requested (no restored/temporary/saved map in progress), prefer it."""
    manager._map_data = None  # _request_i_map_available is True when there's no map data yet
    manager._request_i_map = MagicMock(return_value=True)
    manager._request_map_from_cloud = MagicMock()

    result = manager._request_current_map(123)

    assert result is True
    manager._request_i_map.assert_called_once_with(123)
    manager._request_map_from_cloud.assert_not_called()


def test_request_current_map_falls_back_to_cloud_poll_when_i_map_unavailable(
    manager: DreameMapVacuumMapManager,
) -> None:
    """When the device is mid-restore/saved-map cycle, polling the cloud is used instead."""
    manager._map_data = MagicMock(saved_map_status=1, empty_map=False, restored_map=False, temporary_map=False)
    manager._protocol.dreame_cloud = False
    manager._request_i_map = MagicMock()
    manager._request_map_from_cloud = MagicMock(return_value=True)

    result = manager._request_current_map()

    assert result is True
    manager._request_i_map.assert_not_called()
    manager._request_map_from_cloud.assert_called_once()


# ---------------------------------------------------------------------------
# request_new_map
# ---------------------------------------------------------------------------


def test_request_new_map_requests_i_map_when_no_current_map_data(
    manager: DreameMapVacuumMapManager,
) -> None:
    """With no map data at all yet, request_new_map bootstraps via _request_i_map."""
    manager._map_data = None
    manager._request_i_map = MagicMock()

    manager.request_new_map()

    manager._request_i_map.assert_called_once()
    assert manager._new_map_request_time is not None


def test_request_new_map_requests_full_map_and_polls_cloud_on_success(
    manager: DreameMapVacuumMapManager,
) -> None:
    """With existing map data, request a full I-frame map and follow up with a cloud poll (non dreame_cloud)."""
    manager._map_data = MagicMock()
    manager._protocol.dreame_cloud = False
    manager._request_map = MagicMock(return_value={MAP_PARAMETER_CODE: 0, MAP_PARAMETER_OUT: []})
    manager._request_map_from_cloud = MagicMock()

    manager.request_new_map()

    manager._request_map_from_cloud.assert_called_once()


def test_request_new_map_is_throttled_within_ten_seconds_for_non_cloud_devices(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A repeat call within 10s (and <=3s since the last) is suppressed entirely for non dreame_cloud devices."""
    manager._protocol.dreame_cloud = False
    manager._new_map_request_time = time.time()
    manager._request_i_map = MagicMock()
    manager._request_map = MagicMock()

    manager.request_new_map()

    manager._request_i_map.assert_not_called()
    manager._request_map.assert_not_called()


def test_request_new_map_throttle_window_still_polls_cloud_between_3_and_10_seconds(
    manager: DreameMapVacuumMapManager,
) -> None:
    """Between 3s and 10s since the last request, a lightweight cloud poll is retried instead of a full request."""
    manager._protocol.dreame_cloud = False
    manager._new_map_request_time = time.time() - 5
    manager._request_map_from_cloud = MagicMock()
    manager._request_i_map = MagicMock()
    manager._request_map = MagicMock()

    manager.request_new_map()

    manager._request_map_from_cloud.assert_called_once()
    manager._request_i_map.assert_not_called()
    manager._request_map.assert_not_called()


# ---------------------------------------------------------------------------
# request_next_map / request_next_map_list / request_next_recovery_map_list
# ---------------------------------------------------------------------------


def test_request_next_map_sets_request_flags_and_schedules_update(
    manager: DreameMapVacuumMapManager,
) -> None:
    """request_next_map resets the retry counter, flags a pending request, and schedules an update soon."""
    manager._map_request_count = 4
    manager.schedule_update = MagicMock()

    manager.request_next_map()

    assert manager._map_request_count == 0
    assert manager._need_map_request is True
    assert manager._need_new_map is False
    manager.schedule_update.assert_called_once_with(2)


def test_request_next_map_with_request_new_also_flags_need_new_map(
    manager: DreameMapVacuumMapManager,
) -> None:
    """request_next_map(request_new=True) additionally flags that a brand new map is wanted."""
    manager.schedule_update = MagicMock()

    manager.request_next_map(request_new=True)

    assert manager._need_new_map is True


def test_request_next_map_list_sets_flag(manager: DreameMapVacuumMapManager) -> None:
    manager.request_next_map_list()
    assert manager._need_map_list_request is True


def test_request_next_recovery_map_list_sets_flag(manager: DreameMapVacuumMapManager) -> None:
    manager.request_next_recovery_map_list()
    assert manager._need_recovery_map_list_request is True


# ---------------------------------------------------------------------------
# set_map_list_object_name / set_recovery_map_list_object_name
# ---------------------------------------------------------------------------


def test_set_map_list_object_name_stores_new_value_and_returns_true(
    manager: DreameMapVacuumMapManager,
) -> None:
    result = manager.set_map_list_object_name("list_obj", "md5_1")

    assert result is True
    assert manager._map_list_object_name == "list_obj"
    assert manager._map_list_md5 == "md5_1"


def test_set_map_list_object_name_ignores_empty_string(manager: DreameMapVacuumMapManager) -> None:
    result = manager.set_map_list_object_name("")

    assert result is False
    assert manager._map_list_object_name is None


def test_set_map_list_object_name_unchanged_value_returns_false(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._map_list_object_name = "list_obj"
    manager._map_list_md5 = "md5_1"

    result = manager.set_map_list_object_name("list_obj", "md5_1")

    assert result is False


def test_set_map_list_object_name_requests_refresh_when_device_idle_and_md5_known(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A changed object name while idle (and a previously known md5) triggers an immediate list refresh."""
    manager._device_running = False
    manager._map_list_md5 = "old_md5"
    manager.request_next_map_list = MagicMock()
    manager.schedule_update = MagicMock()

    manager.set_map_list_object_name("new_obj", "new_md5")

    manager.request_next_map_list.assert_called_once()
    manager.schedule_update.assert_called_once_with(3)


def test_set_map_list_object_name_skips_refresh_on_first_ever_value(
    manager: DreameMapVacuumMapManager,
) -> None:
    """The very first md5 (still None) must not trigger a refresh — nothing to compare against yet."""
    manager._device_running = False
    manager.request_next_map_list = MagicMock()

    result = manager.set_map_list_object_name("first_obj", "first_md5")

    assert result is True
    manager.request_next_map_list.assert_not_called()


def test_set_recovery_map_list_object_name_stores_and_flags_request(
    manager: DreameMapVacuumMapManager,
) -> None:
    result = manager.set_recovery_map_list_object_name("recovery_obj")

    assert result is True
    assert manager._recovery_map_list_object_name == "recovery_obj"
    assert manager._need_recovery_map_list_request is True


def test_set_recovery_map_list_object_name_unchanged_returns_false(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._recovery_map_list_object_name = "recovery_obj"
    manager._need_recovery_map_list_request = False

    result = manager.set_recovery_map_list_object_name("recovery_obj")

    assert result is False
    assert manager._need_recovery_map_list_request is False
