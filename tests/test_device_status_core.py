"""Tests for _core.py, _consumables.py and _station.py of DreameVacuumDeviceStatus.

These tests build a ``DreameVacuumDeviceStatus`` backed by a fully controlled
``MagicMock`` device (property map, auto-switch map, AI-property map) and a real
``DreameVacuumDeviceCapability`` instance (whose ``__init__`` only sets plain
False/default attributes without touching the device), so every capability flag
used by a branch can be flipped precisely instead of relying on MagicMock auto-truthiness.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.dreame_vacuum.dreame.const import (
    AUTO_EMPTY_MODE_TO_NAME,
    AUTO_EMPTY_STATUS_TO_NAME,
    CARPET_CLEANING_CODE_TO_NAME,
    CARPET_SENSITIVITY_CODE_TO_NAME,
    CHARGING_STATUS_CODE_TO_NAME,
    CLEAN_WATER_TANK_STATUS_TO_NAME,
    CLEANGENIUS_MODE_TO_NAME,
    CLEANGENIUS_TO_NAME,
    CLEANING_MODE_CODE_TO_NAME,
    CLEANING_ROUTE_TO_NAME,
    CUSTOM_MOPPING_ROUTE_TO_NAME,
    DETERGENT_STATUS_TO_NAME,
    DIRTY_WATER_TANK_STATUS_TO_NAME,
    DRAINAGE_STATUS_TO_NAME,
    DUST_BAG_STATUS_TO_NAME,
    DUST_COLLECTION_TO_NAME,
    ERROR_CODE_TO_ERROR_NAME,
    HOT_WATER_STATUS_TO_NAME,
    LOW_WATER_WARNING_TO_NAME,
    MOP_CLEAN_FREQUENCY_TO_NAME,
    MOP_EXTEND_FREQUENCY_TO_NAME,
    MOP_PAD_SWING_TO_NAME,
    MOP_WASH_LEVEL_TO_NAME,
    MOPPING_TYPE_TO_NAME,
    RELOCATION_STATUS_CODE_TO_NAME,
    SECOND_CLEANING_TO_NAME,
    SELF_CLEAN_FREQUENCY_TO_NAME,
    SELF_WASH_BASE_STATUS_TO_NAME,
    STATE_CODE_TO_STATE,
    STATE_UNKNOWN,
    STATION_DRAINAGE_STATUS_TO_NAME,
    STATUS_CODE_TO_NAME,
    SUCTION_LEVEL_CODE_TO_NAME,
    TASK_STATUS_CODE_TO_NAME,
    TASK_TYPE_TO_NAME,
    VOICE_ASSISTANT_LANGUAGE_TO_NAME,
    WASHING_MODE_TO_NAME,
    WATER_TANK_CODE_TO_NAME,
    WATER_TEMPERATURE_TO_NAME,
    WATER_VOLUME_CODE_TO_NAME,
    WIDER_CORNER_COVERAGE_TO_NAME,
)
from custom_components.dreame_vacuum.dreame.device_status import DreameVacuumDeviceStatus
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    DreameVacuumAIProperty,
    DreameVacuumAutoEmptyMode,
    DreameVacuumAutoEmptyStatus,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumCarpetCleaning,
    DreameVacuumCarpetSensitivity,
    DreameVacuumChargingStatus,
    DreameVacuumCleanGenius,
    DreameVacuumCleanGeniusMode,
    DreameVacuumCleaningMode,
    DreameVacuumCleaningRoute,
    DreameVacuumCleanWaterTankStatus,
    DreameVacuumCustomMoppingRoute,
    DreameVacuumDetergentStatus,
    DreameVacuumDeviceCapability,
    DreameVacuumDirtyWaterTankStatus,
    DreameVacuumDrainageStatus,
    DreameVacuumDustBagStatus,
    DreameVacuumDustCollection,
    DreameVacuumErrorCode,
    DreameVacuumHotWaterStatus,
    DreameVacuumLowWaterWarning,
    DreameVacuumMopCleanFrequency,
    DreameVacuumMopExtendFrequency,
    DreameVacuumMopPadHumidity,
    DreameVacuumMopPadSwing,
    DreameVacuumMoppingType,
    DreameVacuumMopWashLevel,
    DreameVacuumProperty,
    DreameVacuumRelocationStatus,
    DreameVacuumSecondCleaning,
    DreameVacuumSelfCleanFrequency,
    DreameVacuumSelfWashBaseStatus,
    DreameVacuumState,
    DreameVacuumStateOld,
    DreameVacuumStationDrainageStatus,
    DreameVacuumStatus,
    DreameVacuumSuctionLevel,
    DreameVacuumTaskStatus,
    DreameVacuumTaskType,
    DreameVacuumVoiceAssistantLanguage,
    DreameVacuumWashingMode,
    DreameVacuumWaterTank,
    DreameVacuumWaterTemperature,
    DreameVacuumWaterVolume,
    DreameVacuumWiderCornerCoverage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_capability(**overrides: Any) -> DreameVacuumDeviceCapability:
    """Build a capability object with deterministic (mostly False) default flags.

    ``DreameVacuumDeviceCapability.__init__`` only assigns plain attributes; it never
    touches the device passed to it. Constructing it directly (without calling
    ``load()``) therefore gives a safe, fully-known baseline that individual tests
    can selectively override, instead of relying on an auto-truthy ``MagicMock``.
    """
    capability = DreameVacuumDeviceCapability(MagicMock())
    for key, value in overrides.items():
        setattr(capability, key, value)
    return capability


def _make_status(
    properties: dict[Any, Any] | None = None,
    *,
    capability: DreameVacuumDeviceCapability | None = None,
    auto_switch_properties: dict[Any, Any] | None = None,
    ai_properties: dict[Any, Any] | None = None,
    device_connected: bool = True,
) -> DreameVacuumDeviceStatus:
    """Build a DreameVacuumDeviceStatus backed by fully controlled device mocks."""
    props = properties or {}
    switch_props = auto_switch_properties or {}
    ai_props = ai_properties or {}

    device = MagicMock()
    device.get_property = MagicMock(side_effect=lambda prop: props.get(prop))
    device.get_auto_switch_property = MagicMock(side_effect=lambda prop: switch_props.get(prop))
    device.get_ai_property = MagicMock(side_effect=lambda prop: ai_props.get(prop))
    device.capability = capability if capability is not None else _make_capability()
    device.device_connected = device_connected
    # Deterministic: no map manager means current_map/has_saved_map/etc. resolve predictably.
    device._map_manager = None

    return DreameVacuumDeviceStatus(device)


def _not_started_properties(extra: dict[Any, Any] | None = None) -> dict[Any, Any]:
    """Property map that makes ``status.started`` resolve to False."""
    props: dict[Any, Any] = {DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.COMPLETED.value}
    if extra:
        props.update(extra)
    return props


# ---------------------------------------------------------------------------
# _consumables.py - _ConsumablesMixin
# ---------------------------------------------------------------------------

CONSUMABLE_CASES = [
    ("main_brush_life", DreameVacuumProperty.MAIN_BRUSH_LEFT),
    ("side_brush_life", DreameVacuumProperty.SIDE_BRUSH_LEFT),
    ("filter_life", DreameVacuumProperty.FILTER_LEFT),
    ("sensor_dirty_life", DreameVacuumProperty.SENSOR_DIRTY_LEFT),
    ("tank_filter_life", DreameVacuumProperty.TANK_FILTER_LEFT),
    ("mop_life", DreameVacuumProperty.MOP_PAD_LEFT),
    ("silver_ion_life", DreameVacuumProperty.SILVER_ION_LEFT),
    ("detergent_life", DreameVacuumProperty.DETERGENT_LEFT),
    ("squeegee_life", DreameVacuumProperty.SQUEEGEE_LEFT),
    ("onboard_dirty_water_tank_life", DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_LEFT),
    ("dirty_water_tank_life", DreameVacuumProperty.DIRTY_WATER_TANK_LEFT),
    ("deodorizer_life", DreameVacuumProperty.DEODORIZER_LEFT),
    ("wheel_dirty_life", DreameVacuumProperty.WHEEL_DIRTY_LEFT),
    ("scale_inhibitor_life", DreameVacuumProperty.SCALE_INHIBITOR_LEFT),
]


@pytest.mark.parametrize(("attr", "prop"), CONSUMABLE_CASES)
def test_consumable_life_passthrough(attr: str, prop: DreameVacuumProperty) -> None:
    """Every *_life property is a thin int passthrough of its *_LEFT property."""
    status = _make_status({prop: 42})
    assert getattr(status, attr) == 42


@pytest.mark.parametrize(("attr", "prop"), CONSUMABLE_CASES)
def test_consumable_life_zero(attr: str, prop: DreameVacuumProperty) -> None:
    status = _make_status({prop: 0})
    assert getattr(status, attr) == 0


@pytest.mark.parametrize(("attr", "prop"), CONSUMABLE_CASES)
def test_consumable_life_missing_is_none(attr: str, prop: DreameVacuumProperty) -> None:
    status = _make_status({})
    assert getattr(status, attr) is None


# ---------------------------------------------------------------------------
# _station.py - _StationMixin
# ---------------------------------------------------------------------------

STATION_CASES = [
    (
        "dirty_water_tank_status",
        "dirty_water_tank_status_name",
        DreameVacuumProperty.DIRTY_WATER_TANK_STATUS,
        DreameVacuumDirtyWaterTankStatus,
        DreameVacuumDirtyWaterTankStatus.NOT_INSTALLED_OR_FULL,
        DIRTY_WATER_TANK_STATUS_TO_NAME,
    ),
    (
        "dust_bag_status",
        "dust_bag_status_name",
        DreameVacuumProperty.DUST_BAG_STATUS,
        DreameVacuumDustBagStatus,
        DreameVacuumDustBagStatus.CHECK,
        DUST_BAG_STATUS_TO_NAME,
    ),
    (
        "detergent_status",
        "detergent_status_name",
        DreameVacuumProperty.DETERGENT_STATUS,
        DreameVacuumDetergentStatus,
        DreameVacuumDetergentStatus.LOW_DETERGENT,
        DETERGENT_STATUS_TO_NAME,
    ),
    (
        "hot_water_status",
        "hot_water_status_name",
        DreameVacuumProperty.HOT_WATER_STATUS,
        DreameVacuumHotWaterStatus,
        DreameVacuumHotWaterStatus.ENABLED,
        HOT_WATER_STATUS_TO_NAME,
    ),
]


@pytest.mark.parametrize(("attr", "name_attr", "prop", "enum_cls", "valid_value", "to_name"), STATION_CASES)
def test_station_status_valid_value(
    attr: str,
    name_attr: str,
    prop: DreameVacuumProperty,
    enum_cls: Any,
    valid_value: Any,
    to_name: dict[Any, str],
) -> None:
    status = _make_status({prop: valid_value.value})
    assert getattr(status, attr) == valid_value
    assert getattr(status, name_attr) == to_name[valid_value]


@pytest.mark.parametrize(("attr", "name_attr", "prop", "enum_cls", "valid_value", "to_name"), STATION_CASES)
def test_station_status_invalid_value_is_unknown(
    attr: str,
    name_attr: str,
    prop: DreameVacuumProperty,
    enum_cls: Any,
    valid_value: Any,
    to_name: dict[Any, str],
) -> None:
    status = _make_status({prop: 9999})
    assert getattr(status, attr) == enum_cls.UNKNOWN
    assert getattr(status, name_attr) == to_name.get(enum_cls.UNKNOWN, STATE_UNKNOWN)


@pytest.mark.parametrize(("attr", "name_attr", "prop", "enum_cls", "valid_value", "to_name"), STATION_CASES)
def test_station_status_missing_is_unknown(
    attr: str,
    name_attr: str,
    prop: DreameVacuumProperty,
    enum_cls: Any,
    valid_value: Any,
    to_name: dict[Any, str],
) -> None:
    status = _make_status({})
    assert getattr(status, attr) == enum_cls.UNKNOWN


def test_clean_water_tank_status_active_remaps_to_installed() -> None:
    """Raw ACTIVE value is deliberately remapped to INSTALLED (a station.py special case)."""
    status = _make_status({DreameVacuumProperty.CLEAN_WATER_TANK_STATUS: DreameVacuumCleanWaterTankStatus.ACTIVE.value})
    assert status.clean_water_tank_status == DreameVacuumCleanWaterTankStatus.INSTALLED
    assert (
        status.clean_water_tank_status_name
        == CLEAN_WATER_TANK_STATUS_TO_NAME[DreameVacuumCleanWaterTankStatus.INSTALLED]
    )


def test_clean_water_tank_status_not_installed_untouched() -> None:
    status = _make_status(
        {DreameVacuumProperty.CLEAN_WATER_TANK_STATUS: DreameVacuumCleanWaterTankStatus.NOT_INSTALLED.value}
    )
    assert status.clean_water_tank_status == DreameVacuumCleanWaterTankStatus.NOT_INSTALLED
    assert status.clean_water_tank_status_name == "not_installed"


def test_clean_water_tank_status_low_water() -> None:
    status = _make_status(
        {DreameVacuumProperty.CLEAN_WATER_TANK_STATUS: DreameVacuumCleanWaterTankStatus.LOW_WATER.value}
    )
    assert status.clean_water_tank_status == DreameVacuumCleanWaterTankStatus.LOW_WATER
    assert status.clean_water_tank_status_name == "low_water"


def test_clean_water_tank_status_missing_is_unknown() -> None:
    status = _make_status({})
    assert status.clean_water_tank_status == DreameVacuumCleanWaterTankStatus.UNKNOWN


# ---------------------------------------------------------------------------
# _core.py - plain "_value2member_map_" enum properties (no capability gate)
# ---------------------------------------------------------------------------

PLAIN_ENUM_CASES = [
    (
        "auto_empty_status",
        "auto_empty_status_name",
        DreameVacuumProperty.AUTO_EMPTY_STATUS,
        DreameVacuumAutoEmptyStatus,
        DreameVacuumAutoEmptyStatus.ACTIVE,
        AUTO_EMPTY_STATUS_TO_NAME,
    ),
    (
        "relocation_status",
        "relocation_status_name",
        DreameVacuumProperty.RELOCATION_STATUS,
        DreameVacuumRelocationStatus,
        DreameVacuumRelocationStatus.LOCATING,
        RELOCATION_STATUS_CODE_TO_NAME,
    ),
    (
        "self_wash_base_status",
        "self_wash_base_status_name",
        DreameVacuumProperty.SELF_WASH_BASE_STATUS,
        DreameVacuumSelfWashBaseStatus,
        DreameVacuumSelfWashBaseStatus.WASHING,
        SELF_WASH_BASE_STATUS_TO_NAME,
    ),
    (
        "dust_collection",
        "dust_collection_name",
        DreameVacuumProperty.DUST_COLLECTION,
        DreameVacuumDustCollection,
        DreameVacuumDustCollection.AVAILABLE,
        DUST_COLLECTION_TO_NAME,
    ),
    (
        "carpet_sensitivity",
        "carpet_sensitivity_name",
        DreameVacuumProperty.CARPET_SENSITIVITY,
        DreameVacuumCarpetSensitivity,
        DreameVacuumCarpetSensitivity.MEDIUM,
        CARPET_SENSITIVITY_CODE_TO_NAME,
    ),
    (
        "station_drainage_status",
        "station_drainage_status_name",
        DreameVacuumProperty.STATION_DRAINAGE_STATUS,
        DreameVacuumStationDrainageStatus,
        DreameVacuumStationDrainageStatus.DRAINING,
        STATION_DRAINAGE_STATUS_TO_NAME,
    ),
    (
        "task_type",
        "task_type_name",
        DreameVacuumProperty.TASK_TYPE,
        DreameVacuumTaskType,
        DreameVacuumTaskType.CUSTOM,
        TASK_TYPE_TO_NAME,
    ),
    (
        "low_water_warning",
        "low_water_warning_name",
        DreameVacuumProperty.LOW_WATER_WARNING,
        DreameVacuumLowWaterWarning,
        DreameVacuumLowWaterWarning.LOW_WATER,
        LOW_WATER_WARNING_TO_NAME,
    ),
    (
        "suction_level",
        "suction_level_name",
        DreameVacuumProperty.SUCTION_LEVEL,
        DreameVacuumSuctionLevel,
        DreameVacuumSuctionLevel.TURBO,
        SUCTION_LEVEL_CODE_TO_NAME,
    ),
]


@pytest.mark.parametrize(("attr", "name_attr", "prop", "enum_cls", "valid_value", "to_name"), PLAIN_ENUM_CASES)
def test_plain_enum_valid_value(
    attr: str, name_attr: str, prop: DreameVacuumProperty, enum_cls: Any, valid_value: Any, to_name: dict[Any, str]
) -> None:
    status = _make_status({prop: valid_value.value})
    assert getattr(status, attr) == valid_value
    assert getattr(status, name_attr) == to_name[valid_value]


@pytest.mark.parametrize(("attr", "name_attr", "prop", "enum_cls", "valid_value", "to_name"), PLAIN_ENUM_CASES)
def test_plain_enum_invalid_value_is_unknown(
    attr: str, name_attr: str, prop: DreameVacuumProperty, enum_cls: Any, valid_value: Any, to_name: dict[Any, str]
) -> None:
    status = _make_status({prop: 987654})
    assert getattr(status, attr) == enum_cls.UNKNOWN
    assert getattr(status, name_attr) == to_name.get(enum_cls.UNKNOWN, STATE_UNKNOWN)


@pytest.mark.parametrize(("attr", "name_attr", "prop", "enum_cls", "valid_value", "to_name"), PLAIN_ENUM_CASES)
def test_plain_enum_missing_is_unknown(
    attr: str, name_attr: str, prop: DreameVacuumProperty, enum_cls: Any, valid_value: Any, to_name: dict[Any, str]
) -> None:
    status = _make_status({})
    assert getattr(status, attr) == enum_cls.UNKNOWN


# ---------------------------------------------------------------------------
# voice_assistant_language - StrEnum with a DEFAULT (not UNKNOWN) fallback
# ---------------------------------------------------------------------------


def test_voice_assistant_language_valid() -> None:
    status = _make_status({DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE: "EN"})
    assert status.voice_assistant_language == DreameVacuumVoiceAssistantLanguage.ENGLISH
    assert (
        status.voice_assistant_language_name
        == VOICE_ASSISTANT_LANGUAGE_TO_NAME[DreameVacuumVoiceAssistantLanguage.ENGLISH]
    )


def test_voice_assistant_language_invalid_falls_back_to_default() -> None:
    status = _make_status({DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE: "XX"})
    assert status.voice_assistant_language == DreameVacuumVoiceAssistantLanguage.DEFAULT


def test_voice_assistant_language_missing_falls_back_to_default() -> None:
    status = _make_status({})
    assert status.voice_assistant_language == DreameVacuumVoiceAssistantLanguage.DEFAULT
    assert status.voice_assistant_language_name == "default"


# ---------------------------------------------------------------------------
# water_tank - special-cased raw values
# ---------------------------------------------------------------------------


def test_water_tank_not_installed() -> None:
    status = _make_status({DreameVacuumProperty.WATER_TANK: 0})
    assert status.water_tank == DreameVacuumWaterTank.NOT_INSTALLED


def test_water_tank_installed_via_enum_map() -> None:
    status = _make_status({DreameVacuumProperty.WATER_TANK: 1})
    assert status.water_tank == DreameVacuumWaterTank.INSTALLED


def test_water_tank_installed_via_raw_three_special_case() -> None:
    """Raw value 3 is not a real enum member; it is force-mapped to INSTALLED."""
    status = _make_status({DreameVacuumProperty.WATER_TANK: 3})
    assert status.water_tank == DreameVacuumWaterTank.INSTALLED
    assert 3 not in DreameVacuumWaterTank._value2member_map_


def test_water_tank_mop_installed_via_raw_two_special_case() -> None:
    status = _make_status({DreameVacuumProperty.WATER_TANK: 2})
    assert status.water_tank == DreameVacuumWaterTank.MOP_INSTALLED


def test_water_tank_mop_installed_via_enum_map() -> None:
    status = _make_status({DreameVacuumProperty.WATER_TANK: 10})
    assert status.water_tank == DreameVacuumWaterTank.MOP_INSTALLED


def test_water_tank_mop_in_station_overrides_raw_value() -> None:
    """When mop_in_station is true, water_tank reports MOP_IN_STATION regardless of raw value."""
    status = _make_status(
        _not_started_properties(
            {
                DreameVacuumProperty.WATER_TANK: 1,
                DreameVacuumProperty.MOP_IN_STATION: 1,
            }
        )
    )
    assert status.mop_in_station is True
    assert status.water_tank == DreameVacuumWaterTank.MOP_IN_STATION


def test_water_tank_name_uses_code_to_name_dict() -> None:
    status = _make_status({DreameVacuumProperty.WATER_TANK: 1})
    assert status.water_tank_name == WATER_TANK_CODE_TO_NAME[DreameVacuumWaterTank.INSTALLED]
    assert status.mop_pad_name == status.water_tank_name


# ---------------------------------------------------------------------------
# charging_status - CHARGING remapped to CHARGING_COMPLETED at battery 100
# ---------------------------------------------------------------------------


def test_charging_status_charging_below_full_battery() -> None:
    status = _make_status(
        {
            DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.CHARGING.value,
            DreameVacuumProperty.BATTERY_LEVEL: 55,
        }
    )
    assert status.charging_status == DreameVacuumChargingStatus.CHARGING


def test_charging_status_charging_at_full_battery_becomes_completed() -> None:
    status = _make_status(
        {
            DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.CHARGING.value,
            DreameVacuumProperty.BATTERY_LEVEL: 100,
        }
    )
    assert status.charging_status == DreameVacuumChargingStatus.CHARGING_COMPLETED
    assert status.charging_status_name == CHARGING_STATUS_CODE_TO_NAME[DreameVacuumChargingStatus.CHARGING_COMPLETED]


def test_charging_status_not_charging_untouched_at_full_battery() -> None:
    status = _make_status(
        {
            DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.NOT_CHARGING.value,
            DreameVacuumProperty.BATTERY_LEVEL: 100,
        }
    )
    assert status.charging_status == DreameVacuumChargingStatus.NOT_CHARGING


def test_charging_status_return_to_charge() -> None:
    status = _make_status({DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.RETURN_TO_CHARGE.value})
    assert status.charging_status == DreameVacuumChargingStatus.RETURN_TO_CHARGE


def test_charging_status_missing_is_unknown() -> None:
    status = _make_status({})
    assert status.charging_status == DreameVacuumChargingStatus.UNKNOWN


# ---------------------------------------------------------------------------
# status / task_status - go_to_zone and charging special cases
# ---------------------------------------------------------------------------


def test_status_zone_cleaning_without_go_to_zone() -> None:
    status = _make_status({DreameVacuumProperty.STATUS: DreameVacuumStatus.ZONE_CLEANING.value})
    assert status.status == DreameVacuumStatus.ZONE_CLEANING
    assert status.status_name == STATUS_CODE_TO_NAME[DreameVacuumStatus.ZONE_CLEANING]


def test_status_zone_cleaning_with_go_to_zone_becomes_cruising_point() -> None:
    status = _make_status({DreameVacuumProperty.STATUS: DreameVacuumStatus.ZONE_CLEANING.value})
    status.go_to_zone = MagicMock()
    assert status.status == DreameVacuumStatus.CRUISING_POINT


def test_status_charging_without_actually_charging_becomes_idle() -> None:
    """STATUS==CHARGING but charging_status isn't CHARGING -> reported as IDLE."""
    status = _make_status({DreameVacuumProperty.STATUS: DreameVacuumStatus.CHARGING.value})
    assert status.charging is False
    assert status.status == DreameVacuumStatus.IDLE


