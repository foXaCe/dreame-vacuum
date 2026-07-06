"""Tests for the Dreame Vacuum camera HTTP views and setup orchestration.

``camera.py`` registers a handful of ``aiohttp``-based ``CameraView``/
``HomeAssistantView`` subclasses that stream map images, obstacle photos,
history and recovery data. These tests exercise ``handle()``/``get()``
directly with a mocked ``aiohttp.web.Request`` and a bare camera entity
(the entity's own coroutine methods are stubbed so we can pin down exactly
what the view does with the result: status codes, content types, gzip
encoding and headers).

They also cover ``async_update_map_cameras``/``async_remove_map_cameras``
(the per-saved-map entity add/remove orchestration invoked on every
coordinator refresh) using a stubbed ``DreameVacuumCameraEntity`` so the
tests stay focused on the orchestration logic rather than the heavyweight
entity constructor (which is exercised directly in ``test_camera.py``).

Native optional deps (``turbojpeg``, ``py_mini_racer``) are stubbed before
import, mirroring ``test_camera.py``.
"""

from __future__ import annotations

import gzip
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _install_native_stubs() -> None:
    if "turbojpeg" not in sys.modules:
        tj = types.ModuleType("turbojpeg")
        tj.TurboJPEG = type("TurboJPEG", (), {"__init__": lambda self, *a, **k: None})
        sys.modules["turbojpeg"] = tj
    if "py_mini_racer" not in sys.modules:
        pmr = types.ModuleType("py_mini_racer")
        pmr.MiniRacer = type("MiniRacer", (), {"__init__": lambda self, *a, **k: None})
        sys.modules["py_mini_racer"] = pmr


_install_native_stubs()

from aiohttp import web
from homeassistant.components.camera import DEFAULT_CONTENT_TYPE

import custom_components.dreame_vacuum.camera as cam
from custom_components.dreame_vacuum.camera import DreameVacuumCameraEntity
from custom_components.dreame_vacuum.camera_views import (
    JSON_CONTENT_TYPE,
    PNG_CONTENT_TYPE,
    CameraDataView,
    CameraHistoryView,
    CameraObstacleHistoryView,
    CameraObstacleView,
    CameraRecoveryView,
    CameraResourcesView,
    CameraWifiView,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class _ImmediateHass:
    """A minimal ``hass`` whose executor runs the job synchronously."""

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def _bare_camera() -> DreameVacuumCameraEntity:
    """Bare camera entity, mirroring the helper in test_camera.py."""
    entity = object.__new__(DreameVacuumCameraEntity)
    entity._segment_map_cache = (None, None, None)
    entity._should_poll = True
    entity._last_updated = -1
    entity._last_rendered = -1
    entity._last_map_request = 0
    entity._image = b"default-image"
    entity._calibration_points = None
    entity._color_scheme = "Dreame Light"
    entity.map_index = 0
    entity.hass = _ImmediateHass()
    entity.coordinator = MagicMock()
    entity.coordinator.device = None
    return entity


def _set_device(entity: DreameVacuumCameraEntity, device) -> None:
    entity.coordinator.device = device


def _mock_request(**query: str) -> MagicMock:
    """A minimal aiohttp request stand-in with a plain-dict ``query``."""
    request = MagicMock()
    request.query = query
    return request


# ===========================================================================
# CameraDataView
# ===========================================================================
class TestCameraDataView:
    async def test_serves_gzip_json_and_passes_resources_flag(self) -> None:
        entity = _bare_camera()
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "map_data_string", return_value='{"a":1}') as mds,
        ):
            view = CameraDataView(MagicMock())
            response = await view.handle(_mock_request(resources="1"), entity)

        assert response.status == 200
        assert response.content_type == JSON_CONTENT_TYPE
        assert response.headers["Content-Encoding"] == "gzip"
        assert gzip.decompress(response.body) == b'{"a":1}'
        mds.assert_called_once_with(True)

    async def test_resources_flag_defaults_false(self) -> None:
        entity = _bare_camera()
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "map_data_string", return_value="{}") as mds,
        ):
            view = CameraDataView(MagicMock())
            await view.handle(_mock_request(), entity)
        mds.assert_called_once_with(False)

    async def test_404_when_camera_serves_json_map_data(self) -> None:
        entity = _bare_camera()
        with patch.object(type(entity), "map_data_json", new=property(lambda self: True)):
            view = CameraDataView(MagicMock())
            with pytest.raises(web.HTTPNotFound):
                await view.handle(_mock_request(), entity)


