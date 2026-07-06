"""Dreame Vacuum device-state enums (charging, cleaning, errors, etc.)."""

from __future__ import annotations

from enum import IntEnum, StrEnum


class DreameVacuumChargingStatus(IntEnum):
    """Dreame Vacuum charging status"""

    UNKNOWN = -1
    CHARGING = 1
    NOT_CHARGING = 2
    CHARGING_COMPLETED = 3
    RETURN_TO_CHARGE = 5


class DreameVacuumErrorCode(IntEnum):
    """Dreame Vacuum error code"""

    UNKNOWN = -1
    NO_ERROR = 0
    DROP = 1
    CLIFF = 2
    BUMPER = 3
    GESTURE = 4
    BUMPER_REPEAT = 5
    DROP_REPEAT = 6
    OPTICAL_FLOW = 7
    BOX = 8
    TANKBOX = 9
    WATERBOX_EMPTY = 10
    BOX_FULL = 11
    BRUSH = 12
    SIDE_BRUSH = 13
    FAN = 14
    LEFT_WHEEL_MOTOR = 15
    RIGHT_WHEEL_MOTOR = 16
    TURN_SUFFOCATE = 17
    FORWARD_SUFFOCATE = 18
    CHARGER_GET = 19
    BATTERY_LOW = 20
    CHARGE_FAULT = 21
    BATTERY_PERCENTAGE = 22
    HEART = 23
    CAMERA_OCCLUSION = 24
    MOVE = 25
    FLOW_SHIELDING = 26
    INFRARED_SHIELDING = 27
    CHARGE_NO_ELECTRIC = 28
    BATTERY_FAULT = 29
    FAN_SPEED_ERROR = 30
    LEFT_WHEEL_SPEED = 31
    RIGHT_WHEEL_SPEED = 32
    BMI055_ACCE = 33
    BMI055_GYRO = 34
    XV7001 = 35
    LEFT_MAGNET = 36
    RIGHT_MAGNET = 37
    FLOW_ERROR = 38
    INFRARED_FAULT = 39
    CAMERA_FAULT = 40
    STRONG_MAGNET = 41
    WATER_PUMP = 42
    RTC = 43
    AUTO_KEY_TRIG = 44
    P3V3 = 45
    CAMERA_IDLE = 46
    BLOCKED = 47
    LDS_ERROR = 48
    LDS_BUMPER = 49
    WATER_PUMP_2 = 50
    FILTER_BLOCKED = 51
    EDGE = 54
    CARPET = 55
    LASER = 56
    EDGE_2 = 57
    ULTRASONIC = 58
    NO_GO_ZONE = 59
    ROUTE = 61
    ROUTE_2 = 62
    BLOCKED_2 = 63
    BLOCKED_3 = 64
    RESTRICTED = 65
    RESTRICTED_2 = 66
    RESTRICTED_3 = 67
    REMOVE_MOP = 68
    MOP_REMOVED = 69
    MOP_REMOVED_2 = 70
    MOP_PAD_STOP_ROTATE = 71
    MOP_PAD_STOP_ROTATE_2 = 72
    MOP_INSTALL_FAILED = 74
    LOW_BATTERY_TURN_OFF = 75
    DIRTY_TANK_NOT_INSTALLED = 76
    ROBOT_IN_HIDDEN_ROOM = 78
    BIN_FULL = 101
    BIN_OPEN = 102
    BIN_OPEN_2 = 103
    BIN_FULL_2 = 104
    WATER_TANK = 105
    DIRTY_WATER_TANK = 106
    WATER_TANK_DRY = 107
    DIRTY_WATER_TANK_2 = 108
    DIRTY_WATER_TANK_BLOCKED = 109
    DIRTY_WATER_TANK_PUMP = 110
    MOP_PAD = 111
    WET_MOP_PAD = 112
    CLEAN_MOP_PAD = 114
    CLEAN_TANK_LEVEL = 116
    STATION_DISCONNECTED = 117
    DIRTY_TANK_LEVEL = 118
    WASHBOARD_LEVEL = 119
    NO_MOP_IN_STATION = 120
    DUST_BAG_FULL = 121
    UNKNOWN_WARNING_2 = 122
    SELF_TEST_FAILED = 123
    WASHBOARD_NOT_WORKING = 124
    RETURN_TO_CHARGE_FAILED = 1000


