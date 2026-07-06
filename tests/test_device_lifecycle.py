"""Characterization tests for DreameVacuumDevice lifecycle/orchestration logic
not already covered by test_device_core.py / test_device_handle_properties.py /
test_device_update.py.

Scope:

- ``_get_map_module()`` lazy import caching
- ``set_property_inventory`` / ``property_pending`` / ``pending_properties``
- ``_update_status`` / ``_update_property``
- The property-changed listener callbacks registered in ``__init__``:
  ``_cleaning_mode_changed``, ``_water_tank_changed``, ``_auto_mount_mop_changed``,
  ``_task_status_changed`` (remaining branches), ``_status_changed``,
  ``_charging_status_changed``, ``_ai_obstacle_detection_changed``,
  ``_auto_switch_settings_changed``, ``_dnd_task_changed``, ``_schedule_changed``,
  ``_stream_status_changed``, ``_shortcuts_changed``,
  ``_voice_assistant_language_changed``, ``_drainage_status_changed``,
  ``_self_wash_base_status_changed``, ``_off_peak_charging_changed``,
  ``_suction_level_changed``, ``_water_volume_changed``, ``_wetness_level_changed``,
  ``_error_changed``, ``_battery_level_changed``
- ``_request_cleaning_history``
- ``_action_update_task`` / ``_update_task``
- ``_perform_update`` remaining branches (map initialization, dirty-data
  restore, map-manager housekeeping, cleaning-history/AI-config deferral)
- ``_handle_properties`` "not ready" (warm boot) branches: per-property
  added/unavailable counters, immediate custom-property callbacks, and the
  capability-driven status-list pruning tail.

Construction strategy: bare ``object.__new__(DreameVacuumDevice)`` instances
with a *real* ``DreameVacuumDeviceCapability`` (all flags default ``False``,
``load()`` replaced with a no-op so no device-model table lookup is needed)
and a *real* ``DreameVacuumDeviceStatus`` (its ``__init__`` does not touch
capability at all). Collaborator methods that belong to other mixins
(device_setters.py, device_actions.py, device_map_ops.py) are stubbed with
``MagicMock`` to isolate device.py's own branching logic — this mirrors the
established convention in test_device_core.py.
"""

from __future__ import annotations

import json
import sys
from threading import RLock
import time
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Native-extension stubs (turbojpeg / py_mini_racer)
# ---------------------------------------------------------------------------


def _ensure_native_stubs() -> None:
    """Install lightweight stand-ins for optional C-extension dependencies."""
    if "turbojpeg" not in sys.modules:
        tj = types.ModuleType("turbojpeg")
        tj.TurboJPEG = type("TurboJPEG", (), {"__init__": lambda self, *a, **k: None})  # type: ignore[attr-defined]
        sys.modules["turbojpeg"] = tj
    if "py_mini_racer" not in sys.modules:
        pmr = types.ModuleType("py_mini_racer")
        pmr.MiniRacer = type("MiniRacer", (), {"__init__": lambda self, *a, **k: None})  # type: ignore[attr-defined]
        sys.modules["py_mini_racer"] = pmr


_ensure_native_stubs()

import custom_components.dreame_vacuum.dreame.device as device_module
from custom_components.dreame_vacuum.dreame.device import DreameVacuumDevice
from custom_components.dreame_vacuum.dreame.device_status import DreameVacuumDeviceStatus
from custom_components.dreame_vacuum.dreame.exceptions import DeviceException
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    PIID,
    DreameVacuumAIProperty,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumChargingStatus,
    DreameVacuumCleaningMode,
    DreameVacuumDeviceCapability,
    DreameVacuumMopPadHumidity,
    DreameVacuumProperty,
    DreameVacuumPropertyMapping,
    DreameVacuumSelfWashBaseStatus,
    DreameVacuumState,
    DreameVacuumStateOld,
    DreameVacuumStatus,
    DreameVacuumStrAIProperty,
    DreameVacuumStreamStatus,
    DreameVacuumTaskStatus,
    DreameVacuumVoiceAssistantLanguage,
    GoToZoneSettings,
)

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _patch_status_props(monkeypatch: pytest.MonkeyPatch, **props: object) -> None:
    """Override read-only DreameVacuumDeviceStatus properties with fixed values."""
    for name, value in props.items():
        monkeypatch.setattr(DreameVacuumDeviceStatus, name, property(lambda self, v=value: v))


