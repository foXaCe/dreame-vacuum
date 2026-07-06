"""Per-object rendering mixin for :class:`DreameVacuumMapRenderer`.

Holds the per-object drawing routines extracted from the monolithic
``_core.py`` module. Each method takes the map geometry, the object
being rendered, and returns a fresh PIL image layer. They depend on
instance attributes set by the renderer (``self.icon_set``,
``self.color_scheme``, cached icon images, ...) — these are resolved at
runtime through the MRO once the mixin is bound to the renderer class.
"""

from __future__ import annotations

import base64
from io import BytesIO
import math
import time
from typing import Any, cast
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from ..resources import (
    FURNITURE_TYPE_TO_ICON,
    FURNITURE_TYPE_TO_IMAGE,
    FURNITURE_V2_TYPE_MIJIA_TO_IMAGE,
    FURNITURE_V2_TYPE_TO_ICON,
    FURNITURE_V2_TYPE_TO_IMAGE,
    MAP_CHARGER_IMAGE_DREAME,
    MAP_CHARGER_IMAGE_MATERIAL,
    MAP_CHARGER_IMAGE_MIJIA,
    MAP_CHARGER_VSLAM_IMAGE_DREAME,
    MAP_FONT,
    MAP_ICON_CRUISE_POINT_BG_DREAME,
    MAP_ICON_CRUISE_POINT_DREAME,
    MAP_ICON_OBSTACLE_BG_DREAME,
    MAP_ICON_OBSTACLE_HIDDEN_BG_DREAME,
    MAP_ICON_PROBLEM,
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
)
from ..vacuum_types import FurnitureType, MapImageDimensions, ObstacleType, Point, RobotType
from ._base import _MapRendererState


