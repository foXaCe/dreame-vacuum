"""Characterization tests for DreameVacuumDeviceSettersMixin.

Strategy: a minimal host class that inherits only the setters mixin, with
collaborator methods/attributes (``schedule_update``, ``_update_property``,
``_protocol``, ``property_mapping``...) supplied per test via plain mocks or
``SimpleNamespace``. This isolates the mixin's own decision logic (optimistic
update + rollback, reflection-based dispatch, HH:MM validation, typed
setters) from the rest of the real ``DreameVacuumDevice`` machinery.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY, MagicMock, call

import pytest

from custom_components.dreame_vacuum.dreame.device_setters import DreameVacuumDeviceSettersMixin
from custom_components.dreame_vacuum.dreame.exceptions import (
    DeviceUpdateFailedException,
    InvalidActionException,
    InvalidValueException,
)
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    DreameVacuumAction,
    DreameVacuumAIProperty,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumCleaningMode,
    DreameVacuumProperty,
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
