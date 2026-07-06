# Services
The integration adds the following services to vacuum domain.

## Vacuum Services
Services for actions that are not available via an entity.

<a href="https://my.home-assistant.io/redirect/developer_services/" target="_blank"><img src="https://my.home-assistant.io/badges/developer_services.svg" alt="Open your Home Assistant instance and show your service developer tools." /></a>

### `dreame_vacuum.vacuum_clean_segment`

Start selected room cleaning with optional customized cleaning parameters.
> - If you are using integration with map feature, you can acquire segment ids from vacuum entity attributes.
> - Cleaning parameters and cleaning sequence are ignored by the device when `customized_cleaning` or `cleaning_sequence` is enabled.

**Examples:**

- Clean room 3
    ```yaml
    service: dreame_vacuum.vacuum_clean_segment
    data:
      segments: 3
    target:
      entity_id: vacuum.vacuum
    ```
- Clean room 3 and 5
    ```yaml
    service: dreame_vacuum.vacuum_clean_segment
    data:
      segments:
        - 3
        - 5
    target:
      entity_id: vacuum.vacuum
    ```

- Clean room 3 and 5 two times
    ```yaml
    service: dreame_vacuum.vacuum_clean_segment
    data:
      segments:
        - 3
        - 5
      repeats: 2
    target:
      entity_id: vacuum.vacuum
    ```

- Clean room 2 two times and 5 one time
    ```yaml
    service: dreame_vacuum.vacuum_clean_segment
    data:
      segments:
        - 3
        - 5
      repeats:
        - 2
        - 1
    target:
      entity_id: vacuum.vacuum
    ```

- Clean room 3 and 5 with high fan speed
    ```yaml
    service: dreame_vacuum.vacuum_clean_segment
    data:
      segments:
        - 3
        - 5
      suction_level: "high"
    target:
      entity_id: vacuum.vacuum
    ```

- Clean room 3 with high fan speed and 5 with quiet fan speed
    ```yaml
    service: dreame_vacuum.vacuum_clean_segment
    data:
      segments:
        - 3
        - 5
      suction_level:
        - "high"
        - "quiet"
    target:
      entity_id: vacuum.vacuum
    ```


### `dreame_vacuum.vacuum_clean_zone`

Start selected zone cleaning with optional customized cleaning parameters.

> You can acquire zone coordinates with <a href="https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card/blob/master/docs/templates/setup.md#getting-coordinates" target="_blank_">Xiaomi Vacuum Map Card</a>.

**Examples:**

- Clean selected zone
    ```yaml
    service: dreame_vacuum.vacuum_clean_zone
    data:
      zone:
        - 819
        - -263
        - 4424
        - 2105
    target:
      entity_id: vacuum.vacuum
    ```
- Clean multiple zones
    ```yaml
    service: dreame_vacuum.vacuum_clean_zone
    data:
      zone:
        - - 819
          - -263
          - 4424
          - 2105
        - - 2001
          - -3050
          - 542
          - 515
    target:
      entity_id: vacuum.vacuum
    ```
- Clean selected zone two times
    ```yaml
    service: dreame_vacuum.vacuum_clean_zone
    data:
      zone:
        - 819
        - -263
        - 4424
        - 2105
      repeats: 2
    target:
      entity_id: vacuum.vacuum
    ```

- Clean first zone two times second zone three times
    ```yaml
    service: dreame_vacuum.vacuum_clean_zone
    data:
      zone:
        - - 819
          - -263
          - 4424
          - 2105
        - - 2001
          - -3050
          - 542
          - 515
      repeats:
        - 2
        - 3
    target:
      entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_clean_spot`

Start selected spot cleaning with optional customized cleaning parameters.

> Spot cleaning feature is only available for Xiaomi/Mijia branded robots but it works with the Dreame devices too.

> You can acquire point coordinates with <a href="https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card/blob/master/docs/templates/setup.md#getting-coordinates" target="_blank_">Xiaomi Vacuum Map Card</a>.

**Examples:**