class _ObjectsMixin(_MapRendererState):
    """Renderers for vacuum, charger, router, neglected segments and low-lying areas."""

    def render_vacuum(
        self,
        robot_position: Point,
        robot_status: int,
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        size: float,
        map_rotation: int,
        scale: int,
    ) -> Image.Image:
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        icon_size = int(size * scale)
        robot_icon_size = (
            int(icon_size * 1.4)
            if self.icon_set == 2 or (self._robot_type == RobotType.VSLAM and self.icon_set == 3)
            else icon_size
        )
        if self._robot_icon is None:
            if self.icon_set == 2:
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
                    if self.icon_set == 3:
                        robot_image = MAP_ROBOT_VSLAM_IMAGE_DREAME_LIGHT
                    else:
                        robot_image = MAP_ROBOT_VSLAM_IMAGE_DREAME_DARK
                else:
                    if self.icon_set == 3:
                        robot_image = MAP_ROBOT_LIDAR_IMAGE_DREAME_LIGHT
                    else:
                        robot_image = MAP_ROBOT_LIDAR_IMAGE_DREAME_DARK

            self._robot_icon = Image.open(BytesIO(base64.b64decode(robot_image))).convert("RGBA")

            if (
                self._robot_type != RobotType.MOPPING
                and self._robot_type != RobotType.SWEEPING_AND_MOPPING
                and self.icon_set != 2
                and self.icon_set != 3
            ):
                enhancer = ImageEnhance.Brightness(self._robot_icon)
                if self.color_scheme.dark:
                    self._robot_icon = enhancer.enhance(1.5)
                else:
                    self._robot_icon = enhancer.enhance(0.9)

        robot_angle = robot_position.a or 0
        icon = self._robot_icon.resize(
            (robot_icon_size, robot_icon_size),
            resample=Image.Resampling.NEAREST,
        ).rotate(robot_angle, expand=1)
        point = robot_position.to_img(dimensions)

        if not self._low_memory:
            status_icon = None
            has_warning = False
            if robot_status >= 100:
                robot_status = robot_status - 100
            if robot_status >= 10:
                has_warning = True
                robot_status = robot_status - 10

            if robot_status == 1:
                if self._robot_cleaning_icon is None:
                    self._robot_cleaning_icon = (
                        Image.open(BytesIO(base64.b64decode(MAP_ROBOT_CLEANING_IMAGE)))
                        .convert("RGBA")
                        .resize(
                            ((int(icon_size * 1.25), int(icon_size * 1.25))),
                            resample=Image.Resampling.NEAREST,
                        )
                    )
                status_icon = self._robot_cleaning_icon

                if self.config.cleaning_direction:
                    if self._robot_cleaning_direction_icon is None:
                        self._robot_cleaning_direction_icon = (
                            Image.open(BytesIO(base64.b64decode(MAP_ROBOT_CLEANING_DIRECTION_IMAGE)))
                            .convert("RGBA")
                            .resize(
                                ((int(icon_size * 1.5), int(icon_size * 1.5))),
                            )
                        )

                    ico = self._robot_cleaning_direction_icon.rotate(robot_angle, expand=1)

                    offset = int(icon_size * 0.3)
                    x = point.x + offset * math.cos(-robot_angle * math.pi / 180)
                    y = point.y + offset * math.sin(-robot_angle * math.pi / 180)
                    new_layer.paste(
                        ico,
                        (
                            int(x * scale - (ico.size[0] / 2)),
                            int(y * scale - (ico.size[1] / 2)),
                        ),
                    )
            elif robot_status == 2:
                if self._robot_charging_icon is None:
                    self._robot_charging_icon = (
                        Image.open(BytesIO(base64.b64decode(MAP_ROBOT_CHARGING_IMAGE)))
                        .convert("RGBA")
                        .resize(
                            ((int(icon_size * 1.3), int(icon_size * 1.3))),
                            resample=Image.Resampling.NEAREST,
                        )
                    )
                status_icon = self._robot_charging_icon
            elif has_warning:
                if self._robot_warning_icon is None:
                    self._robot_warning_icon = (
                        Image.open(BytesIO(base64.b64decode(MAP_ROBOT_WARNING_IMAGE)))
                        .convert("RGBA")
                        .resize(
                            ((int(icon_size * 1.3), int(icon_size * 1.3))),
                            resample=Image.Resampling.NEAREST,
                        )
                    )
                status_icon = self._robot_warning_icon

            if status_icon:
                mask = Image.new("L", status_icon.size, 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, status_icon.size[0], status_icon.size[1]), fill=255)
                new_layer.paste(
                    status_icon,
                    (
                        int(point.x * scale - (status_icon.size[0] / 2)),
                        int(point.y * scale - (status_icon.size[1] / 2)),
                    ),
                    mask,
                )

        new_layer.paste(
            icon,
            (
                int(point.x * scale - (icon.size[0] / 2)),
                int(point.y * scale - (icon.size[1] / 2)),
            ),
            icon,
        )

        if not self._low_memory and robot_status == 3:
            if self._robot_sleeping_icon is None:
                sleeping_icon = (
                    Image.open(BytesIO(base64.b64decode(MAP_ROBOT_SLEEPING_IMAGE)))
                    .convert("RGBA")
                    .rotate(-map_rotation, expand=1)
                )
                enhancer = ImageEnhance.Brightness(sleeping_icon)
                if not self.color_scheme.dark:
                    sleeping_icon = enhancer.enhance(0.7)

                self._robot_sleeping_icon = [
                    sleeping_icon.resize(
                        ((int(icon_size * 0.3), int(icon_size * 0.3))),
                        resample=Image.Resampling.NEAREST,
                    ),
                    sleeping_icon.resize(
                        ((int(icon_size * 0.35), int(icon_size * 0.35))),
                        resample=Image.Resampling.NEAREST,
                    ),
                ]

            for k in [
                [int(icon_size * 0.34), int(icon_size * 0.18), 0],
                [int(icon_size * 0.43), int(icon_size * 0.43), 1],
            ]:
                status_icon = self._robot_sleeping_icon[k[2]]
                if map_rotation == 90:
                    x = point.x + k[1]
                    y = point.y + k[0]
                elif map_rotation == 180:
                    x = point.x - k[0]
                    y = point.y + k[1]
                elif map_rotation == 270:
                    x = point.x - k[1]
                    y = point.y - k[0]
                else:
                    x = point.x + k[0]
                    y = point.y - k[1]

                new_layer.paste(
                    status_icon,
                    (
                        int(x * scale - (status_icon.size[0] / 2)),
                        int(y * scale - (status_icon.size[1] / 2)),
                    ),
                    status_icon,
                )
        return new_layer

    def render_obstacle(
        self,
        obstacle: Any,
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        size: float,
        rotation: int,
        scale: int,
    ) -> Image.Image | None:
        if obstacle.ignore_status == 1:
            if (
                obstacle.type.value not in self._obstacle_hidden_icons
                and obstacle.type.value in OBSTACLE_TYPE_TO_HIDDEN_ICON
            ):
                self._obstacle_hidden_icons[obstacle.type.value] = Image.open(
                    BytesIO(base64.b64decode(OBSTACLE_TYPE_TO_HIDDEN_ICON[obstacle.type.value]))
                ).convert("RGBA")
            icon = self._obstacle_hidden_icons.get(obstacle.type.value)
        else:
            if obstacle.type.value not in self._obstacle_icons and obstacle.type.value in OBSTACLE_TYPE_TO_ICON:
                self._obstacle_icons[obstacle.type.value] = Image.open(
                    BytesIO(base64.b64decode(OBSTACLE_TYPE_TO_ICON[obstacle.type.value]))
                ).convert("RGBA")
            icon = self._obstacle_icons.get(obstacle.type.value)

        if icon:
            new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
            icon_size = size * scale * (1 if obstacle.ignore_status == 1 else 0.85)
            draw = ImageDraw.Draw(new_layer, "RGBA")

            if obstacle.ignore_status != 2 and self._obstacle_background is None:
                self._obstacle_background = Image.open(BytesIO(base64.b64decode(MAP_ICON_OBSTACLE_BG_DREAME))).convert(
                    "RGBA"
                )
                s = int(size * scale * 2)
                self._obstacle_background.thumbnail((s, s), Image.Resampling.LANCZOS)
                self._obstacle_background = self._obstacle_background.rotate(-rotation, expand=1)

            if obstacle.ignore_status == 2 and self._obstacle_hidden_background is None:
                self._obstacle_hidden_background = Image.open(
                    BytesIO(base64.b64decode(MAP_ICON_OBSTACLE_HIDDEN_BG_DREAME))
                ).convert("RGBA")
                s = int((size * 0.75) * scale * 2)
                self._obstacle_hidden_background.thumbnail((s, s), Image.Resampling.LANCZOS)
                self._obstacle_hidden_background = self._obstacle_hidden_background.rotate(-rotation, expand=1)

            background_image = (
                self._obstacle_hidden_background if obstacle.ignore_status == 2 else self._obstacle_background
            )
            assert background_image is not None
            bg_size = int((min(background_image.size[1], background_image.size[0]) / scale / 4) * 1.25)
            offset = int(-(size * (0.15 if obstacle.ignore_status == 2 else 0.2)) * scale)

            p = obstacle.to_img(dimensions)
            x = p.x
            y = p.y
            # if self.icon_set != 2:
            pos_offset = (
                max(background_image.size[1], background_image.size[0])
                * (1.35 if obstacle.ignore_status == 2 else 0.95)
                / scale
                / 2
            )
            # else:
            #    pos_offset = 0

            if rotation == 90:
                y_offset = 0
                x_offset = offset
                x = x + pos_offset
            elif rotation == 180:
                y_offset = offset
                x_offset = 0
                y = y + pos_offset
            elif rotation == 270:
                y_offset = 0
                x_offset = -offset
                x = x - pos_offset
            else:
                x_offset = 0
                y_offset = -offset
                y = y - pos_offset

            new_layer.paste(
                background_image,
                (
                    int(round(x * scale - (background_image.size[0] / 2) + x_offset)),
                    int(round(y * scale - (background_image.size[1] / 2) + y_offset)),
                ),
            )

            if obstacle.ignore_status == 2:
                icon = self._set_icon_color(
                    icon,
                    icon_size,
                    (34, 109, 242, 240),
                ).rotate(-rotation, expand=1)
            else:
                draw.ellipse(
                    [
                        (x - bg_size) * scale,
                        (y - bg_size) * scale,
                        (x + bg_size) * scale,
                        (y + bg_size) * scale,
                    ],
                    fill=(
                        (212, 212, 212, 255)
                        if obstacle.ignore_status == 1
                        else (
                            (128, 128, 128, 255)
                            if self.icon_set != 2
                            and (
                                obstacle.type == ObstacleType.LIQUID_STAIN
                                or obstacle.type == ObstacleType.DRIED_STAIN
                                or obstacle.type == ObstacleType.MIXED_STAIN
                                or obstacle.type == ObstacleType.DETECTED_STAIN
                            )
                            else (
                                (255, 140, 188, 255)
                                if self.icon_set != 2 and obstacle.type == ObstacleType.PET
                                else self.color_scheme.obstacle_bg
                            )
                        )
                    ),
                )
                icon = icon.resize((int(icon_size), int(icon_size))).rotate(-rotation, expand=1)

            new_layer.paste(
                icon,
                (
                    int(round(x * scale - (icon_size / 2))),
                    int(round(y * scale - (icon_size / 2))),
                ),
                icon,
            )

            return new_layer

        return None

    def render_cruise_point(
        self,
        index: int,
        cruise_point: Any,
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        size: float,
        rotation: int,
        scale: int,
    ) -> Image.Image:
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        if cruise_point.type == 1 and self._cruise_path_point_background is None:
            self._cruise_path_point_background = Image.open(
                BytesIO(base64.b64decode(MAP_ICON_CRUISE_POINT_BG_DREAME))
            ).convert("RGBA")
            s = int(size * scale * 3)
            self._cruise_path_point_background.thumbnail((s, s), Image.Resampling.LANCZOS)
            self._cruise_path_point_background = self._cruise_path_point_background.rotate(-rotation, expand=1)

        if cruise_point.type != 1 and self._cruise_point_background is None:
            self._cruise_point_background = Image.open(BytesIO(base64.b64decode(MAP_ICON_CRUISE_POINT_DREAME))).convert(
                "RGBA"
            )
            s = int(round(size * scale * 2))
            self._cruise_point_background.thumbnail((s, s), Image.Resampling.LANCZOS)
            self._cruise_point_background = self._cruise_point_background.rotate(-rotation, expand=1)

        background_image = (
            self._cruise_point_background if cruise_point.type != 1 else self._cruise_path_point_background
        )
        assert background_image is not None
        bg_size = int(min(background_image.size[1], background_image.size[0]) / scale / 4)
        offset = int(-bg_size * 1.25)

        p = cruise_point.to_img(dimensions)
        x = p.x
        y = p.y
        pos_offset = (
            max(background_image.size[1], background_image.size[0])
            * (1.75 if cruise_point.type != 1 else 1.20)
            / scale
            / 3
        )

        if rotation == 90:
            y_offset = 0
            x_offset = offset
            x = x + pos_offset
        elif rotation == 180:
            y_offset = offset
            x_offset = 0
            y = y + pos_offset
        elif rotation == 270:
            y_offset = 0
            x_offset = -offset
            x = x - pos_offset
        else:
            x_offset = 0
            y_offset = -offset
            y = y - pos_offset

        new_layer.paste(
            background_image,
            (
                int(round(x * scale - (background_image.size[0] / 2) + x_offset)),
                int(round(y * scale - (background_image.size[1] / 2) + y_offset)),
            ),
        )

        if cruise_point.type == 1:
            draw.ellipse(
                [
                    (x - bg_size) * scale,
                    (y - bg_size) * scale,
                    (x + bg_size) * scale,
                    (y + bg_size) * scale,
                ],
                fill=(212, 212, 212, 255) if cruise_point.completed else (34, 109, 242, 255),
            )

        if cruise_point.type == 1:
            text_box = Image.new("RGBA", (bg_size * 2 * scale, bg_size * 2 * scale), (255, 255, 255, 0))
            text_box_draw = ImageDraw.Draw(text_box, "RGBA")

            if self._font_file is None:
                self._font_file = zlib.decompress(base64.b64decode(MAP_FONT), zlib.MAX_WBITS | 32)

            font = ImageFont.truetype(BytesIO(self._font_file), int(bg_size * 1.5 * scale))

            text = str(index)
            left, top, tw, th = text_box_draw.textbbox((0, 0), text, font)
            text_box_draw.text(
                (
                    (text_box.size[1] - tw) / 2,
                    (text_box.size[1] - th - int(round(size * 0.4))) / 2,
                ),
                text,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(255, 255, 255, 100),
            )
            text_box = text_box.rotate(-rotation, expand=1)
            new_layer.paste(
                text_box,
                (int(round((x - bg_size) * scale)), int(round((y - bg_size) * scale))),
                text_box,
            )

        return new_layer

    def render_furniture(
        self,
        furniture: Any,
        furniture_version: int,
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        size: float,
        rotation: int,
        scale: int,
    ) -> Image.Image | None:
        draw_image = furniture.width and furniture.height
        furniture_type = (
            FurnitureType.COFFEE_TABLE.value
            if furniture_version == 1 and furniture.type == FurnitureType.ROUND_COFFEE_TABLE
            else furniture.type.value
        )
        if draw_image:
            if furniture_version == 3:
                furniture_images = FURNITURE_V2_TYPE_MIJIA_TO_IMAGE
            elif furniture_version == 2:
                furniture_images = FURNITURE_V2_TYPE_TO_IMAGE
            else:
                furniture_images = FURNITURE_TYPE_TO_IMAGE

            if furniture_type not in self._furniture_images and furniture_type in furniture_images:
                img = np.array(Image.open(BytesIO(base64.b64decode(furniture_images[furniture_type]))).convert("RGBA"))
                if self.icon_set != 2:
                    img[..., 3] = 235 * (img[..., 3] > 0)
                self._furniture_images[furniture_type] = Image.fromarray(img)
            icon = self._furniture_images.get(furniture_type)
        else:
            furniture_icons = FURNITURE_V2_TYPE_TO_ICON if furniture_version >= 2 else FURNITURE_TYPE_TO_ICON
            if furniture_type not in self._furniture_icons and furniture_type in furniture_icons:
                self._furniture_icons[furniture_type] = Image.open(
                    BytesIO(base64.b64decode(furniture_icons[furniture_type]))
                ).convert("RGBA")
            icon = self._furniture_icons.get(furniture_type)
        if icon:
            new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
            if draw_image:
                w = (furniture.width / dimensions.grid_size) * dimensions.scale
                h = (furniture.height / dimensions.grid_size) * dimensions.scale
                p = Point(
                    furniture.x,
                    furniture.y,
                ).to_img(dimensions)
                x = p.x
                y = p.y

                img = icon.rotate(furniture.angle, expand=1)
                if furniture_version >= 2:
                    img = img.resize(
                        (int(w * scale), int(h * scale)),
                        resample=Image.Resampling.LANCZOS,
                    )
                else:
                    img.thumbnail((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
                img = img.rotate(-(furniture.angle * 2), expand=1)

                new_layer.paste(
                    img,
                    (
                        int((x * scale) - ((img.size[0]) / 2)),
                        int((y * scale) - ((img.size[1]) / 2)),
                    ),
                    img,
                )
            else:
                icon_size = size * scale * 1.15
                if self._furniture_background is None:
                    self._furniture_background = Image.open(
                        BytesIO(base64.b64decode(MAP_ICON_OBSTACLE_BG_DREAME))
                    ).convert("RGBA")
                    s = int(size * scale * 2)
                    self._furniture_background.thumbnail((s, s), Image.Resampling.LANCZOS)
                    self._furniture_background = self._furniture_background.rotate(-rotation, expand=1)

                offset = int(-(size * 0.2) * scale)

                p = furniture.to_img(dimensions)
                x = p.x
                y = p.y
                pos_offset = (
                    (self._furniture_background.size[1] * (1.15 if rotation == 90 or rotation == 270 else 0.9))
                    / scale
                    / 2
                )

                if rotation == 90:
                    y_offset = 0
                    x_offset = offset
                    x = x + pos_offset
                elif rotation == 180:
                    y_offset = offset
                    x_offset = 0
                    y = y + pos_offset
                elif rotation == 270:
                    y_offset = 0
                    x_offset = -offset
                    x = x - pos_offset
                else:
                    x_offset = 0
                    y_offset = -offset
                    y = y - pos_offset

                new_layer.paste(
                    self._furniture_background,
                    (
                        int(round(x * scale - (self._furniture_background.size[0] / 2) + x_offset)),
                        int(round(y * scale - (self._furniture_background.size[1] / 2) + y_offset)),
                    ),
                )

                icon = icon.resize((int(icon_size), int(icon_size))).rotate(-rotation, expand=1)

                new_layer.paste(
                    icon,
                    (
                        int(round(x * scale - (icon_size / 2))),
                        int(round(y * scale - (icon_size / 2))),
                    ),
                    icon,
                )

            return new_layer

        return None

    @staticmethod
    def _badge_transparent_recolor(img: Image.Image, recolor: tuple[int, int, int] | None = None) -> Image.Image:
        """Drop a status icon's white badge disc and optionally recolour the glyph.

        The bundled washing/self-clean icons ship as a coloured pinwheel on an
        opaque white circle. The official app shows them without that disc, so
        make near-white pixels transparent; when ``recolor`` is given, repaint
        the remaining glyph pixels with it (keeping their alpha, so anti-aliased
        edges stay soft).
        """
        arr = np.array(img.convert("RGBA"))
        white = (arr[:, :, 0] > 225) & (arr[:, :, 1] > 225) & (arr[:, :, 2] > 225)
        arr[white, 3] = 0
        if recolor is not None:
            glyph = arr[:, :, 3] > 0
            arr[glyph, 0], arr[glyph, 1], arr[glyph, 2] = recolor
        return Image.fromarray(arr, "RGBA")

    def render_charger(
        self,
        charger_position: Point,
        station_status: int,
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        size: float,
        map_rotation: int,
        scale: int,
    ) -> Image.Image:
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        icon_size = int(size * scale)
        if self.icon_set == 3:
            icon_size = int(icon_size * 1.2)
        elif self.icon_set == 2 or self._robot_type == RobotType.VSLAM:
            icon_size = int(icon_size * 1.5)

        if self._charger_icon is None:
            if self.icon_set == 3:
                charger_image = MAP_CHARGER_IMAGE_MATERIAL
            elif self.icon_set == 2:
                charger_image = MAP_CHARGER_IMAGE_MIJIA
            else:
                if self._robot_type == RobotType.VSLAM:
                    charger_image = MAP_CHARGER_VSLAM_IMAGE_DREAME
                else:
                    charger_image = MAP_CHARGER_IMAGE_DREAME
            self._charger_icon = Image.open(BytesIO(base64.b64decode(charger_image))).convert("RGBA")

            if self.icon_set == 3:
                self._charger_icon = self._set_icon_color(
                    self._charger_icon,
                    icon_size,
                    (0, 255, 126, 255),
                )

            if self.color_scheme.dark:
                enhancer = ImageEnhance.Brightness(self._charger_icon)
                self._charger_icon = enhancer.enhance(0.7)

        charger_icon = self._charger_icon.resize((icon_size, icon_size), resample=Image.Resampling.NEAREST).rotate(
            (
                (charger_position.a or 0)
                if self._robot_type == RobotType.VSLAM or self.icon_set == 0 or self.icon_set == 2 or self.icon_set == 3
                else (-map_rotation)
            ),
            expand=1,
        )

        point = charger_position.to_img(dimensions)
        new_layer.paste(
            charger_icon,
            (
                int((point.x * scale) - (charger_icon.size[0] / 2)),
                int((point.y * scale) - (charger_icon.size[1] / 2)),
            ),
            charger_icon,
        )

        if station_status > 0 and not self._low_memory:
            hot_washing = False
            if station_status >= 10:
                hot_washing = True
                station_status = station_status - 10

            if station_status == 1:
                if self._robot_emptying_icon is None:
                    self._robot_emptying_icon = (
                        Image.open(BytesIO(base64.b64decode(MAP_ROBOT_EMPTYING_IMAGE)))
                        .convert("RGBA")
                        .resize(
                            (int(icon_size * 1.25), int(icon_size * 1.25)),
                            resample=Image.Resampling.NEAREST,
                        )
                        .rotate(-map_rotation, expand=1)
                    )
                offset = icon_size * 1.2
                icon = self._robot_emptying_icon
            elif station_status < 4:
                if not hot_washing and self._robot_washing_icon is None:
                    washing_img = (
                        Image.open(BytesIO(base64.b64decode(MAP_ROBOT_WASHING_IMAGE)))
                        .convert("RGBA")
                        .resize(
                            (int(icon_size * 0.9), int(icon_size * 0.9)),
                            resample=Image.Resampling.LANCZOS,
                        )
                    )
                    # Match the official app: drop the white disc, red pinwheel.
                    washing_img = self._badge_transparent_recolor(washing_img, (255, 59, 48))
                    enhancer = ImageEnhance.Brightness(washing_img)
                    if self.color_scheme.dark:
                        washing_img = enhancer.enhance(0.85)
                    self._robot_washing_icon = washing_img

                if hot_washing and self._robot_hot_washing_icon is None:
                    hot_washing_img = (
                        Image.open(BytesIO(base64.b64decode(MAP_ROBOT_HOT_WASHING_IMAGE)))
                        .convert("RGBA")
                        .resize(
                            (int(icon_size * 0.9), int(icon_size * 0.9)),
                            resample=Image.Resampling.LANCZOS,
                        )
                    )
                    # Keep the hot-wash orange, just drop the white disc.
                    hot_washing_img = self._badge_transparent_recolor(hot_washing_img)
                    enhancer = ImageEnhance.Brightness(hot_washing_img)
                    if self.color_scheme.dark:
                        hot_washing_img = enhancer.enhance(0.85)
                    self._robot_hot_washing_icon = hot_washing_img

                offset = icon_size * 1.5

                # Animate the washing icon rotation based on time.
                # One full turn every 2 seconds for a smooth spinner effect.
                rotation_speed = 360 / 2
                rotation_angle = (time.time() * rotation_speed) % 360

                # Apply both the map rotation and the animation.
                base_icon = self._robot_hot_washing_icon if hot_washing else self._robot_washing_icon
                assert base_icon is not None
                icon = base_icon.rotate(-map_rotation - rotation_angle, expand=1)
            else:
                if not hot_washing and self._robot_drying_icon is None:
                    self._robot_drying_icon = (
                        Image.open(BytesIO(base64.b64decode(MAP_ROBOT_DRYING_IMAGE)))
                        .convert("RGBA")
                        .resize(
                            (int(icon_size * 1.25), int(icon_size * 1.25)),
                            resample=Image.Resampling.NEAREST,
                        )
                        .rotate(-map_rotation, expand=1)
                    )

                if hot_washing and self._robot_hot_drying_icon is None:
                    self._robot_hot_drying_icon = (
                        Image.open(BytesIO(base64.b64decode(MAP_ROBOT_HOT_DRYING_IMAGE)))
                        .convert("RGBA")
                        .resize(
                            (int(icon_size * 1.25), int(icon_size * 1.25)),
                            resample=Image.Resampling.NEAREST,
                        )
                        .rotate(-map_rotation, expand=1)
                    )
                offset = icon_size * 1.2
                icon = cast("Image.Image", self._robot_hot_drying_icon if hot_washing else self._robot_drying_icon)

            icon_x = point.x * scale
            icon_y = point.y * scale
            if map_rotation == 90:
                icon_x = icon_x + offset
            elif map_rotation == 180:
                icon_y = icon_y + offset
            elif map_rotation == 270:
                icon_x = icon_x - offset
            else:
                icon_y = icon_y - offset

            new_layer.paste(icon, (int(icon_x - (icon.size[0] / 2)), int(icon_y - (icon.size[1] / 2))))

        return new_layer

    def render_router(
        self,
        router_position: Point,
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        size: float,
        rotation: int,
        scale: int,
    ) -> Image.Image:
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        icon_size = int(size * scale)
        if self._wifi_icon is None:
            self._wifi_icon = (
                Image.open(BytesIO(base64.b64decode(MAP_WIFI_IMAGE_DREAME)))
                .convert("RGBA")
                .resize((icon_size, icon_size), resample=Image.Resampling.NEAREST)
            )

        point = router_position.to_img(dimensions)
        bg_size = (size * 1.2) / 2
        draw.ellipse(
            [
                int((point.x - bg_size) * scale),
                int((point.y - bg_size) * scale),
                int((point.x + bg_size) * scale),
                int((point.y + bg_size) * scale),
            ],
            fill=(34, 98, 211, 255) if self.color_scheme.dark else (34, 109, 242, 255),
        )
        wifi_icon = self._wifi_icon.rotate(-rotation, expand=1)
        new_layer.paste(
            wifi_icon,
            (
                int((point.x * scale) - (wifi_icon.size[0] / 2)),
                int((point.y * scale) - (wifi_icon.size[1] / 2)),
            ),
            wifi_icon,
        )

        return new_layer

    def render_neglected_segments(
        self,
        neglected_segments: Any,
        segments: Any,
        layer_size: tuple[int, int],
        segment_mask: Any,
        dimensions: MapImageDimensions,
        rotation: Any,
        cleaning_map: Any,
    ) -> Image.Image:
        mask_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        mask_layer.paste(segment_mask, (0, 0))

        if self._map_problem_icon is None:
            self._map_problem_icon = Image.open(BytesIO(base64.b64decode(MAP_ICON_PROBLEM))).convert("RGBA")

        if rotation == 0 or rotation == 180 or self._square:
            width = (dimensions.width) + (
                (dimensions.padding[0] + dimensions.padding[2] - dimensions.crop[0] - dimensions.crop[2])
                / dimensions.scale
            )
            icon_size = width * (0.06 if self._square else 0.07) * dimensions.scale
        else:
            height = (dimensions.height) + (
                (dimensions.padding[1] + dimensions.padding[3] - dimensions.crop[1] - dimensions.crop[3])
                / dimensions.scale
            )
            icon_size = height * 0.07 * dimensions.scale

        if cleaning_map:
            icon_size = int(icon_size * 0.7)

        problem_icon = self._map_problem_icon.resize((int(icon_size), int(icon_size))).rotate(-rotation, expand=1)

        mask_layer.paste(segment_mask, (0, 0))
        for k in neglected_segments:
            if k in segments:
                segment = segments[k]
                p = Point(segment.x, segment.y).to_img(dimensions, False)
                mask_layer.paste(
                    problem_icon,
                    (
                        int(p.x - (problem_icon.size[0] / 2)),
                        int(p.y - (problem_icon.size[1] / 2)),
                    ),
                    mask=problem_icon,
                )

        return mask_layer

    def render_low_lying_areas(
        self,
        areas: Any,
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        width: int,
        scale: int,
    ) -> Image.Image:
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        for area in areas:
            if area.hidden:
                continue
            coords = []
            for i in range(0, len(area.polygon), 2):
                coords.extend(
                    [
                        (
                            ((area.polygon[i] - dimensions.left) / dimensions.grid_size) * dimensions.scale
                            + dimensions.padding[0]
                            - dimensions.crop[0]
                        )
                        * scale,
                        (
                            (
                                (
                                    ((dimensions.height) * dimensions.grid_size - 1)
                                    - (area.polygon[i + 1] - dimensions.top)
                                )
                                / dimensions.grid_size
                            )
                            * dimensions.scale
                            + dimensions.padding[1]
                            - dimensions.crop[1]
                        )
                        * scale,
                    ]
                )
            draw.polygon(
                coords,
                self.color_scheme.low_lying_area,
                (
                    self.color_scheme.auto_low_lying_area_outline
                    if area.type == 0
                    else self.color_scheme.manual_low_lying_area_outline
                ),
                width=(width * scale),
            )
        return new_layer