class DreameVacuumState(IntEnum):
    """Dreame Vacuum state"""

    UNKNOWN = -1
    SWEEPING = 1
    IDLE = 2
    PAUSED = 3
    ERROR = 4
    RETURNING = 5
    CHARGING = 6
    MOPPING = 7
    DRYING = 8
    WASHING = 9
    RETURNING_TO_WASH = 10
    BUILDING = 11
    SWEEPING_AND_MOPPING = 12
    CHARGING_COMPLETED = 13
    UPGRADING = 14
    CLEAN_SUMMON = 15
    STATION_RESET = 16
    RETURNING_INSTALL_MOP = 17
    RETURNING_REMOVE_MOP = 18
    WATER_CHECK = 19
    CLEAN_ADD_WATER = 20
    WASHING_PAUSED = 21
    AUTO_EMPTYING = 22
    REMOTE_CONTROL = 23
    SMART_CHARGING = 24
    SECOND_CLEANING = 25
    HUMAN_FOLLOWING = 26
    SPOT_CLEANING = 27
    RETURNING_AUTO_EMPTY = 28
    WAITING_FOR_TASK = 29
    STATION_CLEANING = 30
    RETURNING_TO_DRAIN = 31
    DRAINING = 32
    AUTO_WATER_DRAINING = 33
    EMPTYING = 34
    DUST_BAG_DRYING = 35
    DUST_BAG_DRYING_PAUSED = 36
    HEADING_TO_EXTRA_CLEANING = 37
    EXTRA_CLEANING = 38
    FINDING_PET_PAUSED = 95
    FINDING_PET = 96
    SHORTCUT = 97
    MONITORING = 98
    MONITORING_PAUSED = 99
    INITIAL_DEEP_CLEANING = 101
    INITIAL_DEEP_CLEANING_PAUSED = 102
    SANITIZING = 103
    SANITIZING_WITH_DRY = 104


class DreameVacuumStateOld(IntEnum):
    """Dreame Vacuum old state"""

    UNKNOWN = -1
    SWEEPING = 1
    IDLE = 2
    PAUSED = 3
    ERROR = 4
    RETURNING = 5
    CHARGING = 6
    MOPPING = 7
    DRYING = 8
    WASHING = 9
    RETURNING_TO_WASH = 10
    BUILDING = 11
    SWEEPING_AND_MOPPING = 12
    CHARGING_COMPLETED = 13
    UPGRADING = 14
    CLEAN_SUMMON = 15
    STATION_RESET = 16
    RETURNING_INSTALL_MOP = 17
    RETURNING_REMOVE_MOP = 18
    REMOTE_CONTROL = 19
    CLEAN_ADD_WATER = 20
    MONITORING = 21
    MONITORING_PAUSED = 22
    WASHING_PAUSED = 23
    AUTO_EMPTYING = 24
    WATER_CHECK = 25
    SMART_CHARGING = 26


class DreameVacuumSuctionLevel(IntEnum):
    """Dreame Vacuum suction level"""

    UNKNOWN = -1
    QUIET = 0
    STANDARD = 1
    STRONG = 2
    TURBO = 3


class DreameVacuumCleaningMode(IntEnum):
    """Dreame Vacuum cleaning mode"""

    UNKNOWN = -1
    SWEEPING = 0
    MOPPING = 1
    SWEEPING_AND_MOPPING = 2
    MOPPING_AFTER_SWEEPING = 3


class DreameVacuumWaterTank(IntEnum):
    """Dreame Vacuum water tank status"""

    UNKNOWN = -1
    NOT_INSTALLED = 0
    INSTALLED = 1
    MOP_INSTALLED = 10
    MOP_IN_STATION = 99


class DreameVacuumWaterVolume(IntEnum):
    """Dreame Vacuum water volume"""

    UNKNOWN = -1
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class DreameVacuumMopPadHumidity(IntEnum):
    """Dreame Vacuum mop pad humidity"""

    UNKNOWN = -1
    SLIGHTLY_DRY = 1
    MOIST = 2
    WET = 3


