"""Non-regression / characterization tests for Passe 6 (dedup) fixes.

P6 do-now scope is limited to the RESET_* consumable cascade in device_actions.py
(turned into a data table). These tests freeze the exact behaviour of all 14 reset
actions so the refactor is provably iso-behaviour; they pass against both the old
cascade and the new table.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.dreame_vacuum.dreame.device import DreameVacuumDevice
import custom_components.dreame_vacuum.dreame.device_actions as device_actions_mod
from custom_components.dreame_vacuum.dreame.vacuum_types import DreameVacuumAction, DreameVacuumProperty

P = DreameVacuumProperty
A = DreameVacuumAction

# action -> (LEFT property, TIME_LEFT property, TIME_LEFT default) — frozen from the
# original 14-branch cascade. Any divergence introduced by the refactor fails here.
EXPECTED_RESETS = {
    A.RESET_MAIN_BRUSH: (P.MAIN_BRUSH_LEFT, P.MAIN_BRUSH_TIME_LEFT, 300),
    A.RESET_SIDE_BRUSH: (P.SIDE_BRUSH_LEFT, P.SIDE_BRUSH_TIME_LEFT, 200),
    A.RESET_FILTER: (P.FILTER_LEFT, P.FILTER_TIME_LEFT, 150),
    A.RESET_SENSOR: (P.SENSOR_DIRTY_LEFT, P.SENSOR_DIRTY_TIME_LEFT, 30),
    A.RESET_TANK_FILTER: (P.TANK_FILTER_LEFT, P.TANK_FILTER_TIME_LEFT, 30),
    A.RESET_MOP_PAD: (P.MOP_PAD_LEFT, P.MOP_PAD_TIME_LEFT, 80),
    A.RESET_SILVER_ION: (P.SILVER_ION_LEFT, P.SILVER_ION_TIME_LEFT, 365),
    A.RESET_DETERGENT: (P.DETERGENT_LEFT, P.DETERGENT_TIME_LEFT, 18),
    A.RESET_SQUEEGEE: (P.SQUEEGEE_LEFT, P.SQUEEGEE_TIME_LEFT, 100),
    A.RESET_ONBOARD_DIRTY_WATER_TANK: (
        P.ONBOARD_DIRTY_WATER_TANK_LEFT,
        P.ONBOARD_DIRTY_WATER_TANK_TIME_LEFT,
        100,
    ),
    A.RESET_DIRTY_WATER_TANK: (P.DIRTY_WATER_TANK_LEFT, P.DIRTY_WATER_TANK_TIME_LEFT, 100),
    A.RESET_DEODORIZER: (P.DEODORIZER_LEFT, P.DEODORIZER_TIME_LEFT, 180),
    A.RESET_WHEEL: (P.WHEEL_DIRTY_LEFT, P.WHEEL_DIRTY_TIME_LEFT, 30),
    A.RESET_SCALE_INHIBITOR: (P.SCALE_INHIBITOR_LEFT, P.SCALE_INHIBITOR_TIME_LEFT, 1095),
}


def _action_device() -> tuple[DreameVacuumDevice, list]:
    device: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    calls: list = []
    device._consumable_change = False
    device._update_property = lambda prop, value, *a, **k: calls.append((prop, value))
    device.status = SimpleNamespace(draining_complete=False)
    device._protocol = SimpleNamespace(dreame_cloud=False, action=lambda *a, **k: {"code": 0})
    device.schedule_update = lambda *a, **k: None
    device._property_changed = lambda *a, **k: None
    device._map_select_time = None
    return device, calls


@pytest.mark.parametrize("action", list(EXPECTED_RESETS))
def test_p6_reset_consumable_behaviour_is_preserved(action, monkeypatch) -> None:
    """Each RESET_* action must reset LEFT=100 and TIME_LEFT=<default>, then flag change."""
    # Neutralise the availability gate so the reset branch is reached deterministically.
    monkeypatch.setattr(device_actions_mod, "ACTION_AVAILABILITY", {})
    device, calls = _action_device()
    device.action_mapping = {action: {"siid": 1, "aiid": 1}}
    left_prop, time_left_prop, time_left_default = EXPECTED_RESETS[action]

    device.call_action(action)

    assert calls == [(left_prop, 100), (time_left_prop, time_left_default)]
    assert device._consumable_change is True


def test_p6_reset_consumables_table_matches_expected() -> None:
    """The extracted data table must hold exactly the 14 frozen mappings."""
    assert device_actions_mod._RESET_CONSUMABLES == EXPECTED_RESETS
