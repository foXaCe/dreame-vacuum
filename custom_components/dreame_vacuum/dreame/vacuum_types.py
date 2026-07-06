from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from .device import DreameVacuumDevice

from .types_attributes import *
from .types_enums import *
from .types_properties import *


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


from .types_map import *


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