class DreameVacuumCarpetSensitivity(IntEnum):
    """Dreame Vacuum carpet sensitivity"""

    UNKNOWN = -1
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class DreameVacuumCarpetCleaning(IntEnum):
    """Dreame Vacuum carpet cleaning"""

    UNKNOWN = -1
    NOT_SET = 0
    AVOIDANCE = 1
    ADAPTATION = 2
    REMOVE_MOP = 3
    ADAPTATION_WITHOUT_ROUTE = 4
    VACUUM_AND_MOP = 5
    IGNORE = 6
    CROSS = 7


class DreameVacuumRelocationStatus(IntEnum):
    """Dreame Vacuum relocation status"""

    UNKNOWN = -1
    LOCATED = 0
    LOCATING = 1
    FAILED = 10
    SUCCESS = 11


class DreameVacuumTaskStatus(IntEnum):
    """Dreame Vacuum task status"""

    UNKNOWN = -1
    COMPLETED = 0
    AUTO_CLEANING = 1
    ZONE_CLEANING = 2
    SEGMENT_CLEANING = 3
    SPOT_CLEANING = 4
    FAST_MAPPING = 5
    AUTO_CLEANING_PAUSED = 6
    ZONE_CLEANING_PAUSED = 7
    SEGMENT_CLEANING_PAUSED = 8
    SPOT_CLEANING_PAUSED = 9
    MAP_CLEANING_PAUSED = 10
    DOCKING_PAUSED = 11
    MOPPING_PAUSED = 12
    SEGMENT_MOPPING_PAUSED = 13
    ZONE_MOPPING_PAUSED = 14
    AUTO_MOPPING_PAUSED = 15
    AUTO_DOCKING_PAUSED = 16
    SEGMENT_DOCKING_PAUSED = 17
    ZONE_DOCKING_PAUSED = 18
    CRUISING_PATH = 20
    CRUISING_PATH_PAUSED = 21
    CRUISING_POINT = 22
    CRUISING_POINT_PAUSED = 23
    SUMMON_CLEAN_PAUSED = 24
    RETURNING_INSTALL_MOP = 25
    RETURNING_REMOVE_MOP = 26
    STATION_CLEANING = 27
    PET_FINDING = 30
    AUTO_CLEANING_WASHING_PAUSED = 31
    AREA_CLEANING_WASHING_PAUSED = 32
    CUSTOM_CLEANING_WASHING_PAUSED = 33


class DreameVacuumStatus(IntEnum):
    """Dreame Vacuum status"""

    UNKNOWN = -1
    IDLE = 0
    PAUSED = 1
    CLEANING = 2
    BACK_HOME = 3
    PART_CLEANING = 4
    FOLLOW_WALL = 5
    CHARGING = 6
    OTA = 7
    FCT = 8
    WIFI_SET = 9
    POWER_OFF = 10
    FACTORY = 11
    ERROR = 12
    REMOTE_CONTROL = 13
    SLEEPING = 14
    SELF_REPAIR = 15
    FACTORY_FUNCION_TEST = 16
    STANDBY = 17
    SEGMENT_CLEANING = 18
    ZONE_CLEANING = 19
    SPOT_CLEANING = 20
    FAST_MAPPING = 21
    CRUISING_PATH = 22
    CRUISING_POINT = 23
    SUMMON_CLEAN = 24
    SHORTCUT = 25
    PERSON_FOLLOW = 26
    WATER_CHECK = 1501


class DreameVacuumDustCollection(IntEnum):
    """Dreame Vacuum dust collection availability"""

    UNKNOWN = -1
    NOT_AVAILABLE = 0
    AVAILABLE = 1
    OVER_USE = 2
    NEVER = 3


class DreameVacuumAutoEmptyStatus(IntEnum):
    """Dreame Vacuum dust collection status"""

    UNKNOWN = -1
    IDLE = 0
    ACTIVE = 1
    NOT_PERFORMED = 2


class DreameVacuumSelfWashBaseStatus(IntEnum):
    """Dreame Vacuum self-wash base status"""

    UNKNOWN = -1
    IDLE = 0
    WASHING = 1
    DRYING = 2
    RETURNING = 3
    PAUSED = 4
    CLEAN_ADD_WATER = 5
    ADDING_WATER = 6
    RETURNING_FOR_DRY_MOP = 7


class DreameVacuumMopCleanFrequency(IntEnum):
    """Dreame Vacuum mop clean frequency"""

    UNKNOWN = -1
    BY_ROOM = 0
    EIGHT_SQUARE_METERS = 8
    TEN_SQUARE_METERS = 10
    FIVE_SQUARE_METERS = 5
    FIFTEEN_SQUARE_METERS = 15
    TWENTY_SQUARE_METERS = 20
    TWENTYFIVE_SQUARE_METERS = 25