- Clean selected spot
    ```yaml
    service: dreame_vacuum.vacuum_clean_spot
    data:
      points:
        - 819
        - -263
    target:
      entity_id: vacuum.vacuum
    ```
- Clean multiple spots
    ```yaml
    service: dreame_vacuum.vacuum_clean_spot
    data:
      points:
        - - 819
          - -263
        - - 2001
          - -3050
    target:
      entity_id: vacuum.vacuum
    ```
- Clean selected spot two times
    ```yaml
    service: dreame_vacuum.vacuum_clean_spot
    data:
      points:
        - 819
        - -263
      repeats: 2
    target:
      entity_id: vacuum.vacuum
    ```

- Clean first spot two times second spot three times
    ```yaml
    service: dreame_vacuum.vacuum_clean_spot
    data:
      points:
        - - 819
          - -263
        - - 2001
          - -3050
      repeats:
        - 2
        - 3
    target:
      entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_goto`

Move the robot to a specific coordinate on the current map without cleaning along the way. On devices without native point-cruising support, the integration triggers a small zone-clean centered on the point instead.

> - The coordinate must be inside the current map.
> - Battery must be at least 15%.
> - Not available while the device is draining the mop tank or self-repairing/testing.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `x` | yes | X coordinate on the current map | `819` |
| `y` | yes | Y coordinate on the current map | `-2235` |

**Example:**

- Go to [819, -2235] and stop
    ```yaml
    service: dreame_vacuum.vacuum_goto
    data:
      x: 819
      y: -2235
    target:
      entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_follow_path`

Start a "follow path" surveillance job: the robot cruises through the given waypoints in order while live camera streaming is active, without cleaning. If `points` is omitted, the map's saved predefined points (see `vacuum_set_predefined_points`) are used instead.

> - Requires a device with cruising capability and an active camera stream (follow path only works with live camera streaming).
> - Battery must be at least 15%.
> - Not available while the device is draining the mop tank or self-repairing/testing.
> - At most 20 points are sent to the device; extra points are ignored.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `points` | no | One `[x, y]` pair or a list of `[x, y]` pairs to cruise through, in order | `[819,-263] or [[819,-263],[900,-463]]` |

**Example:**

- Follow a two-point path
    ```yaml
    service: dreame_vacuum.vacuum_follow_path
    data:
      points:
        - - 819
          - -263
        - - 900
          - -463
    target:
      entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_start_shortcut`

Run a saved shortcut (a saved sequence of cleaning actions, configured in the Dreame app) by its id.

> - Shortcuts are only available on devices that support the shortcuts feature.
> - `shortcut_id` must be between 32 and 128 inclusive.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `shortcut_id` | yes | Id of the shortcut to run (32-128) | `32` |

**Example:**

- Run shortcut 32
    ```yaml
    service: dreame_vacuum.vacuum_start_shortcut
    data:
      shortcut_id: 32
    target:
      entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_remote_control_move_step`

Send remote control command to vacuum. *(For use of a custom lovelace card)*

### `dreame_vacuum.vacuum_install_voice_pack`

Install an official voice pack.

### `dreame_vacuum.vacuum_set_cleaning_sequence`

Set room cleaning sequence on current map.

> Exact number of room ids must be passed as sequence list

**Example:**

- Set room cleaning sequence on current map to 3, 5, 4, 2, 1
    ```yaml
    service: dreame_vacuum.vacuum_set_cleaning_sequence
    data:
        cleaning_sequence:
          - 3
          - 5
          - 4
          - 2
          - 1
    target:
        entity_id: vacuum.vacuum
    ```

- Disable custom cleaning sequence on current map
    ```yaml
    service: dreame_vacuum.vacuum_set_cleaning_sequence
    data:
        cleaning_sequence: []
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_set_custom_cleaning`

Set customized room cleaning parameters on current map.

> Settings for all rooms must be passed as list

**Examples:**

- Set room 1 fan speed to quiet, water level to low, cleaning times to 2 and room 5 fan speed to turbo, water level to medium, repeats to 1
    ```yaml
    service: dreame_vacuum.vacuum_set_custom_cleaning
    data:
        segment_id:
          - 1
          - 5
        suction_level:
          - 0
          - 3
        water_volume:
          - 1
          - 2
        repeats:
          - 2
          - 1
    target:
        entity_id: vacuum.vacuum
    ```

