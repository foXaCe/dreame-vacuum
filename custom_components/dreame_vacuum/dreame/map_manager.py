from __future__ import annotations

"""Map manager module for Dreame vacuum integration.

Contains DreameMapVacuumMapManager which handles map lifecycle,
cloud sync and queue management.
"""

import base64
import copy
from functools import cmp_to_key
import hashlib
import json
import logging
import math
import threading
import time
from time import sleep
import traceback
from typing import Any, cast

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import (
    MAP_PARAMETER_ANGLE,
    MAP_PARAMETER_CODE,
    MAP_PARAMETER_CURR_ID,
    MAP_PARAMETER_EXPIRES_TIME,
    MAP_PARAMETER_MAP,
    MAP_PARAMETER_MAPSTR,
    MAP_PARAMETER_NAME,
    MAP_PARAMETER_OUT,
    MAP_PARAMETER_TIME,
    MAP_PARAMETER_URL,
    MAP_PARAMETER_VALUE,
    MAP_REQUEST_PARAMETER_FORCE_TYPE,
    MAP_REQUEST_PARAMETER_FRAME_ID,
    MAP_REQUEST_PARAMETER_FRAME_TYPE,
    MAP_REQUEST_PARAMETER_MAP_ID,
    MAP_REQUEST_PARAMETER_REQ_TYPE,
)
from .exceptions import DeviceUpdateFailedException
from .map_decoder import DreameVacuumMapDecoder
from .map_editor import DreameMapVacuumMapEditor
from .map_optimizer import DreameVacuumMapOptimizer
from .protocol import DreameVacuumProtocol, redact_url
from .vacuum_types import (
    DIID,
    PIID,
    DreameVacuumAction,
    DreameVacuumActionMapping,
    DreameVacuumDeviceCapability,
    DreameVacuumProperty,
    MapData,
    MapDataPartial,
    MapFrameType,
    RecoveryMapInfo,
)

_LOGGER = logging.getLogger(__name__)