class DreameVacuumMopWashLevel(IntEnum):
    """Dreame Vacuum mop wash level"""

    UNKNOWN = -1
    WATER_SAVING = 0
    DAILY = 1
    DEEP = 2


class DreameVacuumMoppingType(IntEnum):
    """Dreame Vacuum mopping type"""

    UNKNOWN = -1
    DAILY = 0
    ACCURATE = 1
    DEEP = 2


class DreameVacuumCleaningRoute(IntEnum):
    """Dreame Vacuum Cleaning route"""

    UNKNOWN = -1
    NOT_SET = 0
    STANDARD = 1
    INTENSIVE = 2
    DEEP = 3
    QUICK = 4


class DreameVacuumCustomMoppingRoute(IntEnum):
    """Dreame Vacuum Mopping route"""

    UNKNOWN = -2
    OFF = -1
    STANDARD = 0
    INTENSIVE = 1
    DEEP = 2


class DreameVacuumSegmentMoppingMode(IntEnum):
    """Dreame Vacuum Segment mopping effect"""

    UNKNOWN = -1
    AUTO = 0
    DAILY_DRY = 1
    ACCURATE_DRY = 2
    DEEP_DRY = 3
    DAILY_STANDARD = 4
    ACCURATE_STANDARD = 5
    DEEP_STANDARD = 6
    DAILY_WET = 7
    ACCURATE_WET = 8
    DEEP_WET = 9
    QUICK_DRY = 10
    QUICK_STANDARD = 11
    QUICK_WET = 12


class DreameVacuumWiderCornerCoverage(IntEnum):
    """Dreame Vacuum wider corner coverage"""

    UNKNOWN = -1
    OFF = 0
    HIGH_FREQUENCY = 1
    LOW_FREQUENCY = 7


class DreameVacuumMopPadSwing(IntEnum):
    """Dreame Vacuum mop pad swing"""

    UNKNOWN = -1
    OFF = 0
    AUTO = 1
    DAILY = 2
    WEEKLY = 7


class DreameVacuumMopExtendFrequency(IntEnum):
    """Dreame Vacuum mop extend frequency"""

    UNKNOWN = -1
    STANDARD = 7
    INTELLIGENT = 1
    HIGH = 2


class DreameVacuumSelfCleanFrequency(IntEnum):
    """Dreame Vacuum self clean frequency"""

    UNKNOWN = -1
    BY_ROOM = 0
    BY_AREA = 1
    BY_TIME = 2


class DreameVacuumAutoEmptyMode(IntEnum):
    """Dreame Vacuum auto empty mode"""

    UNKNOWN = -1
    OFF = 0
    STANDARD = 1
    HIGH_FREQUENCY = 2
    LOW_FREQUENCY = 3


class DreameVacuumCleanGenius(IntEnum):
    """Dreame Vacuum CleanGenius"""

    UNKNOWN = -1
    OFF = 0
    ROUTINE_CLEANING = 1
    DEEP_CLEANING = 2


class DreameVacuumCleanGeniusMode(IntEnum):
    """Dreame Vacuum CleanGenius mode"""

    UNKNOWN = -1
    VACUUM_AND_MOP = 2
    MOP_AFTER_VACUUM = 3


class DreameVacuumSecondCleaning(IntEnum):
    """Dreame Vacuum Second Cleaning mode"""

    UNKNOWN = -1
    OFF = 0
    IN_DEEP_MODE = 1
    IN_ALL_MODES = 2


class DreameVacuumFloorMaterial(IntEnum):
    """Dreame Vacuum floor material"""

    UNKNOWN = -1
    NONE = 0
    WOOD = 1
    TILE = 2
    MEDIUM_PILE_CARPET = 5
    LOW_PILE_CARPET = 6
    CARPET = 7


class DreameVacuumFloorMaterialDirection(IntEnum):
    """Dreame Vacuum floor direction"""

    UNKNOWN = -1
    HORIZONTAL = 0
    VERTICAL = 90


class DreameVacuumSegmentVisibility(IntEnum):
    """Dreame Vacuum segment visibility"""

    HIDDEN = 0
    VISIBLE = 1