- Set room 3 wetness level to 16
    ```yaml
    service: dreame_vacuum.vacuum_set_custom_cleaning
    data:
        segment_id:
          - 3
        wetness_level:
          - 16
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_set_custom_carpet_cleaning`

Set per-carpet cleaning behavior on the current map (only available on devices with carpet recognition).

> - Settings for all targeted carpets must be passed as lists (or a single value applied to a single carpet).
> - `carpet_settings` requires a device with carpet cleanset v3 support; unsupported flags for your device are ignored.
> - Not available while a temporary (unsaved) map is present.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `id` | yes | Carpet id(s) to configure | `[1,2] or 3` |
| `type` | yes | Carpet type: `0` = automatically detected, `1` = manually created, `2` = room carpet (device dependent) | `[0,1] or 1` |
| `carpet_cleaning` | no | Cleaning behavior: `0`/omitted = not set, `1` = avoidance, `2` = adaptation, `3` = remove mop, `4` = adaptation without route, `5` = vacuum and mop, `6` = ignore, `7` = cross | `[0,3] or 5` |
| `carpet_settings` | no | Extra flags applied on top of `carpet_cleaning` (device dependent): `carpet_boost`, `clean_carpets_first`, `intensive_carpet_cleaning`, `side_brush_carpet_rotate` | `['carpet_boost'] or 'clean_carpets_first' or []` |

**Example:**

- Set carpet 3 (manually created) to vacuum and mop with carpet boost enabled
    ```yaml
    service: dreame_vacuum.vacuum_set_custom_carpet_cleaning
    data:
        id: 3
        type: 1
        carpet_cleaning: 5
        carpet_settings:
          - "carpet_boost"
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_reset_consumable`

Reset a consumable life by type.

> Possible values for consumable
>  - `main_brush`
>  - `side_brush`
>  - `filter`
>  - `tank_filter`
>  - `sensor`
>  - `mop_pad`
>  - `silver_ion`
>  - `detergent`
>  - `squeege`
>  - `dirty_water_tank`
>  - `onboard_dirty_water_tank`
>  - `deodorizer`
>  - `wheel`
>  - `scale_inhibitor`

**Examples:**

- Reset Main Brush Life
    ```yaml
    service: dreame_vacuum.vacuum_reset_consumable
    data:
        consumable: "main_brush"
    target:
        entity_id: vacuum.vacuum
    ```

- Reset Mop Pad Life
    ```yaml
    service: dreame_vacuum.vacuum_reset_consumable
    data:
        consumable: "mop_pad"
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_set_property`

Low-level escape hatch: directly set a device property by name, bypassing the integration's higher-level services.

> **Warning**: `key` must match the name of a `DreameVacuumProperty` (or auto-switch/AI property) member defined in `custom_components/dreame_vacuum/dreame/vacuum_types.py`, whose human-readable mapping lives in `dreame/const.py` (for example `suction_level`, `water_volume`, `cleaning_mode`). Values are validated against the matching enum/type where one exists, but setting an unsupported or out-of-range value for your specific device can still misconfigure it. Prefer the dedicated services (e.g. `vacuum_set_custom_cleaning`) when one already covers your use case.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `key` | yes | Name of the property to set (case-insensitive) | `suction_level` |
| `value` | no | Value to set; accepted forms depend on the property (integer, enum name, or boolean) | `2` |

**Example:**

- Set suction level to level 2 directly
    ```yaml
    service: dreame_vacuum.vacuum_set_property
    data:
        key: suction_level
        value: 2
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_call_action`

Low-level escape hatch: directly invoke a device action by name, bypassing the integration's higher-level services.

