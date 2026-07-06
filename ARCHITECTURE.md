# Architecture

This document describes how the Dreame Vacuum integration is organised, how
data flows through it, and where to extend it.

## Two layers

```
custom_components/dreame_vacuum/
├── <Home Assistant layer>     # entities, coordinator, config flow, platforms
└── dreame/                    # low-level device engine (protocol, maps, status)
```

- **Home Assistant layer** (top-level modules): everything HA talks to. It is
  fully covered by the test suite (100 %) and the part to touch for HA features.
- **`dreame/` engine**: the device library — MiIO/Dreame cloud protocol, MQTT
  push, binary map decoding/rendering, device state. It is large, hardware-shaped,
  and changed only when a real device bug requires it.

## Data flow

```
Dreame cloud / device  ──MQTT push & polling──►  dreame/ engine (DreameVacuumDevice)
        │                                                   │  listeners + status
        ▼                                                   ▼
DreameVacuumDataUpdateCoordinator  ──async_set_updated_data──►  CoordinatorEntity
   (coordinator.py)                                          (entity.py + platforms)
        │                                                          │
        ├─ persistent notifications / repair issues               ├─ state, attributes
        └─ option migration, reauth, host/token capture           └─ services, actions
```

1. `DreameVacuumDevice` connects (cloud login + local/MQTT), then **pushes** updates
   (`iot_class: cloud_push`); a 300 s safety-net poll backs it up.
2. The coordinator wraps the device, forwards pushes via `async_set_updated_data`,
   raises `UpdateFailed` / `ConfigEntryAuthFailed`, manages persistent notifications,
   consumable repair issues, option migration and credential capture.
3. Entities are `CoordinatorEntity` subclasses; they read `coordinator.device` and
   never perform device I/O directly — actions are funnelled through
   `DreameVacuumEntity._try_command`, which maps engine exceptions to
   `HomeAssistantError` and runs blocking calls in an executor.

## Home Assistant layer — file roles

| File | Role |
|------|------|
| `__init__.py` | `async_setup_entry` / `async_unload_entry` / `async_migrate_entry`; guarantees `coordinator.cleanup()` on setup failure; removes stale devices |
| `coordinator.py` | `DataUpdateCoordinator`; device lifecycle, push fan-out, notifications, consumable issues, rate-limit backoff |
| `entity.py` | Base `DreameVacuumEntity`: `available`, `device_info`, `native_value`, `extra_state_attributes`, `_try_command`, set/value/segment resolvers |
| `config_flow.py` | `ConfigFlow` + `OptionsFlowWithReload` (modern selectors): Mi / Dreame / Mova / local login, captcha/2FA, reauth, duplicate guards |
| `vacuum.py` | Main `StateVacuumEntity`; Clean-by-area segments; map-segment change detection |
| `services.py` | All 38 entity services, registered from `async_setup` (action-setup rule) |
| `sensor/binary_sensor/switch/select/number/button/time/camera.py` | Entity platforms — each `async_setup_entry` instantiates entities from `EntityDescription`s; no business logic. Static icons live in `icons.json` (icon-translations); only dynamic `icon_fn` stay in code |
| `camera.py` | Map cameras, executor-based rendering, shared proxy renderer |
| `camera_views.py` | The 7 process-global HTTP proxy views (map data, obstacles, history, recovery, wifi, resources), registered once per HA process |
| `diagnostics.py` | Redacted config-entry diagnostics |
| `repairs.py` | Fix flow for actionable repair issues (segment change → `ConfirmRepairFlow`) |
| `system_health.py` | Connectivity summary on the System Health page |
| `logbook.py` / `recorder.py` | Event descriptions; recorder attribute exclusion |
| `const.py` | All constants, config keys, notification ids, translation helpers |
| `strings.json` + `translations/` | UI strings; English + French are the maintained references |

## Engine (`dreame/`) — high level

- `device.py` — `DreameVacuumDevice`: orchestration, property listeners, update loop.
- `protocol.py` — MiIO + Dreame cloud + MQTT protocol layer, TLS fingerprint pinning.
- `http_client.py` — async-native HTTP transport (aiohttp): `AsyncHttpClient` (can
  borrow an injected `ClientSession`) + `BlockingHttpClient`, a facade running a
  private event loop in one daemon thread for the legacy worker threads. Step 1 of
  the incremental async migration; the remaining steps are listed below.
