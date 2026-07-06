"""Dreame Vacuum property/action protocol tables (MIoT siid/piid mapping)."""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Final

from .types_attributes import aiid, piid, siid


class DreameVacuumProperty(IntEnum):
    """Dreame Vacuum properties"""

    STATE = 0
    ERROR = 1
    BATTERY_LEVEL = 2
    CHARGING_STATUS = 3
    OFF_PEAK_CHARGING = 4
    STATUS = 5
    CLEANING_TIME = 6
    CLEANED_AREA = 7
    SUCTION_LEVEL = 8
    WATER_VOLUME = 9
    WATER_TANK = 10
    TASK_STATUS = 11
    CLEANING_START_TIME = 12
    CLEAN_LOG_FILE_NAME = 13
    CLEANING_PROPERTIES = 14
    RESUME_CLEANING = 15
    CARPET_BOOST = 16
    CLEAN_LOG_STATUS = 17
    SERIAL_NUMBER = 18
    REMOTE_CONTROL = 19
    MOP_CLEANING_REMAINDER = 20
    CLEANING_PAUSED = 21
    FAULTS = 22
    NATION_MATCHED = 23
    RELOCATION_STATUS = 24
    OBSTACLE_AVOIDANCE = 25
    AI_DETECTION = 26
    CLEANING_MODE = 27
    UPLOAD_MAP = 28
    SELF_WASH_BASE_STATUS = 29
    CUSTOMIZED_CLEANING = 30
    CHILD_LOCK = 31
    CARPET_SENSITIVITY = 32
    TIGHT_MOPPING = 33
    CLEANING_CANCEL = 34
    Y_CLEAN = 35
    WATER_ELECTROLYSIS = 36
    CARPET_RECOGNITION = 37
    SELF_CLEAN = 38
    WARN_STATUS = 39
    CARPET_CLEANING = 40
    AUTO_ADD_DETERGENT = 41
    CAPABILITY = 42
    SAVE_WATER_TIPS = 43
    DRYING_TIME = 44
    LOW_WATER_WARNING = 45
    MAP_INDEX = 46
    MAP_NAME = 47
    CRUISE_TYPE = 48
    MOP_WASH_LEVEL = 49
    AUTO_MOUNT_MOP = 50
    SCHEDULED_CLEAN = 51
    SHORTCUTS = 52
    INTELLIGENT_RECOGNITION = 53
    AUTO_SWITCH_SETTINGS = 54
    AUTO_WATER_REFILLING = 55
    MOP_IN_STATION = 56
    MOP_PAD_INSTALLED = 57
    WATER_CHECK = 58
    DRY_STOP_REMAINDER = 59
    NUMERIC_MESSAGE_PROMPT = 60
    MESSAGE_PROMPT = 61
    TASK_TYPE = 62
    PET_DETECTIVE = 63
    DRAINAGE_STATUS = 64
    DOCK_CLEANING_STATUS = 65
    BACK_CLEAN_MODE = 66
    CLEANING_PROGRESS = 67
    DRYING_PROGRESS = 68
    DEVICE_CAPABILITY = 69
    DND = 70
    DND_START = 71
    DND_END = 72
    DND_TASK = 73
    MAP_DATA = 74
    FRAME_INFO = 75
    OBJECT_NAME = 76
    MAP_EXTEND_DATA = 77
    ROBOT_TIME = 78
    RESULT_CODE = 79
    MULTI_FLOOR_MAP = 80
    MAP_LIST = 81
    RECOVERY_MAP_LIST = 82
    MAP_RECOVERY = 83
    MAP_RECOVERY_STATUS = 84
    OLD_MAP_DATA = 85
    MAP_BACKUP_STATUS = 86
    WIFI_MAP = 87
    RESTORE_MAP_BY_AREA = 88
    VOLUME = 89
    VOICE_PACKET_ID = 90
    VOICE_CHANGE_STATUS = 91
    VOICE_CHANGE = 92
    VOICE_ASSISTANT = 93
    VOICE_ASSISTANT_LANGUAGE = 94
    EMPTY_STAMP = 95
    CURRENT_CITY = 96
    VOICE_TEST = 97
    LISTEN_LANGUAGE_TYPE = 98
    BAIDU_LOG = 99
    RESPONSE_WORD = 100
    DREAME_GPT = 101
    LISTEN_LANGUAGE = 102
    LISTEN_LANGUAGE_STATUS = 103
    TIMEZONE = 104
    SCHEDULE = 105
    SCHEDULE_ID = 106
    SCHEDULE_CANCEL_REASON = 107
    CRUISE_SCHEDULE = 108
    MAIN_BRUSH_TIME_LEFT = 109
    MAIN_BRUSH_LEFT = 110
    SIDE_BRUSH_TIME_LEFT = 111
    SIDE_BRUSH_LEFT = 112
    FILTER_LEFT = 113
    FILTER_TIME_LEFT = 114
    FIRST_CLEANING_DATE = 115
    TOTAL_CLEANING_TIME = 116
    CLEANING_COUNT = 117
    TOTAL_CLEANED_AREA = 118
    TOTAL_RUNTIME = 119
    TOTAL_CRUISE_TIME = 120
    MAP_SAVING = 121
    ROBOT_CONFIG = 122
    AUTO_DUST_COLLECTING = 123
    AUTO_EMPTY_FREQUENCY = 124
    DUST_COLLECTION = 125
    AUTO_EMPTY_STATUS = 126
    SENSOR_DIRTY_LEFT = 127
    SENSOR_DIRTY_TIME_LEFT = 128
    MOP_PAD_LEFT = 129
    MOP_PAD_TIME_LEFT = 130
    TANK_FILTER_LEFT = 131
    TANK_FILTER_TIME_LEFT = 132
    SILVER_ION_TIME_LEFT = 133
    SILVER_ION_LEFT = 134
    SILVER_ION_ADD = 135
    DETERGENT_LEFT = 136
    DETERGENT_TIME_LEFT = 137
    SQUEEGEE_LEFT = 138
    SQUEEGEE_TIME_LEFT = 139
    ONBOARD_DIRTY_WATER_TANK_LEFT = 140
    ONBOARD_DIRTY_WATER_TANK_TIME_LEFT = 141
    DIRTY_WATER_TANK_LEFT = 142
    DIRTY_WATER_TANK_TIME_LEFT = 143
    CLEAN_WATER_TANK_STATUS = 144
    DIRTY_WATER_TANK_STATUS = 145
    DUST_BAG_STATUS = 146
    DETERGENT_STATUS = 147
    STATION_DRAINAGE_STATUS = 148
    AI_MAP_OPTIMIZATION_STATUS = 149
    SECOND_CLEANING_STATUS = 150
    WATER_TANK_STATUS = 151
    ADD_CLEANING_AREA_STATUS = 152
    ADD_CLEANING_AREA_RESULT = 153
    FIRST_CONNECT_WIFI = 154
    HAND_DUST_STATUS = 155
    HAND_DUST_CONNECT_STATUS = 156
    HOT_WATER_STATUS = 157
    WETNESS_LEVEL = 158
    CLEAN_CARPETS_FIRST = 159
    AUTO_LDS_LIFTING = 160
    LDS_STATE = 161
    CLEANGENIUS_MODE = 162
    QUICK_WASH_MODE = 163
    WATER_TEMPERATURE = 164
    CLEAN_EFFICIENCY = 165
    IMPACT_INJECTION_PUMP = 166
    OBSTACLE_VIDEOS = 167
    DND_DISABLE_RESUME_CLEANING = 168
    DND_DISABLE_AUTO_EMPTY = 169
    DND_REDUCE_VOLUME = 170
    HAND_VACUUM_AUTO_DUSTING = 171
    DYNAMIC_OBSTACLE_CLEAN = 172
    HUMAN_NOISE_REDUCTION = 173
    PET_CARE = 174
    LOWER_HATCH_CONTROL = 175
    SMART_MOP_WASHING = 176
    BLOCK_HEALTH_CHECKS = 177
    MOP_AFTER_VACUUM = 178
    SMALL_AREA_FAST_CLEAN = 179
    SHIELD_ULTRASONIC_SIGNALS = 180
    SILENT_DRYING = 181
    HAIR_COMPRESSION = 182
    SIDE_BRUSH_CARPET_ROTATE = 183
    ERP_LOW_POWER = 184
    SHIELD_WASHBOARD_IN_PLACE = 185
    SELF_CLEANING_PROBLEM = 186
    WASHING_TEST = 187
    FEEDBACK_SWITCH = 188
    CARPET_AI_SEGMENT = 189
    OBSTACLE_CROSSING = 190
    VISUAL_RESUME = 191
    FAN_ABNORMAL_NOISE = 192
    LARGE_MEMORY_RESET = 193
    BOW_BEFORE_EDGE = 194
    VOLTAGE = 195
    DETERGENT_A = 196
    DETERGENT_B = 197
    MOP_TEMPERATURE = 198
    BATTERY_CHARGE_LEVEL = 199
    DUST_BAG_DRYING = 200
    SWEEP_DISTANCE = 201
    LDS_LIFTING_FREQUENCY = 202
    MOP_WASHING_WITH_DETERGENT = 203
    PRESSURIZED_CLEANING = 204
    SCRAPER_FREQUENCY = 205
    DEODORIZER_TIME_LEFT = 206
    DEODORIZER_LEFT = 207
    WHEEL_DIRTY_TIME_LEFT = 208
    WHEEL_DIRTY_LEFT = 209
    SCALE_INHIBITOR_TIME_LEFT = 210
    SCALE_INHIBITOR_LEFT = 211
    FACTORY_TEST_STATUS = 212
    FACTORY_TEST_RESULT = 213
    SELF_TEST_STATUS = 214
    LSD_TEST_STATUS = 215
    DEBUG_SWITCH = 216
    SERIAL = 217
    CALIBRATION_STATUS = 218
    VERSION = 219
    PERFORMANCE_SWITCH = 220
    AI_TEST_STATUS = 221
    PUBLIC_KEY = 222
    AUTO_PAIR = 223
    MCU_VERSION = 224
    MOP_TEST_STATUS = 225
    PLATFORM_NETWORK = 226
    STREAM_STATUS = 227
    STREAM_AUDIO = 228
    STREAM_RECORD = 229
    TAKE_PHOTO = 230
    STREAM_KEEP_ALIVE = 231
    STREAM_FAULT = 232
    CAMERA_LIGHT_BRIGHTNESS = 233
    CAMERA_LIGHT = 234
    STREAM_VENDOR = 235
    STREAM_PROPERTY = 236
    STREAM_CRUISE_POINT = 237
    STREAM_TASK = 238
    STEAM_HUMAN_FOLLOW = 239
    OBSTACLE_VIDEO_STATUS = 240
    OBSTACLE_VIDEO_DATA = 241
    STREAM_UPLOAD = 242
    STREAM_CODE = 243
    STREAM_SET_CODE = 244
    STREAM_VERIFY_CODE = 245
    STREAM_RESET_CODE = 246
    STREAM_SPACE = 247
    DUST_BAG_DRY_STATUS = 248
    STATION_CLEAN_STATUS = 249
    MECHANICAL_FOOT_STATUS = 250
    STATION_OTA_STATUS = 251


