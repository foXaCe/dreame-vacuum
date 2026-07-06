# Camera HTTP + Attribute Contract

> **Status: draft — pending maintainer confirmation.**
> This document is derived by reading the current source of
> `custom_components/dreame_vacuum/camera_views.py`,
> `custom_components/dreame_vacuum/camera.py`,
> `custom_components/dreame_vacuum/recorder.py` and
> `custom_components/dreame_vacuum/dreame/vacuum_types.py`. Every statement
> below cites the file and line(s) it was read from. It is not a design
> aspiration — it is a description of what the code does today.

## Audience and stability

This is the wire format the companion
[`foXaCe/dreame-vacuum-card`](https://github.com/foXaCe/dreame-vacuum-card)
consumes: 7 process-global HTTP views plus the camera entities' state
attributes. Nothing in this integration versions that surface today — the
views have no version header/param, and the attribute payload is whatever
`extra_state_attributes` happens to return. Both sides currently evolve in
lockstep because one person maintains both repos.

Proposed policy (not yet enforced by code or tests — flag this to the
maintainer):

> This surface is semver-minor-stable: keys and query parameters are only
> **added**, never renamed or removed, within a major version of the
> integration. A breaking change requires a major version bump and a note in
> the changelog stub below.

Two things already look like natural hooks for a future explicit version:

- `MapRendererData.version` (`custom_components/dreame_vacuum/dreame/vacuum_types.py:4616`)
  and `MapRendererResources.version` (`vacuum_types.py:4543`) are both
  hardcoded to `1` today and are never read anywhere else in the codebase —
  they are serialized into the JSON payloads described below but not
  currently used as a real version negotiation mechanism.
- No route or attribute carries an API version. If this contract is ever
  broken intentionally, bumping one of the two `version` fields above (or
  adding a new one) is the least invasive place to start.

Card-side consumption claims in this document that are not backed by reading
the card's source in this repository are marked **"consumer unverified"** —
this task was scoped to no network access, so the card repo itself was not
fetched.

## Auth model

None of the 7 views require a Home Assistant long-lived token by default
except `CameraResourcesView`. The other six subclass Home Assistant core's
`CameraView` (`homeassistant/components/camera/__init__.py:788`, verified
against the installed Home Assistant core 2026.7 package — this class ships
with HA core, not with this integration), which sets `requires_auth = False`
at the class level (`camera/__init__.py:791`) so the generic view dispatcher
(`homeassistant/helpers/http.py:51-76`) never blocks the request before it
reaches the view. `CameraView.get()` then does its own check
(`camera/__init__.py:797-825`):

```
authenticated = request[KEY_AUTHENTICATED] or request.query.get("token") in camera.access_tokens
```

So a `CameraView`-based route accepts **either**:

1. A normal authenticated HA request (browser session cookie or a
   long-lived access token / OAuth bearer in the `Authorization` header —
   whatever HA's auth middleware already validated and flagged
   `KEY_AUTHENTICATED` for), **or**
2. A `token=<value>` query parameter equal to one of the target camera
   entity's two most recently issued per-entity access tokens.

Per-entity tokens live in `self.access_tokens = collections.deque(maxlen=2)`
(`custom_components/dreame_vacuum/camera.py:330`) — a rolling window of the
current and previous token, so a URL fetched just before a rotation stays
valid for one more rotation cycle. Rotation cadence is controlled by
`DREAME_TOKEN_CHANGE_INTERVAL = timedelta(minutes=60)`
(`camera.py:90`, via the counter-based override in
`async_update_token()`, `camera.py:614-624`), which is deliberately longer
than the Home Assistant core default of 5 minutes
(`TOKEN_CHANGE_INTERVAL`, `homeassistant/components/camera/__init__.py:126`)
— the comment at `camera.py:88-89` explains this is to avoid invalidating
cached map-image URLs too often. Every image/JSON URL template embeds the
current token (`camera.py:92-96`, e.g. `MAP_IMAGE_URL`,
`HISTORY_MAP_IMAGE_URL`, `OBSTACLE_IMAGE_URL`, `RECOVERY_MAP_IMAGE_URL`,
`WIFI_MAP_IMAGE_URL`).

`CameraResourcesView(HomeAssistantView)` (`camera_views.py:255-284`) sets
`requires_auth = True` explicitly (`camera_views.py:261`) and does **not**
inherit `CameraView`, so it goes through the generic
`requires_auth` gate in `helpers/http.py:58` with no per-camera token
bypass: a request must already be an authenticated HA session/API call
before `get()` even runs. A `token=` query parameter is accepted by every
other view but has no effect here.

## The 7 HTTP views

All views are process-global singletons, registered once per Home Assistant
process by `async_register_camera_views()`
(`camera_views.py:287-304`), guarded by `hass.data[_VIEWS_REGISTERED_KEY]`
so re-adding a config entry or having multiple vacuums never double-registers
a route.

Two boolean-query-parameter parsers are shared by every view
(`camera_views.py:32-39`):

- `_query_bool(value)` — `None`/absent → `False`; `""`, `"true"`, `"1"`
  (case-insensitive) → `True`; anything else → `False`.
- `_query_bool_default_true(value)` — `None`/absent → `True`; `""`,
  `"true"`, `"1"` → `True`; anything else → `False`.

Filenames placed into `Content-Disposition` headers are sanitized by
`_safe_filename()` (`camera_views.py:45-54`): non `[A-Za-z0-9._-]`
characters are replaced with `_`, the result is truncated to 80 chars and
stripped of leading/trailing `.`/`_` — this exists specifically because
cloud-provided object names reach an HTTP header and could otherwise inject
CRLF/other header syntax.

---

### 1. `CameraDataView` — `/api/camera_map_data_proxy/{entity_id}`

Source: `camera_views.py:57-77`. Auth: `CameraView` (see above).

Serves the JSON representation of the map currently rendered by a **PNG**
camera entity (i.e. the `map`/`saved_map`/`wifi_map` entities — entities
where `camera.map_data_json` is `False`,
`camera.py:860-863`). If called against the dedicated `map_data`
(`DreameVacuumMapType.JSON_MAP_DATA`) entity, it returns `404`
(`camera_views.py:77`) — that entity instead serves its own alternate,
Valetudo-style PNG-with-embedded-JSON-text-chunk format through Home
Assistant's own stock `/api/camera_proxy/{entity_id}` route (rendered by
`DreameVacuumMapDataJsonRenderer.render_map()`,
`custom_components/dreame_vacuum/dreame/map_data_json_renderer.py:121-135`);
that format is out of scope for this document (see docs/map.md's "Valetudo
map card support" section) — **consumer unverified** either way, it wasn't
re-derived here beyond confirming which route serves it.

**Query parameters:**

| Name | Type | Default | Effect |
|---|---|---|---|
| `resources` | bool (`_query_bool`) | `false` | Include the icon/image resource bundle inline (see `MapRendererResources`, below) in the JSON payload's `resources` key. |

**Success response:** `200`, `content_type=application/json`,
`Content-Encoding: gzip` (body is always gzip-compressed,
`camera_views.py:72-75`). Body is the string returned by
`camera.map_data_string(include_resources)`
(`camera.py:783-796`), which — when the underlying map data exists — calls
`self._renderer.get_data_string(...)`
(`camera.py:790-795`, implemented at
`custom_components/dreame_vacuum/dreame/map_renderer/_core.py:569-1059`).
See "JSON map payload shape" below for the top-level keys. If there is no
current map data, the method returns the literal string `"{}"`
(`camera.py:796`).

**Error responses:** `404` if the entity is the `map_data` JSON-type camera
(`camera_views.py:77`).

**Side effects:** none beyond the render itself; if `map_index == 0`,
calling this endpoint also triggers `self.device.update_map()`
(`camera.py:787-789`) — i.e. hitting this URL for the live map can request a
fresh map update from the device.

---

### 2. `CameraObstacleView` — `/api/camera_map_obstacle_proxy/{entity_id}`

Source: `camera_views.py:80-110`. Auth: `CameraView`.

Serves a decrypted obstacle detection photo. Only works against the
**current** map entity (`camera.map_index == 0`,
`camera_views.py:91` / `camera.py:681`).

**Query parameters:**

| Name | Type | Default | Effect |
|---|---|---|---|
| `index` | str (numeric) | `1` | Obstacle key into `map_data.obstacles` (`camera.py:679-688` → `custom_components/dreame_vacuum/dreame/device_actions.py:1289-1295` → `map_manager.py:965-1017`). |
| `box` | bool (`_query_bool_default_true`) | `true` | Whether the renderer draws the AI detection bounding box over the image. |
| `crop` | bool (`_query_bool_default_true`) | `true` | Whether the image is cropped (vs. the full original photo). |
| `file` | bool (`_query_bool`) | `false` | Adds `Content-Disposition: attachment; filename="<safe-name>.jpg"` for downloads (`camera_views.py:105-107`). |

**Success response:** `200`, `content_type=image/jpeg`
(`DEFAULT_CONTENT_TYPE`, from HA core
`homeassistant/components/camera/__init__.py:123`). Raw JPEG bytes, no gzip.

**Error responses:** `404` when `map_index != 0`, when the device has no
matching obstacle, or when decryption/lookup fails
(`camera_views.py:110`, `map_manager.py:1011-1017` swallows decryption
exceptions and returns `(None, None)`).

**Side effects/caching:** results are cached per-entity in
`self._proxy_images["obstacle"]`
(`camera.py:832-853`, `_get_proxy_obstacle_image`), keyed by
`f"b{box}_c{crop}_d{obstacle.id}"`, holding at most 3 items
(`max_item=3` default, `camera.py:833`) — oldest entry evicted first
(dict insertion order, `camera.py:849-850`). Cache lives on the camera
entity instance, not process-global.

---

### 3. `CameraObstacleHistoryView` — `/api/camera_map_obstacle_history_proxy/{entity_id}`

Source: `camera_views.py:113-146`. Auth: `CameraView`. Same
`map_index == 0` restriction as view 2.

**Query parameters:**

| Name | Type | Default | Effect |
|---|---|---|---|
| `index` | str (numeric) | `1` | Obstacle key, as above, but resolved against the historical map. |
| `history_index` | str (numeric) | `1` | Which cleaning/cruising history entry to pull the map from (`camera.py:690-703` → `device_actions.py:1297-1303`). |
| `cruising` | bool (`_query_bool`) | `false` | Pull from cruising history instead of cleaning history. |
| `box` | bool (`_query_bool_default_true`) | `true` | Same as view 2. |
| `crop` | bool (`_query_bool_default_true`) | `true` | Same as view 2. |
| `file` | bool (`_query_bool`) | `false` | Same as view 2 (downloaded filename strips `.jpg`/`.jpeg` before re-appending `.jpg`, `camera_views.py:142`). |

**Success/error responses:** identical shape to view 2.

**Side effects/caching:** same cache dict, key `"obstacle_history"`, but
`max_item=1` (`camera.py:700-701`) — only the single most recent historical
obstacle image is kept, since history browsing rarely revisits the same
obstacle.

---

### 4. `CameraHistoryView` — `/api/camera_history_map_proxy/{entity_id}`

Source: `camera_views.py:149-182`. Auth: `CameraView`. Restricted to
non-JSON, current-map entities (`not camera.map_data_json and
camera.map_index == 0`, `camera_views.py:160` / `camera.py:709`).

**Query parameters:**

| Name | Type | Default | Effect |
|---|---|---|---|
| `index` | str (numeric) | `1` | Which cleaning/cruising history entry (`camera.py:705-722`). |
| `info` | bool (`_query_bool_default_true`) | `true` | `false` renders the map transparent with no header text. |
| `cruising` | bool (`_query_bool`) | `false` | Cruising history instead of cleaning history. |
| `data` | bool (`_query_bool`) | `false` | Return the JSON data string instead of a PNG. |
| `dirty` | bool (`_query_bool`) | `false` | Render the "dirty map" (CleanGenius/second-cleaning) variant when a PNG is requested and `cleaning_map_data` is present (`camera.py:712-715`). Ignored for cruising history. |
| `resources` | bool (`_query_bool`) | `false` | Only takes effect when `data=1`: embed the resource bundle in the JSON payload. |

**Success response:** if `data=1`: `200`,
`content_type=application/json`, gzip-encoded, body from
`_render_data_string()` (`camera.py:775-781`, same
`get_data_string` renderer as view 1). Otherwise: `200`,
`content_type=image/png`, raw bytes, no gzip.

**Error responses:** `404` if the entity is JSON-type, if `map_index != 0`,
or if no history map / render result is found (`camera_views.py:182`).

**Side effects/caching:** PNG branch caches via `_get_proxy_image()`
(`camera.py:817-830`), cache key `"cruising"` / `"dirty"` / `"cleaning"`
(`camera.py:718`), item key
`f"i{index}_t{int(info_text)}_d{int(map_data.last_updated)}"`,
`max_item=2` (default, `camera.py:817`).

---

### 5. `CameraRecoveryView` — `/api/camera_recovery_map_proxy/{entity_id}`

Source: `camera_views.py:185-223`. Auth: `CameraView`. Works for **both**
current and saved-map entities (no `map_index == 0` restriction), but not
for the JSON-type or Wi-Fi-map entities (`camera.py:724-726`,
`camera.py:738`).

**Query parameters:**

| Name | Type | Default | Effect |
|---|---|---|---|
| `index` | str (numeric) | `1` | Which recovery-map entry, 1-based (`camera.py:724-755` → `device_actions.py:1340-1356` → `map_manager.py:1050-1100+`). |
| `file` | bool (`_query_bool`) | `false` | Switches to file-download mode entirely (see below); mutually exclusive in effect with `data`/`info`/`resources`. |
| `info` | bool (`_query_bool_default_true`) | `true` | (Only when `file` is not set.) `false` renders transparent/no-header-text. |
| `data` | bool (`_query_bool`) | `false` | (Only when `file` is not set.) Return the JSON data string instead of PNG. |
| `resources` | bool (`_query_bool`) | `false` | Only takes effect when `data=1`. |

**File-download mode** (`camera_views.py:200-201, 217-219`): when `file=1`,
the handler calls `camera.recovery_map_file(index)`
(`camera.py:724-734`), which returns the raw `.mb.tbz2` archive bytes plus
an object name. Response: `200`,
`content_type=application/x-tar+gzip`, header
`Content-Disposition: attachment; filename="<safe-name>.mb.tbz2"` where
`<safe-name>` is the object name with `/` replaced by `-` and the
`.mb.tbz2` suffix stripped before re-appending it
(`camera_views.py:218`), no gzip re-encoding (the archive is already
compressed). Per `docs/map.md:353`, cloud storage does not retain these
files indefinitely — a renderable recovery map does not guarantee a
downloadable file exists.

**Non-file mode:** same PNG/JSON split as view 4 (`data=1` → gzip JSON via
`_render_data_string`; otherwise PNG via `_get_proxy_image`, cache key
`"recovery"`, `max_item=2` default).

**Error responses:** `404` if the entity is JSON-type or Wi-Fi-type, or if
no result is produced (e.g. cloud no longer has the file,
`camera_views.py:223`).

---

### 6. `CameraWifiView` — `/api/camera_wifi_map_proxy/{entity_id}`

Source: `camera_views.py:226-252`. Auth: `CameraView`. Same
not-JSON/not-Wi-Fi-entity restriction as view 5 (`camera.py:757-759`) — note
this proxy is called *against* the regular map camera entity to fetch *its*
associated Wi-Fi map data, not against the dedicated Wi-Fi camera entity
itself.

**Query parameters:**

| Name | Type | Default | Effect |
|---|---|---|---|
| `data` | bool (`_query_bool`) | `false` | Return JSON data string instead of PNG. |
| `resources` | bool (`_query_bool`) | `false` | Only takes effect when `data=1`. |

Note: unlike views 4 and 5, there is no `info` query parameter — the
renderer is always called with `info_text=False`
(`camera.py:771`, hardcoded), i.e. the Wi-Fi map image never has the header
text overlay.

**Success/error responses:** same PNG/JSON split pattern; `404` if the
entity has no associated Wi-Fi map data (`camera_views.py:252`). Cache key
`"wifi"`, `max_item=1` (`camera.py:772`) — only the latest Wi-Fi render is
kept.

---

### 7. `CameraResourcesView` — `/api/camera_resources_proxy/{entity_id}`

Source: `camera_views.py:255-284`. **Not** a `CameraView` — plain
`HomeAssistantView` with `requires_auth = True` (see Auth model above).
Restricted to non-JSON, current-map entities with a live `device`
(`camera_views.py:269-275`).

**Query parameters:**

| Name | Type | Default | Effect |
|---|---|---|---|
| `icon_set` | str (decimal digits) or absent | camera's configured icon set | Overrides which icon set (`0`/`1` = Dreame current/old, `2` = Mijia, `3` = Material — `custom_components/dreame_vacuum/dreame/map_renderer/_resources_props.py:103-148`) is used to build the resource bundle for this one request. Non-numeric values fall back to the configured default (`_resources_props.py:104-107`). |

**Success response:** `200`, `content_type=application/json`,
gzip-encoded. Body is `camera.resources(icon_set)`
(`camera.py:798-803`), which calls
`self._renderer.get_resources(self.device.capability, True, icon_set)`
(`as_json=True`). See "`MapRendererResources` shape" below for top-level
keys.

**Error responses:** `404` if the entity doesn't exist, is JSON-type, has
`map_index != 0`, or has no `device` (`camera_views.py:269-275`).

## JSON payload shapes (views 1, 4, 5, 6 in `data=1`/JSON mode; view 7)

Both JSON payload families are built by
`json.dumps(obj, default=lambda o: {k: v for k, v in o.__dict__.items() if v
is not None}, allow_nan=False, sort_keys=True, separators=(",", ":"))`
(`custom_components/dreame_vacuum/dreame/map_renderer/_core.py:1058-1061`
and `_resources_props.py:284-289`) — i.e. compact, alphabetically-sorted
keys, and any nested dataclass/object is flattened via its own `__dict__`
(non-`None` fields only), recursively.

### `MapRendererData` (views 1, 4, 5, 6 — the map JSON payload)

Dataclass at `vacuum_types.py:4547-4616`. Top-level fields (all optional /
omitted when `None` or falsy per the `default=` filter above): `data`,
`size`, `map_id`, `saved_map_id`, `map_index`, `saved_map_status`,
`empty_map`, `frame_id`, `saved_map`, `wifi_map`, `history_map`,
`recovery_map`, `segments`, `active_segments`, `active_areas`,
`active_points`, `active_cruise_points`, `task_cruise_points`,
`predefined_points`, `no_mop`, `no_go`, `carpets`, `ignored_carpets`,
`detected_carpets`, `virtual_walls`, `virtual_thresholds`,
`passable_thresholds`, `impassable_thresholds`, `ramps`, `curtains`,
`low_lying_areas`, `obstacles`, `furnitures`, `path`, `floor_material`,
`hidden_segments`, `neglected_segments`, `robot_position`,
`charger_position`, `router_position`, `ai_outborders_user`,
`ai_outborders`, `ai_outborders_new`, `ai_outborders_2d`,
`second_cleaning`, `mop_wash_count`, `dust_collection_count`,
`multiple_cleaning_time`, `dos`, `ai_furniture_warning`, `walls_info`,
`walls_info_new`, `furniture_version`, `startup_method`,
`cleanup_method`, `cleaned_area`, `cleaning_time`, `robot_status`,
`station_status`, `completed`, `remaining_battery`, `cleanset`,
`sequence`, `docked`, `work_status`, `resources` (nested
`MapRendererResources`, only when the `resources` query param was set),
`version` (currently always `1`).

**Important:** this JSON payload does **not** carry `wall_lines` /
`door_lines` (searched `map_renderer/_core.py` for both names — zero hits).
Those two fields, once exposed (see 009 below), only reach the **state
attribute** contract (`MapData.as_dict()`), not this wire format. A
consumer wanting vectorized wall/door geometry must read the camera entity's
`rooms`/attribute payload, not this JSON blob — it only carries the raw,
undecoded `walls_info`/`walls_info_new` fields.

### `MapRendererResources` (view 7, and embedded in `MapRendererData.resources`)

Dataclass at `vacuum_types.py:4502-4543`. Top-level fields: `renderer`,
`icon_set`, `robot_type`, `robot`, `charger`, `charging`, `cleaning`,
`warning`, `sleeping`, `cleaning_direction`, `selected_segment`,
`cruise_point_background`, `segment`, `default_map_image`, `font`,
`repeats`, `suction_level`, `water_volume`, `mop_pad_humidity`,
`cleaning_mode`, `cleaning_route`, `custom_mopping_route`, `washing`,
`hot_washing`, `drying`, `hot_drying`, `emptying`,
`cruise_path_point_background`, `obstacle_background`,
`obstacle_hidden_background`, `obstacle`, `furniture`, `rotate`,
`delete`, `resize`, `move`, `problem`, `clean`, `settings`, `wifi`,
`version` (currently always `1`). Most string-typed fields are data-URI
encoded images/icons.

## The attribute contract (`camera.extra_state_attributes`)

Source: `camera.py:907-1113`. Only the **PNG-type** camera entities expose
attributes at all — the JSON-type (`map_data`) entity's
`extra_state_attributes` always returns `None`
(guarded by `if not self.map_data_json:` at `camera.py:912`, falling
through to `return None` at `camera.py:1113`).

When the map is unavailable (`device.cloud_connected` false, or the map is
empty, or a live map that isn't located yet), the attributes dict is either
`{}` or just `{"calibration_points": <default calibration>}`
(`camera.py:985-989`).

### Keys always considered, regardless of map state

| Attribute key | Present when | Type | Source |
|---|---|---|---|
| `calibration_points` | Always (device present) | `list[dict]`, 3 entries of `{"vacuum": {"x", "y"}, "map": {"x", "y"}}` | `camera.py:926-928` / default shape at `map_renderer/_core.py:113-144` |
| `selected` | `map_index > 0` (saved-map entities only) | `bool` | `camera.py:991-994` |
| `color_scheme` | `map_index == 0` | `str \| None` | `camera.py:998` |
| `color_palette` | `map_index == 0` and renderer has a color scheme | `dict[int, list[int]]` (RGB triples, one per segment color index) | `camera.py:1000-1003` |
| `room_colors` | `map_index == 0`, color scheme + rooms present | `dict[str(room_id), list[int]]` (RGB triple) | `camera.py:1004-1012` |
| `cleaning_history_picture` | `map_index == 0` and cleaning history exists | `dict[str(label), str(url)]` — URL from `HISTORY_MAP_IMAGE_URL` template | `camera.py:1017-1029` |
| `cruising_history_picture` | `map_index == 0` and cruising history exists | same shape, `&cruising=1` appended | `camera.py:1031-1040` |
| `obstacle_picture` | `map_index == 0` and current map has obstacles (filtered by pet/fluid detection settings and picture status) | `dict[str(label), str(url)]` | `camera.py:1042-1077` |
| `recovery_map_picture` | map has a recovery map list | `dict[str(label), str(url)]` | `camera.py:1086-1097` |
| `recovery_map_file` | same as above | `dict[str(label), str(url)]` (`&file=1` appended) | `camera.py:1094-1097` |
| `wifi_map_picture` | map has associated Wi-Fi map data | `str(url)` | `camera.py:1105-1110` |

### Keys derived from the live/saved map (only when a valid, non-empty, located map exists — `camera.py:916-921`)

These come from `map_data.as_dict()` (`vacuum_types.py:3978-4058`) merged
into the attributes dict, plus a few added directly by `camera.py`:

| Attribute key (JSON name) | Python field | Present when | Type |
|---|---|---|---|
| `robot_in_map` | n/a (renderer config) | Renderer has a `config` attr | `bool` — whether the robot icon is baked into the PNG (`camera.py:930-936`) |
| `robot_icon` | n/a (renderer) | Renderer can produce one | `str` (data URI) — static top-view icon for the card's own overlay when `robot_in_map` is `false`; a "glow" variant is served while the fill light is on (`camera.py:938-948`) |
| `segment_map` | n/a (cached PNG) | Non-Wi-Fi map with `pixel_type`/`segments`, and the cache has been populated by a prior `async_camera_image()` poll | `str` (base64 PNG) — blue channel = room key pick-buffer (`camera.py:960-970`) |
| `rooms[*].segment_id` | injected into each room dict | A `segment_map` PNG was produced this cycle | `int` — raw pixel_type value for that room (`camera.py:975-983`) |
| `charger_position` | `charger_position` (optimized if available) | `charger_position is not None` | `Point.as_dict()` → `{"x", "y"}` |
| `custom_name` | `custom_name` | not None | `str` |
| `rooms` | `segments` | segments exist and (`saved_map` or `saved_map_status==2` or `restored_map`) | `dict[int, Segment.as_dict()]` — see "Segment shape" below |
| `vacuum_position` | `robot_position` | not `saved_map` and position known | `Point.as_dict()` → `{"x", "y"}` |
| `map_id` | `map_id` | truthy | `int` |
| `saved_map_id` | `saved_map_id` | truthy | `int` |
| `map_name` | `map_name` | not None | `str` |
| `rotation` | `rotation` | not None | `int` (degrees) |
| `updated_at` | `last_updated` | not None | `datetime` (HA's JSON encoder — see below — serializes via its own datetime handling) |
| `active_areas` | `active_areas` | not `saved_map` and not None | `list[Area.as_dict()]` |
| `active_segments` | `active_segments` | not `saved_map` and not None | `list[int]` |
| `active_points` | `active_points` | not `saved_map` and not None | `list[Point.as_dict()]` |
| `active_cruise_points` | `active_cruise_points` | not `saved_map` and not None | `dict[int, Coordinate]` |
| `predefined_points` | `predefined_points` | truthy | `list[Coordinate]` |
| `virtual_walls` | `virtual_walls` | not None | `list[Wall]` (raw objects — see "how objects serialize" below) |
| `wall_lines` | `wall_lines` | **not yet exposed on this branch** | see "Pending: 009" below |
| `door_lines` | `door_lines` | **not yet exposed on this branch** | see "Pending: 009" below |
| `virtual_thresholds` | `virtual_thresholds` | not None | `list[Wall]` |
| `passable_thresholds` | `passable_thresholds` | not None | `list[Wall]` |
| `impassable_thresholds` | `impassable_thresholds` | not None | `list[Wall]` |
| `ramps` | `ramps` | not None | `list[Area]` |
| `low_lying_areas` | `low_lying_areas` | not None | `list[Polygon]` |
| `no_go_areas` | `no_go_areas` | not None | `list[Area]` |
| `no_mopping_areas` | `no_mopping_areas` | not None | `list[Area]` |
| `carpets` | `carpets` | not None | `list[Carpet]` |
| `ignored_carpets` | `ignored_carpets` | not None | `list[Carpet]` |
| `detected_carpets` | `detected_carpets` | not None | `list[Carpet]` |
| `curtains` | `curtains` | not None | `list[Wall]` |
| `is_empty` | `empty_map` | not None | `bool` |
| `frame_id` | `frame_id` | truthy | `int` |
| `map_index` | `map_index` | truthy | `int` |
| `obstacles` | `obstacles` | truthy | `dict[str, Obstacle]` |
| `furnitures` | `furnitures` or `saved_furnitures` | either truthy | `list[Furniture]` |
| `router_position` | `router_position` | truthy | `Point` |
| `startup_method` | `startup_method` | truthy | `str` (title-cased enum name) |
| `dust_collection_count` | `dust_collection_count` | truthy | `int` |
| `mop_wash_count` | `mop_wash_count` | truthy | `int` |
| `recovery_map_list` | `recovery_map_list` | truthy | `list[RecoveryMapInfo.as_dict()]` (each `{"date", "map_type", "object_name"}`, `vacuum_types.py:3631-3638`) |

**How raw objects serialize:** fields like `virtual_walls`, `obstacles`,
`furnitures` are assigned as lists/dicts of live Python objects (`Wall`,
`Obstacle`, `Furniture`, `Point`, `Area`, ...), not pre-converted
dictionaries — unlike `rooms` and `recovery_map_list`, which explicitly call
`.as_dict()` (`vacuum_types.py:3989, 4057`). This works because Home
Assistant core's own `JSONEncoder.default()`
(`homeassistant/helpers/json.py:33-34`, installed HA core 2026.7 — not part
of this repo) calls `.as_dict()` automatically on any object that has one,
recursively, when serializing state attributes for the REST/WebSocket API.
Every geometry class here defines `as_dict()`
(`Point`: `vacuum_types.py:2622-2625`; `Wall`: `:3118-3119`; `Zone`/`Area`
base: `:2805-2806`; `Obstacle`: `:2747-2758`; `Segment`: `:2999-3053`) for
exactly this reason. A client reading attributes through anything other
than HA's own state API (e.g. a raw diagnostics dump or a custom serializer)
must call `.as_dict()` itself or it will see the live Python object, not a
plain dict.

### Segment (room) shape (`rooms[*]`, `Segment.as_dict()`, `vacuum_types.py:2999-3053`)

Fields present depend on what's set, but typically include: `x0, y0, x1,
y1` (bounding zone, from the `Zone` parent), `outline` (custom outline
points, if set), `room_id`, `name`, `custom_name`, `order`,
`cleaning_times`, `suction_level`, `water_volume`, `wetness_level`
(mop-cleanset-type gated), `cleaning_mode` (gated), `custom_mopping_route`
/ `cleaning_route` (mutually exclusive, cleanset-type gated), `type`,
`index`, `icon`, `color_index`, `unique_id`, `floor_material`,
`floor_material_direction`, `visibility`, `x`, `y` (room center, when
known). `segment_id` (raw pixel_type value) is injected separately by
`camera.py:975-983`, not by `Segment.as_dict()` itself.

### Recorder exclusion (`CAMERA_UNRECORDED_ATTRIBUTES`, `recorder.py:104-152`)

The following camera attribute keys are excluded from Home Assistant's
recorder database (`exclude_attributes()`, `recorder.py:347-350`) — they
either duplicate data better queried live, or are large map-geometry blobs
that would blow the recorder's per-attribute size limit:

`access_token`, `entity_picture`, `rooms`, `calibration_points`,
`selected`, `cleaning_history_picture`, `cruising_history_picture`,
`obstacle_picture`, `recovery_map_picture`, `recovery_map_file`,
`wifi_map_picture`, `vacuum_position`, `room_icon`, `rotation`,
`updated_at`, `frame_id`, `color_scheme`, `obstacles`, `furnitures`,
`virtual_walls`, `virtual_thresholds`, `passable_thresholds`,
`impassable_thresholds`, `no_go_areas`, `no_mopping_areas`, `carpets`,
`ignored_carpets`, `detected_carpets`, `curtains`, `ramps`,
`low_lying_areas`, `predefined_points`, `active_areas`, `active_points`,
`active_cruise_points`, `active_segments`, `charger_position`,
`recovery_map_list`, `room_colors`, `segment_map`, `custom_name`,
`map_id`, `saved_map_id`, `map_name`, `map_index`, `is_empty`.

Every large/geometry attribute key documented in the tables above is on
this list — with the sole exception of `wall_lines`/`door_lines`, which are
not yet exposed at all on this branch (see next section).

## Pending: `wall_lines` / `door_lines` (plan 009, branch `advisor/009-expose-walls-info`, commit `68a98cd`)

On this branch, `MapData.wall_lines` and `MapData.door_lines`
(`vacuum_types.py:3747-3750`) are already populated by the decoder (since
commit `5461398`) but **not yet exposed** through either `as_dict()` or the
recorder exclusion list — confirmed by reading `MapData.as_dict()`
(`vacuum_types.py:3978-4058`, no `wall_lines`/`door_lines` assignment) and
`CAMERA_UNRECORDED_ATTRIBUTES` (`recorder.py:104-152`, no `ATTR_WALL_LINES`/
`ATTR_DOOR_LINES` entries).

Commit `68a98cd` on branch `advisor/009-expose-walls-info` (not merged into
this branch's base) adds:

- `ATTR_WALL_LINES = "wall_lines"` / `ATTR_DOOR_LINES = "door_lines"`
  constants.
- Two new lines in `MapData.as_dict()`, right after the `virtual_walls`
  entry, following the same `if self.wall_lines is not None:` /
  `if self.door_lines is not None:` pattern as every other geometry field.
- Both keys added to `CAMERA_UNRECORDED_ATTRIBUTES`, alongside
  `virtual_walls` and the other large geometry attributes.
- Test coverage in `tests/test_walls_info.py` and `tests/test_recorder.py`.

Once merged, both keys join the "Keys derived from the live/saved map"
table above with type `list[Wall]` (same shape as `virtual_walls`:
`{"x0", "y0", "x1", "y1"}` per entry via `Wall.as_dict()`,
`vacuum_types.py:3118-3119`), present whenever the saved map's decoded
`walls_info` contained wall (type 0) or door (type 1) segments,
respectively. **This does not change the JSON wire format** (views 1, 4, 5,
6) — see the `MapRendererData` note above; `wall_lines`/`door_lines` only
ever reach consumers through the state-attribute contract.

## Changelog

| Date | Change |
|---|---|
| 2026-07-06 | Initial contract document (plan 017), covering the integration state as of commit `72ac377` plus the 004 (lazy icon warm-up) and 009 (`wall_lines`/`door_lines`, documented pending) changes. |
