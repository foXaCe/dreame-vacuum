"""Characterization tests for DreameVacuumDeviceSettersMixin.

Strategy: a minimal host class that inherits only the setters mixin, with
collaborator methods/attributes (``schedule_update``, ``_update_property``,
``_protocol``, ``property_mapping``...) supplied per test via plain mocks or
``SimpleNamespace``. This isolates the mixin's own decision logic (optimistic
update + rollback, reflection-based dispatch, HH:MM validation, typed
setters) from the rest of the real ``DreameVacuumDevice`` machinery.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY, MagicMock, call

import pytest

from custom_components.dreame_vacuum.dreame.device_setters import DreameVacuumDeviceSettersMixin
from custom_components.dreame_vacuum.dreame.exceptions import (
    DeviceException,
    DeviceUpdateFailedException,
    InvalidActionException,
    InvalidValueException,
)
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    DreameVacuumAction,
    DreameVacuumAIProperty,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumCleanGenius,
    DreameVacuumCleaningMode,
    DreameVacuumProperty,
    DreameVacuumSelfCleanFrequency,
    DreameVacuumStrAIProperty,
    DreameVacuumSuctionLevel,
    DreameVacuumWaterVolume,
    GoToZoneSettings,
)

# ---------------------------------------------------------------------------
# Host + builder
# ---------------------------------------------------------------------------


class _Host(DreameVacuumDeviceSettersMixin):
    """Minimal host exposing only the setters-mixin contract."""

    @property
    def device_connected(self) -> bool:
        return self._protocol.connected


def _host(**attrs: Any) -> Any:
    host: Any = _Host()
    host.schedule_update = MagicMock()
    host._update_property = MagicMock()
    host._property_changed = MagicMock()
    host._dirty_data = {}
    host._dirty_auto_switch_data = {}
    host._dirty_ai_data = {}
    host._discarded_properties = []
    host._read_write_properties = []
    host._last_change = 0
    host._last_settings_request = 0
    host.property_mapping = {}
    host.action_mapping = {}
    host._protocol = MagicMock()
    host._protocol.connected = True
    host._map_manager = None
    host.auto_switch_data = {}
    host.ai_data = {}
    host.data = {}
    host.status = SimpleNamespace(started=False)
    host.capability = SimpleNamespace()
    for key, value in attrs.items():
        setattr(host, key, value)
    return host


# ===========================================================================
# set_property: optimistic update + rollback
# ===========================================================================


class TestSetProperty:
    def test_none_value_short_circuits(self) -> None:
        """value=None returns False before touching schedule_update/_update_property."""
        host = _host()
        result = host.set_property(DreameVacuumProperty.SUCTION_LEVEL, None)
        assert result is False
        host.schedule_update.assert_not_called()
        host._update_property.assert_not_called()

    def test_update_property_rejection_skips_protocol_call(self) -> None:
        """_update_property returning None means the write was rejected in memory."""
        host = _host()
        host._update_property = MagicMock(return_value=None)

        result = host.set_property(DreameVacuumProperty.SUCTION_LEVEL, 3)

        assert result is False
        host._protocol.set_property.assert_not_called()
        assert host.schedule_update.call_args_list == [call(10), call(1)]

    def test_success_returns_true_without_rollback(self) -> None:
        host = _host()
        host._update_property = MagicMock(return_value=10)
        host.property_mapping = {DreameVacuumProperty.SUCTION_LEVEL: {"siid": 4, "piid": 4}}
        host._protocol.set_property.return_value = [{"code": 0}]

        result = host.set_property(DreameVacuumProperty.SUCTION_LEVEL, 2)

        assert result is True
        host._update_property.assert_called_once_with(DreameVacuumProperty.SUCTION_LEVEL, 2, False)
        host._protocol.set_property.assert_called_once_with(4, 4, 2)
        host._property_changed.assert_not_called()
        dirty = host._dirty_data[DreameVacuumProperty.SUCTION_LEVEL.value]
        assert dirty.value == 2
        assert dirty.previous_value == 10
        host.schedule_update.assert_called_with(3)

    def test_discarded_property_is_not_dirty_tracked(self) -> None:
        host = _host()
        host._update_property = MagicMock(return_value=10)
        host.property_mapping = {DreameVacuumProperty.SUCTION_LEVEL: {"siid": 4, "piid": 4}}
        host._protocol.set_property.return_value = [{"code": 0}]
        host._discarded_properties = [DreameVacuumProperty.SUCTION_LEVEL]

        result = host.set_property(DreameVacuumProperty.SUCTION_LEVEL, 2)

        assert result is True
        assert host._dirty_data == {}

    def test_protocol_failure_rolls_back_and_returns_false(self) -> None:
        host = _host()
        host._update_property = MagicMock(return_value=10)
        host.property_mapping = {DreameVacuumProperty.SUCTION_LEVEL: {"siid": 4, "piid": 4}}
        host._protocol.set_property.return_value = [{"code": 1}]

        result = host.set_property(DreameVacuumProperty.SUCTION_LEVEL, 3)

        assert result is False
        assert host._update_property.call_args_list == [
            call(DreameVacuumProperty.SUCTION_LEVEL, 3, False),
            call(DreameVacuumProperty.SUCTION_LEVEL, 10),
        ]
        assert DreameVacuumProperty.SUCTION_LEVEL.value not in host._dirty_data
        host._property_changed.assert_called_once_with(False)
        host.schedule_update.assert_called_with(2)

    def test_protocol_falsy_result_also_rolls_back(self) -> None:
        """None/empty result (not just a bad code) triggers the same rollback path."""
        host = _host()
        host._update_property = MagicMock(return_value=10)
        host.property_mapping = {DreameVacuumProperty.SUCTION_LEVEL: {"siid": 4, "piid": 4}}
        host._protocol.set_property.return_value = None

        result = host.set_property(DreameVacuumProperty.SUCTION_LEVEL, 3)

        assert result is False
        host._property_changed.assert_called_once_with(False)

    def test_protocol_exception_rolls_back_and_raises_from_none(self) -> None:
        host = _host()
        host._update_property = MagicMock(return_value=10)
        host.property_mapping = {DreameVacuumProperty.SUCTION_LEVEL: {"siid": 4, "piid": 4}}
        host._protocol.set_property.side_effect = RuntimeError("boom")

        with pytest.raises(DeviceUpdateFailedException) as exc_info:
            host.set_property(DreameVacuumProperty.SUCTION_LEVEL, 3)

        assert exc_info.value.__cause__ is None
        assert exc_info.value.__suppress_context__ is True
        assert host._update_property.call_args_list == [
            call(DreameVacuumProperty.SUCTION_LEVEL, 3, False),
            call(DreameVacuumProperty.SUCTION_LEVEL, 10),
        ]
        assert DreameVacuumProperty.SUCTION_LEVEL.value not in host._dirty_data
        host.schedule_update.assert_called_with(1)

    def test_dispatches_auto_switch_property(self) -> None:
        host = _host()
        host.set_auto_switch_property = MagicMock(return_value={"code": 0})

        result = host.set_property(DreameVacuumAutoSwitchProperty.MOPPING_TYPE, 1)

        assert result is True
        host.set_auto_switch_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.MOPPING_TYPE, 1)

    def test_dispatches_ai_property(self) -> None:
        host = _host()
        host.set_ai_property = MagicMock(return_value=None)

        result = host.set_property(DreameVacuumAIProperty.AI_PET_DETECTION, True)

        assert result is False
        host.set_ai_property.assert_called_once_with(DreameVacuumAIProperty.AI_PET_DETECTION, True)


# ===========================================================================
# set_property_value: reflection dispatch
# ===========================================================================


class TestSetPropertyValueDispatch:
    def test_missing_prop_or_value_raises(self) -> None:
        host = _host()
        with pytest.raises(InvalidActionException, match="Invalid property or value"):
            host.set_property_value(None, 5)
        with pytest.raises(InvalidActionException, match="Invalid property or value"):
            host.set_property_value("volume", None)

    def test_unknown_property_key_raises(self) -> None:
        host = _host()
        with pytest.raises(InvalidActionException, match="Invalid property"):
            host.set_property_value("not_a_real_property_xyz", 5)

    def test_property_not_in_read_write_list_raises(self) -> None:
        """SUCTION_LEVEL has a bespoke set_fn but is still gated by _read_write_properties."""
        host = _host()
        host._read_write_properties = []
        with pytest.raises(InvalidActionException, match="Invalid property"):
            host.set_property_value("suction_level", 2)

    def test_known_key_dispatches_to_set_method_via_reflection(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.VOLUME])
        host.set_volume = MagicMock(return_value=True)

        result = host.set_property_value("volume", 50)

        assert result is True
        host.set_volume.assert_called_once_with(50)

    def test_out_of_range_value_raises_invalid_value(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.VOLUME])
        host.set_volume = MagicMock(return_value=True)

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("volume", 150)

        host.set_volume.assert_not_called()

    def test_non_numeric_string_value_raises_invalid_value(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.VOLUME])
        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("volume", "not_a_number")

    def test_device_not_connected_raises(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.MOP_CLEANING_REMAINDER])
        # No bespoke set_fn: set_property_value first checks get_property(prop) is not
        # None (property "known") before reaching the value coercion/connectivity gate.
        host.data = {DreameVacuumProperty.MOP_CLEANING_REMAINDER.value: 30}
        host._protocol.connected = False

        with pytest.raises(InvalidActionException, match="Device unavailable"):
            host.set_property_value("mop_cleaning_remainder", 60)

    def test_generic_dispatch_falls_back_to_set_property(self) -> None:
        """When there is no bespoke set_<name>, the generic set_property path is used."""
        host = _host(_read_write_properties=[DreameVacuumProperty.MOP_CLEANING_REMAINDER])
        host.get_property = MagicMock(return_value=10)
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("mop_cleaning_remainder", 60)

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumProperty.MOP_CLEANING_REMAINDER, 60)

    def test_generic_dispatch_raises_when_set_property_fails(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.MOP_CLEANING_REMAINDER])
        host.get_property = MagicMock(return_value=10)
        host.set_property = MagicMock(return_value=False)

        with pytest.raises(InvalidActionException, match="not updated"):
            host.set_property_value("mop_cleaning_remainder", 60)


# ===========================================================================
# set_property_value: property-key resolution (AutoSwitch / AI / StrAI)
# ===========================================================================


class TestSetPropertyValueKeyResolution:
    def test_resolves_auto_switch_property_without_bespoke_setter(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, fast_mapping=False)
        host.get_property = MagicMock(return_value=0)
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("mopping_type", 2)

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.MOPPING_TYPE, 2)

    def test_resolves_ai_property_without_bespoke_setter(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False)
        host.ai_data = {"AI_OBSTACLE_DETECTION": False}
        host.get_property = MagicMock(return_value=False)
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("ai_obstacle_detection", True)

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumAIProperty.AI_OBSTACLE_DETECTION, 1)

    def test_resolves_str_ai_property_without_bespoke_setter(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, ai_obstacle_detection=True)
        host.ai_data = {"AI_HUMAN_DETECTION": False}
        host.get_property = MagicMock(return_value=False)
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("ai_human_detection", True)

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumStrAIProperty.AI_HUMAN_DETECTION, 1)


# ===========================================================================
# set_property_value: availability gate
# ===========================================================================


class TestSetPropertyValueAvailabilityGate:
    def test_property_unavailable_raises(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.LOW_WATER_WARNING])
        host.data = {DreameVacuumProperty.LOW_WATER_WARNING.value: 0}
        host.status = SimpleNamespace(started=False, auto_water_refilling_enabled=True)

        with pytest.raises(InvalidActionException, match="Property unavailable"):
            host.set_property_value("low_water_warning", 1)

    def test_property_available_proceeds_to_dispatch(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.LOW_WATER_WARNING])
        host.data = {DreameVacuumProperty.LOW_WATER_WARNING.value: 0}
        host.status = SimpleNamespace(started=False, auto_water_refilling_enabled=False)
        host.get_property = MagicMock(return_value=0)
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("low_water_warning", 1)

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumProperty.LOW_WATER_WARNING, 1)

    def test_excluded_property_bypasses_availability_check_when_not_started(self) -> None:
        """CLEANING_ROUTE has an availability entry but is exempt while not started."""
        host = _host()
        host.status = SimpleNamespace(
            started=False, segments=False, cleaning_route_list={"STANDARD": 1}
        )  # would fail the lambda if evaluated
        host.get_property = MagicMock(return_value=0)
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("cleaning_route", 1)

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.CLEANING_ROUTE, 1)


# ===========================================================================
# set_property_value: SCHEDULE string validation
# ===========================================================================


class TestSetPropertyValueSchedule:
    def test_blank_schedule_clears_the_schedule(self) -> None:
        """A blank value skips task validation and is accepted as-is: it is the
        documented way to clear the schedule (``string_value`` is a flag, so the
        falsy empty payload no longer trips the final validity check)."""
        host = _host(_read_write_properties=[DreameVacuumProperty.SCHEDULE])
        host.status = SimpleNamespace(started=False)
        host.data = {DreameVacuumProperty.SCHEDULE.value: "old"}
        host.set_property = MagicMock(return_value=True)

        host.set_property_value("schedule", "")

        host.set_property.assert_called_once_with(DreameVacuumProperty.SCHEDULE, "")

    def test_wellformed_task_is_accepted(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.SCHEDULE])
        host.status = SimpleNamespace(started=False)
        host.data = {DreameVacuumProperty.SCHEDULE.value: "old"}
        host.set_property = MagicMock(return_value=True)
        task = "1-a-08:00-c-d-e-f-g-h"

        result = host.set_property_value("schedule", task)

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumProperty.SCHEDULE, task)

    def test_task_with_too_few_fields_raises_invalid_value(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.SCHEDULE])
        host.status = SimpleNamespace(started=False)
        host.data = {DreameVacuumProperty.SCHEDULE.value: "old"}

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("schedule", "1-a-08:00")

    def test_task_with_zero_id_raises_invalid_value(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.SCHEDULE])
        host.status = SimpleNamespace(started=False)
        host.data = {DreameVacuumProperty.SCHEDULE.value: "old"}

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("schedule", "0-a-08:00-c-d-e-f-g-h")

    def test_task_without_colon_in_time_raises_invalid_value(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.SCHEDULE])
        host.status = SimpleNamespace(started=False)
        host.data = {DreameVacuumProperty.SCHEDULE.value: "old"}

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("schedule", "1-a-0800-c-d-e-f-g-h")


# ===========================================================================
# set_property_value: value coercion via enum lookups (generic dispatch)
# ===========================================================================


class TestSetPropertyValueMiscCoercion:
    def test_known_property_without_bespoke_setter_and_unknown_value_raises_invalid_property(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.MOP_CLEANING_REMAINDER])
        host.data = {}  # get_property(prop) is None -> "Invalid property", not reached via value coercion

        with pytest.raises(InvalidActionException, match="Invalid property"):
            host.set_property_value("mop_cleaning_remainder", 60)

    def test_get_int_value_returns_none_for_unmatched_string(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.SUCTION_LEVEL])
        host.status = SimpleNamespace(started=False)
        host.set_suction_level = MagicMock()

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("suction_level", "GARBAGE")

        host.set_suction_level.assert_not_called()

    def test_suction_level_named_value_dispatches(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.SUCTION_LEVEL])
        host.status = SimpleNamespace(started=False)
        host.set_suction_level = MagicMock(return_value=True)

        result = host.set_property_value("suction_level", "STRONG")

        assert result is True
        host.set_suction_level.assert_called_once_with(DreameVacuumSuctionLevel.STRONG.value)

    def test_water_volume_named_value_dispatches(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.WATER_VOLUME])
        host.status = SimpleNamespace(started=False)
        host.set_water_volume = MagicMock(return_value=True)

        result = host.set_property_value("water_volume", "HIGH")

        assert result is True
        host.set_water_volume.assert_called_once_with(DreameVacuumWaterVolume.HIGH.value)

    def test_cleaning_mode_named_value_dispatches(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.CLEANING_MODE])
        host.status = SimpleNamespace(started=False)
        host.set_cleaning_mode = MagicMock(return_value=True)

        result = host.set_property_value("cleaning_mode", "MOPPING")

        assert result is True
        host.set_cleaning_mode.assert_called_once_with(DreameVacuumCleaningMode.MOPPING.value)

    def test_wider_corner_coverage_dispatches(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False)
        host.set_wider_corner_coverage = MagicMock(return_value=True)

        result = host.set_property_value("wider_corner_coverage", "HIGH_FREQUENCY")

        assert result is True
        host.set_wider_corner_coverage.assert_called_once_with(1)

    def test_mop_pad_swing_dispatches(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False)
        host.set_mop_pad_swing = MagicMock(return_value=True)

        result = host.set_property_value("mop_pad_swing", "DAILY")

        assert result is True
        host.set_mop_pad_swing.assert_called_once_with(2)

    def test_self_clean_frequency_dispatches(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, self_clean=True, fast_mapping=False, cleangenius_cleaning=False)
        host.set_self_clean_frequency = MagicMock(return_value=True)

        result = host.set_property_value("self_clean_frequency", "BY_TIME")

        assert result is True
        host.set_self_clean_frequency.assert_called_once_with(DreameVacuumSelfCleanFrequency.BY_TIME.value)

    def test_auto_recleaning_dispatches(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, has_temporary_map=False, segments=True, fast_mapping=False)
        host.set_auto_recleaning = MagicMock(return_value=True)

        result = host.set_property_value("auto_recleaning", "IN_DEEP_MODE")

        assert result is True
        host.set_auto_recleaning.assert_called_once_with(1)


class TestSetPropertyValueCoercion:
    def test_carpet_sensitivity_string_name_coerced(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.CARPET_SENSITIVITY])
        host.status = SimpleNamespace(started=False)
        # Real get_property is used (not mocked): the availability lambda reads
        # CARPET_BOOST off ``self.data`` directly.
        host.data = {
            DreameVacuumProperty.CARPET_SENSITIVITY.value: 1,
            DreameVacuumProperty.CARPET_BOOST.value: 1,
        }
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("carpet_sensitivity", "HIGH")

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumProperty.CARPET_SENSITIVITY, 3)

    def test_water_temperature_numeric_string_coerced(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.WATER_TEMPERATURE])
        host.status = SimpleNamespace(started=False, smart_mop_washing=False, self_clean=True)
        host.get_property = MagicMock(return_value=0)
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("water_temperature", "2")

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumProperty.WATER_TEMPERATURE, 2)

    def test_cleangenius_mode_coerced(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.CLEANGENIUS_MODE])
        host.status = SimpleNamespace(
            started=False,
            cleangenius_cleaning=True,
            fast_mapping=False,
            cruising=False,
            spot_cleaning=False,
            zone_cleaning=False,
            mop_pad_installed=True,
        )
        host.get_property = MagicMock(return_value=0)
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("cleangenius_mode", "VACUUM_AND_MOP")

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumProperty.CLEANGENIUS_MODE, 2)

    def test_mop_extend_frequency_coerced(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, fast_mapping=False, washing=False, washing_paused=False)
        host.get_property = MagicMock(return_value=0)
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("mop_extend_frequency", "HIGH")

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.MOP_EXTEND_FREQUENCY, 2)

    def test_cleangenius_auto_switch_coerced(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            started=False,
            fast_mapping=False,
            cruising=False,
            spot_cleaning=False,
            zone_cleaning=False,
            mop_pad_installed=True,
        )
        host.get_property = MagicMock(return_value=0)
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("cleangenius", "ROUTINE_CLEANING")

        assert result is None
        host.set_property.assert_called_once_with(
            DreameVacuumAutoSwitchProperty.CLEANGENIUS, DreameVacuumCleanGenius.ROUTINE_CLEANING.value
        )

    @staticmethod
    def _selected_map_status(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "started": False,
            "map_data_list": {1: object()},
            "multi_map": True,
            "fast_mapping": False,
            "map_list": [1],
            "selected_map": SimpleNamespace(map_name="Downstairs", map_id=1),
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_selected_map_rejects_unknown_map_id(self) -> None:
        host = _host()
        host.status = self._selected_map_status()
        # set_selected_map lives on a sibling mixin (device_map_ops); stub it here.
        host.set_selected_map = MagicMock(return_value=True)

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("selected_map", 99)

        host.set_selected_map.assert_not_called()

    def test_selected_map_accepts_known_map_id(self) -> None:
        host = _host()
        host.status = self._selected_map_status()
        host.set_selected_map = MagicMock(return_value=True)

        result = host.set_property_value("selected_map", 1)

        assert result is True
        host.set_selected_map.assert_called_once_with(1)


# ===========================================================================
# set_property_value: value coercion dispatching to bespoke setters
# ===========================================================================


class TestSetPropertyValueBespokeCoercion:
    def test_carpet_cleaning_named_value_dispatches(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.CARPET_CLEANING])
        host.status = SimpleNamespace(started=False, carpet_recognition=True)
        host.capability = SimpleNamespace(mop_pad_lifting_plus=False, auto_carpet_cleaning=False)
        host.set_carpet_cleaning = MagicMock(return_value=True)

        result = host.set_property_value("carpet_cleaning", "AVOIDANCE")

        assert result is True
        host.set_carpet_cleaning.assert_called_once_with(1)

    def test_mop_wash_level_named_value_dispatches(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.MOP_WASH_LEVEL])
        host.status = SimpleNamespace(started=False, self_clean=True)
        host.set_mop_wash_level = MagicMock(return_value=True)

        result = host.set_property_value("mop_wash_level", "DEEP")

        assert result is True
        host.set_mop_wash_level.assert_called_once_with(2)

    def test_voice_assistant_language_dispatches(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE])
        host.status = SimpleNamespace(started=False, voice_assistant_language_list={"EN": 1, "DE": 5})
        host.data = {DreameVacuumProperty.VOICE_ASSISTANT.value: 1}
        host.set_voice_assistant_language = MagicMock(return_value=True)

        # Numeric-string form: resolved directly against ``voice_assistant_language_list``
        # values (the StrEnum-member-name path returns a non-int and can never match
        # ``enum_list.values()``, so it is not exercised as a "success" case here).
        result = host.set_property_value("voice_assistant_language", "5")

        assert result is True
        host.set_voice_assistant_language.assert_called_once_with(5)

    def test_mop_pad_humidity_excluded_property_bypasses_availability_when_not_started(self) -> None:
        """MOP_PAD_HUMIDITY is in the excluded set: while not started, its
        PROPERTY_AVAILABILITY lambda is skipped entirely (it would otherwise need a
        dozen status attributes)."""
        host = _host()
        host.status = SimpleNamespace(started=False)
        host.set_mop_pad_humidity = MagicMock(return_value=True)

        result = host.set_property_value("mop_pad_humidity", "MOIST")

        assert result is True
        host.set_mop_pad_humidity.assert_called_once_with(2)

    def test_custom_mopping_route_excluded_property_dispatches(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False)
        host.set_custom_mopping_route = MagicMock(return_value=True)

        result = host.set_property_value("custom_mopping_route", "DEEP")

        assert result is True
        host.set_custom_mopping_route.assert_called_once_with(2)

    def test_auto_empty_mode_dispatches(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False)
        host.set_auto_empty_mode = MagicMock(return_value=True)

        result = host.set_property_value("auto_empty_mode", "HIGH_FREQUENCY")

        assert result is True
        host.set_auto_empty_mode.assert_called_once_with(2)

    def test_washing_mode_dispatches(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, self_clean=True)
        host.set_washing_mode = MagicMock(return_value=True)

        result = host.set_property_value("washing_mode", "DEEP")

        assert result is True
        host.set_washing_mode.assert_called_once_with(2)

    def test_dnd_start_valid_time_dispatches(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.DND_START])
        host.status = SimpleNamespace(started=False, dnd=True)
        host.set_dnd_start = MagicMock(return_value=True)

        result = host.set_property_value("dnd_start", "07:30")

        assert result is True
        host.set_dnd_start.assert_called_once_with("07:30")

    def test_dnd_end_invalid_time_raises(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.DND_END])
        host.status = SimpleNamespace(started=False, dnd=True)
        host.set_dnd_end = MagicMock(return_value=True)

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("dnd_end", "25:99")

        host.set_dnd_end.assert_not_called()

    def test_off_peak_charging_start_dispatches(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, off_peak_charging=True)
        host.set_off_peak_charging_start = MagicMock(return_value=True)

        result = host.set_property_value("off_peak_charging_start", "22:15")

        assert result is True
        host.set_off_peak_charging_start.assert_called_once_with("22:15")

    def test_off_peak_charging_end_dispatches(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, off_peak_charging=True)
        host.set_off_peak_charging_end = MagicMock(return_value=True)

        result = host.set_property_value("off_peak_charging_end", "06:00")

        assert result is True
        host.set_off_peak_charging_end.assert_called_once_with("06:00")

    def test_off_peak_charging_start_invalid_time_raises_before_dispatch(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, off_peak_charging=True)
        host.set_off_peak_charging_start = MagicMock(return_value=True)

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("off_peak_charging_start", "bad-time")

        host.set_off_peak_charging_start.assert_not_called()


# ===========================================================================
# set_property_value: bool/string generic fallback coercion
# ===========================================================================


class TestSetPropertyValueGenericFallback:
    def test_bool_value_coerced_to_int(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.MOP_CLEANING_REMAINDER])
        host.get_property = MagicMock(return_value=0)
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("mop_cleaning_remainder", True)

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumProperty.MOP_CLEANING_REMAINDER, 1)

    @pytest.mark.parametrize(("raw", "expected"), [("TRUE", 1), ("1", 1), ("FALSE", 0), ("0", 0), ("42", 42)])
    def test_string_value_variants_coerced(self, raw: str, expected: int) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.MOP_CLEANING_REMAINDER])
        host.get_property = MagicMock(return_value=-1)
        host.set_property = MagicMock(return_value=True)

        result = host.set_property_value("mop_cleaning_remainder", raw)

        assert result is None
        host.set_property.assert_called_once_with(DreameVacuumProperty.MOP_CLEANING_REMAINDER, expected)

    def test_non_numeric_non_boolean_string_raises_invalid_value(self) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.MOP_CLEANING_REMAINDER])
        host.data = {DreameVacuumProperty.MOP_CLEANING_REMAINDER.value: 30}

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("mop_cleaning_remainder", "garbage")


# ===========================================================================
# set_property_value: numeric range validators
# ===========================================================================


class TestSetPropertyValueRangeValidators:
    @pytest.mark.parametrize("value", [-1, 181])
    def test_mop_cleaning_remainder_out_of_range_raises(self, value: int) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.MOP_CLEANING_REMAINDER])
        host.data = {DreameVacuumProperty.MOP_CLEANING_REMAINDER.value: 30}
        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("mop_cleaning_remainder", value)

    @pytest.mark.parametrize("value", [39, 101])
    def test_camera_light_brightness_out_of_range_raises(self, value: int) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS])
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.status = SimpleNamespace(started=False, camera_light_brightness=50, stream_session="sess-1")
        host.set_camera_light_brightness = MagicMock()

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("camera_light_brightness", value)

        host.set_camera_light_brightness.assert_not_called()

    @pytest.mark.parametrize("value", [0, 33])
    def test_wetness_level_out_of_range_raises(self, value: int) -> None:
        host = _host(_read_write_properties=[DreameVacuumProperty.WETNESS_LEVEL])
        # WETNESS_LEVEL is in the "excluded" set: bypasses PROPERTY_AVAILABILITY while
        # not started.
        host.status = SimpleNamespace(started=False)
        host.data = {DreameVacuumProperty.WETNESS_LEVEL.value: 10}

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("wetness_level", value)

    def test_self_clean_area_out_of_range_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            started=False,
            self_clean=True,
            cleangenius_cleaning=False,
            fast_mapping=False,
            self_clean_by_time=False,
            self_clean_value=10,
            self_clean_area_min=5,
            self_clean_area_max=30,
        )
        host.set_self_clean_area = MagicMock()

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("self_clean_area", 99)

        host.set_self_clean_area.assert_not_called()

    def test_self_clean_area_within_range_dispatches(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            started=False,
            self_clean=True,
            cleangenius_cleaning=False,
            fast_mapping=False,
            self_clean_by_time=False,
            self_clean_value=10,
            self_clean_area_min=5,
            self_clean_area_max=30,
        )
        host.set_self_clean_area = MagicMock(return_value=True)

        result = host.set_property_value("self_clean_area", 20)

        assert result is True
        host.set_self_clean_area.assert_called_once_with(20)

    def test_self_clean_time_out_of_range_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            started=False,
            self_clean=True,
            cleangenius_cleaning=False,
            fast_mapping=False,
            self_clean_by_time=True,
            self_clean_value=10,
            self_clean_time_min=5,
            self_clean_time_max=60,
        )
        host.set_self_clean_time = MagicMock()

        with pytest.raises(InvalidActionException, match="Invalid value"):
            host.set_property_value("self_clean_time", 500)

        host.set_self_clean_time.assert_not_called()


# ===========================================================================
# call_action_value: reflection dispatch
# ===========================================================================


class TestCallActionValueDispatch:
    def test_none_action_raises(self) -> None:
        host = _host()
        with pytest.raises(InvalidActionException, match="Invalid action"):
            host.call_action_value(None)

    def test_unknown_action_raises(self) -> None:
        host = _host()
        with pytest.raises(InvalidActionException, match="Invalid action"):
            host.call_action_value("totally_bogus_action")

    def test_action_unavailable_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, main_brush_life=100)
        with pytest.raises(InvalidActionException, match="Action unavailable"):
            host.call_action_value("reset_main_brush")

    def test_device_not_connected_raises(self) -> None:
        host = _host()
        host._protocol.connected = False
        with pytest.raises(InvalidActionException, match="Device unavailable"):
            host.call_action_value("locate")

    def test_known_method_dispatches_without_params(self) -> None:
        host = _host()
        host.locate = MagicMock(return_value={"code": 0})

        result = host.call_action_value("locate")

        assert result == {"code": 0}
        host.locate.assert_called_once_with()

    def test_custom_method_dispatches_with_params(self) -> None:
        host = _host()
        host.foo_bar = MagicMock(return_value="ok")

        result = host.call_action_value("foo_bar", {"a": 1})

        assert result == "ok"
        host.foo_bar.assert_called_once_with({"a": 1})

    def test_falls_back_to_generic_call_action(self) -> None:
        host = _host()
        host.status = SimpleNamespace(docked=False, returning=False)
        host.call_action = MagicMock(return_value={"code": 0})

        result = host.call_action_value("charge", {"x": 1})

        assert result is None
        host.call_action.assert_called_once_with(DreameVacuumAction.CHARGE, {"x": 1})

    def test_generic_call_action_failure_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(docked=False, returning=False)
        host.call_action = MagicMock(return_value={"code": 1})

        with pytest.raises(InvalidActionException, match="Unable to call action"):
            host.call_action_value("charge")


# ===========================================================================
# HH:MM parsing: DnD task
# ===========================================================================


class TestSetDndTaskParsing:
    def test_valid_times_appended_as_first_task(self) -> None:
        host = _host()
        host.status = SimpleNamespace(dnd_tasks=[])
        host.set_property = MagicMock(return_value=True)

        result = host.set_dnd_task(True, "07:30", "22:15")

        assert result is True
        assert host.status.dnd_tasks == [{"id": 1, "en": True, "st": "07:30", "et": "22:15", "wk": 127, "ss": 0}]
        host.set_property.assert_called_once_with(
            DreameVacuumProperty.DND_TASK,
            '[{"id":1,"en":true,"st":"07:30","et":"22:15","wk":127,"ss":0}]',
        )

    def test_existing_task_updated_in_place(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            dnd_tasks=[{"id": 1, "en": False, "st": "01:00", "et": "02:00", "wk": 127, "ss": 0}]
        )
        host.set_property = MagicMock(return_value=True)

        host.set_dnd_task(True, "09:00", "17:00")

        assert len(host.status.dnd_tasks) == 1
        assert host.status.dnd_tasks[0]["st"] == "09:00"
        assert host.status.dnd_tasks[0]["et"] == "17:00"
        assert host.status.dnd_tasks[0]["en"] is True

    def test_blank_start_and_end_default_to_22_08(self) -> None:
        host = _host()
        host.status = SimpleNamespace(dnd_tasks=None)
        host.set_property = MagicMock(return_value=True)

        host.set_dnd_task(True, None, "")

        assert host.status.dnd_tasks[0]["st"] == "22:00"
        assert host.status.dnd_tasks[0]["et"] == "08:00"

    def test_invalid_start_time_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(dnd_tasks=[])
        with pytest.raises(InvalidValueException, match="DnD start time is not valid"):
            host.set_dnd_task(True, "25:00", "08:00")

    def test_invalid_end_time_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(dnd_tasks=[])
        with pytest.raises(InvalidValueException, match="DnD end time is not valid"):
            host.set_dnd_task(True, "07:00", "24:00")

    def test_start_equal_end_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(dnd_tasks=[])
        with pytest.raises(InvalidValueException, match="must be different"):
            host.set_dnd_task(True, "10:00", "10:00")

    @pytest.mark.parametrize("value", ["23:59", "00:00", "19:59", "20:00"])
    def test_boundary_valid_times_accepted(self, value: str) -> None:
        host = _host()
        host.status = SimpleNamespace(dnd_tasks=[])
        host.set_property = MagicMock(return_value=True)

        host.set_dnd_task(True, value, "01:01")

        assert host.status.dnd_tasks[0]["st"] == value

    @pytest.mark.parametrize("value", ["24:00", "12:60", "1:00", "ab:cd"])
    def test_boundary_invalid_times_rejected(self, value: str) -> None:
        host = _host()
        host.status = SimpleNamespace(dnd_tasks=[])
        with pytest.raises(InvalidValueException):
            host.set_dnd_task(True, value, "12:00")


class TestSetOffPeakChargingParsing:
    def test_valid_config_written(self) -> None:
        host = _host()
        host.status = SimpleNamespace(off_peak_charging_config=None)
        host.set_property = MagicMock(return_value=True)

        result = host.set_off_peak_charging_config(True, "23:00", "06:30")

        assert result is True
        assert host.status.off_peak_charging_config == {
            "enable": True,
            "startTime": "23:00",
            "endTime": "06:30",
        }
        host.set_property.assert_called_once_with(
            DreameVacuumProperty.OFF_PEAK_CHARGING,
            '{"enable":true,"startTime":"23:00","endTime":"06:30"}',
        )

    def test_blank_start_and_end_default(self) -> None:
        host = _host()
        host.status = SimpleNamespace(off_peak_charging_config=None)
        host.set_property = MagicMock(return_value=True)

        host.set_off_peak_charging_config(False, "", None)

        assert host.status.off_peak_charging_config["startTime"] == "22:00"
        assert host.status.off_peak_charging_config["endTime"] == "08:00"

    def test_invalid_start_raises(self) -> None:
        host = _host()
        with pytest.raises(InvalidValueException, match="Start time is not valid"):
            host.set_off_peak_charging_config(True, "99:99", "08:00")

    def test_invalid_end_raises(self) -> None:
        host = _host()
        with pytest.raises(InvalidValueException, match="End time is not valid"):
            host.set_off_peak_charging_config(True, "08:00", "99:99")

    def test_start_equal_end_raises(self) -> None:
        host = _host()
        with pytest.raises(InvalidValueException, match="must be different"):
            host.set_off_peak_charging_config(True, "10:00", "10:00")


class TestSetDndWrapperDispatch:
    def test_uses_dnd_task_when_capability_enabled(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(dnd_task=True)
        host.status = SimpleNamespace(dnd_start="07:00", dnd_end="21:00", dnd_tasks=[])
        host.set_property = MagicMock(return_value=True)

        host.set_dnd(True)

        host.set_property.assert_called_once_with(DreameVacuumProperty.DND_TASK, ANY)

    def test_uses_plain_property_when_capability_disabled(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(dnd_task=False)
        host.set_property = MagicMock(return_value=True)

        host.set_dnd(True)

        host.set_property.assert_called_once_with(DreameVacuumProperty.DND, True)


# ===========================================================================
# Typed setters
# ===========================================================================


class TestSetSuctionLevel:
    def test_raises_when_cruising(self) -> None:
        host = _host()
        host.status = SimpleNamespace(cruising=True)
        with pytest.raises(InvalidActionException, match="cruising"):
            host.set_suction_level(2)

    def test_raises_when_customized_cleaning_active(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            cruising=False,
            started=True,
            customized_cleaning=True,
            zone_cleaning=False,
            spot_cleaning=False,
        )
        with pytest.raises(InvalidActionException, match="customized cleaning"):
            host.set_suction_level(2)

    def test_allows_customized_cleaning_during_zone_cleaning(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            cruising=False,
            started=True,
            customized_cleaning=True,
            zone_cleaning=True,
            spot_cleaning=False,
        )
        host._update_suction_level = MagicMock(return_value=True)

        assert host.set_suction_level(2) is True
        host._update_suction_level.assert_called_once_with(2)

    def test_delegates_to_update_suction_level(self) -> None:
        host = _host()
        host.status = SimpleNamespace(cruising=False, started=False)
        host._update_suction_level = MagicMock(return_value=True)

        result = host.set_suction_level(3)

        assert result is True
        host._update_suction_level.assert_called_once_with(3)


# ===========================================================================
# get_property family
# ===========================================================================


class TestGetProperty:
    def test_returns_value_from_data(self) -> None:
        host = _host()
        host.data = {DreameVacuumProperty.BATTERY_LEVEL.value: 77}
        assert host.get_property(DreameVacuumProperty.BATTERY_LEVEL) == 77

    def test_returns_none_when_missing(self) -> None:
        host = _host()
        assert host.get_property(DreameVacuumProperty.BATTERY_LEVEL) is None

    def test_auto_switch_property_requires_capability(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=False)
        host.auto_switch_data = {"CLEANGENIUS": 1}
        assert host.get_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS) is None

    def test_auto_switch_property_returns_value(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.auto_switch_data = {"CLEANGENIUS": 2}
        assert host.get_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS) == 2

    def test_ai_property_requires_capability(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=False)
        host.ai_data = {"AI_PET_DETECTION": True}
        assert host.get_property(DreameVacuumAIProperty.AI_PET_DETECTION) is None

    def test_ai_property_returns_value(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host.ai_data = {"AI_PET_DETECTION": True}
        assert host.get_property(DreameVacuumAIProperty.AI_PET_DETECTION) is True


# ===========================================================================
# set_volume
# ===========================================================================


class TestSetVolume:
    def test_success_triggers_test_sound(self) -> None:
        host = _host()
        host.set_property = MagicMock(return_value=True)
        host.call_action = MagicMock(return_value={"code": 0})

        result = host.set_volume(50)

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.VOLUME, 50)
        host.call_action.assert_called_once_with(DreameVacuumAction.TEST_SOUND)

    def test_failure_skips_test_sound(self) -> None:
        host = _host()
        host.set_property = MagicMock(return_value=False)
        host.call_action = MagicMock()

        result = host.set_volume(50)

        assert result is False
        host.call_action.assert_not_called()


# ===========================================================================
# set_cleaning_mode: guard clauses
# ===========================================================================


class TestSetCleaningMode:
    @staticmethod
    def _status(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "cleaning_mode": DreameVacuumCleaningMode.SWEEPING,
            "cruising": False,
            "draining": False,
            "scheduled_clean": False,
            "shortcut_task": False,
            "started": False,
            "customized_cleaning": False,
            "zone_cleaning": False,
            "spot_cleaning": False,
            "auto_mount_mop": True,
            "mop_in_station": True,
            "water_tank_or_mop_installed": True,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    @staticmethod
    def _capability(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "custom_cleaning_mode": False,
            "mopping_after_sweeping": True,
            "self_wash_base": False,
            "mop_pad_lifting": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_unsupported_when_cleaning_mode_is_none(self) -> None:
        host = _host()
        host.status = self._status(cleaning_mode=None)
        with pytest.raises(InvalidActionException, match="not supported"):
            host.set_cleaning_mode(1)

    def test_raises_when_cruising(self) -> None:
        host = _host()
        host.status = self._status(cruising=True)
        with pytest.raises(InvalidActionException, match="cruising"):
            host.set_cleaning_mode(1)

    def test_raises_when_draining(self) -> None:
        host = _host()
        host.status = self._status(draining=True)
        with pytest.raises(InvalidActionException, match="draining"):
            host.set_cleaning_mode(1)

    def test_raises_when_scheduled_clean(self) -> None:
        host = _host()
        host.status = self._status(scheduled_clean=True)
        with pytest.raises(InvalidActionException, match="scheduled cleaning"):
            host.set_cleaning_mode(1)

    def test_raises_when_customized_cleaning_active(self) -> None:
        host = _host()
        host.status = self._status(started=True, customized_cleaning=True)
        host.capability = self._capability(custom_cleaning_mode=True)
        with pytest.raises(InvalidActionException, match="customized cleaning"):
            host.set_cleaning_mode(1)

    def test_raises_when_mopping_after_sweeping_unsupported(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = self._capability(mopping_after_sweeping=False)
        with pytest.raises(InvalidActionException, match="mopping after sweeping"):
            host.set_cleaning_mode(DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING.value)

    def test_raises_when_sweeping_while_water_tank_installed(self) -> None:
        host = _host()
        host.status = self._status(auto_mount_mop=False, water_tank_or_mop_installed=True)
        host.capability = self._capability()
        with pytest.raises(InvalidActionException, match="water tank is installed"):
            host.set_cleaning_mode(DreameVacuumCleaningMode.SWEEPING.value)

    def test_raises_when_sweeping_while_mop_pads_installed_and_self_wash_base(self) -> None:
        host = _host()
        host.status = self._status(auto_mount_mop=False, water_tank_or_mop_installed=True)
        host.capability = self._capability(self_wash_base=True)
        with pytest.raises(InvalidActionException, match="mop pads are installed"):
            host.set_cleaning_mode(DreameVacuumCleaningMode.SWEEPING.value)

    def test_raises_when_mopping_while_water_tank_not_installed(self) -> None:
        host = _host()
        host.status = self._status(auto_mount_mop=False, water_tank_or_mop_installed=False)
        host.capability = self._capability()
        with pytest.raises(InvalidActionException, match="water tank is not installed"):
            host.set_cleaning_mode(DreameVacuumCleaningMode.MOPPING.value)

    def test_raises_when_mopping_while_mop_pads_not_installed_and_self_wash_base(self) -> None:
        host = _host()
        host.status = self._status(auto_mount_mop=False, water_tank_or_mop_installed=False)
        host.capability = self._capability(self_wash_base=True)
        with pytest.raises(InvalidActionException, match="mop pads are not installed"):
            host.set_cleaning_mode(DreameVacuumCleaningMode.MOPPING.value)

    def test_raises_when_availability_lambda_rejects_while_started(self) -> None:
        host = _host()
        host.status = self._status(
            started=True,
            mopping_after_sweeping=False,
            fast_mapping=True,
            cleangenius_cleaning=False,
            returning=False,
        )
        host.capability = self._capability()

        with pytest.raises(InvalidActionException, match="Cleaning mode unavailable"):
            host.set_cleaning_mode(DreameVacuumCleaningMode.SWEEPING.value)

    def test_happy_path_delegates_to_update_cleaning_mode(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = self._capability()
        host._update_cleaning_mode = MagicMock(return_value=True)

        result = host.set_cleaning_mode(DreameVacuumCleaningMode.MOPPING.value)

        assert result is True
        host._update_cleaning_mode.assert_called_once_with(1)


# ===========================================================================
# set_auto_switch_property: optimistic update + rollback (mirrors set_property)
# ===========================================================================


class TestSetAutoSwitchProperty:
    def test_capability_disabled_and_not_auto_drying_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=False, self_wash_base=False)
        result = host.set_auto_switch_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS, 1)
        assert result is None

    def test_self_wash_base_auto_drying_fallback_delegates_to_set_property(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=False, self_wash_base=True)
        host.set_property = MagicMock(return_value=True)

        result = host.set_auto_switch_property(DreameVacuumAutoSwitchProperty.AUTO_DRYING, 1)

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.INTELLIGENT_RECOGNITION, 1)

    def test_unsupported_property_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.auto_switch_data = {}
        with pytest.raises(InvalidActionException, match="Not supported"):
            host.set_auto_switch_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS, 1)

    def test_unchanged_value_is_a_noop(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.auto_switch_data = {"CLEANGENIUS": 1}
        host.set_auto_switch_settings = MagicMock()

        result = host.set_auto_switch_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS, 1)

        assert result is None
        host.set_auto_switch_settings.assert_not_called()
        host._property_changed.assert_not_called()

    def test_success_updates_memory_and_dirty_time(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.auto_switch_data = {"CLEANGENIUS": 0}
        host.set_auto_switch_settings = MagicMock(return_value=[{"code": 0}])

        result = host.set_auto_switch_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS, 1)

        assert result == [{"code": 0}]
        assert host.auto_switch_data["CLEANGENIUS"] == 1
        host.set_auto_switch_settings.assert_called_once_with({"k": "SmartHost", "v": 1})
        host._property_changed.assert_called_once_with(False)
        assert "CLEANGENIUS" in host._dirty_auto_switch_data

    def test_failure_result_code_rolls_back(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.auto_switch_data = {"CLEANGENIUS": 0}
        host.set_auto_switch_settings = MagicMock(return_value=[{"code": 1}])

        result = host.set_auto_switch_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS, 1)

        assert result == [{"code": 1}]
        assert host.auto_switch_data["CLEANGENIUS"] == 0
        assert "CLEANGENIUS" not in host._dirty_auto_switch_data
        assert host._property_changed.call_count == 2

    def test_exception_rolls_back(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.auto_switch_data = {"CLEANGENIUS": 0}
        host.set_auto_switch_settings = MagicMock(side_effect=ValueError("boom"))

        result = host.set_auto_switch_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS, 1)

        assert result is None
        assert host.auto_switch_data["CLEANGENIUS"] == 0
        assert "CLEANGENIUS" not in host._dirty_auto_switch_data

    def test_cleangenius_refreshes_map_when_map_manager_present(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.auto_switch_data = {"CLEANGENIUS": 0}
        host.set_auto_switch_settings = MagicMock(return_value=[{"code": 0}])
        host._map_manager = MagicMock()

        host.set_auto_switch_property(DreameVacuumAutoSwitchProperty.CLEANGENIUS, 1)

        host._map_manager.editor.refresh_map.assert_called_once_with()


# ===========================================================================
# Carpet setters
# ===========================================================================


class TestCarpetSetters:
    def test_set_carpet_avoidance_true_maps_to_1(self) -> None:
        host = _host()
        host.set_property = MagicMock(return_value=True)
        host.set_carpet_avoidance(True)
        host.set_property.assert_called_once_with(DreameVacuumProperty.CARPET_CLEANING, 1)

    def test_set_carpet_avoidance_false_maps_to_2(self) -> None:
        host = _host()
        host.set_property = MagicMock(return_value=True)
        host.set_carpet_avoidance(False)
        host.set_property.assert_called_once_with(DreameVacuumProperty.CARPET_CLEANING, 2)

    def test_set_carpet_recognition_requires_capability(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(carpet_recognition=False)
        host.set_property = MagicMock()
        assert host.set_carpet_recognition(1) is None
        host.set_property.assert_not_called()

    def test_set_carpet_recognition_enables_and_resets_boost(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(carpet_recognition=True)
        host.get_property = MagicMock(side_effect=[3, 3])  # CARPET_RECOGNITION current, then CARPET_BOOST
        host.set_property = MagicMock(return_value=True)

        host.set_carpet_recognition(1)

        assert host.set_property.call_args_list == [
            call(DreameVacuumProperty.CARPET_RECOGNITION, 1),
            call(DreameVacuumProperty.CARPET_BOOST, 1),
        ]

    def test_set_carpet_cleaning_noop_when_unsupported(self) -> None:
        host = _host()
        host.get_property = MagicMock(return_value=None)
        host.set_property = MagicMock()
        assert host.set_carpet_cleaning(3) is None
        host.set_property.assert_not_called()

    def test_set_carpet_cleaning_value_six_delegates_to_recognition_off(self) -> None:
        host = _host()
        host.get_property = MagicMock(return_value=1)
        host.capability = SimpleNamespace(mop_pad_lifting_plus=True, auto_carpet_cleaning=False, carpet_crossing=False)
        host.set_carpet_recognition = MagicMock(return_value=None)

        host.set_carpet_cleaning(6)

        host.set_carpet_recognition.assert_called_once_with(0)

    def test_set_carpet_cleaning_unsupported_combo_raises(self) -> None:
        host = _host()
        host.get_property = MagicMock(return_value=1)
        host.capability = SimpleNamespace(mop_pad_lifting_plus=False, auto_carpet_cleaning=False, carpet_crossing=False)
        with pytest.raises(InvalidActionException, match="not supported"):
            host.set_carpet_cleaning(6)


# ===========================================================================
# set_multi_floor_map
# ===========================================================================


class TestSetMultiFloorMap:
    def test_failure_returns_false(self) -> None:
        host = _host()
        host.set_property = MagicMock(return_value=False)
        assert host.set_multi_floor_map(True) is False

    def test_success_without_intelligent_recognition_cleanup(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=False)
        host.set_property = MagicMock(return_value=True)

        assert host.set_multi_floor_map(True) is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.MULTI_FLOOR_MAP, 1)

    def test_disabling_clears_intelligent_recognition(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.get_property = MagicMock(return_value=1)
        host.set_property = MagicMock(return_value=True)

        assert host.set_multi_floor_map(False) is True
        assert host.set_property.call_args_list == [
            call(DreameVacuumProperty.MULTI_FLOOR_MAP, 0),
            call(DreameVacuumProperty.INTELLIGENT_RECOGNITION, 0),
        ]


# ===========================================================================
# Water / wetness typed setters: guard clauses
# ===========================================================================


class TestWaterAndWetnessSetters:
    def test_set_water_volume_noop_when_self_wash_base(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True)
        assert host.set_water_volume(2) is False

    def test_set_water_volume_raises_when_cruising(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False)
        host.status = SimpleNamespace(cruising=True)
        with pytest.raises(InvalidActionException, match="cruising"):
            host.set_water_volume(2)

    def test_set_water_volume_delegates(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False)
        host.status = SimpleNamespace(cruising=False, started=False)
        host._update_water_level = MagicMock(return_value=True)

        assert host.set_water_volume(2) is True
        host._update_water_level.assert_called_once_with(2)

    def test_set_mop_pad_humidity_noop_when_not_self_wash_base(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False)
        assert host.set_mop_pad_humidity(50) is False

    def test_set_mop_pad_humidity_raises_when_cruising(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True)
        host.status = SimpleNamespace(cruising=True)
        with pytest.raises(InvalidActionException, match="cruising"):
            host.set_mop_pad_humidity(50)

    def test_set_mop_pad_humidity_delegates(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True)
        host.status = SimpleNamespace(cruising=False, started=False)
        host._update_water_level = MagicMock(return_value=True)

        assert host.set_mop_pad_humidity(50) is True
        host._update_water_level.assert_called_once_with(50)

    def test_set_wetness_level_noop_when_capability_disabled(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(wetness=False)
        host.set_property = MagicMock()
        assert host.set_wetness_level(10) is False
        host.set_property.assert_not_called()

    def test_set_wetness_level_raises_when_customized_cleaning_active(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(wetness=True, self_wash_base=False)
        host.status = SimpleNamespace(started=True, customized_cleaning=True, zone_cleaning=False, spot_cleaning=False)
        with pytest.raises(InvalidActionException, match="customized cleaning"):
            host.set_wetness_level(10)

    def test_set_wetness_level_delegates_to_set_property(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(wetness=True, self_wash_base=False)
        host.status = SimpleNamespace(started=False)
        host.set_property = MagicMock(return_value=True)

        result = host.set_wetness_level(12)

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.WETNESS_LEVEL, 12)


# ===========================================================================
# _update_cleaning_mode
# ===========================================================================


class TestUpdateCleaningMode:
    def test_plain_device_forwards_value_unchanged(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False, mop_pad_lifting=False)
        host.set_property = MagicMock(return_value=True)

        result = host._update_cleaning_mode(1)

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.CLEANING_MODE, 1)

    @pytest.mark.parametrize(("given", "expected"), [(2, 0), (0, 2), (1, 1)])
    def test_mop_pad_lifting_without_self_wash_base_swaps_sweeping_and_mopping(self, given: int, expected: int) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False, mop_pad_lifting=True)
        host.set_property = MagicMock(return_value=True)

        host._update_cleaning_mode(given)

        host.set_property.assert_called_once_with(DreameVacuumProperty.CLEANING_MODE, expected)

    def test_self_wash_base_with_malformed_group_value_returns_false(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, mop_pad_lifting=False)
        host.get_property = MagicMock(return_value=None)
        host.split_group_value = MagicMock(return_value=None)
        host.set_property = MagicMock()

        assert host._update_cleaning_mode(1) is False
        host.set_property.assert_not_called()

    @pytest.mark.parametrize(("given", "expected_first"), [(2, 0), (0, 2), (1, 1)])
    def test_self_wash_base_with_mop_pad_lifting_updates_first_group_slot(
        self, given: int, expected_first: int
    ) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, mop_pad_lifting=True)
        host.get_property = MagicMock(return_value=999)
        host.split_group_value = MagicMock(return_value=[9, 2, 3])
        host.combine_group_value = MagicMock(return_value=555)
        host.set_property = MagicMock(return_value=True)

        host._update_cleaning_mode(given)

        host.combine_group_value.assert_called_once_with([expected_first, 2, 3])
        host.set_property.assert_called_once_with(DreameVacuumProperty.CLEANING_MODE, 555)

    def test_self_wash_base_without_mop_pad_lifting_only_maps_mopping_after_sweeping(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, mop_pad_lifting=False)
        host.get_property = MagicMock(return_value=999)
        host.split_group_value = MagicMock(return_value=[9, 2, 3])
        host.combine_group_value = MagicMock(return_value=555)
        host.set_property = MagicMock(return_value=True)

        host._update_cleaning_mode(2)

        host.combine_group_value.assert_called_once_with([0, 2, 3])
        host.set_property.assert_called_once_with(DreameVacuumProperty.CLEANING_MODE, 555)


# ===========================================================================
# _update_self_clean_value
# ===========================================================================


class TestUpdateSelfCleanValue:
    def test_without_self_wash_base_returns_false(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False)
        assert host._update_self_clean_value(10) is False

    def test_malformed_group_value_returns_false(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, mop_pad_lifting=False)
        host.get_property = MagicMock(return_value=None)
        host.split_group_value = MagicMock(return_value=[1, 2])
        assert host._update_self_clean_value(10) is False

    def test_updates_second_group_slot(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, mop_pad_lifting=False)
        host.get_property = MagicMock(return_value=999)
        host.split_group_value = MagicMock(return_value=[9, 2, 3])
        host.combine_group_value = MagicMock(return_value=777)
        host.set_property = MagicMock(return_value=True)

        result = host._update_self_clean_value(42)

        assert result is True
        host.combine_group_value.assert_called_once_with([9, 42, 3])
        host.set_property.assert_called_once_with(DreameVacuumProperty.CLEANING_MODE, 777)


# ===========================================================================
# _update_water_level
# ===========================================================================


class TestUpdateWaterLevel:
    @staticmethod
    def _capability(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "mopping_settings": False,
            "self_wash_base": False,
            "wetness_level": False,
            "custom_mopping_route": False,
            "wetness": False,
            "mop_clean_frequency": False,
            "mop_pad_lifting": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    @staticmethod
    def _status(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "self_clean_value": 0,
            "self_clean_by_time": False,
            "custom_mopping_mode": True,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_high_water_triggers_self_clean_reduction(self) -> None:
        host = _host()
        host.capability = self._capability(mopping_settings=True, self_wash_base=True, wetness_level=False)
        host.status = self._status(self_clean_value=20, self_clean_by_time=False)
        host.set_self_clean_value = MagicMock()
        host.split_group_value = MagicMock(return_value=[1, 2, 3])
        host.combine_group_value = MagicMock(return_value=42)
        host.get_property = MagicMock(return_value=999)
        host.set_property = MagicMock(return_value=True)

        host._update_water_level(3)

        host.set_self_clean_value.assert_called_once_with(15)

    def test_custom_mopping_route_updates_mopping_mode_auto_switch(self) -> None:
        host = _host()
        host.capability = self._capability(custom_mopping_route=True)
        host.status = self._status(custom_mopping_mode=False)
        host.set_auto_switch_property = MagicMock()
        host.set_property = MagicMock(return_value=True)

        host._update_water_level(2)

        host.set_auto_switch_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.MOPPING_MODE, 2)

    @pytest.mark.parametrize(
        ("water_level", "expected_wetness"),
        [(1, 100), (3, 400), (2, 200)],
    )
    def test_wetness_with_custom_mopping_route_active_uses_route_table(
        self, water_level: int, expected_wetness: int
    ) -> None:
        host = _host()
        host.capability = self._capability(wetness=True, custom_mopping_route=True, wetness_level=True)
        host.status = self._status(custom_mopping_mode=False)
        host.set_wetness_level = MagicMock(return_value="wetness-result")
        host.set_auto_switch_property = MagicMock()

        result = host._update_water_level(water_level)

        assert result == "wetness-result"
        host.set_wetness_level.assert_called_once_with(expected_wetness)

    @pytest.mark.parametrize(
        ("water_level", "expected_wetness"),
        [(1, 2), (3, 14), (2, 8)],
    )
    def test_wetness_with_mop_clean_frequency_uses_frequency_table(
        self, water_level: int, expected_wetness: int
    ) -> None:
        host = _host()
        host.capability = self._capability(wetness=True, mop_clean_frequency=True, wetness_level=True)
        host.status = self._status()
        host.set_wetness_level = MagicMock(return_value="wetness-result")

        host._update_water_level(water_level)

        host.set_wetness_level.assert_called_once_with(expected_wetness)

    @pytest.mark.parametrize(
        ("water_level", "expected_wetness"),
        [(1, 5), (3, 27), (2, 16)],
    )
    def test_wetness_default_table_used_otherwise(self, water_level: int, expected_wetness: int) -> None:
        host = _host()
        host.capability = self._capability(wetness=True, wetness_level=True)
        host.status = self._status()
        host.set_wetness_level = MagicMock(return_value="wetness-result")

        host._update_water_level(water_level)

        host.set_wetness_level.assert_called_once_with(expected_wetness)

    def test_wetness_without_wetness_level_capability_continues_to_water_volume(self) -> None:
        host = _host()
        host.capability = self._capability(wetness=True, wetness_level=False, self_wash_base=False)
        host.status = self._status()
        host.set_wetness_level = MagicMock(return_value=True)
        host.set_property = MagicMock(return_value=True)

        result = host._update_water_level(2)

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.WATER_VOLUME, 2)

    def test_no_self_wash_base_sets_water_volume_directly(self) -> None:
        host = _host()
        host.capability = self._capability(self_wash_base=False)
        host.status = self._status()
        host.set_property = MagicMock(return_value=True)

        result = host._update_water_level(3)

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.WATER_VOLUME, 3)

    def test_self_wash_base_updates_third_group_slot(self) -> None:
        host = _host()
        host.capability = self._capability(self_wash_base=True)
        host.status = self._status()
        host.get_property = MagicMock(return_value=999)
        host.split_group_value = MagicMock(return_value=[1, 2, 0])
        host.combine_group_value = MagicMock(return_value=42)
        host.set_property = MagicMock(return_value=True)

        result = host._update_water_level(3)

        assert result is True
        host.combine_group_value.assert_called_once_with([1, 2, 3])
        host.set_property.assert_called_once_with(DreameVacuumProperty.CLEANING_MODE, 42)

    def test_self_wash_base_with_malformed_group_value_returns_false(self) -> None:
        host = _host()
        host.capability = self._capability(self_wash_base=True)
        host.status = self._status()
        host.get_property = MagicMock(return_value=999)
        host.split_group_value = MagicMock(return_value=None)
        host.set_property = MagicMock()

        assert host._update_water_level(3) is False
        host.set_property.assert_not_called()

    def test_self_wash_base_wetness_without_pad_wet_skips_cleaning_mode_write(self) -> None:
        host = _host()
        host.capability = self._capability(self_wash_base=True, wetness=True, wetness_level=False)
        host.status = self._status()
        host.set_wetness_level = MagicMock(return_value="wetness-result")
        host.get_property = MagicMock(return_value=999)
        host.split_group_value = MagicMock(return_value=[1, 2, 0])
        host.set_property = MagicMock()

        result = host._update_water_level(3)

        assert result == "wetness-result"
        host.set_property.assert_not_called()


# ===========================================================================
# _update_suction_level
# ===========================================================================


class TestUpdateSuctionLevel:
    def test_delegates_to_set_property_as_int(self) -> None:
        host = _host()
        host.set_property = MagicMock(return_value=True)

        result = host._update_suction_level("3")

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.SUCTION_LEVEL, 3)


# ===========================================================================
# _set_go_to_zone / _restore_go_to_zone
# ===========================================================================


class TestSetGoToZone:
    def test_self_wash_base_targets_sweeping_and_quiet(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, mop_pad_lifting=False)
        host.status = SimpleNamespace(
            cleaning_mode=DreameVacuumCleaningMode.MOPPING,
            suction_level=DreameVacuumSuctionLevel.STRONG,
            mop_pad_humidity=2,
            water_volume=SimpleNamespace(value=2),
            go_to_zone=None,
        )
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()
        host._update_cleaning_mode = MagicMock()

        host._set_go_to_zone(100, 200, 50)

        host._update_cleaning_mode.assert_called_once_with(DreameVacuumCleaningMode.SWEEPING.value)
        host._update_suction_level.assert_called_once_with(DreameVacuumSuctionLevel.QUIET.value)
        host._update_water_level.assert_not_called()
        # Original (pre-change) values are captured so they can be restored later.
        assert host.status.go_to_zone == GoToZoneSettings(
            x=100,
            y=200,
            stop=True,
            suction_level=DreameVacuumSuctionLevel.STRONG.value,
            water_level=None,
            cleaning_mode=DreameVacuumCleaningMode.MOPPING.value,
            size=50,
        )

    def test_self_wash_base_already_at_target_leaves_snapshot_populated(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, mop_pad_lifting=False)
        host.status = SimpleNamespace(
            cleaning_mode=DreameVacuumCleaningMode.SWEEPING,
            suction_level=DreameVacuumSuctionLevel.QUIET,
            mop_pad_humidity=2,
            water_volume=SimpleNamespace(value=2),
            go_to_zone=None,
        )
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()
        host._update_cleaning_mode = MagicMock()

        host._set_go_to_zone(100, 200, 50)

        host._update_cleaning_mode.assert_not_called()
        host._update_suction_level.assert_not_called()
        # Already at the target mode/level -> nothing to restore later.
        assert host.status.go_to_zone.suction_level is None
        assert host.status.go_to_zone.cleaning_mode is None

    def test_non_self_wash_base_mops_when_no_obstruction(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False, mop_pad_lifting=False)
        host.status = SimpleNamespace(
            cleaning_mode=DreameVacuumCleaningMode.SWEEPING,
            suction_level=DreameVacuumSuctionLevel.STRONG,
            water_tank_or_mop_installed=True,
            current_map=None,
            water_volume=SimpleNamespace(value=DreameVacuumWaterVolume.HIGH.value),
            go_to_zone=None,
        )
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()
        host._update_cleaning_mode = MagicMock()

        host._set_go_to_zone(10, 20, 50)

        host._update_cleaning_mode.assert_called_once_with(DreameVacuumCleaningMode.MOPPING.value)
        host._update_water_level.assert_called_once_with(DreameVacuumWaterVolume.LOW.value)
        host._update_suction_level.assert_not_called()

    def test_non_self_wash_base_avoids_no_mopping_areas(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False, mop_pad_lifting=False)
        area = MagicMock()
        area.check_point.return_value = True
        host.status = SimpleNamespace(
            cleaning_mode=DreameVacuumCleaningMode.SWEEPING,
            suction_level=DreameVacuumSuctionLevel.STRONG,
            water_tank_or_mop_installed=True,
            current_map=SimpleNamespace(no_mopping_areas=[area]),
            water_volume=SimpleNamespace(value=DreameVacuumWaterVolume.LOW.value),
            go_to_zone=None,
        )
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()
        host._update_cleaning_mode = MagicMock()

        host._set_go_to_zone(10, 20, 50)

        host._update_cleaning_mode.assert_not_called()
        # Obstruction makes the *target* mode SWEEPING too (matches current), so the code
        # falls into the "already matching" branch, which remaps the restore value to
        # SWEEPING_AND_MOPPING since a mop is installed.
        assert host.status.go_to_zone.cleaning_mode == DreameVacuumCleaningMode.SWEEPING_AND_MOPPING.value

    def test_non_self_wash_base_mopping_without_mop_remaps_to_sweeping(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False, mop_pad_lifting=False)
        host.status = SimpleNamespace(
            cleaning_mode=DreameVacuumCleaningMode.MOPPING,
            suction_level=DreameVacuumSuctionLevel.STRONG,
            water_tank_or_mop_installed=False,
            current_map=None,
            water_volume=SimpleNamespace(value=DreameVacuumWaterVolume.LOW.value),
            go_to_zone=None,
        )
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()
        host._update_cleaning_mode = MagicMock()

        host._set_go_to_zone(10, 20, 50)

        host._update_cleaning_mode.assert_not_called()
        assert host.status.go_to_zone.cleaning_mode == DreameVacuumCleaningMode.SWEEPING.value

    def test_non_self_wash_base_matching_mode_with_mop_installed_clears_restore_value(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False, mop_pad_lifting=False)
        host.status = SimpleNamespace(
            cleaning_mode=DreameVacuumCleaningMode.MOPPING,
            suction_level=DreameVacuumSuctionLevel.STRONG,
            water_tank_or_mop_installed=True,
            current_map=None,
            water_volume=SimpleNamespace(value=DreameVacuumWaterVolume.LOW.value),
            go_to_zone=None,
        )
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()
        host._update_cleaning_mode = MagicMock()

        host._set_go_to_zone(10, 20, 50)

        host._update_cleaning_mode.assert_not_called()
        assert host.status.go_to_zone.cleaning_mode is None

    def test_exceptions_from_helpers_are_swallowed(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, mop_pad_lifting=False)
        host.status = SimpleNamespace(
            cleaning_mode=DreameVacuumCleaningMode.MOPPING,
            suction_level=DreameVacuumSuctionLevel.STRONG,
            mop_pad_humidity=2,
            water_volume=SimpleNamespace(value=2),
            go_to_zone=None,
        )
        host._update_suction_level = MagicMock(side_effect=ValueError("boom"))
        host._update_cleaning_mode = MagicMock()

        host._set_go_to_zone(10, 20, 50)

        assert host.status.go_to_zone is not None


class TestRestoreGoToZone:
    def test_none_go_to_zone_is_a_noop(self) -> None:
        host = _host()
        host.status = SimpleNamespace(go_to_zone=None)

        host._restore_go_to_zone()

        host.schedule_update.assert_not_called()

    def test_falsy_but_not_none_resets_to_none(self) -> None:
        class _Falsy:
            def __bool__(self) -> bool:
                return False

        host = _host()
        host.status = SimpleNamespace(go_to_zone=_Falsy())

        host._restore_go_to_zone()

        assert host.status.go_to_zone is None

    def test_stop_true_sends_stop_action(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            go_to_zone=GoToZoneSettings(x=1, y=2, stop=True, suction_level=None, water_level=None, cleaning_mode=None),
            started=True,
        )
        host.action_mapping = {DreameVacuumAction.STOP: {"siid": 2, "aiid": 1}}
        host._update_status = MagicMock()
        host._protocol.dreame_cloud = False

        host._restore_go_to_zone(stop=True)

        host._protocol.action.assert_called_once_with(2, 1)
        host._update_status.assert_called_once_with(ANY, ANY)

    def test_stop_action_exception_is_swallowed(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            go_to_zone=GoToZoneSettings(x=1, y=2, stop=True, suction_level=None, water_level=None, cleaning_mode=None),
            started=False,
        )
        host.action_mapping = {DreameVacuumAction.STOP: {"siid": 2, "aiid": 1}}
        host._protocol.action.side_effect = DeviceException("boom")

        host._restore_go_to_zone(stop=True)

        # No exception propagates; go_to_zone still cleared.
        assert host.status.go_to_zone is None

    def test_snapshot_stop_false_skips_stop_action(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            go_to_zone=GoToZoneSettings(x=1, y=2, stop=False, suction_level=None, water_level=None, cleaning_mode=None),
            started=False,
        )

        host._restore_go_to_zone(stop=True)

        host._protocol.action.assert_not_called()

    def test_restores_cleaning_mode_suction_and_water_when_changed(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            go_to_zone=GoToZoneSettings(
                x=1,
                y=2,
                stop=False,
                suction_level=DreameVacuumSuctionLevel.STRONG.value,
                water_level=DreameVacuumWaterVolume.HIGH.value,
                cleaning_mode=DreameVacuumCleaningMode.MOPPING.value,
            ),
            started=False,
            cleaning_mode=DreameVacuumCleaningMode.SWEEPING,
            suction_level=DreameVacuumSuctionLevel.QUIET,
            water_volume=SimpleNamespace(value=DreameVacuumWaterVolume.LOW.value),
        )
        host._update_cleaning_mode = MagicMock()
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()

        host._restore_go_to_zone()

        host._update_cleaning_mode.assert_called_once_with(DreameVacuumCleaningMode.MOPPING.value)
        host._update_suction_level.assert_called_once_with(DreameVacuumSuctionLevel.STRONG.value)
        host._update_water_level.assert_called_once_with(DreameVacuumWaterVolume.HIGH.value)

    def test_restore_exception_is_swallowed(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            go_to_zone=GoToZoneSettings(
                x=1,
                y=2,
                stop=False,
                suction_level=DreameVacuumSuctionLevel.STRONG.value,
                water_level=None,
                cleaning_mode=None,
            ),
            started=False,
            suction_level=DreameVacuumSuctionLevel.QUIET,
        )
        host._update_suction_level = MagicMock(side_effect=TypeError("boom"))

        host._restore_go_to_zone()

        assert host.status.go_to_zone is None

    def test_stop_and_started_marks_completed(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            go_to_zone=GoToZoneSettings(x=1, y=2, stop=True, suction_level=None, water_level=None, cleaning_mode=None),
            started=True,
        )
        host.action_mapping = {DreameVacuumAction.STOP: {"siid": 2, "aiid": 1}}
        host._update_status = MagicMock()

        host._restore_go_to_zone(stop=True)

        host._update_status.assert_called_once()

    def test_dreame_cloud_schedules_extra_update(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            go_to_zone=GoToZoneSettings(x=1, y=2, stop=False, suction_level=None, water_level=None, cleaning_mode=None),
            started=False,
        )
        host._protocol.dreame_cloud = True

        host._restore_go_to_zone()

        host.schedule_update.assert_called_once_with(3, True)


# ===========================================================================
# set_self_clean_area / set_self_clean_time / set_self_clean_value
# ===========================================================================


class TestSetSelfCleanArea:
    def test_no_self_wash_base_returns_false(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False)
        assert host.set_self_clean_area(10) is False

    def test_self_wash_base_without_frequency_capability_delegates(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, self_clean_frequency=False)
        host.set_self_clean_value = MagicMock(return_value=True)

        assert host.set_self_clean_area(10) is True
        host.set_self_clean_value.assert_called_once_with(10)

    def test_by_time_frequency_active_returns_false(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, self_clean_frequency=True)
        host.status = SimpleNamespace(self_clean_by_time=True)
        host.set_self_clean_value = MagicMock()

        assert host.set_self_clean_area(10) is False
        host.set_self_clean_value.assert_not_called()

    def test_by_area_frequency_delegates(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, self_clean_frequency=True)
        host.status = SimpleNamespace(self_clean_by_time=False)
        host.set_self_clean_value = MagicMock(return_value=True)

        assert host.set_self_clean_area(10) is True
        host.set_self_clean_value.assert_called_once_with(10)


class TestSetSelfCleanTime:
    def test_no_self_wash_base_returns_false(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False, self_clean_frequency=True)
        host.status = SimpleNamespace(self_clean_by_time=True)
        assert host.set_self_clean_time(30) is False

    def test_requires_by_time_frequency_active(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, self_clean_frequency=True)
        host.status = SimpleNamespace(self_clean_by_time=False)
        assert host.set_self_clean_time(30) is False

    def test_delegates_when_all_conditions_met(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, self_clean_frequency=True)
        host.status = SimpleNamespace(self_clean_by_time=True)
        host.set_self_clean_value = MagicMock(return_value=True)

        assert host.set_self_clean_time(30) is True
        host.set_self_clean_value.assert_called_once_with(30)


class TestSetSelfCleanValue:
    def test_no_self_wash_base_returns_false(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False)
        assert host.set_self_clean_value(10) is False

    def test_update_failure_returns_false(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True)
        host.status = SimpleNamespace(self_clean_value=5)
        host._update_self_clean_value = MagicMock(return_value=False)

        assert host.set_self_clean_value(10) is False

    def test_falsy_value_skips_previous_tracking(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True)
        host.status = SimpleNamespace(self_clean_value=5, self_clean_by_time=False)
        host._update_self_clean_value = MagicMock(return_value=True)

        result = host.set_self_clean_value(0)

        assert result is True
        assert not hasattr(host.status, "previous_self_clean_area")

    def test_by_time_records_previous_time(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True)
        host.status = SimpleNamespace(self_clean_value=5, self_clean_by_time=True)
        host._update_self_clean_value = MagicMock(return_value=True)

        result = host.set_self_clean_value(20)

        assert result is True
        assert host.status.previous_self_clean_time == 20

    def test_by_area_records_previous_area(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True)
        host.status = SimpleNamespace(self_clean_value=5, self_clean_by_time=False)
        host._update_self_clean_value = MagicMock(return_value=True)

        result = host.set_self_clean_value(20)

        assert result is True
        assert host.status.previous_self_clean_area == 20

    def test_unchanged_value_skips_previous_tracking(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True)
        host.status = SimpleNamespace(self_clean_value=20, self_clean_by_time=False)
        host._update_self_clean_value = MagicMock(return_value=True)

        result = host.set_self_clean_value(20)

        assert result is True
        assert not hasattr(host.status, "previous_self_clean_area")


class TestSetMopCleanFrequency:
    def test_requires_both_capabilities(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, mop_clean_frequency=False)
        assert host.set_mop_clean_frequency(3) is False

    def test_delegates_when_both_capabilities_present(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True, mop_clean_frequency=True)
        host.set_self_clean_value = MagicMock(return_value=True)

        assert host.set_mop_clean_frequency(3) is True
        host.set_self_clean_value.assert_called_once_with(3)


# ===========================================================================
# set_mop_pad_humidity / set_water_volume: customized-cleaning guard
# ===========================================================================


class TestMopPadHumidityAndWaterVolumeGuards:
    def test_mop_pad_humidity_raises_when_customized_cleaning_active(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True)
        host.status = SimpleNamespace(
            cruising=False, started=True, customized_cleaning=True, zone_cleaning=False, spot_cleaning=False
        )
        with pytest.raises(InvalidActionException, match="customized cleaning"):
            host.set_mop_pad_humidity(2)

    def test_water_volume_raises_when_customized_cleaning_active(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False)
        host.status = SimpleNamespace(
            cruising=False, started=True, customized_cleaning=True, zone_cleaning=False, spot_cleaning=False
        )
        with pytest.raises(InvalidActionException, match="customized cleaning"):
            host.set_water_volume(2)


# ===========================================================================
# set_wetness_level: self-wash-base high-wetness self-clean reduction
# ===========================================================================


class TestSetWetnessLevelSelfCleanReduction:
    def test_high_wetness_reduces_self_clean_when_frequency_capability_absent(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(
            wetness=True, self_wash_base=True, wetness_level=True, self_clean_frequency=False
        )
        host.status = SimpleNamespace(started=False, self_clean_value=25)
        host.set_self_clean_value = MagicMock()
        host.set_property = MagicMock(return_value=True)

        host.set_wetness_level(30)

        host.set_self_clean_value.assert_called_once_with(20)

    def test_high_wetness_reduces_self_clean_when_frequency_by_room(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(
            wetness=True, self_wash_base=True, wetness_level=True, self_clean_frequency=True
        )
        host.status = SimpleNamespace(
            started=False, self_clean_value=25, self_clean_frequency=DreameVacuumSelfCleanFrequency.BY_ROOM
        )
        host.set_self_clean_value = MagicMock()
        host.set_property = MagicMock(return_value=True)

        host.set_wetness_level(30)

        host.set_self_clean_value.assert_called_once_with(20)

    def test_by_area_frequency_skips_reduction(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(
            wetness=True, self_wash_base=True, wetness_level=True, self_clean_frequency=True
        )
        host.status = SimpleNamespace(
            started=False, self_clean_value=25, self_clean_frequency=DreameVacuumSelfCleanFrequency.BY_AREA
        )
        host.set_self_clean_value = MagicMock()
        host.set_property = MagicMock(return_value=True)

        host.set_wetness_level(30)

        host.set_self_clean_value.assert_not_called()

    def test_low_wetness_skips_reduction(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(
            wetness=True, self_wash_base=True, wetness_level=True, self_clean_frequency=False
        )
        host.status = SimpleNamespace(started=False, self_clean_value=25)
        host.set_self_clean_value = MagicMock()
        host.set_property = MagicMock(return_value=True)

        host.set_wetness_level(10)

        host.set_self_clean_value.assert_not_called()


# ===========================================================================
# set_dnd_start / set_dnd_end
# ===========================================================================


class TestSetDndStartEnd:
    def test_dnd_start_uses_plain_property_without_dnd_task(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(dnd_task=False)
        host.set_property = MagicMock(return_value=True)

        assert host.set_dnd_start("07:00") is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.DND_START, "07:00")

    def test_dnd_start_uses_dnd_task_when_capability_enabled(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(dnd_task=True)
        host.status = SimpleNamespace(dnd=True, dnd_end="22:00", dnd_tasks=[])
        host.set_property = MagicMock(return_value=True)

        result = host.set_dnd_start("07:00")

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.DND_TASK, ANY)

    def test_dnd_end_uses_plain_property_without_dnd_task(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(dnd_task=False)
        host.set_property = MagicMock(return_value=True)

        assert host.set_dnd_end("22:00") is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.DND_END, "22:00")

    def test_dnd_end_uses_dnd_task_when_capability_enabled(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(dnd_task=True)
        host.status = SimpleNamespace(dnd=True, dnd_start="07:00", dnd_tasks=[])
        host.set_property = MagicMock(return_value=True)

        result = host.set_dnd_end("23:00")

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.DND_TASK, ANY)


# ===========================================================================
# set_off_peak_charging / start / end wrapper dispatch
# ===========================================================================


class TestSetOffPeakChargingWrappers:
    def test_set_off_peak_charging_delegates_with_current_window(self) -> None:
        host = _host()
        host.status = SimpleNamespace(off_peak_charging_start="22:00", off_peak_charging_end="08:00")
        host.set_off_peak_charging_config = MagicMock(return_value=True)

        result = host.set_off_peak_charging(True)

        assert result is True
        host.set_off_peak_charging_config.assert_called_once_with(True, "22:00", "08:00")

    def test_set_off_peak_charging_start_delegates(self) -> None:
        host = _host()
        host.status = SimpleNamespace(off_peak_charging=True, off_peak_charging_end="08:00")
        host.set_off_peak_charging_config = MagicMock(return_value=True)

        result = host.set_off_peak_charging_start("23:00")

        assert result is True
        host.set_off_peak_charging_config.assert_called_once_with(True, "23:00", "08:00")

    def test_set_off_peak_charging_end_delegates(self) -> None:
        host = _host()
        host.status = SimpleNamespace(off_peak_charging=True, off_peak_charging_start="22:00")
        host.set_off_peak_charging_config = MagicMock(return_value=True)

        result = host.set_off_peak_charging_end("06:00")

        assert result is True
        host.set_off_peak_charging_config.assert_called_once_with(True, "22:00", "06:00")


# ===========================================================================
# set_voice_assistant_language
# ===========================================================================


class TestSetVoiceAssistantLanguage:
    def test_property_not_supported_raises(self) -> None:
        host = _host()
        host.get_property = MagicMock(return_value=None)
        with pytest.raises(InvalidActionException, match="not supported"):
            host.set_voice_assistant_language("english")

    def test_blank_language_raises(self) -> None:
        host = _host()
        host.get_property = MagicMock(return_value=0)
        with pytest.raises(InvalidActionException, match="not supported"):
            host.set_voice_assistant_language("e")

    def test_unknown_language_raises(self) -> None:
        host = _host()
        host.get_property = MagicMock(return_value=0)
        with pytest.raises(InvalidActionException, match="not supported"):
            host.set_voice_assistant_language("klingon")

    def test_known_language_dispatches(self) -> None:
        host = _host()
        host.get_property = MagicMock(return_value=0)
        host.set_property = MagicMock(return_value=True)

        result = host.set_voice_assistant_language("english")

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE, "EN")


# ===========================================================================
# set_washing_mode / set_mop_wash_level
# ===========================================================================


class TestSetWashingMode:
    def test_no_capability_returns_false(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(smart_mop_washing=False)
        assert host.set_washing_mode(1) is False

    def test_unchanged_level_below_three_is_a_noop(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(smart_mop_washing=True)
        host.status = SimpleNamespace(
            mop_wash_level=SimpleNamespace(value=1), ultra_clean_mode=False, smart_mop_washing=False
        )
        host.set_property = MagicMock()

        assert host.set_washing_mode(1) is False
        host.set_property.assert_not_called()

    def test_changed_level_below_three_updates_mop_wash_level(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(smart_mop_washing=True)
        host.status = SimpleNamespace(
            mop_wash_level=SimpleNamespace(value=0), ultra_clean_mode=False, smart_mop_washing=False
        )
        host.set_property = MagicMock(return_value=True)

        assert host.set_washing_mode(1) is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.MOP_WASH_LEVEL, 1)

    def test_success_disables_ultra_clean_mode(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(smart_mop_washing=True)
        host.status = SimpleNamespace(
            mop_wash_level=SimpleNamespace(value=0), ultra_clean_mode=True, smart_mop_washing=False
        )
        host.set_property = MagicMock(return_value=True)
        host.set_auto_switch_property = MagicMock(return_value=True)

        host.set_washing_mode(1)

        host.set_auto_switch_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE, 0)

    def test_level_three_or_more_enables_ultra_clean_mode(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(smart_mop_washing=True, ultra_clean_mode=True)
        host.status = SimpleNamespace(
            mop_wash_level=SimpleNamespace(value=0), ultra_clean_mode=False, smart_mop_washing=False
        )
        host.set_auto_switch_property = MagicMock(return_value=True)

        result = host.set_washing_mode(3)

        assert result is True
        host.set_auto_switch_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE, 1)

    def test_success_disables_smart_mop_washing(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(smart_mop_washing=True, ultra_clean_mode=False)
        host.status = SimpleNamespace(
            mop_wash_level=SimpleNamespace(value=0), ultra_clean_mode=False, smart_mop_washing=True
        )
        host.set_property = MagicMock(return_value=True)

        host.set_washing_mode(1)

        assert host.set_property.call_args_list[-1] == call(DreameVacuumProperty.SMART_MOP_WASHING, 0)


class TestSetMopWashLevel:
    def test_smart_mop_washing_capability_returns_false(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(smart_mop_washing=True)
        assert host.set_mop_wash_level(1) is False

    def test_success_without_ultra_clean_mode_returns_result(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(smart_mop_washing=False, ultra_clean_mode=False)
        host.set_property = MagicMock(return_value=True)

        assert host.set_mop_wash_level(2) is True

    def test_success_disables_active_ultra_clean_mode(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(smart_mop_washing=False, ultra_clean_mode=True)
        host.status = SimpleNamespace(ultra_clean_mode=True)
        host.set_property = MagicMock(return_value=True)
        host.set_auto_switch_property = MagicMock(return_value=True)

        result = host.set_mop_wash_level(2)

        assert result is True
        host.set_auto_switch_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE, 0)

    def test_failure_skips_ultra_clean_mode_check(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(smart_mop_washing=False, ultra_clean_mode=True)
        host.status = SimpleNamespace(ultra_clean_mode=True)
        host.set_property = MagicMock(return_value=False)
        host.set_auto_switch_property = MagicMock()

        result = host.set_mop_wash_level(2)

        assert result is False
        host.set_auto_switch_property.assert_not_called()


# ===========================================================================
# set_drying_time
# ===========================================================================


class TestSetDryingTime:
    def test_success_without_silent_drying(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(silent_drying=False)
        host.set_property = MagicMock(return_value=True)

        assert host.set_drying_time(120) is True

    def test_success_disables_silent_drying(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(silent_drying=True)
        host.status = SimpleNamespace(silent_drying=True)
        host.set_property = MagicMock(return_value=True)

        host.set_drying_time(120)

        assert host.set_property.call_args_list == [
            call(DreameVacuumProperty.DRYING_TIME, 120),
            call(DreameVacuumProperty.SILENT_DRYING, 0),
        ]

    def test_failure_skips_silent_drying_check(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(silent_drying=True)
        host.status = SimpleNamespace(silent_drying=True)
        host.set_property = MagicMock(return_value=False)

        result = host.set_drying_time(120)

        assert result is False
        host.set_property.assert_called_once_with(DreameVacuumProperty.DRYING_TIME, 120)


# ===========================================================================
# set_ai_detection
# ===========================================================================


class TestSetAiDetection:
    def test_no_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=False)
        assert host.set_ai_detection(1) is None

    def test_int_settings_sent_directly(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host.property_mapping = {DreameVacuumProperty.AI_DETECTION: {"siid": 9, "piid": 1}}
        host._protocol.set_property = MagicMock(return_value=[{"code": 0}])

        result = host.set_ai_detection(5)

        assert result == [{"code": 0}]
        host._protocol.set_property.assert_called_once_with(9, 1, 5, 3)

    def test_dict_settings_sent_as_json(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host.property_mapping = {DreameVacuumProperty.AI_DETECTION: {"siid": 9, "piid": 1}}
        host._protocol.set_property = MagicMock(return_value=[{"code": 0}])

        host.set_ai_detection({"pet": True})

        args, _ = host._protocol.set_property.call_args
        assert args[0:2] == (9, 1)
        assert json.loads(args[2]) == {"pet": True}
        assert args[3] == 3


# ===========================================================================
# set_ai_property
# ===========================================================================


class TestSetAiProperty:
    def test_no_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=False)
        assert host.set_ai_property(DreameVacuumAIProperty.AI_PET_DETECTION, True) is None

    def test_unsupported_property_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host.ai_data = {}
        with pytest.raises(InvalidActionException, match="Not supported"):
            host.set_ai_property(DreameVacuumAIProperty.AI_PET_DETECTION, True)

    def test_bitwise_int_ai_value_sets_bit(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host.ai_data = {"AI_PET_DETECTION": False}
        host.get_property = MagicMock(return_value=0)
        host.set_ai_detection = MagicMock(return_value=[{"code": 0}])

        result = host.set_ai_property(DreameVacuumAIProperty.AI_PET_DETECTION, True)

        assert result == [{"code": 0}]
        host.set_ai_detection.assert_called_once_with(DreameVacuumAIProperty.AI_PET_DETECTION.value)
        assert host.ai_data["AI_PET_DETECTION"] is True

    def test_bitwise_int_ai_value_clears_bit(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host.ai_data = {"AI_PET_DETECTION": True}
        bit = DreameVacuumAIProperty.AI_PET_DETECTION.value
        # ``get_property(AI_DETECTION)`` (the raw bitmask) is called exactly once;
        # ``get_ai_property`` (for ``current_value``) reads ``ai_data`` directly and is
        # not mocked here.
        host.get_property = MagicMock(return_value=bit)
        host.set_ai_detection = MagicMock(return_value=[{"code": 0}])

        host.set_ai_property(DreameVacuumAIProperty.AI_PET_DETECTION, False)

        host.set_ai_detection.assert_called_once_with(0)

    def test_string_ai_value_dispatches_dict(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host.ai_data = {"AI_HUMAN_DETECTION": False}
        # A non-int AI_DETECTION bitmask routes through the string/JSON branch instead
        # of the bitwise one (AI_HUMAN_DETECTION has no ``DreameVacuumAIProperty`` member).
        host.get_property = MagicMock(return_value=None)
        host.set_ai_detection = MagicMock(return_value=[{"code": 0}])

        host.set_ai_property(DreameVacuumStrAIProperty.AI_HUMAN_DETECTION, True)

        host.set_ai_detection.assert_called_once_with({"human_detect_switch": True})

    def test_failure_result_rolls_back(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host.ai_data = {"AI_PET_DETECTION": False}
        host.get_property = MagicMock(return_value=0)
        host.set_ai_detection = MagicMock(return_value=[{"code": 1}])

        host.set_ai_property(DreameVacuumAIProperty.AI_PET_DETECTION, True)

        assert host.ai_data["AI_PET_DETECTION"] is False
        assert "AI_PET_DETECTION" not in host._dirty_ai_data

    def test_exception_rolls_back(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host.ai_data = {"AI_PET_DETECTION": False}
        host.get_property = MagicMock(return_value=0)
        host.set_ai_detection = MagicMock(side_effect=ValueError("boom"))

        result = host.set_ai_property(DreameVacuumAIProperty.AI_PET_DETECTION, True)

        assert result is None
        assert host.ai_data["AI_PET_DETECTION"] is False


# ===========================================================================
# set_auto_switch_settings
# ===========================================================================


class TestSetAutoSwitchSettings:
    def test_no_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=False)
        assert host.set_auto_switch_settings({"k": "x", "v": 1}) is None

    def test_sends_json_payload(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.property_mapping = {DreameVacuumProperty.AUTO_SWITCH_SETTINGS: {"siid": 9, "piid": 2}}
        host._protocol.set_property = MagicMock(return_value=[{"code": 0}])

        result = host.set_auto_switch_settings({"k": "SmartHost", "v": 1})

        assert result == [{"code": 0}]
        args, _ = host._protocol.set_property.call_args
        assert args[0:2] == (9, 2)
        assert json.loads(args[2]) == {"k": "SmartHost", "v": 1}
        assert args[3] == 1


# ===========================================================================
# set_camera_light_brightness
# ===========================================================================


class TestSetCameraLightBrightness:
    def test_no_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=False)
        assert host.set_camera_light_brightness(50) is None

    def test_clamps_minimum_to_forty(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.status = SimpleNamespace(camera_light_brightness=60)
        host.call_stream_property_action = MagicMock(return_value={"code": 0})

        host.set_camera_light_brightness(10)

        host.call_stream_property_action.assert_called_once_with(
            DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, {"value": "40"}
        )

    def test_success_updates_property_in_memory(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.status = SimpleNamespace(camera_light_brightness=60)
        host.call_stream_property_action = MagicMock(return_value={"code": 0})

        result = host.set_camera_light_brightness(80)

        assert result == {"code": 0}
        assert host._update_property.call_args_list[0] == call(DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, "80")

    def test_failure_restores_previous_value(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.status = SimpleNamespace(camera_light_brightness=60)
        host.call_stream_property_action = MagicMock(return_value={"code": 1})

        host.set_camera_light_brightness(80)

        assert host._update_property.call_args_list == [
            call(DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, "80"),
            call(DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, "60"),
        ]

    def test_none_result_restores_previous_value(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.status = SimpleNamespace(camera_light_brightness=60)
        host.call_stream_property_action = MagicMock(return_value=None)

        host.set_camera_light_brightness(80)

        assert host._update_property.call_args_list[-1] == call(DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, "60")


# ===========================================================================
# set_wider_corner_coverage / set_mop_pad_swing / set_auto_recleaning / set_auto_rewashing
# ===========================================================================


class TestToggleLikeAutoSwitchSetters:
    def test_wider_corner_coverage_no_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=False)
        assert host.set_wider_corner_coverage(1) is None

    def test_wider_corner_coverage_negates_current_when_disabling(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.get_auto_switch_property = MagicMock(return_value=7)
        host.set_auto_switch_property = MagicMock(return_value={"code": 0})

        host.set_wider_corner_coverage(0)

        host.set_auto_switch_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.WIDER_CORNER_COVERAGE, -7)

    def test_wider_corner_coverage_passes_through_positive_value(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.get_auto_switch_property = MagicMock(return_value=0)
        host.set_auto_switch_property = MagicMock(return_value={"code": 0})

        host.set_wider_corner_coverage(1)

        host.set_auto_switch_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.WIDER_CORNER_COVERAGE, 1)

    def test_mop_pad_swing_no_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=False)
        assert host.set_mop_pad_swing(1) is None

    def test_mop_pad_swing_negates_current_when_disabling(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True)
        host.get_auto_switch_property = MagicMock(return_value=2)
        host.set_auto_switch_property = MagicMock(return_value={"code": 0})

        host.set_mop_pad_swing(-1)

        host.set_auto_switch_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.MOP_PAD_SWING, -2)

    def test_auto_recleaning_requires_both_capabilities(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True, auto_recleaning=False)
        assert host.set_auto_recleaning(1) is None

    def test_auto_recleaning_negates_current_when_disabling(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True, auto_recleaning=True)
        host.get_auto_switch_property = MagicMock(return_value=1)
        host.set_auto_switch_property = MagicMock(return_value={"code": 0})

        host.set_auto_recleaning(0)

        host.set_auto_switch_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.AUTO_RECLEANING, -1)

    def test_auto_rewashing_requires_both_capabilities(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True, auto_rewashing=False)
        assert host.set_auto_rewashing(1) is None

    def test_auto_rewashing_negates_current_when_disabling(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True, auto_rewashing=True)
        host.get_auto_switch_property = MagicMock(return_value=1)
        host.set_auto_switch_property = MagicMock(return_value={"code": 0})

        host.set_auto_rewashing(0)

        host.set_auto_switch_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.AUTO_REWASHING, -1)


# ===========================================================================
# set_self_clean_frequency
# ===========================================================================


class TestSetSelfCleanFrequency:
    def test_no_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=False)
        assert host.set_self_clean_frequency(1) is None

    def test_disabling_by_time_records_previous_time(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True, self_clean_frequency=False)
        host.status = SimpleNamespace(self_clean_value=42)
        host.get_auto_switch_property = MagicMock(return_value=DreameVacuumSelfCleanFrequency.BY_TIME.value)
        host.set_self_clean_value = MagicMock(return_value=True)

        result = host.set_self_clean_frequency(0)

        assert result is True
        assert host.status.previous_self_clean_time == 42
        host.set_self_clean_value.assert_called_once_with(0)

    def test_disabling_by_area_records_previous_area(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True, self_clean_frequency=False)
        host.status = SimpleNamespace(self_clean_value=17)
        host.get_auto_switch_property = MagicMock(return_value=DreameVacuumSelfCleanFrequency.BY_AREA.value)
        host.set_self_clean_value = MagicMock(return_value=True)

        host.set_self_clean_frequency(0)

        assert host.status.previous_self_clean_area == 17

    def test_enabling_by_time_restores_previous_time_or_default(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True, self_clean_frequency=True)
        host.status = SimpleNamespace(self_clean_value=0, previous_self_clean_time=33, self_clean_time_default=15)
        host.get_auto_switch_property = MagicMock(return_value=0)
        host.set_auto_switch_property = MagicMock(return_value=True)
        host.set_self_clean_value = MagicMock(return_value=True)

        result = host.set_self_clean_frequency(DreameVacuumSelfCleanFrequency.BY_TIME.value)

        assert result is True
        host.set_self_clean_value.assert_called_once_with(33)

    def test_enabling_by_area_restores_previous_area_or_default(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True, self_clean_frequency=True)
        host.status = SimpleNamespace(self_clean_value=0, previous_self_clean_area=0, self_clean_area_default=12)
        host.get_auto_switch_property = MagicMock(return_value=0)
        host.set_auto_switch_property = MagicMock(return_value=True)
        host.set_self_clean_value = MagicMock(return_value=True)

        host.set_self_clean_frequency(DreameVacuumSelfCleanFrequency.BY_AREA.value)

        host.set_self_clean_value.assert_called_once_with(12)

    def test_without_frequency_capability_zero_value_still_clears_self_clean(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_switch_settings=True, self_clean_frequency=False)
        host.status = SimpleNamespace(self_clean_value=0)
        host.get_auto_switch_property = MagicMock(return_value=0)
        host.set_self_clean_value = MagicMock(return_value="cleared")

        result = host.set_self_clean_frequency(0)

        assert result == "cleared"


# ===========================================================================
# set_auto_empty_mode / set_custom_mopping_route / set_resume_cleaning
# ===========================================================================


class TestSetAutoEmptyMode:
    def test_no_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_empty_mode=False)
        assert host.set_auto_empty_mode(1) is None

    def test_delegates_to_set_property(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_empty_mode=True)
        host.set_property = MagicMock(return_value=True)

        result = host.set_auto_empty_mode(2)

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.AUTO_DUST_COLLECTING, 2)


class TestSetCustomMoppingRoute:
    def test_no_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(custom_mopping_route=False)
        assert host.set_custom_mopping_route(1) is None

    def test_negative_value_disables_and_restores_water_level(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(custom_mopping_route=True, self_wash_base=False)
        host.status = SimpleNamespace(custom_mopping_mode=True)
        host.set_auto_switch_property = MagicMock(return_value=True)
        host.get_auto_switch_property = MagicMock(return_value=2)
        host._update_water_level = MagicMock(return_value=True)

        result = host.set_custom_mopping_route(-1)

        assert result is True
        host.set_auto_switch_property.assert_any_call(DreameVacuumAutoSwitchProperty.CUSTOM_MOPPING_MODE, 0)
        host._update_water_level.assert_called_once_with(2)

    def test_enabling_when_not_active_syncs_water_level_first(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(custom_mopping_route=True, self_wash_base=False)
        host.status = SimpleNamespace(custom_mopping_mode=False, water_volume=SimpleNamespace(value=3))
        host.set_auto_switch_property = MagicMock(return_value=True)
        host._update_water_level = MagicMock()

        host.set_custom_mopping_route(1)

        host._update_water_level.assert_called_once_with(3)
        assert host.set_auto_switch_property.call_args_list[-1] == call(DreameVacuumAutoSwitchProperty.MOPPING_TYPE, 1)

    def test_enabling_self_wash_base_uses_mop_pad_humidity(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(custom_mopping_route=True, self_wash_base=True)
        host.status = SimpleNamespace(custom_mopping_mode=False, mop_pad_humidity=2)
        host.set_auto_switch_property = MagicMock(return_value=True)
        host._update_water_level = MagicMock()

        host.set_custom_mopping_route(2)

        host._update_water_level.assert_called_once_with(2)

    def test_already_active_skips_resync(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(custom_mopping_route=True, self_wash_base=False)
        host.status = SimpleNamespace(custom_mopping_mode=True)
        host.set_auto_switch_property = MagicMock(return_value=True)
        host._update_water_level = MagicMock()

        host.set_custom_mopping_route(2)

        host._update_water_level.assert_not_called()
        host.set_auto_switch_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.MOPPING_TYPE, 2)


class TestSetResumeCleaning:
    def test_auto_charging_capability_forces_value_two(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_charging=True)
        host.set_property = MagicMock(return_value=True)

        host.set_resume_cleaning(1)

        host.set_property.assert_called_once_with(DreameVacuumProperty.RESUME_CLEANING, 2)

    def test_without_capability_passes_value_through(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_charging=False)
        host.set_property = MagicMock(return_value=True)

        host.set_resume_cleaning(1)

        host.set_property.assert_called_once_with(DreameVacuumProperty.RESUME_CLEANING, 1)

    def test_falsy_value_is_not_forced(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_charging=True)
        host.set_property = MagicMock(return_value=True)

        host.set_resume_cleaning(0)

        host.set_property.assert_called_once_with(DreameVacuumProperty.RESUME_CLEANING, 0)


# ===========================================================================
# set_carpet_cleaning / set_carpet_recognition: remaining branches
# ===========================================================================


class TestCarpetSettersRemainingBranches:
    def test_carpet_cleaning_value_three_unmounts_mop_when_needed(self) -> None:
        host = _host()
        host.get_property = MagicMock(return_value=1)
        host.capability = SimpleNamespace(
            mop_pad_lifting_plus=True,
            auto_carpet_cleaning=False,
            carpet_crossing=False,
            mop_pad_unmounting=True,
        )
        host.status = SimpleNamespace(carpet_recognition=True, auto_mount_mop=False)
        host.set_property = MagicMock(return_value=True)

        host.set_carpet_cleaning(3)

        assert host.set_property.call_args_list == [
            call(DreameVacuumProperty.CARPET_CLEANING, 3),
            call(DreameVacuumProperty.AUTO_MOUNT_MOP, 1),
        ]

    def test_carpet_cleaning_value_three_skips_unmount_when_already_mounted(self) -> None:
        host = _host()
        host.get_property = MagicMock(return_value=1)
        host.capability = SimpleNamespace(
            mop_pad_lifting_plus=True,
            auto_carpet_cleaning=False,
            carpet_crossing=False,
            mop_pad_unmounting=True,
        )
        host.status = SimpleNamespace(carpet_recognition=True, auto_mount_mop=True)
        host.set_property = MagicMock(return_value=True)

        host.set_carpet_cleaning(3)

        host.set_property.assert_called_once_with(DreameVacuumProperty.CARPET_CLEANING, 3)

    def test_carpet_cleaning_enables_recognition_first_when_disabled(self) -> None:
        host = _host()
        host.get_property = MagicMock(return_value=1)
        host.capability = SimpleNamespace(
            mop_pad_lifting_plus=True, auto_carpet_cleaning=False, carpet_crossing=False, mop_pad_unmounting=False
        )
        host.status = SimpleNamespace(carpet_recognition=False, auto_mount_mop=True)
        host.set_property = MagicMock(return_value=True)
        host.set_carpet_recognition = MagicMock()

        host.set_carpet_cleaning(3)

        host.set_carpet_recognition.assert_called_once_with(1)

    def test_carpet_cleaning_value_four_unsupported_combo_raises(self) -> None:
        host = _host()
        host.get_property = MagicMock(return_value=1)
        host.capability = SimpleNamespace(mop_pad_lifting_plus=False, auto_carpet_cleaning=True, carpet_crossing=False)
        with pytest.raises(InvalidActionException, match="not supported"):
            host.set_carpet_cleaning(4)

    def test_carpet_recognition_disabling_with_boost_falls_back_to_three(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(carpet_recognition=True)
        host.get_property = MagicMock(side_effect=[5, 1])
        host.set_property = MagicMock(return_value=True)

        host.set_carpet_recognition(0)

        assert host.set_property.call_args_list == [
            call(DreameVacuumProperty.CARPET_RECOGNITION, 3),
            call(DreameVacuumProperty.CARPET_BOOST, 0),
        ]

    def test_carpet_recognition_returns_none_when_current_value_missing(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(carpet_recognition=True)
        host.get_property = MagicMock(return_value=None)
        host.set_property = MagicMock()

        assert host.set_carpet_recognition(1) is None
        host.set_property.assert_not_called()


# ===========================================================================
# set_obstacle_ignore
# ===========================================================================


class TestSetObstacleIgnore:
    def test_no_ai_detection_capability_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=False)
        with pytest.raises(InvalidActionException, match="not available"):
            host.set_obstacle_ignore(1, 2, True)

    def test_no_map_manager_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host._map_manager = None
        with pytest.raises(InvalidActionException, match="cloud connection"):
            host.set_obstacle_ignore(1, 2, True)

    def test_started_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host._map_manager = MagicMock()
        host.status = SimpleNamespace(started=True)
        with pytest.raises(InvalidActionException, match="while vacuum is running"):
            host.set_obstacle_ignore(1, 2, True)

    def test_no_obstacles_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host._map_manager = MagicMock()
        host.status = SimpleNamespace(started=False, current_map=SimpleNamespace(obstacles=None))
        with pytest.raises(InvalidActionException, match="Obstacle not found"):
            host.set_obstacle_ignore(1, 2, True)

    def test_unsupported_ignore_status_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host._map_manager = MagicMock()
        obstacle = SimpleNamespace(x=1, y=2, ignore_status=None, type=SimpleNamespace(value=142))
        host.status = SimpleNamespace(started=False, current_map=SimpleNamespace(obstacles={"a": obstacle}))
        with pytest.raises(InvalidActionException, match="not supported"):
            host.set_obstacle_ignore(1, 2, True)

    def test_dynamically_ignored_obstacle_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host._map_manager = MagicMock()
        obstacle = SimpleNamespace(x=1, y=2, ignore_status=SimpleNamespace(value=2), type=SimpleNamespace(value=142))
        host.status = SimpleNamespace(started=False, current_map=SimpleNamespace(obstacles={"a": obstacle}))
        with pytest.raises(InvalidActionException, match="dynamically ignored"):
            host.set_obstacle_ignore(1, 2, True)

    def test_obstacle_not_found_at_coordinate_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host._map_manager = MagicMock()
        obstacle = SimpleNamespace(x=10, y=20, ignore_status=SimpleNamespace(value=0), type=SimpleNamespace(value=142))
        host.status = SimpleNamespace(started=False, current_map=SimpleNamespace(obstacles={"a": obstacle}))
        with pytest.raises(InvalidActionException, match="Obstacle not found"):
            host.set_obstacle_ignore(1, 2, True)

    def test_success_updates_map_and_schedules_async_update(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(ai_detection=True)
        host._map_manager = MagicMock()
        obstacle = SimpleNamespace(x=1, y=2, ignore_status=SimpleNamespace(value=0), type=SimpleNamespace(value=99))
        host.status = SimpleNamespace(started=False, current_map=SimpleNamespace(obstacles={"a": obstacle}))
        host.update_map_data_async = MagicMock()

        result = host.set_obstacle_ignore(1, 2, True)

        assert result is None
        host._map_manager.editor.set_obstacle_ignore.assert_called_once_with(1, 2, True)
        host.update_map_data_async.assert_called_once_with({"obstacleignore": [1, 2, 99, 1]})


# ===========================================================================
# set_router_position
# ===========================================================================


class TestSetRouterPosition:
    def test_no_wifi_map_capability_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(wifi_map=False)
        with pytest.raises(InvalidActionException, match="not available"):
            host.set_router_position(1, 2)

    def test_started_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(wifi_map=True)
        host.status = SimpleNamespace(started=True)
        with pytest.raises(InvalidActionException, match="while vacuum is running"):
            host.set_router_position(1, 2)

    def test_success_updates_map_manager_and_schedules_async(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(wifi_map=True)
        host.status = SimpleNamespace(started=False)
        host._map_manager = MagicMock()
        host.update_map_data_async = MagicMock()

        host.set_router_position(3, 4)

        host._map_manager.editor.set_router_position.assert_called_once_with(3, 4)
        host.update_map_data_async.assert_called_once_with({"wrp": [3, 4]})

    def test_success_without_map_manager_still_schedules_async(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(wifi_map=True)
        host.status = SimpleNamespace(started=False)
        host._map_manager = None
        host.update_map_data_async = MagicMock()

        host.set_router_position(3, 4)

        host.update_map_data_async.assert_called_once_with({"wrp": [3, 4]})
