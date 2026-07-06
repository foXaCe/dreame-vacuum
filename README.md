[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg?logo=HomeAssistantCommunityStore&logoColor=white&style=for-the-badge)](https://github.com/hacs/integration)

# Dreame Vacuum - Home Assistant Integration

Custom Home Assistant integration for Dreame robot vacuums. Complete app replacement with full device control.

> **Fork of [Tasshack/dreame-vacuum](https://github.com/Tasshack/dreame-vacuum)** with significant architectural improvements, bug fixes and new features.

## What changed from upstream

This fork has been extensively reworked compared to the original integration:

### Architecture
- **Modular codebase** — the monolithic `device.py` (9000+ lines) and `map.py` (12000+ lines) have been split into focused submodules (`device_actions`, `device_status`, `device_setters`, `device_info`, `device_map_ops`, `map_decoder`, `map_editor`, `map_manager`, `map_optimizer`, `map_renderer`, `map_data_json_renderer`) while preserving full backward compatibility via re-exports
- **Typed config entry** with `runtime_data` pattern (`DreameVacuumConfigEntry`)
- **`__slots__`** on all entity classes for memory optimization
- **`TYPE_CHECKING`** guards for type-only imports (lazy loading)
- **Debouncer** on coordinator refresh (1.5s cooldown)
- **Background tasks** via `entry.async_create_background_task()`
- **Resilience layer** with circuit breaker, retry with backoff, and configurable timeouts
- **Clean unused imports** — full ruff F401/I001 compliance

### Map rendering
- **16-color palette** (up from 4) across all 6 color schemes (Dreame Light, Dreame Dark, Mijia Light, Mijia Dark, Grayscale, Transparent) so every room gets a distinct color
- **Segment map PNG fix** — corrected Y-axis flip so the blue-channel pick buffer aligns with the rendered camera image; rooms now map correctly to pixels
- **Remap LUT** for segment map — raw pixel values are dynamically mapped to room keys by sampling room centers, handling frame map vs saved map ID divergence
- **Room colors attribute** (`room_colors`) exposed on the camera entity for card integration
- **Room icons** — custom name-based icon resolution (e.g. bathroom, kitchen, bedroom) with type 16 support across all icon sets
- **Badge outlines** for dark color schemes
- **Black text** for room names and numbers on light color schemes

### Entities & sensors
- **11 additional device states** from upstream merged
- **`state_class`** on all numeric sensors (`MEASUREMENT` / `TOTAL_INCREASING`)
- **Translated exceptions** via `HomeAssistantError` with `translation_domain`/`translation_key`

### Translations
- **20 languages** fully synchronized: EN, FR, DE, ES, IT, PT, PT-BR, NL, RU, UK, PL, CS, RO, SV, SL, HU, KO, CA, ZH-Hans, ZH-Hant
- **French translations** extensively improved

### Quality & CI
- **Pre-commit / ruff** configuration for linting and formatting
- **GitHub Actions** for CI (lint, tests, hassfest, HACS validation)
- **Test suite** with pytest covering module imports, platform setup, device status, map decoder, config flow, diagnostics, exceptions, and resilience
- **Idempotent migration** with early-return guard


## Features

- Auto generated device entities
- Live and multi floor map support
- Map obstacle photos
- Cleaning and cruising history maps
- Cloud and local map backup/recovery
- Saved WiFi coverage maps
- Customized room cleaning entities
- Services for device and map control
- Persistent notifications and error reporting
- Events for automations
- Segment map with per-room hit testing (blue channel = room key)
- 16 distinct room colors per color scheme
- Dreamehome account support
- Movahome account support


## Installation

#### Via [HACS](https://hacs.xyz/)

Search for "Dreame Vacuum" in HACS integrations and install.

#### Manually

Copy the `custom_components/dreame_vacuum` folder into your Home Assistant `custom_components` directory.


## Configuration

<a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=dreame_vacuum" target="_blank"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Open your Home Assistant instance and start setting up a new integration." /></a>

1. Select configuration type:
   - **Mi Home Account**: Connect via Xiaomi cloud credentials
   - **Dreamehome Account**: Connect via Dreame cloud credentials
   - **Local**: Connect directly via IP address and token

2. Enter required credentials according to the selected configuration type.
   > For `Mi Home Account` and `Local` configuration types, make sure devices are on the same subnet. See [python-miio troubleshooting](https://python-miio.readthedocs.io/en/latest/troubleshooting.html#discover-devices-across-subnets).

3. Set your device name and integration settings (notifications, map color scheme).

4. Navigate to the device page to enable or disable entities.


## How To Use

The integration is compatible with all available Lovelace vacuum cards.

#### With [Dreame Vacuum Card](https://github.com/foXaCe/dreame-vacuum-card) (recommended)

The companion card built specifically for this integration: interactive map with
room, zone, spot and goto cleaning, live status, controls and animations — no
template required.

```yaml
type: custom:dreame-vacuum-card
entity: vacuum.your_dreame_vacuum
map_source:
  camera: camera.your_dreame_vacuum_map
calibration_source:
  camera: true
vacuum_platform: tasshackDreameVacuum
```

#### With [Vacuum Card](https://github.com/denysdovhan/vacuum-card)

```yaml
type: custom:vacuum-card
entity: # Your vacuum entity
map: # Map Entity
map_refresh: 1
stats:
  default:
    - attribute: filter_left
      unit: '%'
      subtitle: Filter
    - attribute: side_brush_left
      unit: '%'
      subtitle: Side brush
    - attribute: main_brush_left
      unit: '%'
      subtitle: Main brush
    - attribute: sensor_dirty_left
      unit: '%'
      subtitle: Sensors
  cleaning:
    - attribute: cleaned_area
      unit: m2
      subtitle: Cleaned area
    - attribute: cleaning_time
      unit: min
      subtitle: Cleaning time
shortcuts:
  - name: Clean Room 1
    service: dreame_vacuum.vacuum_clean_segment
    service_data:
      entity_id: # Your vacuum entity
      segments: 1
    icon: mdi:sofa
  - name: Clean Room 2
    service: dreame_vacuum.vacuum_clean_segment
    service_data:
      entity_id: # Your vacuum entity
      segments: 2
    icon: mdi:bed-empty
  - name: Clean Room 3
    service: dreame_vacuum.vacuum_clean_segment
    service_data:
      entity_id: # Your vacuum entity
      segments: 3
    icon: mdi:silverware-fork-knife
```

#### With [Valetudo Map Card](https://github.com/Hypfer/lovelace-valetudo-map-card)

> Enable **Map Data** camera entity.

<a href="https://my.home-assistant.io/redirect/entities/" target="_blank"><img src="https://my.home-assistant.io/badges/entities.svg" alt="Open your Home Assistant instance and show your entities." /></a>

```yaml
type: custom:valetudo-map-card
vacuum: # Your vacuum name not the entity id
rotate: 0
dock_icon: mdi:lightning-bolt-circle
dock_color: rgb(105 178 141)
vacuum_color: rgb(110, 110, 110)
wall_color: rgb(159, 159, 159)
floor_color: rgb(221, 221, 221)
no_go_area_color: rgb(177, 0, 0)
no_mop_area_color: rgb(170, 47, 255)
virtual_wall_color: rgb(199, 0, 0)
virtual_wall_width: 1.5
currently_cleaned_zone_color: rgb(221, 221, 221)
path_color: rgb(255, 255, 255)
path_width: 1.5
segment_opacity: 1
segment_colors:
  - rgb(171, 199, 248)
  - rgb(249, 224, 125)
  - rgb(184, 227, 255)
  - rgb(184, 217, 141)
```

#### With [Xiaomi Vacuum Map Card](https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card)
 > Template for room and zone cleaning.
<a href="https://my.home-assistant.io/redirect/developer_template/" target="_blank"><img src="https://my.home-assistant.io/badges/developer_template.svg" alt="Open your Home Assistant instance and show your template developer tools." /></a>
```yaml
{# ----------------- PROVIDE YOUR OWN ENTITY IDS HERE ----------------- #}
{% set camera_entity = "camera." %}
{% set vacuum_entity = "vacuum." %}
{# ------------------- DO NOT CHANGE ANYTHING BELOW ------------------- #}
{% set attributes = states[camera_entity].attributes %}

type: custom:xiaomi-vacuum-map-card
vacuum_platform: default
entity: {{ vacuum_entity }}
map_source:
  camera: {{ camera_entity }}
calibration_source:
  camera: true
map_modes:
  - template: vacuum_clean_zone
    max_selections: 10
    repeats_type: EXTERNAL
    max_repeats: 3
    service_call_schema:
      service: dreame_vacuum.vacuum_clean_zone
      service_data:
        entity_id: '[[entity_id]]'
        zone: '[[selection]]'
        repeats: '[[repeats]]'
  - template: vacuum_clean_segment
    repeats_type: EXTERNAL
    max_repeats: 3
    service_call_schema:
      service: dreame_vacuum.vacuum_clean_segment
      service_data:
        entity_id: '[[entity_id]]'
        segments: '[[selection]]'
        repeats: '[[repeats]]'
    predefined_selections:
{%- for room_id in attributes.rooms | default([]) %}
{%- set room = attributes.rooms[room_id] %}
      - id: {{room_id}}
        outline:
          - - {{room["x0"]}}
            - {{room["y0"]}}
          - - {{room["x0"]}}
            - {{room["y1"]}}
          - - {{room["x1"]}}
            - {{room["y1"]}}
          - - {{room["x1"]}}
            - {{room["y0"]}}
{%- endfor %}
  - name: Clean Spot
    icon: mdi:map-marker-plus
    max_repeats: 3
    selection_type: MANUAL_POINT
    repeats_type: EXTERNAL
    service_call_schema:
      service: dreame_vacuum.vacuum_clean_spot
      service_data:
        entity_id: '[[entity_id]]'
        points: '[[selection]]'
        repeats: '[[repeats]]'
```

#### With <a href="https://github.com/benct/lovelace-xiaomi-vacuum-card" target="_blank">Xiaomi Vacuum Card</a> and Picture Entity Card
```yaml
type: picture-entity
entity: # Your vacuum entity
camera_image: # Your camera entity
show_state: false
show_name: false
camera_view: live
tap_action:
  action: none
hold_action:
  action: none
```

```yaml
type: custom:xiaomi-vacuum-card
entity: # Your vacuum entity
vendor: xiaomi
attributes:
  main_brush_life:
    label: 'Main Brush: '
    key: main_brush_left
    unit: '%'
    icon: mdi:car-turbocharger
  side_brush_life:
    label: 'Side Brush: '
    key: side_brush_left
    unit: '%'
    icon: mdi:pinwheel-outline
  filter_life:
    label: 'Filter: '
    key: filter_left
    unit: '%'
    icon: mdi:air-filter
  sensor_life:
    label: 'Sensor: '
    key: sensor_dirty_left
    unit: '%'
    icon: mdi:radar
  main_brush: false
  side_brush: false
  filter: false
  sensor: false

```


## Documentation

- [Entity Availability Reference](docs/entity_availability.md) — Why entities may show as unavailable or unknown, with diagnostic guidance per platform
- [Entities](docs/entities.md) — Full entity list
- [Supported Devices](docs/supported_devices.md) — Tested models and compatibility
- [Map](docs/map.md) — Map configuration and usage
- [Camera HTTP API](docs/camera_http_api.md) — Wire format for the 7 camera HTTP views and the map attribute contract (companion card integrators)
- [Services](docs/services.md) — Available services
- [Room Entities](docs/room_entities.md) — Per-room cleaning entities
- [Notifications](docs/notifications.md) — Notification system
- [Events](docs/events.md) — Automation events


## Removal

1. Go to **Settings > Devices & Services > Dreame Vacuum**
2. Click the three-dot menu and select **Delete**
3. Restart Home Assistant
4. Remove the `custom_components/dreame_vacuum` folder (if installed manually) or uninstall via HACS


## Known limitations

- Updates are pushed by the Dreame cloud over MQTT (`cloud_push`), backed by a
  periodic safety-net poll — a working cloud connection is required
- Map rendering is CPU-intensive on first load (cached afterward)
- Cloud API calls are async-native (aiohttp); the local python-miio backend and some `device.py` worker threads are not fully async yet (see `ARCHITECTURE.md`'s async migration roadmap)
- Some older Dreame models may not expose all entities


## Troubleshooting

- **Integration fails to set up**: Check your credentials and ensure your device is online in the Dreame/Mi Home app
- **Map not loading**: Verify the device has completed at least one cleaning run and has a saved map
- **Entities unavailable**: The device may be offline or the cloud connection interrupted; check the integration logs in **Settings > System > Logs**
- **Room colors look similar**: The integration uses 16 distinct colors; adjacent rooms may get perceptually close hues depending on the color scheme


## To Do

- Shortcut editing
- Furniture editing
- Multi-window DnD editing (single-window done; design: docs/dev/dnd-tasks-design.md)
- Live camera streaming (spike: see docs/dev/streaming-spike.md — size L-or-never, blocked on proprietary transport)


## Contributing

To contribute, fork this repository and open a pull request.


## Credits

Based on [Tasshack/dreame-vacuum](https://github.com/Tasshack/dreame-vacuum). This fork adds modular architecture, extended color palettes, segment map fixes, resilience patterns, test coverage and quality scale improvements.
