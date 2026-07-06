from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum
import json
import math
import time
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from .device import DreameVacuumDevice

from .types_attributes import *
from .types_enums import *
from .types_properties import *


class RobotType(IntEnum):
    LIDAR = 0
    VSLAM = 1
    MOPPING = 2
    SWEEPING_AND_MOPPING = 3


class PathType(StrEnum):
    LINE = "L"
    SWEEP = "S"
    SWEEP_AND_MOP = "W"
    MOP = "M"


class ObstacleType(IntEnum):
    UNKNOWN = 0
    BASE = 128
    SCALE = 129
    THREAD = 130
    WIRE = 131
    TOY = 132
    SHOES = 133
    SOCK = 134
    POO = 135
    TRASH_CAN = 136
    FABRIC = 137
    POWER_STRIP = 138
    LIQUID_STAIN = 139
    OBSTACLE = 142
    PET = 158
    # ??? = 160
    # ??? = 166
    DETECTED_STAIN = 169
    CLEANING_TOOLS = 163
    NEGLECTED_ROOM = 200
    EASY_TO_STUCK_FURNITURE = 201
    MIXED_STAIN = 202
    LARGE_PARTICLES = 205
    DRIED_STAIN = 206


class ObstacleIgnoreStatus(IntEnum):
    UNKNOWN = -1
    NOT_IGNORED = 0
    MANUALLY_IGNORED = 1
    AUTOMATICALLY_IGNORED = 2


class ObstaclePictureStatus(IntEnum):
    UNKNOWN = -1
    DISABLED = 0
    UPLOADING = 1
    UPLOADED = 2
    UPLOAD_FAILED = 3


class SegmentNeglectReason(IntEnum):
    BLOCKED_BY_VIRTUAL_WALL = 2
    BLOCKED_BY_DOOR = 3
    BLOCKED_BY_THRESHOLD = 4
    BLOCKED_BY_OBSTACLE = 5
    BLOCKED_BY_CARPET = 6
    BLOCKED_BY_DETECTED_CARPET = 7
    BLOCKED_BY_HIDDEN_OBSTACLE = 8
    BLOCKED_BY_DYNAMIC_OBSTACLE = 9
    PASSAGE_TOO_LOW = 10
    STEP_TOO_LOW = 27


class TaskInterruptReason(IntEnum):
    UNKNOWN = -1
    TASK_COMPLETED = 0
    ROBOT_LIFTED = 11
    ROBOT_FALLEN = 12
    CLIFF_SENSOR_ERROR = 13
    MOP_PAD_REMOVED = 14
    MOP_PAD_FALLEN_OFF = 15
    MOP_PAD_STUCK = 16
    MOP_PAD_FALLEN_OFF_BY_TABLE = 17
    MOP_PAD_FALLEN_OFF_BY_OBSTACLE = 18
    MOP_PAD_ABNORMALLY_REMOVED = 19
    MOP_PAD_FALLEN_OFF_CROSSING_OBSTACLE = 20
    BRUSH_ENTANGLED_BY_OBSTACLE = 21
    BRUSH_ENTANGLED_BY_CARPET = 22
    BRUSH_ENTANGLED_BY_OBJECT = 23
    LASER_DISTANCE_SENSOR_ERROR = 24
    ROBOT_IS_STUCK_ON_STEP = 25
    ROBOT_IS_STUCK_ON_OBSTACLE = 26
    BASE_STATION_POWERED_OFF = 27
    ABNORMAL_DOCKING = 101
    CANNOT_FIND_BASE_STATION = 102


class FurnitureType(IntEnum):
    SINGLE_BED = 1
    DOUBLE_BED = 2
    ARM_CHAIR = 3
    TWO_SEAT_SOFA = 4
    THREE_SEAT_SOFA = 5
    DINING_TABLE = 6
    NIGHTSTANT = 7
    COFFEE_TABLE = 8
    TOILET = 9
    LITTER_BOX = 10
    PET_BED = 11
    FOOD_BOWL = 12
    PET_TOILET = 13
    REFRIGERATOR = 14
    WASHING_MACHINE = 15
    ENCLOSED_LITTER_BOX = 16
    AIR_CONDITIONER = 17
    TV_CABINET = 18
    BOOKSHELF = 19
    SHOE_CABINET = 20
    WARDROBE = 21
    GREENERY = 22
    FLOOR_MIRROR = 23
    L_SHAPED_SOFA = 24
    ROUND_COFFEE_TABLE = 25
    TABLE = 26
    ARM_CHAIR_NARROW = 29
    THREE_SEAT_SOFA_NARROW = 30
    L_SHAPED_SOFA_RIGHT = 31


class CleansetType(IntEnum):
    NONE = 0
    DEFAULT = 1
    CLEANING_MODE = 2
    CUSTOM_MOPPING_ROUTE = 3
    CLEANING_ROUTE = 4
    WETNESS_LEVEL = 5
    WETNESS_LEVEL_MAX_15 = 6


class DeviceCapability(IntEnum):
    MOP_PAD_UNMOUNTING = 1
    DRAINAGE = 2
    MOPPING_AFTER_SWEEPING = 3
    MAX_SUCTION_POWER = 4
    OBSTACLE_IMAGE_CROP = 5
    UV_STERILIZATION = 6
    MOP_PAD_SWING = 7
    HOT_WASHING = 8
    AUTO_EMPTY_MODE = 9
    FLOOR_DIRECTION_CLEANING = 10
    LARGE_PARTICLES_BOOST = 11
    SEGMENT_VISIBILITY = 12
    MOP_PAD_SWING_PLUS = 13
    AUTO_REWASHING = 14
    MOP_PAD_LIFTING_PLUS = 15
    PET_FURNITURE = 16
    CLEANING_ROUTE = 17
    MOPPING_SETTINGS = 18
    SEGMENT_SLOW_CLEAN_ROUTE = 19
    SMALL_SELF_CLEAN_AREA = 20
    TASK_TYPE = 21
    ULTRA_CLEAN_MODE = 22
    EXTENDED_FURNITURES = 23
    SELF_CLEAN_FREQUENCY = 24
    CLEANGENIUS = 25
    CLEANGENIUS_AUTO = 26
    FLUID_DETECTION = 27
    INTENSIVE_CARPET_CLEANING = 28
    CLEAN_CARPETS_FIRST = 29
    WETNESS_LEVEL = 30
    AUTO_RENAME_SEGMENT = 31
    DISABLE_SENSOR_CLEANING = 32
    FLOOR_MATERIAL = 33
    GEN5 = 34
    NEW_FURNITURES = 35
    SAVED_FURNITURES = 36
    OBSTACLES = 37
    WATER_CHECK = 38
    AUTO_CARPET_CLEANING = 39
    SEGMENT_MOPPING_SETTINGS = 40
    SEGMENT_MOPPING_TYPE = 41
    MOPPING_TYPE = 42
    MAX_SUCTION_POWER_EXTENDED = 43
    AUTO_RECLEANING = 44
    NEW_STATE = 45
    CAMERA_STREAMING = 46
    DETERGENT = 47
    CLEANGENIUS_MODE = 48
    SIDE_REACH = 49
    WATER_TEMPERATURE = 50
    WASHING_MODE = 51
    SMART_MOP_WASHING = 52
    DND_FUNCTIONS = 53
    RAMPS = 54
    VIRTUAL_TRACKS = 55
    DEODORIZER = 56
    WHEEL = 57
    SCALE_INHIBITOR = 58
    SILENT_DRYING = 59
    HAIR_COMPRESSION = 60
    SIDE_BRUSH_CARPET_ROTATE = 61
    AUTO_LDS_LIFTING = 62
    AREA_ROTATION = 63
    MOP_PAD_LIFTING = 64
    MOP_WASHING_WITH_DETERGENT = 65
    CARPET_CROSSING = 66
    DYNAMIC_OBSTACLE_CLEAN = 67
    OBSTACLE_CROSSING = 68
    DOUBLE_DETERGENT = 69
    MOP_TEMPERATURE = 70
    DUST_BAG_DRYING = 71
    LDS_LIFTING_FREQUENCY = 72
    PRESSURIZED_CLEANING = 73
    SCRAPER_FREQUENCY = 74
    CARPET_MATERIAL = 75
    CARPET_TYPE = 76
    CARPET_CLEANSET_V2 = 77
    CARPET_CLEANSET_V3 = 78
    LOW_LYING_AREAS = 79
    LOW_LYING_AREA_DELETE = 80
    LASER_OBSTACLE = 81


