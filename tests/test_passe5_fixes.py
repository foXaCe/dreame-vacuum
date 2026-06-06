"""Non-regression tests for Passe 5 (latent findings) fixes.

Behavioural where modules import without native deps (U4 map_decoder, U15 device,
U16 device_info); source guards where the module is not importable in CI
(U14 entity -> turbojpeg) or a behavioural setup would be disproportionate
(U1, U5, U6, U18).
"""

from __future__ import annotations

import pathlib
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.dreame_vacuum.dreame.vacuum_types import DreameVacuumCleaningMode

_CC = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "dreame_vacuum"


# --- U1: no invalid DreameVacuumCleaningMode member reference ----------------


def test_u1_cleaning_mode_enum_references_are_valid() -> None:
    """device_map_ops must only reference real DreameVacuumCleaningMode members."""
    src = (_CC / "dreame" / "device_map_ops.py").read_text()
    referenced = set(re.findall(r"DreameVacuumCleaningMode\.([A-Z_]+)", src))
    invalid = referenced - set(DreameVacuumCleaningMode.__members__)
    assert not invalid, f"références d'enum invalides: {invalid}"


# --- U4: set_carpet_cleanset must tolerate capability=None -------------------


def test_u4_set_carpet_cleanset_handles_none_capability() -> None:
    """capability=None with no carpets must not raise AttributeError."""
    from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
    from custom_components.dreame_vacuum.dreame.vacuum_types import MapData

    map_data = MapData()
    map_data.detected_carpets = None
    map_data.carpets = None

    # Before the fix this raised AttributeError on capability.carpet_material.
    DreameVacuumMapDecoder.set_carpet_cleanset(map_data, [[2, 1]], None)


# --- U6: recovery-map sort comparator must order by map_type -----------------


def test_u6_recovery_map_comparator_no_longer_broken() -> None:
    """The comparator must compare map_type generically, not only the (0, 2) pair."""
    src = (_CC / "dreame" / "map_manager.py").read_text()
    assert "int(a.map_type == 0) and int(b.map_type == 2)" not in src
    assert "if a.map_type != b.map_type" in src


# --- U5: duplicated frame-id clause removed ----------------------------------


def test_u5_no_duplicated_frame_id_clause() -> None:
    src = (_CC / "dreame" / "map_manager.py").read_text()
    assert "self._current_frame_id is not None\n            and self._current_frame_id is not None" not in src


# --- U14: device_info links on mac, returns None only without mac ------------


def test_u14_device_info_guards_on_mac() -> None:
    """entity.py is not importable in CI (turbojpeg); guard the fix at source level."""
    src = (_CC / "entity.py").read_text()
    assert "if not self.device.mac:" in src


# --- U15: _request_properties must break on a persistent None ----------------


def test_u15_request_properties_breaks_on_persistent_none() -> None:
    """A protocol returning None must not busy-loop a worker thread."""
    from custom_components.dreame_vacuum.dreame.device import DreameVacuumDevice
    from custom_components.dreame_vacuum.dreame.vacuum_types import DreameVacuumProperty

    device: DreameVacuumDevice = object.__new__(DreameVacuumDevice)
    prop = DreameVacuumProperty.BATTERY_LEVEL
    device.property_mapping = {prop: {"siid": 1, "piid": 1}}
    device.data = {}
    device._ready = True
    device._protocol = SimpleNamespace(get_properties=MagicMock(return_value=None))
    device._handle_properties = MagicMock(return_value=False)

    device._request_properties([prop], force_all=True)

    assert device._protocol.get_properties.call_count == 1  # broke out instead of spinning
    device._handle_properties.assert_called_once()


# --- U16: DeviceInfo.__repr__ must not raise ---------------------------------


def test_u16_device_info_repr_does_not_raise() -> None:
    """__repr__ referenced non-existent self.mac/self.token -> AttributeError."""
    from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo

    assert isinstance(repr(DreameVacuumDeviceInfo({})), str)
    assert isinstance(
        repr(DreameVacuumDeviceInfo({"model": "dreame.vacuum.x", "fw_ver": "a_42", "mac": "AA:BB"})),
        str,
    )


# --- U18: PII / credentials must not be logged --------------------------------


def test_u18_sensitive_payloads_not_logged() -> None:
    device_src = (_CC / "dreame" / "device.py").read_text()
    assert "_otc.info (params redacted)" in device_src
    protocol_src = (_CC / "dreame" / "protocol.py").read_text()
    assert "Login failure body" not in protocol_src
    assert "2FA failure body" not in protocol_src
