"""Characterization tests for DreameVacuumDevice._handle_properties and
_message_callback.

Strategy: bare instances via object.__new__ with _ready=True so that the
"not self._ready" branches (capability.load, status mutations) are never
entered.  Only data-routing logic is exercised.
"""

from __future__ import annotations

import sys
import time
import types
from unittest.mock import MagicMock

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

from custom_components.dreame_vacuum.dreame.device import DreameVacuumDevice
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    DirtyData,
    DreameVacuumProperty,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BATTERY_DID = DreameVacuumProperty.BATTERY_LEVEL.value  # int 2
_BATTERY_SIID = 3
_BATTERY_PIID = 1

_MAP_LIST_DID = DreameVacuumProperty.MAP_LIST.value  # int 81

# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _bare_device() -> DreameVacuumDevice:
    """Minimal DreameVacuumDevice instance for pure data-routing tests.

    Attributes set here are the complete set required by _handle_properties
    when _ready=True.  Attributes added to satisfy _message_callback are
    added in _bare_device_with_message_support().
    """
    d: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    d.data = {}
    d._dirty_data = {}
    d._discard_timeout = 2
    d._property_update_callback = {}
    d._ready = True
    d._last_change = 0.0
    d._property_changed = MagicMock()
    return d


def _bare_device_with_message_support() -> DreameVacuumDevice:
    """Extends _bare_device with the attributes needed by _message_callback."""
    d = _bare_device()
    # _default_properties is a list[DreameVacuumProperty] in production.
    d._default_properties = [DreameVacuumProperty.BATTERY_LEVEL]
    d._map_manager = None
    d.available = False
    d.info = None
    return d


# ---------------------------------------------------------------------------
# Helper: build a property dict
# ---------------------------------------------------------------------------


def _prop(did: int, value: object, siid: int = 0, piid: int = 0, code: int = 0) -> dict:
    return {"did": str(did), "siid": siid, "piid": piid, "code": code, "value": value}


# ===========================================================================
# Étape 2 : _handle_properties — détection de changement
# ===========================================================================


class TestHandlePropertiesChangeDetection:
    """_handle_properties core routing: new value, same value, map exclusions."""

    def test_new_value_stored_and_changed_returned(self) -> None:
        """New property value is stored; return is truthy (True)."""
        d = _bare_device()
        result = d._handle_properties([_prop(_BATTERY_DID, 85)])
        assert d.data[_BATTERY_DID] == 85
        assert result is True
        d._property_changed.assert_called_once()

    def test_same_value_reemitted_no_change(self) -> None:
        """Re-emitting the same value produces no change."""
        d = _bare_device()
        d.data[_BATTERY_DID] = 85
        result = d._handle_properties([_prop(_BATTERY_DID, 85)])
        assert result is False
        d._property_changed.assert_not_called()
        assert d.data[_BATTERY_DID] == 85

    def test_different_value_updates_data_and_signals_change(self) -> None:
        """A changed value updates data and triggers _property_changed."""
        d = _bare_device()
        d.data[_BATTERY_DID] = 80
        result = d._handle_properties([_prop(_BATTERY_DID, 90)])
        assert d.data[_BATTERY_DID] == 90
        assert result is True
        d._property_changed.assert_called_once()

    def test_code_nonzero_property_ignored(self) -> None:
        """Props with code != 0 are silently ignored."""
        d = _bare_device()
        result = d._handle_properties([_prop(_BATTERY_DID, 50, code=1)])
        assert _BATTERY_DID not in d.data
        assert result is False
        d._property_changed.assert_not_called()

    def test_non_dict_entry_in_list_ignored(self) -> None:
        """Non-dict entries in the property list must not raise."""
        d = _bare_device()
        result = d._handle_properties(["not a dict", 42, None, _prop(_BATTERY_DID, 77)])  # type: ignore[list-item]
        assert d.data[_BATTERY_DID] == 77
        assert result is True

    def test_unknown_did_and_did_siid_piid_none_ignored(self) -> None:
        """did not in enum AND DID(siid=0, piid=0)==None → property ignored."""
        d = _bare_device()
        result = d._handle_properties([{"did": "999999", "siid": 0, "piid": 0, "code": 0, "value": 1}])
        assert d.data == {}
        assert result is False

    def test_map_list_property_data_updated_but_not_changed(self) -> None:
        """MAP_LIST change updates data but does NOT set changed (no _property_changed call)."""
        d = _bare_device()
        result = d._handle_properties([_prop(_MAP_LIST_DID, "some_map")])
        assert d.data[_MAP_LIST_DID] == "some_map"
        assert result is False
        d._property_changed.assert_not_called()


# ===========================================================================
# Étape 3 : _handle_properties — dirty data
# ===========================================================================


