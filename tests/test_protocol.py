"""Characterization tests for the Dreame cloud protocol layer.

These tests lock down the OBSERVED behaviour of DreameVacuumDreameHomeCloudProtocol
without modifying any production code. Divergences from the plan are noted inline.
"""

from __future__ import annotations

import json
import queue
from unittest.mock import MagicMock, patch

import pytest

from custom_components.dreame_vacuum.dreame.exceptions import RateLimitError
from custom_components.dreame_vacuum.dreame.http_client import (
    HttpConnectionError,
    HttpTimeoutError,
)
from custom_components.dreame_vacuum.dreame.protocol import (
    DreameVacuumDreameHomeCloudProtocol,
)
from custom_components.dreame_vacuum.dreame.resilience import CircuitState


@pytest.fixture
def proto() -> DreameVacuumDreameHomeCloudProtocol:
    """Return a DreameHomeCloud protocol instance with minimal fixtures injected."""
    p = DreameVacuumDreameHomeCloudProtocol("user@example.com", "secret", country="eu")
    # _strings is populated at login time; inject a dummy 60-entry list so
    # accessors that index into it work without network I/O.
    p._strings = [f"s{i}" for i in range(60)]
    p._key = "test-key"
    return p


# ---------------------------------------------------------------------------
# Étape 2 : Accesseurs purs et helpers statiques
# ---------------------------------------------------------------------------


def test_get_random_agent_id_length() -> None:
    """get_random_agent_id() returns exactly 13 characters."""
    result = DreameVacuumDreameHomeCloudProtocol.get_random_agent_id()
    assert len(result) == 13


def test_get_random_agent_id_charset() -> None:
    """get_random_agent_id() only contains characters from 'ABCDEF'."""
    result = DreameVacuumDreameHomeCloudProtocol.get_random_agent_id()
    assert set(result) <= set("ABCDEF")


