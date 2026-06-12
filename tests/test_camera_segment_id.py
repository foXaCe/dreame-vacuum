"""Tests for the segment_id enrichment applied to the rooms attribute.

The camera entity exposes a ``segment_map`` PNG where the blue channel
encodes the room key (after remapping from the raw pixel_type values).
Lovelace cards need the reverse lookup — which raw pixel_type value
corresponds to which room — so we inject it onto each room dict under
``segment_id``. These tests pin that contract.

The camera module pulls in optional native deps (turbojpeg, py_mini_racer)
that aren't guaranteed to be installed in CI or dev. We load
``_find_segment_at`` from source with ``ast`` so the algorithm stays
covered without those heavyweight imports.
"""

from __future__ import annotations

import ast
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest


def _load_find_segment_at():
    """Return the live ``_find_segment_at`` function parsed from camera.py."""
    source = pathlib.Path("custom_components/dreame_vacuum/camera.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_find_segment_at":
            func_src = ast.get_source_segment(source, node)
            namespace: dict = {}
            exec(func_src, namespace)  # nosec B102 -- loading our own source intentionally
            return namespace["_find_segment_at"]
    raise AssertionError("_find_segment_at not found in camera.py")


_find_segment_at = _load_find_segment_at()


def test_find_segment_at_hit() -> None:
    """Direct hit: the center pixel carries the raw pixel_type value."""

    class FakePixelType:
        def __getitem__(self, key):
            x, y = key
            return 7 if (x, y) == (5, 5) else 0

    assert _find_segment_at(FakePixelType(), 5, 5, 10, 10) == 7


def test_find_segment_at_spiral_walk() -> None:
    """The center is empty but a neighbour carries a raw value."""

    class FakePixelType:
        def __getitem__(self, key):
            x, y = key
            return 3 if (x, y) == (6, 5) else 0

    assert _find_segment_at(FakePixelType(), 5, 5, 10, 10) == 3


def test_find_segment_at_background() -> None:
    """Nothing within the search radius → the helper returns 0."""

    class FakePixelType:
        def __getitem__(self, key):
            return 0

    assert _find_segment_at(FakePixelType(), 5, 5, 10, 10) == 0


def test_find_segment_at_ignores_out_of_range_values() -> None:
    """Only raw values in the segment range (0 < v < 64) should match."""

    class FakePixelType:
        def __getitem__(self, key):
            # Floor marker (e.g. 200) must not be picked up.
            return 200

    assert _find_segment_at(FakePixelType(), 5, 5, 10, 10) == 0


def test_segment_id_contract_constants() -> None:
    """The camera imports the ATTR_SEGMENT_ID constant from const.py."""
    from custom_components.dreame_vacuum.dreame.const import ATTR_SEGMENT_ID

    assert ATTR_SEGMENT_ID == "segment_id"


# ===========================================================================
# Structural cache key: _async_update_segment_map rebuild behaviour
# ===========================================================================

def _ensure_native_stubs() -> None:
    """Install lightweight stand-ins for native optional deps."""
    if "turbojpeg" not in sys.modules:
        tj = types.ModuleType("turbojpeg")
        tj.TurboJPEG = type("TurboJPEG", (), {"__init__": lambda self, *a, **k: None})
        sys.modules["turbojpeg"] = tj
    if "py_mini_racer" not in sys.modules:
        pmr = types.ModuleType("py_mini_racer")
        pmr.MiniRacer = type("MiniRacer", (), {"__init__": lambda self, *a, **k: None})
        sys.modules["py_mini_racer"] = pmr


_ensure_native_stubs()

from custom_components.dreame_vacuum.camera import DreameVacuumCameraEntity  # noqa: E402


def _bare_entity_for_cache_tests(executor_mock: AsyncMock) -> DreameVacuumCameraEntity:
    """Minimal camera entity with a controllable executor mock."""
    entity = object.__new__(DreameVacuumCameraEntity)
    entity._segment_map_cache = (None, None, None)
    entity._should_poll = True
    entity._last_updated = -1
    entity._last_rendered = -1
    entity._last_map_request = 0
    entity._image = b"default"
    entity._calibration_points = None
    entity._color_scheme = "Dreame Light"
    entity.map_index = 0

    hass_mock = SimpleNamespace(async_add_executor_job=executor_mock)
    entity.hass = hass_mock
    entity.coordinator = SimpleNamespace(device=None)
    return entity


def _fake_md(raw_value: int = 10, seg_x: float = 2.0, seg_y: float = 2.0, last_updated: float = 1000.0):
    """Build a tiny map_data SimpleNamespace accepted by _async_update_segment_map."""
    w, h = 4, 4
    pt = np.zeros((w, h), dtype=np.uint8)
    pt[2, 2] = raw_value
    dims = SimpleNamespace(width=w, height=h, left=0, top=0, grid_size=1)
    seg = SimpleNamespace(x=seg_x, y=seg_y)
    return SimpleNamespace(
        pixel_type=pt,
        segments={1: seg},
        dimensions=dims,
        last_updated=last_updated,
    )


class TestSegmentMapCacheKey:
    async def test_stability_last_updated_bump_no_rebuild(self) -> None:
        """Bumping last_updated alone must NOT trigger a rebuild."""
        executor = AsyncMock(return_value=("b64", {1: 1}))
        entity = _bare_entity_for_cache_tests(executor)
        map_data = _fake_md(last_updated=1000.0)

        with (
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            await entity._async_update_segment_map()
            assert executor.call_count == 1

            # Bump timestamp only — pixels and segments are unchanged.
            map_data.last_updated = 9999.0
            await entity._async_update_segment_map()

        # Executor must NOT have been called a second time.
        assert executor.call_count == 1

    async def test_invalidation_on_pixel_change(self) -> None:
        """Changing a pixel in pixel_type must trigger a second rebuild."""
        executor = AsyncMock(return_value=("b64", {1: 1}))
        entity = _bare_entity_for_cache_tests(executor)
        map_data = _fake_md(raw_value=10, last_updated=1000.0)

        with (
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            await entity._async_update_segment_map()
            assert executor.call_count == 1

            # Modify a pixel: same timestamp, but different pixel content.
            map_data.pixel_type = np.zeros((4, 4), dtype=np.uint8)
            map_data.pixel_type[2, 2] = 11
            await entity._async_update_segment_map()

        assert executor.call_count == 2

    async def test_invalidation_on_segment_geometry_change(self) -> None:
        """Changing seg.x of a segment must trigger a rebuild."""
        executor = AsyncMock(return_value=("b64", {1: 1}))
        entity = _bare_entity_for_cache_tests(executor)
        map_data = _fake_md(seg_x=2.0, last_updated=1000.0)

        with (
            patch.object(type(entity), "_map_data", new=property(lambda self: map_data)),
            patch.object(type(entity), "wifi_map", new=property(lambda self: False)),
        ):
            await entity._async_update_segment_map()
            assert executor.call_count == 1

            # Shift the segment center — pixels unchanged.
            map_data.segments[1] = SimpleNamespace(x=3.0, y=2.0)
            await entity._async_update_segment_map()

        assert executor.call_count == 2
