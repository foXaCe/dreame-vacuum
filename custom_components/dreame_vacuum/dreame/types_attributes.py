"""Dreame Vacuum module-level attribute/name tables and ATTR_* constants."""

from __future__ import annotations

from typing import Final

SEGMENT_TYPE_CODE_TO_NAME: Final = {
    0: "Room",
    1: "Living Room",
    2: "Primary Bedroom",
    3: "Study",
    4: "Kitchen",
    5: "Dining Hall",
    6: "Bathroom",
    7: "Balcony",
    8: "Corridor",
    9: "Utility Room",
    10: "Closet",
    11: "Meeting Room",
    12: "Office",
    13: "Fitness Area",
    14: "Recreation Area",
    15: "Secondary Bedroom",
}

SEGMENT_TYPE_TRANSLATIONS: Final = {
    "fr": {
        0: "Pièce",
        1: "Salon",
        2: "Chambre",
        3: "Bureau",
        4: "Cuisine",
        5: "Salle à manger",
        6: "Salle de bain",
        7: "Balcon",
        8: "Couloir",
        9: "Buanderie",
        10: "Placard",
        11: "Salle de réunion",
        12: "Bureau",
        13: "Espace fitness",
        14: "Espace de loisirs",
        15: "Chambre secondaire",
    }
}

SEGMENT_TYPE_CODE_TO_HA_ICON: Final = {
    0: "mdi:home-outline",
    1: "mdi:sofa-outline",
    2: "mdi:bed-king-outline",
    3: "mdi:bookshelf",
    4: "mdi:chef-hat",
    5: "mdi:room-service-outline",
    6: "mdi:shower",
    7: "mdi:flower-outline",
    8: "mdi:foot-print",
    9: "mdi:archive-outline",
    10: "mdi:hanger",
    11: "mdi:presentation",
    12: "mdi:monitor-shimmer",
    13: "mdi:dumbbell",
    14: "mdi:gamepad-variant-outline",
    15: "mdi:bed-single-outline",
}

CUSTOM_NAME_TO_HA_ICON: Final = {
    "salle de bain": "mdi:bathtub-outline",
    "bathroom": "mdi:bathtub-outline",
    "wc": "mdi:toilet",
    "w.c": "mdi:toilet",
    "toilet": "mdi:toilet",
    "toilette": "mdi:toilet",
    "cellier": "mdi:bottle-wine",
    "pantry": "mdi:bottle-wine",
    "garage": "mdi:garage",
    "entrée": "mdi:door-open",
    "entry": "mdi:door-open",
    "hall": "mdi:door-open",
    "dressing": "mdi:wardrobe-outline",
    "terrasse": "mdi:deck",
    "terrace": "mdi:deck",
    "patio": "mdi:deck",
    "jardin": "mdi:tree",
    "garden": "mdi:tree",
    "escalier": "mdi:stairs",
    "stairs": "mdi:stairs",
    "cave": "mdi:stairs-down",
    "basement": "mdi:stairs-down",
    "grenier": "mdi:stairs-up",
    "attic": "mdi:stairs-up",
    "buanderie": "mdi:washing-machine",
    "laundry": "mdi:washing-machine",
    "nursery": "mdi:baby-carriage",
    "chambre d'enfant": "mdi:baby-carriage",
    "salle de jeux": "mdi:puzzle",
    "playroom": "mdi:puzzle",
}

CUSTOM_NAME_TO_ICON_TYPE: Final = {
    "salle de bain": 16,
    "bathroom": 16,
    "wc": 6,
    "w.c": 6,
    "toilet": 6,
    "toilette": 6,
    "cellier": 9,
    "pantry": 9,
    "entrée": 8,
    "entry": 8,
    "hall": 8,
    "dressing": 10,
    "terrasse": 7,
    "terrace": 7,
    "patio": 7,
    "jardin": 7,
    "garden": 7,
    "escalier": 8,
    "stairs": 8,
    "buanderie": 9,
    "laundry": 9,
    "salle de jeux": 14,
    "playroom": 14,
}

FURNITURE_TYPE_TO_DIMENSIONS: Final = {
    1: [1500, 2000],
    2: [1800, 2000],
    3: [800, 700],
    4: [1260, 800],
    5: [2340, 750],
    6: [1500, 800],
    7: [500, 400],
    8: [800, 400],
    9: [450, 690],
    10: [735, 990],
    11: [566, 865],
    12: [210, 378],
    13: [628, 936],
}

FURNITURE_V2_TYPE_TO_DIMENSIONS: Final = {
    1: [1000, 2000],
    2: [1500, 2000],
    3: [800, 700],
    4: [1400, 600],
    5: [2300, 700],
    6: [1200, 800],
    7: [500, 400],
    8: [800, 800],
    9: [400, 600],
    10: [300, 500],
    11: [500, 400],
    12: [400, 200],
    13: [400, 600],
    14: [600, 600],
    15: [600, 600],
    16: [300, 500],
    17: [400, 400],
    18: [1600, 300],
    19: [800, 300],
    20: [800, 400],
    21: [2000, 600],
    22: [300, 300],
    23: [1000, 400],
    24: [2800, 1700],
    25: [1000, 1000],
}

