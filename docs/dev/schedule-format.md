# Schedule editing — wire format and design

## Status

**Read path: already shipped, undocumented. Write services: design only, no code
in this change.**

Plan 019 set out to (1) document the `SCHEDULE` wire format, (2) expose
`status.schedule` as a new HA attribute, and (3) scope the write services. Step
2 hit one of the plan's own STOP conditions during verification — see
[Finding: the read attribute already exists](#finding-the-read-attribute-already-exists)
— so this change only delivers (1) and (3). No `custom_components/` code was
touched.

## Wire format (confirmed from the parser)

`custom_components/dreame_vacuum/dreame/device.py:1484-1517`
(`_schedule_changed`, registered unconditionally — no capability gate — at
`device.py:387`) parses the raw `DreameVacuumProperty.SCHEDULE` string:

```
"<id>-<status>-<time>-<repeats>-<once>-<map_id>-<suction_level>-<water_volume>-<options>;<id>-<status>-..."
```

- Tasks are separated by `;` (`device.py:1488`: `schedule.split(";")`).
- Fields within a task are separated by `-` (`device.py:1490`:
  `task.split("-")`).
- A task is only parsed if it has **at least 9** `-`-separated fields
  (`device.py:1491`); shorter entries are silently skipped.
- An empty or `""` raw value produces an empty list (`device.py:1487`) —
  this is also how a fully-cleared schedule reads back.

Field order, exactly as consumed (`device.py:1492-1505`), mapped onto
`ScheduleTask` (`custom_components/dreame_vacuum/dreame/vacuum_types.py:4103-4118`):

| # | Wire value | `ScheduleTask` field | Derivation | Notes |
|---|-----------|----------------------|------------|-------|
| 0 | `props[0]` | `id: int` | `int(props[0])` | Task identifier. No evidence anywhere in the codebase that ids are contiguous or 1-based — treat as opaque. |
| 1 | `props[1]` | `enabled: bool`, `invalid: bool` | `enabled = props[1] in ("1", "2")`; `invalid = props[1] == "3"` | Confirmed values: `"1"`/`"2"` → enabled, `"3"` → invalid. `"0"` (and anything else) falls through to `enabled=False, invalid=False` — i.e. disabled-but-valid. The distinction between wire values `"1"` and `"2"` (both map to `enabled=True`) is **not decoded anywhere** — unconfirmed what the two enabled states mean. |
| 2 | `props[2]` | `time: str` | raw string, kept as-is | Used later as `"HH:MM"` for sort ordering (`device.py:1512`: `int(a.time.replace(":", ""))`), so it is a colon-separated time string. The write-side validator only checks that `":"` is present (`device_setters.py:405-408`, see below) — it does not enforce a full `HH:MM` regex the way the DnD setter does (`device_setters.py:453`). |
| 3 | `props[3]` | `repeats: str` | raw string, kept as-is | **Unconfirmed / opaque.** Never decoded anywhere in `custom_components/` — no code branches on its value or bit-decodes it. By analogy with the DnD `wk` weekday bitmask (`docs/dev/dnd-tasks-design.md`), it plausibly encodes a weekday selection, but there is no evidence for the encoding (bitmask vs. comma list vs. day names) in this repo. Do not guess the encoding in code. |
| 4 | `props[4]` | `once: bool` | `once = (props[4] == "0")` | Note the inversion: wire value `"0"` means "run once" (`once=True`); any other value means "repeating," governed by `repeats`. |
| 5 | `props[5]` | `map_id: str` | raw string, **not cast to int** | Kept as a string in the dataclass (`vacuum_types.py:4111`: `map_id: str \| None`), unlike other map-id fields elsewhere in the codebase that are ints. Confirmed by reading the assignment directly — no cast is applied. |
| 6 | `props[6]` | `suction_level: int` | `int(props[6])` | Unambiguous positionally — the parser names this keyword argument explicitly. Presumed to align with `DreameVacuumSuctionLevel` values used elsewhere, but nothing decodes/maps it to a name for schedule tasks specifically (no `schedule_suction_level_name` helper exists). |
| 7 | `props[7]` | `water_volume: int` | `int(props[7])` | Unambiguous positionally (parser names the keyword explicitly), same caveat as suction_level — presumed to align with `DreameVacuumWaterVolume`, never mapped to a display name for schedule tasks. |
| 8 | `props[8]` | `options: list[str] \| None` | `props[8].split(",") if props[8] != "0" else None` | `"0"` means no options; otherwise a comma-separated list of option codes. **Unconfirmed** what the option codes mean — never decoded or referenced anywhere else in the repo. |

The parser's field order is **not ambiguous** — every field is assigned via
an explicit keyword argument in the `ScheduleTask(...)` constructor call
(`device.py:1493-1504`), so `suction_level` (index 6) and `water_volume`
(index 7) are unambiguously distinguishable by position. This means the
plan's corresponding STOP condition ("field order ambiguous for
`suction_level`/`water_volume`") does **not** apply.

After parsing, tasks are sorted by `time` (numeric `HH:MM` comparison,
ties broken by descending `id`) when there is more than one
(`device.py:1506-1516`), then stored unconditionally at
`self.status.schedule = schedule_list` (`device.py:1517`).
`status.schedule` itself is initialized to `[]`
(`custom_components/dreame_vacuum/dreame/device_status/_core.py:275`).

### `ScheduleTask` dataclass

`custom_components/dreame_vacuum/dreame/vacuum_types.py:4103-4118`:

```python
@dataclass
class ScheduleTask:
    id: int = -1
    enabled: bool = False
    invalid: bool = False
    time: str | None = None
    repeats: str | None = None
    once: bool = False
    map_id: str | None = None
    suction_level: int | None = None
    water_volume: int | None = None
    options: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
```

(Note: the `options` field is typed `str | None` here, but the parser
actually stores a `list[str] | None` into it — see row 8 above. This is a
pre-existing type/behavior mismatch in the current code, not something
introduced by this change; flagging it for whoever picks up the write-service
work, since a future `set_schedule` implementation needs to know the real
runtime type is a list.)

## Finding: the read attribute already exists

Plan 019's Step 2 instructed exposing `status.schedule` as a new
`ATTR_SCHEDULE` attribute, following the `ATTR_DND` exemplar. Before writing
that code, the plan's own preliminary check ("what does the `SCHEDULE`
property formatter produce today — is `SCHEDULE` filtered out of the property
list?") was run, and it is **not** filtered out:

- `DreameVacuumProperty.SCHEDULE` is unconditionally included in the
  properties list built by `_build_property_list()`
  (`custom_components/dreame_vacuum/dreame/device_status/_core.py:951`) —
  it is not behind any `if self._capability...` gate (contrast the block
  starting at `_core.py:956`, which is all capability-conditional).
- The generic `attributes` property loop
  (`_core.py:1460-1476`) calls `self._get_property(prop)` for every listed
  property; for `SCHEDULE` this returns the raw device string, which is
  non-`None` as soon as the device has ever reported the property (even as
  `""`).
- `_format_property_value` (`_core.py:1355-1356`) has a dedicated branch:
  `elif prop is DreameVacuumProperty.SCHEDULE: value = self.schedule` — this
  unconditionally replaces the raw string with the already-parsed
  `list[ScheduleTask]` (or `[]`). There is no capability gate and no early
  `return None, None` here (contrast `VOICE_ASSISTANT_LANGUAGE` at
  `_core.py:1249-1250`, which does gate on `self._capability.voice_assistant`).
- Back in the loop, `attributes[prop_name] = value` runs with
  `prop_name = "schedule"` (from `PROPERTY_TO_NAME[SCHEDULE.name] =
  ["schedule", "Schedule"]`, `custom_components/dreame_vacuum/dreame/const.py:688`).

So **`attributes["schedule"]` already exists today**, wired to the vacuum
entity via `self._attr_extra_state_attributes = self.device.status.attributes
or {}` in `_set_attrs` (`custom_components/dreame_vacuum/vacuum.py:309`),
which runs on every device update. This is confirmed directly by two existing
tests that assert on it: `tests/test_device_status_core.py:3299` /`:3315`
(`status.schedule = [{"id": 1}]` → `attributes["schedule"] == [{"id": 1}]`)
and `tests/test_device_status_core.py:3414` / `:3430` (same assertion in a
richer fixture).

In real operation the value is a `list[ScheduleTask]` (dataclass instances),
not a list of plain dicts — but that distinction mostly disappears at HA's
serialization boundary: `ScheduleTask.as_dict()` means Home Assistant's own
JSON encoder already converts it transparently. Confirmed directly against
the installed `homeassistant==2026.1.2` package,
`homeassistant/helpers/json.py::json_encoder_default`:

```python
def json_encoder_default(obj: Any) -> Any:
    ...
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    ...
```

This is the same `hasattr(obj, "as_dict")` duck-typing used throughout Home
Assistant core (recorder, websocket API, REST API all route through this or
the older `homeassistant.helpers.json.JSONEncoder`, which has the identical
check). So frontend/history/template consumers of the `schedule` attribute
already receive plain dicts with the same keys `as_dict()` would produce
(`id`, `enabled`, `invalid`, `time`, `repeats`, `once`, `map_id`,
`suction_level`, `water_volume`, `options`) — only in-process Python code
holding the raw `EntityState` object before serialization would see
dataclass instances.

Recorder exclusion: also contrary to the plan's framing, neither the
existing `"schedule"` key nor `ATTR_DND` (`"dnd"`) is currently present in
`VACUUM_UNRECORDED_ATTRIBUTES`
(`custom_components/dreame_vacuum/recorder.py:154-344`) — so schedule state
is, today, already recorded to history, same as DND. There is no
pre-existing exclusion to mirror.

### Why this stops Step 2 here

This matches the plan's own listed STOP condition verbatim: *"`SCHEDULE`
turns out to already reach the attributes via the generic property loop
(Step 2's check) — then the work is renaming/structuring an existing
attribute, which is a breaking change for users; report before touching
it."* Concretely, doing Step 2 as specified would mean:

- Either introducing `ATTR_SCHEDULE = "schedule"` (same string) and having
  `_add_state_attributes` set it explicitly via `.as_dict()` — which changes
  *where* the value is produced (moving from the generic per-property loop
  to the capability-attributes block) and *what shape* the in-memory value
  has (list of dicts instead of list of dataclasses) before serialization.
  This is a behavior change for anyone consuming the attribute from Python
  (templates, other integrations) even though the JSON-serialized shape for
  most consumers is unaffected.
- Or picking a different constant name/value for `ATTR_SCHEDULE`, which
  would mean the attribute now appears under two different keys
  simultaneously (the existing generic-loop `"schedule"` key is still
  populated unless the property is also removed from
  `_build_property_list()`), or silently renames a key existing automations/
  dashboards may already reference.
- Adding `"schedule"` (or a new `ATTR_SCHEDULE` constant) to
  `VACUUM_UNRECORDED_ATTRIBUTES` would change recorder behavior for an
  attribute that has been recorded since this property was added to the
  properties list — a user-visible history change that deserves its own
  decision, not a side effect of "adding a missing attribute."

No code was changed in `_core.py`, `const.py`, or `recorder.py` as a result.
This finding, and the recommendation below, are handed off for a
follow-up plan to decide on explicitly (rather than silently reshaping
existing behavior here):

**Recommendation for the follow-up plan:** treat this as "normalize/clean up
an existing attribute" work, not "add a new attribute." Concretely: keep the
same `"schedule"` key (do not introduce a second key), decide deliberately
whether the in-memory (pre-serialization) shape should switch from
`list[ScheduleTask]` to `list[dict]` via explicit `.as_dict()` (probably
yes, for consistency with how `ATTR_DND`/`ATTR_SHORTCUTS` are built at
`_core.py:1364-1389`, and to fix the `options` field's `str | None` vs.
actual-`list[str]` type annotation mismatch noted above at the same time),
and decide separately (with the user) whether to newly exclude `"schedule"`
from recorder history now that its shape is dict-based, matching the
"device config, not history-worthy" reasoning this plan started from.

## `delete_schedule` (write, already implemented)

`custom_components/dreame_vacuum/dreame/device_actions.py:286-321`:

1. Looks up the task by `id` in `self.status.schedule` (string-compared);
   raises `InvalidActionException` if not found (`:288-295`).
2. Re-fetches the **raw** `SCHEDULE` property string, splits on `;`/`-`
   exactly like the parser, and rebuilds the string with the matching task
   removed (`:297-306`), then writes it back via `set_property`
   (`:307`) — i.e. it manipulates the wire string directly rather than
   reusing `_schedule_changed`'s parsed model.
3. Calls `DreameVacuumAction.DELETE_SCHEDULE`
   (`vacuum_types.py:1348`, `siid: 8, aiid: 1` at `vacuum_types.py:1645`)
   with a single parameter: `piid = PIID(DreameVacuumProperty.SCHEDULE_ID,
   self.property_mapping)`, `value = schedule_id` (`:309-317`).
4. Forces a schedule refresh (`schedule_update(3, True)`, `:318`) and, if the
   action response is missing or non-zero `code`, rolls back the local
   `SCHEDULE` property to the pre-edit raw string (`:319-320`).

## `SCHEDULE_ID` / `SCHEDULE_CANCEL_REASON`

`vacuum_types.py:1116-1117`:

```python
SCHEDULE_ID = 106
SCHEDULE_CANCEL_REASON = 107
```

- `SCHEDULE_ID` (`siid: 8, piid: 3`, `vacuum_types.py:1480`) is **write-only**:
  explicitly removed from `_default_properties`
  (`custom_components/dreame_vacuum/dreame/device.py:244-248`, with the
  comment "Remove write only and response only properties from default
  list"). It exists purely as the piid parameter for the
  `DELETE_SCHEDULE` action call above — it is never polled or read.
- `SCHEDULE_CANCEL_REASON` (`siid: 8, piid: 4`, `vacuum_types.py:1481`) **is**
  polled (appears in the periodic property-refresh list at
  `device.py:1166`), but has **no dedicated listener** anywhere in
  `device.py`, and does not appear in `_core.py`'s property list or any
  attribute. It is currently read from the device and discarded — never
  surfaced to HA in any form. Its exact meaning is unconfirmed from this
  codebase (**inference only**: the name suggests it reports why the most
  recent scheduled/action task was cancelled by the firmware — e.g. low
  battery, error, manual override — but nothing in this repo decodes or
  exposes it, so this is a guess, not a confirmed mapping).

## `SCHEDULE` write validation (already implemented, not exposed as a service)

`custom_components/dreame_vacuum/dreame/device_setters.py:392-412`
(`elif prop is DreameVacuumProperty.SCHEDULE:  # Schedule uses string format,
not a HA service`):

- An empty string (`""`) is treated as **valid** — it means "clear the
  schedule" (comment at `:410-411`: *"Flag-only marker: an empty string is a
  valid payload here (it clears the schedule), so do not store the falsy
  value"*). This was the fix from the prior bug-fix campaign referenced in
  the plan.
- A non-empty value is validated per `;`-separated task: split on `-`,
  require at least 9 fields (`:398`), `id = int(props[0])` must be
  truthy/non-zero (`:401-404`), and `time = props[2]` must contain `":"`
  (`:405-408`). This mirrors the parser's field-count check but does **not**
  independently validate `suction_level`/`water_volume`/`options` ranges —
  only structural shape (field count, non-zero id, colon in time).
- This is a generic `set_property`-level guard, not a dedicated method —
  there is no `set_schedule(...)` helper analogous to `delete_schedule`;
  callers must build the full `;`/`-` string themselves today.

## Proposed write services (design only — not built in this change)

Two services, following the plan's scoping. Neither is implemented here;
`services.py` / `services.yaml` / translations are untouched.

### `dreame_vacuum.vacuum_delete_schedule` — lowest risk, engine method exists

```yaml
vacuum_delete_schedule:
  target: {entity: {domain: vacuum, integration: dreame_vacuum}}
  fields:
    schedule_id:
      required: true
      selector: {number: {mode: box, min: 0}}
```

Maps directly to the existing, complete `delete_schedule(schedule_id)`
(`device_actions.py:286-321`) — no new engine logic needed, only the HA
service plumbing (schema, `services.yaml` entry, translations, dispatch in
`services.py`, and a service-level test). Recommended as the first write
service to ship, precisely because it reuses a code path that already
round-trips against the device correctly (delete is exercised by
`tests/test_device_actions.py`).

### `dreame_vacuum.vacuum_set_schedule` (add/edit) — needs a live-device round-trip before shipping

Proposed schema, derived from the parser/validator above:

```yaml
vacuum_set_schedule:
  target: {entity: {domain: vacuum, integration: dreame_vacuum}}
  fields:
    schedule_id:
      required: false   # omit to create a new task
      selector: {number: {mode: box, min: 0}}
    enabled:
      required: true
      selector: {boolean: {}}
    time:
      required: true      # "HH:MM"
      selector: {text: {}}
    repeats:
      required: false     # opaque today — pass-through string, see Unconfirmed above
      selector: {text: {}}
    once:
      required: false
      default: false
      selector: {boolean: {}}
    map_id:
      required: false
      selector: {text: {}}
    suction_level:
      required: false
      selector: {number: {mode: box, min: 0}}
    water_volume:
      required: false
      selector: {number: {mode: box, min: 0}}
```

Validation rules to enforce client-side (derived directly from
`device_setters.py:392-412` and the parser at `device.py:1484-1517`), before
ever writing to the wire:

- `time` must match `HH:MM` (reuse the existing regex pattern used for DnD,
  `device_setters.py:453`: `([0-1][0-9]|2[0-3]):[0-5][0-9]$`, since the
  schedule setter itself only checks for the presence of `":"`, not full
  format — this proposal is stricter than today's minimal guard).
  `id` must be a positive, non-zero integer; when `schedule_id` is omitted
  (create), assign one following the same "opaque id, no proven
  contiguity" caution documented above for the read side.
- `repeats` and `options` must be treated as opaque pass-through values (no
  encoding/decoding attempted) **unless** a live-device capture confirms
  their format — do not invent an encoding.
- Rebuilding the whole `;`-joined string (append/replace one task, keep all
  others byte-identical) is safer than assembling every task from scratch,
  to avoid corrupting fields this integration doesn't understand (e.g.
  `repeats`, `options`) for *other* tasks in the same list.

**Why this is deliberately not built yet:** a malformed string written to
`DreameVacuumProperty.SCHEDULE` can clear *all* schedules (the setter
accepts `""` as "valid" specifically to support clearing — see above), and
the exact encoding of `repeats`/`options` is unconfirmed from static
analysis alone. Shipping `vacuum_set_schedule` needs a live-device
round-trip test (write a known task, read back the raw property, confirm
byte-for-byte reconstruction of untouched sibling tasks) before it's safe to
expose as a public HA service.