class DreameVacuumDeviceCapability:
    def __init__(self, device: DreameVacuumDevice) -> None:
        self.key = None
        self.list = None
        self.lidar_navigation = True
        self.multi_floor_map = True
        self.ai_detection = False
        self.self_wash_base = False
        self.auto_empty_base = False
        self.mop_pad_lifting = False
        self.mop_pad_lifting_plus = False
        self.customized_cleaning = False
        self.auto_switch_settings = False
        self.mop_pad_unmounting = False
        self.mopping_after_sweeping = False
        self.wifi_map = False
        self.backup_map = False
        self.dnd = False
        self.dnd_task = False
        self.shortcuts = False
        self.drainage = False
        self.carpet_recognition = False
        self.fill_light = False
        self.voice_assistant = False
        self.pet_detective = False
        self.hot_washing = False
        self.mop_pad_swing = False
        self.mop_pad_swing_plus = False
        self.smart_drying = False
        self.off_peak_charging = False
        self.max_suction_power = False
        self.obstacle_image_crop = False
        self.uv_sterilization = False
        self.self_clean_frequency = False
        self.auto_empty_mode = False
        self.map_object_offset = False
        self.robot_type = RobotType.LIDAR
        self.tight_mopping = False
        self.floor_material = False
        self.floor_direction_cleaning = False
        self.segment_visibility = False
        self.cleangenius = False
        self.cleangenius_auto = False
        self.large_particles_boost = False
        self.fluid_detection = False
        self.intensive_carpet_cleaning = False
        self.mopping_settings = False
        self.custom_mopping_route = False
        self.cleaning_route = False
        self.segment_slow_clean_route = True
        self.pet_furniture = False
        self.task_type = False
        self.empty_water_tank = False
        self.disable_sensor_cleaning = False
        self.auto_rename_segment = False
        self.ultra_clean_mode = False
        self.clean_carpets_first = False
        self.mop_clean_frequency = False
        self.small_self_clean_area = False
        self.saved_furnitures = False
        self.extended_furnitures = False
        self.new_furnitures = False
        self.wetness = False
        self.wetness_level = False
        self.obstacles = False
        self.water_check = False
        self.auto_carpet_cleaning = False
        self.segment_mopping_settings = False
        self.segment_mopping_type = False
        self.mopping_type = False
        self.mopping_mode = False
        self.auto_charging = False
        self.max_suction_power_extended = False
        self.auto_recleaning = False
        self.auto_rewashing = False
        self.new_state = False
        self.camera_streaming = False
        self.gen5 = False
        self.detergent = False
        self.embedded_tank = False
        self.cleangenius_mode = False
        self.side_reach = False
        self.water_temperature = False
        self.washing_mode = False
        self.smart_mop_washing = False
        self.dnd_functions = False
        self.ramps = False
        self.virtual_tracks = False
        self.wheel = False
        self.scale_inhibitor = False
        self.deodorizer = False
        self.silent_drying = False
        self.hair_compression = False
        self.side_brush_carpet_rotate = False
        self.auto_lds_lifting = False
        self.station_cleaning = False
        self.mijia = False
        self.area_rotation = False
        self.mop_washing_with_detergent = False
        self.carpet_crossing = False
        self.dynamic_obstacle_clean = False
        self.obstacle_crossing = False
        self.double_detergent = False
        self.mop_temperature = False
        self.dust_bag_drying = False
        self.lds_lifting_frequency = False
        self.pressurized_cleaning = False
        self.scraper_frequency = False
        self.laser_obstacle = False
        self.battery_charge_level = False
        self.carpet_material = False
        self.carpet_type = False
        self.carpet_cleanset_v2 = False
        self.carpet_cleanset_v3 = False
        self.low_lying_areas = False
        self.low_lying_area_delete = False
        self._custom_cleaning_mode = False
        self._capability = None
        self._device = device

    def load(self, device_info: list[Any]) -> None:
        info = self._device.info
        if info is None or info.model is None:
            raise Exception("Unsupported Device!")
        model = info.model[(info.model.rfind(".") + 1) :]
        if model not in device_info[3]:
            raise Exception("Unsupported Device!")
        device = device_info[0][device_info[3][model]]
        if not device or not (len(device) == 3 or len(device) == 4) or device[2] < 0:
            raise Exception("Unsupported Device!")
        self._capability = device_info[1][device[2]]
        if self._capability is None:
            raise Exception("Device capability missing!")
        if len(device) == 4:
            if device[3] < 0 or device[3] >= len(device_info[2]):
                raise Exception("Device key missing!")
            self.key = device_info[2][device[3]]
            if not self.key or len(self.key) < 1:
                raise Exception("Device Key missing!")

        self.lidar_navigation = bool(self._device.get_property(DreameVacuumProperty.MAP_SAVING) is None)
        self.multi_floor_map = bool(
            self._device.get_property(DreameVacuumProperty.MULTI_FLOOR_MAP) is not None and self.lidar_navigation
        )
        self.ai_detection = bool(self._device.get_property(DreameVacuumProperty.AI_DETECTION) is not None)
        self.self_wash_base = bool(self._device.get_property(DreameVacuumProperty.SELF_WASH_BASE_STATUS) is not None)
        self.auto_empty_base = bool(self._device.get_property(DreameVacuumProperty.DUST_COLLECTION) is not None)
        self.customized_cleaning = bool(self._device.get_property(DreameVacuumProperty.CUSTOMIZED_CLEANING) is not None)
        self.tight_mopping = bool(self._device.get_property(DreameVacuumProperty.TIGHT_MOPPING) is not None)
        self.auto_switch_settings = bool(
            self._device.get_property(DreameVacuumProperty.AUTO_SWITCH_SETTINGS) is not None
        )
        self.carpet_recognition = bool(
            self._device.get_property(DreameVacuumProperty.CARPET_RECOGNITION) is not None
            or self._device.get_property(DreameVacuumProperty.CARPET_CLEANING) is not None
        )
        self.wifi_map = bool(self._device.get_property(DreameVacuumProperty.WIFI_MAP) is not None)
        self.backup_map = bool(self._device.get_property(DreameVacuumProperty.MAP_BACKUP_STATUS) is not None)
        self.dnd_task = bool(self._device.get_property(DreameVacuumProperty.DND_TASK) is not None)
        self.dnd = bool(self.dnd_task or self._device.get_property(DreameVacuumProperty.DND) is not None)
        self.shortcuts = bool(self._device.get_property(DreameVacuumProperty.SHORTCUTS) is not None)
        self.off_peak_charging = bool(self._device.get_property(DreameVacuumProperty.OFF_PEAK_CHARGING) is not None)
        camera_light = self._device.get_property(DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS)
        self.voice_assistant = bool(self._device.get_property(DreameVacuumProperty.VOICE_ASSISTANT) is not None)

        if self._capability:
            version = self._device.info.version if self._device.info.version else 1
            for v in self._capability:
                capability = v[0]
                if capability in DeviceCapability._value2member_map_:
                    capability = DeviceCapability(capability)
                    param = capability.name.lower()
                    if param and hasattr(self, param):
                        setattr(self, param, bool(version >= v[1]))

        # self.camera_streaming = bool(
        #    self.camera_streaming and (camera_light is not None or self._device.get_property(DreameVacuumProperty.CRUISE_SCHEDULE) is not None)
        # )
        self.detergent = bool(self.detergent or self._device.get_property(DreameVacuumProperty.DETERGENT_LEFT))
        self.fill_light = bool(
            self.camera_streaming
            and camera_light is not None
            and len(camera_light) < 5
            and str(camera_light).isnumeric()
        )
        self.mop_pad_swing = bool(self.mop_pad_swing or self.mop_pad_swing_plus)
        self.mop_pad_unmounting = bool(
            self.mop_pad_unmounting and self._device.get_property(DreameVacuumProperty.AUTO_MOUNT_MOP) is not None
        )
        self.drainage = bool(
            self.drainage and self._device.get_property(DreameVacuumProperty.DRAINAGE_STATUS) is not None
        )
        self.pet_detective = bool(
            self.pet_detective and self._device.get_property(DreameVacuumProperty.PET_DETECTIVE) is not None
        )
        self.mopping_settings = self.mopping_settings or self.mopping_type
        self.segment_mopping_settings = self.segment_mopping_settings or self.segment_mopping_type
        self.task_type = bool(self.task_type and self._device.get_property(DreameVacuumProperty.TASK_TYPE) is not None)
        self.wetness = bool(
            self.wetness_level
            or (self.mopping_settings and self._device.get_property(DreameVacuumProperty.WETNESS_LEVEL))
        )
        if not self.cleaning_route:
            self.segment_slow_clean_route = False
        self.custom_mopping_route = self.mopping_settings and not self.cleaning_route
        self.disable_sensor_cleaning = (
            self.disable_sensor_cleaning
            or not self.lidar_navigation
            or self._device.get_property(DreameVacuumProperty.SENSOR_DIRTY_LEFT) is None
            or (
                not self.camera_streaming and self._device.get_property(DreameVacuumProperty.OBSTACLE_AVOIDANCE) is None
            )
        )
        self.mop_pad_lifting = bool(
            self.mop_pad_lifting
            or self.mop_pad_lifting_plus
            or self.mop_pad_unmounting
            or (self.self_wash_base and self.auto_empty_base)
        )
        self.map_object_offset = bool(self.lidar_navigation and "p20" not in self._device.info.model)
        self.floor_material = bool(self.mop_pad_lifting and self.carpet_recognition and not self.mop_clean_frequency)
        self.robot_type = (
            RobotType.SWEEPING_AND_MOPPING
            if self.self_wash_base and self.mop_pad_lifting
            else (
                RobotType.MOPPING
                if self.self_wash_base
                else RobotType.LIDAR
                if self.lidar_navigation
                else RobotType.VSLAM
            )
        )
        self.station_cleaning = bool(self.self_wash_base and self.gen5)
        if "xiaomi.vacuum." in self._device.info.model:
            self.mijia = True
            self.wifi_map = False
            self.mop_clean_frequency = True
            self.self_clean_frequency = False
            self.floor_material = "d110" in self._device.info.model
            self.off_peak_charging = False
            self.camera_streaming = False
            self.new_furnitures = False
            self.fill_light = False

        self.list = [
            key for key, value in self.__dict__.items() if not callable(value) and not key.startswith("_") and value
        ]
        if self.custom_cleaning_mode:
            self.list.append("custom_cleaning_mode")
        if self.cruising:
            self.list.append("cruising")
        if self.map:
            self.list.append("map")

    @property
    def map(self) -> bool:
        """Returns true when mapping feature is available."""
        return bool(self._device._map_manager is not None)

    @property
    def custom_cleaning_mode(self) -> bool:
        """Returns true if customized cleaning mode can be set to segments."""
        if self.auto_switch_settings and self.mop_pad_lifting:
            return True
        segments = self._device.status.current_segments
        if not self._custom_cleaning_mode:
            if segments:
                if next(iter(segments.values())).cleaning_mode is not None:
                    self._custom_cleaning_mode = True
                    return True
            else:
                self._custom_cleaning_mode = self.mop_pad_lifting
                return self.mop_pad_lifting
        return self._custom_cleaning_mode and (not segments or next(iter(segments.values())).cleaning_mode is not None)

    @property
    def cruising(self) -> bool:
        if not self.lidar_navigation or not self.camera_streaming:
            return False
        return bool(
            (self._device.status.current_map and self._device.status.current_map.predefined_points is not None)
            or self._device.get_property(DreameVacuumProperty.CRUISE_SCHEDULE) is not None
            or self._device.status.fill_light is not None
        )

    @property
    def mop_extend(self) -> bool:
        # Read the raw auto-switch property: status.mop_extend_frequency checks this
        # capability back, so going through it would recurse infinitely.
        return bool(
            self.mop_pad_swing
            and self._device.get_auto_switch_property(DreameVacuumAutoSwitchProperty.MOP_EXTEND_FREQUENCY) is not None
        )


class Point:
    def __init__(self, x: float, y: float, a: float | None = None) -> None:
        self.x = x
        self.y = y
        self.a = a

    def __str__(self) -> str:
        if self.a is None:
            return f"({self.x}, {self.y})"
        return f"({self.x}, {self.y}, a = {self.a})"

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Point):
            return NotImplemented
        return other is not None and self.x == other.x and self.y == other.y and self.a == other.a

    def as_dict(self) -> dict[str, Any]:
        if self.a is None:
            return {ATTR_X: self.x, ATTR_Y: self.y}
        return {ATTR_X: self.x, ATTR_Y: self.y, ATTR_A: self.a}

    def to_img(self, image_dimensions: MapImageDimensions, offset: bool = True) -> Point:
        return image_dimensions.to_img(self, offset)

    def to_coord(self, image_dimensions: MapImageDimensions, offset: bool = True) -> Point:
        return image_dimensions.to_coord(self, offset)

    def rotated(self, image_dimensions: MapImageDimensions, degree: int | None) -> Point:
        w = int(
            (image_dimensions.width * image_dimensions.scale)
            + image_dimensions.padding[0]
            + image_dimensions.padding[2]
            - image_dimensions.crop[0]
            - image_dimensions.crop[2]
        )
        h = int(
            (image_dimensions.height * image_dimensions.scale)
            + image_dimensions.padding[1]
            + image_dimensions.padding[3]
            - image_dimensions.crop[1]
            - image_dimensions.crop[3]
        )
        x = self.x
        y = self.y
        degree = degree or 0
        while degree > 0:
            tmp = y
            y = w - x
            x = tmp
            tmp = h
            h = w
            w = tmp
            degree = degree - 90
        return Point(x, y)

    def __mul__(self, other: float) -> Point:
        return Point(self.x * other, self.y * other, self.a)

    def __truediv__(self, other: float) -> Point:
        return Point(self.x / other, self.y / other, self.a)


class Path(Point):
    def __init__(self, x: float, y: float, path_type: PathType) -> None:
        super().__init__(x, y)
        self.path_type = path_type

    def as_dict(self) -> dict[str, Any]:
        attributes = {**super().as_dict()}
        if self.path_type:
            attributes[ATTR_TYPE] = self.path_type.value
        return attributes


class Obstacle(Point):
    def __init__(
        self,
        x: float,
        y: float,
        type: int,
        possibility: int | None,
        object_id: str | None = None,
        file_name: str | None = None,
        key: int | None = None,
        pos_x: float | None = None,
        pos_y: float | None = None,
        width: float | None = None,
        height: float | None = None,
        picture_status: int = 0,
        ignore_status: int = 0,
    ) -> None:
        super().__init__(x, y)
        self.type = ObstacleType(type) if type in ObstacleType._value2member_map_ else ObstacleType.UNKNOWN
        self.possibility = possibility
        self.object_id = object_id
        self.key = key
        self.file_name = file_name
        self.object_name = file_name
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.height = height
        self.width = width
        self.picture_status = (
            ObstaclePictureStatus(picture_status)
            if picture_status in ObstaclePictureStatus._value2member_map_
            else ObstaclePictureStatus.UNKNOWN
        )
        self.ignore_status = (
            ObstacleIgnoreStatus(ignore_status)
            if ignore_status in ObstacleIgnoreStatus._value2member_map_
            else ObstacleIgnoreStatus.UNKNOWN
        )
        self.id = self.object_id if self.object_id else f"0{int(self.x)}0{int(self.y)}"

        if file_name and "/" in file_name:
            self.object_name = file_name.split("/")[-1]
            if "-" in self.object_name:
                self.object_name = self.object_name.split("-")[0]
        if self.id:
            self.object_name = f"{self.id}-{self.object_name}"

        self.segment: str | None = None
        self.color_index: int | None = None

    def set_segment(self, map_data: MapData) -> None:
        if map_data and map_data.segments and map_data.pixel_type is not None and map_data.dimensions is not None:
            x = int((self.x - map_data.dimensions.left) / map_data.dimensions.grid_size)
            y = int((self.y - map_data.dimensions.top) / map_data.dimensions.grid_size)
            if x >= 0 and x < map_data.dimensions.width and y >= 0 and y < map_data.dimensions.height:
                obstacle_pixel = map_data.pixel_type[x, y]

                if obstacle_pixel not in map_data.segments:
                    for _k, v in map_data.segments.items():
                        if v.check_point(self.x, self.y, map_data.dimensions.grid_size * 4):
                            self.segment = v.name
                            self.color_index = v.color_index
                            break
                else:
                    self.segment = map_data.segments[obstacle_pixel].name
                    self.color_index = map_data.segments[obstacle_pixel].color_index

    def as_dict(self) -> dict[str, Any]:
        attributes = super().as_dict()
        attributes[ATTR_TYPE] = self.type.name.replace("_", " ").title()
        if self.possibility is not None:
            attributes[ATTR_POSSIBILTY] = self.possibility
        if self.picture_status is not None:
            attributes[ATTR_PICTURE_STATUS] = self.picture_status.name.replace("_", " ").title()
        if self.ignore_status is not None:
            attributes[ATTR_IGNORE_STATUS] = self.ignore_status.name.replace("_", " ").title()
        if self.segment is not None:
            attributes[ATTR_ROOM] = self.segment
        return attributes

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Obstacle):
            return NotImplemented
        return not (
            other is None
            or self.x != other.x
            or self.y != other.y
            or self.possibility != other.possibility
            or self.type != other.type
            or self.object_id != other.object_id
            or self.key != other.key
            or self.file_name != other.file_name
            or self.pos_x != other.pos_x
            or self.pos_y != other.pos_y
            or self.height != other.height
            or self.width != other.width
            or self.picture_status != other.picture_status
            or self.ignore_status != other.ignore_status
        )