class DreameVacuumAutoSwitchProperty(StrEnum):
    """Dreame Vacuum Auto Switch properties"""

    COLLISION_AVOIDANCE = "LessColl"
    FILL_LIGHT = "FillinLight"
    AUTO_DRYING = "AutoDry"
    STAIN_AVOIDANCE = "StainIdentify"
    MOPPING_TYPE = "CleanType"
    CLEANGENIUS = "SmartHost"
    WIDER_CORNER_COVERAGE = "MeticulousTwist"
    FLOOR_DIRECTION_CLEANING = "MaterialDirectionClean"
    PET_FOCUSED_CLEANING = "PetPartClean"
    AUTO_RECLEANING = "SmartAutoMop"
    AUTO_REWASHING = "SmartAutoWash"
    MOP_PAD_SWING = "MopScalable"
    AUTO_CHARGING = "SmartCharge"
    HUMAN_FOLLOW = "MonitorHumanFollow"
    MAX_SUCTION_POWER = "SuctionMax"
    SMART_DRYING = "SmartDrying"
    DRAINAGE_CONFIRM_RESULT = "FluctuationConfirmResult"
    DRAINAGE_TEST_RESULT = "FluctuationTestResult"
    HOT_WASHING = "HotWash"
    UV_STERILIZATION = "UVLight"
    CLEANING_ROUTE = "CleanRoute"
    CUSTOM_MOPPING_MODE = "MopEffectSwitch"
    MOPPING_MODE = "MopEffectState"
    SELF_CLEAN_FREQUENCY = "BackWashType"
    INTENSIVE_CARPET_CLEANING = "CarpetFineClean"
    GAP_CLEANING_EXTENSION = "LacuneMopScalable"
    MOPPING_UNDER_FURNITURES = "MopScalable2"
    # CLEAN_CARPETS_FIRST = "CarpetFirstClean"
    ULTRA_CLEAN_MODE = "SuperWash"
    STREAMING_VOICE_PROMPT = "MonitorPromptLevel"
    MOP_EXTEND = "MopExtrSwitch"
    MOP_EXTEND_FREQUENCY = "ExtrFreq"
    SIDE_REACH = "SbrushExtrSwitch"


class DreameVacuumStrAIProperty(StrEnum):
    """Dreame Vacuum json AI obstacle detection properties"""

    AI_OBSTACLE_DETECTION = "obstacle_detect_switch"
    AI_OBSTACLE_IMAGE_UPLOAD = "obstacle_app_display_switch"
    AI_PET_DETECTION = "whether_have_pet"
    AI_HUMAN_DETECTION = "human_detect_switch"
    AI_FURNITURE_DETECTION = "furniture_detect_switch"
    AI_FLUID_DETECTION = "fluid_detect_switch"


class DreameVacuumAIProperty(IntEnum):
    """Dreame Vacuum bitwise AI obstacle detection properties"""

    AI_FURNITURE_DETECTION = 1
    AI_OBSTACLE_DETECTION = 2
    AI_OBSTACLE_PICTURE = 4
    AI_FLUID_DETECTION = 8
    AI_PET_DETECTION = 16
    AI_OBSTACLE_IMAGE_UPLOAD = 32
    AI_IMAGE = 64
    AI_PET_AVOIDANCE = 128
    FUZZY_OBSTACLE_DETECTION = 256
    PET_PICTURE = 512
    PET_FOCUSED_DETECTION = 1024
    LARGE_PARTICLES_BOOST = 2048


class DreameVacuumAction(IntEnum):
    """Dreame Vacuum actions"""

    START = 1
    PAUSE = 2
    CHARGE = 3
    START_CUSTOM = 4
    STOP = 5
    CLEAR_WARNING = 6
    START_WASHING = 7
    GET_PHOTO_INFO = 8
    SHORTCUTS = 9
    REQUEST_MAP = 10
    UPDATE_MAP_DATA = 11
    BACKUP_MAP = 12
    WIFI_MAP = 13
    LOCATE = 14
    TEST_SOUND = 15
    DELETE_SCHEDULE = 16
    DELETE_CRUISE_SCHEDULE = 17
    RESET_MAIN_BRUSH = 18
    RESET_SIDE_BRUSH = 19
    RESET_FILTER = 20
    RESET_SENSOR = 21
    START_AUTO_EMPTY = 22
    RESET_TANK_FILTER = 23
    RESET_MOP_PAD = 24
    RESET_SILVER_ION = 25
    RESET_DETERGENT = 26
    RESET_SQUEEGEE = 27
    RESET_ONBOARD_DIRTY_WATER_TANK = 28
    RESET_DIRTY_WATER_TANK = 29
    RESET_DEODORIZER = 30
    RESET_WHEEL = 31
    RESET_SCALE_INHIBITOR = 32
    STREAM_VIDEO = 33
    STREAM_AUDIO = 34
    STREAM_PROPERTY = 35
    STREAM_CODE = 36


