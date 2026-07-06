"""Non-regression tests for Passe 2 (coordinator robustness) and Passe 3 (security).

Covers B3 (Liskov signature), B4 (device kept on transient error), B6 (no implicit
None on disconnect), B16 (401 re-login replay without spurious breaker failure),
B21 (config flow session closed on flow end) behaviourally, and B9 via a guard.
"""

from __future__ import annotations

from datetime import timedelta
import inspect
import pathlib
from unittest.mock import AsyncMock, MagicMock

from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.dreame_vacuum.config_flow import DreameVacuumFlowHandler
from custom_components.dreame_vacuum.coordinator import DreameVacuumDataUpdateCoordinator
from custom_components.dreame_vacuum.dreame.exceptions import RateLimitError
from custom_components.dreame_vacuum.dreame.protocol import DreameVacuumDreameHomeCloudProtocol

_CC = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "dreame_vacuum"


def _coordinator() -> tuple[DreameVacuumDataUpdateCoordinator, MagicMock]:
    coord = object.__new__(DreameVacuumDataUpdateCoordinator)
    coord.hass = MagicMock()
    coord.update_interval = timedelta(seconds=300)
    coord._default_update_interval = timedelta(seconds=300)
    coord.async_set_updated_data = MagicMock()
    device = MagicMock()
    device.auth_failed = False
    device.disconnected = False
    coord._device = device
    return coord, device


# --- B3: async_set_updated_data signature must match the HA parent (Liskov) --


def test_b3_async_set_updated_data_signature_matches_parent() -> None:
    params = list(inspect.signature(DreameVacuumDataUpdateCoordinator.async_set_updated_data).parameters)
    assert params == ["self", "data"]


# --- B4: a transient update error must NOT destroy the device ----------------


async def test_b4_transient_error_keeps_device() -> None:
    coord, device = _coordinator()
    coord.hass.async_add_executor_job = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()

    # Device preserved so _perform_update can reconnect on the next refresh.
    assert coord._device is device


# --- B5 (coordinator side): RateLimitError backs off the poll interval -------


async def test_b5_rate_limit_backs_off_interval() -> None:
    coord, device = _coordinator()
    coord.hass.async_add_executor_job = AsyncMock(side_effect=RateLimitError(retry_after=90))

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()

    assert coord.update_interval == timedelta(seconds=90)
    assert coord._device is device


# --- B6: a disconnect after a successful update must not return None ----------


async def test_b6_disconnected_after_update_raises_update_failed() -> None:
    coord, device = _coordinator()
    device.disconnected = True
    coord.hass.async_add_executor_job = AsyncMock(return_value=None)

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


# --- B16: 401 triggers a single re-login + replay, no spurious breaker fail ---


def _dreame_protocol() -> DreameVacuumDreameHomeCloudProtocol:
    proto: DreameVacuumDreameHomeCloudProtocol = object.__new__(DreameVacuumDreameHomeCloudProtocol)
    proto._circuit_breaker = MagicMock()
    proto._secondary_key = "tok"
    proto._key = "k"
    proto._ti = None
    proto._country = "de"
    proto._connected = True
    proto._key_expire = 0
    proto._timeout_config = MagicMock()
    proto._strings = [str(i) for i in range(60)]
    proto._session = MagicMock()
    proto.login = MagicMock(return_value=True)
    return proto


def test_b16_replays_once_after_relogin_without_breaker_failure() -> None:
    proto = _dreame_protocol()
    proto._session.post.side_effect = [MagicMock(status=401), MagicMock(status=200, text='{"ok": 1}')]

    result = proto.request("http://x", "data", retry_count=0)

    assert result == {"ok": 1}
    assert proto.login.call_count == 1
    assert proto._session.post.call_count == 2
    proto._circuit_breaker.record_failure.assert_not_called()


def test_b16_login_failure_records_single_breaker_failure() -> None:
    proto = _dreame_protocol()
    proto.login.return_value = False
    proto._session.post.side_effect = [MagicMock(status=401)]

    assert proto.request("http://x", "data", retry_count=0) is None
    assert proto._session.post.call_count == 1  # no replay when login fails
    proto._circuit_breaker.record_failure.assert_called_once()


def test_b16_no_infinite_relogin_loop() -> None:
    proto = _dreame_protocol()
    proto._session.post.side_effect = [MagicMock(status=401), MagicMock(status=401)]

    assert proto.request("http://x", "data", retry_count=0) is None
    assert proto.login.call_count == 1  # relogin attempted at most once
    assert proto._session.post.call_count == 2
    proto._circuit_breaker.record_failure.assert_called_once()


# --- B21: the config flow must close its throwaway session on flow end -------


def test_b21_async_remove_closes_protocol() -> None:
    flow = object.__new__(DreameVacuumFlowHandler)
    protocol = MagicMock()
    flow.protocol = protocol

    flow.async_remove()

    protocol.disconnect.assert_called_once()
    assert flow.protocol is None


def test_b21_async_remove_is_noop_without_protocol() -> None:
    flow = object.__new__(DreameVacuumFlowHandler)
    flow.protocol = None

    flow.async_remove()  # must not raise

    assert flow.protocol is None


# --- B9: reauth must not blindly re-persist the cleartext password -----------


def test_b9_reauth_drops_password_when_auth_key_available() -> None:
    """Guard: the reauth path must drop CONF_PASSWORD when an auth_key is held."""
    src = (_CC / "config_flow.py").read_text()
    assert "data.pop(CONF_PASSWORD, None)" in src
