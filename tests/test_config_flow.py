"""Tests for Dreame Vacuum config flow."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
)
from homeassistant.data_entry_flow import AbortFlow, FlowResultType
import pytest
import voluptuous as vol

from custom_components.dreame_vacuum.config_flow import (
    ACCOUNT_TYPE_DREAME,
    ACCOUNT_TYPE_LOCAL,
    ACCOUNT_TYPE_MI,
    DreameVacuumFlowHandler,
    DreameVacuumOptionsFlowHandler,
)
from custom_components.dreame_vacuum.const import (
    CONF_ACCOUNT_TYPE,
    CONF_AUTH_KEY,
    CONF_COLOR_SCHEME,
    CONF_COUNTRY,
    CONF_DID,
    CONF_HIDDEN_MAP_OBJECTS,
    CONF_ICON_SET,
    CONF_LOW_RESOLUTION,
    CONF_MAC,
    CONF_NOTIFY,
    CONF_PREFER_CLOUD,
    CONF_SQUARE,
    CONF_VERSION,
    DOMAIN,
    NOTIFICATION,
)
from custom_components.dreame_vacuum.dreame import VERSION


def _fake_hass():
    hass = MagicMock()
    hass.config_entries.flow.async_progress_by_handler.return_value = []
    hass.config.language = "en"
    # No existing entries / no unique-id collisions by default. Individual
    # tests override these to drive the duplicate / already_configured paths.
    hass.config_entries.async_entry_for_domain_unique_id.return_value = None
    hass.config_entries.async_entries.return_value = []

    # Run executor jobs inline so the real protocol/cloud side effects driven
    # by the flow (login, connect, verify_code, ...) actually execute.
    async def _run_executor_job(func, *args):
        return func(*args)

    hass.async_add_executor_job = AsyncMock(side_effect=_run_executor_job)
    return hass


def _make_flow(*, reauth: bool = False, account_type: str = ACCOUNT_TYPE_DREAME) -> DreameVacuumFlowHandler:
    """Build a flow handler wired to a fake hass.

    ``context`` carries a ``source`` so the inherited ConfigFlow helpers
    (``async_create_entry``, ``async_set_unique_id`` ...) behave like in a real
    flow while we drive the steps directly.
    """
    flow = DreameVacuumFlowHandler()
    flow.hass = _fake_hass()
    flow.context = {"source": SOURCE_USER}
    flow.reauth = reauth
    flow.account_type = account_type
    return flow


def _cloud_login_input() -> dict:
    return {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret", CONF_COUNTRY: "eu"}


def _dreame_device(mac: str = "AA:BB:CC:DD:EE:FF", model: str = "dreame.vacuum.p2009") -> dict:
    return {
        "mac": mac,
        "model": model,
        "name": "",
        "did": "123456789",
        "bindDomain": "192.168.1.100",
        "customName": "My Vacuum",
        "deviceInfo": {"displayName": "Dreame Test"},
    }


@pytest.fixture
def cloud_protocol(mock_dreame_vacuum_protocol):
    """Expose the protocol instance returned by the patched class."""
    return mock_dreame_vacuum_protocol.return_value


def _cloud_entry_data(include_password: bool = True) -> dict:
    data = {
        CONF_NAME: "Test Vacuum",
        CONF_HOST: "192.168.1.100",
        CONF_TOKEN: " ",
        CONF_USERNAME: "test@example.com",
        CONF_COUNTRY: "eu",
        CONF_ACCOUNT_TYPE: ACCOUNT_TYPE_DREAME,
        CONF_AUTH_KEY: "stored_auth_key",
        CONF_DID: "123456789",
        CONF_MAC: "AA:BB:CC:DD:EE:FF",
    }
    if include_password:
        data[CONF_PASSWORD] = "password"
    return data


async def test_user_step_initialises_flow_handler() -> None:
    """User flow should construct the flow handler without error.

    We don't drive it all the way through because a real flow would pull
    the ``camera`` dependency, which in turn pulls ``turbojpeg`` — a
    native dependency not available in all dev environments. We exercise
    the handler directly instead, which still covers the step logic.
    """
    flow = DreameVacuumFlowHandler()
    flow.hass = _fake_hass()

    result = await flow.async_step_user(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dreame"


async def test_dreame_step_invalid_credentials() -> None:
    """An empty login form should be refused with `credentials_incomplete`."""
    flow = DreameVacuumFlowHandler()
    flow.hass = _fake_hass()
    # Going through async_step_user is what normally pins account_type to
    # "dreame"; call it first so the dreame form reports back with the
    # matching step_id.
    await flow.async_step_user(user_input=None)

    result = await flow.async_step_dreame(user_input={"username": "", "password": "", "country": "eu"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dreame"
    errors = result.get("errors") or {}
    assert errors.get("base") == "credentials_incomplete"


async def test_reauth_accepts_auth_key_only_entry_without_stored_password() -> None:
    """Entries migrated to auth_key-only storage must still reach the reauth form."""
    flow = DreameVacuumFlowHandler()
    flow.hass = _fake_hass()

    result = await flow.async_step_reauth(_cloud_entry_data(include_password=False))

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert flow.password is None


async def test_reconfigure_accepts_auth_key_only_entry_without_stored_password(monkeypatch) -> None:
    """Reconfigure should not require a password removed by the auth_key migration."""
    flow = DreameVacuumFlowHandler()
    flow.hass = _fake_hass()
    entry = SimpleNamespace(data=_cloud_entry_data(include_password=False))
    monkeypatch.setattr(flow, "_get_reconfigure_entry", lambda: entry)

    result = await flow.async_step_reconfigure()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure_confirm"
    assert flow.password is None


# ---------------------------------------------------------------------------
# async_step_user
# ---------------------------------------------------------------------------


async def test_user_step_aborts_when_flow_already_in_progress() -> None:
    """A second user flow while one is in progress must abort."""
    flow = _make_flow()
    # _async_in_progress consults async_progress_by_handler; return a fake flow.
    flow.hass.config_entries.flow.async_progress_by_handler.return_value = [
        {"flow_id": "x", "handler": DOMAIN, "context": {"source": SOURCE_USER}}
    ]

    result = await flow.async_step_user(user_input=None)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"


async def test_user_step_pins_dreame_account_type() -> None:
    """async_step_user always selects the Dreame account type."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)

    result = await flow.async_step_user(user_input=None)

    assert flow.account_type == ACCOUNT_TYPE_DREAME
    assert result["step_id"] == "dreame"