class Zone:
    def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1

    def __str__(self) -> str:
        return f"[{self.x0}, {self.y0}, {self.x1}, {self.y1}]"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Zone):
            return NotImplemented
        return (
            other is not None
            and self.x0 == other.x0
            and self.y0 == other.y0
            and self.x1 == other.x1
            and self.y1 == other.y1
        )

    def __repr__(self) -> str:
        return self.__str__()

    def as_dict(self) -> dict[str, Any]:
        return {ATTR_X0: self.x0, ATTR_Y0: self.y0, ATTR_X1: self.x1, ATTR_Y1: self.y1}

    def as_area(self) -> Area:
        return Area(self.x0, self.y0, self.x0, self.y1, self.x1, self.y1, self.x1, self.y0)

    def to_img(self, image_dimensions: MapImageDimensions, offset: bool = True) -> Zone:
        p0 = Point(self.x0, self.y0).to_img(image_dimensions, offset)
        p1 = Point(self.x1, self.y1).to_img(image_dimensions, offset)
        return Zone(p0.x, p0.y, p1.x, p1.y)

    def to_coord(self, image_dimensions: MapImageDimensions, offset: bool = True) -> Zone:
        p0 = Point(self.x0, self.y0).to_coord(image_dimensions, offset)
        p1 = Point(self.x1, self.y1).to_coord(image_dimensions, offset)
        return Zone(p0.x, p0.y, p1.x, p1.y)

    def check_point(self, x: float, y: float, size: float) -> bool:
        return self.as_area().check_point(x, y, size)


class Segment(Zone):
    def __init__(
        self,
        segment_id: int,
        x0: float | None = None,
        y0: float | None = None,
        x1: float | None = None,
        y1: float | None = None,
        x: int | None = None,
        y: int | None = None,
        name: str | None = None,
        custom_name: str | None = None,
        index: int = 0,
        type: int = 0,
        icon: str | None = None,
        neighbors: list[int] | None = None,
        cleaning_times: int | None = None,
        suction_level: int | None = None,
        water_volume: int | None = None,
        cleaning_mode: int | None = None,
        mopping_settings: int | None = None,
        order: int | None = None,
        outline_points: list[list[int]] | None = None,
    ) -> None:
        super().__init__(x0 or 0, y0 or 0, x1 or 0, y1 or 0)
        self.segment_id = segment_id
        self.unique_id: Any = None
        self.x = x
        self.y = y
        self.name: str = name or ""
        self.custom_name = custom_name
        self.type = type
        self.index = index
        self.icon = icon
        self.neighbors = neighbors if neighbors is not None else []
        self.order = order
        self.cleaning_times = cleaning_times
        self.suction_level = suction_level
        self.water_volume = water_volume
        self.cleaning_mode = cleaning_mode
        self.mopping_settings = mopping_settings
        self._outline_points = outline_points
        self.wetness_level: int | None = None
        self.cleaning_route: int | None = None
        self.custom_mopping_route: int | None = None
        self.color_index: int | None = None
        self.floor_material: int | None = None
        self.floor_material_direction: int | None = None
        self.floor_material_rotated_direction: int | None = None
        self.visibility: int | None = None
        self.cleanset_type = CleansetType.NONE
        self.carpet_cleaning: int | None = None
        self.carpet_settings: int | None = None
        self.set_name()

    @property
    def mop_pad_humidity(self) -> int | None:
        return self.water_volume

    @property
    def icon_type(self) -> int:
        """Resolved type for icon lookup: custom name can override the robot-assigned type.

        Type 6 (Bathroom) uses a toilet icon in Dreame firmware but most users
        expect a bathtub.  We remap it to type 16 (bathtub) unless the custom
        name explicitly indicates a toilet (wc, toilet, toilette).
        """
        if self.custom_name:
            name_lower = self.custom_name.lower()
            for pattern, type_id in CUSTOM_NAME_TO_ICON_TYPE.items():
                if pattern in name_lower:
                    return type_id
        # Dreame type 6 icon is a toilet; use bathtub (16) instead
        if self.type == 6:
            return 16
        return self.type

    @property
    def outline(self) -> list[list[int]]:
        # Return custom outline if provided, otherwise calculate from bounding box
        if self._outline_points is not None:
            return self._outline_points
        return [
            [int(self.x0), int(self.y0)],
            [int(self.x0), int(self.y1)],
            [int(self.x1), int(self.y1)],
            [int(self.x1), int(self.y0)],
        ]

    @property
    def center(self) -> list[int | None]:
        return [self.x, self.y]

    @property
    def letter(self) -> str:
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return (
            f"{letters[((self.segment_id % 26) - 1)]}{math.floor(self.segment_id / 26)}"
            if self.segment_id > 26
            else letters[self.segment_id - 1]
        )

    def set_name(self) -> None:
        if self.type != 0 and SEGMENT_TYPE_CODE_TO_NAME.get(self.type):
            self.name = SEGMENT_TYPE_CODE_TO_NAME[self.type]
            if self.index > 0:
                self.name = f"{self.name} {self.index + 1}"
        elif self.custom_name is not None:
            self.name = self.custom_name
        else:
            self.name = f"Room {self.segment_id}"
        self.icon = SEGMENT_TYPE_CODE_TO_HA_ICON.get(self.type, "mdi:home-outline")
        if self.type == 0 and self.custom_name:
            name_lower = self.custom_name.lower()
            for pattern, icon in CUSTOM_NAME_TO_HA_ICON.items():
                if pattern in name_lower:
                    self.icon = icon
                    break

    def get_translated_name(self, language: str | None = None) -> str:
        """Get the translated name of the segment based on language."""
        if self.custom_name is not None:
            return self.custom_name

        if language and language in SEGMENT_TYPE_TRANSLATIONS:
            translations = SEGMENT_TYPE_TRANSLATIONS[language]
            if self.type != 0 and self.type in translations:
                name = translations[self.type]
                if self.index > 0:
                    name = f"{name} {self.index + 1}"
                return name
            if self.type == 0 and 0 in translations:
                return translations[0]

        # Fallback to English name
        return self.name

    def set_custom_carpet_settings(self, carpet_cleaning: int, carpet_settings: int | None = None) -> None:
        self.carpet_cleaning = carpet_cleaning
        self.carpet_settings = carpet_settings

    def next_type_index(self, type: int, segments: dict[int, Segment]) -> int:
        index = 0
        if type > 0:
            for segment_id in sorted(segments, key=lambda segment_id: segments[segment_id].index):
                if (
                    segment_id != self.segment_id
                    and segments[segment_id].type == type
                    and segments[segment_id].index == index
                ):
                    index = index + 1
        return index

    def name_list(self, segments: dict[int, Segment], language: str | None = None) -> dict[str, int]:
        result = {}
        translations = SEGMENT_TYPE_TRANSLATIONS.get(language, {}) if language else {}
        for k, v in SEGMENT_TYPE_CODE_TO_NAME.items():
            index = self.next_type_index(k, segments)
            name = translations.get(k, v)
            if index > 0:
                name = f"{name} {index + 1}"

            result[k] = name

        if self.type == 0:
            name = self.custom_name if self.custom_name else translations.get(0, f"Room {self.segment_id}")
        else:
            name = self.custom_name if self.custom_name else translations.get(0, f"Room {self.segment_id}")
        result[0] = name
        if self.type != 0:
            result[self.type] = self.get_translated_name(language)

        return {v: k for k, v in result.items()}

    def as_dict(self) -> dict[str, Any]:
        # Always include parent attributes (x, y, etc.)
        attributes = {**super(Segment, self).as_dict()}

        # If custom outline exists, add it (and it will override the parent's outline if any)
        if self._outline_points is not None:
            attributes["outline"] = self._outline_points

        if self.segment_id:
            attributes[ATTR_ROOM_ID] = self.segment_id
        if self.name is not None:
            attributes[ATTR_NAME] = self.name
        if self.custom_name is not None:
            attributes[ATTR_CUSTOM_NAME] = self.custom_name
        if self.order is not None:
            attributes[ATTR_ORDER] = self.order
        if self.cleaning_times is not None:
            attributes[ATTR_CLEANING_TIMES] = self.cleaning_times
        if self.suction_level is not None:
            attributes[ATTR_SUCTION_LEVEL] = self.suction_level
        if self.water_volume is not None:
            attributes[ATTR_WATER_VOLUME] = self.water_volume
        if self.wetness_level is not None and (
            self.cleanset_type == CleansetType.WETNESS_LEVEL or self.cleanset_type == CleansetType.WETNESS_LEVEL_MAX_15
        ):
            attributes[ATTR_WETNESS_LEVEL] = self.wetness_level
        if self.cleaning_mode is not None and self.cleanset_type != CleansetType.DEFAULT:
            attributes[ATTR_CLEANING_MODE] = self.cleaning_mode
        if self.custom_mopping_route is not None and self.cleanset_type == CleansetType.CUSTOM_MOPPING_ROUTE:
            attributes[ATTR_CUSTOM_MOPPING_ROUTE] = self.custom_mopping_route
        if self.cleaning_route is not None and self.cleanset_type != CleansetType.CUSTOM_MOPPING_ROUTE:
            attributes[ATTR_CLEANING_ROUTE] = self.cleaning_route
        if self.type is not None:
            attributes[ATTR_TYPE] = self.type
        if self.index is not None:
            attributes[ATTR_INDEX] = self.index
        if self.icon is not None:
            attributes[ATTR_ICON] = self.icon
        if self.color_index is not None:
            attributes[ATTR_COLOR_INDEX] = self.color_index
        if self.unique_id is not None:
            attributes[ATTR_UNIQUE_ID] = self.unique_id
        if self.floor_material is not None:
            attributes[ATTR_FLOOR_MATERIAL] = self.floor_material
        if self.floor_material_rotated_direction is not None:
            attributes[ATTR_FLOOR_MATERIAL_DIRECTION] = DreameVacuumFloorMaterialDirection(
                self.floor_material_rotated_direction
            ).name.title()
        if self.visibility is not None:
            attributes[ATTR_VISIBILITY] = DreameVacuumSegmentVisibility(int(self.visibility)).name.title()
        if self.x is not None and self.y is not None:
            attributes[ATTR_X] = self.x
            attributes[ATTR_Y] = self.y

        return attributes

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Segment):
            return NotImplemented
        return not (
            other is None
            or self.x0 != other.x0
            or self.y0 != other.y0
            or self.x1 != other.x1
            or self.y1 != other.y1
            or self.x != other.x
            or self.y != other.y
            or self.name != other.name
            or self.index != other.index
            or self.type != other.type
            or self.color_index != other.color_index
            or self.icon != other.icon
            or self.neighbors != other.neighbors
            or self.order != other.order
            or self.cleaning_times != other.cleaning_times
            or self.suction_level != other.suction_level
            or self.water_volume != other.water_volume
            or self.wetness_level != other.wetness_level
            or self.cleaning_mode != other.cleaning_mode
            or self.floor_material != other.floor_material
            or self.floor_material_direction != other.floor_material_direction
            or self.floor_material_rotated_direction != other.floor_material_rotated_direction
            or self.mopping_settings != other.mopping_settings
            or self.visibility != other.visibility
            or self.carpet_cleaning != other.carpet_cleaning
            or self.carpet_settings != other.carpet_settings
        )

    def __str__(self) -> str:
        return f"{{room_id: {self.segment_id}, outline: {self.outline}}}"

    def __repr__(self) -> str:
        return self.__str__()


