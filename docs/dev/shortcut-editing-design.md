# Shortcut editing — wire format and design

## Status

Design only. No code in this change. Written to scope the "Shortcut editing"
README To-Do item and to correct its wording — a meaningful slice of
"editing" (read, trigger, rename) is already shipped; what's missing is
create/delete/reorder and per-task (segment) editing, and that missing slice
turns out to have **zero wire-format evidence anywhere in this codebase** to
build from. This document says so explicitly rather than inventing a
schema.

## What already works today

- **Read**: every shortcut is exposed read-only via `ATTR_SHORTCUTS`
  (`"shortcuts"`, `custom_components/dreame_vacuum/dreame/const.py:514`),
  built in `_add_state_attributes`
  (`custom_components/dreame_vacuum/dreame/device_status/_core.py:1380-1389`)
  as `{id: {"name", "map_id", "running", "tasks"}}`, gated on
  `capability.shortcuts`.
- **Trigger**: `start_shortcut(shortcut_id)`
  (`custom_components/dreame_vacuum/dreame/device_actions.py:941-968`),
  exposed as the `dreame_vacuum.vacuum_start_shortcut` service
  (`custom_components/dreame_vacuum/services.yaml:131-144`, registered
  `custom_components/dreame_vacuum/services.py:277-282` →
  `async_start_shortcut`, `custom_components/dreame_vacuum/vacuum.py:466-468`;
  documented `docs/services.md:276-297`), plus one dynamically-generated
  `button` entity per shortcut
  (`custom_components/dreame_vacuum/button.py:267-283, 363-419`) and a
  "Reload shortcuts" diagnostic button
  (`custom_components/dreame_vacuum/button.py:216-222`) that calls
  `reload_shortcuts()` directly.
- **Rename**: `rename_shortcut(shortcut_id, shortcut_name)`
  (`custom_components/dreame_vacuum/dreame/device_actions.py:1358-1410`),
  exposed as `dreame_vacuum.vacuum_rename_shortcut`
  (`services.yaml:517-533`, registered `services.py:557-564` →
  `async_rename_shortcut`, `vacuum.py:751-759`; documented
  `docs/services.md:825-846`). This is the only field of a shortcut that can
  currently be mutated from Home Assistant.

So "editing" narrowly construed (renaming) is done. What the To-Do item most
plausibly still means — creating a new shortcut, deleting one, reordering
the button list, or editing the segments/settings inside a shortcut's
task list — has no existing engine method, no service, and (per the wire
format below) no discoverable command name in this repository to build one
from.

## Wire format (confirmed from code)

### `SHORTCUTS` property (raw)

`DreameVacuumProperty.SHORTCUTS = 52`
(`custom_components/dreame_vacuum/dreame/types_properties.py:66`), mapped to
`{siid: 4, piid: 48}`
(`custom_components/dreame_vacuum/dreame/types_properties.py:429`). Raw value
is a JSON array, decoded in `reload_shortcuts`
(`device_actions.py:1159-1172`):

```json
[{"id":32,"name":"<base64>","state":"1"}]
```

| Key | Type | Meaning | Evidence |
|-----|------|---------|----------|
| `id` | int | Shortcut identifier. Used directly as the `status.shortcuts` dict key with no cast (`device_actions.py:1166`: `id = shortcut["id"]`) — unlike `ScheduleTask.id` (see `docs/dev/schedule-format.md`), this one is wire-native int, not opaque/string-compared. |
| `name` | str, base64 | Display name. Decoded with `base64.decodebytes(...).decode("utf-8")` on read (`device_actions.py:1170`) and re-encoded with `base64.b64encode(...)` on write (`device_actions.py:1381`). Note: read uses `decodebytes` (MIME-style, tolerates embedded newlines), write uses plain `b64encode` — asymmetric but both are standard base64 alphabets, confirmed compatible by the round-trip test at `tests/test_device_actions.py:2392-2407`. |
| `state` | str, optional | `running = False if "state" not in shortcut else bool(shortcut["state"] == "0" or shortcut["state"] == "1")` (`device_actions.py:1167-1169`, repeated at `:1187-1191`). **Confirmed ambiguous**: both `"0"` and `"1"` map to `running=True`; any other value (or absence) maps to `False`. A code comment characterizing this as a likely bug is already codified in the test suite: `tests/test_device_actions.py:2449-2451` ("likely meant to distinguish 'stopped' vs 'running' but both map to True"). No third value is ever observed in this codebase. |

`map_id` and `tasks` are **not** in the raw `SHORTCUTS` property — they are
fetched separately (see below) and only populated asynchronously after the
initial synchronous parse.

### `SHORTCUTS` action (`call_shortcut_action` / `call_shortcut_action_async`)

