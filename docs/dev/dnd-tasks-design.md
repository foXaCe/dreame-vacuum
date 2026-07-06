# Multi-window DnD task editing — design

## Status

**Implemented**, with the `weekdays`-as-names proposal deliberately *not*
shipped. `set_dnd_task_entry`/`delete_dnd_task` (`device_setters.py`), the
`vacuum_set_dnd_task`/`vacuum_delete_dnd_task` services, and the read-side
`ATTR_DND["weekday_mask"]` addition are all in place — but per the
"Unknowns" section below, the bit-to-day mapping was never confirmed on a
live device, so `weekday_mask` is a **raw pass-through int** (never
decoded/encoded into weekday names) everywhere: the service field, the
engine methods, and the read-side attribute. See `docs/services.md` for the
shipped service contract. The design discussion below (wire format,
unknowns, rationale) still applies as-is; only the "weekday names" service
field shape was replaced with the raw-int approach it flagged as the
fallback.

## What already works today

Simple (single-window) DnD is fully read+write on all devices, regardless of
the `dnd_task` capability:

- `custom_components/dreame_vacuum/switch.py:69-94` — `dnd`,
  `DND_DISABLE_RESUME_CLEANING`, `DND_DISABLE_AUTO_EMPTY`, `DND_REDUCE_VOLUME`
  switch entities.
- `custom_components/dreame_vacuum/time.py:33-44` — `dnd_start` / `dnd_end`
  `TimeEntity` entities (gated on `device.capability.dnd`).

On devices that report the `dnd_task` capability, the device firmware
supports **multiple named DND windows** ("tasks"), but the integration only
ever reads and writes **the first entry** (`dnd_tasks[0]`). That is the gap
this design closes.

## Wire format (confirmed from code)

The `DreameVacuumProperty.DND_TASK` property value is a JSON array of task
objects, written as compact JSON (no spaces):

```json
[{"id":1,"en":true,"st":"22:00","et":"08:00","wk":127,"ss":0}]
```

| Key  | Type | Meaning | Evidence |
|------|------|---------|----------|
| `id` | int  | Task identifier | `custom_components/dreame_vacuum/dreame/device_setters.py:778` sets `"id": 1` for the first-ever task. |
| `en` | bool | Task enabled | `device_setters.py:779`, read at `custom_components/dreame_vacuum/dreame/device_status/_core.py:675` (`dnd_tasks[0].get("en")`) and surfaced read-only at `_core.py:1368` (`"enabled": dnd_task.get("en")`). |
| `st` | str `"HH:MM"` | Window start time | `device_setters.py:780`, read at `_core.py:688`, surfaced at `_core.py:1369` (`"start"`). Validated against `([0-1][0-9]|2[0-3]):[0-5][0-9]$` at `device_setters.py:759-763`. |
| `et` | str `"HH:MM"` | Window end time | `device_setters.py:781`, read at `_core.py:701`, surfaced at `_core.py:1370` (`"end"`). Same HH:MM validation; `device_setters.py:764-769` additionally rejects `st == et`. |
| `wk` | int (bitmask) | Weekday mask, `127` = all 7 days | `device_setters.py:782`. **Confirmed**: only ever written as the literal `127` today — no code path reads or decodes it. Bit-to-day mapping is **unknown** (see below). |
| `ss` | int | Unknown | `device_setters.py:783`. **Unknown** — only ever written as literal `0`; no other reference to this key exists anywhere in `custom_components/` or `tests/` (checked via repo-wide grep). No vendor/protocol-dump asset directory exists in this repo to cross-reference against. |

Serialization: `json.dumps(dnd_tasks, separators=(",", ":")).replace(" ", "")`
at `device_setters.py:790-792` — compact, no whitespace, in list order.

### `set_dnd_task` today (`device_setters.py:751-793`)

```python
def set_dnd_task(self, enabled: bool | None, dnd_start: str | None, dnd_end: str | None) -> bool
```

- Defaults blank start/end to `"22:00"` / `"08:00"` (`:753-757`).
- Validates HH:MM format and `start != end` (`:759-769`), raising
  `InvalidValueException` on failure.
- If `status.dnd_tasks` is empty, **appends** a single new task with
  `id=1, wk=127, ss=0` (`:775-785`).
- Otherwise **mutates `dnd_tasks[0]`** in place — `en`/`st`/`et` only; `wk`
  and `ss` of an existing task are left untouched (`:786-789`).
- Writes the **entire list** back as compact JSON to
  `DreameVacuumProperty.DND_TASK` (`:790-793`) — i.e. the wire protocol
  already supports multiple entries; the integration's own logic is what
  restricts it to one.