class Wall:
    def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Wall):
            return NotImplemented
        return (
            other is not None
            and self.x0 == other.x0
            and self.y0 == other.y0
            and self.x1 == other.x1
            and self.y1 == other.y1
        )

    def __str__(self) -> str:
        return f"[{self.x0}, {self.y0}, {self.x1}, {self.y1}]"

    def __repr__(self) -> str:
        return self.__str__()

    def as_dict(self) -> dict[str, Any]:
        return {ATTR_X0: self.x0, ATTR_Y0: self.y0, ATTR_X1: self.x1, ATTR_Y1: self.y1}

    def to_img(self, image_dimensions: MapImageDimensions, offset: bool = True) -> Wall:
        p0 = Point(self.x0, self.y0).to_img(image_dimensions, offset)
        p1 = Point(self.x1, self.y1).to_img(image_dimensions, offset)
        return Wall(p0.x, p0.y, p1.x, p1.y)

    def to_coord(self, image_dimensions: MapImageDimensions, offset: bool = True) -> Wall:
        p0 = Point(self.x0, self.y0).to_coord(image_dimensions, offset)
        p1 = Point(self.x1, self.y1).to_coord(image_dimensions, offset)
        return Wall(p0.x, p0.y, p1.x, p1.y)

    def as_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


class Area:
    def __init__(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        angle: int | None = None,
    ) -> None:
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.x3 = x3
        self.y3 = y3
        self.angle = angle

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Area):
            return NotImplemented
        return (
            other is not None
            and self.x0 == other.x0
            and self.y0 == other.y0
            and self.x1 == other.x1
            and self.y1 == other.y1
            and self.x2 == other.x2
            and self.y2 == other.y2
            and self.x3 == other.x3
            and self.y3 == other.y3
            and self.angle == other.angle
        )

    def __str__(self) -> str:
        return f"[{self.x0}, {self.y0}, {self.x1}, {self.y1}, {self.x2}, {self.y2}, {self.x3}, {self.y3}]"

    def __repr__(self) -> str:
        return self.__str__()

    def as_dict(self) -> dict[str, Any]:
        return {
            ATTR_X0: self.x0,
            ATTR_Y0: self.y0,
            ATTR_X1: self.x1,
            ATTR_Y1: self.y1,
            ATTR_X2: self.x2,
            ATTR_Y2: self.y2,
            ATTR_X3: self.x3,
            ATTR_Y3: self.y3,
            ATTR_ANGLE: self.angle,
        }

    def as_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1, self.x2, self.y2, self.x3, self.y3]

    def to_img(self, image_dimensions: MapImageDimensions, offset: bool = True) -> Area:
        if self.angle:
            theta = -self.angle * math.pi / 180
            cosang = math.cos(theta)
            sinang = math.sin(theta)
            cx = (self.x0 + self.x1 + self.x2 + self.x3) / 4
            cy = (self.y0 + self.y1 + self.y2 + self.y3) / 4

            coords = self.as_list()
            for i in range(0, 8, 2):
                tx = coords[i] - cx
                ty = coords[i + 1] - cy
                coords[i] = (tx * cosang + ty * sinang) + cx
                coords[i + 1] = (-tx * sinang + ty * cosang) + cy

            p0 = Point(coords[0], coords[1]).to_img(image_dimensions, offset)
            p1 = Point(coords[2], coords[3]).to_img(image_dimensions, offset)
            p2 = Point(coords[4], coords[5]).to_img(image_dimensions, offset)
            p3 = Point(coords[6], coords[7]).to_img(image_dimensions, offset)
        else:
            p0 = Point(self.x0, self.y0).to_img(image_dimensions, offset)
            p1 = Point(self.x1, self.y1).to_img(image_dimensions, offset)
            p2 = Point(self.x2, self.y2).to_img(image_dimensions, offset)
            p3 = Point(self.x3, self.y3).to_img(image_dimensions, offset)
        return Area(p0.x, p0.y, p1.x, p1.y, p2.x, p2.y, p3.x, p3.y)

    def to_coord(self, image_dimensions: MapImageDimensions, offset: bool = True) -> Area:
        p0 = Point(self.x0, self.y0).to_coord(image_dimensions, offset)
        p1 = Point(self.x1, self.y1).to_coord(image_dimensions, offset)
        p2 = Point(self.x2, self.y2).to_coord(image_dimensions, offset)
        p3 = Point(self.x3, self.y3).to_coord(image_dimensions, offset)
        return Area(p0.x, p0.y, p1.x, p1.y, p2.x, p2.y, p3.x, p3.y)

    def check_size(self, size: float) -> bool:
        return self.x2 - self.x0 == size and self.y2 - self.y1 == size

    def check_point(self, x: float, y: float, size: float) -> bool:
        x_coords = [self.x0, self.x1, self.x2, self.x3]
        y_coords = [self.y0, self.y1, self.y2, self.y3]

        min_x = min(x_coords)
        max_x = max(x_coords)
        min_y = min(y_coords)
        max_y = max(y_coords)
        return x >= min_x - size and x <= max_x + size and y >= min_y - size and y <= max_y + size


class Furniture(Point):
    def __init__(
        self,
        x: float,
        y: float,
        x0: float,
        y0: float,
        width: float,
        height: float,
        type: FurnitureType,
        size_type: int,
        angle: float = 0,
        scale: float = 1.0,
        furniture_id: int | None = None,
        segment_id: int | None = None,
    ) -> None:
        super().__init__(x, y)
        self.x0 = x0
        self.y0 = y0
        self.width = width
        self.height = height
        if x0 and y0 and width and height:
            self.x1: float | None = x0 + width
            self.y1: float | None = y0
            self.x2: float | None = x0 + width
            self.y2: float | None = y0 + height
            self.x3: float | None = x0
            self.y3: float | None = y0 + height
        else:
            self.x1 = None
            self.y1 = None
            self.x2 = None
            self.y2 = None
            self.x3 = None
            self.y3 = None
        self.type = type
        self.size_type = size_type
        self.angle = angle
        self.scale = scale
        self.furniture_id = furniture_id
        self.segment_id = segment_id

    def as_dict(self) -> dict[str, Any]:
        attributes = super().as_dict()
        attributes[ATTR_TYPE] = self.type.name.replace("_", " ").title()
        if self.x0 is not None and self.y0 is not None:
            attributes[ATTR_X0] = self.x0
            attributes[ATTR_Y0] = self.y0
        if self.x1 is not None and self.y1 is not None:
            attributes[ATTR_X1] = self.x1
            attributes[ATTR_Y1] = self.y1
        if self.x2 is not None and self.y2 is not None:
            attributes[ATTR_X2] = self.x2
            attributes[ATTR_Y2] = self.y2
        if self.x3 is not None and self.y3 is not None:
            attributes[ATTR_X3] = self.x3
            attributes[ATTR_Y3] = self.y3
        if self.width and self.height:
            attributes[ATTR_WIDTH] = self.width
            attributes[ATTR_HEIGHT] = self.height
        if self.segment_id:
            attributes[ATTR_ROOM_ID] = self.segment_id
        attributes[ATTR_SIZE_TYPE] = self.size_type
        attributes[ATTR_ANGLE] = self.angle
        attributes[ATTR_SCALE] = self.scale
        return attributes

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Furniture):
            return NotImplemented
        return not (
            other is None
            or self.x != other.x
            or self.y != other.y
            or self.x0 != other.x0
            or self.y0 != other.y0
            or self.width != other.width
            or self.height != other.height
            or self.type != other.type
            or self.size_type != other.size_type
            or self.angle != other.angle
            or self.scale != other.scale
        )


class Coordinate(Point):
    def __init__(self, x: float, y: float, completed: bool, type: int) -> None:
        super().__init__(x, y)
        self.type = type
        self.completed = completed

    def as_dict(self) -> dict[str, Any]:
        attributes = {**super().as_dict()}
        if self.type is not None:
            attributes[ATTR_TYPE] = self.type
        if self.completed is not None:
            attributes[ATTR_COMPLETED] = self.completed
        return attributes

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Coordinate):
            return NotImplemented
        return not (
            other is None
            or self.x != other.x
            or self.y != other.y
            or self.type != other.type
            or self.completed != other.completed
        )


class Carpet(Area):
    def __init__(
        self,
        id: int | None,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        ellipse: bool | str | int | None = False,
        carpet_type: int | None = None,
        ignored_areas: list[int] | None = None,
        segments: list[int] | None = None,
        polygon: list[float] | None = None,
    ) -> None:
        super().__init__(x0, y0, x1, y1, x2, y2, x3, y3)
        self.id = id
        self.segments = segments
        self.ignored_areas = ignored_areas
        self.ellipse = ellipse
        self.polygon = polygon
        self.carpet_cleaning: int | None = None
        self.carpet_settings: int | None = None
        self.carpet_type = carpet_type
        if ellipse is not None:
            ## Detected carpets returns string but added and ignored carpets are using int
            self.ellipse = ellipse == "1" or ellipse == 1

    def set_custom_carpet_settings(self, carpet_cleaning: int, carpet_settings: int | None = None) -> None:
        self.carpet_cleaning = carpet_cleaning
        self.carpet_settings = carpet_settings

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Carpet):
            return NotImplemented
        return not (
            other is None
            or self.x0 != other.x0
            or self.y0 != other.y0
            or self.x2 != other.x2
            or self.y2 != other.y2
            or self.id != other.id
            or self.ellipse != other.ellipse
            or self.carpet_cleaning != other.carpet_cleaning
            or self.carpet_settings != other.carpet_settings
            or self.carpet_type != other.carpet_type
            or self.segments != other.segments
            or self.ignored_areas != other.ignored_areas
            or self.polygon != other.polygon
        )


class Polygon(Area):
    def __init__(
        self,
        id: int,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        x3: float,
        y3: float,
        polygon: list[float],
        type: int | None = None,
        hidden: int | None = None,
        ms: int | None = None,
        area: int | None = None,
    ) -> None:
        super().__init__(x0, y0, x1, y1, x2, y2, x3, y3)
        self.id = id
        self.polygon = polygon
        self.type = type  # 0 = Automatically Detected, 1 = Manually Added
        self.hidden = hidden  # 1 = Automatically Hidden, 2 = Manually Hidden
        self.ms = ms
        self.area = area

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Polygon):
            return NotImplemented
        return not (
            other is None
            or self.x0 != other.x0
            or self.y0 != other.y0
            or self.x2 != other.x2
            or self.y2 != other.y2
            or self.id != other.id
            or self.polygon != other.polygon
            or self.type != other.type
            or self.hidden != other.hidden
            or self.ms != other.ms
            or self.area != other.area
        )