# ===========================================================================
# CameraObstacleView
# ===========================================================================
class TestCameraObstacleView:
    async def test_serves_image_with_attachment_header(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        with patch.object(entity, "obstacle_image", AsyncMock(return_value=(b"IMGDATA", "cat.jpg"))) as oi:
            view = CameraObstacleView(MagicMock())
            response = await view.handle(_mock_request(index="3", file="1", box="0", crop="1"), entity)

        assert response.status == 200
        assert response.body == b"IMGDATA"
        assert response.content_type == DEFAULT_CONTENT_TYPE
        assert response.headers["Content-Disposition"] == 'attachment; filename="cat.jpg"'
        oi.assert_called_once_with("3", False, True)

    async def test_no_attachment_header_when_file_flag_absent(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        with patch.object(entity, "obstacle_image", AsyncMock(return_value=(b"IMGDATA", "cat.jpg"))):
            view = CameraObstacleView(MagicMock())
            response = await view.handle(_mock_request(index="1"), entity)
        assert "Content-Disposition" not in response.headers

    async def test_default_box_and_crop_true_when_absent(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        with patch.object(entity, "obstacle_image", AsyncMock(return_value=(b"D", "x.jpg"))) as oi:
            view = CameraObstacleView(MagicMock())
            await view.handle(_mock_request(), entity)
        oi.assert_called_once_with(1, True, True)

    async def test_404_when_map_index_not_zero(self) -> None:
        entity = _bare_camera()
        entity.map_index = 1
        with patch.object(entity, "obstacle_image", AsyncMock()) as oi:
            view = CameraObstacleView(MagicMock())
            with pytest.raises(web.HTTPNotFound):
                await view.handle(_mock_request(), entity)
        oi.assert_not_called()

    async def test_404_when_no_result(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        with patch.object(entity, "obstacle_image", AsyncMock(return_value=(None, None))):
            view = CameraObstacleView(MagicMock())
            with pytest.raises(web.HTTPNotFound):
                await view.handle(_mock_request(), entity)


# ===========================================================================
# CameraObstacleHistoryView
# ===========================================================================
class TestCameraObstacleHistoryView:
    async def test_serves_image_and_forwards_query_params(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        with patch.object(entity, "obstacle_history_image", AsyncMock(return_value=(b"HIST", "pet.jpeg"))) as ohi:
            view = CameraObstacleHistoryView(MagicMock())
            response = await view.handle(
                _mock_request(index="2", history_index="5", cruising="1", file="1", box="1", crop="0"), entity
            )

        assert response.body == b"HIST"
        assert response.headers["Content-Disposition"] == 'attachment; filename="pet.jpg"'
        ohi.assert_called_once_with("2", "5", True, True, False)

    async def test_404_when_map_index_not_zero(self) -> None:
        entity = _bare_camera()
        entity.map_index = 2
        with patch.object(entity, "obstacle_history_image", AsyncMock()) as ohi:
            view = CameraObstacleHistoryView(MagicMock())
            with pytest.raises(web.HTTPNotFound):
                await view.handle(_mock_request(), entity)
        ohi.assert_not_called()

    async def test_404_when_no_result(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        with patch.object(entity, "obstacle_history_image", AsyncMock(return_value=(None, None))):
            view = CameraObstacleHistoryView(MagicMock())
            with pytest.raises(web.HTTPNotFound):
                await view.handle(_mock_request(), entity)


# ===========================================================================
# CameraHistoryView
# ===========================================================================
class TestCameraHistoryView:
    async def test_serves_png_image(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "history_map_image", AsyncMock(return_value=b"PNGDATA")) as hmi,
        ):
            view = CameraHistoryView(MagicMock())
            response = await view.handle(_mock_request(index="4"), entity)

        assert response.body == b"PNGDATA"
        assert response.content_type == PNG_CONTENT_TYPE
        assert "Content-Encoding" not in response.headers
        hmi.assert_called_once_with("4", True, False, False, False, False)

    async def test_serves_gzip_json_when_data_flag_set(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "history_map_image", AsyncMock(return_value='{"h":1}')) as hmi,
        ):
            view = CameraHistoryView(MagicMock())
            response = await view.handle(_mock_request(data="1", resources="1"), entity)

        assert response.content_type == JSON_CONTENT_TYPE
        assert response.headers["Content-Encoding"] == "gzip"
        assert gzip.decompress(response.body) == b'{"h":1}'
        hmi.assert_called_once_with(1, True, False, True, False, True)

    async def test_404_when_json_map_camera(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        with patch.object(type(entity), "map_data_json", new=property(lambda self: True)):
            view = CameraHistoryView(MagicMock())
            with pytest.raises(web.HTTPNotFound):
                await view.handle(_mock_request(), entity)

    async def test_404_when_no_result(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "history_map_image", AsyncMock(return_value=None)),
        ):
            view = CameraHistoryView(MagicMock())
            with pytest.raises(web.HTTPNotFound):
                await view.handle(_mock_request(), entity)


# ===========================================================================
# CameraRecoveryView
# ===========================================================================
class TestCameraRecoveryView:
    async def test_file_branch_serves_tar_with_attachment_header(self) -> None:
        entity = _bare_camera()
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(
                entity,
                "recovery_map_file",
                AsyncMock(return_value=(b"TARDATA", "url", "maps/2024-01-01.mb.tbz2")),
            ) as rmf,
        ):
            view = CameraRecoveryView(MagicMock())
            response = await view.handle(_mock_request(index="2", file="1"), entity)

        assert response.body == b"TARDATA"
        assert response.content_type == "application/x-tar+gzip"
        assert response.headers["Content-Disposition"] == 'attachment; filename="maps-2024-01-01.mb.tbz2"'
        rmf.assert_called_once_with("2")

    async def test_png_branch(self) -> None:
        entity = _bare_camera()
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "recovery_map", AsyncMock(return_value=b"PNGDATA")) as rm,
        ):
            view = CameraRecoveryView(MagicMock())
            response = await view.handle(_mock_request(index="3"), entity)

        assert response.body == b"PNGDATA"
        assert response.content_type == PNG_CONTENT_TYPE
        assert "Content-Encoding" not in response.headers
        rm.assert_called_once_with("3", True, False, False)

    async def test_json_branch_gzip_encoded(self) -> None:
        entity = _bare_camera()
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "recovery_map", AsyncMock(return_value='{"r":1}')) as rm,
        ):
            view = CameraRecoveryView(MagicMock())
            response = await view.handle(_mock_request(data="1", resources="1"), entity)

        assert response.content_type == JSON_CONTENT_TYPE
        assert response.headers["Content-Encoding"] == "gzip"
        assert gzip.decompress(response.body) == b'{"r":1}'
        rm.assert_called_once_with(1, True, True, True)

    async def test_404_when_json_map_camera(self) -> None:
        entity = _bare_camera()
        with patch.object(type(entity), "map_data_json", new=property(lambda self: True)):
            view = CameraRecoveryView(MagicMock())
            with pytest.raises(web.HTTPNotFound):
                await view.handle(_mock_request(), entity)

    async def test_404_when_no_result(self) -> None:
        entity = _bare_camera()
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "recovery_map", AsyncMock(return_value=None)),
        ):
            view = CameraRecoveryView(MagicMock())
            with pytest.raises(web.HTTPNotFound):
                await view.handle(_mock_request(), entity)