# ---------------------------------------------------------------------------
# async_step_dreame (Dreame cloud login)
# ---------------------------------------------------------------------------


async def test_dreame_login_success_routes_to_devices(cloud_protocol) -> None:
    """A successful Dreame login leads to the device-selection step."""
    flow = _make_flow()
    cloud_protocol.cloud.logged_in = True
    cloud_protocol.cloud.get_supported_devices.return_value = (
        {"dev1": _dreame_device()},
        {},
    )

    result = await flow.async_step_dreame(user_input=_cloud_login_input())

    # A single supported device is auto-selected, so the flow falls through to
    # async_step_connect and then to the options form.
    assert flow.username == "user@example.com"
    assert flow.prefer_cloud is True
    cloud_protocol.cloud.login.assert_called_once()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "options"


async def test_dreame_login_failure_shows_login_error(cloud_protocol) -> None:
    """logged_in == False surfaces a login_error on the dreame form."""
    flow = _make_flow()
    cloud_protocol.cloud.logged_in = False

    result = await flow.async_step_dreame(user_input=_cloud_login_input())

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dreame"
    assert result["errors"]["base"] == "login_error"


async def test_dreame_credentials_incomplete(cloud_protocol) -> None:
    """Missing credentials never reach the cloud and report incomplete."""
    flow = _make_flow()

    result = await flow.async_step_dreame(user_input={CONF_USERNAME: "u", CONF_PASSWORD: "", CONF_COUNTRY: "eu"})

    assert result["errors"]["base"] == "credentials_incomplete"
    cloud_protocol.cloud.login.assert_not_called()


async def test_dreame_disconnects_previous_protocol(cloud_protocol) -> None:
    """A lingering protocol from a previous attempt is disconnected first."""
    flow = _make_flow()
    previous = MagicMock()
    flow.protocol = previous
    cloud_protocol.cloud.logged_in = False

    await flow.async_step_dreame(user_input=_cloud_login_input())

    previous.disconnect.assert_called_once()


async def test_dreame_no_devices_error_lists_unsupported() -> None:
    """The no_devices error renders the unsupported model names as placeholder."""
    flow = _make_flow()
    flow.unsupported_devices = {"u1": {"model": "dreame.vacuum.unknown1"}}

    result = await flow.async_step_dreame(error="no_devices")

    assert result["errors"]["base"] == "no_devices"
    assert "dreame.vacuum.unknown1" in result["description_placeholders"]["devices"]


async def test_dreame_error_placeholder_empty_for_other_errors() -> None:
    """A non-no_devices error keeps an empty devices placeholder."""
    flow = _make_flow()

    result = await flow.async_step_dreame(error="cannot_connect")

    assert result["errors"]["base"] == "cannot_connect"
    assert result["description_placeholders"]["devices"] == ""


async def test_mova_login_delegates_to_dreame(cloud_protocol) -> None:
    """The Mova step is a thin wrapper around the Dreame step."""
    flow = _make_flow(account_type="mova")
    cloud_protocol.cloud.logged_in = False

    result = await flow.async_step_mova(user_input=_cloud_login_input())

    # account_type stays mova -> step_id is mova on the rendered form.
    assert result["step_id"] == "mova"
    assert result["errors"]["base"] == "login_error"


# ---------------------------------------------------------------------------
# async_step_login dispatch
# ---------------------------------------------------------------------------


async def test_login_dispatch_mova_routes_to_mova_form() -> None:
    """async_step_login dispatches a mova account to the mova/dreame form."""
    flow = _make_flow(account_type="mova")

    result = await flow.async_step_login(error="cannot_connect")

    assert result["step_id"] == "mova"
    assert result["errors"]["base"] == "cannot_connect"


async def test_login_dispatch_local_routes_to_local_form() -> None:
    """async_step_login dispatches an unknown/local account to the local form."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_LOCAL)

    result = await flow.async_step_login(error="wrong_token")

    assert result["step_id"] == ACCOUNT_TYPE_LOCAL
    assert result["errors"]["base"] == "wrong_token"


async def test_mi_login_disconnects_previous_protocol(cloud_protocol) -> None:
    """A lingering protocol from a previous Mi attempt is disconnected first."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    previous = MagicMock()
    flow.protocol = previous
    cloud_protocol.cloud.logged_in = False
    cloud_protocol.cloud.captcha_img = None
    cloud_protocol.cloud.verification_url = None

    await flow.async_step_mi(user_input=_cloud_login_input())

    previous.disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# async_step_mi (Mi / Xiaomi cloud login) incl. captcha + 2FA