> **Warning**: `key` must match the name of a `DreameVacuumAction` member defined in `custom_components/dreame_vacuum/dreame/vacuum_types.py`, whose human-readable mapping lives in `dreame/const.py` (for example `start_auto_empty`). Calling an action that is unavailable or nonsensical for your model/current state can produce a device error or unexpected behavior. Prefer the dedicated services (e.g. `vacuum_reset_consumable`) when one already covers your use case.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `key` | yes | Name of the action to call (case-insensitive) | `start_auto_empty` |
| `value` | no | Optional parameter passed to the action *(behavior to confirm — meaning depends entirely on which action is called)* | — |

**Example:**

- Trigger auto-empty of the dust bin
    ```yaml
    service: dreame_vacuum.vacuum_call_action
    data:
        key: start_auto_empty
    target:
        entity_id: vacuum.vacuum
    ```

### *`vacuum.send_command`*

Send command service can be used to send raw api requests that are not available with this integration.

> <a href="https://github.com/al-one/hass-xiaomi-miot#xiaomi-miot-for-homeassistant" target="_blank">More info about commands and parameters.</a>

**Examples:**

- Start auto emptying
    ```yaml
    service: vacuum.send_command
    data:
        entity_id: vacuum.vacuum
        command: action
        params:
            did: "15.1"
            siid: 15
            aiid: 1
            in: []
    ```

- Enable tight mopping pattern and disable carpet boost
    ```yaml
    service: vacuum.send_command
    data:
        entity_id: vacuum.vacuum
        command: set_properties
        params:
          - did: "4.29"
            siid: 4
            piid: 29
            value: 1
          - did: "4.12"
            siid: 4
            piid: 12
            value: 0
    ```

## Schedule Services
Services for creating, editing and deleting scheduled cleaning tasks (`status.schedule` / the `schedule` entity attribute). See `docs/dev/schedule-format.md` for the full wire-format derivation these services are built on.

> **Limitations (read before using `vacuum_set_schedule`):** the device's raw `SCHEDULE` property packs each task into an opaque, semicolon/dash-separated string. Several fields in that format are not fully understood from static analysis alone:
> - The enabled/status field has two device-confirmed "enabled" wire values (`1` and `2`); what distinguishes them is unknown, so this integration always writes `1` for an enabled task.
> - `repeats` (the day-of-week/repeat pattern) and `options` are passed through **as opaque raw values** — this integration does not decode or validate their meaning. If you need a specific repeat pattern, read back an existing task's `repeats` value (e.g. from the `schedule` attribute of a vacuum entity, once one has been configured from the official app) and reuse it verbatim; do not guess an encoding.
> - `suction_level` and `water_volume` have no known default, so they are **required** when creating a new task (`schedule_id` omitted); they remain optional when editing an existing task, where the previous value is kept if omitted.
> - When editing an existing task (`schedule_id` provided), any field left out keeps the previous value for that task. Passing `options: []` explicitly clears the previous options (sets it to "no options"), while omitting `options` entirely preserves whatever was there before.
> - All other scheduled tasks are left byte-identical; only the targeted task is added, replaced, or removed.

### `dreame_vacuum.vacuum_delete_schedule`

Delete a scheduled cleaning task.

> - You can acquire the schedule id from the vacuum entity's `schedule` attribute.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `schedule_id` | yes | ID of the scheduled task to delete | `5` |

**Example:**

- Delete the scheduled task with id 5
    ```yaml
    service: dreame_vacuum.vacuum_delete_schedule
    data:
        schedule_id: 5
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_set_schedule`

Create or update a scheduled cleaning task. Omit `schedule_id` to create a new task; pass an existing `schedule_id` to update it in place.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `schedule_id` | no | ID of the task to update. Omit to create a new task | `5` |
| `enabled` | yes | Whether the task is enabled | `true` |
| `time` | yes | Time of day the task runs, as `HH:MM` | `"08:00"` |
| `repeats` | no | Raw, device-specific repeat pattern (opaque, not decoded by this integration). Keeps the previous value on edit if omitted | `"127"` |
| `once` | no | Run once instead of repeating (default `false`) | `true` |
| `map_id` | no | ID of the map this task applies to. Keeps the previous value on edit if omitted | `"1"` |
| `suction_level` | no\* | Suction level for the task. \*Required when creating a new task | `1` |
| `water_volume` | no\* | Water volume for the task. \*Required when creating a new task | `1` |
| `options` | no | Raw list of option codes (opaque, not decoded by this integration). Keeps the previous value on edit if omitted; pass `[]` to explicitly clear | `["1", "2"]` |

