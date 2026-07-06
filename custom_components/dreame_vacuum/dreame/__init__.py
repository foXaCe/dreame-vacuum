"""
Dreame Vacuum library with optimized lazy imports.

This module uses lazy loading to reduce startup time. Only core classes
are imported immediately. Other types and constants are loaded on-demand.
"""

from __future__ import annotations

from typing import Any

VERSION = "v2.0.0b20"

# Core imports - always needed, imported immediately
# Using explicit re-exports to satisfy linters while maintaining public API
from .device import DreameVacuumDevice as DreameVacuumDevice
from .exceptions import (
    DeviceConnectionError as DeviceConnectionError,
    DeviceException as DeviceException,
    DeviceUpdateFailedException as DeviceUpdateFailedException,
    InvalidActionException as InvalidActionException,
    InvalidValueException as InvalidValueException,
    RateLimitError as RateLimitError,
)
from .protocol import DreameVacuumProtocol as DreameVacuumProtocol

# Lazy import cache
_lazy_imports: dict[str, object] = {}


def __getattr__(name: str) -> Any:
    """
    Lazy load attributes from const and types modules.

    This function is called when an attribute is not found in the current module.
    It loads attributes on-demand from const.py and types.py to improve startup time.
    """
    # Check cache first
    if name in _lazy_imports:
        return _lazy_imports[name]

    # A failing import of the backing modules must propagate with its real
    # traceback — swallowing it here would surface every symbol lookup as a
    # misleading AttributeError.
    from . import const, vacuum_types as types

    for module in (const, types):
        try:
            if hasattr(module, name):
                value = getattr(module, name)
                _lazy_imports[name] = value
                return value
        except AttributeError:
            pass

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__() -> list[str]:
    """Return list of available attributes including lazily loaded ones."""
    # Base attributes
    base_attrs = [
        "VERSION",
        "DreameVacuumDevice",
        "DreameVacuumProtocol",
        "DeviceConnectionError",
        "DeviceException",
        "DeviceUpdateFailedException",
        "InvalidActionException",
        "InvalidValueException",
        "RateLimitError",
    ]

    # Add commonly used types that might be imported
    # (These will be loaded on first access)
    lazy_attrs = [
        # From const
        "ACTION_TO_NAME",
        "CLEANING_MODE_CODE_TO_NAME",
        "CLEANING_ROUTE_TO_NAME",
        "CUSTOM_MOPPING_ROUTE_TO_NAME",
        "DEVICE_INFO",
        "FLOOR_MATERIAL_CODE_TO_NAME",
        "FLOOR_MATERIAL_DIRECTION_CODE_TO_NAME",
        "MOP_PAD_HUMIDITY_CODE_TO_NAME",
        "PROPERTY_TO_NAME",
        "SEGMENT_VISIBILITY_CODE_TO_NAME",
        "STATUS_CODE_TO_NAME",
        "SUCTION_LEVEL_CODE_TO_NAME",
        "SUCTION_LEVEL_QUIET",
        "WATER_VOLUME_CODE_TO_NAME",
        # From types
        "ACTION_AVAILABILITY",
        "MAP_COLOR_SCHEME_LIST",
        "MAP_ICON_SET_LIST",
        "PROPERTY_AVAILABILITY",
        "DreameVacuumAction",
        "DreameVacuumAIProperty",
        "DreameVacuumAutoEmptyMode",
        "DreameVacuumAutoEmptyStatus",
        "DreameVacuumAutoSwitchProperty",
        "DreameVacuumCarpetCleaning",
        "DreameVacuumCarpetSensitivity",
        "DreameVacuumCleanGenius",
        "DreameVacuumCleanGeniusMode",
        "DreameVacuumCleaningMode",
        "DreameVacuumCleaningRoute",
        "DreameVacuumCustomMoppingRoute",
        "DreameVacuumDrainageStatus",
        "DreameVacuumFloorMaterial",
        "DreameVacuumFloorMaterialDirection",
        "DreameVacuumLowWaterWarning",
        "DreameVacuumMopCleanFrequency",
        "DreameVacuumMopExtendFrequency",
        "DreameVacuumMopPadHumidity",
        "DreameVacuumMopPadSwing",
        "DreameVacuumMoppingType",
        "DreameVacuumMopWashLevel",
        "DreameVacuumProperty",
        "DreameVacuumRelocationStatus",
        "DreameVacuumSecondCleaning",
        "DreameVacuumSegmentVisibility",
        "DreameVacuumSelfCleanFrequency",
        "DreameVacuumState",
        "DreameVacuumStrAIProperty",
        "DreameVacuumStreamStatus",
        "DreameVacuumSuctionLevel",
        "DreameVacuumTaskStatus",
        "DreameVacuumTaskType",
        "DreameVacuumVoiceAssistantLanguage",
        "DreameVacuumWashingMode",
        "DreameVacuumWaterTemperature",
        "DreameVacuumWaterVolume",
        "DreameVacuumWiderCornerCoverage",
    ]

    return base_attrs + lazy_attrs
