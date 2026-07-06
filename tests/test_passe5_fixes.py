"""Non-regression tests for Passe 5 (latent findings) fixes.

All behavioural: U1 (device_map_ops go-to-zone cleaning-mode swap), U4
(map_decoder), U5/U6 (map_manager frame-id guard / recovery sort), U14
(entity device_info), U15 (device), U16 (device_info repr), U18 (PII not
logged) each drive the real production code path.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# --- U1: no invalid DreameVacuumCleaningMode member reference ----------------


def test_u1_cleaning_mode_enum_references_are_valid() -> None:
    """device_map_ops's go-to-zone cleaning-mode swap must resolve every
    DreameVacuumCleaningMode member it references (MOPPING/SWEEPING/
    SWEEPING_AND_MOPPING), not silently AttributeError on a typo'd name."""
    from custom_components.dreame_vacuum.dreame.vacuum_types import DreameVacuumCleaningMode
    from tests.test_device_map_ops import _area, _base_map_data, _dims, _MapOpsHost

    host = _MapOpsHost()
    host.status.started = True
    host.status.go_to_zone = None
    host.status.zone_cleaning = True
    host.status._capability.cruising = False
    host.capability.self_wash_base = False
    host.capability.mop_pad_lifting = False
    host.status.cleaning_mode = DreameVacuumCleaningMode.MOPPING
    host.status.water_tank_or_mop_installed = False
    host.status.docked = False
    host.status.robot_position = None
    area = _area(0, 0, 100, 100)
    host.status.current_map = _base_map_data(dimensions=_dims(grid_size=50), active_areas=[area], robot_position=None)

    host._map_changed(saved_map=False)

    assert host.status.go_to_zone.cleaning_mode == DreameVacuumCleaningMode.SWEEPING.value


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
    import json

    from custom_components.dreame_vacuum.dreame.map_manager import DreameMapVacuumMapManager

    protocol = MagicMock()
    protocol.dreame_cloud = False
    protocol.cloud = MagicMock(dreame_cloud=False, logged_in=True, connected=True)
    manager = DreameMapVacuumMapManager(protocol)
    manager._recovery_map_list_object_name = "recovery_obj"
    manager._map_list = [1]
    manager._connected = True
    saved = MagicMock(recovery_map_list=None)
    manager._saved_map_data = {1: saved}
    manager._get_file_url = MagicMock(return_value="http://recovery")
    payload = [
        {
            "id": 1,
            "info": [
                {"time": 1, "objname": "o1", "first": 1},  # ORIGINAL (map_type=1)
                {"time": 2, "objname": "o2", "first": 2},  # BACKUP (map_type=2)
                {"time": 3, "objname": "o3", "first": 0},  # EDITED (map_type=0)
            ],
        }
    ]
    manager._protocol.cloud.get_file = MagicMock(return_value=json.dumps(payload).encode())

    manager.request_recovery_map_list()

    # A comparator only handling the (0, 2) pair would leave map_type=1 unordered.
    assert [int(entry.map_type) for entry in saved.recovery_map_list] == [0, 1, 2]


# --- U5: duplicated frame-id clause removed ----------------------------------


def test_u5_no_duplicated_frame_id_clause() -> None:
    """The optimistic-edit carry-over guard must check _map_data is not None, not
    duplicate the _current_frame_id check (which would let a None _map_data slip
    through and crash on `self._map_data.empty_map`)."""
    from unittest.mock import patch

    from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
    from custom_components.dreame_vacuum.dreame.map_manager import DreameMapVacuumMapManager
    from custom_components.dreame_vacuum.dreame.vacuum_types import MapData, MapDataPartial, MapFrameType

    protocol = MagicMock()
    protocol.dreame_cloud = False
    protocol.cloud = MagicMock(dreame_cloud=False, logged_in=True, connected=True)
    manager = DreameMapVacuumMapManager(protocol)
    manager._change_callback = MagicMock()
    manager._update_callback = MagicMock()

    manager._latest_map_id = 1
    manager._current_map_id = 1
    manager._current_frame_id = 5
    manager._current_timestamp_ms = 1000
    manager._updated_frame_id = 6
    manager._map_data = None  # the case the duplicated clause fails to guard against

    partial = MapDataPartial()
    partial.map_id = 1
    partial.frame_id = 7  # <= updated_frame_id(6) + 1 -> within the carry-over window
    partial.frame_type = MapFrameType.I.value
    partial.timestamp_ms = 2000

    new_map = MapData()
    new_map.map_id = 1
    new_map.frame_id = 7
    new_map.timestamp_ms = 2000

    with patch.object(DreameVacuumMapDecoder, "decode_map_data_from_partial", return_value=(new_map, None)):
        result = manager._add_map_data(partial)  # must not raise AttributeError

    assert result is True


# --- U14: device_info links on mac, returns None only without mac ------------


def test_u14_device_info_guards_on_mac() -> None:
    """device_info must return None when the device has no mac, not crash or link
    a phantom device."""
    from custom_components.dreame_vacuum.entity import DreameVacuumEntity

    entity = object.__new__(DreameVacuumEntity)
    entity.coordinator = MagicMock()
    entity.coordinator.device.mac = ""

    assert entity.device_info is None


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


def test_u18_otc_info_message_redacts_pii_from_logs(caplog: pytest.LogCaptureFixture) -> None:
    """_otc.info messages carry the device token/localIp/bssid; the debug log must
    never include the raw payload, only a redacted marker."""
    import logging

    from custom_components.dreame_vacuum.dreame.device import DreameVacuumDevice

    device = object.__new__(DreameVacuumDevice)
    device._ready = True
    device.info = None
    device._last_change = 0.0
    device._property_changed = MagicMock()

    secret_token = "TOP-SECRET-DEVICE-TOKEN"
    message = {"method": "_otc.info", "params": {"token": secret_token, "localIp": "10.0.0.5", "bssid": "AA:BB"}}

    with caplog.at_level(logging.DEBUG, logger="custom_components.dreame_vacuum.dreame.device"):
        device._message_callback(message)

    assert secret_token not in caplog.text
    assert "10.0.0.5" not in caplog.text
    assert "redacted" in caplog.text


def test_u18_login_failure_does_not_log_raw_response_body(caplog: pytest.LogCaptureFixture) -> None:
    """A failed login must log only the HTTP status, never the raw response body
    (which can echo back credentials / secrets from the server)."""
    import logging

    from custom_components.dreame_vacuum.dreame.protocol import DreameVacuumDreameHomeCloudProtocol

    proto: DreameVacuumDreameHomeCloudProtocol = object.__new__(DreameVacuumDreameHomeCloudProtocol)
    proto._strings = [str(i) for i in range(60)]
    proto._secondary_key = "tok"
    proto._key = None
    proto._ti = None
    proto._country = "de"
    proto._username = "user@example.com"
    proto._password = "TOP-SECRET-PASSWORD"
    proto._timeout_config = MagicMock()
    proto._circuit_breaker = MagicMock()
    proto._session = MagicMock()
    proto._session.close_session = MagicMock()
    secret_body = "TOP-SECRET-PASSWORD-ECHOED-BACK"
    proto._session.post.return_value = MagicMock(status=401, text=secret_body)

    with caplog.at_level(logging.DEBUG, logger="custom_components.dreame_vacuum.dreame.protocol"):
        result = proto.login()

    assert result is False
    assert secret_body not in caplog.text
