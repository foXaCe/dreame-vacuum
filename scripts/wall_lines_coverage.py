#!/usr/bin/env python3
"""Dev harness: how much of the grid WALL pixels does walls_info actually cover?

Answers the question behind the "replace pixel walls with wall_lines
vectors" idea (contract backlog C): for every grid cell the renderer paints
as ``MapPixelType.WALL``/``OBSTACLE_WALL``, is there a decoded
``wall_lines``/``door_lines`` segment sitting on top of it? If not, blindly
suppressing the pixel paint there would delete a wall nothing else draws.

Method: decode the committed r95285-saved fixture, take every WALL-type grid
cell's centre in real-world mm, and find its distance to the nearest
wall_lines/door_lines segment (point-to-segment, clamped to the segment's
extent). A cell is "covered" when that distance is within one grid cell
(``dimensions.grid_size``) -- i.e. the vector traces essentially the same
grid line. See ``docs/dev/wall-lines-render-spike.md`` for the numbers this
produced and the resulting decision (wall_lines pixel-replacement: BLOCKED;
door_lines: rendered as an independent additive marker).

Usage::

    python scripts/wall_lines_coverage.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
from custom_components.dreame_vacuum.dreame.vacuum_types import MapPixelType, Wall

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "maps" / "r95285-saved.b64"


def _point_segment_distance(px: np.ndarray, py: np.ndarray, seg: Wall) -> np.ndarray:
    """Vectorized point-to-segment distance, clamped to the segment's extent."""
    dx, dy = seg.x1 - seg.x0, seg.y1 - seg.y0
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return np.hypot(px - seg.x0, py - seg.y0)
    t = np.clip(((px - seg.x0) * dx + (py - seg.y0) * dy) / length_sq, 0, 1)
    proj_x = seg.x0 + t * dx
    proj_y = seg.y0 + t * dy
    return np.hypot(px - proj_x, py - proj_y)


def analyze() -> dict[str, object]:
    raw_map = FIXTURE.read_text(encoding="utf-8").strip()
    map_data, _saved = DreameVacuumMapDecoder.decode_map(raw_map, False)
    if map_data is None or map_data.dimensions is None:
        raise RuntimeError(f"Fixture {FIXTURE} failed to decode")

    dims = map_data.dimensions
    grid_size = dims.grid_size
    pixel_type = map_data.pixel_type

    wall_mask = (pixel_type == MapPixelType.WALL.value) | (pixel_type == MapPixelType.OBSTACLE_WALL.value)
    wall_cells = np.argwhere(wall_mask)
    world_x = dims.left + (wall_cells[:, 0] + 0.5) * grid_size
    world_y = dims.top + (wall_cells[:, 1] + 0.5) * grid_size

    segments = list(map_data.wall_lines or []) + list(map_data.door_lines or [])
    min_dist = np.full(len(world_x), np.inf)
    for seg in segments:
        min_dist = np.minimum(min_dist, _point_segment_distance(world_x, world_y, seg))

    covered = min_dist <= grid_size
    diagonal_segments = [s for s in segments if s.x0 != s.x1 and s.y0 != s.y1]
    door_lengths = [float(np.hypot(w.x1 - w.x0, w.y1 - w.y0)) for w in (map_data.door_lines or [])]

    return {
        "grid_size_mm": grid_size,
        "wall_cell_count": int(len(wall_cells)),
        "segment_count": len(segments),
        "diagonal_segment_count": len(diagonal_segments),
        "covered_count": int(covered.sum()),
        "covered_pct": 100.0 * covered.mean() if len(covered) else 0.0,
        "door_segment_count": len(map_data.door_lines or []),
        "door_length_min_mm": min(door_lengths) if door_lengths else None,
        "door_length_max_mm": max(door_lengths) if door_lengths else None,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    stats = analyze()
    print(f"Fixture: {FIXTURE.name}")
    print(f"Grid size: {stats['grid_size_mm']} mm")
    print(f"WALL-type grid cells: {stats['wall_cell_count']}")
    print(f"wall_lines + door_lines segments: {stats['segment_count']} (diagonal: {stats['diagonal_segment_count']})")
    print(
        f"Covered (within 1 grid cell of a segment): "
        f"{stats['covered_count']}/{stats['wall_cell_count']} = {stats['covered_pct']:.1f}%"
    )
    print(
        f"door_lines: {stats['door_segment_count']} segments, "
        f"length {stats['door_length_min_mm']:.0f}-{stats['door_length_max_mm']:.0f} mm"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
