# Architecture

This document describes how the Dreame Vacuum integration is organised, how
data flows through it, and where to extend it.

## Two layers

```
custom_components/dreame_vacuum/
├── <Home Assistant layer>     # entities, coordinator, config flow, platforms
└── dreame/                    # low-level device engine (protocol, maps, status)
```

- **Home Assistant layer** (top-level modules): everything HA talks to. It is the
  part covered by the test suite (~91 %) and the part to touch for HA features.
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
| `config_flow.py` | `ConfigFlow` + `OptionsFlow`: Mi / Dreame / Mova / local login, captcha/2FA, reauth, duplicate guards |
| `vacuum.py` | Main `StateVacuumEntity`; ~30 custom services; map-segment change detection |
| `sensor/binary_sensor/switch/select/number/button/time/camera.py` | Entity platforms — each `async_setup_entry` instantiates entities from `EntityDescription`s; no business logic |
| `camera.py` | Map cameras, executor-based rendering, shared proxy renderer, HTTP views |
| `diagnostics.py` | Redacted config-entry diagnostics |
| `repairs.py` | Fix flow for actionable repair issues (segment change → `ConfirmRepairFlow`) |
| `system_health.py` | Connectivity summary on the System Health page |
| `logbook.py` / `recorder.py` | Event descriptions; recorder attribute exclusion |
| `const.py` | All constants, config keys, notification ids, translation helpers |
| `strings.json` + `translations/` | UI strings; English + French are the maintained references |

## Engine (`dreame/`) — high level

- `device.py` — `DreameVacuumDevice`: orchestration, property listeners, update loop.
- `protocol.py` — MiIO + Dreame cloud + MQTT transport, TLS fingerprint pinning.
- `device_status/`, `device_setters.py`, `device_actions.py`, `device_map_ops.py` —
  status model, setters, actions, map operations (split into focused mixins).
- `map_decoder.py`, `map_manager.py`, `map_editor.py`, `map_optimizer.py`,
  `map_renderer/`, `map_data_json_renderer.py` — binary map decode + render pipeline.
- `vacuum_types.py`, `const.py` — enums, dataclasses and the protocol constant tables.

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
Register it in `vacuum.py`'s `async_setup_entry` via
`platform.async_register_entity_service(SERVICE_X, schema, "async_x")`, declare it
in `services.yaml`, and translate it in `strings.json` + `translations/`.

### Add a repair issue
Create it with `async_create_issue(...)`. Informational issues use
`is_fixable=False`; actionable ones use `is_fixable=True` and a `fix_flow` block in
the translations, handled by `repairs.async_create_fix_flow`.

## Quality & testing

- **Quality scale**: Gold (coordinator, runtime_data, reauth, options, diagnostics,
  repairs, system_health, recorder, logbook, migration, dynamic entities, tests).
- **Tests**: `pytest` with `pytest-homeassistant-custom-component`; HA layer ≈ 91 %
  (most modules 100 %, camera best-effort). Coverage floor ratchets upward only.
- **Typing**: mypy runs as a ratchet — modules in the per-module allow-list in
  `pyproject.toml` are strictly checked; the engine and a few HA modules
  (`vacuum`, `coordinator`, `select`, `camera`) are still deferred (a `self._device`
  None-guard retype is the main remaining work).
- **Lint/format**: `ruff check` + `ruff format` (Home Assistant rule set).