# ---------------------------------------------------------------------------


def _mi_device(mac: str = "AA:BB:CC:DD:EE:FF", model: str = "dreame.vacuum.p2009") -> dict:
    return {
        "mac": mac,
        "model": model,
        "name": "Mi Vacuum",
        "did": "1",
        "localip": "192.168.1.5",
        "token": "t" * 32,
    }


async def test_mi_login_success_routes_to_devices(cloud_protocol) -> None:
    """A clean Mi login (no captcha/2FA) reaches device selection."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    cloud_protocol.cloud.logged_in = True
    cloud_protocol.cloud.captcha_img = None
    cloud_protocol.cloud.verification_url = None
    # Two devices keep the flow on the selection form (no auto-connect).
    cloud_protocol.cloud.get_supported_devices.return_value = (
        {
            "dev1": _mi_device(mac="AA:BB:CC:DD:EE:01"),
            "dev2": _mi_device(mac="AA:BB:CC:DD:EE:02"),
        },
        {},
    )

    result = await flow.async_step_mi(user_input={**_cloud_login_input(), CONF_PREFER_CLOUD: True})

    cloud_protocol.cloud.login.assert_called_once()
    assert result["step_id"] == "devices"


async def test_mi_login_credentials_incomplete() -> None:
    """Incomplete Mi credentials short-circuit before any cloud call."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)

    result = await flow.async_step_mi(user_input={CONF_USERNAME: "", CONF_PASSWORD: "p", CONF_COUNTRY: "de"})

    assert result["step_id"] == ACCOUNT_TYPE_MI
    assert result["errors"]["base"] == "credentials_incomplete"


async def test_mi_login_failure(cloud_protocol) -> None:
    """logged_in == False produces login_error on the mi form."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    cloud_protocol.cloud.logged_in = False
    cloud_protocol.cloud.captcha_img = None
    cloud_protocol.cloud.verification_url = None

    result = await flow.async_step_mi(user_input=_cloud_login_input())

    assert result["errors"]["base"] == "login_error"


async def test_mi_login_requests_captcha(cloud_protocol) -> None:
    """A captcha image after login routes to the captcha step."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    cloud_protocol.cloud.captcha_img = "data:image/png;base64,AAAA"
    cloud_protocol.cloud.verification_url = None
    cloud_protocol.cloud.logged_in = False

    result = await flow.async_step_mi(user_input=_cloud_login_input())

    assert result["step_id"] == "captcha"
    assert result["description_placeholders"]["img"] == "data:image/png;base64,AAAA"


async def test_mi_login_requests_2fa(cloud_protocol) -> None:
    """A verification URL after login routes to the 2FA step."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    cloud_protocol.cloud.captcha_img = None
    cloud_protocol.cloud.verification_url = "https://verify.example"
    cloud_protocol.cloud.logged_in = False

    result = await flow.async_step_mi(user_input=_cloud_login_input())

    assert result["step_id"] == "2fa"
    assert result["description_placeholders"]["url"] == "https://verify.example"


async def test_mi_login_renders_form_with_error(cloud_protocol) -> None:
    """When called with a bare error, the mi form re-renders with it."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)

    result = await flow.async_step_mi(error="cannot_connect")

    assert result["step_id"] == ACCOUNT_TYPE_MI
    assert result["errors"]["base"] == "cannot_connect"


async def test_captcha_success_routes_to_devices(cloud_protocol) -> None:
    """A correct captcha that completes login goes to device selection."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.captcha_img = "img"
    cloud_protocol.cloud.logged_in = True
    cloud_protocol.cloud.verify_captcha.return_value = True
    cloud_protocol.cloud.get_supported_devices.return_value = (
        {
            "d1": _mi_device(mac="AA:BB:CC:DD:EE:01"),
            "d2": _mi_device(mac="AA:BB:CC:DD:EE:02"),
        },
        {},
    )

    result = await flow.async_step_captcha(user_input={"code": "1234"})

    cloud_protocol.cloud.verify_captcha.assert_called_once_with("1234")
    assert result["step_id"] == "devices"


async def test_captcha_success_but_then_2fa(cloud_protocol) -> None:
    """A captcha can be valid yet still require a follow-up 2FA challenge."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.captcha_img = "img"
    cloud_protocol.cloud.logged_in = False
    cloud_protocol.cloud.verification_url = "https://verify.example"
    cloud_protocol.cloud.verify_captcha.return_value = True

    result = await flow.async_step_captcha(user_input={"code": "1234"})

    assert result["step_id"] == "2fa"


async def test_captcha_success_but_not_logged_in_no_2fa(cloud_protocol) -> None:
    """A valid captcha with no login and no 2FA falls back to the mi form."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.captcha_img = "img"
    cloud_protocol.cloud.logged_in = False
    cloud_protocol.cloud.verification_url = None
    cloud_protocol.cloud.verify_captcha.return_value = True

    result = await flow.async_step_captcha(user_input={"code": "1234"})

    assert result["step_id"] == ACCOUNT_TYPE_MI
    assert result["errors"]["base"] == "login_error"


async def test_captcha_wrong_code(cloud_protocol) -> None:
    """An incorrect captcha re-renders the captcha form with wrong_captcha."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.captcha_img = "img"
    cloud_protocol.cloud.logged_in = False
    cloud_protocol.cloud.verify_captcha.return_value = False

    result = await flow.async_step_captcha(user_input={"code": "bad"})

    assert result["step_id"] == "captcha"
    assert result["errors"]["base"] == "wrong_captcha"


