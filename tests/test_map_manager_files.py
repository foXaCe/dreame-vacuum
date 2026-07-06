"""Characterization tests for file/object fetching helpers of DreameMapVacuumMapManager.

Covers:
- _get_object_file_data / _get_interim_file_data (object-name resolution + cloud fetch)
- _decode_map_partial (timestamp normalization + latest map/frame watermarking)
- _add_map_data_file / _add_raw_map_data (thin wrappers around the above)
- _add_cloud_map_data (cloud-polling orchestration: apply/queue/escalate)
- get_obstacle_image (AES-ECB decrypt of an obstacle snapshot)
- get_history_map / get_recovery_map / get_recovery_map_file

The protocol/cloud layer is fully mocked (MagicMock); no network I/O occurs.
Sibling manager methods (e.g. _add_map_data, _queue_partial_map) are monkeypatched
where a test's target method merely orchestrates them, matching this repo's existing
"isolate the unit under test" convention (see test_map_manager.py).
"""

from __future__ import annotations

import datetime
import hashlib
import json
from unittest.mock import MagicMock

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import pytest

from custom_components.dreame_vacuum.dreame.const import (
    MAP_PARAMETER_EXPIRES_TIME,
    MAP_PARAMETER_URL,
)
from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
from custom_components.dreame_vacuum.dreame.map_manager import DreameMapVacuumMapManager
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    MapData,
    MapDataPartial,
    MapFrameType,
    ObstaclePictureStatus,
)


@pytest.fixture
def protocol() -> MagicMock:
    proto = MagicMock()
    proto.dreame_cloud = False
    proto.cloud = MagicMock()
    proto.cloud.dreame_cloud = False
    proto.cloud.logged_in = True
    proto.cloud.connected = True
    proto.cloud.object_name = "fallback/object/name"
    return proto


@pytest.fixture
def manager(protocol: MagicMock) -> DreameMapVacuumMapManager:
    return DreameMapVacuumMapManager(protocol)


def _partial(map_id: int = 1, frame_id: int = 0, frame_type: int = MapFrameType.P.value) -> MapDataPartial:
    p = MapDataPartial()
    p.map_id = map_id
    p.frame_id = frame_id
    p.frame_type = frame_type
    return p


# ---------------------------------------------------------------------------
# _get_object_file_data
# ---------------------------------------------------------------------------


def test_get_object_file_data_without_comma_has_no_key(manager: DreameMapVacuumMapManager) -> None:
    manager._get_interim_file_data = MagicMock(return_value=b"payload")

    response, key = manager._get_object_file_data("plain_object_name", 123)

    assert response == b"payload"
    assert key is None
    manager._get_interim_file_data.assert_called_once_with("plain_object_name", 123)


def test_get_object_file_data_splits_key_from_comma(manager: DreameMapVacuumMapManager) -> None:
    manager._get_interim_file_data = MagicMock(return_value=b"payload")

    response, key = manager._get_object_file_data("object_name,secret_key", 123)

    assert response == b"payload"
    assert key == "secret_key"
    manager._get_interim_file_data.assert_called_once_with("object_name", 123)


# ---------------------------------------------------------------------------
# _get_interim_file_data
# ---------------------------------------------------------------------------


def test_get_interim_file_data_returns_none_when_not_logged_in(manager: DreameMapVacuumMapManager) -> None:
    manager._protocol.cloud.logged_in = False

    assert manager._get_interim_file_data("obj") is None
    manager._protocol.cloud.get_file.assert_not_called()


