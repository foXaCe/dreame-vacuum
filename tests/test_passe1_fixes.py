"""Non-regression tests for Passe 1 confirmed bug fixes.

Covers B1/B2 (missing imports), B7 (sticky FAN_SPEED flag), B8 (AI optimistic
discard keyed by name), B17 (exception message formatting), B19 (shortcut state
serialization) behaviourally, and B10/B11/B15 via source-level regression guards
where a behavioural setup would be disproportionate.
"""

from __future__ import annotations

import json
import pathlib
import time
from types import SimpleNamespace

import pytest

from custom_components.dreame_vacuum.dreame.device import DreameVacuumDevice
from custom_components.dreame_vacuum.dreame.exceptions import InvalidActionException
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    DreameVacuumStrAIProperty,
    Shortcut,
    ShortcutTask,
)

_CC = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "dreame_vacuum"


# --- B1 / B2: names used in map_renderer/_core.py must be imported -----------


def test_b1_b2_map_renderer_core_names_resolved() -> None:
    """CleansetType, RecoveryMapType and textwrap must resolve in _core (no NameError)."""
    from custom_components.dreame_vacuum.dreame.map_renderer import _core

    for name in ("CleansetType", "RecoveryMapType", "textwrap"):
        assert hasattr(_core, name), f"{name} non importé dans map_renderer/_core.py"


# --- B7: FAN_SPEED feature flag must be cleared when fan speed is unavailable -


def test_b7_fan_speed_flag_removed_when_unavailable() -> None:
    """_set_attrs must clear FAN_SPEED in the else branch so the flag is not sticky.

    A behavioural test would need to import vacuum.py, which pulls the HA ``camera``
    component (-> ``turbojpeg``, absent in CI), so this is a source-level guard.
    """
    src = (_CC / "vacuum.py").read_text()
    assert "self._attr_supported_features & ~VacuumEntityFeature.FAN_SPEED" in src


# --- B8: AI str path discards stale server values keyed by prop.name ---------


def test_b8_strai_property_value_differs_from_name() -> None:
    """StrAIProperty.value differs from .name, so keying a name-dict by .value never matches."""
    for member in DreameVacuumStrAIProperty:
        assert member.value != member.name


def test_b8_ai_str_path_discards_stale_value_by_prop_name() -> None:
    """A recent optimistic value must survive a divergent server value (discard window)."""
    device = object.__new__(DreameVacuumDevice)
    prop = DreameVacuumStrAIProperty.AI_OBSTACLE_DETECTION
    device.ai_data = {prop.name: True}
    device._dirty_ai_data = {prop.name: SimpleNamespace(value=True, update_time=time.time())}
    device._discard_timeout = 1000
    device.get_property = lambda *args, **kwargs: json.dumps({prop.value: False})
    # The method also normalises the ai_policy_accepted flag on status afterwards.
    device.status = SimpleNamespace(
        ai_policy_accepted=False,
        ai_obstacle_detection=False,
        ai_obstacle_picture=False,
    )

    device._ai_obstacle_detection_changed()

    # Stale server value (False) discarded -> optimistic True kept, dirty entry cleared.
    assert device.ai_data[prop.name] is True
    assert prop.name not in device._dirty_ai_data


# --- B17: InvalidActionException messages must be pre-formatted (no %s tuple) -


def test_b17_invalid_zone_exception_message_is_formatted() -> None:
    """clean_zone with invalid zones raises a readable message, not a ('%s', arg) tuple."""
    device = object.__new__(DreameVacuumDevice)
    device.status = SimpleNamespace(draining=False, self_repairing=False)

    with pytest.raises(InvalidActionException) as exc_info:
        device.clean_zone([], 1, "", "")

    message = str(exc_info.value)
    assert message == "Invalid zone coordinates: []"
    assert "%s" not in message


# --- B19: shortcut extra state attributes must be JSON-serializable ----------


def test_b19_shortcut_as_dict_is_json_serializable() -> None:
    """Shortcut.as_dict() recursively serializes nested ShortcutTask to plain dicts."""
    shortcut = Shortcut(id=1, name="Test", tasks=[[ShortcutTask(segment_id=1, suction_level=2)]])

    data = shortcut.as_dict()

    assert isinstance(data["tasks"][0][0], dict)
    json.dumps(data)  # must not raise


# --- B10 / B11 / B15: source-level regression guards -------------------------


def test_b10_segment_change_condition_has_no_stray_comma() -> None:
    """The segment-change condition must be a boolean expression, not a one-tuple (always true)."""
    src = (_CC / "dreame" / "map_renderer" / "_core.py").read_text()
    assert "or name_offsets.get(k) != self._name_offsets.get(k),\n" not in src


def test_b11_washing_paused_attribute_uses_correct_property() -> None:
    """The washing_paused attribute must read washing_paused, not washing."""
    src = (_CC / "dreame" / "device_status" / "_core.py").read_text()
    assert "attributes[ATTR_WASHING_PAUSED] = self.washing_paused" in src
    assert "attributes[ATTR_WASHING_PAUSED] = self.washing\n" not in src


def test_b15_captcha_reset_uses_existing_attribute() -> None:
    """verify_code must reset the real captcha_img attribute, not a phantom captcha_url."""
    src = (_CC / "dreame" / "protocol.py").read_text()
    assert "self.captcha_url" not in src
