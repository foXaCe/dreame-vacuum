from __future__ import annotations

import base64
from collections.abc import Callable
import copy
from datetime import datetime
from functools import cmp_to_key
import json
import logging
from threading import Lock, RLock, Timer
import time
from typing import TYPE_CHECKING, Any, cast
import zlib

if TYPE_CHECKING:
    from .map_manager import DreameMapVacuumMapManager

from .const import (
    CARPET_CLEANING_ADAPTATION_WITHOUT_ROUTE,
    CARPET_CLEANING_CODE_TO_NAME,
    CARPET_CLEANING_CROSS,
    CARPET_CLEANING_IGNORE,
    CARPET_CLEANING_REMOVE_MOP,
    CARPET_CLEANING_VACUUM_AND_MOP,
    CLEANING_MODE_CODE_TO_NAME,
    CLEANING_MODE_MOPPING_AFTER_SWEEPING,
    CLEANING_ROUTE_TO_NAME,
    DEVICE_INFO,
    FLOOR_MATERIAL_CARPET,
    FLOOR_MATERIAL_LOW_PILE_CARPET,
    FLOOR_MATERIAL_MEDIUM_PILE_CARPET,
    MOP_CLEAN_FREQUENCY_BY_ROOM,
    MOP_CLEAN_FREQUENCY_EIGHT_SQUARE_METERS,
    MOP_CLEAN_FREQUENCY_FIFTEEN_SQUARE_METERS,
    MOP_CLEAN_FREQUENCY_FIVE_SQUARE_METERS,
    MOP_CLEAN_FREQUENCY_TWENTY_SQUARE_METERS,
    MOP_CLEAN_FREQUENCY_TWENTYFIVE_SQUARE_METERS,
    MOP_WASH_LEVEL_WATER_SAVING,
    VOICE_ASSISTANT_LANGUAGE_TO_NAME,
    WASHING_MODE_ULTRA_WASHING,
)
from .exceptions import (
    DeviceException,
    DeviceUpdateFailedException,
    RateLimitError,
)

# map module is imported lazily to speed up startup (numpy, PIL are heavy)
# Use _get_map_module() to access it
_map_module = None


def _get_map_module() -> Any:
    """Lazy import of map module to avoid loading numpy/PIL at startup."""
    global _map_module
    if _map_module is None:
        from . import map as _map_module
    return _map_module


from .device_actions import DreameVacuumDeviceActionsMixin
from .device_map_ops import DreameVacuumDeviceMapMixin
from .device_setters import DreameVacuumDeviceSettersMixin
from .protocol import DreameVacuumProtocol
from .vacuum_types import (
    DID,
    DIID,
    CleaningHistory,
    CleanupMethod,
    DirtyData,
    DreameVacuumAction,
    DreameVacuumActionMapping,
    DreameVacuumAIProperty,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumCarpetCleaning,
    DreameVacuumChargingStatus,
    DreameVacuumCleaningMode,
    DreameVacuumCleaningRoute,
    DreameVacuumDeviceCapability,
    DreameVacuumMopPadHumidity,
    DreameVacuumProperty,
    DreameVacuumPropertyMapping,
    DreameVacuumSelfWashBaseStatus,
    DreameVacuumState,
    DreameVacuumStateOld,
    DreameVacuumStatus,
    DreameVacuumStrAIProperty,
    DreameVacuumStreamStatus,
    DreameVacuumTaskStatus,
    DreameVacuumVoiceAssistantLanguage,
    ScheduleTask,
)

_LOGGER = logging.getLogger(__name__)