# Dreame Vacuum property mapping
DreameVacuumPropertyMapping = {
    DreameVacuumProperty.STATE: {siid: 2, piid: 1},
    DreameVacuumProperty.ERROR: {siid: 2, piid: 2},
    DreameVacuumProperty.BATTERY_LEVEL: {siid: 3, piid: 1},
    DreameVacuumProperty.CHARGING_STATUS: {siid: 3, piid: 2},
    DreameVacuumProperty.OFF_PEAK_CHARGING: {siid: 3, piid: 3},
    DreameVacuumProperty.STATUS: {siid: 4, piid: 1},
    DreameVacuumProperty.CLEANING_TIME: {siid: 4, piid: 2},
    DreameVacuumProperty.CLEANED_AREA: {siid: 4, piid: 3},
    DreameVacuumProperty.SUCTION_LEVEL: {siid: 4, piid: 4},
    DreameVacuumProperty.WATER_VOLUME: {siid: 4, piid: 5},
    DreameVacuumProperty.WATER_TANK: {siid: 4, piid: 6},
    DreameVacuumProperty.TASK_STATUS: {siid: 4, piid: 7},
    DreameVacuumProperty.CLEANING_START_TIME: {siid: 4, piid: 8},
    DreameVacuumProperty.CLEAN_LOG_FILE_NAME: {siid: 4, piid: 9},
    DreameVacuumProperty.CLEANING_PROPERTIES: {siid: 4, piid: 10},
    DreameVacuumProperty.RESUME_CLEANING: {siid: 4, piid: 11},
    DreameVacuumProperty.CARPET_BOOST: {siid: 4, piid: 12},
    DreameVacuumProperty.CLEAN_LOG_STATUS: {siid: 4, piid: 13},
    DreameVacuumProperty.SERIAL_NUMBER: {siid: 4, piid: 14},
    DreameVacuumProperty.REMOTE_CONTROL: {siid: 4, piid: 15},
    DreameVacuumProperty.MOP_CLEANING_REMAINDER: {siid: 4, piid: 16},
    DreameVacuumProperty.CLEANING_PAUSED: {siid: 4, piid: 17},
    DreameVacuumProperty.FAULTS: {siid: 4, piid: 18},
    DreameVacuumProperty.NATION_MATCHED: {siid: 4, piid: 19},
    DreameVacuumProperty.RELOCATION_STATUS: {siid: 4, piid: 20},
    DreameVacuumProperty.OBSTACLE_AVOIDANCE: {siid: 4, piid: 21},
    DreameVacuumProperty.AI_DETECTION: {siid: 4, piid: 22},
    DreameVacuumProperty.CLEANING_MODE: {siid: 4, piid: 23},
    DreameVacuumProperty.UPLOAD_MAP: {siid: 4, piid: 24},
    DreameVacuumProperty.SELF_WASH_BASE_STATUS: {siid: 4, piid: 25},
    DreameVacuumProperty.CUSTOMIZED_CLEANING: {siid: 4, piid: 26},
    DreameVacuumProperty.CHILD_LOCK: {siid: 4, piid: 27},
    DreameVacuumProperty.CARPET_SENSITIVITY: {siid: 4, piid: 28},
    DreameVacuumProperty.TIGHT_MOPPING: {siid: 4, piid: 29},
    DreameVacuumProperty.CLEANING_CANCEL: {siid: 4, piid: 30},
    DreameVacuumProperty.Y_CLEAN: {siid: 4, piid: 31},
    DreameVacuumProperty.WATER_ELECTROLYSIS: {siid: 4, piid: 32},
    DreameVacuumProperty.CARPET_RECOGNITION: {siid: 4, piid: 33},
    DreameVacuumProperty.SELF_CLEAN: {siid: 4, piid: 34},
    DreameVacuumProperty.WARN_STATUS: {siid: 4, piid: 35},
    DreameVacuumProperty.CARPET_CLEANING: {siid: 4, piid: 36},
    DreameVacuumProperty.AUTO_ADD_DETERGENT: {siid: 4, piid: 37},
    DreameVacuumProperty.CAPABILITY: {siid: 4, piid: 38},
    DreameVacuumProperty.SAVE_WATER_TIPS: {siid: 4, piid: 39},
    DreameVacuumProperty.DRYING_TIME: {siid: 4, piid: 40},
    DreameVacuumProperty.LOW_WATER_WARNING: {siid: 4, piid: 41},
    DreameVacuumProperty.MAP_INDEX: {siid: 4, piid: 42},
    DreameVacuumProperty.MAP_NAME: {siid: 4, piid: 43},
    DreameVacuumProperty.CRUISE_TYPE: {siid: 4, piid: 44},
    DreameVacuumProperty.AUTO_MOUNT_MOP: {siid: 4, piid: 45},
    DreameVacuumProperty.MOP_WASH_LEVEL: {siid: 4, piid: 46},
    DreameVacuumProperty.SCHEDULED_CLEAN: {siid: 4, piid: 47},
    DreameVacuumProperty.SHORTCUTS: {siid: 4, piid: 48},
    DreameVacuumProperty.INTELLIGENT_RECOGNITION: {siid: 4, piid: 49},
    DreameVacuumProperty.AUTO_SWITCH_SETTINGS: {siid: 4, piid: 50},
    DreameVacuumProperty.AUTO_WATER_REFILLING: {siid: 4, piid: 51},
    DreameVacuumProperty.MOP_IN_STATION: {siid: 4, piid: 52},
    DreameVacuumProperty.MOP_PAD_INSTALLED: {siid: 4, piid: 53},
    DreameVacuumProperty.WATER_CHECK: {siid: 4, piid: 54},
    DreameVacuumProperty.DRY_STOP_REMAINDER: {siid: 4, piid: 55},
    DreameVacuumProperty.NUMERIC_MESSAGE_PROMPT: {siid: 4, piid: 56},
    DreameVacuumProperty.MESSAGE_PROMPT: {siid: 4, piid: 57},
    DreameVacuumProperty.TASK_TYPE: {siid: 4, piid: 58},
    DreameVacuumProperty.PET_DETECTIVE: {siid: 4, piid: 59},
    DreameVacuumProperty.DRAINAGE_STATUS: {siid: 4, piid: 60},
    DreameVacuumProperty.DOCK_CLEANING_STATUS: {siid: 4, piid: 61},
    DreameVacuumProperty.BACK_CLEAN_MODE: {siid: 4, piid: 62},
    DreameVacuumProperty.CLEANING_PROGRESS: {siid: 4, piid: 63},
    DreameVacuumProperty.DRYING_PROGRESS: {siid: 4, piid: 64},
    DreameVacuumProperty.DEVICE_CAPABILITY: {siid: 4, piid: 83},
    # DreameVacuumProperty.COMBINED_DATA: {siid: 4, piid: 99},
    DreameVacuumProperty.DND: {siid: 5, piid: 1},
    DreameVacuumProperty.DND_START: {siid: 5, piid: 2},
    DreameVacuumProperty.DND_END: {siid: 5, piid: 3},
    DreameVacuumProperty.DND_TASK: {siid: 5, piid: 4},
    DreameVacuumProperty.MAP_DATA: {siid: 6, piid: 1},
    DreameVacuumProperty.FRAME_INFO: {siid: 6, piid: 2},
    DreameVacuumProperty.OBJECT_NAME: {siid: 6, piid: 3},
    DreameVacuumProperty.MAP_EXTEND_DATA: {siid: 6, piid: 4},
    DreameVacuumProperty.ROBOT_TIME: {siid: 6, piid: 5},
    DreameVacuumProperty.RESULT_CODE: {siid: 6, piid: 6},
    DreameVacuumProperty.MULTI_FLOOR_MAP: {siid: 6, piid: 7},
    DreameVacuumProperty.MAP_LIST: {siid: 6, piid: 8},
    DreameVacuumProperty.RECOVERY_MAP_LIST: {siid: 6, piid: 9},
    DreameVacuumProperty.MAP_RECOVERY: {siid: 6, piid: 10},
    DreameVacuumProperty.MAP_RECOVERY_STATUS: {siid: 6, piid: 11},
    DreameVacuumProperty.OLD_MAP_DATA: {siid: 6, piid: 13},
    DreameVacuumProperty.MAP_BACKUP_STATUS: {siid: 6, piid: 14},
    DreameVacuumProperty.WIFI_MAP: {siid: 6, piid: 15},
    DreameVacuumProperty.RESTORE_MAP_BY_AREA: {siid: 6, piid: 16},
    DreameVacuumProperty.VOLUME: {siid: 7, piid: 1},
    DreameVacuumProperty.VOICE_PACKET_ID: {siid: 7, piid: 2},
    DreameVacuumProperty.VOICE_CHANGE_STATUS: {siid: 7, piid: 3},
    DreameVacuumProperty.VOICE_CHANGE: {siid: 7, piid: 4},
    DreameVacuumProperty.VOICE_ASSISTANT: {siid: 7, piid: 5},
    DreameVacuumProperty.EMPTY_STAMP: {siid: 7, piid: 6},
    DreameVacuumProperty.CURRENT_CITY: {siid: 7, piid: 7},
    DreameVacuumProperty.VOICE_TEST: {siid: 7, piid: 9},
    DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE: {siid: 7, piid: 10},
    DreameVacuumProperty.LISTEN_LANGUAGE_TYPE: {siid: 7, piid: 10},
    DreameVacuumProperty.BAIDU_LOG: {siid: 7, piid: 11},
    DreameVacuumProperty.RESPONSE_WORD: {siid: 7, piid: 12},
    DreameVacuumProperty.DREAME_GPT: {siid: 7, piid: 14},
    DreameVacuumProperty.LISTEN_LANGUAGE: {siid: 7, piid: 15},
    DreameVacuumProperty.LISTEN_LANGUAGE_STATUS: {siid: 7, piid: 16},
    DreameVacuumProperty.TIMEZONE: {siid: 8, piid: 1},
    DreameVacuumProperty.SCHEDULE: {siid: 8, piid: 2},
    DreameVacuumProperty.SCHEDULE_ID: {siid: 8, piid: 3},
    DreameVacuumProperty.SCHEDULE_CANCEL_REASON: {siid: 8, piid: 4},
    DreameVacuumProperty.CRUISE_SCHEDULE: {siid: 8, piid: 5},
    DreameVacuumProperty.MAIN_BRUSH_TIME_LEFT: {siid: 9, piid: 1},
    DreameVacuumProperty.MAIN_BRUSH_LEFT: {siid: 9, piid: 2},
    DreameVacuumProperty.SIDE_BRUSH_TIME_LEFT: {siid: 10, piid: 1},
    DreameVacuumProperty.SIDE_BRUSH_LEFT: {siid: 10, piid: 2},
    DreameVacuumProperty.FILTER_LEFT: {siid: 11, piid: 1},
    DreameVacuumProperty.FILTER_TIME_LEFT: {siid: 11, piid: 2},
    DreameVacuumProperty.FIRST_CLEANING_DATE: {siid: 12, piid: 1},
    DreameVacuumProperty.TOTAL_CLEANING_TIME: {siid: 12, piid: 2},
    DreameVacuumProperty.CLEANING_COUNT: {siid: 12, piid: 3},
    DreameVacuumProperty.TOTAL_CLEANED_AREA: {siid: 12, piid: 4},
    DreameVacuumProperty.TOTAL_RUNTIME: {siid: 12, piid: 5},
    DreameVacuumProperty.TOTAL_CRUISE_TIME: {siid: 12, piid: 6},
    DreameVacuumProperty.MAP_SAVING: {siid: 13, piid: 1},
    DreameVacuumProperty.ROBOT_CONFIG: {siid: 14, piid: 1},
    DreameVacuumProperty.AUTO_DUST_COLLECTING: {siid: 15, piid: 1},
    DreameVacuumProperty.AUTO_EMPTY_FREQUENCY: {siid: 15, piid: 2},
    DreameVacuumProperty.DUST_COLLECTION: {siid: 15, piid: 3},
    DreameVacuumProperty.AUTO_EMPTY_STATUS: {siid: 15, piid: 5},
    DreameVacuumProperty.SENSOR_DIRTY_LEFT: {siid: 16, piid: 1},
    DreameVacuumProperty.SENSOR_DIRTY_TIME_LEFT: {siid: 16, piid: 2},
    DreameVacuumProperty.TANK_FILTER_LEFT: {siid: 17, piid: 1},
    DreameVacuumProperty.TANK_FILTER_TIME_LEFT: {siid: 17, piid: 2},
    DreameVacuumProperty.MOP_PAD_LEFT: {siid: 18, piid: 1},
    DreameVacuumProperty.MOP_PAD_TIME_LEFT: {siid: 18, piid: 2},
    DreameVacuumProperty.SILVER_ION_TIME_LEFT: {siid: 19, piid: 1},
    DreameVacuumProperty.SILVER_ION_LEFT: {siid: 19, piid: 2},
    DreameVacuumProperty.SILVER_ION_ADD: {siid: 19, piid: 3},
    DreameVacuumProperty.DETERGENT_LEFT: {siid: 20, piid: 1},
    DreameVacuumProperty.DETERGENT_TIME_LEFT: {siid: 20, piid: 2},
    DreameVacuumProperty.SQUEEGEE_LEFT: {siid: 24, piid: 1},
    DreameVacuumProperty.SQUEEGEE_TIME_LEFT: {siid: 24, piid: 2},
    DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_LEFT: {siid: 25, piid: 1},
    DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_TIME_LEFT: {siid: 25, piid: 2},
    DreameVacuumProperty.DIRTY_WATER_TANK_LEFT: {siid: 26, piid: 1},
    DreameVacuumProperty.DIRTY_WATER_TANK_TIME_LEFT: {siid: 26, piid: 2},
    DreameVacuumProperty.CLEAN_WATER_TANK_STATUS: {siid: 27, piid: 1},
    DreameVacuumProperty.DIRTY_WATER_TANK_STATUS: {siid: 27, piid: 2},
    DreameVacuumProperty.DUST_BAG_STATUS: {siid: 27, piid: 3},
    DreameVacuumProperty.DETERGENT_STATUS: {siid: 27, piid: 4},
    DreameVacuumProperty.STATION_DRAINAGE_STATUS: {siid: 27, piid: 5},
    DreameVacuumProperty.AI_MAP_OPTIMIZATION_STATUS: {siid: 27, piid: 7},
    DreameVacuumProperty.SECOND_CLEANING_STATUS: {siid: 27, piid: 8},
    DreameVacuumProperty.WATER_TANK_STATUS: {siid: 27, piid: 9},
    DreameVacuumProperty.ADD_CLEANING_AREA_STATUS: {siid: 27, piid: 10},
    DreameVacuumProperty.ADD_CLEANING_AREA_RESULT: {siid: 27, piid: 11},
    DreameVacuumProperty.FIRST_CONNECT_WIFI: {siid: 27, piid: 12},
    DreameVacuumProperty.HAND_DUST_STATUS: {siid: 27, piid: 13},
    DreameVacuumProperty.HAND_DUST_CONNECT_STATUS: {siid: 27, piid: 14},
    DreameVacuumProperty.HOT_WATER_STATUS: {siid: 27, piid: 15},
    DreameVacuumProperty.DUST_BAG_DRY_STATUS: {siid: 27, piid: 18},
    DreameVacuumProperty.STATION_CLEAN_STATUS: {siid: 27, piid: 27},
    DreameVacuumProperty.MECHANICAL_FOOT_STATUS: {siid: 27, piid: 28},
    DreameVacuumProperty.STATION_OTA_STATUS: {siid: 27, piid: 30},
    DreameVacuumProperty.WETNESS_LEVEL: {siid: 28, piid: 1},
    DreameVacuumProperty.CLEAN_CARPETS_FIRST: {siid: 28, piid: 2},
    DreameVacuumProperty.AUTO_LDS_LIFTING: {siid: 28, piid: 3},
    DreameVacuumProperty.LDS_STATE: {siid: 28, piid: 4},
    DreameVacuumProperty.CLEANGENIUS_MODE: {siid: 28, piid: 5},
    DreameVacuumProperty.QUICK_WASH_MODE: {siid: 28, piid: 6},
    DreameVacuumProperty.WATER_TEMPERATURE: {siid: 28, piid: 8},
    DreameVacuumProperty.CLEAN_EFFICIENCY: {siid: 28, piid: 9},
    DreameVacuumProperty.IMPACT_INJECTION_PUMP: {siid: 28, piid: 12},
    DreameVacuumProperty.OBSTACLE_VIDEOS: {siid: 28, piid: 13},
    DreameVacuumProperty.DND_DISABLE_RESUME_CLEANING: {siid: 28, piid: 14},
    DreameVacuumProperty.DND_DISABLE_AUTO_EMPTY: {siid: 28, piid: 15},
    DreameVacuumProperty.DND_REDUCE_VOLUME: {siid: 28, piid: 16},
    DreameVacuumProperty.HAND_VACUUM_AUTO_DUSTING: {siid: 28, piid: 17},
    DreameVacuumProperty.DYNAMIC_OBSTACLE_CLEAN: {siid: 28, piid: 18},
    DreameVacuumProperty.HUMAN_NOISE_REDUCTION: {siid: 28, piid: 19},
    DreameVacuumProperty.PET_CARE: {siid: 28, piid: 20},
    DreameVacuumProperty.LOWER_HATCH_CONTROL: {siid: 28, piid: 21},
    DreameVacuumProperty.SMART_MOP_WASHING: {siid: 28, piid: 22},
    DreameVacuumProperty.BLOCK_HEALTH_CHECKS: {siid: 28, piid: 23},
    DreameVacuumProperty.MOP_AFTER_VACUUM: {siid: 28, piid: 24},
    DreameVacuumProperty.SMALL_AREA_FAST_CLEAN: {siid: 28, piid: 25},
    DreameVacuumProperty.SHIELD_ULTRASONIC_SIGNALS: {siid: 28, piid: 26},
    DreameVacuumProperty.SILENT_DRYING: {siid: 28, piid: 27},
    DreameVacuumProperty.HAIR_COMPRESSION: {siid: 28, piid: 28},
    DreameVacuumProperty.SIDE_BRUSH_CARPET_ROTATE: {siid: 28, piid: 29},
    DreameVacuumProperty.ERP_LOW_POWER: {siid: 28, piid: 30},
    DreameVacuumProperty.SHIELD_WASHBOARD_IN_PLACE: {siid: 28, piid: 31},
    DreameVacuumProperty.SELF_CLEANING_PROBLEM: {siid: 28, piid: 32},
    DreameVacuumProperty.WASHING_TEST: {siid: 28, piid: 33},
    DreameVacuumProperty.FEEDBACK_SWITCH: {siid: 28, piid: 36},
    DreameVacuumProperty.CARPET_AI_SEGMENT: {siid: 28, piid: 37},
    DreameVacuumProperty.OBSTACLE_CROSSING: {siid: 28, piid: 38},
    DreameVacuumProperty.VISUAL_RESUME: {siid: 28, piid: 39},
    DreameVacuumProperty.FAN_ABNORMAL_NOISE: {siid: 28, piid: 40},
    DreameVacuumProperty.LARGE_MEMORY_RESET: {siid: 28, piid: 41},
    DreameVacuumProperty.BOW_BEFORE_EDGE: {siid: 28, piid: 42},
    DreameVacuumProperty.VOLTAGE: {siid: 28, piid: 43},
    DreameVacuumProperty.DETERGENT_A: {siid: 28, piid: 44},
    DreameVacuumProperty.DETERGENT_B: {siid: 28, piid: 45},
    DreameVacuumProperty.MOP_TEMPERATURE: {siid: 28, piid: 46},
    DreameVacuumProperty.BATTERY_CHARGE_LEVEL: {siid: 28, piid: 47},
    DreameVacuumProperty.DUST_BAG_DRYING: {siid: 28, piid: 48},
    DreameVacuumProperty.SWEEP_DISTANCE: {siid: 28, piid: 49},
    DreameVacuumProperty.LDS_LIFTING_FREQUENCY: {siid: 28, piid: 51},
    DreameVacuumProperty.MOP_WASHING_WITH_DETERGENT: {siid: 28, piid: 52},
    DreameVacuumProperty.PRESSURIZED_CLEANING: {siid: 28, piid: 53},
    DreameVacuumProperty.SCRAPER_FREQUENCY: {siid: 28, piid: 54},
    DreameVacuumProperty.DEODORIZER_TIME_LEFT: {siid: 29, piid: 1},
    DreameVacuumProperty.DEODORIZER_LEFT: {siid: 29, piid: 2},
    DreameVacuumProperty.WHEEL_DIRTY_TIME_LEFT: {siid: 30, piid: 1},
    DreameVacuumProperty.WHEEL_DIRTY_LEFT: {siid: 30, piid: 2},
    DreameVacuumProperty.SCALE_INHIBITOR_TIME_LEFT: {siid: 31, piid: 1},
    DreameVacuumProperty.SCALE_INHIBITOR_LEFT: {siid: 31, piid: 2},
    DreameVacuumProperty.FACTORY_TEST_STATUS: {siid: 99, piid: 1},
    DreameVacuumProperty.FACTORY_TEST_RESULT: {siid: 99, piid: 3},
    DreameVacuumProperty.SELF_TEST_STATUS: {siid: 99, piid: 8},
    DreameVacuumProperty.LSD_TEST_STATUS: {siid: 99, piid: 9},
    DreameVacuumProperty.DEBUG_SWITCH: {siid: 99, piid: 11},
    DreameVacuumProperty.SERIAL: {siid: 99, piid: 14},
    DreameVacuumProperty.CALIBRATION_STATUS: {siid: 99, piid: 15},
    DreameVacuumProperty.VERSION: {siid: 99, piid: 17},
    DreameVacuumProperty.PERFORMANCE_SWITCH: {siid: 99, piid: 24},
    DreameVacuumProperty.AI_TEST_STATUS: {siid: 99, piid: 25},
    DreameVacuumProperty.PUBLIC_KEY: {siid: 99, piid: 27},
    DreameVacuumProperty.AUTO_PAIR: {siid: 99, piid: 28},
    DreameVacuumProperty.MCU_VERSION: {siid: 99, piid: 31},
    DreameVacuumProperty.MOP_TEST_STATUS: {siid: 99, piid: 35},
    DreameVacuumProperty.PLATFORM_NETWORK: {siid: 99, piid: 95},
    DreameVacuumProperty.STREAM_STATUS: {siid: 10001, piid: 1},
    DreameVacuumProperty.STREAM_AUDIO: {siid: 10001, piid: 2},
    DreameVacuumProperty.STREAM_RECORD: {siid: 10001, piid: 4},
    DreameVacuumProperty.TAKE_PHOTO: {siid: 10001, piid: 5},
    DreameVacuumProperty.STREAM_KEEP_ALIVE: {siid: 10001, piid: 6},
    DreameVacuumProperty.STREAM_FAULT: {siid: 10001, piid: 7},
    DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS: {siid: 10001, piid: 9},
    DreameVacuumProperty.CAMERA_LIGHT: {siid: 10001, piid: 10},
    DreameVacuumProperty.STREAM_VENDOR: {siid: 10001, piid: 11},
    DreameVacuumProperty.STREAM_PROPERTY: {siid: 10001, piid: 99},
    DreameVacuumProperty.STREAM_CRUISE_POINT: {siid: 10001, piid: 101},
    DreameVacuumProperty.STREAM_TASK: {siid: 10001, piid: 103},
    DreameVacuumProperty.STEAM_HUMAN_FOLLOW: {siid: 10001, piid: 110},
    DreameVacuumProperty.OBSTACLE_VIDEO_STATUS: {siid: 10001, piid: 111},
    DreameVacuumProperty.OBSTACLE_VIDEO_DATA: {siid: 10001, piid: 112},
    DreameVacuumProperty.STREAM_UPLOAD: {siid: 10001, piid: 1003},
    DreameVacuumProperty.STREAM_CODE: {siid: 10001, piid: 1100},
    DreameVacuumProperty.STREAM_SET_CODE: {siid: 10001, piid: 1101},
    DreameVacuumProperty.STREAM_VERIFY_CODE: {siid: 10001, piid: 1102},
    DreameVacuumProperty.STREAM_RESET_CODE: {siid: 10001, piid: 1103},
    DreameVacuumProperty.STREAM_SPACE: {siid: 10001, piid: 2003},
}