- `device_status/` (`_core` + `_named_props`/`_activity`/`_map_props`/`_consumables`/
  `_station` mixins), `device_setters.py`, `device_actions.py`, `device_map_ops.py` —
  status model, setters, actions, map operations (split into focused mixins).
- `map_decoder.py`, `map_manager.py`, `map_editor.py`, `map_optimizer.py`,
  `map_renderer/` (`_core` + `_layers`/`_segments_render`/`_resources_props`/
  `_objects`/`_shapes`/`_helpers` mixins), `map_data_json_renderer.py` — binary map
  decode + render pipeline. The optimizer runs the vendor JS algorithm in an
  embedded V8 (`py-mini-racer`); it is CPU-bound and, like the PIL/numpy renderer,
  must only ever be called from an executor thread (camera.py is the orchestrator
  and upholds this invariant).
- `vacuum_types.py`, `const.py` — enums, dataclasses and the protocol constant tables.

### Async migration roadmap (strangler pattern)

Step 1 (done): cloud HTTP is async-native (`http_client.py`, aiohttp) behind the
`BlockingHttpClient` facade. Remaining steps, in order — each keeps the system
functional: (2) `device.py` worker threads → asyncio tasks on the HA loop;
(3) `_api_task` queues → `asyncio.Queue`; (4) paho-mqtt → aiomqtt, porting the
TOFU fingerprint pinning (`_check_mqtt_fingerprint`) via a custom SSL context;
(5) local MiIO backend (python-miio is sync — asyncio UDP reimplementation or
keep in executor); (6) inject Home Assistant's shared websession and delete
`BlockingHttpClient`. Steps 4-6 unlock the Platinum `async-dependency` /
`inject-websession` rules.

## How to extend

### Add an entity to an existing platform
Add an `EntityDescription` to the platform's description tuple (e.g. `SENSORS` in
`sensor.py`). Use `value_fn` / `set_fn` / `exists_fn` / `available_fn`; the base
class resolves `<key>_name` / `<key>_list` / `set_<key>` from `device.status` /
`device` automatically. Keep the `unique_id` suffix (`key`) stable — it must never
change for an existing entity without an `async_migrate_entry` migration.

### Add a new entity platform
Create `the_platform.py` with an `async_setup_entry`, add `Platform.X` to
`PLATFORMS` in `__init__.py`, and subclass `DreameVacuumEntity` + the HA platform
entity. Mirror the description-driven pattern of the existing platforms.

### Add a device capability / property
Expose it in the `dreame/` engine (`DreameVacuumProperty` + status), then surface
it via a new `EntityDescription` guarded by `exists_fn=lambda d, dev:
dev.capability.<flag>`.

### Add a custom service
Register it in `services.py` (`async_register_services`, called from
`async_setup`) via the `register(SERVICE_X, schema_dict, "async_x")` helper —
schemas are plain dicts wrapped by HA in `cv.make_entity_service_schema`.
Declare it in `services.yaml` and translate it in `strings.json` + `translations/`.

### Add a repair issue
Create it with `async_create_issue(...)`. Informational issues use
`is_fixable=False`; actionable ones use `is_fixable=True` and a `fix_flow` block in
the translations, handled by `repairs.async_create_fix_flow`.

## Quality & testing

- **Quality scale**: Gold — the per-rule checklist lives in
  `custom_components/dreame_vacuum/quality_scale.yaml` (honest statuses:
  documented todos and justified exemptions).
- **Tests**: `pytest` with `pytest-homeassistant-custom-component`; HA layer at
  **100 %** (camera and its HTTP views included), engine covered on its critical
  logic (protocol, manager/optimizer fixes, setters/actions). Global ≈ 46 %,
  coverage floor (`fail_under = 45`) ratchets upward only.
- **Typing**: mypy runs as a ratchet — modules in the per-module allow-list in
  `pyproject.toml` are strictly checked; the engine and a few HA modules
  (`vacuum`, `coordinator`, `select`, `camera`) are still deferred (a `self._device`
  None-guard retype is the main remaining work).
- **Lint/format**: `ruff check` + `ruff format` (Home Assistant rule set).
