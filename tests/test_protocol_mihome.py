"""Characterization tests for MiHome cloud and MiIO device protocol classes.

These tests lock down the OBSERVED behaviour of DreameVacuumMiHomeCloudProtocol,
DreameVacuumDeviceProtocol, and the DreameVacuumProtocol aggregate without
modifying any production code.  Divergences from the plan are noted inline.
"""

from __future__ import annotations

import base64
import json
import threading
from unittest.mock import MagicMock, patch

from Crypto.Cipher import ARC4
import pytest

from custom_components.dreame_vacuum.dreame.exceptions import (
    DeviceException,
    RateLimitError,
)
from custom_components.dreame_vacuum.dreame.http_client import (
    HttpConnectionError,
    HttpRequestError,
    HttpTimeoutError,
)
from custom_components.dreame_vacuum.dreame.protocol import (
    DreameVacuumDeviceProtocol,
    DreameVacuumDreameHomeCloudProtocol,
    DreameVacuumMiHomeCloudProtocol,
    DreameVacuumProtocol,
)
from custom_components.dreame_vacuum.dreame.resilience import CircuitState

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mihome() -> DreameVacuumMiHomeCloudProtocol:
    p = DreameVacuumMiHomeCloudProtocol("user@example.com", "secret", "de")
    p._ssecurity = "c2VjdXJpdHk="  # base64("security")
    p._service_token = "service-token"
    p._userId = "12345"
    return p