async def test_captcha_stale_state_returns_to_mi(cloud_protocol) -> None:
    """No captcha image and not logged in -> bounce back to the mi step."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.captcha_img = None
    cloud_protocol.cloud.logged_in = False

    result = await flow.async_step_captcha(user_input=None)

    assert result["step_id"] == ACCOUNT_TYPE_MI


async def test_2fa_success_routes_to_devices(cloud_protocol) -> None:
    """A correct 2FA code that completes login goes to device selection."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.verification_url = "https://verify.example"
    cloud_protocol.cloud.logged_in = True
    cloud_protocol.cloud.verify_code.return_value = True
    cloud_protocol.cloud.get_supported_devices.return_value = (
        {
            "d1": _mi_device(mac="AA:BB:CC:DD:EE:01"),
            "d2": _mi_device(mac="AA:BB:CC:DD:EE:02"),
        },
        {},
    )

    result = await flow.async_step_2fa(user_input={"verification_code": "000000"})

    cloud_protocol.cloud.verify_code.assert_called_once_with("000000")
    assert result["step_id"] == "devices"


async def test_2fa_success_but_not_logged_in(cloud_protocol) -> None:
    """A valid 2FA result without login returns to the mi form with login_error."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.verification_url = "https://verify.example"
    cloud_protocol.cloud.logged_in = False
    cloud_protocol.cloud.verify_code.return_value = True

    result = await flow.async_step_2fa(user_input={"verification_code": "000000"})

    assert result["step_id"] == ACCOUNT_TYPE_MI
    assert result["errors"]["base"] == "login_error"


async def test_2fa_wrong_code(cloud_protocol) -> None:
    """An invalid 2FA code re-renders the 2FA form with 2fa_failed."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.verification_url = "https://verify.example"
    cloud_protocol.cloud.logged_in = False
    cloud_protocol.cloud.verify_code.return_value = False

    result = await flow.async_step_2fa(user_input={"verification_code": "bad"})

    assert result["step_id"] == "2fa"
    assert result["errors"]["base"] == "2fa_failed"