def test_status_charging_while_actually_charging_stays_charging() -> None:
    status = _make_status(
        {
            DreameVacuumProperty.STATUS: DreameVacuumStatus.CHARGING.value,
            DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.CHARGING.value,
            DreameVacuumProperty.BATTERY_LEVEL: 40,
        }
    )
    assert status.charging is True
    assert status.status == DreameVacuumStatus.CHARGING


def test_status_missing_is_unknown() -> None:
    status = _make_status({})
    assert status.status == DreameVacuumStatus.UNKNOWN


def test_task_status_zone_cleaning_with_go_to_zone() -> None:
    status = _make_status({DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.ZONE_CLEANING.value})
    status.go_to_zone = MagicMock()
    assert status.task_status == DreameVacuumTaskStatus.CRUISING_POINT


def test_task_status_zone_cleaning_paused_with_go_to_zone() -> None:
    status = _make_status({DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.ZONE_CLEANING_PAUSED.value})
    status.go_to_zone = MagicMock()
    assert status.task_status == DreameVacuumTaskStatus.CRUISING_POINT_PAUSED


def test_task_status_zone_cleaning_without_go_to_zone() -> None:
    status = _make_status({DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.ZONE_CLEANING.value})
    assert status.task_status == DreameVacuumTaskStatus.ZONE_CLEANING
    assert status.task_status_name == TASK_STATUS_CODE_TO_NAME[DreameVacuumTaskStatus.ZONE_CLEANING]