class DreameVacuumVoiceAssistantLanguage(StrEnum):
    """Dreame Vacuum assistant language"""

    DEFAULT = ""
    ENGLISH = "EN"
    GERMAN = "DE"
    CHINESE = "ZH"


class DreameVacuumStreamStatus(IntEnum):
    """Dreame Vacuum stream status"""

    UNKNOWN = -1
    IDLE = 0
    VIDEO = 1
    AUDIO = 2
    RECORDING = 3


class DreameVacuumLowWaterWarning(IntEnum):
    """Dreame Vacuum low water warning"""

    UNKNOWN = -1
    NO_WARNING = 0
    NO_WATER_LEFT_DISMISS = 1
    NO_WATER_LEFT = 2
    NO_WATER_LEFT_AFTER_CLEAN = 3
    NO_WATER_FOR_CLEAN = 4
    LOW_WATER = 5
    TANK_NOT_INSTALLED = 6


class DreameVacuumDrainageStatus(IntEnum):
    """Dreame Vacuum drainage status"""

    UNKNOWN = -1
    IDLE = 0
    DRAINING = 1
    DRAINING_SUCCESS = 2
    DRAINING_FAILED = 3


class DreameVacuumTaskType(IntEnum):
    """Dreame Vacuum task type status"""

    UNKNOWN = -1
    IDLE = 0
    STANDARD = 1
    STANDARD_PAUSED = 2
    CUSTOM = 3
    CUSTOM_PAUSED = 4
    SHORTCUT = 5
    SHORTCUT_PAUSED = 6
    SCHEDULED = 7
    SCHEDULED_PAUSED = 8
    SMART = 9
    SMART_PAUSED = 10
    PARTIAL = 11
    PARTIAL_PAUSED = 12
    SUMMON = 13
    SUMMON_PAUSED = 14
    WATER_STAIN = 15
    WATER_STAIN_PAUSED = 16
    BOOSTED_EDGE_CLEANING = 17
    HAIR_COMPRESSING = 18


class DreameVacuumMapRecoveryStatus(IntEnum):
    """Dreame Vacuum map recovery status"""

    UNKNOWN = -1
    IDLE = 0
    RUNNING = 2
    SUCCESS = 3
    FAIL = 4
    FAIL_2 = 5


class DreameVacuumMapBackupStatus(IntEnum):
    """Dreame Vacuum map backup status"""

    UNKNOWN = -1
    IDLE = 0
    RUNNING = 2
    SUCCESS = 3
    FAIL = 4


class DreameVacuumCleanWaterTankStatus(IntEnum):
    """Dreame Vacuum clean water tank status"""

    UNKNOWN = -1
    INSTALLED = 0
    NOT_INSTALLED = 1
    LOW_WATER = 2
    ACTIVE = 3


class DreameVacuumDirtyWaterTankStatus(IntEnum):
    """Dreame Vacuum dirty water tank status"""

    UNKNOWN = -1
    INSTALLED = 0
    NOT_INSTALLED_OR_FULL = 1


class DreameVacuumDustBagStatus(IntEnum):
    """Dreame Vacuum dust bag status"""

    UNKNOWN = -1
    INSTALLED = 0
    NOT_INSTALLED = 1
    CHECK = 2


class DreameVacuumDetergentStatus(IntEnum):
    """Dreame Vacuum detergent status"""

    UNKNOWN = -1
    INSTALLED = 0
    DISABLED = 1
    LOW_DETERGENT = 2


class DreameVacuumHotWaterStatus(IntEnum):
    """Dreame Vacuum hot water status"""

    UNKNOWN = -1
    DISABLED = 0
    ENABLED = 1


class DreameVacuumStationDrainageStatus(IntEnum):
    """Dreame Vacuum station drainage status"""

    UNKNOWN = -1
    IDLE = 0
    DRAINING = 1


class DreameVacuumWashingMode(IntEnum):
    """Dreame Vacuum washing mode"""

    UNKNOWN = -1
    LIGHT = 0
    STANDARD = 1
    DEEP = 2
    ULTRA_WASHING = 3


class DreameVacuumWaterTemperature(IntEnum):
    """Dreame Vacuum water temperature"""

    UNKNOWN = -1
    NORMAL = 0
    MILD = 1
    WARM = 2
    HOT = 3
