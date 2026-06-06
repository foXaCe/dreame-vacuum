# Entity Availability Reference

This document explains why entities may appear as **unavailable** (grayed out) or **absent** (not created) in Home Assistant, and whether this is normal behavior.

## How Entity Availability Works

### Three levels of entity visibility

| State | Appearance in HA | Cause |
|-------|-----------------|-------|
| **Absent** | Entity does not exist at all | `exists_fn` returned `False` — device model doesn't support this feature |
| **Unavailable** | Entity exists but grayed out | `available` property returned `False` — device state doesn't allow this right now |
| **Unknown** | Entity exists, shows "Unknown" | Property hasn't been read yet, or cloud data is missing |

### Decision flow

```
1. exists_fn(description, device) → False?  → Entity NOT created (absent)
2. device.device_connected → False?         → ALL entities unavailable
3. available_fn(device) → False?            → This entity unavailable
4. PROPERTY_AVAILABILITY[key] → False?      → This entity unavailable
5. ACTION_AVAILABILITY[key] → False?        → This entity unavailable
6. Otherwise                                → Entity available
```

## Diagnostic Guide

### All entities unavailable at once
**Cause**: `device.device_connected` is `False` — the vacuum is offline or the cloud connection is lost.
**Fix**: Check network connectivity, restart the integration, verify cloud credentials.

### Entity absent (not in entity list)
**Normal if**: Your vacuum model doesn't have this hardware feature.
Check the `exists_fn` column below — if it requires a capability your model lacks, the entity correctly doesn't exist.

### Entity intermittently unavailable
**Normal if**: The entity has a state-dependent availability condition.
Example: "Suction level" is unavailable during mopping-only mode. "Start mapping" is unavailable while cleaning.

### Entity permanently unavailable (but created)
**Possibly a bug if**: The entity exists but is always unavailable regardless of device state. Check the availability condition — it might be checking a property that your device never reports.

---

## Sensor Entities (60)