async def test_2fa_stale_state_returns_to_mi(cloud_protocol) -> None:
    """No verification URL and not logged in -> bounce back to the mi step."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.verification_url = None
    cloud_protocol.cloud.logged_in = False

    result = await flow.async_step_2fa(user_input=None)

    assert result["step_id"] == ACCOUNT_TYPE_MI


# ---------------------------------------------------------------------------
# async_step_devices (device selection / get_supported_devices)
# ---------------------------------------------------------------------------


async def test_devices_no_supported_returns_no_devices(cloud_protocol) -> None:
    """An empty supported set surfaces the no_devices error on login."""
    flow = _make_flow()
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.get_supported_devices.return_value = ({}, {})

    result = await flow.async_step_devices(user_input=None)

    assert result["step_id"] == "dreame"
    assert result["errors"]["base"] == "no_devices"


async def test_devices_all_filtered_with_unsupported_returns_no_devices(cloud_protocol) -> None:
    """Supported devices all already configured + unsupported present -> no_devices."""
    flow = _make_flow()
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.get_supported_devices.return_value = (
        {"d": _dreame_device()},
        {"u": {"model": "dreame.vacuum.unknown"}},
    )
    # Mark the device as already configured so it is filtered out.
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = MagicMock()

    result = await flow.async_step_devices(user_input=None)

    assert result["step_id"] == "dreame"
    assert result["errors"]["base"] == "no_devices"


async def test_devices_all_filtered_no_unsupported_aborts_already_configured(cloud_protocol) -> None:
    """All supported devices configured and nothing unsupported -> already_configured."""
    flow = _make_flow()
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.get_supported_devices.return_value = (
        {"d": _dreame_device()},
        {},
    )
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = MagicMock()

    with pytest.raises(AbortFlow) as err:
        await flow.async_step_devices(user_input=None)

    assert err.value.reason == "already_configured"


async def test_devices_multiple_shows_selection_form(cloud_protocol) -> None:
    """Two selectable devices render the selection form."""
    flow = _make_flow()
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.get_supported_devices.return_value = (
        {
            "dev1": _dreame_device(mac="AA:BB:CC:DD:EE:01"),
            "dev2": _dreame_device(mac="AA:BB:CC:DD:EE:02"),
        },
        {},
    )

    result = await flow.async_step_devices(user_input=None)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "devices"
    assert set(flow.devices.keys()) == {"dev1", "dev2"}


async def test_devices_selection_extracts_info_and_connects(cloud_protocol) -> None:
    """Selecting a device extracts its info and proceeds to connect/options."""
    flow = _make_flow()
    flow.protocol = cloud_protocol
    flow.devices = {"dev1": _dreame_device()}

    result = await flow.async_step_devices(user_input={"devices": "dev1"})

    # Dreame extract_info path: token is space-filled, host from bindDomain.
    assert flow.token == " "
    assert flow.host == "192.168.1.100"
    assert flow.mac == "AA:BB:CC:DD:EE:FF"
    assert flow.device_id == "123456789"
    # customName populated -> used as name.
    assert flow.name == "My Vacuum"
    assert result["step_id"] == "options"


async def test_devices_reauth_keeps_already_configured_device(cloud_protocol) -> None:
    """During reauth, an already-configured device is not filtered out."""
    flow = _make_flow(reauth=True)
    flow.protocol = cloud_protocol
    cloud_protocol.cloud.get_supported_devices.return_value = (
        {
            "dev1": _dreame_device(mac="AA:BB:CC:DD:EE:01"),
            "dev2": _dreame_device(mac="AA:BB:CC:DD:EE:02"),
        },
        {},
    )
    # Even though these would normally match an existing entry, reauth bypasses
    # the per-device dedup filter, so both stay selectable.
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = MagicMock()

    result = await flow.async_step_devices(user_input=None)

    assert result["step_id"] == "devices"
    assert set(flow.devices.keys()) == {"dev1", "dev2"}


# ---------------------------------------------------------------------------
# async_step_connect
# ---------------------------------------------------------------------------


def _connect_ready_flow(cloud_protocol, *, account_type=ACCOUNT_TYPE_MI, model="dreame.vacuum.p2009"):
    """A flow primed so async_step_connect performs a real probe."""
    flow = _make_flow(account_type=account_type)
    flow.protocol = cloud_protocol
    flow.prefer_cloud = True
    flow.host = "192.168.1.100"
    flow.token = "t" * 32
    flow.username = "user@example.com"
    flow.password = "secret"
    flow.country = "eu"
    flow.device_id = "1"
    # connect() returns probe info for a supported model.
    cloud_protocol.connect = MagicMock(return_value={"mac": "AA:BB:CC:DD:EE:FF", "model": model})
    return flow


async def test_connect_success_supported_model_goes_to_options(cloud_protocol) -> None:
    """A successful probe for a supported model proceeds to the options step."""
    flow = _connect_ready_flow(cloud_protocol)

    result = await flow.async_step_connect()

    assert flow.mac == "AA:BB:CC:DD:EE:FF"
    assert flow.model == "dreame.vacuum.p2009"
    # Probe disconnects after connecting and a new protocol was constructed.
    cloud_protocol.disconnect.assert_called()
    assert result["step_id"] == "options"


async def test_connect_unsupported_model_returns_to_login(cloud_protocol) -> None:
    """A supported probe of an unknown model falls back to the login form."""
    flow = _connect_ready_flow(cloud_protocol, model="dreame.vacuum.notreal999")

    result = await flow.async_step_connect()

    # username+password set -> returns to login (mi) carrying the error.
    assert result["step_id"] == ACCOUNT_TYPE_MI
    assert result["errors"]["base"] == "unsupported"


async def test_connect_failure_cannot_connect_returns_to_login(cloud_protocol) -> None:
    """A raising probe yields cannot_connect and returns to login."""
    flow = _connect_ready_flow(cloud_protocol)
    cloud_protocol.connect = MagicMock(side_effect=OSError("boom"))

    result = await flow.async_step_connect()

    assert result["step_id"] == ACCOUNT_TYPE_MI
    assert result["errors"]["base"] == "cannot_connect"


async def test_connect_failure_without_credentials_goes_to_local(cloud_protocol) -> None:
    """A failed probe with no cloud creds drops to the local form."""
    flow = _connect_ready_flow(cloud_protocol)
    flow.username = None
    flow.password = None
    cloud_protocol.connect = MagicMock(side_effect=OSError("boom"))

    result = await flow.async_step_connect()

    assert result["step_id"] == ACCOUNT_TYPE_LOCAL
    assert result["errors"]["base"] == "cannot_connect"


async def test_connect_local_only_wrong_token() -> None:
    """A non-cloud flow with a short token reports wrong_token on the local form."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_LOCAL)
    flow.prefer_cloud = False
    flow.token = "short"
    flow.host = "192.168.1.50"

    result = await flow.async_step_connect()

    assert result["step_id"] == ACCOUNT_TYPE_LOCAL
    assert result["errors"]["base"] == "wrong_token"


async def test_connect_aborts_when_unique_id_already_configured(cloud_protocol) -> None:
    """A probe whose MAC matches an existing entry aborts already_configured."""
    flow = _connect_ready_flow(cloud_protocol)
    # The probe finds a MAC; an existing entry shares that unique id.
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = MagicMock()

    with pytest.raises(AbortFlow) as err:
        await flow.async_step_connect()

    assert err.value.reason == "already_configured"


async def test_connect_reauth_updates_entry_and_drops_password(cloud_protocol, monkeypatch) -> None:
    """Reauth success persists the new auth_key and removes the cleartext password."""
    flow = _connect_ready_flow(cloud_protocol)
    flow.reauth = True
    cloud_protocol.cloud.auth_key = "fresh_key"

    existing = SimpleNamespace(data=dict(_cloud_entry_data(include_password=True)))
    monkeypatch.setattr(flow, "_get_reauth_entry", lambda: existing)

    captured = {}

    def _update_reload_and_abort(entry, *, data):
        captured["entry"] = entry
        captured["data"] = data
        return {"type": FlowResultType.ABORT, "reason": "reauth_successful"}

    monkeypatch.setattr(flow, "async_update_reload_and_abort", _update_reload_and_abort)

    result = await flow.async_step_connect()

    assert result["reason"] == "reauth_successful"
    assert captured["data"][CONF_AUTH_KEY] == "fresh_key"
    # auth_key present -> password dropped.
    assert CONF_PASSWORD not in captured["data"]
    assert captured["data"][CONF_USERNAME] == "user@example.com"