def test_task_status_missing_is_unknown() -> None:
    status = _make_status({})
    assert status.task_status == DreameVacuumTaskStatus.UNKNOWN


# ---------------------------------------------------------------------------
# carpet_cleaning - capability-driven special cases
# ---------------------------------------------------------------------------


def test_carpet_cleaning_plain_passthrough() -> None:
    status = _make_status({DreameVacuumProperty.CARPET_CLEANING: DreameVacuumCarpetCleaning.AVOIDANCE.value})
    assert status.carpet_cleaning == DreameVacuumCarpetCleaning.AVOIDANCE
    assert status.carpet_cleaning_name == CARPET_CLEANING_CODE_TO_NAME[DreameVacuumCarpetCleaning.AVOIDANCE]


def test_carpet_cleaning_ignore_when_recognition_off_and_capabilities_set() -> None:
    capability = _make_capability(mop_pad_lifting_plus=True, auto_carpet_cleaning=True)
    status = _make_status(
        {DreameVacuumProperty.CARPET_CLEANING: DreameVacuumCarpetCleaning.AVOIDANCE.value}, capability=capability
    )
    assert status.carpet_recognition is False
    assert status.carpet_cleaning == DreameVacuumCarpetCleaning.IGNORE


def test_carpet_cleaning_raw_value_six_is_always_adaptation() -> None:
    status = _make_status({DreameVacuumProperty.CARPET_CLEANING: 6})
    assert status.carpet_cleaning == DreameVacuumCarpetCleaning.ADAPTATION


def test_carpet_cleaning_raw_three_with_unmounting_and_no_auto_mount_is_adaptation() -> None:
    capability = _make_capability(mop_pad_unmounting=True)
    status = _make_status({DreameVacuumProperty.CARPET_CLEANING: 3}, capability=capability)
    assert status.auto_mount_mop is False
    assert status.carpet_cleaning == DreameVacuumCarpetCleaning.ADAPTATION


def test_carpet_cleaning_raw_three_without_unmounting_is_remove_mop_member() -> None:
    status = _make_status({DreameVacuumProperty.CARPET_CLEANING: 3})
    assert status.carpet_cleaning == DreameVacuumCarpetCleaning.REMOVE_MOP


def test_carpet_cleaning_missing_is_unknown() -> None:
    status = _make_status({})
    assert status.carpet_cleaning == DreameVacuumCarpetCleaning.UNKNOWN


# ---------------------------------------------------------------------------
# state - old/new state remap + IDLE cascade + go_to_zone monitoring
# ---------------------------------------------------------------------------


def test_state_plain_passthrough_when_not_started_and_not_docked() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATE: DreameVacuumState.IDLE.value}))
    assert status.started is False
    assert status.docked is False
    assert status.state == DreameVacuumState.IDLE
    assert status.state_name == STATE_CODE_TO_STATE[DreameVacuumState.IDLE]


def test_state_idle_defaults_to_paused_when_started() -> None:
    """With no TASK_STATUS set, started defaults True, so IDLE reports as PAUSED."""
    status = _make_status({DreameVacuumProperty.STATE: DreameVacuumState.IDLE.value})
    assert status.started is True
    assert status.state == DreameVacuumState.PAUSED


def test_state_idle_docked_and_charging_becomes_charging() -> None:
    status = _make_status(
        _not_started_properties(
            {
                DreameVacuumProperty.STATE: DreameVacuumState.IDLE.value,
                DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.CHARGING.value,
                DreameVacuumProperty.BATTERY_LEVEL: 50,
            }
        )
    )
    assert status.docked is True
    assert status.state == DreameVacuumState.CHARGING


def test_state_idle_docked_and_charging_completed_compat_branch() -> None:
    status = _make_status(
        _not_started_properties(
            {
                DreameVacuumProperty.STATE: DreameVacuumState.IDLE.value,
                DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.CHARGING_COMPLETED.value,
            }
        )
    )
    assert status.docked is True
    assert status.charging is False
    assert status.state == DreameVacuumState.CHARGING_COMPLETED


def test_state_old_firmware_remaps_state_old_values() -> None:
    """When new_state capability is off, raw values > 18 are reinterpreted via DreameVacuumStateOld."""
    capability = _make_capability(new_state=False)
    raw = DreameVacuumStateOld.WASHING_PAUSED.value
    assert raw == 23
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATE: raw}), capability=capability)
    assert status.state == DreameVacuumState.WASHING_PAUSED


def test_state_new_firmware_does_not_remap() -> None:
    capability = _make_capability(new_state=True)
    raw = DreameVacuumStateOld.WASHING_PAUSED.value
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATE: raw}), capability=capability)
    assert status.state == DreameVacuumState.REMOTE_CONTROL


def test_state_go_to_zone_monitoring() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATE: DreameVacuumState.IDLE.value}))
    status.go_to_zone = MagicMock()
    assert status.paused is False
    assert status.state == DreameVacuumState.MONITORING


def test_state_go_to_zone_monitoring_paused() -> None:
    status = _make_status(
        _not_started_properties(
            {
                DreameVacuumProperty.STATE: DreameVacuumState.SWEEPING.value,
                DreameVacuumProperty.CLEANING_PAUSED: 1,
            }
        )
    )
    status.go_to_zone = MagicMock()
    assert status.paused is True
    assert status.state == DreameVacuumState.MONITORING_PAUSED


def test_state_missing_is_unknown() -> None:
    status = _make_status({})
    assert status.state == DreameVacuumState.UNKNOWN


# ---------------------------------------------------------------------------
# drainage_status - overridden by self.state
# ---------------------------------------------------------------------------


def test_drainage_status_plain_passthrough() -> None:
    status = _make_status({DreameVacuumProperty.DRAINAGE_STATUS: DreameVacuumDrainageStatus.DRAINING_SUCCESS.value})
    assert status.drainage_status == DreameVacuumDrainageStatus.DRAINING_SUCCESS
    assert status.drainage_status_name == DRAINAGE_STATUS_TO_NAME[DreameVacuumDrainageStatus.DRAINING_SUCCESS]


def test_drainage_status_forced_draining_when_state_is_auto_water_draining() -> None:
    status = _make_status(
        _not_started_properties(
            {
                DreameVacuumProperty.DRAINAGE_STATUS: DreameVacuumDrainageStatus.IDLE.value,
                DreameVacuumProperty.STATE: DreameVacuumState.AUTO_WATER_DRAINING.value,
            }
        )
    )
    assert status.state == DreameVacuumState.AUTO_WATER_DRAINING
    assert status.drainage_status == DreameVacuumDrainageStatus.DRAINING


def test_drainage_status_forced_draining_when_state_is_draining() -> None:
    status = _make_status(
        _not_started_properties(
            {
                DreameVacuumProperty.DRAINAGE_STATUS: DreameVacuumDrainageStatus.IDLE.value,
                DreameVacuumProperty.STATE: DreameVacuumState.DRAINING.value,
            }
        )
    )
    assert status.drainage_status == DreameVacuumDrainageStatus.DRAINING


def test_drainage_status_missing_is_unknown() -> None:
    status = _make_status({})
    assert status.drainage_status == DreameVacuumDrainageStatus.UNKNOWN


# ---------------------------------------------------------------------------
# error - special-case remaps + has_error/has_warning/error_name
# ---------------------------------------------------------------------------


def test_error_remove_mop_with_self_wash_base_is_no_error() -> None:
    capability = _make_capability(self_wash_base=True)
    status = _make_status({DreameVacuumProperty.ERROR: DreameVacuumErrorCode.REMOVE_MOP.value}, capability=capability)
    assert status.error == DreameVacuumErrorCode.NO_ERROR


def test_error_remove_mop_without_self_wash_base_passes_through() -> None:
    status = _make_status({DreameVacuumProperty.ERROR: DreameVacuumErrorCode.REMOVE_MOP.value})
    assert status.error == DreameVacuumErrorCode.REMOVE_MOP


def test_error_low_battery_turn_off_is_always_no_error() -> None:
    status = _make_status({DreameVacuumProperty.ERROR: DreameVacuumErrorCode.LOW_BATTERY_TURN_OFF.value})
    assert status.error == DreameVacuumErrorCode.NO_ERROR


def test_error_unknown_warning_2_is_always_no_error() -> None:
    status = _make_status({DreameVacuumProperty.ERROR: DreameVacuumErrorCode.UNKNOWN_WARNING_2.value})
    assert status.error == DreameVacuumErrorCode.NO_ERROR


def test_error_missing_is_unknown() -> None:
    status = _make_status({})
    assert status.error == DreameVacuumErrorCode.UNKNOWN


def test_error_drop_has_error_true_and_warning_false() -> None:
    status = _make_status({DreameVacuumProperty.ERROR: DreameVacuumErrorCode.DROP.value})
    assert status.has_warning is False
    assert status.has_error is True
    assert status.error_name == ERROR_CODE_TO_ERROR_NAME[DreameVacuumErrorCode.DROP]


def test_error_battery_low_is_not_reported_as_error() -> None:
    status = _make_status({DreameVacuumProperty.ERROR: DreameVacuumErrorCode.BATTERY_LOW.value})
    assert status.has_error is False


def test_error_blocked_is_warning_not_error() -> None:
    status = _make_status({DreameVacuumProperty.ERROR: DreameVacuumErrorCode.BLOCKED.value})
    assert status.has_warning is True
    assert status.has_error is False
    assert status.error_name == ERROR_CODE_TO_ERROR_NAME[DreameVacuumErrorCode.BLOCKED]