| Key | Existence Condition | Availability Condition | Notes |
|-----|---------------------|----------------------|-------|
| `status` | Property in device data | Always | Core entity |
| `cleaning_mode` | Property in device data | Not during mapping/cruising/custom cleaning/cleangenius/returning/draining | State-dependent |
| `suction_level` | Property in device data | Not mopping, not custom cleaning, not cleangenius, not mapping, not cruising | State-dependent |
| `water_volume` | Property in device data | Mop installed, not sweeping, not custom cleaning, not cleangenius, not mapping | State-dependent |
| `water_tank` | Not self_wash_base AND not embedded_tank | Always | Model: no base station |
| `mop_pad` | self_wash_base | Always | Model: base station required |
| `task_type` | task_type capability | task_type value > 0 | Only when task active |
| `low_water_warning` | self_wash_base | Not auto_water_refilling_enabled | State-dependent |
| `drainage_status` | water_check | Always | Model: water check |
| `stream_status` | camera_streaming | Stream status not None | Camera models only |
| `cleaning_time` | Property in device data | Not mapping, not cruising | State-dependent |
| `cleaned_area` | Property in device data | Not mapping, not cruising | State-dependent |
| `battery_level` | Property in device data | Always | Core entity |
| `cleaning_progress` | Property in device data | Started and not cruising | Only during cleaning |
| `drying_progress` | Property in device data | Drying active | Only during drying |
| `mapping_time` | lidar_navigation | Fast mapping active | Only during mapping |
| `main_brush_left` | Property in device data | Always | Consumable |
| `main_brush_time_left` | Property in device data | Always | Consumable |
| `side_brush_left` | Property in device data | Always | Consumable |
| `side_brush_time_left` | Property in device data | Always | Consumable |
| `filter_left` | Property in device data | Always | Consumable |
| `filter_time_left` | Property in device data | Always | Consumable |
| `sensor_dirty_left` | Not disable_sensor_cleaning | Always | Consumable |
| `sensor_dirty_time_left` | Not disable_sensor_cleaning | Always | Consumable |
| `tank_filter_left` | Property in device data | Always | Consumable |
| `tank_filter_time_left` | Property in device data | Always | Consumable |
| `mop_pad_left` | Property in device data | Always | Consumable |
| `mop_pad_time_left` | Property in device data | Always | Consumable |
| `silver_ion_left` | Property in device data | Always | Consumable |
| `silver_ion_time_left` | Property in device data | Always | Consumable |
| `detergent_left` | Property + detergent capability | Always | Model: detergent |
| `detergent_time_left` | Property + detergent capability | Always | Model: detergent |
| `squeegee_left` | Property in device data | Always | Consumable |
| `squeegee_time_left` | Property in device data | Always | Consumable |
| `onboard_dirty_water_tank_left` | Property in device data | Always | Consumable |
| `onboard_dirty_water_tank_time_left` | Property in device data | Always | Consumable |
| `dirty_water_tank_left` | Property in device data | Always | Consumable |
| `dirty_water_tank_time_left` | Property in device data | Always | Consumable |
| `deodorizer_left` | Property + deodorizer capability | Always | Model: deodorizer |
| `deodorizer_time_left` | Property + deodorizer capability | Always | Model: deodorizer |
| `wheel_dirty_left` | Property + wheel capability | Always | Model: wheel tracking |
| `wheel_dirty_time_left` | Property + wheel capability | Always | Model: wheel tracking |
| `scale_inhibitor_left` | Property + scale_inhibitor capability | Always | Model: scale inhibitor |
| `scale_inhibitor_time_left` | Property + scale_inhibitor capability | Always | Model: scale inhibitor |
| `first_cleaning_date` | Property in device data | Property has value | Unavailable if never cleaned |
| `total_cleaning_time` | Property in device data | Always | Statistics |
| `cleaning_count` | Property in device data | Always | Statistics |
| `total_cleaned_area` | Property in device data | Always | Statistics |
| `clean_water_tank_status` | self_wash_base + property | Always | Model: base station |
| `dirty_water_tank_status` | self_wash_base + property | Always | Model: base station |
| `dust_bag_status` | auto_empty_base + property | Always | Model: auto-empty dock |
| `detergent_status` | Property in device data | Always | If present |
| `station_drainage_status` | drainage capability | Always | Model: drainage |
| `hot_water_status` | hot_washing capability | Always | Model: hot washing |
| `current_room` | map + lidar_navigation | Current room not None, not mapping | During cleaning only |
| `cleaning_history` | map capability | Last cleaning time not None | After first clean |
| `cruising_history` | map + cruising capability | Last cruising time not None | After first cruise |
| `relocation_status` | Property in device data | Not mapping | State-dependent |
| `firmware_version` | Always | Always | Core entity |

## Binary Sensor Entities (1)

| Key | Existence Condition | Availability Condition | Notes |
|-----|---------------------|----------------------|-------|
| `charging_state` | Always | Always | Core entity, always available if connected |

## Switch Entities (64)