**Examples:**

- Create a new, enabled, non-repeating task at 08:00
    ```yaml
    service: dreame_vacuum.vacuum_set_schedule
    data:
        enabled: true
        time: "08:00"
        once: true
        suction_level: 1
        water_volume: 1
    target:
        entity_id: vacuum.vacuum
    ```

- Update the time of the existing task with id 5, keeping every other field as-is
    ```yaml
    service: dreame_vacuum.vacuum_set_schedule
    data:
        schedule_id: 5
        enabled: true
        time: "07:30"
    target:
        entity_id: vacuum.vacuum
    ```

- Disable the existing task with id 5 without changing anything else
    ```yaml
    service: dreame_vacuum.vacuum_set_schedule
    data:
        schedule_id: 5
        enabled: false
        time: "07:30"
    target:
        entity_id: vacuum.vacuum
    ```

## Map Services
Map editing services also uses the vacuum domain because all services are available even without cloud connection.

<a href="https://my.home-assistant.io/redirect/developer_services/" target="_blank"><img src="https://my.home-assistant.io/badges/developer_services.svg" alt="Open your Home Assistant instance and show your service developer tools." /></a>

### `dreame_vacuum.vacuum_request_map`

Request device to upload a new map to the cloud. *(This service is useful when cloud connection is not used and another integration used for handing the map rendering)*

> Device does not responds to this action when:
> - Spot cleaning
> - Fast mapping
> - Relocating
> - After a map edit until it moves

### `dreame_vacuum.vacuum_select_map`

Change currently selected map. (Only possible of multi-floor map is enabled)

> - You can acquire map id from saved map camera entity attributes.

> - Robot will end active job when selected map is changed.

**Example:**

- Set current map as map with id 27
    ```yaml
    service: dreame_vacuum.vacuum_select_map
    data:
        map_id: 27
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_delete_map`

Delete a map.

> - You can acquire map id from saved map camera entity attributes.
> - When multi-floor map feature is enabled map indexes may change after deletion. <a href="https://github.com/foXaCe/dreame-vacuum/blob/main/docs/#multi-floor-map-support" target="_blank">(More about multi-floor map support)</a>

**Example:**

- Set delete map with id 48
    ```yaml
    service: dreame_vacuum.vacuum_delete_map
    data:
        map_id: 48
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_rename_map`

Rename a map.

> - You can acquire map id from saved map camera entity attributes.
> - Official App does not allow you to enter special characters in map name but this integration does so use this service carefully.

**Example:**

- Rename map with id 14 to "Second Floor"
    ```yaml
    service: dreame_vacuum.vacuum_rename_map
    data:
        map_id: 14
        map_name: "Second Floor"
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_restore_map`

Restore a map from previous state that are created and uploaded by the device.
> - It is not guaranteed that map recovery will be successful. Cloud does not store the files forever and recovery files usually be deleted from the cloud after 365 days from the last access.
>  - Cloud connection is required with this service.

**Examples:**

- Restore selected map to second saved recovery map in the recovery map list
    ```yaml
    service: dreame_vacuum.vacuum_restore_map
    data:
        recovery_map_index: 2
    target:
        entity_id: vacuum.vacuum
    ```

- Restore saved map with id 14 to original state
    ```yaml
    service: dreame_vacuum.vacuum_restore_map
    data:
        map_id: 14
        recovery_map_index: 1
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_restore_map_from_file`

Restore a map from previously saved recovery map file.
> - This service can be used for offline recovery if you download and place the recovery map file to the /www/ folder of Home Assistant (Vacuum and server must be at the same network).
> - Map Id is required if cloud connection is not enabled.

**Examples:**

