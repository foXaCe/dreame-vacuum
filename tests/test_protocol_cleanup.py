"""Tests for protocol cleanup paths."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from custom_components.dreame_vacuum.dreame.protocol import DreameVacuumDreameHomeCloudProtocol


def test_dreame_cloud_disconnect_cancels_pending_reconnect_timer() -> None:
    """Unload/reload should not leave a pending MQTT reconnect timer alive."""
    protocol: Any = object.__new__(DreameVacuumDreameHomeCloudProtocol)
    timer = MagicMock()
    protocol._reconnect_timer = timer
    protocol._session = MagicMock()
    protocol._circuit_breaker = MagicMock()
    protocol._client = None
    protocol._thread = None
    protocol._client_thread = None
    protocol._message_callback = MagicMock()
    protocol._connected_callback = MagicMock()

    protocol.disconnect()

    timer.cancel.assert_called_once()
    assert protocol._reconnect_timer is None
    assert protocol._message_callback is None
    assert protocol._connected_callback is None
