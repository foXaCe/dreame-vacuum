# Live camera streaming — feasibility spike

## Status

Investigation only. No code in this change. Written to size the "Live camera
streaming" README To-Do item, which currently carries no estimate and no
evidence of what it would actually take.

## Verdict (up front)

**Not feasible as a `Camera.stream_source()` implementation with the current
protocol evidence. Sizing: L-or-never, and likely never without a live
device capture.** The engine already tracks a session lifecycle
(`stream_session` / `stream_status`) driven by a cloud-relayed handshake, but
no property or action anywhere in the codebase yields a URL, host/port, or
any connection descriptor a media player could consume. Recommendation:
**keep the item on the To-Do list but re-word it to reflect the real
blocker** (see recommendation section) rather than drop it — the current
wording implies simple wiring work, which this spike shows is false.

## 1. What the engine already has (Step 1 — code, confirmed)

### Property surface

`DreameVacuumProperty` (`custom_components/dreame_vacuum/dreame/vacuum_types.py:1237-1257`)
defines a `siid: 10001` property block (ids 227-251) that mixes stream
control with unrelated camera-adjacent features. Exact ids, confirmed by
reading the enum (the plan's estimate of "228-245" was close but the block
also interleaves `TAKE_PHOTO`, `CAMERA_LIGHT_BRIGHTNESS`, `CAMERA_LIGHT`,
`STEAM_HUMAN_FOLLOW`, `OBSTACLE_VIDEO_STATUS/DATA` — all `siid: 10001` too):

| Property | id | piid | Notes |
|---|---|---|---|
| `STREAM_STATUS` | 227 | 1 | read; JSON session/operation blob (see below) |
| `STREAM_AUDIO` | 228 | 2 | write-only (excluded from default poll list) |
| `STREAM_RECORD` | 229 | 4 | write-only |
| `TAKE_PHOTO` | 230 | 5 | write-only |
| `STREAM_KEEP_ALIVE` | 231 | 6 | write-only |
| `STREAM_FAULT` | 232 | 7 | write-only |
| `CAMERA_LIGHT_BRIGHTNESS` | 233 | 9 | read/write, unrelated to A/V transport |
| `CAMERA_LIGHT` | 234 | 10 | read/write, unrelated to A/V transport |
| `STREAM_VENDOR` | 235 | 11 | never read anywhere in `custom_components/` |
| `STREAM_PROPERTY` | 236 | 99 | write channel used by `set_camera_light_brightness` (see below) |
| `STREAM_CRUISE_POINT` | 237 | 101 | write-only |
| `STREAM_TASK` | 238 | 103 | write-only |
| `STEAM_HUMAN_FOLLOW` | 239 | 110 | (sic — typo in upstream/vendor name), never read |
| `OBSTACLE_VIDEO_STATUS` | 240 | 111 | never read |
| `OBSTACLE_VIDEO_DATA` | 241 | 112 | never read |
| `STREAM_UPLOAD` | 242 | 1003 | write-only |
| `STREAM_CODE` | 243 | 1100 | write-only |
| `STREAM_SET_CODE` | 244 | 1101 | write-only |
| `STREAM_VERIFY_CODE` | 245 | 1102 | write-only |
| `STREAM_RESET_CODE` | 246 | 1103 | write-only |
| `STREAM_SPACE` | 247 | 2003 | never read |

Mapping table: `vacuum_types.py:1605-1625`. The "write-only" designation in
the table above is confirmed by `custom_components/dreame_vacuum/dreame/device.py:244-296`
— a comment-labeled `# Remove write only and response only properties from
default list` block that excludes exactly these properties
(`STREAM_KEEP_ALIVE`, `STREAM_UPLOAD`, `STREAM_AUDIO`, `STREAM_RECORD`,
`STREAM_CODE`, `STREAM_SET_CODE`, `STREAM_VERIFY_CODE`,
`STREAM_RESET_CODE`, `STREAM_CRUISE_POINT`, `STREAM_FAULT`, `STREAM_TASK`,
`TAKE_PHOTO`, `STEAM_HUMAN_FOLLOW`) from the device's default polled
property set — i.e. the device firmware itself treats them as
request/response, not periodically-reported state.

There is a **second, distinct** `STREAM_*` set on `DreameVacuumAction`
(`vacuum_types.py:1365-1368`, mapped at `:1662-1665`, all `siid: 10001`):
`STREAM_VIDEO` (aiid 1), `STREAM_AUDIO` (aiid 2), `STREAM_PROPERTY` (aiid 3),
`STREAM_CODE` (aiid 4). These are MIoT *actions* (RPC-style calls), separate
from the *properties* of the same name above.

