"""Repairs platform for Dreame Vacuum.

Provides the fix flow for actionable repair issues. The map-segment change
issue (``segments_changed``) is acknowledged through a simple confirmation:
once the user has reviewed their segment-based automations they submit the
flow, which dismisses the issue. Consumable-depleted issues are informational
(``is_fixable=False``) and are not handled here.

The MQTT TOFU fingerprint-change issue (``mqtt_fingerprint_changed_*``) uses
its own flow: the engine keeps trusting the old certificate until the user
explicitly re-trusts the new one here, which covers a legitimate vendor key
rotation without ever having blocked connectivity in the meantime.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import voluptuous as vol

from .const import CONF_MQTT_FINGERPRINTS
from .dreame.protocol import DreameVacuumDreameHomeCloudProtocol

_ISSUE_PREFIX_MQTT_FINGERPRINT = "mqtt_fingerprint_changed_"


class MqttFingerprintRepairFlow(RepairsFlow):
    """Fix flow for a changed MQTT broker TLS fingerprint.

    On submit, the new certificate's fingerprint becomes the trusted TOFU
    baseline (both for the running engine and persisted into the config
    entry) and the issue is dismissed.
    """

    def __init__(self, hass: HomeAssistant, data: dict[str, Any]) -> None:
        self.hass = hass
        self._data = data

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> FlowResult:
        """Handle the first step of the fix flow."""
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> FlowResult:
        """Handle the confirm step: re-trust the new certificate on submit."""
        if user_input is not None:
            entry_id = self._data.get("entry_id")
            key = self._data.get("key")
            fingerprint = self._data.get("fingerprint")
            entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
            if entry is not None and key and fingerprint:
                fingerprints = dict(entry.data.get(CONF_MQTT_FINGERPRINTS, {}))
                fingerprints[key] = fingerprint
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_MQTT_FINGERPRINTS: fingerprints},
                )
                DreameVacuumDreameHomeCloudProtocol.trust_mqtt_fingerprint(key, fingerprint)
            return self.async_create_entry(data={})

        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({}))


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow for a Dreame Vacuum repair issue."""
    if issue_id.startswith(_ISSUE_PREFIX_MQTT_FINGERPRINT):
        return MqttFingerprintRepairFlow(hass, data or {})
    return ConfirmRepairFlow()