| Key | Existence Condition | Availability Condition | Notes |
|-----|---------------------|----------------------|-------|
| `resume_cleaning` | Property in device data | Always | |
| `carpet_boost` | Property in device data | carpet_recognition active and not carpet_avoidance | State-dependent |
| `obstacle_avoidance` | Property in device data | Always | |
| `customized_cleaning` | Property in device data | Not started, has saved map, not cleangenius | State-dependent |
| `child_lock` | Property in device data | Always | |
| `tight_mopping` | Property + mopping_type is None | Mop installed, not cleangenius | State-dependent |
| `dnd` | Always (custom) | Always | |
| `dnd_disable_resume_cleaning` | dnd_functions + property | DND enabled | Unavailable if DND off |
| `dnd_disable_auto_empty` | dnd_functions + property | DND enabled | Unavailable if DND off |
| `dnd_reduce_volume` | dnd_functions + property | DND enabled | Unavailable if DND off |
| `multi_floor_map` | Property + lidar_navigation | No temp map, not started | State-dependent |
| `auto_dust_collecting` | Property + not auto_empty_mode | auto_dust_collecting enabled | State-dependent |
| `carpet_recognition` | Property + not auto_carpet_cleaning, not mop_pad_lifting_plus | Always | Model-dependent |
| `self_clean` | Property in device data | Always | |
| `water_electrolysis` | Property + self_wash_base + conditions | Always | Model-specific |
| `auto_water_refilling` | water_check + property | Always | Model: water check |
| `intelligent_recognition` | wifi_map + property | Multi-map enabled | State-dependent |
| `auto_drying` | self_wash_base | Always | Model: base station |
| `carpet_avoidance` | Not unmounting/auto_carpet/mop_pad_lifting_plus + carpet_recognition | Always | Model-specific |
| `auto_add_detergent` | Property + detergent or smart_mop_washing | Detergent value != 2 | State-dependent |
| `mop_washing_with_detergent` | mop_washing_with_detergent + property | Always | Model-specific |
| `map_saving` | Property in device data | Always | |
| `auto_mount_mop` | mop_pad_unmounting + property | Always | Model: mop unmounting |
| `voice_assistant` | Property in device data | Always | |
| `cleaning_sequence` | customized_cleaning + map | Not started, has saved map, segments have order | State-dependent |
| `self_clean_by_zone` | self_wash_base + conditions | self_clean active, conditions | State-dependent |
| `ai_obstacle_detection` | AI data present | Always (but AI features depend on it) | |
| `ai_obstacle_image_upload` | AI data present | ai_obstacle_detection enabled | State-dependent |
| `ai_obstacle_picture` | AI data present | ai_obstacle_detection enabled | State-dependent |
| `ai_pet_detection` | AI data present | ai_obstacle_detection enabled | State-dependent |
| `ai_human_detection` | AI data present | ai_obstacle_detection enabled | State-dependent |
| `ai_furniture_detection` | AI data present | ai_obstacle_detection enabled | State-dependent |
| `ai_fluid_detection` | fluid_detection capability | ai_obstacle_detection enabled | Model + state |
| `fuzzy_obstacle_detection` | AI data present | ai_obstacle_detection enabled | State-dependent |
| `ai_pet_avoidance` | pet_detective capability | ai_obstacle + ai_pet enabled | State-dependent |
| `pet_picture` | AI data present | ai_obstacle + ai_pet enabled | State-dependent |
| `pet_focused_detection` | pet_furniture capability | ai_obstacle + ai_pet enabled | State-dependent |
| `large_particles_boost` | large_particles_boost capability | Always | Model-specific |
| `fill_light` | fill_light + auto_switch | Always | Model-specific |
| `collision_avoidance` | Auto-switch data present | Always | |
| `stain_avoidance` | fluid_detection + auto_switch | ai_fluid_detection enabled | State-dependent |
| `floor_direction_cleaning` | floor_direction_cleaning + auto_switch | floor_direction available | State-dependent |
| `pet_focused_cleaning` | pet_detective + auto_switch | Always | Model-specific |
| `intensive_carpet_cleaning` | intensive_carpet_cleaning + auto_switch | Not started, carpet_recognition active | State-dependent |
| `side_reach` | side_reach + auto_switch | Always | Model-specific |
| `mop_extend` | mop_extend + auto_switch | Always | Model-specific |
| `gap_cleaning_extension` | mop_pad_swing_plus + auto_switch | mop_extend or mop_pad_swing > 0 | State-dependent |
| `mopping_under_furnitures` | mop_pad_swing_plus + auto_switch | mop_extend or mop_pad_swing > 0 | State-dependent |
| `off_peak_charging` | off_peak_charging capability | Always | Model-specific |
| `auto_charging` | auto_charging + auto_switch | Always | Model-specific |
| `human_follow` | mop_pad_swing + camera + auto_switch | Always | Model-specific |
| `max_suction_power` | max_suction_power + auto_switch | Sweeping or mopping_after_sweeping, not cleangenius | State-dependent |
| `smart_drying` | smart_drying + auto_switch | Always | Model-specific |
| `hot_washing` | hot_washing + not smart_mop + auto_switch | Always | Model-specific |
| `uv_sterilization` | uv_sterilization + auto_switch | Always | Model-specific |
| `ultra_clean_mode` | ultra_clean_mode + not smart_mop + auto_switch | self_clean active | State-dependent |
| `streaming_voice_prompt` | camera_streaming + auto_switch | Always | Model: camera |
| `clean_carpets_first` | clean_carpets_first + property | Not started, carpet_recognition active | State-dependent |
| `smart_mop_washing` | smart_mop_washing + property | self_clean active | State-dependent |
| `silent_drying` | silent_drying + property | Not drying | State-dependent |
| `hair_compression` | hair_compression + property | Always | Model-specific |
| `side_brush_carpet_rotate` | side_brush_carpet_rotate + property | carpet_recognition, not avoidance, carpet_cleaning != 6 | State-dependent |
| `auto_lds_lifting` | auto_lds_lifting + property | Always | Model-specific |
| `camera_light_brightness_auto` | camera_streaming + fill_light | Camera light on, stream active | State-dependent |