`DreameVacuumAction.SHORTCUTS = 9`
(`types_properties.py:345`), mapped to `{siid: 4, aiid: 8}`
(`types_properties.py:642`). Every call sends the same envelope, via the
`CLEANING_PROPERTIES` piid (`device_actions.py:151-167`, `:169-188`):

```json
{"cmd":"<command>","params":{...}}
```

Exactly **three** command names appear anywhere in this repository (confirmed
by a repo-wide grep for `"cmd"` / the four command literals — no others
exist in `custom_components/` or `tests/`):

| Command | Params | Response shape | Evidence |
|---------|--------|-----------------|----------|
| `GET_COMMANDS` | `{}` | `out[0].value` = JSON array of `{"id":.., "mapId":..}` — used only to backfill `map_id` per shortcut | `device_actions.py:1175-1183, 1218` |
| `GET_COMMAND_BY_ID` | `{"id": <id>}` | `out[0].value` = JSON array of task-groups; each task-group is itself an array of 5-element segment arrays `[segment_id, suction_level, water_volume, cleaning_times, cleaning_mode]`, decoded into `Shortcut.tasks: list[list[ShortcutTask]]` | `device_actions.py:1195-1213`; `ShortcutTask` dataclass at `custom_components/dreame_vacuum/dreame/types_map.py:1735-1744` |
| `EDIT_COMMAND` | `{"id": <id>, "name": <base64>, "type": 3}` | `out[0].value == "0"` means success (any other value, or a missing/empty `out`, is treated as failure) | `device_actions.py:1396-1405`; confirmed by `tests/test_device_actions.py:2922-2983` |

`"type": 3` is **only ever set to the literal `3`**, for the rename
operation, in this entire codebase. There is no code path, test, constant,
or comment anywhere that assigns or interprets any other `type` value.
**Unknown**: what `type` values other than `3` would mean (create? delete?
reorder? edit tasks?) — nothing in this repository decodes or documents
that space.

No `ADD_COMMAND`, `CREATE_COMMAND`, `DELETE_COMMAND`, `REMOVE_COMMAND`, or
similarly-named command appears anywhere in `custom_components/` or
`tests/` (checked via repo-wide grep for `"cmd"` literals and for those
name fragments). Creating a new shortcut, deleting one, or editing the
segment/settings list inside an existing shortcut's `tasks` has **no
precedent whatsoever** in this codebase — not even a single observed byte,
unlike (for example) the DnD `wk` bitmask, which is at least always written
as a known literal (see `docs/dev/dnd-tasks-design.md`).

### `ShortcutTask` field semantics (inferred only, not confirmed)

`ShortcutTask` (`types_map.py:1735-1744`) fields — `segment_id`,
`suction_level`, `water_volume`, `cleaning_times`, `cleaning_mode` — share
their names exactly with the per-segment cleanset fields already
read/written elsewhere for direct segment cleaning (`Segment` class and
`set_segment_suction_level` / `set_segment_water_volume` /
`set_segment_cleaning_times` / `set_segment_cleaning_mode` in
`custom_components/dreame_vacuum/dreame/device_map_ops.py:1394-1492`). **By
analogy only** (no code anywhere confirms this for shortcuts specifically),
`suction_level`/`water_volume`/`cleaning_mode` plausibly align with
`DreameVacuumSuctionLevel` / `DreameVacuumWaterVolume` /
`DreameVacuumCleaningMode` int values used for direct segment cleaning — but
nothing decodes or maps a `ShortcutTask` field to a named enum anywhere in
this repository, so this must be verified on a live device before being
relied on.

## Capability gating

`capability.shortcuts` is derived purely from property presence
(`custom_components/dreame_vacuum/dreame/types_capability.py:259`):

```python
self.shortcuts = bool(self._device.get_property(DreameVacuumProperty.SHORTCUTS) is not None)
```

— unlike most other capability flags (which come from the versioned
capability table), this one is a simple existence check, same style as
`capability.dnd_task` / `capability.dnd` right above it
(`types_capability.py:257-258`). `SHORTCUTS` is listed in
`_PRIORITY_BOOT_PROPERTIES` (`custom_components/dreame_vacuum/dreame/device.py:134`)
and in `_discarded_properties` (`device.py:307`, so it never appears via the
generic property-attributes loop — `ATTR_SHORTCUTS` is built exclusively by
the dedicated block in `_core.py:1380-1389`) and in
`_read_write_properties` (`device.py:346`). `_shortcuts_changed`
(`device.py:1539-1540`) unconditionally calls `reload_shortcuts()` whenever
the raw property changes.

## Confirmed bug in `rename_shortcut` (already characterized by a test)

