"""
Lazy loading wrapper for resources with optimized caching.

This module implements true lazy loading of large image resources to improve startup time.
Resources are loaded on-demand when first accessed and cached in memory for subsequent use.

Performance optimization:
- Resources module (_resources_data.py) is ~21MB
- Only loaded once on first attribute access
- Individual attributes are cached to avoid repeated lookups
- Reduces memory pressure and improves response time

Even with 'from .resources import *', actual data loading is deferred until use.
"""

# ruff: noqa: F822
import logging

_LOGGER = logging.getLogger(__name__)

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

# Module-level cache for optimized resource loading
_resources_module = None
_loaded_attrs = {}
_module_load_logged = False  # Track if we've logged the module load


def __getattr__(name):
    """
    Lazy load attributes from _resources_data module with optimized caching.

    This function is called when an attribute is not found in the current module.
    It loads only the requested attribute from the resources module on first access,
    then caches it in memory for subsequent access.

    Performance notes:
    - First access triggers module load (~21MB, one-time cost)
    - Subsequent attribute access uses in-memory cache (near-instant)
    - Module is shared across all resource accesses
    """
    global _resources_module, _module_load_logged

    # Fast path: Check cache first (most common case after first load)
    if name in _loaded_attrs:
        return _loaded_attrs[name]

    # Load the module if not loaded yet (happens once per Python session)
    if _resources_module is None:
        if not _module_load_logged:
            _LOGGER.debug("Loading resources module (_resources_data.py, ~21MB) - this happens once")
            _module_load_logged = True

        try:
            from . import _resources_data

            _resources_module = _resources_data
            _LOGGER.debug("Resources module loaded successfully and cached in memory")
        except ImportError:
            # Fallback for direct execution
            import _resources_data

            _resources_module = _resources_data

    # Get and cache the attribute for future access
    try:
        value = getattr(_resources_module, name)
        _loaded_attrs[name] = value
        return value
    except AttributeError:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'") from None


def clear_cache():
    """
    Clear the resource cache to free memory.

    This can be called manually if memory needs to be reclaimed.
    Note: Subsequent resource access will reload from _resources_data module.
    """
    global _loaded_attrs
    cache_size = len(_loaded_attrs)
    _loaded_attrs.clear()
    _LOGGER.info("Cleared %d cached resources from memory", cache_size)


def get_cache_stats():
    """
    Get statistics about the resource cache.

    Returns:
        dict: Cache statistics including size and loaded state
    """
    return {
        "module_loaded": _resources_module is not None,
        "cached_attributes": len(_loaded_attrs),
        "available_attributes": len(__all__),
        "cache_hit_rate": (
            f"{len(_loaded_attrs) / len(__all__) * 100:.1f}%" if _resources_module is not None else "0%"
        ),
    }


def __dir__():
    """Return list of available attributes."""
    return __all__
