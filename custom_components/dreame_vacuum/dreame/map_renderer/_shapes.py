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

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..vacuum_types import Area, MapImageDimensions, Point, Wall
from ._base import _MapRendererState

# Extends the same "supersample, then reduce" idea already used for the base
# floor/room raster (_smooth_upscale, bicubic) and the path layer (drawn at
# object_scale then BOX-thumbnailed) to the remaining vector object layers
# that still show visible stair-stepping on diagonal/curved edges: no-go/
# no-mop zone outlines, virtual walls, thresholds and door markers
# (render_areas, render_walls, render_doors, render_thresholds). PIL's
# ImageDraw has no native anti-aliasing, and these shapes are drawn directly
# at the object-layer resolution (already a 2x supersample of the final
# image -- see _LayersMixin.render_objects/_compose_object_layers), so a
# small Gaussian blur right before returning softens the jagged edges left
# over from that supersample without needing a second, more expensive
# full-canvas supersample-and-resize pass. The radius scales with ``scale``
# (the object-layer multiplier) so the blur amount at final resolution
# stays consistent regardless of how much supersampling already happened
# upstream. Deliberately NOT applied to the segment_map raster (never
# anti-aliased, contract) or to furniture (pastes pre-rendered icon
# bitmaps, a different mechanism -- rotation there already gets PIL's
# resampling-filter AA).
_AA_BLUR_MIN_RADIUS = 0.45
_AA_BLUR_SCALE_FACTOR = 0.25


def _blur_premultiplied(img: Image.Image, radius: float) -> Image.Image:
    """Alpha-aware Gaussian blur: premultiply, blur, un-premultiply.

    Blurring RGB and alpha independently (a plain ``Image.filter`` call)
    bleeds whatever RGB value sits behind a fully-transparent pixel into the
    blurred result -- these layers are always initialized to opaque white
    with alpha=0 (``(255, 255, 255, 0)``), so a naive blur would fringe every
    edge with a faint white halo, in both the light and dark themes.
    Premultiplying RGB by alpha before the blur, and un-premultiplying by the
    *blurred* alpha afterwards, keeps the softened edge a pure fade of the
    shape's own colour instead.
    """
    arr = np.asarray(img, dtype=np.float32)
    alpha = arr[..., 3:4] / 255.0
    premultiplied = arr.copy()
    premultiplied[..., :3] *= alpha
    blurred = np.asarray(
        Image.fromarray(premultiplied.astype(np.uint8), "RGBA").filter(ImageFilter.GaussianBlur(radius=radius)),
        dtype=np.float32,
    )
    out_alpha = blurred[..., 3:4]
    safe_alpha = np.where(out_alpha > 0, out_alpha, 1.0)
    out_rgb = np.clip(blurred[..., :3] / (safe_alpha / 255.0), 0, 255)
    out = np.concatenate([out_rgb, out_alpha], axis=-1).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _antialias_region(layer: Image.Image, scale: int, bbox: tuple[float, float, float, float]) -> Image.Image:
    """Blur only ``bbox`` (padded for the blur radius) of ``layer`` in place.

    These vector shapes (a couple of no-go zones, a handful of wall/
    threshold segments) are usually tiny relative to the full object-layer
    canvas, which is already a 2x supersample of the whole map image --
    blurring the *entire* layer costs O(map area) per shape layer regardless
    of how small the shape itself is. Restricting the blur to the drawn
    content's own bounding box keeps the cost proportional to the shape,
    not the map.
    """
    radius = max(_AA_BLUR_MIN_RADIUS, scale * _AA_BLUR_SCALE_FACTOR)
    pad = int(math.ceil(radius * 3)) + 2
    min_x, min_y, max_x, max_y = bbox
    left = max(0, int(math.floor(min_x)) - pad)
    top = max(0, int(math.floor(min_y)) - pad)
    right = min(layer.width, int(math.ceil(max_x)) + pad)
    bottom = min(layer.height, int(math.ceil(max_y)) + pad)
    if right <= left or bottom <= top:
        return layer
    crop = layer.crop((left, top, right, bottom))
    layer.paste(_blur_premultiplied(crop, radius), (left, top))
    return layer


class _BBoxTracker:
    """Accumulates a bounding box across draw calls (in already-scaled px)."""

    def __init__(self) -> None:
        self.min_x = math.inf
        self.min_y = math.inf
        self.max_x = -math.inf
        self.max_y = -math.inf

    def add(self, *coords: float) -> None:
        xs = coords[0::2]
        ys = coords[1::2]
        self.min_x = min(self.min_x, *xs)
        self.max_x = max(self.max_x, *xs)
        self.min_y = min(self.min_y, *ys)
        self.max_y = max(self.max_y, *ys)

    def expand(self, margin: float) -> tuple[float, float, float, float]:
        return (self.min_x - margin, self.min_y - margin, self.max_x + margin, self.max_y + margin)