- Restore selected map from saved recovery map file
    ```yaml
    service: dreame_vacuum.vacuum_restore_map_from_file
    data:
        file_url: http://192.168.1.10/local/2023-11-04-1724223415-423528451_284320462.1156.mb.tbz2
    target:
        entity_id: vacuum.vacuum
    ```

- Restore saved map with id 14 saved recovery map file
    ```yaml
    service: dreame_vacuum.vacuum_restore_map_from_file
    data:
        map_id: 14
        file_url: https://dreame-cn.oss-cn-shanghai.aliyuncs.com/iot/tmp/000000/ali_dreame/YR649291/648921668/101?Expires=1699189998&OSSAccessKeyId=LTAI5t96WkBXXNzQrX4HtQti&Signature=ttRrjg8p7aC650H3DwI3%2F2ngOOE%3D
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_backup_map`

Trigger upload of a saved map as a recovery map to the cloud.
> - Cloud can store only one backup map for every saved map. This service will override the previously backup map if you have one.
> - Vacuums without a camera or a lidar sensor does not have this feature, map backup trigger only works on supported devices.

**Examples:**

- Trigger backup of selected map
    ```yaml
    service: dreame_vacuum.vacuum_backup_map
    target:
        entity_id: vacuum.vacuum
    ```

- Trigger backup of map with id 15
    ```yaml
    service: dreame_vacuum.vacuum_backup_map
    data:
        map_id: 15
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_set_restricted_zone`

Set invisible walls, no go and no mopping zones on current map.

> - You can acquire line and zone coordinates with <a href="https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card/blob/master/docs/templates/setup.md#getting-coordinates" target="_blank_">Xiaomi Vacuum Map Card</a>.
> - All object must be passed at one, you cannot add or remove single wall or no zone. You can acquire current line and zone coordinates from selected map camera entity attributes.

**Examples:**

- Define virtual walls, restricted zones, and/or no mop zones
    ```yaml
    service: dreame_vacuum.vacuum_set_restricted_zone
    data:
        walls:
            - - 819
              - -263
              - 4424
              - 2105
        zones:
            - - 819
              - -263
              - 4424
              - 2105
            - - -2001
              - -3050
              - -542
              - 515
        no_mops: []
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_save_temporary_map`

Save newly created map. (Device ask you to do when first map is created after factory reset)

### `dreame_vacuum.vacuum_discard_temporary_map`

Discard newly created map.

### `dreame_vacuum.vacuum_replace_temporary_map`

Replace new map with an old one.

> - You can acquire map id from saved map camera entity attributes.
> - When multi-floor map feature is enabled map indexes may change after replacing the map. Replaced new map will always be at last available index event replaced with a lower indexed map. <a href="https://github.com/foXaCe/dreame-vacuum/blob/main/docs/#multi-floor-map-support" target="_blank">(More about multi-floor map support)</a>

**Example:**

- Replace new map with map with id 39
    ```yaml
    service: dreame_vacuum.vacuum_replace_temporary_map
    data:
        map_id: 39
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_merge_segments`

Merge two rooms from a map.

> - You can acquire map and segment ids from saved map camera entity attributes.
> - Rooms needs to be neighbors with each other.
> - Deleted segment ids are not used again on new created segments.
> - When multi-floor map feature is enabled selected map will change to edited map.

**Examples:**

- Merge rooms 4 with 6 on the map with 63 (Room 6 will be deleted)
    ```yaml
    service: dreame_vacuum.vacuum_replace_temporary_map
    data:
        map_id: 63
        segments:
            - 4
            - 6
    target:
        entity_id: vacuum.vacuum
    ```

- Merge rooms 6 with 4 on the map with 63 (Room 4 will be deleted)
    ```yaml
    service: dreame_vacuum.vacuum_replace_temporary_map
    data:
        map_id: 63
        segments:
            - 6
            - 4
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_split_segments`

Split a map room into to different rooms.

> - You can acquire map and segment ids from saved map camera entity attributes.
> - You can acquire line coordinates coordinates with <a href="https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card/blob/master/docs/templates/setup.md#getting-coordinates" target="_blank_">Xiaomi Vacuum Map Card</a>.
> - Line coordinates must cover selected room area.
> - Deleted segment ids are not used again and new segment always will be at highest next available index.
> - When multi-floor map feature is enabled selected map will change to edited map.