`set_dnd`, `set_dnd_start`, `set_dnd_end` (`device_setters.py:795-815`) all
delegate to `set_dnd_task` when `capability.dnd_task` is set, otherwise write
the plain `DND` / `DND_START` / `DND_END` properties directly.

### Read side (`_core.py:669-705`, `_core.py:1362-1373`)

- `dnd` / `dnd_start` / `dnd_end` properties: when `capability.dnd_task`,
  read from `dnd_tasks[0]` with static fallbacks (`False` / `"22:00"` /
  `"08:00"`) if the list is empty or absent (`_core.py:675-676`,
  `:688-689`, `:701-702`).
- `_add_state_attributes` (`_core.py:1362-1373`): when `capability.dnd_task`
  and `dnd_tasks is not None`, **all** tasks are already exposed read-only in
  `ATTR_DND` (`const.py:512`, value `"dnd"`) as a dict keyed by task `id`:
  `{id: {"enabled": ..., "start": ..., "end": ...}}` (`_core.py:1364-1371`).
  Non-`dnd_task` devices get `attributes[ATTR_DND] = self.dnd` (a plain
  bool) instead (`_core.py:1372-1373`).
- Change lands via `_dnd_task_changed` (`custom_components/dreame_vacuum/dreame/device.py:1479-1482`),
  which does `json.loads()` on the raw property string whenever it's
  non-empty; confirmed by `tests/test_device_lifecycle.py:1123-1132`
  (`TestDndTaskChanged`).

## Step 1 findings — unknowns from the plan

Checked repo-wide (`grep -rn` over `custom_components/`, `tests/`, and the
whole repo tree; no vendor/protocol-asset directory exists to consult):

- **`ss` field meaning**: **unknown**. It is only ever written as the
  literal `0` (`device_setters.py:783`) and appears in test fixtures with
  the same literal value (`tests/test_device_setters.py:968,971,977`). No
  code anywhere reads it or branches on it. No naming convention elsewhere
  in the codebase (e.g. `ScheduleTask` at
  `custom_components/dreame_vacuum/dreame/vacuum_types.py:4104-4118`, which
  stores its own weekday-like field `repeats` as an opaque, never-decoded
  string) offers a clue. Treat as opaque/pass-through: preserve whatever
  value is already present in an existing task when upserting; default to
  `0` for brand-new tasks, matching current behavior.
- **Weekday bitmask (`wk`) bit order**: **inferred only as far as** `127`
  (`0b1111111`, 7 bits set) = "all days," consistent with 7 days of the
  week (`device_setters.py:782`). The **bit-to-day mapping (which bit is
  Monday vs. Sunday, etc.) is unknown** — no code decodes or constructs any
  `wk` value other than the literal `127`, and no test fixture uses a
  partial mask. This must be **confirmed on a live device** before shipping
  a weekday-name-to-bit mapping; ship the design with the mapping explicitly
  marked TBC.
- **Task id contiguity / 1-based**: **inferred, not proven**. The only
  code path that creates a task assigns `"id": 1` for the very first entry
  (`device_setters.py:778`) and never increments beyond that (since nothing
  today creates a second task). `tests/test_device_status_core.py:2536` uses
  a string id (`"id": "t1"`) in a synthetic fixture, showing the read side
  does not assume `id` is an `int` — it only does dict/key lookups
  (`_core.py:1367`, keyed by whatever `dnd_task["id"]` is). No evidence
  constrains ids to be contiguous or 1-based on the wire; the follow-up
  implementation should treat `id` as an opaque key for upsert/delete
  purposes and only assign `max(existing ids) + 1` (starting at `1`) when
  creating a brand-new task, to stay consistent with existing behavior.
- **Maximum task count**: **unknown / unbounded in code**. No constant,
  validation, or comment anywhere limits the length of `dnd_tasks`; grep for
  limits (`max`, `MAX`, task count comparisons) near `dnd_task` turned up
  nothing. Ship without a client-side cap; if the device rejects an
  oversized array, that will surface as a normal `set_property` failure to
  handle at the call site (as `set_dnd_task` already does for existing
  fields).

## Proposed engine additions

Both live in `device_setters.py` alongside `set_dnd_task`, reusing its
validation and serialization exactly (same HH:MM regex, same
`start != end` check, same compact-JSON write to
`DreameVacuumProperty.DND_TASK`):

