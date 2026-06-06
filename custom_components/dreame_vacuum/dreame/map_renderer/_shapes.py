"""Shape-drawing mixin for :class:`DreameVacuumMapRenderer`.

These methods are self-contained 2D rendering helpers: they take
geometry + styling + a layer size and return a fresh PIL Image. They
don't touch renderer instance state (``self._layers``, caches, etc.),
which makes them safe to live in a dedicated module.

The mixin is stitched back into the renderer in ``_core.py`` so call
sites keep working without changes.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

from ..vacuum_types import Area, Point


class _ShapesMixin:
    """Draws polygons, walls, thresholds, curtains, ramps and points."""

    def render_areas(self, areas, color, fill, layer_size, dimensions, width, scale):
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        for area in areas:
            p = area.to_img(dimensions)
            draw.polygon(
                [
                    p.x0 * scale,
                    p.y0 * scale,
                    p.x1 * scale,
                    p.y1 * scale,
                    p.x2 * scale,
                    p.y2 * scale,
                    p.x3 * scale,
                    p.y3 * scale,
                ],
                fill,
                color,
                width=(width * scale),
            )
        return new_layer

    def render_points(self, points, color, fill, layer_size, dimensions, width, scale):
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        size = 15 * dimensions.grid_size
        for point in points:
            area = Area(
                point.x - size,
                point.y - size,
                point.x + size,
                point.y - size,
                point.x + size,
                point.y + size,
                point.x - size,
                point.y + size,
            )

            p = area.to_img(dimensions)
            coords = [
                p.x0 * scale,
                p.y0 * scale,
                p.x1 * scale,
                p.y1 * scale,
                p.x2 * scale,
                p.y2 * scale,
                p.x3 * scale,
                p.y3 * scale,
            ]
            draw.polygon(coords, fill, color, width=(width * scale))
        return new_layer

    def render_walls(self, walls, color, layer_size, dimensions, width, scale):
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        for wall in walls:
            p = wall.to_img(dimensions)
            draw.line(
                [p.x0 * scale, p.y0 * scale, p.x1 * scale, p.y1 * scale],
                color,
                width=(width * scale),
            )
        return new_layer

    def render_thresholds(self, thresholds, color, fill, layer_size, dimensions, width, scale):
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        for wall in thresholds:
            p = wall.to_img(dimensions)

            thickness = width * 8
            w = -(p.y1 - p.y0)
            h = p.x1 - p.x0
            t = math.sqrt(w * w + h * h)
            x = w / t * thickness / 2
            y = h / t * thickness / 2

            draw.polygon(
                [
                    (p.x0 - x) * scale,
                    (p.y0 - y) * scale,
                    (p.x1 - x) * scale,
                    (p.y1 - y) * scale,
                    (p.x1 + x) * scale,
                    (p.y1 + y) * scale,
                    (p.x0 + x) * scale,
                    (p.y0 + y) * scale,
                ],
                fill,
                color,
                width=(width * scale),
            )

            thickness = thickness - width
            x = w / t * thickness / 2
            y = h / t * thickness / 2

            coords = [
                (p.x0 - x) * scale,
                (p.y0 - y) * scale,
                (p.x1 - x) * scale,
                (p.y1 - y) * scale,
                (p.x1 + x) * scale,
                (p.y1 + y) * scale,
                (p.x0 + x) * scale,
                (p.y0 + y) * scale,
            ]

            bp = self._coords_on_line(coords[0], coords[1], coords[2], coords[3], thickness * scale)
            tp = self._coords_on_line(coords[6], coords[7], coords[4], coords[5], thickness * scale)

            for i in range(len(tp) - 1):
                draw.line([tp[i][0], tp[i][1], bp[i + 1][0], bp[i + 1][1]], color, width=(width * scale), joint="curve")
        return new_layer

    def render_curtains(self, curtains, color, layer_size, dimensions, width, scale):
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        for wall in curtains:
            p = wall.to_img(dimensions)

            w = -(p.y1 - p.y0)
            h = p.x1 - p.x0
            t = math.sqrt(w * w + h * h)
            x = w / t * 5
            y = h / t * 5

            coords = [
                (p.x0 - x) * scale,
                (p.y0 - y) * scale,
                (p.x1 - x) * scale,
                (p.y1 - y) * scale,
                (p.x1 + x) * scale,
                (p.y1 + y) * scale,
                (p.x0 + x) * scale,
                (p.y0 + y) * scale,
            ]

            t = int(
                math.floor(
                    math.sqrt((wall.x0 - wall.x1) * (wall.x0 - wall.x1) + (wall.y0 - wall.y1) * (wall.y0 - wall.y1))
                    / 150
                )
            )
            tp = self._coords_on_line(coords[6], coords[7], coords[4], coords[5], 0, t + 1)
            bp = self._coords_on_line(coords[0], coords[1], coords[2], coords[3], 0, t + 1)

            path = []
            for i in range(0, len(tp) - 1, 2):
                path.extend([tp[i][0], tp[i][1], bp[i + 1][0], bp[i + 1][1]])
            draw.line(path, color, width=(width * scale), joint="curve")

        return new_layer

    def render_ramps(self, ramps, color, fill, layer_size, dimensions, width, scale, rotation):
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        for area in ramps:
            p = area.to_img(dimensions)
            draw.polygon(
                [
                    p.x0 * scale,
                    p.y0 * scale,
                    p.x1 * scale,
                    p.y1 * scale,
                    p.x2 * scale,
                    p.y2 * scale,
                    p.x3 * scale,
                    p.y3 * scale,
                ],
                fill,
                color,
                width=(width * scale),
            )

            p0 = Point(area.x0, area.y0).to_img(dimensions)
            p1 = Point(area.x2, area.y2).to_img(dimensions)

            x_coords = sorted([p0.x, p1.x])
            y_coords = sorted([p0.y, p1.y])
            min_x = x_coords[0]
            min_y = y_coords[0]
            max_x = x_coords[1]
            max_y = y_coords[1]
            w = max_x - min_x
            h = max_y - min_y

            m = min(w, h)
            s = width
            size = 8.165 * dimensions.scale

            if m < size:
                s /= 2
                size = m * 0.6

            sx = int(w / size)
            sy = int(h / size)
            rw = size * 0.6
            rh = rw / 2
            xx = (w - sx * rw) / (sx + 1)
            yy = (h - sy * rh) / (sy + 1)

            arrow_image = Image.new("RGBA", (int(w * scale), int(h * scale)), (255, 255, 255, 0))
            arrow_draw = ImageDraw.Draw(arrow_image, "RGBA")

            for k in range(sx):
                for j in range(sy):
                    x = xx * (k + 1) + rw * k
                    y = h - yy * (j + 1) - rh * j
                    arrow_draw.line(
                        [x * scale, y * scale, (x + rh) * scale, (y - rh) * scale, (x + (rh * 2)) * scale, y * scale],
                        width=int(s * scale),
                        fill=color,
                        joint="curve",
                    )

            unrotated = arrow_image
            arrow_image = arrow_image.rotate(area.angle, expand=1)
            self._close_image(unrotated)
            new_layer.paste(
                arrow_image,
                (
                    int(((min_x + (w / 2)) * scale) - (arrow_image.size[0] / 2)),
                    int(((min_y + (h / 2)) * scale) - (arrow_image.size[1] / 2)),
                ),
                arrow_image,
            )
            self._close_image(arrow_image)

        return new_layer
