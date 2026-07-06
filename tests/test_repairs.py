"""Tests for the Dreame Vacuum repairs platform."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.components.repairs import ConfirmRepairFlow
from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.dreame_vacuum.const import CONF_MQTT_FINGERPRINTS
from custom_components.dreame_vacuum.dreame.protocol import DreameVacuumDreameHomeCloudProtocol
from custom_components.dreame_vacuum.repairs import (
    MqttFingerprintRepairFlow,
    async_create_fix_flow,
)


@pytest.fixture(autouse=True)
def _clear_mqtt_fingerprint_state() -> None:
    """Isolate the TOFU ClassVar cache (shared with protocol.py) between tests."""
    DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprints.clear()
    DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprint_listeners.clear()


async def test_create_fix_flow_returns_confirm_flow() -> None:
    """The fix flow for the segment-change issue is a simple confirmation."""
    flow = await async_create_fix_flow(MagicMock(), "segments_changed_AA:BB:CC:DD:EE:FF", None)
    assert isinstance(flow, ConfirmRepairFlow)


async def test_create_fix_flow_with_data() -> None:
    """A fix flow is returned regardless of issue_id / data payload."""
    flow = await async_create_fix_flow(MagicMock(), "segments_changed_x", {"foo": "bar"})
    assert isinstance(flow, ConfirmRepairFlow)


async def test_create_fix_flow_mqtt_fingerprint_returns_dedicated_flow() -> None:
    """A mqtt_fingerprint_changed_* issue gets the dedicated re-trust flow."""
    flow = await async_create_fix_flow(
        MagicMock(),
        "mqtt_fingerprint_changed_mqtt.example.com:8883",
        {"entry_id": "entry123", "key": "mqtt.example.com:8883", "fingerprint": "abc"},
    )
    assert isinstance(flow, MqttFingerprintRepairFlow)


async def test_mqtt_fingerprint_flow_shows_confirm_form_first() -> None:
    """With no user input yet, the flow shows the confirmation form."""
    flow = await async_create_fix_flow(
        MagicMock(),
        "mqtt_fingerprint_changed_key",
        {"entry_id": "entry123", "key": "key", "fingerprint": "abc"},
    )
    result = await flow.async_step_init()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "confirm"


async def test_mqtt_fingerprint_flow_confirm_retrusts_and_persists() -> None:
    """Submitting the confirm step updates the entry data, re-trusts the
    fingerprint on the running engine, and completes the flow."""
    entry = SimpleNamespace(
        entry_id="entry123",
        data={"host": "1.2.3.4", CONF_MQTT_FINGERPRINTS: {"mqtt.example.com:8883": "old-fingerprint"}},
    )
    hass = MagicMock()
    hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    flow = await async_create_fix_flow(
        hass,
        "mqtt_fingerprint_changed_mqtt.example.com:8883",
        {"entry_id": "entry123", "key": "mqtt.example.com:8883", "fingerprint": "new-fingerprint"},
    )
    result = await flow.async_step_confirm(user_input={})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    hass.config_entries.async_get_entry.assert_called_once_with("entry123")
    hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = hass.config_entries.async_update_entry.call_args
    assert kwargs["data"][CONF_MQTT_FINGERPRINTS] == {"mqtt.example.com:8883": "new-fingerprint"}
    assert DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprints["mqtt.example.com:8883"] == "new-fingerprint"


async def test_mqtt_fingerprint_flow_missing_entry_finishes_without_raising() -> None:
    """If the entry was removed in the meantime, the flow just finishes
    (no crash, no re-trust, no entry update)."""
    hass = MagicMock()
    hass.config_entries.async_get_entry = MagicMock(return_value=None)

    flow = await async_create_fix_flow(
        hass,
        "mqtt_fingerprint_changed_key",
        {"entry_id": "gone", "key": "key", "fingerprint": "abc"},
    )
    result = await flow.async_step_confirm(user_input={})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    hass.config_entries.async_update_entry.assert_not_called()
    assert "key" not in DreameVacuumDreameHomeCloudProtocol._mqtt_fingerprints


async def test_mqtt_fingerprint_flow_missing_entry_id_finishes_without_raising() -> None:
    """No entry_id in the issue data at all: still finishes cleanly."""
    hass = MagicMock()

    flow = await async_create_fix_flow(hass, "mqtt_fingerprint_changed_key", {})
    result = await flow.async_step_confirm(user_input={})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    hass.config_entries.async_get_entry.assert_not_called()
    hass.config_entries.async_update_entry.assert_not_called()