```python
def set_dnd_task_entry(
    self,
    task_id: int | None,
    enabled: bool,
    start: str,
    end: str,
    weekdays: list[str] | None = None,
) -> bool:
    """Create or update a single DnD task by id.

    - task_id is None (or not found in the current list): append a new
      task. Assign id = max(existing ids, default 0) + 1, mirroring the
      id=1 the current single-task path assigns for the first task
      (device_setters.py:778).
    - task_id found: update en/st/et (and wk, if weekdays given) in place,
      preserving any other keys already on that task's dict (in
      particular `ss`, whose meaning is unknown — never overwrite it).
    - Reuses the existing HH:MM regex and start != end validation
      (device_setters.py:759-769) — raise InvalidValueException the same
      way.
    - weekdays: list of weekday names (see service schema below); mapped
      to a bitmask via a WEEKDAY_TO_BIT table. If None, preserve the
      existing task's wk, or default to 127 (all days) for a new task —
      matching current behavior (device_setters.py:782).
    - Writes the full list back exactly like set_dnd_task does today
      (device_setters.py:790-793).
    """

def delete_dnd_task(self, task_id: int) -> bool:
    """Remove a single task by id from dnd_tasks and write the list back.

    - Raise InvalidValueException (consistent with set_dnd_task's error
      style) if task_id is not found — mirrors the existence check used
      by the analogous per-id action `rename_shortcut`
      (custom_components/dreame_vacuum/dreame/device_actions.py:1358-1367,
      which raises InvalidActionException("Shortcut {id} not found") for
      the same shape of problem).
    - After removal, write the remaining list (which may be empty) back
      via the same set_property(DreameVacuumProperty.DND_TASK, ...) call
      set_dnd_task uses today.
    """
```

Both functions only make sense when `capability.dnd_task` is set; on
non-`dnd_task` devices the existing single-window `set_dnd`/`set_dnd_start`/
`set_dnd_end` remain the only entry points, untouched.

## Proposed services

New service definitions in `services.yaml`, modeled directly on
`vacuum_rename_shortcut` (`services.yaml:517-533`), which is the existing
exemplar for per-id, entity-targeted operations, and registered the same
way `SERVICE_RENAME_SHORTCUT` is (`custom_components/dreame_vacuum/services.py:557-564`,
via `register(name, {vol.Required/Optional(...): validator, ...},
"async_handler_name")`, with the handler living on the vacuum entity in
`vacuum.py`, e.g. `async_rename_shortcut` at `vacuum.py:751-759`).

```yaml
vacuum_set_dnd_task:
  target:
    entity:
      integration: dreame_vacuum
      domain: vacuum
  fields:
    task_id:
      example: "1"
      required: false        # omit to create a new task
      selector:
        number:
          mode: box
    enabled:
      example: "true"
      required: true
      selector:
        boolean:
    start:
      example: "22:00"
      required: true
      selector:
        text:
    end:
      example: "08:00"
      required: true
      selector:
        text:
    weekdays:
      example: "[monday, tuesday, wednesday, thursday, friday]"
      required: false        # omit = preserve existing / default all days
      selector:
        select:
          multiple: true
          options:
            - monday
            - tuesday
            - wednesday
            - thursday
            - friday
            - saturday
            - sunday

vacuum_delete_dnd_task:
  target:
    entity:
      integration: dreame_vacuum
      domain: vacuum
  fields:
    task_id:
      example: "1"
      required: true
      selector:
        number:
          mode: box
```

Weekday names are used instead of a raw bitmask int because the bit order
is not yet confirmed (see Unknowns above) — the friendly list lets the
mapping table (`WEEKDAY_TO_BIT`) be corrected in one place once verified on
a live device, without changing the service's public field shape. **The
bit-to-day mapping itself must be confirmed on a live device before this
ships** — until then, implement the mapping but flag it clearly (code
comment + this doc) as unverified, and consider gating `weekdays` support
behind a follow-up if verification isn't possible before the build lands.

Both services should reject calls on devices without `capability.dnd_task`
(same style as `rename_shortcut`'s
`if not self.capability.shortcuts: raise InvalidActionException(...)` at
`device_actions.py:1363-1364`) and, for `vacuum_delete_dnd_task`, reject an
unknown `task_id` the same way `rename_shortcut` rejects an unknown
`shortcut_id` (`device_actions.py:1366-1367`).

## Read-side addition: expose `wk` in `ATTR_DND`

`_core.py:1364-1371` currently builds, per task:

```python
attributes[ATTR_DND][dnd_task["id"]] = {
    "enabled": dnd_task.get("en"),
    "start": dnd_task.get("st"),
    "end": dnd_task.get("et"),
}
```

Proposed: add a `"weekdays"` key holding the decoded list of weekday names
(via the same `WEEKDAY_TO_BIT` mapping, inverted), e.g.:

```python
attributes[ATTR_DND][dnd_task["id"]] = {
    "enabled": dnd_task.get("en"),
    "start": dnd_task.get("st"),
    "end": dnd_task.get("et"),
    "weekdays": decode_weekday_bitmask(dnd_task.get("wk")),
}
```

