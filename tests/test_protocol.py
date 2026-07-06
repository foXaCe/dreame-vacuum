"""Characterization tests for the Dreame cloud protocol layer.

These tests lock down the OBSERVED behaviour of DreameVacuumDreameHomeCloudProtocol
without modifying any production code. Divergences from the plan are noted inline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from custom_components.dreame_vacuum.dreame.exceptions import RateLimitError
from custom_components.dreame_vacuum.dreame.http_client import (
    HttpConnectionError,
    HttpRequestError,
    HttpTimeoutError,
)
from custom_components.dreame_vacuum.dreame.protocol import (
    DreameVacuumDreameHomeCloudProtocol,
    DreameVacuumMiHomeCloudProtocol,
    redact_url,
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


# ---------------------------------------------------------------------------
# Étape 5 : _check_mqtt_fingerprint (TOFU pinning)
# ---------------------------------------------------------------------------


class _FakeTLSSocket:
    def __init__(self, der: bytes | None) -> None:
        self._der = der

    def getpeercert(self, binary_form: bool = False) -> bytes | None:
        return self._der

    def __enter__(self) -> _FakeTLSSocket:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class _FakeRawSocket:
    def __enter__(self) -> _FakeRawSocket:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class _FakeSSLContext:
    def __init__(self, der: bytes | None) -> None:
        self._der = der
        self.check_hostname = True
        self.verify_mode = None

    def wrap_socket(self, raw: object, server_hostname: str | None = None) -> _FakeTLSSocket:
        return _FakeTLSSocket(self._der)


@pytest.fixture(autouse=True)
def _clear_mqtt_fingerprints() -> None:
    """Isolate the TOFU cache and listener list (both ClassVars) between tests."""
    DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprints.clear()
    DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprint_listeners.clear()


def test_check_mqtt_fingerprint_first_time_is_trust_on_first_use(caplog: pytest.LogCaptureFixture) -> None:
    der = b"certificate-bytes-1"
    with (
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.socket.create_connection",
            return_value=_FakeRawSocket(),
        ),
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.ssl.create_default_context",
            return_value=_FakeSSLContext(der),
        ),
        caplog.at_level(logging.INFO),
    ):
        DreameVacuumDreameHomeCloudProtocol._check_mqtt_fingerprint("mqtt.example.com", 8883)

    expected = hashlib.sha256(der).hexdigest()
    assert DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprints["mqtt.example.com:8883"] == expected
    assert "cert fingerprint" in caplog.text


def test_check_mqtt_fingerprint_change_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    key = "mqtt.example.com:8883"
    DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprints[key] = "old-fingerprint"
    der = b"certificate-bytes-2"
    with (
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.socket.create_connection",
            return_value=_FakeRawSocket(),
        ),
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.ssl.create_default_context",
            return_value=_FakeSSLContext(der),
        ),
        caplog.at_level(logging.WARNING),
    ):
        DreameVacuumDreameHomeCloudProtocol._check_mqtt_fingerprint("mqtt.example.com", 8883)

    assert "fingerprint changed" in caplog.text
    # The old baseline must NOT be clobbered by an unverified new certificate:
    # a mismatch keeps trusting "old-fingerprint" until the user explicitly
    # re-trusts the new one (via trust_mqtt_fingerprint / the repair flow).
    # This inverts the previous assertion, which encoded the bug this plan fixes.
    assert DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprints[key] == "old-fingerprint"


def test_check_mqtt_fingerprint_first_time_notifies_listener_with_none_previous() -> None:
    der = b"certificate-bytes-1"
    calls: list[tuple[str, str, str | None]] = []
    DreameVacuumDreameHomeCloudProtocol.add_mqtt_fingerprint_listener(
        lambda key, fingerprint, previous: calls.append((key, fingerprint, previous))
    )
    with (
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.socket.create_connection",
            return_value=_FakeRawSocket(),
        ),
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.ssl.create_default_context",
            return_value=_FakeSSLContext(der),
        ),
    ):
        DreameVacuumDreameHomeCloudProtocol._check_mqtt_fingerprint("mqtt.example.com", 8883)

    expected = hashlib.sha256(der).hexdigest()
    assert calls == [("mqtt.example.com:8883", expected, None)]


def test_check_mqtt_fingerprint_change_notifies_listener_with_previous() -> None:
    key = "mqtt.example.com:8883"
    DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprints[key] = "old-fingerprint"
    der = b"certificate-bytes-2"
    calls: list[tuple[str, str, str | None]] = []
    DreameVacuumDreameHomeCloudProtocol.add_mqtt_fingerprint_listener(
        lambda key, fingerprint, previous: calls.append((key, fingerprint, previous))
    )
    with (
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.socket.create_connection",
            return_value=_FakeRawSocket(),
        ),
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.ssl.create_default_context",
            return_value=_FakeSSLContext(der),
        ),
    ):
        DreameVacuumDreameHomeCloudProtocol._check_mqtt_fingerprint("mqtt.example.com", 8883)

    expected = hashlib.sha256(der).hexdigest()
    assert calls == [(key, expected, "old-fingerprint")]


def test_check_mqtt_fingerprint_listener_exception_is_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    der = b"certificate-bytes-1"

    def _boom(key: str, fingerprint: str, previous: str | None) -> None:
        raise RuntimeError("listener boom")

    DreameVacuumDreameHomeCloudProtocol.add_mqtt_fingerprint_listener(_boom)
    with (
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.socket.create_connection",
            return_value=_FakeRawSocket(),
        ),
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.ssl.create_default_context",
            return_value=_FakeSSLContext(der),
        ),
        caplog.at_level(logging.DEBUG),
    ):
        DreameVacuumDreameHomeCloudProtocol._check_mqtt_fingerprint("mqtt.example.com", 8883)  # must not raise

    expected = hashlib.sha256(der).hexdigest()
    assert DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprints["mqtt.example.com:8883"] == expected


def test_add_mqtt_fingerprint_listener_remover_unregisters() -> None:
    calls: list[tuple[str, str, str | None]] = []
    remove = DreameVacuumDreameHomeCloudProtocol.add_mqtt_fingerprint_listener(
        lambda key, fingerprint, previous: calls.append((key, fingerprint, previous))
    )
    remove()

    der = b"certificate-bytes-1"
    with (
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.socket.create_connection",
            return_value=_FakeRawSocket(),
        ),
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.ssl.create_default_context",
            return_value=_FakeSSLContext(der),
        ),
    ):
        DreameVacuumDreameHomeCloudProtocol._check_mqtt_fingerprint("mqtt.example.com", 8883)

    assert calls == []


def test_trust_mqtt_fingerprint_then_check_same_cert_is_noop(caplog: pytest.LogCaptureFixture) -> None:
    key = "mqtt.example.com:8883"
    der = b"certificate-bytes-1"
    fingerprint = hashlib.sha256(der).hexdigest()
    DreameVacuumDreameHomeCloudProtocol.trust_mqtt_fingerprint(key, fingerprint)

    calls: list[tuple[str, str, str | None]] = []
    DreameVacuumDreameHomeCloudProtocol.add_mqtt_fingerprint_listener(lambda k, f, p: calls.append((k, f, p)))
    with (
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.socket.create_connection",
            return_value=_FakeRawSocket(),
        ),
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.ssl.create_default_context",
            return_value=_FakeSSLContext(der),
        ),
        caplog.at_level(logging.WARNING),
    ):
        DreameVacuumDreameHomeCloudProtocol._check_mqtt_fingerprint("mqtt.example.com", 8883)

    assert calls == []
    assert "fingerprint changed" not in caplog.text
    assert DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprints[key] == fingerprint


def test_check_mqtt_fingerprint_no_cert_is_noop() -> None:
    with (
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.socket.create_connection",
            return_value=_FakeRawSocket(),
        ),
        patch(
            "custom_components.dreame_vacuum.dreame.protocol.ssl.create_default_context",
            return_value=_FakeSSLContext(None),
        ),
    ):
        DreameVacuumDreameHomeCloudProtocol._check_mqtt_fingerprint("mqtt.example.com", 8883)

    assert DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprints == {}


def test_check_mqtt_fingerprint_exception_is_swallowed() -> None:
    with patch(
        "custom_components.dreame_vacuum.dreame.protocol.socket.create_connection",
        side_effect=OSError("refused"),
    ):
        DreameVacuumDreameHomeCloudProtocol._check_mqtt_fingerprint("mqtt.example.com", 8883)  # must not raise

    assert DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprints == {}


# ---------------------------------------------------------------------------
# Étape 6 : _api_task / _api_call_async / _api_call
# ---------------------------------------------------------------------------


def test_dreamehome_api_task_normal_item_calls_callback_and_sleeps(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._api_call = MagicMock(return_value={"data": {"result": "ok"}})
    callback = MagicMock()
    with patch("custom_components.dreame_vacuum.dreame.protocol.sleep") as mock_sleep:
        t = threading.Thread(target=proto._api_task)
        t.start()
        proto._queue.put((callback, "url", {"p": 1}, 2))
        proto._queue.join()
        proto._queue.put([])
        t.join(timeout=2)

    callback.assert_called_once_with({"data": {"result": "ok"}})
    proto._api_call.assert_called_once_with("url", {"p": 1}, 2)
    mock_sleep.assert_called_once_with(0.1)
    assert proto._thread is None


def test_dreamehome_api_task_rate_limit_error_is_caught(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._api_call = MagicMock(side_effect=RateLimitError(retry_after=5))
    callback = MagicMock()
    t = threading.Thread(target=proto._api_task)
    t.start()
    proto._queue.put((callback, "url", None, 1))
    proto._queue.join()
    proto._queue.put([])
    t.join(timeout=2)

    callback.assert_not_called()


def test_dreamehome_api_task_generic_exception_is_caught(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._api_call = MagicMock(side_effect=RuntimeError("boom"))
    callback = MagicMock()
    t = threading.Thread(target=proto._api_task)
    t.start()
    proto._queue.put((callback, "url", None, 1))
    proto._queue.join()
    proto._queue.put([])
    t.join(timeout=2)

    callback.assert_not_called()


def test_dreamehome_api_call_async_starts_thread_and_queues_item(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._api_call = MagicMock(return_value={"data": {"result": 1}})
    callback = MagicMock()

    proto._api_call_async(callback, "url/path", {"a": 1}, 3)
    assert proto._thread is not None
    proto._queue.join()

    callback.assert_called_once_with({"data": {"result": 1}})
    proto._queue.put([])
    proto._thread.join(timeout=2)


def test_dreamehome_api_call_builds_url_and_serializes_params(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    with patch.object(proto, "request", return_value={"ok": 1}) as mock_request:
        result = proto._api_call("path/x", {"b": 2}, 5)

    assert result == {"ok": 1}
    mock_request.assert_called_once_with(f"{proto.get_api_url()}/path/x", '{"b":2}', 5)


def test_dreamehome_api_call_none_params_sends_none_data(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    with patch.object(proto, "request", return_value={"ok": 2}) as mock_request:
        proto._api_call("path/y")

    mock_request.assert_called_once_with(f"{proto.get_api_url()}/path/y", None, 2)


# ---------------------------------------------------------------------------
# Étape 7 : reconnect timer / client key / client task
# ---------------------------------------------------------------------------


def test_reconnect_timer_task_marks_disconnected_when_still_connecting(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._client_connecting = True
    proto._client_connected = True
    proto._reconnect_timer = MagicMock()
    proto._reconnect_timer_task()
    assert proto._client_connected is False


def test_reconnect_timer_task_noop_when_not_connecting(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._client_connecting = False
    proto._client_connected = True
    proto._reconnect_timer = None
    proto._reconnect_timer_task()
    assert proto._client_connected is True


def test_set_client_key_updates_and_returns_true_on_change(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._client = MagicMock()
    proto._client_key = "old"
    proto._key = "new"
    proto._uuid = "uuid1"
    result = proto._set_client_key()
    assert result is True
    assert proto._client_key == "new"
    proto._client.username_pw_set.assert_called_once_with("uuid1", "new")


def test_set_client_key_returns_false_when_unchanged(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._client = MagicMock()
    proto._client_key = "same"
    proto._key = "same"
    result = proto._set_client_key()
    assert result is False
    proto._client.username_pw_set.assert_not_called()


def test_client_task_calls_callback_with_arg(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    cb = MagicMock()
    t = threading.Thread(target=proto._client_task)
    t.start()
    proto._client_queue.put((cb, {"x": 1}))
    proto._client_queue.join()
    proto._client_queue.put([])
    t.join(timeout=2)

    cb.assert_called_once_with({"x": 1})
    assert proto._client_thread is None


def test_client_task_calls_callback_without_arg(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    cb = MagicMock()
    t = threading.Thread(target=proto._client_task)
    t.start()
    proto._client_queue.put((cb, None))
    proto._client_queue.join()
    proto._client_queue.put([])
    t.join(timeout=2)

    cb.assert_called_once_with()


def test_client_task_swallows_exception(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    cb = MagicMock(side_effect=RuntimeError("boom"))
    t = threading.Thread(target=proto._client_task)
    t.start()
    proto._client_queue.put((cb, None))
    proto._client_queue.join()
    proto._client_queue.put([])
    t.join(timeout=2)  # must not raise / must terminate cleanly


# ---------------------------------------------------------------------------
# Étape 8 : _on_client_connect / _on_client_disconnect (paho v2 callbacks)
# ---------------------------------------------------------------------------


class _ReasonCode:
    """Minimal stand-in for paho's ReasonCode (is_failure + int equality)."""

    def __init__(self, is_failure: bool, value: int) -> None:
        self.is_failure = is_failure
        self._value = value

    def __eq__(self, other: object) -> bool:
        return self._value == other

    def __repr__(self) -> str:
        return f"ReasonCode({self._value})"