def test_get_interim_file_data_fetches_directly_with_explicit_object_name(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._get_file_url = MagicMock(return_value="http://file")
    manager._protocol.cloud.get_file = MagicMock(return_value=b"raw_bytes")

    result = manager._get_interim_file_data("explicit_obj")

    assert result == b"raw_bytes"
    manager._get_file_url.assert_called_once_with("explicit_obj")
    manager._protocol.cloud.get_device_property.assert_not_called()


def test_get_interim_file_data_resolves_object_name_from_dreame_cloud_properties(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._protocol.cloud.dreame_cloud = True
    manager._protocol.cloud.get_properties = MagicMock(return_value=[{"value": ["resolved_obj"]}])
    manager._get_file_url = MagicMock(return_value="http://file")
    manager._protocol.cloud.get_file = MagicMock(return_value=b"raw_bytes")

    result = manager._get_interim_file_data("")

    assert result == b"raw_bytes"
    manager._get_file_url.assert_called_once_with("resolved_obj")


def test_get_interim_file_data_resolves_object_name_from_device_property_json(
    manager: DreameMapVacuumMapManager,
) -> None:

    manager._protocol.cloud.dreame_cloud = False
    manager._protocol.cloud.get_device_property = MagicMock(return_value=[{"value": json.dumps(["json_obj"])}])
    manager._get_file_url = MagicMock(return_value="http://file")
    manager._protocol.cloud.get_file = MagicMock(return_value=b"raw_bytes")

    result = manager._get_interim_file_data("")

    assert result == b"raw_bytes"
    manager._get_file_url.assert_called_once_with("json_obj")


def test_get_interim_file_data_falls_back_to_cloud_object_name_when_still_empty(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._protocol.cloud.dreame_cloud = False
    manager._protocol.cloud.get_device_property = MagicMock(return_value=None)
    manager._get_file_url = MagicMock(return_value="http://file")
    manager._protocol.cloud.get_file = MagicMock(return_value=b"raw_bytes")

    manager._get_interim_file_data("")

    manager._get_file_url.assert_called_once_with("fallback/object/name")


def test_get_interim_file_data_returns_none_when_no_url_available(manager: DreameMapVacuumMapManager) -> None:
    manager._get_file_url = MagicMock(return_value=None)

    result = manager._get_interim_file_data("obj")

    assert result is None
    manager._protocol.cloud.get_file.assert_not_called()


def test_get_interim_file_data_purges_cache_entry_when_cloud_fetch_fails(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A failed cloud.get_file() must not leave a now-unusable URL sitting in the cache."""
    manager._get_file_url = MagicMock(return_value="http://stale")
    manager._protocol.cloud.get_file = MagicMock(return_value=None)
    manager._file_urls = {"obj": {MAP_PARAMETER_URL: "http://stale", MAP_PARAMETER_EXPIRES_TIME: 99999999999}}

    result = manager._get_interim_file_data("obj")

    assert result is None
    assert "obj" not in manager._file_urls


# ---------------------------------------------------------------------------
# _decode_map_partial
# ---------------------------------------------------------------------------


def test_decode_map_partial_returns_none_when_decoder_fails(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_partial", MagicMock(return_value=None))

    result = manager._decode_map_partial("raw", timestamp=1000)

    assert result is None
    assert manager._latest_map_timestamp_ms is None


def test_decode_map_partial_overrides_missing_timestamp_with_given_one(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    partial = MapDataPartial()
    partial.map_id = 5
    partial.timestamp_ms = None
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_partial", MagicMock(return_value=partial))

    result = manager._decode_map_partial("raw", timestamp=987654321000)

    assert result is partial
    assert result.timestamp_ms == 987654321000
    assert manager._latest_map_timestamp_ms == 987654321000
    assert manager._latest_map_id == 5


def test_decode_map_partial_overrides_uptime_like_timestamp_below_epoch_threshold(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A post-reboot device sometimes reports uptime (a small number) instead of a real epoch ms timestamp."""
    partial = MapDataPartial()
    partial.map_id = 5
    partial.timestamp_ms = 42  # clearly not a real 2020+ epoch-ms timestamp
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_partial", MagicMock(return_value=partial))

    manager._decode_map_partial("raw", timestamp=1700000000000)

    assert partial.timestamp_ms == 1700000000000


def test_decode_map_partial_keeps_valid_timestamp_untouched(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    partial = MapDataPartial()
    partial.map_id = 5
    partial.timestamp_ms = 1700000000000  # already a plausible real timestamp
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_partial", MagicMock(return_value=partial))

    manager._decode_map_partial("raw", timestamp=999999999999999)

    assert partial.timestamp_ms == 1700000000000


def test_decode_map_partial_does_not_regress_the_latest_watermark(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager._latest_map_timestamp_ms = 5000
    manager._latest_map_id = 99
    partial = MapDataPartial()
    partial.map_id = 1
    partial.timestamp_ms = 4000  # older than the current watermark
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_partial", MagicMock(return_value=partial))

    manager._decode_map_partial("raw")

    assert manager._latest_map_timestamp_ms == 5000
    assert manager._latest_map_id == 99


# ---------------------------------------------------------------------------
# _add_map_data_file / _add_raw_map_data
# ---------------------------------------------------------------------------


def test_add_map_data_file_decodes_and_forwards_when_response_present(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._get_object_file_data = MagicMock(return_value=(b"encoded_bytes", "key1"))
    manager._add_raw_map_data = MagicMock()

    manager._add_map_data_file("obj_name", 555)

    manager._get_object_file_data.assert_called_once_with("obj_name", 555)
    manager._add_raw_map_data.assert_called_once_with("encoded_bytes", 555, "key1")


def test_add_map_data_file_noop_when_no_response(manager: DreameMapVacuumMapManager) -> None:
    manager._get_object_file_data = MagicMock(return_value=(None, None))
    manager._add_raw_map_data = MagicMock()

    manager._add_map_data_file("obj_name", 555)

    manager._add_raw_map_data.assert_not_called()


def test_add_raw_map_data_decodes_then_dispatches_to_add_map_data(
    manager: DreameMapVacuumMapManager,
) -> None:
    sentinel_partial = object()
    manager._decode_map_partial = MagicMock(return_value=sentinel_partial)
    manager._add_map_data = MagicMock(return_value=True)

    result = manager._add_raw_map_data("raw_map", 100, "key")

    assert result is True
    manager._decode_map_partial.assert_called_once_with("raw_map", 100, "key")
    manager._add_map_data.assert_called_once_with(sentinel_partial)


# ---------------------------------------------------------------------------
# _add_cloud_map_data
# ---------------------------------------------------------------------------


def test_add_cloud_map_data_dispatches_i_frames_directly_and_queues_others(
    manager: DreameMapVacuumMapManager,
) -> None:
    """Each row from a cloud map_data poll is applied immediately if it's an I frame, queued otherwise."""
    manager._latest_map_id = 1
    manager._current_frame_id = 3
    i_frame = _partial(map_id=1, frame_id=0, frame_type=MapFrameType.I.value)
    p_frame = _partial(map_id=1, frame_id=4, frame_type=MapFrameType.P.value)

    manager._add_map_data = MagicMock(return_value=True)
    manager._queue_partial_map = MagicMock()
    manager._unqueue_partial_map = MagicMock(return_value=None)

    manager._add_cloud_map_data([i_frame, p_frame], None, None)

    manager._add_map_data.assert_any_call(i_frame)
    manager._queue_partial_map.assert_called_once_with(p_frame)
    # Follow-up unqueue-and-apply attempt for the next expected frame (current_frame_id+1).
    manager._unqueue_partial_map.assert_called_once_with(1, 4)


@pytest.mark.parametrize(
    ("dreame_cloud", "expected_method"),
    [(True, "_request_map"), (False, "request_new_map")],
)
def test_add_cloud_map_data_escalates_to_full_request_on_large_backlog(
    manager: DreameMapVacuumMapManager, dreame_cloud: bool, expected_method: str
) -> None:
    """A >8 frame backlog with nothing applied and no object_name gives up and asks for a full map."""
    manager._protocol.dreame_cloud = dreame_cloud
    manager._add_map_data = MagicMock(return_value=False)
    manager._unqueue_partial_map = MagicMock(return_value=None)
    manager._delete_invalid_partial_maps = MagicMock()
    manager._partial_map_queue_size = MagicMock(return_value=9)
    setattr(manager, expected_method, MagicMock())

    manager._add_cloud_map_data(None, None, None)

    getattr(manager, expected_method).assert_called_once()


def test_add_cloud_map_data_medium_backlog_requests_missing_p_map(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._add_map_data = MagicMock(return_value=False)
    manager._unqueue_partial_map = MagicMock(return_value=None)
    manager._delete_invalid_partial_maps = MagicMock()
    manager._partial_map_queue_size = MagicMock(return_value=5)
    manager._request_missing_p_map = MagicMock()

    manager._add_cloud_map_data(None, None, None)

    manager._request_missing_p_map.assert_called_once()


def test_add_cloud_map_data_small_backlog_with_new_rows_requests_next_p_map(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A small backlog only triggers a gap-fill request when this call actually brought new partial_map_data."""
    manager._latest_map_id = 7
    manager._current_frame_id = 2
    manager._add_map_data = MagicMock(return_value=False)
    manager._unqueue_partial_map = MagicMock(return_value=None)
    manager._delete_invalid_partial_maps = MagicMock()
    manager._partial_map_queue_size = MagicMock(return_value=1)
    manager._request_next_p_map = MagicMock()

    manager._add_cloud_map_data([_partial()], None, None)

    manager._request_next_p_map.assert_called_once_with(7, 3)


def test_add_cloud_map_data_small_backlog_without_new_rows_does_not_request(
    manager: DreameMapVacuumMapManager,
) -> None:
    """With no partial_map_data at all this call, a lingering backlog does not trigger a fresh request."""
    manager._add_map_data = MagicMock(return_value=False)
    manager._unqueue_partial_map = MagicMock(return_value=None)
    manager._delete_invalid_partial_maps = MagicMock()
    manager._partial_map_queue_size = MagicMock(return_value=1)
    manager._request_next_p_map = MagicMock()

    manager._add_cloud_map_data(None, None, None)

    manager._request_next_p_map.assert_not_called()


def test_add_cloud_map_data_skips_escalation_when_something_was_applied(
    manager: DreameMapVacuumMapManager,
) -> None:
    """If the unqueue-and-apply follow-up succeeded, none of the backlog-escalation branches run."""
    manager._add_map_data = MagicMock(return_value=True)
    manager._unqueue_partial_map = MagicMock(return_value=object())
    manager._partial_map_queue_size = MagicMock()
    manager._request_missing_p_map = MagicMock()

    manager._add_cloud_map_data(None, None, None)

    manager._partial_map_queue_size.assert_not_called()
    manager._request_missing_p_map.assert_not_called()


def test_add_cloud_map_data_object_name_applied_directly_for_i_frame_and_propagates_result(
    manager: DreameMapVacuumMapManager,
) -> None:
    """An object-name-driven I frame (or when there's no current map yet) is applied directly, and its
    result becomes _add_cloud_map_data's own return value (unlike every other code path, which returns None).
    """
    manager._add_map_data = MagicMock(return_value=False)  # the earlier unqueue-follow-up: nothing applied
    manager._unqueue_partial_map = MagicMock(return_value=None)
    manager._delete_invalid_partial_maps = MagicMock()
    manager._partial_map_queue_size = MagicMock(return_value=0)
    manager._get_object_file_data = MagicMock(return_value=(MagicMock(decode=lambda: "raw"), "key1"))
    decoded_partial = _partial(frame_type=MapFrameType.I.value)
    manager._decode_map_partial = MagicMock(return_value=decoded_partial)
    # Second call to _add_map_data (for the object-name-driven I frame) returns a distinct sentinel.
    manager._add_map_data.side_effect = [False, "APPLIED_SENTINEL"]

    result = manager._add_cloud_map_data(None, "object_name", 12345)

    assert result == "APPLIED_SENTINEL"
    assert manager._need_new_map is False
    manager._add_map_data.assert_called_with(decoded_partial)


def test_add_cloud_map_data_object_name_p_frame_queued_and_drained_when_next_available(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A P frame from an object_name fetch (with an existing current map) is queued, then immediately drained
    if it happens to be the very next expected frame."""
    manager._map_data = MagicMock()  # a current map already exists
    manager._add_map_data = MagicMock(return_value=False)
    manager._unqueue_partial_map = MagicMock(return_value=None)
    manager._delete_invalid_partial_maps = MagicMock()
    manager._partial_map_queue_size = MagicMock(return_value=0)
    manager._get_object_file_data = MagicMock(return_value=(MagicMock(decode=lambda: "raw"), None))
    decoded_partial = _partial(frame_type=MapFrameType.P.value)
    manager._decode_map_partial = MagicMock(return_value=decoded_partial)
    manager._queue_partial_map = MagicMock()
    manager._unqueue_next_partial_map = MagicMock(return_value=decoded_partial)

    manager._add_cloud_map_data(None, "object_name", 12345)

    manager._queue_partial_map.assert_called_once_with(decoded_partial)
    manager._unqueue_next_partial_map.assert_called_once()
    manager._add_map_data.assert_called_with(decoded_partial)


def test_add_cloud_map_data_object_name_p_frame_queued_and_stuck_escalates_on_deep_backlog(
    manager: DreameMapVacuumMapManager,
) -> None:
    """When the just-queued P frame isn't drainable and the backlog is deep, request a full map."""
    manager._protocol.dreame_cloud = False
    manager._map_data = MagicMock()
    manager._add_map_data = MagicMock(return_value=False)
    manager._unqueue_partial_map = MagicMock(return_value=None)
    manager._delete_invalid_partial_maps = MagicMock()
    manager._get_object_file_data = MagicMock(return_value=(MagicMock(decode=lambda: "raw"), None))
    decoded_partial = _partial(frame_type=MapFrameType.P.value)
    manager._decode_map_partial = MagicMock(return_value=decoded_partial)
    manager._queue_partial_map = MagicMock()
    manager._unqueue_next_partial_map = MagicMock(return_value=None)
    # object_name is not None, so the top-level escalation check is skipped entirely;
    # this is the only _partial_map_queue_size() call made (the post-queue-drain check).
    manager._partial_map_queue_size = MagicMock(return_value=9)
    manager.request_new_map = MagicMock()

    manager._add_cloud_map_data(None, "object_name", 12345)

    manager.request_new_map.assert_called_once()


def test_add_cloud_map_data_object_name_p_frame_queued_and_stuck_uses_request_map_for_dreame_cloud(
    manager: DreameMapVacuumMapManager,
) -> None:
    """The dreame_cloud variant of the deep-backlog escalation uses _request_map(), not request_new_map()."""
    manager._protocol.dreame_cloud = True
    manager._map_data = MagicMock()
    manager._add_map_data = MagicMock(return_value=False)
    manager._unqueue_partial_map = MagicMock(return_value=None)
    manager._delete_invalid_partial_maps = MagicMock()
    manager._get_object_file_data = MagicMock(return_value=(MagicMock(decode=lambda: "raw"), None))
    decoded_partial = _partial(frame_type=MapFrameType.P.value)
    manager._decode_map_partial = MagicMock(return_value=decoded_partial)
    manager._queue_partial_map = MagicMock()
    manager._unqueue_next_partial_map = MagicMock(return_value=None)
    manager._partial_map_queue_size = MagicMock(return_value=9)
    manager._request_map = MagicMock()
    manager.request_new_map = MagicMock()

    manager._add_cloud_map_data(None, "object_name", 12345)

    manager._request_map.assert_called_once()
    manager.request_new_map.assert_not_called()


# ---------------------------------------------------------------------------
# get_obstacle_image
# ---------------------------------------------------------------------------


def _encrypted_obstacle_payload(plaintext: bytes, key_str: str) -> bytes:
    """Build ciphertext the way the real device would (AES-128-ECB with an md5-derived key)."""
    aes_key = bytearray.fromhex(hashlib.md5(key_str.encode("utf-8")).hexdigest())
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(bytes(aes_key)), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def test_get_obstacle_image_missing_obstacle_returns_none_tuple(manager: DreameMapVacuumMapManager) -> None:
    map_data = MapData()
    map_data.obstacles = {}

    result = manager.get_obstacle_image(map_data, "3")

    assert result == (None, None)


def test_get_obstacle_image_short_file_name_is_rejected(manager: DreameMapVacuumMapManager) -> None:
    map_data = MapData()
    map_data.obstacles = {"3": MagicMock(file_name="x", key="longkey", picture_status=None)}

    assert manager.get_obstacle_image(map_data, "3") == (None, None)


def test_get_obstacle_image_wrong_picture_status_is_rejected(manager: DreameMapVacuumMapManager) -> None:
    obstacle = MagicMock(file_name="obstacle_file", key="longkey", picture_status=MagicMock(value=1))
    map_data = MapData()
    map_data.obstacles = {"3": obstacle}

    assert manager.get_obstacle_image(map_data, "3") == (None, None)


def test_get_obstacle_image_decrypts_successfully(manager: DreameMapVacuumMapManager) -> None:
    """Full AES-128-ECB round trip: decrypted+unpadded bytes must equal the original plaintext."""
    plaintext = b"hello obstacle image payload!"
    key_str = "obstacle-secret-key"
    ciphertext = _encrypted_obstacle_payload(plaintext, key_str)

    obstacle = MagicMock(
        file_name="obstacle_file",
        object_id=None,
        key=key_str,
        picture_status=ObstaclePictureStatus.UPLOADED,
    )
    map_data = MapData()
    map_data.obstacles = {"3": obstacle}
    manager._get_file_url = MagicMock(return_value="http://obstacle-url")
    manager._protocol.cloud.get_file = MagicMock(return_value=ciphertext)
    manager._protocol.dreame_cloud = False

    image_bytes, returned_obstacle = manager.get_obstacle_image(map_data, 3)

    assert image_bytes == plaintext
    assert returned_obstacle is obstacle
    manager._get_file_url.assert_called_once_with("obstacle_file", False)


def test_get_obstacle_image_uses_composite_object_name_for_dreame_cloud(
    manager: DreameMapVacuumMapManager,
) -> None:
    plaintext = b"payload"
    key_str = "key123"
    ciphertext = _encrypted_obstacle_payload(plaintext, key_str)
    obstacle = MagicMock(file_name="obstacle_file", object_id="42", key=key_str, picture_status=None)
    map_data = MapData()
    map_data.obstacles = {"3": obstacle}
    manager._get_file_url = MagicMock(return_value="http://obstacle-url")
    manager._protocol.cloud.get_file = MagicMock(return_value=ciphertext)
    manager._protocol.dreame_cloud = True

    manager.get_obstacle_image(map_data, "3")

    manager._get_file_url.assert_called_once_with("obstacle_file-42", False)


def test_get_obstacle_image_swallows_exceptions_and_returns_none_tuple(
    manager: DreameMapVacuumMapManager,
) -> None:
    obstacle = MagicMock(file_name="obstacle_file", key="key", picture_status=None)
    map_data = MapData()
    map_data.obstacles = {"3": obstacle}
    manager._get_file_url = MagicMock(side_effect=RuntimeError("network exploded"))

    result = manager.get_obstacle_image(map_data, "3")

    assert result == (None, None)


# ---------------------------------------------------------------------------
# get_history_map
# ---------------------------------------------------------------------------


def test_get_history_map_returns_none_for_empty_object_name(manager: DreameMapVacuumMapManager) -> None:
    manager._get_file_url = MagicMock()

    assert manager.get_history_map("") is None
    manager._get_file_url.assert_not_called()


def test_get_history_map_returns_none_when_no_file_url(manager: DreameMapVacuumMapManager) -> None:
    manager._get_file_url = MagicMock(return_value=None)

    assert manager.get_history_map("obj") is None
    manager._protocol.cloud.get_file.assert_not_called()


def test_get_history_map_returns_none_when_cloud_get_file_fails(manager: DreameMapVacuumMapManager) -> None:
    manager._get_file_url = MagicMock(return_value="http://map")
    manager._protocol.cloud.get_file = MagicMock(return_value=None)

    assert manager.get_history_map("obj") is None


def test_get_history_map_returns_none_when_decode_fails(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager._get_file_url = MagicMock(return_value="http://map")
    manager._protocol.cloud.get_file = MagicMock(return_value=MagicMock(decode=lambda: "raw"))
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map", MagicMock(return_value=(None, None)))

    assert manager.get_history_map("obj") is None


def test_get_history_map_marks_history_map_and_skips_optimization_when_not_needed(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    map_data = MapData()
    map_data.need_optimization = False
    manager._get_file_url = MagicMock(return_value="http://map")
    manager._protocol.cloud.get_file = MagicMock(return_value=MagicMock(decode=lambda: "raw"))
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map", MagicMock(return_value=(map_data, None)))
    manager.optimizer.optimize = MagicMock()

    result = manager.get_history_map("obj", key="k")

    assert result is map_data
    assert result.history_map is True
    manager.optimizer.optimize.assert_not_called()


def test_get_history_map_optimizes_when_needed(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    map_data = MapData()
    map_data.need_optimization = True
    saved_map_data = MapData()
    optimized = MapData()
    optimized.need_optimization = True  # must be flipped to False by get_history_map afterwards

    manager._get_file_url = MagicMock(return_value="http://map")
    manager._protocol.cloud.get_file = MagicMock(return_value=MagicMock(decode=lambda: "raw"))
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map", MagicMock(return_value=(map_data, saved_map_data)))
    manager.optimizer.optimize = MagicMock(return_value=optimized)

    result = manager.get_history_map("obj")

    manager.optimizer.optimize.assert_called_once_with(map_data, saved_map_data)
    assert result is optimized
    assert result.need_optimization is False


def test_get_history_map_swallows_exceptions(manager: DreameMapVacuumMapManager) -> None:
    manager._get_file_url = MagicMock(side_effect=RuntimeError("boom"))

    assert manager.get_history_map("obj") is None


# ---------------------------------------------------------------------------
# get_recovery_map
# ---------------------------------------------------------------------------


def test_get_recovery_map_returns_none_for_unknown_map_id(manager: DreameMapVacuumMapManager) -> None:
    manager._map_list = [1, 2]

    assert manager.get_recovery_map(99, 1) is None


def test_get_recovery_map_returns_none_for_out_of_range_index(manager: DreameMapVacuumMapManager) -> None:
    manager._map_list = [1]
    manager._saved_map_data = {1: MagicMock(recovery_map_list=[MagicMock()])}

    assert manager.get_recovery_map(1, 5) is None


def test_get_recovery_map_returns_cached_map_data_without_decoding(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    cached = MapData()
    entry = MagicMock(map_data=cached)
    manager._map_list = [1]
    manager._saved_map_data = {1: MagicMock(recovery_map_list=[entry])}
    decode = MagicMock()
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_saved_map", decode)

    result = manager.get_recovery_map(1, 1)

    assert result is cached
    decode.assert_not_called()


def test_get_recovery_map_fetches_raw_map_then_decodes(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = MagicMock(
        map_data=None,
        raw_map=None,
        map_object_name="obj_name",
        date=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
        map_type="TYPE",
    )
    manager._map_list = [1]
    manager._saved_map_data = {1: MagicMock(recovery_map_list=[entry], rotation=180)}
    manager._get_interim_file_data = MagicMock(return_value=MagicMock(decode=lambda: "raw_map_str"))
    decoded = MapData()
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_saved_map", MagicMock(return_value=decoded))

    result = manager.get_recovery_map(1, 1)

    assert result is decoded
    assert result.recovery_map is True
    assert result.recovery_map_type == "TYPE"
    manager._get_interim_file_data.assert_called_once_with("obj_name")


def test_get_recovery_map_returns_none_when_object_fetch_raises(
    manager: DreameMapVacuumMapManager,
) -> None:
    entry = MagicMock(map_data=None, raw_map=None, map_object_name="obj_name")
    manager._map_list = [1]
    manager._saved_map_data = {1: MagicMock(recovery_map_list=[entry])}
    manager._get_interim_file_data = MagicMock(side_effect=RuntimeError("fetch failed"))

    assert manager.get_recovery_map(1, 1) is None


def test_get_recovery_map_returns_none_when_no_raw_map_available_at_all(
    manager: DreameMapVacuumMapManager,
) -> None:
    """No cached map_data, no raw_map, and no map_object_name to fetch from -> stays None."""
    entry = MagicMock(map_data=None, raw_map=None, map_object_name=None)
    manager._map_list = [1]
    manager._saved_map_data = {1: MagicMock(recovery_map_list=[entry])}

    assert manager.get_recovery_map(1, 1) is None


# ---------------------------------------------------------------------------
# get_recovery_map_file
# ---------------------------------------------------------------------------


def test_get_recovery_map_file_returns_none_tuple_for_unknown_map_id(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._map_list = []

    assert manager.get_recovery_map_file(99, 1) == (None, None, None)


def test_get_recovery_map_file_returns_none_tuple_when_object_name_missing(
    manager: DreameMapVacuumMapManager,
) -> None:
    entry = MagicMock(object_name="")
    manager._map_list = [1]
    manager._saved_map_data = {1: MagicMock(recovery_map_list=[entry])}

    assert manager.get_recovery_map_file(1, 1) == (None, None, None)


def test_get_recovery_map_file_returns_none_tuple_when_no_url(manager: DreameMapVacuumMapManager) -> None:
    entry = MagicMock(object_name="obj.map")
    manager._map_list = [1]
    manager._saved_map_data = {1: MagicMock(recovery_map_list=[entry])}
    manager._get_file_url = MagicMock(return_value=None)

    assert manager.get_recovery_map_file(1, 1) == (None, None, None)


def test_get_recovery_map_file_returns_file_bytes_url_and_object_name(
    manager: DreameMapVacuumMapManager,
) -> None:
    entry = MagicMock(object_name="obj.map")
    manager._map_list = [1]
    manager._saved_map_data = {1: MagicMock(recovery_map_list=[entry])}
    manager._get_file_url = MagicMock(return_value="http://recovery")
    manager._protocol.cloud.get_file = MagicMock(return_value=b"filebytes")

    result = manager.get_recovery_map_file(1, 1)

    assert result == (b"filebytes", "http://recovery", "obj.map")


@pytest.mark.parametrize(
    ("object_name", "dreame_cloud", "expected_interim"),
    [
        ("plain_object", False, True),  # no special suffix -> always interim
        ("archive_mb.tbz2", False, False),  # tbz2 archive on a non dreame_cloud device -> direct file URL
        ("archive_mb.tbz2", True, True),  # tbz2 archive but dreame_cloud device -> still interim
    ],
)
def test_get_recovery_map_file_picks_interim_flag_from_object_name_suffix(
    manager: DreameMapVacuumMapManager, object_name: str, dreame_cloud: bool, expected_interim: bool
) -> None:
    entry = MagicMock(object_name=object_name)
    manager._map_list = [1]
    manager._saved_map_data = {1: MagicMock(recovery_map_list=[entry])}
    manager._protocol.dreame_cloud = dreame_cloud
    manager._get_file_url = MagicMock(return_value="http://recovery")
    manager._protocol.cloud.get_file = MagicMock(return_value=b"filebytes")

    manager.get_recovery_map_file(1, 1)

    manager._get_file_url.assert_called_once_with(object_name, expected_interim)
