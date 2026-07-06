"""Resource/asset accessors for :class:`DreameVacuumMapRenderer`.

Builds the icon/image resource bundle served to the frontend
(``get_resources``) and exposes the calibration-point and
default/disconnected placeholder map images. Extracted from the
monolithic ``_core.py`` module.
"""

from __future__ import annotations

import base64
from io import BytesIO
import json
from typing import Any, cast
import zlib

from PIL import Image, ImageFilter, ImageOps

from ..resources import (
    DEFAULT_MAP_IMAGE,
    FURNITURE_TYPE_TO_ICON,
    FURNITURE_TYPE_TO_IMAGE,
    FURNITURE_V2_TYPE_MIJIA_TO_IMAGE,
    FURNITURE_V2_TYPE_TO_ICON,
    FURNITURE_V2_TYPE_TO_IMAGE,
    MAP_CHARGER_IMAGE_DREAME,
    MAP_CHARGER_IMAGE_MATERIAL,
    MAP_CHARGER_IMAGE_MIJIA,
    MAP_CHARGER_VSLAM_IMAGE_DREAME,
    MAP_FONT_LIGHT,
    MAP_ICON_CLEAN,
    MAP_ICON_CLEANING_MODE_DREAME,
    MAP_ICON_CLEANING_MODE_MATERIAL,
    MAP_ICON_CLEANING_MODE_MIJIA,
    MAP_ICON_CLEANING_ROUTE_DREAME,
    MAP_ICON_CLEANING_ROUTE_MATERIAL,
    MAP_ICON_CRUISE_POINT_BG_DREAME,
    MAP_ICON_CRUISE_POINT_DREAME,
    MAP_ICON_CUSTOM_MOPPING_ROUTE_DREAME,
    MAP_ICON_DELETE,
    MAP_ICON_MOP_PAD_HUMIDITY_DREAME,
    MAP_ICON_MOP_PAD_HUMIDITY_MATERIAL,
    MAP_ICON_MOVE,
    MAP_ICON_OBSTACLE_BG_DREAME,
    MAP_ICON_OBSTACLE_HIDDEN_BG_DREAME,
    MAP_ICON_PROBLEM,
    MAP_ICON_REPEATS_DREAME,
    MAP_ICON_REPEATS_MATERIAL,
    MAP_ICON_REPEATS_MIJIA,
    MAP_ICON_RESIZE,
    MAP_ICON_ROTATE,
    MAP_ICON_SELECTED_SEGMENT,
    MAP_ICON_SETTINGS,
    MAP_ICON_SUCTION_LEVEL_DREAME,
    MAP_ICON_SUCTION_LEVEL_MATERIAL,
    MAP_ICON_SUCTION_LEVEL_MIJIA,
    MAP_ICON_WATER_VOLUME_DREAME,
    MAP_ICON_WATER_VOLUME_MATERIAL,
    MAP_ICON_WATER_VOLUME_MIJIA,
    MAP_ROBOT_CHARGING_IMAGE,
    MAP_ROBOT_CLEANING_DIRECTION_IMAGE,
    MAP_ROBOT_CLEANING_IMAGE,
    MAP_ROBOT_DRYING_IMAGE,
    MAP_ROBOT_EMPTYING_IMAGE,
    MAP_ROBOT_HOT_DRYING_IMAGE,
    MAP_ROBOT_HOT_WASHING_IMAGE,
    MAP_ROBOT_LIDAR_IMAGE_DREAME_DARK,
    MAP_ROBOT_LIDAR_IMAGE_DREAME_LIGHT,
    MAP_ROBOT_LIDAR_IMAGE_MIJIA,
    MAP_ROBOT_MOP_IMAGE_DREAME,
    MAP_ROBOT_MOP_IMAGE_MIJIA,
    MAP_ROBOT_SLEEPING_IMAGE,
    MAP_ROBOT_VSLAM_IMAGE_DREAME_DARK,
    MAP_ROBOT_VSLAM_IMAGE_DREAME_LIGHT,
    MAP_ROBOT_VSLAM_IMAGE_MIJIA,
    MAP_ROBOT_WARNING_IMAGE,
    MAP_ROBOT_WASHING_IMAGE,
    MAP_WIFI_IMAGE_DREAME,
    OBSTACLE_TYPE_TO_HIDDEN_ICON,
    OBSTACLE_TYPE_TO_ICON,
    SEGMENT_ICONS_DREAME,
    SEGMENT_ICONS_DREAME_OLD,
    SEGMENT_ICONS_MATERIAL,
    SEGMENT_ICONS_MIJIA,
)
from ..vacuum_types import (
    FURNITURE_TYPE_TO_DIMENSIONS,
    FURNITURE_V2_TYPE_MIJIA_TO_DIMENSIONS,
    FURNITURE_V2_TYPE_TO_DIMENSIONS,
    SEGMENT_TYPE_CODE_TO_HA_ICON,
    SEGMENT_TYPE_CODE_TO_NAME,
    FurnitureType,
    MapRendererResources,
    ObstacleType,
    RobotType,
)
from ._base import _MapRendererState