class MapImageDimensions:
    def __init__(self, top: int, left: int, height: int, width: int, grid_size: int) -> None:
        self.top = top
        self.left = left
        self.height = height
        self.width = width
        self.grid_size = grid_size
        self.scale: Any = 1
        self.padding: list[Any] = [0, 0, 0, 0]
        self.crop: list[Any] = [0, 0, 0, 0]
        self.bounds: Any = None

    def to_img(self, point: Point, offset: bool = True) -> Point:
        left: float = self.left
        top: float = self.top
        if not offset and (left % self.grid_size != 0 or top % self.grid_size != 0):
            left = left + (self.grid_size / 2)
            top = top + (self.grid_size / 2)

        return Point(
            ((point.x - left) / self.grid_size) * self.scale + self.padding[0] - self.crop[0],
            ((((self.height) * self.grid_size - 1) - (point.y - top)) / self.grid_size) * self.scale
            + self.padding[1]
            - self.crop[1],
        )

    def to_coord(self, point: Point, offset: bool = True) -> Point:
        left: float = self.left
        top: float = self.top
        if not offset and (left % self.grid_size != 0 or top % self.grid_size != 0):
            left = left + (self.grid_size / 2)
            top = top + (self.grid_size / 2)

        return Point(
            ((point.x - left) / self.grid_size),
            ((((self.height) * self.grid_size - 1) - (point.y - top)) / self.grid_size),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MapImageDimensions):
            return NotImplemented
        return (
            other is not None
            and self.top == other.top
            and self.left == other.left
            and self.height == other.height
            and self.width == other.width
            and self.grid_size == other.grid_size
        )


class CleaningHistory:
    def __init__(
        self, history_data: list[dict[str, Any]], property_mapping: dict[DreameVacuumProperty, dict[str, int]]
    ) -> None:
        self.date: datetime | None = None
        self.status: DreameVacuumStatus | None = None
        self.cleaning_time: int = 0
        self.cleaned_area: int = 0
        self.suction_level: DreameVacuumSuctionLevel | None = None
        self.file_name: str | None = None
        self.key: str | None = None
        self.object_name: str | None = None
        self.completed: bool | None = None
        self.water_tank_or_mop: DreameVacuumWaterTank | None = None
        self.map_index: int | None = None
        self.map_name: str | None = None
        self.cruise_type: int | None = None
        self.cleanup_method: CleanupMethod | None = None
        self.second_cleaning: int | None = None
        self.second_mopping: int | None = None
        self.mopping_mode: int | None = None
        self.multiple_cleaning_time: str | None = None
        self.pet_focused_cleaning: int | None = None
        self.task_interrupt_reason: TaskInterruptReason | None = None
        self.neglected_segments: dict[int, int] | None = None
        self.clean_again: int | None = None

        for history_data_item in history_data:
            pid = history_data_item[piid]
            value = history_data_item["value"] if "value" in history_data_item else history_data_item["val"]

            if pid == PIID(DreameVacuumProperty.STATUS, property_mapping):
                if value in DreameVacuumStatus._value2member_map_:
                    self.status = DreameVacuumStatus(value)
                else:
                    self.status = DreameVacuumStatus.UNKNOWN
            elif pid == PIID(DreameVacuumProperty.CLEANING_TIME, property_mapping):
                self.cleaning_time = value
            elif pid == PIID(DreameVacuumProperty.CLEANED_AREA, property_mapping):
                self.cleaned_area = value
            elif pid == PIID(DreameVacuumProperty.SUCTION_LEVEL, property_mapping):
                if value in DreameVacuumSuctionLevel._value2member_map_:
                    self.suction_level = DreameVacuumSuctionLevel(value)
                else:
                    self.suction_level = DreameVacuumSuctionLevel.UNKNOWN
            elif pid == PIID(DreameVacuumProperty.CLEANING_START_TIME, property_mapping):
                self.date = datetime.fromtimestamp(value)
            elif pid == PIID(DreameVacuumProperty.CLEAN_LOG_FILE_NAME, property_mapping):
                self.file_name = value
                if len(value) > 1:
                    if "," in value:
                        values = value.split(",")
                        self.object_name = values[0]
                        self.key = values[1]
                    else:
                        self.object_name = value
            elif pid == PIID(DreameVacuumProperty.CLEAN_LOG_STATUS, property_mapping):
                self.completed = bool(value)
            elif pid == PIID(DreameVacuumProperty.WATER_TANK, property_mapping):
                if value in DreameVacuumWaterTank._value2member_map_:
                    self.water_tank_or_mop = DreameVacuumWaterTank(value)
                else:
                    self.water_tank_or_mop = DreameVacuumWaterTank.UNKNOWN
            elif pid == PIID(DreameVacuumProperty.MAP_INDEX, property_mapping):
                self.map_index = value
            elif pid == PIID(DreameVacuumProperty.MAP_NAME, property_mapping):
                self.map_name = value
            elif pid == PIID(DreameVacuumProperty.CRUISE_TYPE, property_mapping):
                self.cruise_type = value
            elif pid == PIID(DreameVacuumProperty.CLEANING_PROPERTIES, property_mapping):
                props = json.loads(value)
                if "cmc" in props:
                    value = props["cmc"]
                    self.cleanup_method = (
                        CleanupMethod(value) if value in CleanupMethod._value2member_map_ else CleanupMethod.OTHER
                    )
                if "abnormal_end" in props:
                    values = json.loads(props["abnormal_end"])
                    self.task_interrupt_reason = (
                        TaskInterruptReason(values[0])
                        if values[0] in TaskInterruptReason._value2member_map_
                        else TaskInterruptReason.UNKNOWN
                    )
                self.second_cleaning = props.get("ismultiple")
                self.second_mopping = props.get("ctyo")
                self.mopping_mode = props.get("mooClean")
                self.multiple_cleaning_time = props.get("multime")
                self.pet_focused_cleaning = props.get("pet")
                self.clean_again = props.get("cleanagain")
                if "area_clean_detail" in props:
                    values = props["area_clean_detail"]
                    if len(values) > 1:
                        values = json.loads(values)
                        if values:
                            self.neglected_segments = {
                                v[0]: SegmentNeglectReason(v[1])
                                for v in values
                                if v[1] in SegmentNeglectReason._value2member_map_
                            }


class RecoveryMapInfo:
    date: datetime | None = None

    def __init__(
        self,
        map_id: int,
        date: float | None,
        raw_map: str,
        map_object_name: str,
        object_name: str,
        map_type: int,
    ) -> None:
        self.date = datetime.fromtimestamp(date) if date else None
        self.raw_map: str = raw_map
        self.map_object_name: str = map_object_name
        self.object_name: str = object_name
        self.map_data: MapData | None = None
        self.map_id: int = map_id
        # Display name/index, filled in later by the map manager (_refresh_map_list).
        self.map_name: str | None = None
        self.map_index: int | None = None

        self.map_type = (
            RecoveryMapType(map_type) if map_type in RecoveryMapType._value2member_map_ else RecoveryMapType.UNKNOWN
        )

    def as_dict(self) -> dict[str, Any] | None:
        if self.date:
            return {
                "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(self.date.timestamp())),
                "map_type": self.map_type.name.replace("_", " ").title(),
                "object_name": self.object_name,
            }
        return None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RecoveryMapInfo):
            return NotImplemented
        return self.date != other.date or self.map_id != other.map_id or self.object_name != other.object_name

    @property
    def __dict__(self: RecoveryMapInfo) -> dict[str, Any]:  # type: ignore[override]
        if self.date:
            return {
                "date": self.date,
                "map_id": self.map_id,
                "object_name": self.object_name,
                "map_object_name": self.map_object_name,
            }
        return {}


class MapFrameType(IntEnum):
    I = 73  # noqa: E741 — protocol frame letter (I-frame), must match the wire format name
    P = 80
    # T = ??
    W = 87


class MapPixelType(IntEnum):
    OUTSIDE = 0
    WIFI_WALL = 2
    WIFI_UNREACHED = 10
    WIFI_POOR = 11
    WIFI_LOW = 12
    WIFI_HIGH = 13
    WIFI_EXCELLENT = 14
    WALL = 255
    FLOOR = 254
    NEW_SEGMENT = 253
    UNKNOWN = 252
    OBSTACLE_WALL = 251
    HIDDEN_WALL = 250
    CLEAN_AREA = 249
    DIRTY_AREA = 248


class RecoveryMapType(IntEnum):
    UNKNOWN = -1
    EDITED = 0
    ORIGINAL = 1
    BACKUP = 2


class StartupMethod(IntEnum):
    OTHER = -1
    BY_BUTTON = 0
    THROUGH_APP = 1
    SCHEDULED_ACTIVATION = 2
    THROUGH_VOICE = 3


class CleanupMethod(IntEnum):
    OTHER = -1
    DEFAULT_MODE = 0
    CUSTOMIZED_CLEANING = 1
    CLEANGENIUS = 2
    WATER_STAIN_CLEANING = 3


class TaskEndType(IntEnum):
    OTHER = 0
    MANUAL_DOCKING = 1
    NORMAL_RECHARGING = 2
    ABNORMAL_DOCKING = 3
    INTERRUPTION_ENDED = 4


class MapDataPartial:
    def __init__(self) -> None:
        self.map_id: int | None = None  # Map header: map_id
        self.frame_id: int | None = None  # Map header: frame_id
        self.frame_type: int | None = None  # Map header: frame_type
        self.timestamp_ms: int | None = None  # Data json: timestamp_ms
        self.raw: bytes | None = None  # Unzipped raw map
        self.data_json: Any = {}  # Data json