def _listener_full_device(
    *,
    capability: dict[str, object] | None = None,
    data: dict[int, object] | None = None,
    status_attrs: dict[str, object] | None = None,
    ready: bool = True,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> DreameVacuumDevice:
    """Bare device with real capability (defaults False) + real status.

    Cross-mixin collaborator methods (device_setters/device_actions/device_map_ops)
    are stubbed so only device.py's own branching is exercised.

    A handful of ``DreameVacuumDeviceCapability`` attributes (``cruising``,
    ``map``, ``custom_cleaning_mode``, ``mop_extend``) are read-only computed
    properties rather than plain flags; overriding those requires patching the
    class itself (a ``monkeypatch`` fixture must be supplied).
    """
    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    d.data = dict(data or {})
    d.auto_switch_data = None
    d.ai_data = None
    d._dirty_data = {}
    d._dirty_auto_switch_data = {}
    d._dirty_ai_data = {}
    d._discard_timeout = 5
    d._restore_timeout = 15
    d._property_update_callback = {}
    d._last_change = 0.0
    d._ready = ready
    d._map_manager = None
    d._protocol = SimpleNamespace(dreame_cloud=False, prefer_cloud=False, cloud=None, connected=True)
    d._previous_cleaning_mode = None
    d._previous_cleangenius = None
    d._remote_control = False
    d._consumable_change = False
    d._cleaning_history_lock = RLock()
    d._cleaning_history_update = 0
    d._cleaning_history_retry_after = 0
    d.info = None

    cap = DreameVacuumDeviceCapability(d)
    cap.load = lambda *_a, **_k: None  # bypass the device-model table lookup
    for key, value in (capability or {}).items():
        if isinstance(getattr(DreameVacuumDeviceCapability, key, None), property):
            assert monkeypatch is not None, f"capability.{key} is read-only; pass monkeypatch=... to override it"
            monkeypatch.setattr(DreameVacuumDeviceCapability, key, property(lambda self, v=value: v))
        else:
            setattr(cap, key, value)
    d.capability = cap

    d.status = DreameVacuumDeviceStatus(d)
    for key, value in (status_attrs or {}).items():
        setattr(d.status, key, value)

    d._property_changed = MagicMock(name="_property_changed")
    d._restore_go_to_zone = MagicMock(name="_restore_go_to_zone")
    d.set_auto_switch_property = MagicMock(name="set_auto_switch_property")
    d.reload_shortcuts = MagicMock(name="reload_shortcuts")
    d._update_cleaning_mode = MagicMock(name="_update_cleaning_mode")
    d._map_property_changed = MagicMock(name="_map_property_changed")
    d._request_properties = MagicMock(name="_request_properties", return_value=True)
    d.history_map = MagicMock(name="history_map")
    d.set_property = MagicMock(name="set_property")
    d.schedule_update = MagicMock(name="schedule_update")
    d.connect_device = MagicMock(name="connect_device")
    return d


# ===========================================================================
# _get_map_module lazy import caching
# ===========================================================================


class TestGetMapModule:
    def test_lazy_import_caches_module(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(device_module, "_map_module", None)
        first = device_module._get_map_module()
        assert hasattr(first, "DreameMapVacuumMapManager")
        # Second call must reuse the cached module (identity, not merely equal).
        second = device_module._get_map_module()
        assert first is second

    def test_returns_cached_module_without_reimport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sentinel = SimpleNamespace(DreameMapVacuumMapManager=MagicMock())
        monkeypatch.setattr(device_module, "_map_module", sentinel)
        assert device_module._get_map_module() is sentinel


# ===========================================================================
# set_property_inventory / property_pending / pending_properties
# ===========================================================================


class TestPropertyInventoryAccessors:
    def test_set_property_inventory_stores_inventory_and_callback(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        inventory = {"model": "x", "firmware": "1", "present": [], "absent": []}
        cb = MagicMock()
        d.set_property_inventory(inventory, cb)
        assert d._property_inventory is inventory
        assert d._inventory_callback is cb

    def test_property_pending_reflects_pending_set(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d._pending_properties = {DreameVacuumProperty.BATTERY_LEVEL.value}
        assert d.property_pending(DreameVacuumProperty.BATTERY_LEVEL) is True
        assert d.property_pending(DreameVacuumProperty.ERROR) is False

    def test_pending_properties_property_returns_the_set(self) -> None:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        pending = {1, 2, 3}
        d._pending_properties = pending
        assert d.pending_properties is pending


# ===========================================================================
# _update_status / _update_property
# ===========================================================================


class TestUpdateStatus:
    def _device(self) -> DreameVacuumDevice:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d._update_property = MagicMock()
        d.status = SimpleNamespace(cleaning_mode=DreameVacuumCleaningMode.SWEEPING_AND_MOPPING)
        return d

    def test_not_completed_mopping_sets_mopping_state(self) -> None:
        d = self._device()
        d.status.cleaning_mode = DreameVacuumCleaningMode.MOPPING
        d._update_status(DreameVacuumTaskStatus.AUTO_CLEANING, DreameVacuumStatus.CLEANING)
        calls = d._update_property.call_args_list
        assert calls[0].args == (DreameVacuumProperty.STATE, DreameVacuumState.MOPPING.value)

    def test_not_completed_sweeping_and_mopping_sets_that_state(self) -> None:
        d = self._device()
        d.status.cleaning_mode = DreameVacuumCleaningMode.SWEEPING_AND_MOPPING
        d._update_status(DreameVacuumTaskStatus.AUTO_CLEANING, DreameVacuumStatus.CLEANING)
        calls = d._update_property.call_args_list
        assert calls[0].args == (DreameVacuumProperty.STATE, DreameVacuumState.SWEEPING_AND_MOPPING.value)

    def test_not_completed_default_sets_sweeping_state(self) -> None:
        d = self._device()
        d.status.cleaning_mode = DreameVacuumCleaningMode.UNKNOWN
        d._update_status(DreameVacuumTaskStatus.AUTO_CLEANING, DreameVacuumStatus.CLEANING)
        calls = d._update_property.call_args_list
        assert calls[0].args == (DreameVacuumProperty.STATE, DreameVacuumState.SWEEPING.value)

    def test_completed_skips_state_update(self) -> None:
        d = self._device()
        d._update_status(DreameVacuumTaskStatus.COMPLETED, DreameVacuumStatus.IDLE)
        calls = d._update_property.call_args_list
        # Only STATUS and TASK_STATUS updated, never STATE.
        assert [c.args[0] for c in calls] == [DreameVacuumProperty.STATUS, DreameVacuumProperty.TASK_STATUS]

    def test_status_and_task_status_always_updated(self) -> None:
        d = self._device()
        d._update_status(DreameVacuumTaskStatus.COMPLETED, DreameVacuumStatus.BACK_HOME)
        calls = {c.args[0]: c.args[1] for c in d._update_property.call_args_list}
        assert calls[DreameVacuumProperty.STATUS] == DreameVacuumStatus.BACK_HOME.value
        assert calls[DreameVacuumProperty.TASK_STATUS] == DreameVacuumTaskStatus.COMPLETED.value


class TestUpdateProperty:
    def _device(self, *, new_state: bool = True) -> DreameVacuumDevice:
        d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
        d.property_mapping = DreameVacuumPropertyMapping
        d.data = {}
        d._property_update_callback = {}
        d.capability = SimpleNamespace(new_state=new_state)
        d._property_changed = MagicMock()
        return d

    def test_unknown_property_returns_none(self) -> None:
        d = self._device()
        result = d._update_property(object(), 1)
        assert result is None

    def test_unchanged_value_returns_current_without_side_effects(self) -> None:
        d = self._device()
        d.data[DreameVacuumProperty.BATTERY_LEVEL.value] = 42
        result = d._update_property(DreameVacuumProperty.BATTERY_LEVEL, 42)
        assert result is None
        d._property_changed.assert_not_called()

    def test_changed_value_stores_and_notifies(self) -> None:
        d = self._device()
        d.data[DreameVacuumProperty.BATTERY_LEVEL.value] = 40
        cb = MagicMock()
        d._property_update_callback[DreameVacuumProperty.BATTERY_LEVEL.value] = [cb]
        result = d._update_property(DreameVacuumProperty.BATTERY_LEVEL, 55)
        assert result == 40
        assert d.data[DreameVacuumProperty.BATTERY_LEVEL.value] == 55
        cb.assert_called_once_with(40)
        d._property_changed.assert_called_once_with(True)

    def test_state_customized_cleaning_and_auto_empty_status_skip_property_changed(self) -> None:
        d = self._device()
        for prop in (
            DreameVacuumProperty.STATE,
            DreameVacuumProperty.CUSTOMIZED_CLEANING,
            DreameVacuumProperty.AUTO_EMPTY_STATUS,
        ):
            d._property_changed.reset_mock()
            d.data.pop(prop.value, None)
            d._update_property(prop, 1)
            d._property_changed.assert_not_called()

    def test_old_state_conversion_when_new_state_capability_missing(self) -> None:
        """STATE values > 18 map through DreameVacuumStateOld on legacy firmware."""
        d = self._device(new_state=False)
        d.data[DreameVacuumProperty.STATE.value] = DreameVacuumState.SWEEPING.value
        d._update_property(DreameVacuumProperty.STATE, DreameVacuumState.WATER_CHECK.value)
        expected = int(DreameVacuumStateOld[DreameVacuumState.WATER_CHECK.name])
        assert d.data[DreameVacuumProperty.STATE.value] == expected

    def test_new_state_capability_present_skips_conversion(self) -> None:
        d = self._device(new_state=True)
        d.data[DreameVacuumProperty.STATE.value] = DreameVacuumState.SWEEPING.value
        d._update_property(DreameVacuumProperty.STATE, DreameVacuumState.WATER_CHECK.value)
        assert d.data[DreameVacuumProperty.STATE.value] == DreameVacuumState.WATER_CHECK.value

    def test_returns_value_when_current_value_is_none(self) -> None:
        d = self._device()
        result = d._update_property(DreameVacuumProperty.BATTERY_LEVEL, 77)
        assert result == 77


# ===========================================================================
# _cleaning_mode_changed
# ===========================================================================


class TestCleaningModeChanged:
    def test_no_self_wash_no_mop_pad_lifting_uses_raw_value(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: DreameVacuumCleaningMode.MOPPING.value},
            capability={"self_wash_base": False, "mop_pad_lifting": False},
        )
        d._cleaning_mode_changed()
        assert d.status.cleaning_mode is DreameVacuumCleaningMode.MOPPING

    def test_unknown_raw_value_falls_back_to_unknown(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: 99999},
            capability={"self_wash_base": False, "mop_pad_lifting": False},
        )
        d._cleaning_mode_changed()
        assert d.status.cleaning_mode is DreameVacuumCleaningMode.UNKNOWN

    def test_mop_pad_lifting_without_self_wash_base_maps_group_values(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: 3},
            capability={"self_wash_base": False, "mop_pad_lifting": True},
        )
        d._cleaning_mode_changed()
        assert d.status.cleaning_mode is DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING

        d.data[DreameVacuumProperty.CLEANING_MODE.value] = 2
        d._cleaning_mode_changed()
        assert d.status.cleaning_mode is DreameVacuumCleaningMode.SWEEPING

        d.data[DreameVacuumProperty.CLEANING_MODE.value] = 0
        d._cleaning_mode_changed()
        assert d.status.cleaning_mode is DreameVacuumCleaningMode.SWEEPING_AND_MOPPING

    def test_self_wash_base_mop_pad_lifting_group_value_mapping(self) -> None:
        # split_group_value(value, mop_pad_lifting=True): byte0 = value & 0x03
        value = DreameVacuumDevice.combine_group_value([2, 1, 0])
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: value},
            capability={"self_wash_base": True, "mop_pad_lifting": True, "wetness": False},
        )
        d._cleaning_mode_changed()
        assert d.status.cleaning_mode is DreameVacuumCleaningMode.SWEEPING

    def test_self_wash_base_without_mop_pad_lifting_and_water_tank_not_installed(self) -> None:
        value = DreameVacuumDevice.combine_group_value([1, 1, 0])
        d = _listener_full_device(
            data={
                DreameVacuumProperty.CLEANING_MODE.value: value,
                DreameVacuumProperty.WATER_TANK.value: 0,  # NOT_INSTALLED
            },
            capability={"self_wash_base": True, "mop_pad_lifting": False, "wetness": False},
        )
        d._cleaning_mode_changed()
        assert d.status.cleaning_mode is DreameVacuumCleaningMode.SWEEPING

    def test_self_wash_base_group_value_zero_maps_to_mopping_after_sweeping(self) -> None:
        value = DreameVacuumDevice.combine_group_value([3, 1, 0])
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: value},
            capability={"self_wash_base": True, "mop_pad_lifting": True, "wetness": False},
        )
        d._cleaning_mode_changed()
        assert d.status.cleaning_mode is DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING

    def test_self_wash_base_without_mop_pad_lifting_water_tank_installed_mopping(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_status_props(monkeypatch, water_tank_or_mop_installed=True)
        value = DreameVacuumDevice.combine_group_value([1, 1, 0])
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: value},
            capability={"self_wash_base": True, "mop_pad_lifting": False, "wetness": False},
        )
        d._cleaning_mode_changed()
        assert d.status.cleaning_mode is DreameVacuumCleaningMode.MOPPING

    def test_self_wash_base_without_mop_pad_lifting_water_tank_installed_sweeping_and_mopping(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_status_props(monkeypatch, water_tank_or_mop_installed=True)
        value = DreameVacuumDevice.combine_group_value([2, 1, 0])
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: value},
            capability={"self_wash_base": True, "mop_pad_lifting": False, "wetness": False},
        )
        d._cleaning_mode_changed()
        assert d.status.cleaning_mode is DreameVacuumCleaningMode.SWEEPING_AND_MOPPING

    def test_self_wash_base_mop_pad_lifting_group_zero_and_unmapped_values(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: DreameVacuumDevice.combine_group_value([0, 1, 0])},
            capability={"self_wash_base": True, "mop_pad_lifting": True, "wetness": False},
        )
        d._cleaning_mode_changed()
        assert d.status.cleaning_mode is DreameVacuumCleaningMode.SWEEPING_AND_MOPPING

        # values[0]=1 is a valid DreameVacuumCleaningMode member (MOPPING) -> falls
        # through to `DreameVacuumCleaningMode(values[0])`.
        d.data[DreameVacuumProperty.CLEANING_MODE.value] = DreameVacuumDevice.combine_group_value([1, 1, 0])
        d._cleaning_mode_changed()
        assert d.status.cleaning_mode is DreameVacuumCleaningMode.MOPPING

    def test_self_clean_by_time_stores_previous_self_clean_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, self_clean_by_time=True)
        value = DreameVacuumDevice.combine_group_value([2, 5, 0])
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: value},
            capability={"self_wash_base": True, "mop_pad_lifting": True, "wetness": False},
            status_attrs={"self_clean_value": 0},
        )
        d._cleaning_mode_changed()
        assert d.status.previous_self_clean_time == 5

    def test_custom_mopping_route_pulls_mop_pad_humidity_from_auto_switch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_status_props(monkeypatch, custom_mopping_mode=False)
        value = DreameVacuumDevice.combine_group_value([2, 1, 0])
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: value},
            capability={
                "self_wash_base": True,
                "mop_pad_lifting": True,
                "wetness": False,
                "custom_mopping_route": True,
                "auto_switch_settings": True,
            },
        )
        d.auto_switch_data = {DreameVacuumAutoSwitchProperty.MOPPING_MODE.name: 2}
        d._cleaning_mode_changed()
        assert d.status.mop_pad_humidity == 2

    def test_previous_mode_resets_go_to_zone_cleaning_settings(self) -> None:
        zone = GoToZoneSettings(cleaning_mode=1, water_level=2)
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: DreameVacuumCleaningMode.MOPPING.value},
            capability={"self_wash_base": False, "mop_pad_lifting": False},
            status_attrs={"go_to_zone": zone},
        )
        d._cleaning_mode_changed(previous_cleaning_mode=DreameVacuumCleaningMode.SWEEPING.value)
        assert zone.cleaning_mode is None
        assert zone.water_level is None

    def test_ready_and_cleaning_route_rebuilds_route_list_and_syncs_setting(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: DreameVacuumCleaningMode.MOPPING.value},
            capability={"self_wash_base": False, "mop_pad_lifting": False, "cleaning_route": True},
            ready=True,
        )
        d._cleaning_mode_changed()
        # Cleaning route becomes UNKNOWN (no auto_switch data) which is never a
        # member of the pruned route list -> device re-syncs to STANDARD.
        d.set_auto_switch_property.assert_called_once()

    def test_not_ready_skips_route_list_rebuild(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: DreameVacuumCleaningMode.MOPPING.value},
            capability={"self_wash_base": False, "mop_pad_lifting": False, "cleaning_route": True},
            ready=False,
        )
        d._cleaning_mode_changed()
        d.set_auto_switch_property.assert_not_called()


# ===========================================================================
# _water_tank_changed
# ===========================================================================


class TestWaterTankChanged:
    def test_none_cleaning_mode_is_noop(self) -> None:
        d = _listener_full_device(data={})
        # Must not raise even though CLEANING_MODE was never set.
        d._water_tank_changed()

    def test_mopping_after_sweeping_kept_when_capability_enabled_and_not_started(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_status_props(monkeypatch, started=False)
        d = _listener_full_device(
            data={
                DreameVacuumProperty.CLEANING_MODE.value: DreameVacuumCleaningMode.SWEEPING.value,
                DreameVacuumProperty.WATER_TANK.value: 3,
            },
            capability={"mopping_after_sweeping": True, "embedded_tank": True},
        )
        d._water_tank_changed()

        assert DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING in d.status.cleaning_mode_list.values()

    def test_water_tank_not_installed_switches_to_sweeping(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, water_tank_or_mop_installed=False, scheduled_clean=False, shortcut_task=False)
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: DreameVacuumCleaningMode.MOPPING.value},
            capability={"embedded_tank": False, "mop_pad_lifting": False},
            status_attrs={"cleaning_mode": DreameVacuumCleaningMode.MOPPING},
            ready=True,
        )
        d._water_tank_changed()
        d._update_cleaning_mode.assert_called_once_with(DreameVacuumCleaningMode.SWEEPING.value)
        assert d._previous_cleaning_mode is DreameVacuumCleaningMode.MOPPING

    def test_water_tank_not_installed_already_sweeping_skips_switch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, water_tank_or_mop_installed=False, scheduled_clean=False, shortcut_task=False)
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: DreameVacuumCleaningMode.SWEEPING.value},
            capability={"embedded_tank": False, "mop_pad_lifting": False},
            status_attrs={"cleaning_mode": DreameVacuumCleaningMode.SWEEPING},
            ready=True,
        )
        d._water_tank_changed()
        d._update_cleaning_mode.assert_not_called()

    def test_update_cleaning_mode_exception_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, water_tank_or_mop_installed=False, scheduled_clean=False, shortcut_task=False)
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: DreameVacuumCleaningMode.MOPPING.value},
            capability={"embedded_tank": False, "mop_pad_lifting": False},
            status_attrs={"cleaning_mode": DreameVacuumCleaningMode.MOPPING},
            ready=True,
        )
        d._update_cleaning_mode.side_effect = ValueError("boom")
        # Must not propagate.
        d._water_tank_changed()

    def test_water_tank_installed_without_mop_pad_lifting_restores_previous(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_status_props(
            monkeypatch,
            water_tank_or_mop_installed=True,
            scheduled_clean=False,
            shortcut_task=False,
            sweeping=True,
        )
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: DreameVacuumCleaningMode.SWEEPING.value},
            capability={"embedded_tank": False, "mop_pad_lifting": False},
            status_attrs={"cleaning_mode": DreameVacuumCleaningMode.SWEEPING},
            ready=True,
        )
        d._previous_cleaning_mode = DreameVacuumCleaningMode.MOPPING
        d._water_tank_changed()
        d._update_cleaning_mode.assert_called_once_with(DreameVacuumCleaningMode.MOPPING.value)

    def test_water_tank_installed_without_previous_mode_defaults_to_sweeping_and_mopping(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_status_props(
            monkeypatch,
            water_tank_or_mop_installed=True,
            scheduled_clean=False,
            shortcut_task=False,
            sweeping=True,
        )
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: DreameVacuumCleaningMode.SWEEPING.value},
            capability={"embedded_tank": False, "mop_pad_lifting": False},
            status_attrs={"cleaning_mode": DreameVacuumCleaningMode.SWEEPING},
            ready=True,
        )
        d._previous_cleaning_mode = None
        d._water_tank_changed()
        d._update_cleaning_mode.assert_called_once_with(DreameVacuumCleaningMode.SWEEPING_AND_MOPPING.value)

    def test_embedded_tank_skips_inner_transition_logic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, water_tank_or_mop_installed=False)
        d = _listener_full_device(
            data={DreameVacuumProperty.CLEANING_MODE.value: DreameVacuumCleaningMode.MOPPING.value},
            capability={"embedded_tank": True, "mop_pad_lifting": False},
            status_attrs={"cleaning_mode": DreameVacuumCleaningMode.MOPPING},
            ready=True,
        )
        d._water_tank_changed()
        d._update_cleaning_mode.assert_not_called()


