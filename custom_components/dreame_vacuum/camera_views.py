"""HTTP proxy views for the Dreame Vacuum camera platform.

These process-global ``CameraView``/``HomeAssistantView`` subclasses stream
map data, obstacle photos, cleaning/cruising history, recovery maps, WiFi
maps and renderer resources for the camera entities defined in ``camera.py``.

The views resolve the target entity through Home Assistant's camera
component, so they only import ``DreameVacuumCameraEntity`` lazily inside
the request handlers — ``camera.py`` imports this module at load time and a
module-level import here would create a cycle.
"""

from __future__ import annotations

import gzip
import re
from typing import Any, Final

from aiohttp import web
from homeassistant.components.camera import DEFAULT_CONTENT_TYPE, Camera, CameraView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import HomeAssistantView

from .const import DOMAIN

JSON_CONTENT_TYPE: Final = "application/json"
PNG_CONTENT_TYPE: Final = "image/png"

_VIEWS_REGISTERED_KEY = f"{DOMAIN}_camera_views_registered"


def _query_bool(value: str | None) -> bool:
    """Parse a query parameter as a boolean. None or absent means False."""
    return value is not None and value.lower() in ("", "true", "1")


def _query_bool_default_true(value: str | None) -> bool:
    """Parse a query parameter as a boolean, defaulting to True if absent."""
    return value is None or value.lower() in ("", "true", "1")


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_filename(name: str | None, fallback: str = "image") -> str:
    """Sanitize a filename before putting it in an HTTP header.

    Cloud-provided names can reach Content-Disposition; we strip CR/LF and any
    character outside a small safe alphabet to prevent header injection.
    """
    if not name:
        return fallback
    cleaned = _SAFE_FILENAME_RE.sub("_", name)[:80].strip("._")
    return cleaned or fallback


class CameraDataView(CameraView):
    """Camera view to serve the map data."""

    url = "/api/camera_map_data_proxy/{entity_id}"
    name = "api:camera:map_data"

    async def handle(self, request: web.Request, camera: Camera) -> web.Response:
        """Serve camera data."""
        from .camera import DreameVacuumCameraEntity  # local import to avoid a cycle

        assert isinstance(camera, DreameVacuumCameraEntity)
        if not camera.map_data_json:
            include_resources = _query_bool(request.query.get("resources"))
            payload = await camera.hass.async_add_executor_job(camera.map_data_string, include_resources)
            response = web.Response(
                body=gzip.compress(bytes(payload, "utf-8")),
                content_type=JSON_CONTENT_TYPE,
            )
            response.headers["Content-Encoding"] = "gzip"
            return response
        raise web.HTTPNotFound()


class CameraObstacleView(CameraView):
    """Camera view to serve the map data obstacle image."""

    url = "/api/camera_map_obstacle_proxy/{entity_id}"
    name = "api:camera:map_obstacle"

    async def handle(self, request: web.Request, camera: Camera) -> web.Response:
        """Serve camera obstacle image."""
        from .camera import DreameVacuumCameraEntity  # local import to avoid a cycle

        assert isinstance(camera, DreameVacuumCameraEntity)
        if camera.map_index == 0:
            crop = request.query.get("crop")
            box = request.query.get("box")
            file = _query_bool(request.query.get("file"))
            result, object_name = await camera.obstacle_image(
                request.query.get("index", 1),
                _query_bool_default_true(box),
                _query_bool_default_true(crop),
            )
            if result:
                response = web.Response(
                    body=result,
                    content_type=DEFAULT_CONTENT_TYPE,
                )
                if file:
                    safe = _safe_filename(object_name.replace(".jpg", "").replace(".jpeg", ""))
                    response.headers["Content-Disposition"] = f'attachment; filename="{safe}.jpg"'
                return response

        raise web.HTTPNotFound()


class CameraObstacleHistoryView(CameraView):
    """Camera view to serve the map history data obstacle image."""

    url = "/api/camera_map_obstacle_history_proxy/{entity_id}"
    name = "api:camera:map_obstacle_history"

    async def handle(self, request: web.Request, camera: Camera) -> web.Response:
        """Serve camera obstacle image."""
        from .camera import DreameVacuumCameraEntity  # local import to avoid a cycle

        assert isinstance(camera, DreameVacuumCameraEntity)
        if camera.map_index == 0:
            crop = request.query.get("crop")
            box = request.query.get("box")
            file = _query_bool(request.query.get("file"))
            cruising = request.query.get("cruising")
            result, object_name = await camera.obstacle_history_image(
                request.query.get("index", 1),
                request.query.get("history_index", 1),
                _query_bool(cruising),
                _query_bool_default_true(box),
                _query_bool_default_true(crop),
            )
            if result:
                response = web.Response(
                    body=result,
                    content_type=DEFAULT_CONTENT_TYPE,
                )
                if file:
                    safe = _safe_filename(object_name.replace(".jpg", "").replace(".jpeg", ""))
                    response.headers["Content-Disposition"] = f'attachment; filename="{safe}.jpg"'
                return response

        raise web.HTTPNotFound()


