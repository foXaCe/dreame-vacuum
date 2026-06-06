"""Tests for the availability / enabled-default tweaks.

Covers two user-requested behaviour changes:
- per-room (segment) selects/numbers ship disabled by default,
- progress sensors stay available (report a value when idle) instead of going
  "unavailable".
"""

from __future__ import annotations

from custom_components.dreame_vacuum.dreame import DreameVacuumProperty
from custom_components.dreame_vacuum.dreame.vacuum_types import PROPERTY_AVAILABILITY
from custom_components.dreame_vacuum.number import DreameVacuumSegmentNumberEntity
from custom_components.dreame_vacuum.select import DreameVacuumSegmentSelectEntity


def test_segment_entities_disabled_by_default() -> None:
    """Per-room selects/numbers ship disabled by default to avoid flooding the UI."""
    assert DreameVacuumSegmentSelectEntity.entity_registry_enabled_default.fget(None) is False
    assert DreameVacuumSegmentNumberEntity.entity_registry_enabled_default.fget(None) is False


def test_progress_sensors_not_gated() -> None:
    """cleaning/drying progress and task_type stay available (report a value when idle)."""
    for prop in (
        DreameVacuumProperty.CLEANING_PROGRESS,
        DreameVacuumProperty.DRYING_PROGRESS,
        DreameVacuumProperty.TASK_TYPE,
    ):
        assert prop.name not in PROPERTY_AVAILABILITY