# ===========================================================================
# _auto_mount_mop_changed
# ===========================================================================


class TestAutoMountMopChanged:
    def test_previous_none_is_noop(self) -> None:
        d = _listener_full_device()
        d._auto_mount_mop_changed(None)
        # cleaning_mode_list untouched (still the default full set).
        assert len(d.status.carpet_cleaning_list) > 0

    def test_previous_not_none_prunes_remove_mop_when_not_auto_mount(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, auto_mount_mop=False)
        d = _listener_full_device()
        from custom_components.dreame_vacuum.dreame.vacuum_types import DreameVacuumCarpetCleaning

        d._auto_mount_mop_changed(previous_auto_mount_mop=1)
        assert DreameVacuumCarpetCleaning.REMOVE_MOP not in d.status.carpet_cleaning_list.values()

    def test_previous_not_none_keeps_remove_mop_when_auto_mount(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, auto_mount_mop=True)
        d = _listener_full_device()
        from custom_components.dreame_vacuum.dreame.vacuum_types import DreameVacuumCarpetCleaning

        d._auto_mount_mop_changed(previous_auto_mount_mop=1)
        assert DreameVacuumCarpetCleaning.REMOVE_MOP in d.status.carpet_cleaning_list.values()


# ===========================================================================
# _task_status_changed (branches not already covered by test_device_core.py)
# ===========================================================================


class TestTaskStatusChangedMapManager:
    def test_no_map_manager_and_no_previous_status_only_runs_tail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, water_tank_or_mop_installed=False)
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.AUTO_CLEANING.value},
            capability={"mopping_after_sweeping": False},
        )
        # Must not raise despite map_manager=None and previous=None.
        d._task_status_changed(None)
        d._request_properties.assert_not_called()

    def test_previous_completed_and_still_completed_clears_path_for_new_cleaning(self) -> None:
        """~device.py:1040-1055: when the PREVIOUS status was already COMPLETED
        (a brand new task is starting from idle), the map-manager path-clearing
        branch is keyed off the *current* task_status, not the transition out
        of COMPLETED handled elsewhere in this method."""
        map_manager = MagicMock()
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.AUTO_CLEANING.value},
            capability={"mopping_after_sweeping": False, "disable_sensor_cleaning": True},
        )
        d._map_manager = map_manager
        d._task_status_changed(DreameVacuumTaskStatus.COMPLETED.value)
        map_manager.editor.clear_path.assert_called_once()

    def test_previous_completed_fast_mapping_resets_current_map(self) -> None:
        map_manager = MagicMock()
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.FAST_MAPPING.value},
            capability={"mopping_after_sweeping": False, "disable_sensor_cleaning": True},
        )
        d._map_manager = map_manager
        d._task_status_changed(DreameVacuumTaskStatus.COMPLETED.value)
        map_manager.editor.reset_map.assert_called_once()

    def test_previous_completed_other_status_refreshes_map(self) -> None:
        map_manager = MagicMock()
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.STATION_CLEANING.value},
            capability={"mopping_after_sweeping": False, "disable_sensor_cleaning": True},
        )
        d._map_manager = map_manager
        d._task_status_changed(DreameVacuumTaskStatus.COMPLETED.value)
        # Once from the "previous was COMPLETED" branch's else clause, once
        # more from the unconditional refresh further down in the method.
        assert map_manager.editor.refresh_map.call_count == 2

    def test_completed_from_cruising_requests_next_map_list_and_marks_history(self) -> None:
        map_manager = MagicMock()
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.COMPLETED.value},
            capability={"mopping_after_sweeping": False, "disable_sensor_cleaning": True},
        )
        d._map_manager = map_manager
        d._task_status_changed(DreameVacuumTaskStatus.CRUISING_PATH.value)
        map_manager.editor.set_cruise_points.assert_called_once_with([])
        map_manager.request_next_map_list.assert_called_once()
        assert d._cleaning_history_update != 0

    def test_completed_from_fast_mapping_resets_cleaning_time(self) -> None:
        map_manager = MagicMock()
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.COMPLETED.value},
            capability={"mopping_after_sweeping": False, "disable_sensor_cleaning": True},
        )
        d._map_manager = map_manager
        d._task_status_changed(DreameVacuumTaskStatus.FAST_MAPPING.value)
        assert d.data[DreameVacuumProperty.CLEANING_TIME.value] == 0
        map_manager.request_next_map_list.assert_called_once()

    def test_completed_marks_cleanup_completed_when_back_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, running=False)
        d = _listener_full_device(
            data={
                DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.COMPLETED.value,
                DreameVacuumProperty.STATUS.value: DreameVacuumStatus.BACK_HOME.value,
            },
            capability={"mopping_after_sweeping": False, "disable_sensor_cleaning": True},
            status_attrs={"cleanup_started": True, "cleanup_completed": False},
        )
        d._previous_cleangenius = 3
        d._task_status_changed(DreameVacuumTaskStatus.AUTO_CLEANING.value)
        assert d.status.cleanup_started is False
        assert d.status.cleanup_completed is True
        d.set_auto_switch_property.assert_called_once_with(DreameVacuumAutoSwitchProperty.CLEANGENIUS, 3)
        assert d._previous_cleangenius is None

    def test_not_completed_resets_cleaning_time_and_area_after_previous_completed(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.AUTO_CLEANING.value},
            capability={"mopping_after_sweeping": False, "disable_sensor_cleaning": True},
        )
        d._task_status_changed(DreameVacuumTaskStatus.COMPLETED.value)
        assert d.data[DreameVacuumProperty.CLEANING_TIME.value] == 0
        assert d.data[DreameVacuumProperty.CLEANED_AREA.value] == 0

    def test_go_to_zone_restored_when_task_status_leaves_zone_states(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.AUTO_CLEANING.value},
            capability={"mopping_after_sweeping": False, "disable_sensor_cleaning": True},
            status_attrs={"go_to_zone": GoToZoneSettings()},
        )
        d._task_status_changed(DreameVacuumTaskStatus.SEGMENT_CLEANING.value)
        d._restore_go_to_zone.assert_called_once()

    def test_go_to_zone_not_restored_while_still_in_zone_cleaning(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.ZONE_CLEANING.value},
            capability={"mopping_after_sweeping": False, "disable_sensor_cleaning": True},
            status_attrs={"go_to_zone": GoToZoneSettings()},
        )
        d._task_status_changed(DreameVacuumTaskStatus.AUTO_CLEANING.value)
        d._restore_go_to_zone.assert_not_called()

    def test_request_properties_device_exception_is_swallowed(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.AUTO_CLEANING.value},
            capability={"mopping_after_sweeping": False, "disable_sensor_cleaning": True},
        )
        d._request_properties.side_effect = DeviceException("boom")
        d._task_status_changed(DreameVacuumTaskStatus.COMPLETED.value)  # must not raise

    def test_prefer_cloud_dreame_cloud_schedules_fast_update(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.AUTO_CLEANING.value},
            capability={"mopping_after_sweeping": False, "disable_sensor_cleaning": True},
        )
        d._protocol = SimpleNamespace(prefer_cloud=True, dreame_cloud=True, connected=True, cloud=None)
        d._task_status_changed(DreameVacuumTaskStatus.COMPLETED.value)
        d.schedule_update.assert_called_once_with(1, True)

    def test_mopping_after_sweeping_removed_while_started(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, started=True)
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.AUTO_CLEANING.value},
            capability={"mopping_after_sweeping": True, "disable_sensor_cleaning": True},
            status_attrs={"cleaning_mode": DreameVacuumCleaningMode.SWEEPING},
        )
        from custom_components.dreame_vacuum.dreame.const import CLEANING_MODE_MOPPING_AFTER_SWEEPING

        assert CLEANING_MODE_MOPPING_AFTER_SWEEPING in d.status.cleaning_mode_list
        d._task_status_changed(None)
        assert CLEANING_MODE_MOPPING_AFTER_SWEEPING not in d.status.cleaning_mode_list
        d._property_changed.assert_called_with(False)

    def test_mopping_after_sweeping_added_back_when_not_started(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, started=False, water_tank_or_mop_installed=True)
        d = _listener_full_device(
            data={DreameVacuumProperty.TASK_STATUS.value: DreameVacuumTaskStatus.AUTO_CLEANING.value},
            capability={"mopping_after_sweeping": True, "disable_sensor_cleaning": True},
        )
        from custom_components.dreame_vacuum.dreame.const import CLEANING_MODE_MOPPING_AFTER_SWEEPING

        del d.status.cleaning_mode_list[CLEANING_MODE_MOPPING_AFTER_SWEEPING]
        d._task_status_changed(None)
        assert DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING in d.status.cleaning_mode_list.values()
        d._property_changed.assert_called_with(False)


# ===========================================================================
# _status_changed (branches not already exercised elsewhere)
# ===========================================================================


class TestStatusChanged:
    def test_previous_none_is_noop(self) -> None:
        d = _listener_full_device(data={DreameVacuumProperty.STATUS.value: DreameVacuumStatus.IDLE.value})
        d._status_changed(None)
        d._property_changed.assert_not_called()

    def test_remote_control_reset_when_status_transitions_away(self) -> None:
        d = _listener_full_device(data={DreameVacuumProperty.STATUS.value: DreameVacuumStatus.IDLE.value})
        d._remote_control = True
        d._status_changed(previous_status=DreameVacuumStatus.CLEANING.value)
        assert d._remote_control is False

    def test_remote_control_kept_when_current_is_remote_control(self) -> None:
        d = _listener_full_device(data={DreameVacuumProperty.STATUS.value: DreameVacuumStatus.REMOTE_CONTROL.value})
        d._remote_control = True
        d._status_changed(previous_status=DreameVacuumStatus.CLEANING.value)
        assert d._remote_control is True

    def test_zone_cleaning_back_home_without_cruising_restores_go_to_zone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_status_props(monkeypatch, started=True)
        zone = GoToZoneSettings()
        # capability.cruising is a read-only property that defaults to False
        # (lidar_navigation=True, camera_streaming=False by default), which is
        # exactly the "without cruising" precondition this test needs.
        d = _listener_full_device(
            data={DreameVacuumProperty.STATUS.value: DreameVacuumStatus.BACK_HOME.value},
            status_attrs={"go_to_zone": zone, "cleanup_started": True, "cleanup_completed": False},
        )
        d._status_changed(previous_status=DreameVacuumStatus.ZONE_CLEANING.value)
        assert zone.stop is True
        d._restore_go_to_zone.assert_called_once_with(True)
        assert d.status.cleanup_started is False
        assert d.status.cleanup_completed is False

    def test_cleanup_marked_completed_when_idle_and_back_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, started=False, running=False)
        d = _listener_full_device(
            data={DreameVacuumProperty.STATUS.value: DreameVacuumStatus.BACK_HOME.value},
            status_attrs={"cleanup_started": True, "cleanup_completed": False},
        )
        d._previous_cleangenius = 5
        cb = MagicMock()
        d._property_update_callback[DreameVacuumProperty.TASK_STATUS.value] = [cb]
        d._status_changed(previous_status=DreameVacuumStatus.CLEANING.value)
        assert d.status.cleanup_started is False
        assert d.status.cleanup_completed is True
        cb.assert_called_once_with(d.status.task_status.value)
        d._property_changed.assert_any_call(False)

    def test_charging_after_back_home_marks_cleaning_history_update(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.STATUS.value: DreameVacuumStatus.CHARGING.value},
        )
        d._cleaning_history_update = 0
        d._status_changed(previous_status=DreameVacuumStatus.BACK_HOME.value)
        assert d._cleaning_history_update != 0

    def test_ota_previous_reconnects_device(self) -> None:
        d = _listener_full_device(data={DreameVacuumProperty.STATUS.value: DreameVacuumStatus.IDLE.value})
        d._ready = True
        d._status_changed(previous_status=DreameVacuumStatus.OTA.value)
        assert d._ready is False
        d.connect_device.assert_called_once()

    def test_map_manager_refresh_called_when_present(self) -> None:
        map_manager = MagicMock()
        d = _listener_full_device(data={DreameVacuumProperty.STATUS.value: DreameVacuumStatus.IDLE.value})
        d._map_manager = map_manager
        d._status_changed(previous_status=DreameVacuumStatus.CLEANING.value)
        map_manager.editor.refresh_map.assert_called_once()


