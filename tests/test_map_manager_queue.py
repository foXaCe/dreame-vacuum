"""Characterization tests for the P/I/W frame queue and _add_map_data state machine.

This is the stateful heart of DreameMapVacuumMapManager: partial map frames can
arrive out of order (P frames are diffs applied on top of the last I frame), and
the manager must queue, drop, or request-retransmit them depending on ordering.

DreameVacuumMapDecoder.decode_p_map_data_from_partial / decode_map_data_from_partial
are monkeypatched so each test controls exactly what a "decoded" frame looks like,
without needing real binary/AES-encoded map payloads (matching this repo's existing
pattern of monkeypatching DreameVacuumMapDecoder.decode_saved_map in test_map_manager.py).

Because these tests call _add_map_data() directly (bypassing _decode_map_partial),
_latest_map_id / _latest_map_timestamp_ms — normally maintained by _decode_map_partial —
are set explicitly to simulate that bookkeeping.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
from custom_components.dreame_vacuum.dreame.map_manager import DreameMapVacuumMapManager
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    MapData,
    MapDataPartial,
    MapFrameType,
    Point,
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
    mgr = DreameMapVacuumMapManager(protocol)
    mgr._change_callback = MagicMock()
    mgr._update_callback = MagicMock()
    return mgr


def _partial(map_id: int, frame_id: int, frame_type: int, timestamp_ms: int | None = None) -> MapDataPartial:
    p = MapDataPartial()
    p.map_id = map_id
    p.frame_id = frame_id
    p.frame_type = frame_type
    p.timestamp_ms = timestamp_ms
    return p


def _map_data(map_id: int, frame_id: int, frame_type: int, timestamp_ms: int, **overrides: object) -> MapData:
    md = MapData()
    md.map_id = map_id
    md.frame_id = frame_id
    md.frame_type = frame_type
    md.timestamp_ms = timestamp_ms
    for key, value in overrides.items():
        setattr(md, key, value)
    return md


# ---------------------------------------------------------------------------
# _queue_partial_map
# ---------------------------------------------------------------------------


def test_queue_partial_map_ignores_frame_for_a_different_map_id(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A partial map for a map_id other than the currently tracked latest map is dropped."""
    manager._latest_map_id = 1
    partial = _partial(map_id=2, frame_id=5, frame_type=MapFrameType.P.value)

    manager._queue_partial_map(partial)

    assert manager._map_data_queue == {}