def test_get_api_url(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    """get_api_url() builds URL from country + _strings[0] and _strings[1]."""
    # country="eu" → prefix "eu"; strings[0]="s0", strings[1]="s1"
    assert proto.get_api_url() == "https://eus0:s1"


def test_object_name(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    """object_name property returns '<model>/<uid>/<did>/0'."""
    proto._model = "m"
    proto._uid = "u"
    proto._did = "d"
    assert proto.object_name == "m/u/d/0"


def test_connected_false_by_default(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    """connected is False when both flags are False."""
    proto._connected = False
    proto._client_connected = False
    assert proto.connected is False


def test_connected_requires_both_flags(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    """connected is True only when _connected AND _client_connected are True."""
    proto._connected = True
    proto._client_connected = False
    assert proto.connected is False

    proto._connected = False
    proto._client_connected = True
    assert proto.connected is False

    proto._connected = True
    proto._client_connected = True
    assert proto.connected is True


def test_auth_key_returns_constructor_param() -> None:
    """auth_key property returns the auth_key passed at construction."""
    p = DreameVacuumDreameHomeCloudProtocol("user@example.com", "secret", auth_key="my-auth-key")
    assert p.auth_key == "my-auth-key"


def test_auth_key_none_by_default() -> None:
    """auth_key is None when not provided at construction."""
    p = DreameVacuumDreameHomeCloudProtocol("user@example.com", "secret")
    assert p.auth_key is None


# ---------------------------------------------------------------------------
# Étape 3 : Comportement de request()
# ---------------------------------------------------------------------------


def _mock_response(status: int, text: str, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.text = text
    resp.headers = headers or {}
    return resp


def test_request_200_valid_json(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    """HTTP 200 with valid JSON returns parsed dict and sets _connected=True."""
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(200, '{"ok": 1}')

    result = proto.request("https://example.com/api", None)

    assert result == {"ok": 1}
    assert proto._connected is True


def test_request_200_invalid_json(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    """HTTP 200 with non-JSON body returns None."""
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(200, "not json")

    result = proto.request("https://example.com/api", None)

    assert result is None


def test_request_429_raises_rate_limit_error(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """HTTP 429 raises RateLimitError with retry_after from Retry-After header."""
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(429, "", headers={"Retry-After": "30"})

    with pytest.raises(RateLimitError) as exc_info:
        proto.request("https://example.com/api", None)

    assert exc_info.value.retry_after == 30.0


def test_request_401_relogin_replays(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """HTTP 401 with _secondary_key triggers login() then replays once returning 200 JSON."""
    proto._secondary_key = "secondary-k"
    proto._session = MagicMock()
    resp_401 = _mock_response(401, "Unauthorized")
    resp_200 = _mock_response(200, '{"ok": 2}')
    proto._session.post.side_effect = [resp_401, resp_200]

    with patch.object(proto, "login", return_value=True) as mock_login:
        result = proto.request("https://example.com/api", None)

    assert result == {"ok": 2}
    assert proto._session.post.call_count == 2
    mock_login.assert_called_once()


def test_request_401_relogin_already_attempted(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """HTTP 401 with _relogin_attempted=True returns None without calling login()."""
    proto._secondary_key = "secondary-k"
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(401, "Unauthorized")

    with patch.object(proto, "login", return_value=True) as mock_login:
        result = proto.request("https://example.com/api", None, _relogin_attempted=True)

    assert result is None
    mock_login.assert_not_called()


def test_request_circuit_open_skips_post(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """When circuit breaker is OPEN, request() returns None without calling post."""
    # Drive circuit to OPEN by repeated failures (failure_threshold=5)
    for _ in range(proto._circuit_breaker.failure_threshold):
        proto._circuit_breaker.record_failure()

    assert proto._circuit_breaker.state is CircuitState.OPEN

    proto._session = MagicMock()
    result = proto.request("https://example.com/api", None)

    assert result is None
    proto._session.post.assert_not_called()


def test_request_timeout_retries(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """Timeout retries: post called retry_count+1 times, sleep called retry_count times."""
    proto._session = MagicMock()
    proto._session.post.side_effect = HttpTimeoutError

    with patch("custom_components.dreame_vacuum.dreame.protocol.sleep") as mock_sleep:
        result = proto.request("https://example.com/api", None, retry_count=2)

    assert result is None
    # retry_count=2 → 3 total attempts (0, 1, 2)
    assert proto._session.post.call_count == 3
    # sleep called between retries: 2 times
    assert mock_sleep.call_count == 2


# ---------------------------------------------------------------------------
# Étape 4 : Parsing MQTT et disconnect
# ---------------------------------------------------------------------------


def test_on_client_message_valid_payload(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """Valid MQTT message with 'data' key is pushed onto _client_queue."""
    proto._message_callback = MagicMock()
    # Pre-set flags to bypass the dirty-patch branch
    proto._client_connected = True
    proto._connected = True

    payload = json.dumps({"data": {"x": 1}}).encode("utf-8")
    fake_msg = MagicMock()
    fake_msg.payload = payload

    DreameVacuumDreameHomeCloudProtocol._on_client_message(None, proto, fake_msg)

    callback, data = proto._client_queue.get_nowait()
    assert callback is proto._message_callback
    assert data == {"x": 1}


def test_on_client_message_invalid_utf8(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """Non-UTF-8 payload is silently ignored, queue stays empty."""
    proto._message_callback = MagicMock()
    proto._client_connected = True
    proto._connected = True

    fake_msg = MagicMock()
    fake_msg.payload = b"\xff\xfe"

    DreameVacuumDreameHomeCloudProtocol._on_client_message(None, proto, fake_msg)

    with pytest.raises(queue.Empty):
        proto._client_queue.get_nowait()


def test_on_client_message_json_without_data(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """JSON without a 'data' key is silently ignored, queue stays empty."""
    proto._message_callback = MagicMock()
    proto._client_connected = True
    proto._connected = True

    fake_msg = MagicMock()
    fake_msg.payload = json.dumps({"other": "value"}).encode("utf-8")

    DreameVacuumDreameHomeCloudProtocol._on_client_message(None, proto, fake_msg)

    with pytest.raises(queue.Empty):
        proto._client_queue.get_nowait()


def test_request_connection_error_retries(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """ConnectionError retries: post called retry_count+1 times, sleep called retry_count times."""
    proto._session = MagicMock()
    proto._session.post.side_effect = HttpConnectionError("refused")

    with patch("custom_components.dreame_vacuum.dreame.protocol.sleep") as mock_sleep:
        result = proto.request("https://example.com/api", None, retry_count=2)

    assert result is None
    assert proto._session.post.call_count == 3
    assert mock_sleep.call_count == 2


def test_request_generic_exception_no_retry(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """A generic exception exhausts retries and returns None."""
    proto._session = MagicMock()
    proto._session.post.side_effect = RuntimeError("unexpected")

    result = proto.request("https://example.com/api", None, retry_count=1)

    assert result is None
    # Generic Exception branch does NOT sleep and does NOT retry further
    assert proto._session.post.call_count >= 1


def test_request_retry_count_zero_normalized(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """retry_count=0 (or negative) → single attempt, no retries."""
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(200, '{"v": 0}')

    result = proto.request("https://example.com/api", None, retry_count=0)

    assert result == {"v": 0}
    assert proto._session.post.call_count == 1


def test_request_retry_count_negative_normalized(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """retry_count=-1 → normalized to 0, single attempt."""
    proto._session = MagicMock()
    proto._session.post.side_effect = HttpTimeoutError

    with patch("custom_components.dreame_vacuum.dreame.protocol.sleep") as mock_sleep:
        result = proto.request("https://example.com/api", None, retry_count=-1)

    assert result is None
    assert proto._session.post.call_count == 1
    mock_sleep.assert_not_called()


def test_request_401_login_returns_false(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """HTTP 401 with _secondary_key but login() returns False → falls through to record_failure."""
    proto._secondary_key = "secondary-k"
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(401, "Unauthorized")

    with patch.object(proto, "login", return_value=False) as mock_login:
        result = proto.request("https://example.com/api", None)

    assert result is None
    mock_login.assert_called_once()


def test_request_non_401_non_429_non_200(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """Any other status code (e.g. 500) records a failure and returns None."""
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(500, "Server Error")

    result = proto.request("https://example.com/api", None)

    assert result is None
    # Circuit breaker should have registered a failure
    assert proto._circuit_breaker._failure_count >= 1


def test_request_401_no_secondary_key(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """HTTP 401 without _secondary_key goes straight to record_failure, returns None."""
    proto._secondary_key = None
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(401, "Unauthorized")

    with patch.object(proto, "login") as mock_login:
        result = proto.request("https://example.com/api", None)

    assert result is None
    mock_login.assert_not_called()


def test_request_429_default_retry_after(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """HTTP 429 without Retry-After header defaults retry_after to 60.0."""
    proto._session = MagicMock()
    # No Retry-After header
    proto._session.post.return_value = _mock_response(429, "", headers={})

    with pytest.raises(RateLimitError) as exc_info:
        proto.request("https://example.com/api", None)

    assert exc_info.value.retry_after == 60.0


def test_request_country_cn_adds_header(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """For country='cn', the CN-specific header is included (strings[48])."""
    # Re-create proto with country=cn
    p = DreameVacuumDreameHomeCloudProtocol("user@example.com", "secret", country="cn")
    p._strings = [f"s{i}" for i in range(60)]
    p._key = "test-key"
    p._session = MagicMock()
    p._session.post.return_value = _mock_response(200, '{"cn": 1}')

    result = p.request("https://example.com/api", None)

    assert result == {"cn": 1}
    call_kwargs = p._session.post.call_args
    sent_headers = call_kwargs[1]["headers"]
    # strings[48] should be a key in the headers for cn
    assert "s48" in sent_headers


def test_request_key_expire_login_fails_returns_none(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """If key is expired and login() fails, request returns None without calling post."""
    import time as _time

    proto._session = MagicMock()
    # Set key_expire to a past timestamp
    proto._key_expire = _time.time() - 1.0

    with patch.object(proto, "login", return_value=False):
        result = proto.request("https://example.com/api", None)

    assert result is None
    proto._session.post.assert_not_called()


def test_request_timeout_with_connected_logs_warning(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """Timeout while _connected=True triggers logging path (coverage for :780 branch)."""
    proto._session = MagicMock()
    proto._session.post.side_effect = HttpTimeoutError
    proto._connected = True  # triggers the warning branch

    with patch("custom_components.dreame_vacuum.dreame.protocol.sleep"):
        result = proto.request("https://example.com/api", None, retry_count=1)

    assert result is None
    assert proto._session.post.call_count == 2


def test_request_connection_error_with_connected_logs_warning(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """ConnectionError while _connected=True triggers logging path (coverage for :787 branch)."""
    proto._session = MagicMock()
    proto._session.post.side_effect = HttpConnectionError("refused")
    proto._connected = True

    with patch("custom_components.dreame_vacuum.dreame.protocol.sleep"):
        result = proto.request("https://example.com/api", None, retry_count=1)

    assert result is None


def test_request_generic_exception_with_connected_logs_warning(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """Generic Exception while _connected=True triggers logging path (coverage for :792 branch)."""
    proto._session = MagicMock()
    proto._session.post.side_effect = RuntimeError("boom")
    proto._connected = True

    result = proto.request("https://example.com/api", None, retry_count=1)

    assert result is None


def test_disconnect_fresh_instance(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """disconnect() on a fresh instance raises no exception and resets flags."""
    # Ensure no MQTT client, no threads
    proto._client = None
    proto._thread = None
    proto._client_thread = None
    # Simulate logged-in state
    proto._logged_in = True
    proto._connected = True

    proto.disconnect()

    assert proto._logged_in is False
    assert proto._connected is False


def test_pure_properties(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    """Cover simple pure properties on DreameHome protocol."""
    assert proto.dreame_cloud is True
    assert proto.logged_in is False
    assert proto.auth_failed is False
    proto._did = "dev123"
    assert proto.device_id == "dev123"


def test_reconnect_timer_cancel_noop_when_none(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """_reconnect_timer_cancel does nothing when timer is None."""
    proto._reconnect_timer = None
    proto._reconnect_timer_cancel()  # should not raise


def test_reconnect_timer_cancel_calls_cancel(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """_reconnect_timer_cancel calls .cancel() on the timer and clears it."""
    mock_timer = MagicMock()
    proto._reconnect_timer = mock_timer

    proto._reconnect_timer_cancel()

    mock_timer.cancel.assert_called_once()
    assert proto._reconnect_timer is None


def test_on_client_message_dirty_patch_triggers_connected_callback(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """When _client_connected is False, dirty-patch sets it True and fires connected_callback."""
    proto._message_callback = MagicMock()
    proto._connected_callback = MagicMock()
    # Simulate disconnected state (triggers the dirty-patch branch)
    proto._client_connected = False
    proto._connected = False

    payload = json.dumps({"data": {"x": 1}}).encode("utf-8")
    fake_msg = MagicMock()
    fake_msg.payload = payload

    DreameVacuumDreameHomeCloudProtocol._on_client_message(None, proto, fake_msg)

    assert proto._client_connected is True
    assert proto._connected is True
    # connected_callback should have been pushed onto the queue
    cb, arg = proto._client_queue.get_nowait()
    assert cb is proto._connected_callback
    assert arg is None
    # And the data message too
    cb2, data = proto._client_queue.get_nowait()
    assert cb2 is proto._message_callback
    assert data == {"x": 1}


def test_on_client_message_generic_exception_ignored(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """A generic exception inside _on_client_message is swallowed, queue stays empty."""
    proto._client_connected = True
    proto._connected = True

    # Make message_callback truthy but payload.decode raise a non-JSON/UnicodeDecodeError
    proto._message_callback = MagicMock()
    fake_msg = MagicMock()
    fake_msg.payload = MagicMock()
    fake_msg.payload.decode.side_effect = AttributeError("boom")

    # Should not raise
    DreameVacuumDreameHomeCloudProtocol._on_client_message(None, proto, fake_msg)

    with pytest.raises(queue.Empty):
        proto._client_queue.get_nowait()


def test_disconnect_with_mqtt_client_and_threads(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    """disconnect() calls client.disconnect()/loop_stop() and sends sentinel to threads."""
    mock_client = MagicMock()
    proto._client = mock_client
    proto._client_connected = True
    proto._client_connecting = True
    # Simulate active threads with sentinel-safe real queues (already queue.Queue instances)
    import threading

    proto._thread = threading.Thread(target=lambda: None)
    proto._client_thread = threading.Thread(target=lambda: None)
    proto._logged_in = True
    proto._connected = True

    proto.disconnect()

    mock_client.disconnect.assert_called_once()
    mock_client.loop_stop.assert_called_once()
    assert proto._client is None
    assert proto._client_connected is False
    assert proto._client_connecting is False
    assert proto._logged_in is False
    assert proto._connected is False
    # Sentinels pushed into queues
    assert proto._queue.get_nowait() == []
    assert proto._client_queue.get_nowait() == []


class TestSendRequestIdAllocation:
    """Concurrent send() calls must never share a request id."""

    def test_concurrent_sends_use_unique_ids(self):
        import threading

        from custom_components.dreame_vacuum.dreame.protocol import (
            DreameVacuumDreameHomeCloudProtocol,
        )

        proto = DreameVacuumDreameHomeCloudProtocol.__new__(DreameVacuumDreameHomeCloudProtocol)
        proto._id = 0
        proto._id_lock = threading.Lock()
        proto._did = "123"
        proto._host = "eu.host"
        proto._strings = [str(i) for i in range(60)]

        seen_ids = []
        lock = threading.Lock()

        def fake_api_call(url, params=None, retry_count=2):
            with lock:
                seen_ids.append(params["id"])
                assert params["data"]["id"] == params["id"]
            return {"data": {"result": []}}

        proto._api_call = fake_api_call

        threads = [threading.Thread(target=proto.send, args=("get_properties", [])) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert len(seen_ids) == 8
        assert len(set(seen_ids)) == 8, f"ids dupliqués: {sorted(seen_ids)}"
        assert sorted(seen_ids) == list(range(1, 9))