**Example:**

- Split room 4 from line coordinates (A new room will be created and room 4 settings will set to defaults)
    ```yaml
    service: dreame_vacuum.vacuum_replace_temporary_map
    data:
        map_id: 63
        segment: 4
        line:
            - 819
            - -263
            - 4424
            - 2105
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_rename_segment`

Set custom name for a room in current map.

> - You can acquire map and segment ids from saved map camera entity attributes.
> - Official App does not allow you to enter special characters in room name but this integration does so use this service carefully.

**Example:**
- Rename room 3 to "Dining Room"
    ```yaml
    service: dreame_vacuum.vacuum_rename_segment
    data:
        segment_id: 3
        segment_name: "Dining Room"
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_rename_shortcut`

Rename a saved shortcut.

> - The vacuum must not be running.
> - If the requested name is already used by another shortcut, a numeric suffix is appended automatically.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `shortcut_id` | yes | Id of the shortcut to rename | `32` |
| `shortcut_name` | yes | New name for the shortcut | `"Mopping after sweeping"` |

**Example:**

- Rename shortcut 32 to "Mopping after sweeping"
    ```yaml
    service: dreame_vacuum.vacuum_rename_shortcut
    data:
        shortcut_id: 32
        shortcut_name: "Mopping after sweeping"
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_set_dnd_task`

Create or update a single multi-window Do Not Disturb (DnD) task by id.

> - Only supported on devices reporting the `dnd_task` capability (devices whose firmware supports several
>   named DnD windows). On other devices, keep using the `dnd` switch entity and the `dnd_start`/`dnd_end`
>   time entities — this service is rejected on those devices.
> - Omit `task_id` to create a new task; the device assigns the next free id.
> - If `task_id` is given but doesn't match an existing task, a new task is created with that exact id.
> - `weekday_mask` is the **raw** weekday bitmask reported by the device firmware. **The bit-to-day mapping
>   is not confirmed on a live device** — only `127` (all 7 bits set) is known to mean "all days". This
>   service never decodes or interprets the value; it is passed straight to the device. Omit it to preserve
>   an existing task's mask, or to default a new task to `127` (all days). See
>   `docs/dev/dnd-tasks-design.md` for the full wire-format writeup and open unknowns.
> - All tasks (not just the first) are exposed read-only via the vacuum entity's `dnd` attribute, keyed by
>   task id, including the raw `weekday_mask` for each task.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `task_id` | no | Id of the task to update; omit to create a new task | `1` |
| `enabled` | yes | Whether the task is enabled | `true` |
| `start` | yes | Window start time (`HH:MM`) | `"22:00"` |
| `end` | yes | Window end time (`HH:MM`, must differ from `start`) | `"08:00"` |
| `weekday_mask` | no | Raw device weekday bitmask; meaning unconfirmed, `127` = all days; omit to preserve/default | `127` |

**Example:**

- Create (or update) task 1 to run 22:00-08:00, enabled, on all days
    ```yaml
    service: dreame_vacuum.vacuum_set_dnd_task
    data:
        task_id: 1
        enabled: true
        start: "22:00"
        end: "08:00"
        weekday_mask: 127
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_delete_dnd_task`

Delete a single multi-window DnD task by id.

> - Only supported on devices reporting the `dnd_task` capability.
> - Raises an error if `task_id` does not match any existing task.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `task_id` | yes | Id of the task to delete | `1` |

**Example:**

- Delete task 1
    ```yaml
    service: dreame_vacuum.vacuum_delete_dnd_task
    data:
        task_id: 1
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_set_obstacle_ignore`

Mark a detected obstacle at a coordinate as ignored (or un-ignore it) so the robot does not avoid it during cleaning.

