"""Config flow for Dreame Vacuum."""

from __future__ import annotations

import base64
from collections.abc import Mapping
import json
import re
from typing import Any
import zlib

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .const import (
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
    CONF_VECTOR_ROOMS,
    CONF_VERSION,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    LOGGER,
    MAP_OBJECTS,
    NOTIFICATION,
    get_notification_labels,
)
from .dreame import DEVICE_INFO, MAP_COLOR_SCHEME_LIST, MAP_ICON_SET_LIST, VERSION, DreameVacuumProtocol

_TEXT = TextSelector()
_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_BOOL = BooleanSelector()


def _select(options: list[str]) -> SelectSelector:
    """Return a dropdown selector over plain string options."""
    return SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN))


def _multi_select(options: dict[str, str]) -> SelectSelector:
    """Return a multi-select selector from a value -> label mapping."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(value=value, label=label) for value, label in options.items()],
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


# Account type constants
# New integrations will use DREAME only, but keep others for backward compatibility
ACCOUNT_TYPE_DREAME = "dreame"
ACCOUNT_TYPE_MOVA = "mova"  # Keep for backward compatibility with existing configs
ACCOUNT_TYPE_MI = "mi"  # Keep for backward compatibility with existing configs
ACCOUNT_TYPE_LOCAL = "local"  # Keep for backward compatibility with existing configs


class DreameVacuumOptionsFlowHandler(OptionsFlowWithReload):
    """Handle Dreame Vacuum options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage Dreame Vacuum options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.config_entry.options, **user_input})

        notify = self.config_entry.options[CONF_NOTIFY]
        if isinstance(notify, bool):
            if notify is True:
                notify = list(NOTIFICATION.keys())
            else:
                notify = []

        notification_labels = get_notification_labels(self.hass.config.language)
        data_schema = vol.Schema({vol.Required(CONF_NOTIFY, default=notify): _multi_select(notification_labels)})
        if self.config_entry.data[CONF_USERNAME]:
            data_schema = data_schema.extend(
                {
                    vol.Required(CONF_COLOR_SCHEME, default=self.config_entry.options[CONF_COLOR_SCHEME]): _select(
                        list(MAP_COLOR_SCHEME_LIST.keys())
                    ),
                    vol.Required(
                        CONF_ICON_SET,
                        default=self.config_entry.options.get(CONF_ICON_SET, next(iter(MAP_ICON_SET_LIST))),
                    ): _select(list(MAP_ICON_SET_LIST.keys())),
                    vol.Required(
                        CONF_HIDDEN_MAP_OBJECTS,
                        default=self.config_entry.options.get(CONF_HIDDEN_MAP_OBJECTS, []),
                    ): _multi_select(MAP_OBJECTS),
                    vol.Required(CONF_SQUARE, default=self.config_entry.options.get(CONF_SQUARE, False)): _BOOL,
                    vol.Required(
                        CONF_VECTOR_ROOMS,
                        default=self.config_entry.options.get(CONF_VECTOR_ROOMS, True),
                    ): _BOOL,
                    vol.Required(
                        CONF_LOW_RESOLUTION,
                        default=self.config_entry.options.get(CONF_LOW_RESOLUTION, False),
                    ): _BOOL,
                }
            )
            if self.config_entry.data.get(CONF_ACCOUNT_TYPE, ACCOUNT_TYPE_MI) == ACCOUNT_TYPE_MI:
                data_schema = data_schema.extend(
                    {
                        vol.Required(
                            CONF_PREFER_CLOUD,
                            default=self.config_entry.options.get(CONF_PREFER_CLOUD, True),
                        ): _BOOL,
                    }
                )

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
        )


class DreameVacuumFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle config flow for an Dreame Vacuum device."""

    VERSION = CONFIG_ENTRY_VERSION

    def __init__(self) -> None:
        """Initialize."""
        self.entry: ConfigEntry | None = None
        self.mac: str | None = None
        self.model = None
        self.host: str | None = None
        self.token: str | None = None
        self.name: str | None = None
        self.username: str | None = None
        self.password: str | None = None
        self.country: str = "eu"
        self.account_type: str = ACCOUNT_TYPE_MI
        self.device_id: int | None = None
        self.prefer_cloud: bool = True
        self.low_resolution: bool = False
        self.square: bool = False
        self.options: dict[str, Any] = {}
        self.protocol: DreameVacuumProtocol | None = None
        self.models: dict[str, int] | None = None
        self.devices: dict[str, Any] | None = None
        self.unsupported_devices: dict[str, Any] | None = None
        self.reauth: bool = False

    @callback
    def async_remove(self) -> None:
        """Close the throwaway cloud session when the flow ends.

        Called by HA on every flow termination (create entry, abort, reauth,
        reconfigure) and on user cancellation, so the requests Session opened
        during login is always released instead of leaking its connection pool
        until garbage collection.
        """
        if self.protocol is not None:
            try:
                self.protocol.disconnect()
            except Exception:  # teardown must never raise
                LOGGER.debug("Failed to close config flow cloud session", exc_info=True)
            self.protocol = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> DreameVacuumOptionsFlowHandler:
        """Get the options flow for this handler."""
        return DreameVacuumOptionsFlowHandler()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        if self._async_in_progress():
            return self.async_abort(reason="already_in_progress")

        # Always use Dreame account type
        self.account_type = ACCOUNT_TYPE_DREAME
        return await self.async_step_login()

    async def async_step_reauth(self, user_input: Mapping[str, Any]) -> ConfigFlowResult:
        """Perform reauth upon an authentication error or missing cloud credentials."""
        self.name = user_input[CONF_NAME]
        self.host = user_input[CONF_HOST]
        self.token = user_input[CONF_TOKEN]
        self.username = user_input[CONF_USERNAME]
        self.password = user_input.get(CONF_PASSWORD)
        self.country = user_input[CONF_COUNTRY]
        self.account_type = user_input.get(CONF_ACCOUNT_TYPE, ACCOUNT_TYPE_MI)
        self.device_id = user_input.get(CONF_DID)
        self.mac = user_input.get(CONF_MAC)
        self.prefer_cloud = True  # Only for reauth
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        if user_input is not None:
            self.reauth = True
            return await self.async_step_login()
        return self.async_show_form(step_id="reauth_confirm")

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        reconfigure_entry = self._get_reconfigure_entry()
        self.name = reconfigure_entry.data[CONF_NAME]
        self.host = reconfigure_entry.data[CONF_HOST]
        self.token = reconfigure_entry.data[CONF_TOKEN]
        self.username = reconfigure_entry.data[CONF_USERNAME]
        self.password = reconfigure_entry.data.get(CONF_PASSWORD)
        self.country = reconfigure_entry.data[CONF_COUNTRY]
        self.account_type = reconfigure_entry.data.get(CONF_ACCOUNT_TYPE, ACCOUNT_TYPE_MI)
        self.device_id = reconfigure_entry.data.get(CONF_DID)
        self.mac = reconfigure_entry.data.get(CONF_MAC)
        return await self.async_step_reconfigure_confirm()

    async def async_step_reconfigure_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle reconfiguration confirmation."""
        errors: dict[str, str] = {}
        if user_input is not None:
            reconfigure_entry = self._get_reconfigure_entry()
            new_host = user_input.get(CONF_HOST, self.host)

            return self.async_update_reload_and_abort(
                reconfigure_entry,
                data_updates={CONF_HOST: new_host},
            )

        return self.async_show_form(
            step_id="reconfigure_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self.host): _TEXT,
                }
            ),
            errors=errors,
        )

    async def async_step_connect(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Connect to a Dreame Vacuum device."""
        error = None
        if self.prefer_cloud or (self.token and len(self.token) == 32):
            try:
                if self.account_type not in (ACCOUNT_TYPE_DREAME, ACCOUNT_TYPE_MOVA):
                    if self.protocol is not None:
                        self.protocol.disconnect()

                    self.protocol = DreameVacuumProtocol(
                        self.host,
                        self.token,
                        self.username,
                        self.password,
                        self.country,
                        self.prefer_cloud,
                        self.account_type,
                        str(self.device_id) if self.device_id is not None else None,
                        self.protocol.cloud.auth_key if self.protocol and self.protocol.cloud else None,
                    )

                    info = await self.hass.async_add_executor_job(self.protocol.connect, None, None, 3)
                    if info:
                        self.mac = info["mac"]
                        self.model = info["model"]

                    self.protocol.disconnect()
            except Exception:
                LOGGER.debug("Probe connection to device failed", exc_info=True)
                error = "cannot_connect"
            else:
                if self.reauth:
                    reauth_entry = self._get_reauth_entry()
                    new_auth_key = self.protocol.cloud.auth_key if self.protocol and self.protocol.cloud else None
                    # Rebuild the full data mapping from the existing entry so we
                    # can DROP a key (data_updates can only add/override). Once we
                    # hold a server-issued auth_key the cleartext password is no
                    # longer needed: stay consistent with the coordinator storage
                    # hardening and never re-persist it. Without an auth_key we
                    # keep the freshly entered password so reconnection still works.
                    data = dict(reauth_entry.data)
                    data[CONF_USERNAME] = self.username
                    data[CONF_HOST] = self.host
                    data[CONF_TOKEN] = self.token
                    data[CONF_AUTH_KEY] = new_auth_key
                    if new_auth_key:
                        data.pop(CONF_PASSWORD, None)
                    else:
                        data[CONF_PASSWORD] = self.password
                    return self.async_update_reload_and_abort(
                        reauth_entry,
                        data=data,
                    )

                if self.mac:
                    await self.async_set_unique_id(format_mac(self.mac))
                    self._abort_if_unique_id_configured(
                        updates={
                            CONF_HOST: self.host,
                            CONF_TOKEN: self.token,
                            CONF_MAC: self.mac,
                            CONF_DID: self.device_id,
                        }
                    )

                self.load_devices()
                if self.models and self.model in self.models:
                    if self.name is None:
                        self.name = self.model
                    return await self.async_step_options()
                error = "unsupported"

            if self.username and self.password:
                return await self.async_step_login(error=error)
        else:
            error = "wrong_token"
        return await self.async_step_local(error=error)

    async def async_step_local(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if errors is None:
            errors = {}
        if user_input is not None:
            self._async_abort_entries_match(user_input)

            self.host = user_input[CONF_HOST]
            self.token = user_input[CONF_TOKEN]
            self.mac = None
            return await self.async_step_connect()
        if error:
            errors["base"] = error

        return self.async_show_form(
            step_id=ACCOUNT_TYPE_LOCAL,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self.host): _TEXT,
                    vol.Required(CONF_TOKEN, default=self.token): _TEXT,
                }
            ),
            description_placeholders={
                "token_url": "https://www.home-assistant.io/integrations/xiaomi_miio#retrieving-the-access-token"
            },
            errors=errors,
        )

    async def async_step_login(self, error: str | None = None) -> ConfigFlowResult:
        """Dispatch to the login step matching the selected account type."""
        if self.account_type == ACCOUNT_TYPE_MI:
            return await self.async_step_mi(error=error)
        if self.account_type == ACCOUNT_TYPE_DREAME:
            return await self.async_step_dreame(error=error)
        if self.account_type == ACCOUNT_TYPE_MOVA:
            return await self.async_step_mova(error=error)
        return await self.async_step_local(error=error)

    async def async_step_mi(
        self, user_input: dict[str, Any] | None = None, errors: dict[str, Any] | None = None, error: str | None = None
    ) -> ConfigFlowResult:
        """Configure a dreame vacuum device through the Miio Cloud."""
        if errors is None:
            errors = {}
        if user_input is not None:
            username = user_input.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD)
            country = user_input.get(CONF_COUNTRY, self.country)

            if username and password and country:
                self.username = username
                self.password = password
                self.country = country
                self.prefer_cloud = user_input.get(CONF_PREFER_CLOUD, self.prefer_cloud)

                if self.protocol is not None:
                    self.protocol.disconnect()

                self.protocol = DreameVacuumProtocol(
                    username=self.username,
                    password=self.password,
                    country=self.country,
                    prefer_cloud=self.prefer_cloud,
                    account_type=self.account_type,
                )

                await self.hass.async_add_executor_job(self.protocol.cloud.login)

                if self.protocol.cloud.captcha_img is not None:
                    return await self.async_step_captcha()
                if self.protocol.cloud.verification_url is not None:
                    return await self.async_step_2fa()
                if self.protocol.cloud.logged_in is False:
                    errors["base"] = "login_error"
                elif self.protocol.cloud.logged_in:
                    return await self.async_step_devices()
            else:
                errors["base"] = "credentials_incomplete"
        elif error:
            errors["base"] = error

        return self.async_show_form(
            step_id=self.account_type,
            data_schema=self.login_schema,
            description_placeholders={
                "devices": "",
                "server_url": "https://www.openhab.org/addons/bindings/miio/#country-servers",
            },
            errors=errors,
        )

    async def async_step_2fa(
        self, user_input: dict[str, Any] | None = None, errors: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the two-factor authentication verification step."""
        if errors is None:
            errors = {}
        assert self.protocol is not None  # set during the login flow before reaching 2FA
        if self.protocol.cloud.verification_url is None and not self.protocol.cloud.logged_in:
            return await self.async_step_mi()

        if user_input is not None:
            verification_code = user_input.get("verification_code")
            result = await self.hass.async_add_executor_job(self.protocol.cloud.verify_code, verification_code)
            if result:
                if not self.protocol.cloud.logged_in:
                    return await self.async_step_mi(user_input=None, error="login_error")
                return await self.async_step_devices()
            errors["base"] = "2fa_failed"

        return self.async_show_form(
            step_id="2fa",
            data_schema=vol.Schema(
                {
                    vol.Required("verification_code"): _TEXT,
                }
            ),
            description_placeholders={"url": self.protocol.cloud.verification_url or ""},
            errors=errors,
        )

    async def async_step_captcha(
        self, user_input: dict[str, Any] | None = None, errors: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the captcha verification step."""
        if errors is None:
            errors = {}
        assert self.protocol is not None  # set during the login flow before reaching captcha
        if self.protocol.cloud.captcha_img is None and not self.protocol.cloud.logged_in:
            return await self.async_step_mi()

        if user_input is not None:
            code = user_input.get("code")
            result = await self.hass.async_add_executor_job(self.protocol.cloud.verify_captcha, code)
            if result:
                if not self.protocol.cloud.logged_in:
                    if self.protocol.cloud.verification_url is not None:
                        return await self.async_step_2fa()
                    return await self.async_step_mi(user_input=None, error="login_error")
                return await self.async_step_devices()
            errors["base"] = "wrong_captcha"

        return self.async_show_form(
            step_id="captcha",
            data_schema=vol.Schema(
                {
                    vol.Required("code"): _TEXT,
                }
            ),
            description_placeholders={"img": self.protocol.cloud.captcha_img or ""},
            errors=errors,
        )

    async def async_step_dreame(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ConfigFlowResult:
        """Configure a dreame vacuum device through the Dreame Cloud."""
        if errors is None:
            errors = {}
        description_placeholders = {}
        if user_input is not None:
            username = user_input.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD)
            country = user_input.get(CONF_COUNTRY, self.country)

            if username and password and country:
                self.username = username
                self.password = password
                self.country = country
                self.prefer_cloud = True

                if self.protocol is not None:
                    self.protocol.disconnect()

                self.protocol = DreameVacuumProtocol(
                    username=self.username,
                    password=self.password,
                    country=self.country,
                    prefer_cloud=self.prefer_cloud,
                    account_type=self.account_type,
                )
                await self.hass.async_add_executor_job(self.protocol.cloud.login)

                if self.protocol.cloud.logged_in is False:
                    errors["base"] = "login_error"
                elif self.protocol.cloud.logged_in:
                    return await self.async_step_devices()
            else:
                errors["base"] = "credentials_incomplete"
        elif error:
            errors["base"] = error
            devices = ""
            if error == "no_devices" and self.unsupported_devices:
                for device in self.unsupported_devices.values():
                    devices = f"{devices} ({device.get('model', 'unknown')})"

            description_placeholders = {"devices": devices}

        return self.async_show_form(
            step_id=self.account_type,
            data_schema=self.login_schema,
            description_placeholders=description_placeholders,
            errors=errors,
        )

    async def async_step_mova(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ConfigFlowResult:
        """Configure a dreame vacuum device through the Mova Cloud."""
        return await self.async_step_dreame(user_input, errors, error)

    async def async_step_devices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle Dreame Vacuum devices found."""
        assert self.protocol is not None  # set during the login flow before device selection

        if user_input is None:
            if not self.devices:
                self.load_devices()
                supported_devices, self.unsupported_devices = await self.hass.async_add_executor_job(
                    self.protocol.cloud.get_supported_devices, self.models, self.host, self.mac
                )
                if not supported_devices:
                    return await self.async_step_login(error="no_devices")

                self.devices = {}
                for k, v in supported_devices.items():
                    if self.reauth or not self.hass.config_entries.async_entry_for_domain_unique_id(
                        self.handler, format_mac(v["mac"])
                    ):
                        self.devices[k] = v

                if not self.devices:
                    if self.unsupported_devices:
                        return await self.async_step_login(error="no_devices")
                    raise AbortFlow("already_configured")

                if len(self.devices) == 1:
                    user_input = {"devices": next(iter(self.devices.keys()))}

        assert self.devices is not None  # populated above (or in a prior step) before selection
        if user_input is not None:
            self.extract_info(self.devices[user_input["devices"]])
            return await self.async_step_connect()

        return self.async_show_form(
            step_id="devices",
            data_schema=vol.Schema({vol.Required("devices"): _select(list(self.devices))}),
            errors={},
        )

    async def async_step_options(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle Dreame Vacuum options step."""

        if user_input is not None:
            self.name = user_input[CONF_NAME]
            self.options = {
                CONF_NOTIFY: user_input[CONF_NOTIFY],
                CONF_COLOR_SCHEME: user_input.get(CONF_COLOR_SCHEME),
                CONF_ICON_SET: user_input.get(CONF_ICON_SET),
                CONF_HIDDEN_MAP_OBJECTS: user_input.get(CONF_HIDDEN_MAP_OBJECTS),
                CONF_SQUARE: user_input.get(CONF_SQUARE),
                CONF_VECTOR_ROOMS: user_input.get(CONF_VECTOR_ROOMS, True),
                CONF_LOW_RESOLUTION: user_input.get(CONF_LOW_RESOLUTION),
                CONF_PREFER_CLOUD: self.prefer_cloud,
            }

            return self.async_create_entry(
                title=self.name,
                data={
                    CONF_NAME: self.name,
                    CONF_HOST: self.host,
                    CONF_TOKEN: self.token,
                    CONF_USERNAME: self.username,
                    CONF_PASSWORD: self.password,
                    CONF_COUNTRY: self.country,
                    CONF_MAC: self.mac,
                    CONF_DID: self.device_id,
                    CONF_AUTH_KEY: self.protocol.cloud.auth_key if self.protocol and self.protocol.cloud else None,
                    CONF_ACCOUNT_TYPE: self.account_type,
                },
                options=self.options | {CONF_VERSION: VERSION},
            )

        notification_labels = get_notification_labels(self.hass.config.language)
        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=self.name): _TEXT,
                vol.Required(CONF_NOTIFY, default=list(NOTIFICATION.keys())): _multi_select(notification_labels),
            }
        )

        self.load_devices()
        hidden_map_objects: list[str] = []
        assert self.models is not None
        assert self.model is not None
        if self.models[self.model] == 1:
            default_color_scheme = "Mijia Light"
            default_icon_set = "Mijia"
            hidden_map_objects.append("name_background")
            hidden_map_objects.append("icon")
        else:
            default_color_scheme = "Dreame Light"
            default_icon_set = "Dreame"
            model = re.sub(r"[^0-9]", "", self.model)
            if not (model.isnumeric() and int(model) >= 2215):
                hidden_map_objects.append("name_background")
                hidden_map_objects.append("name")

        if self.account_type != ACCOUNT_TYPE_LOCAL:
            data_schema = data_schema.extend(
                {
                    vol.Required(CONF_COLOR_SCHEME, default=default_color_scheme): _select(
                        list(MAP_COLOR_SCHEME_LIST.keys())
                    ),
                    vol.Required(CONF_ICON_SET, default=default_icon_set): _select(list(MAP_ICON_SET_LIST.keys())),
                    vol.Required(CONF_HIDDEN_MAP_OBJECTS, default=hidden_map_objects): _multi_select(MAP_OBJECTS),
                    vol.Required(CONF_SQUARE, default=False): _BOOL,
                    vol.Required(CONF_VECTOR_ROOMS, default=True): _BOOL,
                    vol.Required(CONF_LOW_RESOLUTION, default=False): _BOOL,
                }
            )

        return self.async_show_form(step_id="options", data_schema=data_schema, errors={})

    def extract_info(self, device_info: dict[str, Any]) -> None:
        """Extract the device info."""

        if self.account_type == ACCOUNT_TYPE_MI:
            if self.host is None:
                self.host = device_info["localip"]
            if self.mac is None:
                self.mac = device_info["mac"]
            if self.model is None:
                self.model = device_info["model"]
            if self.name is None:
                self.name = device_info["name"]
            self.token = device_info["token"]
            self.device_id = device_info["did"]
        elif self.account_type in (ACCOUNT_TYPE_DREAME, ACCOUNT_TYPE_MOVA):
            if self.token is None:
                self.token = " "
            if self.host is None:
                self.host = device_info["bindDomain"]
            if self.mac is None:
                self.mac = device_info["mac"]
            if self.model is None:
                self.model = device_info["model"]
            if self.name is None:
                self.name = (
                    device_info["customName"] if device_info["customName"] else device_info["deviceInfo"]["displayName"]
                )
            self.device_id = device_info["did"]

    def load_devices(self) -> None:
        """Lazily load the bundled model-to-name mapping."""
        if self.models is None:
            self.models = {}
            device_info = json.loads(zlib.decompress(base64.b64decode(DEVICE_INFO), zlib.MAX_WBITS | 32))
            for k in device_info[3]:
                info = device_info[0][device_info[3][k]]
                if info:
                    account_type = (
                        "xiaomi" if info[0] == 1 else ACCOUNT_TYPE_MOVA if info[0] == 2 else ACCOUNT_TYPE_DREAME
                    )
                    self.models[f"{account_type}.vacuum.{k}"] = info[1]

    @property
    def login_schema(self) -> vol.Schema:
        """Return the login form schema matching the reauth state and account type."""
        if self.reauth:
            return vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=self.username): _TEXT,
                    vol.Required(CONF_PASSWORD): _PASSWORD,
                }
            )

        if self.account_type == ACCOUNT_TYPE_MI:
            return vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=self.username): _TEXT,
                    vol.Required(CONF_PASSWORD): _PASSWORD,
                    vol.Required(CONF_COUNTRY, default=("de" if self.country == "eu" else self.country)): _select(
                        ["de", "cn", "us", "ru", "tw", "sg", "in", "i2"]
                    ),
                    vol.Optional(CONF_PREFER_CLOUD, default=self.prefer_cloud): _BOOL,
                }
            )

        return vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=self.username): _TEXT,
                vol.Required(CONF_PASSWORD): _PASSWORD,
                vol.Required(CONF_COUNTRY, default=self.country): _select(["eu", "cn", "us", "ru", "sg"]),
            }
        )
