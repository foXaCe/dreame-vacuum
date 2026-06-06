"""Tests for Dreame vacuum device update concurrency behavior."""

from __future__ import annotations

from threading import Lock
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.dreame_vacuum.dreame.device import DreameVacuumDevice
from custom_components.dreame_vacuum.dreame.exceptions import DeviceUpdateFailedException, RateLimitError


def _minimal_device() -> Any:
    device: Any = object.__new__(DreameVacuumDevice)
    device._update_lock = Lock()
    device._update_running = False
    device._map_initialized = True
    device._protocol = SimpleNamespace(
        connected=True,
        cloud=SimpleNamespace(connected=True),
        prefer_cloud=False,
        dreame_cloud=False,
    )
    device._last_settings_request = 0
    device._last_update_failed = 0
    device._last_change = 0
    device._consumable_change = False
    device._read_write_properties = []
    device._last_map_list_request = 0
    device._dirty_data = {}
    device._dirty_auto_switch_data = {}
    device._dirty_ai_data = {}
    device._map_manager = None
    device._draining_complete_time = None
    device._deferred_cloud_loaded = True
    device.status = SimpleNamespace(
        active=False,
        started=False,
        washing=False,
        map_backup_status=False,
        map_recovery_status=False,
    )
    device.capability = SimpleNamespace(
        backup_map=False,
        dnd_task=True,
    )
    return device


def test_update_returns_immediately_when_already_running() -> None:
    """A concurrent update should be ignored before touching connection state."""
    device = _minimal_device()
    device._update_running = True
    device.connect_cloud = pytest.fail

    device.update()

    assert device._update_running is True


def test_update_sets_running_flag_during_request_and_resets_on_failure() -> None:
    """The guard must be active while the update body is executing."""
    device = _minimal_device()

    def request_properties(_properties):
        assert device._update_running is True
        raise RuntimeError("boom")

    device._request_properties = request_properties

    with pytest.raises(DeviceUpdateFailedException):
        device.update()

    assert device._update_running is False


def test_perform_update_propagates_rate_limit_error() -> None:
    """B5: RateLimitError must propagate unflattened so the coordinator backs off."""
    device = _minimal_device()
    device._request_properties = MagicMock(side_effect=RateLimitError(retry_after=120))

    with pytest.raises(RateLimitError) as exc_info:
        device.update()

    assert exc_info.value.retry_after == 120
    assert device._update_running is False


def test_perform_update_wraps_generic_errors() -> None:
    """Non-rate-limit errors stay wrapped in DeviceUpdateFailedException (no regression)."""
    device = _minimal_device()
    device._request_properties = MagicMock(side_effect=ValueError("boom"))

    with pytest.raises(DeviceUpdateFailedException):
        device.update()
