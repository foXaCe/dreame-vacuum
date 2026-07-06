# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Exhaustive engine test suite**: 2 063 new behavioural tests
  (1 897 → 3 960, green in ~28 s), lifting coverage from 66 % to **98.8 %**
  (coverage floor raised 65 → 95). The campaign pinned 22 real pre-existing
  engine anomalies with tests documenting the current behaviour — see
  `docs/overhaul/known-issues-2026-07-06.md` (5 user-impacting ones flagged
  for priority follow-up).

### Changed
- **Cloud HTTP now runs on an async-native aiohttp transport** — `requests`
  is gone from the requirements. The new `dreame/http_client.py` hosts the
  async core (ready for Home Assistant's injected websession) behind a
  blocking facade with a private event loop, so the proven worker-thread
  protocol layer is untouched and Home Assistant's loop is never involved.
  This is step 1 of the incremental async migration (see ARCHITECTURE.md).
- Icon translations completed (Gold `icon-translations`): the 143 static
  `icon=` fields were removed from the entity descriptions — they were
  silently overriding the `icons.json` mechanism. Icons are unchanged
  visually; dynamic state-dependent icons stay in code.
- All user-facing command errors are now translatable (Gold
  `exception-translations`): the last raw `HomeAssistantError(str(exc))`
  sites raise `invalid_command` / `command_failed` with the device error as
  a placeholder (English + French shipped).
- `strings.json` is now sorted like the translation files; `strings.json`
  and `en.json` are structurally identical at full 957-key parity.
- Large internal modules split into focused mixins (no behaviour change):
  `device_status/_core.py` (2858 → 1489 lines) and
  `map_renderer/_core.py` (3920 → 2035 lines); the camera HTTP proxy views
  moved to `camera_views.py`; the per-room entity add/remove logic is now
  shared between the number and select platforms.
- Dev/CI environment aligned with HA 2026.7 (Python 3.14); the ruff ignore
  debt was paid off (F841/B006/B008/F507/F634/E712 re-enabled at zero
  violations, ~80 mechanical fixes for SIM118/B007/RET503 and friends).

### Fixed
- Map rendering: disabling the "stain" map object no longer hides every
  regular obstacle while leaving stains visible (the filter was inverted).
- Map rendering: the charger icon renders again with the Material icon set
  (an RGB/RGBA mismatch crashed the tint step, silently freezing the map).
- Map rendering: a failure during the very first render now falls back to
  the placeholder image instead of returning no image at all.
- Map recovery: restoring a saved map fetches the recovery file again — a
  missing helper made the restore silently do nothing when the raw map was
  not already cached.
- Schedule: clearing the schedule with an empty value works again instead
  of being rejected as invalid.

### Removed
- Dead commented-out map fields (`walls_info`/`ai_outborders_*`) in the map
  decoder and renderer.

### Changed
- Faster startup on warm boots: the integration now persists the device's
  answered-property inventory (model/firmware keyed) and only loads the
  priority batch (capability inputs + primary state) synchronously during
  the first refresh; the remaining properties load in the background while
  their entities stay unavailable until the first value arrives — the exact
  timeline they had before. Measured on the same network window: entry
  setup 10.7 s → 5.8 s (≈3.5-4 s under normal cloud latency). First setup
  and firmware changes keep the full synchronous load.

### Fixed
- Cloud request ids are now allocated atomically: concurrent requests
  (MQTT push handling, polling, entity commands) could share the same id
  and the Dreame cloud silently rejected the duplicate (empty result).

## [6.6.0] - 2026-07-02

### Changed
- **Minimum Home Assistant raised to 2025.8** (hacs.json).
- Options flow migrated to `OptionsFlowWithReload`: the deprecated
  constructor pattern and the manual reload update-listener are gone;
  options changes still reload the entry automatically.
- Config and options flows now use modern selectors (password-typed
  credential fields, dropdowns for country/color scheme/icon set/device,
  proper multi-selects for notifications and hidden map objects).
- Cloud retry backoff gained jitter and is shared
  (`resilience.backoff_delay`) instead of being duplicated inline.
- DEBUG logs no longer dump full HTTP bodies or raw map payloads
  (truncated / summarized).
- MQTT callbacks migrated to paho `CallbackAPIVersion.VERSION2` (the v1
  API is removed in paho 3.0); the auth-refused relogin now happens in
  `on_connect`, where the v2 reason code is precise. `paho-mqtt` stays
  pinned `<3.0` until 3.0 actually ships and is validated.
- Entity services are now registered once from the integration's
  `async_setup` (quality-scale rule `action-setup`); the previously
  undocumented `vacuum_set_property` / `vacuum_call_action` services are
  now declared and translated in all 20 languages.

### Fixed
- Local protocol `set_credentials` compared `bytes` to `str`, resetting
  the miIO connection on every call even with unchanged credentials.
- A failed P-frame map request could never be retried (its key stayed in
  the request queue forever).
- One corrupted saved map aborted the processing of the whole saved-map
  list; it is now skipped.
- The map file-URL cache grew without bound (map object names change on
  every update); expired entries are now purged.
- Event-loop hygiene: `get_map_for_render` (V8 map optimizer + deep
  copies) now always runs in the executor, and the default/disconnected
  camera images are encoded once and cached instead of re-encoding PNG
  (and re-blurring) on every access from the loop.
- Dynamic-entity coordinator listeners (rooms, shortcuts, map buttons,
  cameras) are now unsubscribed on config entry unload (previously leaked
  on every reload).
- The JSON map renderer no longer raises `KeyError` when the first frame
  arrives without dimensions.
- `recorder`: fixed the `carpet_sensivity_list` typo that made the
  exclusion inoperative.
- The embedded V8 context of the map optimizer is released on unload.

### Removed
- ~1 500 lines of dead code, chiefly the never-invoked pure-Python
  fallback of the map optimizer (the MiniRacer JS path is the only
  production path) plus assorted dead methods, dead exceptions
  (`AuthenticationError`, `InvalidResponseError`, `CircuitOpenError`),
  unused constants and stale commented blocks.
- Obsolete `CI_STATUS.md`; `requirements_dev.txt` merged into
  `requirements-dev.txt`.

### Added
- `quality_scale.yaml` with honest per-rule statuses (documented todos
  and justified exemptions).
- 7 missing translation keys (map-edge smoothing option and the
  `segments_changed` repair issue) natively translated into the 18
  languages that lagged behind; all 20 languages are at strict key parity
  with `strings.json`.
- +916 real tests (976 → 1 892): the Home Assistant layer is now at
  100 % coverage (camera included, with all HTTP views), and the embedded
  engine is covered on its critical logic — map decoder 81 % (synthetic
  wire-format payloads incl. AES), device status core 63 %, device
  orchestration 50 %, map editor 50 %, map operations 45 %, map manager
  and optimizer fixes locked (real V8 path), renderer pipeline with exact
  RGBA pixel asserts, Valetudo JSON renderer 100 %. Global coverage
  38.5 % → 66 %; coverage gate raised to 65 %.

## [6.5.3] - 2026-06-20

### Added
- Characterization test suites for the MiHome/MiIO cloud & device protocols and for device property routing / dirty-data discard (internal coverage; no user-facing behaviour change).

### Changed
- Development tooling & CI: adopt `prek` (Rust drop-in for pre-commit) as the hook runner; repository bootstrap (health files, issue forms, Renovate, CodeQL); extend the Lint job to cover `tests/`; bandit (`B106`) and codespell config fixes; dependency updates (checkout, codeql-action).

## [6.5.2] - 2026-06-16

### Fixed
- Thread safety: the persistent-notification dismiss listener scheduled the
  warning-clear task via `hass.async_create_task` from outside the event loop,
  which Home Assistant flags as unsafe (potential crash or data corruption). It
  is now scheduled on the loop via `call_soon_threadsafe`.
- Transient cloud API errors (device offline / command timeout, code 80001) are
  no longer logged at ERROR with the raw upstream message — they are translated
  and logged at WARNING.

## [6.5.1] - 2026-06-16

### Fixed
- Map decoding crash on AI obstacles: an `UnboundLocalError` discarded the
  entire map frame whenever a "simple" AI obstacle was present, and silently
  mis-placed the obstacle (reusing the last path point's coordinates) when it
  did not crash.
- Map decoding crash (`IndexError`) on AI obstacles reported with only four
  fields.
- Out-of-bounds segment-center lookup on malformed or truncated map payloads no
  longer discards the whole frame.

### Changed
- Performance: the camera segment-map cache is now keyed on the actual map
  structure instead of a timestamp, avoiding a full PNG re-render on every
  frame during cleaning.
- Performance: hidden-segment lookups in the map-decoder pixel loops use a set
  (O(1)) instead of a list (O(n) per pixel).
- Expanded test coverage: characterization suites for the Dreame and MiHome
  cloud protocols and for device property routing.
- CI now enforces version parity between `manifest.json` and `pyproject.toml`.
- Dependencies: bumped `ruff` (>=0.15.17), pre-commit hooks, and
  `home-assistant/actions`.

## [6.5.0] - 2026-06-11

### Added
- `vector_rooms` camera option (enabled by default): rooms are upscaled with
  smooth bicubic resampling instead of hard pixel blocks, with EN/FR strings.

### Changed
- Full `mypy --strict` typing across the entire integration (51 files, from
  roughly 4100 errors down to zero), with shared `TYPE_CHECKING` stubs
  (`dreame/_device_base.py`, `map_renderer/_base.py`) describing the
  cross-mixin surface. 851 tests stay green.

### Fixed
- Pillow 10+ compatibility: `Image.Resampling.BICUBIC` and
  `Image.Transpose.ROTATE_90/180/270` (rotated maps raised `AttributeError`).
- `capability.mop_extend` was defined without `@property` (feature detection
  always truthy), and the capability/status recursion this uncovered.
- `DreameVacuumWaterTank.MOP_IN_STATION`: code referenced a nonexistent
  `IN_STATION` enum member.
- Map restore read `wifi_map` (a bool) instead of `wifi_map_data`.
- `cleaning_route` reset compared against dict keys instead of values.
- Missing fallback returns in `combine_group_value` and
  `combine_mopping_settings`.
- Dead `go_to_zone.water_volume` attribute (now `water_level`).
- Import `VacuumEntityFeature` and logbook constants from the public Home
  Assistant packages (`vacuum.const` no longer exposes them on recent HA,
  which broke test collection on CI).

## [6.4.0] - 2026-06-06

### Added
- System Health connectivity summary (`system_health.py`): configured,
  locally-connected and cloud-connected device counts on HA's System Health page.
- Repairs platform (`repairs.py`): the map-segment change issue is now actionable
  through a confirmation fix flow.
- Restored the **map segment change detection** repair issue (`segments_changed`):
  the vacuum entity records a baseline of cleanable room ids and raises a repair
  issue when they change, warning that segment-based automations may need review.
  Translated in English and French (vouvoiement).
- `quality_scale: gold` declared in the manifest.
- Exhaustive test suite for the Home Assistant layer (~700 new tests). HA-layer
  coverage ≈ 91 % — coordinator, config flow, the nine entity platforms, init,
  logbook, diagnostics, system_health and repairs at ~100 %; camera best-effort.
  The coverage floor was ratcheted from 20 % to 35 %.
- mypy ratchet: `repairs` and `system_health` added to the strictly type-checked
  module list.

### Changed
- Progress sensors (`cleaning_progress`, `drying_progress`, `task_type`) stay
  available and report their value (e.g. `0` / `idle`) at rest instead of going
  "unavailable" — friendlier for history graphs and automations.
- Per-room (segment) selects and numbers are now disabled by default
  (`entity_registry_enabled_default = False`): they only matter when "Customized
  cleaning" is enabled, so they no longer flood the UI with unavailable rows.
  Enable them from the entity settings if you use per-room control.

### Fixed
- Camera: the segment-map PNG (numpy/PIL) is now built off the event loop in an
  executor instead of inside `extra_state_attributes`, removing a recurring
  event-loop block during cleaning.
- Coordinator: `clear_warning()` (blocking MIoT network I/O) is dispatched to an
  executor from the persistent-notification dismiss callback instead of running
  on the event loop.
- Setup: `coordinator.cleanup()` is guaranteed when the first refresh fails,
  preventing MQTT/cloud worker threads from leaking on every `ConfigEntryNotReady`
  retry.
- Camera: `async_camera_image` re-arms polling via `try/finally`, so a transient
  error no longer freezes the map refresh permanently.
- Vacuum: map-segment change detection no longer raises `AttributeError` on Home
  Assistant builds exposing `VacuumEntityFeature.CLEAN_AREA` (the
  `last_seen_segments` / `async_create_segments_issue` collaborators were missing).
- Button: shortcut buttons with no matching shortcut id no longer raise
  `AttributeError` during construction.
- Entity: a select's `value_int_fn` receiving an "unknown" value no longer breaks
  the entity's state-attribute read.
- Select: navigation services (next/previous/first/last) no longer raise
  `ZeroDivisionError` on option-less selects; `floor_material_direction` no longer
  dereferences a `None` current map.
- Services: `vacuum_set_obstacle_ignore` parses `"false"` correctly (`cv.boolean`),
  `vacuum_delete_map` no longer raises `TypeError` without `map_id`, and
  `vacuum_merge_segments` validates its segment-list length.

## [6.3.1] - 2026-06-05

### Added
- mypy type-check ratchet: a dedicated CI job plus per-module opt-in
  configuration in `pyproject.toml`, alongside a coverage floor
  (`fail_under = 20`) that ratchets upwards as the suite grows.
- Per-pass regression suites covering coordinator reconnection,
  config-flow session/password handling, entity `device_info` linking
  and protocol cleanup.

### Changed
- Tightened typing across the integration: entity descriptions, config
  flow (`FlowResult` → `ConfigFlowResult`), device, protocol and map
  modules. Extracted shared `set_fn`/`value_fn`/segment resolvers reused
  by the switch/number/time/select platforms and dropped the unused
  camera entity description.
- The test suite now runs with `-p no:homeassistant`.
- Dependency bumps: pillow, requests, pytest-asyncio, ruff and codespell;
  CI actions refreshed.

### Fixed
- Coordinator now raises `UpdateFailed` when the device disconnects
  mid-update and no longer destroys the device on transient errors, so
  the next refresh can reconnect instead of staying permanently
  unavailable.
- Config flow closes the throwaway cloud session on flow teardown
  (no more leaked `requests` connection pool) and drops the cleartext
  password once a server-issued auth_key is held on reauth.
- Entity `device_info` is linked via the stable MAC before `info` is
  populated, so entities are never added unlinked during the transient
  connect window.
- French translations: grammatical agreements (Vertical, Précis, Normal,
  Par défaut), product naming (Home Assistant, Wi-Fi) and wording
  consistency.

## [6.3.0] - 2026-04-19

### Added
- Expose `segment_id` on each entry of the camera `rooms` attribute so
  Lovelace cards can hit-test against the `segment_map` PNG (pixel blue
  channel ⇌ room).
- MQTT broker TLS fingerprint (SHA-256) is captured on every reconnect
  and logged; Trust-On-First-Use pinning warns if the fingerprint ever
  changes (vendor PKI uses a self-signed chain so strict TLS is not
  possible).
- Icon translations for `binary_sensor`, `number`, missing `vacuum`
  services and sensor states (Gold Quality-Scale coverage).
- Python matrix in CI: the test job now runs on 3.11, 3.12 and 3.13.
- Real config-flow tests driving `DreameVacuumFlowHandler` through the
  user/Dreame login steps.

### Changed
- `iot_class` switched from `cloud_polling` to `cloud_push`; the
  coordinator safety-net poll relaxed to 300 s now that MQTT push
  handles realtime updates.
- 18 locales synchronised with strings.json: eleven new
  `sensor.state.state` entries plus the `issues.consumable_depleted`
  pair added in 6.2 now exist in every translation file.
- `map_renderer.py` (5000+ lines) and `device_status.py` (3000+ lines)
  split into `map_renderer/` and `device_status/` packages with focused
  helper/shape/object and consumable/station mixins. Public API is
  unchanged; `self._xxx` and class-level call sites keep working
  through MRO.
- `_resources_data.py` split: a new lightweight
  `_notification_images.py` holds the images referenced by coordinator
  notifications and `error_image`, so notification-only code paths no
  longer parse the 12 MB map-renderer blob.
- The camera entity now renders in the executor (`async_add_executor_job`
  around `render_map`, `map_data_string`, `resources` and proxy image
  builders), registers its HTTP views once per HA instance, and shares
  a single proxy renderer across every map camera of a coordinator.
- `numpy`/`PIL` are imported lazily in `camera.py` (TYPE_CHECKING guard
  plus in-hot-path imports), shaving setup time when the map capability
  is disabled.
- `DreameVacuumConfigEntry` now resolves to
  `ConfigEntry[DreameVacuumRuntimeData]` at type-check time while
  staying a bare `ConfigEntry` alias at runtime (Python 3.11 compat).
- `_attr_name = None` + `has_entity_name = True` on the vacuum entity
  replaces the leading-whitespace hack; existing entity_ids stay stable
  via the registry.
- Internal device polling cadence relaxed when idle now that MQTT push
  drives realtime updates.

### Fixed
- `response.text` dropped from WARNING/ERROR logs in the cloud protocol
  so login/2FA/API error payloads no longer leak session tokens into
  shared logs.
- `persistent_notification.create`/`dismiss` and `bus.fire` invocations
  coming from device callbacks are now dispatched via
  `call_soon_threadsafe`, eliminating a class of data races on unload.
- Debounce and map-editor `threading.Timer` instances are cancelled
  during `disconnect()` so callbacks cannot fire after unload.
- `device.listen()` / `listen_error()` return an unsubscribe callable;
  the legacy `listen(None)` wipe path is preserved for backwards
  compatibility.
- `DreameVacuumProtocol.__init__` accepts `auth_key` without a password
  so reloads work after the cleartext password has been purged from
  the config entry.
- `async_setup_entry` now raises `ConfigEntryNotReady` when the first
  refresh returns no device/MAC instead of silently continuing.
- ~20 overly broad `except Exception` blocks narrowed to the specific
  error classes actually raised, with `exc_info=True` debug logs where
  they were previously silent.
- `_handle_properties` emits a single summary line at setup instead of
  ~100 DEBUG entries.
- `time.sleep` cap in `call_action` reduced to 3 s to limit executor
  worker saturation.

### Security
- Trust-On-First-Use TLS fingerprint pinning for the Dreame MQTT
  broker (documented trade-off: the vendor ships a self-signed cert
  chain, so `CERT_NONE` is required, but fingerprint drift is logged).
- URL validation (http/https) and JSON-safe payload construction in
  `install_voice_pack` and `restore_map_from_file` to block SSRF and
  payload injection via user-supplied URLs.
- Content-Disposition filenames coming from the cloud are sanitised
  before reaching HTTP headers to prevent response-splitting attacks.
- `CONF_PASSWORD` is removed from the config entry once the server-issued
  `auth_key` has been captured; future reloads only need the auth key
  (reauth already exists when the key expires).
- `TO_REDACT` in diagnostics extended with `ssecurity`, `service_token`,
  `uuid`, `client_id`, `_secondary_key` and related fields.

### CI
- `pytest-homeassistant-custom-component` now drives the pytest stack
  (pytest, pytest-cov, pytest-asyncio) so Python 3.11 stops tripping
  over version conflicts with upstream pins.
- Dependabot: `home-assistant/actions` bumped to `f6f29a7e`;
  `softprops/action-gh-release` bumped from 2 to 3.

## [6.2.0] - 2026-04-07

### Added
- Support for `vacuum.clean_area` (HA 2026.3) with backward compatibility for older HA versions
- Segment-based cleaning via native HA interface (`async_get_segments`, `async_clean_segments`)
- Segment change detection with repair issue notification
- Missing `issues.consumable_depleted` translations in en.json and fr.json (936/936 keys)

### Changed
- Config entry type alias now uses `TypeAlias` with proper `ConfigEntry[DreameVacuumRuntimeData]` parameterization
- Added `from __future__ import annotations` to all dreame/ subpackage files

### CI
- Bumped `codecov/codecov-action` from 5 to 6
- Bumped `home-assistant/actions` to latest

## [6.1.2] - 2026-02-26

### Fixed
- Removed unused `pybase64` dependency (no longer available in HA 2025.3+)
- Release workflow now uses CHANGELOG.md for release notes

## [6.1.1] - 2026-02-07

### Fixed
- Reverted TLS CERT_REQUIRED on MQTT — Dreame cloud uses self-signed certificates
- Removed Tasshack-only account type check that blocked `dreame` accounts
- Thread-safe issue registry calls via `call_soon_threadsafe` (prevents RuntimeError from sync threads)

## [6.1.0] - 2026-02-07

### Added
- 103 missing French translations for error notifications
- Static icons for all entity platforms (icons.json) — Gold-level compliance
- Repair issues for depleted consumables (HA issue registry)
- Stale device removal after coordinator refresh
- Log-when-unavailable for device availability changes
- ConfigEntryError for unsupported account types

### Changed
- Migrated `(str, Enum)` classes to `StrEnum` (Python 3.11+)
- Entity ID generation uses `async_generate_entity_id` instead of f-strings
- 16 duration sensors now expose `device_class=DURATION` and `state_class=MEASUREMENT`
- CI actions bumped: codecov/codecov-action v5, actions/checkout v6, actions/setup-python v6, actions/stale v10

### Fixed
- AND/OR logic inversion in device_setters
- Copy-paste error in map_editor merge operation
- Loop variable shadowing in device_map_ops
- Token masking in device_info for security
- TLS certificate verification enforced in protocol
- Thread-safe circuit breaker with Lock in resilience module
- Thread-safe map manager with Lock
- Deque popleft() instead of pop(0) in map_optimizer
- PIL resource cleanup and numpy vectorization in map_renderer
- Password field no longer has a default value in config_flow
- Codespell false positives on French words in const.py

### Security
- TLS CERT_REQUIRED enforced on MQTT connections
- Sensitive token data masked in logs

## [6.0.1] - 2026-02-03

### Added
- Bedrock furniture types (rock 1-4) with custom icons
- Optimized base64 image data for improved performance

### Changed
- Asset management with dreame_assets/ directory support

## [6.0.0] - 2026-02-02

### Added
- Segment map with per-room hit testing (blue channel = room key)
- `room_colors` attribute on camera entity mapping room_id to border color
- Room icons with custom name-based icon resolution (type 16 support across all icon sets)
- Badge outlines for dark color schemes
- 16 distinct room colors per color scheme (up from 4) across all 6 color schemes

### Changed
- **BREAKING**: Monolithic `device.py` (9000+ lines) split into `device_actions`, `device_status`, `device_setters`, `device_info`, `device_map_ops` submodules (re-exports preserved)
- **BREAKING**: Monolithic `map.py` (12000+ lines) split into `map_decoder`, `map_editor`, `map_manager`, `map_optimizer`, `map_renderer`, `map_data_json_renderer` submodules (re-exports preserved)
- Segment map PNG corrected with Y-axis flip so blue-channel pick buffer aligns with rendered camera image
- Remap LUT for segment map dynamically maps raw pixel values to room keys by sampling room centers
- README rewritten with upstream diff, troubleshooting, known limitations and credits sections

### Fixed
- Segment map rooms now map correctly to pixels (Y-axis flip fix)
- Missing `cmp_to_key` import in `map_manager` and `map_optimizer` after module split
- Missing `base64`, `numpy`, `cryptography`, `MiniRacer` imports after ruff auto-fix
- `MAP_OPTIMIZER_JS` imported from correct module (`resources` instead of `const`)
- Test file import sources and class names corrected
- Import sorting in test files (isort compliance)
- Ruff F822 false positives suppressed for `resources.py` lazy-loading module
- Applied ruff format to all modules

## [5.1.1] - 2026-02-01

### Changed
- Room names and numbers now displayed in black on light color schemes (Dreame Light, Mijia Light) for better readability
- White text with contrast stroke preserved for dark schemes (Dreame Dark, Mijia Dark, Transparent)

## [5.0.0] - 2025-01-31

### Added
- `data_description` help texts for all config and options flow fields
- `config.abort.already_in_progress` translation key
- Entity availability reference documentation (`docs/entity_availability.md`)

### Fixed
- Inverted `available_fn` logic for carpet-related switches (`clean_carpets_first`, `intensive_carpet_cleaning`, `side_brush_carpet_rotate`) — these were unavailable when carpet recognition was enabled instead of available
- Propagated all new translation keys to 20 language files

## [4.4.0] - 2025-01-24

### Added
- Diagnostics support with `async_get_config_entry_diagnostics`
- Automatic redaction of sensitive data in diagnostics
- Entity descriptions with `_attr_has_entity_name = True` pattern
- Runtime data pattern (`entry.runtime_data`) for Platinum quality scale
- `__slots__` on all entity classes for memory optimization
- `TYPE_CHECKING` guards for type-only imports (lazy loading)
- `state_class` on all numeric sensors (`MEASUREMENT` / `TOTAL_INCREASING`)
- `suggested_display_precision=0` on all percentage sensors
- Translated exceptions via `HomeAssistantError` with `translation_domain`/`translation_key`
- 11 exception translation keys in strings.json (device_not_available, entity_unavailable, invalid_value, etc.)
- `Debouncer` on coordinator refresh (1.5s cooldown)
- Idempotent config entry migration with early-return guard
- `entry.async_create_background_task()` for delayed refresh
- Reconfigure step in config flow
- Full French translation (fr.json)
- CI/CD with GitHub Actions (ci.yml, hacs.yml, stale.yml)
- CODEOWNERS, dependabot.yml, pull request template
- Test suite (22 tests for config_flow, diagnostics, init)
- Logbook support (`logbook.py`)
- `py.typed` marker for type checking

### Changed
- Renamed `types.py` to `vacuum_types.py` to avoid stdlib conflict
- Increased property batch size to 50 for single network call
- Optimized startup with selective property loading (~43 vs ~201 properties)
- Improved manifest.json with proper `integration_type` and `iot_class`
- Updated pre-commit hooks to latest versions
- Narrowed exception handling: `(ImportError, AttributeError)` instead of bare `Exception` for VacuumActivity import
- Exception chains preserved with `from exc` instead of `from None`
- Notification dismiss listener guards against `bool` type for `_notify` config
- Removed `InvalidActionException` from vacuum.py in favor of translated `HomeAssistantError`
- Type annotations corrected (`DreameVacuumDevice | None`, `DreameVacuumEntityDescription | None`)
- All 20 translation files synchronized (exceptions, reconfigure_confirm, mop rename, orphan cleanup)

### Fixed
- Use `is None` instead of `== None` comparisons (E711)
- Removed unused variables and fixed mutable default arguments (B006)
- Added missing translation keys for mop and self_repair states
- Fixed typo in config_flow docstring (Dremae -> Dreame)
- Fixed critical bugs (index out of bounds, encapsulation)
- Fixed outline validation with 50% area coverage check
- Use bounding box when segment outline is invalid
- CleanGenius Mode not created if not supported
- Fixed `_notify` type confusion crash in notification dismiss listener
- Fixed `ConfigEntryAuthFailed() from None` outside except block
- Fixed missing `__slots__` entries (`_map_id`, `_map_name` in camera, `_vacuum_state` in vacuum)

### Removed
- Dead code: `_legacy_webrtc_provider`, `_webrtc_provider`, `_supports_native_*_webrtc` attributes
- Dead code: commented-out TODO blocks in device.py (auto_switch_data, ai_data restore)
- Dead code: `exceptions.py` (unused custom exceptions)
- Dead code: `del entity` no-op in camera cleanup
- Orphan translation keys across 20 files (selector, vacuum_set_dnd, streaming states, mop_pad, self_test_failed)
- Commented-out `entity_registry_enabled_default=False` lines (15 occurrences)

## [4.3.0] - 2024-11-12

### Added
- Initial HACS release
- Support for Dreame vacuum robots
- Live and multi-floor map support
- Map obstacle photos
- Cleaning and cruising history maps
- Cloud and local map backup/recovery
- Saved WiFi coverage maps
- Customized room cleaning entities
- Services for device and map control
- Persistent notifications and error reporting
- Events for automations
- Dreamehome and Movahome account support