def test_on_client_connect_success_subscribes_and_queues_callback(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._did = "d1"
    proto._uid = "u1"
    proto._model = "m1"
    proto._country = "eu"
    proto._client_connected = False
    proto._connected_callback = MagicMock()
    mock_client = MagicMock()
    reason_code = _ReasonCode(False, 0)

    DreameVacuumDreameHomeCloudProtocol._on_client_connect(mock_client, proto, None, reason_code, None)

    assert proto._client_connected is True
    mock_client.subscribe.assert_called_once_with(f"/{proto._strings[7]}/d1/u1/m1/eu/")
    cb, arg = proto._client_queue.get_nowait()
    assert cb is proto._connected_callback
    assert arg is None


def test_on_client_connect_success_already_connected_no_callback_push(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._did = "d"
    proto._uid = "u"
    proto._model = "m"
    proto._country = "eu"
    proto._client_connected = True
    proto._connected_callback = None
    mock_client = MagicMock()
    reason_code = _ReasonCode(False, 0)

    DreameVacuumDreameHomeCloudProtocol._on_client_connect(mock_client, proto, None, reason_code, None)

    mock_client.subscribe.assert_called_once()
    with pytest.raises(queue.Empty):
        proto._client_queue.get_nowait()


def test_on_client_connect_failure_key_expired_relogin_success(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._key_expire = time.time() + 100
    with (
        patch.object(proto, "login", return_value=True) as mock_login,
        patch.object(proto, "_set_client_key") as mock_set_key,
    ):
        reason_code = _ReasonCode(True, 135)
        DreameVacuumDreameHomeCloudProtocol._on_client_connect(MagicMock(), proto, None, reason_code, None)

    mock_login.assert_called_once()
    mock_set_key.assert_called_once()


def test_on_client_connect_failure_other_reason_marks_disconnected(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._key_expire = None
    proto._client_connected = True
    with patch.object(proto, "_set_client_key", return_value=False):
        reason_code = _ReasonCode(True, 5)
        DreameVacuumDreameHomeCloudProtocol._on_client_connect(MagicMock(), proto, None, reason_code, None)

    assert proto._client_connected is False


def test_on_client_connect_failure_set_client_key_succeeds_no_state_change(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._key_expire = None
    proto._client_connected = True
    with patch.object(proto, "_set_client_key", return_value=True):
        reason_code = _ReasonCode(True, 5)
        DreameVacuumDreameHomeCloudProtocol._on_client_connect(MagicMock(), proto, None, reason_code, None)

    assert proto._client_connected is True


def test_on_client_disconnect_failure_starts_reconnect_timer(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._client_connected = True
    proto._client_connecting = False
    with (
        patch.object(proto, "_set_client_key", return_value=False),
        patch("custom_components.dreame_vacuum.dreame.protocol.Timer") as mock_timer_cls,
    ):
        mock_timer = MagicMock()
        mock_timer_cls.return_value = mock_timer
        reason_code = _ReasonCode(True, 5)
        DreameVacuumDreameHomeCloudProtocol._on_client_disconnect(MagicMock(), proto, None, reason_code, None)

    assert proto._client_connecting is True
    mock_timer_cls.assert_called_once_with(10, proto._reconnect_timer_task)
    mock_timer.start.assert_called_once()


def test_on_client_disconnect_failure_already_connecting_restarts_timer(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._client_connected = True
    proto._client_connecting = True
    with (
        patch.object(proto, "_set_client_key", return_value=False),
        patch("custom_components.dreame_vacuum.dreame.protocol.Timer") as mock_timer_cls,
    ):
        reason_code = _ReasonCode(True, 5)
        DreameVacuumDreameHomeCloudProtocol._on_client_disconnect(MagicMock(), proto, None, reason_code, None)

    mock_timer_cls.assert_called_once()


def test_on_client_disconnect_set_client_key_succeeds_is_noop(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._client_connected = True
    with patch.object(proto, "_set_client_key", return_value=True):
        reason_code = _ReasonCode(True, 5)
        DreameVacuumDreameHomeCloudProtocol._on_client_disconnect(MagicMock(), proto, None, reason_code, None)
    # no exception; state untouched by the disconnect handler itself


def test_on_client_disconnect_not_failure_is_noop(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    with patch.object(proto, "_set_client_key") as mock_set_key:
        reason_code = _ReasonCode(False, 0)
        DreameVacuumDreameHomeCloudProtocol._on_client_disconnect(MagicMock(), proto, None, reason_code, None)
    mock_set_key.assert_not_called()


def test_on_client_disconnect_not_connected_no_timer(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._client_connected = False
    with (
        patch.object(proto, "_set_client_key", return_value=False),
        patch("custom_components.dreame_vacuum.dreame.protocol.Timer") as mock_timer_cls,
    ):
        reason_code = _ReasonCode(True, 5)
        DreameVacuumDreameHomeCloudProtocol._on_client_disconnect(MagicMock(), proto, None, reason_code, None)

    mock_timer_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Étape 9 : _handle_device_info
# ---------------------------------------------------------------------------


def test_handle_device_info_parses_prop_with_stream_key(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    info = {
        "s8": "uid1",
        "did": "did1",
        "s35": "model1",
        "s9": "host1",
        "s10": json.dumps({"s11": "streamkey1"}),
    }
    proto._handle_device_info(info)
    assert proto._uid == "uid1"
    assert proto._did == "did1"
    assert proto._model == "model1"
    assert proto._host == "host1"
    assert proto._stream_key == "streamkey1"


def test_handle_device_info_empty_prop_skips_stream_key(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    info = {"s8": "uid2", "did": "did2", "s35": "model2", "s9": "host2", "s10": ""}
    proto._stream_key = None
    proto._handle_device_info(info)
    assert proto._stream_key is None


def test_handle_device_info_prop_without_stream_key_field(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    info = {"s8": "uid3", "did": "did3", "s35": "model3", "s9": "host3", "s10": json.dumps({"other": 1})}
    proto._stream_key = None
    proto._handle_device_info(info)
    assert proto._stream_key is None


# ---------------------------------------------------------------------------
# Étape 10 : connect() — MQTT client setup (paho mocked)
# ---------------------------------------------------------------------------


def test_connect_not_logged_in_returns_none(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._logged_in = False
    assert proto.connect() is None


def test_connect_logged_in_no_device_info_returns_none(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._logged_in = True
    with patch.object(proto, "get_device_info", return_value=None):
        assert proto.connect() is None


def test_connect_without_message_callback_sets_connected(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._logged_in = True
    info = {"ok": 1}
    with patch.object(proto, "get_device_info", return_value=info):
        result = proto.connect()
    assert result is info
    assert proto._connected is True
    assert proto._client is None


def test_connect_with_message_callback_builds_mqtt_client(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._logged_in = True
    proto._uid = "uid1"
    proto._did = "did1"
    proto._model = "model1"
    proto._country = "eu"
    proto._host = "mqtt.example.com:8883"
    info = {"ok": 1}
    mock_client_instance = MagicMock()
    fake_mod = MagicMock()
    fake_mod.Client = MagicMock(return_value=mock_client_instance)
    message_cb = MagicMock()
    connected_cb = MagicMock()

    with (
        patch.object(proto, "get_device_info", return_value=info),
        patch("custom_components.dreame_vacuum.dreame.protocol.paho.mqtt.client", fake_mod),
        patch.object(DreameVacuumDreameHomeCloudProtocol, "_check_mqtt_fingerprint") as mock_fp,
    ):
        result = proto.connect(message_callback=message_cb, connected_callback=connected_cb)

    assert result is info
    assert proto._message_callback is message_cb
    assert proto._connected_callback is connected_cb
    assert proto._client is mock_client_instance
    mock_client_instance.tls_set.assert_called_once()
    mock_client_instance.tls_insecure_set.assert_called_once_with(True)
    mock_client_instance.connect.assert_called_once_with("mqtt.example.com", port=8883, keepalive=60)
    mock_client_instance.loop_start.assert_called_once()
    mock_client_instance.disable_logger.assert_called_once()
    mock_fp.assert_called_once_with("mqtt.example.com", 8883)
    assert proto._connected is True

    proto._client_queue.put([])
    if proto._client_thread:
        proto._client_thread.join(timeout=2)


def test_connect_mqtt_setup_exception_is_logged_not_raised(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._logged_in = True
    proto._host = "mqtt.example.com:8883"
    info = {"ok": 1}
    mock_client_instance = MagicMock()
    mock_client_instance.tls_set.side_effect = RuntimeError("boom")
    fake_mod = MagicMock()
    fake_mod.Client = MagicMock(return_value=mock_client_instance)

    with (
        patch.object(proto, "get_device_info", return_value=info),
        patch("custom_components.dreame_vacuum.dreame.protocol.paho.mqtt.client", fake_mod),
        patch.object(DreameVacuumDreameHomeCloudProtocol, "_check_mqtt_fingerprint"),
    ):
        result = proto.connect(message_callback=MagicMock())

    assert result is info  # exception is logged, not raised
    proto._client_queue.put([])
    if proto._client_thread:
        proto._client_thread.join(timeout=2)


def test_connect_host_without_port_defaults_to_8883(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._logged_in = True
    proto._host = "mqtt.example.com"
    info = {"ok": 1}
    mock_client_instance = MagicMock()
    fake_mod = MagicMock()
    fake_mod.Client = MagicMock(return_value=mock_client_instance)

    with (
        patch.object(proto, "get_device_info", return_value=info),
        patch("custom_components.dreame_vacuum.dreame.protocol.paho.mqtt.client", fake_mod),
        patch.object(DreameVacuumDreameHomeCloudProtocol, "_check_mqtt_fingerprint"),
    ):
        proto.connect(message_callback=MagicMock())

    mock_client_instance.connect.assert_called_once_with("mqtt.example.com", port=8883, keepalive=60)
    proto._client_queue.put([])
    if proto._client_thread:
        proto._client_thread.join(timeout=2)


def test_connect_existing_client_not_connected_refreshes_key(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._logged_in = True
    proto._client = MagicMock()
    proto._client_connected = False
    info = {"ok": 1}
    with (
        patch.object(proto, "get_device_info", return_value=info),
        patch.object(proto, "_set_client_key") as mock_set_key,
    ):
        result = proto.connect(message_callback=MagicMock())

    assert result is info
    mock_set_key.assert_called_once()


# ---------------------------------------------------------------------------
# Étape 11 : login() — full behavioural coverage
# ---------------------------------------------------------------------------


def test_login_secondary_key_builds_refresh_token_payload(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._secondary_key = "existing-refresh"
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(200, json.dumps({"s18": "tok2", "s19": "rt2", "s20": 100}))

    result = proto.login()

    assert result is True
    sent_data = proto._session.post.call_args.kwargs["data"]
    assert sent_data == "s12s13existing-refresh"
    assert proto._key == "tok2"
    assert proto._secondary_key == "rt2"
    assert proto._connected is True
    proto._session.close_session.assert_called_once()


def test_login_username_password_builds_password_payload(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._secondary_key = None
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(200, json.dumps({"s18": "tok3", "s19": "rt3", "s20": 50}))

    proto.login()

    sent_data = proto._session.post.call_args.kwargs["data"]
    assert sent_data.startswith("s12s14user@example.coms15")
    assert sent_data.endswith("s16")


def test_login_country_cn_adds_extra_header() -> None:
    p = DreameVacuumDreameHomeCloudProtocol("u", "pw", country="cn")
    p._strings = [f"s{i}" for i in range(60)]
    p._session = MagicMock()
    p._session.post.return_value = _mock_response(200, json.dumps({"s18": "t", "s19": "r", "s20": 5}))

    p.login()

    headers = p._session.post.call_args.kwargs["headers"]
    assert "s48" in headers


def test_login_200_missing_key_field_leaves_logged_in_false(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(200, json.dumps({"other": 1}))

    result = proto.login()

    assert result is False
    assert proto._logged_in is False


def test_login_non_200_refresh_token_error_retries_login(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._secondary_key = "expired-refresh"
    proto._username = "user@example.com"
    proto._password = "secret"
    proto._session = MagicMock()
    fail_resp = _mock_response(400, json.dumps({"error_description": "invalid refresh token"}))
    success_resp = _mock_response(200, json.dumps({"s18": "newtok", "s19": "newrt", "s20": 100}))
    proto._session.post.side_effect = [fail_resp, success_resp]

    result = proto.login()

    assert result is True
    assert proto._secondary_key == "newrt"
    assert proto._session.post.call_count == 2


def test_login_non_200_invalid_json_sets_auth_failed(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._username = "u"
    proto._password = "p"
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(500, "not json")

    result = proto.login()

    assert result is False
    assert proto._auth_failed is True
    assert proto._logged_in is False


def test_login_non_200_no_credentials_sets_auth_failed(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    # secondary_key set so the initial payload assembly doesn't need username/password;
    # username/password are None so the non-200 handler skips the refresh-token JSON parse.
    proto._secondary_key = "some-refresh-key"
    proto._username = None
    proto._password = None
    proto._session = MagicMock()
    proto._session.post.return_value = _mock_response(401, "Unauthorized")

    result = proto.login()

    assert result is False
    assert proto._auth_failed is True


def test_login_timeout_sets_logged_in_false(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._session = MagicMock()
    proto._session.post.side_effect = HttpTimeoutError

    result = proto.login()

    assert result is False
    assert proto._logged_in is False


def test_login_http_request_error_sets_logged_in_false(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._session = MagicMock()
    proto._session.post.side_effect = HttpRequestError("boom")

    result = proto.login()

    assert result is False


def test_login_decompresses_strings_lazily_dreame_account() -> None:
    """A fresh instance (no pre-populated _strings) exercises the real decompression path."""
    p = DreameVacuumDreameHomeCloudProtocol("user@example.com", "secret", country="eu")
    p._session = MagicMock()
    p._session.post.return_value = _mock_response(
        200,
        json.dumps({"access_token": "tok", "refresh_token": "rt", "expires_in": 3600, "uid": "u1"}),
    )
    assert p._strings is None

    result = p.login()

    assert result is True
    assert p._strings is not None
    assert p._strings[0] == ".iot.dreame.tech"  # untouched for account_type == "dreame"
    assert p._key == "tok"
    assert p._secondary_key == "rt"


def test_login_decompresses_strings_adjusts_for_non_dreame_account() -> None:
    p = DreameVacuumDreameHomeCloudProtocol("user@example.com", "secret", account_type="mova", country="eu")
    p._session = MagicMock()
    p._session.post.return_value = _mock_response(
        200,
        json.dumps({"access_token": "t", "refresh_token": "r", "expires_in": 10}),
    )

    p.login()

    assert p._strings[0] == ".iot.mova-tech.com"
    assert p._strings[6] == "000002"


# ---------------------------------------------------------------------------
# Étape 12 : get_supported_devices / get_devices / get_device_info / get_info
# ---------------------------------------------------------------------------


def test_get_devices_returns_data_on_success(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    with patch.object(proto, "_api_call", return_value={"data": {"page": {"records": []}}, "code": 0}):
        result = proto.get_devices()
    assert result == {"page": {"records": []}}


def test_get_devices_returns_none_when_code_nonzero(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    with patch.object(proto, "_api_call", return_value={"data": {}, "code": 1}):
        assert proto.get_devices() is None


def test_get_devices_returns_none_when_no_response(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    with patch.object(proto, "_api_call", return_value=None):
        assert proto.get_devices() is None


def test_get_supported_devices_filters_by_model_and_collects_unsupported(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    records = [
        {
            "model": "dreame.vacuum.p2008",
            "customName": "My Vac",
            "deviceInfo": {"displayName": "D"},
            "localip": "1.2.3.4",
            "mac": "AA",
        },
        {
            "model": "dreame.vacuum.other",
            "customName": None,
            "deviceInfo": {"displayName": "Other"},
            "localip": "9.9.9.9",
            "mac": "BB",
        },
        {
            "model": "dreame.vacuum.unsupported999",
            "customName": None,
            "deviceInfo": {"displayName": "Unsup"},
            "localip": "192.0.2.10",
            "mac": "CC",
        },
    ]
    devices_payload = {"page": {"records": records}}
    with patch.object(proto, "get_devices", return_value=devices_payload):
        devices, unsupported = proto.get_supported_devices(["dreame.vacuum.p2008", "dreame.vacuum.other"])

    assert devices == {
        "My Vac - dreame.vacuum.p2008": records[0],
        "Other - dreame.vacuum.other": records[1],
    }
    assert unsupported == {"Unsup - dreame.vacuum.unsupported999": records[2]}


def test_get_supported_devices_host_match_breaks_early(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    records = [
        {
            "model": "dreame.vacuum.p2008",
            "customName": "My Vac",
            "deviceInfo": {"displayName": "D"},
            "localip": "1.2.3.4",
            "mac": "AA",
        },
        {
            "model": "dreame.vacuum.other",
            "customName": "Other Name",
            "deviceInfo": {"displayName": "Other"},
            "localip": "9.9.9.9",
            "mac": "BB",
        },
    ]
    devices_payload = {"page": {"records": records}}
    with patch.object(proto, "get_devices", return_value=devices_payload):
        devices, _unsupported = proto.get_supported_devices(
            ["dreame.vacuum.p2008", "dreame.vacuum.other"], host="9.9.9.9"
        )

    assert devices == {"Other Name - dreame.vacuum.other": records[1]}


def test_get_supported_devices_no_host_returns_all_matching(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    devices_payload = {
        "page": {
            "records": [
                {"model": "m1", "customName": "A", "deviceInfo": {"displayName": "A2"}},
                {"model": "m2", "customName": None, "deviceInfo": {"displayName": "B2"}},
            ]
        }
    }
    with patch.object(proto, "get_devices", return_value=devices_payload):
        devices, unsupported = proto.get_supported_devices(["m1", "m2"])

    assert len(devices) == 2
    assert unsupported == {}


def test_get_supported_devices_empty_response(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    with patch.object(proto, "get_devices", return_value=None):
        devices, unsupported = proto.get_supported_devices(["m1"])
    assert devices == {}
    assert unsupported == {}


def test_get_device_info_success_merges_otc_info(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._did = "d1"
    info_data = {"s8": "uid1", "did": "d1", "s35": "model1", "s9": "host1", "s10": ""}
    call_results = [
        {"code": 0, "data": info_data},
        {"code": 0, "data": {"s31": {"s32": {"extra": "x"}}}},
    ]
    with patch.object(proto, "_api_call", side_effect=call_results):
        result = proto.get_device_info()

    assert result == {"extra": "x", **info_data}
    assert proto._uid == "uid1"
    assert proto._did == "d1"


def test_get_device_info_first_call_fails_returns_none(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    with patch.object(proto, "_api_call", return_value=None):
        assert proto.get_device_info() is None


def test_get_device_info_otc_missing_falls_back_to_get_devices(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._did = "d1"
    info_data = {"s8": "uid1", "did": "d1", "s35": "model1", "s9": "host1", "s10": ""}
    call_results = [
        {"code": 0, "data": info_data},
        {"code": 0, "data": {"nope": True}},  # missing strings[31] key -> fallback path
    ]
    fallback_device = {"did": "d1", "s8": "uidX", "s35": "modelX", "s9": "hostX", "s10": ""}
    devices_payload = {"s34": {"s36": [fallback_device]}}
    with (
        patch.object(proto, "_api_call", side_effect=call_results),
        patch.object(proto, "get_devices", return_value=devices_payload),
    ):
        result = proto.get_device_info()

    assert result is fallback_device
    assert proto._uid == "uidX"


def test_get_device_info_otc_missing_and_no_devices_returns_none(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._did = "d1"
    info_data = {"s8": "uid1", "did": "d1", "s35": "model1", "s9": "host1", "s10": ""}
    call_results = [{"code": 0, "data": info_data}, {"code": 0, "data": {}}]
    with (
        patch.object(proto, "_api_call", side_effect=call_results),
        patch.object(proto, "get_devices", return_value=None),
    ):
        assert proto.get_device_info() is None


def test_get_device_info_otc_missing_devices_no_match_returns_none(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._did = "d1"
    info_data = {"s8": "uid1", "did": "d1", "s35": "model1", "s9": "host1", "s10": ""}
    call_results = [{"code": 0, "data": info_data}, {"code": 0, "data": {}}]
    devices_payload = {"s34": {"s36": [{"did": "other-device"}]}}
    with (
        patch.object(proto, "_api_call", side_effect=call_results),
        patch.object(proto, "get_devices", return_value=devices_payload),
    ):
        assert proto.get_device_info() is None


def test_get_device_info_otc_call_fails_returns_unmerged_data(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._did = "d1"
    info_data = {"s8": "uid1", "did": "d1", "s35": "model1", "s9": "host1", "s10": ""}
    call_results = [{"code": 0, "data": info_data}, {"code": 1, "data": {}}]
    with patch.object(proto, "_api_call", side_effect=call_results):
        result = proto.get_device_info()
    assert result == info_data


def test_get_info_returns_early_when_did_already_set(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._did = "existing-did"
    proto._host = "host1"
    result = proto.get_info("AA:BB")
    assert result == (" ", "host1")


def test_get_info_finds_device_by_mac(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._did = None
    devices_payload = {
        "s34": {"s36": [{"mac": "AA:BB", "s8": "uid1", "did": "d1", "s35": "model1", "s9": "host1", "s10": ""}]}
    }
    with patch.object(proto, "get_devices", return_value=devices_payload):
        result = proto.get_info("AA:BB")
    assert result == (" ", "host1")
    assert proto._did == "d1"


def test_get_info_no_match_returns_none_none(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._did = None
    devices_payload = {"s34": {"s36": [{"mac": "ZZ:ZZ"}]}}
    with patch.object(proto, "get_devices", return_value=devices_payload):
        result = proto.get_info("AA:BB")
    assert result == (None, None)


def test_get_info_no_devices_returns_none_none(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._did = None
    with patch.object(proto, "get_devices", return_value=None):
        result = proto.get_info("AA:BB")
    assert result == (None, None)


# ---------------------------------------------------------------------------
# Étape 13 : send_async / send() error branches
# ---------------------------------------------------------------------------


def test_send_async_builds_payload_and_wraps_callback(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._did = "d1"
    proto._host = "eu.example.com"
    proto._id = 0
    callback = MagicMock()
    with patch.object(proto, "_api_call_async") as mock_call_async:
        proto.send_async(callback, "get_prop", ["a"], retry_count=5)

    args = mock_call_async.call_args[0]
    wrapped_cb, url, payload, retry_count = args
    assert url == f"{proto._strings[37]}-eu/{proto._strings[27]}/{proto._strings[38]}"
    assert payload["did"] == "d1"
    assert payload["data"]["method"] == "get_prop"
    assert retry_count == 5

    wrapped_cb({"data": {"result": [1, 2]}})
    callback.assert_called_once_with([1, 2])

    callback.reset_mock()
    wrapped_cb(None)
    callback.assert_called_once_with(None)


def test_send_async_no_host_prefix(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._did = "d1"
    proto._host = None
    with patch.object(proto, "_api_call_async") as mock_call_async:
        proto.send_async(MagicMock(), "get_prop", [])
    url = mock_call_async.call_args[0][1]
    assert url == f"{proto._strings[37]}/{proto._strings[27]}/{proto._strings[38]}"


def test_send_returns_result_on_success(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._did = "d1"
    proto._host = None
    with patch.object(proto, "_api_call", return_value={"data": {"result": [1]}}):
        result = proto.send("get_properties", [])
    assert result == [1]


def test_send_code_80001_logs_warning_returns_none(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._did = "d1"
    with patch.object(proto, "_api_call", return_value={"success": False, "code": 80001, "msg": "offline"}):
        result = proto.send("get_properties", [])
    assert result is None


def test_send_other_error_code_logs_error_returns_none(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._did = "d1"
    with patch.object(proto, "_api_call", return_value={"success": False, "code": 500, "msg": "boom"}):
        result = proto.send("get_properties", [])
    assert result is None


def test_send_no_result_data_logs_debug_returns_none(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    proto._did = "d1"
    with patch.object(proto, "_api_call", return_value={"success": True, "other": 1}):
        result = proto.send("get_properties", [])
    assert result is None


def test_send_none_api_response_returns_none(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._did = "d1"
    with patch.object(proto, "_api_call", return_value=None):
        result = proto.send("get_properties", [])
    assert result is None


# ---------------------------------------------------------------------------
# Étape 14 : get_file / get_file_url / get_interim_file_url / get_properties
# ---------------------------------------------------------------------------


def test_get_file_success_first_try(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._session = MagicMock()
    proto._session.get.return_value = MagicMock(status=200, body=b"filedata")
    result = proto.get_file("http://example.com/f")
    assert result == b"filedata"
    assert proto._session.get.call_count == 1


def test_get_file_retries_then_succeeds(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._session = MagicMock()
    fail = MagicMock(status=404, body=b"")
    ok = MagicMock(status=200, body=b"data2")
    proto._session.get.side_effect = [fail, ok]
    result = proto.get_file("http://example.com/f", retry_count=2)
    assert result == b"data2"
    assert proto._session.get.call_count == 2


def test_get_file_all_retries_fail_returns_none(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._session = MagicMock()
    proto._session.get.return_value = MagicMock(status=500, body=b"")
    result = proto.get_file("http://example.com/f", retry_count=1)
    assert result is None
    assert proto._session.get.call_count == 2


def test_get_file_http_request_error_returns_none(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._session = MagicMock()
    proto._session.get.side_effect = HttpRequestError("boom")
    result = proto.get_file("http://example.com/f", retry_count=0)
    assert result is None


def test_get_file_retry_count_negative_normalized(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._session = MagicMock()
    proto._session.get.return_value = MagicMock(status=200, body=b"ok")
    result = proto.get_file("http://example.com/f", retry_count=-5)
    assert result == b"ok"
    assert proto._session.get.call_count == 1


def test_get_file_url_success(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._did = "d1"
    proto._uid = "u1"
    proto._model = "m1"
    proto._country = "eu"
    with patch.object(proto, "_api_call", return_value={"data": "http://file/url"}):
        result = proto.get_file_url("/obj/name")
    assert result == "http://file/url"


def test_get_file_url_none_response(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    with patch.object(proto, "_api_call", return_value=None):
        assert proto.get_file_url("/x") is None


def test_get_file_url_missing_data_key(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    with patch.object(proto, "_api_call", return_value={"other": 1}):
        assert proto.get_file_url("/x") is None


def test_get_interim_file_url_success(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    with patch.object(proto, "_api_call", return_value={"data": "http://interim/url"}):
        assert proto.get_interim_file_url("obj") == "http://interim/url"


def test_get_interim_file_url_none(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    with patch.object(proto, "_api_call", return_value=None):
        assert proto.get_interim_file_url("obj") is None


def test_get_properties_success(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._did = "d1"
    with patch.object(proto, "_api_call", return_value={"data": {"p": 1}}) as mock_call:
        result = proto.get_properties(["k1", "k2"])
    assert result == {"p": 1}
    mock_call.assert_called_once_with(
        f"{proto._strings[23]}/{proto._strings[25]}/{proto._strings[41]}",
        {"did": "d1", "keys": ["k1", "k2"]},
    )


def test_get_properties_none(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    with patch.object(proto, "_api_call", return_value=None):
        assert proto.get_properties(["k"]) is None


def test_get_device_property_calls_get_device_data(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    with patch.object(proto, "get_device_data", return_value=[1]) as mock_gdd:
        result = proto.get_device_property("1.2", limit=3)
    mock_gdd.assert_called_once_with("1.2", "prop", 3, 0, 9999999999)
    assert result == [1]


def test_get_device_event_calls_get_device_data(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    with patch.object(proto, "get_device_data", return_value=[2]) as mock_gdd:
        proto.get_device_event("1.3")
    mock_gdd.assert_called_once_with("1.3", "event", 1, 0, 9999999999)


def test_get_device_data_prop_type(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._uid = "u1"
    proto._did = "d1"
    proto._country = "eu"
    with patch.object(proto, "_api_call", return_value={"data": {"s33": [{"v": 1}]}}) as mock_call:
        result = proto.get_device_data("1.2", "prop", limit=5, time_start=100)
    assert result == [{"v": 1}]
    params = mock_call.call_args[0][1]
    assert params["piid"] == "2"
    assert params["from"] == 100


def test_get_device_data_event_type(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._uid = "u"
    proto._did = "d"
    with patch.object(proto, "_api_call", return_value={"data": {"s33": []}}) as mock_call:
        proto.get_device_data("5.6", "event")
    params = mock_call.call_args[0][1]
    assert params["eiid"] == "6"


def test_get_device_data_action_type(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._uid = "u"
    proto._did = "d"
    with patch.object(proto, "_api_call", return_value={"data": {"s33": []}}) as mock_call:
        proto.get_device_data("5.6", "action")
    params = mock_call.call_args[0][1]
    assert params["aiid"] == "6"


def test_get_device_data_default_time_start(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._uid = "u"
    proto._did = "d"
    with patch.object(proto, "_api_call", return_value={"data": {"s33": []}}) as mock_call:
        proto.get_device_data("1.2", "prop", time_start=0)
    params = mock_call.call_args[0][1]
    assert params["from"] == 1687019188


def test_get_device_data_missing_key_returns_none(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    with patch.object(proto, "_api_call", return_value={"data": {}}):
        assert proto.get_device_data("1.2", "prop") is None


def test_get_device_data_none_response_returns_none(
    proto: DreameVacuumDreameHomeCloudProtocol,
) -> None:
    with patch.object(proto, "_api_call", return_value=None):
        assert proto.get_device_data("1.2", "prop") is None


def test_get_batch_device_datas_success(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._did = "d1"
    with patch.object(proto, "_api_call", return_value={"data": {"x": 1}}):
        assert proto.get_batch_device_datas(["p1"]) == {"x": 1}


def test_get_batch_device_datas_none(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    with patch.object(proto, "_api_call", return_value=None):
        assert proto.get_batch_device_datas(["p1"]) is None


def test_set_batch_device_datas_success(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    proto._did = "d1"
    with patch.object(proto, "_api_call", return_value={"result": "ok"}):
        assert proto.set_batch_device_datas(["p1"]) == "ok"


def test_set_batch_device_datas_missing_result(proto: DreameVacuumDreameHomeCloudProtocol) -> None:
    with patch.object(proto, "_api_call", return_value={"other": 1}):
        assert proto.set_batch_device_datas(["p1"]) is None


# ---------------------------------------------------------------------------
# redact_url: pre-signed cloud URLs must never reach the logs
# ---------------------------------------------------------------------------

SIGNED_URL = "https://oss.example/map.b64?Signature=SECRETSIG&Expires=1"


def test_redact_url_strips_query() -> None:
    """The query string (the download credential) is dropped, path kept."""
    assert redact_url("https://h/p?sig=abc") == "https://h/p?<redacted>"
    assert redact_url("https://h/p") == "https://h/p"
    assert redact_url(None) == "None"


def test_get_file_failure_log_redacts_signature_dreame_home(
    proto: DreameVacuumDreameHomeCloudProtocol,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DreameHome get_file() failure warning must not leak the signed query string."""
    proto._session = MagicMock()
    proto._session.get.side_effect = HttpRequestError("boom")

    with caplog.at_level(logging.WARNING):
        result = proto.get_file(SIGNED_URL, retry_count=0)

    assert result is None
    assert "SECRETSIG" not in caplog.text
    assert "oss.example" in caplog.text


def test_get_file_failure_log_redacts_signature_mihome(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """MiHome get_file() failure warning must not leak the signed query string."""
    p = DreameVacuumMiHomeCloudProtocol("user@example.com", "secret", "de")
    p._session = MagicMock()
    p._session.get.side_effect = HttpRequestError("boom")

    with caplog.at_level(logging.WARNING):
        result = p.get_file(SIGNED_URL, retry_count=0)

    assert result is None
    assert "SECRETSIG" not in caplog.text
    assert "oss.example" in caplog.text


def test_get_file_url_debug_log_redacts_signature(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """get_file_url() logs a redacted URL but still returns the raw signed one."""
    p = DreameVacuumMiHomeCloudProtocol("user@example.com", "secret", "de")

    with (
        patch.object(p, "_api_call", return_value={"result": {"url": SIGNED_URL}}),
        caplog.at_level(logging.DEBUG),
    ):
        result = p.get_file_url("obj")

    # The caller needs the real pre-signed URL to download the file.
    assert result == SIGNED_URL
    assert "SECRETSIG" not in caplog.text
    assert "oss.example" in caplog.text


def test_get_interim_file_url_debug_log_redacts_signature(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """get_interim_file_url() logs a redacted URL but still returns the raw signed one."""
    p = DreameVacuumMiHomeCloudProtocol("user@example.com", "secret", "de")

    with (
        patch.object(p, "_api_call", return_value={"result": {"url": SIGNED_URL}}),
        caplog.at_level(logging.DEBUG),
    ):
        result = p.get_interim_file_url("obj")

    assert result == SIGNED_URL
    assert "SECRETSIG" not in caplog.text
    assert "oss.example" in caplog.text


def test_get_file_url_error_response_still_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without a URL in the response, the (URL-free) api_response is still logged."""
    p = DreameVacuumMiHomeCloudProtocol("user@example.com", "secret", "de")

    with (
        patch.object(p, "_api_call", return_value={"code": -1}),
        caplog.at_level(logging.DEBUG),
    ):
        result = p.get_file_url("obj")

    assert result is None
    assert "'code': -1" in caplog.text
