"""Dreame Vacuum device capability model (feature detection from device info)."""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, Any

from .types_map import RobotType
from .types_properties import DreameVacuumAutoSwitchProperty, DreameVacuumProperty

if TYPE_CHECKING:
    from .device import DreameVacuumDevice


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