# ===========================================================================
# _charging_status_changed
# ===========================================================================


class TestChargingStatusChanged:
    def test_previous_none_only_resets_remote_control(self) -> None:
        d = _listener_full_device(data={})
        d._remote_control = True
        d._charging_status_changed(None)
        assert d._remote_control is False

    def test_previous_not_none_refreshes_map_and_water_tank(self) -> None:
        map_manager = MagicMock()
        d = _listener_full_device(
            data={DreameVacuumProperty.CHARGING_STATUS.value: DreameVacuumChargingStatus.CHARGING.value},
            capability={"mop_pad_lifting": True},
            ready=True,
        )
        d._map_manager = map_manager
        d._water_tank_changed = MagicMock()
        d._charging_status_changed(previous_charging_status=DreameVacuumChargingStatus.NOT_CHARGING.value)
        map_manager.editor.refresh_map.assert_called_once()
        d._water_tank_changed.assert_called_once()

    def test_not_ready_skips_water_tank_changed(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.CHARGING_STATUS.value: DreameVacuumChargingStatus.CHARGING.value},
            capability={"mop_pad_lifting": True},
            ready=False,
        )
        d._water_tank_changed = MagicMock()
        d._charging_status_changed(previous_charging_status=DreameVacuumChargingStatus.NOT_CHARGING.value)
        d._water_tank_changed.assert_not_called()

    def test_dreame_cloud_not_completed_schedules_update(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.CHARGING_STATUS.value: DreameVacuumChargingStatus.CHARGING.value},
        )
        d._protocol = SimpleNamespace(dreame_cloud=True)
        d._charging_status_changed(previous_charging_status=DreameVacuumChargingStatus.NOT_CHARGING.value)
        d.schedule_update.assert_called_once_with(2, True)

    def test_dreame_cloud_completed_does_not_schedule(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.CHARGING_STATUS.value: DreameVacuumChargingStatus.CHARGING_COMPLETED.value},
        )
        d._protocol = SimpleNamespace(dreame_cloud=True)
        d._charging_status_changed(previous_charging_status=DreameVacuumChargingStatus.CHARGING.value)
        d.schedule_update.assert_not_called()


# ===========================================================================
# _ai_obstacle_detection_changed
# ===========================================================================


class TestAiObstacleDetectionChanged:
    def test_string_payload_updates_ai_data_and_marks_changed(self) -> None:
        payload = json.dumps({DreameVacuumStrAIProperty.AI_PET_DETECTION.value: 1})
        d = _listener_full_device(data={DreameVacuumProperty.AI_DETECTION.value: payload}, ready=True)
        # Pre-seed so this is a *change* (map refresh only fires on change, not add).
        d.ai_data = {DreameVacuumStrAIProperty.AI_PET_DETECTION.name: 0}
        d._ai_obstacle_detection_changed()
        assert d.ai_data[DreameVacuumStrAIProperty.AI_PET_DETECTION.name] == 1
        d._map_property_changed.assert_called_once()
        d._property_changed.assert_called_once()

    def test_string_payload_discards_stale_dirty_echo(self) -> None:
        from custom_components.dreame_vacuum.dreame.vacuum_types import DirtyData

        payload = json.dumps({DreameVacuumStrAIProperty.AI_HUMAN_DETECTION.value: 1})
        d = _listener_full_device(data={DreameVacuumProperty.AI_DETECTION.value: payload})
        d._dirty_ai_data[DreameVacuumStrAIProperty.AI_HUMAN_DETECTION.name] = DirtyData(
            value=0, update_time=time.time()
        )
        d._ai_obstacle_detection_changed()
        assert DreameVacuumStrAIProperty.AI_HUMAN_DETECTION.name not in d._dirty_ai_data
        assert DreameVacuumStrAIProperty.AI_HUMAN_DETECTION.name not in (d.ai_data or {})

    def test_int_payload_bitmask_updates_ai_data(self) -> None:
        value = int(DreameVacuumAIProperty.AI_PET_DETECTION) | int(DreameVacuumAIProperty.AI_FLUID_DETECTION)
        d = _listener_full_device(data={DreameVacuumProperty.AI_DETECTION.value: value})
        # Pre-seed opposite values so this is a *change* for PET/FLUID (map
        # refresh only fires on change, not on first add).
        d.ai_data = {
            DreameVacuumAIProperty.AI_PET_DETECTION.name: False,
            DreameVacuumAIProperty.AI_FLUID_DETECTION.name: False,
        }
        d._ai_obstacle_detection_changed()
        assert d.ai_data[DreameVacuumAIProperty.AI_PET_DETECTION.name] is True
        assert d.ai_data[DreameVacuumAIProperty.AI_FLUID_DETECTION.name] is True
        assert d.ai_data[DreameVacuumAIProperty.AI_OBSTACLE_DETECTION.name] is False
        # Both PET and FLUID trigger _map_property_changed once each.
        assert d._map_property_changed.call_count == 2

    def test_int_payload_discards_stale_dirty_echo(self) -> None:
        from custom_components.dreame_vacuum.dreame.vacuum_types import DirtyData

        value = int(DreameVacuumAIProperty.AI_FURNITURE_DETECTION)
        d = _listener_full_device(data={DreameVacuumProperty.AI_DETECTION.value: value})
        # Sentinel says "not furniture" (False); real value now says "furniture" (True)
        # within the discard window -> the echo must be rejected.
        d._dirty_ai_data[DreameVacuumAIProperty.AI_FURNITURE_DETECTION.name] = DirtyData(
            value=False, update_time=time.time()
        )
        d._ai_obstacle_detection_changed()
        assert DreameVacuumAIProperty.AI_FURNITURE_DETECTION.name not in d._dirty_ai_data
        # The echoed (discarded) property is skipped entirely this round.
        assert DreameVacuumAIProperty.AI_FURNITURE_DETECTION.name not in d.ai_data

    def test_not_ready_does_not_call_property_changed(self) -> None:
        value = int(DreameVacuumAIProperty.AI_PET_DETECTION)
        d = _listener_full_device(data={DreameVacuumProperty.AI_DETECTION.value: value}, ready=False)
        d._ai_obstacle_detection_changed()
        d._property_changed.assert_not_called()

    def test_ai_policy_accepted_true_when_obstacle_detection_enabled(self) -> None:
        value = int(DreameVacuumAIProperty.AI_OBSTACLE_DETECTION)
        d = _listener_full_device(
            data={DreameVacuumProperty.AI_DETECTION.value: value}, capability={"ai_detection": True}
        )
        d._ai_obstacle_detection_changed()
        assert d.status.ai_policy_accepted is True


# ===========================================================================
# _auto_switch_settings_changed
# ===========================================================================


class TestAutoSwitchSettingsChanged:
    def test_list_payload_updates_auto_switch_data(self) -> None:
        payload = json.dumps([{"k": DreameVacuumAutoSwitchProperty.CLEANGENIUS.value, "v": 1}])
        d = _listener_full_device(data={DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value: payload})
        d._auto_switch_settings_changed(previous_auto_switch_settings="old")
        assert d.auto_switch_data[DreameVacuumAutoSwitchProperty.CLEANGENIUS.name] == 1
        d._property_changed.assert_called_once()

    def test_single_dict_payload_updates_auto_switch_data(self) -> None:
        payload = json.dumps({"k": DreameVacuumAutoSwitchProperty.CLEANGENIUS.value, "v": 2})
        d = _listener_full_device(data={DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value: payload})
        d._auto_switch_settings_changed(previous_auto_switch_settings="old")
        assert d.auto_switch_data[DreameVacuumAutoSwitchProperty.CLEANGENIUS.name] == 2

    def test_previous_none_does_not_call_property_changed(self) -> None:
        payload = json.dumps([{"k": DreameVacuumAutoSwitchProperty.CLEANGENIUS.value, "v": 1}])
        d = _listener_full_device(data={DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value: payload})
        d._auto_switch_settings_changed(previous_auto_switch_settings=None)
        d._property_changed.assert_not_called()

    def test_malformed_json_logs_error_without_raising(self, caplog) -> None:
        d = _listener_full_device(data={DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value: "{not-json"})
        d._auto_switch_settings_changed(previous_auto_switch_settings="old")
        assert "Failed to parse auto switch settings" in caplog.text

    def test_cleangenius_previous_pending_value_updated_instead_of_reset(self) -> None:
        payload = json.dumps([{"k": DreameVacuumAutoSwitchProperty.CLEANGENIUS.value, "v": 7}])
        d = _listener_full_device(data={DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value: payload})
        d._previous_cleangenius = 1
        d._auto_switch_settings_changed(previous_auto_switch_settings="old")
        assert d._previous_cleangenius == 7

    def test_mopping_setting_changed_adjusts_self_clean_defaults_humidity_high(self) -> None:
        payload = json.dumps([{"k": DreameVacuumAutoSwitchProperty.MOPPING_MODE.value, "v": 1}])
        d = _listener_full_device(
            data={DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value: payload},
            capability={
                "self_wash_base": True,
                "custom_mopping_route": True,
                "wetness_level": False,
                "mop_clean_frequency": False,
                "small_self_clean_area": False,
                "self_clean_frequency": True,
            },
            status_attrs={"mop_pad_humidity": 3},
        )
        d._auto_switch_settings_changed(previous_auto_switch_settings="old")
        assert d.status.self_clean_area_max == 15
        assert d.status.self_clean_time_max == 20

    def test_mopping_setting_changed_adjusts_self_clean_defaults_humidity_low(self) -> None:
        payload = json.dumps([{"k": DreameVacuumAutoSwitchProperty.CUSTOM_MOPPING_MODE.value, "v": 1}])
        d = _listener_full_device(
            data={DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value: payload},
            capability={
                "self_wash_base": True,
                "custom_mopping_route": True,
                "wetness_level": False,
                "mop_clean_frequency": False,
                "small_self_clean_area": False,
                "self_clean_frequency": True,
                "cleaning_route": True,
            },
            status_attrs={"mop_pad_humidity": 1},
        )
        d._auto_switch_settings_changed(previous_auto_switch_settings="old")
        assert d.status.self_clean_area_max == 35
        assert d.status.self_clean_time_max == 50

    def test_cleangenius_changed_refreshes_map_when_ready(self) -> None:
        payload = json.dumps([{"k": DreameVacuumAutoSwitchProperty.CLEANGENIUS.value, "v": 1}])
        map_manager = MagicMock()
        d = _listener_full_device(data={DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value: payload}, ready=True)
        d._map_manager = map_manager
        d._auto_switch_settings_changed(previous_auto_switch_settings="old")
        map_manager.editor.refresh_map.assert_called_once()

    def test_dirty_value_discarded_within_window(self) -> None:
        from custom_components.dreame_vacuum.dreame.vacuum_types import DirtyData

        payload = json.dumps([{"k": DreameVacuumAutoSwitchProperty.CLEANGENIUS.value, "v": 1}])
        d = _listener_full_device(data={DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value: payload})
        d._dirty_auto_switch_data[DreameVacuumAutoSwitchProperty.CLEANGENIUS.name] = DirtyData(
            value=0, update_time=time.time()
        )
        d._auto_switch_settings_changed(previous_auto_switch_settings="old")
        assert DreameVacuumAutoSwitchProperty.CLEANGENIUS.name not in d._dirty_auto_switch_data
        assert DreameVacuumAutoSwitchProperty.CLEANGENIUS.name not in (d.auto_switch_data or {})

    def test_short_value_is_ignored(self) -> None:
        d = _listener_full_device(data={DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value: ""})
        d._auto_switch_settings_changed(previous_auto_switch_settings="old")
        d._property_changed.assert_not_called()