class MapData:
    def __init__(self) -> None:
        # Header
        self.map_id: int | None = None  # Map header: map_id
        self.frame_id: int | None = None  # Map header: frame_id
        self.frame_type: int | None = None  # Map header: frame_type
        # Map header: robot x, robot y, robot angle
        self.robot_position: Point | None = None
        # Map header: charger x, charger y, charger angle
        self.charger_position: Point | None = None
        self.optimized_charger_position: Point | None = None
        self.router_position: Point | None = None  # Data json: whmp
        # Map header: top, left, height, width, grid_size
        self.dimensions: MapImageDimensions | None = None
        self.optimized_dimensions: MapImageDimensions | None = None
        self.combined_dimensions: MapImageDimensions | None = None
        self.data: Any = None  # Raw image data for handling P frames
        # Data json
        self.timestamp_ms: int | None = None  # Data json: timestamp_ms
        self.rotation: int | None = None  # Data json: mra
        self.no_go_areas: list[Area] | None = None  # Data json: vw.rect
        self.no_mopping_areas: list[Area] | None = None  # Data json: vw.mop
        self.virtual_walls: list[Wall] | None = None  # Data json: vw.line
        self.virtual_thresholds: list[Wall] | None = None  # Data json: vws.vwsl
        # Vectorized room boundaries from the saved map (Data json: walls_info).
        # wall_lines = wall segments (type 0), door_lines = doorways (type 1).
        self.wall_lines: list[Wall] | None = None
        self.door_lines: list[Wall] | None = None
        self.passable_thresholds: list[Wall] | None = None  # Data json: vws.vwsl
        self.impassable_thresholds: list[Wall] | None = None  # Data json: vws.npthrsd
        self.ramps: list[Area] | None = None  # Data json: vws.ramp
        self.curtains: list[Wall] | None = None  # Data json: ct.line
        self.path: list[Path] | None = None  # Data json: tr
        self.active_segments: list[int] | None = None  # Data json: sa
        self.active_areas: list[Area] | None = None  # Data json: da2
        self.active_points: list[Point] | None = None  # Data json: sp
        # Data json: rism.map_header.map_id
        self.saved_map_id: int | None = None
        self.saved_map_status: int | None = None  # Data json: ris
        self.restored_map: bool | None = None  # Data json: rpur
        self.frame_map: bool | None = None  # Data json: fsm
        self.docked: bool | None = None  # Data json: oc
        self.clean_log: bool | None = None  # Data json: iscleanlog
        # ``dict[str(segment_id), list[int]]`` of cleaning settings; ``True``/``None``
        # sentinels are also stored by the renderer pipeline — hence ``Any``.
        self.cleanset: Any = None  # Data json: cleanset
        self.sequence: bool | None = None  # cleaning-order flag (set by decoder/renderer)
        # ``list[list[int]]`` per-carpet settings at runtime (editor mutates rows in place).
        self.carpet_cleanset: Any = None  # Data json: carpetcleanset
        self.line_to_robot: bool | None = None  # Data json: l2r
        self.temporary_map: int | None = None  # Data json: suw
        self.cleaned_area: int | None = None  # Data json: cs
        self.cleaning_time: int | None = None  # Data json: ct
        self.completed: bool | None = None  # Data json: cf
        # ``dict[segment_id, reason]`` from the cleaning map, plain list from 'delsr'.
        self.neglected_segments: Any = None  #
        self.second_cleaning: bool | None = None  #
        self.remaining_battery: int | None = None  # Data json: clean_finish_remain_electricity
        self.work_status: int | None = None  # Data json: wm
        self.recovery_map: bool | None = None  # Data json: us
        self.recovery_map_type: RecoveryMapType | None = None  # Generated from recovery map list json
        self.obstacles: dict[str, Obstacle] | None = None  # Data json: ai_obstacle (str-keyed)
        self.furnitures: dict[int, Furniture] | None = None  # Data json: ai_furniture
        self.saved_furnitures: dict[int, Furniture] | None = None  # Data json: furniture_info
        self.carpets: list[Carpet] | None = None  # Data json: vw.addcpt
        self.ignored_carpets: list[Carpet] | None = None  # Data json: vw.nocpt
        self.detected_carpets: list[Carpet] | None = None  # Data json: carpet_info
        self.low_lying_areas: list[Polygon] | None = None  # Data json: sneak_areas or sneak_areas_end
        self.carpet_pixels: Any | None = None  # Generated from map data
        self.new_map: bool | None = None  # Data json: risp
        self.startup_method: StartupMethod | None = None  # Data json: smd
        self.task_end_type: TaskEndType | None = None  # Data json: ctyi
        self.cleanup_method: CleanupMethod | None = None  #
        self.customized_cleaning: int | None = None  # Data json: customeclean
        self.dust_collection_count: int | None = None  # Data json: ds
        self.mop_wash_count: int | None = None  # Data json: wt
        self.cleaned_segments: list[Any] | None = None  # Data json: CleanArea (from dirty map data)
        self.multiple_cleaning_time: int | None = None  # Data json: multime
        self.dos: int | None = None  # Data json: dos
        # Generated
        self.custom_name: str | None = None  # Map list json: name
        self.object_name: str | None = None  # Map list json: mapobj
        self.map_index: int | None = None  # Generated from saved map list
        # Legacy field only ever written by the decoder; kept for parity with the app.
        self.index: int = 0
        self.map_name: str | None = None  # Generated map name for map list
        # Generated pixel map for rendering colors
        self.pixel_type: Any = None
        self.optimized_pixel_type: Any = None
        self.combined_pixel_type: Any = None
        # Generated segments from pixel_type
        self.segments: dict[int, Segment] | None = None
        self.floor_material: dict[int, int] | None = None  # Generated from seg_inf.material
        self.saved_map: bool | None = None  # Generated for rism map
        self.empty_map: bool | None = None  # Generated from pixel_type
        self.wifi_map_data: MapData | None = None  # Generated from whm
        self.wifi_map: bool | None = None  #
        self.cleaning_map_data: MapData | None = None  # Generated from decmap
        self.cleaning_map: bool | None = None  #
        self.has_cleaned_area: bool | None = None  #
        self.has_dirty_area: bool | None = None  #
        self.history_map: bool | None = None  #
        self.furniture_version: int | None = None  #
        self.recovery_map_list: list[RecoveryMapInfo] | None = None  # Generated from recovery map list
        self.active_cruise_points: dict[int, Coordinate] | None = None  # Data json: pointinfo.tpoint
        self.predefined_points: dict[int, Coordinate] | None = None  # Data json: pointinfo.spoint
        # ``dict[int, Coordinate]`` while active, ``True`` once consumed by the renderer.
        self.task_cruise_points: Any = None  # Data json: tpointinfo
        # Generated from pixel_type and robot poisiton
        self.hidden_segments: list[int] | None = None  # Data json: delsr
        self.robot_segment: int | None = None
        # For renderer to detect changes
        self.last_updated: float | None = None
        # For vslam map rendering optimization
        self.need_optimization: bool | None = None
        # 3D Map Properties
        self.ai_outborders_user: Any | None = None
        self.ai_outborders: Any | None = None
        self.ai_outborders_new: Any | None = None
        self.ai_outborders_2d: Any | None = None
        self.ai_furniture_warning: Any | None = None
        self.walls_info: Any | None = None
        self.walls_info_new: Any | None = None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MapData):
            return NotImplemented
        if other is None:
            return False

        if self.map_id != other.map_id:
            return False

        if self.custom_name != other.custom_name:
            return False

        if self.rotation != other.rotation:
            return False

        if self.work_status != other.work_status:
            return False

        if self.robot_position != other.robot_position:
            return False

        if self.charger_position != other.charger_position:
            return False

        if self.no_go_areas != other.no_go_areas:
            return False

        if self.no_mopping_areas != other.no_mopping_areas:
            return False

        if self.carpets != other.carpets:
            return False

        if self.ignored_carpets != other.ignored_carpets:
            return False

        if self.detected_carpets != other.detected_carpets:
            return False

        if self.virtual_walls != other.virtual_walls:
            return False

        if self.virtual_thresholds != other.virtual_thresholds:
            return False

        if self.wall_lines != other.wall_lines:
            return False

        if self.door_lines != other.door_lines:
            return False

        if self.passable_thresholds != other.passable_thresholds:
            return False

        if self.impassable_thresholds != other.impassable_thresholds:
            return False

        if self.ramps != other.ramps:
            return False

        if self.low_lying_areas != other.low_lying_areas:
            return False

        if self.curtains != other.curtains:
            return False

        if self.docked != other.docked:
            return False

        if self.active_segments != other.active_segments:
            return False

        if self.active_areas != other.active_areas:
            return False

        if self.active_points != other.active_points:
            return False

        if self.active_cruise_points != other.active_cruise_points:
            return False

        if self.clean_log != other.clean_log:
            return False

        if self.saved_map_status != other.saved_map_status:
            return False

        if self.restored_map != other.restored_map:
            return False

        if self.frame_map != other.frame_map:
            return False

        if self.temporary_map != other.temporary_map:
            return False

        if self.saved_map != other.saved_map:
            return False

        if self.new_map != other.new_map:
            return False

        if self.cleanset != other.cleanset:
            return False

        if self.sequence != other.sequence:
            return False

        if self.carpet_cleanset != other.carpet_cleanset:
            return False

        if self.furnitures != other.furnitures:
            return False

        if self.saved_furnitures != other.saved_furnitures:
            return False

        if self.obstacles != other.obstacles:
            return False

        if self.predefined_points != other.predefined_points:
            return False

        if self.router_position != other.router_position:
            return False

        if self.hidden_segments != other.hidden_segments:
            return False

        return True

    def as_dict(self) -> dict[str, Any]:
        attributes_list: dict[str, Any] = {}
        if self.charger_position is not None:
            attributes_list[ATTR_CHARGER] = (
                self.optimized_charger_position
                if self.optimized_charger_position is not None
                else self.charger_position
            )
        if self.custom_name is not None:
            attributes_list[ATTR_CUSTOM_NAME] = self.custom_name
        if self.segments is not None and (self.saved_map or self.saved_map_status == 2 or self.restored_map):
            attributes_list[ATTR_ROOMS] = {k: v.as_dict() for k, v in sorted(self.segments.items())}
        if not self.saved_map and self.robot_position is not None:
            attributes_list[ATTR_ROBOT_POSITION] = self.robot_position
        if self.map_id:
            attributes_list[ATTR_MAP_ID] = self.map_id
        if self.saved_map_id:
            attributes_list[ATTR_SAVED_MAP_ID] = self.saved_map_id
        if self.map_name is not None:
            attributes_list[ATTR_MAP_NAME] = self.map_name
        if self.rotation is not None:
            attributes_list[ATTR_ROTATION] = self.rotation
        if self.last_updated is not None:
            attributes_list[ATTR_UPDATED] = datetime.fromtimestamp(self.last_updated)
        if not self.saved_map and self.active_areas is not None:
            attributes_list[ATTR_ACTIVE_AREAS] = self.active_areas
        if not self.saved_map and self.active_segments is not None:
            attributes_list[ATTR_ACTIVE_SEGMENTS] = self.active_segments
        if not self.saved_map and self.active_points is not None:
            attributes_list[ATTR_ACTIVE_POINTS] = self.active_points
        if not self.saved_map and self.active_cruise_points is not None:
            attributes_list[ATTR_ACTIVE_CRUISE_POINTS] = self.active_cruise_points
        if self.predefined_points:
            attributes_list[ATTR_PREDEFINED_POINTS] = list(self.predefined_points.values())
        if self.virtual_walls is not None:
            attributes_list[ATTR_VIRTUAL_WALLS] = self.virtual_walls
        if self.wall_lines is not None:
            attributes_list[ATTR_WALL_LINES] = self.wall_lines
        if self.door_lines is not None:
            attributes_list[ATTR_DOOR_LINES] = self.door_lines
        if self.virtual_thresholds is not None:
            attributes_list[ATTR_VIRTUAL_THRESHOLDS] = self.virtual_thresholds
        if self.passable_thresholds is not None:
            attributes_list[ATTR_PASSABLE_THRESHOLDS] = self.passable_thresholds
        if self.impassable_thresholds is not None:
            attributes_list[ATTR_IMPASSABLE_THRESHOLDS] = self.impassable_thresholds
        if self.ramps is not None:
            attributes_list[ATTR_RAMPS] = self.ramps
        if self.low_lying_areas is not None:
            attributes_list[ATTR_LOW_LYING_AREAS] = self.low_lying_areas
        if self.no_go_areas is not None:
            attributes_list[ATTR_NO_GO_AREAS] = self.no_go_areas
        if self.no_mopping_areas is not None:
            attributes_list[ATTR_NO_MOPPING_AREAS] = self.no_mopping_areas
        if self.carpets is not None:
            attributes_list[ATTR_CARPETS] = self.carpets
        if self.ignored_carpets is not None:
            attributes_list[ATTR_IGNORED_CARPETS] = self.ignored_carpets
        if self.detected_carpets is not None:
            attributes_list[ATTR_DETECTED_CARPETS] = self.detected_carpets
        if self.curtains is not None:
            attributes_list[ATTR_CURTAINS] = self.curtains
        if self.empty_map is not None:
            attributes_list[ATTR_IS_EMPTY] = self.empty_map
        if self.frame_id:
            attributes_list[ATTR_FRAME_ID] = self.frame_id
        if self.map_index:
            attributes_list[ATTR_MAP_INDEX] = self.map_index
        if self.obstacles:
            attributes_list[ATTR_OBSTACLES] = self.obstacles
        if self.saved_furnitures and self.saved_map:
            attributes_list[ATTR_FURNITURES] = list(self.saved_furnitures.values())
        elif self.furnitures:
            attributes_list[ATTR_FURNITURES] = list(self.furnitures.values())
        if self.router_position:
            attributes_list[ATTR_ROUTER_POSITION] = self.router_position
        if self.startup_method:
            attributes_list[ATTR_STARTUP_METHOD] = self.startup_method.name.replace("_", " ").title()
        if self.dust_collection_count:
            attributes_list[ATTR_DUST_COLLECTION_COUNT] = self.dust_collection_count
        if self.mop_wash_count:
            attributes_list[ATTR_MOP_WASH_COUNT] = self.mop_wash_count
        if self.recovery_map_list:
            attributes_list[ATTR_RECOVERY_MAP_LIST] = [v.as_dict() for v in reversed(self.recovery_map_list)]
        return attributes_list

    def check_point(self, x: float, y: float, absolute: bool = False) -> bool:
        if self.dimensions is None or self.pixel_type is None:
            return False
        if not absolute:
            x = int((x - self.dimensions.left) / self.dimensions.grid_size)
            y = int((y - self.dimensions.top) / self.dimensions.grid_size)
        if x < 0 or x >= self.dimensions.width or y < 0 or y >= self.dimensions.height:
            return False
        value = int(self.pixel_type[x, y])
        return value > 0 and value != 255


@dataclass
class DirtyData:
    value: Any = None
    previous_value: Any = None
    update_time: float | None = None