def test_queue_partial_map_drops_frame_older_than_next_expected(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A frame at or behind the next-expected frame_id is not queued (it is stale).

    Note: the map_id bucket is created unconditionally before the staleness check,
    so an empty ``{map_id: {}}`` placeholder is left behind even though nothing was
    actually queued -- documented here as observed (harmless) behavior.
    """
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 5  # next expected is 6
    partial = _partial(map_id=1, frame_id=5, frame_type=MapFrameType.P.value)

    manager._queue_partial_map(partial)

    assert manager._map_data_queue == {1: {}}


def test_queue_partial_map_stores_future_frame_for_current_map(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A genuinely-ahead frame for the currently tracked map is queued under [map_id][frame_id]."""
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 5  # next expected is 6
    partial = _partial(map_id=1, frame_id=8, frame_type=MapFrameType.P.value)

    manager._queue_partial_map(partial)

    assert manager._map_data_queue[1][8] is partial


def test_queue_partial_map_accepts_frame_zero_when_no_current_map_tracked(
    manager: DreameMapVacuumMapManager,
) -> None:
    """When there is no current map yet (current_map_id != latest_map_id), next_frame_id defaults to 0."""
    manager._latest_map_id = 1
    manager._current_map_id = None
    partial = _partial(map_id=1, frame_id=0, frame_type=MapFrameType.I.value)

    manager._queue_partial_map(partial)

    assert manager._map_data_queue[1][0] is partial


# ---------------------------------------------------------------------------
# _delete_invalid_partial_maps
# ---------------------------------------------------------------------------


def test_delete_invalid_partial_maps_noop_without_latest_map_id(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._latest_map_id = None
    manager._map_data_queue = {1: {2: object()}}

    manager._delete_invalid_partial_maps()

    assert manager._map_data_queue == {1: {2: manager._map_data_queue[1][2]}}


def test_delete_invalid_partial_maps_noop_without_current_frame_id(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._latest_map_id = 1
    manager._current_frame_id = None
    manager._map_data_queue = {1: {2: object()}}

    manager._delete_invalid_partial_maps()

    assert manager._map_data_queue == {1: {2: manager._map_data_queue[1][2]}}


def test_delete_invalid_partial_maps_drops_other_map_ids_and_stale_frames(
    manager: DreameMapVacuumMapManager,
) -> None:
    """Frames for a different map_id, and frames at/behind current_frame_id, are purged."""
    manager._latest_map_id = 1
    manager._current_frame_id = 4
    manager._map_data_queue = {
        1: {3: "stale", 4: "stale_equal", 5: "future_ok", 6: "future_ok_too"},
        2: {9: "other_map_dropped_entirely"},
    }

    manager._delete_invalid_partial_maps()

    assert 2 not in manager._map_data_queue
    assert set(manager._map_data_queue[1].keys()) == {5, 6}


# ---------------------------------------------------------------------------
# _unqueue_next_partial_map / _unqueue_partial_map / _partial_map_queue_size
# ---------------------------------------------------------------------------


def test_unqueue_next_partial_map_returns_none_when_map_id_mismatch(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._latest_map_id = 1
    manager._current_map_id = 2  # mismatch: no "current" map tracked yet for latest
    manager._current_frame_id = 5

    assert manager._unqueue_next_partial_map() is None


def test_unqueue_next_partial_map_pops_and_returns_the_expected_next_frame(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 5
    sentinel = object()
    manager._map_data_queue = {1: {6: sentinel, 7: "later"}}

    result = manager._unqueue_next_partial_map()

    assert result is sentinel
    assert 6 not in manager._map_data_queue[1]
    assert 7 in manager._map_data_queue[1]


def test_unqueue_next_partial_map_leaves_falsy_entry_in_place_and_returns_none(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A falsy (e.g. None) queued entry is not popped and yields None, unlike a real object."""
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 5
    manager._map_data_queue = {1: {6: None}}

    result = manager._unqueue_next_partial_map()

    assert result is None
    assert 6 in manager._map_data_queue[1]  # not removed


def test_unqueue_partial_map_pops_specific_entry(manager: DreameMapVacuumMapManager) -> None:
    sentinel = object()
    manager._map_data_queue = {3: {9: sentinel}}

    result = manager._unqueue_partial_map(3, 9)

    assert result is sentinel
    assert 9 not in manager._map_data_queue[3]


def test_unqueue_partial_map_returns_none_when_absent(manager: DreameMapVacuumMapManager) -> None:
    manager._map_data_queue = {}

    assert manager._unqueue_partial_map(1, 1) is None


def test_partial_map_queue_size_zero_without_timestamp_watermark(
    manager: DreameMapVacuumMapManager,
) -> None:
    """No decoded frame has ever been seen (_latest_map_timestamp_ms is None) -> size is defined as 0."""
    manager._latest_map_timestamp_ms = None
    manager._map_data_queue = {1: {2: object(), 3: object()}}
    manager._latest_map_id = 1

    assert manager._partial_map_queue_size() == 0


def test_partial_map_queue_size_zero_when_latest_map_id_absent_from_queue(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A timestamp watermark exists, but nothing has ever been queued for the current latest_map_id."""
    manager._latest_map_timestamp_ms = 1000
    manager._latest_map_id = 5
    manager._map_data_queue = {1: {2: object()}}

    assert manager._partial_map_queue_size() == 0


def test_partial_map_queue_size_counts_entries_for_latest_map(
    manager: DreameMapVacuumMapManager,
) -> None:
    manager._latest_map_timestamp_ms = 1000
    manager._latest_map_id = 1
    manager._map_data_queue = {1: {2: object(), 3: object()}, 2: {9: object()}}

    assert manager._partial_map_queue_size() == 2


# ---------------------------------------------------------------------------
# _add_map_data: top-level guard clauses shared by all frame types
# ---------------------------------------------------------------------------


def test_add_map_data_returns_false_for_none_partial_map(manager: DreameMapVacuumMapManager) -> None:
    """A None partial map (e.g. a failed decode upstream) is rejected outright."""
    assert manager._add_map_data(None) is False


def test_add_map_data_skips_older_timestamp_than_current(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A frame timestamped before the currently applied frame is dropped without touching decoders."""
    manager._current_frame_id = 5
    manager._current_map_id = 1
    manager._current_timestamp_ms = 5000
    manager._latest_map_id = 1
    partial = _partial(map_id=1, frame_id=6, frame_type=MapFrameType.P.value, timestamp_ms=4000)
    decode_p = MagicMock()
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_p_map_data_from_partial", decode_p)

    result = manager._add_map_data(partial)

    assert result is True
    decode_p.assert_not_called()


def test_add_map_data_skips_frame_for_a_different_map_id(manager: DreameMapVacuumMapManager) -> None:
    """A partial map for a map_id that isn't the tracked latest one is skipped."""
    manager._current_map_id = 1
    manager._latest_map_id = 1
    partial = _partial(map_id=99, frame_id=1, frame_type=MapFrameType.P.value, timestamp_ms=1000)

    result = manager._add_map_data(partial)

    assert result is True
    assert manager._current_map_id == 1  # untouched


def test_add_map_data_map_id_change_resets_tracking_before_reprocessing(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    When the latest_map_id diverges from the stale current_map_id, tracking resets to None
    and the incoming frame (now matching the new latest_map_id) is processed as fresh.
    """
    manager._current_map_id = 1
    manager._current_frame_id = 4
    manager._current_timestamp_ms = 4000
    manager._latest_map_id = 2  # a new map has started elsewhere (bookkeeping already updated)

    new_map = _map_data(map_id=2, frame_id=0, frame_type=MapFrameType.I.value, timestamp_ms=5000, empty_map=False)
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(new_map, None)))

    partial = _partial(map_id=2, frame_id=0, frame_type=MapFrameType.I.value, timestamp_ms=5000)
    result = manager._add_map_data(partial)

    assert result is True
    assert manager._current_map_id == 2
    assert manager._current_frame_id == 0
    assert manager._map_data is new_map


def test_add_map_data_map_id_change_with_saved_map_payload_wipes_stale_live_map_data(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    When the map_id-changed reset clears _current_frame_id to None but the incoming I
    frame's map_data.saved_map=True (which skips the whole "live map" changed-detection
    block entirely), the manager is left with _current_frame_id=None while _map_data is
    still the stale previous object. The shared tail cleanup then wipes it and notifies,
    rather than leaving a frame-orphaned stale map_data lying around.
    """
    stale_map_data = _map_data(1, 4, MapFrameType.I.value, 4000)
    manager._current_map_id = 1
    manager._current_frame_id = 4
    manager._current_timestamp_ms = 4000
    manager._map_data = stale_map_data
    manager._latest_map_id = 2  # a new map has started elsewhere

    saved_map_only = _map_data(2, 0, MapFrameType.I.value, 5000, saved_map=True, empty_map=False)
    monkeypatch.setattr(
        DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(saved_map_only, None))
    )

    partial = _partial(map_id=2, frame_id=0, frame_type=MapFrameType.I.value, timestamp_ms=5000)
    result = manager._add_map_data(partial)

    assert result is True
    assert manager._current_frame_id is None  # reset by the map_id-changed branch, never reassigned
    assert manager._map_data is None  # wiped by the shared tail cleanup
    manager._change_callback.assert_called_once_with(False)


def test_add_map_data_i_frame_with_newer_timestamp_bypasses_frame_id_regression_guard(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    An I frame with a *lower* frame_id than current but a strictly newer timestamp represents
    a device-side frame counter reset (e.g. after reboot) and must still be processed, unlike
    a P frame in the same situation.
    """
    manager._current_map_id = 1
    manager._current_frame_id = 10
    manager._current_timestamp_ms = 1000
    manager._latest_map_id = 1

    new_map = _map_data(map_id=1, frame_id=0, frame_type=MapFrameType.I.value, timestamp_ms=2000, empty_map=False)
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(new_map, None)))

    partial = _partial(map_id=1, frame_id=0, frame_type=MapFrameType.I.value, timestamp_ms=2000)
    result = manager._add_map_data(partial)

    assert result is True
    assert manager._current_frame_id == 0
    assert manager._map_data is new_map


def test_add_map_data_p_frame_with_lower_frame_id_is_dropped_regardless_of_timestamp(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unlike I frames, a P frame behind current_frame_id is always dropped, even with a newer timestamp."""
    manager._current_map_id = 1
    manager._current_frame_id = 10
    manager._current_timestamp_ms = 1000
    manager._latest_map_id = 1
    decode_p = MagicMock()
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_p_map_data_from_partial", decode_p)

    partial = _partial(map_id=1, frame_id=3, frame_type=MapFrameType.P.value, timestamp_ms=9999)
    result = manager._add_map_data(partial)

    assert result is True
    decode_p.assert_not_called()
    assert manager._current_frame_id == 10


# ---------------------------------------------------------------------------
# _add_map_data: full P/I/W lifecycle scenario (the stateful queue in action)
# ---------------------------------------------------------------------------


def test_full_frame_lifecycle_i_bootstrap_then_sequential_and_out_of_order_p_frames(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    End-to-end scenario exercising the stateful P/I/W queue:
    1. An I frame bootstraps the map.
    2. A sequential P frame (frame_id == current+1) applies immediately.
    3. An out-of-order P frame (frame_id > current+1) is queued and triggers a
       gap-fill request instead of applying immediately.
    4. A duplicate P frame (frame_id == current, not < current) is dropped by
       the P-block's own de-dup check (add_next_map_data, no state change).
    5. The missing gap frame arrives and applies normally...
    6. ...which then automatically drains the previously queued out-of-order
       frame via _add_next_map_data (frame chaining), advancing state twice
       from a single _add_map_data() call.
    """
    manager._latest_map_id = 1

    decode_p = MagicMock()
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_p_map_data_from_partial", decode_p)

    # --- 1. I frame bootstrap -------------------------------------------------
    map_i = _map_data(map_id=1, frame_id=0, frame_type=MapFrameType.I.value, timestamp_ms=1000, empty_map=False)
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(map_i, None)))
    partial_i = _partial(map_id=1, frame_id=0, frame_type=MapFrameType.I.value, timestamp_ms=1000)

    assert manager._add_map_data(partial_i) is True
    assert manager._map_data is map_i
    assert manager._current_frame_id == 0
    manager._change_callback.assert_called_once_with(False)

    # --- 2. Sequential P frame applies immediately ----------------------------
    map_p1 = _map_data(
        map_id=1, frame_id=1, frame_type=MapFrameType.P.value, timestamp_ms=2000, robot_position=Point(1, 1)
    )
    decode_p.return_value = map_p1
    partial_p1 = _partial(map_id=1, frame_id=1, frame_type=MapFrameType.P.value, timestamp_ms=2000)

    assert manager._add_map_data(partial_p1) is True
    assert manager._map_data is map_p1
    assert manager._current_frame_id == 1
    assert manager._current_timestamp_ms == 2000

    # --- 3. Out-of-order P frame (frame_id=3, expected=2) is queued ----------
    manager._request_next_p_map = MagicMock()
    # Normally maintained by _decode_map_partial (bypassed here); reflects that this
    # frame's timestamp is now the latest one observed.
    manager._latest_map_timestamp_ms = 4000
    partial_p3 = _partial(map_id=1, frame_id=3, frame_type=MapFrameType.P.value, timestamp_ms=4000)
    decode_p.reset_mock()

    assert manager._add_map_data(partial_p3) is True
    assert manager._current_frame_id == 1  # unchanged: not applied yet
    assert manager._map_data_queue[1][3] is partial_p3
    manager._request_next_p_map.assert_called_once_with(1, 2)
    decode_p.assert_not_called()  # queued, not decoded

    # --- 4. Duplicate of the current frame is dropped (P-block de-dup) -------
    partial_p1_dup = _partial(map_id=1, frame_id=1, frame_type=MapFrameType.P.value, timestamp_ms=2000)
    decode_p.reset_mock()

    assert manager._add_map_data(partial_p1_dup) is True
    assert manager._current_frame_id == 1  # unchanged
    decode_p.assert_not_called()
    assert manager._map_data_queue[1][3] is partial_p3  # queued frame 3 survives the dedup no-op

    # --- 5 & 6. The missing frame 2 arrives, applies, and auto-drains frame 3 --
    map_p2 = _map_data(map_id=1, frame_id=2, frame_type=MapFrameType.P.value, timestamp_ms=3000)
    map_p3 = _map_data(map_id=1, frame_id=3, frame_type=MapFrameType.P.value, timestamp_ms=4000)
    decode_p.side_effect = [map_p2, map_p3]
    partial_p2 = _partial(map_id=1, frame_id=2, frame_type=MapFrameType.P.value, timestamp_ms=3000)

    assert manager._add_map_data(partial_p2) is True

    # A single _add_map_data() call for frame 2 advanced state twice: frame 2 applied
    # directly, then _add_next_map_data() found frame 3 sitting in the queue (the exact
    # next-expected frame_id) and recursively decoded+applied it too.
    assert decode_p.call_count == 2
    assert decode_p.call_args_list[0].args[0] is partial_p2
    assert decode_p.call_args_list[1].args[0] is partial_p3
    assert manager._current_frame_id == 3
    assert manager._map_data is map_p3
    assert 3 not in manager._map_data_queue.get(1, {})


# ---------------------------------------------------------------------------
# _add_map_data: P out-of-order gap-fill strategy differs for dreame_cloud devices
# (they push updates instead of pulling P frames one-by-one).
# ---------------------------------------------------------------------------


def _setup_out_of_order(manager: DreameMapVacuumMapManager, queued_frame_ids: list[int]) -> None:
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 3
    manager._latest_map_timestamp_ms = 9000
    manager._map_data = _map_data(map_id=1, frame_id=3, frame_type=MapFrameType.P.value, timestamp_ms=1000)
    manager._map_data_queue = {1: {fid: object() for fid in queued_frame_ids}}


def test_add_map_data_dreame_cloud_large_gap_requests_full_map(
    manager: DreameMapVacuumMapManager,
) -> None:
    """dreame_cloud devices with a >8 frame backlog give up on P frames and request a full map."""
    manager._protocol.dreame_cloud = True
    _setup_out_of_order(manager, list(range(10, 18)))  # 8 queued + the new one below = 9 (> 8)
    manager._request_map = MagicMock(return_value=None)
    manager._request_missing_p_map = MagicMock()
    manager._request_next_p_map = MagicMock()

    partial = _partial(map_id=1, frame_id=20, frame_type=MapFrameType.P.value, timestamp_ms=9500)
    result = manager._add_map_data(partial)

    assert result is True
    manager._request_map.assert_called_once()
    manager._request_missing_p_map.assert_not_called()
    manager._request_next_p_map.assert_not_called()


def test_add_map_data_dreame_cloud_medium_gap_requests_missing_p_map(
    manager: DreameMapVacuumMapManager,
) -> None:
    """dreame_cloud devices with a 5-8 frame backlog request just the missing P frame."""
    manager._protocol.dreame_cloud = True
    _setup_out_of_order(manager, list(range(10, 14)))  # 4 queued + new one = 5 (> 4, <= 8)
    manager._request_map = MagicMock()
    manager._request_missing_p_map = MagicMock()
    manager._request_next_p_map = MagicMock()

    partial = _partial(map_id=1, frame_id=20, frame_type=MapFrameType.P.value, timestamp_ms=9500)
    result = manager._add_map_data(partial)

    assert result is True
    manager._request_missing_p_map.assert_called_once()
    manager._request_map.assert_not_called()
    manager._request_next_p_map.assert_not_called()


def test_add_map_data_dreame_cloud_small_gap_requests_next_p_map_for_current_frame(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A small (<=4) backlog on a dreame_cloud device asks for current_frame_id+1 via the latest_map_id."""
    manager._protocol.dreame_cloud = True
    _setup_out_of_order(manager, [])  # only the new frame ends up queued -> tmpLen == 1
    manager._request_next_p_map = MagicMock()

    partial = _partial(map_id=1, frame_id=20, frame_type=MapFrameType.P.value, timestamp_ms=9500)
    result = manager._add_map_data(partial)

    assert result is True
    manager._request_next_p_map.assert_called_once_with(1, 4)  # latest_map_id, current_frame_id(3)+1


def test_add_map_data_dreame_cloud_small_gap_with_falsy_current_frame_id_defaults_to_one(
    manager: DreameMapVacuumMapManager,
) -> None:
    """When current_frame_id is 0 (falsy), the small-gap request falls back to next_frame_id=1."""
    manager._protocol.dreame_cloud = True
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 0
    manager._latest_map_timestamp_ms = 9000
    manager._map_data = _map_data(map_id=1, frame_id=0, frame_type=MapFrameType.P.value, timestamp_ms=1000)
    manager._map_data_queue = {}
    manager._request_next_p_map = MagicMock()

    partial = _partial(map_id=1, frame_id=20, frame_type=MapFrameType.P.value, timestamp_ms=9500)
    result = manager._add_map_data(partial)

    assert result is True
    manager._request_next_p_map.assert_called_once_with(1, 1)


def test_add_map_data_p_out_of_order_with_no_timestamp_watermark_skips_request_entirely(
    manager: DreameMapVacuumMapManager,
) -> None:
    """
    _partial_map_queue_size() is defined to return 0 whenever _latest_map_timestamp_ms
    is still None (no frame has ever been through _decode_map_partial), even though a
    frame was just queued. In that case out-of-order handling falls through to a plain
    _add_next_map_data() instead of requesting a retransmit.
    """
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 3
    manager._latest_map_timestamp_ms = None  # never set: forces _partial_map_queue_size() == 0
    manager._map_data = _map_data(map_id=1, frame_id=3, frame_type=MapFrameType.P.value, timestamp_ms=1000)
    manager._request_next_p_map = MagicMock()
    manager._request_missing_p_map = MagicMock()
    manager._request_map = MagicMock()

    partial = _partial(map_id=1, frame_id=20, frame_type=MapFrameType.P.value, timestamp_ms=9500)
    result = manager._add_map_data(partial)

    assert result is True
    assert manager._map_data_queue[1][20] is partial  # still queued...
    # ...but no retransmit request was issued, since the queue "looked" empty.
    manager._request_next_p_map.assert_not_called()
    manager._request_missing_p_map.assert_not_called()
    manager._request_map.assert_not_called()


def test_w_frame_passes_validation_but_produces_no_map_update(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """
    A W-type frame (MapFrameType.W) that otherwise passes every top-level guard (correct
    map_id, correct next frame_id, newer timestamp) is *not* handled by either the P or
    the I branch in _add_map_data (there is no `elif frame_type == W` case). The frame is
    silently accepted (returns True) with no decoder call and no state change - this is
    left unchanged, but an explicit debug log now records that it was ignored instead of
    staying completely silent.
    """
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 4
    manager._current_timestamp_ms = 4000
    existing_map_data = manager._map_data = _map_data(
        map_id=1, frame_id=4, frame_type=MapFrameType.P.value, timestamp_ms=4000
    )

    decode_p = MagicMock()
    decode_i = MagicMock()
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_p_map_data_from_partial", decode_p)
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_data_from_partial", decode_i)

    partial_w = _partial(map_id=1, frame_id=5, frame_type=MapFrameType.W.value, timestamp_ms=5000)
    with caplog.at_level(logging.DEBUG, logger="custom_components.dreame_vacuum.dreame.map_manager"):
        result = manager._add_map_data(partial_w)

    assert result is True
    decode_p.assert_not_called()
    decode_i.assert_not_called()
    assert manager._current_frame_id == 4  # NOT advanced to 5
    assert manager._map_data is existing_map_data  # untouched
    assert "no decoder for this type" in caplog.text


def test_add_map_data_p_frame_invalid_decode_result_leaves_state_unchanged(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A P frame that decodes to a falsy/corrupted result must not corrupt or advance manager state."""
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 4
    manager._current_timestamp_ms = 4000
    existing_map_data = manager._map_data = _map_data(
        map_id=1, frame_id=4, frame_type=MapFrameType.P.value, timestamp_ms=4000
    )
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_p_map_data_from_partial", MagicMock(return_value=None))

    partial_p = _partial(map_id=1, frame_id=5, frame_type=MapFrameType.P.value, timestamp_ms=5000)
    result = manager._add_map_data(partial_p)

    assert result is True
    assert manager._current_frame_id == 4
    assert manager._map_data is existing_map_data


def test_add_map_data_i_frame_invalid_decode_result_short_circuits(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """decode_map_data_from_partial returning a None map_data must short-circuit without touching state."""
    manager._latest_map_id = 1
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(None, None)))

    partial_i = _partial(map_id=1, frame_id=0, frame_type=MapFrameType.I.value, timestamp_ms=1000)
    result = manager._add_map_data(partial_i)

    assert result is True
    assert manager._map_data is None
    assert manager._current_frame_id is None


def test_add_map_data_p_frame_requests_i_map_when_no_current_map_yet(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A P frame arriving before any I frame is queued and triggers an I-map bootstrap request."""
    manager._latest_map_id = 1
    manager._request_i_map = MagicMock(return_value=True)

    partial_p = _partial(map_id=1, frame_id=1, frame_type=MapFrameType.P.value, timestamp_ms=1000)
    result = manager._add_map_data(partial_p)

    assert result is True
    manager._request_i_map.assert_called_once()
    assert manager._map_data_queue[1][1] is partial_p


def test_add_map_data_p_frame_restored_map_forces_full_reset(
    manager: DreameMapVacuumMapManager,
) -> None:
    """A P frame arriving while the current map is a 'restored_map' forces a full state wipe first."""
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 4
    manager._map_data = _map_data(
        map_id=1, frame_id=4, frame_type=MapFrameType.I.value, timestamp_ms=1000, restored_map=True
    )
    manager._request_i_map = MagicMock(return_value=True)

    partial_p = _partial(map_id=1, frame_id=5, frame_type=MapFrameType.P.value, timestamp_ms=2000)
    result = manager._add_map_data(partial_p)

    assert result is True
    assert manager._map_data is None
    assert manager._current_frame_id is None
    assert manager._current_map_id is None
    manager._request_i_map.assert_called_once()


# ---------------------------------------------------------------------------
# _add_map_data: I-frame carpet_pixels regeneration
# ---------------------------------------------------------------------------


def test_add_map_data_p_frame_regenerates_carpet_pixels_when_dimensions_change(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """carpet_pixels are recomputed via get_carpets() when the map's dimensions changed from the previous frame."""
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 3
    manager._current_timestamp_ms = 1000
    manager._map_data = _map_data(
        map_id=1, frame_id=3, frame_type=MapFrameType.P.value, timestamp_ms=1000, dimensions="dims_v1"
    )

    new_map = _map_data(
        map_id=1,
        frame_id=4,
        frame_type=MapFrameType.P.value,
        timestamp_ms=2000,
        dimensions="dims_v2",
        carpet_pixels="raw_carpets",
    )
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_p_map_data_from_partial", MagicMock(return_value=new_map))
    get_carpets = MagicMock(return_value="regenerated_carpets")
    monkeypatch.setattr(DreameVacuumMapDecoder, "get_carpets", get_carpets)

    partial_p = _partial(map_id=1, frame_id=4, frame_type=MapFrameType.P.value, timestamp_ms=2000)
    manager._add_map_data(partial_p)

    get_carpets.assert_called_once()
    assert manager._map_data.carpet_pixels == "regenerated_carpets"


def test_add_map_data_p_frame_keeps_carpet_pixels_when_dimensions_unchanged(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No dimensions change -> get_carpets() is not called and the decoded carpet_pixels are kept as-is."""
    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 3
    manager._current_timestamp_ms = 1000
    manager._map_data = _map_data(
        map_id=1, frame_id=3, frame_type=MapFrameType.P.value, timestamp_ms=1000, dimensions="dims_v1"
    )

    new_map = _map_data(
        map_id=1,
        frame_id=4,
        frame_type=MapFrameType.P.value,
        timestamp_ms=2000,
        dimensions="dims_v1",
        carpet_pixels="raw_carpets",
    )
    monkeypatch.setattr(DreameVacuumMapDecoder, "decode_p_map_data_from_partial", MagicMock(return_value=new_map))
    get_carpets = MagicMock()
    monkeypatch.setattr(DreameVacuumMapDecoder, "get_carpets", get_carpets)

    partial_p = _partial(map_id=1, frame_id=4, frame_type=MapFrameType.P.value, timestamp_ms=2000)
    manager._add_map_data(partial_p)

    get_carpets.assert_not_called()
    assert manager._map_data.carpet_pixels == "raw_carpets"


# ---------------------------------------------------------------------------
# _add_map_data: I-frame empty_map handling
# ---------------------------------------------------------------------------


def test_add_map_data_i_frame_empty_map_first_time_resets_and_notifies(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first empty-map I frame (no prior map, or a prior non-empty map) triggers a full state reset."""
    manager._latest_map_id = 1
    manager._map_list = [1]  # sanity: pre-existing state that _init_data() must wipe
    empty_map = _map_data(map_id=1, frame_id=0, frame_type=MapFrameType.I.value, timestamp_ms=1000, empty_map=True)
    monkeypatch.setattr(
        DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(empty_map, None))
    )

    partial_i = _partial(map_id=1, frame_id=0, frame_type=MapFrameType.I.value, timestamp_ms=1000)
    result = manager._add_map_data(partial_i)

    assert result is True
    assert manager._map_data is empty_map
    assert manager._map_list == []  # wiped by _init_data()
    manager._change_callback.assert_called_once_with(False)


def test_add_map_data_i_frame_already_empty_map_skips_reinit_and_notify(
    manager: DreameMapVacuumMapManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repeat empty-map I frame while already tracking an empty map does not reset state or notify again."""
    manager._latest_map_id = 1
    manager._map_data = _map_data(
        map_id=1, frame_id=0, frame_type=MapFrameType.I.value, timestamp_ms=500, empty_map=True
    )
    manager._map_list = [1]

    new_empty_map = _map_data(map_id=1, frame_id=1, frame_type=MapFrameType.I.value, timestamp_ms=1000, empty_map=True)
    monkeypatch.setattr(
        DreameVacuumMapDecoder, "decode_map_data_from_partial", MagicMock(return_value=(new_empty_map, None))
    )

    partial_i = _partial(map_id=1, frame_id=1, frame_type=MapFrameType.I.value, timestamp_ms=1000)
    result = manager._add_map_data(partial_i)

    assert result is True
    manager._change_callback.assert_not_called()
    assert manager._map_list == [1]  # untouched: _init_data() was not called