async def test_connect_reauth_keeps_password_without_auth_key(cloud_protocol, monkeypatch) -> None:
    """Reauth with no server auth_key keeps the freshly entered password."""
    flow = _connect_ready_flow(cloud_protocol)
    flow.reauth = True
    flow.password = "newsecret"
    cloud_protocol.cloud.auth_key = None

    existing = SimpleNamespace(data=dict(_cloud_entry_data(include_password=True)))
    monkeypatch.setattr(flow, "_get_reauth_entry", lambda: existing)

    captured = {}

    def _update_reload_and_abort(entry, *, data):
        captured["data"] = data
        return {"type": FlowResultType.ABORT, "reason": "reauth_successful"}

    monkeypatch.setattr(flow, "async_update_reload_and_abort", _update_reload_and_abort)

    await flow.async_step_connect()

    assert captured["data"][CONF_AUTH_KEY] is None
    assert captured["data"][CONF_PASSWORD] == "newsecret"


# ---------------------------------------------------------------------------
# async_step_local
# ---------------------------------------------------------------------------


async def test_local_form_rendered_with_error() -> None:
    """The local form is rendered, carrying any propagated error."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_LOCAL)

    result = await flow.async_step_local(error="wrong_token")

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == ACCOUNT_TYPE_LOCAL
    assert result["errors"]["base"] == "wrong_token"
    assert "token_url" in result["description_placeholders"]


async def test_local_submit_proceeds_to_connect() -> None:
    """Submitting host+token clears the mac and probes via connect."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_LOCAL)
    flow.prefer_cloud = False  # short token -> wrong_token, but we only check routing

    result = await flow.async_step_local(user_input={CONF_HOST: "10.0.0.5", CONF_TOKEN: "x" * 10})

    assert flow.host == "10.0.0.5"
    assert flow.token == "x" * 10
    assert flow.mac is None
    # 10-char token (<32) with prefer_cloud False -> local form, wrong_token.
    assert result["step_id"] == ACCOUNT_TYPE_LOCAL
    assert result["errors"]["base"] == "wrong_token"