class TestHandlePropertiesDirtyData:
    """Dirty-data discard logic."""

    def test_stale_echo_discarded_within_window(self) -> None:
        """Incoming value differs from dirty sentinel within timeout → rejected."""
        d = _bare_device()
        d._dirty_data[_BATTERY_DID] = DirtyData(value=90, update_time=time.time())
        result = d._handle_properties([_prop(_BATTERY_DID, 85)])
        # Value 85 must NOT be stored — the echo was discarded
        assert _BATTERY_DID not in d.data
        # dirty entry removed after discard
        assert _BATTERY_DID not in d._dirty_data
        assert result is False

    def test_matching_value_accepted_dirty_cleared(self) -> None:
        """Incoming value matches dirty sentinel → accepted, dirty cleared."""
        d = _bare_device()
        d._dirty_data[_BATTERY_DID] = DirtyData(value=85, update_time=time.time())
        result = d._handle_properties([_prop(_BATTERY_DID, 85)])
        assert d.data[_BATTERY_DID] == 85
        assert _BATTERY_DID not in d._dirty_data
        # First write → changed
        assert result is True

    def test_expired_window_accepted(self) -> None:
        """Dirty entry outside discard window → incoming value accepted."""
        d = _bare_device()
        d._dirty_data[_BATTERY_DID] = DirtyData(value=90, update_time=time.time() - 10)
        result = d._handle_properties([_prop(_BATTERY_DID, 85)])
        assert d.data[_BATTERY_DID] == 85
        assert _BATTERY_DID not in d._dirty_data
        assert result is True

    def test_update_time_none_treated_as_expired(self) -> None:
        """update_time=None → (None or 0) == 0 → window expired → value accepted."""
        d = _bare_device()
        d._dirty_data[_BATTERY_DID] = DirtyData(value=90, update_time=None)
        result = d._handle_properties([_prop(_BATTERY_DID, 85)])
        # time.time() - 0 is a large positive number > _discard_timeout=2 → accepted
        assert d.data[_BATTERY_DID] == 85
        assert _BATTERY_DID not in d._dirty_data
        assert result is True


# ===========================================================================
# Étape 4 : _handle_properties — callbacks
# ===========================================================================


class TestHandlePropertiesCallbacks:
    """Callback dispatch."""

    def test_callback_called_with_old_value(self) -> None:
        """Registered callback receives the previous (old) value.

        On first insertion d.data has no entry → current_value is None.
        """
        d = _bare_device()
        cb = MagicMock()
        d._property_update_callback[_BATTERY_DID] = [cb]
        d._handle_properties([_prop(_BATTERY_DID, 85)])
        cb.assert_called_once_with(None)

    def test_callback_called_with_previous_value_on_update(self) -> None:
        """On update, callback receives the value that was stored before the change."""
        d = _bare_device()
        d.data[_BATTERY_DID] = 80
        cb = MagicMock()
        d._property_update_callback[_BATTERY_DID] = [cb]
        d._handle_properties([_prop(_BATTERY_DID, 90)])
        cb.assert_called_once_with(80)

    def test_callback_not_called_when_no_change(self) -> None:
        """No change → callback not invoked."""
        d = _bare_device()
        d.data[_BATTERY_DID] = 85
        cb = MagicMock()
        d._property_update_callback[_BATTERY_DID] = [cb]
        d._handle_properties([_prop(_BATTERY_DID, 85)])
        cb.assert_not_called()

    def test_two_callbacks_both_called(self) -> None:
        """Two callbacks registered for same did → both invoked."""
        d = _bare_device()
        cb1 = MagicMock()
        cb2 = MagicMock()
        d._property_update_callback[_BATTERY_DID] = [cb1, cb2]
        d._handle_properties([_prop(_BATTERY_DID, 77)])
        cb1.assert_called_once_with(None)
        cb2.assert_called_once_with(None)


# ===========================================================================
# Étape 5 : _message_callback — routing
# ===========================================================================


class TestMessageCallbackRouting:
    """_message_callback routing and guards."""

    def test_not_ready_returns_immediately(self) -> None:
        """_ready=False → early return, nothing mutated."""
        d = _bare_device_with_message_support()
        d._ready = False
        msg = {
            "method": "properties_changed",
            "params": [{"siid": _BATTERY_SIID, "piid": _BATTERY_PIID, "code": 0, "value": 50}],
        }
        d._message_callback(msg)
        assert d.available is False
        assert d.data == {}

    def test_properties_changed_updates_data_and_available(self) -> None:
        """properties_changed with known siid/piid → available=True, data updated."""
        d = _bare_device_with_message_support()
        msg = {
            "method": "properties_changed",
            "params": [{"siid": _BATTERY_SIID, "piid": _BATTERY_PIID, "code": 0, "value": 72}],
        }
        d._message_callback(msg)
        assert d.available is True
        assert d.data[_BATTERY_DID] == 72

    def test_map_property_no_map_manager_no_crash(self) -> None:
        """Map property (OBJECT_NAME) with _map_manager=None → no exception."""
        d = _bare_device_with_message_support()
        # OBJECT_NAME siid=6 piid=3, not in _default_properties → map_properties path
        msg = {
            "method": "properties_changed",
            "params": [{"siid": 6, "piid": 3, "code": 0, "value": "mapdata"}],
        }
        # Should not raise
        d._message_callback(msg)
        assert d.available is True

    def test_message_without_method_or_params_ignored(self) -> None:
        """Message missing method/params keys → silently ignored."""
        d = _bare_device_with_message_support()
        d._message_callback({"method": "properties_changed"})  # no params
        assert d.available is False
        d._message_callback({"params": []})  # no method
        assert d.available is False
        d._message_callback({})
        assert d.available is False