This is an **additive key on an existing per-task dict** — safe: existing
consumers reading `"enabled"`/`"start"`/`"end"` are unaffected; nothing
currently depends on the per-task dict *not* having other keys. It does
not change the dict for non-`dnd_task` devices, which keep
`attributes[ATTR_DND] = self.dnd` (a plain bool) at `_core.py:1372-1373`,
untouched.

## Capability gating

Everything above — both new engine methods, both new services, and the
`weekdays` attribute addition — is gated behind `capability.dnd_task`
(the same capability flag already gating the existing `dnd_tasks[0]`
special-casing throughout `_core.py` and `device_setters.py`). Single-window
devices (`capability.dnd_task is False`) are completely unaffected: they
keep using `set_dnd` / `set_dnd_start` / `set_dnd_end` against the plain
`DND` / `DND_START` / `DND_END` properties, and the existing `switch.py`
(`:69-94`) / `time.py` (`:33-44`) entities are untouched.

## Test strategy

Follows the existing pattern in `tests/test_device_setters.py`
(`TestSetDndTaskParsing`, `:959-1031`) — pure-engine tests against a
`SimpleNamespace`-backed host, no live device or coordinator needed, because
`set_dnd_task` (and the proposed `set_dnd_task_entry` /
`delete_dnd_task`) are deterministic pure functions over
`status.dnd_tasks` + a mocked `set_property`:

- **Upsert (new task)**: empty/`None` list → appends with a fresh id,
  `wk=127` default, mirrors
  `tests/test_device_setters.py:960-972`
  (`test_valid_times_appended_as_first_task`).
- **Upsert (existing id)**: list with a matching id → mutates in place,
  preserves `ss` and any unspecified `wk`, mirrors
  `tests/test_device_setters.py:974-986`
  (`test_existing_task_updated_in_place`).
- **Upsert (id not found, non-None)**: decide append-vs-error and cover
  whichever is chosen (recommendation: append, treating it like "create
  with this specific id" — avoids a surprising `InvalidValueException` for
  a plausible caller pattern of re-sending a previously-deleted id).
- **Delete (found / not found)**: found → list shrinks by one, remaining
  entries unchanged, `set_property` called with the new compact JSON;
  not found → `InvalidValueException`, mirroring the existence-check style
  of `rename_shortcut` (`device_actions.py:1366-1367`) and covered the same
  way `tests/test_device_setters.py` covers other `InvalidValueException`
  paths (e.g. `:998-1014`).
- **HH:MM / start==end validation**: reuse the exact parametrized cases
  already in `TestSetDndTaskParsing`
  (`tests/test_device_setters.py:1016-1031`) against the new entry points.
- **JSON serialization**: assert the exact compact-JSON string passed to
  `set_property`, as `tests/test_device_setters.py:969-972` does today —
  extend to multi-entry lists (order preserved, no added whitespace).
- **Weekday bitmask round-trip**: pure unit tests for
  `weekdays -> wk` and `wk -> weekdays` against the (flagged-unverified)
  `WEEKDAY_TO_BIT` table, independent of live-device confirmation — these
  tests validate the code's internal consistency, not the real device
  mapping.
- **Read-side `ATTR_DND["weekdays"]`**: extend
  `tests/test_device_status_core.py` (near `:2533-2548` and the broader
  attributes test at `:3352-3412`,
  `test_attributes_smart_mop_washing_map_and_dnd_task_path`) with a case
  asserting the new key appears alongside `enabled`/`start`/`end` when
  `capability.dnd_task` is set.
- **Service schema tests**: follow `tests/test_services.py` patterns for
  `vacuum_rename_shortcut` — required/optional field validation, target
  resolution, and the handler delegating to the right engine method.

## Follow-up implementation scope (out of scope for this design)

- `custom_components/dreame_vacuum/dreame/device_setters.py`: add
  `set_dnd_task_entry`, `delete_dnd_task`.
- `custom_components/dreame_vacuum/dreame/device_status/_core.py:1364-1371`:
  add `"weekdays"` key.
- `custom_components/dreame_vacuum/services.yaml`: add
  `vacuum_set_dnd_task`, `vacuum_delete_dnd_task`.
- `custom_components/dreame_vacuum/services.py`: register the two new
  services.
- `custom_components/dreame_vacuum/vacuum.py`: add
  `async_set_dnd_task` / `async_delete_dnd_task` handlers.
- `custom_components/dreame_vacuum/const.py`: new `SERVICE_*` / `INPUT_*`
  constants, and the `WEEKDAY_TO_BIT` mapping (clearly commented as
  unverified pending live-device confirmation).
- Tests per the strategy above.
- `docs/services.md`: document the two new services once implemented.
