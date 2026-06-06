"""Tests for Dreame Vacuum logbook event descriptions."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_ICON,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)

from custom_components.dreame_vacuum.const import (
    DOMAIN,
    EVENT_CONSUMABLE,
    EVENT_DRAINAGE_STATUS,
    EVENT_ERROR,
    EVENT_INFORMATION,
    EVENT_LOW_WATER,
    EVENT_TASK_STATUS,
    EVENT_WARNING,
)
from custom_components.dreame_vacuum.logbook import async_describe_events


def _make_event(data: dict) -> MagicMock:
    """Return a fake Event whose .data is the supplied mapping."""
    event = MagicMock()
    event.data = data
    return event


def _collect_describers() -> dict[str, callable]:
    """Run async_describe_events and capture the registered describer callbacks.

    Returns a mapping of event_type -> describer function.
    """
    registered: dict[str, callable] = {}

    def _async_describe_event(domain: str, event_type: str, describer: callable) -> None:
        assert domain == DOMAIN
        registered[event_type] = describer

    async_describe_events(MagicMock(), _async_describe_event)
    return registered


def test_all_event_types_registered() -> None:
    """Every Dreame event type must be registered exactly once."""
    registered = _collect_describers()
    expected = {
        f"{DOMAIN}_{EVENT_TASK_STATUS}",
        f"{DOMAIN}_{EVENT_CONSUMABLE}",
        f"{DOMAIN}_{EVENT_WARNING}",
        f"{DOMAIN}_{EVENT_ERROR}",
        f"{DOMAIN}_{EVENT_LOW_WATER}",
        f"{DOMAIN}_{EVENT_INFORMATION}",
        f"{DOMAIN}_{EVENT_DRAINAGE_STATUS}",
    }
    assert set(registered) == expected


def test_describe_task_status() -> None:
    """Task status describer reflects the status field."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_TASK_STATUS}"]
    result = describe(_make_event({"status": "cleaning"}))
    assert result[LOGBOOK_ENTRY_NAME] == "Dreame Vacuum"
    assert result[LOGBOOK_ENTRY_MESSAGE] == "task status changed: cleaning"
    assert result[LOGBOOK_ENTRY_ICON] == "mdi:robot-vacuum"


def test_describe_task_status_missing_field() -> None:
    """Missing status field falls back to 'unknown'."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_TASK_STATUS}"]
    result = describe(_make_event({}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "task status changed: unknown"


def test_describe_consumable() -> None:
    """Consumable describer includes consumable name and remaining life."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_CONSUMABLE}"]
    result = describe(_make_event({EVENT_CONSUMABLE: "main_brush", "life_left": 12}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "consumable alert: main_brush (12% remaining)"
    assert result[LOGBOOK_ENTRY_ICON] == "mdi:alert-circle"


def test_describe_consumable_missing_fields() -> None:
    """Consumable describer defaults both fields to 'unknown'."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_CONSUMABLE}"]
    result = describe(_make_event({}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "consumable alert: unknown (unknown% remaining)"


def test_describe_warning() -> None:
    """Warning describer reflects the warning field."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_WARNING}"]
    result = describe(_make_event({EVENT_WARNING: "stuck"}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "warning: stuck"
    assert result[LOGBOOK_ENTRY_ICON] == "mdi:alert"


def test_describe_warning_missing_field() -> None:
    """Warning describer defaults to 'unknown'."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_WARNING}"]
    result = describe(_make_event({}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "warning: unknown"


def test_describe_error() -> None:
    """Error describer includes the error text and code."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_ERROR}"]
    result = describe(_make_event({EVENT_ERROR: "blocked", "code": 42}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "error: blocked (code: 42)"
    assert result[LOGBOOK_ENTRY_ICON] == "mdi:alert-octagon"


def test_describe_error_missing_fields() -> None:
    """Error describer defaults error to 'unknown' and code to empty."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_ERROR}"]
    result = describe(_make_event({}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "error: unknown (code: )"


def test_describe_low_water() -> None:
    """Low water describer reflects the low_water field."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_LOW_WATER}"]
    result = describe(_make_event({EVENT_LOW_WATER: "clean tank empty"}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "low water warning: clean tank empty"
    assert result[LOGBOOK_ENTRY_ICON] == "mdi:water-alert"


def test_describe_low_water_missing_field() -> None:
    """Low water describer defaults to 'unknown'."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_LOW_WATER}"]
    result = describe(_make_event({}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "low water warning: unknown"


def test_describe_information() -> None:
    """Information describer reflects the information field."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_INFORMATION}"]
    result = describe(_make_event({EVENT_INFORMATION: "dust_collection"}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "information: dust_collection"
    assert result[LOGBOOK_ENTRY_ICON] == "mdi:information"


def test_describe_information_missing_field() -> None:
    """Information describer defaults to 'unknown'."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_INFORMATION}"]
    result = describe(_make_event({}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "information: unknown"


def test_describe_drainage_status_completed() -> None:
    """Drainage describer reports 'completed' on success."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_DRAINAGE_STATUS}"]
    result = describe(_make_event({EVENT_DRAINAGE_STATUS: True}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "drainage completed"
    assert result[LOGBOOK_ENTRY_ICON] == "mdi:water-pump"


def test_describe_drainage_status_failed() -> None:
    """Drainage describer reports 'failed' when the flag is falsy."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_DRAINAGE_STATUS}"]
    result = describe(_make_event({EVENT_DRAINAGE_STATUS: False}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "drainage failed"


def test_describe_drainage_status_default_failed() -> None:
    """Drainage describer defaults to 'failed' when the flag is absent."""
    describe = _collect_describers()[f"{DOMAIN}_{EVENT_DRAINAGE_STATUS}"]
    result = describe(_make_event({}))
    assert result[LOGBOOK_ENTRY_MESSAGE] == "drainage failed"