# ===========================================================================
# CameraWifiView
# ===========================================================================
class TestCameraWifiView:
    async def test_png_branch(self) -> None:
        entity = _bare_camera()
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "wifi_map_data", AsyncMock(return_value=b"WIFIPNG")) as wmd,
        ):
            view = CameraWifiView(MagicMock())
            response = await view.handle(_mock_request(), entity)

        assert response.body == b"WIFIPNG"
        assert response.content_type == PNG_CONTENT_TYPE
        assert "Content-Encoding" not in response.headers
        wmd.assert_called_once_with(False, False)

    async def test_json_branch_gzip_encoded(self) -> None:
        entity = _bare_camera()
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "wifi_map_data", AsyncMock(return_value='{"w":1}')) as wmd,
        ):
            view = CameraWifiView(MagicMock())
            response = await view.handle(_mock_request(data="1", resources="1"), entity)

        assert response.content_type == JSON_CONTENT_TYPE
        assert response.headers["Content-Encoding"] == "gzip"
        assert gzip.decompress(response.body) == b'{"w":1}'
        wmd.assert_called_once_with(True, True)

    async def test_404_when_json_map_camera(self) -> None:
        entity = _bare_camera()
        with patch.object(type(entity), "map_data_json", new=property(lambda self: True)):
            view = CameraWifiView(MagicMock())
            with pytest.raises(web.HTTPNotFound):
                await view.handle(_mock_request(), entity)

    async def test_404_when_no_result(self) -> None:
        entity = _bare_camera()
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "wifi_map_data", AsyncMock(return_value=None)),
        ):
            view = CameraWifiView(MagicMock())
            with pytest.raises(web.HTTPNotFound):
                await view.handle(_mock_request(), entity)