@dataclass
class Shortcut:
    id: int = -1
    name: str | None = None
    map_id: int | None = None
    running: bool = False
    tasks: list[list[ShortcutTask]] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ShortcutTask:
    segment_id: int | None = None
    suction_level: int | None = None
    water_volume: int | None = None
    cleaning_times: int | None = None
    cleaning_mode: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScheduleTask:
    id: int = -1
    enabled: bool = False
    invalid: bool = False
    time: str | None = None
    repeats: str | None = None
    once: bool = False
    map_id: str | None = None
    suction_level: int | None = None
    water_volume: int | None = None
    options: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GoToZoneSettings:
    x: int | None = None
    y: int | None = None
    stop: bool = False
    suction_level: int | None = None
    water_level: int | None = None
    cleaning_mode: int | None = None
    size: int = 50


@dataclass
class MapRendererConfig:
    color: bool = True
    icon: bool = True
    name: bool = True
    name_background: bool = True
    order: bool = True
    suction_level: bool = True
    water_volume: bool = True
    cleaning_times: bool = True
    cleaning_mode: bool = True
    mopping_mode: bool = True
    path: bool = True
    no_go: bool = True
    no_mop: bool = True
    virtual_wall: bool = True
    pathway: bool = True
    low_lying_area: bool = True
    active_area: bool = True
    active_point: bool = True
    charger: bool = True
    robot: bool = True
    cleaning_direction: bool = True
    obstacle: bool = True
    stain: bool = True
    pet: bool = True
    carpet: bool = True
    material: bool = True
    furniture: bool = True
    curtain: bool = True
    ramp: bool = True
    cruise_point: bool = True


@dataclass
class MapRendererColorScheme:
    floor: tuple[int, ...] = (221, 221, 221, 255)
    outside: tuple[int, ...] = (0, 0, 0, 0)
    wall: tuple[int, ...] = (159, 159, 159, 255)
    passive_segment: tuple[int, ...] = (200, 200, 200, 255)
    hidden_segment: tuple[int, ...] = (226, 226, 226, 255)
    new_segment: tuple[int, ...] = (153, 191, 255, 255)
    cleaned_area: tuple[int, ...] = (158, 240, 117, 255)
    dirty_area: tuple[int, ...] = (247, 135, 106, 255)
    clean_area: tuple[int, ...] = (156, 202, 250, 255)
    second_clean_area: tuple[int, ...] = (123, 148, 172, 255)
    neglected_segment: tuple[int, ...] = (255, 159, 10, 110)
    no_go: tuple[int, ...] = (177, 0, 0, 50)
    no_go_outline: tuple[int, ...] = (199, 0, 0, 200)
    no_mop: tuple[int, ...] = (170, 47, 255, 50)
    no_mop_outline: tuple[int, ...] = (153, 0, 210, 200)
    virtual_wall: tuple[int, ...] = (199, 0, 0, 200)
    virtual_threshold: tuple[int, ...] = (50, 215, 75, 255)
    passable_threshold_outline: tuple[int, ...] = (50, 215, 75, 255)
    passable_threshold: tuple[int, ...] = (50, 215, 75, 50)
    impassable_threshold_outline: tuple[int, ...] = (199, 0, 0, 255)
    impassable_threshold: tuple[int, ...] = (199, 0, 0, 50)
    curtain: tuple[int, ...] = (247, 123, 46, 255)
    ramp: tuple[int, ...] = (255, 255, 255, 50)
    ramp_outline: tuple[int, ...] = (10, 132, 255, 255)
    low_lying_area: tuple[int, ...] = (157, 211, 246, 40)
    auto_low_lying_area_outline: tuple[int, ...] = (121, 203, 255, 255)
    manual_low_lying_area_outline: tuple[int, ...] = (100, 181, 232, 255)
    active_area: tuple[int, ...] = (255, 255, 255, 80)
    active_area_outline: tuple[int, ...] = (34, 109, 242, 255)  # (103, 156, 244, 200)
    active_point: tuple[int, ...] = (255, 255, 255, 80)
    active_point_outline: tuple[int, ...] = (34, 109, 242, 255)  # (103, 156, 244, 200)
    path: tuple[int, ...] = (255, 255, 255, 255)
    mop_path: tuple[int, ...] = (255, 255, 255, 100)
    segment: tuple[list[tuple[int, int, int, int]], ...] = (
        [(171, 199, 248, 255), (121, 170, 255, 255)],  # 0  Bleu
        [(249, 224, 125, 255), (255, 211, 38, 255)],  # 1  Jaune
        [(184, 227, 255, 255), (141, 210, 255, 255)],  # 2  Bleu clair
        [(184, 217, 141, 255), (150, 217, 141, 255)],  # 3  Vert
        [(255, 182, 182, 255), (255, 130, 130, 255)],  # 4  Rose
        [(218, 191, 255, 255), (180, 150, 255, 255)],  # 5  Violet
        [(255, 213, 170, 255), (255, 180, 120, 255)],  # 6  Orange
        [(170, 235, 220, 255), (110, 215, 190, 255)],  # 7  Turquoise
        [(235, 200, 170, 255), (210, 170, 130, 255)],  # 8  Beige
        [(200, 230, 180, 255), (165, 210, 140, 255)],  # 9  Vert clair
        [(210, 210, 240, 255), (175, 175, 220, 255)],  # 10 Lavande
        [(255, 230, 180, 255), (255, 210, 140, 255)],  # 11 Or pâle
        [(195, 230, 230, 255), (155, 210, 210, 255)],  # 12 Cyan pâle
        [(240, 200, 215, 255), (220, 165, 185, 255)],  # 13 Mauve
        [(215, 235, 200, 255), (185, 215, 165, 255)],  # 14 Sauge
        [(230, 215, 230, 255), (205, 185, 205, 255)],  # 15 Lilas
    )
    obstacle_bg: tuple[int, ...] = (34, 109, 242, 255)
    icon_background: tuple[int, ...] = (0, 0, 0, 100)
    settings_background: tuple[int, ...] = (255, 255, 255, 175)
    settings_icon_background: tuple[int, ...] = (255, 255, 255, 205)
    material_color: tuple[int, ...] = (0, 0, 0, 20)
    carpet_color_detected: tuple[int, ...] = (0, 0, 0, 35)
    carpet_color: tuple[int, ...] = (0, 0, 0, 80)
    text: tuple[int, ...] = (0, 0, 0, 255)
    order: tuple[int, ...] = (0, 0, 0, 255)
    text_stroke: tuple[int, ...] = (255, 255, 255, 200)
    badge_outline: tuple[int, ...] = (0, 0, 0, 180)
    invert: bool = False
    dark: bool = False