def test_error_no_error_has_neither_error_nor_warning() -> None:
    status = _make_status({DreameVacuumProperty.ERROR: DreameVacuumErrorCode.NO_ERROR.value})
    assert status.has_error is False
    assert status.has_warning is False
    assert status.error_name == ERROR_CODE_TO_ERROR_NAME[DreameVacuumErrorCode.NO_ERROR]


# ---------------------------------------------------------------------------
# Capability-gated, auto-switch-backed, negative-clamped enum properties
# ---------------------------------------------------------------------------

AUTO_SWITCH_CLAMPED_CASES = [
    (
        "mop_pad_swing",
        "mop_pad_swing_name",
        "mop_pad_swing",
        DreameVacuumAutoSwitchProperty.MOP_PAD_SWING,
        DreameVacuumMopPadSwing,
        DreameVacuumMopPadSwing.WEEKLY,
        MOP_PAD_SWING_TO_NAME,
    ),
    (
        "mop_extend_frequency",
        "mop_extend_frequency_name",
        # capability.mop_extend is a *computed* property gated on mop_pad_swing (see the
        # dedicated mop_extend test below); flipping mop_pad_swing is how we drive it here.
        "mop_pad_swing",
        DreameVacuumAutoSwitchProperty.MOP_EXTEND_FREQUENCY,
        DreameVacuumMopExtendFrequency,
        DreameVacuumMopExtendFrequency.HIGH,
        MOP_EXTEND_FREQUENCY_TO_NAME,
    ),
    (
        "auto_recleaning",
        "auto_recleaning_name",
        "auto_recleaning",
        DreameVacuumAutoSwitchProperty.AUTO_RECLEANING,
        DreameVacuumSecondCleaning,
        DreameVacuumSecondCleaning.IN_ALL_MODES,
        SECOND_CLEANING_TO_NAME,
    ),
    (
        "auto_rewashing",
        "auto_rewashing_name",
        "auto_rewashing",
        DreameVacuumAutoSwitchProperty.AUTO_REWASHING,
        DreameVacuumSecondCleaning,
        DreameVacuumSecondCleaning.IN_DEEP_MODE,
        SECOND_CLEANING_TO_NAME,
    ),
    (
        "cleaning_route",
        "cleaning_route_name",
        "cleaning_route",
        DreameVacuumAutoSwitchProperty.CLEANING_ROUTE,
        DreameVacuumCleaningRoute,
        DreameVacuumCleaningRoute.INTENSIVE,
        CLEANING_ROUTE_TO_NAME,
    ),
    (
        "cleangenius",
        "cleangenius_name",
        "cleangenius",
        DreameVacuumAutoSwitchProperty.CLEANGENIUS,
        DreameVacuumCleanGenius,
        DreameVacuumCleanGenius.DEEP_CLEANING,
        CLEANGENIUS_TO_NAME,
    ),
]


@pytest.mark.parametrize(
    ("attr", "name_attr", "capability_flag", "switch_prop", "enum_cls", "valid_value", "to_name"),
    AUTO_SWITCH_CLAMPED_CASES,
)
def test_auto_switch_clamped_enum_valid(
    attr: str,
    name_attr: str,
    capability_flag: str,
    switch_prop: DreameVacuumAutoSwitchProperty,
    enum_cls: Any,
    valid_value: Any,
    to_name: dict[Any, str],
) -> None:
    capability = _make_capability(**{capability_flag: True})
    status = _make_status(capability=capability, auto_switch_properties={switch_prop: valid_value.value})
    assert getattr(status, attr) == valid_value
    assert getattr(status, name_attr) == to_name[valid_value]


@pytest.mark.parametrize(
    ("attr", "name_attr", "capability_flag", "switch_prop", "enum_cls", "valid_value", "to_name"),
    AUTO_SWITCH_CLAMPED_CASES,
)
def test_auto_switch_clamped_enum_capability_off_is_unknown(
    attr: str,
    name_attr: str,
    capability_flag: str,
    switch_prop: DreameVacuumAutoSwitchProperty,
    enum_cls: Any,
    valid_value: Any,
    to_name: dict[Any, str],
) -> None:
    capability = _make_capability(**{capability_flag: False})
    status = _make_status(capability=capability, auto_switch_properties={switch_prop: valid_value.value})
    assert getattr(status, attr) == enum_cls.UNKNOWN


@pytest.mark.parametrize(
    ("attr", "name_attr", "capability_flag", "switch_prop", "enum_cls", "valid_value", "to_name"),
    AUTO_SWITCH_CLAMPED_CASES,
)
def test_auto_switch_clamped_enum_negative_clamps_to_zero(
    attr: str,
    name_attr: str,
    capability_flag: str,
    switch_prop: DreameVacuumAutoSwitchProperty,
    enum_cls: Any,
    valid_value: Any,
    to_name: dict[Any, str],
) -> None:
    capability = _make_capability(**{capability_flag: True})
    status = _make_status(capability=capability, auto_switch_properties={switch_prop: -5})
    # -5 gets clamped to 0 before the membership check.
    expected = enum_cls(0) if 0 in enum_cls._value2member_map_ else enum_cls.UNKNOWN
    assert getattr(status, attr) == expected


# ---------------------------------------------------------------------------
# mopping_type / wider_corner_coverage - auto-switch backed, no capability gate
# ---------------------------------------------------------------------------


def test_mopping_type_valid() -> None:
    status = _make_status(
        auto_switch_properties={DreameVacuumAutoSwitchProperty.MOPPING_TYPE: DreameVacuumMoppingType.ACCURATE.value}
    )
    assert status.mopping_type == DreameVacuumMoppingType.ACCURATE
    assert status.mopping_type_name == MOPPING_TYPE_TO_NAME[DreameVacuumMoppingType.ACCURATE]


def test_mopping_type_invalid_is_unknown() -> None:
    status = _make_status(auto_switch_properties={DreameVacuumAutoSwitchProperty.MOPPING_TYPE: 9999})
    assert status.mopping_type == DreameVacuumMoppingType.UNKNOWN


def test_mopping_type_missing_is_none() -> None:
    status = _make_status({})
    assert status.mopping_type is None
    assert status.mopping_type_name == STATE_UNKNOWN


def test_wider_corner_coverage_valid() -> None:
    status = _make_status(
        auto_switch_properties={
            DreameVacuumAutoSwitchProperty.WIDER_CORNER_COVERAGE: DreameVacuumWiderCornerCoverage.HIGH_FREQUENCY.value
        }
    )
    assert status.wider_corner_coverage == DreameVacuumWiderCornerCoverage.HIGH_FREQUENCY


def test_wider_corner_coverage_negative_clamps_to_off() -> None:
    status = _make_status(auto_switch_properties={DreameVacuumAutoSwitchProperty.WIDER_CORNER_COVERAGE: -3})
    assert status.wider_corner_coverage == DreameVacuumWiderCornerCoverage.OFF
    assert status.wider_corner_coverage_name == WIDER_CORNER_COVERAGE_TO_NAME[DreameVacuumWiderCornerCoverage.OFF]


def test_wider_corner_coverage_missing_is_unknown() -> None:
    status = _make_status({})
    assert status.wider_corner_coverage == DreameVacuumWiderCornerCoverage.UNKNOWN


# ---------------------------------------------------------------------------
# mop_wash_level / cleangenius_mode / water_temperature
# ---------------------------------------------------------------------------


def test_mop_wash_level_requires_self_wash_base() -> None:
    capability = _make_capability(self_wash_base=True)
    status = _make_status(
        {DreameVacuumProperty.MOP_WASH_LEVEL: DreameVacuumMopWashLevel.DEEP.value}, capability=capability
    )
    assert status.mop_wash_level == DreameVacuumMopWashLevel.DEEP
    assert status.mop_wash_level_name == MOP_WASH_LEVEL_TO_NAME[DreameVacuumMopWashLevel.DEEP]


def test_mop_wash_level_without_self_wash_base_is_unknown() -> None:
    status = _make_status({DreameVacuumProperty.MOP_WASH_LEVEL: DreameVacuumMopWashLevel.DEEP.value})
    assert status.mop_wash_level == DreameVacuumMopWashLevel.UNKNOWN


def test_cleangenius_mode_valid() -> None:
    capability = _make_capability(cleangenius_mode=True)
    status = _make_status(
        {DreameVacuumProperty.CLEANGENIUS_MODE: DreameVacuumCleanGeniusMode.MOP_AFTER_VACUUM.value},
        capability=capability,
    )
    assert status.cleangenius_mode == DreameVacuumCleanGeniusMode.MOP_AFTER_VACUUM
    assert status.cleangenius_mode_name == CLEANGENIUS_MODE_TO_NAME[DreameVacuumCleanGeniusMode.MOP_AFTER_VACUUM]


def test_cleangenius_mode_negative_clamps_to_zero_which_is_not_a_member() -> None:
    """0 isn't a valid DreameVacuumCleanGeniusMode member (only -1/2/3 are), so this resolves to UNKNOWN."""
    capability = _make_capability(cleangenius_mode=True)
    status = _make_status({DreameVacuumProperty.CLEANGENIUS_MODE: -7}, capability=capability)
    assert 0 not in DreameVacuumCleanGeniusMode._value2member_map_
    assert status.cleangenius_mode == DreameVacuumCleanGeniusMode.UNKNOWN


def test_cleangenius_mode_capability_off_is_unknown() -> None:
    status = _make_status({DreameVacuumProperty.CLEANGENIUS_MODE: DreameVacuumCleanGeniusMode.MOP_AFTER_VACUUM.value})
    assert status.cleangenius_mode == DreameVacuumCleanGeniusMode.UNKNOWN


def test_water_temperature_valid() -> None:
    capability = _make_capability(water_temperature=True)
    status = _make_status(
        {DreameVacuumProperty.WATER_TEMPERATURE: DreameVacuumWaterTemperature.HOT.value}, capability=capability
    )
    assert status.water_temperature == DreameVacuumWaterTemperature.HOT
    assert status.water_temperature_name == WATER_TEMPERATURE_TO_NAME[DreameVacuumWaterTemperature.HOT]


def test_water_temperature_negative_clamps_to_normal() -> None:
    capability = _make_capability(water_temperature=True)
    status = _make_status({DreameVacuumProperty.WATER_TEMPERATURE: -9}, capability=capability)
    assert status.water_temperature == DreameVacuumWaterTemperature.NORMAL


def test_water_temperature_capability_off_is_unknown() -> None:
    status = _make_status({DreameVacuumProperty.WATER_TEMPERATURE: DreameVacuumWaterTemperature.HOT.value})
    assert status.water_temperature == DreameVacuumWaterTemperature.UNKNOWN


# ---------------------------------------------------------------------------
# custom_mopping_route - capability + custom_mopping_mode dependency
# ---------------------------------------------------------------------------


def test_custom_mopping_route_off_when_custom_mopping_mode_disabled() -> None:
    capability = _make_capability(custom_mopping_route=True)
    status = _make_status(
        capability=capability,
        auto_switch_properties={
            DreameVacuumAutoSwitchProperty.MOPPING_TYPE: DreameVacuumCustomMoppingRoute.INTENSIVE.value
        },
    )
    assert status.custom_mopping_mode is False
    assert status.custom_mopping_route == DreameVacuumCustomMoppingRoute.OFF
    assert status.custom_mopping_route_name == CUSTOM_MOPPING_ROUTE_TO_NAME[DreameVacuumCustomMoppingRoute.OFF]