async def test_local_submit_aborts_on_duplicate() -> None:
    """A host+token matching an existing entry aborts already_configured."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_LOCAL)
    existing = SimpleNamespace(
        data={CONF_HOST: "10.0.0.5", CONF_TOKEN: "x" * 32},
        options={},
        source=SOURCE_USER,
        entry_id="other_entry",
    )
    flow.hass.config_entries.async_entries.return_value = [existing]

    with pytest.raises(AbortFlow) as err:
        await flow.async_step_local(user_input={CONF_HOST: "10.0.0.5", CONF_TOKEN: "x" * 32})

    assert err.value.reason == "already_configured"


# ---------------------------------------------------------------------------
# async_step_options (entry creation + defaults per model)
# ---------------------------------------------------------------------------


def _options_ready_flow(model: str, account_type: str = ACCOUNT_TYPE_DREAME, *, protocol: MagicMock | None = None):
    flow = _make_flow(account_type=account_type)
    flow.model = model
    flow.name = None
    flow.host = "192.168.1.100"
    flow.token = " "
    flow.username = "user@example.com"
    flow.password = "secret"
    flow.country = "eu"
    flow.mac = "AA:BB:CC:DD:EE:FF"
    flow.device_id = "1"
    flow.prefer_cloud = True
    if protocol is not None:
        flow.protocol = protocol
    return flow


async def test_options_form_dreame_recent_model() -> None:
    """A recent Dreame model (>=2215) does not hide name layers by default."""
    flow = _options_ready_flow("dreame.vacuum.p2259")

    result = await flow.async_step_options(user_input=None)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "options"
    schema = result["data_schema"].schema
    keys = {str(k.schema) for k in schema}
    assert CONF_COLOR_SCHEME in keys
    assert CONF_ICON_SET in keys
    assert CONF_LOW_RESOLUTION in keys
    # Default hidden objects empty for a recent model.
    defaults = {str(k.schema): k.default() for k in schema if k.default is not vol.UNDEFINED}
    assert defaults[CONF_HIDDEN_MAP_OBJECTS] == []
    assert defaults[CONF_COLOR_SCHEME] == "Dreame Light"


async def test_options_form_dreame_old_model_hides_names() -> None:
    """An older Dreame model (<2215) hides the name + name_background layers."""
    flow = _options_ready_flow("dreame.vacuum.p2009")

    result = await flow.async_step_options(user_input=None)

    schema = result["data_schema"].schema
    defaults = {str(k.schema): k.default() for k in schema if k.default is not vol.UNDEFINED}
    assert set(defaults[CONF_HIDDEN_MAP_OBJECTS]) == {"name", "name_background"}


async def test_options_form_mijia_model_uses_mijia_defaults() -> None:
    """A Mijia (models value == 1) device defaults to the Mijia palette."""
    flow = _options_ready_flow("xiaomi.vacuum.c102cn", account_type=ACCOUNT_TYPE_MI)

    result = await flow.async_step_options(user_input=None)

    schema = result["data_schema"].schema
    defaults = {str(k.schema): k.default() for k in schema if k.default is not vol.UNDEFINED}
    assert defaults[CONF_COLOR_SCHEME] == "Mijia Light"
    assert defaults[CONF_ICON_SET] == "Mijia"
    assert set(defaults[CONF_HIDDEN_MAP_OBJECTS]) == {"name_background", "icon"}


async def test_options_form_local_account_omits_map_options() -> None:
    """A local account does not expose the color/icon/map option fields."""
    flow = _options_ready_flow("dreame.vacuum.p2009", account_type=ACCOUNT_TYPE_LOCAL)

    result = await flow.async_step_options(user_input=None)

    schema = result["data_schema"].schema
    keys = {str(k.schema) for k in schema}
    assert CONF_NAME in keys
    assert CONF_NOTIFY in keys
    assert CONF_COLOR_SCHEME not in keys
    assert CONF_ICON_SET not in keys


async def test_options_submit_creates_entry() -> None:
    """Submitting the options form creates the config entry with the right data."""
    protocol = MagicMock()
    protocol.cloud.auth_key = "the_auth_key"
    flow = _options_ready_flow("dreame.vacuum.p2259", protocol=protocol)
    flow.name = "Living Room"

    result = await flow.async_step_options(
        user_input={
            CONF_NAME: "Living Room",
            CONF_NOTIFY: ["error"],
            CONF_COLOR_SCHEME: "Dreame Light",
            CONF_ICON_SET: "Dreame",
            CONF_HIDDEN_MAP_OBJECTS: [],
            CONF_SQUARE: False,
            CONF_LOW_RESOLUTION: False,
        }
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living Room"
    data = result["data"]
    assert data[CONF_HOST] == "192.168.1.100"
    assert data[CONF_AUTH_KEY] == "the_auth_key"
    assert data[CONF_ACCOUNT_TYPE] == ACCOUNT_TYPE_DREAME
    assert result["options"][CONF_NOTIFY] == ["error"]
    assert result["options"][CONF_VERSION] == VERSION
    assert result["options"][CONF_PREFER_CLOUD] is True


# ---------------------------------------------------------------------------
# Reauth confirm
# ---------------------------------------------------------------------------


async def test_reauth_confirm_shows_form_first() -> None:
    """The reauth confirm step first renders an empty confirmation form."""
    flow = _make_flow()

    result = await flow.async_step_reauth_confirm(user_input=None)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_confirm_proceeds_to_login(cloud_protocol) -> None:
    """Confirming reauth flips the reauth flag and starts the login flow."""
    flow = _make_flow()
    flow.username = "user@example.com"
    cloud_protocol.cloud.logged_in = False

    result = await flow.async_step_reauth_confirm(user_input={})

    assert flow.reauth is True
    # Dreame account -> dreame login form (reauth schema, username default kept).
    assert result["step_id"] == "dreame"


# ---------------------------------------------------------------------------
# extract_info (Mi vs Dreame) + login_schema variants
# ---------------------------------------------------------------------------


async def test_extract_info_mi_account() -> None:
    """The Mi extract path maps localip/token/did onto the flow state."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)
    flow.extract_info(
        {
            "localip": "10.0.0.9",
            "mac": "11:22:33:44:55:66",
            "model": "dreame.vacuum.p2009",
            "name": "Mi Bot",
            "token": "z" * 32,
            "did": "999",
        }
    )

    assert flow.host == "10.0.0.9"
    assert flow.token == "z" * 32
    assert flow.name == "Mi Bot"
    assert flow.device_id == "999"


async def test_extract_info_dreame_falls_back_to_display_name() -> None:
    """When customName is empty, the Dreame display name is used."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_DREAME)
    device = _dreame_device()
    device["customName"] = ""
    flow.extract_info(device)

    assert flow.name == "Dreame Test"
    assert flow.token == " "
    assert flow.host == "192.168.1.100"


async def test_login_schema_reauth_variant() -> None:
    """The reauth login schema only asks for username + password."""
    flow = _make_flow(reauth=True)
    flow.username = "user@example.com"

    keys = {str(k.schema) for k in flow.login_schema.schema}

    assert keys == {CONF_USERNAME, CONF_PASSWORD}


async def test_login_schema_mi_variant_includes_country_and_prefer_cloud() -> None:
    """The Mi login schema offers country + prefer_cloud toggles."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_MI)

    keys = {str(k.schema) for k in flow.login_schema.schema}

    assert CONF_COUNTRY in keys
    assert CONF_PREFER_CLOUD in keys


async def test_login_schema_dreame_variant() -> None:
    """The Dreame login schema offers username/password/country only."""
    flow = _make_flow(account_type=ACCOUNT_TYPE_DREAME)

    keys = {str(k.schema) for k in flow.login_schema.schema}

    assert keys == {CONF_USERNAME, CONF_PASSWORD, CONF_COUNTRY}
    assert CONF_PREFER_CLOUD not in keys


# ---------------------------------------------------------------------------
# async_remove (session teardown)
# ---------------------------------------------------------------------------


async def test_async_remove_disconnects_protocol() -> None:
    """async_remove releases the throwaway cloud session."""
    flow = _make_flow()
    protocol = MagicMock()
    flow.protocol = protocol

    flow.async_remove()

    protocol.disconnect.assert_called_once()
    assert flow.protocol is None


async def test_async_remove_swallows_disconnect_errors() -> None:
    """A failing disconnect during teardown must never raise."""
    flow = _make_flow()
    protocol = MagicMock()
    protocol.disconnect.side_effect = RuntimeError("already closed")
    flow.protocol = protocol

    flow.async_remove()  # must not raise

    assert flow.protocol is None


