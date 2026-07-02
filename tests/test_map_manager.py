"""Characterization tests for DreameMapVacuumMapManager.

These tests target the map lifecycle / cloud sync queue management module
(map_manager.py), focusing on recent robustness fixes:
- _request_queue keys must be released on failure so a request can be retried
- _file_urls cache must purge expired entries instead of growing unbounded
- a single corrupted saved map must not abort the rest of request_map_list()
- disconnect() must release the optimizer's V8 context and the editor timers

The protocol layer is fully mocked (MagicMock); no network I/O occurs.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame.const import (
    MAP_PARAMETER_CODE,
    MAP_PARAMETER_EXPIRES_TIME,
    MAP_PARAMETER_OUT,
    MAP_PARAMETER_URL,
    MAP_PARAMETER_VALUE,
)
from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
from custom_components.dreame_vacuum.dreame.map_manager import DreameMapVacuumMapManager
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    PIID,
    DreameVacuumProperty,
    MapData,
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
# _request_next_p_map: _request_queue key release (recent fix)
# ---------------------------------------------------------------------------


def test_request_next_p_map_releases_key_on_none_result_and_allows_retry(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A None result from _request_map must not leave the key stuck in the queue."""
    manager._request_map = MagicMock(return_value=None)

    first = manager._request_next_p_map(5, 1)

    assert first is False
    assert "5:1" not in manager._request_queue
    assert manager._request_map.call_count == 1

    # A subsequent call with the same map_id/frame_id must actually retry,
    # proving the key was released rather than left stuck as True.
    second = manager._request_next_p_map(5, 1)

    assert second is False
    assert "5:1" not in manager._request_queue
    assert manager._request_map.call_count == 2