class _ShapesMixin(_MapRendererState):
    """Draws polygons, walls, thresholds, curtains, ramps and points."""

    def render_areas(
        self,
        areas: list[Area],
        color: tuple[int, ...],
        fill: tuple[int, ...] | None,
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        width: int,
        scale: int,
    ) -> Image.Image:
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        for area in areas:
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
            # Antialias per-item (not once over the whole layer/all items):
            # a map can carry many no-go/no-mop zones scattered across the
            # whole canvas, and blurring the full layer costs O(map area)
            # regardless of how small each zone actually is.
            bbox = _BBoxTracker()
            bbox.add(*coords)
            _antialias_region(new_layer, scale, bbox.expand(width * scale))
        return new_layer

    def render_points(
        self,
        points: list[Point],
        color: tuple[int, ...],
        fill: tuple[int, ...] | None,
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        width: int,
        scale: int,
    ) -> Image.Image:
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

    def render_walls(
        self,
        walls: list[Wall],
        color: tuple[int, ...],
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        width: int,
        scale: int,
    ) -> Image.Image:
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        for wall in walls:
            p = wall.to_img(dimensions)
            coords = [p.x0 * scale, p.y0 * scale, p.x1 * scale, p.y1 * scale]
            draw.line(coords, color, width=(width * scale))
            # Per-item antialiasing: see render_areas.
            bbox = _BBoxTracker()
            bbox.add(*coords)
            _antialias_region(new_layer, scale, bbox.expand(width * scale))
        return new_layer

    def render_doors(
        self,
        doors: list[Wall],
        color: tuple[int, ...],
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        width: int,
        scale: int,
    ) -> Image.Image:
        """Draw walls_info door segments as a subtle dashed marker.

        Deliberately dashed rather than solid: a solid, wall-coloured trace
        redrawing the same segment the pixel wall already occupies is
        exactly the "additive" render that was reverted before (redundant
        gray frames -- see docs/dev/wall-lines-render-spike.md). A dashed
        line in a distinct, sober tint can never read as a duplicated wall
        outline.
        """
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        dash_length = 6 * scale
        gap_length = 5 * scale
        period = dash_length + gap_length
        for wall in doors:
            p = wall.to_img(dimensions)
            x0, y0 = p.x0 * scale, p.y0 * scale
            x1, y1 = p.x1 * scale, p.y1 * scale
            length = math.hypot(x1 - x0, y1 - y0)
            if length <= 0:
                continue
            ux, uy = (x1 - x0) / length, (y1 - y0) / length
            position = 0.0
            while position < length:
                dash_end = min(position + dash_length, length)
                draw.line(
                    [
                        x0 + ux * position,
                        y0 + uy * position,
                        x0 + ux * dash_end,
                        y0 + uy * dash_end,
                    ],
                    color,
                    width=(width * scale),
                )
                position += period
            # Per-door antialiasing (see render_areas): walls_info can carry
            # many door segments spread across the whole building, so a
            # single shared bounding box would degenerate to ~the full map.
            bbox = _BBoxTracker()
            bbox.add(x0, y0, x1, y1)
            _antialias_region(new_layer, scale, bbox.expand(width * scale))
        return new_layer

    def render_thresholds(
        self,
        thresholds: list[Wall],
        color: tuple[int, ...],
        fill: tuple[int, ...] | None,
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        width: int,
        scale: int,
    ) -> Image.Image:
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

            outer_coords = [
                (p.x0 - x) * scale,
                (p.y0 - y) * scale,
                (p.x1 - x) * scale,
                (p.y1 - y) * scale,
                (p.x1 + x) * scale,
                (p.y1 + y) * scale,
                (p.x0 + x) * scale,
                (p.y0 + y) * scale,
            ]
            draw.polygon(outer_coords, fill, color, width=(width * scale))
            # The outer polygon (thickness = width*8) is the widest extent of
            # this shape -- the inner zigzag drawn below stays within it.
            bbox = _BBoxTracker()
            bbox.add(*outer_coords)

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

            # Per-threshold antialiasing: see render_areas.
            _antialias_region(new_layer, scale, bbox.expand(width * scale))
        return new_layer

    def render_curtains(
        self,
        curtains: list[Wall],
        color: tuple[int, ...],
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        width: int,
        scale: int,
    ) -> Image.Image:
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

    def render_ramps(
        self,
        ramps: list[Area],
        color: tuple[int, ...],
        fill: tuple[int, ...] | None,
        layer_size: tuple[int, int],
        dimensions: MapImageDimensions,
        width: int,
        scale: int,
        rotation: int,
    ) -> Image.Image:
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
            s: float = width
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
            arrow_image = arrow_image.rotate(area.angle or 0, expand=1)
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
