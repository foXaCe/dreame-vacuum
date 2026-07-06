"""Tests for the integration-level entity service registration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import custom_components.dreame_vacuum as dreame_init
from custom_components.dreame_vacuum.const import DOMAIN
import custom_components.dreame_vacuum.services as services_mod
from custom_components.dreame_vacuum.services import async_register_services


def _register_all() -> list:
    """Run async_register_services against a mock hass, return the call list."""
    hass = MagicMock()
    with patch.object(services_mod, "async_register_platform_entity_service") as reg:
        async_register_services(hass)
    return reg.call_args_list


def test_registers_expected_service_count() -> None:
    """36 vacuum + 4 select + 1 camera services are registered."""
    calls = _register_all()
    assert len(calls) == 41
    domains = [c.kwargs["entity_domain"] for c in calls]
    assert domains.count("vacuum") == 36
    assert domains.count("select") == 4
    assert domains.count("camera") == 1


def test_all_services_use_integration_domain() -> None:
    """Every service is registered under the dreame_vacuum domain."""
    for call in _register_all():
        assert call.args[1] == DOMAIN


def test_anchor_service_names_and_methods() -> None:
    """Known services map to the expected entity method names."""
    by_name = {c.args[2]: c for c in _register_all()}
    expected = {
        "vacuum_clean_zone": ("vacuum", "async_clean_zone"),
        "vacuum_clean_segment": ("vacuum", "async_clean_segment"),
        "vacuum_goto": ("vacuum", "async_goto"),
        "vacuum_merge_segments": ("vacuum", "async_merge_segments"),
        "vacuum_set_property": ("vacuum", "async_set_property"),
        "vacuum_call_action": ("vacuum", "async_call_action"),
        "vacuum_delete_schedule": ("vacuum", "async_delete_schedule"),
        "vacuum_set_schedule": ("vacuum", "async_set_schedule"),
        "select_select_first": ("select", "async_first"),
        "select_select_next": ("select", "async_next"),
        "update": ("camera", "async_update"),
    }
    for name, (entity_domain, func) in expected.items():
        call = by_name[name]
        assert call.kwargs["entity_domain"] == entity_domain
        assert call.kwargs["func"] == func


def test_every_func_is_an_async_method_name() -> None:
    """Methods are referenced by name; all follow the async_* convention."""
    for call in _register_all():
        assert isinstance(call.kwargs["func"], str)
        assert call.kwargs["func"].startswith("async_")


def test_service_names_match_services_yaml() -> None:
    """Every registered service (except camera update) is declared in services.yaml."""
    from pathlib import Path

    import yaml

    services_yaml = yaml.safe_load(Path("custom_components/dreame_vacuum/services.yaml").read_text())
    for call in _register_all():
        name = call.args[2]
        if name == "update":
            continue
        assert name in services_yaml, f"service {name} absent de services.yaml"


async def test_async_setup_registers_services() -> None:
    """The integration's async_setup wires the service registration."""
    hass = MagicMock()
    with patch.object(dreame_init, "async_register_services") as reg:
        result = await dreame_init.async_setup(hass, {})

    assert result is True
    reg.assert_called_once_with(hass)