class DreameMapVacuumMapManager:
    def __init__(self, _protocol: DreameVacuumProtocol) -> None:
        self._map_list_object_name: str | None = None
        self._map_list_md5: str | None = None
        self._recovery_map_list_object_name: str | None = None
        self._update_callback: Any = None
        self._change_callback: Any = None
        self._error_callback: Any = None
        self._update_timer: threading.Timer | None = None
        self._update_lock: threading.Lock = threading.Lock()
        self._update_interval: float = 10
        self._device_running: bool = False
        self._device_docked: bool = False
        self._available: bool = False
        self._disconnected: bool = False
        self._ready: bool = False
        self._connected: bool = True
        self._vslam_map: bool = False

        self._init_data()

        self._protocol = _protocol
        self.editor = DreameMapVacuumMapEditor(self)
        self.optimizer = DreameVacuumMapOptimizer()

    def _init_data(self) -> None:
        self._map_data: MapData | None = None
        self._current_frame_id: int | None = None
        self._current_map_id: int | None = None
        self._current_timestamp_ms: int | None = None
        self._file_urls: dict[str, Any] = {}
        self._saved_map_data: dict[int, MapData] = {}
        self._map_list: list[int] = []
        self._need_map_request: bool = False
        self._need_new_map: bool = False
        self._need_map_list_request: bool | None = None
        self._need_recovery_map_list_request: bool | None = None
        self._map_data_queue: dict[int, dict[int, Any]] = {}
        self._updated_frame_id: int | None = None
        self._selected_map_id: int | None = None
        self._request_queue: dict[str, bool] = {}
        self._latest_map_data_time: float | None = None
        self._latest_object_name_time: float | None = None
        self._latest_map_timestamp_ms: int | None = None
        self._latest_map_id: int | None = None
        self._last_p_request_map_id: int | None = None
        self._last_p_request_frame_id: int | None = None
        self._last_p_request_time: float | None = None
        self._last_robot_time: float | None = None
        self._map_request_time: float | None = None
        self._map_request_count: int = 0
        self._new_map_request_time: float | None = None
        self._aes_iv: str | None = None
        self._capability: DreameVacuumDeviceCapability | None = None

    def _request_map_from_cloud(self) -> bool:
        if self._protocol.cloud.dreame_cloud:
            return True

        if self._current_timestamp_ms is not None:
            start_time = self._current_timestamp_ms
            request_start_time: float = int(math.floor(start_time / 1000.0))
        else:
            request_start_time = 0
            if self._latest_object_name_time is not None:
                request_start_time = self._latest_object_name_time
            elif self._map_request_time is not None:
                request_start_time = self._map_request_time
            elif self._last_robot_time is not None:
                request_start_time = int(self._last_robot_time / 1000)

        if self._latest_map_data_time is None or self._latest_map_data_time < request_start_time:
            self._latest_map_data_time = request_start_time

        if self._latest_object_name_time is None or self._latest_object_name_time < request_start_time:
            self._latest_object_name_time = request_start_time

        map_data_result = self._protocol.cloud.get_device_property(
            DIID(DreameVacuumProperty.MAP_DATA), 20, self._latest_map_data_time
        )

        if not self._protocol.cloud.connected:
            if self._connected:
                self._connected = False
                self._map_data_changed()
            return False
        if not self._connected:
            self._connected = True
            self._map_data_changed()

        if map_data_result is None:
            _LOGGER.warning("Getting map_data from cloud failed")
            map_data_result = []

        object_name_result = self._protocol.cloud.get_device_property(
            DIID(DreameVacuumProperty.OBJECT_NAME), 1, self._latest_object_name_time
        )
        if object_name_result is None:
            _LOGGER.warning("Getting object_name from cloud failed")

        partial_map_data = None
        if len(map_data_result):
            partial_map_data = []
            self._latest_map_data_time = map_data_result[0][MAP_PARAMETER_TIME] + 1

            for data in map_data_result:
                partial_map_data.append(
                    self._decode_map_partial(
                        json.loads(data[MAP_PARAMETER_VALUE if MAP_PARAMETER_VALUE in data else "val"])[0],
                        data[MAP_PARAMETER_TIME] * 1000 if data.get(MAP_PARAMETER_TIME) else None,
                    )
                )

        object_name = None
        object_name_timestamp = None
        if object_name_result:
            data = object_name_result[0]
            timestamp = None
            if MAP_PARAMETER_TIME in data:
                timestamp = data[MAP_PARAMETER_TIME]
                self._latest_object_name_time = timestamp + 1

            if len(object_name_result) == 1:
                object_name = json.loads(data[MAP_PARAMETER_VALUE if MAP_PARAMETER_VALUE in data else "val"])[0]
                if timestamp:
                    object_name_timestamp = timestamp * 1000

        self._add_cloud_map_data(partial_map_data, object_name, object_name_timestamp)
        return bool(len(map_data_result) or object_name is not None)

    def _request_map(self, parameters: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if parameters is None:
            parameters = {
                MAP_REQUEST_PARAMETER_FRAME_TYPE: MapFrameType.I.name,
            }

        payload = [
            {
                "piid": PIID(DreameVacuumProperty.FRAME_INFO),
                MAP_PARAMETER_VALUE: str(json.dumps(parameters, separators=(",", ":"))).replace(" ", ""),
            }
        ]

        try:
            _LOGGER.debug("Request map from device %s", payload)
            mapping = DreameVacuumActionMapping[DreameVacuumAction.REQUEST_MAP]
            return cast("dict[str, Any] | None", self._protocol.action(mapping["siid"], mapping["aiid"], payload, 0))
        except Exception as ex:
            _LOGGER.warning("Send request map failed: %s", ex)
        return None

    def _request_i_map(self, start_time: float | None = None) -> bool:
        if not self._request_i_map_available and not self._protocol.dreame_cloud:
            self.request_new_map()
            return False

        parameters = {
            MAP_REQUEST_PARAMETER_REQ_TYPE: 1,
            MAP_REQUEST_PARAMETER_FRAME_TYPE: MapFrameType.I.name,
            MAP_REQUEST_PARAMETER_FORCE_TYPE: 1,
        }

        if start_time:
            parameters[MAP_PARAMETER_TIME] = start_time

        result = self._request_map(parameters)
        if result and result[MAP_PARAMETER_CODE] == 0:
            out = result[MAP_PARAMETER_OUT]
            _LOGGER.debug("Response from device %s", out)
            has_map = False
            object_name = None
            raw_map_data = None
            for prop in out:
                value = prop[MAP_PARAMETER_VALUE]
                if value != "":
                    piid = prop["piid"]
                    if piid == PIID(DreameVacuumProperty.OBJECT_NAME):
                        has_map = True
                        object_name = value
                    elif piid == PIID(DreameVacuumProperty.MAP_DATA):
                        has_map = True
                        raw_map_data = value
                    elif piid == PIID(DreameVacuumProperty.ROBOT_TIME):
                        self._last_robot_time = int(value)
                        if start_time is None:
                            self._map_request_time = self._last_robot_time
                            self._map_request_count = 1
                    elif piid == PIID(DreameVacuumProperty.OLD_MAP_DATA):
                        if not has_map:
                            values = value.split(",")
                            if values[0] == "0":
                                raw_map_data = values[1]
                            else:
                                object_name = values[1]
                                if len(values) == 3:
                                    object_name = f"{object_name},{values[2]}"

            if has_map:
                self._latest_object_name_time = int((self._last_robot_time or 0) / 1000) + 1
                self._map_request_time = None

            if object_name:
                self._add_map_data_file(object_name, self._last_robot_time)
                return True
            if raw_map_data:
                self._add_raw_map_data(raw_map_data, self._last_robot_time)
                return True
            return False

        self._request_map_from_cloud()
        return False

    def _request_missing_p_map(self) -> bool:
        if self._map_data is None:
            return False

        if self._partial_map_queue_size() == 0:
            return False

        frame_id = (self._current_frame_id or 0) + 1
        map_id = self._current_map_id

        if (
            self._last_p_request_time is not None
            and self._last_p_request_map_id == map_id
            and self._last_p_request_frame_id == frame_id
            and (time.time() - self._last_p_request_time) < 3
        ):
            return False

        self._last_p_request_map_id = map_id
        self._last_p_request_frame_id = frame_id
        self._last_p_request_time = time.time()

        _LOGGER.debug("Request missing P map: %s", frame_id)
        result = self._request_map(
            {
                MAP_REQUEST_PARAMETER_MAP_ID: map_id,
                MAP_REQUEST_PARAMETER_FRAME_ID: frame_id,
                MAP_REQUEST_PARAMETER_FRAME_TYPE: MapFrameType.P.name,
            }
        )
        return bool(result and result[MAP_PARAMETER_CODE] == 0)

    def _request_next_p_map(self, map_id: int | None, frame_id: int) -> bool:
        key = f"{map_id}:{frame_id}"
        if self._request_queue.get(key):
            return False

        self._request_queue[key] = True
        _LOGGER.debug("Request next P map: %s", frame_id)
        result = self._request_map(
            {
                MAP_REQUEST_PARAMETER_MAP_ID: map_id,
                MAP_REQUEST_PARAMETER_REQ_TYPE: 1,
                MAP_REQUEST_PARAMETER_FRAME_ID: frame_id,
                MAP_REQUEST_PARAMETER_FRAME_TYPE: MapFrameType.P.name,
            }
        )
        # Release the key whatever the outcome; keeping it on failure would
        # block any future retry of this exact map_id/frame_id pair.
        self._request_queue.pop(key, None)
        if result and result[MAP_PARAMETER_CODE] == 0:
            object_name = None
            raw_map_data = None
            timestamp = None

            for prop in result[MAP_PARAMETER_OUT]:
                value = prop[MAP_PARAMETER_VALUE]
                if value != "":
                    piid = prop["piid"]
                    if piid == PIID(DreameVacuumProperty.OBJECT_NAME):
                        object_name = value
                    elif piid == PIID(DreameVacuumProperty.MAP_DATA):
                        raw_map_data = value
                    elif piid == PIID(DreameVacuumProperty.ROBOT_TIME):
                        timestamp = int(value)

            if object_name:
                self._add_map_data_file(object_name, timestamp)
            if raw_map_data:
                _LOGGER.debug("Lost P map received: %s:%s", map_id, frame_id)
                self._add_raw_map_data(raw_map_data, timestamp)

            if not raw_map_data and self._vslam_map and not object_name:
                self.request_new_map()
                return False
            return True
        return False

    def _request_current_map(self, map_request_time: float | None = None) -> bool:
        if self._request_i_map_available or self._protocol.dreame_cloud:
            return self._request_i_map(map_request_time)

        return self._request_map_from_cloud()

    def _map_data_updated(self) -> None:
        if self._update_callback:
            _LOGGER.debug("Update callback")
            self._update_callback()

    def _map_data_changed(self, saved_map: bool = False) -> None:
        if self._change_callback:
            _LOGGER.debug("Change callback")
            self._change_callback(saved_map)

    def _update_task(self) -> None:
        if self._update_timer is not None:
            self._update_timer.cancel()
            self._update_timer = None

        start = time.time()
        self.update()
        self.schedule_update(max(self._update_interval - (time.time() - start), 1))

    def _queue_partial_map(self, map_data: Any) -> None:
        if map_data.map_id != self._latest_map_id:
            return
        next_frame_id = 0

        if self._current_map_id is not None and self._current_map_id == self._latest_map_id:
            next_frame_id = (self._current_frame_id or 0) + 1

        if map_data.map_id not in self._map_data_queue:
            self._map_data_queue[map_data.map_id] = {}

        if map_data.frame_id < next_frame_id:
            return
        self._map_data_queue[map_data.map_id][map_data.frame_id] = map_data

    def _delete_invalid_partial_maps(self) -> None:
        if self._latest_map_id is None:
            return

        if self._current_frame_id is None:
            return

        frame_id = self._current_frame_id
        map_data_queue = copy.deepcopy(self._map_data_queue)
        for k, _v in map_data_queue.items():
            if k != self._latest_map_id:
                del self._map_data_queue[k]

        if self._latest_map_id not in self._map_data_queue or not self._map_data_queue[self._latest_map_id]:
            return

        map_data_queue = copy.deepcopy(self._map_data_queue[self._latest_map_id])
        for k, _v in map_data_queue.items():
            if k <= frame_id:
                del self._map_data_queue[self._latest_map_id][k]

    def _unqueue_next_partial_map(self) -> MapData | None:
        if self._latest_map_id is None or self._current_frame_id is None or self._current_map_id != self._latest_map_id:
            return None

        frame_id = self._current_frame_id + 1
        if (
            self._latest_map_id not in self._map_data_queue
            or not self._map_data_queue[self._latest_map_id]
            or frame_id not in self._map_data_queue[self._latest_map_id]
        ):
            return None

        map_data = self._map_data_queue[self._latest_map_id][frame_id]

        if map_data:
            del self._map_data_queue[self._latest_map_id][frame_id]
            return cast("MapData | None", map_data)
        return None

    def _unqueue_partial_map(self, map_id: int | None, frame_id: int) -> MapData | None:
        if map_id in self._map_data_queue and self._map_data_queue[map_id] and frame_id in self._map_data_queue[map_id]:
            map_data = self._map_data_queue[map_id][frame_id]
            del self._map_data_queue[map_id][frame_id]
            return cast("MapData | None", map_data)
        return None

    def _partial_map_queue_size(self) -> int:
        if self._latest_map_timestamp_ms is None:
            return 0

        if self._latest_map_id not in self._map_data_queue or not self._map_data_queue[self._latest_map_id]:
            return 0

        return len(self._map_data_queue[self._latest_map_id])

    def _get_object_file_data(self, object_name: str = "", timestamp: Any = None) -> tuple[Any, str | None]:
        key = None
        if object_name and "," in object_name:
            values = object_name.split(",")
            object_name = values[0]
            key = values[1]
        response = self._get_interim_file_data(object_name, timestamp)
        return response, key

    def _get_interim_file_data(self, object_name: str = "", timestamp: Any = None) -> Any:
        cloud: Any = self._protocol.cloud
        if cloud.logged_in:
            if object_name is None or object_name == "":
                _LOGGER.debug("Get object name from cloud")
                if cloud.dreame_cloud:
                    object_name_result = cloud.get_properties(DIID(DreameVacuumProperty.OBJECT_NAME))
                    if object_name_result:
                        object_name_result = object_name_result[0][MAP_PARAMETER_VALUE]
                        object_name = object_name_result[0]
                else:
                    object_name_result = cloud.get_device_property(DIID(DreameVacuumProperty.OBJECT_NAME))
                    if object_name_result:
                        object_name_result = json.loads(object_name_result[0][MAP_PARAMETER_VALUE])
                        object_name = object_name_result[0]

            if object_name is None or object_name == "":
                object_name = cloud.object_name

            url = self._get_file_url(object_name)
            if url:
                # The query string is the download credential — never log it.
                _LOGGER.debug("Request map data from cloud %s", redact_url(url))
                response = cloud.get_file(url)
                if response is not None:
                    return response
                _LOGGER.warning("Request map data from cloud failed %s", redact_url(url))
                if self._file_urls.get(object_name):
                    del self._file_urls[object_name]
        return None

    def _get_file_url(self, object_name: str, interim: bool = True) -> str | None:
        url = None
        now = int(round(time.time()))
        if self._file_urls and self._file_urls.get(object_name):
            object = self._file_urls[object_name]
            if object[MAP_PARAMETER_EXPIRES_TIME] - now > 60:
                url = f"{object[MAP_PARAMETER_URL]}&current={now!s}"

        if url is None:
            # Drop expired entries so the URL cache cannot grow unbounded
            # (map object names change with every map update).
            self._file_urls = {k: v for k, v in self._file_urls.items() if v[MAP_PARAMETER_EXPIRES_TIME] > now}
            response = (
                self._protocol.cloud.get_interim_file_url(object_name)
                if interim
                else self._protocol.cloud.get_file_url(object_name)
            )
            if response:
                self._file_urls[object_name] = {
                    MAP_PARAMETER_URL: response,
                    MAP_PARAMETER_EXPIRES_TIME: now + (30 * 60),
                }
                url = self._file_urls[object_name][MAP_PARAMETER_URL]
        return url

    def _decode_map_partial(self, raw_map: Any, timestamp: Any = None, key: Any = None) -> MapDataPartial | None:
        partial_map = DreameVacuumMapDecoder.decode_map_partial(raw_map, self._aes_iv, key)
        if partial_map is not None:
            # After restart or unsuccessful start robot returns timestamp_ms as uptime and that messes up with the latest map/frame id detection.
            # I could not figure out how app handles with this issue but i have added this code to update time stamp as request/object time.

            if timestamp and (partial_map.timestamp_ms is None or partial_map.timestamp_ms < 1577826000000):
                partial_map.timestamp_ms = timestamp

            if self._latest_map_timestamp_ms is None or (partial_map.timestamp_ms or 0) > self._latest_map_timestamp_ms:
                self._latest_map_timestamp_ms = partial_map.timestamp_ms
                self._latest_map_id = partial_map.map_id

        return partial_map

    def _add_cloud_map_data(self, partial_map_data: Any, object_name: Any, object_name_timestamp: Any) -> Any:
        if partial_map_data:
            for partial_map in partial_map_data:
                if partial_map.frame_type == MapFrameType.I.value:
                    self._add_map_data(partial_map)
                else:
                    self._queue_partial_map(partial_map)

        next_frame_id = 1
        if self._current_frame_id:
            next_frame_id = self._current_frame_id + 1

        if (
            not self._add_map_data(self._unqueue_partial_map(self._latest_map_id, next_frame_id))
            and object_name is None
        ):
            self._delete_invalid_partial_maps()
            tmpLen = self._partial_map_queue_size()
            if tmpLen > 8:
                if self._protocol.dreame_cloud:
                    self._request_map()
                else:
                    self.request_new_map()
            elif tmpLen > 4:
                self._request_missing_p_map()
            elif tmpLen > 0 and partial_map_data:
                self._request_next_p_map(self._latest_map_id, next_frame_id)

        if object_name is not None:
            self._need_new_map = False
            _LOGGER.debug("New object name received: %s", object_name)
            response, key = self._get_object_file_data(object_name, object_name_timestamp)
            if response:
                partial_map = self._decode_map_partial(response.decode(), object_name_timestamp, key)
                if partial_map:
                    if self._map_data is None or partial_map.frame_type == MapFrameType.I.value:
                        return self._add_map_data(partial_map)

                    self._queue_partial_map(partial_map)
                    next_partial_map = self._unqueue_next_partial_map()
                    if next_partial_map:
                        self._add_map_data(next_partial_map)
                    else:
                        self._delete_invalid_partial_maps()
                        if self._partial_map_queue_size() > 8:
                            if self._protocol.dreame_cloud:
                                self._request_map()
                            else:
                                self.request_new_map()
        return None

    def _add_map_data_file(self, object_name: str, timestamp: Any) -> None:
        response, key = self._get_object_file_data(object_name, timestamp)
        if response is not None:
            self._add_raw_map_data(response.decode(), timestamp, key)

    def _add_raw_map_data(self, raw_map: str, timestamp: Any = None, key: Any = None) -> bool:
        return self._add_map_data(self._decode_map_partial(raw_map, timestamp, key))

    def _add_map_data(self, partial_map: Any) -> bool:
        if partial_map is None:
            return False

        if (
            partial_map.timestamp_ms is not None
            and self._current_timestamp_ms is not None
            and self._current_frame_id
            and self._current_timestamp_ms > partial_map.timestamp_ms
        ):
            _LOGGER.debug(
                "Skip frame %s, timestamp %s:%s < %s:%s",
                partial_map.frame_type,
                partial_map.frame_id,
                partial_map.timestamp_ms,
                self._current_frame_id,
                self._current_timestamp_ms,
            )
            return True

        if self._current_map_id is not None and self._current_map_id != self._latest_map_id:
            _LOGGER.debug(
                "Map ID Changed: %s -> %s",
                self._current_map_id,
                self._latest_map_id,
            )

            self._current_frame_id = None
            self._current_map_id = None
            self._updated_frame_id = None
            # self.request_next_map_list()

        if partial_map.map_id != self._latest_map_id:
            _LOGGER.debug(
                "Skip frame, map_id %s != %s",
                partial_map.map_id,
                self._latest_map_id,
            )
            # self._add_next_map_data()
            return True

        if self._current_frame_id is not None and partial_map.frame_id < self._current_frame_id:
            if partial_map.frame_type != MapFrameType.I.value or partial_map.timestamp_ms <= self._current_timestamp_ms:
                _LOGGER.debug(
                    "Skip frame, frame id %s:%s < %s:%s",
                    partial_map.map_id,
                    partial_map.frame_id,
                    self._current_map_id,
                    self._current_frame_id,
                )
                # self._add_next_map_data()
                return True

        if partial_map.frame_type == MapFrameType.P.value:
            if self._current_frame_id is not None and self._map_data is not None and self._map_data.restored_map:
                _LOGGER.debug("Current map data removed")
                self._map_data = None
                self._current_frame_id = None
                self._current_map_id = None

            if self._current_frame_id is None or self._map_data is None:
                self._queue_partial_map(partial_map)

                if self._map_request_time is None:
                    self._request_i_map()
                    return True

            if partial_map.frame_id != (self._current_frame_id or 0) + 1:
                if partial_map.frame_id <= (self._current_frame_id or 0):
                    self._add_next_map_data()
                    return True

                self._queue_partial_map(partial_map)
                self._delete_invalid_partial_maps()

                tmpLen = self._partial_map_queue_size()
                if tmpLen > 0:
                    if self._protocol.dreame_cloud:
                        if tmpLen > 8:
                            self._request_map()
                        elif tmpLen > 4:
                            self._request_missing_p_map()
                        else:
                            next_frame_id = 1
                            if self._current_frame_id:
                                next_frame_id = self._current_frame_id + 1
                            self._request_next_p_map(self._latest_map_id, next_frame_id)
                    else:
                        self._request_next_p_map(partial_map.map_id, (self._current_frame_id or 0) + 1)
                else:
                    self._add_next_map_data()
                return True

            current_map_data: Any = self._map_data
            current_robot_position = (
                copy.deepcopy(current_map_data.robot_position)
                if current_map_data and current_map_data.robot_position
                else None
            )

            map_data = DreameVacuumMapDecoder.decode_p_map_data_from_partial(
                partial_map,
                current_map_data,
                self._vslam_map,
            )
            if map_data:
                if map_data.carpet_pixels and (
                    current_map_data is None or current_map_data.dimensions != map_data.dimensions
                ):
                    map_data.carpet_pixels = DreameVacuumMapDecoder.get_carpets(map_data, self.selected_map)

                self._map_data = map_data
                self._map_data.last_updated = time.time()
                self._updated_frame_id = None
                self._current_frame_id = map_data.frame_id
                self._current_map_id = map_data.map_id
                self._current_timestamp_ms = map_data.timestamp_ms

                _LOGGER.debug("Decode P map %d %d", map_data.map_id, map_data.frame_id)

                if not self._device_running or current_robot_position != map_data.robot_position:
                    self._map_data_changed()

        elif partial_map.frame_type == MapFrameType.I.value:
            self._need_map_request = False
            self._delete_invalid_partial_maps()

            (
                map_data,
                saved_map_data,
            ) = DreameVacuumMapDecoder.decode_map_data_from_partial(partial_map, self._vslam_map)
            if map_data is None:
                self._add_next_map_data()
                return True

            if map_data.empty_map:
                if self._map_data is None or not self._map_data.empty_map:
                    self._init_data()
                    self._map_data = map_data
                    self._current_frame_id = map_data.frame_id
                    self._current_map_id = map_data.map_id
                    self._current_timestamp_ms = map_data.timestamp_ms

                    self._map_data_changed()
                self._add_next_map_data()
                return True

            if saved_map_data is not None and saved_map_data.saved_map:
                if saved_map_data.map_id in self._saved_map_data:
                    map_data.temporary_map = False
                    self._selected_map_id = saved_map_data.map_id
                    saved_map_data.map_name = self._saved_map_data[saved_map_data.map_id].map_name
                    saved_map_data.custom_name = self._saved_map_data[saved_map_data.map_id].custom_name
                    saved_map_data.rotation = self._saved_map_data[saved_map_data.map_id].rotation
                    saved_map_data.map_index = self._saved_map_data[saved_map_data.map_id].map_index
                    saved_map_data.recovery_map_list = self._saved_map_data[saved_map_data.map_id].recovery_map_list

                    saved_map_data.timestamp_ms = map_data.timestamp_ms
                    if (
                        saved_map_data != self._saved_map_data[saved_map_data.map_id]
                        or saved_map_data.segments != self._saved_map_data[saved_map_data.map_id].segments
                    ):
                        saved_map_data.last_updated = time.time()
                        if saved_map_data.wifi_map_data:
                            saved_map_data.wifi_map_data.last_updated = saved_map_data.last_updated
                        self._saved_map_data[saved_map_data.map_id] = saved_map_data
                        if not self._protocol.dreame_cloud:
                            self.request_next_map_list()

                        _LOGGER.debug(
                            "Decode saved map %s: %s",
                            saved_map_data.map_id,
                            saved_map_data.map_name,
                        )
                elif not map_data.temporary_map:
                    if not self._map_list:
                        saved_map_data.last_updated = time.time()
                        if saved_map_data.wifi_map_data:
                            saved_map_data.wifi_map_data.last_updated = saved_map_data.last_updated
                        self._saved_map_data[saved_map_data.map_id] = saved_map_data

                        _LOGGER.debug("Add saved map from new map %s", saved_map_data.map_id)
                        self._refresh_map_list()
                        if self._map_data:
                            self._map_data_changed()

                    if not self._protocol.dreame_cloud:
                        if self._device_running:
                            self.request_next_map_list()
                        else:
                            self.request_map_list()

            DreameVacuumMapDecoder.set_segment_cleanset(map_data, map_data.cleanset, self._capability)
            DreameVacuumMapDecoder.set_floor_material(map_data, self._capability)
            DreameVacuumMapDecoder.set_carpet_cleanset(map_data, map_data.carpet_cleanset, self._capability)
            if not map_data.saved_map:
                if map_data.saved_map_id and map_data.saved_map_id in self._saved_map_data:
                    map_data.map_index = self._saved_map_data[map_data.saved_map_id].map_index

                if self._vslam_map:
                    if map_data.saved_map_status == 1 and saved_map_data and self._device_docked:
                        map_data.segments = copy.deepcopy(saved_map_data.segments)
                        map_data.data = copy.deepcopy(saved_map_data.data)
                        map_data.pixel_type = copy.deepcopy(saved_map_data.pixel_type)
                        map_data.dimensions = copy.deepcopy(saved_map_data.dimensions)
                        map_data.charger_position = copy.deepcopy(saved_map_data.charger_position)
                        map_data.no_go_areas = saved_map_data.no_go_areas
                        map_data.no_mopping_areas = saved_map_data.no_mopping_areas
                        map_data.virtual_walls = saved_map_data.virtual_walls
                        map_data.robot_position = None
                        map_data.docked = True
                        # map_data.restored_map = True
                        map_data.path = None
                        map_data.need_optimization = False
                        map_data.saved_map_status = 2
                    elif (
                        map_data.robot_position is None
                        and map_data.restored_map
                        and not self._device_docked
                        and self._map_data
                        and not map_data.docked
                    ):
                        map_data.robot_position = self._map_data.robot_position

                changed = (
                    self._current_frame_id is None
                    or self._map_data is None
                    or map_data != self._map_data
                    or map_data.rotation != self._map_data.rotation
                    or map_data.segments != self._map_data.segments
                )

                if (
                    changed
                    or self._current_frame_id != map_data.frame_id
                    or self._current_timestamp_ms != map_data.timestamp_ms
                ):
                    if (
                        self._current_frame_id is not None
                        and self._map_data is not None
                        and self._updated_frame_id is not None
                    ):
                        if (map_data.frame_id or 0) <= self._updated_frame_id + 1:
                            if not self._map_data.empty_map and (
                                self._map_data.saved_map_status == 2
                                or (self._vslam_map and self._map_data.saved_map_status == 1)
                            ):
                                map_data.active_segments = self._map_data.active_segments
                                map_data.active_areas = self._map_data.active_areas
                                map_data.active_points = self._map_data.active_points
                                map_data.active_cruise_points = self._map_data.active_cruise_points
                                map_data.path = self._map_data.path
                                map_data.segments = self._map_data.segments
                                map_data.floor_material = self._map_data.floor_material
                                map_data.hidden_segments = self._map_data.hidden_segments
                                map_data.cleanset = self._map_data.cleanset
                                map_data.carpet_cleanset = self._map_data.carpet_cleanset
                                changed = map_data != self._map_data
                            else:
                                changed = False
                                map_data.empty_map = True
                        else:
                            self._updated_frame_id = None

                    if (
                        self._map_data
                        and not changed
                        and map_data.need_optimization
                        and not self._map_data.need_optimization
                    ):
                        map_data.need_optimization = False
                        map_data.optimized_pixel_type = copy.deepcopy(self._map_data.optimized_pixel_type)
                        map_data.optimized_dimensions = copy.deepcopy(self._map_data.optimized_dimensions)
                        map_data.optimized_charger_position = copy.deepcopy(self._map_data.optimized_charger_position)

                    self._map_data = map_data
                    self._current_frame_id = map_data.frame_id
                    self._current_map_id = map_data.map_id
                    self._current_timestamp_ms = map_data.timestamp_ms

                    if changed:
                        _LOGGER.debug("Decode I map %d %d", map_data.map_id, map_data.frame_id)
                        self._map_data.last_updated = time.time()
                        self._map_data_changed()
                    else:
                        _LOGGER.debug(
                            "Decode map %d %d not changed",
                            map_data.map_id,
                            map_data.frame_id,
                        )

        if self._current_frame_id is None and self._map_data is not None:
            self._map_data = None
            self._map_data_changed()

        self._add_next_map_data()
        return True

    def _add_next_map_data(self) -> None:
        next_partial_map = self._unqueue_next_partial_map()
        if next_partial_map is not None:
            _LOGGER.debug("Continue to next map data")
            self._add_map_data(next_partial_map)

    def _refresh_map_list(self) -> None:
        index = 1
        new_map_list = []
        for map_id, saved_map_data in sorted(self._saved_map_data.items()):
            new_map_list.append(map_id)
            if saved_map_data.custom_name is None:
                saved_map_data.map_name = f"Map {index!s}"
            else:
                saved_map_data.map_name = saved_map_data.custom_name
            saved_map_data.map_index = index
            index = index + 1
        self._map_list = new_map_list

    def _refresh_recovery_map_list(self) -> None:
        index = 1
        for _map_id, saved_map_data in sorted(self._saved_map_data.items()):
            if saved_map_data.recovery_map_list:
                for recovery_map_data in saved_map_data.recovery_map_list:
                    map_type = recovery_map_data.map_type.name.replace("_", " ").title()
                    if saved_map_data.custom_name is None:
                        recovery_map_data.map_name = f"Recovery Map {index!s} ({map_type})"
                    else:
                        recovery_map_data.map_name = f"{saved_map_data.custom_name} Recovery Map {index!s} ({map_type})"
                    recovery_map_data.map_index = index
                    index = index + 1

    def handle_properties(self, properties: Any) -> None:
        if not self._ready:
            return

        has_map = False
        object_name = None
        raw_map_data = None

        for prop in properties:
            value = prop[MAP_PARAMETER_VALUE]
            if value != "":
                piid = prop["piid"]
                if piid == PIID(DreameVacuumProperty.OBJECT_NAME):
                    has_map = True
                    object_name = value
                elif piid == PIID(DreameVacuumProperty.MAP_DATA):
                    has_map = True
                    raw_map_data = value
                elif piid == PIID(DreameVacuumProperty.OLD_MAP_DATA):
                    if not has_map:
                        values = value.split(",")
                        if values[0] == "0":
                            raw_map_data = values[1]
                        else:
                            object_name = values[1]
                            if len(values) == 3:
                                object_name = f"{object_name},{values[2]}"

        if has_map:
            self._map_request_time = None

        if object_name or raw_map_data:
            partial_map_data = None
            timestamp = int(time.time() * 1000)

            if raw_map_data:
                partial_map_data = [self._decode_map_partial(raw_map_data, timestamp)]
            self._add_cloud_map_data(partial_map_data, object_name, timestamp)

    def get_map(self, map_index: int = 0) -> MapData | None:
        if map_index:
            if map_index <= len(self._map_list):
                return self._saved_map_data[self._map_list[map_index - 1]]
            return None
        return self._map_data

    def get_obstacle_image(self, map_data: Any, index: Any) -> Any:
        index = str(index)
        if map_data and map_data.obstacles and index in map_data.obstacles:
            obstacle = map_data.obstacles[index]
            if (
                obstacle.file_name
                and len(obstacle.file_name) > 1
                and obstacle.key
                and len(obstacle.key) > 1
                and (obstacle.picture_status is None or obstacle.picture_status.value == 2)
            ):
                try:
                    object_name = (
                        f"{obstacle.file_name}-{obstacle.object_id}"
                        if self._protocol.dreame_cloud and obstacle.object_id
                        else obstacle.file_name
                    )
                    _LOGGER.debug(
                        "Obstacle image object name: %s",
                        object_name,
                    )
                    response = self._get_file_url(object_name, False)
                    if response:
                        response = self._protocol.cloud.get_file(response)
                        if response:
                            response = base64.b64encode(response).decode("utf-8")

                            cipher = Cipher(
                                algorithms.AES(
                                    bytearray.fromhex(hashlib.md5((obstacle.key).encode("utf-8")).hexdigest())
                                ),
                                modes.ECB(),
                                backend=default_backend(),
                            )
                            decryptor = cipher.decryptor()
                            unpadder = padding.PKCS7(128).unpadder()
                            return (
                                (
                                    unpadder.update(
                                        decryptor.update(base64.b64decode(response[response.find(",") + 1 :]))
                                        + decryptor.finalize()
                                    )
                                    + unpadder.finalize()
                                ),
                                obstacle,
                            )
                except Exception:
                    _LOGGER.warning(
                        "Obstacle (%s) image decryption failed: %s",
                        index,
                        traceback.format_exc(),
                    )
        return (None, None)

    def get_history_map(self, object_name: Any, key: Any = None) -> Any:
        if object_name and len(object_name):
            try:
                _LOGGER.debug(
                    "History map object name: %s",
                    object_name,
                )
                response = self._get_file_url(object_name, self._protocol.cloud.dreame_cloud)
                if response:
                    response = self._protocol.cloud.get_file(response)
                    if response:
                        map_data, saved_map_data = DreameVacuumMapDecoder.decode_map(
                            response.decode(), self._vslam_map, None, self._aes_iv, key
                        )
                        if map_data:
                            DreameVacuumMapDecoder.set_segment_cleanset(map_data, map_data.cleanset, self._capability)
                            DreameVacuumMapDecoder.set_carpet_cleanset(
                                map_data, map_data.carpet_cleanset, self._capability
                            )
                            map_data.history_map = True
                            if map_data.need_optimization:
                                map_data = self.optimizer.optimize(map_data, saved_map_data)
                                map_data.need_optimization = False
                            return map_data
            except Exception:
                _LOGGER.warning(
                    "History map decoding failed: %s",
                    traceback.format_exc(),
                )
        return None

    def get_recovery_map(self, map_id: Any, index: Any) -> Any:
        if map_id in self._map_list:
            recovery_map_list = self._saved_map_data[map_id].recovery_map_list
            index = int(index) - 1
            if recovery_map_list and len(recovery_map_list) > index:
                if recovery_map_list[index].map_data is None:
                    if (
                        recovery_map_list[index].raw_map is None
                        and recovery_map_list[index].map_object_name is not None
                    ):
                        try:
                            response = self._get_interim_file_data(recovery_map_list[index].map_object_name)
                            if response:
                                recovery_map_list[index].raw_map = response.decode()
                        except Exception as ex:
                            _LOGGER.warning("Get Recovery Map Object failed: %s", ex)
                            return None

                    if recovery_map_list[index].raw_map:
                        recovery_map_list[index].map_data = DreameVacuumMapDecoder.decode_saved_map(
                            recovery_map_list[index].raw_map,
                            self._vslam_map,
                            self._saved_map_data[map_id].rotation,
                            self._aes_iv,
                        )
                        recovery_map_list[index].map_data.last_updated = recovery_map_list[index].date.timestamp()
                        recovery_map_list[index].map_data.recovery_map_type = recovery_map_list[index].map_type
                        recovery_map_list[index].map_data.recovery_map = True
                return recovery_map_list[index].map_data
        return None

    def get_recovery_map_file(self, map_id: Any, index: Any) -> Any:
        if map_id in self._map_list:
            recovery_map_list = self._saved_map_data[map_id].recovery_map_list
            index = int(index) - 1
            if recovery_map_list and len(recovery_map_list) > index:
                object_name = recovery_map_list[index].object_name
                if object_name and object_name != "":
                    _LOGGER.debug(
                        "Recovery map object name: %s",
                        object_name,
                    )
                    map_url = self._get_file_url(
                        object_name,
                        not (object_name.endswith("mb.tbz2") and not self._protocol.dreame_cloud),
                    )
                    _LOGGER.debug("Recovery map file url: %s = %s", object_name, redact_url(map_url))
                    if map_url:
                        return (
                            self._protocol.cloud.get_file(map_url),
                            map_url,
                            object_name,
                        )
        return None, None, None

    def listen(self, change_callback: Any, update_callback: Any) -> None:
        self._change_callback = change_callback
        self._update_callback = update_callback

    def listen_error(self, callback: Any) -> None:
        self._error_callback = callback

    def disconnect(self) -> None:
        """Disconnect from map and cancel timers"""
        self._disconnected = True
        self.schedule_update(-1)
        if self.editor is not None:
            self.editor.cancel_pending()
        if self.optimizer is not None:
            self.optimizer.close()
        self._update_callback = None
        self._change_callback = None
        self._error_callback = None

    def schedule_update(self, wait: float | None = None) -> None:
        if wait is None:
            wait = self._update_interval
        if self._update_timer is not None:
            self._update_timer.cancel()
            del self._update_timer
            self._update_timer = None
        if wait >= 0 and not self._disconnected:
            self._update_timer = threading.Timer(wait, self._update_task)
            self._update_timer.start()

    def update(self) -> None:
        if not self._update_lock.acquire(blocking=False):
            return

        try:
            if (self._map_list_object_name and self._need_map_list_request is None) or (
                self._need_map_list_request and not self._device_running
            ):
                self.request_map_list()

            if self._recovery_map_list_object_name and self._need_recovery_map_list_request:
                self.request_recovery_map_list()

            if self._need_new_map:
                self.request_new_map()
                self._need_new_map = False
            elif self._map_request_time is not None or self._need_map_request:
                self._updated_frame_id = None
                self._map_request_count = self._map_request_count + 1
                if self._map_request_count >= 6:
                    self._map_request_time = None
                    self._need_map_request = False
                elif (
                    not self._request_current_map(self._map_request_time)
                    and self._protocol.dreame_cloud
                    and self._map_request_count == 2
                    and self._map_data is None
                ):
                    dreame_cloud: Any = self._protocol.cloud
                    object_name_result = dreame_cloud.get_properties(DIID(DreameVacuumProperty.OBJECT_NAME))
                    if object_name_result and MAP_PARAMETER_VALUE in object_name_result[0]:
                        self._add_cloud_map_data(
                            None, object_name_result[0][MAP_PARAMETER_VALUE], object_name_result[0].get("updateDate")
                        )
            elif not self._protocol.dreame_cloud:
                if self._map_data is None or (
                    self._device_running
                    and (time.time() - ((self._current_timestamp_ms or 0) / 1000.0) > 15 or self._map_data.empty_map)
                ):
                    self._updated_frame_id = None
                    if self._map_data and not self._map_data.empty_map:
                        _LOGGER.debug(
                            "Need map request: %.2f",
                            time.time() - ((self._current_timestamp_ms or 0) / 1000.0),
                        )
                    if self._protocol.cloud.logged_in:
                        self._request_current_map()
                elif not self._request_map_from_cloud() and self._device_running:
                    sleep(1)
                    if not self._request_map_from_cloud():
                        self.schedule_update(1)
            elif self._protocol.cloud.connected:
                if not self._connected:
                    self._connected = True
                    self._map_data_changed()

                if self._map_data is None or (
                    self._device_running
                    and (
                        (self._map_data.last_updated and time.time() - (self._map_data.last_updated) > 60)
                        or self._map_data.empty_map
                    )
                ):
                    if self._map_data and not self._map_data.empty_map:
                        _LOGGER.debug(
                            "Need map request: %.2f",
                            time.time() - (self._map_data.last_updated or 0),
                        )
                        self._request_map()
                    else:
                        self._request_current_map()
            elif self._connected:
                self._connected = False
                self._map_data_changed()

            if not self._available and self._connected:
                self._available = True
                self._map_data_changed()
        except Exception as ex:
            if self._available:
                _LOGGER.warning("Map update Failed: %s", traceback.format_exc())
                self._available = False
                if self._error_callback:
                    self._error_callback(DeviceUpdateFailedException(ex))
        finally:
            self._ready = True
            self._update_lock.release()

    def set_capability(self, capability: Any) -> None:
        if capability:
            self._capability = capability
            if not capability.lidar_navigation:
                self._vslam_map = True
            self._aes_iv = capability.key

    def set_update_interval(self, update_interval: float) -> None:
        if self._update_interval != update_interval:
            self._update_interval = update_interval
            self.schedule_update()

    def set_device_running(self, running: bool, docked: bool) -> None:
        if self._device_running != running:
            self._device_running = running

        if self._device_docked != docked:
            if docked:
                if not self._vslam_map:
                    self._request_map()
                elif self._map_data and self._map_data.saved_map_status == 1:
                    saved_map_data: Any = self.selected_map
                    self._map_data.segments = copy.deepcopy(saved_map_data.segments)
                    self._map_data.data = copy.deepcopy(saved_map_data.data)
                    self._map_data.pixel_type = copy.deepcopy(saved_map_data.pixel_type)
                    self._map_data.dimensions = copy.deepcopy(saved_map_data.dimensions)
                    self._map_data.charger_position = copy.deepcopy(saved_map_data.charger_position)
                    self._map_data.no_go_areas = saved_map_data.no_go_areas
                    self._map_data.no_mopping_areas = saved_map_data.no_mopping_areas
                    self._map_data.virtual_walls = saved_map_data.virtual_walls
                    self._map_data.robot_position = self._map_data.charger_position
                    self._map_data.docked = True
                    # self._map_data.restored_map = True
                    self._map_data.path = None
                    self._map_data.need_optimization = False
                    self._map_data.saved_map_status = 2
                    self._map_data.last_updated = time.time()
                    self._map_data.optimized_pixel_type = None
                    self._map_data.optimized_charger_position = None
                    self._map_data_changed()

            self._device_docked = docked
            self.schedule_update(2)

    def set_device_docked(self, device_docked: bool) -> None:
        if self._device_docked != device_docked:
            self.schedule_update(2)
        self._device_docked = device_docked

    def request_new_map(self) -> None:
        if (
            self._new_map_request_time
            and time.time() - self._new_map_request_time < 10
            and not self._protocol.dreame_cloud
        ):
            if time.time() - self._new_map_request_time > 3:
                self._new_map_request_time = time.time()
                self._request_map_from_cloud()
            return

        self._new_map_request_time = time.time()
        if self._map_data is None:
            self._request_i_map()
            return
        result = self._request_map()
        if result and result[MAP_PARAMETER_CODE] == 0 and not self._protocol.dreame_cloud:
            self._request_map_from_cloud()

    def request_next_map(self, request_new: bool = False) -> None:
        self._map_request_count = 0
        self._need_map_request = True
        if request_new:
            self._need_new_map = True
        self.schedule_update(2)

    def request_next_map_list(self) -> None:
        self._need_map_list_request = True

    def request_next_recovery_map_list(self) -> None:
        self._need_recovery_map_list_request = True

    def set_map_list_object_name(self, object_name: str, md5: str | None = None) -> bool:
        if object_name and object_name != "":
            if self._map_list_object_name != object_name or self._map_list_md5 != md5:
                self._map_list_object_name = object_name
                if not self._device_running and self._map_list_md5 is not None:
                    self.request_next_map_list()
                    self.schedule_update(3)
                self._map_list_md5 = md5
                return True
        return False

    def set_recovery_map_list_object_name(self, object_name: str) -> bool:
        if object_name and object_name != "":
            if self._recovery_map_list_object_name != object_name:
                self._recovery_map_list_object_name = object_name
                self._need_recovery_map_list_request = True
                return True
        return False

    def request_map_list(self) -> None:
        if self._map_list_object_name and self._protocol.cloud.logged_in:
            _LOGGER.debug("Get Map List: %s", self._map_list_object_name)
            try:
                response = self._get_interim_file_data(self._map_list_object_name)
            except Exception as ex:
                _LOGGER.warning("Get Map List failed: %s", ex)
                return

            if response:
                self._need_map_list_request = False
                try:
                    map_info = json.loads(response.decode())
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                    _LOGGER.warning("Get Map List json parse failed")
                    return

                saved_map_list = map_info[MAP_PARAMETER_MAPSTR]
                changed = False
                now = time.time()
                map_list = {}
                if saved_map_list:
                    for v in saved_map_list:
                        raw_map = None
                        if v.get(MAP_PARAMETER_MAP):
                            raw_map = v[MAP_PARAMETER_MAP]
                        elif map_info.get("server") == 1 and "rismobj" in v:
                            try:
                                response = self._get_interim_file_data(v["rismobj"])
                                if response:
                                    raw_map = response.decode()
                            except Exception as ex:
                                _LOGGER.warning("Get Saved Map Object failed: %s", ex)
                                continue

                        if raw_map:
                            try:
                                saved_map_data = DreameVacuumMapDecoder.decode_saved_map(
                                    raw_map,
                                    self._vslam_map,
                                    int(v[MAP_PARAMETER_ANGLE]) if v.get(MAP_PARAMETER_ANGLE) else 0,
                                    self._aes_iv,
                                )
                            except Exception:
                                _LOGGER.error("Parse saved map failed: %s", traceback.format_exc())
                                continue

                            if saved_map_data is not None:
                                name = v.get(MAP_PARAMETER_NAME)
                                saved_map_data.object_name = v.get("mapobj")
                                if name:
                                    saved_map_data.custom_name = name
                                    saved_map_data.map_name = name
                                map_list[saved_map_data.map_id] = saved_map_data

                    for map_id, saved_map_data in sorted(map_list.items()):
                        if map_id in self._saved_map_data:
                            if self._selected_map_id == map_id and self._map_data:
                                saved_map_data.cleanset = self._map_data.cleanset
                            else:
                                saved_map_data.cleanset = self._saved_map_data[map_id].cleanset

                            if self._saved_map_data[map_id] != saved_map_data:
                                _LOGGER.debug("Saved map changed: %s", map_id)
                                changed = True
                                saved_map_data.last_updated = now
                                if saved_map_data.wifi_map_data:
                                    saved_map_data.wifi_map_data.last_updated = saved_map_data.last_updated
                                saved_map_data.recovery_map_list = self._saved_map_data[map_id].recovery_map_list
                                if self._map_data is None or self._selected_map_id != map_id:
                                    self._saved_map_data[map_id] = saved_map_data
                                else:
                                    self._saved_map_data[map_id].custom_name = saved_map_data.custom_name
                                    self._saved_map_data[map_id].rotation = saved_map_data.rotation
                            else:
                                _LOGGER.debug("Saved map not changed: %s", map_id)
                        else:
                            saved_map_data.last_updated = now
                            if saved_map_data.wifi_map_data:
                                saved_map_data.wifi_map_data.last_updated = saved_map_data.last_updated
                            self._saved_map_data[cast(int, map_id)] = saved_map_data
                            _LOGGER.debug("Add saved map: %s", map_id)
                            changed = True

                selected_map_id = map_info[MAP_PARAMETER_CURR_ID]
                current_map_list = self._saved_map_data.copy()
                for map_id in current_map_list:
                    if map_id not in map_list and map_id != selected_map_id:
                        del self._saved_map_data[map_id]
                        changed = True

                if selected_map_id in self._saved_map_data and self._selected_map_id != selected_map_id:
                    self._selected_map_id = selected_map_id
                    changed = True

                if changed:
                    self._refresh_map_list()
                    if self._map_data:
                        self._map_data_changed(True)
                    self.request_next_recovery_map_list()

    def request_recovery_map_list(self) -> None:
        if self._recovery_map_list_object_name:
            if self._vslam_map:
                self._need_recovery_map_list_request = False
                return
            _LOGGER.debug("Get Recovery Map List: %s", self._recovery_map_list_object_name)
            response = self._get_file_url(self._recovery_map_list_object_name)
            if response:
                self._need_recovery_map_list_request = False
                response = self._protocol.cloud.get_file(response)
                if response:
                    try:
                        recovery_map_list = json.loads(response.decode())
                    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                        _LOGGER.warning("Get Recovery Map List json parse failed")
                        return

                    changed = False
                    for recovery_map in recovery_map_list:
                        map_id = recovery_map["id"]
                        if map_id in self._map_list:
                            recovery_map_list = []
                            map_info_list = recovery_map["info"]
                            for map_info in map_info_list:
                                recovery_map_list.append(
                                    RecoveryMapInfo(
                                        map_id,
                                        map_info.get("time"),
                                        map_info.get("thb"),
                                        map_info.get("rismobj"),
                                        map_info.get("objname"),
                                        map_info.get("first", -1),
                                    )
                                )
                            if len(recovery_map_list) > 2:

                                def _map_type_cmp(a: Any, b: Any) -> int:
                                    return int(a.map_type) - int(b.map_type) if a.map_type != b.map_type else 0

                                recovery_map_list.sort(key=cmp_to_key(_map_type_cmp))

                            existing_list = self._saved_map_data[map_id].recovery_map_list
                            if (
                                not existing_list
                                or len(existing_list) != len(recovery_map_list)
                                or not all(
                                    existing_list[i].__dict__ == recovery_map_list[i].__dict__
                                    for i in range(len(existing_list))
                                )
                            ):
                                self._saved_map_data[map_id].last_updated = time.time()
                                self._saved_map_data[map_id].recovery_map_list = recovery_map_list
                                _LOGGER.debug("Saved recovery map list changed: %s", map_id)
                                changed = True

                    if changed:
                        self._refresh_recovery_map_list()
                        if self._connected:
                            self._map_data_changed(True)
                    else:
                        _LOGGER.debug("Saved recovery map list not changed: %s", map_id)

    @property
    def _request_i_map_available(self) -> bool:
        return bool(
            not (
                self._map_data is not None
                and (
                    (self._map_data.saved_map_status == 0 and not self._map_data.empty_map)
                    or self._map_data.saved_map_status == 1
                    or self._map_data.restored_map
                    or self._map_data.temporary_map
                )
            )
        )

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def map_list(self) -> list[int] | None:
        return list(self._saved_map_data.keys())

    @property
    def map_data_list(self) -> dict[int, MapData] | None:
        return self._saved_map_data

    @property
    def selected_map(self) -> MapData | None:
        if self._map_data:
            if self._selected_map_id is not None and self._selected_map_id in self._saved_map_data:
                return self._saved_map_data[self._selected_map_id]

            if self._map_list and len(self._map_list) == 1 and self._map_list[0] in self._saved_map_data:
                return self._saved_map_data[self._map_list[0]]
        return None

    @property
    def cleaning_sequence(self) -> list[Any] | None:
        return (
            [
                (k)
                for k, v in sorted(
                    self._map_data.segments.items(),
                    key=lambda s: s[1].order if s[1].order is not None else 0,
                )
                if v.order
            ]
            if self._map_data and self._map_data.segments
            else []
        )
