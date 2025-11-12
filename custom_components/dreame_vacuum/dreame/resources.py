"""
Lazy loading wrapper for resources.

This module implements true lazy loading of large image resources to improve startup time.
Resources are loaded on-demand when first accessed, even with 'from .resources import *'.
"""

# ruff: noqa: F822
# Auto-generated list of exported constants
__all__ = [
    "CONSUMABLE_IMAGE",
    "DEFAULT_MAP_DATA",
    "DEFAULT_MAP_DATA_IMAGE",
    "DEFAULT_MAP_IMAGE",
    "DRAINAGE_STATUS_FAIL",
    "DRAINAGE_STATUS_SUCCESS",
    "ERROR_IMAGE",
    "FURNITURE_TYPE_TO_ICON",
    "FURNITURE_TYPE_TO_IMAGE",
    "FURNITURE_V2_TYPE_MIJIA_TO_IMAGE",
    "FURNITURE_V2_TYPE_TO_ICON",
    "FURNITURE_V2_TYPE_TO_IMAGE",
    "MAP_CHARGER_IMAGE_DREAME",
    "MAP_CHARGER_IMAGE_MATERIAL",
    "MAP_CHARGER_IMAGE_MIJIA",
    "MAP_CHARGER_VSLAM_IMAGE_DREAME",
    "MAP_FONT",
    "MAP_FONT_LIGHT",
    "MAP_ICON_CLEAN",
    "MAP_ICON_CLEANING_MODE_DREAME",
    "MAP_ICON_CLEANING_MODE_MATERIAL",
    "MAP_ICON_CLEANING_MODE_MIJIA",
    "MAP_ICON_CLEANING_ROUTE_DREAME",
    "MAP_ICON_CLEANING_ROUTE_MATERIAL",
    "MAP_ICON_CRUISE_POINT_BG_DREAME",
    "MAP_ICON_CRUISE_POINT_DREAME",
    "MAP_ICON_CUSTOM_MOPPING_ROUTE_DREAME",
    "MAP_ICON_DELETE",
    "MAP_ICON_MOP_PAD_HUMIDITY_DREAME",
    "MAP_ICON_MOP_PAD_HUMIDITY_MATERIAL",
    "MAP_ICON_MOVE",
    "MAP_ICON_OBSTACLE_BG_DREAME",
    "MAP_ICON_OBSTACLE_HIDDEN_BG_DREAME",
    "MAP_ICON_PROBLEM",
    "MAP_ICON_REPEATS_DREAME",
    "MAP_ICON_REPEATS_MATERIAL",
    "MAP_ICON_REPEATS_MIJIA",
    "MAP_ICON_RESIZE",
    "MAP_ICON_ROTATE",
    "MAP_ICON_SELECTED_SEGMENT",
    "MAP_ICON_SETTINGS",
    "MAP_ICON_SUCTION_LEVEL_DREAME",
    "MAP_ICON_SUCTION_LEVEL_MATERIAL",
    "MAP_ICON_SUCTION_LEVEL_MIJIA",
    "MAP_ICON_WATER_VOLUME_DREAME",
    "MAP_ICON_WATER_VOLUME_MATERIAL",
    "MAP_ICON_WATER_VOLUME_MIJIA",
    "MAP_OPTIMIZER_JS",
    "MAP_ROBOT_CHARGING_IMAGE",
    "MAP_ROBOT_CLEANING_DIRECTION_IMAGE",
    "MAP_ROBOT_CLEANING_IMAGE",
    "MAP_ROBOT_DRYING_IMAGE",
    "MAP_ROBOT_EMPTYING_IMAGE",
    "MAP_ROBOT_HOT_DRYING_IMAGE",
    "MAP_ROBOT_HOT_WASHING_IMAGE",
    "MAP_ROBOT_LIDAR_IMAGE_DREAME_DARK",
    "MAP_ROBOT_LIDAR_IMAGE_DREAME_LIGHT",
    "MAP_ROBOT_LIDAR_IMAGE_MIJIA",
    "MAP_ROBOT_MOP_CLEANING_IMAGE",
    "MAP_ROBOT_MOP_IMAGE_DREAME",
    "MAP_ROBOT_MOP_IMAGE_MIJIA",
    "MAP_ROBOT_OBSTACLE_BOTTOM_LEFT_IMAGE",
    "MAP_ROBOT_OBSTACLE_BOTTOM_RIGHT_IMAGE",
    "MAP_ROBOT_OBSTACLE_TOP_LEFT_IMAGE",
    "MAP_ROBOT_OBSTACLE_TOP_RIGHT_IMAGE",
    "MAP_ROBOT_SLEEPING_IMAGE",
    "MAP_ROBOT_VSLAM_IMAGE_DREAME_DARK",
    "MAP_ROBOT_VSLAM_IMAGE_DREAME_LIGHT",
    "MAP_ROBOT_VSLAM_IMAGE_MIJIA",
    "MAP_ROBOT_WARNING_IMAGE",
    "MAP_ROBOT_WASHING_IMAGE",
    "MAP_WIFI_IMAGE_DREAME",
    "OBSTACLE_TYPE_TO_HIDDEN_ICON",
    "OBSTACLE_TYPE_TO_ICON",
    "SEGMENT_ICONS_DREAME",
    "SEGMENT_ICONS_DREAME_OLD",
    "SEGMENT_ICONS_MATERIAL",
    "SEGMENT_ICONS_MIJIA",
]

# Module-level cache
_resources_module = None
_loaded_attrs = {}


def __getattr__(name):
    """
    Lazy load attributes from _resources_data module.

    This function is called when an attribute is not found in the current module.
    It loads only the requested attribute from the resources module.
    """
    global _resources_module

    # Check cache first
    if name in _loaded_attrs:
        return _loaded_attrs[name]

    # Load the module if not loaded yet
    if _resources_module is None:
        try:
            from . import _resources_data
        except ImportError:
            import _resources_data
        _resources_module = _resources_data

    # Get and cache the attribute
    try:
        value = getattr(_resources_module, name)
        _loaded_attrs[name] = value
        return value
    except AttributeError:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'") from None


def __dir__():
    """Return list of available attributes."""
    return __all__
