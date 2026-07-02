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

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from custom_components.dreame_vacuum.dreame.device_actions import (
    _RESET_CONSUMABLES,
    DreameVacuumDeviceActionsMixin,
)
from custom_components.dreame_vacuum.dreame.exceptions import InvalidActionException
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    DreameVacuumAction,
    DreameVacuumCleaningMode,
    DreameVacuumProperty,
    DreameVacuumState,
    DreameVacuumStatus,
    DreameVacuumTaskStatus,
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