FURNITURE_V2_TYPE_MIJIA_TO_DIMENSIONS: Final = {
    1: [1000, 2000],
    2: [1500, 2000],
    3: [800, 700],
    4: [1400, 600],
    5: [2300, 700],
    6: [1200, 800],
    7: [500, 400],
    8: [1000, 1000],
    9: [400, 600],
    10: [300, 500],
    11: [500, 400],
    12: [400, 200],
    13: [400, 600],
    14: [600, 600],
    15: [600, 600],
    16: [300, 500],
    17: [400, 400],
    18: [1600, 300],
    19: [800, 300],
    20: [800, 400],
    21: [2000, 600],
    22: [300, 300],
    23: [1000, 400],
    24: [2800, 1700],
    25: [800, 800],
    26: [600, 1400],
    29: [800, 700],
    30: [2300, 700],
    31: [2800, 1700],
}

piid: Final = "piid"
siid: Final = "siid"
aiid: Final = "aiid"

ATTR_A: Final = "a"
ATTR_X: Final = "x"
ATTR_X0: Final = "x0"
ATTR_X1: Final = "x1"
ATTR_X2: Final = "x2"
ATTR_X3: Final = "x3"
ATTR_Y: Final = "y"
ATTR_Y0: Final = "y0"
ATTR_Y1: Final = "y1"
ATTR_Y2: Final = "y2"
ATTR_Y3: Final = "y3"
ATTR_CHARGER: Final = "charger_position"
ATTR_IS_EMPTY: Final = "is_empty"
ATTR_NO_GO_AREAS: Final = "no_go_areas"
ATTR_NO_MOPPING_AREAS: Final = "no_mopping_areas"
ATTR_CARPETS: Final = "carpets"
ATTR_IGNORED_CARPETS: Final = "ignored_carpets"
ATTR_DETECTED_CARPETS: Final = "detected_carpets"
ATTR_PREDEFINED_POINTS: Final = "predefined_points"
ATTR_VIRTUAL_WALLS: Final = "virtual_walls"
ATTR_WALL_LINES: Final = "wall_lines"
ATTR_DOOR_LINES: Final = "door_lines"
ATTR_VIRTUAL_THRESHOLDS: Final = "virtual_thresholds"
ATTR_PASSABLE_THRESHOLDS: Final = "passable_thresholds"
ATTR_IMPASSABLE_THRESHOLDS: Final = "impassable_thresholds"
ATTR_RAMPS: Final = "ramps"
ATTR_CURTAINS: Final = "curtains"
ATTR_LOW_LYING_AREAS: Final = "low_lying_areas"
ATTR_ROOMS: Final = "rooms"
ATTR_ROBOT_POSITION: Final = "vacuum_position"
ATTR_MAP_ID: Final = "map_id"
ATTR_SAVED_MAP_ID: Final = "saved_map_id"
ATTR_MAP_NAME: Final = "map_name"
ATTR_ROTATION: Final = "rotation"
ATTR_TIMESTAMP: Final = "timestamp"
ATTR_UPDATED: Final = "updated_at"
ATTR_ACTIVE_AREAS: Final = "active_areas"
ATTR_ACTIVE_POINTS: Final = "active_points"
ATTR_ACTIVE_CRUISE_POINTS: Final = "active_cruise_points"
ATTR_ACTIVE_SEGMENTS: Final = "active_segments"
ATTR_FRAME_ID: Final = "frame_id"
ATTR_MAP_INDEX: Final = "map_index"
ATTR_ROOM_ID: Final = "room_id"
ATTR_ROOM_ICON: Final = "room_icon"
ATTR_UNIQUE_ID: Final = "unique_id"
ATTR_FLOOR_MATERIAL: Final = "floor_material"
ATTR_FLOOR_MATERIAL_DIRECTION: Final = "floor_material_direction"
ATTR_VISIBILITY: Final = "visibility"
ATTR_NAME: Final = "name"
ATTR_CUSTOM_NAME: Final = "custom_name"
ATTR_OUTLINE: Final = "outline"
ATTR_CENTER: Final = "center"
ATTR_ORDER: Final = "order"
ATTR_CLEANING_TIMES: Final = "cleaning_times"
ATTR_SUCTION_LEVEL: Final = "suction_level"
ATTR_WATER_VOLUME: Final = "water_volume"
ATTR_WETNESS_LEVEL: Final = "wetness_level"
ATTR_CLEANING_MODE: Final = "cleaning_mode"
ATTR_CLEANING_ROUTE: Final = "cleaning_route"
ATTR_CUSTOM_MOPPING_ROUTE: Final = "custom_mopping_route"
ATTR_TYPE: Final = "type"
ATTR_INDEX: Final = "index"
ATTR_ICON: Final = "icon"
ATTR_COLOR_INDEX: Final = "color_index"
ATTR_OBSTACLES: Final = "obstacles"
ATTR_POSSIBILTY: Final = "possibility"
ATTR_PICTURE_STATUS: Final = "picture_status"
ATTR_IGNORE_STATUS: Final = "ignore_status"
ATTR_ROOM: Final = "room"
ATTR_ROUTER_POSITION: Final = "router_position"
ATTR_FURNITURES: Final = "furnitures"
ATTR_STARTUP_METHOD: Final = "startup_method"
ATTR_DUST_COLLECTION_COUNT: Final = "dust_collection_count"
ATTR_MOP_WASH_COUNT: Final = "mop_wash_count"
ATTR_RECOVERY_MAP_LIST: Final = "recovery_map_list"
ATTR_WIDTH: Final = "width"
ATTR_HEIGHT: Final = "height"
ATTR_SIZE_TYPE: Final = "size_type"
ATTR_ANGLE: Final = "angle"
ATTR_SCALE: Final = "scale"
ATTR_COMPLETED: Final = "completed"