# ===========================================================================
# _dnd_task_changed / _schedule_changed / _stream_status_changed /
# _shortcuts_changed / _voice_assistant_language_changed /
# _drainage_status_changed / _self_wash_base_status_changed /
# _off_peak_charging_changed / _suction_level_changed / _water_volume_changed /
# _wetness_level_changed / _error_changed / _battery_level_changed
# ===========================================================================


class TestDndTaskChanged:
    def test_parses_json_payload(self) -> None:
        d = _listener_full_device(data={DreameVacuumProperty.DND_TASK.value: json.dumps([{"id": 1}])})
        d._dnd_task_changed()
        assert d.status.dnd_tasks == [{"id": 1}]

    def test_empty_payload_leaves_dnd_tasks_untouched(self) -> None:
        d = _listener_full_device(data={})
        d._dnd_task_changed()
        assert d.status.dnd_tasks is None


class TestScheduleChanged:
    def test_parses_and_sorts_multiple_tasks(self) -> None:
        schedule = ";".join(
            [
                "2-1-10:00-1234567-1-map-1-1-0",
                "1-1-09:00-1234567-1-map-1-1-0",
            ]
        )
        d = _listener_full_device(data={DreameVacuumProperty.SCHEDULE.value: schedule})
        d._schedule_changed()
        assert [t.id for t in d.status.schedule] == [1, 2]

    def test_options_field_parsed_when_not_zero(self) -> None:
        schedule = "5-1-09:00-1234567-1-map-1-1-a,b"
        d = _listener_full_device(data={DreameVacuumProperty.SCHEDULE.value: schedule})
        d._schedule_changed()
        assert d.status.schedule[0].options == ["a", "b"]

    def test_empty_schedule_results_in_empty_list(self) -> None:
        d = _listener_full_device(data={DreameVacuumProperty.SCHEDULE.value: ""})
        d._schedule_changed()
        assert d.status.schedule == []

    def test_invalid_task_missing_fields_skipped(self) -> None:
        d = _listener_full_device(data={DreameVacuumProperty.SCHEDULE.value: "1-2-3"})
        d._schedule_changed()
        assert d.status.schedule == []


class TestStreamStatusChanged:
    @pytest.mark.parametrize(
        ("operation_type", "operation", "expected"),
        [
            ("end", None, DreameVacuumStreamStatus.IDLE),
            ("start", "monitor", DreameVacuumStreamStatus.VIDEO),
            ("monitor", "start", DreameVacuumStreamStatus.VIDEO),
            ("start", "intercom", DreameVacuumStreamStatus.AUDIO),
            ("start", "recordVideo", DreameVacuumStreamStatus.RECORDING),
        ],
    )
    def test_operation_variants_set_stream_status(self, operation_type, operation, expected) -> None:
        payload = json.dumps({"result": 0, "session": "abc", "operType": operation_type, "operation": operation})
        d = _listener_full_device(data={DreameVacuumProperty.STREAM_STATUS.value: payload})
        d._stream_status_changed()
        assert d.status.stream_status is expected
        assert d.status.stream_session == "abc"

    def test_falsy_operation_type_leaves_stream_status_untouched(self) -> None:
        payload = json.dumps({"result": 0, "session": "abc"})
        d = _listener_full_device(data={DreameVacuumProperty.STREAM_STATUS.value: payload})
        d._stream_status_changed()
        assert d.status.stream_status is None
        assert d.status.stream_session == "abc"

    def test_null_string_ignored(self) -> None:
        d = _listener_full_device(data={DreameVacuumProperty.STREAM_STATUS.value: "null"})
        d._stream_status_changed()
        assert d.status.stream_status is None

    def test_nonzero_result_ignored(self) -> None:
        payload = json.dumps({"result": 1})
        d = _listener_full_device(data={DreameVacuumProperty.STREAM_STATUS.value: payload})
        d._stream_status_changed()
        assert d.status.stream_status is None


class TestShortcutsChanged:
    def test_delegates_to_reload_shortcuts(self) -> None:
        d = _listener_full_device()
        d._shortcuts_changed()
        d.reload_shortcuts.assert_called_once()


class TestVoiceAssistantLanguageChanged:
    def test_value_present_builds_language_list_without_default(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE.value: "en"},
        )
        d._voice_assistant_language_changed()
        assert DreameVacuumVoiceAssistantLanguage.DEFAULT not in d.status.voice_assistant_language_list.values()

    def test_value_absent_keeps_default_in_list(self) -> None:
        d = _listener_full_device(data={})
        d._voice_assistant_language_changed()
        assert DreameVacuumVoiceAssistantLanguage.DEFAULT in d.status.voice_assistant_language_list.values()


class TestDrainageStatusChanged:
    def test_sets_time_when_draining_complete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, draining_complete=True)
        d = _listener_full_device()
        d._drainage_status_changed()
        assert d._draining_complete_time is not None

    def test_clears_time_when_not_draining_complete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, draining_complete=False)
        d = _listener_full_device()
        d._draining_complete_time = 123.0
        d._drainage_status_changed()
        assert d._draining_complete_time is None


class TestSelfWashBaseStatusChanged:
    def test_previous_none_is_noop(self) -> None:
        d = _listener_full_device()
        d._self_wash_base_status_changed(None)
        assert d._consumable_change is False

    def test_washing_state_change_flags_consumable_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # started=True + previous==WASHING makes the "was washing" side of the
        # XOR True; washing=False makes the "is washing now" side False ->
        # mismatch -> consumable_change flagged.
        _patch_status_props(monkeypatch, started=True, washing=False)
        d = _listener_full_device()
        d._self_wash_base_status_changed(previous_self_wash_base_status=DreameVacuumSelfWashBaseStatus.WASHING.value)
        assert d._consumable_change is True

    def test_map_manager_refreshed_when_present(self) -> None:
        map_manager = MagicMock()
        d = _listener_full_device()
        d._map_manager = map_manager
        d._self_wash_base_status_changed(previous_self_wash_base_status=DreameVacuumSelfWashBaseStatus.IDLE.value)
        map_manager.editor.refresh_map.assert_called_once()


class TestOffPeakChargingChanged:
    def test_parses_json_config(self) -> None:
        d = _listener_full_device(data={DreameVacuumProperty.OFF_PEAK_CHARGING.value: json.dumps({"start": "01:00"})})
        d._off_peak_charging_changed()
        assert d.status.off_peak_charging_config == {"start": "01:00"}

    def test_empty_value_leaves_config_untouched(self) -> None:
        d = _listener_full_device(data={})
        d._off_peak_charging_changed()
        assert d.status.off_peak_charging_config is None


class TestSuctionLevelChanged:
    def test_resets_go_to_zone_suction_level(self) -> None:
        zone = GoToZoneSettings(suction_level=5)
        d = _listener_full_device(status_attrs={"go_to_zone": zone})
        d._suction_level_changed(previous_suction_level=3)
        assert zone.suction_level is None

    def test_previous_none_is_noop(self) -> None:
        zone = GoToZoneSettings(suction_level=5)
        d = _listener_full_device(status_attrs={"go_to_zone": zone})
        d._suction_level_changed(previous_suction_level=None)
        assert zone.suction_level == 5


class TestWaterVolumeChanged:
    def test_wetness_without_wetness_level_syncs_mop_pad_humidity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, water_volume=DreameVacuumMopPadHumidity.WET)
        d = _listener_full_device(capability={"wetness": True, "wetness_level": False})
        d._water_volume_changed()
        assert d.status.mop_pad_humidity == DreameVacuumMopPadHumidity.WET.value

    def test_resets_go_to_zone_water_level(self) -> None:
        zone = GoToZoneSettings(water_level=2)
        d = _listener_full_device(
            capability={"wetness": False, "wetness_level": False}, status_attrs={"go_to_zone": zone}
        )
        d._water_volume_changed(previous_water_volume=1)
        assert zone.water_level is None


class TestWetnessLevelChanged:
    def test_high_wetness_level_sets_wet(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.WETNESS_LEVEL.value: 250},
            capability={"self_wash_base": False, "wetness_level": False, "mop_clean_frequency": False},
        )
        d._wetness_level_changed()
        assert d.status.mop_pad_humidity == 3

    def test_mid_high_wetness_level_between_thresholds_stays_moist(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.WETNESS_LEVEL.value: 200},
            capability={"self_wash_base": False, "wetness_level": False, "mop_clean_frequency": False},
        )
        d._wetness_level_changed()
        assert d.status.mop_pad_humidity == 2

    def test_low_wetness_level_sets_slightly_dry(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.WETNESS_LEVEL.value: 3},
            capability={"self_wash_base": False, "wetness_level": False, "mop_clean_frequency": False},
        )
        d._wetness_level_changed()
        assert d.status.mop_pad_humidity == 1

    def test_self_wash_base_high_wetness_sets_time_defaults(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.WETNESS_LEVEL.value: 250},
            capability={
                "self_wash_base": True,
                "wetness_level": True,
                "mop_clean_frequency": False,
                "small_self_clean_area": False,
            },
        )
        d._wetness_level_changed()
        assert d.status.self_clean_time_max == 20
        assert d.status.self_clean_area_max == 20

    def test_self_wash_base_low_wetness_sets_other_defaults(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.WETNESS_LEVEL.value: 3},
            capability={
                "self_wash_base": True,
                "wetness_level": True,
                "mop_clean_frequency": False,
                "small_self_clean_area": False,
            },
        )
        d._wetness_level_changed()
        assert d.status.self_clean_time_max == 50
        assert d.status.self_clean_area_max == 35

    def test_zero_wetness_level_is_noop(self) -> None:
        d = _listener_full_device(
            data={DreameVacuumProperty.WETNESS_LEVEL.value: 0},
            capability={"self_wash_base": False},
        )
        d.status.mop_pad_humidity = 42
        d._wetness_level_changed()
        assert d.status.mop_pad_humidity == 42


class TestErrorChanged:
    def test_restores_go_to_zone_when_error_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_status_props(monkeypatch, has_error=True)
        d = _listener_full_device(status_attrs={"go_to_zone": GoToZoneSettings()})
        d._error_changed(previous_error=0)
        d._restore_go_to_zone.assert_called_once_with(True)

    def test_previous_none_is_noop(self) -> None:
        d = _listener_full_device(status_attrs={"go_to_zone": GoToZoneSettings()})
        d._error_changed(previous_error=None)
        d._restore_go_to_zone.assert_not_called()

    def test_map_manager_refreshed_when_previous_present(self) -> None:
        map_manager = MagicMock()
        d = _listener_full_device()
        d._map_manager = map_manager
        d._error_changed(previous_error=0)
        map_manager.editor.refresh_map.assert_called_once()


class TestBatteryLevelChanged:
    def test_refreshes_map_when_full_and_previous_present(self) -> None:
        map_manager = MagicMock()
        d = _listener_full_device(data={DreameVacuumProperty.BATTERY_LEVEL.value: 100})
        d._map_manager = map_manager
        d._battery_level_changed(previous_battery_level=90)
        map_manager.editor.refresh_map.assert_called_once()

    def test_no_refresh_when_previous_is_none(self) -> None:
        map_manager = MagicMock()
        d = _listener_full_device(data={DreameVacuumProperty.BATTERY_LEVEL.value: 100})
        d._map_manager = map_manager
        d._battery_level_changed(previous_battery_level=None)
        map_manager.editor.refresh_map.assert_not_called()

    def test_no_refresh_when_not_full(self) -> None:
        map_manager = MagicMock()
        d = _listener_full_device(data={DreameVacuumProperty.BATTERY_LEVEL.value: 80})
        d._map_manager = map_manager
        d._battery_level_changed(previous_battery_level=70)
        map_manager.editor.refresh_map.assert_not_called()


