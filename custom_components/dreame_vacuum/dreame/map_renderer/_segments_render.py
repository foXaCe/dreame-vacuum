"""Segment-drawing mixin for :class:`DreameVacuumMapRenderer`.

Holds the room-level rendering routines extracted from the monolithic
``_core.py`` module: the segment badge/label layer (``render_segment``),
the floor-material overlay (``render_floor_material``) and the carpet
overlay (``render_carpets``). Like the object renderers in
``_objects.py``, they rely on instance attributes set by the renderer
(``self.icon_set``, ``self.color_scheme``, cached icon images, ...)
resolved at runtime through the MRO once the mixin is bound to the
renderer class.
"""

from __future__ import annotations

import base64
from io import BytesIO
import math
from typing import Any, cast
import zlib

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from ..resources import (
    MAP_FONT,
    SEGMENT_ICONS_DREAME,
    SEGMENT_ICONS_DREAME_OLD,
    SEGMENT_ICONS_MATERIAL,
    SEGMENT_ICONS_MIJIA,
)
from ..vacuum_types import Point, RobotType
from ._base import _MapRendererState


class _SegmentsRenderMixin(_MapRendererState):
    """Renders segment badges/labels, floor material overlays and carpets."""

    def render_segment(
        self,
        segment: Any,
        cleanset: Any,
        sequence: Any,
        layer_size: Any,
        dimensions: Any,
        size: Any,
        rotation: Any,
        scale: Any,
        active: Any,
        neglected: Any,
        flip_badge: bool = False,
        name_offset: Any = (0, 0),
    ) -> Any:
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        if segment.x is not None and segment.y is not None:
            active = active and not neglected
            text = None
            icon_type = segment.icon_type
            if icon_type not in self._segment_icons:
                icon_set = SEGMENT_ICONS_DREAME
                if self.icon_set == 1:
                    icon_set = SEGMENT_ICONS_DREAME_OLD
                elif self.icon_set == 2:
                    icon_set = SEGMENT_ICONS_MIJIA
                elif self.icon_set == 3:
                    icon_set = SEGMENT_ICONS_MATERIAL

                if icon_type in icon_set:
                    self._segment_icons[icon_type] = Image.open(BytesIO(base64.b64decode(icon_set[icon_type]))).convert(
                        "RGBA"
                    )
                    if self.color_scheme.invert and not (self.config.name_background and self.icon_set != 2):
                        enhancer = ImageEnhance.Brightness(self._segment_icons[icon_type])
                        self._segment_icons[icon_type] = enhancer.enhance(0.1)

            icon = self._segment_icons.get(icon_type) if self.config.icon else None
            if segment.type == 0 or self.config.name or icon is None:
                text = (
                    segment.get_translated_name(self._language)
                    if (self._robot_type != RobotType.VSLAM or icon is not None)
                    or (segment.custom_name is not None and segment.type == 0)
                    or self.icon_set == 2
                    else segment.letter
                )
            elif segment.index > 0:
                text = str(segment.index)

            text_font = None
            order_font = None
            render_font = text and (self.config.name or segment.type == 0 or segment.index > 0)
            if self._font_file is None and (render_font or (segment.order and self.config.order and sequence)):
                self._font_file = zlib.decompress(base64.b64decode(MAP_FONT), zlib.MAX_WBITS | 32)

            if render_font and self._font_file:
                text_font = ImageFont.truetype(
                    BytesIO(self._font_file),
                    int(size * 1.9) if segment.index or icon is None else int(size * 1.7),
                )

            if active and segment.order and self.config.order and sequence:
                order_font = ImageFont.truetype(BytesIO(cast(bytes, self._font_file)), int(size * 2.1))

            p = Point(segment.x, segment.y).to_img(dimensions, False)
            x = p.x + name_offset[0]
            y = p.y + name_offset[1]

            if neglected:
                offset = size * 1.5
                x_offset = 0
                y_offset = -offset
                if rotation == 90:
                    y_offset = 0
                    x_offset = offset
                elif rotation == 180:
                    y_offset = offset
                elif rotation == 270:
                    y_offset = 0
                    x_offset = -offset

                x = x + x_offset
                y = y + y_offset

            if self.config.name or self.config.icon:
                if segment.type or text_font or not self.config.name:
                    icon_size = size * (1.75 if self.icon_set == 1 else 1.3)
                    x0 = x - size
                    y0 = y - size
                    x1 = x + size
                    y1 = y + size

                    if text_font:
                        left, top, tw, th = draw.textbbox((0, 0), text or "", text_font)
                        ws = tw / 4

                        if segment.index or icon is None:
                            icon_size = size * 1.35
                            padding = icon_size / 2
                            text_offset = (icon_size / 2) + 2
                            icon_offset = 2
                            th = int(round(size * 2.3))
                        else:
                            icon_size = size * 1.15
                            padding = icon_size * 0.35
                            icon_offset = padding - 2
                            text_offset = icon_size / 2
                            th = int(round(size * 1.9))

                        if icon is None:
                            text_offset = 0
                            padding = -(icon_size / 4)

                        name_background = self.config.icon or (self.config.name_background and self.config.name)

                        stroke_width = dimensions.scale
                        if neglected:
                            stroke_color = self.color_scheme.neglected_segment
                            text_color: Any = (
                                stroke_color[0],
                                stroke_color[1],
                                stroke_color[2],
                                255,
                            )
                        elif not name_background:
                            if self.color_scheme.dark:
                                text_color = (240, 240, 240, 255)
                                stroke_color = (0, 0, 0, 200)
                            else:
                                text_color = (15, 15, 15, 255)
                                stroke_color = (255, 255, 255, 200)
                        elif self.config.icon or self.config.name:
                            stroke_width = 1
                            if self.config.name_background and self.icon_set != 2 and self.color_scheme.invert:
                                text_color = (240, 240, 240, 255)
                                stroke_color = (240, 240, 240, 200)
                            else:
                                text_color = self.color_scheme.text
                                stroke_color = self.color_scheme.text_stroke

                        th = th + int(stroke_width * 2)

                        if rotation == 90 or rotation == 270:
                            y0 = y0 - ws - padding
                            y1 = y1 + ws + padding

                            if rotation == 90:
                                ty = (y - ws + text_offset) * scale
                                tx = (x - (th / 4)) * scale
                                y = y - ws - icon_offset
                            else:
                                ty = (y - ws - text_offset) * scale
                                tx = (x - (th / 4)) * scale
                                y = y + ws + icon_offset
                        else:
                            x0 = x0 - ws - padding
                            x1 = x1 + ws + padding

                            if rotation == 0:
                                tx = (x - ws + text_offset) * scale
                                ty = (y - (th / 4)) * scale
                                x = x - ws - icon_offset
                            else:
                                tx = (x - ws - text_offset) * scale
                                ty = (y - (th / 4)) * scale
                                x = x + ws + icon_offset

                        if (
                            name_background
                            # and not self.config.name_background
                            and active
                            and not neglected
                        ):
                            draw.rounded_rectangle(
                                [
                                    int(x0 * scale),
                                    int(y0 * scale),
                                    int(x1 * scale),
                                    int(y1 * scale),
                                ],
                                fill=(
                                    self.color_scheme.segment[segment.color_index][1]
                                    if name_background and self.config.name_background and self.icon_set != 2
                                    else self.color_scheme.icon_background
                                ),
                                outline=self.color_scheme.badge_outline,
                                width=max(1, int(scale * 0.5)),
                                radius=(size * scale),
                            )

                        bold_stroke = max(1, int(dimensions.scale * 0.7))
                        icon_text = Image.new("RGBA", (int(tw), int(th)), (255, 255, 255, 0))
                        draw_text = ImageDraw.Draw(icon_text, "RGBA")

                        draw_text.text(
                            (0, 0),
                            text,
                            font=text_font,
                            fill=text_color,
                            stroke_width=bold_stroke,
                            stroke_fill=text_color,
                        )
                        icon_text = icon_text.rotate(-rotation, expand=1)
                        new_layer.paste(icon_text, (int(tx), int(ty)), icon_text)
                        if self.icon_set == 1:
                            icon_size *= 1.3
                    elif active:  # and not self.config.name_background
                        draw.ellipse(
                            [x0 * scale, y0 * scale, x1 * scale, y1 * scale],
                            fill=(
                                self.color_scheme.segment[segment.color_index][1]
                                if self.config.name_background and self.icon_set != 2
                                else self.color_scheme.icon_background
                            ),
                            outline=self.color_scheme.badge_outline,
                            width=max(1, int(scale * 0.5)),
                        )

                    if icon is not None:
                        s = icon_size * scale
                        if neglected:
                            icon = self._set_icon_color(
                                icon,
                                s,
                                text_color,
                            )
                        else:
                            icon = icon.resize((int(s), int(s)))
                        icon = icon.rotate(-rotation, expand=1)
                        new_layer.paste(
                            icon,
                            (
                                int(x * scale - (icon.size[0] / 2)),
                                int(y * scale - (icon.size[1] / 2)),
                            ),
                            icon,
                        )

            custom = (
                active
                and not neglected
                and cleanset
                and (
                    self.config.suction_level
                    or self.config.water_volume
                    or self.config.cleaning_times
                    or self.config.cleaning_mode
                )
            )
            if order_font or custom:
                offset = size * 2.7
                flip = -1 if flip_badge else 1
                x_offset = 0
                y_offset = -offset * flip

                if rotation == 90:
                    y_offset = 0
                    x_offset = offset * flip
                elif rotation == 180:
                    y_offset = offset * flip
                elif rotation == 270:
                    y_offset = 0
                    x_offset = -offset * flip

                x = p.x + x_offset
                y = p.y + y_offset
                cleaning_mode = (
                    None
                    if segment.cleaning_mode is None or segment.cleaning_mode < 0 or segment.cleaning_mode > 3
                    else segment.cleaning_mode
                )
                if custom:
                    s = scale * 2
                    arrow = (s + 2) * scale
                    if order_font:
                        icon_count = 5
                    else:
                        icon_count = 4

                    if not self.config.suction_level or segment.suction_level is None:
                        icon_count = icon_count - 1
                    if not self.config.water_volume or segment.water_volume is None:
                        icon_count = icon_count - 1
                    if not self.config.cleaning_times or segment.cleaning_times is None:
                        icon_count = icon_count - 1
                    if not self.config.cleaning_mode or cleaning_mode is None:
                        icon_count = icon_count - 1
                    if cleaning_mode == 0 or cleaning_mode == 1:
                        icon_count = icon_count - 1
                    if (
                        self.config.mopping_mode
                        and segment.custom_mopping_route is None
                        and segment.cleaning_route is not None
                        and cleaning_mode == 1
                    ):
                        icon_count = icon_count + 1
                else:
                    icon_count = 1

                if not icon and not self.config.icon:
                    arrow = 0

                radius = size
                arrow = int(round(radius * 0.6))
                margin = int(round(size * 0.3)) if icon_count > 1 else 0
                if custom:
                    radius = size - 2

                icon_w = ((radius * icon_count * 2) * scale) + (arrow * 2) + (margin * 2)
                icon_h = ((radius * 2) * scale) + (arrow * 2)
                icon = Image.new("RGBA", (icon_w, icon_h), (255, 255, 255, 0))
                icon_draw = ImageDraw.Draw(icon, "RGBA")

                if arrow and (segment.type != 0 or text_font):
                    xx = icon_w / 2
                    if flip_badge:
                        yy = 2
                        icon_draw.polygon(
                            [
                                (xx, yy),
                                (xx - arrow, yy + arrow),
                                (xx + arrow, yy + arrow),
                            ],
                            fill=self.color_scheme.settings_background,
                        )
                    else:
                        yy = icon_h - 2
                        icon_draw.polygon(
                            [
                                (xx, yy),
                                (xx - arrow, yy - arrow),
                                (xx + arrow, yy - arrow),
                            ],
                            fill=self.color_scheme.settings_background,
                        )

                icon_draw.rounded_rectangle(
                    [arrow, arrow, icon_w - arrow, icon_h - arrow],
                    fill=self.color_scheme.settings_background,
                    radius=((icon_h - (arrow * 2)) / 2),
                )

                padding = int(round((size * 0.3) + (size * 0.6)))
                r = icon_h - (padding * 2)
                ellipse_x1 = padding + margin
                ellipse_x2 = ellipse_x1 + r
                if order_font:
                    icon_draw.ellipse(
                        [ellipse_x1, padding, ellipse_x2, icon_h - padding],
                        fill=self.color_scheme.segment[segment.color_index][1],
                    )
                    text = str(segment.order)
                    left, top, tw, th = icon_draw.textbbox((0, 0), text, order_font)
                    icon_draw.text(
                        (
                            (icon_h - tw) / 2 + margin,
                            (icon_h - th - int(round(radius * 0.4))) / 2,
                        ),
                        text,
                        font=order_font,
                        fill=self.color_scheme.order,
                        stroke_width=1,
                        stroke_fill=self.color_scheme.text_stroke,
                    )

                    ellipse_x1 = ellipse_x2 + (margin * 2)
                    ellipse_x2 = ellipse_x1 + r

                if custom:
                    icon_size = size * 1.45

                    if self.config.cleaning_mode and cleaning_mode is not None:
                        if self.icon_set == 2:
                            s = icon_size * 1.2 * scale
                        else:
                            s = icon_size * 0.85 * scale

                        ico = self._set_icon_color(
                            self._cleaning_mode_icon[segment.cleaning_mode],
                            s,
                            self.color_scheme.segment[segment.color_index][1],
                        )

                        icon_draw.ellipse(
                            [ellipse_x1, padding, ellipse_x2, (icon_h - padding)],
                            fill=self.color_scheme.settings_icon_background,
                        )
                        icon.paste(
                            ico,
                            (
                                int(2 + ellipse_x1 + ((ellipse_x2 - ellipse_x1) / 2) - ico.size[0] / 2),
                                int((icon_h / 2) - ico.size[1] / 2),
                            ),
                            ico,
                        )

                        ellipse_x1 = ellipse_x2 + (margin * 2)
                        ellipse_x2 = ellipse_x1 + r

                    if self.config.suction_level and segment.suction_level is not None and cleaning_mode != 1:
                        if self.icon_set == 2:
                            s = icon_size * 1.2 * scale
                        else:
                            s = icon_size * 0.85 * scale

                        ico = self._set_icon_color(
                            self._suction_level_icon[segment.suction_level],
                            s,
                            self.color_scheme.segment[segment.color_index][1],
                        )
                        icon_draw.ellipse(
                            [ellipse_x1, padding, ellipse_x2, (icon_h - padding)],
                            fill=self.color_scheme.settings_icon_background,
                        )
                        icon.paste(
                            ico,
                            (
                                int(2 + ellipse_x1 + ((ellipse_x2 - ellipse_x1) / 2) - ico.size[0] / 2),
                                int((icon_h / 2) - ico.size[1] / 2),
                            ),
                            ico,
                        )

                        ellipse_x1 = ellipse_x2 + (margin * 2)
                        ellipse_x2 = ellipse_x1 + r

                    if self.config.water_volume and segment.water_volume is not None and cleaning_mode != 0:
                        water = segment.water_volume - 1
                        if self.config.mopping_mode and segment.custom_mopping_route is not None:
                            s = icon_size * 1.05 * scale
                            ico = self._custom_mopping_route_icon[(water * 3) + (segment.cleaning_route - 1)]
                        elif self.config.mopping_mode and segment.cleaning_route is not None:
                            if self.icon_set == 3:
                                s = icon_size * 0.95 * scale
                            else:
                                s = icon_size * scale
                            ico = self._mop_pad_humidity_icon[water]
                        else:
                            if self.icon_set == 3:
                                s = icon_size * 0.95 * scale
                            elif self.icon_set == 2:
                                s = icon_size * 1.2 * scale
                            ico = self._water_volume_icon[water]

                        ico = self._set_icon_color(
                            ico,
                            s,
                            self.color_scheme.segment[segment.color_index][1],
                        )

                        icon_draw.ellipse(
                            [ellipse_x1, padding, ellipse_x2, (icon_h - padding)],
                            fill=self.color_scheme.settings_icon_background,
                        )
                        icon.paste(
                            ico,
                            (
                                int(2 + ellipse_x1 + ((ellipse_x2 - ellipse_x1) / 2) - ico.size[0] / 2),
                                int((icon_h / 2) - ico.size[1] / 2),
                            ),
                            ico,
                        )

                        ellipse_x1 = ellipse_x2 + (margin * 2)
                        ellipse_x2 = ellipse_x1 + r

                    if (
                        self.config.mopping_mode
                        and segment.custom_mopping_route is None
                        and segment.cleaning_route is not None
                        and cleaning_mode == 1
                    ):
                        if self.icon_set == 3:
                            s = icon_size * 0.85 * scale
                        else:
                            s = icon_size * 0.7 * scale
                        ico = self._set_icon_color(
                            self._cleaning_route_icon[segment.cleaning_route - 1],
                            s,
                            self.color_scheme.segment[segment.color_index][1],
                        )
                        icon_draw.ellipse(
                            [ellipse_x1, padding, ellipse_x2, (icon_h - padding)],
                            fill=self.color_scheme.settings_icon_background,
                        )
                        icon.paste(
                            ico,
                            (
                                int(2 + ellipse_x1 + ((ellipse_x2 - ellipse_x1) / 2) - ico.size[0] / 2),
                                int((icon_h / 2) - ico.size[1] / 2),
                            ),
                            ico,
                        )

                        ellipse_x1 = ellipse_x2 + (margin * 2)
                        ellipse_x2 = ellipse_x1 + r

                    if self.config.cleaning_times and segment.cleaning_times is not None:
                        if self.icon_set == 3 or self.icon_set == 2:
                            s = icon_size * 0.95 * scale
                        else:
                            s = icon_size * 0.85 * scale

                        ico = self._set_icon_color(
                            self._cleaning_times_icon[segment.cleaning_times - 1],
                            s,
                            self.color_scheme.segment[segment.color_index][1],
                        )

                        icon_draw.ellipse(
                            [ellipse_x1, padding, ellipse_x2, (icon_h - padding)],
                            fill=self.color_scheme.settings_icon_background,
                        )
                        icon.paste(
                            ico,
                            (
                                int(2 + ellipse_x1 + ((ellipse_x2 - ellipse_x1) / 2) - ico.size[0] / 2),
                                int((icon_h / 2) - ico.size[1] / 2),
                            ),
                            ico,
                        )

                icon = icon.rotate(-rotation, expand=1)
                new_layer.paste(
                    icon,
                    (
                        int((x * scale) - ((icon.size[0]) / 2)),
                        int((y * scale) - ((icon.size[1]) / 2)),
                    ),
                    icon,
                )
        return new_layer

    def render_floor_material(
        self, image: Any, floor_material: Any, pixel_type: Any, color: Any, dimensions: Any, scale: Any
    ) -> Any:
        tile_w = 12
        floor_w = 4
        floor_h = 16

        height = dimensions.height * scale
        tiles = {}
        for k, v in floor_material.items():
            if v > 0 and v < 4:
                if v not in tiles:
                    tiles[v] = [k]
                else:
                    tiles[v].append(k)

        if tiles:
            color_map = {}
            for floor_type, tile in tiles.items():
                if tile:
                    if floor_type == 1:
                        w = math.floor(2 * dimensions.width / floor_h)
                        h = math.floor(dimensions.height / floor_w)
                        y_start = 1
                        x_start = 0
                        x_multiplier = floor_h / 2
                        y_multiplier: float = floor_w
                    elif floor_type == 2:
                        w = math.floor(dimensions.width / floor_w)
                        h = math.floor(2 * dimensions.height / floor_h)
                        y_start = 0
                        x_start = 1
                        x_multiplier = floor_w
                        y_multiplier = floor_h / 2
                    else:
                        w = math.floor(dimensions.width / tile_w)
                        h = math.floor(dimensions.height / tile_w)
                        y_start = 0
                        x_start = 0
                        x_multiplier = tile_w
                        y_multiplier = tile_w

                    for x in range(1, w + 1):
                        for y in range(y_start, dimensions.height):
                            xx = int(x * x_multiplier)
                            if xx < dimensions.width and (
                                floor_type != 1
                                or (
                                    (math.floor((y - 1) / floor_w) % 2 == 0 and x % 2 == 0)
                                    or (math.floor((y - 1) / floor_w) % 2 == 1 and x % 2 == 1)
                                )
                            ):
                                val = int(pixel_type[xx, y])
                                if val > 0 and val < 63 and val in tile:
                                    x_index = (xx * scale) + 1
                                    y_index = (height - 1) - (y * scale) - 1

                                    if val not in color_map:
                                        cc = self._alpha_composite(color, image[y_index, x_index])
                                        color_map[val] = cc
                                    else:
                                        cc = color_map[val]
                                    image[y_index, x_index] = cc
                                    y_index = y_index + 1
                                    image[y_index, x_index] = cc

                    for x in range(x_start, dimensions.width):
                        for y in range(1, h + 1):
                            yy = int(y * y_multiplier)
                            if yy < dimensions.height and (
                                floor_type != 2
                                or (
                                    (math.floor((x - 1) / floor_w) % 2 == 0 and y % 2 == 0)
                                    or (math.floor((x - 1) / floor_w) % 2 == 1 and y % 2 == 1)
                                )
                            ):
                                val = int(pixel_type[x, yy])
                                if val > 0 and val < 63 and val in tile:
                                    x_index = x * scale
                                    y_index = (height - 1) - ((yy * scale) + 1)
                                    if val not in color_map:
                                        cc = self._alpha_composite(color, image[y_index, x_index])
                                        color_map[val] = cc
                                    else:
                                        cc = color_map[val]
                                    image[y_index, x_index] = cc
                                    x_index = x_index + 1
                                    image[y_index, x_index] = cc
            return image
        return None

    def render_carpets(
        self,
        image: Any,
        pixel_type: Any,
        carpets: Any,
        ignored_carpets: Any,
        detected_carpets: Any,
        carpet_pixels: Any,
        segments: Any,
        color: Any,
        detected_color: Any,
        dimensions: Any,
        scale: Any,
    ) -> Any:
        carpet_data = {}
        left = dimensions.left
        top = dimensions.top
        if left % dimensions.grid_size != 0 or top % dimensions.grid_size != 0:
            left = left + (dimensions.grid_size / 2)
            top = top + (dimensions.grid_size / 2)

        if detected_carpets:
            optimimized_carpet_pixels = None
            for carpet in detected_carpets:
                x0, y0, x1, y1 = self._get_carpet_coords(carpet, dimensions)
                for x in range(max(0, x0), min(x1, dimensions.width - 1)):
                    for y in range(max(y0, 0), min(y1, dimensions.height - 1)):
                        if not self._check_carpet(x, y, carpet, dimensions, int(pixel_type[x, y])):
                            continue

                        if carpet.polygon and len(carpet.polygon) > 100 and carpet_pixels:
                            if optimimized_carpet_pixels is None:
                                optimimized_carpet_pixels = self._optimize_carpet_pixels(
                                    carpet_pixels, dimensions, pixel_type
                                )
                            if (x, y) not in optimimized_carpet_pixels:
                                continue
                        carpet_data[(x, y)] = 1
        elif carpet_pixels:
            carpet_data = self._optimize_carpet_pixels(carpet_pixels, dimensions, pixel_type)

        if segments:
            for k in segments:
                segment = segments[k]
                if segment.floor_material and segment.floor_material > 4 and segment.floor_material < 8:
                    x0 = int((segment.x0 - dimensions.left) / dimensions.grid_size)
                    y0 = int((segment.y0 - dimensions.top) / dimensions.grid_size)
                    x1 = int((segment.x1 - dimensions.left) / dimensions.grid_size)
                    y1 = int((segment.y1 - dimensions.top) / dimensions.grid_size)
                    for x in range(x0 - 1, x1 + 1):
                        for y in range(y0 - 1, y1 + 1):
                            if int(pixel_type[x, y]) == int(k):
                                carpet_data[(x, y)] = 1

        if ignored_carpets:
            for carpet in ignored_carpets:
                x0, y0, x1, y1 = self._get_carpet_coords(carpet, dimensions)
                for x in range(x0, x1):
                    for y in range(y0, y1):
                        if self._check_carpet(x, y, carpet, dimensions):
                            carpet_data[(x, y)] = 0

        if carpets:
            for carpet in carpets:
                x0, y0, x1, y1 = self._get_carpet_coords(carpet, dimensions)
                for x in range(x0, x1):
                    for y in range(y0, y1):
                        if self._check_carpet(x, y, carpet, dimensions):
                            carpet_data[(x, y)] = 2

        color_map = {}
        for coord, px_type in carpet_data.items():
            if px_type != 0:
                x_index = coord[0] * scale
                y_index = (dimensions.height - coord[1] - 1) * scale
                render_color = detected_color if px_type == 1 else color
                for _i in range(2):
                    if (
                        y_index >= 0
                        and y_index < dimensions.height * scale
                        and x_index >= 0
                        and x_index < dimensions.width * scale
                    ):
                        val = f"{image[y_index, x_index]}{px_type}"
                        if val not in color_map:
                            cc = self._alpha_composite(render_color, image[y_index, x_index])
                            color_map[val] = cc
                        else:
                            cc = color_map[val]
                        image[y_index, x_index] = cc
                        x_index = x_index + 1
                        y_index = y_index + 1

        return image
