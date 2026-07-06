"""Tests for the Dreame Vacuum camera platform logic.

``camera.py`` is dominated by image rendering (numpy + PIL) and aiohttp
HTTP views, neither of which is meaningfully unit-testable without a full
device/cloud pipeline. These tests target the *logic* instead:

* the pure query/filename helpers (header-injection sanitisation included),
* ``_build_segment_map`` and its cache driver ``_async_update_segment_map``
  (the recent pick-buffer fix) using small *real* numpy arrays,
* the read-only ``extra_state_attributes`` cache contract,
* ``async_camera_image``'s ``try/finally`` re-arming of ``_should_poll``,
* ``async_setup_entry`` entity creation + idempotent HTTP-view registration.

The HA ``camera`` component imports ``turbojpeg`` at module load and the
Dreame map optimizer imports ``py_mini_racer``; neither native wheel is
guaranteed in CI. We inject tiny stand-ins into ``sys.modules`` *before*
importing the platform so the rest of the module loads unchanged. numpy and
PIL are genuine dependencies and are used for real.
"""

from __future__ import annotations

import base64
from datetime import datetime
import io
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# --------------------------------------------------------------------------- #
# Native-dependency stand-ins (must be installed before importing camera.py).
# --------------------------------------------------------------------------- #
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

import numpy as np

import custom_components.dreame_vacuum.camera as cam
from custom_components.dreame_vacuum.camera import (
    CAMERAS,
    DreameVacuumCameraEntity,
    DreameVacuumMapType,
    _find_segment_at,
    async_setup_entry,
)
from custom_components.dreame_vacuum.camera_views import (
    _VIEWS_REGISTERED_KEY,
    _query_bool,
    _query_bool_default_true,
    _safe_filename,
)
from custom_components.dreame_vacuum.dreame.const import (
    ATTR_CALIBRATION,
    ATTR_ROOMS,
    ATTR_SEGMENT_ID,
    ATTR_SEGMENT_MAP,
)


# --------------------------------------------------------------------------- #
# Helpers for building bare entity instances and fake map data.
# --------------------------------------------------------------------------- #
class _ImmediateHass:
    """A minimal ``hass`` whose executor runs the job synchronously."""

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def _bare_camera() -> DreameVacuumCameraEntity:
    """Create a camera instance bypassing the heavyweight ``__init__``.

    ``__init__`` constructs real renderers and needs a live ``hass`` for entity
    id / token generation. The logic under test only touches a handful of
    attributes, so we set just those. ``device`` is a read-only property over
    ``coordinator.device``, so callers set the device via ``_set_device``.
    """
    entity = object.__new__(DreameVacuumCameraEntity)
    entity._segment_map_cache = (None, None, None)
    entity._attributes_cache = (None, None)
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
    """Assign the device behind the read-only ``device`` property."""
    entity.coordinator.device = device


def _fake_map_data(*, raw_at=(2, 2), raw_value=10, room_key=5, last_updated=1000):
    """Build a tiny ``map_data`` accepted by ``_build_segment_map``.

    The pixel_type is indexed ``pt[x, y]`` (shape ``(w, h)``), which is how the
    renderer and ``_find_segment_at`` read it.
    """
    w, h = 6, 5
    pt = np.zeros((w, h), dtype=np.uint8)
    pt[raw_at] = raw_value
    dims = SimpleNamespace(width=w, height=h, left=0, top=0, grid_size=1)
    seg = SimpleNamespace(x=float(raw_at[0]), y=float(raw_at[1]))
    return SimpleNamespace(
        pixel_type=pt,
        segments={room_key: seg},
        dimensions=dims,
        last_updated=last_updated,
    )


# ===========================================================================
# Pure helpers
# ===========================================================================
class TestQueryBool:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, False),
            ("", True),
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("0", False),
            ("false", False),
            ("no", False),
            ("anything", False),
        ],
    )
    def test_query_bool(self, value, expected) -> None:
        assert _query_bool(value) is expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, True),  # default-true: absent means True
            ("", True),
            ("true", True),
            ("1", True),
            ("0", False),
            ("false", False),
            ("nope", False),
        ],
    )
    def test_query_bool_default_true(self, value, expected) -> None:
        assert _query_bool_default_true(value) is expected


class TestSafeFilename:
    def test_plain_name_keeps_safe_chars(self) -> None:
        assert _safe_filename("My_File-1.jpg") == "My_File-1.jpg"

    def test_spaces_and_specials_replaced(self) -> None:
        assert _safe_filename("my file (1).jpg") == "my_file__1_.jpg"

    def test_none_returns_fallback(self) -> None:
        assert _safe_filename(None) == "image"

    def test_empty_returns_custom_fallback(self) -> None:
        assert _safe_filename("", "recovery") == "recovery"

    def test_only_dots_underscores_returns_fallback(self) -> None:
        # ``strip("._")`` empties the string -> fallback kicks in.
        assert _safe_filename("..__..") == "image"

    def test_header_injection_crlf_stripped(self) -> None:
        """CR/LF and the header separator must never survive into a header."""
        out = _safe_filename("evil\r\nSet-Cookie: pwned=1")
        assert "\r" not in out
        assert "\n" not in out
        assert ":" not in out
        assert " " not in out
        assert out == "evil__Set-Cookie__pwned_1"

    def test_truncated_to_80_chars(self) -> None:
        assert len(_safe_filename("a" * 250)) == 80

    def test_leading_trailing_dots_stripped(self) -> None:
        assert _safe_filename("...name...") == "name"


class TestFindSegmentAt:
    def test_direct_center_hit(self) -> None:
        pt = np.zeros((10, 10), dtype=np.uint8)
        pt[5, 5] = 7
        assert _find_segment_at(pt, 5, 5, 10, 10) == 7

    def test_spiral_finds_neighbour(self) -> None:
        pt = np.zeros((10, 10), dtype=np.uint8)
        pt[6, 5] = 3  # one ring out from (5,5)
        assert _find_segment_at(pt, 5, 5, 10, 10) == 3

    def test_background_returns_zero(self) -> None:
        pt = np.zeros((10, 10), dtype=np.uint8)
        assert _find_segment_at(pt, 5, 5, 10, 10) == 0

    def test_out_of_segment_range_ignored(self) -> None:
        # Values >= 64 (floor markers etc.) are not segments.
        pt = np.full((10, 10), 200, dtype=np.uint8)
        assert _find_segment_at(pt, 5, 5, 10, 10) == 0

    def test_radius_bound_respected(self) -> None:
        # Value sits outside the default search radius of 5 -> not found.
        pt = np.zeros((30, 30), dtype=np.uint8)
        pt[5 + 8, 5] = 12
        assert _find_segment_at(pt, 5, 5, 30, 30) == 0
        # ...but a wider radius reaches it.
        assert _find_segment_at(pt, 5, 5, 30, 30, radius=8) == 12

    def test_respects_image_bounds(self) -> None:
        # Centre at the corner: out-of-range neighbours are skipped, no IndexError.
        pt = np.zeros((10, 10), dtype=np.uint8)
        pt[0, 0] = 9
        assert _find_segment_at(pt, 0, 0, 10, 10) == 9


# ===========================================================================
# _build_segment_map (recent pick-buffer fix)
# ===========================================================================
class TestBuildSegmentMap:
    def test_returns_b64_png_and_room_mapping(self) -> None:
        entity = _bare_camera()
        map_data = _fake_map_data(raw_at=(2, 2), raw_value=10, room_key=5)

        result = entity._build_segment_map(map_data)
        assert result is not None
        b64, room_to_raw = result

        # The room key maps back to the raw pixel value sampled at its centre.
        assert room_to_raw == {5: 10}

        # Decodes to a valid RGB PNG of the declared dimensions.
        img_bytes = base64.b64decode(b64)
        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes))
        assert img.mode == "RGB"
        assert img.size == (6, 5)  # (width, height)

        # Exactly one blue-channel pixel carries the remapped room key (==5).
        arr = np.array(img)
        assert arr[:, :, 0].sum() == 0  # red unused
        assert arr[:, :, 1].sum() == 0  # green unused
        assert int((arr[:, :, 2] == 5).sum()) == 1
        assert int((arr[:, :, 2] > 0).sum()) == 1

    def test_remaps_raw_value_to_room_key_in_blue_channel(self) -> None:
        """Blue channel encodes the *room key*, not the raw pixel value."""
        entity = _bare_camera()
        # raw value 42 at centre, but the room key is 9.
        map_data = _fake_map_data(raw_at=(3, 1), raw_value=42, room_key=9)
        b64, room_to_raw = entity._build_segment_map(map_data)
        assert room_to_raw == {9: 42}

        from PIL import Image

        arr = np.array(Image.open(io.BytesIO(base64.b64decode(b64))))
        # The remapped value present in the buffer is the room key (9), never 42.
        present = set(np.unique(arr[:, :, 2]).tolist())
        assert 9 in present
        assert 42 not in present

    def test_none_when_pixel_type_missing(self) -> None:
        entity = _bare_camera()
        map_data = _fake_map_data()
        map_data.pixel_type = None
        assert entity._build_segment_map(map_data) is None

    def test_none_when_segments_empty(self) -> None:
        entity = _bare_camera()
        map_data = _fake_map_data()
        map_data.segments = {}
        assert entity._build_segment_map(map_data) is None

    def test_none_when_no_room_maps_to_a_raw_value(self) -> None:
        """A room whose centre lands on background (raw 0) is not mapped, so the
        buffer would be uniformly zero -> return None instead (contract 3.3: do
        not publish a degenerate all-zero segment_map)."""
        entity = _bare_camera()
        map_data = _fake_map_data(raw_at=(2, 2), raw_value=10, room_key=5)
        # Point the (only) segment at an empty cell far from the painted pixel.
        map_data.segments[5] = SimpleNamespace(x=0.0, y=0.0)
        # Re-zero the painted pixel so nothing is in range.
        map_data.pixel_type[2, 2] = 0
        assert entity._build_segment_map(map_data) is None

    def test_none_when_segment_has_no_coordinates(self) -> None:
        """The only segment has no centre -> nothing maps -> None (no all-zero buffer)."""
        entity = _bare_camera()
        map_data = _fake_map_data()
        map_data.segments = {5: SimpleNamespace(x=None, y=None)}
        assert entity._build_segment_map(map_data) is None

    def test_out_of_range_room_key_skipped(self) -> None:
        """Room keys must satisfy 0 < key < 256 to be remapped; the only key here
        is out of range so nothing maps -> None (no degenerate buffer)."""
        entity = _bare_camera()
        map_data = _fake_map_data(raw_at=(2, 2), raw_value=10, room_key=5)
        # Replace with an out-of-range key (>= 256).
        map_data.segments = {300: SimpleNamespace(x=2.0, y=2.0)}
        assert entity._build_segment_map(map_data) is None


