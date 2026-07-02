"""
Lazy loading wrapper for resources with optimized caching.

This module implements true lazy loading of large image resources to improve startup time.
Resources are loaded on-demand when first accessed and cached in memory for subsequent use.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Re-export the lazily-loaded resource constants so static type checkers can
    # resolve ``from .resources import *``. At runtime these names are provided
    # on demand by ``__getattr__`` below; this block never executes and triggers
    # no eager import of the heavy backing modules.
    from ._notification_images import *
    from ._resources_data import *

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

# Attributes that live in the lightweight _notification_images.py module
# (~8.7MB). Everything else lives in the larger _resources_data.py (~12MB),
# which is only needed when the map renderer is active.
_NOTIFICATION_ATTRS: frozenset[str] = frozenset(
    {
        "CONSUMABLE_IMAGE",
        "DRAINAGE_STATUS_FAIL",
        "DRAINAGE_STATUS_SUCCESS",
        "ERROR_IMAGE",
        "FURNITURE_TYPE_TO_ICON",
        "FURNITURE_TYPE_TO_IMAGE",
        "FURNITURE_V2_TYPE_MIJIA_TO_IMAGE",
        "FURNITURE_V2_TYPE_TO_ICON",
        "FURNITURE_V2_TYPE_TO_IMAGE",
        "OBSTACLE_TYPE_TO_HIDDEN_ICON",
        "OBSTACLE_TYPE_TO_ICON",
        "SEGMENT_ICONS_DREAME",
        "SEGMENT_ICONS_DREAME_OLD",
        "SEGMENT_ICONS_MATERIAL",
        "SEGMENT_ICONS_MIJIA",
    }
)

# Module-level cache for optimized resource loading. Kept separate so that
# loading one backing module does not force the other to be parsed.
_notification_module = None
_resources_module = None
_loaded_attrs: dict[str, object] = {}
_notification_load_logged = False
_resources_load_logged = False


def __getattr__(name: str) -> Any:
    """Lazy-load a resource attribute from the appropriate backing module.

    Resources live in two sibling modules:
    - ``_notification_images.py`` (~8.7MB): notification and icon images
      referenced from the coordinator/device status.
    - ``_resources_data.py`` (~12MB): everything the map renderer needs
      (robot, charger, segment icons, map optimizer JS, fonts).

    Splitting them means a notification-only code path never parses the
    map-renderer module, and vice-versa.
    """
    global _notification_module, _resources_module
    global _notification_load_logged, _resources_load_logged

    # Fast path: in-memory cache hit
    if name in _loaded_attrs:
        return _loaded_attrs[name]

    is_notification = name in _NOTIFICATION_ATTRS

    if is_notification:
        if _notification_module is None:
            if not _notification_load_logged:
                _LOGGER.debug("Loading notification images module (_notification_images.py, ~8.7MB)")
                _notification_load_logged = True
            try:
                from . import _notification_images

                _notification_module = _notification_images
            except ImportError:
                import _notification_images  # type: ignore[import-not-found, no-redef]

                _notification_module = _notification_images
        module = _notification_module
    else:
        if _resources_module is None:
            if not _resources_load_logged:
                _LOGGER.debug("Loading resources module (_resources_data.py, ~12MB)")
                _resources_load_logged = True
            try:
                from . import _resources_data

                _resources_module = _resources_data
            except ImportError:
                import _resources_data  # type: ignore[import-not-found, no-redef]

                _resources_module = _resources_data
        module = _resources_module

    try:
        value = getattr(module, name)
    except AttributeError:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'") from None
    _loaded_attrs[name] = value
    return value


def __dir__() -> list[str]:
    """Return list of available attributes."""
    return __all__
