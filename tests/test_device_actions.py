"""Characterization tests for DreameVacuumDeviceActionsMixin.

Strategy: a minimal host class that inherits only the actions mixin.
Collaborator methods that live on sibling mixins (``_restore_go_to_zone``,
``_update_suction_level``, ``set_property``...) are supplied per test as
plain ``MagicMock`` spies, isolating the orchestration logic in this mixin
(``call_action``'s optimistic updates, consumable resets, start/stop/pause,
zone/segment cleaning payload construction) from the rest of the real
``DreameVacuumDevice``.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import ANY, MagicMock, call

import pytest

from custom_components.dreame_vacuum.dreame.device_actions import (
    _RESET_CONSUMABLES,
    DreameVacuumDeviceActionsMixin,
)
from custom_components.dreame_vacuum.dreame.exceptions import (
    InvalidActionException,
    InvalidValueException,
)
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    PIID,
    CleanupMethod,
    DreameVacuumAction,
    DreameVacuumAutoEmptyStatus,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumCleanGenius,
    DreameVacuumCleaningMode,
    DreameVacuumErrorCode,
    DreameVacuumProperty,
    DreameVacuumSelfWashBaseStatus,
    DreameVacuumState,
    DreameVacuumStatus,
    DreameVacuumStreamStatus,
    DreameVacuumTaskStatus,
    Shortcut,
)

# ---------------------------------------------------------------------------
# Host + builder
# ---------------------------------------------------------------------------


class _Host(DreameVacuumDeviceActionsMixin):
    """Minimal host exposing only the actions-mixin contract."""

    @property
    def device_connected(self) -> bool:
        return self._protocol.connected


def _host(**attrs: Any) -> Any:
    host: Any = _Host()
    host.schedule_update = MagicMock()
    host._update_property = MagicMock()
    host._property_changed = MagicMock()
    host._update_status = MagicMock()
    host._last_change = 0
    host._last_settings_request = 0
    host._consumable_change = False
    host._map_select_time = None
    host._map_manager = None
    host._remote_control = False
    host.info = None
    host.action_mapping = {}
    host.property_mapping = {}
    host._protocol = MagicMock()
    host._protocol.connected = True
    host._protocol.dreame_cloud = False
    host._protocol.action = MagicMock(return_value={"code": 0})
    host.status = SimpleNamespace(draining_complete=False)
    host.capability = SimpleNamespace()
    for key, value in attrs.items():
        setattr(host, key, value)
    return host


# ===========================================================================
# call_action: core dispatcher
# ===========================================================================


class TestCallActionCore:
    def test_unknown_action_raises(self) -> None:
        host = _host()
        with pytest.raises(InvalidActionException, match="action mapping"):
            host.call_action(DreameVacuumAction.LOCATE)

    def test_mapping_missing_siid_or_aiid_raises(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.LOCATE: {"siid": 1}})
        with pytest.raises(InvalidActionException, match="not an action"):
            host.call_action(DreameVacuumAction.LOCATE)

    def test_draining_complete_clears_drainage_status_first(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.LOCATE: {"siid": 7, "aiid": 1}})
        host.status = SimpleNamespace(draining_complete=True)
        host.set_property = MagicMock(return_value=True)

        host.call_action(DreameVacuumAction.LOCATE)

        host.set_property.assert_called_once_with(DreameVacuumProperty.DRAINAGE_STATUS, 0)

    def test_protocol_exception_returns_none_and_schedules_retry(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.LOCATE: {"siid": 7, "aiid": 1}})
        host._protocol.action.side_effect = OSError("disconnected")

        result = host.call_action(DreameVacuumAction.LOCATE)

        assert result is None
        host.schedule_update.assert_called_with(1, True)

    def test_action_unavailable_for_noncleaning_action_raises(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.RESET_MAIN_BRUSH: {"siid": 7, "aiid": 1}})
        host.status = SimpleNamespace(draining_complete=False, main_brush_life=100)

        with pytest.raises(InvalidActionException, match="Action unavailable"):
            host.call_action(DreameVacuumAction.RESET_MAIN_BRUSH)

        host._protocol.action.assert_not_called()

    def test_successful_action_updates_change_tracking(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.LOCATE: {"siid": 7, "aiid": 1}})
        host._last_settings_request = 123

        result = host.call_action(DreameVacuumAction.LOCATE)

        assert result == {"code": 0}
        host._protocol.action.assert_called_once_with(7, 1, None)
        assert host._last_change > 0
        assert host._last_settings_request == 0

    def test_failed_result_code_does_not_reset_last_settings_request(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.LOCATE: {"siid": 7, "aiid": 1}})
        host._protocol.action.return_value = {"code": 1}
        host._last_settings_request = 123

        result = host.call_action(DreameVacuumAction.LOCATE)

        assert result == {"code": 1}
        assert host._last_settings_request == 123
        assert host._last_change == 0

    def test_parameters_are_forwarded_to_protocol(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.LOCATE: {"siid": 7, "aiid": 1}})
        params = [{"piid": 10, "value": "x"}]

        host.call_action(DreameVacuumAction.LOCATE, params)

        host._protocol.action.assert_called_once_with(7, 1, params)


# ===========================================================================
# Consumable resets: table-driven dispatch
# ===========================================================================

_ALL_LIFE_ATTRS = [
    "main_brush_life",
    "side_brush_life",
    "filter_life",
    "sensor_dirty_life",
    "tank_filter_life",
    "mop_life",
    "silver_ion_life",
    "detergent_life",
    "squeegee_life",
    "onboard_dirty_water_tank_life",
    "dirty_water_tank_life",
    "deodorizer_life",
    "wheel_dirty_life",
    "scale_inhibitor_life",
]


class TestResetConsumables:
    @pytest.mark.parametrize("action", list(_RESET_CONSUMABLES.keys()), ids=lambda a: a.name)
    def test_reset_action_writes_left_and_time_left(self, action: DreameVacuumAction) -> None:
        left_prop, time_left_prop, time_left_default = _RESET_CONSUMABLES[action]
        host = _host(action_mapping={action: {"siid": 9, "aiid": 3}})
        host.status = SimpleNamespace(
            draining_complete=False,
            **dict.fromkeys(_ALL_LIFE_ATTRS, 50),
        )

        result = host.call_action(action)

        assert result == {"code": 0}
        assert host._update_property.call_args_list == [
            call(left_prop, 100),
            call(time_left_prop, time_left_default),
        ]
        assert host._consumable_change is True
        host._property_changed.assert_called_once_with(False)
        host._protocol.action.assert_called_once_with(9, 3, None)

    def test_unavailable_reset_raises_before_touching_properties(self) -> None:
        """When the consumable is already at 100%, the action is rejected up front."""
        host = _host(action_mapping={DreameVacuumAction.RESET_MAIN_BRUSH: {"siid": 9, "aiid": 3}})
        host.status = SimpleNamespace(draining_complete=False, main_brush_life=100)

        with pytest.raises(InvalidActionException, match="Action unavailable"):
            host.call_action(DreameVacuumAction.RESET_MAIN_BRUSH)

        host._update_property.assert_not_called()
        assert host._consumable_change is False


# ===========================================================================
# start / stop / pause / return_to_base (dock)
# ===========================================================================


class TestStart:
    def test_raises_when_draining(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            fast_mapping_paused=False,
            returning_paused=False,
            returning_to_wash_paused=False,
            paused=False,
            draining=True,
            self_repairing=False,
        )
        host.capability = SimpleNamespace(cruising=False)
        host._restore_go_to_zone = MagicMock()

        with pytest.raises(InvalidActionException, match="draining"):
            host.start()

    def test_fast_mapping_paused_resumes_fast_mapping(self) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping_paused=True)
        host.start_custom = MagicMock(return_value={"code": 0})

        result = host.start()

        assert result == {"code": 0}
        host._update_status.assert_called_once_with(
            DreameVacuumTaskStatus.FAST_MAPPING, DreameVacuumStatus.FAST_MAPPING
        )
        host.start_custom.assert_called_once_with(DreameVacuumStatus.FAST_MAPPING.value)

    def test_returning_paused_delegates_to_return_to_base(self) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping_paused=False, returning_paused=True)
        host.return_to_base = MagicMock(return_value={"code": 0})

        result = host.start()

        assert result == {"code": 0}
        host.return_to_base.assert_called_once_with()

    def test_returning_to_wash_paused_delegates_to_start_washing(self) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping_paused=False, returning_paused=False, returning_to_wash_paused=True)
        host.start_washing = MagicMock(return_value={"code": 0})

        result = host.start()

        assert result == {"code": 0}
        host.start_washing.assert_called_once_with()

    def test_normal_start_updates_status_and_calls_action(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            fast_mapping_paused=False,
            returning_paused=False,
            returning_to_wash_paused=False,
            paused=False,
            draining=False,
            self_repairing=False,
            started=False,
        )
        host.capability = SimpleNamespace(cruising=False)
        host._restore_go_to_zone = MagicMock()
        host.call_action = MagicMock(return_value={"code": 0})

        result = host.start()

        assert result == {"code": 0}
        host._restore_go_to_zone.assert_called_once_with()
        host._update_status.assert_called_once_with(DreameVacuumTaskStatus.AUTO_CLEANING, DreameVacuumStatus.CLEANING)
        host.call_action.assert_called_once_with(DreameVacuumAction.START)

    def test_resume_from_pause_updates_state_and_status_in_memory(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            fast_mapping_paused=False,
            returning_paused=False,
            returning_to_wash_paused=False,
            paused=True,
            cleaning_paused=False,
            cruising=False,
            scheduled_clean=False,
            draining=False,
            self_repairing=False,
            started=True,
            task_status=DreameVacuumTaskStatus.SEGMENT_CLEANING_PAUSED,
            cleaning_mode=DreameVacuumCleaningMode.MOPPING,
        )
        host.capability = SimpleNamespace(cruising=False)
        host.call_action = MagicMock(return_value={"code": 0})

        host.start()

        assert host._update_property.call_args_list == [
            call(DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value),
            call(DreameVacuumProperty.STATE, DreameVacuumState.MOPPING.value),
        ]
        host._update_status.assert_not_called()


class TestStop:
    def test_fast_mapping_delegates_to_return_to_base(self) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping=True)
        host.return_to_base = MagicMock(return_value={"code": 0})

        result = host.stop()

        assert result == {"code": 0}
        host.return_to_base.assert_called_once_with()

    def test_raises_when_self_repairing(self) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping=False, draining=False, self_repairing=True)
        with pytest.raises(InvalidActionException, match="repairing"):
            host.stop()

    def test_go_to_zone_response_short_circuits_final_action_call(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            fast_mapping=False,
            draining=False,
            self_repairing=False,
            go_to_zone=True,
            started=True,
        )
        host._map_manager = MagicMock()
        host.call_action = MagicMock(return_value={"code": 0})

        result = host.stop()

        assert result == {"code": 0}
        host.call_action.assert_called_once_with(DreameVacuumAction.STOP)
        host._update_status.assert_called_once_with(DreameVacuumTaskStatus.COMPLETED, DreameVacuumStatus.STANDBY)
        host._map_manager.editor.set_active_areas.assert_called_once_with([])
        host._map_manager.editor.set_cruise_points.assert_called_once_with([])
        host._map_manager.editor.set_active_segments.assert_called_once_with([])

    def test_drying_when_not_started_delegates_to_stop_drying(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            fast_mapping=False,
            draining=False,
            self_repairing=False,
            go_to_zone=False,
            started=False,
            drying=True,
        )
        host.stop_drying = MagicMock(return_value={"code": 0})

        result = host.stop()

        assert result == {"code": 0}
        host.stop_drying.assert_called_once_with()

    def test_normal_stop_calls_action_exactly_once(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            fast_mapping=False,
            draining=False,
            self_repairing=False,
            go_to_zone=False,
            started=False,
            drying=False,
        )
        host.call_action = MagicMock(return_value={"code": 0})

        result = host.stop()

        assert result == {"code": 0}
        host.call_action.assert_called_once_with(DreameVacuumAction.STOP)


class TestPause:
    def test_raises_when_draining(self) -> None:
        host = _host()
        host.status = SimpleNamespace(draining=True, self_repairing=False)
        with pytest.raises(InvalidActionException, match="draining"):
            host.pause()

    def test_washing_and_not_started_delegates_to_pause_washing(self) -> None:
        host = _host()
        host.status = SimpleNamespace(draining=False, self_repairing=False, started=False, washing=True)
        host.pause_washing = MagicMock(return_value={"code": 0})

        result = host.pause()

        assert result == {"code": 0}
        host.pause_washing.assert_called_once_with()

    def test_started_updates_state_and_status(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            draining=False,
            self_repairing=False,
            started=True,
            washing=False,
            paused=False,
            cruising=False,
            go_to_zone=False,
        )
        host.capability = SimpleNamespace(cruising=False)
        host.call_action = MagicMock(return_value={"code": 0})

        host.pause()

        assert host._update_property.call_args_list == [
            call(DreameVacuumProperty.STATE, DreameVacuumState.PAUSED.value),
            call(DreameVacuumProperty.STATUS, DreameVacuumStatus.PAUSED.value),
        ]
        host.call_action.assert_called_once_with(DreameVacuumAction.PAUSE)

    def test_cruising_without_capability_uses_monitoring_paused_and_task_status(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            draining=False,
            self_repairing=False,
            started=True,
            washing=False,
            paused=False,
            cruising=True,
            go_to_zone=True,
        )
        host.capability = SimpleNamespace(cruising=False)
        host.call_action = MagicMock(return_value={"code": 0})

        host.pause()

        assert host._update_property.call_args_list == [
            call(DreameVacuumProperty.STATE, DreameVacuumState.MONITORING_PAUSED.value),
            call(DreameVacuumProperty.STATUS, DreameVacuumStatus.PAUSED.value),
            call(DreameVacuumProperty.TASK_STATUS, DreameVacuumTaskStatus.CRUISING_POINT_PAUSED.value),
        ]


class TestReturnToBase:
    def test_not_docked_updates_status_and_state(self) -> None:
        host = _host()
        host.status = SimpleNamespace(docked=False)
        host.capability = SimpleNamespace(cruising=True)
        host.call_action = MagicMock(return_value={"code": 0})

        result = host.return_to_base()

        assert result == {"code": 0}
        assert host._update_property.call_args_list == [
            call(DreameVacuumProperty.STATUS, DreameVacuumStatus.BACK_HOME.value),
            call(DreameVacuumProperty.STATE, DreameVacuumState.RETURNING.value),
        ]
        host.call_action.assert_called_once_with(DreameVacuumAction.CHARGE)

    def test_docked_skips_status_update(self) -> None:
        host = _host()
        host.status = SimpleNamespace(docked=True)
        host.capability = SimpleNamespace(cruising=True)
        host.call_action = MagicMock(return_value={"code": 0})

        host.return_to_base()

        host._update_property.assert_not_called()

    def test_clears_cruise_points_when_map_manager_present(self) -> None:
        host = _host()
        host.status = SimpleNamespace(docked=True)
        host.capability = SimpleNamespace(cruising=True)
        host._map_manager = MagicMock()
        host.call_action = MagicMock(return_value={"code": 0})

        host.return_to_base()

        host._map_manager.editor.set_cruise_points.assert_called_once_with([])

    def test_not_cruising_restores_go_to_zone(self) -> None:
        host = _host()
        host.status = SimpleNamespace(docked=True)
        host.capability = SimpleNamespace(cruising=False)
        host._restore_go_to_zone = MagicMock()
        host.call_action = MagicMock(return_value={"code": 0})

        host.return_to_base()

        host._restore_go_to_zone.assert_called_once_with()


# ===========================================================================
# clean_zone / clean_segment / clean_spot: payload construction
# ===========================================================================


def _wire_start_custom(host: Any) -> None:
    host.action_mapping = {DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}}
    host.property_mapping = {
        DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
        DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
    }
    host._restore_go_to_zone = MagicMock()


class TestCleanZone:
    @staticmethod
    def _status(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "draining": False,
            "self_repairing": False,
            "suction_level": SimpleNamespace(value=1),
            "water_volume": SimpleNamespace(value=1),
            "current_map": None,
            "cleangenius_cleaning": False,
            "started": False,
            "paused": False,
            "fast_mapping": False,
            "draining_complete": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_scalar_zone_normalized_to_list_and_defaults_used(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()

        result = host.clean_zone([0, 0, 300, 300], None, None, None)

        assert result == {"code": 0}
        host._restore_go_to_zone.assert_called_once_with()
        host._update_status.assert_called_once_with(
            DreameVacuumTaskStatus.ZONE_CLEANING, DreameVacuumStatus.ZONE_CLEANING
        )
        host._protocol.action.assert_called_once()
        siid, aiid, payload = host._protocol.action.call_args[0]
        assert (siid, aiid) == (4, 1)
        assert payload[0] == {"piid": 1, "value": DreameVacuumStatus.ZONE_CLEANING.value}
        assert payload[1]["piid"] == 10
        assert payload[1]["value"] == '{"areas":[[0,0,300,300,1,1,1]]}'

    def test_multiple_zones_resolve_scalar_and_list_parameters_per_zone(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()

        zones = [[0, 0, 300, 300], [400, 400, 900, 900]]
        result = host.clean_zone(zones, 2, [1, 3], [1, 2])

        assert result == {"code": 0}
        host._update_suction_level.assert_called_once_with(1)
        host._update_water_level.assert_called_once_with(1)
        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"areas":[[0,0,300,300,2,1,1],[400,400,900,900,2,3,2]]}'

    def test_zone_below_minimum_size_raises(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)

        with pytest.raises(InvalidActionException, match="smaller than minimum zone size"):
            host.clean_zone([0, 0, 50, 50], None, None, None)

    def test_invalid_zones_raises(self) -> None:
        host = _host()
        host.status = self._status()

        with pytest.raises(InvalidActionException, match="Invalid zone coordinates"):
            host.clean_zone([], None, None, None)

    def test_draining_raises(self) -> None:
        host = _host()
        host.status = self._status(draining=True)

        with pytest.raises(InvalidActionException, match="draining"):
            host.clean_zone([0, 0, 300, 300], None, None, None)

    def test_protocol_failure_returns_none_gracefully(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host._protocol.action.side_effect = OSError("disconnected")

        result = host.clean_zone([0, 0, 300, 300], None, None, None)

        assert result is None
        host.schedule_update.assert_called_with(1, True)

    def test_malformed_inner_zone_raises(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)

        with pytest.raises(InvalidActionException, match="Invalid zone coordinates"):
            host.clean_zone([[0, 0, 300, 300], [1, 2, 3]], None, None, None)

    def test_list_params_shorter_than_zones_use_defaults_past_bounds(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()

        zones = [[0, 0, 300, 300], [400, 400, 900, 900]]
        # single-element lists: index 1 falls back to defaults (repeat=1, fan/water from status)
        host.clean_zone(zones, [5], [3], [2])

        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"areas":[[0,0,300,300,5,3,2],[400,400,900,900,1,1,1]]}'

    def test_water_volume_default_uses_mop_pad_humidity_for_self_wash_base(self) -> None:
        host = _host()
        host.status = self._status(mop_pad_humidity=9)
        host.capability = SimpleNamespace(cruising=False, self_wash_base=True)
        _wire_start_custom(host)
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()

        zones = [[0, 0, 300, 300], [400, 400, 900, 900]]
        host.clean_zone(zones, [5], [3], [2])

        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"areas":[[0,0,300,300,5,3,2],[400,400,900,900,1,1,9]]}'

    def test_cleangenius_cleaning_disabled_before_zone_cleaning(self) -> None:
        host = _host()
        host.status = self._status(cleangenius_cleaning=True)
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host.get_property = MagicMock(return_value=DreameVacuumCleanGenius.DEEP_CLEANING.value)
        host.set_auto_switch_property = MagicMock()

        host.clean_zone([0, 0, 300, 300], None, None, None)

        host.get_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.CLEANGENIUS)
        host.set_auto_switch_property.assert_called_once_with(
            DreameVacuumAutoSwitchProperty.CLEANGENIUS, DreameVacuumCleanGenius.OFF.value
        )
        assert host._previous_cleangenius == DreameVacuumCleanGenius.DEEP_CLEANING.value

    def test_map_manager_active_areas_set_when_not_started(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host._map_manager = MagicMock()

        zones = [[0, 0, 300, 300]]
        host.clean_zone(zones, None, None, None)

        host._map_manager.editor.clear_path.assert_called_once_with()
        host._map_manager.editor.set_active_areas.assert_called_once_with(zones)

    def test_map_manager_skips_clear_path_when_resuming_from_pause(self) -> None:
        host = _host()
        host.status = self._status(started=True, paused=True)
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host._map_manager = MagicMock()

        zones = [[0, 0, 300, 300]]
        host.clean_zone(zones, None, None, None)

        host._map_manager.editor.clear_path.assert_not_called()
        host._map_manager.editor.set_active_areas.assert_called_once_with(zones)


class TestCleanSegment:
    @staticmethod
    def _status(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "draining": False,
            "self_repairing": False,
            "current_map": None,
            "suction_level": SimpleNamespace(value=2),
            "water_volume": SimpleNamespace(value=1),
            "current_segments": None,
            "started": False,
            "paused": False,
            "fast_mapping": False,
            "draining_complete": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_scalar_segment_normalized_to_list(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False, customized_cleaning=False)
        _wire_start_custom(host)

        result = host.clean_segment(10)

        assert result == {"code": 0}
        host._update_status.assert_called_once_with(
            DreameVacuumTaskStatus.SEGMENT_CLEANING, DreameVacuumStatus.SEGMENT_CLEANING
        )
        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"selects":[[10,1,2,1,1]]}'

    def test_multiple_segments_use_incrementing_priority_index(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False, customized_cleaning=False)
        _wire_start_custom(host)

        host.clean_segment([10, 20])

        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"selects":[[10,1,2,1,1],[20,1,2,1,2]]}'

    def test_customized_cleaning_forces_priority_to_one(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False, customized_cleaning=True)
        _wire_start_custom(host)

        host.clean_segment([10, 20])

        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"selects":[[10,1,2,1,1],[20,1,2,1,1]]}'

    def test_timestamp_included_in_payload(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False, customized_cleaning=False)
        _wire_start_custom(host)

        host.clean_segment([10], timestamp="2024-01-01")

        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"selects":[[10,1,2,1,1]],"timestamp":"2024-01-01"}'

    def test_draining_raises(self) -> None:
        host = _host()
        host.status = self._status(draining=True)

        with pytest.raises(InvalidActionException, match="draining"):
            host.clean_segment(10)

    def test_current_map_without_saved_map_raises(self) -> None:
        host = _host()
        host.status = self._status(current_map=MagicMock(), has_saved_map=False)

        with pytest.raises(InvalidActionException, match="Cannot clean segments"):
            host.clean_segment(10)

    def test_protocol_failure_returns_none_gracefully(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False, customized_cleaning=False)
        _wire_start_custom(host)
        host._protocol.action.side_effect = OSError("disconnected")

        result = host.clean_segment(10)

        assert result is None
        host.schedule_update.assert_called_with(1, True)

    def test_list_params_shorter_than_segments_use_scalar_defaults(self) -> None:
        host = _host()
        host.status = self._status()  # current_segments=None -> segment-defaults branch unreachable
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False, customized_cleaning=False)
        _wire_start_custom(host)

        host.clean_segment([10, 20], [7], [7], [7])

        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"selects":[[10,7,7,7,1],[20,1,2,1,2]]}'

    def test_water_volume_default_uses_mop_pad_humidity_for_self_wash_base(self) -> None:
        host = _host()
        host.status = self._status(mop_pad_humidity=6)
        host.capability = SimpleNamespace(cruising=False, self_wash_base=True, customized_cleaning=False)
        _wire_start_custom(host)

        host.clean_segment([10, 20], [7], [7], [7])

        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"selects":[[10,7,7,7,1],[20,1,2,6,2]]}'

    def test_customized_cleaning_uses_segment_defaults_past_list_bounds(self) -> None:
        host = _host()
        segments = {20: SimpleNamespace(cleaning_times=4, suction_level=3, water_volume=2)}
        host.status = self._status(current_segments=segments, customized_cleaning=True)
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False, customized_cleaning=False)
        _wire_start_custom(host)

        host.clean_segment([10, 20], [9], [9], [9])

        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"selects":[[10,9,9,9,1],[20,4,3,2,2]]}'

    def test_map_manager_active_segments_set_when_not_started(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False, customized_cleaning=False)
        _wire_start_custom(host)
        host._map_manager = MagicMock()

        host.clean_segment([10, 20])

        host._map_manager.editor.clear_path.assert_called_once_with()
        host._map_manager.editor.set_active_segments.assert_called_once_with([10, 20])

    def test_map_manager_skips_clear_path_when_resuming_from_pause(self) -> None:
        host = _host()
        host.status = self._status(started=True, paused=True)
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False, customized_cleaning=False)
        _wire_start_custom(host)
        host._map_manager = MagicMock()

        host.clean_segment([10, 20])

        host._map_manager.editor.clear_path.assert_not_called()
        host._map_manager.editor.set_active_segments.assert_called_once_with([10, 20])


class TestCleanSpot:
    @staticmethod
    def _status(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "draining": False,
            "self_repairing": False,
            "current_map": None,
            "suction_level": SimpleNamespace(value=2),
            "water_volume": SimpleNamespace(value=1),
            "cleangenius_cleaning": False,
            "started": False,
            "paused": False,
            "fast_mapping": False,
            "draining_complete": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_scalar_point_normalized_to_list(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()

        result = host.clean_spot([100, 200], None, None, None)

        assert result == {"code": 0}
        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"points":[[100,200,1,2,1]]}'

    def test_invalid_points_raises(self) -> None:
        host = _host()
        host.status = self._status()

        with pytest.raises(InvalidActionException, match="Invalid point coordinates"):
            host.clean_spot([], None, None, None)

    def test_draining_raises(self) -> None:
        host = _host()
        host.status = self._status(draining=True)

        with pytest.raises(InvalidActionException, match="draining"):
            host.clean_spot([100, 200], None, None, None)

    def test_list_suction_and_water_volume_use_first_element(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()

        host.clean_spot([100, 200], None, [3, 1], [2, 1])

        host._update_suction_level.assert_called_once_with(3)
        host._update_water_level.assert_called_once_with(2)

    def test_multiple_points_use_defaults_past_list_bounds(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()

        points = [[100, 200], [300, 400]]
        host.clean_spot(points, [5], [3], [2])

        _, _, payload = host._protocol.action.call_args[0]
        # second point falls back to cleaning_times=1, fan=status.suction_level.value, water=status.water_volume.value
        assert payload[1]["value"] == '{"points":[[100,200,5,3,2],[300,400,1,2,1]]}'

    def test_multiple_points_water_default_uses_mop_pad_humidity_for_self_wash_base(self) -> None:
        host = _host()
        host.status = self._status(mop_pad_humidity=7)
        host.capability = SimpleNamespace(cruising=False, self_wash_base=True)
        _wire_start_custom(host)
        host._update_suction_level = MagicMock()
        host._update_water_level = MagicMock()

        points = [[100, 200], [300, 400]]
        host.clean_spot(points, [5], [3], [2])

        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"points":[[100,200,5,3,2],[300,400,1,2,7]]}'

    def test_point_outside_map_raises(self) -> None:
        host = _host()
        current_map = MagicMock()
        current_map.check_point.return_value = False
        host.status = self._status(current_map=current_map)
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)

        with pytest.raises(InvalidActionException, match="not inside the map"):
            host.clean_spot([100, 200], None, None, None)

    def test_cleangenius_cleaning_disabled_before_spot_cleaning(self) -> None:
        host = _host()
        host.status = self._status(cleangenius_cleaning=True)
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host.get_property = MagicMock(return_value=DreameVacuumCleanGenius.ROUTINE_CLEANING.value)
        host.set_auto_switch_property = MagicMock()

        host.clean_spot([100, 200], None, None, None)

        host.get_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.CLEANGENIUS)
        host.set_auto_switch_property.assert_called_once_with(
            DreameVacuumAutoSwitchProperty.CLEANGENIUS, DreameVacuumCleanGenius.OFF.value
        )
        assert host._previous_cleangenius == DreameVacuumCleanGenius.ROUTINE_CLEANING.value

    def test_map_manager_active_points_set_when_not_started(self) -> None:
        host = _host()
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host._map_manager = MagicMock()

        points = [[100, 200]]
        host.clean_spot(points, None, None, None)

        host._map_manager.editor.clear_path.assert_called_once_with()
        host._map_manager.editor.set_active_points.assert_called_once_with(points)

    def test_map_manager_skips_clear_path_when_already_started(self) -> None:
        host = _host()
        host.status = self._status(started=True, paused=True)
        host.capability = SimpleNamespace(cruising=False, self_wash_base=False)
        _wire_start_custom(host)
        host._map_manager = MagicMock()

        points = [[100, 200]]
        host.clean_spot(points, None, None, None)

        host._map_manager.editor.clear_path.assert_not_called()
        host._map_manager.editor.set_active_points.assert_called_once_with(points)


# ===========================================================================
# call_stream_*_action helpers
# ===========================================================================


class TestStreamActionHelpers:
    def test_audio_delegates_with_stream_audio_action(self) -> None:
        host = _host()
        host.call_stream_action = MagicMock(return_value={"code": 0})

        result = host.call_stream_audio_action(DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, {"a": 1})

        assert result == {"code": 0}
        host.call_stream_action.assert_called_once_with(
            DreameVacuumAction.STREAM_AUDIO, DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, {"a": 1}
        )

    def test_video_delegates_with_stream_video_action(self) -> None:
        host = _host()
        host.call_stream_action = MagicMock(return_value={"code": 0})

        host.call_stream_video_action(DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS)

        host.call_stream_action.assert_called_once_with(
            DreameVacuumAction.STREAM_VIDEO, DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, None
        )

    def test_property_delegates_with_stream_property_action(self) -> None:
        host = _host()
        host.call_stream_action = MagicMock(return_value={"code": 0})

        host.call_stream_property_action(DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, {"value": "50"})

        host.call_stream_action.assert_called_once_with(
            DreameVacuumAction.STREAM_PROPERTY, DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS, {"value": "50"}
        )

    def test_call_stream_action_builds_session_payload(self) -> None:
        host = _host()
        host.status = SimpleNamespace(draining_complete=False, stream_session="sess-1")
        host.call_action = MagicMock(return_value={"code": 0})

        result = host.call_stream_action(
            DreameVacuumAction.STREAM_PROPERTY, DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS
        )

        assert result == {"code": 0}
        expected_piid = PIID(DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS)
        host.call_action.assert_called_once_with(
            DreameVacuumAction.STREAM_PROPERTY,
            [{"piid": expected_piid, "value": '{"session":"sess-1"}'}],
        )

    def test_call_stream_action_merges_extra_parameters(self) -> None:
        host = _host()
        host.status = SimpleNamespace(draining_complete=False, stream_session="sess-1")
        host.call_action = MagicMock(return_value={"code": 0})

        host.call_stream_action(
            DreameVacuumAction.STREAM_PROPERTY,
            DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS,
            {"value": "50"},
        )

        _, payload = host.call_action.call_args[0]
        assert json.loads(payload[0]["value"]) == {"session": "sess-1", "value": "50"}


# ===========================================================================
# call_shortcut_action / call_shortcut_action_async
# ===========================================================================


class TestShortcutActionHelpers:
    def test_call_shortcut_action_builds_command_payload(self) -> None:
        host = _host()
        host.call_action = MagicMock(return_value={"code": 0})

        result = host.call_shortcut_action("GET_COMMANDS")

        assert result == {"code": 0}
        expected_piid = PIID(DreameVacuumProperty.CLEANING_PROPERTIES)
        host.call_action.assert_called_once_with(
            DreameVacuumAction.SHORTCUTS,
            [{"piid": expected_piid, "value": '{"cmd":"GET_COMMANDS","params":{}}'}],
        )

    def test_call_shortcut_action_includes_parameters(self) -> None:
        host = _host()
        host.call_action = MagicMock(return_value={"code": 0})

        host.call_shortcut_action("EDIT_COMMAND", {"id": 32, "name": "Zm9v"})

        _, payload = host.call_action.call_args[0]
        assert json.loads(payload[0]["value"]) == {
            "cmd": "EDIT_COMMAND",
            "params": {"id": 32, "name": "Zm9v"},
        }

    def test_call_shortcut_action_async_dispatches_via_protocol(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.SHORTCUTS: {"siid": 9, "aiid": 1}})
        callback = MagicMock()

        host.call_shortcut_action_async(callback, "GET_COMMANDS")

        host._protocol.action_async.assert_called_once()
        args, _ = host._protocol.action_async.call_args
        assert args[0] is callback
        assert args[1:3] == (9, 1)
        assert json.loads(args[3][0]["value"]) == {"cmd": "GET_COMMANDS", "params": {}}


# ===========================================================================
# call_action: remaining branches (sleep guard, auto-empty, clear-warning)
# ===========================================================================


class TestCallActionRemainingBranches:
    def test_cleaning_action_sleeps_when_map_select_recent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        host = _host(action_mapping={DreameVacuumAction.START: {"siid": 2, "aiid": 1}})
        host._map_select_time = 100.0

        sleep_mock = MagicMock()
        monkeypatch.setattr("custom_components.dreame_vacuum.dreame.device_actions.time.time", lambda: 101.0)
        monkeypatch.setattr("custom_components.dreame_vacuum.dreame.device_actions.time.sleep", sleep_mock)

        host.call_action(DreameVacuumAction.START)

        sleep_mock.assert_called_once()
        assert host._map_select_time is None

    def test_cleaning_action_skips_sleep_when_elapsed_exceeds_five_seconds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        host = _host(action_mapping={DreameVacuumAction.START: {"siid": 2, "aiid": 1}})
        host._map_select_time = 0.0

        sleep_mock = MagicMock()
        monkeypatch.setattr("custom_components.dreame_vacuum.dreame.device_actions.time.time", lambda: 100.0)
        monkeypatch.setattr("custom_components.dreame_vacuum.dreame.device_actions.time.sleep", sleep_mock)

        host.call_action(DreameVacuumAction.START)

        sleep_mock.assert_not_called()

    def test_start_auto_empty_updates_status_to_active(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_AUTO_EMPTY: {"siid": 15, "aiid": 1}})
        host.status = SimpleNamespace(draining_complete=False, dust_collection_available=True)

        host.call_action(DreameVacuumAction.START_AUTO_EMPTY)

        host._update_property.assert_called_once_with(
            DreameVacuumProperty.AUTO_EMPTY_STATUS, DreameVacuumAutoEmptyStatus.ACTIVE.value
        )

    def test_clear_warning_resets_error_code(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.CLEAR_WARNING: {"siid": 6, "aiid": 1}})
        host.status = SimpleNamespace(draining_complete=False, has_warning=True)

        host.call_action(DreameVacuumAction.CLEAR_WARNING)

        host._update_property.assert_called_once_with(DreameVacuumProperty.ERROR, DreameVacuumErrorCode.NO_ERROR.value)


# ===========================================================================
# send_command
# ===========================================================================


class TestSendCommand:
    def test_empty_command_raises(self) -> None:
        host = _host()
        with pytest.raises(InvalidActionException, match="Invalid Command"):
            host.send_command("")

    def test_sends_command_and_schedules_updates(self) -> None:
        host = _host()
        host._protocol.send = MagicMock(return_value={"ok": True})

        result = host.send_command("some_cmd", {"a": 1})

        assert result is None
        host._protocol.send.assert_called_once_with("some_cmd", {"a": 1}, 3)
        assert host.schedule_update.call_args_list == [call(10, True), call(2, True)]

    def test_falsy_response_does_not_log_but_still_schedules(self) -> None:
        host = _host()
        host._protocol.send = MagicMock(return_value=None)

        result = host.send_command("some_cmd")

        assert result is None
        assert host.schedule_update.call_args_list == [call(10, True), call(2, True)]


# ===========================================================================
# delete_schedule
# ===========================================================================


class TestDeleteSchedule:
    def test_not_found_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(schedule=[SimpleNamespace(id=1), SimpleNamespace(id=2)], draining_complete=False)

        with pytest.raises(InvalidActionException, match="Schedule not found"):
            host.delete_schedule(99)

    def test_found_filters_schedule_string_and_calls_action(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.DELETE_SCHEDULE: {"siid": 8, "aiid": 1}})
        host.status = SimpleNamespace(schedule=[SimpleNamespace(id=1), SimpleNamespace(id=2)], draining_complete=False)
        raw_schedule = "1-a-08:00-...-x;2-b-09:00-...-y"
        host.get_property = MagicMock(return_value=raw_schedule)
        host.set_property = MagicMock(return_value=True)

        result = host.delete_schedule(1)

        assert result == {"code": 0}
        host.set_property.assert_called_once_with(DreameVacuumProperty.SCHEDULE, "2-b-09:00-...-y")
        host.schedule_update.assert_called_with(3, True)

    def test_found_filters_multiple_remaining_tasks_joined_with_semicolon(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.DELETE_SCHEDULE: {"siid": 8, "aiid": 1}})
        host.status = SimpleNamespace(
            schedule=[SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)],
            draining_complete=False,
        )
        raw_schedule = "1-a-08:00-...-x;2-b-09:00-...-y;3-c-10:00-...-z"
        host.get_property = MagicMock(return_value=raw_schedule)
        host.set_property = MagicMock(return_value=True)

        result = host.delete_schedule(1)

        assert result == {"code": 0}
        host.set_property.assert_called_once_with(DreameVacuumProperty.SCHEDULE, "2-b-09:00-...-y;3-c-10:00-...-z")

    def test_found_with_empty_schedule_list_skips_filtering(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.DELETE_SCHEDULE: {"siid": 8, "aiid": 1}})
        host.status = SimpleNamespace(schedule=[SimpleNamespace(id=1)], draining_complete=False)
        host.get_property = MagicMock(return_value="")
        host.set_property = MagicMock()

        result = host.delete_schedule(1)

        assert result == {"code": 0}
        host.set_property.assert_not_called()

    def test_action_failure_restores_previous_schedule_string(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.DELETE_SCHEDULE: {"siid": 8, "aiid": 1}})
        host.status = SimpleNamespace(schedule=[SimpleNamespace(id=1)], draining_complete=False)
        raw_schedule = "1-a-08:00-...-x"
        host.get_property = MagicMock(return_value=raw_schedule)
        host.set_property = MagicMock(return_value=True)
        host._protocol.action.return_value = {"code": 1}

        result = host.delete_schedule(1)

        assert result == {"code": 1}
        assert host.set_property.call_args_list == [
            call(DreameVacuumProperty.SCHEDULE, ""),
            call(DreameVacuumProperty.SCHEDULE, raw_schedule),
        ]

    def test_action_none_response_restores_previous_schedule_string(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.DELETE_SCHEDULE: {"siid": 8, "aiid": 1}})
        host.status = SimpleNamespace(schedule=[SimpleNamespace(id=1)], draining_complete=False)
        raw_schedule = "1-a-08:00-...-x"
        host.get_property = MagicMock(return_value=raw_schedule)
        host.set_property = MagicMock(return_value=True)
        host._protocol.action.side_effect = OSError("disconnected")

        result = host.delete_schedule(1)

        assert result is None
        assert host.set_property.call_args_list[-1] == call(DreameVacuumProperty.SCHEDULE, raw_schedule)


# ===========================================================================
# locate
# ===========================================================================


class TestLocate:
    def test_delegates_to_call_action(self) -> None:
        host = _host()
        host.call_action = MagicMock(return_value={"code": 0})

        result = host.locate()

        assert result == {"code": 0}
        host.call_action.assert_called_once_with(DreameVacuumAction.LOCATE)


# ===========================================================================
# start(): remaining branches
# ===========================================================================


class TestStartRemainingBranches:
    def test_cruising_paused_resumes_with_current_status(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            fast_mapping_paused=False,
            returning_paused=False,
            returning_to_wash_paused=False,
            cruising_paused=True,
            status=DreameVacuumStatus.CRUISING_POINT,
        )
        host.capability = SimpleNamespace(cruising=True)
        host.start_custom = MagicMock(return_value={"code": 0})

        result = host.start()

        assert result == {"code": 0}
        host.start_custom.assert_called_once_with(DreameVacuumStatus.CRUISING_POINT.value)

    def test_resume_with_sweeping_and_mopping_mode_updates_state(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            fast_mapping_paused=False,
            returning_paused=False,
            returning_to_wash_paused=False,
            paused=True,
            cleaning_paused=False,
            cruising=False,
            scheduled_clean=False,
            draining=False,
            self_repairing=False,
            started=True,
            task_status=DreameVacuumTaskStatus.SEGMENT_CLEANING_PAUSED,
            cleaning_mode=DreameVacuumCleaningMode.SWEEPING_AND_MOPPING,
        )
        host.capability = SimpleNamespace(cruising=False)
        host.call_action = MagicMock(return_value={"code": 0})

        host.start()

        assert host._update_property.call_args_list == [
            call(DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value),
            call(DreameVacuumProperty.STATE, DreameVacuumState.SWEEPING_AND_MOPPING.value),
        ]

    def test_map_manager_clears_path_when_not_started_and_always_refreshes(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            fast_mapping_paused=False,
            returning_paused=False,
            returning_to_wash_paused=False,
            paused=False,
            draining=False,
            self_repairing=False,
            started=False,
        )
        host.capability = SimpleNamespace(cruising=False)
        host._restore_go_to_zone = MagicMock()
        host.call_action = MagicMock(return_value={"code": 0})
        host._map_manager = MagicMock()

        host.start()

        host._map_manager.editor.clear_path.assert_called_once_with()
        host._map_manager.editor.refresh_map.assert_called_once_with()

    def test_map_manager_skips_clear_path_when_already_started(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            fast_mapping_paused=False,
            returning_paused=False,
            returning_to_wash_paused=False,
            paused=False,
            draining=False,
            self_repairing=False,
            started=True,
            task_status=DreameVacuumTaskStatus.COMPLETED,
        )
        host.capability = SimpleNamespace(cruising=False)
        host._restore_go_to_zone = MagicMock()
        host.call_action = MagicMock(return_value={"code": 0})
        host._map_manager = MagicMock()

        host.start()

        host._map_manager.editor.clear_path.assert_not_called()
        host._map_manager.editor.refresh_map.assert_called_once_with()


class TestStartCustom:
    def test_fast_mapping_in_progress_blocks_other_status(self) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping=True)
        host.capability = SimpleNamespace(cruising=False)
        host._restore_go_to_zone = MagicMock()

        with pytest.raises(InvalidActionException, match="fast mapping"):
            host.start_custom(DreameVacuumStatus.CLEANING.value)

    def test_fast_mapping_status_itself_is_allowed(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.status = SimpleNamespace(fast_mapping=True, draining_complete=False)
        host.capability = SimpleNamespace(cruising=False)
        host._restore_go_to_zone = MagicMock()

        result = host.start_custom(DreameVacuumStatus.FAST_MAPPING.value)

        assert result == {"code": 0}


class TestStartPause:
    def test_not_started_calls_start(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, state=None, status=None)
        host.start = MagicMock(return_value={"code": 0})
        host.pause = MagicMock()

        result = host.start_pause()

        assert result == {"code": 0}
        host.start.assert_called_once_with()
        host.pause.assert_not_called()

    def test_paused_state_calls_start(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=True, state=DreameVacuumState.PAUSED, status=DreameVacuumStatus.PAUSED)
        host.start = MagicMock(return_value={"code": 0})

        result = host.start_pause()

        assert result == {"code": 0}
        host.start.assert_called_once_with()

    def test_back_home_status_calls_start(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            started=True, state=DreameVacuumState.RETURNING, status=DreameVacuumStatus.BACK_HOME
        )
        host.start = MagicMock(return_value={"code": 0})

        result = host.start_pause()

        assert result == {"code": 0}
        host.start.assert_called_once_with()

    def test_running_calls_pause(self) -> None:
        host = _host()
        host.status = SimpleNamespace(
            started=True, state=DreameVacuumState.SWEEPING, status=DreameVacuumStatus.CLEANING
        )
        host.start = MagicMock()
        host.pause = MagicMock(return_value={"code": 0})

        result = host.start_pause()

        assert result == {"code": 0}
        host.pause.assert_called_once_with()
        host.start.assert_not_called()


# ===========================================================================
# go_to
# ===========================================================================


class TestGoTo:
    @staticmethod
    def _status(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "draining": False,
            "self_repairing": False,
            "current_map": None,
            "battery_level": 80,
            "cleangenius_cleaning": False,
            "started": False,
            "paused": False,
            "fast_mapping": False,
            "draining_complete": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_draining_raises(self) -> None:
        host = _host()
        host.status = self._status(draining=True)
        host.capability = SimpleNamespace(cruising=False)

        with pytest.raises(InvalidActionException, match="draining"):
            host.go_to(10, 20)

    def test_point_outside_map_raises(self) -> None:
        host = _host()
        current_map = MagicMock()
        current_map.check_point.return_value = False
        host.status = self._status(current_map=current_map)
        host.capability = SimpleNamespace(cruising=False)

        with pytest.raises(InvalidActionException, match="not inside the map"):
            host.go_to(10, 20)

    def test_low_battery_raises(self) -> None:
        host = _host()
        host.status = self._status(battery_level=10)
        host.capability = SimpleNamespace(cruising=False)

        with pytest.raises(InvalidActionException, match="Low battery"):
            host.go_to(10, 20)

    def test_already_on_coordinate_raises(self) -> None:
        host = _host()
        current_map = MagicMock()
        current_map.check_point.return_value = True
        current_map.dimensions = SimpleNamespace(grid_size=25)
        current_map.robot_position = SimpleNamespace(x=10, y=20)
        host.status = self._status(current_map=current_map)
        host.capability = SimpleNamespace(cruising=False)

        with pytest.raises(InvalidActionException, match="already on selected coordinate"):
            host.go_to(10, 20)

    def test_non_cruising_device_sets_go_to_zone_and_starts_zone_cleaning(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False)
        host._set_go_to_zone = MagicMock()
        host._restore_go_to_zone = MagicMock()

        result = host.go_to(100, 200)

        assert result == {"code": 0}
        host._set_go_to_zone.assert_called_once_with(100, 200, 100)
        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"areas":[[50,150,150,250,1,0,1]]}'

    def test_non_cruising_response_failure_restores_go_to_zone(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=False)
        host._set_go_to_zone = MagicMock()
        host._restore_go_to_zone = MagicMock()
        host._protocol.action.return_value = None

        result = host.go_to(100, 200)

        assert result is None
        host._restore_go_to_zone.assert_called_once_with()

    def test_cruising_device_uses_cruising_point_status(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=True)
        host._set_go_to_zone = MagicMock()

        result = host.go_to(100, 200)

        assert result == {"code": 0}
        host._set_go_to_zone.assert_not_called()
        _, _, payload = host._protocol.action.call_args[0]
        assert payload[0] == {"piid": 1, "value": DreameVacuumStatus.CRUISING_POINT.value}
        assert payload[1]["value"] == '{"tpoint":[[100,200,0,0]]}'

    def test_not_started_updates_monitoring_state_and_cruise_points(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.status = self._status()
        host.capability = SimpleNamespace(cruising=True)
        host._map_manager = MagicMock()

        host.go_to(100, 200)

        assert host._update_property.call_args_list == [
            call(DreameVacuumProperty.STATE, ANY),
            call(DreameVacuumProperty.STATUS, ANY),
            call(DreameVacuumProperty.TASK_STATUS, ANY),
        ]
        host._map_manager.editor.set_cruise_points.assert_called_once_with([[100, 200, 0, 0]])

    def test_started_skips_monitoring_state_update(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.status = self._status(started=True)
        host.capability = SimpleNamespace(cruising=True)

        host.go_to(100, 200)

        host._update_property.assert_not_called()

    def test_cleangenius_cleaning_disabled_before_cruise(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.status = self._status(cleangenius_cleaning=True)
        host.capability = SimpleNamespace(cruising=False)
        host._set_go_to_zone = MagicMock()
        host.get_property = MagicMock(return_value=DreameVacuumCleanGenius.ROUTINE_CLEANING.value)
        host.set_auto_switch_property = MagicMock()

        host.go_to(100, 200)

        host.set_auto_switch_property.assert_called_once_with(
            DreameVacuumAutoSwitchProperty.CLEANGENIUS, DreameVacuumCleanGenius.OFF.value
        )


# ===========================================================================
# follow_path
# ===========================================================================


class TestFollowPath:
    @staticmethod
    def _status(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "stream_status": DreameVacuumStreamStatus.IDLE,
            "draining": False,
            "self_repairing": False,
            "battery_level": 80,
            "current_map": None,
            "started": False,
            "paused": False,
            "fast_mapping": False,
            "draining_complete": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_not_supported_without_cruising_capability(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(cruising=False)

        with pytest.raises(InvalidActionException, match="not supported"):
            host.follow_path([[1, 2]])

    def test_requires_idle_stream_status(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(cruising=True)
        host.status = self._status(stream_status=DreameVacuumStreamStatus.VIDEO)

        with pytest.raises(InvalidActionException, match="live camera streaming"):
            host.follow_path([[1, 2]])

    def test_draining_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(cruising=True)
        host.status = self._status(draining=True)

        with pytest.raises(InvalidActionException, match="draining"):
            host.follow_path([[1, 2]])

    def test_low_battery_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(cruising=True)
        host.status = self._status(battery_level=5)

        with pytest.raises(InvalidActionException, match="Low battery"):
            host.follow_path([[1, 2]])

    def test_point_outside_map_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(cruising=True)
        current_map = MagicMock()
        current_map.check_point.return_value = False
        host.status = self._status(current_map=current_map)

        with pytest.raises(InvalidActionException, match="not inside the map"):
            host.follow_path([[1, 2]])

    def test_no_points_and_no_predefined_points_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(cruising=True)
        host.status = self._status()

        with pytest.raises(InvalidActionException, match="At least one valid or saved coordinate"):
            host.follow_path(None)

    def test_falls_back_to_predefined_points(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.capability = SimpleNamespace(cruising=True)
        current_map = SimpleNamespace(predefined_points={1: SimpleNamespace(x=5, y=6)}, check_point=lambda x, y: True)
        host.status = self._status(current_map=current_map)

        result = host.follow_path(None)

        assert result == {"code": 0}
        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == '{"tpoint":[[5,6,0,1]]}'

    def test_scalar_point_normalized_and_path_sent(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.capability = SimpleNamespace(cruising=True)
        host.status = self._status()

        result = host.follow_path([1, 2])

        assert result == {"code": 0}
        _, _, payload = host._protocol.action.call_args[0]
        assert payload[0] == {"piid": 1, "value": DreameVacuumStatus.CRUISING_PATH.value}
        assert payload[1]["value"] == '{"tpoint":[[1,2,0,1]]}'

    def test_map_manager_cruise_points_updated_when_not_started(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.capability = SimpleNamespace(cruising=True)
        host.status = self._status()
        host._map_manager = MagicMock()

        host.follow_path([[1, 2]])

        host._map_manager.editor.set_cruise_points.assert_called_once_with([[1, 2, 0, 1]])
        assert host._update_property.call_args_list == [
            call(DreameVacuumProperty.STATE, ANY),
            call(DreameVacuumProperty.STATUS, ANY),
            call(DreameVacuumProperty.TASK_STATUS, ANY),
        ]

    def test_started_and_not_paused_skips_state_updates(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.capability = SimpleNamespace(cruising=True)
        host.status = self._status(started=True, paused=False)

        host.follow_path([[1, 2]])

        host._update_property.assert_not_called()


# ===========================================================================
# start_shortcut
# ===========================================================================


class TestStartShortcut:
    @staticmethod
    def _status(**overrides: Any) -> SimpleNamespace:
        defaults = {
            "draining": False,
            "self_repairing": False,
            "shortcuts": None,
            "started": False,
            "status": DreameVacuumStatus.STANDBY,
            "fast_mapping": False,
            "draining_complete": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_unsupported_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(shortcuts=False)
        host.status = self._status(shortcuts=None)

        with pytest.raises(InvalidActionException, match="not supported"):
            host.start_shortcut(40)

    @pytest.mark.parametrize("shortcut_id", [10, 200])
    def test_out_of_range_id_raises(self, shortcut_id: int) -> None:
        host = _host()
        host.capability = SimpleNamespace(shortcuts=True, cruising=False)
        host.status = self._status()

        with pytest.raises(InvalidActionException, match="Invalid shortcut ID"):
            host.start_shortcut(shortcut_id)

    def test_draining_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(shortcuts=True, cruising=False)
        host.status = self._status(draining=True)

        with pytest.raises(InvalidActionException, match="draining"):
            host.start_shortcut(40)

    def test_not_started_from_standby_updates_state_and_marks_shortcut_running(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.capability = SimpleNamespace(shortcuts=True, cruising=False)
        shortcut = Shortcut(id=40, name="Test", running=False)
        host.status = self._status(shortcuts={40: shortcut})
        host._restore_go_to_zone = MagicMock()

        result = host.start_shortcut(40)

        assert result == {"code": 0}
        assert shortcut.running is True
        assert host._update_property.call_args_list == [
            call(DreameVacuumProperty.STATE, ANY),
            call(DreameVacuumProperty.STATUS, DreameVacuumStatus.SEGMENT_CLEANING.value),
            call(DreameVacuumProperty.TASK_STATUS, DreameVacuumTaskStatus.AUTO_CLEANING.value),
        ]
        _, _, payload = host._protocol.action.call_args[0]
        assert payload[1]["value"] == "40"

    def test_already_started_skips_status_updates(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.capability = SimpleNamespace(shortcuts=True, cruising=False)
        host.status = self._status(started=True)
        host._restore_go_to_zone = MagicMock()

        host.start_shortcut(40)

        host._update_property.assert_not_called()


# ===========================================================================
# start_fast_mapping / start_mapping
# ===========================================================================


class TestStartFastMapping:
    def test_already_fast_mapping_returns_none(self) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping=True)

        assert host.start_fast_mapping() is None

    def test_low_battery_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping=False, battery_level=5)

        with pytest.raises(InvalidActionException, match="Low battery"):
            host.start_fast_mapping()

    def test_mop_installed_without_lifting_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping=False, battery_level=80, water_tank_or_mop_installed=True)
        host.capability = SimpleNamespace(mop_pad_lifting=False)

        with pytest.raises(InvalidActionException, match="mop pad is not installed"):
            host.start_fast_mapping()

    def test_happy_path_resets_map_and_starts_custom(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.status = SimpleNamespace(
            fast_mapping=False, battery_level=80, water_tank_or_mop_installed=False, draining_complete=False
        )
        host.capability = SimpleNamespace(mop_pad_lifting=False, cruising=False)
        host._map_manager = MagicMock()
        host._restore_go_to_zone = MagicMock()

        result = host.start_fast_mapping()

        assert result == {"code": 0}
        host._update_status.assert_called_once_with(
            DreameVacuumTaskStatus.FAST_MAPPING, DreameVacuumStatus.FAST_MAPPING
        )
        host._map_manager.editor.reset_map.assert_called_once_with()
        _, _, payload = host._protocol.action.call_args[0]
        assert payload[0] == {"piid": 1, "value": DreameVacuumStatus.FAST_MAPPING.value}


class TestStartMapping:
    def test_resets_map_and_starts_custom_cleaning(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.status = SimpleNamespace(fast_mapping=False, draining_complete=False)
        host.capability = SimpleNamespace(cruising=False)
        host._map_manager = MagicMock()
        host._restore_go_to_zone = MagicMock()

        result = host.start_mapping()

        assert result == {"code": 0}
        host._update_status.assert_called_once_with(DreameVacuumTaskStatus.AUTO_CLEANING, DreameVacuumStatus.CLEANING)
        host._map_manager.editor.reset_map.assert_called_once_with()
        _, _, payload = host._protocol.action.call_args[0]
        assert payload[0] == {"piid": 1, "value": DreameVacuumStatus.CLEANING.value}
        assert payload[1] == {"piid": 10, "value": "3"}


# ===========================================================================
# start_self_wash_base
# ===========================================================================


class TestStartSelfWashBase:
    def test_no_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=False)
        assert host.start_self_wash_base("1,1") is None

    def test_old_firmware_forces_parameters_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True)
        host.info = SimpleNamespace(version=1030)
        host.call_action = MagicMock(return_value={"code": 0})

        result = host.start_self_wash_base("1,1")

        assert result == {"code": 0}
        host.call_action.assert_called_once_with(DreameVacuumAction.START_WASHING, None)

    def test_builds_payload_with_parameters(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True)
        host.property_mapping = {DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10}}
        host.call_action = MagicMock(return_value={"code": 0})

        host.start_self_wash_base("2,1")

        host.call_action.assert_called_once_with(DreameVacuumAction.START_WASHING, [{"piid": 10, "value": "2,1"}])

    def test_no_parameters_sends_none_payload(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(self_wash_base=True)
        host.call_action = MagicMock(return_value={"code": 0})

        host.start_self_wash_base()

        host.call_action.assert_called_once_with(DreameVacuumAction.START_WASHING, None)


# ===========================================================================
# toggle_washing / start_washing / pause_washing
# ===========================================================================


class TestToggleWashing:
    def test_washing_delegates_to_pause_washing(self) -> None:
        host = _host()
        host.status = SimpleNamespace(washing=True)
        host.pause_washing = MagicMock(return_value={"code": 0})

        assert host.toggle_washing() == {"code": 0}
        host.pause_washing.assert_called_once_with()

    def test_not_washing_delegates_to_start_washing(self) -> None:
        host = _host()
        host.status = SimpleNamespace(washing=False)
        host.start_washing = MagicMock(return_value={"code": 0})

        assert host.toggle_washing() == {"code": 0}
        host.start_washing.assert_called_once_with()


class TestStartWashing:
    def test_washing_paused_resumes_with_old_firmware_calls_start(self) -> None:
        host = _host()
        host.status = SimpleNamespace(washing_paused=True)
        host.info = SimpleNamespace(version=1030)
        host.start = MagicMock(return_value={"code": 0})

        result = host.start_washing()

        assert result == {"code": 0}
        host._update_property.assert_called_once_with(
            DreameVacuumProperty.SELF_WASH_BASE_STATUS, DreameVacuumSelfWashBaseStatus.WASHING.value
        )
        host.start.assert_called_once_with()

    def test_washing_paused_resumes_with_new_firmware_calls_self_wash_base(self) -> None:
        host = _host()
        host.status = SimpleNamespace(washing_paused=True)
        host.info = None
        host.start_self_wash_base = MagicMock(return_value={"code": 0})

        result = host.start_washing()

        assert result == {"code": 0}
        host.start_self_wash_base.assert_called_once_with("1,1")

    def test_washing_available_starts_new_wash(self) -> None:
        host = _host()
        host.status = SimpleNamespace(washing_paused=False, washing_available=True, returning_to_wash_paused=False)
        host.start_self_wash_base = MagicMock(return_value={"code": 0})

        result = host.start_washing()

        assert result == {"code": 0}
        host._update_property.assert_called_once_with(
            DreameVacuumProperty.SELF_WASH_BASE_STATUS, DreameVacuumSelfWashBaseStatus.WASHING.value
        )
        host.start_self_wash_base.assert_called_once_with("2,1")

    def test_returning_to_wash_paused_starts_new_wash(self) -> None:
        host = _host()
        host.status = SimpleNamespace(washing_paused=False, washing_available=False, returning_to_wash_paused=True)
        host.start_self_wash_base = MagicMock(return_value={"code": 0})

        result = host.start_washing()

        assert result == {"code": 0}
        host.start_self_wash_base.assert_called_once_with("2,1")

    def test_neither_condition_returns_none(self) -> None:
        host = _host()
        host.status = SimpleNamespace(washing_paused=False, washing_available=False, returning_to_wash_paused=False)

        assert host.start_washing() is None


class TestPauseWashing:
    def test_not_washing_returns_none(self) -> None:
        host = _host()
        host.status = SimpleNamespace(washing=False)
        assert host.pause_washing() is None

    def test_washing_with_old_firmware_calls_pause(self) -> None:
        host = _host()
        host.status = SimpleNamespace(washing=True)
        host.info = SimpleNamespace(version=1030)
        host.pause = MagicMock(return_value={"code": 0})

        result = host.pause_washing()

        assert result == {"code": 0}
        host._update_property.assert_called_once_with(
            DreameVacuumProperty.SELF_WASH_BASE_STATUS, DreameVacuumSelfWashBaseStatus.PAUSED.value
        )
        host.pause.assert_called_once_with()

    def test_washing_with_new_firmware_calls_self_wash_base(self) -> None:
        host = _host()
        host.status = SimpleNamespace(washing=True)
        host.info = None
        host.start_self_wash_base = MagicMock(return_value={"code": 0})

        result = host.pause_washing()

        assert result == {"code": 0}
        host.start_self_wash_base.assert_called_once_with("1,0")


# ===========================================================================
# toggle_drying / start_drying / stop_drying
# ===========================================================================


class TestToggleDrying:
    def test_drying_delegates_to_stop_drying(self) -> None:
        host = _host()
        host.status = SimpleNamespace(drying_available=True, drying=True)
        host.stop_drying = MagicMock(return_value={"code": 0})

        assert host.toggle_drying() == {"code": 0}
        host.stop_drying.assert_called_once_with()

    def test_otherwise_delegates_to_start_drying(self) -> None:
        host = _host()
        host.status = SimpleNamespace(drying_available=True, drying=False)
        host.start_drying = MagicMock(return_value={"code": 0})

        assert host.toggle_drying() == {"code": 0}
        host.start_drying.assert_called_once_with()


class TestStartDrying:
    def test_starts_when_available_and_not_drying(self) -> None:
        host = _host()
        host.status = SimpleNamespace(drying_available=True, drying=False)
        host.start_self_wash_base = MagicMock(return_value={"code": 0})

        result = host.start_drying()

        assert result == {"code": 0}
        host._update_property.assert_called_once_with(
            DreameVacuumProperty.SELF_WASH_BASE_STATUS, DreameVacuumSelfWashBaseStatus.DRYING.value
        )
        host.start_self_wash_base.assert_called_once_with("3,1")

    def test_returns_none_when_already_drying(self) -> None:
        host = _host()
        host.status = SimpleNamespace(drying_available=True, drying=True)
        assert host.start_drying() is None

    def test_returns_none_when_unavailable(self) -> None:
        host = _host()
        host.status = SimpleNamespace(drying_available=False, drying=False)
        assert host.start_drying() is None


class TestStopDrying:
    def test_stops_when_available_and_drying(self) -> None:
        host = _host()
        host.status = SimpleNamespace(drying_available=True, drying=True)
        host.start_self_wash_base = MagicMock(return_value={"code": 0})

        result = host.stop_drying()

        assert result == {"code": 0}
        host._update_property.assert_called_once_with(
            DreameVacuumProperty.SELF_WASH_BASE_STATUS, DreameVacuumSelfWashBaseStatus.IDLE.value
        )
        host.start_self_wash_base.assert_called_once_with("3,0")

    def test_returns_none_when_not_drying(self) -> None:
        host = _host()
        host.status = SimpleNamespace(drying_available=True, drying=False)
        assert host.stop_drying() is None


# ===========================================================================
# start_draining
# ===========================================================================


class TestStartDraining:
    def test_clean_water_tank_with_capability(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(empty_water_tank=True)
        host.status = SimpleNamespace(washing_available=False, drying_available=False)
        host.start_self_wash_base = MagicMock(return_value={"code": 0})

        result = host.start_draining(clean_water_tank=True)

        assert result == {"code": 0}
        host.start_self_wash_base.assert_called_once_with("9,1")

    def test_clean_water_tank_without_capability_falls_through(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(empty_water_tank=False)
        host.status = SimpleNamespace(washing_available=True, drying_available=True)
        host.start_self_wash_base = MagicMock(return_value={"code": 0})

        result = host.start_draining(clean_water_tank=True)

        assert result == {"code": 0}
        host.start_self_wash_base.assert_called_once_with("7,1")

    def test_normal_drain_when_washing_and_drying_available(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(empty_water_tank=False)
        host.status = SimpleNamespace(washing_available=True, drying_available=True)
        host.start_self_wash_base = MagicMock(return_value={"code": 0})

        result = host.start_draining()

        assert result == {"code": 0}
        host.start_self_wash_base.assert_called_once_with("7,1")

    def test_returns_none_when_unavailable(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(empty_water_tank=False)
        host.status = SimpleNamespace(washing_available=False, drying_available=True)
        assert host.start_draining() is None


# ===========================================================================
# start_self_repairing
# ===========================================================================


class TestStartSelfRepairing:
    def test_returns_none_when_already_draining_or_repairing(self) -> None:
        host = _host()
        host.status = SimpleNamespace(draining=True, self_repairing=False, status=DreameVacuumStatus.STANDBY)
        assert host.start_self_repairing() is None

    def test_success_sets_status_and_returns_result(self) -> None:
        host = _host()
        host.status = SimpleNamespace(draining=False, self_repairing=False, status=DreameVacuumStatus.STANDBY)
        host.property_mapping = {DreameVacuumProperty.SELF_TEST_STATUS: {"siid": 99, "piid": 8}}
        host._protocol.set_property = MagicMock(return_value=[{"code": 0}])

        result = host.start_self_repairing()

        assert result == [{"code": 0}]
        host._update_property.assert_called_once_with(DreameVacuumProperty.STATUS, DreameVacuumStatus.SELF_REPAIR.value)
        host._protocol.set_property.assert_called_once_with(99, 8, '{"bittest":[17,0]}')

    def test_failure_restores_status_and_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(draining=False, self_repairing=False, status=DreameVacuumStatus.STANDBY)
        host.property_mapping = {DreameVacuumProperty.SELF_TEST_STATUS: {"siid": 99, "piid": 8}}
        host._protocol.set_property = MagicMock(return_value=[{"code": 1}])

        with pytest.raises(InvalidActionException, match="Start self repairing failed"):
            host.start_self_repairing()

        assert host._update_property.call_args_list[-1] == call(DreameVacuumProperty.STATUS, DreameVacuumStatus.STANDBY)

    def test_none_result_also_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(draining=False, self_repairing=False, status=DreameVacuumStatus.STANDBY)
        host.property_mapping = {DreameVacuumProperty.SELF_TEST_STATUS: {"siid": 99, "piid": 8}}
        host._protocol.set_property = MagicMock(return_value=None)

        with pytest.raises(InvalidActionException, match="Start self repairing failed"):
            host.start_self_repairing()


# ===========================================================================
# start_station_cleaning
# ===========================================================================


class TestStartStationCleaning:
    def test_returns_none_without_capability(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(station_cleaning=False)
        host.status = SimpleNamespace(draining=False, self_repairing=False, station_cleaning=False)
        assert host.start_station_cleaning() is None

    def test_returns_none_when_already_cleaning(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(station_cleaning=True)
        host.status = SimpleNamespace(draining=False, self_repairing=False, station_cleaning=True)
        assert host.start_station_cleaning() is None

    def test_success_updates_task_status(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(station_cleaning=True)
        host.status = SimpleNamespace(
            draining=False,
            self_repairing=False,
            station_cleaning=False,
            task_status=DreameVacuumTaskStatus.COMPLETED,
        )
        host.start_self_wash_base = MagicMock(return_value=[{"code": 0}])

        result = host.start_station_cleaning()

        assert result == [{"code": 0}]
        host._update_property.assert_called_once_with(
            DreameVacuumProperty.TASK_STATUS, DreameVacuumTaskStatus.STATION_CLEANING.value
        )
        host.start_self_wash_base.assert_called_once_with("5,1")

    def test_failure_restores_task_status_and_raises(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(station_cleaning=True)
        host.status = SimpleNamespace(
            draining=False,
            self_repairing=False,
            station_cleaning=False,
            task_status=DreameVacuumTaskStatus.COMPLETED,
        )
        host.start_self_wash_base = MagicMock(return_value=[{"code": 1}])

        with pytest.raises(InvalidActionException, match="Start base station cleaning failed"):
            host.start_station_cleaning()

        assert host._update_property.call_args_list[-1] == call(
            DreameVacuumProperty.TASK_STATUS, DreameVacuumTaskStatus.COMPLETED
        )


# ===========================================================================
# start_recleaning
# ===========================================================================


class TestStartRecleaning:
    def test_returns_none_without_capability(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_recleaning=False)
        host.status = SimpleNamespace(_cleaning_history=[SimpleNamespace()], current_map=MagicMock())
        assert host.start_recleaning() is None

    def test_returns_none_without_cleaning_history(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_recleaning=True)
        host.status = SimpleNamespace(_cleaning_history=None, current_map=MagicMock())
        assert host.start_recleaning() is None

    def test_returns_none_without_current_map(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_recleaning=True)
        host.status = SimpleNamespace(_cleaning_history=[SimpleNamespace()], current_map=None)
        assert host.start_recleaning() is None

    def test_returns_none_when_map_data_missing(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_recleaning=True)
        history = SimpleNamespace(object_name="obj-1")
        host.status = SimpleNamespace(
            _cleaning_history=[history],
            current_map=MagicMock(map_id="map-1"),
            _history_map_data={},
        )
        assert host.start_recleaning() is None

    def test_returns_none_when_map_id_mismatches(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_recleaning=True)
        history = SimpleNamespace(object_name="obj-1")
        map_data = SimpleNamespace(map_id="map-2")
        host.status = SimpleNamespace(
            _cleaning_history=[history],
            current_map=MagicMock(map_id="map-1"),
            _history_map_data={"obj-1": map_data},
        )
        assert host.start_recleaning() is None

    def test_neglected_segments_delegate_to_clean_segment(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(auto_recleaning=True)
        history = SimpleNamespace(
            object_name="obj-1",
            multiple_cleaning_time="2024-01-01",
            cleanup_method=CleanupMethod.DEFAULT_MODE,
        )
        map_data = SimpleNamespace(map_id="map-1", neglected_segments={5: object(), 6: object()}, cleaned_segments=None)
        host.status = SimpleNamespace(
            _cleaning_history=[history],
            current_map=SimpleNamespace(map_id="map-1"),
            _history_map_data={"obj-1": map_data},
        )
        host.clean_segment = MagicMock(return_value={"code": 0})

        result = host.start_recleaning()

        assert result == {"code": 0}
        host.clean_segment.assert_called_once()
        args, kwargs = host.clean_segment.call_args
        assert set(args[0]) == {5, 6}
        assert kwargs == {"timestamp": "2024-01-01"}

    def test_cleangenius_history_builds_second_cleaning_payload(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.START_CUSTOM: {"siid": 4, "aiid": 1}})
        host.property_mapping = {
            DreameVacuumProperty.STATUS: {"siid": 4, "piid": 1},
            DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10},
        }
        host.capability = SimpleNamespace(auto_recleaning=True, cruising=False)
        history = SimpleNamespace(
            object_name="obj-1",
            multiple_cleaning_time="",
            cleanup_method=CleanupMethod.CLEANGENIUS,
        )
        map_data = SimpleNamespace(
            map_id="map-1",
            neglected_segments=None,
            cleaned_segments=[1, 2],
            dos=2,
        )
        host.status = SimpleNamespace(
            _cleaning_history=[history],
            current_map=SimpleNamespace(map_id="map-1"),
            _history_map_data={"obj-1": map_data},
            draining_complete=False,
            fast_mapping=False,
        )
        host._restore_go_to_zone = MagicMock()

        result = host.start_recleaning()

        assert result == {"code": 0}
        host._update_property.assert_any_call(DreameVacuumProperty.STATE, ANY)
        _, _, payload = host._protocol.action.call_args[0]
        assert payload[0] == {"piid": 1, "value": DreameVacuumStatus.CLEANING.value}
        assert json.loads(payload[1]["value"]) == {
            "MopAgain": 2,
            "timestamp": "",
            "CleanArea": [1, 2],
            "BigArea": [],
        }


# ===========================================================================
# reload_shortcuts
# ===========================================================================


class TestReloadShortcuts:
    def test_no_shortcuts_property_is_a_noop(self) -> None:
        host = _host()
        host.get_property = MagicMock(return_value="")

        host.reload_shortcuts()

        host._property_changed.assert_not_called()

    def test_loads_shortcuts_and_schedules_async_detail_fetch(self) -> None:
        host = _host()
        encoded = base64.encodebytes(b"Living Room").decode("utf8")
        raw = json.dumps([{"id": 32, "name": encoded, "state": "1"}])
        host.get_property = MagicMock(return_value=raw)
        host.call_shortcut_action_async = MagicMock()

        host.reload_shortcuts()

        assert host.status.shortcuts[32].name == "Living Room"
        assert host.status.shortcuts[32].running is True
        host._property_changed.assert_called_once_with()
        host.call_shortcut_action_async.assert_called_once()
        args, _ = host.call_shortcut_action_async.call_args
        assert callable(args[0])
        assert args[1] == "GET_COMMANDS"

    def test_async_callback_populates_map_id_and_tasks(self) -> None:
        host = _host()
        encoded = base64.encodebytes(b"Kitchen").decode("utf8")
        raw = json.dumps([{"id": 32, "name": encoded}])
        host.get_property = MagicMock(return_value=raw)
        host.call_shortcut_action_async = MagicMock()

        host.reload_shortcuts()
        callback = host.call_shortcut_action_async.call_args[0][0]

        detail_response = {"out": [{"value": json.dumps([{"id": 32, "mapId": 7}])}]}
        commands_value = json.dumps([[[10, 1, 2, 1, 0]]])
        host.call_shortcut_action = MagicMock(return_value={"out": [{"value": commands_value}]})

        callback(detail_response)

        shortcut = host.status.shortcuts[32]
        assert shortcut.map_id == 7
        assert shortcut.name == "Kitchen"
        assert shortcut.tasks is not None
        assert shortcut.tasks[0][0].segment_id == 10
        host._property_changed.assert_called_with()

    def test_async_callback_without_detail_or_tasks(self) -> None:
        host = _host()
        encoded = base64.encodebytes(b"Bedroom").decode("utf8")
        raw = json.dumps([{"id": 40, "name": encoded, "state": "0"}])
        host.get_property = MagicMock(return_value=raw)
        host.call_shortcut_action_async = MagicMock()

        host.reload_shortcuts()
        callback = host.call_shortcut_action_async.call_args[0][0]

        host.call_shortcut_action = MagicMock(return_value=None)

        callback(None)

        shortcut = host.status.shortcuts[40]
        assert shortcut.map_id is None
        assert shortcut.tasks is None
        # Regression test for a real bug: ``running`` used to be True for state "0"
        # *and* "1" (bool(x == "0" or x == "1")), so the flag was always True whenever
        # "state" was present. Fixed to follow the codebase's TRUE/FALSE string
        # convention: only "1" means running.
        assert shortcut.running is False


# ===========================================================================
# clear_warning / clear_low_water_warning
# ===========================================================================


class TestClearWarning:
    def test_draining_complete_clears_drainage_status(self) -> None:
        host = _host()
        host.status = SimpleNamespace(draining_complete=True)
        host.set_property = MagicMock(return_value=True)

        result = host.clear_warning()

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.DRAINAGE_STATUS, 0)

    def test_has_warning_calls_clear_warning_action(self) -> None:
        host = _host(action_mapping={DreameVacuumAction.CLEAR_WARNING: {"siid": 6, "aiid": 1}})
        host.property_mapping = {DreameVacuumProperty.CLEANING_PROPERTIES: {"siid": 4, "piid": 10}}
        host.status = SimpleNamespace(
            draining_complete=False,
            has_warning=True,
            error=DreameVacuumErrorCode.BUMPER,
        )

        result = host.clear_warning()

        assert result == {"code": 0}
        _, _, payload = host._protocol.action.call_args[0]
        assert payload == [{"piid": 10, "value": f"[{DreameVacuumErrorCode.BUMPER.value}]"}]

    def test_falls_back_to_low_water_warning(self) -> None:
        host = _host()
        host.status = SimpleNamespace(draining_complete=False, has_warning=False, low_water=True)
        host.set_property = MagicMock(return_value=True)

        result = host.clear_warning()

        assert result is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.LOW_WATER_WARNING, 1)

    def test_no_warning_at_all_returns_none(self) -> None:
        host = _host()
        host.status = SimpleNamespace(draining_complete=False, has_warning=False, low_water=False)

        assert host.clear_warning() is None


class TestClearLowWaterWarning:
    def test_low_water_sets_property(self) -> None:
        host = _host()
        host.status = SimpleNamespace(low_water=True)
        host.set_property = MagicMock(return_value=True)

        assert host.clear_low_water_warning() is True
        host.set_property.assert_called_once_with(DreameVacuumProperty.LOW_WATER_WARNING, 1)

    def test_no_low_water_returns_none(self) -> None:
        host = _host()
        host.status = SimpleNamespace(low_water=False)
        assert host.clear_low_water_warning() is None


# ===========================================================================
# remote_control_move_step
# ===========================================================================


class TestRemoteControlMoveStep:
    def test_fast_mapping_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping=True)

        with pytest.raises(InvalidActionException, match="fast mapping"):
            host.remote_control_move_step()

    def test_washing_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping=False, washing=True)

        with pytest.raises(InvalidActionException, match="self-wash base"):
            host.remote_control_move_step()

    def test_builds_payload_and_sets_remote_control_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping=False, washing=False, status=DreameVacuumStatus.STANDBY)
        host.property_mapping = {DreameVacuumProperty.REMOTE_CONTROL: {"siid": 4, "piid": 15}}
        host._protocol.set_property = MagicMock(return_value={"code": 0})
        monkeypatch.setattr("custom_components.dreame_vacuum.dreame.device_actions.randrange", lambda n: 555)

        result = host.remote_control_move_step(rotation=10, velocity=-20, prompt=True)

        assert result == {"code": 0}
        assert host._remote_control is True
        host._protocol.set_property.assert_called_once_with(
            4, 15, '{"spdv":-20,"spdw":10,"audio":"true","random":555}', 1
        )

    def test_prompt_false_sends_silent_audio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        host = _host()
        host.status = SimpleNamespace(fast_mapping=False, washing=False, status=DreameVacuumStatus.STANDBY)
        host.property_mapping = {DreameVacuumProperty.REMOTE_CONTROL: {"siid": 4, "piid": 15}}
        host._protocol.set_property = MagicMock(return_value={"code": 0})
        monkeypatch.setattr("custom_components.dreame_vacuum.dreame.device_actions.randrange", lambda n: 1)

        host.remote_control_move_step(prompt=False)

        args, _ = host._protocol.set_property.call_args
        assert '"audio":"false"' in args[2]


# ===========================================================================
# install_voice_pack
# ===========================================================================


class TestInstallVoicePack:
    def test_invalid_url_scheme_raises(self) -> None:
        host = _host()
        with pytest.raises(InvalidValueException, match="must be http"):
            host.install_voice_pack(1, "ftp://example.com/file.pk", "a" * 32, 100)

    def test_missing_host_raises(self) -> None:
        host = _host()
        with pytest.raises(InvalidValueException, match="must be http"):
            host.install_voice_pack(1, "http://", "a" * 32, 100)

    def test_invalid_md5_raises(self) -> None:
        host = _host()
        with pytest.raises(InvalidValueException, match="md5 must be"):
            host.install_voice_pack(1, "http://example.com/file.pk", "not-hex", 100)

    def test_valid_request_builds_payload(self) -> None:
        host = _host()
        host.property_mapping = {DreameVacuumProperty.VOICE_CHANGE: {"siid": 7, "piid": 4}}
        host._protocol.set_property = MagicMock(return_value={"code": 0})

        result = host.install_voice_pack(3, "https://example.com/voice.pk", "a" * 32, 12345)

        assert result == {"code": 0}
        args, _ = host._protocol.set_property.call_args
        assert args[0:2] == (7, 4)
        assert json.loads(args[2]) == {
            "id": "3",
            "url": "https://example.com/voice.pk",
            "md5": "a" * 32,
            "size": 12345,
        }
        assert args[3] == 3


# ===========================================================================
# obstacle_image / obstacle_history_image / history_map / recovery_map*
# ===========================================================================


class TestObstacleImage:
    def test_no_map_capability_returns_none_tuple(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=False)
        host.status = SimpleNamespace(current_map=MagicMock())
        host._map_manager = MagicMock()

        assert host.obstacle_image(1) == (None, None)

    def test_no_map_manager_returns_none_tuple(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host.status = SimpleNamespace(current_map=MagicMock())
        host._map_manager = None

        assert host.obstacle_image(1) == (None, None)

    def test_delegates_to_map_manager(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        map_data = MagicMock()
        host.status = SimpleNamespace(current_map=map_data)
        host._map_manager = MagicMock()
        host._map_manager.get_obstacle_image.return_value = ("img", "meta")

        result = host.obstacle_image(3)

        assert result == ("img", "meta")
        host._map_manager.get_obstacle_image.assert_called_once_with(map_data, 3)


class TestObstacleHistoryImage:
    def test_no_map_manager_returns_none_tuple(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = None

        assert host.obstacle_history_image(1, 1) == (None, None)

    def test_no_history_map_data_returns_none_tuple(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        host.history_map = MagicMock(return_value=None)

        assert host.obstacle_history_image(1, 2, cruising=True) == (None, None)
        host.history_map.assert_called_once_with(2, True)

    def test_delegates_to_map_manager_with_resolved_history_map(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        map_data = MagicMock()
        host.history_map = MagicMock(return_value=map_data)
        host._map_manager.get_obstacle_image.return_value = ("img", "meta")

        result = host.obstacle_history_image(5, 2)

        assert result == ("img", "meta")
        host._map_manager.get_obstacle_image.assert_called_once_with(map_data, 5)


class TestHistoryMap:
    def test_no_map_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=False)
        host._map_manager = MagicMock()
        assert host.history_map(1) is None

    def test_falsy_index_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        assert host.history_map(0) is None

    def test_non_numeric_index_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        assert host.history_map("abc") is None

    def test_no_map_manager_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = None
        assert host.history_map(1) is None

    def test_index_out_of_range_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        host.status = SimpleNamespace(_cleaning_history=[], _cruising_history=None, _history_map_data={})

        assert host.history_map(1) is None

    def test_item_without_object_name_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        item = SimpleNamespace(object_name=None)
        host.status = SimpleNamespace(_cleaning_history=[item], _cruising_history=None, _history_map_data={})

        assert host.history_map(1) is None

    def test_cruising_uses_cruising_history(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        item = SimpleNamespace(object_name=None)
        host.status = SimpleNamespace(_cleaning_history=None, _cruising_history=[item], _history_map_data={})

        assert host.history_map(1, cruising=True) is None

    def test_get_history_map_none_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        host._map_manager.get_history_map.return_value = None
        item = SimpleNamespace(object_name="obj-1", key="key-1")
        host.status = SimpleNamespace(_cleaning_history=[item], _cruising_history=None, _history_map_data={})

        assert host.history_map(1) is None
        host._map_manager.get_history_map.assert_called_once_with("obj-1", "key-1")

    def test_already_cached_returns_cached_without_refetching(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        item = SimpleNamespace(object_name="obj-1", key="key-1")
        cached_map = MagicMock()
        host.status = SimpleNamespace(
            _cleaning_history=[item], _cruising_history=None, _history_map_data={"obj-1": cached_map}
        )

        result = host.history_map(1)

        assert result is cached_map
        host._map_manager.get_history_map.assert_not_called()

    def test_fetches_and_populates_map_data_fields(self) -> None:
        from datetime import UTC, datetime

        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        map_data = SimpleNamespace(
            last_updated=None,
            completed=None,
            neglected_segments=None,
            second_cleaning=None,
            cleaned_area=None,
            cleaning_time=None,
            cleanup_method=None,
            cleaning_map_data=None,
        )
        host._map_manager.get_history_map.return_value = map_data
        item = SimpleNamespace(
            object_name="obj-1",
            key="key-1",
            date=datetime(2024, 1, 1, tzinfo=UTC),
            completed=True,
            neglected_segments={1: "a"},
            second_cleaning=False,
            cleaned_area=12.5,
            cleaning_time=600,
            cleanup_method=CleanupMethod.CUSTOMIZED_CLEANING,
        )
        host.status = SimpleNamespace(_cleaning_history=[item], _cruising_history=None, _history_map_data={})

        result = host.history_map(1)

        assert result is map_data
        assert map_data.completed is True
        assert map_data.cleanup_method == CleanupMethod.CUSTOMIZED_CLEANING
        assert host.status._history_map_data["obj-1"] is map_data

    def test_nested_cleaning_map_data_is_also_populated(self) -> None:
        from datetime import UTC, datetime

        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        nested = SimpleNamespace(
            last_updated=None,
            completed=None,
            neglected_segments=None,
            second_cleaning=None,
            cleaned_area=None,
            cleaning_time=None,
            cleanup_method=None,
        )
        map_data = SimpleNamespace(
            last_updated=None,
            completed=None,
            neglected_segments=None,
            second_cleaning=None,
            cleaned_area=None,
            cleaning_time=None,
            cleanup_method=None,
            cleaning_map_data=nested,
        )
        host._map_manager.get_history_map.return_value = map_data
        item = SimpleNamespace(
            object_name="obj-1",
            key="key-1",
            date=datetime(2024, 1, 1, tzinfo=UTC),
            completed=True,
            neglected_segments=None,
            second_cleaning=True,
            cleaned_area=1.0,
            cleaning_time=10,
            cleanup_method=None,
        )
        host.status = SimpleNamespace(_cleaning_history=[item], _cruising_history=None, _history_map_data={})

        host.history_map(1)

        assert nested.completed is True
        assert nested.second_cleaning is True
        assert nested.cleanup_method == map_data.cleanup_method


class TestRecoveryMap:
    def test_no_map_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=False)
        assert host.recovery_map("m1", 1) is None

    def test_falsy_map_id_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        assert host.recovery_map(None, 1) is None

    def test_non_numeric_index_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        assert host.recovery_map("m1", "abc") is None

    def test_no_map_manager_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = None
        assert host.recovery_map("m1", 1) is None

    def test_delegates_to_map_manager(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        host._map_manager.get_recovery_map.return_value = "recovered"

        result = host.recovery_map("m1", 1)

        assert result == "recovered"
        host._map_manager.get_recovery_map.assert_called_once_with("m1", 1)


class TestRecoveryMapFile:
    def test_no_map_capability_returns_none(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=False)
        assert host.recovery_map_file("m1", 1) is None

    def test_delegates_to_map_manager(self) -> None:
        host = _host()
        host.capability = SimpleNamespace(map=True)
        host._map_manager = MagicMock()
        host._map_manager.get_recovery_map_file.return_value = "file-bytes"

        result = host.recovery_map_file("m1", 1)

        assert result == "file-bytes"
        host._map_manager.get_recovery_map_file.assert_called_once_with("m1", 1)


# ===========================================================================
# rename_shortcut
# ===========================================================================


class TestRenameShortcut:
    def test_started_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=True)

        with pytest.raises(InvalidActionException, match="while vacuum is running"):
            host.rename_shortcut(40, "New")

    def test_unsupported_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, shortcuts=None)
        host.capability = SimpleNamespace(shortcuts=False)

        with pytest.raises(InvalidActionException, match="not supported"):
            host.rename_shortcut(40, "New")

    def test_unknown_shortcut_id_raises(self) -> None:
        host = _host()
        host.status = SimpleNamespace(started=False, shortcuts={40: Shortcut(id=40, name="A")})
        host.capability = SimpleNamespace(shortcuts=True)

        with pytest.raises(InvalidActionException, match="not found"):
            host.rename_shortcut(99, "New")

    def test_blank_name_is_a_noop(self) -> None:
        host = _host()
        shortcut = Shortcut(id=40, name="A")
        host.status = SimpleNamespace(started=False, shortcuts={40: shortcut})
        host.capability = SimpleNamespace(shortcuts=True)

        assert host.rename_shortcut(40, "") is None
        assert shortcut.name == "A"

    def test_successful_rename_updates_name_and_shortcuts_property(self) -> None:
        host = _host()
        shortcut = Shortcut(id=40, name="A")
        host.status = SimpleNamespace(started=False, shortcuts={40: shortcut})
        host.capability = SimpleNamespace(shortcuts=True)
        encoded_old = base64.b64encode(b"A").decode("utf-8")
        host.get_property = MagicMock(return_value=json.dumps([{"id": 40, "name": encoded_old}]))
        host.call_shortcut_action = MagicMock(return_value={"out": [{"value": "0"}]})

        result = host.rename_shortcut(40, "B")

        assert shortcut.name == "B"
        encoded_new = base64.b64encode(b"B").decode("utf-8")
        host._update_property.assert_called_once_with(
            DreameVacuumProperty.SHORTCUTS,
            json.dumps([{"id": 40, "name": encoded_new}], separators=(",", ":")),
        )
        host.call_shortcut_action.assert_called_once_with("EDIT_COMMAND", {"id": 40, "name": encoded_new, "type": 3})
        assert result == {"out": [{"value": "0"}]}

    def test_name_conflict_appends_counter(self) -> None:
        host = _host()
        shortcut_a = Shortcut(id=40, name="A")
        shortcut_b = Shortcut(id=41, name="B")
        host.status = SimpleNamespace(started=False, shortcuts={40: shortcut_a, 41: shortcut_b})
        host.capability = SimpleNamespace(shortcuts=True)
        host.get_property = MagicMock(return_value="")
        host.call_shortcut_action = MagicMock(return_value={"out": [{"value": "0"}]})

        host.rename_shortcut(40, "B")

        assert shortcut_a.name == "B2"

    def test_failed_response_rolls_back_name(self) -> None:
        host = _host()
        shortcut = Shortcut(id=40, name="A")
        host.status = SimpleNamespace(started=False, shortcuts={40: shortcut})
        host.capability = SimpleNamespace(shortcuts=True)
        host.get_property = MagicMock(return_value="")
        host.call_shortcut_action = MagicMock(return_value={"out": [{"value": "1"}]})

        result = host.rename_shortcut(40, "B")

        assert result == {"out": [{"value": "1"}]}
        assert host._property_changed.call_count == 2
        # NOTE: characterizes a real bug — ``current_name`` captures the whole
        # ``Shortcut`` object (not its ``.name`` string), so the rollback assigns
        # the object itself into its own ``.name`` attribute.
        assert shortcut.name is shortcut

    def test_missing_out_key_is_treated_as_failure(self) -> None:
        host = _host()
        shortcut = Shortcut(id=40, name="A")
        host.status = SimpleNamespace(started=False, shortcuts={40: shortcut})
        host.capability = SimpleNamespace(shortcuts=True)
        host.get_property = MagicMock(return_value="")
        host.call_shortcut_action = MagicMock(return_value=None)

        host.rename_shortcut(40, "B")

        assert host._property_changed.call_count == 2