# Dreame Vacuum action mapping
DreameVacuumActionMapping = {
    DreameVacuumAction.START: {siid: 2, aiid: 1},
    DreameVacuumAction.PAUSE: {siid: 2, aiid: 2},
    DreameVacuumAction.CHARGE: {siid: 3, aiid: 1},
    DreameVacuumAction.START_CUSTOM: {siid: 4, aiid: 1},
    DreameVacuumAction.STOP: {siid: 4, aiid: 2},
    DreameVacuumAction.CLEAR_WARNING: {siid: 4, aiid: 3},
    DreameVacuumAction.START_WASHING: {siid: 4, aiid: 4},
    DreameVacuumAction.GET_PHOTO_INFO: {siid: 4, aiid: 6},
    DreameVacuumAction.SHORTCUTS: {siid: 4, aiid: 8},
    DreameVacuumAction.REQUEST_MAP: {siid: 6, aiid: 1},
    DreameVacuumAction.UPDATE_MAP_DATA: {siid: 6, aiid: 2},
    DreameVacuumAction.BACKUP_MAP: {siid: 6, aiid: 3},
    DreameVacuumAction.WIFI_MAP: {siid: 6, aiid: 4},
    DreameVacuumAction.LOCATE: {siid: 7, aiid: 1},
    DreameVacuumAction.TEST_SOUND: {siid: 7, aiid: 2},
    DreameVacuumAction.DELETE_SCHEDULE: {siid: 8, aiid: 1},
    DreameVacuumAction.DELETE_CRUISE_SCHEDULE: {siid: 8, aiid: 2},
    DreameVacuumAction.RESET_MAIN_BRUSH: {siid: 9, aiid: 1},
    DreameVacuumAction.RESET_SIDE_BRUSH: {siid: 10, aiid: 1},
    DreameVacuumAction.RESET_FILTER: {siid: 11, aiid: 1},
    DreameVacuumAction.RESET_SENSOR: {siid: 16, aiid: 1},
    DreameVacuumAction.START_AUTO_EMPTY: {siid: 15, aiid: 1},
    DreameVacuumAction.RESET_TANK_FILTER: {siid: 17, aiid: 1},
    DreameVacuumAction.RESET_MOP_PAD: {siid: 18, aiid: 1},
    DreameVacuumAction.RESET_SILVER_ION: {siid: 19, aiid: 1},
    DreameVacuumAction.RESET_DETERGENT: {siid: 20, aiid: 1},
    DreameVacuumAction.RESET_SQUEEGEE: {siid: 24, aiid: 1},
    DreameVacuumAction.RESET_ONBOARD_DIRTY_WATER_TANK: {siid: 25, aiid: 1},
    DreameVacuumAction.RESET_DIRTY_WATER_TANK: {siid: 26, aiid: 1},
    DreameVacuumAction.RESET_DEODORIZER: {siid: 29, aiid: 1},
    DreameVacuumAction.RESET_WHEEL: {siid: 30, aiid: 1},
    DreameVacuumAction.RESET_SCALE_INHIBITOR: {siid: 31, aiid: 1},
    DreameVacuumAction.STREAM_VIDEO: {siid: 10001, aiid: 1},
    DreameVacuumAction.STREAM_AUDIO: {siid: 10001, aiid: 2},
    DreameVacuumAction.STREAM_PROPERTY: {siid: 10001, aiid: 3},
    DreameVacuumAction.STREAM_CODE: {siid: 10001, aiid: 4},
}