class CameraHistoryView(CameraView):
    """Camera view to serve the cleaning or cruising history map."""

    url = "/api/camera_history_map_proxy/{entity_id}"
    name = "api:camera:history_map"

    async def handle(self, request: web.Request, camera: Camera) -> web.Response:
        """Serve camera cleaning history or cruising data."""
        from .camera import DreameVacuumCameraEntity  # local import to avoid a cycle

        assert isinstance(camera, DreameVacuumCameraEntity)
        if not camera.map_data_json and camera.map_index == 0:
            data = _query_bool(request.query.get("data"))
            cruising = request.query.get("cruising")
            resources = request.query.get("resources")
            dirty = request.query.get("dirty")
            info = request.query.get("info")
            result = await camera.history_map_image(
                request.query.get("index", 1),
                _query_bool_default_true(info),
                _query_bool(cruising),
                data,
                _query_bool(dirty),
                data and _query_bool(resources),
            )
            if result:
                response = web.Response(
                    body=gzip.compress(bytes(result, "utf-8")) if data else result,
                    content_type=JSON_CONTENT_TYPE if data else PNG_CONTENT_TYPE,
                )
                if data:
                    response.headers["Content-Encoding"] = "gzip"
                return response
        raise web.HTTPNotFound()


class CameraRecoveryView(CameraView):
    """Camera view to serve the recovery map."""

    url = "/api/camera_recovery_map_proxy/{entity_id}"
    name = "api:camera:recovery_map"

    async def handle(self, request: web.Request, camera: Camera) -> web.Response:
        """Serve camera recovery map data."""
        from .camera import DreameVacuumCameraEntity  # local import to avoid a cycle

        assert isinstance(camera, DreameVacuumCameraEntity)
        if not camera.map_data_json:
            index = request.query.get("index", 1)
            file = _query_bool(request.query.get("file"))
            data = False
            if file:
                result, map_url, object_name = await camera.recovery_map_file(index)
            else:
                data = _query_bool(request.query.get("data"))
                resources = request.query.get("resources")
                info = request.query.get("info")
                result = await camera.recovery_map(
                    index,
                    _query_bool_default_true(info),
                    data,
                    data and _query_bool(resources),
                )
            if result:
                response = web.Response(
                    body=gzip.compress(bytes(result, "utf-8")) if data and not file else result,
                    content_type="application/x-tar+gzip" if file else JSON_CONTENT_TYPE if data else PNG_CONTENT_TYPE,
                )
                if file:
                    safe = _safe_filename(object_name.replace("/", "-").replace(".mb.tbz2", ""), "recovery")
                    response.headers["Content-Disposition"] = f'attachment; filename="{safe}.mb.tbz2"'
                elif data:
                    response.headers["Content-Encoding"] = "gzip"
                return response
        raise web.HTTPNotFound()


class CameraWifiView(CameraView):
    """Camera view to serve the saved wifi map."""

    url = "/api/camera_wifi_map_proxy/{entity_id}"
    name = "api:camera:wifi_map"

    async def handle(self, request: web.Request, camera: Camera) -> web.Response:
        """Serve camera wifi map data."""
        from .camera import DreameVacuumCameraEntity  # local import to avoid a cycle

        assert isinstance(camera, DreameVacuumCameraEntity)
        if not camera.map_data_json:
            data = _query_bool(request.query.get("data"))
            resources = request.query.get("resources")
            result = await camera.wifi_map_data(
                data,
                data and _query_bool(resources),
            )
            if result:
                response = web.Response(
                    body=gzip.compress(bytes(result, "utf-8")) if data else result,
                    content_type=JSON_CONTENT_TYPE if data else PNG_CONTENT_TYPE,
                )
                if data:
                    response.headers["Content-Encoding"] = "gzip"
                return response
        raise web.HTTPNotFound()


class CameraResourcesView(HomeAssistantView):
    """Camera view to serve the map data resources."""

    url = "/api/camera_resources_proxy/{entity_id}"
    name = "api:camera:resources"

    requires_auth = True

    def __init__(self, component: Any) -> None:
        """Initialize camera view."""
        self.component = component

    async def get(self, request: web.Request, entity_id: str) -> web.StreamResponse:
        """Serve resources data."""
        if (
            (camera := self.component.get_entity(entity_id)) is None
            or camera.map_data_json
            or camera.map_index != 0
            or not camera.device
        ):
            raise web.HTTPNotFound

        icon_set = request.query.get("icon_set")
        payload = await camera.hass.async_add_executor_job(camera.resources, icon_set)
        response = web.Response(
            body=gzip.compress(bytes(payload, "utf-8")),
            content_type=JSON_CONTENT_TYPE,
        )
        response.headers["Content-Encoding"] = "gzip"
        return response


def async_register_camera_views(hass: HomeAssistant) -> None:
    """Register the camera proxy views once per Home Assistant process.

    HTTP views are process-global; register them only once even when several
    Dreame vacuums share a Home Assistant instance or the integration is
    reloaded.
    """
    if hass.data.get(_VIEWS_REGISTERED_KEY):
        return
    camera = hass.data["camera"]
    hass.http.register_view(CameraDataView(camera))
    hass.http.register_view(CameraObstacleView(camera))
    hass.http.register_view(CameraObstacleHistoryView(camera))
    hass.http.register_view(CameraHistoryView(camera))
    hass.http.register_view(CameraRecoveryView(camera))
    hass.http.register_view(CameraWifiView(camera))
    hass.http.register_view(CameraResourcesView(camera))
    hass.data[_VIEWS_REGISTERED_KEY] = True