# ===========================================================================
# CameraResourcesView (plain HomeAssistantView, not CameraView)
# ===========================================================================
class TestCameraResourcesView:
    async def test_serves_gzip_json_resources(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        _set_device(entity, device)
        component = MagicMock()
        component.get_entity.return_value = entity
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "resources", return_value='{"x":1}') as res,
        ):
            view = CameraResourcesView(component)
            response = await view.get(_mock_request(icon_set="dreame"), "camera.test")

        assert response.headers["Content-Encoding"] == "gzip"
        assert gzip.decompress(response.body) == b'{"x":1}'
        res.assert_called_once_with("dreame")

    async def test_404_when_entity_missing(self) -> None:
        component = MagicMock()
        component.get_entity.return_value = None
        view = CameraResourcesView(component)
        with pytest.raises(web.HTTPNotFound):
            await view.get(_mock_request(), "camera.missing")

    async def test_404_when_camera_serves_json_map_data(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        _set_device(entity, MagicMock())
        component = MagicMock()
        component.get_entity.return_value = entity
        with patch.object(type(entity), "map_data_json", new=property(lambda self: True)):
            view = CameraResourcesView(component)
            with pytest.raises(web.HTTPNotFound):
                await view.get(_mock_request(), "camera.test")

    async def test_404_when_map_index_not_zero(self) -> None:
        entity = _bare_camera()
        entity.map_index = 3
        _set_device(entity, MagicMock())
        component = MagicMock()
        component.get_entity.return_value = entity
        with patch.object(type(entity), "map_data_json", new=property(lambda self: False)):
            view = CameraResourcesView(component)
            with pytest.raises(web.HTTPNotFound):
                await view.get(_mock_request(), "camera.test")

    async def test_404_when_no_device(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        _set_device(entity, None)
        component = MagicMock()
        component.get_entity.return_value = entity
        with patch.object(type(entity), "map_data_json", new=property(lambda self: False)):
            view = CameraResourcesView(component)
            with pytest.raises(web.HTTPNotFound):
                await view.get(_mock_request(), "camera.test")


# ===========================================================================
# async_update_map_cameras / async_remove_map_cameras
# ===========================================================================
class TestAsyncUpdateMapCameras:
    def test_returns_immediately_when_no_device(self) -> None:
        coordinator = MagicMock()
        coordinator.device = None
        async_add_entities = MagicMock()
        current: dict = {}
        cam.async_update_map_cameras(coordinator, current, async_add_entities, None, None, [], False, False)
        async_add_entities.assert_not_called()
        assert current == {}

    def test_no_op_when_nothing_changed(self) -> None:
        coordinator = MagicMock()
        device = MagicMock()
        device.status.map_list = []
        coordinator.device = device
        async_add_entities = MagicMock()
        current: dict = {}
        cam.async_update_map_cameras(coordinator, current, async_add_entities, None, None, [], False, False)
        async_add_entities.assert_not_called()

    def test_removes_stale_map_indexes(self) -> None:
        coordinator = MagicMock()
        device = MagicMock()
        device.status.map_list = []  # no saved maps -> index 2 is now stale
        coordinator.device = device
        async_add_entities = MagicMock()
        current = {2: [MagicMock()]}
        with patch.object(cam, "async_remove_map_cameras") as remove_spy:
            cam.async_update_map_cameras(coordinator, current, async_add_entities, None, None, [], False, False)
        remove_spy.assert_called_once_with(2, coordinator, current)
        async_add_entities.assert_not_called()

    def test_adds_saved_map_and_wifi_map_when_capable(self) -> None:
        coordinator = MagicMock()
        device = MagicMock()
        device.status.map_list = [MagicMock()]  # one saved map -> index 1
        device.capability.wifi_map = True
        coordinator.device = device
        async_add_entities = MagicMock()
        current: dict = {}

        created_calls = []

        def factory(*args, **kwargs):
            created_calls.append(args)
            return MagicMock()

        with patch.object(cam, "DreameVacuumCameraEntity", side_effect=factory):
            cam.async_update_map_cameras(
                coordinator,
                current,
                async_add_entities,
                "Dreame Light",
                None,
                [],
                False,
                False,
                "en",
            )

        assert 1 in current
        assert len(current[1]) == 2  # saved_map + wifi_map
        descriptions = [call_args[1].key for call_args in created_calls]
        assert descriptions == ["saved_map", "wifi_map"]
        async_add_entities.assert_called_once()
        added = list(async_add_entities.call_args.args[0])
        assert added == current[1]

    def test_skips_wifi_map_when_not_capable(self) -> None:
        coordinator = MagicMock()
        device = MagicMock()
        device.status.map_list = [MagicMock()]
        device.capability.wifi_map = False
        coordinator.device = device
        async_add_entities = MagicMock()
        current: dict = {}

        with patch.object(cam, "DreameVacuumCameraEntity", side_effect=lambda *a, **k: MagicMock()):
            cam.async_update_map_cameras(coordinator, current, async_add_entities, None, None, [], False, False)

        assert len(current[1]) == 1

    def test_skips_wifi_map_when_low_resolution(self) -> None:
        coordinator = MagicMock()
        device = MagicMock()
        device.status.map_list = [MagicMock()]
        device.capability.wifi_map = True
        coordinator.device = device
        async_add_entities = MagicMock()
        current: dict = {}

        with patch.object(cam, "DreameVacuumCameraEntity", side_effect=lambda *a, **k: MagicMock()):
            cam.async_update_map_cameras(coordinator, current, async_add_entities, None, None, [], True, False)

        assert len(current[1]) == 1


class TestAsyncRemoveMapCameras:
    def test_removes_only_registered_entities(self) -> None:
        coordinator = MagicMock()
        registered_entity = SimpleNamespace(entity_id="camera.saved_1")
        unregistered_entity = SimpleNamespace(entity_id="camera.saved_1_wifi")
        current = {1: [registered_entity, unregistered_entity]}
        registry = MagicMock()
        registry.entities = {"camera.saved_1": MagicMock()}

        with patch.object(cam.entity_registry, "async_get", return_value=registry) as get_registry:
            cam.async_remove_map_cameras(1, coordinator, current)

        get_registry.assert_called_once_with(coordinator.hass)
        registry.async_remove.assert_called_once_with("camera.saved_1")
        assert 1 not in current

    def test_deletes_current_entry_even_when_nothing_registered(self) -> None:
        coordinator = MagicMock()
        current = {5: [SimpleNamespace(entity_id="camera.saved_5")]}
        registry = MagicMock()
        registry.entities = {}

        with patch.object(cam.entity_registry, "async_get", return_value=registry):
            cam.async_remove_map_cameras(5, coordinator, current)

        registry.async_remove.assert_not_called()
        assert 5 not in current