class DreameVacuumDevice(
    DreameVacuumDeviceSettersMixin,
    DreameVacuumDeviceActionsMixin,
    DreameVacuumDeviceMapMixin,
):
    """Support for Dreame Vacuum"""

    property_mapping: dict[DreameVacuumProperty, dict[str, int]] = DreameVacuumPropertyMapping
    action_mapping: dict[DreameVacuumAction, dict[str, int]] = DreameVacuumActionMapping

    def __init__(
        self,
        name: str,
        host: str,
        token: str,
        mac: str | None = None,
        username: str | None = None,
        password: str | None = None,
        country: str | None = None,
        prefer_cloud: bool = False,
        account_type: str = "mi",
        device_id: str | None = None,
        auth_key: str | None = None,
    ) -> None:
        # Used for easy filtering the device from cloud device list and generating unique ids
        self.info = None
        self.mac: str | None = None
        self.token: str | None = None  # Local api token
        self.host: str | None = None  # IP address or host name of the device
        # Dictionary for storing the current property values
        self.data: dict[int, Any] = {}
        self.auto_switch_data: dict[str, Any] | None = None
        self.ai_data: dict[str, Any] | None = None
        self.available: bool = False  # Last update is successful or not
        self.disconnected: bool = False

        self._update_lock = Lock()
        # Guards short in-memory reads/writes of _cleaning_history_update /
        # _cleaning_history_retry_after against concurrent MQTT push handlers;
        # never held across the blocking get_device_event() network call.
        self._cleaning_history_lock = Lock()
        # Reentrant lock guarding ONLY the disconnected flag + (re)scheduling of
        # _update_timer. Reentrant because disconnect() holds it while calling
        # schedule_update(). Never held during any blocking network/MQTT call.
        self._timer_lock = RLock()
        self._update_running: bool = False  # Update is running
        # Previous cleaning mode for restoring it after water tank is installed or removed
        self._previous_cleaning_mode: DreameVacuumCleaningMode | None = None
        self._previous_cleangenius: int | None = None
        # Device do not request properties that returned -1 as result. This property used for overriding that behavior at first connection
        self._ready: bool = False
        # Last settings properties requested time
        self._last_settings_request: float = 0
        self._last_map_list_request: float = 0  # Last map list property requested time
        self._last_map_request: float = 0  # Last map request trigger time
        self._last_change: float = 0  # Last property change time
        self._last_update_failed: float | None = 0  # Last update failed time
        self._cleaning_history_update: float = 0  # Cleaning history update time
        self._cleaning_history_retry_after: float = 0  # Next allowed cleaning history retry time
        self._update_fail_count: int = 0  # Update failed counter
        self._draining_complete_time: float | None = None
        self._map_select_time: float | None = None
        self._last_map_change_time: float | None = None
        # Map Manager object. Only available when cloud connection is present
        self._map_manager: DreameMapVacuumMapManager | None = None
        self._update_callback: Callable[..., Any] | None = None  # External update callback for device
        self._error_callback: Callable[..., None] | None = None  # External update failed callback
        # External update callbacks for specific device property
        self._property_update_callback: dict[int, list[Callable[..., Any]]] = {}
        self._update_timer: Timer | None = None  # Update schedule timer
        self._callback_timer: Timer | None = None  # Update listener debouncing timer
        # Used for requesting consumable properties after reset action otherwise they will only requested when cleaning completed
        self._consumable_change: bool = False
        self._remote_control: bool = False
        self._dirty_data: dict[int, DirtyData] = {}
        self._dirty_auto_switch_data: dict[str, DirtyData] = {}
        self._dirty_ai_data: dict[str, DirtyData] = {}
        self._discard_timeout = 5
        self._restore_timeout = 15

        self._name = name
        self.mac = mac
        self.token = token
        self.host = host
        self.auth_failed = False
        self.account_type = account_type
        self.status = DreameVacuumDeviceStatus(self)
        self.capability = DreameVacuumDeviceCapability(self)

        # Startup flags: two-phase loading for faster startup
        self._full_properties_loaded = False
        self._map_initialized = False
        self._deferred_cloud_loaded = False

        # Remove write only and response only properties from default list
        self._default_properties = list(
            set(DreameVacuumProperty)
            - {
                DreameVacuumProperty.SCHEDULE_ID,
                DreameVacuumProperty.REMOTE_CONTROL,
                DreameVacuumProperty.VOICE_CHANGE,
                DreameVacuumProperty.VOICE_CHANGE_STATUS,
                DreameVacuumProperty.MAP_RECOVERY,
                DreameVacuumProperty.CLEANING_START_TIME,
                DreameVacuumProperty.CLEAN_LOG_FILE_NAME,
                DreameVacuumProperty.CLEANING_PROPERTIES,
                DreameVacuumProperty.CLEAN_LOG_STATUS,
                DreameVacuumProperty.MAP_INDEX,
                DreameVacuumProperty.MAP_NAME,
                DreameVacuumProperty.CRUISE_TYPE,
                DreameVacuumProperty.MAP_DATA,
                DreameVacuumProperty.FRAME_INFO,
                DreameVacuumProperty.OBJECT_NAME,
                DreameVacuumProperty.MAP_EXTEND_DATA,
                DreameVacuumProperty.ROBOT_TIME,
                DreameVacuumProperty.RESULT_CODE,
                DreameVacuumProperty.OLD_MAP_DATA,
                DreameVacuumProperty.FACTORY_TEST_STATUS,
                DreameVacuumProperty.FACTORY_TEST_RESULT,
                DreameVacuumProperty.SELF_TEST_STATUS,
                DreameVacuumProperty.LSD_TEST_STATUS,
                DreameVacuumProperty.DEBUG_SWITCH,
                DreameVacuumProperty.SERIAL,
                DreameVacuumProperty.CALIBRATION_STATUS,
                DreameVacuumProperty.VERSION,
                DreameVacuumProperty.PERFORMANCE_SWITCH,
                DreameVacuumProperty.AI_TEST_STATUS,
                DreameVacuumProperty.PUBLIC_KEY,
                DreameVacuumProperty.AUTO_PAIR,
                DreameVacuumProperty.MCU_VERSION,
                DreameVacuumProperty.MOP_TEST_STATUS,
                DreameVacuumProperty.PLATFORM_NETWORK,
                DreameVacuumProperty.TAKE_PHOTO,
                DreameVacuumProperty.STEAM_HUMAN_FOLLOW,
                DreameVacuumProperty.STREAM_KEEP_ALIVE,
                DreameVacuumProperty.STREAM_UPLOAD,
                DreameVacuumProperty.STREAM_AUDIO,
                DreameVacuumProperty.STREAM_RECORD,
                DreameVacuumProperty.STREAM_CODE,
                DreameVacuumProperty.STREAM_SET_CODE,
                DreameVacuumProperty.STREAM_VERIFY_CODE,
                DreameVacuumProperty.STREAM_RESET_CODE,
                DreameVacuumProperty.STREAM_CRUISE_POINT,
                DreameVacuumProperty.STREAM_FAULT,
                DreameVacuumProperty.STREAM_TASK,
            }
        )
        self._discarded_properties = [
            DreameVacuumProperty.ERROR,
            DreameVacuumProperty.STATE,
            DreameVacuumProperty.STATUS,
            DreameVacuumProperty.TASK_STATUS,
            DreameVacuumProperty.AUTO_EMPTY_STATUS,
            DreameVacuumProperty.SELF_WASH_BASE_STATUS,
            DreameVacuumProperty.AUTO_SWITCH_SETTINGS,
            DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS,
            DreameVacuumProperty.AI_DETECTION,
            DreameVacuumProperty.SHORTCUTS,
            DreameVacuumProperty.MAP_BACKUP_STATUS,
            DreameVacuumProperty.MAP_RECOVERY_STATUS,
            DreameVacuumProperty.OFF_PEAK_CHARGING,
            DreameVacuumProperty.SCHEDULE,
        ]
        self._read_write_properties = [
            DreameVacuumProperty.WATER_VOLUME,
            DreameVacuumProperty.SUCTION_LEVEL,
            DreameVacuumProperty.RESUME_CLEANING,
            DreameVacuumProperty.CARPET_BOOST,
            DreameVacuumProperty.MOP_CLEANING_REMAINDER,
            DreameVacuumProperty.OBSTACLE_AVOIDANCE,
            DreameVacuumProperty.AI_DETECTION,
            DreameVacuumProperty.DRYING_TIME,
            DreameVacuumProperty.AUTO_ADD_DETERGENT,
            DreameVacuumProperty.CARPET_CLEANING,
            DreameVacuumProperty.CLEANING_MODE,
            DreameVacuumProperty.WATER_ELECTROLYSIS,
            DreameVacuumProperty.INTELLIGENT_RECOGNITION,
            DreameVacuumProperty.AUTO_WATER_REFILLING,
            DreameVacuumProperty.AUTO_MOUNT_MOP,
            DreameVacuumProperty.MOP_WASH_LEVEL,
            DreameVacuumProperty.CUSTOMIZED_CLEANING,
            DreameVacuumProperty.CHILD_LOCK,
            DreameVacuumProperty.CARPET_SENSITIVITY,
            DreameVacuumProperty.TIGHT_MOPPING,
            DreameVacuumProperty.CARPET_RECOGNITION,
            DreameVacuumProperty.SELF_CLEAN,
            DreameVacuumProperty.DND_TASK,
            DreameVacuumProperty.SCHEDULE,
            DreameVacuumProperty.MULTI_FLOOR_MAP,
            DreameVacuumProperty.VOLUME,
            DreameVacuumProperty.AUTO_DUST_COLLECTING,
            DreameVacuumProperty.AUTO_EMPTY_FREQUENCY,
            DreameVacuumProperty.VOICE_PACKET_ID,
            DreameVacuumProperty.TIMEZONE,
            DreameVacuumProperty.MAP_SAVING,
            DreameVacuumProperty.AUTO_SWITCH_SETTINGS,
            DreameVacuumProperty.SHORTCUTS,
            DreameVacuumProperty.VOICE_ASSISTANT,
            DreameVacuumProperty.CRUISE_SCHEDULE,
            DreameVacuumProperty.CAMERA_LIGHT_BRIGHTNESS,
            DreameVacuumProperty.STREAM_PROPERTY,
            DreameVacuumProperty.STREAM_SPACE,
            DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE,
            DreameVacuumProperty.OFF_PEAK_CHARGING,
            DreameVacuumProperty.WETNESS_LEVEL,
            DreameVacuumProperty.CLEAN_CARPETS_FIRST,
            DreameVacuumProperty.QUICK_WASH_MODE,
            DreameVacuumProperty.DND,
            DreameVacuumProperty.DND_START,
            DreameVacuumProperty.DND_END,
            DreameVacuumProperty.CLEANGENIUS_MODE,
            DreameVacuumProperty.SMART_MOP_WASHING,
            DreameVacuumProperty.WATER_TEMPERATURE,
            DreameVacuumProperty.DND_DISABLE_RESUME_CLEANING,
            DreameVacuumProperty.DND_DISABLE_AUTO_EMPTY,
            DreameVacuumProperty.DND_REDUCE_VOLUME,
            DreameVacuumProperty.SILENT_DRYING,
            DreameVacuumProperty.HAIR_COMPRESSION,
            DreameVacuumProperty.SIDE_BRUSH_CARPET_ROTATE,
            DreameVacuumProperty.AUTO_LDS_LIFTING,
            DreameVacuumProperty.MOP_WASHING_WITH_DETERGENT,
        ]

        self.listen(self._task_status_changed, DreameVacuumProperty.TASK_STATUS)
        self.listen(self._status_changed, DreameVacuumProperty.STATUS)
        self.listen(self._charging_status_changed, DreameVacuumProperty.CHARGING_STATUS)
        self.listen(self._cleaning_mode_changed, DreameVacuumProperty.CLEANING_MODE)
        self.listen(self._water_tank_changed, DreameVacuumProperty.WATER_TANK)
        self.listen(self._water_tank_changed, DreameVacuumProperty.MOP_PAD_INSTALLED)
        self.listen(self._water_tank_changed, DreameVacuumProperty.MOP_IN_STATION)
        self.listen(self._auto_mount_mop_changed, DreameVacuumProperty.AUTO_MOUNT_MOP)
        self.listen(self._ai_obstacle_detection_changed, DreameVacuumProperty.AI_DETECTION)
        self.listen(
            self._auto_switch_settings_changed,
            DreameVacuumProperty.AUTO_SWITCH_SETTINGS,
        )
        self.listen(self._dnd_task_changed, DreameVacuumProperty.DND_TASK)
        self.listen(self._schedule_changed, DreameVacuumProperty.SCHEDULE)
        self.listen(self._stream_status_changed, DreameVacuumProperty.STREAM_STATUS)
        self.listen(self._shortcuts_changed, DreameVacuumProperty.SHORTCUTS)
        self.listen(
            self._voice_assistant_language_changed,
            DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE,
        )
        self.listen(self._drainage_status_changed, DreameVacuumProperty.DRAINAGE_STATUS)
        self.listen(
            self._self_wash_base_status_changed,
            DreameVacuumProperty.SELF_WASH_BASE_STATUS,
        )
        self.listen(self._off_peak_charging_changed, DreameVacuumProperty.OFF_PEAK_CHARGING)
        self.listen(self._suction_level_changed, DreameVacuumProperty.SUCTION_LEVEL)
        self.listen(self._water_volume_changed, DreameVacuumProperty.WATER_VOLUME)
        self.listen(self._wetness_level_changed, DreameVacuumProperty.WETNESS_LEVEL)
        self.listen(self._error_changed, DreameVacuumProperty.ERROR)
        self.listen(
            self._map_recovery_status_changed,
            DreameVacuumProperty.MAP_RECOVERY_STATUS,
        )

        self._protocol = DreameVacuumProtocol(
            self.host,
            self.token,
            username,
            password,
            country,
            prefer_cloud,
            account_type,
            device_id,
            auth_key,
        )
        if self._protocol.cloud:
            map_mod = _get_map_module()
            self._map_manager = map_mod.DreameMapVacuumMapManager(self._protocol)

            self.listen(self._map_list_changed, DreameVacuumProperty.MAP_LIST)
            self.listen(self._recovery_map_list_changed, DreameVacuumProperty.RECOVERY_MAP_LIST)
            self.listen(self._battery_level_changed, DreameVacuumProperty.BATTERY_LEVEL)
            self.listen(self._map_property_changed, DreameVacuumProperty.CUSTOMIZED_CLEANING)
            self.listen(self._map_property_changed, DreameVacuumProperty.STATE)
            self.listen(self._map_property_changed, DreameVacuumProperty.AUTO_EMPTY_STATUS)
            self.listen(
                self._map_backup_status_changed,
                DreameVacuumProperty.MAP_BACKUP_STATUS,
            )
            self._map_manager.listen(self._map_changed, self._map_updated)
            self._map_manager.listen_error(self._update_failed)

    def _connected_callback(self) -> None:
        if not self._ready:
            return
        _LOGGER.debug("Requesting properties after connect")
        self.available = True
        self.schedule_update(2, True)
        self._property_changed()

    def _message_callback(self, message: Any) -> None:
        if not self._ready:
            return

        if isinstance(message, dict) and message.get("method") == "_otc.info":
            # _otc.info params carry the device token / localIp / bssid: never log them.
            _LOGGER.debug("Message Callback: _otc.info (params redacted)")
        else:
            _LOGGER.debug("Message Callback: %s", message)

        if "method" in message and "params" in message:
            self.available = True
            method = message["method"]
            params = message["params"]
            if method == "properties_changed":
                properties = []
                map_properties = []
                for param in params:
                    prop = DID(param["siid"], param["piid"])
                    if prop is not None:
                        if prop in self._default_properties:
                            param["did"] = str(prop.value)
                            param["code"] = 0
                            properties.append(param)
                            continue

                        if (
                            prop is DreameVacuumProperty.OBJECT_NAME
                            or prop is DreameVacuumProperty.MAP_DATA
                            or prop is DreameVacuumProperty.ROBOT_TIME
                            or prop is DreameVacuumProperty.OLD_MAP_DATA
                        ):
                            map_properties.append(param)

                if len(map_properties) and self._map_manager:
                    self._map_manager.handle_properties(map_properties)

                self._handle_properties(properties)
            elif method == "_otc.info":
                info = DreameVacuumDeviceInfo(params)
                if info != self.info:
                    self.info = info
                    self._last_change = time.time()
                    if self._ready:
                        self._property_changed()

    def _handle_properties(self, properties: list[Any]) -> bool:
        changed = False
        callbacks: list[tuple[Callable[..., Any], Any]] = []
        # Collect per-property noise during the initial burst so we can emit a
        # single summary line instead of ~100 DEBUG entries at setup time.
        collect_summary = not self._ready
        added_count = 0
        unavailable_count = 0
        for prop in properties:
            if not isinstance(prop, dict):
                continue
            did = int(prop["did"])
            if did not in DreameVacuumProperty._value2member_map_:
                mapped = DID(prop["siid"], prop["piid"])
                if mapped is None:
                    continue
                did = int(mapped.value)
            if prop["code"] == 0 and "value" in prop:
                value = prop["value"]
                if did in self._dirty_data:
                    if (
                        self._dirty_data[did].value != value
                        and time.time() - (self._dirty_data[did].update_time or 0) < self._discard_timeout
                    ):
                        _LOGGER.debug(
                            "Property %s Value Discarded: %s <- %s",
                            DreameVacuumProperty(did).name,
                            self._dirty_data[did].value,
                            value,
                        )
                        del self._dirty_data[did]
                        continue
                    del self._dirty_data[did]

                current_value = self.data.get(did)
                if current_value != value:
                    # Do not call external listener when map and json properties changed
                    if not (
                        did == DreameVacuumProperty.MAP_LIST.value
                        or did == DreameVacuumProperty.RECOVERY_MAP_LIST.value
                        or did == DreameVacuumProperty.MAP_DATA.value
                        or did == DreameVacuumProperty.OBJECT_NAME.value
                        or did == DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value
                        or did == DreameVacuumProperty.AI_DETECTION.value
                        # or did == DreameVacuumProperty.SELF_TEST_STATUS.value
                    ):
                        changed = True
                    custom_property = (
                        did == DreameVacuumProperty.AUTO_SWITCH_SETTINGS.value
                        or did == DreameVacuumProperty.AI_DETECTION.value
                        or did == DreameVacuumProperty.MAP_LIST.value
                        or did == DreameVacuumProperty.SERIAL_NUMBER.value
                    )
                    if not custom_property:
                        if current_value is not None:
                            _LOGGER.debug(
                                "Property %s Changed: %s -> %s",
                                DreameVacuumProperty(did).name,
                                current_value,
                                value,
                            )
                        elif collect_summary:
                            added_count += 1
                        else:
                            _LOGGER.debug(
                                "Property %s Added: %s",
                                DreameVacuumProperty(did).name,
                                value,
                            )
                    self.data[did] = value
                    if did in self._property_update_callback:
                        for callback in self._property_update_callback[did]:
                            if not self._ready and custom_property:
                                callback(current_value)
                            else:
                                callbacks.append((callback, current_value))
            else:
                if collect_summary:
                    unavailable_count += 1
                else:
                    _LOGGER.debug("Property %s Not Available", DreameVacuumProperty(did).name)

        if collect_summary and (added_count or unavailable_count):
            _LOGGER.debug(
                "Initial properties loaded: %d added, %d unavailable",
                added_count,
                unavailable_count,
            )

        if not self._ready:
            self.capability.load(json.loads(zlib.decompress(base64.b64decode(DEVICE_INFO), zlib.MAX_WBITS | 32)))

        for cb, cb_value in callbacks:
            cb(cb_value)

        if changed:
            self._last_change = time.time()
            if self._ready:
                self._property_changed()

        if not self._ready:
            if self._protocol.dreame_cloud:
                self._discard_timeout = 5

            if self.capability.self_wash_base:
                if self.capability.mop_clean_frequency:
                    self.status.self_clean_area_min = 5
                    self.status.self_clean_area_max = 10
                    self.status.self_clean_area_default = 8
                elif self.capability.small_self_clean_area:
                    self.status.self_clean_area_min = 5
                    self.status.self_clean_area_max = 15
                    self.status.self_clean_area_default = 15
                else:
                    self.status.self_clean_area_max = 35 if self.capability.cleaning_route else 30

            self.status.previous_self_clean_area = (
                self.status.self_clean_value if self.status.self_clean_value else self.status.self_clean_area_default
            )
            self.status.previous_self_clean_time = (
                self.status.self_clean_value
                if self.status.self_clean_value and self.status.self_clean_by_time
                else self.status.self_clean_time_default
            )

            if self.capability.mop_clean_frequency:
                if MOP_WASH_LEVEL_WATER_SAVING in self.status.mop_wash_level_list:
                    self.status.mop_wash_level_list.pop(MOP_WASH_LEVEL_WATER_SAVING)

                if self.capability.mop_pad_swing:
                    if MOP_CLEAN_FREQUENCY_EIGHT_SQUARE_METERS in self.status.mop_clean_frequency_list:
                        self.status.mop_clean_frequency_list.pop(MOP_CLEAN_FREQUENCY_EIGHT_SQUARE_METERS)
                    if MOP_CLEAN_FREQUENCY_FIVE_SQUARE_METERS in self.status.mop_clean_frequency_list:
                        self.status.mop_clean_frequency_list.pop(MOP_CLEAN_FREQUENCY_FIVE_SQUARE_METERS)
                else:
                    if MOP_CLEAN_FREQUENCY_BY_ROOM in self.status.mop_clean_frequency_list:
                        self.status.mop_clean_frequency_list.pop(MOP_CLEAN_FREQUENCY_BY_ROOM)
                    if MOP_CLEAN_FREQUENCY_FIFTEEN_SQUARE_METERS in self.status.mop_clean_frequency_list:
                        self.status.mop_clean_frequency_list.pop(MOP_CLEAN_FREQUENCY_FIFTEEN_SQUARE_METERS)
                    if MOP_CLEAN_FREQUENCY_TWENTY_SQUARE_METERS in self.status.mop_clean_frequency_list:
                        self.status.mop_clean_frequency_list.pop(MOP_CLEAN_FREQUENCY_TWENTY_SQUARE_METERS)
                    if MOP_CLEAN_FREQUENCY_TWENTYFIVE_SQUARE_METERS in self.status.mop_clean_frequency_list:
                        self.status.mop_clean_frequency_list.pop(MOP_CLEAN_FREQUENCY_TWENTYFIVE_SQUARE_METERS)

            if (
                self.capability.smart_mop_washing
                and not self.capability.ultra_clean_mode
                and WASHING_MODE_ULTRA_WASHING in self.status.washing_mode_list
            ):
                self.status.washing_mode_list.pop(WASHING_MODE_ULTRA_WASHING)

            if (
                not self.capability.mopping_after_sweeping
                and CLEANING_MODE_MOPPING_AFTER_SWEEPING in self.status.cleaning_mode_list
            ):
                self.status.cleaning_mode_list.pop(CLEANING_MODE_MOPPING_AFTER_SWEEPING)

            if (
                not self.capability.mop_pad_lifting_plus
                or self.capability.auto_carpet_cleaning
                or self.capability.carpet_crossing
            ) and CARPET_CLEANING_ADAPTATION_WITHOUT_ROUTE in self.status.carpet_cleaning_list:
                self.status.carpet_cleaning_list.pop(CARPET_CLEANING_ADAPTATION_WITHOUT_ROUTE)

            if (
                not self.capability.auto_carpet_cleaning or self.capability.carpet_crossing
            ) and CARPET_CLEANING_VACUUM_AND_MOP in self.status.carpet_cleaning_list:
                self.status.carpet_cleaning_list.pop(CARPET_CLEANING_VACUUM_AND_MOP)

            if (
                not self.capability.mop_pad_unmounting
            ) and CARPET_CLEANING_REMOVE_MOP in self.status.carpet_cleaning_list:
                self.status.carpet_cleaning_list.pop(CARPET_CLEANING_REMOVE_MOP)

            if (
                not self.capability.mop_pad_lifting_plus and not self.capability.auto_carpet_cleaning
            ) and CARPET_CLEANING_IGNORE in self.status.carpet_cleaning_list:
                self.status.carpet_cleaning_list.pop(CARPET_CLEANING_IGNORE)

            if not self.capability.carpet_crossing and CARPET_CLEANING_CROSS in self.status.carpet_cleaning_list:
                self.status.carpet_cleaning_list.pop(CARPET_CLEANING_CROSS)

            if (
                not (self.capability.carpet_material and self.capability.carpet_type)
                and FLOOR_MATERIAL_CARPET in self.status.floor_material_list
            ):
                self.status.floor_material_list.pop(FLOOR_MATERIAL_MEDIUM_PILE_CARPET)
                self.status.floor_material_list.pop(FLOOR_MATERIAL_LOW_PILE_CARPET)
                self.status.floor_material_list.pop(FLOOR_MATERIAL_CARPET)

            self.status.segment_cleaning_mode_list = self.status.cleaning_mode_list.copy()
            if CLEANING_MODE_MOPPING_AFTER_SWEEPING in self.status.segment_cleaning_mode_list:
                self.status.segment_cleaning_mode_list.pop(CLEANING_MODE_MOPPING_AFTER_SWEEPING)

            if self.capability.cleaning_route:
                if (
                    self.status.cleaning_mode == DreameVacuumCleaningMode.SWEEPING
                    or self.status.cleaning_mode == DreameVacuumCleaningMode.SWEEPING_AND_MOPPING
                ):
                    new_list = CLEANING_ROUTE_TO_NAME.copy()
                    new_list.pop(DreameVacuumCleaningRoute.DEEP)
                    new_list.pop(DreameVacuumCleaningRoute.INTENSIVE)
                    self.status.cleaning_route_list = {v: k for k, v in new_list.items()}
                    new_list = CLEANING_ROUTE_TO_NAME.copy()
                    if self.capability.segment_slow_clean_route:
                        new_list.pop(DreameVacuumCleaningRoute.QUICK)
                    self.status.segment_cleaning_route_list = {v: k for k, v in new_list.items()}

            for p in dir(self.capability):
                if not p.startswith("__") and not callable(getattr(self.capability, p)):
                    val = getattr(self.capability, p)
                    if isinstance(val, bool) and val:
                        _LOGGER.debug("Capability %s", p.upper())

        return changed

    def _request_properties(
        self, properties: list[DreameVacuumProperty] | None = None, force_all: bool = False
    ) -> bool:
        """Request properties from the device."""
        if not properties:
            properties = self._default_properties

        property_list = []
        for prop in properties:
            if prop in self.property_mapping:
                mapping = self.property_mapping[prop]
                # Do not include properties that are not exists on the device
                if "aiid" not in mapping and (force_all or not self._ready or prop.value in self.data):
                    property_list.append({"did": str(prop.value), **mapping})

        props = property_list.copy()
        results = []
        batch_size = 50  # Increased from 25 for faster startup (fewer network calls)
        while props:
            result = self._protocol.get_properties(props[:batch_size])
            if result is None:
                # No progress possible (connection lost / protocol returned None).
                # Stop instead of busy-looping a worker thread on an unchanging
                # batch; the next update cycle will retry.
                break
            results.extend(result)
            props[:] = props[batch_size:]

        return self._handle_properties(results)

    def _update_status(self, task_status: DreameVacuumTaskStatus, status: DreameVacuumStatus) -> None:
        """Update status properties on memory for map renderer to update the image before action is sent to the device."""
        if task_status is not DreameVacuumTaskStatus.COMPLETED:
            new_state = DreameVacuumState.SWEEPING
            if self.status.cleaning_mode is DreameVacuumCleaningMode.MOPPING:
                new_state = DreameVacuumState.MOPPING
            elif self.status.cleaning_mode is DreameVacuumCleaningMode.SWEEPING_AND_MOPPING:
                new_state = DreameVacuumState.SWEEPING_AND_MOPPING
            self._update_property(DreameVacuumProperty.STATE, new_state.value)

        self._update_property(DreameVacuumProperty.STATUS, status.value)
        self._update_property(DreameVacuumProperty.TASK_STATUS, task_status.value)

    def _update_property(self, prop: DreameVacuumProperty, value: Any, delay: bool = True) -> Any:
        """Update device property on memory and notify listeners."""
        if prop in self.property_mapping:
            if (
                not self.capability.new_state
                and prop == DreameVacuumProperty.STATE
                and int(value) > 18
                and value in DreameVacuumState._value2member_map_
            ):
                old_state = DreameVacuumStateOld[DreameVacuumState(value).name]
                if old_state:
                    value = int(old_state)

            current_value = self.get_property(prop)
            if current_value != value:
                did = prop.value
                self.data[did] = value
                if did in self._property_update_callback:
                    for callback in self._property_update_callback[did]:
                        callback(current_value)

                if (
                    prop != DreameVacuumProperty.CUSTOMIZED_CLEANING
                    and prop != DreameVacuumProperty.STATE
                    and prop != DreameVacuumProperty.AUTO_EMPTY_STATUS
                ):
                    self._property_changed(delay)
                return current_value if current_value is not None else value
        return None

    def _cleaning_mode_changed(self, previous_cleaning_mode: Any = None) -> None:
        value = self.get_property(DreameVacuumProperty.CLEANING_MODE)
        new_cleaning_mode = None
        if self.capability.self_wash_base:
            values = DreameVacuumDevice.split_group_value(value, self.capability.mop_pad_lifting)
            if values and len(values) == 3:
                if (
                    self.status.self_clean_value != values[1]
                    and values[1] > 0
                    and (self.status.wetness_level is None or self.status.wetness_level < 27)
                ):
                    if self.status.self_clean_by_time:
                        self.status.previous_self_clean_time = values[1]
                    else:
                        self.status.previous_self_clean_area = values[1]
                self.status.self_clean_value = values[1]
                if not self.capability.wetness or values[2] != 0:
                    if values[2] <= 0:
                        if self.capability.custom_mopping_route:
                            if not self.status.custom_mopping_mode:
                                values[2] = (
                                    self.get_auto_switch_property(DreameVacuumAutoSwitchProperty.MOPPING_MODE) or 0
                                )
                        elif self.status.water_volume:
                            values[2] = self.status.water_volume.value

                    if (
                        values[2] > 0
                        and values[2] is not None
                        and values[2] in DreameVacuumMopPadHumidity._value2member_map_
                    ):
                        self.status.mop_pad_humidity = values[2]
                if values[0] == 3:
                    new_cleaning_mode = DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING
                elif not self.capability.mop_pad_lifting:
                    if not self.status.water_tank_or_mop_installed:
                        new_cleaning_mode = DreameVacuumCleaningMode.SWEEPING
                    elif values[0] == 1:
                        new_cleaning_mode = DreameVacuumCleaningMode.MOPPING
                    else:
                        new_cleaning_mode = DreameVacuumCleaningMode.SWEEPING_AND_MOPPING
                else:
                    if values[0] == 2:
                        new_cleaning_mode = DreameVacuumCleaningMode.SWEEPING
                    elif values[0] == 0:
                        new_cleaning_mode = DreameVacuumCleaningMode.SWEEPING_AND_MOPPING
                    elif values[0] in DreameVacuumCleaningMode._value2member_map_:
                        new_cleaning_mode = DreameVacuumCleaningMode(values[0])
        elif self.capability.mop_pad_lifting:
            if value == 3:
                new_cleaning_mode = DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING
            elif value == 2:
                new_cleaning_mode = DreameVacuumCleaningMode.SWEEPING
            elif value == 0:
                new_cleaning_mode = DreameVacuumCleaningMode.SWEEPING_AND_MOPPING

        if new_cleaning_mode is None:
            if value in DreameVacuumCleaningMode._value2member_map_:
                new_cleaning_mode = DreameVacuumCleaningMode(value)
            else:
                new_cleaning_mode = DreameVacuumCleaningMode.UNKNOWN

        if previous_cleaning_mode is not None and self.status.go_to_zone:
            self.status.go_to_zone.cleaning_mode = None
            self.status.go_to_zone.water_level = None

        if self.status.cleaning_mode != new_cleaning_mode:
            self.status.cleaning_mode = new_cleaning_mode

            if self._ready and self.capability.cleaning_route:
                new_list = CLEANING_ROUTE_TO_NAME.copy()
                if (
                    self.status.cleaning_mode == DreameVacuumCleaningMode.SWEEPING
                    or self.status.cleaning_mode == DreameVacuumCleaningMode.SWEEPING_AND_MOPPING
                ):
                    new_list.pop(DreameVacuumCleaningRoute.DEEP)
                    new_list.pop(DreameVacuumCleaningRoute.INTENSIVE)
                self.status.cleaning_route_list = {v: k for k, v in new_list.items()}

                if (
                    self.status.cleaning_route
                    and self.status.cleaning_route not in self.status.cleaning_route_list.values()
                ):
                    self.set_auto_switch_property(
                        DreameVacuumAutoSwitchProperty.CLEANING_ROUTE,
                        DreameVacuumCleaningRoute.STANDARD.value,
                    )

    def _water_tank_changed(self, previous_water_tank: Any = None) -> None:
        """Update cleaning mode on device when water tank status is changed."""
        # App does not allow you to update cleaning mode when water tank or mop pad is not installed.
        if self.get_property(DreameVacuumProperty.CLEANING_MODE) is not None:
            new_list = CLEANING_MODE_CODE_TO_NAME.copy()
            if not self.capability.mopping_after_sweeping or (
                self.status.started and self.status.cleaning_mode is not DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING
            ):
                new_list.pop(DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING)

            if not self.capability.embedded_tank and (not self.status.auto_mount_mop or not self.status.mop_in_station):
                try:
                    if not self.status.water_tank_or_mop_installed:
                        new_list.pop(DreameVacuumCleaningMode.MOPPING)
                        new_list.pop(DreameVacuumCleaningMode.SWEEPING_AND_MOPPING)
                        if DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING in new_list:
                            new_list.pop(DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING)
                        if self.status.cleaning_mode is not DreameVacuumCleaningMode.SWEEPING:
                            # Store current cleaning mode for future use when water tank is reinstalled
                            self._previous_cleaning_mode = self.status.cleaning_mode
                            if self._ready and not self.status.scheduled_clean and not self.status.shortcut_task:
                                try:
                                    self._update_cleaning_mode(DreameVacuumCleaningMode.SWEEPING.value)
                                except (AttributeError, ValueError, KeyError):
                                    _LOGGER.debug("cleaning_mode switch failed", exc_info=True)
                    elif not self.capability.mop_pad_lifting:
                        new_list.pop(DreameVacuumCleaningMode.SWEEPING)
                        if DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING in new_list:
                            new_list.pop(DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING)
                        if self.status.sweeping:
                            if self._ready and not self.status.scheduled_clean and not self.status.shortcut_task:
                                if (
                                    self._previous_cleaning_mode is not None
                                    and self._previous_cleaning_mode is not DreameVacuumCleaningMode.SWEEPING
                                ):
                                    self._update_cleaning_mode(self._previous_cleaning_mode.value)
                                else:
                                    self._update_cleaning_mode(DreameVacuumCleaningMode.SWEEPING_AND_MOPPING.value)
                            # Store current cleaning mode for future use when water tank is removed
                            self._previous_cleaning_mode = self.status.cleaning_mode
                except (AttributeError, KeyError, ValueError):
                    _LOGGER.debug("water_tank state transition failed", exc_info=True)

            self.status.cleaning_mode_list = {v: k for k, v in new_list.items()}

    def _auto_mount_mop_changed(self, previous_auto_mount_mop: Any = None) -> None:
        if previous_auto_mount_mop is not None:
            carpet_cleaning_list = CARPET_CLEANING_CODE_TO_NAME.copy()
            if not self.status.auto_mount_mop:
                carpet_cleaning_list.pop(DreameVacuumCarpetCleaning.REMOVE_MOP)
            self.status.carpet_cleaning_list = {v: k for k, v in carpet_cleaning_list.items()}

    def _task_status_changed(self, previous_task_status: Any = None) -> None:
        """Task status is a very important property and must be listened to trigger necessary actions when a task started or ended"""
        if previous_task_status is not None:
            if previous_task_status in DreameVacuumTaskStatus._value2member_map_:
                previous_task_status = DreameVacuumTaskStatus(previous_task_status)

            task_status = self.get_property(DreameVacuumProperty.TASK_STATUS)
            if task_status in DreameVacuumTaskStatus._value2member_map_:
                task_status = DreameVacuumTaskStatus(task_status)

            if self._map_manager is not None:
                # Update map data for renderer to update the map image according to the new task status
                if previous_task_status is DreameVacuumTaskStatus.COMPLETED:
                    if (
                        task_status is DreameVacuumTaskStatus.AUTO_CLEANING
                        or task_status is DreameVacuumTaskStatus.ZONE_CLEANING
                        or task_status is DreameVacuumTaskStatus.SEGMENT_CLEANING
                        or task_status is DreameVacuumTaskStatus.SPOT_CLEANING
                        or task_status is DreameVacuumTaskStatus.CRUISING_PATH
                        or task_status is DreameVacuumTaskStatus.CRUISING_POINT
                    ):
                        # Clear path on current map on cleaning start as implemented on the app
                        self._map_manager.editor.clear_path()
                    elif task_status is DreameVacuumTaskStatus.FAST_MAPPING:
                        # Clear current map on mapping start as implemented on the app
                        self._map_manager.editor.reset_map()
                    else:
                        self._map_manager.editor.refresh_map()
                else:
                    self._map_manager.editor.refresh_map()

            if task_status is DreameVacuumTaskStatus.COMPLETED:
                if (
                    previous_task_status is DreameVacuumTaskStatus.CRUISING_PATH
                    or previous_task_status is DreameVacuumTaskStatus.CRUISING_POINT
                    or self.status.go_to_zone
                ):
                    if self._map_manager is not None:
                        # Get the new map list from cloud
                        self._map_manager.editor.set_cruise_points([])
                        self._map_manager.request_next_map_list()
                    with self._cleaning_history_lock:
                        self._cleaning_history_update = time.time()
                elif previous_task_status is DreameVacuumTaskStatus.FAST_MAPPING:
                    # as implemented on the app
                    self._update_property(DreameVacuumProperty.CLEANING_TIME, 0)
                    if self._map_manager is not None:
                        # Mapping is completed, get the new map list from cloud
                        self._map_manager.request_next_map_list()
                elif (
                    self.status.cleanup_started
                    and not self.status.cleanup_completed
                    and (self.status.status is DreameVacuumStatus.BACK_HOME or not self.status.running)
                ):
                    self.status.cleanup_started = False
                    self.status.cleanup_completed = True
                    with self._cleaning_history_lock:
                        self._cleaning_history_update = time.time()

                    if self._previous_cleangenius is not None:
                        self.set_auto_switch_property(
                            DreameVacuumAutoSwitchProperty.CLEANGENIUS, self._previous_cleangenius
                        )
                        self._previous_cleangenius = None
            else:
                self.status.cleanup_started = not (
                    self.status.fast_mapping
                    or self.status.cruising
                    or (
                        task_status is DreameVacuumTaskStatus.DOCKING_PAUSED
                        and previous_task_status is DreameVacuumTaskStatus.COMPLETED
                    )
                )
                self.status.cleanup_completed = False
                if self.status.cleanup_started:
                    if previous_task_status is DreameVacuumTaskStatus.COMPLETED:
                        # as implemented on the app
                        self._update_property(DreameVacuumProperty.CLEANING_TIME, 0)
                        self._update_property(DreameVacuumProperty.CLEANED_AREA, 0)

                    if (
                        task_status is not DreameVacuumTaskStatus.ZONE_CLEANING
                        and self._previous_cleangenius is not None
                    ):
                        self._previous_cleangenius = None

            if self.status.go_to_zone is not None and not (
                task_status is DreameVacuumTaskStatus.ZONE_CLEANING
                or task_status is DreameVacuumTaskStatus.ZONE_CLEANING_PAUSED
                or task_status is DreameVacuumTaskStatus.ZONE_MOPPING_PAUSED
                or task_status is DreameVacuumTaskStatus.ZONE_DOCKING_PAUSED
                or task_status is DreameVacuumTaskStatus.CRUISING_POINT
                or task_status is DreameVacuumTaskStatus.CRUISING_POINT_PAUSED
            ):
                self._restore_go_to_zone()

            if self._map_manager:
                self._map_manager.editor.refresh_map()

            if (
                task_status is DreameVacuumTaskStatus.COMPLETED
                or previous_task_status is DreameVacuumTaskStatus.COMPLETED
            ):
                # Get properties that only changes when task status is changed
                properties = [
                    DreameVacuumProperty.MAIN_BRUSH_TIME_LEFT,
                    DreameVacuumProperty.MAIN_BRUSH_LEFT,
                    DreameVacuumProperty.SIDE_BRUSH_TIME_LEFT,
                    DreameVacuumProperty.SIDE_BRUSH_LEFT,
                    DreameVacuumProperty.FILTER_LEFT,
                    DreameVacuumProperty.FILTER_TIME_LEFT,
                    DreameVacuumProperty.TANK_FILTER_LEFT,
                    DreameVacuumProperty.TANK_FILTER_TIME_LEFT,
                    DreameVacuumProperty.MOP_PAD_LEFT,
                    DreameVacuumProperty.MOP_PAD_TIME_LEFT,
                    DreameVacuumProperty.SILVER_ION_TIME_LEFT,
                    DreameVacuumProperty.SILVER_ION_LEFT,
                    DreameVacuumProperty.DETERGENT_TIME_LEFT,
                    DreameVacuumProperty.DETERGENT_LEFT,
                    DreameVacuumProperty.SQUEEGEE_TIME_LEFT,
                    DreameVacuumProperty.SQUEEGEE_LEFT,
                    DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_TIME_LEFT,
                    DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_LEFT,
                    DreameVacuumProperty.DIRTY_WATER_TANK_TIME_LEFT,
                    DreameVacuumProperty.DIRTY_WATER_TANK_LEFT,
                    DreameVacuumProperty.DEODORIZER_TIME_LEFT,
                    DreameVacuumProperty.DEODORIZER_LEFT,
                    DreameVacuumProperty.WHEEL_DIRTY_TIME_LEFT,
                    DreameVacuumProperty.WHEEL_DIRTY_LEFT,
                    DreameVacuumProperty.SCALE_INHIBITOR_TIME_LEFT,
                    DreameVacuumProperty.SCALE_INHIBITOR_LEFT,
                    DreameVacuumProperty.TOTAL_CLEANING_TIME,
                    DreameVacuumProperty.CLEANING_COUNT,
                    DreameVacuumProperty.TOTAL_CLEANED_AREA,
                    DreameVacuumProperty.TOTAL_RUNTIME,
                    DreameVacuumProperty.TOTAL_CRUISE_TIME,
                    DreameVacuumProperty.FIRST_CLEANING_DATE,
                    DreameVacuumProperty.SCHEDULE,
                    DreameVacuumProperty.SCHEDULE_CANCEL_REASON,
                    DreameVacuumProperty.CRUISE_SCHEDULE,
                ]

                if not self.capability.disable_sensor_cleaning:
                    properties.extend(
                        [
                            DreameVacuumProperty.SENSOR_DIRTY_LEFT,
                            DreameVacuumProperty.SENSOR_DIRTY_TIME_LEFT,
                        ]
                    )

                if self._map_manager is not None:
                    properties.extend(
                        [
                            DreameVacuumProperty.MAP_LIST,
                            DreameVacuumProperty.RECOVERY_MAP_LIST,
                        ]
                    )
                    self._last_map_list_request = time.time()

                try:
                    self._request_properties(properties)
                except DeviceException:
                    _LOGGER.debug("Property refresh after map update failed", exc_info=True)

                if self._protocol.prefer_cloud and self._protocol.dreame_cloud:
                    self.schedule_update(1, True)

        if self.capability.mopping_after_sweeping:
            if self.status.started:
                if (
                    self.status.cleaning_mode is not DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING
                    and CLEANING_MODE_MOPPING_AFTER_SWEEPING in self.status.cleaning_mode_list
                ):
                    self.status.cleaning_mode_list.pop(CLEANING_MODE_MOPPING_AFTER_SWEEPING)
                    self._property_changed(False)
            elif CLEANING_MODE_MOPPING_AFTER_SWEEPING not in self.status.cleaning_mode_list and (
                self.status.water_tank_or_mop_installed
            ):
                self.status.cleaning_mode_list[CLEANING_MODE_MOPPING_AFTER_SWEEPING] = (
                    DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING
                )
                self._property_changed(False)

    def _status_changed(self, previous_status: Any = None) -> None:
        if previous_status is not None:
            if previous_status in DreameVacuumStatus._value2member_map_:
                previous_status = DreameVacuumStatus(previous_status)

            status = self.get_property(DreameVacuumProperty.STATUS)
            if (
                self._remote_control
                and status != DreameVacuumStatus.REMOTE_CONTROL.value
                and previous_status != DreameVacuumStatus.REMOTE_CONTROL.value
            ):
                self._remote_control = False

            if (
                not self.capability.cruising
                and status == DreameVacuumStatus.BACK_HOME
                and previous_status == DreameVacuumStatus.ZONE_CLEANING
                and self.status.started
            ):
                self.status.cleanup_started = False
                self.status.cleanup_completed = False
                if self.status.go_to_zone:
                    self.status.go_to_zone.stop = True
                self._restore_go_to_zone(True)
            elif (
                not self.status.started
                and self.status.cleanup_started
                and not self.status.cleanup_completed
                and (self.status.status is DreameVacuumStatus.BACK_HOME or not self.status.running)
            ):
                self.status.cleanup_started = False
                self.status.cleanup_completed = True
                with self._cleaning_history_lock:
                    self._cleaning_history_update = time.time()

                if self._previous_cleangenius is not None:
                    self.set_auto_switch_property(
                        DreameVacuumAutoSwitchProperty.CLEANGENIUS, self._previous_cleangenius
                    )
                    self._previous_cleangenius = None

                did = DreameVacuumProperty.TASK_STATUS.value
                if did in self._property_update_callback:
                    for callback in self._property_update_callback[did]:
                        callback(self.status.task_status.value)
                self._property_changed(False)
            elif status == DreameVacuumStatus.CHARGING.value and previous_status == DreameVacuumStatus.BACK_HOME.value:
                with self._cleaning_history_lock:
                    self._cleaning_history_update = time.time()

            if previous_status == DreameVacuumStatus.OTA.value:
                self._ready = False
                self.connect_device()

            if self._map_manager:
                self._map_manager.editor.refresh_map()

    def _charging_status_changed(self, previous_charging_status: Any = None) -> None:
        self._remote_control = False
        if previous_charging_status is not None:
            if self._map_manager:
                self._map_manager.editor.refresh_map()

            if self._ready and self.capability.mop_pad_lifting:
                self._water_tank_changed()

            if (
                self._protocol.dreame_cloud
                and self.status.charging_status != DreameVacuumChargingStatus.CHARGING_COMPLETED
            ):
                self.schedule_update(2, True)

    def _ai_obstacle_detection_changed(self, previous_ai_obstacle_detection: Any = None) -> None:
        """AI Detection property returns multiple values as json or int this function parses and sets the sub properties to memory"""
        ai_value = self.get_property(DreameVacuumProperty.AI_DETECTION)
        changed = False
        if isinstance(ai_value, str):
            settings = json.loads(ai_value)
            if self.ai_data is None:
                self.ai_data = {}
            ai_data = self.ai_data

            for prop in DreameVacuumStrAIProperty:
                if prop.value in settings:
                    value = settings[prop.value]
                    if prop.name in self._dirty_ai_data:
                        if (
                            self._dirty_ai_data[prop.name].value != value
                            and time.time() - (self._dirty_ai_data[prop.name].update_time or 0) < self._discard_timeout
                        ):
                            _LOGGER.debug(
                                "AI Property %s Value Discarded: %s <- %s",
                                prop.name,
                                self._dirty_ai_data[prop.name].value,
                                value,
                            )
                            del self._dirty_ai_data[prop.name]
                            continue
                        del self._dirty_ai_data[prop.name]

                    current_value = ai_data.get(prop.name)
                    if current_value != value:
                        if current_value is not None:
                            _LOGGER.debug(
                                "AI Property %s Changed: %s -> %s",
                                prop.name,
                                current_value,
                                value,
                            )
                            if (
                                prop == DreameVacuumStrAIProperty.AI_PET_DETECTION
                                or prop == DreameVacuumStrAIProperty.AI_FLUID_DETECTION
                            ):
                                self._map_property_changed(current_value)
                        else:
                            _LOGGER.debug("AI Property %s Added: %s", prop.name, value)
                        changed = True
                        ai_data[prop.name] = value
        elif isinstance(ai_value, int):
            if self.ai_data is None:
                self.ai_data = {}
            ai_data = self.ai_data

            for ai_prop in DreameVacuumAIProperty:
                bit = int(ai_prop.value)
                value = (ai_value & bit) == bit
                if ai_prop.name in self._dirty_ai_data:
                    if (
                        self._dirty_ai_data[ai_prop.name].value != value
                        and time.time() - (self._dirty_ai_data[ai_prop.name].update_time or 0) < self._discard_timeout
                    ):
                        _LOGGER.debug(
                            "AI Property %s Value Discarded: %s <- %s",
                            ai_prop.name,
                            self._dirty_ai_data[ai_prop.name].value,
                            value,
                        )
                        del self._dirty_ai_data[ai_prop.name]
                        continue
                    del self._dirty_ai_data[ai_prop.name]

                current_value = ai_data.get(ai_prop.name)
                if current_value != value:
                    if current_value is not None:
                        _LOGGER.debug(
                            "AI Property %s Changed: %s -> %s",
                            ai_prop.name,
                            current_value,
                            value,
                        )
                        if (
                            ai_prop == DreameVacuumAIProperty.AI_PET_DETECTION
                            or ai_prop == DreameVacuumAIProperty.AI_FLUID_DETECTION
                        ):
                            self._map_property_changed(current_value)
                    else:
                        _LOGGER.debug("AI Property %s Added: %s", ai_prop.name, value)
                    changed = True
                    ai_data[ai_prop.name] = value

        if changed:
            self._last_change = time.time()
            if self._ready:
                self._property_changed()

        self.status.ai_policy_accepted = bool(
            self.status.ai_policy_accepted or self.status.ai_obstacle_detection or self.status.ai_obstacle_picture
        )

    def _auto_switch_settings_changed(self, previous_auto_switch_settings: Any = None) -> None:
        value = self.get_property(DreameVacuumProperty.AUTO_SWITCH_SETTINGS)
        if isinstance(value, str) and len(value) > 2:
            mopping_setting_changed = False
            cleangenius_changed = False
            try:
                settings = json.loads(value)
                settings_dict = {}

                if isinstance(settings, list):
                    for setting in settings:
                        settings_dict[setting["k"]] = setting["v"]
                elif "k" in settings:
                    settings_dict[settings["k"]] = settings["v"]

                if self.auto_switch_data is None:
                    self.auto_switch_data = {}
                auto_switch_data = self.auto_switch_data

                changed = False
                for prop in DreameVacuumAutoSwitchProperty:
                    if prop.value in settings_dict:
                        value = settings_dict[prop.value]

                        if prop.name in self._dirty_auto_switch_data:
                            if (
                                self._dirty_auto_switch_data[prop.name].value != value
                                and time.time() - (self._dirty_auto_switch_data[prop.name].update_time or 0)
                                < self._discard_timeout
                            ):
                                _LOGGER.debug(
                                    "Property %s Value Discarded: %s <- %s",
                                    prop.name,
                                    self._dirty_auto_switch_data[prop.name].value,
                                    value,
                                )
                                del self._dirty_auto_switch_data[prop.name]
                                continue
                            del self._dirty_auto_switch_data[prop.name]

                        current_value = auto_switch_data.get(prop.name)
                        if current_value != value:
                            if (
                                prop == DreameVacuumAutoSwitchProperty.MOPPING_MODE
                                or prop == DreameVacuumAutoSwitchProperty.CUSTOM_MOPPING_MODE
                            ):
                                mopping_setting_changed = True
                            if prop == DreameVacuumAutoSwitchProperty.CLEANGENIUS:
                                cleangenius_changed = True
                                if self._previous_cleangenius is not None:
                                    self._previous_cleangenius = value

                            if current_value is not None:
                                _LOGGER.debug(
                                    "Property %s Changed: %s -> %s",
                                    prop.name,
                                    current_value,
                                    value,
                                )
                            else:
                                _LOGGER.debug("Property %s Added: %s", prop.name, value)
                            changed = True
                            auto_switch_data[prop.name] = value

                if changed:
                    self._last_change = time.time()
                    if self._ready and previous_auto_switch_settings is not None:
                        self._property_changed()
            except Exception as ex:
                _LOGGER.error("Failed to parse auto switch settings: %s", ex)

            if (
                mopping_setting_changed
                and self.capability.self_wash_base
                and self.capability.custom_mopping_route
                and not self.capability.wetness_level
                and not self.capability.mop_clean_frequency
            ):
                if self.status.mop_pad_humidity == 3:
                    if not self.capability.small_self_clean_area:
                        self.status.self_clean_area_max = 15
                        self.status.self_clean_area_default = 15

                    if self.capability.self_clean_frequency:
                        if self.status.mop_pad_humidity == 3:
                            self.status.self_clean_time_max = 20
                            self.status.self_clean_time_default = 20
                else:
                    if not self.capability.small_self_clean_area:
                        self.status.self_clean_area_max = 35 if self.capability.cleaning_route else 30
                        self.status.self_clean_area_default = 20

                    if self.capability.self_clean_frequency:
                        self.status.self_clean_time_max = 50
                        self.status.self_clean_time_default = 25

            if cleangenius_changed and self._map_manager and self._ready and previous_auto_switch_settings is not None:
                self._map_manager.editor.refresh_map()

    def _dnd_task_changed(self, previous_dnd_task: Any = None) -> None:
        dnd_tasks = self.get_property(DreameVacuumProperty.DND_TASK)
        if dnd_tasks and dnd_tasks != "":
            self.status.dnd_tasks = json.loads(dnd_tasks)

    def _schedule_changed(self, previous_schedule: Any = None) -> None:
        schedule = self.get_property(DreameVacuumProperty.SCHEDULE)
        schedule_list = []
        if schedule and schedule != "":
            tasks = schedule.split(";")
            for task in tasks:
                props = task.split("-")
                if len(props) >= 9:
                    schedule_list.append(
                        ScheduleTask(
                            id=int(props[0]),
                            enabled=bool(props[1] == "1" or props[1] == "2"),
                            invalid=bool(props[1] == "3"),
                            time=props[2],
                            repeats=props[3],
                            once=bool(props[4] == "0"),
                            map_id=props[5],
                            suction_level=int(props[6]),
                            water_volume=int(props[7]),
                            options=props[8].split(",") if props[8] != "0" else None,
                        )
                    )
        if schedule_list and len(schedule_list) > 1:
            schedule_list.sort(
                key=cmp_to_key(
                    lambda a, b: (
                        b.id - a.id
                        if a.time == b.time
                        else (int(a.time.replace(":", "")) if a.time else 0)
                        - (int(b.time.replace(":", "")) if b.time else 0)
                    )
                )
            )
        self.status.schedule = schedule_list

    def _stream_status_changed(self, previous_stream_status: Any = None) -> None:
        stream_status = self.get_property(DreameVacuumProperty.STREAM_STATUS)
        if stream_status and stream_status != "" and stream_status != "null":
            stream_status = json.loads(stream_status)
            if stream_status and stream_status.get("result") == 0:
                self.status.stream_session = stream_status.get("session")
                operation_type = stream_status.get("operType")
                operation = stream_status.get("operation")
                if operation_type:
                    if operation_type == "end" or operation == "end":
                        self.status.stream_status = DreameVacuumStreamStatus.IDLE
                    elif operation_type == "start" or operation == "start":
                        if operation:
                            if operation == "monitor" or operation_type == "monitor":
                                self.status.stream_status = DreameVacuumStreamStatus.VIDEO
                            elif operation == "intercom" or operation_type == "intercom":
                                self.status.stream_status = DreameVacuumStreamStatus.AUDIO
                            elif operation == "recordVideo" or operation_type == "recordVideo":
                                self.status.stream_status = DreameVacuumStreamStatus.RECORDING

    def _shortcuts_changed(self, previous_shortcuts: Any = None) -> None:
        self.reload_shortcuts()

    def _voice_assistant_language_changed(self, previous_voice_assistant_language: Any = None) -> None:
        value = self.get_property(DreameVacuumProperty.VOICE_ASSISTANT_LANGUAGE)
        language_list: dict[Any, Any] = self.status.voice_assistant_language_list
        if value and len(value):
            language_list = VOICE_ASSISTANT_LANGUAGE_TO_NAME.copy()
            language_list.pop(DreameVacuumVoiceAssistantLanguage.DEFAULT)
            language_list = {v: k for k, v in language_list.items()}
        elif DreameVacuumVoiceAssistantLanguage.DEFAULT.value not in language_list:
            language_list = {v: k for k, v in VOICE_ASSISTANT_LANGUAGE_TO_NAME.items()}
        self.status.voice_assistant_language_list = language_list

    def _drainage_status_changed(self, previous_drainage_status: Any = None) -> None:
        if self.status.draining_complete:
            self._draining_complete_time = time.time()
        else:
            self._draining_complete_time = None

    def _self_wash_base_status_changed(self, previous_self_wash_base_status: Any = None) -> None:
        if previous_self_wash_base_status is not None:
            if (
                bool(
                    (
                        self.status.started
                        and previous_self_wash_base_status == DreameVacuumSelfWashBaseStatus.WASHING.value
                    )
                    or previous_self_wash_base_status == DreameVacuumSelfWashBaseStatus.CLEAN_ADD_WATER.value
                )
                != self.status.washing
            ):
                self._consumable_change = True

            if self._map_manager:
                self._map_manager.editor.refresh_map()

    def _off_peak_charging_changed(self, previous_off_peak_charging: Any = None) -> None:
        off_peak_charging = self.get_property(DreameVacuumProperty.OFF_PEAK_CHARGING)
        if off_peak_charging and off_peak_charging != "":
            self.status.off_peak_charging_config = json.loads(off_peak_charging)

    def _suction_level_changed(self, previous_suction_level: Any = None) -> None:
        if previous_suction_level is not None and self.status.go_to_zone:
            self.status.go_to_zone.suction_level = None

    def _water_volume_changed(self, previous_water_volume: Any = None) -> None:
        if self.capability.wetness and not self.capability.wetness_level:
            self.status.mop_pad_humidity = self.status.water_volume.value
        if previous_water_volume is not None and self.status.go_to_zone:
            self.status.go_to_zone.water_level = None

    def _wetness_level_changed(self, previous_wetness_level: Any = None) -> None:
        wetness_level = self.status.wetness_level
        if wetness_level:
            water_level = 2
            if wetness_level > 32:
                if wetness_level > 200:
                    water_level = 3
                elif wetness_level < 200:
                    water_level = 1
            else:
                if wetness_level > (14 if self.capability.mop_clean_frequency else 26):
                    water_level = 3
                elif wetness_level < 6:
                    water_level = 1

            self.status.mop_pad_humidity = water_level

            if (
                self.capability.self_wash_base
                and self.capability.wetness_level
                and not self.capability.mop_clean_frequency
            ):
                if self.status.wetness_level > 26:
                    self.status.self_clean_time_max = 20
                    self.status.self_clean_time_default = 20

                    if not self.capability.small_self_clean_area:
                        self.status.self_clean_area_max = 20
                else:
                    self.status.self_clean_time_max = 50
                    self.status.self_clean_time_default = 25

                    if not self.capability.small_self_clean_area:
                        self.status.self_clean_area_max = 35

    def _error_changed(self, previous_error: Any = None) -> None:
        if previous_error is not None and self.status.go_to_zone and self.status.has_error:
            self._restore_go_to_zone(True)

        if self._map_manager and previous_error is not None:
            self._map_manager.editor.refresh_map()

    def _battery_level_changed(self, previous_battery_level: Any = None) -> None:
        if self._map_manager and previous_battery_level is not None and self.status.battery_level == 100:
            self._map_manager.editor.refresh_map()

    def _request_cleaning_history(self) -> None:
        """Get and parse the cleaning history from cloud event data and set it to memory"""
        now = time.time()
        if (
            self.cloud_connected
            and self._cleaning_history_update != 0
            and now >= self._cleaning_history_retry_after
            and (
                self._cleaning_history_update == -1
                or self.status._cleaning_history is None
                or (
                    now - self._cleaning_history_update >= 5
                    and self.status.task_status is DreameVacuumTaskStatus.COMPLETED
                )
            )
        ):
            with self._cleaning_history_lock:
                pending_cleaning_history_update = self._cleaning_history_update
                self._cleaning_history_update = 0
                self._cleaning_history_retry_after = 0

            _LOGGER.debug("Get Cleaning History")
            request_failed = False
            try:
                # Limit the results
                start = None
                max = 25
                total = self.get_property(DreameVacuumProperty.CLEANING_COUNT)
                if total is None:
                    total = 5
                if total > 0:
                    start = self.get_property(DreameVacuumProperty.FIRST_CLEANING_DATE)

                if start is None:
                    start = int(time.time())
                limit = 40
                if total < max:
                    limit = total + max

                changed = False
                # Cleaning history is generated from events of status property that has been sent to cloud by the device when it changed
                result = self._protocol.cloud.get_device_event(
                    DIID(DreameVacuumProperty.STATUS, self.property_mapping),
                    limit,
                    start,
                )
                if result is None:
                    request_failed = True
                if result:
                    cleaning_history: list[CleaningHistory] = []
                    history_size = 0
                    for data in result:
                        history = CleaningHistory(
                            json.loads(data["history"] if "history" in data else data["value"]),
                            self.property_mapping,
                        )
                        if history_size > 0 and cleaning_history[-1].date == history.date:
                            continue

                        if history.cleanup_method == CleanupMethod.CUSTOMIZED_CLEANING and self.capability.cleangenius:
                            history.cleanup_method = CleanupMethod.DEFAULT_MODE

                        cleaning_history.append(history)
                        history_size = history_size + 1
                        if history_size >= max or history_size >= total:
                            break

                    if self.status._cleaning_history != cleaning_history:
                        _LOGGER.debug("Cleaning History Changed")
                        self.status._cleaning_history = cleaning_history
                        self.status._cleaning_history_attrs = None
                        first_date = cleaning_history[0].date if cleaning_history else None
                        if first_date is not None:
                            self.status._last_cleaning_time = first_date.replace(
                                tzinfo=datetime.now().astimezone().tzinfo
                            )
                        changed = True

                if self.capability.cruising:
                    # Cruising history is generated from events of water volume property that has been sent to cloud by the device when it changed
                    result = self._protocol.cloud.get_device_event(
                        DIID(DreameVacuumProperty.WATER_VOLUME, self.property_mapping),
                        limit,
                        start,
                    )
                    if result is None:
                        request_failed = True
                    if result:
                        cruising_history: list[CleaningHistory] = []
                        history_size = 0
                        for data in result:
                            history = CleaningHistory(
                                json.loads(data["history"] if "history" in data else data["value"]),
                                self.property_mapping,
                            )
                            if history_size > 0 and cruising_history[-1].date == history.date:
                                continue
                            cruising_history.append(history)
                            history_size = history_size + 1
                            if history_size >= max or history_size >= total:
                                break

                        if self.status._cruising_history != cruising_history:
                            _LOGGER.debug("Cruising History Changed")
                            self.status._cruising_history = cruising_history
                            self.status._cruising_history_attrs = None
                            cruising_first_date = cruising_history[0].date if cruising_history else None
                            if cruising_first_date is not None:
                                self.status._last_cruising_time = cruising_first_date.replace(
                                    tzinfo=datetime.now().astimezone().tzinfo
                                )
                            changed = True

                if changed:
                    if self.capability.auto_recleaning:
                        self.history_map(1)

                    if self._ready:
                        for k, v in copy.deepcopy(self.status._history_map_data).items():
                            found = False
                            if self.status._cleaning_history:
                                for item in self.status._cleaning_history:
                                    if k in item.file_name:
                                        found = True
                                        break

                            if found:
                                continue

                            if self.status._cruising_history:
                                for item in self.status._cruising_history:
                                    if k in item.file_name:
                                        found = True
                                        break

                            if found:
                                continue

                            del self.status._history_map_data[k]

                        if self._map_manager:
                            self._map_manager.editor.refresh_map()
                        self._property_changed()

            except Exception as ex:
                request_failed = True
                _LOGGER.warning("Get Cleaning History failed!: %s", ex)
            finally:
                if request_failed:
                    with self._cleaning_history_lock:
                        # Only restore the stale 'pending' value if no concurrent
                        # MQTT push re-armed a fresh re-fetch in the meantime (it
                        # would have set the field to a non-zero time.time()).
                        # Otherwise we would clobber that fresh signal.
                        if self._cleaning_history_update == 0:
                            self._cleaning_history_update = pending_cleaning_history_update
                            self._cleaning_history_retry_after = time.time() + 300

    def _property_changed(self, delay: bool = True) -> None:
        """Call external listener when a property changed"""
        if self._update_callback:
            if self._callback_timer is not None:
                self._callback_timer.cancel()

            if delay:
                self._callback_timer = Timer(0.1, self._update_callback)
                self._callback_timer.start()
            else:
                self._update_callback()

    def _update_failed(self, ex: Exception) -> None:
        """Call external listener when update failed"""
        if self._error_callback:
            self._error_callback(ex)

    def _action_update_task(self) -> None:
        self._update_task(True)

    def _update_task(self, force_request_properties: bool = False) -> None:
        """Timer task for updating properties periodically"""
        self._update_timer = None
        try:
            self.update(force_request_properties)
            if self._ready:
                self.available = True
            self._update_fail_count = 0
        except Exception as ex:
            self._update_fail_count = self._update_fail_count + 1
            if self.available:
                self._last_update_failed = time.time()
                if self._update_fail_count <= 3:
                    _LOGGER.debug(
                        "Update failed, retrying %s: %s",
                        self._update_fail_count,
                        str(ex),
                    )
                elif self._ready:
                    _LOGGER.warning("Update Failed: %s", str(ex))
                    self.available = False
                    self._update_failed(ex)

        # Atomically re-check the disconnect flag and reschedule under the timer
        # lock so a concurrent disconnect() cannot be overtaken by an in-flight
        # timer arming an orphan Timer after teardown.
        with self._timer_lock:
            if not self.disconnected:
                self.schedule_update(self._update_interval)

    @staticmethod
    def split_group_value(value: int, mop_pad_lifting: bool = False) -> list[int]:
        if value is not None:
            value_list = []
            value_list.append((value & 0x03) if mop_pad_lifting else (value & 1))
            byte1 = value >> 8
            byte1 = byte1 & -769
            value_list.append(byte1)
            value_list.append(value >> 16)
            return value_list

    @staticmethod
    def combine_group_value(values: list[int]) -> int:
        if values and len(values) == 3:
            return ((((0 ^ values[2]) << 8) ^ values[1]) << 8) ^ values[0]
        return 0

    def connect_device(self) -> None:
        """Connect to the device api."""
        _LOGGER.debug("Connecting to device")
        info = self._protocol.connect(self._message_callback, self._connected_callback)
        if info:
            self.info = DreameVacuumDeviceInfo(info)
            if self.mac is None:
                self.mac = self.info.mac_address
            _LOGGER.debug(
                "Connected to device: %s %s",
                self.info.model,
                self.info.firmware_version,
            )

            self._last_settings_request = time.time()
            self._last_map_list_request = self._last_settings_request
            self._dirty_data = {}
            self._dirty_auto_switch_data = {}
            self._dirty_ai_data = {}

            # Load ALL properties in a single pass (eliminates separate capability batch overhead)
            t_props = time.time()
            self._request_properties(force_all=True)
            self._full_properties_loaded = True
            _LOGGER.debug("connect_device: all properties loaded in %.2fs", time.time() - t_props)
            self._last_update_failed = None

            # Set up map manager (capabilities are now available from loaded properties)
            if self.device_connected and self._protocol.cloud is not None and (not self._ready or not self.available):
                if self._map_manager:
                    self._map_manager.set_capability(self.capability)
                    self._map_manager.set_update_interval(self._map_update_interval)
                    self._map_manager.schedule_update(2)

            if not self.available:
                self.available = True

            if not self._ready:
                self._ready = True
            else:
                self._property_changed(False)

    def connect_cloud(self) -> None:
        """Connect to the cloud api."""
        if self._protocol.cloud and not self._protocol.cloud.logged_in:
            self._protocol.cloud.login()
            self.auth_failed = False
            if self._protocol.cloud.logged_in is False:
                if self._protocol.cloud.auth_failed:
                    self.auth_failed = True
                    self._property_changed(False)
                if self._map_manager:
                    self._map_manager.schedule_update(-1)
            elif self._protocol.cloud.logged_in:
                if self._protocol.connected and self._map_manager:
                    self._map_manager.schedule_update(5)

                self.token, self.host = self._protocol.cloud.get_info(self.mac)
                if not self._protocol.dreame_cloud:
                    self._protocol.set_credentials(self.host, self.token, self.mac, self.account_type)

    def disconnect(self) -> None:
        """Disconnect from device and cancel timers"""
        _LOGGER.debug("Disconnect")
        # Set the flag and tear the timers down atomically wrt _update_task's
        # reschedule path. RLock lets schedule_update() re-acquire it here.
        # Any blocking network/MQTT call stays OUTSIDE the lock.
        with self._timer_lock:
            self.disconnected = True
            self.schedule_update(-1)
            if self._callback_timer is not None:
                self._callback_timer.cancel()
                self._callback_timer = None
        self._protocol.disconnect()
        if self._map_manager:
            self._map_manager.disconnect()
        self._property_changed(False)

    def listen(
        self, callback: Callable[..., Any] | None, property: DreameVacuumProperty | None = None
    ) -> Callable[[], None] | None:
        """Register a callback and return an unsubscribe callable.

        Historical behavior: ``listen(None)`` wipes every registered callback.
        That is preserved for compatibility, but new callers should capture
        the returned ``unsub`` callable to release exactly the listener they
        registered — following the HA dispatcher convention.
        """
        if callback is None:
            # Legacy "wipe everything" path, kept until all callers migrate.
            self._update_callback = None
            self._property_update_callback = {}
            return None

        if property is None:
            self._update_callback = callback

            def _unsub_global() -> None:
                if self._update_callback is callback:
                    self._update_callback = None

            return _unsub_global

        piid = property.value
        self._property_update_callback.setdefault(piid, []).append(callback)

        def _unsub_property() -> None:
            callbacks = self._property_update_callback.get(piid)
            if not callbacks:
                return
            try:
                callbacks.remove(callback)
            except ValueError:
                return
            if not callbacks:
                self._property_update_callback.pop(piid, None)

        return _unsub_property

    def listen_error(self, callback: Callable[..., None]) -> Callable[[], None]:
        """Register an error callback and return an unsubscribe callable."""
        self._error_callback = callback

        def _unsub() -> None:
            if self._error_callback is callback:
                self._error_callback = None

        return _unsub

    def schedule_update(self, wait: float | None = None, force_request_properties: bool = False) -> None:
        """Schedule a device update for future"""
        if wait is None:
            wait = self._update_interval

        with self._timer_lock:
            if self._update_timer is not None:
                self._update_timer.cancel()
                del self._update_timer
                self._update_timer = None

            # Never arm a new timer once teardown started, even if a caller
            # passes a non-negative wait.
            if wait >= 0 and not self.disconnected:
                self._update_timer = Timer(
                    wait, self._action_update_task if force_request_properties else self._update_task
                )
                self._update_timer.start()

    def update(self, force_request_properties: bool = False) -> None:
        """Get properties from the device."""
        with self._update_lock:
            if self._update_running:
                return
            self._update_running = True

        try:
            _LOGGER.debug("Device update: %s", self._update_interval)
            self._perform_update(force_request_properties)
        finally:
            self._update_running = False

    def _perform_update(self, force_request_properties: bool = False) -> None:
        """Run one device update after the concurrency guard has been acquired."""
        if not self.cloud_connected:
            self.connect_cloud()

        if not self.device_connected:
            self.connect_device()

        if not self.device_connected:
            raise DeviceUpdateFailedException("Device cannot be reached") from None

        # First update: initialize map (properties already loaded in connect_device)
        # Cleaning history and AI config are deferred to second update cycle
        if not self._map_initialized:
            self._map_initialized = True

            # Fallback: if connect_device didn't load all properties, load them now
            if not self._full_properties_loaded:
                self._full_properties_loaded = True
                t0 = time.time()
                self._request_properties(force_all=True)
                _LOGGER.debug("First update: properties loaded in %.2fs", time.time() - t0)

            # Initialize map manager (needed for camera entities)
            if self._map_manager:
                self._map_manager.set_device_running(
                    self.status.running,
                    self.status.docked and not self.status.started,
                )
                if self.status.current_map is None:
                    t1 = time.time()
                    try:
                        self._map_manager.update()
                        self._last_map_request = time.time()
                    except Exception as ex:
                        _LOGGER.error("Initial map update failed! %s", str(ex))
                    self._map_manager.schedule_update()
                    _LOGGER.debug("First update: map loaded in %.2fs", time.time() - t1)
                else:
                    self.update_map()

            # Defer cleaning history and AI config to next update cycle
            if self.cloud_connected:
                with self._cleaning_history_lock:
                    self._cleaning_history_update = -1
            return

        # Read-only properties
        properties = [
            DreameVacuumProperty.STATE,
            DreameVacuumProperty.ERROR,
            DreameVacuumProperty.BATTERY_LEVEL,
            DreameVacuumProperty.CHARGING_STATUS,
            DreameVacuumProperty.STATUS,
            DreameVacuumProperty.WATER_TANK,
            DreameVacuumProperty.TASK_STATUS,
            DreameVacuumProperty.WARN_STATUS,
            DreameVacuumProperty.RELOCATION_STATUS,
            DreameVacuumProperty.SELF_WASH_BASE_STATUS,
            DreameVacuumProperty.DUST_COLLECTION,
            DreameVacuumProperty.AUTO_EMPTY_STATUS,
            DreameVacuumProperty.CLEANING_PAUSED,
            DreameVacuumProperty.CLEANING_CANCEL,
            DreameVacuumProperty.SCHEDULED_CLEAN,
            DreameVacuumProperty.MOP_IN_STATION,
            DreameVacuumProperty.MOP_PAD_INSTALLED,
            DreameVacuumProperty.LOW_WATER_WARNING,
            DreameVacuumProperty.DRAINAGE_STATUS,
            DreameVacuumProperty.TASK_TYPE,
            DreameVacuumProperty.WATER_CHECK,
            DreameVacuumProperty.MAP_RECOVERY_STATUS,
            DreameVacuumProperty.CLEAN_WATER_TANK_STATUS,
            DreameVacuumProperty.DIRTY_WATER_TANK_STATUS,
            DreameVacuumProperty.DUST_BAG_STATUS,
            DreameVacuumProperty.DETERGENT_STATUS,
            DreameVacuumProperty.STATION_DRAINAGE_STATUS,
            DreameVacuumProperty.HOT_WATER_STATUS,
        ]

        if self.capability.backup_map:
            properties.append(DreameVacuumProperty.MAP_BACKUP_STATUS)

        now = time.time()
        if self.status.active:
            # Only changed when robot is active
            properties.extend([DreameVacuumProperty.CLEANED_AREA, DreameVacuumProperty.CLEANING_TIME])

        if self._consumable_change:
            # Consumable properties
            properties.extend(
                [
                    DreameVacuumProperty.MAIN_BRUSH_TIME_LEFT,
                    DreameVacuumProperty.MAIN_BRUSH_LEFT,
                    DreameVacuumProperty.SIDE_BRUSH_TIME_LEFT,
                    DreameVacuumProperty.SIDE_BRUSH_LEFT,
                    DreameVacuumProperty.FILTER_LEFT,
                    DreameVacuumProperty.FILTER_TIME_LEFT,
                    DreameVacuumProperty.MOP_PAD_LEFT,
                    DreameVacuumProperty.MOP_PAD_TIME_LEFT,
                    DreameVacuumProperty.DETERGENT_LEFT,
                    DreameVacuumProperty.DETERGENT_TIME_LEFT,
                    DreameVacuumProperty.SQUEEGEE_LEFT,
                    DreameVacuumProperty.SQUEEGEE_TIME_LEFT,
                    DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_LEFT,
                    DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_TIME_LEFT,
                    DreameVacuumProperty.DIRTY_WATER_TANK_LEFT,
                    DreameVacuumProperty.DIRTY_WATER_TANK_TIME_LEFT,
                    DreameVacuumProperty.SILVER_ION_LEFT,
                    DreameVacuumProperty.SILVER_ION_TIME_LEFT,
                    DreameVacuumProperty.TANK_FILTER_LEFT,
                    DreameVacuumProperty.TANK_FILTER_TIME_LEFT,
                    DreameVacuumProperty.DEODORIZER_LEFT,
                    DreameVacuumProperty.DEODORIZER_TIME_LEFT,
                    DreameVacuumProperty.WHEEL_DIRTY_LEFT,
                    DreameVacuumProperty.WHEEL_DIRTY_TIME_LEFT,
                    DreameVacuumProperty.SCALE_INHIBITOR_LEFT,
                    DreameVacuumProperty.SCALE_INHIBITOR_TIME_LEFT,
                ]
            )

            if not self.capability.disable_sensor_cleaning:
                properties.extend(
                    [
                        DreameVacuumProperty.SENSOR_DIRTY_LEFT,
                        DreameVacuumProperty.SENSOR_DIRTY_TIME_LEFT,
                    ]
                )

        if now - self._last_settings_request > 9.5:
            self._last_settings_request = now

            if not self._consumable_change and self.status.washing:
                properties.extend(
                    [
                        DreameVacuumProperty.DETERGENT_LEFT,
                        DreameVacuumProperty.DETERGENT_TIME_LEFT,
                        DreameVacuumProperty.SQUEEGEE_LEFT,
                        DreameVacuumProperty.SQUEEGEE_TIME_LEFT,
                        DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_LEFT,
                        DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_TIME_LEFT,
                        DreameVacuumProperty.DIRTY_WATER_TANK_LEFT,
                        DreameVacuumProperty.DIRTY_WATER_TANK_TIME_LEFT,
                        DreameVacuumProperty.SCALE_INHIBITOR_LEFT,
                        DreameVacuumProperty.SCALE_INHIBITOR_TIME_LEFT,
                        DreameVacuumProperty.DEODORIZER_LEFT,
                        DreameVacuumProperty.DEODORIZER_TIME_LEFT,
                    ]
                )

            properties.extend(self._read_write_properties)

            if not self.capability.dnd_task:
                properties.extend(
                    [
                        DreameVacuumProperty.DND,
                        DreameVacuumProperty.DND_START,
                        DreameVacuumProperty.DND_END,
                    ]
                )

        if self._map_manager and not self.status.running and now - self._last_map_list_request > 60:
            properties.extend([DreameVacuumProperty.MAP_LIST, DreameVacuumProperty.RECOVERY_MAP_LIST])
            self._last_map_list_request = time.time()

        try:
            if self._protocol.dreame_cloud and (not self.device_connected or not self.cloud_connected):
                force_request_properties = True

            if not self._protocol.dreame_cloud or force_request_properties:
                self._request_properties(properties)
            elif self.status.map_backup_status:
                self._request_properties([DreameVacuumProperty.MAP_BACKUP_STATUS])
            elif self.status.map_recovery_status:
                self._request_properties([DreameVacuumProperty.MAP_RECOVERY_STATUS])
        except RateLimitError:
            # Propagate the rate-limit unchanged so retry_after survives; the
            # coordinator uses it to back off the poll interval.
            raise
        except Exception as ex:
            raise DeviceUpdateFailedException(ex) from None

        if self._dirty_data:
            for k, v in copy.deepcopy(self._dirty_data).items():
                if time.time() - (v.update_time or 0) >= self._restore_timeout:
                    if v.previous_value is not None:
                        value = self.data.get(k)
                        if value is None or v.value == value:
                            _LOGGER.debug(
                                "Property %s Value Restored: %s <- %s",
                                DreameVacuumProperty(k).name,
                                v.previous_value,
                                value,
                            )
                            self.data[k] = v.previous_value
                            if k in self._property_update_callback:
                                for callback in self._property_update_callback[k]:
                                    callback(v.previous_value)

                            self._property_changed(False)
                            self.schedule_update(1, True)
                    del self._dirty_data[k]

        if self._dirty_auto_switch_data:
            for auto_k, v in copy.deepcopy(self._dirty_auto_switch_data).items():
                if time.time() - (v.update_time or 0) >= self._restore_timeout:
                    del self._dirty_auto_switch_data[auto_k]

        if self._dirty_ai_data:
            for ai_k, v in copy.deepcopy(self._dirty_ai_data).items():
                if time.time() - (v.update_time or 0) >= self._restore_timeout:
                    del self._dirty_ai_data[ai_k]

        if self._consumable_change:
            self._consumable_change = False

        if self._map_manager:
            if (
                not self.status.started
                and not self.status.running
                and self._last_map_change_time is not None
                and now - self._last_map_change_time > 120
            ):
                self._last_map_change_time = None
                self._map_manager.request_next_map_list()
                self._map_manager.request_next_recovery_map_list()
            self._map_manager.set_update_interval(self._map_update_interval)
            self._map_manager.set_device_running(self.status.running, self.status.docked and not self.status.started)

        # Reset drainage status after 10 minutes
        if self._draining_complete_time is not None and now - self._draining_complete_time > 600:
            self._draining_complete_time = None
            if self.status.draining_complete:
                self.set_property(DreameVacuumProperty.DRAINAGE_STATUS, 0)

        if self.cloud_connected:
            self._request_cleaning_history()
            # Load deferred cloud data on second update cycle (AI config)
            if not self._deferred_cloud_loaded:
                self._deferred_cloud_loaded = True
                if self.capability.ai_detection and not self.status.ai_policy_accepted:
                    try:
                        prop = "prop.s_ai_config"
                        response = self._protocol.cloud.get_batch_device_datas([prop])
                        if response and prop in response and response[prop]:
                            value = json.loads(response[prop])
                            self.status.ai_policy_accepted = (
                                value.get("privacyAuthed") if "privacyAuthed" in value else value.get("aiPrivacyAuthed")
                            )
                    except (DeviceException, ValueError, KeyError, TypeError):
                        _LOGGER.debug("ai_config lookup failed", exc_info=True)

    @property
    def _update_interval(self) -> float:
        """Dynamic update interval of the device for the internal timer.

        MQTT push handles realtime state changes; this timer is the fallback
        poll. Kept tight during cleaning / recent changes for responsiveness,
        relaxed when idle so we don't double-poll alongside the coordinator.
        """
        now = time.time()
        if self.status.map_backup_status or self.status.map_recovery_status:
            return 2
        if self._last_update_failed:
            return 5 if now - self._last_update_failed <= 60 else 10 if now - self._last_update_failed <= 300 else 30
        if now - self._last_change <= 60:
            return 3 if self.status.active or not self._protocol.prefer_cloud else 5
        if self.status.active or self.status.started:
            return 3 if self.status.running or not self._protocol.prefer_cloud else 5
        if self._map_manager:
            return min(self._map_update_interval, 30 if not self._protocol.prefer_cloud else 60)
        return 30 if not self._protocol.prefer_cloud else 60

    @property
    def _map_update_interval(self) -> float:
        """Dynamic map update interval for the map manager."""
        if self._map_manager:
            if self._protocol.dreame_cloud:
                return 10 if self.status.active else 30
            now = time.time()
            if now - self._last_map_request <= 120 or now - self._last_change <= 60:
                return 2.5 if self.status.active or self.status.started else 5
            return 3 if self.status.running else 10 if self.status.active else 30
        return -1

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self._name

    @property
    def device_connected(self) -> bool:
        """Return connection status of the device."""
        return self._protocol.connected

    @property
    def cloud_connected(self) -> bool:
        """Return connection status of the device."""
        return bool(
            self._protocol.cloud
            and self._protocol.cloud.connected
            and (not self._protocol.prefer_cloud or self.device_connected)
        )

    @property
    def cloud_auth_key(self) -> str | None:
        """Return the cloud auth key if available."""
        if self._protocol.cloud:
            return cast("str | None", self._protocol.cloud.auth_key)
        return None


# Classes split into separate modules for maintainability
from .device_info import DreameVacuumDeviceInfo
from .device_status import DreameVacuumDeviceStatus
