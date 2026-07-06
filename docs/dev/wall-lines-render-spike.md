# Vector wall_lines rendering — feasibility spike

## Status

Investigation + partial delivery. Sizes contract backlog C ("murs vectoriels —
décodés, rendu différé") on the real reference fixture (r95285-saved, an
Aqua10 Ultra saved map: 331x390 grid, 10 rooms, `walls_info` present).

## Verdict (up front)

**Replacing the pixel wall contour with `wall_lines` vectors is BLOCKED.**
Only ~44% of the grid's `WALL`-type cells sit near a `wall_lines`/`door_lines`
segment on the reference fixture — the rest is a LIDAR-scanned free-form
perimeter `walls_info` never describes at all. Suppressing pixel-wall
painting wherever a vector *is* available would still delete over half the
walls actually on the map. Worse, the covered half buys nothing visually:
every decoded segment is axis-aligned, and an axis-aligned 1-grid-cell-wide
band already renders pixel-perfect under the existing block-repeat
rasterizer — there is no aliasing to fix there. Forcing a replace would
either lose walls or reproduce the exact bug that was reverted before
(redundant traces on top of pixel walls that are already there).

**Shipped instead:** `door_lines` (`walls_info` `type 1` segments) render as
a subtle dashed marker (`MapRendererLayer.DOOR`), independently of the
wall-replacement question. Doors carry information the pixel grid cannot
express on its own (most door segments sample as gaps/room-floor in the
grid, not `WALL` cells), so drawing them is purely additive — it never
touches or duplicates an existing wall pixel, so it can't regress into the
reverted bug.

## 1. Method

`scripts/wall_lines_coverage.py` decodes the committed
`tests/fixtures/maps/r95285-saved.b64` fixture and, for every grid cell the
renderer paints as `MapPixelType.WALL`/`OBSTACLE_WALL`, computes the distance
(mm, point-to-segment, clamped to the segment's extent) to the nearest
`wall_lines`/`door_lines` segment. A cell counts as "covered" when that
distance is within one grid cell (50 mm here) — i.e. the vector traces
essentially the same grid line the pixel occupies.

```
$ python scripts/wall_lines_coverage.py
Fixture: r95285-saved.b64
Grid size: 50 mm
WALL-type grid cells: 2023
wall_lines + door_lines segments: 86 (diagonal: 0)
Covered (within 1 grid cell of a segment): 900/2023 = 44.5%
door_lines: 20 segments, length 50-7800 mm
```

A visual cross-check (colour every `WALL` cell green if covered, red if not,
overlaid on the map silhouette) makes the pattern obvious: the entire
irregular, jagged left portion of the map (the free-form exterior perimeter)
is solid red — walls_info has zero representation there. The straight
interior partition walls on the right/lower portion of the map (the ones a
user would have split via the app's room editor) are green — those are
exactly the segments `wall_lines` encodes.

## 2. Findings

1. **Partial coverage (44.5%), not noise.** The distribution is bimodal:
   covered cells sit within 0-50 mm of a vector (i.e. essentially exact grid
   alignment — `wall_lines` coordinates trace real grid lines when they
   exist at all); uncovered cells sit hundreds to thousands of mm away (the
   nearest vector is nowhere close, not a rounding-distance miss). There is
   no threshold that "fixes" this — the uncovered cells simply have no
   corresponding vector data.
2. **100% axis-aligned.** Every decoded `wall_lines`/`door_lines` segment on
   this fixture is a horizontal or vertical line (zero diagonals). An
   axis-aligned band of pixel cells has no aliasing to begin with — the
   current `pixels.repeat(scale, ...)` block-fill (or the bicubic
   `vector_rooms` smooth-upscale) already renders it as a crisp rectangle at
   any resolution. So even in the 44.5% that *is* covered, vectorizing would
   be a pixel-identical no-op at best.
3. **`door_lines` segment lengths range from 50 mm to 7800 mm.** A "door" is
   normally ~700-900 mm; an 8 m segment is clearly not a literal doorway
   opening, so `type 1` likely tags something closer to "open/threshold
   boundary" than "this exact span is a door". Several door segments sample
   mostly through room-interior pixel types along most of their length (not
   the wall band), consistent with that broader reading. This matters for
   what a "door marker" should look like: a short, sober dashed line is a
   safe rendering for both a literal small doorway and a longer open
   threshold — it never claims more than "here is a walls_info type-1
   segment", which is what the data actually says.

## 3. Decision and what shipped

- **`wall_lines`: no rendering change.** The renderer never reads
  `MapData.wall_lines`. Confirmed byte-identical output with/without it
  populated, all else equal — pinned by
  `tests/test_map_renderer.py::TestRenderMapFullPipeline::test_wall_lines_alone_does_not_change_pixel_output`.
  The decode (since 5461398) and the `wall_lines` attribute exposure (since
  68a98cd) are untouched; the companion card can still read the raw
  segments from the camera attribute even though the integration's own PNG
  doesn't use them for wall drawing.
- **`door_lines`: rendered.** New `MapRendererLayer.DOOR` object layer
  (`_ShapesMixin.render_doors`, `_layers.py`'s `render_objects`), drawn after
  the existing wall pixels/objects, in a dashed pattern (`_shapes.py`) using
  a colour derived from the wall colour with a warm tint
  (`_StaticHelpersMixin._door_line_color`) so it reads as a distinct,
  restrained marker in both the light and dark built-in colour schemes —
  never a duplicated wall outline. Toggle-able like every other map object
  (`hidden_map_objects` entry `"door"`, `MapRendererConfig.door`, default
  visible). Benefits from the same object-layer 2x supersample + BOX-filter
  thumbnail every other vector object layer already gets (see
  `_LayersMixin.render_objects` / `_compose_object_layers`), so it is
  anti-aliased for free.

## 4. How to revisit this

The wall-replacement idea only becomes viable if a firmware/protocol
revision starts describing the *entire* wall perimeter in `walls_info`
(matching the pixel-grid `WALL` cells 1:1, not just the user-edited straight
partitions), and/or the segments stop being purely axis-aligned (making
vectorization worth something visually). Re-run
`scripts/wall_lines_coverage.py` against a fresh fixture first — if coverage
is still well under 100%, the replacement remains unsafe by construction (it
would delete real walls) regardless of anything else.