## Select Entities (27 global + 12 per-room)

### Global Selects

| Key | Existence Condition | Availability Condition | Notes |
|-----|---------------------|----------------------|-------|
| `suction_level` | Property in device data | Complex: not mopping, not custom, not cleangenius, not mapping | State-dependent |
| `water_volume` | Property + not self_wash_base | Mop installed, not sweeping, not custom, not cleangenius | State + model |
| `cleaning_mode` | Property in device data | Complex: not started/mopping_after_sweeping, many exclusions | State-dependent |
| `carpet_sensitivity` | Property + not carpet_recognition | carpet_boost enabled | State-dependent |
| `carpet_cleaning` | mop_pad_unmounting or auto_carpet or mop_pad_lifting_plus | carpet_recognition or mop_pad_lifting_plus or auto_carpet | Model + state |
| `auto_empty_frequency` | Property + not auto_empty_mode | auto_dust_collecting enabled | State-dependent |
| `drying_time` | Property + not mop_clean_frequency | Not smart_drying, not silent_drying | State-dependent |
| `mop_wash_level` | Property + self_wash_base + not smart_mop | Not ultra_clean_mode, self_clean active | State-dependent |
| `voice_assistant_language` | voice_assistant capability | voice_assistant == 1 (enabled) | State-dependent |
| `mop_pad_humidity` | self_wash_base | Complex: mop installed, not sweeping, not started, not cleangenius | State-dependent |
| `mopping_type` | self_wash_base + not custom_route + not cleaning_route | Not started, not mapping | State-dependent |
| `custom_mopping_route` | custom_mopping_route capability | Not started, not cleangenius, not customized | State-dependent |
| `wider_corner_coverage` | Not mop_pad_swing + not mop_clean_freq + auto_switch | Not started, not mapping, not washing | State-dependent |
| `mop_pad_swing` | mop_pad_swing + not mop_extend + auto_switch | Not started, not mapping, not washing | State-dependent |
| `mop_extend_frequency` | mop_extend + auto_switch | Not started, not mapping, not washing | State-dependent |
| `self_clean_frequency` | self_clean_frequency + auto_switch | self_clean on, not started, not mapping | State-dependent |
| `auto_recleaning` | auto_recleaning + auto_switch | No temp map, has segments, not started | State-dependent |
| `auto_rewashing` | auto_rewashing + auto_switch | No temp map, has segments, not started | State-dependent |
| `cleaning_route` | cleaning_route + auto_switch | Complex: segments, route > 0, not started, conditions | State-dependent |
| `cleangenius` | cleangenius + auto_switch | Not started, not mapping, not cruising, mop installed | State-dependent |
| `cleangenius_mode` | cleangenius_mode capability | Cleangenius active, not started, mop installed | State-dependent |
| `water_temperature` | water_temperature + property | Not smart_mop_washing, self_clean active | State-dependent |
| `auto_empty_mode` | auto_empty_mode capability | Always | Model-specific |
| `mop_clean_frequency` | self_wash_base + mop_clean_frequency | self_clean active, not cleangenius, not mapping | State-dependent |
| `washing_mode` | smart_mop_washing + property | Not smart_mop_washing, self_clean active | State-dependent |
| `map_rotation` | map capability | Selected map exists, not mapping, has saved map | State-dependent |
| `selected_map` | map + multi_floor_map | Complex: multi_map, map data, map list | State-dependent |

### Per-Room Selects (created for each room/segment)