# ===========================================================================
# _request_cleaning_history
# ===========================================================================


def _history_event(*entries: tuple[DreameVacuumProperty, object]) -> dict[str, str]:
    payload = [{"piid": PIID(prop, DreameVacuumPropertyMapping), "value": value} for prop, value in entries]
    return {"value": json.dumps(payload)}


def _cleaning_history_device(
    *,
    capability: dict[str, object] | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
    **overrides: object,
) -> DreameVacuumDevice:
    cap_overrides = {"auto_recleaning": False, "cleangenius": False}
    cap_overrides.update(capability or {})
    d = _listener_full_device(capability=cap_overrides, monkeypatch=monkeypatch)
    d._protocol = SimpleNamespace(cloud=MagicMock(connected=True), prefer_cloud=False, dreame_cloud=False)
    d._cleaning_history_update = -1
    d._cleaning_history_retry_after = 0
    d.status._cleaning_history = None
    d.data[DreameVacuumProperty.TASK_STATUS.value] = DreameVacuumTaskStatus.COMPLETED.value
    for key, value in overrides.items():
        setattr(d, key, value)
    return d


class TestRequestCleaningHistory:
    def test_not_cloud_connected_skips_request(self) -> None:
        d = _cleaning_history_device()
        d._protocol = SimpleNamespace(cloud=None)
        d._request_cleaning_history()
        # No crash, nothing to assert on a None cloud beyond "did not raise".

    def test_update_flag_zero_skips_request(self) -> None:
        d = _cleaning_history_device()
        d._cleaning_history_update = 0
        d._request_cleaning_history()
        d._protocol.cloud.get_device_event.assert_not_called()

    def test_retry_after_in_future_skips_request(self) -> None:
        d = _cleaning_history_device()
        d._cleaning_history_retry_after = time.time() + 1000
        d._request_cleaning_history()
        d._protocol.cloud.get_device_event.assert_not_called()

    def test_successful_fetch_populates_cleaning_history(self) -> None:
        d = _cleaning_history_device()
        d._protocol.cloud.get_device_event.return_value = [
            _history_event(
                (DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value),
                (DreameVacuumProperty.CLEANING_START_TIME, 1_700_000_000),
            )
        ]
        d._request_cleaning_history()
        assert d.status._cleaning_history is not None
        assert len(d.status._cleaning_history) == 1
        d._property_changed.assert_called()

    def test_none_result_marks_request_failed_and_reschedules_retry(self) -> None:
        d = _cleaning_history_device()
        d._protocol.cloud.get_device_event.return_value = None
        d._request_cleaning_history()
        assert d._cleaning_history_retry_after > time.time()

    def test_concurrent_rearm_during_failure_is_not_clobbered(self) -> None:
        """If cleaning_history_update was re-armed mid-call, the failure path
        must not stomp the fresh signal with the stale pending value."""

        def _rearm_and_fail(*_args: object, **_kwargs: object) -> None:
            d._cleaning_history_update = time.time()
            return

        d = _cleaning_history_device()
        d._protocol.cloud.get_device_event.side_effect = _rearm_and_fail
        d._request_cleaning_history()
        # The rearmed nonzero value must survive (not reset to the old pending sentinel of -1).
        assert d._cleaning_history_update != -1

    def test_exception_during_fetch_marks_request_failed(self) -> None:
        d = _cleaning_history_device()
        d._protocol.cloud.get_device_event.side_effect = RuntimeError("network boom")
        d._request_cleaning_history()
        assert d._cleaning_history_retry_after > time.time()

    def test_cruising_capability_also_fetches_cruising_history(self, monkeypatch: pytest.MonkeyPatch) -> None:
        d = _cleaning_history_device(capability={"cruising": True}, monkeypatch=monkeypatch)
        events = [
            _history_event((DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value)),
        ]
        d._protocol.cloud.get_device_event.return_value = events
        d._request_cleaning_history()
        assert d._protocol.cloud.get_device_event.call_count == 2
        assert d.status._cruising_history is not None

    def test_auto_recleaning_triggers_history_map(self) -> None:
        d = _cleaning_history_device(capability={"auto_recleaning": True})
        d._protocol.cloud.get_device_event.return_value = [
            _history_event((DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value))
        ]
        d._request_cleaning_history()
        d.history_map.assert_called_once_with(1)

    def test_duplicate_dates_are_deduplicated(self) -> None:
        d = _cleaning_history_device()
        event = _history_event(
            (DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value),
            (DreameVacuumProperty.CLEANING_START_TIME, 1_700_000_000),
        )
        d._protocol.cloud.get_device_event.return_value = [event, event]
        d._request_cleaning_history()
        assert len(d.status._cleaning_history) == 1

    def test_stale_history_map_data_entries_are_pruned_when_ready(self) -> None:
        from custom_components.dreame_vacuum.dreame.vacuum_types import MapData

        d = _cleaning_history_device()
        d._ready = True
        stale = MapData()
        d.status._history_map_data = {"stale-key": stale}
        event = _history_event(
            (DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value),
            (DreameVacuumProperty.CLEAN_LOG_FILE_NAME, "other-file.json"),
        )
        d._protocol.cloud.get_device_event.return_value = [event]
        d._request_cleaning_history()
        assert "stale-key" not in d.status._history_map_data

    def test_history_map_data_entry_referenced_by_cleaning_history_is_kept(self) -> None:
        from custom_components.dreame_vacuum.dreame.vacuum_types import MapData

        d = _cleaning_history_device()
        d._ready = True
        kept = MapData()
        d.status._history_map_data = {"mykey": kept}
        event = _history_event(
            (DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value),
            (DreameVacuumProperty.CLEAN_LOG_FILE_NAME, "prefix_mykey_suffix.json"),
        )
        d._protocol.cloud.get_device_event.return_value = [event]
        map_manager = MagicMock()
        d._map_manager = map_manager
        d._request_cleaning_history()
        assert "mykey" in d.status._history_map_data
        map_manager.editor.refresh_map.assert_called_once()

    def test_history_map_data_entry_referenced_by_cruising_history_is_kept(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from custom_components.dreame_vacuum.dreame.vacuum_types import MapData

        d = _cleaning_history_device(capability={"cruising": True}, monkeypatch=monkeypatch)
        d._ready = True
        kept = MapData()
        d.status._history_map_data = {"cruisekey": kept}
        cleaning_event = _history_event(
            (DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value),
            (DreameVacuumProperty.CLEAN_LOG_FILE_NAME, "unrelated.json"),
        )
        cruising_event = _history_event(
            (DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value),
            (DreameVacuumProperty.CLEAN_LOG_FILE_NAME, "prefix_cruisekey_suffix.json"),
        )
        d._protocol.cloud.get_device_event.side_effect = [[cleaning_event], [cruising_event]]
        d._request_cleaning_history()
        assert "cruisekey" in d.status._history_map_data

    def test_cleanup_method_customized_cleaning_becomes_default_when_cleangenius(self) -> None:
        d = _cleaning_history_device(capability={"cleangenius": True})
        event = _history_event(
            (DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value),
            (
                DreameVacuumProperty.CLEANING_PROPERTIES,
                json.dumps({"cmc": 1}),  # CleanupMethod.CUSTOMIZED_CLEANING
            ),
        )
        d._protocol.cloud.get_device_event.return_value = [event]
        d._request_cleaning_history()
        from custom_components.dreame_vacuum.dreame.vacuum_types import CleanupMethod

        assert d.status._cleaning_history[0].cleanup_method is CleanupMethod.DEFAULT_MODE

    def test_result_limited_to_total_breaks_early(self) -> None:
        d = _cleaning_history_device()
        d.data[DreameVacuumProperty.CLEANING_COUNT.value] = 1
        events = [
            _history_event(
                (DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value),
                (DreameVacuumProperty.CLEANING_START_TIME, 1_700_000_000 + i),
            )
            for i in range(3)
        ]
        d._protocol.cloud.get_device_event.return_value = events
        d._request_cleaning_history()
        # total=1 -> loop breaks after the first distinct-date entry.
        assert len(d.status._cleaning_history) == 1

    def test_cruising_none_result_also_marks_request_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        d = _cleaning_history_device(capability={"cruising": True}, monkeypatch=monkeypatch)
        cleaning_event = _history_event((DreameVacuumProperty.STATUS, DreameVacuumStatus.CLEANING.value))
        d._protocol.cloud.get_device_event.side_effect = [[cleaning_event], None]
        d._request_cleaning_history()
        assert d._cleaning_history_retry_after > time.time()


# ===========================================================================
# _action_update_task / _update_task
# ===========================================================================


def _update_task_device(**overrides: object) -> DreameVacuumDevice:
    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    d._update_timer = MagicMock()
    d._timer_lock = RLock()
    d.disconnected = False
    d.available = False
    d._ready = True
    d._update_fail_count = 0
    d._last_update_failed = None
    d.update = MagicMock()
    d.schedule_update = MagicMock()
    d._update_failed = MagicMock()
    # _update_task() reads self._update_interval (a real property) as the
    # argument to schedule_update() even though schedule_update is mocked.
    d.status = SimpleNamespace(
        map_backup_status=False, map_recovery_status=False, active=False, started=False, running=False
    )
    d._protocol = SimpleNamespace(prefer_cloud=False)
    d._last_change = 0.0
    d._map_manager = None
    for key, value in overrides.items():
        setattr(d, key, value)
    return d


class TestActionUpdateTask:
    def test_delegates_to_update_task_with_force_flag(self) -> None:
        d = _update_task_device()
        d._update_task = MagicMock()
        d._action_update_task()
        d._update_task.assert_called_once_with(True)


class TestUpdateTask:
    def test_success_resets_fail_count_and_reschedules(self) -> None:
        d = _update_task_device()
        d._update_fail_count = 2
        d._update_task()
        assert d._update_fail_count == 0
        assert d.available is True
        d.schedule_update.assert_called_once()
        assert d._update_timer is None

    def test_failure_increments_count_and_logs_debug_below_threshold(self, caplog) -> None:
        d = _update_task_device()
        d.update.side_effect = RuntimeError("boom")
        d.available = True
        import logging

        with caplog.at_level(logging.DEBUG):
            d._update_task()
        assert d._update_fail_count == 1
        assert d._last_update_failed is not None
        d._update_failed.assert_not_called()

    def test_failure_above_threshold_marks_unavailable_and_notifies(self) -> None:
        d = _update_task_device(_update_fail_count=3, _ready=True)
        d.update.side_effect = RuntimeError("boom")
        d.available = True
        d._update_task()
        assert d.available is False
        d._update_failed.assert_called_once()

    def test_failure_while_already_unavailable_does_not_touch_last_failed(self) -> None:
        d = _update_task_device()
        d.update.side_effect = RuntimeError("boom")
        d.available = False
        d._last_update_failed = None
        d._update_task()
        assert d._last_update_failed is None

    def test_disconnected_device_does_not_reschedule(self) -> None:
        d = _update_task_device()
        d.disconnected = True
        d._update_task()
        d.schedule_update.assert_not_called()

    def test_force_request_properties_forwarded_to_update(self) -> None:
        d = _update_task_device()
        d._update_task(True)
        d.update.assert_called_once_with(True)


# ===========================================================================
# _perform_update — remaining branches
# ===========================================================================


def _boot_perform_update_device(**status_overrides: object) -> DreameVacuumDevice:
    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    d._protocol = SimpleNamespace(connected=True, cloud=None, prefer_cloud=False, dreame_cloud=False)
    d.connect_cloud = MagicMock()
    d.connect_device = MagicMock()
    d._map_initialized = False
    d._full_properties_loaded = False
    d._map_manager = None
    d._consumable_change = False
    d._last_settings_request = time.time()
    d._last_map_list_request = time.time()
    d._last_map_request = 0.0
    d._draining_complete_time = None
    d._dirty_data = {}
    d._dirty_auto_switch_data = {}
    d._dirty_ai_data = {}
    d._deferred_cloud_loaded = True
    d._last_map_change_time = None
    d._cleaning_history_lock = RLock()
    d._cleaning_history_update = 0
    d._last_change = 0.0
    base_status = {
        "active": False,
        "started": False,
        "washing": False,
        "running": False,
        "map_backup_status": False,
        "map_recovery_status": False,
        "current_map": None,
        "docked": False,
        "ai_policy_accepted": True,
        "draining_complete": False,
    }
    base_status.update(status_overrides)
    d.status = SimpleNamespace(**base_status)
    d.capability = SimpleNamespace(backup_map=False, disable_sensor_cleaning=False, dnd_task=True, ai_detection=False)
    d._read_write_properties = []
    d._request_properties = MagicMock(return_value=True)
    d.set_property = MagicMock()
    return d


class TestPerformUpdateDeviceUnreachable:
    def test_device_not_connected_raises(self) -> None:
        d = _boot_perform_update_device()
        d._protocol = SimpleNamespace(connected=False, cloud=None, prefer_cloud=False, dreame_cloud=False)
        d.connect_cloud = MagicMock()
        d.connect_device = MagicMock()
        from custom_components.dreame_vacuum.dreame.exceptions import DeviceUpdateFailedException

        with pytest.raises(DeviceUpdateFailedException):
            d._perform_update()
        d.connect_device.assert_called_once()


class TestPerformUpdateFirstCycle:
    def test_full_properties_not_loaded_fallback_loads_them(self) -> None:
        d = _boot_perform_update_device()
        d._full_properties_loaded = False
        d._perform_update()
        d._request_properties.assert_called_once_with(force_all=True)
        assert d._full_properties_loaded is True

    def test_map_manager_updates_map_when_no_current_map(self) -> None:
        map_manager = MagicMock()
        d = _boot_perform_update_device()
        d._map_manager = map_manager
        d._full_properties_loaded = True
        d._perform_update()
        map_manager.update.assert_called_once()
        map_manager.schedule_update.assert_called_once()

    def test_map_manager_uses_update_map_when_current_map_present(self) -> None:
        map_manager = MagicMock()
        d = _boot_perform_update_device(current_map=object())
        d._map_manager = map_manager
        d._full_properties_loaded = True
        d.update_map = MagicMock()
        d._perform_update()
        d.update_map.assert_called_once()
        map_manager.update.assert_not_called()

    def test_map_update_exception_is_logged_not_raised(self) -> None:
        map_manager = MagicMock()
        map_manager.update.side_effect = RuntimeError("boom")
        d = _boot_perform_update_device()
        d._map_manager = map_manager
        d._full_properties_loaded = True
        d._perform_update()  # must not raise

    def test_cloud_connected_defers_cleaning_history_flag(self) -> None:
        d = _boot_perform_update_device()
        d._protocol = SimpleNamespace(
            connected=True, cloud=SimpleNamespace(connected=True), prefer_cloud=False, dreame_cloud=False
        )
        d.connect_cloud = MagicMock()
        d.connect_device = MagicMock()
        d._perform_update()
        assert d._cleaning_history_update == -1

    def test_returns_before_reaching_second_cycle_properties(self) -> None:
        d = _boot_perform_update_device()
        d._perform_update()
        # Second-cycle "read-only properties" request never happens on cycle 1
        # because of the early `return` in the map-initialization branch.
        d._request_properties.assert_called_once_with(force_all=True)


class TestPerformUpdateSecondCycleBranches:
    def _ready_device(self, **status_overrides: object) -> DreameVacuumDevice:
        d = _boot_perform_update_device(**status_overrides)
        d._map_initialized = True
        d._full_properties_loaded = True
        return d

    def test_backup_map_capability_adds_property(self) -> None:
        d = self._ready_device()
        d.capability.backup_map = True
        d._perform_update()
        props = d._request_properties.call_args.args[0]
        assert DreameVacuumProperty.MAP_BACKUP_STATUS in props

    def test_dreame_cloud_disconnected_forces_full_request(self) -> None:
        d = self._ready_device()
        # device_connected must be True (else _perform_update raises earlier);
        # cloud_connected False is what triggers the force_request_properties path.
        d._protocol = SimpleNamespace(
            connected=True, cloud=SimpleNamespace(connected=False), prefer_cloud=False, dreame_cloud=True
        )
        d._perform_update()
        d._request_properties.assert_called_once()
        # Forced full request: not restricted to MAP_BACKUP_STATUS/MAP_RECOVERY_STATUS only.
        props = d._request_properties.call_args.args[0]
        assert DreameVacuumProperty.STATE in props

    def test_dreame_cloud_connected_map_backup_status_only(self) -> None:
        d = self._ready_device(map_backup_status=True)
        d._protocol = SimpleNamespace(
            connected=True, cloud=SimpleNamespace(connected=True), prefer_cloud=False, dreame_cloud=True
        )
        d._perform_update()
        d._request_properties.assert_called_once_with([DreameVacuumProperty.MAP_BACKUP_STATUS])

    def test_dreame_cloud_connected_map_recovery_status_only(self) -> None:
        d = self._ready_device(map_recovery_status=True)
        d._protocol = SimpleNamespace(
            connected=True, cloud=SimpleNamespace(connected=True), prefer_cloud=False, dreame_cloud=True
        )
        d._perform_update()
        d._request_properties.assert_called_once_with([DreameVacuumProperty.MAP_RECOVERY_STATUS])

    def test_dreame_cloud_connected_neither_status_skips_request(self) -> None:
        d = self._ready_device()
        d._protocol = SimpleNamespace(
            connected=True, cloud=SimpleNamespace(connected=True), prefer_cloud=False, dreame_cloud=True
        )
        d._perform_update()
        d._request_properties.assert_not_called()

    def test_generic_exception_from_request_properties_is_wrapped(self) -> None:
        d = self._ready_device()
        d._request_properties.side_effect = ValueError("boom")
        from custom_components.dreame_vacuum.dreame.exceptions import DeviceUpdateFailedException

        with pytest.raises(DeviceUpdateFailedException):
            d._perform_update()

    def test_dirty_data_restored_after_timeout(self) -> None:
        from custom_components.dreame_vacuum.dreame.vacuum_types import DirtyData

        d = self._ready_device()
        d._restore_timeout = 1
        d.data = {DreameVacuumProperty.SUCTION_LEVEL.value: 5}
        d._dirty_data = {
            DreameVacuumProperty.SUCTION_LEVEL.value: DirtyData(value=5, previous_value=2, update_time=time.time() - 10)
        }
        cb = MagicMock()
        d._property_update_callback = {DreameVacuumProperty.SUCTION_LEVEL.value: [cb]}
        d._property_changed = MagicMock()
        d.schedule_update = MagicMock()
        d._perform_update()
        assert d.data[DreameVacuumProperty.SUCTION_LEVEL.value] == 2
        cb.assert_called_once_with(2)
        d.schedule_update.assert_called_once_with(1, True)
        assert DreameVacuumProperty.SUCTION_LEVEL.value not in d._dirty_data

    def test_dirty_auto_switch_and_ai_data_expire(self) -> None:
        from custom_components.dreame_vacuum.dreame.vacuum_types import DirtyData

        d = self._ready_device()
        d._restore_timeout = 1
        d._dirty_auto_switch_data = {"X": DirtyData(value=1, update_time=time.time() - 10)}
        d._dirty_ai_data = {"Y": DirtyData(value=1, update_time=time.time() - 10)}
        d._perform_update()
        assert d._dirty_auto_switch_data == {}
        assert d._dirty_ai_data == {}

    def test_map_manager_requests_next_lists_after_idle_period(self) -> None:
        map_manager = MagicMock()
        d = self._ready_device()
        d._map_manager = map_manager
        d._last_map_change_time = time.time() - 200
        d._perform_update()
        map_manager.request_next_map_list.assert_called_once()
        map_manager.request_next_recovery_map_list.assert_called_once()
        assert d._last_map_change_time is None

    def test_draining_reset_after_ten_minutes(self) -> None:
        d = self._ready_device(draining_complete=True)
        d._draining_complete_time = time.time() - 700
        d._perform_update()
        d.set_property.assert_called_once_with(DreameVacuumProperty.DRAINAGE_STATUS, 0)
        assert d._draining_complete_time is None

    def test_cloud_connected_triggers_cleaning_history_request(self) -> None:
        d = self._ready_device()
        d._protocol = SimpleNamespace(
            connected=True, cloud=SimpleNamespace(connected=True), prefer_cloud=False, dreame_cloud=False
        )
        d._request_cleaning_history = MagicMock()
        d._perform_update()
        d._request_cleaning_history.assert_called_once()

    def test_ai_config_lookup_sets_policy_accepted(self) -> None:
        d = self._ready_device(ai_policy_accepted=False)
        d._protocol = SimpleNamespace(
            connected=True, cloud=SimpleNamespace(connected=True), prefer_cloud=False, dreame_cloud=False
        )
        d._protocol.cloud.get_batch_device_datas = MagicMock(
            return_value={"prop.s_ai_config": json.dumps({"privacyAuthed": True})}
        )
        d.capability.ai_detection = True
        d._deferred_cloud_loaded = False
        d._request_cleaning_history = MagicMock()
        d._perform_update()
        assert d.status.ai_policy_accepted is True
        assert d._deferred_cloud_loaded is True

    def test_ai_config_lookup_failure_is_swallowed(self) -> None:
        d = self._ready_device(ai_policy_accepted=False)
        d._protocol = SimpleNamespace(
            connected=True, cloud=SimpleNamespace(connected=True), prefer_cloud=False, dreame_cloud=False
        )
        d._protocol.cloud.get_batch_device_datas = MagicMock(side_effect=ValueError("boom"))
        d.capability.ai_detection = True
        d._deferred_cloud_loaded = False
        d._request_cleaning_history = MagicMock()
        d._perform_update()  # must not raise
        assert d._deferred_cloud_loaded is True

    def test_consumable_change_reset_after_cycle(self) -> None:
        d = self._ready_device()
        d._consumable_change = True
        d._perform_update()
        assert d._consumable_change is False


# ===========================================================================
# _handle_properties "not ready" (warm boot) branches
# ===========================================================================


def _boot_handle_properties_device(*, capability: dict[str, object] | None = None) -> DreameVacuumDevice:
    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    d.data = {}
    d._dirty_data = {}
    d._discard_timeout = 5
    d._property_update_callback = {}
    d._ready = False
    d._last_change = 0.0
    d._map_manager = None
    d._protocol = SimpleNamespace(dreame_cloud=False)

    cap = DreameVacuumDeviceCapability(d)
    cap.load = lambda *_a, **_k: None
    for key, value in (capability or {}).items():
        setattr(cap, key, value)
    d.capability = cap
    d.status = DreameVacuumDeviceStatus(d)
    return d


def _boot_prop(did: int, value: object, siid: int = 0, piid: int = 0, code: int = 0) -> dict:
    return {"did": str(did), "siid": siid, "piid": piid, "code": code, "value": value}


class TestHandlePropertiesBootLoop:
    def test_did_resolved_via_siid_piid_when_not_a_known_enum_value(self) -> None:
        d = _boot_handle_properties_device()
        mapping = DreameVacuumPropertyMapping[DreameVacuumProperty.BATTERY_LEVEL]
        result = d._handle_properties([_boot_prop(999999, 88, siid=mapping["siid"], piid=mapping["piid"])])
        assert d.data[DreameVacuumProperty.BATTERY_LEVEL.value] == 88
        assert result is True

    def test_added_and_unavailable_counted_during_boot_summary(self, caplog) -> None:
        import logging

        d = _boot_handle_properties_device()
        with caplog.at_level(logging.DEBUG):
            d._handle_properties(
                [
                    _boot_prop(DreameVacuumProperty.BATTERY_LEVEL.value, 50),
                    _boot_prop(DreameVacuumProperty.ERROR.value, 0, code=1),
                ]
            )
        assert "Initial properties loaded" in caplog.text

    def test_custom_property_callback_invoked_immediately_when_not_ready(self) -> None:
        d = _boot_handle_properties_device()
        cb = MagicMock()
        d._property_update_callback[DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value] = [cb]
        d._handle_properties([_boot_prop(DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value, "[]")])
        cb.assert_called_once_with(None)


class TestHandlePropertiesBootFinalize:
    def test_self_wash_base_with_mop_clean_frequency_sets_small_range(self) -> None:
        d = _boot_handle_properties_device(capability={"self_wash_base": True, "mop_clean_frequency": True})
        d._handle_properties([])
        assert d.status.self_clean_area_min == 5
        assert d.status.self_clean_area_max == 10
        assert d.status.self_clean_area_default == 8

    def test_self_wash_base_with_small_self_clean_area(self) -> None:
        d = _boot_handle_properties_device(
            capability={"self_wash_base": True, "mop_clean_frequency": False, "small_self_clean_area": True}
        )
        d._handle_properties([])
        assert d.status.self_clean_area_max == 15
        assert d.status.self_clean_area_default == 15

    def test_self_wash_base_default_range_uses_cleaning_route(self) -> None:
        d = _boot_handle_properties_device(
            capability={
                "self_wash_base": True,
                "mop_clean_frequency": False,
                "small_self_clean_area": False,
                "cleaning_route": True,
            }
        )
        d._handle_properties([])
        assert d.status.self_clean_area_max == 35

    def test_mop_clean_frequency_with_pad_swing_prunes_low_frequencies(self) -> None:
        from custom_components.dreame_vacuum.dreame.const import (
            MOP_CLEAN_FREQUENCY_EIGHT_SQUARE_METERS,
            MOP_CLEAN_FREQUENCY_FIVE_SQUARE_METERS,
        )

        d = _boot_handle_properties_device(capability={"mop_clean_frequency": True, "mop_pad_swing": True})
        d._handle_properties([])
        assert MOP_CLEAN_FREQUENCY_EIGHT_SQUARE_METERS not in d.status.mop_clean_frequency_list
        assert MOP_CLEAN_FREQUENCY_FIVE_SQUARE_METERS not in d.status.mop_clean_frequency_list

    def test_mop_clean_frequency_without_pad_swing_prunes_other_frequencies(self) -> None:
        from custom_components.dreame_vacuum.dreame.const import MOP_CLEAN_FREQUENCY_BY_ROOM

        d = _boot_handle_properties_device(capability={"mop_clean_frequency": True, "mop_pad_swing": False})
        d._handle_properties([])
        assert MOP_CLEAN_FREQUENCY_BY_ROOM not in d.status.mop_clean_frequency_list

    def test_smart_mop_washing_without_ultra_clean_mode_prunes_ultra_washing(self) -> None:
        from custom_components.dreame_vacuum.dreame.const import WASHING_MODE_ULTRA_WASHING

        d = _boot_handle_properties_device(capability={"smart_mop_washing": True, "ultra_clean_mode": False})
        d._handle_properties([])
        assert WASHING_MODE_ULTRA_WASHING not in d.status.washing_mode_list

    def test_mopping_after_sweeping_capability_keeps_mode_but_prunes_segment_copy(self) -> None:
        from custom_components.dreame_vacuum.dreame.const import CLEANING_MODE_MOPPING_AFTER_SWEEPING

        d = _boot_handle_properties_device(capability={"mopping_after_sweeping": True})
        d._handle_properties([])
        assert CLEANING_MODE_MOPPING_AFTER_SWEEPING in d.status.cleaning_mode_list
        assert CLEANING_MODE_MOPPING_AFTER_SWEEPING not in d.status.segment_cleaning_mode_list

    def test_cleaning_route_capability_prunes_deep_and_intensive_for_sweeping(self) -> None:
        from custom_components.dreame_vacuum.dreame.vacuum_types import DreameVacuumCleaningRoute

        d = _boot_handle_properties_device(capability={"cleaning_route": True, "segment_slow_clean_route": True})
        d.status.cleaning_mode = DreameVacuumCleaningMode.SWEEPING
        d._handle_properties([])
        assert DreameVacuumCleaningRoute.DEEP not in d.status.cleaning_route_list.values()
        assert DreameVacuumCleaningRoute.INTENSIVE not in d.status.cleaning_route_list.values()

    def test_floor_material_pruned_without_carpet_material_and_type(self) -> None:
        from custom_components.dreame_vacuum.dreame.const import FLOOR_MATERIAL_CARPET

        d = _boot_handle_properties_device(capability={"carpet_material": False, "carpet_type": False})
        d._handle_properties([])
        assert FLOOR_MATERIAL_CARPET not in d.status.floor_material_list

    def test_dreame_cloud_resets_discard_timeout(self) -> None:
        d = _boot_handle_properties_device()
        d._protocol = SimpleNamespace(dreame_cloud=True)
        d._discard_timeout = 999
        d._handle_properties([])
        assert d._discard_timeout == 5


# ===========================================================================
# device_info.py — DreameVacuumDeviceInfo
# ===========================================================================


class TestDeviceInfo:
    def test_repr_formats_model_version_mac_and_ip(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        info = DreameVacuumDeviceInfo(
            {
                "model": "dreame.vacuum.p2028",
                "fw_ver": "4.5.6_0078",
                "mac": "AA:BB:CC:DD:EE:FF",
                "netif": {"localIp": "192.168.1.42"},
            }
        )
        text = repr(info)
        assert "dreame.vacuum.p2028" in text
        assert "78" in text  # version parsed from fw_ver suffix
        assert "AA:BB:CC:DD:EE:FF" in text
        assert "192.168.1.42" in text

    def test_repr_without_network_interface_uses_empty_string(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        info = DreameVacuumDeviceInfo({"model": "m", "mac": "AA:BB:CC:DD:EE:FF"})
        # Must not raise despite no "netif" key.
        assert repr(info).endswith(" @ ")

    def test_network_interface_present_and_absent(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        present = DreameVacuumDeviceInfo({"netif": {"localIp": "10.0.0.1"}})
        assert present.network_interface == {"localIp": "10.0.0.1"}
        absent = DreameVacuumDeviceInfo({})
        assert absent.network_interface is None

    def test_ap_present_builds_dict_from_ssid_bssid_rssi_and_ip(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        info = DreameVacuumDeviceInfo(
            {"ap": {"ssid": "MyWifi", "bssid": "11:22:33:44:55:66", "rssi": -50}, "netif": {"localIp": "10.0.0.2"}}
        )
        assert info.ap == {"ssid": "MyWifi", "bssid": "11:22:33:44:55:66", "rssi": -50, "ip": "10.0.0.2"}

    def test_ap_falls_back_to_siid_when_ssid_missing(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        info = DreameVacuumDeviceInfo({"ap": {"siid": "fallback-ssid"}})
        assert info.ap["ssid"] == "fallback-ssid"

    def test_ap_absent_returns_none(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        assert DreameVacuumDeviceInfo({}).ap is None

    def test_model_present_and_absent(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        assert DreameVacuumDeviceInfo({"model": "dreame.vacuum.p2028"}).model == "dreame.vacuum.p2028"
        assert DreameVacuumDeviceInfo({}).model is None

    def test_firmware_version_prefers_fw_ver_then_falls_back_to_ver(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        assert DreameVacuumDeviceInfo({"fw_ver": "4.5.6_0078"}).firmware_version == "4.5.6_0078"
        assert DreameVacuumDeviceInfo({"ver": "1.2.3_0005"}).firmware_version == "1.2.3_0005"
        assert DreameVacuumDeviceInfo({}).firmware_version is None

    def test_hardware_version_present_and_default(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        assert DreameVacuumDeviceInfo({"hw_ver": "esp32"}).hardware_version == "esp32"
        assert DreameVacuumDeviceInfo({}).hardware_version == "Linux"

    def test_mac_address_present_and_absent(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        assert DreameVacuumDeviceInfo({"mac": "AA:BB:CC:DD:EE:FF"}).mac_address == "AA:BB:CC:DD:EE:FF"
        assert DreameVacuumDeviceInfo({}).mac_address is None

    def test_ip_address_present_and_absent(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        with_ip = DreameVacuumDeviceInfo({"netif": {"localIp": "10.0.0.5"}})
        assert with_ip.ip_address == "10.0.0.5"
        assert DreameVacuumDeviceInfo({}).ip_address is None

    def test_manufacturer_is_constant(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        assert DreameVacuumDeviceInfo({}).manufacturer == "Dreametech™"

    def test_raw_returns_underlying_data(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        data = {"model": "m"}
        assert DreameVacuumDeviceInfo(data).raw is data

    def test_version_parsed_from_two_part_firmware(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        info = DreameVacuumDeviceInfo({"fw_ver": "4.5.6_0078"})
        assert info.version == 78

    def test_version_defaults_to_zero_without_two_part_firmware(self) -> None:
        from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

        info = DreameVacuumDeviceInfo({"fw_ver": "no-underscore-here"})
        assert info.version == 0

        info_missing = DreameVacuumDeviceInfo({})
        assert info_missing.version == 0


# ===========================================================================
# dreame/__init__.py — lazy __getattr__ facade
# ===========================================================================


class TestDreamePackageLazyFacade:
    def test_dir_includes_base_and_lazy_attrs(self) -> None:
        import custom_components.dreame_vacuum.dreame as dreame_pkg

        names = dir(dreame_pkg)
        assert "DreameVacuumDevice" in names
        assert "DreameVacuumProperty" in names
        assert "PROPERTY_TO_NAME" in names

    def test_getattr_lazily_loads_from_const_module(self) -> None:
        import custom_components.dreame_vacuum.dreame as dreame_pkg

        value = dreame_pkg.PROPERTY_TO_NAME
        from custom_components.dreame_vacuum.dreame import const

        assert value is const.PROPERTY_TO_NAME

    def test_getattr_lazily_loads_from_vacuum_types_module(self) -> None:
        import custom_components.dreame_vacuum.dreame as dreame_pkg

        # PROPERTY_AVAILABILITY exists only in vacuum_types.py (not re-exported
        # by const.py), so this genuinely exercises the *second* try/except
        # (the const.py lookup must miss first).
        value = dreame_pkg.PROPERTY_AVAILABILITY
        from custom_components.dreame_vacuum.dreame import vacuum_types

        assert value is vacuum_types.PROPERTY_AVAILABILITY

    def test_getattr_caches_result(self) -> None:
        import custom_components.dreame_vacuum.dreame as dreame_pkg

        first = dreame_pkg.SUCTION_LEVEL_QUIET
        assert "SUCTION_LEVEL_QUIET" in dreame_pkg._lazy_imports
        second = dreame_pkg.__getattr__("SUCTION_LEVEL_QUIET")
        assert first is second

    def test_getattr_unknown_name_raises_attribute_error(self) -> None:
        import custom_components.dreame_vacuum.dreame as dreame_pkg

        with pytest.raises(AttributeError):
            dreame_pkg.__getattr__("THIS_DOES_NOT_EXIST_ANYWHERE_XYZ")

    # NOTE: the `except (ImportError, AttributeError): pass` guards around the
    # `from . import const` / `from . import vacuum_types` lookups (device/../
    # __init__.py) are not exercised here. Forcing an ImportError requires
    # both (a) setting sys.modules[fullname] = None *and* (b) deleting the
    # submodule attribute already bound on the `dreame` package object (every
    # import of `dreame.const`/`dreame.vacuum_types` anywhere in the process
    # — which has always already happened by the time any test runs — binds
    # it as a package attribute; only removing sys.modules is not enough
    # because `from . import X` first tries `getattr(package, "X")`).
    # But (b) makes `getattr` fail, which per PEP 562 re-invokes this very
    # `__getattr__` with name="const"/"vacuum_types", which immediately hits
    # the same `from . import const` line again -> infinite recursion
    # (verified: raises RecursionError). There is no way to reach the except
    # body without either mocking the module under test's own import
    # statement directly (forbidden) or reproducing a state that cannot occur
    # in this codebase (const.py/vacuum_types.py are always importable next
    # to __init__.py). Left uncovered as genuinely-unreachable defensive code.


# ===========================================================================
# miio_patch.py
# ===========================================================================


class TestMiioPatch:
    def test_apply_miio_patch_filters_warning(self) -> None:
        from custom_components.dreame_vacuum.dreame.miio_patch import apply_miio_patch

        apply_miio_patch()  # must not raise

    def test_apply_miio_patch_swallows_unexpected_exception(self, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
        import logging

        from custom_components.dreame_vacuum.dreame import miio_patch

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("filter boom")

        monkeypatch.setattr(miio_patch.warnings, "filterwarnings", _boom)
        with caplog.at_level(logging.WARNING):
            miio_patch.apply_miio_patch()  # must not raise
        assert "Error applying miio warning filter" in caplog.text
