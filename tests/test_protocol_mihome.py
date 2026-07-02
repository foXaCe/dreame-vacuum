"""Characterization tests for MiHome cloud and MiIO device protocol classes.

These tests lock down the OBSERVED behaviour of DreameVacuumMiHomeCloudProtocol,
DreameVacuumDeviceProtocol, and the DreameVacuumProtocol aggregate without
modifying any production code.  Divergences from the plan are noted inline.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

from Crypto.Cipher import ARC4
import pytest
import requests

from custom_components.dreame_vacuum.dreame.exceptions import RateLimitError
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


def _mock_response(status_code: int, text: str, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
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
    mihome._session.post.side_effect = requests.exceptions.Timeout

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
    mihome._session.post.side_effect = requests.exceptions.ConnectionError("refused")

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
    mihome._session.post.side_effect = requests.exceptions.Timeout
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
    mihome._session.post.side_effect = requests.exceptions.ConnectionError("refused")
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