def test_request_next_p_map_releases_key_on_error_code_and_allows_retry(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A non-zero response code must also release the key for a future retry."""
    manager._request_map = MagicMock(return_value={MAP_PARAMETER_CODE: -1, MAP_PARAMETER_OUT: []})

    first = manager._request_next_p_map(9, 4)

    assert first is False
    assert "9:4" not in manager._request_queue

    second = manager._request_next_p_map(9, 4)

    assert second is False
    assert "9:4" not in manager._request_queue
    assert manager._request_map.call_count == 2


def test_request_next_p_map_releases_key_on_success(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A successful response must also release the key (not just the failure path)."""
    manager._add_map_data_file = MagicMock()
    manager._request_map = MagicMock(
        return_value={
            MAP_PARAMETER_CODE: 0,
            MAP_PARAMETER_OUT: [
                {
                    "piid": PIID(DreameVacuumProperty.OBJECT_NAME),
                    MAP_PARAMETER_VALUE: "object/name/0",
                },
            ],
        }
    )

    result = manager._request_next_p_map(3, 2)

    assert result is True
    assert "3:2" not in manager._request_queue
    manager._add_map_data_file.assert_called_once_with("object/name/0", None)


def test_request_next_p_map_already_queued_returns_false_without_calling_request(
    manager: DreameMapVacuumMapManager,
) -> None:
    """If the key is already reserved in _request_queue, bail out early."""
    manager._request_map = MagicMock()
    manager._request_queue["5:1"] = True

    result = manager._request_next_p_map(5, 1)

    assert result is False
    manager._request_map.assert_not_called()
    # The pre-existing reservation must be left untouched by the early return.
    assert manager._request_queue["5:1"] is True


# ---------------------------------------------------------------------------
# _get_file_url: expired cache entry purge (recent fix)
# ---------------------------------------------------------------------------


def test_get_file_url_purges_expired_entries_when_requesting_new_url(
    manager: DreameMapVacuumMapManager,
) -> None:
    """Requesting a new URL purges unrelated expired entries from the cache."""
    now = int(round(time.time()))
    manager._file_urls = {
        "expired_obj": {MAP_PARAMETER_URL: "http://old", MAP_PARAMETER_EXPIRES_TIME: now - 10},
        "still_valid_obj": {MAP_PARAMETER_URL: "http://valid", MAP_PARAMETER_EXPIRES_TIME: now + 1000},
    }
    manager._protocol.cloud.get_interim_file_url = MagicMock(return_value="http://new")

    url = manager._get_file_url("new_obj")

    assert url == "http://new"
    manager._protocol.cloud.get_interim_file_url.assert_called_once_with("new_obj")
    assert "expired_obj" not in manager._file_urls
    assert "still_valid_obj" in manager._file_urls
    assert "new_obj" in manager._file_urls


def test_get_file_url_reuses_non_expired_url_without_cloud_call(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A cached URL with more than 60s left before expiry is reused as-is."""
    now = int(round(time.time()))
    manager._file_urls = {
        "obj": {MAP_PARAMETER_URL: "http://cached", MAP_PARAMETER_EXPIRES_TIME: now + 1000},
    }
    manager._protocol.cloud.get_interim_file_url = MagicMock()

    url = manager._get_file_url("obj")

    assert url == f"http://cached&current={now!s}"
    manager._protocol.cloud.get_interim_file_url.assert_not_called()
    # Cache entry must be left untouched (still present, unexpired).
    assert manager._file_urls["obj"][MAP_PARAMETER_EXPIRES_TIME] == now + 1000


def test_get_file_url_expired_own_entry_is_refreshed(
    manager: DreameMapVacuumMapManager,
) -> None:
    """If the entry for the requested object itself is expired, it is refreshed via the cloud."""
    now = int(round(time.time()))
    manager._file_urls = {
        "obj": {MAP_PARAMETER_URL: "http://stale", MAP_PARAMETER_EXPIRES_TIME: now + 10},
    }
    manager._protocol.cloud.get_interim_file_url = MagicMock(return_value="http://fresh")

    url = manager._get_file_url("obj")

    assert url == "http://fresh"
    manager._protocol.cloud.get_interim_file_url.assert_called_once_with("obj")
    assert manager._file_urls["obj"][MAP_PARAMETER_URL] == "http://fresh"


# ---------------------------------------------------------------------------
# request_map_list: a corrupted saved map must not abort the rest (recent fix)
# ---------------------------------------------------------------------------


def test_request_map_list_skips_corrupted_map_and_keeps_processing_next(
    manager: DreameMapVacuumMapManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """decode_saved_map raising on one entry must not stop later valid entries from being added."""
    manager._map_list_object_name = "list_object_name"
    manager._protocol.cloud.logged_in = True

    payload = {
        "mapstr": [
            {"map": "corrupted_raw_map", "mapobj": "obj1"},
            {"map": "valid_raw_map", "mapobj": "obj2", "name": "Kitchen"},
        ],
        "curr_id": 2,
    }
    manager._get_interim_file_data = MagicMock(return_value=json.dumps(payload).encode())

    good_map = MapData()
    good_map.map_id = 2
    good_map.wifi_map_data = None

    decode_mock = MagicMock(side_effect=[Exception("corrupted map data"), good_map])
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_saved_map", decode_mock)

    manager.request_map_list()

    # decode_saved_map was attempted for BOTH entries, proving the corrupted
    # one did not short-circuit the loop.
    assert decode_mock.call_count == 2
    # Only the valid map made it into _saved_map_data.
    assert list(manager._saved_map_data.keys()) == [2]
    assert manager._saved_map_data[2].map_name == "Kitchen"


def test_request_map_list_skips_object_fetch_error_and_keeps_processing_next(
    manager: DreameMapVacuumMapManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure while fetching a rismobj-referenced map must not stop later valid entries."""
    manager._map_list_object_name = "list_object_name"
    manager._protocol.cloud.logged_in = True

    payload = {
        "server": 1,
        "mapstr": [
            {"rismobj": "broken_obj"},
            {"map": "valid_raw_map", "mapobj": "obj2", "name": "Living Room"},
        ],
        "curr_id": 3,
    }

    def fake_get_interim_file_data(object_name: str = "", timestamp: object = None) -> object:
        if object_name == "list_object_name":
            return json.dumps(payload).encode()
        raise RuntimeError("object fetch failed")

    manager._get_interim_file_data = MagicMock(side_effect=fake_get_interim_file_data)

    good_map = MapData()
    good_map.map_id = 3
    good_map.wifi_map_data = None
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_saved_map", MagicMock(return_value=good_map))

    manager.request_map_list()

    assert list(manager._saved_map_data.keys()) == [3]
    assert manager._saved_map_data[3].map_name == "Living Room"


# ---------------------------------------------------------------------------
# disconnect(): optimizer.close() / editor.cancel_pending() / timer cleanup
# ---------------------------------------------------------------------------


def test_disconnect_closes_optimizer_and_cancels_editor_and_timer(
    manager: DreameMapVacuumMapManager,
) -> None:
    """disconnect() must release the optimizer's V8 context and editor timers."""
    manager.optimizer.close = MagicMock()
    manager.editor.cancel_pending = MagicMock()
    timer_mock = MagicMock()
    manager._update_timer = timer_mock

    manager.disconnect()

    manager.optimizer.close.assert_called_once()
    manager.editor.cancel_pending.assert_called_once()
    timer_mock.cancel.assert_called_once()
    assert manager._update_timer is None
    assert manager._disconnected is True
    assert manager._update_callback is None
    assert manager._change_callback is None
    assert manager._error_callback is None


def test_disconnect_is_safe_when_editor_and_optimizer_are_none(
    manager: DreameMapVacuumMapManager,
) -> None:
    """disconnect() guards against editor/optimizer being None (defensive branch)."""
    manager.editor = None
    manager.optimizer = None

    manager.disconnect()

    assert manager._disconnected is True
