"""Entity service registration for the Dreame Vacuum integration.

Services are registered once from the integration's async_setup (quality
scale rule action-setup). Entity methods are referenced by name so this
module never imports the platform modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_platform_entity_service
import voluptuous as vol

from .const import (
    CONSUMABLE_DEODORIZER,
    CONSUMABLE_DETERGENT,
    CONSUMABLE_DIRTY_WATER_TANK,
    CONSUMABLE_FILTER,
    CONSUMABLE_MAIN_BRUSH,
    CONSUMABLE_MOP_PAD,
    CONSUMABLE_ONBOARD_DIRTY_WATER_TANK,
    CONSUMABLE_SCALE_INHIBITOR,
    CONSUMABLE_SENSOR,
    CONSUMABLE_SIDE_BRUSH,
    CONSUMABLE_SILVER_ION,
    CONSUMABLE_SQUEEGEE,
    CONSUMABLE_TANK_FILTER,
    CONSUMABLE_WHEEL,
    DOMAIN,
    INPUT_CARPET_ARRAY,
    INPUT_CARPET_CLEANING,
    INPUT_CARPET_SETTINGS,
    INPUT_CLEANING_MODE,
    INPUT_CLEANING_ROUTE,
    INPUT_CLEANING_SEQUENCE,
    INPUT_CONSUMABLE,
    INPUT_CUSTOM_MOPPING_ROUTE,
    INPUT_CYCLE,
    INPUT_FILE_URL,
    INPUT_ID,
    INPUT_IGNORED_CARPET_ARRAY,
    INPUT_KEY,
    INPUT_LANGUAGE_ID,
    INPUT_LINE,
    INPUT_MAP_ID,
    INPUT_MAP_NAME,
    INPUT_MD5,
    INPUT_MOP_ARRAY,
    INPUT_OBSTACLE_IGNORED,
    INPUT_POINTS,
    INPUT_RECOVERY_MAP_INDEX,
    INPUT_REPEATS,
    INPUT_ROTATION,
    INPUT_SEGMENT,
    INPUT_SEGMENT_ID,
    INPUT_SEGMENT_NAME,
    INPUT_SEGMENTS_ARRAY,
    INPUT_SHORTCUT_ID,
    INPUT_SHORTCUT_NAME,
    INPUT_SIZE,
    INPUT_SUCTION_LEVEL,
    INPUT_TYPE,
    INPUT_URL,
    INPUT_VALUE,
    INPUT_VELOCITY,
    INPUT_VIRTUAL_THRESHOLD_ARRAY,
    INPUT_WALL_ARRAY,
    INPUT_WATER_VOLUME,
    INPUT_WETNESS_LEVEL,
    INPUT_X,
    INPUT_Y,
    INPUT_ZONE,
    INPUT_ZONE_ARRAY,
    SERVICE_BACKUP_MAP,
    SERVICE_CALL_ACTION,
    SERVICE_CLEAN_SEGMENT,
    SERVICE_CLEAN_SPOT,
    SERVICE_CLEAN_ZONE,
    SERVICE_DELETE_MAP,
    SERVICE_DISCARD_TEMPORARY_MAP,
    SERVICE_FOLLOW_PATH,
    SERVICE_GOTO,
    SERVICE_INSTALL_VOICE_PACK,
    SERVICE_MERGE_SEGMENTS,
    SERVICE_MOVE_REMOTE_CONTROL_STEP,
    SERVICE_RENAME_MAP,
    SERVICE_RENAME_SEGMENT,
    SERVICE_RENAME_SHORTCUT,
    SERVICE_REPLACE_TEMPORARY_MAP,
    SERVICE_REQUEST_MAP,
    SERVICE_RESET_CONSUMABLE,
    SERVICE_RESTORE_MAP,
    SERVICE_RESTORE_MAP_FROM_FILE,
    SERVICE_SAVE_TEMPORARY_MAP,
    SERVICE_SELECT_FIRST,
    SERVICE_SELECT_LAST,
    SERVICE_SELECT_MAP,
    SERVICE_SELECT_NEXT,
    SERVICE_SELECT_PREVIOUS,
    SERVICE_SET_CARPET_AREA,
    SERVICE_SET_CLEANING_SEQUENCE,
    SERVICE_SET_CUSTOM_CARPET_CLEANING,
    SERVICE_SET_CUSTOM_CLEANING,
    SERVICE_SET_OBSTACLE_IGNORE,
    SERVICE_SET_PREDEFINED_POINTS,
    SERVICE_SET_PROPERTY,
    SERVICE_SET_RESTRICTED_ZONE,
    SERVICE_SET_ROUTER_POSITION,
    SERVICE_SET_VIRTUAL_THRESHOLD,
    SERVICE_SPLIT_SEGMENTS,
    SERVICE_START_SHORTCUT,
)

if TYPE_CHECKING:
    from homeassistant.helpers.typing import VolDictType


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register all entity services of the integration."""

    def register(
        service_name: str,
        schema: VolDictType | None,
        func: str,
        *,
        entity_domain: str = "vacuum",
    ) -> None:
        async_register_platform_entity_service(
            hass,
            DOMAIN,
            service_name,
            entity_domain=entity_domain,
            func=func,
            schema=schema,
        )

    register(
        SERVICE_REQUEST_MAP,
        {},
        "async_request_map",
    )

    register(
        SERVICE_SELECT_MAP,
        {
            vol.Required(INPUT_MAP_ID): cv.positive_int,
        },
        "async_select_map",
    )

    register(
        SERVICE_DELETE_MAP,
        {
            vol.Optional(INPUT_MAP_ID): cv.positive_int,
        },
        "async_delete_map",
    )

    register(
        SERVICE_SAVE_TEMPORARY_MAP,
        {},
        "async_save_temporary_map",
    )

    register(
        SERVICE_DISCARD_TEMPORARY_MAP,
        {},
        "async_discard_temporary_map",
    )

    register(
        SERVICE_REPLACE_TEMPORARY_MAP,
        {
            vol.Optional(INPUT_MAP_ID): cv.positive_int,
        },
        "async_replace_temporary_map",
    )

    register(
        SERVICE_CLEAN_ZONE,
        {
            vol.Required(INPUT_ZONE): vol.Any(
                [
                    vol.ExactSequence(
                        [
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                        ]
                    )
                ],
                vol.ExactSequence(
                    [
                        vol.Coerce(int),
                        vol.Coerce(int),
                        vol.Coerce(int),
                        vol.Coerce(int),
                    ]
                ),
            ),
            vol.Optional(INPUT_REPEATS): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
            vol.Optional(INPUT_SUCTION_LEVEL): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
            vol.Optional(INPUT_WATER_VOLUME): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
        },
        "async_clean_zone",
    )

    register(
        SERVICE_CLEAN_SEGMENT,
        {
            vol.Required(INPUT_SEGMENTS_ARRAY): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
            vol.Optional(INPUT_REPEATS): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
            vol.Optional(INPUT_SUCTION_LEVEL): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
            vol.Optional(INPUT_WATER_VOLUME): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
        },
        "async_clean_segment",
    )

    register(
        SERVICE_CLEAN_SPOT,
        {
            vol.Required(INPUT_POINTS): vol.Any(
                [
                    vol.ExactSequence(
                        [
                            vol.Coerce(int),
                            vol.Coerce(int),
                        ]
                    )
                ],
                vol.ExactSequence(
                    [
                        vol.Coerce(int),
                        vol.Coerce(int),
                    ]
                ),
            ),
            vol.Optional(INPUT_REPEATS): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
            vol.Optional(INPUT_SUCTION_LEVEL): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
            vol.Optional(INPUT_WATER_VOLUME): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
        },
        "async_clean_spot",
    )

    register(
        SERVICE_GOTO,
        {
            vol.Required(INPUT_X): vol.All(vol.Coerce(int)),
            vol.Required(INPUT_Y): vol.All(vol.Coerce(int)),
        },
        "async_goto",
    )

    register(
        SERVICE_FOLLOW_PATH,
        {
            vol.Optional(INPUT_POINTS): vol.All(
                list,
                [
                    vol.ExactSequence(
                        [
                            vol.Coerce(int),
                            vol.Coerce(int),
                        ]
                    )
                ],
            ),
        },
        "async_follow_path",
    )

    register(
        SERVICE_START_SHORTCUT,
        {
            vol.Required(INPUT_SHORTCUT_ID): vol.All(vol.Coerce(int)),
        },
        "async_start_shortcut",
    )

    register(
        SERVICE_SET_RESTRICTED_ZONE,
        {
            vol.Optional(INPUT_WALL_ARRAY): vol.All(
                list,
                [
                    vol.ExactSequence(
                        [
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                        ]
                    )
                ],
            ),
            vol.Optional(INPUT_ZONE_ARRAY): vol.All(
                list,
                [
                    vol.ExactSequence(
                        [
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                        ]
                    )
                ],
            ),
            vol.Optional(INPUT_MOP_ARRAY): vol.All(
                list,
                [
                    vol.ExactSequence(
                        [
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                        ]
                    )
                ],
            ),
        },
        "async_set_restricted_zone",
    )

    register(
        SERVICE_SET_CARPET_AREA,
        {
            vol.Optional(INPUT_CARPET_ARRAY): vol.All(
                list,
                [
                    vol.ExactSequence(
                        [
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                        ]
                    )
                ],
            ),
            vol.Optional(INPUT_IGNORED_CARPET_ARRAY): vol.All(
                list,
                [
                    vol.ExactSequence(
                        [
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                        ]
                    )
                ],
            ),
        },
        "async_set_carpet_area",
    )

    register(
        SERVICE_SET_VIRTUAL_THRESHOLD,
        {
            vol.Optional(INPUT_VIRTUAL_THRESHOLD_ARRAY): vol.All(
                list,
                [
                    vol.ExactSequence(
                        [
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                            vol.Coerce(int),
                        ]
                    )
                ],
            ),
        },
        "async_set_virtual_threshold",
    )

    register(
        SERVICE_SET_PREDEFINED_POINTS,
        {
            vol.Optional(INPUT_POINTS): vol.All(
                list,
                [
                    vol.ExactSequence(
                        [
                            vol.Coerce(int),
                            vol.Coerce(int),
                        ]
                    )
                ],
            ),
        },
        "async_set_predefined_points",
    )

    register(
        SERVICE_MOVE_REMOTE_CONTROL_STEP,
        {
            vol.Required(INPUT_VELOCITY): vol.All(vol.Coerce(int), vol.Clamp(min=-600, max=600)),
            vol.Required(INPUT_ROTATION): vol.All(vol.Coerce(int), vol.Clamp(min=-360, max=360)),
            vol.Optional("prompt"): cv.boolean,
        },
        "async_remote_control_move_step",
    )

    register(
        SERVICE_INSTALL_VOICE_PACK,
        {
            vol.Required(INPUT_LANGUAGE_ID): cv.string,
            vol.Required(INPUT_URL): cv.url,
            vol.Required(INPUT_MD5): cv.string,
            vol.Required(INPUT_SIZE): cv.positive_int,
        },
        "async_install_voice_pack",
    )

    register(
        SERVICE_RENAME_MAP,
        {
            vol.Required(INPUT_MAP_ID): cv.positive_int,
            vol.Required(INPUT_MAP_NAME): cv.string,
        },
        "async_rename_map",
    )

    register(
        SERVICE_RESTORE_MAP,
        {
            vol.Required(INPUT_RECOVERY_MAP_INDEX): cv.positive_int,
            vol.Optional(INPUT_MAP_ID): cv.positive_int,
        },
        "async_restore_map",
    )

    register(
        SERVICE_RESTORE_MAP_FROM_FILE,
        {
            vol.Required(INPUT_FILE_URL): cv.url,
            vol.Optional(INPUT_MAP_ID): cv.positive_int,
        },
        "async_restore_map_from_file",
    )

    register(
        SERVICE_BACKUP_MAP,
        {
            vol.Optional(INPUT_MAP_ID): cv.positive_int,
        },
        "async_backup_map",
    )

    register(
        SERVICE_MERGE_SEGMENTS,
        {
            vol.Optional(INPUT_MAP_ID): cv.positive_int,
            vol.Required(INPUT_SEGMENTS_ARRAY): vol.All([vol.Coerce(int)], vol.Length(min=2, max=2)),
        },
        "async_merge_segments",
    )

    register(
        SERVICE_SPLIT_SEGMENTS,
        {
            vol.Optional(INPUT_MAP_ID): cv.positive_int,
            vol.Required(INPUT_SEGMENT): vol.All(vol.Coerce(int)),
            vol.Required(INPUT_LINE): vol.All(
                list,
                vol.ExactSequence(
                    [
                        vol.Coerce(int),
                        vol.Coerce(int),
                        vol.Coerce(int),
                        vol.Coerce(int),
                    ]
                ),
            ),
        },
        "async_split_segments",
    )

    register(
        SERVICE_RENAME_SEGMENT,
        {
            vol.Required(INPUT_SEGMENT_ID): cv.positive_int,
            vol.Required(INPUT_SEGMENT_NAME): cv.string,
        },
        "async_rename_segment",
    )

    register(
        SERVICE_SET_CLEANING_SEQUENCE,
        {
            vol.Required(INPUT_CLEANING_SEQUENCE): cv.ensure_list,
        },
        "async_set_cleaning_sequence",
    )

    register(
        SERVICE_SET_CUSTOM_CLEANING,
        {
            vol.Required(INPUT_SEGMENT_ID): cv.ensure_list,
            vol.Required(INPUT_SUCTION_LEVEL): cv.ensure_list,
            vol.Required(INPUT_WATER_VOLUME): cv.ensure_list,
            vol.Required(INPUT_REPEATS): cv.ensure_list,
            vol.Optional(INPUT_CLEANING_MODE): cv.ensure_list,
            vol.Optional(INPUT_CUSTOM_MOPPING_ROUTE): cv.ensure_list,
            vol.Optional(INPUT_CLEANING_ROUTE): cv.ensure_list,
            vol.Optional(INPUT_WETNESS_LEVEL): cv.ensure_list,
        },
        "async_set_custom_cleaning",
    )

    register(
        SERVICE_SET_CUSTOM_CARPET_CLEANING,
        {
            vol.Required(INPUT_ID): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
            vol.Required(INPUT_TYPE): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
            vol.Optional(INPUT_CARPET_CLEANING): vol.Any(vol.Coerce(int), [vol.Coerce(int)]),
            vol.Optional(INPUT_CARPET_SETTINGS): vol.Any(
                [vol.Coerce(str)], [[vol.Coerce(str)]], [vol.Coerce(int)], [[vol.Coerce(int)]]
            ),
        },
        "async_set_custom_carpet_cleaning",
    )

    register(
        SERVICE_RESET_CONSUMABLE,
        {
            vol.Required(INPUT_CONSUMABLE): vol.In(
                [
                    CONSUMABLE_MAIN_BRUSH,
                    CONSUMABLE_SIDE_BRUSH,
                    CONSUMABLE_FILTER,
                    CONSUMABLE_TANK_FILTER,
                    CONSUMABLE_SENSOR,
                    CONSUMABLE_MOP_PAD,
                    CONSUMABLE_SILVER_ION,
                    CONSUMABLE_DETERGENT,
                    CONSUMABLE_SQUEEGEE,
                    CONSUMABLE_ONBOARD_DIRTY_WATER_TANK,
                    CONSUMABLE_DIRTY_WATER_TANK,
                    CONSUMABLE_DEODORIZER,
                    CONSUMABLE_WHEEL,
                    CONSUMABLE_SCALE_INHIBITOR,
                ]
            ),
        },
        "async_reset_consumable",
    )

    register(
        SERVICE_RENAME_SHORTCUT,
        {
            vol.Required(INPUT_SHORTCUT_ID): cv.positive_int,
            vol.Required(INPUT_SHORTCUT_NAME): cv.string,
        },
        "async_rename_shortcut",
    )

    register(
        SERVICE_SET_OBSTACLE_IGNORE,
        {
            vol.Required(INPUT_X): vol.All(vol.Coerce(float)),
            vol.Required(INPUT_Y): vol.All(vol.Coerce(float)),
            vol.Required(INPUT_OBSTACLE_IGNORED): cv.boolean,
        },
        "async_set_obstacle_ignore",
    )

    register(
        SERVICE_SET_ROUTER_POSITION,
        {
            vol.Required(INPUT_X): vol.All(vol.Coerce(int)),
            vol.Required(INPUT_Y): vol.All(vol.Coerce(int)),
        },
        "async_set_router_position",
    )

    register(
        SERVICE_SET_PROPERTY,
        {
            vol.Required(INPUT_KEY): cv.string,
            vol.Optional(INPUT_VALUE): vol.Any(vol.Coerce(int), vol.Coerce(str), vol.Coerce(bool)),
        },
        "async_set_property",
    )

    register(
        SERVICE_CALL_ACTION,
        {vol.Required(INPUT_KEY): cv.string, vol.Optional(INPUT_VALUE): cv.string},
        "async_call_action",
    )

    register(
        SERVICE_SELECT_NEXT,
        {vol.Optional(INPUT_CYCLE, default=True): bool},
        "async_next",
        entity_domain="select",
    )
    register(
        SERVICE_SELECT_PREVIOUS,
        {vol.Optional(INPUT_CYCLE, default=True): bool},
        "async_previous",
        entity_domain="select",
    )
    register(SERVICE_SELECT_FIRST, {}, "async_first", entity_domain="select")
    register(SERVICE_SELECT_LAST, {}, "async_last", entity_domain="select")
    register("update", {}, "async_update", entity_domain="camera")
