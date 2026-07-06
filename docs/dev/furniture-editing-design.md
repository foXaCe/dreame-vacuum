# Furniture editing — wire format and design

## Status

Design only. No code in this change. Written to scope the "Furniture
editing" README To-Do item. Unlike shortcuts (see
`docs/dev/shortcut-editing-design.md`), furniture has **no write path of any
kind today** — it is decoded, capability-gated, rendered into the map PNG,
and served through an icon/dimension resource catalog that looks purpose-
built for an eventual editor UI, but nothing in this codebase ever sends a
furniture edit back to the device. This document documents the two
confirmed read-side wire formats, the rendering/resource scaffolding that
already exists, and proposes a write service shaped by strong (but
explicitly unconfirmed) analogy to the rest of the map-editing subsystem.

## What already works today

- **Two confirmed decode formats** (see below), producing `Furniture`
  objects (`custom_components/dreame_vacuum/dreame/types_map.py:883-965`,
  subclass of `Point`), keyed into `MapData.furnitures` or
  `MapData.saved_furnitures`
  (`custom_components/dreame_vacuum/dreame/map_decoder.py:870-955`).
- **Capability gating** for which `FurnitureType`s and which icon/dimension
  table apply (`pet_furniture`, `extended_furnitures`, `new_furnitures`,
  `mijia` — see below).
- **Full PNG rendering** of furniture icons/images on the map, with
  per-type rotation, scaling and background handling
  (`custom_components/dreame_vacuum/dreame/map_renderer/_objects.py:640-720`,
  `map_renderer/_layers.py:423`, `map_renderer/_core.py:1417`).
- **A furniture type/icon/dimension resource catalog**, already served to
  the frontend over HTTP (see "Resource catalog" below) — this is exactly
  the kind of scaffolding an "add furniture" picker UI would need, and
  appears to exist for no other reason.
- **Read-only exposure** on the camera entity's `extra_state_attributes`
  as `furnitures` (`ATTR_FURNITURES = "furnitures"`,
  `custom_components/dreame_vacuum/dreame/types_attributes.py:275`), built
  in `MapData.as_dict()`
  (`custom_components/dreame_vacuum/dreame/types_map.py:1688-1691`) and
  documented in `docs/camera_http_api.md:479` (`list[Furniture]`, raw
  objects relying on HA's `.as_dict()` duck-typing serialization, same
  mechanism documented in `docs/dev/schedule-format.md`'s finding about
  `ScheduleTask`). Excluded from recorder history as a "large map-geometry
  blob" alongside `obstacles`/`virtual_walls`/etc.
  (`custom_components/dreame_vacuum/recorder.py:85, 134`).
- **An existing AI toggle** — `ai_furniture_detection`
  (`DreameVacuumAIProperty.AI_FURNITURE_DETECTION`,
  `custom_components/dreame_vacuum/dreame/types_properties.py:313, 320`,
  switch entity at `custom_components/dreame_vacuum/switch.py:258-261`) —
  controls whether the device's AI *detects* furniture at all, and also
  whether already-decoded furniture is suppressed from rendering
  (`custom_components/dreame_vacuum/dreame/device_map_ops.py:406-407`:
  `if render_map_data.furnitures and self.status.ai_furniture_detection == 0: render_map_data.furnitures = {}`).
  This is unrelated to editing an individual piece of furniture's
  position/size/type — it is a global on/off switch for the whole feature.

What's entirely missing: any way to add, move, resize, rotate, retype, or
delete a single piece of furniture from Home Assistant. There is no
`set_furniture`, no `delete_furniture`, no furniture-shaped key ever passed
to `update_map_data_async`, and no furniture handling anywhere in
`custom_components/dreame_vacuum/dreame/map_editor.py` (confirmed by a
direct grep for "furniture" in that file and in `map_manager.py`: zero
matches in both).

## Wire format (confirmed from the decoder)

Furniture data arrives embedded in the same JSON tail as everything else
decoded by `DreameVacuumMapDecoder`
(`custom_components/dreame_vacuum/dreame/map_decoder.py`), under one of two
mutually-independent key families. Both are read in
`decode_map_data_from_partial`, in this order:

### Format 1 — `funiture_info` (sic; the misspelling is the device firmware's own key, preserved verbatim)