### The only payload we can see: `STREAM_STATUS`

`custom_components/dreame_vacuum/dreame/device.py:1519-1537`
(`_stream_status_changed`) is the entire consumer of `STREAM_STATUS`. It
parses the property value as JSON and, when `result == 0`, does two things:

```python
self.status.stream_session = stream_status.get("session")
```
and maps `operType`/`operation` — string values `"end"`, `"start"` combined
with `"monitor"`, `"intercom"`, `"recordVideo"` — onto
`DreameVacuumStreamStatus` (`vacuum_types.py:856-863`: `IDLE`, `VIDEO`,
`AUDIO`, `RECORDING`).

This is the full extent of what the property tells us: a session **token**
(opaque string/number, never a URL) and a coarse state machine (idle →
video/audio/recording → idle). No IP, port, RTSP/HTTP URL, ICE candidate, or
any transport descriptor appears anywhere in this payload or in any other
property. `status.stream_session` (`device_status/_core.py:272`, init) has
exactly these five references in the whole codebase, confirmed by
`grep -rn "stream_session" custom_components/`:
- `device.py:1524` (written, from `STREAM_STATUS` JSON)
- `device_actions.py:138` (read, re-sent as a request parameter — see below)
- `device_status/_core.py:272` (init to `None`)
- `vacuum_types.py:1765`, `:1950` (capability/availability gates, not transport use)

### Consumers of the STREAM_* action/property machinery (audited exhaustively)

`custom_components/dreame_vacuum/dreame/device_actions.py:121-149` defines:
- `call_stream_audio_action` → calls `STREAM_AUDIO` action
- `call_stream_video_action` → calls `STREAM_VIDEO` action
- `call_stream_property_action` → calls `STREAM_PROPERTY` action
- `call_stream_action` (shared helper) — builds `{"session": self.status.stream_session, ...params}` as the action payload

Grepped every caller in the repo (`grep -rn "call_stream_video_action\|call_stream_audio_action\|call_stream_property_action" custom_components/`):
- `call_stream_video_action` and `call_stream_audio_action`: **zero callers**.
  They are dead scaffolding — defined, never invoked from any entity
  platform (`vacuum.py`, `camera.py`, `button.py`, `switch.py`, etc. never
  reference them).
- `call_stream_property_action`: **one caller** —
  `custom_components/dreame_vacuum/dreame/device_setters.py:1027-1039`
  (`set_camera_light_brightness`). This sets the camera light's brightness
  by piggy-backing the write on the stream-property action (passing
  `{"session": ..., "value": str(brightness)}` with
  `piid=PIID(CAMERA_LIGHT_BRIGHTNESS)`). This is a **settings write**, not
  video/audio consumption — it never touches a media payload.

The `stream_status` sensor
(`custom_components/dreame_vacuum/sensor.py:149-154`) is the only other
consumer: a read-only `sensor.<vacuum>_stream_status` entity, gated on
`device.capability.camera_streaming`, that shows an icon
(`mdi:webcam`/`mdi:cctv`/`mdi:microphone`/`mdi:record-rec`,
`sensor.py:47-52`) for the four `DreameVacuumStreamStatus` states. It
reports *that* a stream session is active/idle — never *how* to reach it.

