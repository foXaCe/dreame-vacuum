"""Non-regression tests for Passe 4 (threading concurrency) fixes.

U7: cleaning-history "lost update" — a concurrent MQTT push must not be clobbered
    by the stale 'pending' value restored in the failure path.
U8: orphan Timer after disconnect() — schedule_update must never arm a Timer once
    the device is disconnected, and disconnect()/reschedule must be deadlock-free.

Tests are deterministic: thread interleavings are pivoted within a single thread by
patching the network/update call, so there is no stress or timing dependency.
"""

from __future__ import annotations

from threading import Lock, RLock
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.dreame_vacuum.dreame.device import DreameVacuumDevice

# --- U7: conditional restore in _request_cleaning_history --------------------


def _history_device(get_device_event) -> DreameVacuumDevice:
    device: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    device._cleaning_history_lock = Lock()
    device._cleaning_history_update = -1
    device._cleaning_history_retry_after = 0
    device.property_mapping = {}
    device.get_property = lambda *args, **kwargs: None
    device.status = SimpleNamespace(_cleaning_history=None)
    device.capability = SimpleNamespace(cruising=False)
    device._protocol = SimpleNamespace(
        connected=True,
        prefer_cloud=False,
        dreame_cloud=False,
        cloud=SimpleNamespace(connected=True, get_device_event=get_device_event),
    )
    return device


def test_u7_concurrent_push_is_not_clobbered_on_failed_fetch() -> None:
    """A push that re-arms a fetch during a failing fetch must survive the finally."""

    def fetch(*_args, **_kwargs):
        # Simulate an MQTT push landing mid-fetch: it re-arms a fresh re-fetch.
        device._cleaning_history_update = 12345.0
        return  # the fetch itself fails

    device = _history_device(fetch)
    device._request_cleaning_history()

    # The fresh push signal must be preserved; no 5-minute backoff posted over it.
    assert device._cleaning_history_update == 12345.0
    assert device._cleaning_history_retry_after == 0


def test_u7_failed_fetch_without_push_restores_pending_and_backs_off() -> None:
    """Without a concurrent push, a failed fetch restores the pending value + backoff."""

    device = _history_device(lambda *a, **k: None)
    device._request_cleaning_history()

    assert device._cleaning_history_update == -1  # pending value restored
    assert device._cleaning_history_retry_after > 0  # 5-minute backoff armed


# --- U8: no orphan Timer after disconnect ------------------------------------


def _timer_device() -> DreameVacuumDevice:
    device: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    device._timer_lock = RLock()
    device._update_timer = None
    device.disconnected = False
    device._ready = True
    device.available = True
    device._update_fail_count = 0
    device._callback_timer = None
    device._map_manager = None
    device._protocol = MagicMock()
    device._property_changed = MagicMock()
    return device


def test_u8_inflight_timer_does_not_rearm_after_disconnect() -> None:
    """If disconnect() runs during update(), _update_task must not arm an orphan Timer."""
    device = _timer_device()

    def fake_update(force_request_properties=False):
        # disconnect() lands while the timer task is mid-update.
        device.disconnect()

    device.update = fake_update
    device._update_task()

    assert device.disconnected is True
    assert device._update_timer is None  # no orphan timer scheduled post-teardown


def test_u8_schedule_update_refuses_to_arm_when_disconnected() -> None:
    """schedule_update must not create a Timer once the device is disconnected."""
    device = _timer_device()
    device.disconnected = True

    device.schedule_update(30)

    assert device._update_timer is None


def test_u8_disconnect_is_reentrant_and_cancels_timer() -> None:
    """disconnect() holds the RLock while calling schedule_update(): must not deadlock."""
    device = _timer_device()
    timer = MagicMock()
    device._update_timer = timer

    device.disconnect()  # would hang forever with a non-reentrant Lock

    assert device.disconnected is True
    assert device._update_timer is None
    timer.cancel.assert_called_once()
    device._protocol.disconnect.assert_called_once()