PROPERTY_AVAILABILITY: Final = {
    DreameVacuumProperty.CUSTOMIZED_CLEANING.name: lambda device: (
        not device.status.started
        and (device.status.has_saved_map or device.status.current_map is None)
        and not device.status.cleangenius_cleaning
    ),
    DreameVacuumProperty.TIGHT_MOPPING.name: lambda device: (
        (device.status.water_tank_or_mop_installed) and not device.status.cleangenius_cleaning
    ),
    DreameVacuumProperty.MULTI_FLOOR_MAP.name: lambda device: (
        not device.status.has_temporary_map and not device.status.started
    ),
    DreameVacuumProperty.SUCTION_LEVEL.name: lambda device: (
        not device.status.mopping
        and not (device.status.customized_cleaning and not (device.status.zone_cleaning or device.status.spot_cleaning))
        and not device.status.cleangenius_cleaning
        and not device.status.fast_mapping
        and not device.status.scheduled_clean
        and not device.status.cruising
        and not device.status.max_suction_power
    ),
    DreameVacuumAutoSwitchProperty.MAX_SUCTION_POWER.name: lambda device: (
        (
            (device.capability.max_suction_power_extended and device.status.mopping_after_sweeping)
            or device.status.sweeping
        )
        and not device.status.cleangenius_cleaning
        and not device.status.fast_mapping
        and not device.status.scheduled_clean
        and not device.status.cruising
        and not (device.status.customized_cleaning and not (device.status.zone_cleaning or device.status.spot_cleaning))
    ),
    DreameVacuumProperty.WATER_VOLUME.name: lambda device: (
        (device.status.water_tank_or_mop_installed)
        and not device.status.sweeping
        and not (device.status.customized_cleaning and not (device.status.zone_cleaning or device.status.spot_cleaning))
        and not device.status.cleangenius_cleaning
        and not device.status.fast_mapping
        and not device.status.scheduled_clean
        and not device.status.cruising
    ),
    DreameVacuumProperty.WETNESS_LEVEL.name: lambda device: (
        (device.status.water_tank_or_mop_installed)
        and not device.status.sweeping
        and not device.status.fast_mapping
        and not device.status.scheduled_clean
        and not device.status.cruising
        and not device.status.cleangenius_cleaning
        and not (device.status.customized_cleaning and not (device.status.zone_cleaning or device.status.spot_cleaning))
    ),
    DreameVacuumProperty.CLEANING_MODE.name: lambda device: (
        (not device.status.started or not device.status.mopping_after_sweeping)
        and not device.status.fast_mapping
        and not device.status.scheduled_clean
        and not device.status.cruising
        and (not device.status.customized_cleaning or not device.capability.custom_cleaning_mode)
        and not device.status.cleangenius_cleaning
        and not device.status.returning
        and not device.status.draining
        and not device.status.shortcut_task
    ),
    DreameVacuumProperty.CARPET_SENSITIVITY.name: lambda device: bool(
        device.get_property(DreameVacuumProperty.CARPET_BOOST)
    ),
    DreameVacuumProperty.CARPET_BOOST.name: lambda device: (
        not device.capability.carpet_recognition
        or not (not device.status.carpet_recognition or device.status.carpet_avoidance)
    ),
    DreameVacuumProperty.CARPET_CLEANING.name: lambda device: (
        device.status.carpet_recognition
        or device.capability.mop_pad_lifting_plus
        or device.capability.auto_carpet_cleaning
    ),
    DreameVacuumProperty.AUTO_EMPTY_FREQUENCY.name: lambda device: bool(
        device.get_property(DreameVacuumProperty.AUTO_DUST_COLLECTING)
    ),
    DreameVacuumProperty.CLEANING_TIME.name: lambda device: (
        not device.status.fast_mapping and not device.status.cruising
    ),
    DreameVacuumProperty.CLEANED_AREA.name: lambda device: (
        not device.status.fast_mapping and not device.status.cruising
    ),
    DreameVacuumProperty.RELOCATION_STATUS.name: lambda device: not device.status.fast_mapping,
    DreameVacuumProperty.AUTO_ADD_DETERGENT.name: lambda device: bool(
        device.get_property(DreameVacuumProperty.AUTO_ADD_DETERGENT) != 2
    ),
    DreameVacuumProperty.INTELLIGENT_RECOGNITION.name: lambda device: device.status.multi_map,
    DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE.name: lambda device: bool(
        device.get_property(DreameVacuumProperty.VOICE_ASSISTANT) == 1
    ),
    DreameVacuumProperty.STREAM_STATUS.name: lambda device: bool(
        device.get_property(DreameVacuumProperty.STREAM_STATUS) is not None
    ),
    DreameVacuumProperty.LOW_WATER_WARNING.name: lambda device: not device.status.auto_water_refilling_enabled,
    DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS.name: lambda device: bool(
        device.status.camera_light_brightness
        and device.status.camera_light_brightness != 101
        and device.status.stream_session is not None
    ),
    DreameVacuumProperty.DRYING_TIME.name: lambda device: bool(not device.status.smart_drying),
    DreameVacuumProperty.MOP_WASH_LEVEL.name: lambda device: device.status.self_clean,
    # task_type / cleaning_progress / drying_progress are intentionally NOT gated
    # here: they stay available and report their value (e.g. 0%) when idle instead
    # of going "unavailable" — friendlier for history graphs and automations.
    DreameVacuumProperty.CLEAN_CARPETS_FIRST.name: lambda device: (
        not (not device.status.carpet_recognition or device.status.carpet_avoidance)
    ),
    DreameVacuumAutoSwitchProperty.WIDER_CORNER_COVERAGE.name: lambda device: (
        not device.status.started
        and not device.status.fast_mapping
        and not device.status.washing
        and not device.status.washing_paused
    ),
    DreameVacuumAutoSwitchProperty.MOP_PAD_SWING.name: lambda device: (
        not device.status.started
        and not device.status.fast_mapping
        and not device.status.washing
        and not device.status.washing_paused
    ),
    DreameVacuumAutoSwitchProperty.MOP_EXTEND_FREQUENCY.name: lambda device: (
        not device.status.started
        and not device.status.fast_mapping
        and not device.status.washing
        and not device.status.washing_paused
    ),
    DreameVacuumAutoSwitchProperty.SELF_CLEAN_FREQUENCY.name: lambda device: (
        device.status.self_clean
        and not device.status.started
        and not device.status.fast_mapping
        and not device.status.cleangenius_cleaning
    ),
    DreameVacuumAutoSwitchProperty.STAIN_AVOIDANCE.name: lambda device: device.status.ai_fluid_detection,
    DreameVacuumAutoSwitchProperty.CLEANGENIUS.name: lambda device: (
        not device.status.started
        and not device.status.fast_mapping
        and not device.status.cruising
        and not device.status.spot_cleaning
        and not device.status.zone_cleaning
        and device.status.mop_pad_installed
    ),
    DreameVacuumProperty.CLEANGENIUS_MODE.name: lambda device: (
        not device.status.started
        and device.status.cleangenius_cleaning
        and not device.status.fast_mapping
        and not device.status.cruising
        and not device.status.spot_cleaning
        and not device.status.zone_cleaning
        and device.status.mop_pad_installed
    ),
    DreameVacuumAutoSwitchProperty.FLOOR_DIRECTION_CLEANING.name: lambda device: (
        device.status.floor_direction_cleaning_available
    ),
    DreameVacuumAutoSwitchProperty.MOPPING_TYPE.name: lambda device: (
        not device.status.started and not device.status.fast_mapping
    ),
    DreameVacuumStrAIProperty.AI_HUMAN_DETECTION.name: lambda device: device.status.ai_obstacle_detection,
    DreameVacuumAIProperty.AI_OBSTACLE_IMAGE_UPLOAD.name: lambda device: device.status.ai_obstacle_detection,
    DreameVacuumAIProperty.AI_OBSTACLE_PICTURE.name: lambda device: device.status.ai_obstacle_detection,
    DreameVacuumAIProperty.AI_PET_DETECTION.name: lambda device: device.status.ai_obstacle_detection,
    DreameVacuumAIProperty.AI_FURNITURE_DETECTION.name: lambda device: device.status.ai_obstacle_detection,
    DreameVacuumAIProperty.AI_FLUID_DETECTION.name: lambda device: device.status.ai_obstacle_detection,
    DreameVacuumAIProperty.FUZZY_OBSTACLE_DETECTION.name: lambda device: device.status.ai_obstacle_detection,
    DreameVacuumAIProperty.AI_PET_AVOIDANCE.name: lambda device: (
        device.status.ai_obstacle_detection and device.status.ai_pet_detection
    ),
    DreameVacuumAIProperty.PET_PICTURE.name: lambda device: (
        device.status.ai_obstacle_detection and device.status.ai_pet_detection
    ),
    DreameVacuumAIProperty.PET_FOCUSED_DETECTION.name: lambda device: (
        device.status.ai_obstacle_detection and device.status.ai_pet_detection
    ),
    DreameVacuumAutoSwitchProperty.INTENSIVE_CARPET_CLEANING.name: lambda device: (
        not (not device.status.carpet_recognition or device.status.carpet_avoidance)
    ),
    DreameVacuumAutoSwitchProperty.GAP_CLEANING_EXTENSION.name: lambda device: (
        device.status.mop_extend if device.capability.mop_extend else device.status.mop_pad_swing.value > 0
    ),
    DreameVacuumAutoSwitchProperty.MOPPING_UNDER_FURNITURES.name: lambda device: (
        device.status.mop_extend if device.capability.mop_extend else device.status.mop_pad_swing.value > 0
    ),
    DreameVacuumAutoSwitchProperty.AUTO_RECLEANING.name: lambda device: (
        not device.status.has_temporary_map
        and device.status.segments
        and not device.status.fast_mapping
        and not device.status.started
    ),
    DreameVacuumAutoSwitchProperty.AUTO_REWASHING.name: lambda device: (
        not device.status.has_temporary_map
        and device.status.segments
        and not device.status.fast_mapping
        and not device.status.started
    ),
    DreameVacuumAutoSwitchProperty.CLEANING_ROUTE.name: lambda device: (
        not device.status.has_temporary_map
        and device.status.segments
        and device.status.cleaning_route.value > 0
        and not device.status.fast_mapping
        and not device.status.started
        and (not device.status.customized_cleaning or not device.capability.custom_cleaning_mode)
        and not device.status.cleangenius_cleaning
        and device.status.custom_mopping_mode
    ),
    DreameVacuumAutoSwitchProperty.ULTRA_CLEAN_MODE.name: lambda device: device.status.self_clean,
    DreameVacuumProperty.FIRST_CLEANING_DATE.name: lambda device: device.get_property(
        DreameVacuumProperty.FIRST_CLEANING_DATE
    ),
    DreameVacuumProperty.WATER_TEMPERATURE.name: lambda device: (
        not device.status.smart_mop_washing and device.status.self_clean
    ),
    DreameVacuumProperty.SILENT_DRYING.name: lambda device: not device.status.drying,
    DreameVacuumProperty.SIDE_BRUSH_CARPET_ROTATE.name: lambda device: (
        device.status.carpet_recognition
        and not device.status.carpet_avoidance
        and device.status.carpet_cleaning.value != 6
    ),
    DreameVacuumProperty.DND_DISABLE_RESUME_CLEANING: lambda device: device.status.dnd,
    DreameVacuumProperty.DND_DISABLE_AUTO_EMPTY: lambda device: device.status.dnd,
    DreameVacuumProperty.DND_REDUCE_VOLUME: lambda device: device.status.dnd,
    DreameVacuumProperty.SMART_MOP_WASHING: lambda device: device.status.self_clean,
    "self_clean_area": lambda device: (
        device.status.self_clean
        and not device.status.cleangenius_cleaning
        and not device.status.fast_mapping
        and not device.status.self_clean_by_time
        and (device.status.self_clean_value or (device.status.current_map and not device.status.has_saved_map))
    ),
    "self_clean_time": lambda device: (
        device.status.self_clean
        and not device.status.cleangenius_cleaning
        and not device.status.fast_mapping
        and device.status.self_clean_by_time
        and (device.status.self_clean_value or (device.status.current_map and not device.status.has_saved_map))
    ),
    "self_clean_by_zone": lambda device: (
        device.status.self_clean
        and not device.status.cleangenius_cleaning
        and not device.status.fast_mapping
        and device.status.self_clean_value is not None
        and (not device.status.current_map or device.status.has_saved_map)
    ),
    "mop_clean_frequency": lambda device: (
        device.status.self_clean
        and not device.status.cleangenius_cleaning
        and not device.status.fast_mapping
        and device.status.self_clean_value is not None
    ),
    "mop_pad_humidity": lambda device: (
        (device.status.water_tank_or_mop_installed)
        and not device.status.cleangenius_cleaning
        and not device.status.sweeping
        and not (device.status.customized_cleaning and not (device.status.zone_cleaning or device.status.spot_cleaning))
        and not device.status.fast_mapping
        and not device.status.started
        and not device.status.scheduled_clean
        and not device.status.cruising
    ),
    "washing_mode": lambda device: device.status.self_clean,
    "map_rotation": lambda device: bool(
        device.status.selected_map is not None
        and device.status.selected_map.rotation is not None
        and not device.status.fast_mapping
        and device.status.has_saved_map
    ),
    "selected_map": lambda device: bool(
        device.status.multi_map
        and not device.status.fast_mapping
        and device.status.map_list
        and device.status.map_data_list
        and device.status.selected_map
        and device.status.selected_map.map_name
        and device.status.selected_map.map_id in device.status.map_list
    ),
    "current_room": lambda device: device.status.current_room is not None and not device.status.fast_mapping,
    "cleaning_history": lambda device: bool(device.status.last_cleaning_time is not None),
    "cruising_history": lambda device: bool(device.status.last_cruising_time is not None),
    "cleaning_sequence": lambda device: (
        not device.status.started
        and device.status.has_saved_map
        and device.status.current_segments
        and next(iter(device.status.current_segments.values())).order is not None
    ),
    "camera_light_brightness_auto": lambda device: (
        device.status.camera_light_brightness and device.status.stream_session is not None
    ),
    "dnd_start": lambda device: device.status.dnd,
    "dnd_end": lambda device: device.status.dnd,
    "off_peak_charging_start": lambda device: device.status.off_peak_charging,
    "off_peak_charging_end": lambda device: device.status.off_peak_charging,
    "custom_mopping_route": lambda device: (
        not device.status.started and not device.status.cleangenius_cleaning and not device.status.customized_cleaning
    ),
}