| Key | Existence Condition | Availability Condition | Notes |
|-----|---------------------|----------------------|-------|
| `suction_level_room` | customized_cleaning | custom_cleaning or cleangenius | State-dependent |
| `water_volume_room` | customized_cleaning + not self_wash_base | custom_cleaning or cleangenius | State + model |
| `mop_pad_humidity_room` | customized_cleaning + self_wash_base | custom_cleaning or cleangenius | State + model |
| `cleaning_mode_room` | customized_cleaning + custom_cleaning_mode | custom_cleaning or cleangenius | State-dependent |
| `cleaning_times_room` | customized_cleaning | custom_cleaning or cleangenius | State-dependent |
| `custom_mopping_route_room` | segment_mopping_settings + not cleaning_route | custom_cleaning or cleangenius | State-dependent |
| `cleaning_route_room` | cleaning_route capability | custom_cleaning or cleangenius | State-dependent |
| `order_room` | customized_cleaning | custom_cleaning or cleangenius | State-dependent |
| `floor_material_room` | floor_material capability | custom_cleaning or cleangenius | Model-dependent |
| `floor_material_direction_room` | floor_direction_cleaning | custom_cleaning or cleangenius | Model-dependent |
| `visibility_room` | segment_visibility capability | custom_cleaning or cleangenius | Model-dependent |
| `name_room` | Always (default) | custom_cleaning or cleangenius | State-dependent |

## Number Entities (7 global + 1 per-room)

| Key | Existence Condition | Availability Condition | Notes |
|-----|---------------------|----------------------|-------|
| `volume` | Property in device data | Always | |
| `mop_cleaning_remainder` | Property + not self_wash_base | Always | Model: no base |
| `self_clean_area` | self_wash_base + not mop_clean_frequency | self_clean, not cleangenius, not by_time, conditions | State-dependent |
| `self_clean_time` | self_clean_frequency + not mop_clean_frequency | self_clean, not cleangenius, by_time, conditions | State-dependent |
| `camera_light_brightness` | camera_streaming + fill_light | Camera light on, brightness != 101, stream active | State-dependent |
| `wetness_level` | wetness_level + property | Mop installed, not sweeping, not cleangenius, not mapping | State-dependent |
| `drying_time` | mop_clean_frequency + property | Not smart_drying | State-dependent |
| `wetness_level_room` | wetness_level capability | custom_cleaning or cleangenius | Per-room, state |

## Button Entities (26 + dynamic)

| Key | Existence Condition | Availability Condition | Notes |
|-----|---------------------|----------------------|-------|
| `reset_main_brush` | Action + main_brush_life exists | main_brush_life < 100% | Only when worn |
| `reset_side_brush` | Action + side_brush_life exists | side_brush_life < 100% | Only when worn |
| `reset_filter` | Action + filter_life exists | filter_life < 100% | Only when worn |
| `reset_sensor` | Not disable_sensor_cleaning | sensor_dirty_life < 100% | Only when worn |
| `reset_mop_pad` | Action + mop_life exists | mop_life < 100% | Only when worn |
| `reset_silver_ion` | Action + silver_ion_life exists | silver_ion_life < 100% | Only when worn |
| `reset_detergent` | Action + detergent capability | detergent_life < 100% | Only when worn |
| `reset_squeegee` | Action + squeegee_life exists | squeegee_life < 100% | Only when worn |
| `reset_onboard_dirty_water_tank` | Action + life exists | life < 100% | Only when worn |
| `reset_dirty_water_tank` | Action + life exists | life < 100% | Only when worn |
| `reset_deodorizer` | Action + deodorizer capability | deodorizer_life < 100% | Only when worn |
| `reset_scale_inhibitor` | Action + scale_inhibitor | scale_inhibitor_life < 100% | Only when worn |
| `reset_wheel` | Action + wheel capability | wheel_dirty_life < 100% | Only when worn |
| `start_auto_empty` | Action + auto_empty_base | dust_collection_available | State-dependent |
| `clear_warning` | Always (default action) | has_warning or low_water or draining_complete | State-dependent |
| `start_fast_mapping` | lidar_navigation | mapping_available, not draining/repairing | State-dependent |
| `start_mapping` | lidar_navigation | mapping_available, not draining/repairing | State-dependent |
| `self_clean` | self_wash_base | washing_available, not draining/repairing | State-dependent |
| `manual_drying` | self_wash_base | drying_available, not draining/repairing | State-dependent |
| `water_tank_draining` | self_wash_base + drainage | water_draining_available | State-dependent |
| `empty_water_tank` | self_wash_base + empty_water_tank | Not draining, docked, not repairing/washing | State-dependent |
| `base_station_self_repair` | self_wash_base | Complex: not active (many exclusions) | State-dependent |
| `base_station_cleaning` | station_cleaning capability | Docked, not active, mop installed | State-dependent |
| `start_recleaning` | auto_recleaning + map | Not started, second_cleaning_available | State-dependent |
| `reload_shortcuts` | shortcuts capability | Always | Model-specific |
| `backup/restore` | map capability | Not started / backup conditions | Dynamic |
| `shortcut_*` | shortcuts capability | Dynamic per shortcut | Dynamic |