`device_actions.py:1370`:

```python
current_name = self.status.shortcuts[shortcut_id]
```

This captures the **whole `Shortcut` dataclass instance**, not its `.name`
string (should be `self.status.shortcuts[shortcut_id].name`). Two
consequences, both already reproduced and pinned down by the existing test
suite rather than being new speculation here:

1. `if current_name != shortcut_name:` (`:1371`) compares a `Shortcut`
   instance to a `str`. A dataclass's generated `__eq__` returns
   `NotImplemented` for a type mismatch, and Python then falls back to
   identity-based inequality — so this condition is **always true**,
   regardless of whether the new name actually differs from the old one.
   The name-conflict-counter logic (`:1372-1378`) therefore always runs,
   even when renaming a shortcut to its own current name.
2. On a failed device response, the rollback at `:1407`
   (`self.status.shortcuts[shortcut_id].name = current_name`) assigns the
   **`Shortcut` object itself** into its own `.name` attribute instead of
   restoring the previous string. Reproduced exactly by
   `tests/test_device_actions.py:2955-2970`
   (`test_failed_response_rolls_back_name`), which asserts
   `shortcut.name is shortcut` with an explicit `NOTE` comment calling this
   out as "a real bug."

This is a pre-existing bug, not introduced by this document, and is
independent of any new service work — flagging it here because any future
change to `rename_shortcut` (or a new service built alongside it) should fix
it in the same pass rather than propagating the same mistake into new code.

## Unknowns (explicit)

- **`state` "0" vs "1"**: both map to `running=True`; the intended
  distinction (if any) between the two wire values is not decoded anywhere.
- **`EDIT_COMMAND` `type` values other than `3`**: completely unknown. No
  create/delete/reorder/task-edit operation has ever been observed or
  encoded in this codebase.
- **Command names for create/delete**: unknown. No `ADD_COMMAND` /
  `DELETE_COMMAND` (or similar) exists anywhere to reference.
- **`ShortcutTask` field value semantics**: inferred by name-similarity to
  segment cleanset fields only, never confirmed for shortcuts specifically.
- **Shortcut id allocation for new shortcuts**: `start_shortcut` enforces
  `32 <= shortcut_id <= 128` (`device_actions.py:946-947`), but that is a
  *validation* guard on an existing id, not evidence of how the device (or
  app) would mint a new id when creating a shortcut. No code anywhere
  constructs a new shortcut id.
- **Maximum shortcut count**: unknown / unbounded in this codebase — no
  constant or check limits the length of the `SHORTCUTS` array.

## Why no create/delete/task-edit service is proposed here

Every other design doc in `docs/dev/` that proposes a write service
(`dnd-tasks-design.md`, `schedule-format.md`) does so by taking a
**known wire encoding with at least one confirmed literal** (`wk=127`,
`SCHEDULE`'s `;`/`-` string grammar) and building a schema around it, with
the genuinely unknown parts (bit order, `repeats` encoding) marked TBC and
gated behind live-device verification. Shortcuts differ qualitatively: there
is no confirmed literal at all for the operations this To-Do item is really
asking for (add, remove, reorder, edit the segment list). Proposing a
service schema for `EDIT_COMMAND` with an invented `type` value, or an
invented `ADD_COMMAND`/`DELETE_COMMAND` name, would not be a design — it
would be a guess presented as one, and if wrong, a malformed action call
sent to a real device (unlike a rejected `set_property`, a bad action
`params` payload's failure mode on this device family is not well
characterized in this codebase either).

## Recommended next step (prerequisite to any further design)

Capture the Dreame/Mijia app's shortcut editor screen (create a shortcut,
delete one, reorder the list, edit a task's segments) at the network layer
— the same kind of live capture already used for map payloads
(`docs/dev/capture-map-payload.md`), but here the target is the `SHORTCUTS`
action's `cmd`/`params` traffic (`device_actions.py:151-188` is the existing
hook shape to mirror: `siid=4, aiid=8`, `CLEANING_PROPERTIES` piid) rather
than the `MAP_EXTEND_DATA` property. Once real `cmd` names and `params`
shapes for create/delete/reorder/task-edit are observed, a follow-up design
can propose `vacuum_create_shortcut` / `vacuum_delete_shortcut` /
`vacuum_set_shortcut_tasks` services with actual evidence, following the
same `register(...)` / `services.yaml` / `vacuum.py` handler pattern already
used for `vacuum_rename_shortcut`
(`services.py:557-564`, `vacuum.py:751-759`).

Until that capture happens, the only concrete, evidence-backed action item
from this document is the `rename_shortcut` rollback bug fix above, which
is a small, independent bug fix rather than new "editing" scope.