@pytest.fixture
def device_proto() -> DreameVacuumDeviceProtocol:
    return DreameVacuumDeviceProtocol("192.168.1.100", "a" * 32)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _mock_response(status: int, text: str, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.text = text
    resp.headers = headers or {}
    return resp


def _make_encrypted_response(ssecurity: str, nonce: str, payload: dict) -> str:
    """Return a base64 string that decrypt_rc4(signed_nonce(nonce), text) yields payload JSON."""
    import hashlib

    hash_object = hashlib.sha256(base64.b64decode(ssecurity) + base64.b64decode(nonce))
    signed_nonce = base64.b64encode(hash_object.digest()).decode("utf-8")
    r = ARC4.new(base64.b64decode(signed_nonce))
    r.encrypt(bytes(1024))
    return base64.b64encode(r.encrypt(json.dumps(payload).encode())).decode()


# ---------------------------------------------------------------------------
# Étape 2 : DeviceProtocol
# ---------------------------------------------------------------------------


def test_device_proto_constructor_sets_token(
    device_proto: DreameVacuumDeviceProtocol,
) -> None:
    """Constructor calls set_credentials: token stored as bytes and port set."""
    assert device_proto.token == bytes.fromhex("a" * 32)
    assert device_proto.port == 54321


def test_device_proto_empty_token_becomes_zero_bytes() -> None:
    """Empty string token is normalised to 32 zero bytes."""
    p = DreameVacuumDeviceProtocol("192.168.1.100", "")
    assert p.token == bytes.fromhex("0" * 32)


def test_device_proto_none_token_becomes_zero_bytes() -> None:
    """None token normalisation: set_credentials with None falls back to zero bytes.

    NOTE: DreameVacuumDeviceProtocol.__init__ calls set_credentials(ip, token)
    immediately after MiIOProtocol.__init__.  We reach the None branch by calling
    set_credentials directly on an already-initialised instance after clearing ip/token
    so the ``self.ip != ip or self.token != token`` guard is satisfied.
    """
    p = DreameVacuumDeviceProtocol("192.168.1.100", "a" * 32)
    # Force ip to differ so the guard condition passes
    p.ip = None
    p.set_credentials("192.168.1.100", None)  # type: ignore[arg-type]
    assert p.token == bytes.fromhex("0" * 32)


def test_device_proto_ip_change_resets_discovered(
    device_proto: DreameVacuumDeviceProtocol,
) -> None:
    """Changing IP causes _discovered to reset to False."""
    device_proto._discovered = True
    device_proto.set_credentials("192.168.1.200", "a" * 32)
    assert device_proto._discovered is False


def test_device_proto_same_credentials_keeps_discovered(
    device_proto: DreameVacuumDeviceProtocol,
) -> None:
    """Calling set_credentials with the same ip+token keeps _discovered.

    The guard compares the stored token (bytes) against the hex-decoded
    incoming token, so logically-equal credentials are a no-op.
    """
    device_proto._discovered = True
    device_proto.set_credentials("192.168.1.100", "a" * 32)
    assert device_proto._discovered is True


def test_device_proto_connected_reflects_discovered(
    device_proto: DreameVacuumDeviceProtocol,
) -> None:
    """connected property mirrors _discovered."""
    device_proto._discovered = True
    assert device_proto.connected is True
    device_proto._discovered = False
    assert device_proto.connected is False


def test_device_proto_disconnect_clears_discovered(
    device_proto: DreameVacuumDeviceProtocol,
) -> None:
    """disconnect() sets _discovered to False without raising when no thread."""
    device_proto._discovered = True
    device_proto.disconnect()
    assert device_proto._discovered is False


# ---------------------------------------------------------------------------
# Étape 3 : MiHome — constructor and pure helpers
# ---------------------------------------------------------------------------


def test_mihome_constructor_no_network(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    """Constructor completes without network calls."""
    assert mihome._username == "user@example.com"
    assert mihome._password == "secret"
    assert mihome._country == "de"
    assert mihome._logged_in is False
    assert mihome._auth_failed is False


def test_mihome_auth_key_four_parts_parsed() -> None:
    """auth_key with 4 space-separated parts assigns all 4 attributes."""
    ak = "svc-token stoken123 uid-999 client-abc"
    p = DreameVacuumMiHomeCloudProtocol("u", "p", "de", auth_key=ak)
    assert p._service_token == "svc-token"
    assert p._ssecurity == "stoken123"
    assert p._userId == "uid-999"
    assert p._client_id == "client-abc"


def test_mihome_auth_key_three_parts_ignored() -> None:
    """auth_key with fewer than 4 parts leaves cloud attrs as None."""
    ak = "part1 part2 part3"
    p = DreameVacuumMiHomeCloudProtocol("u", "p", "de", auth_key=ak)
    assert p._service_token is None
    assert p._ssecurity is None
    assert p._userId is None


def test_mihome_generate_client_id_length_and_charset() -> None:
    """generate_client_id() returns exactly 16 lowercase ASCII letters."""
    cid = DreameVacuumMiHomeCloudProtocol.generate_client_id()
    assert len(cid) == 16
    assert cid.isalpha()
    assert cid.islower()


def test_mihome_generate_nonce_base64_12_bytes() -> None:
    """generate_nonce() returns base64 that decodes to exactly 12 bytes."""
    nonce = DreameVacuumMiHomeCloudProtocol.generate_nonce()
    decoded = base64.b64decode(nonce)
    assert len(decoded) == 12


def test_mihome_encrypt_decrypt_rc4_roundtrip() -> None:
    """decrypt_rc4(pwd, encrypt_rc4(pwd, payload)) recovers the original payload."""
    pwd = "c2VjdXJpdHk="  # base64('security')
    payload = "hello world"
    encrypted = DreameVacuumMiHomeCloudProtocol.encrypt_rc4(pwd, payload)
    decrypted = DreameVacuumMiHomeCloudProtocol.decrypt_rc4(pwd, encrypted)
    assert decrypted == b"hello world"


def test_mihome_encrypt_rc4_drops_first_1024_bytes() -> None:
    """RC4 keystream skips first 1024 bytes (RC4-drop1024 variant)."""
    # Two separate ARC4 instances with the same key should give same result
    # because both skip the first 1024 bytes.
    pwd = "c2VjdXJpdHk="
    payload = "test payload"
    r1 = ARC4.new(base64.b64decode(pwd))
    r1.encrypt(bytes(1024))
    manual = base64.b64encode(r1.encrypt(payload.encode())).decode()
    assert DreameVacuumMiHomeCloudProtocol.encrypt_rc4(pwd, payload) == manual


def test_mihome_generate_signature_deterministic() -> None:
    """generate_signature with fixed inputs returns a stable value."""
    url = "https://de.api.io.mi.com/app/v2/device/stuff"
    signed_nonce = "tNfoaeifqEL840oNVDy1wWxcSezI23TbtXCTt8FH1Rs="
    nonce = "bm9uY2U="  # base64('nonce')
    params = {"data": "testdata"}
    result = DreameVacuumMiHomeCloudProtocol.generate_signature(url, signed_nonce, nonce, params)
    assert result == "rUvM5mf+PJ3s7wCocHeSFtCkDB6CjjcoPjDxrOmW350="


def test_mihome_signed_nonce_deterministic(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """signed_nonce with a fixed nonce returns a stable value."""
    # ssecurity = 'c2VjdXJpdHk=' (base64 of 'security'), nonce = base64('nonce')
    nonce = "bm9uY2U="
    result = mihome.signed_nonce(nonce)
    assert result == "tNfoaeifqEL840oNVDy1wWxcSezI23TbtXCTt8FH1Rs="


def test_mihome_to_json_strips_prefix() -> None:
    """to_json strips the '&&&START&&&' anti-hijacking prefix."""
    raw = '&&&START&&&{"ok": 1}'
    assert DreameVacuumMiHomeCloudProtocol.to_json(raw) == {"ok": 1}


def test_mihome_to_json_plain_json() -> None:
    """to_json works on plain JSON (no prefix)."""
    assert DreameVacuumMiHomeCloudProtocol.to_json('{"ok": 1}') == {"ok": 1}


def test_mihome_get_api_url_cn() -> None:
    """get_api_url() for country 'cn' omits the country prefix."""
    p = DreameVacuumMiHomeCloudProtocol("u", "p", "cn")
    assert p.get_api_url() == "https://api.io.mi.com/app"


def test_mihome_get_api_url_de() -> None:
    """get_api_url() for country 'de' prefixes the subdomain."""
    p = DreameVacuumMiHomeCloudProtocol("u", "p", "de")
    assert p.get_api_url() == "https://de.api.io.mi.com/app"


def test_mihome_object_name() -> None:
    """object_name property returns '<uid>/<did>/0'."""
    p = DreameVacuumMiHomeCloudProtocol("u", "p", "de")
    p._uid = "uid123"
    p._did = "did456"
    assert p.object_name == "uid123/did456/0"


def test_mihome_check_login_code_2_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    assert mihome.check_login({"code": 2, "message": "ok"}) is False


def test_mihome_check_login_code_3_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    assert mihome.check_login({"code": 3, "message": "ok"}) is False


def test_mihome_check_login_auth_err_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    assert mihome.check_login({"code": 0, "message": "auth err detected"}) is False


def test_mihome_check_login_invalid_signature_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    assert mihome.check_login({"code": 0, "message": "invalid signature"}) is False


def test_mihome_check_login_servicetoken_expired_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    assert mihome.check_login({"code": 0, "message": "SERVICETOKEN_EXPIRED"}) is False


def test_mihome_check_login_ok_true(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    assert mihome.check_login({"code": 0, "message": "ok"}) is True


def test_mihome_check_login_none_calls_request(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """check_login(None) calls self.request() and returns False when it returns None."""
    with patch.object(mihome, "request", return_value=None) as mock_req:
        result = mihome.check_login(None)
    mock_req.assert_called_once()
    assert result is False


def test_mihome_pure_properties(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    """Cover simple pure properties."""
    assert mihome.dreame_cloud is False
    assert mihome.logged_in is False
    assert mihome.auth_failed is False
    assert mihome.connected is False
    mihome._did = "dev789"
    assert mihome.device_id == "dev789"


# ---------------------------------------------------------------------------
# Étape 4 : MiHome — request() with mocked session
# ---------------------------------------------------------------------------


def test_mihome_request_200_valid_json(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """HTTP 200 with properly encrypted response returns parsed dict and _connected=True."""
    fixed_nonce = "dGVzdA=="  # base64('test')
    encrypted_text = _make_encrypted_response(mihome._ssecurity, fixed_nonce, {"result": 42})
    mihome._session = MagicMock()
    mihome._session.post.return_value = _mock_response(200, encrypted_text)

    with patch.object(DreameVacuumMiHomeCloudProtocol, "generate_nonce", return_value=fixed_nonce):
        result = mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"})

    assert result == {"result": 42}
    assert mihome._connected is True


def test_mihome_request_200_invalid_json_returns_none(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """HTTP 200 but decrypt_rc4 yields non-JSON → returns None."""
    mihome._session = MagicMock()
    mihome._session.post.return_value = _mock_response(200, "notvalidb64==")

    with patch.object(
        DreameVacuumMiHomeCloudProtocol,
        "decrypt_rc4",
        return_value=b"not json",
    ):
        result = mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"})

    assert result is None


def test_mihome_request_circuit_breaker_open_skips_post(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """When circuit breaker is OPEN, request() returns None without calling post."""
    for _ in range(mihome._circuit_breaker.failure_threshold):
        mihome._circuit_breaker.record_failure()

    assert mihome._circuit_breaker.state is CircuitState.OPEN

    mihome._session = MagicMock()
    result = mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"})

    assert result is None
    mihome._session.post.assert_not_called()


def test_mihome_request_timeout_retries(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """Timeout retries: post called retry_count+1 times, sleep called retry_count times."""
    mihome._session = MagicMock()
    mihome._session.post.side_effect = HttpTimeoutError

    with patch("custom_components.dreame_vacuum.dreame.protocol.sleep") as mock_sleep:
        result = mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"}, retry_count=2)

    assert result is None
    assert mihome._session.post.call_count == 3
    assert mock_sleep.call_count == 2


def test_mihome_request_429_raises_rate_limit_error(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """HTTP 429 raises RateLimitError with retry_after from header."""
    mihome._session = MagicMock()
    mihome._session.post.return_value = _mock_response(429, "", headers={"Retry-After": "45"})

    with pytest.raises(RateLimitError) as exc_info:
        mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"})

    assert exc_info.value.retry_after == 45.0


def test_mihome_request_429_default_retry_after(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """HTTP 429 without Retry-After header defaults to 60.0."""
    mihome._session = MagicMock()
    mihome._session.post.return_value = _mock_response(429, "", headers={})

    with pytest.raises(RateLimitError) as exc_info:
        mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"})

    assert exc_info.value.retry_after == 60.0


def test_mihome_request_non_200_non_429_records_failure(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """Any non-200/non-429 status records a circuit-breaker failure and returns None.

    Unlike DreameHome, MiHome has no 401-relogin mechanism.
    """
    mihome._session = MagicMock()
    mihome._session.post.return_value = _mock_response(500, "error")

    result = mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"})

    assert result is None
    assert mihome._circuit_breaker._failure_count >= 1


def test_mihome_request_connection_error_retries(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """ConnectionError retries same as Timeout."""
    mihome._session = MagicMock()
    mihome._session.post.side_effect = HttpConnectionError("refused")

    with patch("custom_components.dreame_vacuum.dreame.protocol.sleep") as mock_sleep:
        result = mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"}, retry_count=2)

    assert result is None
    assert mihome._session.post.call_count == 3
    assert mock_sleep.call_count == 2


def test_mihome_request_cookies_include_service_token(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """request() sends serviceToken and yetAnotherServiceToken cookies."""
    fixed_nonce = "dGVzdA=="
    encrypted_text = _make_encrypted_response(mihome._ssecurity, fixed_nonce, {"ok": 1})
    mihome._session = MagicMock()
    mihome._session.post.return_value = _mock_response(200, encrypted_text)

    with patch.object(DreameVacuumMiHomeCloudProtocol, "generate_nonce", return_value=fixed_nonce):
        mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"})

    call_kwargs = mihome._session.post.call_args
    cookies = call_kwargs[1]["cookies"]
    assert cookies["serviceToken"] == "service-token"
    assert cookies["yetAnotherServiceToken"] == "service-token"
    assert cookies["userId"] == "12345"


# ---------------------------------------------------------------------------
# Étape 5 : Aggregate DreameVacuumProtocol
# ---------------------------------------------------------------------------


def test_aggregate_mi_account_creates_mihome_cloud() -> None:
    """account_type='mi' with credentials creates a MiHome cloud instance."""
    p = DreameVacuumProtocol(
        ip="192.168.1.100",
        token="a" * 32,
        username="u@example.com",
        password="secret",
        country="de",
        account_type="mi",
    )
    assert isinstance(p.cloud, DreameVacuumMiHomeCloudProtocol)
    assert isinstance(p.device, DreameVacuumDeviceProtocol)


def test_aggregate_dreame_account_creates_dreamehome_cloud() -> None:
    """account_type='dreame' with credentials creates a DreameHome cloud instance."""
    p = DreameVacuumProtocol(
        ip="192.168.1.100",
        token="a" * 32,
        username="u@example.com",
        password="secret",
        country="eu",
        account_type="dreame",
        prefer_cloud=True,
    )
    assert isinstance(p.cloud, DreameVacuumDreameHomeCloudProtocol)


def test_aggregate_no_ip_token_sets_prefer_cloud_and_no_device() -> None:
    """Without ip+token, device is None and prefer_cloud is forced True."""
    p = DreameVacuumProtocol(
        username="u@example.com",
        password="secret",
        country="de",
        account_type="mi",
    )
    assert p.device is None
    assert p.prefer_cloud is True


def test_aggregate_connected_false_by_default() -> None:
    """connected returns False when device is not discovered."""
    p = DreameVacuumProtocol(
        ip="192.168.1.100",
        token="a" * 32,
        username="u@example.com",
        password="secret",
        country="de",
        account_type="mi",
        prefer_cloud=False,
    )
    assert p.connected is False


def test_aggregate_dreame_cloud_property_mi_account() -> None:
    """dreame_cloud is False for a mi account."""
    p = DreameVacuumProtocol(
        ip="192.168.1.100",
        token="a" * 32,
        username="u@example.com",
        password="secret",
        country="de",
        account_type="mi",
    )
    assert p.dreame_cloud is False


def test_aggregate_dreame_cloud_property_dreame_account() -> None:
    """dreame_cloud is True for a dreame account."""
    p = DreameVacuumProtocol(
        ip="192.168.1.100",
        token="a" * 32,
        username="u@example.com",
        password="secret",
        country="eu",
        account_type="dreame",
        prefer_cloud=True,
    )
    assert p.dreame_cloud is True


def test_aggregate_set_credentials_updates_existing_device() -> None:
    """set_credentials propagates new ip/token to existing device."""
    p = DreameVacuumProtocol(
        ip="192.168.1.100",
        token="a" * 32,
        username="u@example.com",
        password="secret",
        country="de",
        account_type="mi",
    )
    p.set_credentials("192.168.1.200", "b" * 32)
    assert p.device is not None
    assert p.device.ip == "192.168.1.200"


def test_aggregate_set_credentials_creates_device_when_none() -> None:
    """set_credentials creates a DeviceProtocol when device is None."""
    p = DreameVacuumProtocol(
        username="u@example.com",
        password="secret",
        country="de",
        account_type="mi",
    )
    assert p.device is None
    p.set_credentials("192.168.1.100", "a" * 32)
    assert isinstance(p.device, DreameVacuumDeviceProtocol)


# ---------------------------------------------------------------------------
# Extra coverage: MiHome auth_key property, disconnect, request branches
# ---------------------------------------------------------------------------


def test_mihome_auth_key_property_returns_constructor_value() -> None:
    """auth_key property (line 959) returns the value passed at construction."""
    p = DreameVacuumMiHomeCloudProtocol("u", "p", "de", auth_key="my-key value1 uid1 cid1")
    assert p.auth_key == "my-key value1 uid1 cid1"


def test_mihome_auth_key_property_none_by_default() -> None:
    """auth_key property returns None when not provided."""
    p = DreameVacuumMiHomeCloudProtocol("u", "p", "de")
    assert p.auth_key is None


def test_mihome_disconnect_resets_state(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    """disconnect() closes session, resets flags, and does not raise (no thread)."""
    mihome._logged_in = True
    mihome._connected = True
    mihome._auth_failed = True
    mihome._thread = None
    mihome.disconnect()
    assert mihome._connected is False
    assert mihome._logged_in is False
    assert mihome._auth_failed is False


def test_mihome_request_retry_count_none_normalized(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """retry_count=None is normalised to 0 → single attempt (covers line 1412)."""
    mihome._session = MagicMock()
    fixed_nonce = "dGVzdA=="
    encrypted_text = _make_encrypted_response(mihome._ssecurity, fixed_nonce, {"ok": 1})
    mihome._session.post.return_value = _mock_response(200, encrypted_text)

    with patch.object(DreameVacuumMiHomeCloudProtocol, "generate_nonce", return_value=fixed_nonce):
        result = mihome.request(
            "https://de.api.io.mi.com/app/v2/test",
            {"data": "x"},
            retry_count=None,  # type: ignore[arg-type]
        )

    assert result == {"ok": 1}
    assert mihome._session.post.call_count == 1


def test_mihome_request_timeout_with_connected_logs_warning(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """Timeout while _connected=True covers the warning branch (line 1445)."""
    mihome._session = MagicMock()
    mihome._session.post.side_effect = HttpTimeoutError
    mihome._connected = True

    with patch("custom_components.dreame_vacuum.dreame.protocol.sleep"):
        result = mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"}, retry_count=1)

    assert result is None
    assert mihome._session.post.call_count == 2


def test_mihome_request_connection_error_with_connected_logs_warning(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """ConnectionError while _connected=True covers the warning branch (line 1452)."""
    mihome._session = MagicMock()
    mihome._session.post.side_effect = HttpConnectionError("refused")
    mihome._connected = True

    with patch("custom_components.dreame_vacuum.dreame.protocol.sleep"):
        result = mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"}, retry_count=1)

    assert result is None


def test_mihome_request_generic_exception_with_connected(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """Generic exception while _connected=True covers lines 1455-1459."""
    mihome._session = MagicMock()
    mihome._session.post.side_effect = RuntimeError("boom")
    mihome._connected = True

    result = mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"}, retry_count=1)

    assert result is None


def test_mihome_request_200_decrypt_returns_empty_bytes(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    """HTTP 200 but decrypt_rc4 returns empty bytes → branch line 1472 returns None."""
    mihome._session = MagicMock()
    mihome._session.post.return_value = _mock_response(200, "anythingbase64")

    with patch.object(DreameVacuumMiHomeCloudProtocol, "decrypt_rc4", return_value=b""):
        result = mihome.request("https://de.api.io.mi.com/app/v2/test", {"data": "x"})

    assert result is None


# ---------------------------------------------------------------------------
# DreameVacuumDeviceProtocol — _api_task / send_async / disconnect w/ thread
# ---------------------------------------------------------------------------


def test_device_proto_api_task_processes_queue_and_thread_starts(
    device_proto: DreameVacuumDeviceProtocol,
) -> None:
    device_proto.send = MagicMock(return_value={"ok": 1})
    callback = MagicMock()

    device_proto.send_async(callback, "get_prop", ["x"], retry_count=3)
    device_proto._queue.join()

    callback.assert_called_once_with({"ok": 1})
    device_proto.send.assert_called_once_with("get_prop", ["x"], 3)
    assert device_proto._thread is not None

    device_proto._queue.put([])
    device_proto._thread.join(timeout=2)


def test_device_proto_disconnect_signals_active_thread(
    device_proto: DreameVacuumDeviceProtocol,
) -> None:
    device_proto.send = MagicMock(return_value=None)
    device_proto.send_async(MagicMock(), "get_prop", [])
    device_proto._queue.join()

    device_proto.disconnect()

    assert device_proto._discovered is False
    device_proto._thread.join(timeout=2)


# ---------------------------------------------------------------------------
# MiHome — constructor exception-guarded branches
# ---------------------------------------------------------------------------


def test_mihome_locale_error_defaults_to_none() -> None:
    with patch(
        "custom_components.dreame_vacuum.dreame.protocol.locale.getlocale",
        side_effect=ValueError("boom"),
    ):
        p = DreameVacuumMiHomeCloudProtocol("u", "p", "de")
    assert p._locale is None


def test_mihome_timezone_error_defaults_to_gmt() -> None:
    with patch(
        "custom_components.dreame_vacuum.dreame.protocol.time.localtime",
        side_effect=OSError("boom"),
    ):
        p = DreameVacuumMiHomeCloudProtocol("u", "p", "de")
    assert p._timezone == "GMT+00:00"


# ---------------------------------------------------------------------------
# MiHome — _api_task / _api_call_async / _api_call
# ---------------------------------------------------------------------------


def test_mihome_api_task_success_calls_callback(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._api_call = MagicMock(return_value={"code": 0, "message": "ok"})
    callback = MagicMock()
    with patch("custom_components.dreame_vacuum.dreame.protocol.sleep") as mock_sleep:
        t = threading.Thread(target=mihome._api_task)
        t.start()
        mihome._queue.put((callback, "url", {}, 1))
        mihome._queue.join()
        mihome._queue.put([])
        t.join(timeout=2)

    callback.assert_called_once_with({"code": 0, "message": "ok"})
    mock_sleep.assert_called_once_with(0.1)
    assert mihome._thread is None


def test_mihome_api_task_check_login_false_clears_response(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._api_call = MagicMock(return_value={"code": 2, "message": "bad"})
    callback = MagicMock()
    with patch("custom_components.dreame_vacuum.dreame.protocol.sleep"):
        t = threading.Thread(target=mihome._api_task)
        t.start()
        mihome._queue.put((callback, "url", {}, 1))
        mihome._queue.join()
        mihome._queue.put([])
        t.join(timeout=2)

    callback.assert_called_once_with(None)
    assert mihome._logged_in is False
    assert mihome._auth_failed is True


def test_mihome_api_call_async_starts_thread(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._api_call = MagicMock(return_value={"code": 0})
    cb = MagicMock()
    mihome._api_call_async(cb, "url", {"a": 1}, 2)
    assert mihome._thread is not None
    mihome._queue.join()

    cb.assert_called_once()
    mihome._queue.put([])
    mihome._thread.join(timeout=2)


def test_mihome_api_call_wraps_request_and_checks_login(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    with patch.object(mihome, "request", return_value={"code": 0, "message": "ok"}) as mock_request:
        result = mihome._api_call("some/path", {"k": "v"}, 3)

    assert result == {"code": 0, "message": "ok"}
    call_args = mock_request.call_args[0]
    assert call_args[0] == f"{mihome.get_api_url()}/some/path"
    assert json.loads(call_args[1]["data"]) == {"k": "v"}
    assert call_args[2] == 3


def test_mihome_api_call_check_login_false_returns_none(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    with patch.object(mihome, "request", return_value={"code": 2, "message": "bad"}):
        result = mihome._api_call("path", {}, 1)
    assert result is None
    assert mihome._logged_in is False
    assert mihome._auth_failed is True


def test_mihome_check_login_request_raises_returns_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    with patch.object(mihome, "request", side_effect=HttpRequestError("boom")):
        assert mihome.check_login(None) is False


# ---------------------------------------------------------------------------
# MiHome — login_step_1 / login_step_2 / login_step_3
# ---------------------------------------------------------------------------


def test_login_step_1_success_updates_state(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._session = MagicMock()
    body = "&&&START&&&" + json.dumps(
        {"_sign": "sign1", "code": 0, "userId": "uid1", "ssecurity": "sec1", "location": "loc1"}
    )
    mihome._session.get.return_value = _mock_response(200, body)

    result = mihome.login_step_1()

    assert result is True
    assert mihome._sign == "sign1"
    assert mihome._userId == "uid1"
    assert mihome._ssecurity == "sec1"
    assert mihome._location == "loc1"


def test_login_step_1_success_nonzero_code_skips_state_update(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._session = MagicMock()
    body = "&&&START&&&" + json.dumps({"_sign": "sign2", "code": 1})
    mihome._session.get.return_value = _mock_response(200, body)
    prev_userid = mihome._userId

    result = mihome.login_step_1()

    assert result is True
    assert mihome._sign == "sign2"
    assert mihome._userId == prev_userid


def test_login_step_1_non_200_sets_auth_failed(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._session = MagicMock()
    mihome._session.get.return_value = _mock_response(403, "")

    result = mihome.login_step_1()

    assert result is False
    assert mihome._auth_failed is True


def test_login_step_1_http_request_error_returns_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._session = MagicMock()
    mihome._session.get.side_effect = HttpRequestError("boom")

    assert mihome.login_step_1() is False


def test_login_step_2_success_with_location(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._sign = "sign-x"
    mihome._session = MagicMock()
    body = "&&&START&&&" + json.dumps(
        {"location": "https://sts.api.io.mi.com/sts?x=1", "userId": "u2", "ssecurity": "sec2"}
    )
    mihome._session.post.return_value = _mock_response(200, body)

    result = mihome.login_step_2()

    assert result is True
    assert mihome._location == "https://sts.api.io.mi.com/sts?x=1"
    sent = mihome._session.post.call_args
    assert sent.kwargs["data"]["_sign"] == "sign-x"


def test_login_step_2_captcha_code_included_when_present(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._captcha_code = "1234"
    mihome._captcha_ick = "ick-value"
    mihome._session = MagicMock()
    body = "&&&START&&&" + json.dumps({"location": "https://loc"})
    mihome._session.post.return_value = _mock_response(200, body)

    mihome.login_step_2()

    sent = mihome._session.post.call_args
    assert sent.kwargs["data"]["captCode"] == "1234"
    assert sent.kwargs["cookies"]["ick"] == "ick-value"
    assert "_dc" in sent.kwargs["params"]


def test_login_step_2_notification_url_relative(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._session = MagicMock()
    body = "&&&START&&&" + json.dumps({"notificationUrl": "/identity/authStart?x=1"})
    mihome._session.post.return_value = _mock_response(200, body)

    result = mihome.login_step_2()

    assert result is False
    assert mihome.verification_url == "https://account.xiaomi.com/identity/authStart?x=1"
    assert mihome._auth_failed is True


def test_login_step_2_notification_url_absolute(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._session = MagicMock()
    body = "&&&START&&&" + json.dumps({"notificationUrl": "https://elsewhere/identity/authStart"})
    mihome._session.post.return_value = _mock_response(200, body)

    mihome.login_step_2()

    assert mihome.verification_url == "https://elsewhere/identity/authStart"


def test_login_step_2_captcha_url_fetches_image_and_ick(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._session = MagicMock()
    body1 = "&&&START&&&" + json.dumps({"captchaUrl": "/captcha.jpg"})
    resp1 = _mock_response(200, body1)
    resp2 = MagicMock(status=200, body=b"imgbytes")
    resp2.cookies = {"ick": "ick-abc"}
    mihome._session.post.return_value = resp1
    mihome._session.get.return_value = resp2

    result = mihome.login_step_2()

    assert result is False
    assert mihome._captcha_ick == "ick-abc"
    assert mihome.captcha_img == base64.b64encode(b"imgbytes").decode()
    mihome._session.get.assert_called_once_with("https://account.xiaomi.com/captcha.jpg")


def test_login_step_2_captcha_url_absolute_no_ick_cookie(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._session = MagicMock()
    body1 = "&&&START&&&" + json.dumps({"captchaUrl": "https://cdn/captcha.jpg"})
    resp1 = _mock_response(200, body1)
    resp2 = MagicMock(status=200, body=b"img2")
    resp2.cookies = {}
    mihome._session.post.return_value = resp1
    mihome._session.get.return_value = resp2

    result = mihome.login_step_2()

    assert result is False
    assert mihome.captcha_img is None


def test_login_step_2_non_200_sets_auth_failed(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._session = MagicMock()
    mihome._session.post.return_value = _mock_response(500, "")

    result = mihome.login_step_2()

    assert result is False
    assert mihome._auth_failed is True


def test_login_step_2_http_request_error_returns_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._session = MagicMock()
    mihome._session.post.side_effect = HttpRequestError("boom")

    assert mihome.login_step_2() is False


def test_login_step_3_success_sets_service_token_and_auth_key(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._location = "https://sts.api.io.mi.com/sts?abc"
    mihome._session = MagicMock()
    resp = MagicMock(status=200)
    resp.cookies = {"serviceToken": "svc-tok-1"}
    mihome._session.get.return_value = resp

    result = mihome.login_step_3()

    assert result is True
    assert mihome._service_token == "svc-tok-1"
    assert mihome._auth_key == f"svc-tok-1 {mihome._ssecurity} {mihome._userId} {mihome._client_id}"


def test_login_step_3_200_without_service_token_sets_auth_failed(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._location = "https://loc"
    mihome._session = MagicMock()
    resp = MagicMock(status=200)
    resp.cookies = {}
    mihome._session.get.return_value = resp

    result = mihome.login_step_3()

    assert result is False
    assert mihome._auth_failed is True


def test_login_step_3_non_200_sets_auth_failed(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._location = "https://loc"
    mihome._session = MagicMock()
    resp = MagicMock(status=403)
    resp.cookies = {}
    mihome._session.get.return_value = resp

    result = mihome.login_step_3()

    assert result is False
    assert mihome._auth_failed is True


def test_login_step_3_http_request_error_returns_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._location = "https://loc"
    mihome._session = MagicMock()
    mihome._session.get.side_effect = HttpRequestError("boom")

    assert mihome.login_step_3() is False


# ---------------------------------------------------------------------------
# MiHome — login()
# ---------------------------------------------------------------------------


def test_mihome_login_ssecurity_and_check_login_true_short_circuits(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._session = MagicMock()
    with patch.object(mihome, "check_login", return_value=True) as mock_check:
        result = mihome.login()

    assert result is True
    assert mihome._logged_in is True
    assert mihome._connected is True
    mock_check.assert_called_once()


def test_mihome_login_full_flow_success(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._ssecurity = None
    mihome._session = MagicMock()
    with (
        patch.object(mihome, "login_step_1", return_value=True),
        patch.object(mihome, "login_step_2", return_value=True),
        patch.object(mihome, "login_step_3", return_value=True),
    ):
        result = mihome.login()

    assert result is True
    assert mihome._auth_failed is False


def test_mihome_login_failure_resets_ssecurity(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._ssecurity = None
    mihome._session = MagicMock()
    with patch.object(mihome, "login_step_1", return_value=False):
        result = mihome.login()

    assert result is False
    assert mihome._ssecurity is None


def test_mihome_login_sets_cookies(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._session = MagicMock()
    mihome._ssecurity = None
    with (
        patch.object(mihome, "login_step_1", return_value=True),
        patch.object(mihome, "login_step_2", return_value=True),
        patch.object(mihome, "login_step_3", return_value=True),
    ):
        mihome.login()

    mihome._session.close_session.assert_called_once()
    assert mihome._session.set_cookie.call_count == 4


# ---------------------------------------------------------------------------
# MiHome — verify_code()
# ---------------------------------------------------------------------------


def test_verify_code_no_verification_url_returns_false(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome.verification_url = None
    assert mihome.verify_code("1234") is False


def test_verify_code_wrong_path_returns_false(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome.verification_url = "https://account.xiaomi.com/identity/other"
    assert mihome.verify_code("1234") is False


def test_verify_code_full_success_flow(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome.verification_url = "https://account.xiaomi.com/identity/authStart?x=1"
    mihome._session = MagicMock()
    list_resp = MagicMock(status=200)
    list_resp.cookies = {"identity_session": "sess1"}
    list_resp.text = json.dumps({"flag": 4})
    verify_resp = MagicMock(status=200)
    verify_resp.text = json.dumps({"code": 0, "location": "https://final/loc"})
    final_get_resp = MagicMock(status=200)
    mihome._session.get.side_effect = [list_resp, final_get_resp]
    mihome._session.post.return_value = verify_resp

    with (
        patch.object(mihome, "login_step_1", return_value=True),
        patch.object(mihome, "login_step_3", return_value=True),
    ):
        result = mihome.verify_code("999999")

    assert result is True
    assert mihome.verification_url is None
    assert mihome.captcha_img is None
    assert mihome._logged_in is True
    assert mihome._auth_failed is False
    assert mihome._connected is True


def test_verify_code_no_identity_session_returns_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome.verification_url = "https://account.xiaomi.com/identity/authStart"
    mihome._session = MagicMock()
    resp = MagicMock(status=200)
    resp.cookies = {}
    mihome._session.get.return_value = resp

    assert mihome.verify_code("123") is False


def test_verify_code_list_call_non_200_returns_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome.verification_url = "https://account.xiaomi.com/identity/authStart"
    mihome._session = MagicMock()
    resp = MagicMock(status=500)
    mihome._session.get.return_value = resp

    assert mihome.verify_code("123") is False


def test_verify_code_flag_not_4_uses_verify_email_path(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome.verification_url = "https://account.xiaomi.com/identity/authStart"
    mihome._session = MagicMock()
    list_resp = MagicMock(status=200)
    list_resp.cookies = {"identity_session": "s1"}
    list_resp.text = json.dumps({"flag": 1})
    verify_resp = MagicMock(status=200)
    verify_resp.text = json.dumps({"code": 1})
    mihome._session.get.return_value = list_resp
    mihome._session.post.return_value = verify_resp

    result = mihome.verify_code("123")

    assert result is False
    post_url = mihome._session.post.call_args[0][0]
    assert "verifyEmail" in post_url


def test_verify_code_code_zero_no_location_logs_warning(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome.verification_url = "https://account.xiaomi.com/identity/authStart"
    mihome._session = MagicMock()
    list_resp = MagicMock(status=200)
    list_resp.cookies = {"identity_session": "s1"}
    list_resp.text = json.dumps({"flag": 4})
    verify_resp = MagicMock(status=200)
    verify_resp.text = json.dumps({"code": 0})
    mihome._session.get.return_value = list_resp
    mihome._session.post.return_value = verify_resp

    assert mihome.verify_code("123") is False


def test_verify_code_exception_raises_device_exception(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome.verification_url = "https://account.xiaomi.com/identity/authStart"
    mihome._session = MagicMock()
    mihome._session.get.side_effect = RuntimeError("network exploded")

    with pytest.raises(DeviceException):
        mihome.verify_code("123")


def test_verify_captcha_sets_code_and_returns_login_result(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    with patch.object(mihome, "login", return_value=True) as mock_login:
        result = mihome.verify_captcha("55555")

    assert result is True
    assert mihome._captcha_code == "55555"
    mock_login.assert_called_once()


def test_verify_captcha_login_false_but_no_captcha_img_returns_true(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome.captcha_img = None
    with patch.object(mihome, "login", return_value=False):
        result = mihome.verify_captcha("000")
    assert result is True


def test_verify_captcha_login_false_with_captcha_img_returns_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome.captcha_img = "somedata"
    with patch.object(mihome, "login", return_value=False):
        result = mihome.verify_captcha("000")
    assert result is False


# ---------------------------------------------------------------------------
# MiHome — get_file / get_file_url / get_interim_file_url
# ---------------------------------------------------------------------------


def test_mihome_get_file_success(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._session = MagicMock()
    mihome._session.get.return_value = MagicMock(status=200, body=b"filedata")
    assert mihome.get_file("http://x/f") == b"filedata"


def test_mihome_get_file_retries_and_fails(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._session = MagicMock()
    mihome._session.get.return_value = MagicMock(status=404, body=b"")
    result = mihome.get_file("http://x/f", retry_count=1)
    assert result is None
    assert mihome._session.get.call_count == 2


def test_mihome_get_file_http_error_returns_none(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._session = MagicMock()
    mihome._session.get.side_effect = HttpRequestError("boom")
    result = mihome.get_file("http://x/f", retry_count=0)
    assert result is None


def test_mihome_get_file_url_success(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "_api_call", return_value={"result": {"url": "http://f"}}):
        assert mihome.get_file_url("obj") == "http://f"


def test_mihome_get_file_url_v3_fallback_to_v2(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._v3 = True
    responses = [{"code": -8}, {"result": {"url": "http://v2"}}]
    with patch.object(mihome, "_api_call", side_effect=responses) as mock_call:
        result = mihome.get_file_url("obj")
    assert result == "http://v2"
    assert mihome._v3 is False
    assert mock_call.call_count == 2


def test_mihome_get_file_url_missing_result_no_fallback(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._v3 = False
    with patch.object(mihome, "_api_call", return_value={"code": -8}):
        result = mihome.get_file_url("obj")
    assert result is None


def test_mihome_get_file_url_none_response(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "_api_call", return_value=None):
        assert mihome.get_file_url("obj") is None


def test_mihome_get_interim_file_url_success(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "_api_call", return_value={"result": {"url": "http://interim"}}):
        assert mihome.get_interim_file_url("obj") == "http://interim"


def test_mihome_get_interim_file_url_v3_fallback(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._v3 = True
    responses = [{"code": -8}, {"result": {"url": "http://v2interim"}}]
    with patch.object(mihome, "_api_call", side_effect=responses):
        result = mihome.get_interim_file_url("obj")
    assert result == "http://v2interim"
    assert mihome._v3 is False


def test_mihome_get_interim_file_url_none(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "_api_call", return_value=None):
        assert mihome.get_interim_file_url("obj") is None


# ---------------------------------------------------------------------------
# MiHome — send_async / send / get_device_property / get_device_event
# ---------------------------------------------------------------------------


def test_mihome_send_async_wraps_callback(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._did = "d1"
    cb = MagicMock()
    with patch.object(mihome, "_api_call_async") as mock_call_async:
        mihome.send_async(cb, "get_prop", ["a"], retry_count=4)

    args = mock_call_async.call_args[0]
    wrapped_cb, url, payload, retry = args
    assert url == "v2/home/rpc/d1"
    assert payload == {"method": "get_prop", "params": ["a"]}
    assert retry == 4

    wrapped_cb({"result": [9]})
    cb.assert_called_once_with([9])

    cb.reset_mock()
    wrapped_cb(None)
    cb.assert_called_once_with(None)


def test_mihome_send_success(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._did = "d1"
    with patch.object(mihome, "_api_call", return_value={"result": "r1"}):
        assert mihome.send("get_prop", []) == "r1"


def test_mihome_send_missing_result(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "_api_call", return_value={"other": 1}):
        assert mihome.send("get_prop", []) is None


def test_mihome_send_none_response(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "_api_call", return_value=None):
        assert mihome.send("get_prop", []) is None


def test_mihome_get_device_property_delegates(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "get_device_data", return_value=[1]) as mock_gdd:
        mihome.get_device_property("1.2", limit=2)
    mock_gdd.assert_called_once_with("1.2", "prop", 2, 0, 9999999999)


def test_mihome_get_device_event_delegates(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "get_device_data", return_value=[2]) as mock_gdd:
        mihome.get_device_event("1.3")
    mock_gdd.assert_called_once_with("1.3", "event", 1, 0, 9999999999)


def test_mihome_get_device_data_success(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._uid = "u1"
    mihome._did = "d1"
    with patch.object(mihome, "_api_call", return_value={"result": [{"v": 1}]}) as mock_call:
        result = mihome.get_device_data("k1", "prop", limit=10, time_start=5, time_end=99)
    assert result == [{"v": 1}]
    params = mock_call.call_args[0][1]
    assert params == {
        "uid": "u1",
        "did": "d1",
        "time_end": 99,
        "time_start": 5,
        "limit": 10,
        "key": "k1",
        "type": "prop",
    }


def test_mihome_get_device_data_missing_result(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "_api_call", return_value={"other": 1}):
        assert mihome.get_device_data("k", "prop") is None


def test_mihome_get_device_data_none_response(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "_api_call", return_value=None):
        assert mihome.get_device_data("k", "prop") is None


# ---------------------------------------------------------------------------
# MiHome — get_info / get_supported_devices / get_devices
# ---------------------------------------------------------------------------


def test_mihome_get_info_finds_device_and_sets_v3(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    devices = [
        {"mac": "AA", "uid": "u1", "did": "d1", "model": "xiaomi.vacuum.a1", "token": "tok", "localip": "1.2.3.4"}
    ]
    with patch.object(mihome, "get_devices", return_value=devices):
        result = mihome.get_info("AA")
    assert result == ("tok", "1.2.3.4")
    assert mihome._uid == "u1"
    assert mihome._did == "d1"
    assert mihome._v3 is True


def test_mihome_get_info_no_match(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "get_devices", return_value=[{"mac": "ZZ"}]):
        assert mihome.get_info("AA") == (None, None)


def test_mihome_get_info_no_devices(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "get_devices", return_value=None):
        assert mihome.get_info("AA") == (None, None)


def test_mihome_get_info_non_xiaomi_vacuum_model_v3_false(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    devices = [
        {"mac": "AA", "uid": "u1", "did": "d1", "model": "dreame.vacuum.p1", "token": "tok", "localip": "1.1.1.1"}
    ]
    with patch.object(mihome, "get_devices", return_value=devices):
        mihome.get_info("AA")
    assert mihome._v3 is False


def test_mihome_get_supported_devices_filters(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    devices = [
        {"name": "Vac1", "model": "m.vacuum.a1", "localip": "1.1.1.1", "mac": "AA"},
        {"name": "Other", "model": "m.other", "localip": "2.2.2.2", "mac": "BB"},
        {"name": "Unsup", "model": "x.vacuum.zz", "localip": "3.3.3.3", "mac": "CC"},
        {"name": "Child", "model": "m.vacuum.a1", "parent_id": "AA", "mac": "DD"},
    ]
    with patch.object(mihome, "get_devices", return_value=devices):
        supported, unsupported = mihome.get_supported_devices(["m.vacuum.a1"])
    assert supported == {"Vac1 - m.vacuum.a1": devices[0]}
    assert "Unsup - x.vacuum.zz" in unsupported


def test_mihome_get_supported_devices_host_match_breaks_early(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    devices = [
        {"name": "Vac1", "model": "m.vacuum.a1", "localip": "1.1.1.1", "mac": "AA"},
        {"name": "Vac2", "model": "m.vacuum.a1", "localip": "2.2.2.2", "mac": "BB"},
    ]
    with patch.object(mihome, "get_devices", return_value=devices):
        supported, _unsupported = mihome.get_supported_devices(["m.vacuum.a1"], host="2.2.2.2")
    assert supported == {"Vac2 - m.vacuum.a1": devices[1]}


def test_mihome_get_supported_devices_empty(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    with patch.object(mihome, "get_devices", return_value=None):
        supported, unsupported = mihome.get_supported_devices(["m1"])
    assert supported == {}
    assert unsupported == {}


def test_mihome_get_devices_gethome_fails_returns_none(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    with patch.object(mihome, "_api_call", return_value=None):
        assert mihome.get_devices() is None


def test_mihome_get_devices_full_aggregation(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._userId = "owner1"
    home_response = {"result": {"homelist": [{"id": 1}, {"id": 2}]}}
    cnt_response = {"result": {"share": {"share_family": [{"home_id": 2, "home_owner": "shared_owner"}]}}}
    home_device_list_1 = {"result": {"device_info": [{"mac": "AA", "did": "d1"}]}}
    home_device_list_2 = {"result": {"device_info": [{"mac": "BB", "did": "d2"}]}}
    legacy_list = {"result": {"list": [{"mac": "AA", "did": "d1-old"}, {"mac": "CC", "did": "d3"}]}}

    home_device_calls = [home_device_list_1, home_device_list_2]

    def fake_api_call(url: str, params: object, retry_count: int = 2) -> object:
        if url == "v2/home/home_device_list":
            return home_device_calls.pop(0)
        return {
            "v2/homeroom/gethome": home_response,
            "v2/user/get_device_cnt": cnt_response,
            "home/device_list": legacy_list,
        }[url]

    with patch.object(mihome, "_api_call", side_effect=fake_api_call):
        result = mihome.get_devices()

    macs = sorted(d["mac"] for d in result)
    assert macs == ["AA", "BB", "CC"]


def test_mihome_get_devices_no_homes_skips_device_list_loop_but_checks_legacy(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    home_response = {"result": {"homelist": []}}
    cnt_response = {"result": {}}
    legacy_list = {"result": {"list": [{"mac": "ZZ", "did": "dz"}]}}

    def fake_api_call(url: str, params: object, retry_count: int = 2) -> object:
        return {
            "v2/homeroom/gethome": home_response,
            "v2/user/get_device_cnt": cnt_response,
            "home/device_list": legacy_list,
        }[url]

    with patch.object(mihome, "_api_call", side_effect=fake_api_call) as mock_call:
        result = mihome.get_devices()

    assert result == [{"mac": "ZZ", "did": "dz"}]
    called_urls = [c.args[0] for c in mock_call.call_args_list]
    assert "v2/home/home_device_list" not in called_urls


def test_mihome_get_devices_legacy_list_missing_returns_home_device_list_only(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    mihome._userId = "u1"
    home_response = {"result": {"homelist": [{"id": 1}]}}
    cnt_response = {"result": {"share": None}}
    home_device_list = {"result": {"device_info": [{"mac": "AA", "did": "d1"}]}}
    legacy_list = {"result": {}}

    def fake_api_call(url: str, params: object, retry_count: int = 2) -> object:
        return {
            "v2/homeroom/gethome": home_response,
            "v2/user/get_device_cnt": cnt_response,
            "v2/home/home_device_list": home_device_list,
            "home/device_list": legacy_list,
        }[url]

    with patch.object(mihome, "_api_call", side_effect=fake_api_call):
        result = mihome.get_devices()

    assert result == [{"mac": "AA", "did": "d1"}]


def test_mihome_get_batch_device_datas_success(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._did = "d1"
    with patch.object(mihome, "_api_call", return_value={"d1": {"x": 1}}):
        assert mihome.get_batch_device_datas(["p"]) == {"x": 1}


def test_mihome_get_batch_device_datas_missing_did(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._did = "d1"
    with patch.object(mihome, "_api_call", return_value={"other": 1}):
        assert mihome.get_batch_device_datas(["p"]) is None


def test_mihome_set_batch_device_datas_success(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._did = "d1"
    with patch.object(mihome, "_api_call", return_value={"result": "ok"}):
        assert mihome.set_batch_device_datas(["p"]) == "ok"


def test_mihome_set_batch_device_datas_missing_result(
    mihome: DreameVacuumMiHomeCloudProtocol,
) -> None:
    with patch.object(mihome, "_api_call", return_value={}):
        assert mihome.set_batch_device_datas(["p"]) is None


def test_mihome_disconnect_signals_active_thread(mihome: DreameVacuumMiHomeCloudProtocol) -> None:
    mihome._thread = MagicMock()
    mihome.disconnect()
    item = mihome._queue.get_nowait()
    assert item == []


# ---------------------------------------------------------------------------
# Aggregate DreameVacuumProtocol — remaining branches
# ---------------------------------------------------------------------------


def test_aggregate_no_credentials_at_all_disables_cloud() -> None:
    p = DreameVacuumProtocol(ip="192.168.1.50", token="a" * 32)
    assert p.cloud is None
    assert p.prefer_cloud is False


def test_aggregate_set_credentials_missing_token_clears_device() -> None:
    p = DreameVacuumProtocol(ip="1.2.3.4", token="a" * 32, username="u", password="p", country="de")
    assert p.device is not None
    p.set_credentials("1.2.3.4", "", account_type="mi")
    assert p.device is None


def test_aggregate_set_credentials_non_mi_account_clears_device() -> None:
    p = DreameVacuumProtocol(
        ip="1.2.3.4", token="a" * 32, username="u", password="p", country="eu", account_type="dreame"
    )
    p.set_credentials("1.2.3.4", "a" * 32, account_type="dreame")
    assert p.device is None


def test_aggregate_connect_mi_account_sets_connected_when_cloud_available() -> None:
    p = DreameVacuumProtocol(
        ip="1.2.3.4", token="a" * 32, username="u", password="pw", country="de", account_type="mi", prefer_cloud=True
    )
    with patch.object(p, "send", return_value={"info": 1}) as mock_send:
        result = p.connect()
    assert result == {"info": 1}
    assert p._connected is True
    assert p._ready is True
    mock_send.assert_called_once_with("miIO.info", retry_count=1)


def test_aggregate_connect_mi_account_no_device_cloud_no_connected_flag() -> None:
    p = DreameVacuumProtocol(ip="1.2.3.4", token="a" * 32, account_type="mi")
    with patch.object(p, "send", return_value={"info": 1}):
        result = p.connect()
    assert result == {"info": 1}
    assert p._connected is False


def test_aggregate_connect_dreame_account_uses_cloud_connect() -> None:
    p = DreameVacuumProtocol(
        ip="1.2.3.4",
        token="a" * 32,
        username="u",
        password="pw",
        country="eu",
        account_type="dreame",
        prefer_cloud=True,
    )
    with patch.object(p.cloud, "connect", return_value={"c": 1}) as mock_cloud_connect:
        result = p.connect(message_callback=MagicMock())
    assert result == {"c": 1}
    assert p._connected is True
    mock_cloud_connect.assert_called_once()


def test_aggregate_connect_no_info_leaves_ready_false() -> None:
    p = DreameVacuumProtocol(ip="1.2.3.4", token="a" * 32)
    with patch.object(p, "send", return_value=None):
        result = p.connect()
    assert result is None
    assert p._ready is False


def test_aggregate_disconnect_calls_all_present_components() -> None:
    p = DreameVacuumProtocol(
        ip="1.2.3.4", token="a" * 32, username="u", password="pw", country="de", account_type="mi", prefer_cloud=True
    )
    p.device = MagicMock()
    p.cloud = MagicMock()
    p.device_cloud = MagicMock()
    p._connected = True

    p.disconnect()

    p.device.disconnect.assert_called_once()
    p.cloud.disconnect.assert_called_once()
    p.device_cloud.disconnect.assert_called_once()
    assert p._connected is False


def test_aggregate_disconnect_noop_components_when_none() -> None:
    p = DreameVacuumProtocol()
    p.disconnect()
    assert p._connected is False


def test_aggregate_send_async_device_cloud_not_logged_in_uses_cloud_device_id() -> None:
    p = DreameVacuumProtocol(username="u", password="pw", country="de", account_type="mi", prefer_cloud=True)
    p.cloud = MagicMock(device_id="cloud-did")
    p.device_cloud = MagicMock(logged_in=False, device_id=None)

    def fake_login() -> None:
        p.device_cloud.logged_in = True

    p.device_cloud.login.side_effect = fake_login
    cb = MagicMock()

    p.send_async(cb, "get_properties", [])

    p.device_cloud.login.assert_called_once()
    assert p.device_cloud._did == "cloud-did"
    p.device_cloud.send_async.assert_called_once()

    inner_cb = p.device_cloud.send_async.call_args[0][0]
    inner_cb({"ok": 1})
    cb.assert_called_once_with({"ok": 1})
    assert p._connected is True


def test_aggregate_send_async_device_cloud_uses_mac_when_no_cloud_did() -> None:
    """When self.cloud has no device_id either, falls back to self._mac."""
    p = DreameVacuumProtocol(username="u", password="pw", country="de", account_type="mi", prefer_cloud=True)
    p.cloud = MagicMock(device_id=None)
    p._mac = "AA:BB"
    p.device_cloud = MagicMock(logged_in=False, device_id=None)

    def fake_login() -> None:
        p.device_cloud.logged_in = True

    p.device_cloud.login.side_effect = fake_login

    p.send_async(MagicMock(), "get_properties", [])

    p.device_cloud.get_info.assert_called_once_with("AA:BB")


def test_aggregate_send_async_device_cloud_uses_mac_when_cloud_is_none() -> None:
    """Regression test for a real bug: send_async() used to access
    ``self.cloud.device_id`` unconditionally in this branch, with no
    ``self.cloud is not None`` guard. If ``self.cloud`` is ``None`` while
    ``device_cloud`` is truthy (possible when ``prefer_cloud=True`` but
    username/country/password were not all supplied), this raised
    ``AttributeError`` instead of falling back to ``self._mac``.
    Unreachable via the current config flow (which always supplies cloud
    credentials together), but defended against here regardless.
    """
    # No username/country/password/auth_key -> self.cloud stays None. prefer_cloud=True
    # still builds device_cloud (device_cloud construction only checks the
    # constructor's ``prefer_cloud`` argument, not the cloud credentials).
    p = DreameVacuumProtocol(account_type="mi", prefer_cloud=True)
    assert p.cloud is None
    p._mac = "AA:BB"
    p.device_cloud = MagicMock(logged_in=False, device_id=None)

    def fake_login() -> None:
        p.device_cloud.logged_in = True

    p.device_cloud.login.side_effect = fake_login

    p.send_async(MagicMock(), "get_properties", [])

    p.device_cloud.get_info.assert_called_once_with("AA:BB")


def test_aggregate_send_async_device_cloud_login_fails_raises() -> None:
    p = DreameVacuumProtocol(username="u", password="pw", country="de", account_type="mi", prefer_cloud=True)
    p.device_cloud = MagicMock(logged_in=False)
    with pytest.raises(DeviceException):
        p.send_async(MagicMock(), "get_properties", [])


def test_aggregate_send_async_cloud_callback_none_response_raises_and_disconnects() -> None:
    p = DreameVacuumProtocol(username="u", password="pw", country="de", account_type="mi", prefer_cloud=True)
    p.cloud = MagicMock(device_id="d1")
    p.device_cloud = MagicMock(logged_in=True, device_id="d1")
    p._connected = True

    p.send_async(MagicMock(), "get_properties", [])
    inner_cb = p.device_cloud.send_async.call_args[0][0]

    with pytest.raises(DeviceException):
        inner_cb(None)
    assert p._connected is False


def test_aggregate_send_async_falls_back_to_device_when_no_cloud() -> None:
    p = DreameVacuumProtocol(ip="1.2.3.4", token="a" * 32)
    cb = MagicMock()
    with patch.object(p.device, "send_async") as mock_send_async:
        p.send_async(cb, "get_properties", [1], retry_count=3)
    mock_send_async.assert_called_once_with(cb, "get_properties", parameters=[1], retry_count=3)


def test_aggregate_send_device_cloud_not_logged_in_uses_cloud_device_id() -> None:
    """send() mirrors send_async()'s not-logged-in relogin + device-id resolution branch."""
    p = DreameVacuumProtocol(username="u", password="pw", country="de", account_type="mi", prefer_cloud=True)
    p.cloud = MagicMock(device_id="cloud-did")
    p.device_cloud = MagicMock(logged_in=False, device_id=None)

    def fake_login() -> None:
        p.device_cloud.logged_in = True

    p.device_cloud.login.side_effect = fake_login
    p.device_cloud.send.return_value = {"ok": 1}

    result = p.send("get_properties", [])

    assert result == {"ok": 1}
    assert p.device_cloud._did == "cloud-did"


def test_aggregate_send_device_cloud_not_logged_in_uses_mac_fallback() -> None:
    p = DreameVacuumProtocol(username="u", password="pw", country="de", account_type="mi", prefer_cloud=True)
    p.cloud = MagicMock(device_id=None)
    p._mac = "AA:BB"
    p.device_cloud = MagicMock(logged_in=False, device_id=None)

    def fake_login() -> None:
        p.device_cloud.logged_in = True

    p.device_cloud.login.side_effect = fake_login
    p.device_cloud.send.return_value = {"ok": 1}

    p.send("get_properties", [])

    p.device_cloud.get_info.assert_called_once_with("AA:BB")


def test_aggregate_send_device_cloud_uses_mac_when_cloud_is_none() -> None:
    """Regression test mirroring the send_async() case above: send() must not
    dereference ``self.cloud.device_id`` when ``self.cloud`` is None."""
    p = DreameVacuumProtocol(account_type="mi", prefer_cloud=True)
    assert p.cloud is None
    p._mac = "AA:BB"
    p.device_cloud = MagicMock(logged_in=False, device_id=None)

    def fake_login() -> None:
        p.device_cloud.logged_in = True

    p.device_cloud.login.side_effect = fake_login
    p.device_cloud.send.return_value = {"ok": 1}

    p.send("get_properties", [])

    p.device_cloud.get_info.assert_called_once_with("AA:BB")


def test_aggregate_action_defaults_parameters_to_empty_list() -> None:
    p = DreameVacuumProtocol(ip="1.2.3.4", token="a" * 32)
    with patch.object(p, "send", return_value={"r": 1}) as mock_send:
        result = p.action(1, 2)
    assert result == {"r": 1}
    assert mock_send.call_args[1]["parameters"]["in"] == []


def test_aggregate_send_device_cloud_success() -> None:
    p = DreameVacuumProtocol(username="u", password="pw", country="de", account_type="mi", prefer_cloud=True)
    p.cloud = MagicMock(device_id="d1")
    p.device_cloud = MagicMock(logged_in=True, device_id="d1")
    p.device_cloud.send.return_value = {"ok": 1}

    result = p.send("get_properties", [])

    assert result == {"ok": 1}
    assert p._connected is True


def test_aggregate_send_device_cloud_none_response_raises_and_disconnects_for_properties() -> None:
    p = DreameVacuumProtocol(username="u", password="pw", country="de", account_type="mi", prefer_cloud=True)
    p.cloud = MagicMock(device_id="d1")
    p.device_cloud = MagicMock(logged_in=True, device_id="d1")
    p.device_cloud.send.return_value = None
    p._connected = True

    with pytest.raises(DeviceException):
        p.send("get_properties", [])
    assert p._connected is False


def test_aggregate_send_device_cloud_none_response_other_method_keeps_connected() -> None:
    p = DreameVacuumProtocol(username="u", password="pw", country="de", account_type="mi", prefer_cloud=True)
    p.cloud = MagicMock(device_id="d1")
    p.device_cloud = MagicMock(logged_in=True, device_id="d1")
    p.device_cloud.send.return_value = None
    p._connected = True

    with pytest.raises(DeviceException):
        p.send("action", [])
    assert p._connected is True


def test_aggregate_send_device_cloud_not_logged_in_login_fails_raises() -> None:
    p = DreameVacuumProtocol(username="u", password="pw", country="de", account_type="mi", prefer_cloud=True)
    p.device_cloud = MagicMock(logged_in=False)
    with pytest.raises(DeviceException):
        p.send("get_properties", [])


def test_aggregate_send_falls_back_to_device() -> None:
    p = DreameVacuumProtocol(ip="1.2.3.4", token="a" * 32)
    with patch.object(p.device, "send", return_value={"r": 1}) as mock_send:
        result = p.send("get_properties", [1], retry_count=2)
    assert result == {"r": 1}
    mock_send.assert_called_once_with("get_properties", parameters=[1], retry_count=2)


def test_aggregate_send_no_device_no_cloud_returns_none() -> None:
    p = DreameVacuumProtocol()
    assert p.send("get_properties") is None


def test_aggregate_get_properties_delegates_to_send() -> None:
    p = DreameVacuumProtocol(ip="1.2.3.4", token="a" * 32)
    with patch.object(p, "send", return_value={"r": 1}) as mock_send:
        result = p.get_properties(["k"], retry_count=3)
    assert result == {"r": 1}
    mock_send.assert_called_once_with("get_properties", parameters=["k"], retry_count=3)


def test_aggregate_set_property_builds_params_non_cloud() -> None:
    p = DreameVacuumProtocol(ip="1.2.3.4", token="a" * 32)
    with patch.object(p, "set_properties", return_value={"r": 1}) as mock_set_props:
        result = p.set_property(2, 3, value="v", retry_count=1)
    assert result == {"r": 1}
    params = mock_set_props.call_args[0][0]
    assert params == [{"did": "2.3", "siid": 2, "piid": 3, "value": "v"}]


def test_aggregate_set_property_dreame_cloud_uses_device_id() -> None:
    p = DreameVacuumProtocol(
        ip="1.2.3.4",
        token="a" * 32,
        username="u",
        password="pw",
        country="eu",
        account_type="dreame",
        prefer_cloud=True,
    )
    p.cloud = MagicMock(device_id="cloud-did-1")
    with patch.object(p, "set_properties", return_value={"r": 1}) as mock_set_props:
        p.set_property(1, 2, value="x")
    params = mock_set_props.call_args[0][0]
    assert params[0]["did"] == "cloud-did-1"


def test_aggregate_set_properties_delegates_to_send() -> None:
    p = DreameVacuumProtocol(ip="1.2.3.4", token="a" * 32)
    with patch.object(p, "send", return_value={"ok": 1}) as mock_send:
        result = p.set_properties([{"a": 1}], retry_count=2)
    assert result == {"ok": 1}
    mock_send.assert_called_once_with("set_properties", parameters=[{"a": 1}], retry_count=2)


def test_aggregate_action_async_builds_params_and_defaults_parameters() -> None:
    p = DreameVacuumProtocol(ip="1.2.3.4", token="a" * 32)
    cb = MagicMock()
    with patch.object(p, "send_async") as mock_send_async:
        p.action_async(cb, 3, 4)
    args, kwargs = mock_send_async.call_args
    assert args[0] is cb
    assert args[1] == "action"
    assert kwargs["parameters"]["did"] == "3.4"
    assert kwargs["parameters"]["in"] == []


def test_aggregate_action_builds_params_dreame_cloud() -> None:
    p = DreameVacuumProtocol(
        ip="1.2.3.4",
        token="a" * 32,
        username="u",
        password="pw",
        country="eu",
        account_type="dreame",
        prefer_cloud=True,
    )
    p.cloud = MagicMock(device_id="cid-1")
    with patch.object(p, "send", return_value={"r": 1}) as mock_send:
        result = p.action(1, 2, parameters=["x"])
    assert result == {"r": 1}
    sent_params = mock_send.call_args[1]["parameters"]
    assert sent_params["did"] == "cid-1"
    assert sent_params["in"] == ["x"]


def test_aggregate_connected_property_device_cloud_path() -> None:
    p = DreameVacuumProtocol(username="u", password="pw", country="de", account_type="mi", prefer_cloud=True)
    p.device_cloud = MagicMock(logged_in=True, connected=True)
    p._connected = True
    assert p.connected is True


def test_aggregate_connected_property_device_path() -> None:
    p = DreameVacuumProtocol(ip="1.2.3.4", token="a" * 32)
    p.device._discovered = True
    assert p.connected is True
    p.device._discovered = False
    assert p.connected is False


def test_aggregate_connected_property_false_when_nothing() -> None:
    p = DreameVacuumProtocol()
    assert p.connected is False


def test_aggregate_dreame_cloud_property_false_without_cloud() -> None:
    p = DreameVacuumProtocol()
    assert p.dreame_cloud is False