## Time Entities (4)

| Key | Existence Condition | Availability Condition | Notes |
|-----|---------------------|----------------------|-------|
| `dnd_start` | dnd capability | DND enabled | Unavailable if DND off |
| `dnd_end` | dnd capability | DND enabled | Unavailable if DND off |
| `off_peak_charging_start` | off_peak_charging capability | off_peak_charging enabled | Unavailable if off |
| `off_peak_charging_end` | off_peak_charging capability | off_peak_charging enabled | Unavailable if off |

---

## Expected Entities by Device Type

### Minimum (all models)
- binary_sensor: `charging_state`
- sensor: `status`, `battery_level`, `cleaning_time`, `cleaned_area`, `main_brush_left/time`, `side_brush_left/time`, `filter_left/time`, `total_cleaning_time`, `cleaning_count`, `total_cleaned_area`, `firmware_version`
- switch: `child_lock`, `dnd`
- number: `volume`

### + LIDAR navigation (most models)
- sensor: `mapping_time`, `current_room`
- switch: `multi_floor_map`
- button: `start_fast_mapping`, `start_mapping`
- select: `map_rotation`

### + Map capability
- sensor: `cleaning_history`
- switch: `cleaning_sequence`
- select: `selected_map` (if multi_floor_map)

### + Self-wash base station
- sensor: `mop_pad`, `low_water_warning`, `clean_water_tank_status`, `dirty_water_tank_status`
- switch: `self_clean`, `auto_drying`
- select: `mop_pad_humidity`, `mop_wash_level`
- button: `self_clean`, `manual_drying`
- number: `self_clean_area` or `self_clean_time`

### + Auto-empty dock
- sensor: `dust_bag_status`
- button: `start_auto_empty`
- switch: `auto_dust_collecting` or select: `auto_empty_mode`

### + Camera
- sensor: `stream_status`
- switch: `streaming_voice_prompt`
- number: `camera_light_brightness` (if fill_light)

### + AI features
- switch: `ai_obstacle_detection`, `ai_pet_detection`, `ai_furniture_detection`, etc.

### + Advanced consumables
- sensor/button pairs: `detergent`, `deodorizer`, `wheel`, `scale_inhibitor` (model-dependent)

---

## Common "Unavailable" Scenarios (Normal Behavior)

| Entity | When Unavailable | Why |
|--------|-----------------|-----|
| Suction level | Mopping mode | Can't change suction while mopping |
| Water volume | Sweeping mode | Can't change water while sweeping |
| Cleaning mode | During cleaning | Can't switch mode mid-clean |
| Customized cleaning | During cleaning | Can't toggle while active |
| Reset consumable buttons | Consumable at 100% | Nothing to reset |
| Start/mapping buttons | During cleaning | Can't start new task |
| DND sub-switches | DND disabled | Only configurable when DND is on |
| AI sub-switches | AI detection off | Parent toggle must be on first |
| Cleangenius mode | Cleangenius off | Only when cleangenius is active |
| Selected map | Single map / temp map | Need multi-map + saved maps |
| Self-clean settings | Self-clean off | Toggle self-clean first |
| Time entities | Feature disabled | Enable DND or off-peak first |
| Per-room selects | Custom cleaning off | Enable customized cleaning first |
