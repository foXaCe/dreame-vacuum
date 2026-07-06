"""Non-regression tests for Passe 1 confirmed bug fixes.

Covers B1/B2 (missing imports), B7 (sticky FAN_SPEED flag), B8 (AI optimistic
discard keyed by name), B17 (exception message formatting), B19 (shortcut state
serialization), and B10/B11/B15 (segment-cache stray comma, washing_paused
attribute, captcha_img reset) all behaviourally: each drives the real
production code path and would fail if the guarded bug regressed.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.dreame_vacuum.dreame.device import DreameVacuumDevice
from custom_components.dreame_vacuum.dreame.exceptions import InvalidActionException
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    DreameVacuumStrAIProperty,
    Shortcut,
    ShortcutTask,
)

# --- B1 / B2: names used in map_renderer/_core.py must be imported -----------


def test_b1_b2_map_renderer_core_names_resolved() -> None:
    """CleansetType, RecoveryMapType and textwrap must resolve in _core (no NameError)."""
    from custom_components.dreame_vacuum.dreame.map_renderer import _core

    for name in ("CleansetType", "RecoveryMapType", "textwrap"):
        assert hasattr(_core, name), f"{name} non importé dans map_renderer/_core.py"


# --- B7: FAN_SPEED feature flag must be cleared when fan speed is unavailable -


def test_b7_fan_speed_flag_removed_when_unavailable() -> None:
    """_set_attrs must clear FAN_SPEED in the else branch so the flag is not sticky."""
    from homeassistant.components.vacuum import VacuumEntityFeature

    from custom_components.dreame_vacuum.vacuum import DreameVacuum

    coordinator = MagicMock()
    status = coordinator.device.status
    status.started = True
    status.customized_cleaning = True
    status.zone_cleaning = False
    status.spot_cleaning = False
    status.scheduled_clean = False

    entity = DreameVacuum(coordinator)
    assert not (entity.supported_features & VacuumEntityFeature.FAN_SPEED)

    # Leave customized cleaning: a sticky flag would stay off instead of coming back.
    status.started = False
    status.customized_cleaning = False
    entity._set_attrs()
    assert entity.supported_features & VacuumEntityFeature.FAN_SPEED


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


# --- B10 / B11 / B15: behavioural regressions --------------------------------


def test_b10_segment_change_condition_has_no_stray_comma() -> None:
    """The per-segment cache-change condition must be a boolean expression, not a
    one-tuple (a trailing comma there makes it always truthy, forcing every
    segment image to re-render every time even when nothing changed)."""
    from PIL import Image

    from custom_components.dreame_vacuum.dreame.map_renderer._core import DreameVacuumMapRenderer
    from custom_components.dreame_vacuum.dreame.vacuum_types import MapRendererLayer
    from tests.test_map_renderer import _make_small_map_data

    renderer = DreameVacuumMapRenderer(low_resolution=False, cache=True)
    map_image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    cached_layers: dict = {}
    map_data = _make_small_map_data()

    renderer.render_objects(cached_layers, map_data, 0, 0, map_image, 2)
    first_image = cached_layers[MapRendererLayer.SEGMENT][1]

    # Simulate the state render_map() would have persisted, then force re-entry
    # into the SEGMENTS block via a stale composite cache only (drop the combined
    # image, keep the per-segment cache), so the per-segment condition alone
    # decides whether segment 1 gets rebuilt.
    renderer._map_data = map_data
    del cached_layers[MapRendererLayer.SEGMENTS]
    renderer.render_objects(cached_layers, map_data, 0, 0, map_image, 2)

    # Nothing changed -> segment 1 must not have been re-rendered (same object).
    assert cached_layers[MapRendererLayer.SEGMENT][1] is first_image


def test_b11_washing_paused_attribute_uses_correct_property() -> None:
    """The washing_paused attribute must read washing_paused, not washing."""
    from custom_components.dreame_vacuum.dreame.const import ATTR_WASHING_PAUSED
    from custom_components.dreame_vacuum.dreame.vacuum_types import (
        DreameVacuumProperty,
        DreameVacuumSelfWashBaseStatus,
    )
    from tests.test_device_status_core import _make_capability, _make_status

    capability = _make_capability(self_wash_base=True)
    status = _make_status(
        {DreameVacuumProperty.SELF_WASH_BASE_STATUS: DreameVacuumSelfWashBaseStatus.WASHING.value},
        capability=capability,
    )
    # Washing and washing_paused are mutually exclusive states of the same property.
    assert status.washing is True
    assert status.washing_paused is False

    attributes: dict = {}
    status._add_state_attributes(attributes)

    assert attributes[ATTR_WASHING_PAUSED] is False


def test_b15_captcha_reset_uses_existing_attribute() -> None:
    """verify_code must reset the real captcha_img attribute, not a phantom captcha_url."""
    from custom_components.dreame_vacuum.dreame.protocol import DreameVacuumMiHomeCloudProtocol

    proto = DreameVacuumMiHomeCloudProtocol("user@example.com", "secret", "de")
    proto.verification_url = "https://account.xiaomi.com/identity/authStart?x=1"
    proto.captcha_img = "sentinel-captcha"
    proto._session = MagicMock()
    list_resp = MagicMock(status=200)
    list_resp.cookies = {"identity_session": "sess1"}
    list_resp.text = json.dumps({"flag": 4})
    verify_resp = MagicMock(status=200, text=json.dumps({"code": 0, "location": "https://final/loc"}))
    final_get_resp = MagicMock(status=200)
    proto._session.get.side_effect = [list_resp, final_get_resp]
    proto._session.post.return_value = verify_resp

    with (
        patch.object(proto, "login_step_1", return_value=True),
        patch.object(proto, "login_step_3", return_value=True),
    ):
        result = proto.verify_code("999999")

    assert result is True
    # Not a phantom captcha_url; the real attribute is cleared, no AttributeError.
    assert proto.captcha_img is None