# ===========================================================================
# _async_update_segment_map (recent fix: cache only on last_updated change)
# ===========================================================================
class TestAsyncUpdateSegmentMap:
    async def test_populates_cache_first_time(self) -> None:
        entity = _bare_camera()
        map_data = _fake_map_data(last_updated=1000)
        with (
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            await entity._async_update_segment_map()

        cache_key, b64, room_to_raw = entity._segment_map_cache
        # The structural key is a tuple of (shape, content-hash, segments-signature).
        assert isinstance(cache_key, tuple)
        assert isinstance(b64, str)
        assert b64
        assert room_to_raw == {5: 10}

    async def test_skips_when_structure_unchanged(self) -> None:
        """No rebuild when the pixel data and segment geometry are identical."""
        entity = _bare_camera()
        map_data = _fake_map_data(last_updated=1000)

        # First call: populate the cache with the real structural key.
        with (
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            await entity._async_update_segment_map()

        structural_key = entity._segment_map_cache[0]
        assert isinstance(structural_key, tuple)

        # Second call: same map_data (even if last_updated changed) → no rebuild.
        map_data.last_updated = 9999
        build_spy = MagicMock(wraps=entity._build_segment_map)
        with (
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(entity, "_build_segment_map", build_spy),
        ):
            await entity._async_update_segment_map()

        build_spy.assert_not_called()
        assert entity._segment_map_cache[0] == structural_key

    async def test_rebuilds_when_structure_changes(self) -> None:
        """Rebuild fires when pixel_type content changes, regardless of timestamp."""
        entity = _bare_camera()
        map_data = _fake_map_data(last_updated=1000, raw_value=10)
        with (
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            await entity._async_update_segment_map()

        first_key = entity._segment_map_cache[0]

        # Change a pixel — same timestamp, but different pixel_type content.
        map_data.pixel_type[2, 2] = 11
        with (
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            await entity._async_update_segment_map()

        cache_key, b64, room_to_raw = entity._segment_map_cache
        assert cache_key != first_key
        assert room_to_raw == {5: 11}

    async def test_skips_wifi_map(self) -> None:
        entity = _bare_camera()
        map_data = _fake_map_data()
        with (
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: True)),
        ):
            await entity._async_update_segment_map()
        # wifi_map short-circuits before touching the cache.
        assert entity._segment_map_cache == (None, None, None)

    async def test_skips_when_no_map_data(self) -> None:
        entity = _bare_camera()
        with (
            patch.object(type(entity), "_map_data", new=property(lambda self: None)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            await entity._async_update_segment_map()
        assert entity._segment_map_cache == (None, None, None)

    async def test_skips_when_segments_empty(self) -> None:
        entity = _bare_camera()
        map_data = _fake_map_data()
        map_data.segments = {}
        with (
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            await entity._async_update_segment_map()
        assert entity._segment_map_cache == (None, None, None)

    async def test_cache_unchanged_when_build_returns_none(self) -> None:
        """If the executor build yields None, the cache key is *not* advanced."""
        entity = _bare_camera()
        map_data = _fake_map_data(last_updated=3000)
        with (
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(entity, "_build_segment_map", return_value=None),
        ):
            await entity._async_update_segment_map()
        assert entity._segment_map_cache == (None, None, None)


# ===========================================================================
# async_camera_image (recent fix: try/finally re-arms _should_poll)
# ===========================================================================
class TestAsyncCameraImage:
    async def test_returns_cached_image(self) -> None:
        entity = _bare_camera()
        entity._should_poll = False  # not time to poll
        entity._image = b"the-image"
        result = await entity.async_camera_image()
        assert result == b"the-image"

    async def test_rearms_should_poll_on_success(self) -> None:
        entity = _bare_camera()
        entity._should_poll = True
        _set_device(entity, MagicMock())
        entity._renderer = MagicMock()
        entity._renderer.render_complete = True
        # last_updated == last_rendered so no re-render path is taken.
        entity._last_updated = -1
        entity._last_rendered = -1
        with (
            patch.object(entity, "update", MagicMock()),
            patch.object(entity, "_async_update_segment_map", AsyncMock()),
        ):
            await entity.async_camera_image()
        assert entity._should_poll is True

    async def test_rearms_should_poll_even_when_update_raises(self) -> None:
        """The try/finally must restore polling after a transient error."""
        entity = _bare_camera()
        entity._should_poll = True
        _set_device(entity, MagicMock())
        entity._renderer = MagicMock()

        def boom():
            raise RuntimeError("render pipeline blew up")

        with (
            patch.object(entity, "update", side_effect=boom),
            patch.object(entity, "_async_update_segment_map", AsyncMock()),
            pytest.raises(RuntimeError, match="render pipeline blew up"),
        ):
            await entity.async_camera_image()

        # Without the finally clause the camera would stop refreshing forever.
        assert entity._should_poll is True

    async def test_calls_update_map_for_live_camera(self) -> None:
        entity = _bare_camera()
        entity._should_poll = True
        entity.map_index = 0
        device = MagicMock()
        _set_device(entity, device)
        entity._renderer = MagicMock()
        entity._renderer.render_complete = True
        with (
            patch.object(entity, "update", MagicMock()),
            patch.object(entity, "_async_update_segment_map", AsyncMock()),
        ):
            await entity.async_camera_image()
        device.update_map.assert_called_once()

    async def test_renders_when_map_updated(self) -> None:
        entity = _bare_camera()
        entity._should_poll = True
        entity.map_index = 0
        device = MagicMock()
        _set_device(entity, device)
        entity._renderer = MagicMock()
        entity._renderer.render_complete = True
        entity._last_updated = 5000  # truthy and != last_rendered
        entity._last_rendered = 4000
        update_image = AsyncMock()
        with (
            patch.object(entity, "update", MagicMock()),
            patch.object(entity, "_async_update_segment_map", AsyncMock()),
            patch.object(type(entity), "_map_data", new=property(lambda self: MagicMock())),
            patch.object(entity, "_update_image", update_image),
        ):
            await entity.async_camera_image()
        update_image.assert_awaited_once()
        # After a successful render the rendered marker catches up.
        assert entity._last_rendered == 5000


# ===========================================================================
# extra_state_attributes: read-only cache contract
# ===========================================================================
class TestExtraStateAttributes:
    def _build_attr_entity(self, *, segments_present=True):
        entity = _bare_camera()
        entity.map_index = 0
        entity.access_tokens = ["tok-a", "tok-b"]
        entity.entity_id = "camera.test_map"
        # Renderer without a ``color_scheme`` attribute keeps the palette branch
        # out of the way; we only assert on the segment-map cache contract here.
        entity._renderer = MagicMock(spec=["calibration_points", "default_calibration_points"])
        entity._renderer.calibration_points = [{"x": 1}]

        map_data = SimpleNamespace(
            empty_map=False,
            pixel_type=np.zeros((4, 4), dtype=np.uint8) if segments_present else None,
            segments={5: SimpleNamespace(x=1.0, y=1.0)} if segments_present else {},
            last_updated=1000,
            obstacles=None,
            recovery_map_list=None,
            wifi_map_data=None,
        )
        map_data.as_dict = lambda: {ATTR_ROOMS: {5: {"name": "Kitchen"}}}

        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status.selected_map = None
        device.status._cleaning_history = None
        device.status._cruising_history = None
        _set_device(entity, device)
        return entity, map_data

    def test_returns_empty_when_no_device(self) -> None:
        entity = _bare_camera()
        _set_device(entity, None)
        assert entity.extra_state_attributes == {}

    def test_reads_segment_map_from_cache(self) -> None:
        entity, map_data = self._build_attr_entity()
        # Pre-seed the cache exactly as _async_update_segment_map would.
        entity._segment_map_cache = (1000, "BASE64PNG", {5: 42})

        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs = entity.extra_state_attributes

        # The property must *read* the cached PNG, never recompute it.
        assert attrs[ATTR_SEGMENT_MAP] == "BASE64PNG"
        # The raw pixel value is injected onto the room dict as ``segment_id``.
        assert attrs[ATTR_ROOMS][5][ATTR_SEGMENT_ID] == 42

    def test_no_segment_map_when_cache_empty(self) -> None:
        entity, map_data = self._build_attr_entity()
        entity._segment_map_cache = (None, None, None)  # nothing cached yet
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs = entity.extra_state_attributes
        assert ATTR_SEGMENT_MAP not in attrs
        # No room enrichment without a mapping.
        assert ATTR_SEGMENT_ID not in attrs[ATTR_ROOMS][5]

    def test_calibration_points_present(self) -> None:
        entity, map_data = self._build_attr_entity()
        entity._segment_map_cache = (None, None, None)
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs = entity.extra_state_attributes
        assert attrs[ATTR_CALIBRATION] == [{"x": 1}]

    def test_map_data_json_returns_none(self) -> None:
        """For the JSON-data camera the property returns ``None`` (no attrs)."""
        entity = _bare_camera()
        _set_device(entity, MagicMock())
        with patch.object(type(entity), "map_data_json", new=property(lambda self: True)):
            assert entity.extra_state_attributes is None

    def test_selected_flag_for_saved_map(self) -> None:
        """A saved-map camera reports whether it is the currently selected map."""
        entity = _bare_camera()
        entity.map_index = 2
        entity.access_tokens = ["t"]
        entity._renderer = MagicMock(spec=["calibration_points"])
        entity._renderer.calibration_points = []
        map_data = SimpleNamespace(
            empty_map=False,
            pixel_type=None,
            segments={},
            last_updated=1000,
            obstacles=None,
            recovery_map_list=None,
            wifi_map_data=None,
        )
        map_data.as_dict = dict
        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        selected = MagicMock()
        selected.map_index = 2
        device.status.selected_map = selected
        _set_device(entity, device)
        from custom_components.dreame_vacuum.dreame.const import ATTR_SELECTED

        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs = entity.extra_state_attributes
        assert attrs[ATTR_SELECTED] is True

    def test_color_palette_and_history_and_obstacles(self) -> None:
        """The current map exposes palette, history URLs and obstacle URLs."""
        from custom_components.dreame_vacuum.dreame.const import (
            ATTR_CLEANING_HISTORY_PICTURE,
            ATTR_COLOR_PALETTE,
            ATTR_CRUISING_HISTORY_PICTURE,
            ATTR_OBSTACLE_PICTURE,
            ATTR_RECOVERY_MAP_FILE,
            ATTR_RECOVERY_MAP_PICTURE,
            ATTR_ROOM_COLORS,
            ATTR_WIFI_MAP_PICTURE,
        )

        entity = _bare_camera()
        entity.map_index = 0
        entity.entity_id = "camera.test_map"
        entity.access_tokens = ["tok"]
        entity._segment_map_cache = (None, None, None)

        # Renderer that exposes a colour scheme so the palette branch runs.
        renderer = MagicMock(spec=["calibration_points", "color_scheme"])
        renderer.calibration_points = []
        # segment[i] == (border_rgba, fill_rgba); we read [1][:3] and [0][:3].
        renderer.color_scheme.segment = [
            ((10, 11, 12, 255), (20, 21, 22, 255)),
            ((30, 31, 32, 255), (40, 41, 42, 255)),
        ]
        entity._renderer = renderer

        # One room referencing color_index 1.
        rooms = {5: {"name": "Kitchen", "color_index": 1}}

        obstacle = MagicMock()
        obstacle.type.value = 1
        obstacle.type.name = "unknown_obstacle"
        obstacle.id = "obs-1"
        obstacle.possibility = 0
        obstacle.segment = None
        obstacle.ignore_status = None
        obstacle.picture_status = None

        recovery_entry = MagicMock()
        recovery_entry.date.timestamp.return_value = 1_600_000_000
        recovery_entry.map_type.name = "mopping"

        wifi_sub = SimpleNamespace(last_updated=1_600_000_500)

        map_data = SimpleNamespace(
            empty_map=False,
            pixel_type=None,
            segments={},
            last_updated=1_600_000_000,
            obstacles={9: obstacle},
            recovery_map_list=None,
            wifi_map_data=None,
        )
        map_data.as_dict = lambda: {ATTR_ROOMS: dict(rooms)}

        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status._cleaning_history = None
        device.status._cruising_history = None
        device.status.ai_pet_detection = 1
        device.status.ai_fluid_detection = True
        device.capability.fluid_detection = False
        selected = MagicMock()
        selected.recovery_map_list = [recovery_entry]
        selected.wifi_map_data = wifi_sub
        device.status.selected_map = selected
        _set_device(entity, device)

        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs = entity.extra_state_attributes

        # Palette: index -> RGB list.
        assert attrs[ATTR_COLOR_PALETTE][1] == [40, 41, 42]
        # Room colour resolved from its color_index.
        assert attrs[ATTR_ROOMS][5]["color"] == [40, 41, 42]
        assert attrs[ATTR_ROOM_COLORS]["5"] == [30, 31, 32]
        # History dicts present (empty since histories are None).
        assert ATTR_CLEANING_HISTORY_PICTURE not in attrs  # _cleaning_history is None
        assert ATTR_CRUISING_HISTORY_PICTURE not in attrs
        # Obstacle URL built and points at the right proxy.
        obstacle_urls = attrs[ATTR_OBSTACLE_PICTURE]
        assert len(obstacle_urls) == 1
        assert "/api/camera_map_obstacle_proxy/camera.test_map" in next(iter(obstacle_urls.values()))
        # Recovery map + file URLs.
        assert len(attrs[ATTR_RECOVERY_MAP_PICTURE]) == 1
        recovery_url = next(iter(attrs[ATTR_RECOVERY_MAP_PICTURE].values()))
        assert "/api/camera_recovery_map_proxy/camera.test_map" in recovery_url
        assert next(iter(attrs[ATTR_RECOVERY_MAP_FILE].values())).endswith("&file=1")
        # Wifi map picture URL.
        assert "/api/camera_wifi_map_proxy/camera.test_map" in attrs[ATTR_WIFI_MAP_PICTURE]

    def test_obstacle_filtered_out_when_picture_pending(self) -> None:
        """Obstacles whose picture is not ready (status != 2) are dropped."""
        from custom_components.dreame_vacuum.dreame.const import ATTR_OBSTACLE_PICTURE

        entity = _bare_camera()
        entity.map_index = 0
        entity.entity_id = "camera.test_map"
        entity.access_tokens = ["tok"]
        entity._segment_map_cache = (None, None, None)
        entity._renderer = MagicMock(spec=["calibration_points"])
        entity._renderer.calibration_points = []

        obstacle = MagicMock()
        obstacle.type.value = 1
        obstacle.picture_status = MagicMock()
        obstacle.picture_status.value = 1  # not 2 -> filtered

        map_data = SimpleNamespace(
            empty_map=False,
            pixel_type=None,
            segments={},
            last_updated=1000,
            obstacles={9: obstacle},
            recovery_map_list=None,
            wifi_map_data=None,
        )
        map_data.as_dict = dict

        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status._cleaning_history = None
        device.status._cruising_history = None
        device.status.ai_pet_detection = 1
        device.capability.fluid_detection = False
        device.status.selected_map = None
        _set_device(entity, device)

        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs = entity.extra_state_attributes
        assert attrs[ATTR_OBSTACLE_PICTURE] == {}

    def test_default_calibration_when_map_unavailable(self) -> None:
        """Cloud connected but no usable map -> only default calibration points."""
        entity = _bare_camera()
        entity.map_index = 0
        entity.access_tokens = ["tok"]
        entity._renderer = MagicMock(spec=["default_calibration_points", "calibration_points"])
        entity._renderer.default_calibration_points = [{"d": 1}]
        device = MagicMock()
        device.cloud_connected = True
        device.status.located = False  # not located -> map block skipped
        device.status._cleaning_history = None
        device.status._cruising_history = None
        device.status.selected_map = None
        _set_device(entity, device)
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: None)),
        ):
            attrs = entity.extra_state_attributes
        assert attrs[ATTR_CALIBRATION] == [{"d": 1}]


# ===========================================================================
# Simple properties / state
# ===========================================================================
class TestProperties:
    def test_state_returns_internal_state(self) -> None:
        entity = _bare_camera()
        entity._state = "some-state"
        assert entity.state == "some-state"

    def test_available_always_true(self) -> None:
        # The camera overrides the base entity to stay available so the map
        # stays renderable even while the cloud is briefly down.
        entity = _bare_camera()
        assert entity.available is True

    def test_frame_interval_constant(self) -> None:
        assert _bare_camera().frame_interval == 0.25

    def test_entity_picture_embeds_token_and_version(self) -> None:
        entity = _bare_camera()
        entity.entity_id = "camera.test_map"
        entity.access_tokens = ["old", "current-token"]
        map_data = SimpleNamespace(last_updated=1717)
        with patch.object(type(entity), "_map_data", new=property(lambda self: map_data)):
            url = entity.entity_picture
        assert url == "/api/camera_proxy/camera.test_map?token=current-token&v=1717"

    def test_entity_picture_without_map_data_uses_zero_version(self) -> None:
        entity = _bare_camera()
        entity.entity_id = "camera.test_map"
        entity.access_tokens = ["old", "current-token"]
        with patch.object(type(entity), "_map_data", new=property(lambda self: None)):
            url = entity.entity_picture
        assert url.endswith("v=0")

    def test_wifi_map_flag(self) -> None:
        entity = _bare_camera()
        entity.entity_description = SimpleNamespace(map_type=DreameVacuumMapType.WIFI_MAP)
        assert entity.wifi_map is True
        entity.entity_description = SimpleNamespace(map_type=DreameVacuumMapType.FLOOR_MAP)
        assert entity.wifi_map is False

    def test_map_data_json_flag(self) -> None:
        entity = _bare_camera()
        entity.entity_description = SimpleNamespace(map_type=DreameVacuumMapType.JSON_MAP_DATA)
        assert entity.map_data_json is True
        entity.entity_description = SimpleNamespace(map_type=DreameVacuumMapType.FLOOR_MAP)
        assert entity.map_data_json is False


# ===========================================================================
# _map_data / _default_map_image source properties
# ===========================================================================
class TestMapDataProperty:
    def test_map_data_none_without_device(self) -> None:
        entity = _bare_camera()
        _set_device(entity, None)
        assert entity._map_data is None

    def test_map_data_returns_device_map(self) -> None:
        entity = _bare_camera()
        entity.map_index = 2
        device = MagicMock()
        raw_map = SimpleNamespace(map_id=7)
        device.get_map.return_value = raw_map
        _set_device(entity, device)
        with patch.object(type(entity), "wifi_map", new=property(lambda self: False)):
            assert entity._map_data is raw_map
        device.get_map.assert_called_once_with(2)

    def test_map_data_returns_wifi_submap(self) -> None:
        entity = _bare_camera()
        device = MagicMock()
        wifi_sub = SimpleNamespace(name="wifi")
        device.get_map.return_value = SimpleNamespace(wifi_map_data=wifi_sub)
        _set_device(entity, device)
        with patch.object(type(entity), "wifi_map", new=property(lambda self: True)):
            assert entity._map_data is wifi_sub

    def test_default_map_image_disconnected(self) -> None:
        entity = _bare_camera()
        entity._image = b"some-rendered-image"
        renderer = MagicMock()
        renderer.disconnected_map_image = b"DISCONNECTED"
        renderer.default_map_image = b"DEFAULT"
        entity._renderer = renderer
        device = MagicMock()
        device.cloud_connected = False
        _set_device(entity, device)
        # Cloud down + we already have an image -> show the disconnected banner.
        assert entity._default_map_image == b"DISCONNECTED"

    def test_default_map_image_connected_falls_back_to_default(self) -> None:
        entity = _bare_camera()
        entity._image = b"some-rendered-image"
        renderer = MagicMock()
        renderer.disconnected_map_image = b"DISCONNECTED"
        renderer.default_map_image = b"DEFAULT"
        entity._renderer = renderer
        device = MagicMock()
        device.cloud_connected = True
        _set_device(entity, device)
        assert entity._default_map_image == b"DEFAULT"


# ===========================================================================
# update() state machine
# ===========================================================================
class TestUpdate:
    def test_sets_state_from_last_updated(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        entity._default_map = True
        entity._last_updated = -1
        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status.active = True
        _set_device(entity, device)
        map_data = SimpleNamespace(last_updated=1_600_000_000, timestamp_ms=None, frame_id=3)
        with patch.object(type(entity), "_map_data", new=property(lambda self: map_data)):
            entity.update()
        # last_updated advanced and we left the default-map state.
        assert entity._last_updated == 1_600_000_000
        assert entity._frame_id == 3
        assert entity._default_map is False
        assert isinstance(entity._state, datetime)

    def test_falls_back_to_default_when_disconnected(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        entity._default_map = False  # was showing a live map
        entity._renderer = MagicMock()
        entity._renderer.default_map_image = b"DEFAULT"
        entity._renderer.disconnected_map_image = b"DISCONNECTED"
        device = MagicMock()
        device.cloud_connected = False
        device.status.located = True
        _set_device(entity, device)
        with patch.object(type(entity), "_map_data", new=property(lambda self: None)):
            entity.update()
        assert entity._state == cam.STATE_UNAVAILABLE
        assert entity._default_map is True
        assert entity._last_updated == -1
        assert entity._frame_id == -1


# ===========================================================================
# _handle_coordinator_update state machine
# ===========================================================================
class TestHandleCoordinatorUpdate:
    def test_no_device_just_writes_state(self) -> None:
        entity = _bare_camera()
        _set_device(entity, None)
        with (
            patch.object(entity, "async_write_ha_state", MagicMock()) as write,
            patch.object(entity, "update", MagicMock()) as upd,
        ):
            entity._handle_coordinator_update()
        write.assert_called_once()
        upd.assert_not_called()

    def test_disconnected_marks_unavailable(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        device.cloud_connected = False
        device.status.located = True
        _set_device(entity, device)
        with (
            patch.object(entity, "async_write_ha_state", MagicMock()),
            patch.object(entity, "update", MagicMock()) as upd,
            patch.object(type(entity), "_map_data", new=property(lambda self: None)),
        ):
            entity._handle_coordinator_update()
        upd.assert_called_once()
        assert entity._state == cam.STATE_UNAVAILABLE
        assert entity._last_map_request == 0

    def test_live_map_update_refreshes_state(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        entity._default_map = True  # forces the update() call path
        entity._frame_id = -1
        entity._last_updated = -1
        entity._device_active = None
        entity._error = None
        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status.active = True
        device.status.error = 0
        _set_device(entity, device)
        map_data = SimpleNamespace(
            last_updated=1_600_000_000,
            timestamp_ms=None,
            frame_id=4,
            custom_name=None,
            map_id=1,
        )
        with (
            patch.object(entity, "async_write_ha_state", MagicMock()) as write,
            patch.object(entity, "update", MagicMock()) as upd,
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            entity._handle_coordinator_update()
        upd.assert_called_once()
        write.assert_called_once()
        assert isinstance(entity._state, datetime)
        assert entity._frame_id == 4
        # active/error snapshots refreshed.
        assert entity._device_active is True
        assert entity._error == 0

    def test_saved_map_name_change_triggers_rename(self) -> None:
        entity = _bare_camera()
        entity.map_index = 2
        entity._default_map = False
        entity._map_name = "Old"
        entity._map_id = 1
        entity._frame_id = 7
        entity._last_updated = 1_600_000_000
        entity._device_active = False
        entity._error = 0
        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status.active = False
        device.status.error = 0
        _set_device(entity, device)
        map_data = SimpleNamespace(
            last_updated=1_600_000_000,
            timestamp_ms=None,
            frame_id=7,
            custom_name="New Name",
            map_id=1,
        )
        with (
            patch.object(entity, "async_write_ha_state", MagicMock()),
            patch.object(entity, "update", MagicMock()),
            patch.object(entity, "_set_map_name", MagicMock()) as set_name,
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            entity._handle_coordinator_update()
        assert entity._map_name == "New Name"
        set_name.assert_called_once_with(False)


# ===========================================================================
# Lifecycle helpers
# ===========================================================================
class TestLifecycle:
    async def test_async_update_resets_frame_and_last_updated(self) -> None:
        entity = _bare_camera()
        entity._frame_id = 99
        entity._last_updated = 1234
        with patch.object(entity, "update", MagicMock()) as upd:
            await entity.async_update()
        assert entity._frame_id is None
        assert entity._last_updated is None
        upd.assert_called_once()

    async def test_async_will_remove_drops_renderer_refs(self) -> None:
        entity = _bare_camera()
        entity._renderer = MagicMock()
        entity._proxy_renderer = MagicMock()
        await entity.async_will_remove_from_hass()
        assert entity._renderer is None
        assert entity._proxy_renderer is None


# ===========================================================================
# async_update_token throttling
# ===========================================================================
class TestTokenThrottle:
    def test_first_call_updates_token(self) -> None:
        entity = _bare_camera()
        entity._access_token_update_counter = 0
        with patch("homeassistant.components.camera.Camera.async_update_token") as super_update:
            entity.async_update_token()
        # Counter starts at 0 -> token refresh happens and counter resets to 1.
        assert entity._access_token_update_counter == 1
        super_update.assert_called_once()

    def test_intermediate_calls_only_increment(self) -> None:
        entity = _bare_camera()
        entity._access_token_update_counter = 1
        with patch("homeassistant.components.camera.Camera.async_update_token") as super_update:
            entity.async_update_token()
        # Below the threshold -> only the counter moves, no super() refresh.
        assert entity._access_token_update_counter == 2
        super_update.assert_not_called()

    def test_threshold_triggers_refresh_and_reset(self) -> None:
        from homeassistant.components.camera import TOKEN_CHANGE_INTERVAL

        from custom_components.dreame_vacuum.camera import DREAME_TOKEN_CHANGE_INTERVAL

        threshold = int(DREAME_TOKEN_CHANGE_INTERVAL.total_seconds() / TOKEN_CHANGE_INTERVAL.total_seconds())
        entity = _bare_camera()
        # One step before exceeding the window.
        entity._access_token_update_counter = threshold
        with patch("homeassistant.components.camera.Camera.async_update_token") as super_update:
            entity.async_update_token()
        # Counter would become threshold+1 (> threshold) -> refresh + reset to 1.
        assert entity._access_token_update_counter == 1
        super_update.assert_called_once()


# ===========================================================================
# CAMERAS descriptor table
# ===========================================================================
def test_cameras_table_shape() -> None:
    keys = {c.key for c in CAMERAS}
    assert keys == {"map", "map_data"}
    map_data_desc = next(c for c in CAMERAS if c.key == "map_data")
    assert map_data_desc.map_type == DreameVacuumMapType.JSON_MAP_DATA.value


# ===========================================================================
# async_setup_entry: entity creation + idempotent HTTP-view registration
# ===========================================================================
def _setup_entry_mocks(*, views_already_registered=False, capability_map=True):
    """Build (hass, entry, async_add_entities, register_view_spy)."""
    device = MagicMock()
    device.capability.map = capability_map
    device.capability.wifi_map = False
    device.capability.robot_type = 0
    device.status.map_list = []  # no saved maps -> only the two base cameras

    coordinator = MagicMock()
    coordinator.device = device
    coordinator._shared_proxy_renderer = None

    entry = MagicMock()
    entry.runtime_data.coordinator = coordinator
    entry.options = {}

    hass = MagicMock()
    hass.config.language = "en"
    data = {"camera": MagicMock()}
    if views_already_registered:
        data[_VIEWS_REGISTERED_KEY] = True
    hass.data = data

    async_add_entities = MagicMock()
    return hass, entry, async_add_entities, coordinator


class TestAsyncSetupEntry:
    async def test_skips_when_no_map_capability(self) -> None:
        hass, entry, async_add_entities, _ = _setup_entry_mocks(capability_map=False)
        await async_setup_entry(hass, entry, async_add_entities)
        async_add_entities.assert_not_called()
        hass.http.register_view.assert_not_called()

    async def test_creates_cameras_and_registers_views(self) -> None:
        hass, entry, async_add_entities, coordinator = _setup_entry_mocks()

        await async_setup_entry(hass, entry, async_add_entities)

        # The two base map cameras are added (generator consumed by add_entities).
        assert async_add_entities.call_count >= 1
        first_added = list(async_add_entities.call_args_list[0].args[0])
        assert len(first_added) == 2
        assert all(isinstance(e, DreameVacuumCameraEntity) for e in first_added)

        # All seven HTTP views registered exactly once, flag set.
        assert hass.http.register_view.call_count == 7
        assert hass.data[_VIEWS_REGISTERED_KEY] is True

        coordinator.async_add_listener.assert_called_once()

    async def test_views_not_reregistered_when_flag_set(self) -> None:
        hass, entry, async_add_entities, _ = _setup_entry_mocks(views_already_registered=True)

        await async_setup_entry(hass, entry, async_add_entities)

        # Idempotent: views already registered -> register_view is never called.
        hass.http.register_view.assert_not_called()


# ===========================================================================
# _set_map_name (direct unit tests)
# ===========================================================================
class TestSetMapNameDirect:
    def test_indexed_when_no_custom_name(self) -> None:
        entity = _bare_camera()
        entity.map_index = 3
        entity._map_name = None
        entity._set_map_name(False)
        assert entity._attr_translation_key == "saved_map_indexed"
        assert entity._attr_translation_placeholders == {"index": "3"}

    def test_named_capitalizes_and_replaces_separators(self) -> None:
        entity = _bare_camera()
        entity._map_name = "kitchen_dining-room"
        entity._set_map_name(False)
        assert entity._attr_translation_key == "saved_map_named"
        assert entity._attr_translation_placeholders == {"map_name": "Kitchen dining room"}

    def test_wifi_prefix_used_when_wifi_map(self) -> None:
        entity = _bare_camera()
        entity._map_name = None
        entity.map_index = 1
        entity._set_map_name(True)
        assert entity._attr_translation_key == "saved_wifi_map_indexed"
        assert entity._attr_translation_placeholders == {"index": "1"}

    def test_wifi_named_prefix(self) -> None:
        entity = _bare_camera()
        entity._map_name = "office"
        entity._set_map_name(True)
        assert entity._attr_translation_key == "saved_wifi_map_named"
        assert entity._attr_translation_placeholders == {"map_name": "Office"}


# ===========================================================================
# __init__ branches: wifi_map objects exclusion, map_index/map_data
# combinations, translation_key selection for the "current map" entities.
# ===========================================================================
def _init_coordinator(*, wifi_capability: bool = True):
    """Build a coordinator/device pair sufficient for a real __init__ call."""
    device = MagicMock()
    device.capability.map = True
    device.capability.wifi_map = wifi_capability
    device.capability.robot_type = 0
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.name = "Vacuum"
    device.cloud_connected = True
    coordinator = MagicMock()
    coordinator.device = device
    coordinator._shared_proxy_renderer = None
    coordinator.hass = MagicMock()
    coordinator.hass.config.language = "en"
    return coordinator, device


class TestInitConstruction:
    def test_saved_map_with_existing_data_uses_custom_name(self) -> None:
        coordinator, device = _init_coordinator()
        map_data = SimpleNamespace(
            map_id=42, custom_name="Kitchen Room", last_updated=1000, timestamp_ms=None, frame_id=3
        )
        device.get_map.return_value = map_data
        desc = cam.DreameVacuumCameraEntityDescription(key="saved_map", icon="mdi:map-search")
        entity = DreameVacuumCameraEntity(coordinator, desc, "Dreame Light", None, [], False, False, 1, "en")
        assert entity._map_name == "Kitchen Room"
        assert entity._attr_translation_key == "saved_map_named"
        assert entity._attr_unique_id == "AA:BB:CC:DD:EE:FF_map_1"
        assert entity.entity_id.startswith("camera.")

    def test_saved_map_without_data_defaults_to_indexed_name(self) -> None:
        coordinator, device = _init_coordinator()
        device.get_map.return_value = None
        desc = cam.DreameVacuumCameraEntityDescription(key="saved_map", icon="mdi:map-search")
        entity = DreameVacuumCameraEntity(coordinator, desc, "Dreame Light", None, [], False, False, 2, "en")
        assert entity._map_name is None
        assert entity._attr_translation_key == "saved_map_indexed"
        assert entity._attr_translation_placeholders == {"index": "2"}

    def test_wifi_map_excludes_charger_and_skips_proxy_renderer(self) -> None:
        coordinator, device = _init_coordinator()
        device.get_map.return_value = None
        desc = cam.DreameVacuumCameraEntityDescription(
            key="wifi_map", icon="mdi:wifi-settings", map_type=DreameVacuumMapType.WIFI_MAP
        )
        entity = DreameVacuumCameraEntity(coordinator, desc, "Dreame Light", None, [], True, False, 1, "en")
        assert entity.wifi_map is True
        # The shared proxy renderer is only built for the non-wifi variant.
        assert entity._proxy_renderer is None
        assert entity._attr_unique_id == "AA:BB:CC:DD:EE:FF_wifi_map_1"

    def test_current_wifi_map_uses_translation_key(self) -> None:
        coordinator, device = _init_coordinator()
        wifi_sub = SimpleNamespace(map_id=1, custom_name=None, last_updated=0, timestamp_ms=None, frame_id=0)
        device.get_map.return_value = SimpleNamespace(wifi_map_data=wifi_sub)
        desc = cam.DreameVacuumCameraEntityDescription(key="map", icon="mdi:map", map_type=DreameVacuumMapType.WIFI_MAP)
        entity = DreameVacuumCameraEntity(coordinator, desc, "Dreame Light", None, [], True, False, 0, "en")
        assert entity._attr_translation_key == "current_wifi_map"

    def test_current_floor_map_uses_translation_key(self) -> None:
        coordinator, device = _init_coordinator()
        device.get_map.return_value = None
        device.status.located = False
        desc = cam.DreameVacuumCameraEntityDescription(key="map", icon="mdi:map")
        entity = DreameVacuumCameraEntity(coordinator, desc, "Dreame Light", None, [], False, False, 0, "en")
        assert entity._attr_translation_key == "current_map"

    def test_construction_leaves_image_none_for_map_index_zero(self) -> None:
        """The default map image is no longer decoded on the event loop at construction.

        It used to be read eagerly here; it is now warmed lazily in
        ``async_added_to_hass`` (see TestAsyncAddedToHass below).
        """
        coordinator, device = _init_coordinator()
        device.get_map.return_value = None
        device.status.located = False
        desc = cam.DreameVacuumCameraEntityDescription(key="map", icon="mdi:map")
        entity = DreameVacuumCameraEntity(coordinator, desc, "Dreame Light", None, [], False, False, 0, "en")
        assert entity._image is None

    def test_construction_never_calls_pil_image_open(self) -> None:
        """No PIL decode (icon warm-up or default-image render) may run at construction time."""
        coordinator, device = _init_coordinator()
        device.get_map.return_value = None
        device.status.located = False
        desc = cam.DreameVacuumCameraEntityDescription(key="map", icon="mdi:map")
        from PIL import Image

        with patch.object(Image, "open", wraps=Image.open) as spy:
            DreameVacuumCameraEntity(coordinator, desc, "Dreame Light", None, [], False, False, 0, "en")
        spy.assert_not_called()


# ===========================================================================
# async_added_to_hass: off-loop warm-up of the default/disconnected images
# ===========================================================================
class TestAsyncAddedToHass:
    @staticmethod
    def _entity_with_mock_renderer(*, map_index: int = 0, map_data_json: bool = False) -> DreameVacuumCameraEntity:
        entity = _bare_camera()
        entity.map_index = map_index
        entity._image = None
        entity._renderer = MagicMock()
        entity._renderer.default_map_image = b"DEFAULT"
        entity._renderer.disconnected_map_image = b"DISCONNECTED"
        if map_data_json:
            entity.entity_description = SimpleNamespace(map_type=DreameVacuumMapType.JSON_MAP_DATA)
        else:
            entity.entity_description = SimpleNamespace(map_type=None)
        return entity

    async def test_warms_both_images_and_sets_image_for_map_index_zero(self) -> None:
        entity = self._entity_with_mock_renderer(map_index=0)
        with (
            patch.object(cam.DreameVacuumEntity, "async_added_to_hass", AsyncMock(), create=True),
            patch.object(entity, "async_write_ha_state", MagicMock()) as write_state,
        ):
            await entity.async_added_to_hass()
        # Both lazy image caches were touched (loop-side reads now hit the cache).
        assert entity._renderer.disconnected_map_image == b"DISCONNECTED"
        assert entity._renderer.default_map_image == b"DEFAULT"
        assert entity._image == b"DEFAULT"
        write_state.assert_called_once()

    async def test_does_not_overwrite_existing_image(self) -> None:
        entity = self._entity_with_mock_renderer(map_index=0)
        entity._image = b"ALREADY-SET"
        with (
            patch.object(cam.DreameVacuumEntity, "async_added_to_hass", AsyncMock(), create=True),
            patch.object(entity, "async_write_ha_state", MagicMock()) as write_state,
        ):
            await entity.async_added_to_hass()
        assert entity._image == b"ALREADY-SET"
        write_state.assert_not_called()

    async def test_non_zero_map_index_warms_but_does_not_set_image(self) -> None:
        entity = self._entity_with_mock_renderer(map_index=2)
        with (
            patch.object(cam.DreameVacuumEntity, "async_added_to_hass", AsyncMock(), create=True),
            patch.object(entity, "async_write_ha_state", MagicMock()) as write_state,
        ):
            await entity.async_added_to_hass()
        assert entity._image is None
        write_state.assert_not_called()

    async def test_json_map_data_entity_skips_warm_up(self) -> None:
        entity = self._entity_with_mock_renderer(map_index=0, map_data_json=True)
        with (
            patch.object(cam.DreameVacuumEntity, "async_added_to_hass", AsyncMock(), create=True),
            patch.object(entity, "async_write_ha_state", MagicMock()) as write_state,
            patch.object(entity.hass, "async_add_executor_job", AsyncMock()) as exec_job,
        ):
            await entity.async_added_to_hass()
        exec_job.assert_not_called()
        assert entity._image is None
        write_state.assert_not_called()


# ===========================================================================
# _handle_coordinator_update: remaining timestamp/error/map-id branches
# ===========================================================================
class TestHandleCoordinatorUpdateBranches:
    def test_falls_back_to_timestamp_ms_when_last_updated_missing(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        entity._default_map = True
        entity._device_active = None
        entity._error = None
        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status.active = True
        device.status.error = 0
        _set_device(entity, device)
        map_data = SimpleNamespace(last_updated=0, timestamp_ms=5_000_000, frame_id=1)
        with (
            patch.object(entity, "async_write_ha_state", MagicMock()),
            patch.object(entity, "update", MagicMock()),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            entity._handle_coordinator_update()
        assert entity._state == datetime.fromtimestamp(5000)

    def test_falls_back_to_now_when_no_timestamps(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        entity._default_map = True
        entity._device_active = None
        entity._error = None
        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status.active = True
        device.status.error = 0
        _set_device(entity, device)
        map_data = SimpleNamespace(last_updated=0, timestamp_ms=0, frame_id=1)
        before = datetime.now()
        with (
            patch.object(entity, "async_write_ha_state", MagicMock()),
            patch.object(entity, "update", MagicMock()),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            entity._handle_coordinator_update()
        assert isinstance(entity._state, datetime)
        assert entity._state >= before

    def test_map_id_change_resets_frame_tracking(self) -> None:
        entity = _bare_camera()
        entity.map_index = 2
        entity._default_map = False
        entity._map_id = 1
        entity._map_name = "Old"
        entity._frame_id = 7
        entity._last_updated = 1_600_000_000
        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status.active = False
        device.status.error = 0
        _set_device(entity, device)
        map_data = SimpleNamespace(
            last_updated=1_600_000_000,
            timestamp_ms=None,
            frame_id=7,
            custom_name="Old",
            map_id=99,  # different map_id -> resets frame tracking
        )
        with (
            patch.object(entity, "async_write_ha_state", MagicMock()),
            patch.object(entity, "update", MagicMock()) as upd,
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            entity._handle_coordinator_update()
        assert entity._map_id == 99
        # update() is called because _frame_id/_last_updated were reset to None.
        upd.assert_called_once()

    def test_error_change_without_frame_change_still_updates(self) -> None:
        """The ``elif`` branch: frame/last_updated unchanged but error/active did."""
        entity = _bare_camera()
        entity.map_index = 0
        entity._default_map = False
        entity._frame_id = 4
        entity._last_updated = 1_600_000_000
        entity._device_active = True
        entity._error = 0
        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status.active = True
        device.status.error = 5  # changed from 0 -> 5
        _set_device(entity, device)
        map_data = SimpleNamespace(
            last_updated=1_600_000_000,  # unchanged
            timestamp_ms=None,
            frame_id=4,  # unchanged
            custom_name=None,
            map_id=None,
        )
        with (
            patch.object(entity, "async_write_ha_state", MagicMock()),
            patch.object(entity, "update", MagicMock()) as upd,
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            entity._handle_coordinator_update()
        upd.assert_called_once()


# ===========================================================================
# update(): timestamp_ms fallback branch
# ===========================================================================
class TestUpdateTimestampFallback:
    def test_uses_timestamp_ms_when_last_updated_falsy(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status.active = True
        _set_device(entity, device)
        map_data = SimpleNamespace(last_updated=0, timestamp_ms=8_000_000, frame_id=2)
        with patch.object(type(entity), "_map_data", new=property(lambda self: map_data)):
            entity.update()
        assert entity._state == datetime.fromtimestamp(8000)


# ===========================================================================
# handle_async_still_stream
# ===========================================================================
class TestHandleAsyncStillStream:
    async def test_writes_frame_twice_and_stops_when_device_disappears(self) -> None:
        entity = _bare_camera()
        entity.content_type = "image/png"
        _set_device(entity, MagicMock())  # device present for the first check

        async def fake_camera_image(*_a, **_k):
            entity.coordinator.device = None  # gone by the time we check again
            return b"FRAME1"

        response = MagicMock()
        response.prepare = AsyncMock()
        response.write = AsyncMock()
        request = MagicMock()

        with (
            patch.object(entity, "async_camera_image", side_effect=fake_camera_image),
            patch("custom_components.dreame_vacuum.camera.web.StreamResponse", return_value=response),
        ):
            result = await entity.handle_async_still_stream(request, 0.01)

        assert result is response
        response.prepare.assert_awaited_once_with(request)
        # Written twice (Chrome workaround) for the single new frame.
        assert response.write.await_count == 2
        first_call = response.write.await_args_list[0].args[0]
        assert b"FRAME1" in first_call
        assert b"Content-Type: image/png" in first_call

    async def test_uses_default_image_when_frame_missing(self) -> None:
        entity = _bare_camera()
        entity.content_type = "image/png"
        _set_device(entity, None)  # loop breaks immediately after first frame

        renderer = MagicMock()
        renderer.default_map_image = b"DEFAULTIMG"
        renderer.disconnected_map_image = b"DISCONNECTED"
        entity._renderer = renderer

        response = MagicMock()
        response.prepare = AsyncMock()
        response.write = AsyncMock()
        request = MagicMock()

        with (
            patch.object(entity, "async_camera_image", AsyncMock(return_value=None)),
            patch("custom_components.dreame_vacuum.camera.web.StreamResponse", return_value=response),
        ):
            await entity.handle_async_still_stream(request, 0.01)

        written = response.write.await_args_list[0].args[0]
        assert b"DEFAULTIMG" in written

    async def test_identical_frame_not_rewritten(self) -> None:
        """No device -> the loop only runs once, so a repeat frame writes nothing extra."""
        entity = _bare_camera()
        entity.content_type = "image/png"
        device_holder = {"device": MagicMock()}
        entity.coordinator = SimpleNamespace()
        type(entity.coordinator)
        entity.coordinator = MagicMock()
        entity.coordinator.device = device_holder["device"]

        frames = iter([b"SAME", b"SAME"])

        async def fake_camera_image(*_a, **_k):
            # After the second frame is fetched, drop the device to end the loop.
            try:
                frame = next(frames)
            except StopIteration:
                frame = b"SAME"
            if frame == b"SAME" and response.write.await_count >= 2:
                entity.coordinator.device = None
            return frame

        response = MagicMock()
        response.prepare = AsyncMock()
        response.write = AsyncMock()
        request = MagicMock()

        async def fake_sleep(_interval):
            entity.coordinator.device = None

        with (
            patch.object(entity, "async_camera_image", side_effect=fake_camera_image),
            patch("custom_components.dreame_vacuum.camera.web.StreamResponse", return_value=response),
            patch("custom_components.dreame_vacuum.camera.asyncio.sleep", side_effect=fake_sleep),
        ):
            await entity.handle_async_still_stream(request, 0.01)

        # Only the first (new) frame is written (twice); the identical second
        # frame observed after sleep triggers no additional writes.
        assert response.write.await_count == 2


# ===========================================================================
# obstacle_image / obstacle_history_image
# ===========================================================================
class TestObstacleImage:
    async def test_success_returns_proxy_and_object_name(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        _set_device(entity, device)
        obstacle = SimpleNamespace(object_name="pet.jpg")
        device.obstacle_image.return_value = (b"resp", obstacle)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "_get_proxy_obstacle_image", return_value=b"PROXY") as proxy,
        ):
            result, name = await entity.obstacle_image(3, box=True, crop=True)
        assert result == b"PROXY"
        assert name == "pet.jpg"
        device.obstacle_image.assert_called_once_with(3)
        proxy.assert_called_once_with(b"resp", obstacle, True, True, "obstacle")

    async def test_returns_none_when_response_missing(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        device.obstacle_image.return_value = (None, None)
        _set_device(entity, device)
        with patch.object(type(entity), "map_data_json", new=property(lambda self: False)):
            result = await entity.obstacle_image(1)
        assert result == (None, None)

    async def test_guard_short_circuits_for_saved_map(self) -> None:
        entity = _bare_camera()
        entity.map_index = 1
        device = MagicMock()
        _set_device(entity, device)
        with patch.object(type(entity), "map_data_json", new=property(lambda self: False)):
            result = await entity.obstacle_image(1)
        assert result == (None, None)
        device.obstacle_image.assert_not_called()

    async def test_guard_short_circuits_for_json_camera(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        _set_device(entity, device)
        with patch.object(type(entity), "map_data_json", new=property(lambda self: True)):
            result = await entity.obstacle_image(1)
        assert result == (None, None)
        device.obstacle_image.assert_not_called()


class TestObstacleHistoryImage:
    async def test_success_returns_proxy_and_object_name(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        _set_device(entity, device)
        obstacle = SimpleNamespace(object_name="pet_history.jpg")
        device.obstacle_history_image.return_value = (b"resp", obstacle)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "_get_proxy_obstacle_image", return_value=b"PROXY") as proxy,
        ):
            result, name = await entity.obstacle_history_image(2, 5, True, box=False, crop=True)
        assert result == b"PROXY"
        assert name == "pet_history.jpg"
        device.obstacle_history_image.assert_called_once_with(2, 5, True)
        proxy.assert_called_once_with(b"resp", obstacle, False, True, "obstacle_history", 1)

    async def test_returns_none_when_obstacle_missing(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        device.obstacle_history_image.return_value = (b"resp", None)
        _set_device(entity, device)
        with patch.object(type(entity), "map_data_json", new=property(lambda self: False)):
            result = await entity.obstacle_history_image(1, 1, False)
        assert result == (None, None)

    async def test_guard_short_circuits_for_json_camera(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        _set_device(entity, device)
        with patch.object(type(entity), "map_data_json", new=property(lambda self: True)):
            result = await entity.obstacle_history_image(1, 1, False)
        assert result == (None, None)
        device.obstacle_history_image.assert_not_called()


# ===========================================================================
# history_map_image
# ===========================================================================
class TestHistoryMapImage:
    async def test_png_path_renders_via_get_map_for_render(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        _set_device(entity, device)
        map_data = SimpleNamespace(cleaning_map_data=None)
        device.history_map.return_value = map_data
        device.get_map_for_render.return_value = "rendered"
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "_get_proxy_image", return_value=b"IMG") as proxy,
        ):
            result = await entity.history_map_image(2, True, False, False, False, False)
        device.history_map.assert_called_once_with(2, False)
        device.get_map_for_render.assert_called_once_with(map_data)
        proxy.assert_called_once_with(2, "rendered", True, "cleaning")
        assert result == b"IMG"

    async def test_dirty_map_uses_cleaning_map_data_directly(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        _set_device(entity, device)
        cleaning_data = SimpleNamespace(marker="clean")
        map_data = SimpleNamespace(cleaning_map_data=cleaning_data)
        device.history_map.return_value = map_data
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "_get_proxy_image", return_value=b"IMG") as proxy,
        ):
            result = await entity.history_map_image(1, True, False, False, True, False)
        device.get_map_for_render.assert_not_called()
        proxy.assert_called_once_with(1, cleaning_data, True, "dirty")
        assert result == b"IMG"

    async def test_cruising_forces_render_even_when_dirty(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        _set_device(entity, device)
        map_data = SimpleNamespace(cleaning_map_data=SimpleNamespace())
        device.history_map.return_value = map_data
        device.get_map_for_render.return_value = "rendered"
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "_get_proxy_image", return_value=b"IMG") as proxy,
        ):
            await entity.history_map_image(2, False, True, False, True, False)
        device.history_map.assert_called_once_with(2, True)
        device.get_map_for_render.assert_called_once_with(map_data)
        proxy.assert_called_once_with(2, "rendered", False, "cruising")

    async def test_data_string_renders_json(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        _set_device(entity, device)
        map_data = SimpleNamespace(cleaning_map_data=None)
        device.history_map.return_value = map_data
        device.get_map_for_render.return_value = "rendered"
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(entity, "_render_data_string", return_value="JSONSTR") as render,
        ):
            result = await entity.history_map_image(1, True, False, True, False, True)
        render.assert_called_once_with("rendered", True)
        assert result == "JSONSTR"

    async def test_returns_none_when_no_map_data(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        device.history_map.return_value = None
        _set_device(entity, device)
        with patch.object(type(entity), "map_data_json", new=property(lambda self: False)):
            result = await entity.history_map_image(1, True, False, False, False, False)
        assert result is None

    async def test_guard_short_circuits_for_saved_map(self) -> None:
        entity = _bare_camera()
        entity.map_index = 1
        device = MagicMock()
        _set_device(entity, device)
        with patch.object(type(entity), "map_data_json", new=property(lambda self: False)):
            result = await entity.history_map_image(1, True, False, False, False, False)
        assert result is None
        device.history_map.assert_not_called()


# ===========================================================================
# recovery_map_file
# ===========================================================================
class TestRecoveryMapFile:
    async def test_current_map_uses_selected_map_id(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        selected = SimpleNamespace(map_id=99)
        device.status.selected_map = selected
        device.recovery_map_file.return_value = (b"tar", "url", "name.mb.tbz2")
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            result = await entity.recovery_map_file(2)
        assert result == (b"tar", "url", "name.mb.tbz2")
        device.recovery_map_file.assert_called_once_with(99, 2)

    async def test_no_map_id_returns_none_tuple(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        device.status.selected_map = None
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            result = await entity.recovery_map_file(1)
        assert result == (None, None, None)
        device.recovery_map_file.assert_not_called()

    async def test_saved_map_uses_internal_map_id(self) -> None:
        entity = _bare_camera()
        entity.map_index = 3
        entity._map_id = 55
        device = MagicMock()
        device.recovery_map_file.return_value = (b"tar", "url", "n")
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            result = await entity.recovery_map_file(4)
        assert result == (b"tar", "url", "n")
        device.recovery_map_file.assert_called_once_with(55, 4)

    async def test_guard_short_circuits_for_wifi_or_json(self) -> None:
        entity = _bare_camera()
        device = MagicMock()
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: True)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            result = await entity.recovery_map_file(1)
        assert result == (None, None, None)
        device.recovery_map_file.assert_not_called()


# ===========================================================================
# recovery_map
# ===========================================================================
class TestRecoveryMap:
    async def test_current_map_with_selected(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        selected = SimpleNamespace(map_id=7)
        device.status.selected_map = selected
        map_data = SimpleNamespace()
        device.recovery_map.return_value = map_data
        device.get_map_for_render.return_value = "rendered"
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(entity, "_get_proxy_image", return_value=b"IMG") as proxy,
        ):
            result = await entity.recovery_map(3, True, False, False)
        device.recovery_map.assert_called_once_with(7, 3)
        device.get_map_for_render.assert_called_once_with(map_data)
        proxy.assert_called_once_with(3, "rendered", True, "recovery")
        assert result == b"IMG"

    async def test_current_map_without_selected_returns_none(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        device.status.selected_map = None
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            result = await entity.recovery_map(1, True, False, False)
        assert result is None
        device.recovery_map.assert_not_called()

    async def test_saved_map_uses_internal_map_id(self) -> None:
        entity = _bare_camera()
        entity.map_index = 2
        entity._map_id = 44
        device = MagicMock()
        map_data = SimpleNamespace()
        device.recovery_map.return_value = map_data
        device.get_map_for_render.return_value = "rendered"
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(entity, "_render_data_string", return_value="JSON") as render,
        ):
            result = await entity.recovery_map(5, False, True, True)
        device.recovery_map.assert_called_once_with(44, 5)
        render.assert_called_once_with("rendered", True)
        assert result == "JSON"

    async def test_guard_short_circuits_for_wifi_map(self) -> None:
        entity = _bare_camera()
        device = MagicMock()
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: True)),
        ):
            result = await entity.recovery_map(1, True, False, False)
        assert result is None
        device.recovery_map.assert_not_called()


# ===========================================================================
# wifi_map_data
# ===========================================================================
class TestWifiMapData:
    async def test_current_map_renders_proxy_image(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        wifi_sub = MagicMock()
        selected = SimpleNamespace(wifi_map_data=wifi_sub)
        device.status.selected_map = selected
        rendered = SimpleNamespace(map_index=9)
        device.get_map_for_render.return_value = rendered
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(entity, "_get_proxy_image", return_value=b"IMG") as proxy,
        ):
            result = await entity.wifi_map_data(False, False)
        device.get_map_for_render.assert_called_once_with(wifi_sub)
        proxy.assert_called_once_with(9, rendered, False, "wifi", 1)
        assert result == b"IMG"

    async def test_saved_map_uses_map_index_directly(self) -> None:
        entity = _bare_camera()
        entity.map_index = 3
        device = MagicMock()
        wifi_sub = MagicMock()
        map_data = SimpleNamespace(wifi_map_data=wifi_sub)
        device.get_map.return_value = map_data
        rendered = SimpleNamespace(map_index=None)
        device.get_map_for_render.return_value = rendered
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(entity, "_get_proxy_image", return_value=b"IMG") as proxy,
        ):
            result = await entity.wifi_map_data(False, False)
        device.get_map.assert_called_once_with(3)
        proxy.assert_called_once_with(3, rendered, False, "wifi", 1)
        assert result == b"IMG"

    async def test_no_wifi_submap_returns_none(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        selected = SimpleNamespace(wifi_map_data=None)
        device.status.selected_map = selected
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            result = await entity.wifi_map_data(False, False)
        assert result is None
        device.get_map_for_render.assert_not_called()

    async def test_data_string_renders_json(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        wifi_sub = MagicMock()
        selected = SimpleNamespace(wifi_map_data=wifi_sub)
        device.status.selected_map = selected
        rendered = SimpleNamespace(map_index=9)
        device.get_map_for_render.return_value = rendered
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(entity, "_render_data_string", return_value="JSON") as render,
        ):
            result = await entity.wifi_map_data(True, True)
        render.assert_called_once_with(rendered, True)
        assert result == "JSON"

    async def test_guard_short_circuits_when_wifi_map_itself(self) -> None:
        entity = _bare_camera()
        device = MagicMock()
        _set_device(entity, device)
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: True)),
        ):
            result = await entity.wifi_map_data(False, False)
        assert result is None


# ===========================================================================
# _render_data_string / map_data_string / resources
# ===========================================================================
class TestRenderDataString:
    def test_with_resources(self) -> None:
        entity = _bare_camera()
        device = MagicMock()
        device.capability = "CAP"
        _set_device(entity, device)
        renderer = MagicMock()
        renderer.get_resources.return_value = {"r": 1}
        renderer.get_data_string.return_value = "JSON"
        entity._renderer = renderer
        result = entity._render_data_string("MAPDATA", True)
        assert result == "JSON"
        renderer.get_resources.assert_called_once_with("CAP")
        renderer.get_data_string.assert_called_once_with("MAPDATA", {"r": 1})

    def test_without_resources(self) -> None:
        entity = _bare_camera()
        device = MagicMock()
        _set_device(entity, device)
        renderer = MagicMock()
        renderer.get_data_string.return_value = "JSON"
        entity._renderer = renderer
        entity._render_data_string("MAPDATA", False)
        renderer.get_resources.assert_not_called()
        renderer.get_data_string.assert_called_once_with("MAPDATA", None)


class TestMapDataStringMethod:
    def test_returns_empty_json_when_json_map(self) -> None:
        entity = _bare_camera()
        with patch.object(type(entity), "map_data_json", new=property(lambda self: True)):
            assert entity.map_data_string(False) == "{}"

    def test_returns_empty_json_when_no_map_data(self) -> None:
        entity = _bare_camera()
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: None)),
        ):
            assert entity.map_data_string(False) == "{}"

    def test_success_updates_map_and_renders(self) -> None:
        entity = _bare_camera()
        entity.map_index = 0
        device = MagicMock()
        device.get_map_for_render.return_value = "rendered"
        device.status.robot_status = "R"
        device.status.station_status = "S"
        _set_device(entity, device)
        renderer = MagicMock()
        renderer.get_data_string.return_value = "JSONSTR"
        renderer.get_resources.return_value = {}
        entity._renderer = renderer
        map_data = SimpleNamespace()
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            result = entity.map_data_string(True)
        assert result == "JSONSTR"
        device.update_map.assert_called_once()
        device.get_map_for_render.assert_called_once_with(map_data)
        renderer.get_data_string.assert_called_once_with("rendered", {}, "R", "S")

    def test_saved_map_does_not_trigger_update_map(self) -> None:
        entity = _bare_camera()
        entity.map_index = 2
        device = MagicMock()
        device.get_map_for_render.return_value = "rendered"
        _set_device(entity, device)
        renderer = MagicMock()
        renderer.get_data_string.return_value = "JSONSTR"
        entity._renderer = renderer
        map_data = SimpleNamespace()
        with (
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            entity.map_data_string(False)
        device.update_map.assert_not_called()


class TestResourcesMethod:
    def test_with_device(self) -> None:
        entity = _bare_camera()
        device = MagicMock()
        _set_device(entity, device)
        renderer = MagicMock()
        renderer.get_resources.return_value = "RES"
        entity._renderer = renderer
        result = entity.resources("iconset1")
        assert result == "RES"
        renderer.get_resources.assert_called_once_with(device.capability, True, "iconset1")

    def test_without_device(self) -> None:
        entity = _bare_camera()
        _set_device(entity, None)
        assert entity.resources() == "{}"


# ===========================================================================
# _update_image
# ===========================================================================
class TestUpdateImage:
    async def test_success_triggers_coordinator_update(self) -> None:
        entity = _bare_camera()
        renderer = MagicMock()
        renderer.render_map.return_value = b"NEWIMG"
        renderer.calibration_points = [{"a": 1}]
        entity._renderer = renderer
        entity._calibration_points = None
        with patch.object(type(entity), "map_data_json", new=property(lambda self: False)):
            await entity._update_image("MAPDATA", "R", "S")
        assert entity._image == b"NEWIMG"
        assert entity._calibration_points == [{"a": 1}]
        entity.coordinator.set_updated_data.assert_called_once()
        renderer.render_map.assert_called_once_with("MAPDATA", "R", "S")

    async def test_no_coordinator_update_when_calibration_unchanged(self) -> None:
        entity = _bare_camera()
        renderer = MagicMock()
        renderer.render_map.return_value = b"NEWIMG"
        renderer.calibration_points = [{"a": 1}]
        entity._renderer = renderer
        entity._calibration_points = [{"a": 1}]
        with patch.object(type(entity), "map_data_json", new=property(lambda self: False)):
            await entity._update_image("MAPDATA", "R", "S")
        entity.coordinator.set_updated_data.assert_not_called()

    async def test_logs_warning_on_render_failure(self) -> None:
        entity = _bare_camera()
        renderer = MagicMock()
        renderer.render_map.side_effect = RuntimeError("boom")
        entity._renderer = renderer
        old_image = entity._image
        with patch.object(cam.LOGGER, "warning") as warn:
            await entity._update_image("MAPDATA", "R", "S")
        warn.assert_called_once()
        assert entity._image == old_image


# ===========================================================================
# _get_proxy_image / _get_proxy_obstacle_image caches
# ===========================================================================
class TestGetProxyImage:
    def test_cache_hit_avoids_second_render(self) -> None:
        entity = _bare_camera()
        renderer = MagicMock()
        renderer.render_map.side_effect = lambda md, a, b, info: f"IMG{md.last_updated}".encode()
        entity._proxy_renderer = renderer
        entity._proxy_images = {}
        md1 = SimpleNamespace(last_updated=1)
        img1 = entity._get_proxy_image(1, md1, True, "cleaning", max_item=2)
        assert img1 == b"IMG1"
        img1b = entity._get_proxy_image(1, md1, True, "cleaning", max_item=2)
        assert img1b == img1
        assert renderer.render_map.call_count == 1

    def test_evicts_oldest_when_max_item_reached(self) -> None:
        entity = _bare_camera()
        renderer = MagicMock()
        renderer.render_map.side_effect = lambda md, a, b, info: f"IMG{md.last_updated}".encode()
        entity._proxy_renderer = renderer
        entity._proxy_images = {}
        for ts in (1, 2, 3):
            entity._get_proxy_image(ts, SimpleNamespace(last_updated=ts), True, "cleaning", max_item=2)
        assert len(entity._proxy_images["cleaning"]) == 2
        # The oldest item (ts=1) must have been evicted.
        assert not any(key.endswith("_d1") for key in entity._proxy_images["cleaning"])

    def test_returns_none_and_does_not_cache_when_render_returns_falsy(self) -> None:
        entity = _bare_camera()
        renderer = MagicMock()
        renderer.render_map.return_value = None
        entity._proxy_renderer = renderer
        entity._proxy_images = {}
        result = entity._get_proxy_image(1, SimpleNamespace(last_updated=1), True, "cleaning")
        assert result is None
        assert entity._proxy_images["cleaning"] == {}


class TestGetProxyObstacleImage:
    def test_cache_hit_avoids_second_render(self) -> None:
        entity = _bare_camera()
        device = MagicMock()
        device.capability.obstacle_image_crop = True
        _set_device(entity, device)
        renderer = MagicMock()
        renderer.render_obstacle_image.side_effect = lambda data, obstacle, crop_cap, box, crop: (
            f"OBS{obstacle.id}".encode()
        )
        entity._renderer = renderer
        entity._proxy_images = {}
        obstacle = SimpleNamespace(id="a1")
        img1 = entity._get_proxy_obstacle_image(b"data", obstacle, True, True, "obstacle", max_item=3)
        assert img1 == b"OBSa1"
        img1b = entity._get_proxy_obstacle_image(b"data", obstacle, True, True, "obstacle", max_item=3)
        assert img1b == img1
        assert renderer.render_obstacle_image.call_count == 1

    def test_evicts_oldest_when_max_item_reached(self) -> None:
        entity = _bare_camera()
        device = MagicMock()
        device.capability.obstacle_image_crop = False
        _set_device(entity, device)
        renderer = MagicMock()
        renderer.render_obstacle_image.side_effect = lambda data, obstacle, crop_cap, box, crop: (
            f"OBS{obstacle.id}".encode()
        )
        entity._renderer = renderer
        entity._proxy_images = {}
        for oid in ("a", "b", "c"):
            entity._get_proxy_obstacle_image(b"data", SimpleNamespace(id=oid), True, True, "obstacle", max_item=2)
        assert len(entity._proxy_images["obstacle"]) == 2
        assert not any(key.endswith("_da") for key in entity._proxy_images["obstacle"])

    def test_returns_none_when_render_returns_falsy(self) -> None:
        entity = _bare_camera()
        device = MagicMock()
        device.capability.obstacle_image_crop = True
        _set_device(entity, device)
        renderer = MagicMock()
        renderer.render_obstacle_image.return_value = None
        entity._renderer = renderer
        entity._proxy_images = {}
        result = entity._get_proxy_obstacle_image(b"data", SimpleNamespace(id="x"), True, True, "obstacle")
        assert result is None


# ===========================================================================
# _default_map_image: renderer missing
# ===========================================================================
class TestDefaultMapImageNoRenderer:
    def test_returns_none_when_no_renderer(self) -> None:
        entity = _bare_camera()
        entity._renderer = None
        assert entity._default_map_image is None


# ===========================================================================
# extra_state_attributes: remaining branches
# ===========================================================================
class TestExtraStateAttributesBranches:
    def _build_attr_entity(self, *, segments_present=True):
        entity = _bare_camera()
        entity.map_index = 0
        entity.access_tokens = ["tok-a", "tok-b"]
        entity.entity_id = "camera.test_map"
        entity._renderer = MagicMock(spec=["calibration_points", "default_calibration_points"])
        entity._renderer.calibration_points = [{"x": 1}]

        map_data = SimpleNamespace(
            empty_map=False,
            pixel_type=np.zeros((4, 4), dtype=np.uint8) if segments_present else None,
            segments={5: SimpleNamespace(x=1.0, y=1.0)} if segments_present else {},
            last_updated=1000,
            obstacles=None,
            recovery_map_list=None,
            wifi_map_data=None,
        )
        map_data.as_dict = lambda: {ATTR_ROOMS: {5: {"name": "Kitchen"}}}

        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status.selected_map = None
        device.status._cleaning_history = None
        device.status._cruising_history = None
        _set_device(entity, device)
        return entity, map_data

    def test_robot_in_map_reflects_renderer_config(self) -> None:
        entity, map_data = self._build_attr_entity()
        entity._segment_map_cache = (None, None, None)
        entity._renderer = MagicMock(spec=["calibration_points", "default_calibration_points", "config"])
        entity._renderer.calibration_points = []
        entity._renderer.config = SimpleNamespace(robot=False)
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs = entity.extra_state_attributes
        from custom_components.dreame_vacuum.dreame.const import ATTR_ROBOT_IN_MAP

        assert attrs[ATTR_ROBOT_IN_MAP] is False

    def test_non_dict_room_entries_are_skipped(self) -> None:
        entity, map_data = self._build_attr_entity()
        map_data.as_dict = lambda: {ATTR_ROOMS: {5: {"name": "Kitchen"}, 6: "unexpected-string"}}
        entity._segment_map_cache = (1000, "B64", {5: 10, 6: 11})
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs = entity.extra_state_attributes
        assert attrs[ATTR_ROOMS][5][ATTR_SEGMENT_ID] == 10
        assert attrs[ATTR_ROOMS][6] == "unexpected-string"

    def test_attributes_default_to_empty_dict_when_cloud_disconnected(self) -> None:
        entity, map_data = self._build_attr_entity()
        entity.device.cloud_connected = False
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs = entity.extra_state_attributes
        assert attrs is not None
        assert ATTR_CALIBRATION not in attrs

    def test_history_urls_and_obstacle_annotations(self) -> None:
        from custom_components.dreame_vacuum.dreame.const import (
            ATTR_CLEANING_HISTORY_PICTURE,
            ATTR_CRUISING_HISTORY_PICTURE,
            ATTR_OBSTACLE_PICTURE,
        )

        class _IgnoreStatus:
            def __init__(self, value: int, name: str) -> None:
                self._value = value
                self.name = name

            def __int__(self) -> int:
                return self._value

        entity = _bare_camera()
        entity.map_index = 0
        entity.entity_id = "camera.test_map"
        entity.access_tokens = ["tok"]
        entity._segment_map_cache = (None, None, None)
        entity._renderer = MagicMock(spec=["calibration_points"])
        entity._renderer.calibration_points = []

        cleaning_entry = SimpleNamespace(
            date=SimpleNamespace(timestamp=lambda: 1_700_000_000),
            second_cleaning=True,
            status=1,
            completed=True,
        )
        cruising_entry = SimpleNamespace(
            date=SimpleNamespace(timestamp=lambda: 1_700_000_100),
            second_cleaning=False,
            status=2,
            completed=False,
        )

        obstacle = SimpleNamespace(
            type=SimpleNamespace(value=1, name="some_obstacle"),
            id="obs-1",
            possibility=87,
            segment=5,
            ignore_status=_IgnoreStatus(1, "user_ignored"),
            picture_status=None,
        )

        map_data = SimpleNamespace(
            empty_map=False,
            pixel_type=None,
            segments={},
            last_updated=1_700_000_000,
            obstacles={1: obstacle},
            recovery_map_list=None,
            wifi_map_data=None,
        )
        map_data.as_dict = dict

        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status._cleaning_history = [cleaning_entry]
        device.status._cruising_history = [cruising_entry]
        device.status.ai_pet_detection = 1
        device.capability.fluid_detection = False
        device.status.selected_map = None
        _set_device(entity, device)

        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs = entity.extra_state_attributes

        cleaning_urls = attrs[ATTR_CLEANING_HISTORY_PICTURE]
        assert len(cleaning_urls) == 1
        cleaning_key = next(iter(cleaning_urls))
        assert "Second" in cleaning_key
        assert "Completed" in cleaning_key

        cruising_urls = attrs[ATTR_CRUISING_HISTORY_PICTURE]
        assert len(cruising_urls) == 1
        assert next(iter(cruising_urls.values())).endswith("&cruising=1")

        obstacle_key = next(iter(attrs[ATTR_OBSTACLE_PICTURE]))
        assert "%87" in obstacle_key
        assert "(5)" in obstacle_key
        assert "(User Ignored)" in obstacle_key


# ===========================================================================
# extra_state_attributes: memoization cache (Plan 008)
# ===========================================================================
class TestAttributesCache:
    """``extra_state_attributes`` is memoized by an input signature: an
    unchanged signature must return the *same* dict object (proves the
    rebuild was skipped); any signature input changing must produce a fresh
    dict reflecting the new content.
    """

    def _build_entity(self):
        entity = _bare_camera()
        entity.map_index = 0
        entity.access_tokens = ["tok-a", "tok-b"]
        entity.entity_id = "camera.test_map"
        entity._segment_map_cache = (None, None, None)

        renderer = MagicMock(spec=["calibration_points", "robot_icon_data_uri", "robot_beam_icon_data_uri", "config"])
        renderer.calibration_points = []
        renderer.config = SimpleNamespace(robot=False)
        renderer.robot_icon_data_uri = lambda light_on: f"icon-{'on' if light_on else 'off'}"
        renderer.robot_beam_icon_data_uri = lambda: "data:image/png;base64,beam"
        entity._renderer = renderer

        map_data = SimpleNamespace(
            empty_map=False,
            pixel_type=None,
            segments={},
            last_updated=1000,
            obstacles=None,
            recovery_map_list=None,
            wifi_map_data=None,
        )
        map_data.as_dict = lambda: {ATTR_ROOMS: {}}

        device = MagicMock()
        device.cloud_connected = True
        device.status.located = True
        device.status.selected_map = None
        device.status._cleaning_history = None
        device.status._cruising_history = None
        device.status.fill_light = False
        _set_device(entity, device)
        return entity, map_data, device

    def test_cache_hit_returns_same_object(self) -> None:
        entity, map_data, _device = self._build_entity()
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs1 = entity.extra_state_attributes
            attrs2 = entity.extra_state_attributes
        assert attrs1 is attrs2

    def test_cache_invalidates_on_last_updated_change(self) -> None:
        entity, map_data, _device = self._build_entity()
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs1 = entity.extra_state_attributes
            map_data.last_updated = 2000
            attrs2 = entity.extra_state_attributes
        assert attrs1 is not attrs2

    def test_cache_invalidates_on_token_rotation(self) -> None:
        entity, map_data, _device = self._build_entity()
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs1 = entity.extra_state_attributes
            entity.access_tokens.append("tok-c")
            attrs2 = entity.extra_state_attributes
        assert attrs1 is not attrs2
        assert attrs1 is not None
        assert attrs2 is not None

    def test_fill_light_toggle_changes_robot_icon(self) -> None:
        from custom_components.dreame_vacuum.dreame.const import ATTR_ROBOT_ICON

        entity, map_data, device = self._build_entity()
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs1 = entity.extra_state_attributes
            device.status.fill_light = True
            attrs2 = entity.extra_state_attributes
        assert attrs1 is not None
        assert attrs2 is not None
        assert attrs1[ATTR_ROBOT_ICON] == "icon-off"
        assert attrs2[ATTR_ROBOT_ICON] == "icon-on"
        assert attrs1 is not attrs2

    def test_no_beam_icon_when_fill_light_off(self) -> None:
        """The beam attribute (Plan 021) must be absent while the fill light
        is off -- the card only draws it behind the body when the light is on.
        """
        from custom_components.dreame_vacuum.dreame.const import ATTR_ROBOT_BEAM_ICON

        entity, map_data, _device = self._build_entity()
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs = entity.extra_state_attributes
        assert attrs is not None
        assert ATTR_ROBOT_BEAM_ICON not in attrs

    def test_beam_icon_present_when_fill_light_on(self) -> None:
        """When the fill light is on, the beam data URI is exposed alongside
        the (subtly warmed) body icon.
        """
        from custom_components.dreame_vacuum.dreame.const import ATTR_ROBOT_BEAM_ICON

        entity, map_data, device = self._build_entity()
        device.status.fill_light = True
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs = entity.extra_state_attributes
        assert attrs is not None
        assert attrs[ATTR_ROBOT_BEAM_ICON].startswith("data:image/png;base64,")

    def test_cache_invalidates_on_segment_rename(self) -> None:
        """A room rename mutates the ``Segment`` object in place without the
        owning ``MapData`` gaining a new ``last_updated``/``frame_id`` (that
        only happens ~0.5s later via the editor's deferred refresh timer --
        see ``_segment_signature`` in camera.py). The attributes cache must
        still pick up the rename immediately.
        """
        entity, map_data, _device = self._build_entity()
        segment = SimpleNamespace(custom_name="Kitchen", type=0)
        map_data.segments = {5: segment}
        map_data.as_dict = lambda: {ATTR_ROOMS: {5: {"name": segment.custom_name}}}
        with (
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
            patch.object(type(entity), "map_data_json", new=property(lambda self: False)),
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
        ):
            attrs1 = entity.extra_state_attributes
            # Simulate the map editor's in-place rename (map_editor.py
            # set_segment_name): the Segment object is mutated directly,
            # last_updated/frame_id are untouched until the deferred timer.
            segment.custom_name = "Living Room"
            attrs2 = entity.extra_state_attributes
        assert attrs1[ATTR_ROOMS][5]["name"] == "Kitchen"
        assert attrs2[ATTR_ROOMS][5]["name"] == "Living Room"
        assert attrs1 is not attrs2