async def test_async_remove_noop_without_protocol() -> None:
    """async_remove is a no-op when no protocol was ever created."""
    flow = _make_flow()
    flow.protocol = None

    flow.async_remove()  # must not raise

    assert flow.protocol is None


async def test_async_get_options_flow_returns_handler() -> None:
    """The static options-flow factory returns the options handler."""
    entry = MagicMock()

    handler = DreameVacuumFlowHandler.async_get_options_flow(entry)

    assert isinstance(handler, DreameVacuumOptionsFlowHandler)


# ---------------------------------------------------------------------------
# Reconfigure confirm
# ---------------------------------------------------------------------------


async def test_reconfigure_confirm_updates_host(monkeypatch) -> None:
    """Submitting the reconfigure form updates the host and reloads."""
    flow = _make_flow()
    flow.host = "192.168.1.100"
    entry = SimpleNamespace(data=_cloud_entry_data())
    monkeypatch.setattr(flow, "_get_reconfigure_entry", lambda: entry)

    captured = {}

    def _update_reload_and_abort(target, *, data_updates):
        captured["data_updates"] = data_updates
        return {"type": FlowResultType.ABORT, "reason": "reconfigure_successful"}

    monkeypatch.setattr(flow, "async_update_reload_and_abort", _update_reload_and_abort)

    result = await flow.async_step_reconfigure_confirm(user_input={CONF_HOST: "192.168.1.200"})

    assert result["reason"] == "reconfigure_successful"
    assert captured["data_updates"][CONF_HOST] == "192.168.1.200"


# ---------------------------------------------------------------------------
# OptionsFlow
# ---------------------------------------------------------------------------


def _options_flow(*, username: str | None, account_type: str = ACCOUNT_TYPE_DREAME, options: dict | None = None):
    base_options = {
        CONF_NOTIFY: ["error"],
        CONF_COLOR_SCHEME: "Dreame Light",
    }
    if options:
        base_options.update(options)
    entry = SimpleNamespace(
        data={CONF_USERNAME: username, CONF_ACCOUNT_TYPE: account_type},
        options=base_options,
    )
    handler = DreameVacuumOptionsFlowHandler()
    handler.handler = "test-entry-id"
    handler.hass = _fake_hass()
    handler.hass.config_entries.async_get_known_entry.return_value = entry
    return handler


async def test_options_flow_cloud_account_full_schema() -> None:
    """A cloud (username) account exposes the full map-option schema."""
    handler = _options_flow(username="user@example.com")

    result = await handler.async_step_init(user_input=None)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    keys = {str(k.schema) for k in result["data_schema"].schema}
    assert CONF_NOTIFY in keys
    assert CONF_COLOR_SCHEME in keys
    assert CONF_ICON_SET in keys
    assert CONF_HIDDEN_MAP_OBJECTS in keys
    assert CONF_SQUARE in keys
    assert CONF_LOW_RESOLUTION in keys
    # Dreame account -> no prefer_cloud toggle.
    assert CONF_PREFER_CLOUD not in keys


async def test_options_flow_mi_account_adds_prefer_cloud() -> None:
    """A Mi account additionally exposes the prefer_cloud toggle."""
    handler = _options_flow(username="user@example.com", account_type=ACCOUNT_TYPE_MI)

    result = await handler.async_step_init(user_input=None)

    keys = {str(k.schema) for k in result["data_schema"].schema}
    assert CONF_PREFER_CLOUD in keys


async def test_options_flow_local_account_only_notify() -> None:
    """A local account (no username) only offers the notify selector."""
    handler = _options_flow(username=None)

    result = await handler.async_step_init(user_input=None)

    keys = {str(k.schema) for k in result["data_schema"].schema}
    assert keys == {CONF_NOTIFY}


async def test_options_flow_notify_bool_true_expands_to_all() -> None:
    """A legacy notify == True default expands to every notification key."""
    handler = _options_flow(username=None, options={CONF_NOTIFY: True})

    result = await handler.async_step_init(user_input=None)

    notify_key = next(k for k in result["data_schema"].schema if str(k.schema) == CONF_NOTIFY)
    assert notify_key.default() == list(NOTIFICATION.keys())


async def test_options_flow_notify_bool_false_expands_to_empty() -> None:
    """A legacy notify == False default expands to an empty selection."""
    handler = _options_flow(username=None, options={CONF_NOTIFY: False})

    result = await handler.async_step_init(user_input=None)

    notify_key = next(k for k in result["data_schema"].schema if str(k.schema) == CONF_NOTIFY)
    assert notify_key.default() == []


async def test_options_flow_submit_merges_options() -> None:
    """Submitting the options form merges new values onto the stored options."""
    handler = _options_flow(
        username="user@example.com",
        options={CONF_COLOR_SCHEME: "Dreame Dark", CONF_ICON_SET: "Dreame"},
    )

    result = await handler.async_step_init(user_input={CONF_NOTIFY: ["warning"], CONF_COLOR_SCHEME: "Dreame Light"})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    # New values override, untouched stored values are preserved.
    assert result["data"][CONF_NOTIFY] == ["warning"]
    assert result["data"][CONF_COLOR_SCHEME] == "Dreame Light"
    assert result["data"][CONF_ICON_SET] == "Dreame"