MAP_COLOR_SCHEME_LIST: Final = {
    "Dreame Light": MapRendererColorScheme(),
    "Dreame Dark": MapRendererColorScheme(
        floor=(110, 110, 110, 255),
        wall=(64, 64, 64, 255),
        passive_segment=(100, 100, 100, 255),
        hidden_segment=(116, 116, 116, 255),
        new_segment=(0, 91, 244, 255),
        no_go=(133, 0, 0, 128),
        no_go_outline=(149, 0, 0, 200),
        no_mop=(134, 0, 226, 128),
        no_mop_outline=(115, 0, 157, 200),
        virtual_wall=(133, 0, 0, 200),
        active_area=(200, 200, 200, 70),
        active_area_outline=(28, 81, 176, 255),  # (9, 54, 129, 200),
        active_point=(200, 200, 200, 80),
        active_point_outline=(28, 81, 176, 255),  # (9, 54, 129, 200),
        path=(200, 200, 200, 255),
        mop_path=(200, 200, 200, 100),
        segment=(
            [(13, 64, 155, 255), (0, 55, 150, 255)],  # 0  Bleu
            [(143, 75, 7, 255), (117, 53, 0, 255)],  # 1  Ambre
            [(0, 106, 176, 255), (0, 96, 158, 255)],  # 2  Bleu clair
            [(76, 107, 36, 255), (44, 107, 36, 255)],  # 3  Vert
            [(155, 50, 50, 255), (130, 30, 30, 255)],  # 4  Rose
            [(100, 60, 155, 255), (80, 40, 135, 255)],  # 5  Violet
            [(160, 90, 20, 255), (140, 70, 0, 255)],  # 6  Orange
            [(20, 120, 100, 255), (0, 100, 80, 255)],  # 7  Turquoise
            [(130, 95, 60, 255), (110, 75, 40, 255)],  # 8  Beige
            [(70, 120, 40, 255), (50, 100, 20, 255)],  # 9  Vert clair
            [(80, 80, 130, 255), (60, 60, 110, 255)],  # 10 Lavande
            [(150, 120, 30, 255), (130, 100, 10, 255)],  # 11 Or pâle
            [(40, 120, 120, 255), (20, 100, 100, 255)],  # 12 Cyan pâle
            [(135, 70, 90, 255), (115, 50, 70, 255)],  # 13 Mauve
            [(75, 115, 55, 255), (55, 95, 35, 255)],  # 14 Sauge
            [(110, 85, 110, 255), (90, 65, 90, 255)],  # 15 Lilas
        ),
        obstacle_bg=(28, 81, 176, 255),
        material_color=(255, 255, 255, 20),
        carpet_color_detected=(255, 255, 255, 35),
        carpet_color=(255, 255, 255, 80),
        settings_icon_background=(255, 255, 255, 195),
        text=(255, 255, 255, 255),
        order=(255, 255, 255, 255),
        text_stroke=(240, 240, 240, 200),
        badge_outline=(200, 200, 200, 180),
        dark=True,
    ),
    "Mijia Light": MapRendererColorScheme(
        new_segment=(131, 178, 255, 255),
        virtual_wall=(255, 45, 45, 200),
        no_go=(230, 30, 30, 128),
        no_go_outline=(255, 45, 45, 200),
        segment=(
            [(131, 178, 255, 255), (105, 142, 204, 255)],  # 0  Bleu
            [(245, 201, 66, 255), (196, 161, 53, 255)],  # 1  Jaune
            [(103, 207, 229, 255), (82, 165, 182, 255)],  # 2  Cyan
            [(255, 155, 101, 255), (204, 124, 81, 255)],  # 3  Orange
            [(255, 140, 140, 255), (204, 112, 112, 255)],  # 4  Rose
            [(178, 150, 255, 255), (142, 120, 204, 255)],  # 5  Violet
            [(255, 190, 100, 255), (204, 152, 80, 255)],  # 6  Ambre
            [(100, 220, 190, 255), (80, 176, 152, 255)],  # 7  Turquoise
            [(210, 180, 140, 255), (168, 144, 112, 255)],  # 8  Beige
            [(160, 215, 110, 255), (128, 172, 88, 255)],  # 9  Vert clair
            [(180, 180, 230, 255), (144, 144, 184, 255)],  # 10 Lavande
            [(255, 210, 130, 255), (204, 168, 104, 255)],  # 11 Or pâle
            [(130, 210, 210, 255), (104, 168, 168, 255)],  # 12 Cyan pâle
            [(225, 160, 180, 255), (180, 128, 144, 255)],  # 13 Mauve
            [(175, 215, 150, 255), (140, 172, 120, 255)],  # 14 Sauge
            [(200, 180, 210, 255), (160, 144, 168, 255)],  # 15 Lilas
        ),
        obstacle_bg=(131, 178, 255, 255),
    ),
    "Mijia Dark": MapRendererColorScheme(
        floor=(150, 150, 150, 255),
        wall=(119, 133, 153, 255),
        new_segment=(99, 148, 230, 255),
        passive_segment=(100, 100, 100, 255),
        hidden_segment=(116, 116, 116, 255),
        no_go=(133, 0, 0, 128),
        no_go_outline=(149, 0, 0, 200),
        no_mop=(134, 0, 226, 128),
        no_mop_outline=(115, 0, 157, 200),
        virtual_wall=(133, 0, 0, 200),
        active_area=(200, 200, 200, 70),
        active_area_outline=(9, 54, 129, 200),
        active_point=(200, 200, 200, 80),
        active_point_outline=(9, 54, 129, 200),
        path=(200, 200, 200, 255),
        mop_path=(200, 200, 200, 100),
        segment=(
            [(108, 141, 195, 255), (76, 99, 137, 255)],  # 0  Bleu
            [(188, 157, 62, 255), (133, 111, 44, 255)],  # 1  Jaune
            [(88, 161, 176, 255), (62, 113, 123, 255)],  # 2  Cyan
            [(195, 125, 87, 255), (138, 89, 62, 255)],  # 3  Orange
            [(180, 100, 100, 255), (126, 70, 70, 255)],  # 4  Rose
            [(140, 115, 195, 255), (98, 81, 137, 255)],  # 5  Violet
            [(195, 148, 80, 255), (138, 105, 57, 255)],  # 6  Ambre
            [(80, 170, 148, 255), (56, 119, 104, 255)],  # 7  Turquoise
            [(165, 140, 108, 255), (116, 98, 76, 255)],  # 8  Beige
            [(125, 168, 88, 255), (88, 118, 62, 255)],  # 9  Vert clair
            [(140, 140, 180, 255), (98, 98, 126, 255)],  # 10 Lavande
            [(195, 165, 100, 255), (138, 116, 70, 255)],  # 11 Or pâle
            [(100, 165, 165, 255), (70, 116, 116, 255)],  # 12 Cyan pâle
            [(175, 125, 140, 255), (123, 88, 98, 255)],  # 13 Mauve
            [(135, 168, 115, 255), (95, 118, 81, 255)],  # 14 Sauge
            [(155, 140, 165, 255), (109, 98, 116, 255)],  # 15 Lilas
        ),
        obstacle_bg=(108, 141, 195, 255),
        material_color=(255, 255, 255, 35),
        carpet_color_detected=(255, 255, 255, 50),
        carpet_color=(255, 255, 255, 90),
        settings_icon_background=(255, 255, 255, 195),
        text=(255, 255, 255, 255),
        order=(255, 255, 255, 255),
        text_stroke=(240, 240, 240, 200),
        badge_outline=(200, 200, 200, 180),
        dark=True,
    ),
    "Grayscale": MapRendererColorScheme(
        floor=(100, 100, 100, 255),
        wall=(40, 40, 40, 255),
        passive_segment=(50, 50, 50, 255),
        hidden_segment=(55, 55, 55, 255),
        new_segment=(80, 80, 80, 255),
        no_go=(133, 0, 0, 128),
        no_go_outline=(149, 0, 0, 200),
        no_mop=(134, 0, 226, 128),
        no_mop_outline=(115, 0, 157, 200),
        virtual_wall=(133, 0, 0, 200),
        active_area=(221, 221, 221, 60),
        active_area_outline=(22, 103, 238, 200),
        active_point=(221, 221, 221, 80),
        active_point_outline=(22, 103, 238, 200),
        path=(200, 200, 200, 255),
        mop_path=(200, 200, 200, 100),
        segment=(
            [(90, 90, 90, 255), (95, 95, 95, 255)],  # 0
            [(80, 80, 80, 255), (85, 85, 85, 255)],  # 1
            [(70, 70, 70, 255), (75, 75, 75, 255)],  # 2
            [(60, 60, 60, 255), (65, 65, 65, 255)],  # 3
            [(110, 110, 110, 255), (115, 115, 115, 255)],  # 4
            [(120, 120, 120, 255), (125, 125, 125, 255)],  # 5
            [(130, 130, 130, 255), (135, 135, 135, 255)],  # 6
            [(140, 140, 140, 255), (145, 145, 145, 255)],  # 7
            [(150, 150, 150, 255), (155, 155, 155, 255)],  # 8
            [(160, 160, 160, 255), (165, 165, 165, 255)],  # 9
            [(170, 170, 170, 255), (175, 175, 175, 255)],  # 10
            [(180, 180, 180, 255), (185, 185, 185, 255)],  # 11
            [(190, 190, 190, 255), (195, 195, 195, 255)],  # 12
            [(200, 200, 200, 255), (205, 205, 205, 255)],  # 13
            [(210, 210, 210, 255), (215, 215, 215, 255)],  # 14
            [(220, 220, 220, 255), (225, 225, 225, 255)],  # 15
        ),
        obstacle_bg=(90, 90, 90, 255),
        material_color=(255, 255, 255, 20),
        carpet_color_detected=(255, 255, 255, 35),
        carpet_color=(255, 255, 255, 80),
        icon_background=(200, 200, 200, 200),
        settings_icon_background=(255, 255, 255, 205),
        text=(0, 0, 0, 255),
        text_stroke=(0, 0, 0, 100),
        badge_outline=(40, 40, 40, 200),
        invert=True,
        dark=True,
    ),
    "Transparent": MapRendererColorScheme(
        floor=(0, 0, 0, 0),
        wall=(0, 0, 0, 0),
        passive_segment=(0, 0, 0, 0),
        hidden_segment=(0, 0, 0, 0),
        new_segment=(0, 0, 0, 0),
        path=(255, 255, 255, 200),
        mop_path=(255, 255, 255, 50),
        segment=(
            [(0, 0, 0, 0), (121, 170, 255, 255)],  # 0  Bleu
            [(0, 0, 0, 0), (255, 211, 38, 255)],  # 1  Jaune
            [(0, 0, 0, 0), (141, 210, 255, 255)],  # 2  Bleu clair
            [(0, 0, 0, 0), (150, 217, 141, 255)],  # 3  Vert
            [(0, 0, 0, 0), (255, 130, 130, 255)],  # 4  Rose
            [(0, 0, 0, 0), (180, 150, 255, 255)],  # 5  Violet
            [(0, 0, 0, 0), (255, 180, 120, 255)],  # 6  Orange
            [(0, 0, 0, 0), (110, 215, 190, 255)],  # 7  Turquoise
            [(0, 0, 0, 0), (210, 170, 130, 255)],  # 8  Beige
            [(0, 0, 0, 0), (165, 210, 140, 255)],  # 9  Vert clair
            [(0, 0, 0, 0), (175, 175, 220, 255)],  # 10 Lavande
            [(0, 0, 0, 0), (255, 210, 140, 255)],  # 11 Or pâle
            [(0, 0, 0, 0), (155, 210, 210, 255)],  # 12 Cyan pâle
            [(0, 0, 0, 0), (220, 165, 185, 255)],  # 13 Mauve
            [(0, 0, 0, 0), (185, 215, 165, 255)],  # 14 Sauge
            [(0, 0, 0, 0), (205, 185, 205, 255)],  # 15 Lilas
        ),
        text=(255, 255, 255, 255),
        order=(255, 255, 255, 255),
        text_stroke=(240, 240, 240, 200),
        badge_outline=(0, 0, 0, 120),
    ),
}

MAP_ICON_SET_LIST: Final = {"Dreame": 0, "Dreame Old": 1, "Mijia": 2, "Material": 3}


class MapRendererLayer(IntEnum):
    IMAGE = 0
    OBJECTS = 1
    PATH = 2
    PATH_MASK = 3
    NO_MOP = 4
    NO_GO = 5
    WALL = 6
    VIRTUAL_THRESHOLD = 7
    PASSABLE_THRESHOLD = 8
    IMPASSABLE_THRESHOLD = 9
    RAMP = 10
    CURTAIN = 11
    LOW_LYING_AREA = 12
    FURNITURES = 13
    FURNITURE = 14
    ACTIVE_AREA = 15
    ACTIVE_POINT = 16
    SEGMENTS = 17
    SEGMENT = 18
    CHARGER = 19
    ROBOT = 20
    ROUTER = 21
    OBSTACLES = 22
    OBSTACLE = 23
    CRUISE_POINTS = 24
    CRUISE_POINT = 25


@dataclass
class Line:
    x: int | list[int] | None = None
    y: int | list[int] | None = None
    ishorizontal: bool = False
    direction: int = 0


@dataclass
class CLine(Line):
    length: int = 0
    findEnd: bool = False


@dataclass
class ALine:
    p0: Line = field(default_factory=lambda: Line(0, 0, False, 0))
    p1: Line = field(default_factory=lambda: Line(0, 0, False, 0))
    length: int = 0


@dataclass
class Paths:
    # ``clines`` = *converted* lines (the ``ALine`` wrappers built by the optimizer),
    # ``alines`` = *all* raw ``CLine`` segments — see ``DreameVacuumMapOptimizer._add_line``.
    clines: list[ALine] = field(default_factory=list)
    alines: list[CLine] = field(default_factory=list)
    length: int = 0


@dataclass
class Angle:
    lines: list[CLine] = field(default_factory=list)
    horizontalDir: int = 0
    verticalDir: int = 0


@dataclass
class MapRendererResources:
    renderer: str = ""
    icon_set: int = 0
    robot_type: int = 0
    robot: str | None = None
    charger: str | None = None
    charging: str | None = None
    cleaning: str | None = None
    warning: str | None = None
    sleeping: str | None = None
    cleaning_direction: str | None = None
    selected_segment: str | None = None
    cruise_point_background: str | None = None
    segment: Any = None
    default_map_image: str | None = None
    font: str | None = None
    repeats: list[str] | None = None
    suction_level: list[str] | None = None
    water_volume: list[str] | None = None
    mop_pad_humidity: list[str] | None = None
    cleaning_mode: list[str] | None = None
    cleaning_route: list[str] | None = None
    custom_mopping_route: list[str] | None = None
    washing: str | None = None
    hot_washing: str | None = None
    drying: str | None = None
    hot_drying: str | None = None
    emptying: str | None = None
    cruise_path_point_background: str | None = None
    obstacle_background: str | None = None
    obstacle_hidden_background: str | None = None
    obstacle: Any = None
    furniture: Any = None
    rotate: str | None = None
    delete: str | None = None
    resize: str | None = None
    move: str | None = None
    problem: str | None = None
    clean: str | None = None
    settings: str | None = None
    wifi: str | None = None
    version: int = 1


@dataclass
class MapRendererData:
    # JSON payload mirror for the Lovelace card — geometry rows mix int/float
    # coordinates (and str names for segments), hence the ``Any`` rows.
    data: Any
    size: list[Any] | None = None
    map_id: Any = 0
    saved_map_id: int | None = None
    map_index: int | None = None
    saved_map_status: int | None = None
    empty_map: bool | None = None
    frame_id: Any = 0
    saved_map: Any = False
    wifi_map: Any = False
    history_map: Any = False
    recovery_map: Any = False
    segments: Any = None
    active_segments: Any = field(default_factory=list)
    active_areas: list[list[Any]] = field(default_factory=list)
    active_points: list[list[Any]] = field(default_factory=list)
    active_cruise_points: list[list[Any]] = field(default_factory=list)
    task_cruise_points: bool = False
    predefined_points: list[list[Any]] | None = None
    no_mop: list[list[Any]] = field(default_factory=list)
    no_go: list[list[Any]] = field(default_factory=list)
    carpets: list[list[Any]] | None = None
    ignored_carpets: list[list[Any]] | None = None
    detected_carpets: list[list[Any]] | None = None
    virtual_walls: list[list[Any]] = field(default_factory=list)
    virtual_thresholds: list[list[Any]] | None = None
    passable_thresholds: list[list[Any]] | None = None
    impassable_thresholds: list[list[Any]] | None = None
    ramps: list[list[Any]] | None = None
    curtains: list[list[Any]] | None = None
    low_lying_areas: list[list[Any]] | None = None
    obstacles: list[list[Any]] = field(default_factory=list)
    furnitures: list[list[Any]] | None = None
    path: list[list[Any]] = field(default_factory=list)
    floor_material: dict[int, Any] | None = None
    hidden_segments: Any = None
    neglected_segments: Any = None
    robot_position: list[Any] | None = None
    charger_position: list[Any] | None = None
    router_position: list[Any] | None = None
    ai_outborders_user: list[list[Any]] | None = None
    ai_outborders: list[list[Any]] | None = None
    ai_outborders_new: list[list[Any]] | None = None
    ai_outborders_2d: list[list[Any]] | None = None
    second_cleaning: int | None = None
    mop_wash_count: int | None = None
    dust_collection_count: int | None = None
    multiple_cleaning_time: int | None = None
    dos: int | None = None
    ai_furniture_warning: int | None = None
    walls_info: Any | None = None
    walls_info_new: Any | None = None
    furniture_version: int | None = None
    startup_method: str | None = None
    cleanup_method: str | None = None
    cleaned_area: int | None = None
    cleaning_time: int | None = None
    robot_status: int | None = None
    station_status: int | None = None
    completed: bool | None = None
    remaining_battery: int | None = None
    cleanset: bool = False
    sequence: bool = False
    docked: Any = True
    work_status: Any = 0
    resources: Any = None
    version: int = 1