ACTION_AVAILABILITY: Final = {
    DreameVacuumAction.RESET_MAIN_BRUSH.name: lambda device: bool(device.status.main_brush_life < 100),
    DreameVacuumAction.RESET_SIDE_BRUSH.name: lambda device: bool(device.status.side_brush_life < 100),
    DreameVacuumAction.RESET_FILTER.name: lambda device: bool(device.status.filter_life < 100),
    DreameVacuumAction.RESET_SENSOR.name: lambda device: bool(device.status.sensor_dirty_life < 100),
    DreameVacuumAction.RESET_TANK_FILTER.name: lambda device: bool(device.status.tank_filter_life < 100),
    DreameVacuumAction.RESET_MOP_PAD.name: lambda device: bool(device.status.mop_life < 100),
    DreameVacuumAction.RESET_SILVER_ION.name: lambda device: bool(device.status.silver_ion_life < 100),
    DreameVacuumAction.RESET_DETERGENT.name: lambda device: bool(device.status.detergent_life < 100),
    DreameVacuumAction.RESET_SQUEEGEE.name: lambda device: bool(device.status.squeegee_life < 100),
    DreameVacuumAction.RESET_ONBOARD_DIRTY_WATER_TANK.name: lambda device: bool(
        device.status.onboard_dirty_water_tank_life is not None and device.status.onboard_dirty_water_tank_life < 100
    ),
    DreameVacuumAction.RESET_DIRTY_WATER_TANK.name: lambda device: bool(
        device.status.dirty_water_tank_life is not None and device.status.dirty_water_tank_life < 100
    ),
    DreameVacuumAction.RESET_DEODORIZER.name: lambda device: (
        device.status.deodorizer_life is not None and bool(device.status.deodorizer_life < 100)
    ),
    DreameVacuumAction.RESET_WHEEL.name: lambda device: (
        device.status.wheel_dirty_life is not None and bool(device.status.wheel_dirty_life < 100)
    ),
    DreameVacuumAction.RESET_SCALE_INHIBITOR.name: lambda device: (
        device.status.scale_inhibitor_life is not None and bool(device.status.scale_inhibitor_life < 100)
    ),
    DreameVacuumAction.START_AUTO_EMPTY.name: lambda device: device.status.dust_collection_available,
    DreameVacuumAction.CLEAR_WARNING.name: lambda device: (
        device.status.has_warning or device.status.low_water or device.status.draining_complete
    ),
    DreameVacuumAction.START.name: lambda device: (
        not (device.status.started or device.status.draining or device.status.self_repairing)
        or device.status.paused
        or device.status.returning
        or device.status.returning_paused
    ),
    DreameVacuumAction.START_CUSTOM.name: lambda device: not (device.status.draining or device.status.self_repairing),
    # DreameVacuumAction.START_CUSTOM.name: lambda device: not (device.status.started or device.status.returning or device.status.returning_paused or device.status.draining or device.status.self_repairing),
    DreameVacuumAction.CHARGE.name: lambda device: not device.status.docked and not device.status.returning,
    DreameVacuumAction.PAUSE.name: lambda device: (
        device.status.started
        and not (
            device.status.returning_paused
            or device.status.paused
            or device.status.draining
            or device.status.self_repairing
        )
    ),
    DreameVacuumAction.STOP.name: lambda device: (
        (
            device.status.started
            or device.status.returning
            or device.status.washing
            or device.status.washing_paused
            or device.status.drying
            or device.status.returning_to_wash_paused
            or device.status.paused
        )
        and not device.status.draining
        and not device.status.self_repairing
    ),
    "start_fast_mapping": lambda device: (
        device.status.mapping_available and not device.status.draining and not device.status.self_repairing
    ),
    "start_mapping": lambda device: (
        device.status.mapping_available and not device.status.draining and not device.status.self_repairing
    ),
    "manual_drying": lambda device: (
        device.status.drying_available and not device.status.draining and not device.status.self_repairing
    ),
    "water_tank_draining": lambda device: device.status.water_draining_available and not device.status.self_repairing,
    "base_station_self_repair": lambda device: (
        not device.status.draining
        and not device.status.self_repairing
        and not device.status.started
        and not device.status.paused
        and not device.status.returning
        and not device.status.returning_paused
        and not device.status.returning_to_wash_paused
        and not device.status.washing
        and not device.status.washing_paused
        and not device.status.drying
    ),
    "base_station_cleaning": lambda device: (
        device.status.docked
        and not device.status.station_cleaning
        and device.status.water_tank_or_mop_installed
        and not device.status.draining
        and not device.status.self_repairing
        and not device.status.started
        and not device.status.paused
        and not device.status.washing
        and not device.status.washing_paused
        and not device.status.drying
        and not device.status.auto_emptying
    ),
    "start_recleaning": lambda device: not device.status.started and device.status.second_cleaning_available,
    "empty_water_tank": lambda device: (
        not device.draining and device.docked and not device.status.self_repairing and not device.status.washing
    ),
}


def PIID(
    property: DreameVacuumProperty,
    mapping: dict[DreameVacuumProperty, dict[str, int]] = DreameVacuumPropertyMapping,
) -> int | None:
    if property in mapping:
        return mapping[property][piid]
    return None


def DIID(
    property: DreameVacuumProperty,
    mapping: dict[DreameVacuumProperty, dict[str, int]] = DreameVacuumPropertyMapping,
) -> str | None:
    if property in mapping:
        return f"{mapping[property][siid]}.{mapping[property][piid]}"
    return None


def DID(siid: int, piid: int) -> DreameVacuumProperty | None:
    for prop in list(DreameVacuumProperty):
        mapping = DreameVacuumPropertyMapping.get(prop)
        if mapping is not None and siid == mapping["siid"] and piid == mapping["piid"]:
            return prop
    return None