def test_custom_mopping_route_passthrough_when_custom_mopping_mode_enabled() -> None:
    capability = _make_capability(custom_mopping_route=True, mopping_settings=True)
    status = _make_status(
        # custom_mopping_mode reads CUSTOM_MOPPING_MODE via plain get_property (see source),
        # while custom_mopping_route reads MOPPING_TYPE via get_auto_switch_property.
        {DreameVacuumAutoSwitchProperty.CUSTOM_MOPPING_MODE: 1},
        capability=capability,
        auto_switch_properties={
            DreameVacuumAutoSwitchProperty.MOPPING_TYPE: DreameVacuumCustomMoppingRoute.INTENSIVE.value,
        },
    )
    assert status.custom_mopping_mode is True
    assert status.custom_mopping_route == DreameVacuumCustomMoppingRoute.INTENSIVE
    assert status.custom_mopping_route_name == CUSTOM_MOPPING_ROUTE_TO_NAME[DreameVacuumCustomMoppingRoute.INTENSIVE]


def test_custom_mopping_route_capability_off_is_unknown() -> None:
    status = _make_status(auto_switch_properties={DreameVacuumAutoSwitchProperty.MOPPING_TYPE: 1})
    assert status.custom_mopping_route == DreameVacuumCustomMoppingRoute.UNKNOWN


# ---------------------------------------------------------------------------
# washing_mode - ultra_clean_mode override + mop_wash_level based
# ---------------------------------------------------------------------------


def test_washing_mode_ultra_clean_mode_override() -> None:
    capability = _make_capability(cleangenius_mode=True, ultra_clean_mode=True)
    # ultra_clean_mode (status) reads ULTRA_CLEAN_MODE via plain get_property (see source).
    status = _make_status({DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE: 1}, capability=capability)
    assert status.ultra_clean_mode is True
    assert status.washing_mode == DreameVacuumWashingMode.ULTRA_WASHING
    assert status.washing_mode_name == WASHING_MODE_TO_NAME[DreameVacuumWashingMode.ULTRA_WASHING]


def test_washing_mode_from_mop_wash_level() -> None:
    capability = _make_capability(cleangenius_mode=True, self_wash_base=True)
    status = _make_status(
        {DreameVacuumProperty.MOP_WASH_LEVEL: DreameVacuumMopWashLevel.DEEP.value}, capability=capability
    )
    assert status.washing_mode == DreameVacuumWashingMode.DEEP


def test_washing_mode_capability_off_is_unknown() -> None:
    status = _make_status({DreameVacuumProperty.MOP_WASH_LEVEL: DreameVacuumMopWashLevel.DEEP.value})
    assert status.washing_mode == DreameVacuumWashingMode.UNKNOWN


# ---------------------------------------------------------------------------
# mop_clean_frequency / self_clean_frequency / auto_empty_mode
# ---------------------------------------------------------------------------


def test_mop_clean_frequency_by_room_when_zero() -> None:
    capability = _make_capability(self_wash_base=True, mop_clean_frequency=True)
    status = _make_status(capability=capability)
    status.self_clean_value = 0
    assert status.mop_clean_frequency == DreameVacuumMopCleanFrequency.BY_ROOM
    assert status.mop_clean_frequency_name == MOP_CLEAN_FREQUENCY_TO_NAME[DreameVacuumMopCleanFrequency.BY_ROOM]


def test_mop_clean_frequency_valid_area() -> None:
    capability = _make_capability(self_wash_base=True, mop_clean_frequency=True)
    status = _make_status(capability=capability)
    status.self_clean_value = 10
    assert status.mop_clean_frequency == DreameVacuumMopCleanFrequency.TEN_SQUARE_METERS


def test_mop_clean_frequency_none_is_unknown() -> None:
    capability = _make_capability(self_wash_base=True, mop_clean_frequency=True)
    status = _make_status(capability=capability)
    status.self_clean_value = None
    assert status.mop_clean_frequency == DreameVacuumMopCleanFrequency.UNKNOWN


def test_mop_clean_frequency_capabilities_off_is_unknown() -> None:
    status = _make_status()
    status.self_clean_value = 10
    assert status.mop_clean_frequency == DreameVacuumMopCleanFrequency.UNKNOWN


def test_self_clean_frequency_by_room_when_falsy() -> None:
    capability = _make_capability(self_clean_frequency=True)
    status = _make_status(capability=capability)
    status.self_clean_value = None
    assert status.self_clean_frequency == DreameVacuumSelfCleanFrequency.BY_ROOM
    assert status.self_clean_frequency_name == SELF_CLEAN_FREQUENCY_TO_NAME[DreameVacuumSelfCleanFrequency.BY_ROOM]


def test_self_clean_frequency_by_time_from_auto_switch() -> None:
    capability = _make_capability(self_clean_frequency=True)
    status = _make_status(
        capability=capability,
        auto_switch_properties={
            DreameVacuumAutoSwitchProperty.SELF_CLEAN_FREQUENCY: DreameVacuumSelfCleanFrequency.BY_TIME.value
        },
    )
    status.self_clean_value = 20
    assert status.self_clean_frequency == DreameVacuumSelfCleanFrequency.BY_TIME


def test_self_clean_frequency_capability_off_is_unknown() -> None:
    status = _make_status()
    status.self_clean_value = 20
    assert status.self_clean_frequency == DreameVacuumSelfCleanFrequency.UNKNOWN


def test_auto_empty_mode_valid() -> None:
    capability = _make_capability(auto_empty_mode=True)
    status = _make_status(
        {DreameVacuumProperty.AUTO_DUST_COLLECTING: DreameVacuumAutoEmptyMode.HIGH_FREQUENCY.value},
        capability=capability,
    )
    assert status.auto_empty_mode == DreameVacuumAutoEmptyMode.HIGH_FREQUENCY
    assert status.auto_empty_mode_name == AUTO_EMPTY_MODE_TO_NAME[DreameVacuumAutoEmptyMode.HIGH_FREQUENCY]


def test_auto_empty_mode_capability_off_is_unknown() -> None:
    status = _make_status({DreameVacuumProperty.AUTO_DUST_COLLECTING: DreameVacuumAutoEmptyMode.HIGH_FREQUENCY.value})
    assert status.auto_empty_mode == DreameVacuumAutoEmptyMode.UNKNOWN
    assert status.auto_empty_mode_name == STATE_UNKNOWN


# ---------------------------------------------------------------------------
# water_volume
# ---------------------------------------------------------------------------


def test_water_volume_without_self_wash_base_is_plain_enum() -> None:
    status = _make_status({DreameVacuumProperty.WATER_VOLUME: DreameVacuumWaterVolume.HIGH.value})
    assert status.water_volume == DreameVacuumWaterVolume.HIGH
    assert status.water_volume_name == WATER_VOLUME_CODE_TO_NAME[DreameVacuumWaterVolume.HIGH]


def test_water_volume_without_self_wash_base_missing_is_unknown() -> None:
    status = _make_status({})
    assert status.water_volume == DreameVacuumWaterVolume.UNKNOWN


def test_water_volume_self_wash_base_uses_mop_pad_humidity_instance_attr() -> None:
    """mop_pad_humidity is a plain instance attribute (defaults to 1 == SLIGHTLY_DRY)."""
    capability = _make_capability(self_wash_base=True)
    status = _make_status(capability=capability)
    assert status.mop_pad_humidity == 1
    # mop_pad_humidity(1) casts to DreameVacuumMopPadHumidity.SLIGHTLY_DRY
    assert status.water_volume == DreameVacuumMopPadHumidity.SLIGHTLY_DRY


def test_water_volume_wetness_level_branch_raises_due_to_source_bug() -> None:
    """When mop_pad_humidity is None and wetness_level capability is on, the source reads
    ``self.status.wetness_level`` - but ``status`` is a plain IntEnum member with no such
    attribute. This documents the resulting AttributeError as current, real behavior.
    """
    capability = _make_capability(self_wash_base=True, wetness_level=True)
    status = _make_status(capability=capability)
    status.mop_pad_humidity = None
    with pytest.raises(AttributeError):
        _ = status.water_volume


# ---------------------------------------------------------------------------
# Boolean derived properties: charging / docked / running / paused / started / active
# ---------------------------------------------------------------------------


def test_started_true_by_default_task_status_unknown() -> None:
    status = _make_status({})
    assert status.started is True


def test_started_false_when_task_completed() -> None:
    status = _make_status(_not_started_properties())
    assert status.started is False


def test_started_true_when_status_is_cleaning() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATUS: DreameVacuumStatus.CLEANING.value}))
    assert status.started is True


def test_started_true_when_cleaning_paused() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.CLEANING_PAUSED: 1}))
    assert status.started is True


def test_charging_true_when_charging_status_charging_and_battery_below_100() -> None:
    status = _make_status(
        {
            DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.CHARGING.value,
            DreameVacuumProperty.BATTERY_LEVEL: 99,
        }
    )
    assert status.charging is True


def test_charging_false_when_battery_full() -> None:
    status = _make_status(
        {
            DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.CHARGING.value,
            DreameVacuumProperty.BATTERY_LEVEL: 100,
        }
    )
    # charging_status itself becomes CHARGING_COMPLETED at 100, so `charging` (which needs
    # charging_status is CHARGING) resolves False.
    assert status.charging is False


def test_docked_false_when_running() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATUS: DreameVacuumStatus.CLEANING.value}))
    # No charging/washing/drying condition is met while actively cleaning, so docked is False.
    assert status.running is True
    assert status.docked is False


def test_docked_true_when_charging_and_not_running() -> None:
    status = _make_status(
        {
            DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.CHARGING.value,
            DreameVacuumProperty.BATTERY_LEVEL: 50,
        }
    )
    assert status.running is False
    assert status.docked is True


def test_running_true_for_cleaning_status_when_not_docked() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATUS: DreameVacuumStatus.CLEANING.value}))
    assert status.running is True


def test_running_false_when_status_idle() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATUS: DreameVacuumStatus.IDLE.value}))
    assert status.running is False


def test_paused_true_when_started_and_status_paused() -> None:
    status = _make_status({DreameVacuumProperty.STATUS: DreameVacuumStatus.PAUSED.value})
    assert status.started is True
    assert status.paused is True


def test_paused_false_when_not_started() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATUS: DreameVacuumStatus.PAUSED.value}))
    assert status.paused is False


def test_paused_true_when_cleaning_paused_regardless_of_status() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.CLEANING_PAUSED: 1}))
    assert status.paused is True


def test_active_true_when_running() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATUS: DreameVacuumStatus.CLEANING.value}))
    assert status.active is True


def test_active_true_when_standby() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATUS: DreameVacuumStatus.STANDBY.value}))
    assert status.active is True


def test_active_false_when_idle_and_not_running() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATUS: DreameVacuumStatus.IDLE.value}))
    assert status.active is False


def test_sleeping_true_when_status_sleeping() -> None:
    status = _make_status({DreameVacuumProperty.STATUS: DreameVacuumStatus.SLEEPING.value})
    assert status.sleeping is True


def test_sleeping_false_otherwise() -> None:
    status = _make_status({DreameVacuumProperty.STATUS: DreameVacuumStatus.IDLE.value})
    assert status.sleeping is False


def test_returning_true_when_back_home_and_not_docked() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATUS: DreameVacuumStatus.BACK_HOME.value}))
    assert status.docked is False
    assert status.returning is True


def test_returning_false_when_device_not_connected() -> None:
    status = _make_status(
        _not_started_properties({DreameVacuumProperty.STATUS: DreameVacuumStatus.BACK_HOME.value}),
        device_connected=False,
    )
    assert status.returning is False


