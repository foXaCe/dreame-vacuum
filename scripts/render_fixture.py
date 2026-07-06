#!/usr/bin/env python3
"""Dev harness: render a committed map fixture through the production renderer.

Loads ``tests/fixtures/maps/r95285-saved.b64`` (a real, redacted saved map
from an Aqua10 Ultra, 331x390 grid, 10 rooms, with ``walls_info`` decoded
into ``MapData.wall_lines``/``door_lines``), decodes it with
``DreameVacuumMapDecoder.decode_map`` (the same entry point production code
uses), and renders it with ``DreameVacuumMapRenderer.render_map`` (the same
call ``camera.py`` makes) in both the light and dark built-in colour
schemes, at the production-default render scale (``map_scale=2``,
``vector_rooms=True``).

Usage::

    python scripts/render_fixture.py <output-dir>

Writes to ``<output-dir>``:

- ``light.png`` / ``dark.png`` — full render in each theme.
- ``light-zoom.png`` — a x3 crop of ``light.png`` centered on a wall corner
  that has a nearby door, for close inspection of wall/door line quality.

This is a throwaway dev script (not test code): it has no assertions, it
just produces PNGs for a human (or another agent) to eyeball. Keep it
in sync with ``camera.py``'s renderer construction if that call shape
changes.
"""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
import sys

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
from custom_components.dreame_vacuum.dreame.map_renderer import DreameVacuumMapRenderer
from custom_components.dreame_vacuum.dreame.vacuum_types import Point

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "maps" / "r95285-saved.b64"

# Production defaults (camera.py: DEFAULT_MAP_SCALE=2, CONF_VECTOR_ROOMS default True).
RENDER_SCALE = 2
VECTOR_ROOMS = True

ZOOM_FACTOR = 3
ZOOM_HALF_SIZE = 90  # half-width in final-image px of the zoom crop, before x3 upscale


def load_map_data():
    raw_map = FIXTURE.read_text(encoding="utf-8").strip()
    map_data, _saved_map_data = DreameVacuumMapDecoder.decode_map(raw_map, False)
    if map_data is None:
        raise RuntimeError(f"Fixture {FIXTURE} failed to decode")
    return map_data


def render(map_data, color_scheme: str) -> tuple[bytes, object]:
    """Render map_data with the given colour scheme, production-shaped renderer.

    Returns the PNG bytes and the (mutated) map_data.dimensions, so callers
    can convert wall/door mm coordinates to final-image pixel coordinates
    with ``Point(...).to_img(map_data.dimensions)`` after the render.
    """
    renderer = DreameVacuumMapRenderer(
        color_scheme,
        None,  # icon_set: default
        None,  # hidden_map_objects: none hidden
        0,  # robot_type
        False,  # low_resolution
        False,  # square
        True,  # cache
        None,  # language
        VECTOR_ROOMS,
        render_scale=RENDER_SCALE,
    )
    png_bytes = renderer.render_map(map_data, robot_status=0, station_status=0, info_text=False)
    return png_bytes, map_data.dimensions


def _wall_corner_with_door(map_data, dimensions, image_size: tuple[int, int]) -> tuple[float, float] | None:
    """Find a wall-segment endpoint that exactly meets a door segment endpoint.

    Used to centre the zoom crop on an interesting spot (a corner where a
    wall meets a doorway) rather than an arbitrary point. Among all such
    coincident corners, picks the one furthest from every image edge so the
    crop lands on real content instead of clipping outside the render.
    """
    if not map_data.wall_lines or not map_data.door_lines:
        return None

    def endpoints(walls):
        for w in walls:
            yield (w.x0, w.y0)
            yield (w.x1, w.y1)

    door_points = set(endpoints(map_data.door_lines))
    wall_points = set(endpoints(map_data.wall_lines))
    coincident = wall_points & door_points
    if not coincident:
        return None

    width, height = image_size
    best = None
    best_edge_dist = -1.0
    for mx, my in coincident:
        p = Point(mx, my).to_img(dimensions)
        edge_dist = min(p.x, p.y, width - p.x, height - p.y)
        if edge_dist > best_edge_dist:
            best_edge_dist = edge_dist
            best = (mx, my)
    return best


def make_zoom_crop(png_bytes: bytes, dimensions, map_data) -> Image.Image:
    image = Image.open(BytesIO(png_bytes)).convert("RGBA")

    corner = _wall_corner_with_door(map_data, dimensions, image.size)
    if corner is None:
        # Fallback: centre of the image.
        cx, cy = image.width / 2, image.height / 2
    else:
        p = Point(corner[0], corner[1]).to_img(dimensions)
        cx, cy = p.x, p.y

    left = max(0, int(cx - ZOOM_HALF_SIZE))
    top = max(0, int(cy - ZOOM_HALF_SIZE))
    right = min(image.width, int(cx + ZOOM_HALF_SIZE))
    bottom = min(image.height, int(cy + ZOOM_HALF_SIZE))

    crop = image.crop((left, top, right, bottom))
    return crop.resize((crop.width * ZOOM_FACTOR, crop.height * ZOOM_FACTOR), Image.Resampling.NEAREST)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="Directory to write light.png/dark.png/light-zoom.png into")
    args = parser.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    schemes = {"light": "Dreame Light", "dark": "Dreame Dark"}
    rendered_dims = {}
    map_datas = {}

    for name, scheme in schemes.items():
        map_data = load_map_data()  # fresh decode per render: render_map mutates dimensions in place
        png_bytes, dimensions = render(map_data, scheme)
        out_path = args.output_dir / f"{name}.png"
        out_path.write_bytes(png_bytes)
        print(f"Wrote {out_path} ({len(png_bytes)} bytes)")
        rendered_dims[name] = dimensions
        map_datas[name] = map_data

    # Zoom crop on the light render, centered on a wall/door corner.
    light_bytes = (args.output_dir / "light.png").read_bytes()
    zoomed = make_zoom_crop(light_bytes, rendered_dims["light"], map_datas["light"])
    zoom_path = args.output_dir / "light-zoom.png"
    zoomed.save(zoom_path)
    print(f"Wrote {zoom_path} ({zoomed.width}x{zoomed.height})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