class _ResourcesMixin(_MapRendererState):
    """Builds the frontend icon/image resource bundle and placeholder map images."""

    def get_resources(self, capability: Any, as_json: bool = False, icon_set: Any = None) -> MapRendererResources | str:
        if icon_set is None or not str(icon_set).isdecimal():
            icon_set = self.icon_set
        else:
            icon_set = int(icon_set)

        if icon_set == 2:
            if self._robot_type == RobotType.MOPPING:
                robot_image = MAP_ROBOT_MOP_IMAGE_MIJIA
            elif self._robot_type == RobotType.VSLAM:
                robot_image = MAP_ROBOT_VSLAM_IMAGE_MIJIA
            else:
                robot_image = MAP_ROBOT_LIDAR_IMAGE_MIJIA
        else:
            if self._robot_type == RobotType.MOPPING:
                robot_image = MAP_ROBOT_MOP_IMAGE_DREAME
            elif self._robot_type == RobotType.SWEEPING_AND_MOPPING:
                robot_image = MAP_ROBOT_LIDAR_IMAGE_DREAME_LIGHT
            elif self._robot_type == RobotType.VSLAM:
                if icon_set == 3:
                    robot_image = MAP_ROBOT_VSLAM_IMAGE_DREAME_LIGHT
                else:
                    robot_image = MAP_ROBOT_VSLAM_IMAGE_DREAME_DARK
            else:
                if icon_set == 3:
                    robot_image = MAP_ROBOT_LIDAR_IMAGE_DREAME_LIGHT
                else:
                    robot_image = MAP_ROBOT_LIDAR_IMAGE_DREAME_DARK

        if icon_set == 3:
            charger_image = MAP_CHARGER_IMAGE_MATERIAL
        elif icon_set == 2:
            charger_image = MAP_CHARGER_IMAGE_MIJIA
        else:
            if self._robot_type == RobotType.VSLAM:
                charger_image = MAP_CHARGER_VSLAM_IMAGE_DREAME
            else:
                charger_image = MAP_CHARGER_IMAGE_DREAME

        icons = SEGMENT_ICONS_DREAME
        if icon_set == 1:
            icons = SEGMENT_ICONS_DREAME_OLD
        elif icon_set == 2:
            icons = SEGMENT_ICONS_MIJIA
        elif icon_set == 3:
            icons = SEGMENT_ICONS_MATERIAL

        if icon_set == 2:
            repeats = MAP_ICON_REPEATS_MIJIA
            suction_level = MAP_ICON_SUCTION_LEVEL_MIJIA
            water_volume = MAP_ICON_WATER_VOLUME_MIJIA
            cleaning_mode = MAP_ICON_CLEANING_MODE_MIJIA
        elif icon_set == 3:
            repeats = MAP_ICON_REPEATS_MATERIAL
            suction_level = MAP_ICON_SUCTION_LEVEL_MATERIAL
            water_volume = MAP_ICON_WATER_VOLUME_MATERIAL
            cleaning_mode = MAP_ICON_CLEANING_MODE_MATERIAL
        else:
            repeats = MAP_ICON_REPEATS_DREAME
            suction_level = MAP_ICON_SUCTION_LEVEL_DREAME
            water_volume = MAP_ICON_WATER_VOLUME_DREAME
            cleaning_mode = MAP_ICON_CLEANING_MODE_DREAME

        if self._light_font_file is None:
            self._light_font_file = zlib.decompress(base64.b64decode(MAP_FONT_LIGHT), zlib.MAX_WBITS | 32)

        resources = MapRendererResources(
            icon_set=icon_set,
            robot_type=self._robot_type.value,
            robot=robot_image,
            charger=charger_image,
            charging=MAP_ROBOT_CHARGING_IMAGE,
            cleaning=MAP_ROBOT_CLEANING_IMAGE,
            warning=MAP_ROBOT_WARNING_IMAGE,
            sleeping=MAP_ROBOT_SLEEPING_IMAGE,
            cleaning_direction=MAP_ROBOT_CLEANING_DIRECTION_IMAGE,
            selected_segment=MAP_ICON_SELECTED_SEGMENT,
            cruise_point_background=MAP_ICON_CRUISE_POINT_DREAME,
            segment={
                k: {
                    "name": SEGMENT_TYPE_CODE_TO_NAME.get(k),
                    "icon": v,
                    "mdi": SEGMENT_TYPE_CODE_TO_HA_ICON.get(k, "mdi:home-outline"),
                }
                for k, v in icons.items()
            },
            default_map_image=DEFAULT_MAP_IMAGE,
            font=base64.b64encode(self._light_font_file).decode("utf-8"),
            rotate=MAP_ICON_ROTATE,
            delete=MAP_ICON_DELETE,
            resize=MAP_ICON_RESIZE,
            move=MAP_ICON_MOVE,
            problem=MAP_ICON_PROBLEM,
            clean=MAP_ICON_CLEAN,
            settings=MAP_ICON_SETTINGS,
        )

        if capability.customized_cleaning:
            resources.repeats = repeats
            resources.suction_level = suction_level
            resources.water_volume = water_volume
            resources.mop_pad_humidity = (
                MAP_ICON_MOP_PAD_HUMIDITY_MATERIAL if icon_set == 3 else MAP_ICON_MOP_PAD_HUMIDITY_DREAME
            )
            if capability.custom_cleaning_mode:
                resources.cleaning_mode = cleaning_mode
                if capability.cleaning_route:
                    resources.cleaning_route = (
                        MAP_ICON_CLEANING_ROUTE_MATERIAL if icon_set == 3 else MAP_ICON_CLEANING_ROUTE_DREAME
                    )
                elif capability.segment_mopping_settings:
                    resources.custom_mopping_route = MAP_ICON_CUSTOM_MOPPING_ROUTE_DREAME

        if capability.self_wash_base:
            resources.washing = MAP_ROBOT_WASHING_IMAGE
            resources.drying = MAP_ROBOT_DRYING_IMAGE
            if capability.hot_washing:
                resources.hot_washing = MAP_ROBOT_HOT_WASHING_IMAGE
                resources.hot_drying = MAP_ROBOT_HOT_DRYING_IMAGE

        if capability.auto_empty_base:
            resources.emptying = MAP_ROBOT_EMPTYING_IMAGE

        if capability.wifi_map:
            resources.wifi = MAP_WIFI_IMAGE_DREAME

        if capability.camera_streaming:
            resources.cruise_path_point_background = MAP_ICON_CRUISE_POINT_BG_DREAME
            resources.obstacle_background = MAP_ICON_OBSTACLE_BG_DREAME
            resources.obstacle_hidden_background = MAP_ICON_OBSTACLE_HIDDEN_BG_DREAME
            resources.obstacle = {
                i.value: {
                    "name": i.name.replace("_", " ").capitalize(),
                    "icon": OBSTACLE_TYPE_TO_ICON.get(i.value),
                    "hidden_icon": OBSTACLE_TYPE_TO_HIDDEN_ICON.get(i.value),
                }
                for i in ObstacleType
            }
            furniture_types = list(FurnitureType)
            if not capability.pet_furniture:
                furniture_types = list(
                    set(furniture_types)
                    - {
                        FurnitureType.LITTER_BOX,
                        FurnitureType.PET_BED,
                        FurnitureType.FOOD_BOWL,
                        FurnitureType.PET_TOILET,
                        FurnitureType.ENCLOSED_LITTER_BOX,
                    }
                )

            if not capability.extended_furnitures:
                furniture_types = list(set(furniture_types) - {i for i in FurnitureType if i.value > 13})

            if capability.new_furnitures:
                if icon_set == 2 and capability.mijia:
                    dimensions = FURNITURE_V2_TYPE_MIJIA_TO_DIMENSIONS
                    images = FURNITURE_V2_TYPE_MIJIA_TO_IMAGE
                else:
                    dimensions = FURNITURE_V2_TYPE_TO_DIMENSIONS
                    images = FURNITURE_V2_TYPE_TO_IMAGE

                resources.furniture = {
                    i.value: {
                        "name": i.name.replace("_", " ").capitalize(),
                        "icon": FURNITURE_V2_TYPE_TO_ICON.get(i.value),
                        "image": images.get(i.value),
                        "dimensions": dimensions.get(i.value),
                    }
                    for i in furniture_types
                }
            else:
                resources.furniture = {
                    i.value: {
                        "name": i.name.replace("_", " ").capitalize(),
                        "icon": FURNITURE_TYPE_TO_ICON.get(i.value),
                        "image": FURNITURE_TYPE_TO_IMAGE.get(i.value),
                        "dimensions": FURNITURE_TYPE_TO_DIMENSIONS.get(i.value),
                    }
                    for i in furniture_types
                }

        if as_json:
            return json.dumps(
                resources,
                default=lambda o: {key: value for key, value in o.__dict__.items() if value is not None},
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )

        return resources

    @property
    def calibration_points(self) -> dict[str, int]:
        return cast("dict[str, int]", self._calibration_points)

    @property
    def default_map_image(self) -> bytes:
        if self._default_map_image is None:
            default_map_image = Image.open(BytesIO(base64.b64decode(DEFAULT_MAP_IMAGE))).convert("RGBA")
            self._default_map_image = ImageOps.expand(
                default_map_image.resize(
                    (
                        int(default_map_image.size[0] * 0.8),
                        int(default_map_image.size[1] * 0.8),
                    )
                ),
                border=(50, 75, 50, 75),
            )
        if self._default_map_image_data is None:
            # Cache the encoded PNG: this property is read from the event
            # loop, so the encode must not be paid on every access.
            self._default_map_image_data = cast(bytes, self._to_buffer(self._default_map_image))
        return self._default_map_image_data

    @property
    def disconnected_map_image(self) -> bytes:
        if self._image:
            if self._disconnected_map_image_src is not self._image or self._disconnected_map_image_data is None:
                self._disconnected_map_image_src = self._image
                self._disconnected_map_image_data = cast(
                    bytes,
                    self._to_buffer(self._image.filter(ImageFilter.GaussianBlur(7 if self._low_resolution else 13))),
                )
            return self._disconnected_map_image_data
        return self.default_map_image

    @property
    def default_calibration_points(self) -> dict[str, int]:
        return cast("dict[str, int]", self._default_calibration_points)