def test_returning_paused_true() -> None:
    status = _make_status({DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.DOCKING_PAUSED.value})
    assert status.returning_paused is True


def test_returning_paused_false_when_docked() -> None:
    status = _make_status(
        {
            DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.DOCKING_PAUSED.value,
            DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.CHARGING.value,
            DreameVacuumProperty.BATTERY_LEVEL: 40,
        }
    )
    assert status.docked is True
    assert status.returning_paused is False


# ---------------------------------------------------------------------------
# washing / drying / washing_paused / returning_to_wash(_paused) / washing_available / drying_available
# ---------------------------------------------------------------------------


def test_washing_true_when_self_wash_base_status_washing() -> None:
    capability = _make_capability(self_wash_base=True)
    status = _make_status(
        {DreameVacuumProperty.SELF_WASH_BASE_STATUS: DreameVacuumSelfWashBaseStatus.WASHING.value},
        capability=capability,
    )
    assert status.washing is True


def test_washing_true_when_clean_add_water() -> None:
    capability = _make_capability(self_wash_base=True)
    status = _make_status(
        {DreameVacuumProperty.SELF_WASH_BASE_STATUS: DreameVacuumSelfWashBaseStatus.CLEAN_ADD_WATER.value},
        capability=capability,
    )
    assert status.washing is True


def test_washing_false_without_capability() -> None:
    status = _make_status({DreameVacuumProperty.SELF_WASH_BASE_STATUS: DreameVacuumSelfWashBaseStatus.WASHING.value})
    assert status.washing is False


def test_drying_true_when_self_wash_base_status_drying() -> None:
    capability = _make_capability(self_wash_base=True)
    status = _make_status(
        {DreameVacuumProperty.SELF_WASH_BASE_STATUS: DreameVacuumSelfWashBaseStatus.DRYING.value}, capability=capability
    )
    assert status.drying is True


def test_washing_paused_true() -> None:
    capability = _make_capability(self_wash_base=True)
    status = _make_status(
        {DreameVacuumProperty.SELF_WASH_BASE_STATUS: DreameVacuumSelfWashBaseStatus.PAUSED.value}, capability=capability
    )
    assert status.washing_paused is True


def test_returning_to_wash_true() -> None:
    capability = _make_capability(self_wash_base=True)
    status = _make_status(
        {
            DreameVacuumProperty.SELF_WASH_BASE_STATUS: DreameVacuumSelfWashBaseStatus.RETURNING.value,
            DreameVacuumProperty.STATE: DreameVacuumState.RETURNING_TO_WASH.value,
        },
        capability=capability,
    )
    assert status.returning_to_wash is True


def test_returning_to_wash_paused_true() -> None:
    capability = _make_capability(self_wash_base=True)
    status = _make_status(
        {
            DreameVacuumProperty.SELF_WASH_BASE_STATUS: DreameVacuumSelfWashBaseStatus.RETURNING.value,
            DreameVacuumProperty.STATE: DreameVacuumState.PAUSED.value,
        },
        capability=capability,
    )
    assert status.returning_to_wash_paused is True


def test_washing_available_true_when_installed_and_idle() -> None:
    capability = _make_capability(self_wash_base=True, embedded_tank=True)
    status = _make_status(_not_started_properties(), capability=capability)
    assert status.water_tank_or_mop_installed is True
    assert status.washing_available is True


def test_washing_available_false_while_washing() -> None:
    capability = _make_capability(self_wash_base=True, embedded_tank=True)
    status = _make_status(
        _not_started_properties(
            {DreameVacuumProperty.SELF_WASH_BASE_STATUS: DreameVacuumSelfWashBaseStatus.WASHING.value}
        ),
        capability=capability,
    )
    assert status.washing is True
    assert status.washing_available is False


def test_drying_available_true_when_docked_and_not_started() -> None:
    capability = _make_capability(self_wash_base=True, embedded_tank=True)
    status = _make_status(
        _not_started_properties(
            {
                DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.CHARGING.value,
                DreameVacuumProperty.BATTERY_LEVEL: 50,
            }
        ),
        capability=capability,
    )
    assert status.docked is True
    assert status.drying_available is True


def test_drying_available_false_when_started() -> None:
    capability = _make_capability(self_wash_base=True, embedded_tank=True)
    status = _make_status(
        {
            DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.CHARGING.value,
            DreameVacuumProperty.BATTERY_LEVEL: 50,
        },
        capability=capability,
    )
    assert status.started is True
    assert status.drying_available is False


# ---------------------------------------------------------------------------
# sweeping / mopping / mopping_after_sweeping
# ---------------------------------------------------------------------------


def test_sweeping_true_when_cleaning_mode_sweeping() -> None:
    status = _make_status({})
    status.cleaning_mode = DreameVacuumCleaningMode.SWEEPING
    assert status.sweeping is True


def test_sweeping_false_when_cleaning_mode_mopping() -> None:
    status = _make_status({})
    status.cleaning_mode = DreameVacuumCleaningMode.MOPPING
    assert status.sweeping is False


def test_sweeping_none_cleaning_mode_depends_on_water_tank_installed() -> None:
    capability = _make_capability(embedded_tank=True)
    status = _make_status({DreameVacuumProperty.WATER_TANK: 1}, capability=capability)
    status.cleaning_mode = None
    assert status.water_tank_or_mop_installed is True
    assert status.sweeping is False


def test_mopping_true_when_cleaning_mode_mopping() -> None:
    status = _make_status({})
    status.cleaning_mode = DreameVacuumCleaningMode.MOPPING
    assert status.mopping is True
    assert status.cleaning_mode_name == CLEANING_MODE_CODE_TO_NAME[DreameVacuumCleaningMode.MOPPING]


def test_mopping_after_sweeping_true() -> None:
    status = _make_status({})
    status.cleaning_mode = DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING
    assert status.mopping_after_sweeping is True
    assert status.mopping is False


def test_cleaning_mode_name_none_is_unknown() -> None:
    status = _make_status({})
    status.cleaning_mode = None
    assert status.cleaning_mode_name == STATE_UNKNOWN


# ---------------------------------------------------------------------------
# zone_cleaning / spot_cleaning / segment_cleaning / auto_cleaning / fast_mapping(_paused) / cruising(_paused)
# ---------------------------------------------------------------------------


def test_zone_cleaning_true() -> None:
    status = _make_status({DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.ZONE_CLEANING.value})
    assert status.zone_cleaning is True


def test_zone_cleaning_false_when_not_started() -> None:
    status = _make_status(
        _not_started_properties({DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.COMPLETED.value})
    )
    assert status.zone_cleaning is False


def test_spot_cleaning_true_via_task_status() -> None:
    status = _make_status({DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.SPOT_CLEANING.value})
    assert status.spot_cleaning is True


def test_spot_cleaning_true_via_status() -> None:
    status = _make_status(
        {
            DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.AUTO_CLEANING.value,
            DreameVacuumProperty.STATUS: DreameVacuumStatus.SPOT_CLEANING.value,
        }
    )
    assert status.spot_cleaning is True


def test_segment_cleaning_true() -> None:
    status = _make_status({DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.SEGMENT_CLEANING_PAUSED.value})
    assert status.segment_cleaning is True


def test_auto_cleaning_true() -> None:
    status = _make_status({DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.AUTO_CLEANING.value})
    assert status.auto_cleaning is True


def test_fast_mapping_true_via_task_status() -> None:
    status = _make_status({DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.FAST_MAPPING.value})
    assert status.fast_mapping is True


def test_fast_mapping_true_via_status() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.STATUS: DreameVacuumStatus.FAST_MAPPING.value}))
    assert status.fast_mapping is True


def test_fast_mapping_paused_true() -> None:
    status = _make_status(
        {
            DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.FAST_MAPPING.value,
            DreameVacuumProperty.STATE: DreameVacuumState.PAUSED.value,
        }
    )
    assert status.fast_mapping_paused is True


def test_fast_mapping_paused_false_wrong_state() -> None:
    status = _make_status(
        {
            DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.FAST_MAPPING.value,
            DreameVacuumProperty.STATE: DreameVacuumState.CHARGING.value,
        }
    )
    assert status.fast_mapping_paused is False


def test_cruising_true_via_task_status_when_capability_on() -> None:
    # capability.cruising is a *computed* property; camera_streaming=True (with the default
    # lidar_navigation=True) is enough to make it resolve True via the capability's own
    # (unrelated, auto-mocked) device.
    capability = _make_capability(camera_streaming=True)
    assert capability.cruising is True
    status = _make_status(
        {DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.CRUISING_PATH.value}, capability=capability
    )
    assert status.cruising is True


def test_cruising_uses_go_to_zone_when_capability_off() -> None:
    status = _make_status({})
    status.go_to_zone = MagicMock()
    assert status.cruising is True


def test_cruising_false_by_default() -> None:
    status = _make_status({})
    assert status.cruising is False


def test_cruising_paused_true_with_capability() -> None:
    capability = _make_capability(camera_streaming=True)
    status = _make_status(
        {DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.CRUISING_PATH_PAUSED.value}, capability=capability
    )
    assert status.cruising_paused is True


def test_cruising_paused_true_via_go_to_zone() -> None:
    status = _make_status({DreameVacuumProperty.STATUS: DreameVacuumStatus.PAUSED.value})
    status.go_to_zone = MagicMock()
    assert status.started is True
    assert status.cruising_paused is True


def test_station_cleaning_true() -> None:
    status = _make_status({DreameVacuumProperty.TASK_STATUS: DreameVacuumTaskStatus.STATION_CLEANING.value})
    assert status.station_cleaning is True


def test_self_repairing_true_for_self_repair_status() -> None:
    status = _make_status({DreameVacuumProperty.STATUS: DreameVacuumStatus.SELF_REPAIR.value})
    assert status.self_repairing is True


def test_self_repairing_true_for_water_check_state() -> None:
    # Raw STATE 19 collides with DreameVacuumStateOld.REMOTE_CONTROL under the old-firmware
    # remap (value > 18 and not capability.new_state), so new_state=True is required here to
    # read WATER_CHECK (19) directly as the new-firmware state.
    capability = _make_capability(new_state=True)
    status = _make_status(
        _not_started_properties({DreameVacuumProperty.STATE: DreameVacuumState.WATER_CHECK.value}),
        capability=capability,
    )
    assert status.state == DreameVacuumState.WATER_CHECK
    assert status.self_repairing is True


def test_draining_true() -> None:
    capability = _make_capability(drainage=True)
    status = _make_status(
        {DreameVacuumProperty.DRAINAGE_STATUS: DreameVacuumDrainageStatus.DRAINING.value}, capability=capability
    )
    assert status.draining is True


def test_draining_complete_true_on_success() -> None:
    capability = _make_capability(drainage=True)
    status = _make_status(
        {DreameVacuumProperty.DRAINAGE_STATUS: DreameVacuumDrainageStatus.DRAINING_SUCCESS.value}, capability=capability
    )
    assert status.draining_complete is True


def test_draining_complete_true_on_failure() -> None:
    capability = _make_capability(drainage=True)
    status = _make_status(
        {DreameVacuumProperty.DRAINAGE_STATUS: DreameVacuumDrainageStatus.DRAINING_FAILED.value}, capability=capability
    )
    assert status.draining_complete is True


# ---------------------------------------------------------------------------
# water_tank_or_mop_installed / mop_pad_installed / located
# ---------------------------------------------------------------------------


def test_water_tank_or_mop_installed_true_plain() -> None:
    status = _make_status({DreameVacuumProperty.WATER_TANK: DreameVacuumWaterTank.INSTALLED.value})
    assert status.water_tank_or_mop_installed is True