**Net finding**: the STREAM_* surface implements (a) a status readout and
(b) a settings-write side-channel (camera light brightness) that happens to
ride over the same action id as the (unused) video/audio session actions.
Nothing in the codebase requests, opens, or decodes an actual media
connection. This does **not** trigger the plan's first STOP condition
("STREAM_* properties turn out to be consumed... in a way that already
implements part of a session") — the session *token* is threaded through,
but no media transport is ever established or read.

### `camera_streaming` capability — what it actually gates

`camera_streaming` is a per-model capability flag, defaulted `False` at
`vacuum_types.py:2384` and set from the device capability table at load time
(`vacuum_types.py:2473-2481`). It is **not** derived from anything
stream-protocol-related; it gates unrelated feature surfaces:

- `fill_light` (camera light auto-switch) — `vacuum_types.py:2487-2492`
- `cruising` (patrol-to-point navigation) — `vacuum_types.py:2584-2591`
- `camera_light_brightness` status property — `device_status/_core.py:442-448`
- AI obstacle/pet-detection auto-switch settings exposure —
  `device_status/_core.py:1091-1100`
- `disable_sensor_cleaning` logic — `vacuum_types.py:2513-2520`
- forced `False` for Mijia/`xiaomi.vacuum.*` models —
  `vacuum_types.py:2541-2550`

None of these branches touch video/audio transport. The capability name is
inherited from the vendor's internal feature table and is best read as
"this model has an onboard camera with a light" rather than "this
integration can stream video."

### The existing `camera.py` entity is unrelated

`custom_components/dreame_vacuum/camera.py` implements
`DreameVacuumCameraEntity` — a `Camera` platform entity that renders the
**cleaning map** as PNG/MJPEG (`async_camera_image` at `:550`,
`handle_async_still_stream` at `:583`, a still-image multipart stream of
map renders — see `CONTENT_TYPE_MULTIPART` import). There is no
`stream_source()` method anywhere in the file
(confirmed: `grep -n "stream_source" custom_components/dreame_vacuum/camera.py` → no hits).
This entity is the map camera family (`camera.<vacuum>`,
`camera.<vacuum>_map_1` etc. per `docs/dev/dnd-tasks-design.md`-style
entities doc), unrelated to the onboard physical camera.

## 2. Vendor transport (Steps 2-3 — evidence quality noted per finding)

### Step 2: local vendor assets (evidence quality: weak/inferred)

This worktree does **not** contain `dreame_assets/` or `*.apks` — confirmed
absent (gitignored, as the plan anticipated). Per the plan, I grepped the
**main repo checkout** read-only (no writes made there):
`/mnt/39c0f0e6-4018-4aa1-8d96-24720083fa77/Codage/GitHub/dreame/dreame-vacuum/dreame_assets/`.

That directory contains only extracted **resources** — 1633 PNGs, 119 JSON
locale/animation files, 24 mp4s, no decompiled code, no `.so` libs, no
manifest. Per the plan's constraint ("strings and config files only; do NOT
decompile bytecode"), I did not touch the sibling `com.dreame.smartlife_*.apks`
bundle beyond confirming its presence — unpacking it further would mean
inspecting native libraries/bytecode to find an SDK name, which is out of
scope here.

Grepping the locale JSON (`projects_dreamevacuumcommon_src_resources_string_en.json`)
for camera/stream/audio copy turned up real UI strings confirming the
**vendor app** has a working live-view feature:
- `"monitorTasking": "Camera monitoring..."`
- `"monitorTaskPause": "Camera monitoring paused."`
- `"errorCameraFault": "Error. Restart your robot and try again."`
- `"audioInterceptTip": "Enabling a voice call will suspend the cleaning task. Continue enabling?"`
- `"recordInterceptTip": "Recording completed. Save and upload the video?"`

These strings corroborate the `monitor`/`intercom`/`recordVideo` operation
vocabulary seen in `_stream_status_changed` (Section 1) — i.e., the vendor
app really does drive video, two-way audio, and recording through this same
property/action surface. **No SDK/vendor name** (e.g. Agora, TUTK) appears
in any resource string, filename, or JSON config accessible without
decompiling — that data point remains **unknown** from this repo's local
assets.

### Step 3: prior art (web search/fetch available; evidence quality: confirmed where cited)

- Upstream maintainer, directly asked about camera streaming for a D10s Pro
  on the Dreamehome (cloud) account: **"Camera streaming is not possible
  yet."** Also: "Cloud connection is required with the Dreamehome account."
  — [Dreamehome Account Support · Tasshack/dreame-vacuum · Discussion #109](https://github.com/Tasshack/dreame-vacuum/discussions/109)
- Upstream's own `docs/entities.md` documents camera entities as **map
  images only** ("Live map image", saved-map snapshots); no mention of
  video/audio streaming — [entities.md](https://github.com/Tasshack/dreame-vacuum/blob/master/docs/entities.md)
- A user attempting to feed a Dreame "camera" into go2rtc for
  HomeKit/RTSP found only an **MJPEG** feed (consistent with the map-image
  camera in Section 1, not a physical video feed) and could not get
  HomeKit streaming to work — [Can't get camera from vacuum bot to work in go2rtc · Issue #1615](https://github.com/AlexxIT/go2rtc/issues/1615)
- A separate, unrelated bug (`_webrtc_provider` `AttributeError`) was a
  Home Assistant Camera base-class compatibility issue on the **map**
  camera entities, not the onboard physical camera —
  [Issue #787](https://github.com/Tasshack/dreame-vacuum/issues/787)
- `Uberi/dreame-maploader-web-ui` implements browser-based video streaming
  from a Dreame robot's onboard camera, but **only after replacing the
  firmware with Valetudo** (requires rooting the robot) and explicitly
  works around Valetudo's own policy: **"Valetudo also intentionally
  doesn't support video streaming from a robot's onboard cameras, for
  security reasons."** — [Uberi/dreame-maploader-web-ui](https://github.com/Uberi/dreame-maploader-web-ui)
- No evidence found (search performed against 2026 results) of upstream
  Tasshack/dreame-vacuum having since shipped real onboard-camera video
  streaming; the maintainer's "not possible yet" statement appears to still
  hold.

Taken together: the hardware plainly has a working onboard camera used by
the vendor app for monitoring/intercom/recording (Step 2 evidence,
corroborated by Step 1's code), but every independent party that has looked
at extracting that stream through the **stock cloud firmware** — this
integration's maintainer, a go2rtc user, and even the maximally-permissive
Valetudo alternative-firmware ecosystem — has either failed, found it
infeasible, or deliberately declined to support it. This is consistent with
a proprietary cloud-relayed P2P/session protocol (the `session` token +
start/end handshake we see in code strongly resembles this class of vendor
SDK, e.g. Agora/TUTK-style IoT camera SDKs), though the **specific SDK name
is unknown** — that would require decompiling the APK's native code, which
is out of scope for this spike.

## 3. Honest sizing of an HA `stream_source()` implementation

**Verdict: not feasible today; if it ever becomes feasible, it's L, not
S/M.**

- If `stream_session` yielded a directly-playable URL (RTSP/HLS/HTTP), this
  would be S/M: implement `Camera.stream_source()` to request a session via
  `STREAM_VIDEO`/`call_stream_video_action` (already scaffolded, just
  unused), parse the URL out of the response, hand it to HA's stream
  component. That is **not** what the evidence shows.
- What the evidence actually shows is a **session-token handshake with no
  connection descriptor** ever appearing in any property this integration
  can read. Implementing playback would require, at minimum: (1) reverse
  engineering the actual wire protocol the vendor app uses once it has a
  `session` (almost certainly a proprietary P2P/relay client, not a
  standard media protocol, going by the go2rtc/Valetudo prior art), (2)
  either reimplementing that client in Python/HA or embedding a vendor SDK
  (likely closed-source, C/native, licensed per-app — not redistributable
  in a HACS integration), and (3) bridging whatever that yields into
  something HA's `Camera`/`stream` component can consume. That is squarely
  **L, with a real chance of "never"** if the vendor SDK is closed-source
  and not embeddable in a Python HA integration (the common case for
  Agora/TUTK-style consumer IoT camera SDKs).
- A live-device follow-up (out of scope for this spike, noted per the
  plan) that would actually move this forward: capture the vendor app's
  network traffic while starting a "Camera monitoring" session, to observe
  whether the relay handshake resolves to any conventional media transport
  or is pure proprietary P2P. Without that capture, this stays "unknown but
  looks like proprietary P2P," not "confirmed."

## 4. Privacy note

A live in-home camera feed is a materially stronger privacy surface than
the existing static map camera:

- The map camera renders processed geometry (rooms/walls/paths); a live
  video/audio feed would expose real-time video and, per the vendor
  strings found in Step 2, **two-way audio** ("voice call") and **local
  recording with cloud upload** of the user's home interior.
- Any HA-side implementation would need explicit, per-user opt-in (not
  auto-created on integration setup, unlike most entities here), a clear
  warning in the config flow / entity description about what the feed
  shows, and should very likely default the corresponding entities to
  disabled — mirroring how sensitive entities are already gated in this
  integration (e.g. consumable/status entities disabled by default per the
  Discussion #109 note).
- If the transport does turn out to be a vendor cloud relay (P2P/Agora/TUTK
  style, per Section 2's inference), video would transit vendor cloud
  infrastructure exactly as it does in the official app today — this
  integration would not make that better or worse, but should say so
  explicitly in any docs/config flow copy so users aren't surprised.

## 5. Recommendation

**Keep on the To-Do list, but re-size and re-word it** so it no longer
reads as unsized, approachable work. Suggested README wording (applied in
this change):

`- Live camera streaming (spike: see docs/dev/streaming-spike.md — size L-or-never, blocked on proprietary transport; see doc)`

Do not schedule implementation work against this item until a live-device
network capture (see Section 3) either (a) finds a conventional media URL
inside the handshake — in which case, re-open at S/M — or (b) confirms a
closed vendor SDK is required, in which case this should be re-labeled
"blocked, not feasible" rather than a sizeable To-Do.