`map_decoder.py:870-899`. Checked **first**. Sets
`map_data.furniture_version = 1` and populates `map_data.saved_furnitures`
(not `map_data.furnitures`):

```python
if "funiture_info" in data_json:
    map_data.furniture_version = 1
    map_data.saved_furnitures = {}
    index = 0
    for furniture in data_json["funiture_info"]:
        index = index + 1
        furniture_type = int(furniture[1])
        if furniture_type == 8:
            furniture_type = 25
        elif furniture_type == 25:
            furniture_type = 8
        if furniture[3] > 0 and furniture[4] > 0:
            if furniture_type in FurnitureType._value2member_map_:
                map_data.saved_furnitures[index] = Furniture(
                    int(furniture[6]), int(furniture[7]),
                    int(furniture[6] - (furniture[3] / 2)), int(furniture[7] - (furniture[4] / 2)),
                    furniture[3], furniture[4],
                    FurnitureType(furniture_type), int(furniture[13]),
                    furniture[9], furniture[12],
                    furniture[0], furniture[2],
                )
```

| Index | Field | Meaning | Notes |
|-------|-------|---------|-------|
| `[0]` | `furniture_id` | Stable per-piece id | Only field present here that is **absent** in Format 0 below. |
| `[1]` | `type` (raw) | `FurnitureType` value | **Types 8 and 25 are swapped** unconditionally before validation (`:876-880`) — confirmed by `tests/test_map_decoder_extra.py:561-572` (`furniture_type=25` in → `.type.value == 8` out). `8` is `TOILET`, `25` is `ROUND_COFFEE_TABLE` in the enum (`types_map.py:201-230`) — no explanation for the swap is given anywhere; **unknown why**, only that it is deliberate and tested. |
| `[2]` | `segment_id` | Room id the furniture belongs to | Passed straight through, no validation. |
| `[3]` | `width` | Required `> 0` (`:882`) or the whole entry is skipped | |
| `[4]` | `height` | Required `> 0` (`:882`) or the whole entry is skipped | |
| `[5]` | *(unused)* | — | Never read by the decoder. **Unknown.** |
| `[6]` | center `x` | `Furniture.x` | Also used to derive `x0 = x - width/2`. |
| `[7]` | center `y` | `Furniture.y` | Also used to derive `y0 = y - height/2`. |
| `[8]` | *(unused)* | — | Never read. **Unknown.** |
| `[9]` | `angle` | `Furniture.angle` | No swap/adjustment applied in this format (contrast Format 0's legacy-key angle flip below). |
| `[10]`, `[11]` | *(unused)* | — | Never read. **Unknown** — two more positions with no decoded meaning. |
| `[12]` | `scale` | `Furniture.scale` | |
| `[13]` | `size_type` | `Furniture.size_type` | |

A furniture entry is only stored if both `furniture[3] > 0 and
furniture[4] > 0` **and** the (possibly-swapped) type is a known
`FurnitureType` value; otherwise the raw-array index is still consumed
(`index` increments unconditionally, `:875`) but no dict entry is written,
confirmed by `tests/test_map_decoder_extra.py:561-572` (a 2-item input
array producing exactly one output key, `[1]`, because the second item's
type `9999` is unknown).

Confirmed field mapping via
`tests/test_map_decoder_paths.py:588-599`
(`test_decode_legacy_funiture_info_format`): input
`[11, 8, 3, 40, 60, 0, 500, 600, 0, 45.0, 0, 0, 1.5, 2]` decodes to
`x=500, y=600, x0=480, y0=570` — exactly `x0 = 500 - 40/2`,
`y0 = 600 - 60/2`.

### Format 0 — `ai_furniture_user` / `ai_furniture_new` / `ai_furniture`

`map_decoder.py:901-955`. Checked **only if `map_data.furnitures is None`**
(i.e. independent of whether Format 1 already populated
`saved_furnitures` — the two are different `MapData` fields; see "Version
interaction" below). Key priority, first match wins
(`map_decoder.py:902-910`): `ai_furniture_user` → `ai_furniture_new` →
`ai_furniture`. Sets `map_data.furniture_version = 0` and populates
`map_data.furnitures` (not `saved_furnitures`):

```python
map_data.furnitures[index] = Furniture(
    center_x, center_y, start_x0, start_y0,
    rect_width, rect_height,
    FurnitureType(furniture_type), int(furniture[3]),
    angle, scale,
)
```

— note only **10** positional args are passed here: `furniture_id` and
`segment_id` are **not** provided at all in this format, so they default to
`None` on the `Furniture` object (`types_map.py:896-897`). **A Format-0
furniture item has no stable id in this codebase's data model** — see
"Gap: no id on legacy-format devices" below.

| Index | Field | Meaning | Notes |
|-------|-------|---------|-------|
| `[0]` | center `x` | `Furniture.x` | |
| `[1]` | center `y` | `Furniture.y` | |
| `[2]` | `type` (raw) | `FurnitureType` value | No swap in this format. |
| `[3]` | `size_type` | | Entry requires `len(furniture) >= 4` to be considered at all (`:917`). |
| `[4]` | `x0` | Only read if `len(furniture) >= 8` (`:929-933`); otherwise `x0 = center_x` (i.e. falls back to the center point) | |
| `[5]` | `y0` | Same `len >= 8` gate; falls back to `center_y` | |
| `[6]` | `width` | `abs(int(furniture[6]))`, same gate; falls back to `0` | |
| `[7]` | `height` | `abs(int(furniture[7]))`, same gate; falls back to `0` | |
| `[8]` | `angle` | Only read if `len >= 9` (`:934-940`); falls back to `0`. **Only when the source key is literally `"ai_furniture"`** (not `"ai_furniture_new"` or `"ai_furniture_user"`), a `180`⇄`0` flip is applied (`:936-940`) — confirmed by `tests/test_map_decoder_extra.py:575-585`. **Unknown why** this legacy-key-only flip exists. | |
| `[9]` | `scale` | Only read if `len >= 10` (`:941-942`); falls back to `1.0` | |

Confirmed field mapping via
`tests/test_map_decoder_paths.py:484-584`
(`test_decode_geometry_metadata_fields`, furniture assertions at
`:578-584`): input `[100, 200, 1, 3, 90, 190, 20, 30, 180, 1.0]` under
`ai_furniture_new` decodes to `x=100, y=200, x0=90, y0=190, width=20,
height=30, type=SINGLE_BED, angle=180.0, scale=1.0` — `x0`/`y0` taken
directly from the array (not derived from center - width/2, unlike
Format 1).

### Version interaction (confirmed, easy to misread)

`furniture_version` is a single field on `MapData`, but it is set by
**both** independent branches above, and the second branch's guard
(`if map_data.furnitures is None`) only checks `.furnitures`, not
`.saved_furnitures`. So if a single raw payload contained **both**
`funiture_info` and one of the `ai_furniture*` keys, the final
`furniture_version` would be `0` (the second branch always runs and always
overwrites it when triggered), even though `saved_furnitures` (Format 1,
"version 1") was populated first. **Unknown whether real payloads ever
contain both key families simultaneously** — no test exercises that
combination, and nothing in this codebase asserts they are mutually
exclusive on the wire; this is flagged as a latent inconsistency, not a
confirmed bug, since it may simply never occur in practice.

Separately, on a **saved/restored map merge**
(`map_decoder.py:844-846`, `saved_map_status == 2` branch): if the inner
saved map has `saved_furnitures` (i.e. was decoded via Format 1), those are
copied onto the *outer* map's `.furnitures` field (not `.saved_furnitures`)
along with the saved map's `furniture_version`. Then, in
`device_map_ops.py:227-228`, a `furniture_version == 1` gets **upgraded to
2 or 3** purely for rendering purposes if the device capability supports it:

```python
if render_map_data.furniture_version == 1 and self.capability.new_furnitures:
    render_map_data.furniture_version = 3 if self.capability.mijia else 2
```

So versions 2/3 are **not** distinct wire encodings — they select a
different icon/dimension asset table (`FURNITURE_V2_TYPE_TO_*` vs.
`FURNITURE_V2_TYPE_MIJIA_TO_*`) for the *same* Format-1 data, purely so
newer devices get newer-style icons.

## `Furniture` object shape

`types_map.py:883-948` (`Furniture(Point)`):

```python
class Furniture(Point):
    def __init__(self, x, y, x0, y0, width, height, type: FurnitureType,
                 size_type: int, angle: float = 0, scale: float = 1.0,
                 furniture_id: int | None = None, segment_id: int | None = None): ...
```

`x1,y1 / x2,y2 / x3,y3` (the other three rectangle corners) are derived
automatically from `x0, y0, width, height` when all four are truthy
(`:904-917`); otherwise left `None`. `as_dict()` (`:925-948`) emits
`type` (title-cased enum name, not the raw int), `x0/y0` through `x3/y3`
(only the ones that are set), `width/height` (only if both truthy),
`room_id` (only if `segment_id` truthy), and unconditionally `size_type`,
`angle`, `scale`. `furniture_id` is **not** included in `as_dict()`'s output
at all (confirmed by reading the method body directly) — only `x, y`
(inherited from `Point.as_dict()`) plus the fields listed above. This means
today's read-only `furnitures` attribute already doesn't surface
`furniture_id` to Home Assistant, even for Format-1 devices that have one
internally.

## Capability gating

Four `DeviceCapability` enum entries govern furniture
(`custom_components/dreame_vacuum/dreame/types_capability.py:31, 38, 50-51`):
`PET_FURNITURE = 16`, `EXTENDED_FURNITURES = 23`, `NEW_FURNITURES = 35`,
`SAVED_FURNITURES = 36`. Unlike `capability.shortcuts`/`capability.dnd`,
these are populated from the versioned per-device capability table (the
generic `setattr(self, param, bool(version >= v[1]))` loop,
`types_capability.py:264-272`), not a property-presence check.

- `capability.pet_furniture`: gates whether pet-specific `FurnitureType`s
  (`LITTER_BOX`, `PET_BED`, `FOOD_BOWL`, `PET_TOILET`,
  `ENCLOSED_LITTER_BOX`) are included in the resource catalog
  (`map_renderer/_resources_props.py:242-252`).
- `capability.extended_furnitures`: gates whether `FurnitureType` values
  `> 13` are included at all (`_resources_props.py:254-255`) — i.e. the
  older/base furniture type set is capped at 13 types
  (`SINGLE_BED` through `TOILET`; see `types_map.py:201-230`), and only
  devices with this capability get the extended set up to `L_SHAPED_SOFA_RIGHT = 31`.
- `capability.new_furnitures`: selects the `FURNITURE_V2_*` resource tables
  and icon set (`_resources_props.py:257-283`), and is what triggers the
  `furniture_version` 1→2/3 rendering upgrade in `device_map_ops.py:227-228`.
- `capability.mijia`: further selects the `_MIJIA_` variant of the V2
  dimension/image tables when both `new_furnitures` and `mijia` are set
  (`_resources_props.py:258-260`, `device_map_ops.py:228`).
- `capability.saved_furnitures` exists as a capability flag but is **never
  read anywhere** in `custom_components/` outside its own definition and
  the generic capability-list construction (confirmed by grep) — its
  effect, if any, is unknown from this codebase; it may simply be exposed
  in `capability.list` for diagnostics/UI purposes without being consumed
  by any code path here.

## Resource catalog (already served over HTTP — built for a picker, unused by one)

`get_resources()` (`custom_components/dreame_vacuum/dreame/map_renderer/_resources_props.py:103-284`)
builds, per capability-gated `FurnitureType`, a dict of
`{"name", "icon", "image", "dimensions"}` (name = title-cased enum name;
dimensions from `FURNITURE_TYPE_TO_DIMENSIONS` /
`FURNITURE_V2_TYPE_TO_DIMENSIONS` / `FURNITURE_V2_TYPE_MIJIA_TO_DIMENSIONS`,
`custom_components/dreame_vacuum/dreame/types_attributes.py:125-199` — a
literal default-`[width, height]` in millimeters per type, e.g.
`FurnitureType.SINGLE_BED: [1500, 2000]`). This is served to the frontend
over an authenticated HTTP view:

```
GET /api/camera_resources_proxy/{entity_id}?icon_set=<n>
```

(`custom_components/dreame_vacuum/camera_views.py:255-284`,
`CameraResourcesView`), backed by `camera.resources()`
(`custom_components/dreame_vacuum/camera.py:843-847` calling
`self._renderer.get_resources(self.device.capability, True, icon_set)`).

This is exactly the shape a "pick a furniture type, place it with sensible
default dimensions" editor UI would need — a name, an icon/image to show in
a picker, and a default width/height to seed a placement rectangle before
the user drags/resizes it. **No code anywhere consumes this catalog for
anything other than rendering the PNG map image itself** (confirmed: the
only importers of `FURNITURE_TYPE_TO_ICON` / `FURNITURE_TYPE_TO_IMAGE` /
the V2/mijia variants are `map_renderer/_resources_props.py` and
`map_renderer/_objects.py`, both server-side renderer code, per repo-wide
grep). Whether the existing companion Lovelace card already fetches this
endpoint for its own editor UI is **outside this repository** and therefore
unknown from here — this repo only confirms the endpoint exists and what it
serves.

## Gap: no stable id on legacy-format (Format 0) devices

Any per-item edit/delete service needs a stable key to address "this one
piece of furniture" across successive map updates. Format 1
(`funiture_info`) carries a real `furniture_id` field (index `[0]`). Format
0 (`ai_furniture*`) carries **none** — `Furniture.furniture_id` stays `None`
for every item decoded from that format (only 10 of 12 constructor
positional args are ever passed, `map_decoder.py:944-955`). The dict key
used internally (`map_data.furnitures[index]`) is a **decode-time sequential
counter**, recomputed from scratch on every single decode call
(`index = 0` at the top of the loop, `map_decoder.py:914`) — nothing in this
codebase demonstrates that this ordering is stable across successive polls
of the same device (e.g. if the device reorders the array between
payloads, the same physical piece of furniture could get a different
`index` key next time). **Unknown / unconfirmed**: whether the device
always emits Format-0 furniture in a stable order. Until confirmed on a
live Format-0 device, a per-item edit/delete service should be considered
safe **only for Format-1 (`furniture_version == 1`, i.e.
`capability.new_furnitures` or a saved map carrying `saved_furnitures`)**
devices, where `furniture_id` is a real, device-issued identifier.

## Unknowns (explicit)

- **Write wire key**: no code anywhere writes furniture data back to the
  device. By strong analogy (not confirmed) with every other map-editing
  operation in `device_map_ops.py` — where the JSON key used to *read* a
  field out of a decoded payload is the exact same key used to *write* it
  back via `update_map_data_async` (confirmed pattern: `"vw"` read at
  `map_decoder.py:1023` / written at `device_map_ops.py:657`; `"vws"` read
  at `map_decoder.py:1110` / written at `device_map_ops.py:707`; `"delsr"`
  read at `map_decoder.py:469-470` / written at `device_map_ops.py:1363`;
  `"carpetcleanset"` read at `map_decoder.py:502-503` / written at
  `device_map_ops.py:1342`; `"customeClean"` read at `map_decoder.py:386` /
  written implicitly via `set_cleanset`) — it is plausible that a furniture
  write would use `"funiture_info"` (matching the modern, id-bearing
  Format 1) as its key. **This is an inference from a pattern, not a
  confirmed fact** — no furniture write of any kind has ever been observed
  in this codebase, and the pattern, while consistent across many other
  fields, is not guaranteed to hold for furniture specifically.
- **Write payload shape**: unknown whether a write would be a whole-list
  replace (matching `set_restricted_zone`'s `{"line": [...], "rect": [...],
  "mop": [...]}` / `set_carpet_area`'s `{"addcpt": [...], "nocpt": [...]}`
  style) or a per-item upsert. Given every existing map-editing operation in
  `device_map_ops.py` is whole-list replace, that is the more consistent
  guess, but again unconfirmed for furniture.
- **`[5]`, `[8]`, `[10]`, `[11]` in Format 1**: four unused array positions
  with no decoded meaning anywhere in this codebase.
- **Type-8/25 swap reason** (Format 1) and **the `"ai_furniture"`-only
  angle 180/0 flip** (Format 0): both confirmed to happen, neither's
  *reason* is known.
- **Format-0 index stability**: see "Gap" section above.
- **`capability.saved_furnitures`' effect**: defined but never consumed
  anywhere in this codebase.
- **Companion card behavior**: whether an editor UI already exists
  client-side against the resources endpoint is outside this repository and
  unknown from here.

## Proposed service (design only — not built in this change)

Given the write wire key is unconfirmed, this is explicitly a **draft to
validate against a live-device capture**, not a ready-to-implement spec —
following the same posture `docs/dev/dnd-tasks-design.md` took for the `wk`
bitmask, but more conservative here because *no* part of the write side has
even a single observed literal to anchor on (contrast `wk=127`, which was at
least always observed as that literal).

### `dreame_vacuum.vacuum_set_furniture` (whole-list replace, Format-1 devices only)

Modeled on the existing whole-list-replace map-editing services
(`set_restricted_zone` / `set_carpet_area` / `set_virtual_threshold`,
`device_map_ops.py:640-707`), all of which take the full new list and
`update_map_data_async` it in one shot rather than upserting a single item:

```yaml
vacuum_set_furniture:
  target:
    entity: {domain: vacuum, integration: dreame_vacuum}
  fields:
    furnitures:
      example: "[[1,1,3,1500,2000,0,0,0,1.0]]"
      required: true
      selector:
        object:
```

Proposed engine method shape (`device_map_ops.py`, alongside
`set_restricted_zone`):

```python
def set_furniture(self, furnitures: list[list[Any]] | None = None) -> dict[str, Any] | None:
    """Replace the full furniture list on the current saved map.

    Gated on capability.new_furnitures (Format 1 / furniture_version >= 1) —
    Format-0 devices are not addressable by a stable id (see design doc's
    "Gap: no stable id" section) and are out of scope for this service
    until that is separately resolved.

    UNCONFIRMED wire key: proposed as "funiture_info" by analogy with every
    other read-key == write-key pair in this file; must be verified against
    a live device before implementation, exactly like set_restricted_zone's
    "vw" key was presumably verified when it was built.
    """
    if not self.capability.new_furnitures:
        raise InvalidActionException("Furniture editing is not supported on this device")
    if furnitures is None:
        furnitures = []
    return self.update_map_data_async({"funiture_info": furnitures})
```

Deliberately **not** proposing a per-item `vacuum_delete_furniture` /
`vacuum_move_furniture` service: every existing map-editing write in this
codebase is whole-list replace (the client is expected to fetch the current
list from the `furnitures` attribute, mutate it, and send the whole thing
back — same as walls/carpets/thresholds), so a companion card would build
add/move/delete/resize/rotate interactions client-side against this single
service, exactly as it presumably already does for virtual walls and
carpets.

### Why this is not built yet

Three independent reasons, each sufficient on its own to block
implementation:

1. **The write key is an inference, not a confirmed fact.** Sending an
   unconfirmed key to `UPDATE_MAP_DATA` either silently no-ops (if the
   firmware ignores unknown keys, consistent with how `set_property`
   guards work elsewhere in this codebase) or, worse, is misinterpreted —
   neither failure mode is characterized in this codebase for this
   specific action.
2. **The payload element shape is unconfirmed.** Even if `"funiture_info"`
   is the right key, whether each element should mirror the *raw wire
   tuple* (`[furniture_id, type, segment_id, width, height, ?, x, y, ?,
   angle, ?, ?, scale, size_type]`, matching the read-side positional
   layout) or some other shape entirely is unverified.
3. **Format-0 devices have no safe per-item identity** (see "Gap" section),
   so any service must at minimum be capability-gated to exclude them, and
   that gate itself (`capability.new_furnitures`) is a best-effort proxy,
   not a proven exact match for "this device uses Format 1."

## Recommended next step (prerequisite to implementation)

Capture a real `UPDATE_MAP_DATA` payload from the Dreame/Mijia app while
adding, moving, resizing, and deleting a piece of furniture on a live
Format-1 device (`capability.new_furnitures`), using the same live-capture
methodology already documented for map payloads in
`docs/dev/capture-map-payload.md` (the hook point differs: here it's the
*outgoing* `UPDATE_MAP_DATA` action call from the app, not the *incoming*
`MAP_DATA` property, so the capture point would be on the app/network side —
e.g. a proxy on the phone — rather than `map_manager.py`'s
`_decode_map_partial`). Once the real key and payload shape are confirmed,
this document's proposed schema can be corrected and the engine method /
service / capability gate finalized with actual evidence, following the
same `update_map_data_async` + `register(...)` + `services.yaml` pattern
already used throughout `device_map_ops.py` and `services.py`.