def test_water_tank_or_mop_installed_false_plain() -> None:
    status = _make_status({DreameVacuumProperty.WATER_TANK: DreameVacuumWaterTank.NOT_INSTALLED.value})
    assert status.water_tank_or_mop_installed is False


def test_water_tank_or_mop_installed_embedded_tank_forces_true() -> None:
    capability = _make_capability(embedded_tank=True)
    status = _make_status(
        {DreameVacuumProperty.WATER_TANK: DreameVacuumWaterTank.NOT_INSTALLED.value}, capability=capability
    )
    assert status.water_tank_or_mop_installed is True


def test_mop_pad_installed_with_unmounting_capability() -> None:
    capability = _make_capability(mop_pad_unmounting=True)
    status = _make_status({DreameVacuumProperty.MOP_PAD_INSTALLED: 0}, capability=capability)
    assert status.mop_pad_installed is True


def test_mop_pad_installed_with_unmounting_capability_false_value() -> None:
    capability = _make_capability(mop_pad_unmounting=True)
    status = _make_status({DreameVacuumProperty.MOP_PAD_INSTALLED: 1}, capability=capability)
    assert status.mop_pad_installed is False


def test_mop_pad_installed_falls_back_to_water_tank_or_mop_installed() -> None:
    status = _make_status({DreameVacuumProperty.WATER_TANK: DreameVacuumWaterTank.INSTALLED.value})
    assert status.mop_pad_installed == status.water_tank_or_mop_installed is True


def test_located_true_when_relocation_located() -> None:
    status = _make_status({DreameVacuumProperty.RELOCATION_STATUS: DreameVacuumRelocationStatus.LOCATED.value})
    assert status.located is True


def test_located_false_when_locating() -> None:
    status = _make_status({DreameVacuumProperty.RELOCATION_STATUS: DreameVacuumRelocationStatus.LOCATING.value})
    assert status.located is False


def test_located_true_when_unknown_relocation_status() -> None:
    status = _make_status({})
    assert status.located is True


# ---------------------------------------------------------------------------
# dnd / off_peak_charging / dnd_remaining
# ---------------------------------------------------------------------------


def test_dnd_true_when_capability_on_and_property_set() -> None:
    capability = _make_capability(dnd=True)
    status = _make_status({DreameVacuumProperty.DND: 1}, capability=capability)
    assert status.dnd is True


def test_dnd_none_when_capability_off() -> None:
    status = _make_status({DreameVacuumProperty.DND: 1})
    assert status.dnd is None


def test_dnd_start_end_passthrough() -> None:
    capability = _make_capability(dnd=True)
    status = _make_status(
        {DreameVacuumProperty.DND_START: "21:00", DreameVacuumProperty.DND_END: "07:30"}, capability=capability
    )
    assert status.dnd_start == "21:00"
    assert status.dnd_end == "07:30"


def test_off_peak_charging_true() -> None:
    capability = _make_capability(off_peak_charging=True)
    status = _make_status(capability=capability)
    status.off_peak_charging_config = {"enable": True}
    assert status.off_peak_charging is True


def test_off_peak_charging_false_when_disabled() -> None:
    capability = _make_capability(off_peak_charging=True)
    status = _make_status(capability=capability)
    status.off_peak_charging_config = {"enable": False}
    assert status.off_peak_charging is False


def test_off_peak_charging_none_when_capability_off() -> None:
    status = _make_status()
    assert status.off_peak_charging is None


def test_off_peak_charging_start_default_when_no_config() -> None:
    capability = _make_capability(off_peak_charging=True)
    status = _make_status(capability=capability)
    status.off_peak_charging_config = None
    assert status.off_peak_charging_start == "22:00"
    assert status.off_peak_charging_end == "08:00"


@pytest.mark.parametrize(
    ("now", "dnd_start", "dnd_end", "expected"),
    [
        (datetime(2024, 1, 1, 23, 30, tzinfo=UTC), "22:00", "08:00", 30600),
        (datetime(2024, 1, 1, 4, 0, tzinfo=UTC), "22:00", "08:00", 14400),
        (datetime(2024, 1, 1, 12, 0, tzinfo=UTC), "22:00", "08:00", 0),
        (datetime(2024, 1, 1, 12, 0, tzinfo=UTC), "10:00", "14:00", 7200),
        (datetime(2024, 1, 1, 10, 0, tzinfo=UTC), "10:00", "14:00", 14400),
    ],
)
def test_dnd_remaining_arithmetic(now: datetime, dnd_start: str, dnd_end: str, expected: int) -> None:
    capability = _make_capability(dnd=True)
    status = _make_status(
        {DreameVacuumProperty.DND: 1, DreameVacuumProperty.DND_START: dnd_start, DreameVacuumProperty.DND_END: dnd_end},
        capability=capability,
    )
    with patch("custom_components.dreame_vacuum.dreame.device_status._core.datetime") as mock_datetime:
        mock_datetime.now.return_value = now
        assert status.dnd_remaining == expected


def test_dnd_remaining_none_when_dnd_disabled() -> None:
    capability = _make_capability(dnd=True)
    status = _make_status({DreameVacuumProperty.DND: 0}, capability=capability)
    assert status.dnd is False
    assert status.dnd_remaining is None


def test_dnd_remaining_none_when_start_or_end_missing() -> None:
    capability = _make_capability(dnd=True)
    status = _make_status({DreameVacuumProperty.DND: 1}, capability=capability)
    assert status.dnd_start is None
    assert status.dnd_remaining is None


# ---------------------------------------------------------------------------
# Simple boolean passthroughs
# ---------------------------------------------------------------------------


def test_ai_property_passthroughs_true() -> None:
    status = _make_status(
        ai_properties={
            DreameVacuumAIProperty.AI_OBSTACLE_DETECTION: 1,
            DreameVacuumAIProperty.AI_PET_DETECTION: 1,
            DreameVacuumAIProperty.AI_FURNITURE_DETECTION: 1,
            DreameVacuumAIProperty.AI_FLUID_DETECTION: 1,
            DreameVacuumAIProperty.AI_OBSTACLE_PICTURE: 1,
            DreameVacuumAIProperty.AI_OBSTACLE_IMAGE_UPLOAD: 1,
        }
    )
    assert status.ai_obstacle_detection is True
    assert status.ai_pet_detection is True
    assert status.ai_furniture_detection is True
    assert status.ai_fluid_detection is True
    assert status.ai_obstacle_picture is True
    assert status.ai_obstacle_image_upload is True


def test_ai_property_passthroughs_false_when_missing() -> None:
    status = _make_status()
    assert status.ai_obstacle_detection is False
    assert status.ai_pet_detection is False
    assert status.ai_furniture_detection is False
    assert status.ai_fluid_detection is False
    assert status.ai_obstacle_picture is False
    assert status.ai_obstacle_image_upload is False


def test_fill_light_true() -> None:
    status = _make_status(auto_switch_properties={DreameVacuumAutoSwitchProperty.FILL_LIGHT: 1})
    assert status.fill_light is True


def test_stain_avoidance_requires_exact_value_two() -> None:
    status_true = _make_status(auto_switch_properties={DreameVacuumAutoSwitchProperty.STAIN_AVOIDANCE: 2})
    status_false = _make_status(auto_switch_properties={DreameVacuumAutoSwitchProperty.STAIN_AVOIDANCE: 1})
    assert status_true.stain_avoidance is True
    assert status_false.stain_avoidance is False


def test_pet_focused_cleaning_truthy_passthrough() -> None:
    status = _make_status(auto_switch_properties={DreameVacuumAutoSwitchProperty.PET_FOCUSED_CLEANING: 1})
    assert status.pet_focused_cleaning is True
    status_off = _make_status()
    assert status_off.pet_focused_cleaning is False


def test_uv_sterilization_requires_capability_and_value() -> None:
    capability = _make_capability(uv_sterilization=True)
    status = _make_status(
        capability=capability, auto_switch_properties={DreameVacuumAutoSwitchProperty.UV_STERILIZATION: 1}
    )
    assert status.uv_sterilization is True
    status_off = _make_status(auto_switch_properties={DreameVacuumAutoSwitchProperty.UV_STERILIZATION: 1})
    assert status_off.uv_sterilization is False


def test_max_suction_power_requires_capability_and_value() -> None:
    # max_suction_power (status) reads MAX_SUCTION_POWER via plain get_property (see source).
    capability = _make_capability(max_suction_power=True)
    status = _make_status({DreameVacuumAutoSwitchProperty.MAX_SUCTION_POWER: 1}, capability=capability)
    assert status.max_suction_power is True


def test_ultra_clean_mode_requires_capability_and_value() -> None:
    capability = _make_capability(ultra_clean_mode=True)
    status = _make_status({DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE: 1}, capability=capability)
    assert status.ultra_clean_mode is True


def test_mop_extend_requires_capability_and_value() -> None:
    # capability.mop_extend is a *computed* property (mop_pad_swing and the auto-switch
    # value being non-None); the capability's own throwaway device auto-mocks a non-None
    # auto-switch value, so setting mop_pad_swing alone makes it resolve True.
    capability = _make_capability(mop_pad_swing=True)
    assert capability.mop_extend is True
    status = _make_status({DreameVacuumAutoSwitchProperty.MOP_EXTEND: 1}, capability=capability)
    assert status.mop_extend is True


def test_smart_mop_washing_requires_capability_and_value() -> None:
    capability = _make_capability(smart_mop_washing=True)
    status = _make_status({DreameVacuumProperty.SMART_MOP_WASHING: 1}, capability=capability)
    assert status.smart_mop_washing is True


def test_custom_mopping_mode_requires_capability_and_value() -> None:
    capability = _make_capability(mopping_settings=True)
    status = _make_status({DreameVacuumAutoSwitchProperty.CUSTOM_MOPPING_MODE: 1}, capability=capability)
    assert status.custom_mopping_mode is True


def test_multi_map_truthy_passthrough() -> None:
    status = _make_status({DreameVacuumProperty.MULTI_FLOOR_MAP: 1})
    assert status.multi_map is True
    status_off = _make_status({DreameVacuumProperty.MULTI_FLOOR_MAP: 0})
    assert status_off.multi_map is False


def test_self_clean_requires_exact_value_one() -> None:
    status = _make_status({DreameVacuumProperty.SELF_CLEAN: 1})
    assert status.self_clean is True
    status_off = _make_status({DreameVacuumProperty.SELF_CLEAN: 2})
    assert status_off.self_clean is False


def test_auto_water_refilling_enabled_requires_exact_value_one() -> None:
    status = _make_status({DreameVacuumProperty.AUTO_WATER_REFILLING: 1})
    assert status.auto_water_refilling_enabled is True


def test_auto_add_detergent_true_for_one_or_three() -> None:
    status_one = _make_status({DreameVacuumProperty.AUTO_ADD_DETERGENT: 1})
    status_three = _make_status({DreameVacuumProperty.AUTO_ADD_DETERGENT: 3})
    status_two = _make_status({DreameVacuumProperty.AUTO_ADD_DETERGENT: 2})
    assert status_one.auto_add_detergent is True
    assert status_three.auto_add_detergent is True
    assert status_two.auto_add_detergent is False


def test_cleaning_paused_truthy_passthrough() -> None:
    status = _make_status({DreameVacuumProperty.CLEANING_PAUSED: 1})
    assert status.cleaning_paused is True


def test_carpet_recognition_requires_capability_and_value() -> None:
    capability = _make_capability(carpet_recognition=True)
    status = _make_status({DreameVacuumProperty.CARPET_RECOGNITION: 1}, capability=capability)
    assert status.carpet_recognition is True
    status_off = _make_status({DreameVacuumProperty.CARPET_RECOGNITION: 1})
    assert status_off.carpet_recognition is False