> - Requires AI obstacle detection and a cloud connection (map manager).
> - The vacuum must not be running.
> - An obstacle matching the coordinate must already exist on the current map; obstacles that were dynamically ignored by the device itself cannot be re-ignored through this service.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `x` | yes | X coordinate of the obstacle on the current map | `819` |
| `y` | yes | Y coordinate of the obstacle on the current map | `-263` |
| `obstacle_ignored` | yes | `true` to ignore the obstacle, `false` to stop ignoring it | `false` |

**Example:**

- Ignore the obstacle at [819, -263]
    ```yaml
    service: dreame_vacuum.vacuum_set_obstacle_ignore
    data:
        x: 819
        y: -263
        obstacle_ignored: true
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_set_router_position`

Set the WiFi router's position on the current map (used to render its icon and, on supported devices, for router-relative navigation).

> - Requires a device with WiFi map support.
> - The vacuum must not be running.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `x` | yes | X coordinate of the router on the current map | `819` |
| `y` | yes | Y coordinate of the router on the current map | `-263` |

**Example:**

- Place the router marker at [819, -263]
    ```yaml
    service: dreame_vacuum.vacuum_set_router_position
    data:
        x: 819
        y: -263
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_set_carpet_area`

Define which areas of the current saved map are carpets, and which detected carpets should be ignored.

> - Cannot be used to edit carpets on a temporary (unsaved) map.
> - Both fields default to an empty list, which clears the corresponding set.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `carpets` | no | List of `[x0, y0, x1, y1]` rectangles to mark as carpets | `[[819,-263,4424,2105],[-2001,-3050,-542,515]]` |
| `ignored_carpets` | no | List of `[x0, y0, x1, y1]` rectangles of detected carpets to ignore | `[[819,-263,4424,2105],[-2001,-3050,-542,515]]` |

**Example:**

- Mark one rectangle as a carpet
    ```yaml
    service: dreame_vacuum.vacuum_set_carpet_area
    data:
        carpets:
          - - 819
            - -263
            - 4424
            - 2105
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_set_virtual_threshold`

Define virtual thresholds (floor-transition lines) on the current saved map, used by devices that distinguish floor materials or auto-carpet cleaning to decide where to lift the mop or change suction.

> - Cannot be used to edit thresholds on a temporary (unsaved) map.
> - Requires a device that supports virtual/passable thresholds or floor material detection.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `virtual_thresholds` | no | List of `[x0, y0, x1, y1]` lines marking floor-material transitions | `[[819,-263,4424,2105],[-2001,-3050,-542,515]]` |

**Example:**

- Define one virtual threshold line
    ```yaml
    service: dreame_vacuum.vacuum_set_virtual_threshold
    data:
        virtual_thresholds:
          - - 819
            - -263
            - 4424
            - 2105
    target:
        entity_id: vacuum.vacuum
    ```

### `dreame_vacuum.vacuum_set_predefined_points`

Save a list of predefined coordinates on the current map. These points are reused by `vacuum_follow_path` when called without explicit `points`, and are shown in the app as saved points of interest.

> - Requires a device with cruising capability.
> - The vacuum must not be running.
> - Coordinates must be inside the current map.
> - At most 20 points are kept; extra points are truncated.

**Fields:**

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `points` | no | One `[x, y]` pair or a list of `[x, y]` pairs to save | `[819,-263] or [[819,-263],[900,-463]]` |

**Example:**

- Save two predefined points
    ```yaml
    service: dreame_vacuum.vacuum_set_predefined_points
    data:
        points:
          - - 819
            - -263
          - - 900
            - -463
    target:
        entity_id: vacuum.vacuum
    ```


## Other Services
Integration adds <a href="https://www.home-assistant.io/integrations/input_select/#services" target="_blank_">**input_select** services</a> that are missing from the **select** entity to generated select entities for ease of use.

### `dreame_vacuum.select_select_first`

Select first option from options list

### `dreame_vacuum.select_select_last`

Select last option from options list

### `dreame_vacuum.select_select_previous`

Select previous option from options list

### `dreame_vacuum.select_select_next`

Select next option from options list

**<a href="https://github.com/foXaCe/dreame-vacuum/blob/main/room_entities.md#rooms-card" target="_blank">For more info about how these services are used</a>**