def test_resume_cleaning_without_auto_charging() -> None:
    status = _make_status({DreameVacuumProperty.RESUME_CLEANING: 1})
    assert status.resume_cleaning is True
    status_wrong = _make_status({DreameVacuumProperty.RESUME_CLEANING: 2})
    assert status_wrong.resume_cleaning is False


def test_resume_cleaning_with_auto_charging() -> None:
    capability = _make_capability(auto_charging=True)
    status = _make_status({DreameVacuumProperty.RESUME_CLEANING: 2}, capability=capability)
    assert status.resume_cleaning is True


def test_auto_mount_mop_requires_capability_and_value() -> None:
    capability = _make_capability(mop_pad_unmounting=True)
    status = _make_status({DreameVacuumProperty.AUTO_MOUNT_MOP: 1}, capability=capability)
    assert status.auto_mount_mop is True


def test_camera_light_brightness_numeric() -> None:
    capability = _make_capability(camera_streaming=True)
    status = _make_status({DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS: "50"}, capability=capability)
    assert status.camera_light_brightness == 50


def test_camera_light_brightness_zero_is_falsy_none() -> None:
    capability = _make_capability(camera_streaming=True)
    status = _make_status({DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS: 0}, capability=capability)
    assert status.camera_light_brightness is None


def test_camera_light_brightness_non_numeric_is_none() -> None:
    capability = _make_capability(camera_streaming=True)
    status = _make_status({DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS: "abc"}, capability=capability)
    assert status.camera_light_brightness is None


def test_camera_light_brightness_capability_off_is_none() -> None:
    status = _make_status({DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS: "50"})
    assert status.camera_light_brightness is None


def test_faults_blank_string_becomes_zero() -> None:
    status_empty = _make_status({DreameVacuumProperty.FAULTS: ""})
    status_space = _make_status({DreameVacuumProperty.FAULTS: " "})
    assert status_empty.faults == 0
    assert status_space.faults == 0


def test_faults_non_blank_passthrough() -> None:
    status = _make_status({DreameVacuumProperty.FAULTS: "E11"})
    assert status.faults == "E11"


def test_low_water_requires_self_wash_base_and_no_refilling() -> None:
    capability = _make_capability(self_wash_base=True)
    status = _make_status(
        {DreameVacuumProperty.LOW_WATER_WARNING: DreameVacuumLowWaterWarning.LOW_WATER.value}, capability=capability
    )
    assert status.auto_water_refilling_enabled is False
    assert status.low_water is True


def test_low_water_false_when_refilling_enabled() -> None:
    capability = _make_capability(self_wash_base=True)
    status = _make_status(
        {
            DreameVacuumProperty.LOW_WATER_WARNING: DreameVacuumLowWaterWarning.LOW_WATER.value,
            DreameVacuumProperty.AUTO_WATER_REFILLING: 1,
        },
        capability=capability,
    )
    assert status.low_water is False


def test_low_water_false_no_warning() -> None:
    capability = _make_capability(self_wash_base=True)
    status = _make_status(
        {DreameVacuumProperty.LOW_WATER_WARNING: DreameVacuumLowWaterWarning.NO_WARNING.value}, capability=capability
    )
    assert status.low_water is False


def test_scheduled_clean_true_when_started() -> None:
    status = _make_status({DreameVacuumProperty.SCHEDULED_CLEAN: 1})
    assert status.started is True
    assert status.scheduled_clean is True


def test_scheduled_clean_false_when_not_started() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.SCHEDULED_CLEAN: 1}))
    assert status.scheduled_clean is False


def test_scheduled_clean_false_for_unmatched_value() -> None:
    status = _make_status({DreameVacuumProperty.SCHEDULED_CLEAN: 3})
    assert status.scheduled_clean is False


def test_mop_in_station_true_when_not_docked() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.MOP_IN_STATION: 1}))
    assert status.docked is False
    assert status.mop_in_station is True


def test_mop_in_station_false_when_docked() -> None:
    status = _make_status(
        {
            DreameVacuumProperty.MOP_IN_STATION: 1,
            DreameVacuumProperty.CHARGING_STATUS: DreameVacuumChargingStatus.CHARGING.value,
            DreameVacuumProperty.BATTERY_LEVEL: 50,
        }
    )
    assert status.docked is True
    assert status.mop_in_station is False


def test_self_clean_by_time_true() -> None:
    capability = _make_capability(self_clean_frequency=True)
    status = _make_status(
        capability=capability, auto_switch_properties={DreameVacuumAutoSwitchProperty.SELF_CLEAN_FREQUENCY: 2}
    )
    status.self_clean_value = 20
    assert status.self_clean_by_time is True


def test_self_clean_by_time_false_when_value_falsy() -> None:
    capability = _make_capability(self_clean_frequency=True)
    status = _make_status(
        capability=capability, auto_switch_properties={DreameVacuumAutoSwitchProperty.SELF_CLEAN_FREQUENCY: 2}
    )
    status.self_clean_value = 0
    assert status.self_clean_by_time is False


def test_auto_emptying_true() -> None:
    status = _make_status({DreameVacuumProperty.AUTO_EMPTY_STATUS: DreameVacuumAutoEmptyStatus.ACTIVE.value})
    assert status.auto_emptying is True


def test_auto_emptying_not_performed_true() -> None:
    status = _make_status({DreameVacuumProperty.AUTO_EMPTY_STATUS: DreameVacuumAutoEmptyStatus.NOT_PERFORMED.value})
    assert status.auto_emptying_not_performed is True


def test_customized_cleaning_true() -> None:
    status = _make_status({DreameVacuumProperty.CUSTOMIZED_CLEANING: 1})
    # has_saved_map defaults True (no map manager), cleangenius_cleaning defaults False.
    assert status.has_saved_map is True
    assert status.customized_cleaning is True


def test_customized_cleaning_false_when_property_unset() -> None:
    status = _make_status({})
    assert status.customized_cleaning is False


def test_cleangenius_cleaning_true() -> None:
    # cleangenius_cleaning (status) reads CLEANGENIUS via plain get_property (see source).
    capability = _make_capability(cleangenius=True, mop_pad_unmounting=True)
    status = _make_status(
        {
            DreameVacuumProperty.MOP_PAD_INSTALLED: 0,
            DreameVacuumAutoSwitchProperty.CLEANGENIUS: 1,
        },
        capability=capability,
    )
    assert status.mop_pad_installed is True
    assert status.cleangenius_cleaning is True


def test_cleangenius_cleaning_false_without_capability() -> None:
    status = _make_status({DreameVacuumAutoSwitchProperty.CLEANGENIUS: 1})
    assert status.cleangenius_cleaning is False


# ---------------------------------------------------------------------------
# hot_washing / auto_drying / smart_drying / silent_drying
# ---------------------------------------------------------------------------


def test_hot_washing_via_water_temperature_capability() -> None:
    capability = _make_capability(water_temperature=True)
    status = _make_status(
        {DreameVacuumProperty.HOT_WATER_STATUS: DreameVacuumHotWaterStatus.ENABLED.value}, capability=capability
    )
    assert status.hot_washing is True


def test_hot_washing_false_when_disabled_water_temperature() -> None:
    capability = _make_capability(water_temperature=True)
    status = _make_status(
        {DreameVacuumProperty.HOT_WATER_STATUS: DreameVacuumHotWaterStatus.DISABLED.value}, capability=capability
    )
    assert status.hot_washing is False


def test_hot_washing_via_auto_switch_capability() -> None:
    capability = _make_capability(hot_washing=True)
    status = _make_status(capability=capability, auto_switch_properties={DreameVacuumAutoSwitchProperty.HOT_WASHING: 1})
    assert status.hot_washing is True


def test_auto_drying_false_without_self_wash_base() -> None:
    status = _make_status({DreameVacuumProperty.INTELLIGENT_RECOGNITION: 1})
    assert status.auto_drying is False


def test_auto_drying_via_intelligent_recognition() -> None:
    capability = _make_capability(self_wash_base=True)
    status = _make_status({DreameVacuumProperty.INTELLIGENT_RECOGNITION: 1}, capability=capability)
    assert status.auto_drying is True


def test_auto_drying_via_auto_switch_settings() -> None:
    capability = _make_capability(self_wash_base=True, auto_switch_settings=True)
    status = _make_status(capability=capability, auto_switch_properties={DreameVacuumAutoSwitchProperty.AUTO_DRYING: 1})
    assert status.auto_drying is True


def test_smart_drying_requires_capability_and_value() -> None:
    capability = _make_capability(smart_drying=True)
    status = _make_status(
        capability=capability, auto_switch_properties={DreameVacuumAutoSwitchProperty.SMART_DRYING: 1}
    )
    assert status.smart_drying is True
    status_off = _make_status(auto_switch_properties={DreameVacuumAutoSwitchProperty.SMART_DRYING: 1})
    assert status_off.smart_drying is False


def test_silent_drying_requires_capability_and_value() -> None:
    capability = _make_capability(silent_drying=True)
    status = _make_status({DreameVacuumProperty.SILENT_DRYING: 1}, capability=capability)
    assert status.silent_drying is True


# ---------------------------------------------------------------------------
# maximum_maps / stream_status_name / dust_collection_available
# ---------------------------------------------------------------------------


def test_maximum_maps_one_when_no_lidar() -> None:
    capability = _make_capability(lidar_navigation=False)
    status = _make_status(capability=capability)
    assert status.maximum_maps == 1


def test_maximum_maps_one_when_multi_map_disabled() -> None:
    capability = _make_capability(lidar_navigation=True)
    status = _make_status(capability=capability)
    assert status.multi_map is False
    assert status.maximum_maps == 1


def test_maximum_maps_four_with_wifi_map() -> None:
    capability = _make_capability(lidar_navigation=True, wifi_map=True)
    status = _make_status({DreameVacuumProperty.MULTI_FLOOR_MAP: 1}, capability=capability)
    assert status.maximum_maps == 4


def test_maximum_maps_three_without_wifi_map() -> None:
    capability = _make_capability(lidar_navigation=True)
    status = _make_status({DreameVacuumProperty.MULTI_FLOOR_MAP: 1}, capability=capability)
    assert status.maximum_maps == 3


def test_stream_status_name_unknown_when_none() -> None:
    status = _make_status()
    assert status.stream_status is None
    assert status.stream_status_name == STATE_UNKNOWN


def test_dust_collection_available_true_via_raw_property() -> None:
    status = _make_status(_not_started_properties({DreameVacuumProperty.DUST_COLLECTION: 1}))
    assert status.dust_collection_available is True


def test_dust_collection_available_false_by_default() -> None:
    status = _make_status(_not_started_properties())
    assert status.dust_collection_available is False


# ---------------------------------------------------------------------------
# Simple pass-through numeric properties
# ---------------------------------------------------------------------------


def test_serial_number_passthrough() -> None:
    status = _make_status({DreameVacuumProperty.SERIAL_NUMBER: 123456})
    assert status.serial_number == 123456


def test_battery_level_passthrough() -> None:
    status = _make_status({DreameVacuumProperty.BATTERY_LEVEL: 0})
    assert status.battery_level == 0
    status_full = _make_status({DreameVacuumProperty.BATTERY_LEVEL: 100})
    assert status_full.battery_level == 100


def test_wetness_level_passthrough() -> None:
    status = _make_status({DreameVacuumProperty.WETNESS_LEVEL: 17})
    assert status.wetness_level == 17
