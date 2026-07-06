"""Characterization tests for DreameVacuumMapOptimizer.

Covers the JS/MiniRacer optimization path, the wifi_map majority-vote
smoothing branch, the saved_map early return, the JS-failure fallback to
_merge_saved_map_data, and close() releasing the embedded V8 context.

py_mini_racer is installed in the project venv, so the real JS path is
exercised (no skip/mocking of MiniRacer itself, except where the test
explicitly needs to simulate a JS failure).

Note: tests/test_camera.py injects a bare `py_mini_racer` double into
sys.modules (no `.eval`/`.call`) when collected, guarded by
``if "py_mini_racer" not in sys.modules``. Depending on pytest's collection
order that double can "win" the cache before this module is imported, which
would make map_optimizer.py bind its `MiniRacer` name to the double instead
of the real native extension. Repair that here before importing anything
that depends on it, so this suite genuinely exercises the real V8 JS path.
"""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest


def _ensure_real_py_mini_racer() -> None:
    cached = sys.modules.get("py_mini_racer")
    if cached is None or not hasattr(getattr(cached, "MiniRacer", None), "eval"):
        sys.modules.pop("py_mini_racer", None)
        importlib.import_module("py_mini_racer")
        map_optimizer_name = "custom_components.dreame_vacuum.dreame.map_optimizer"
        if map_optimizer_name in sys.modules:
            importlib.reload(sys.modules[map_optimizer_name])


_ensure_real_py_mini_racer()

from py_mini_racer import MiniRacer

from custom_components.dreame_vacuum.dreame.map_optimizer import DreameVacuumMapOptimizer
from custom_components.dreame_vacuum.dreame.vacuum_types import MapImageDimensions


def _make_map_data(**overrides: object) -> SimpleNamespace:
    """Build a minimal synthetic map_data compatible with DreameVacuumMapOptimizer.optimize()."""
    w, h = 40, 30
    grid = np.full((w, h), 0, dtype=np.uint8)
    grid[5:35, 5:25] = 253
    grid[5, 5:25] = 255
    grid[34, 5:25] = 255
    grid[5:35, 5] = 255
    grid[5:35, 24] = 255
    md = SimpleNamespace(
        saved_map=False,
        wifi_map=False,
        empty_map=False,
        pixel_type=grid,
        dimensions=SimpleNamespace(left=0, top=0, width=w, height=h, grid_size=5),
        charger_position=SimpleNamespace(x=50, y=50, a=0),
        optimized_pixel_type=None,
        optimized_dimensions=None,
        optimized_charger_position=None,
    )
    for key, value in overrides.items():
        setattr(md, key, value)
    return md


@pytest.fixture
def optimizer() -> DreameVacuumMapOptimizer:
    return DreameVacuumMapOptimizer()


# ---------------------------------------------------------------------------
# JS/MiniRacer path
# ---------------------------------------------------------------------------


def test_optimize_js_path_populates_optimized_pixel_type_and_dimensions(
    optimizer: DreameVacuumMapOptimizer,
) -> None:
    """The real JS optimizer fills optimized_pixel_type/optimized_dimensions with the expected shape."""
    map_data = _make_map_data()

    result = optimizer.optimize(map_data)

    assert result is map_data
    assert result.optimized_pixel_type is not None
    assert isinstance(result.optimized_pixel_type, np.ndarray)
    assert result.optimized_pixel_type.shape == (40, 30)

    assert result.optimized_dimensions is not None
    assert isinstance(result.optimized_dimensions, MapImageDimensions)
    assert result.optimized_dimensions.top == 0
    assert result.optimized_dimensions.left == 0
    assert result.optimized_dimensions.width == 40
    assert result.optimized_dimensions.height == 30
    assert result.optimized_dimensions.grid_size == 5

    # The JS context is created lazily and cached on the optimizer instance.
    assert optimizer._js_optimizer is not None


def test_optimize_js_path_reuses_cached_js_optimizer_across_calls(
    optimizer: DreameVacuumMapOptimizer,
) -> None:
    """A second optimize() call must reuse the same MiniRacer context instead of recreating it."""
    optimizer.optimize(_make_map_data())
    first_context = optimizer._js_optimizer
    assert first_context is not None

    optimizer.optimize(_make_map_data())

    assert optimizer._js_optimizer is first_context


# ---------------------------------------------------------------------------
# saved_map early return
# ---------------------------------------------------------------------------


def test_optimize_saved_map_returns_map_data_unchanged(
    optimizer: DreameVacuumMapOptimizer,
) -> None:
    """map_data.saved_map=True triggers an early return with no mutation at all."""
    map_data = _make_map_data(saved_map=True)

    result = optimizer.optimize(map_data)

    assert result is map_data
    assert result.optimized_pixel_type is None
    assert result.optimized_dimensions is None
    # No JS context should have been created for a saved map.
    assert optimizer._js_optimizer is None


# ---------------------------------------------------------------------------
# wifi_map branch: majority-vote smoothing
# ---------------------------------------------------------------------------


def test_optimize_wifi_map_smooths_pixel_by_majority_vote(
    optimizer: DreameVacuumMapOptimizer,
) -> None:
    """A wifi pixel surrounded by a differing majority signal strength is smoothed to that majority.

    Grid is 7x7. Every cell is WIFI_LOW (12) except the center (3, 3), which is
    WIFI_POOR (11). At delta=3 the neighbourhood window covers the whole grid,
    so the vote is 48 x WIFI_LOW vs 1 x WIFI_POOR (the center itself) -> the
    center must be smoothed to WIFI_LOW (12).
    """
    size = 7
    grid = np.full((size, size), 12, dtype=np.uint8)  # WIFI_LOW everywhere
    grid[3, 3] = 11  # WIFI_POOR at the center only

    map_data = _make_map_data(
        wifi_map=True,
        pixel_type=grid,
        dimensions=SimpleNamespace(left=0, top=0, width=size, height=size, grid_size=5),
    )

    result = optimizer.optimize(map_data)

    assert result is map_data
    assert result.optimized_pixel_type is not None
    assert int(result.optimized_pixel_type[3, 3]) == 12
    # Untouched neighbours (already WIFI_LOW, value <= 2 check does not apply here
    # since 12 > 2, but the majority vote keeps them at 12 too).
    assert int(result.optimized_pixel_type[0, 0]) == 12
    assert result.optimized_dimensions is map_data.dimensions
    # JS path must not be used for the wifi_map branch.
    assert optimizer._js_optimizer is None


def test_optimize_wifi_map_empty_map_copies_without_smoothing(
    optimizer: DreameVacuumMapOptimizer,
) -> None:
    """empty_map=True skips the smoothing loop entirely; output is an untouched copy."""
    size = 7
    grid = np.full((size, size), 12, dtype=np.uint8)
    grid[3, 3] = 11

    map_data = _make_map_data(
        wifi_map=True,
        empty_map=True,
        pixel_type=grid,
        dimensions=SimpleNamespace(left=0, top=0, width=size, height=size, grid_size=5),
    )

    result = optimizer.optimize(map_data)

    assert result.optimized_pixel_type is not None
    # No smoothing happened: the lone WIFI_POOR pixel is preserved.
    assert int(result.optimized_pixel_type[3, 3]) == 11
    assert np.array_equal(result.optimized_pixel_type, grid)
    # It is a copy, not the same array object.
    assert result.optimized_pixel_type is not grid


# ---------------------------------------------------------------------------
# JS failure -> _merge_saved_map_data fallback
# ---------------------------------------------------------------------------


def test_optimize_js_failure_falls_back_to_merge_saved_map_data(
    optimizer: DreameVacuumMapOptimizer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When MiniRacer.call raises, optimize() must not propagate and must call _merge_saved_map_data."""
    monkeypatch.setattr(
        MiniRacer,
        "call",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    merge_spy = MagicMock()
    monkeypatch.setattr(optimizer, "_merge_saved_map_data", merge_spy)

    map_data = _make_map_data()

    result = optimizer.optimize(map_data)

    assert result is map_data
    merge_spy.assert_called_once_with(map_data, None)


def test_optimize_js_failure_with_saved_map_data_passed_through_to_merge(
    optimizer: DreameVacuumMapOptimizer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The saved_map_data argument to optimize() is forwarded to _merge_saved_map_data on JS failure."""
    monkeypatch.setattr(
        MiniRacer,
        "call",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    merge_spy = MagicMock()
    monkeypatch.setattr(optimizer, "_merge_saved_map_data", merge_spy)

    map_data = _make_map_data()
    saved_map_data = _make_map_data()

    result = optimizer.optimize(map_data, saved_map_data)

    assert result is map_data
    merge_spy.assert_called_once_with(map_data, saved_map_data)


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


def test_close_resets_js_optimizer_to_none(optimizer: DreameVacuumMapOptimizer) -> None:
    """close() drops the embedded V8 context so it can be reclaimed."""
    optimizer._js_optimizer = MagicMock()

    optimizer.close()

    assert optimizer._js_optimizer is None


def test_close_is_idempotent_when_already_none(optimizer: DreameVacuumMapOptimizer) -> None:
    """Calling close() when no JS context was ever created is a no-op, not an error."""
    assert optimizer._js_optimizer is None

    optimizer.close()

    assert optimizer._js_optimizer is None


# ---------------------------------------------------------------------------
# _merge_saved_map_data: JS-failure fallback merge algorithm (direct unit tests)
#
# Saved map covers global bbox (0,0)-(4,4), new map covers (2,2)-(6,6), both with
# grid_size=1, so the merged bbox is (0,0)-(6,6) with an overlap region of
# global (2,2)-(4,4). This lets every precedence rule be exercised in one grid.
# ---------------------------------------------------------------------------


def test_merge_saved_map_data_noop_when_saved_map_data_is_none(
    optimizer: DreameVacuumMapOptimizer,
) -> None:
    """With no saved_map_data, the merge is a pure no-op (early `if saved_map_data:` guard)."""
    map_data = _make_map_data()

    result = optimizer._merge_saved_map_data(map_data, None)

    assert result is None
    assert map_data.optimized_pixel_type is None
    assert map_data.optimized_dimensions is None


def test_merge_saved_map_data_precedence_rules_cell_by_cell(
    optimizer: DreameVacuumMapOptimizer,
) -> None:
    """
    Verifies the merge precedence rules cell by cell:
    - saved non-wall/non-zero value always wins, overlap or not
    - saved wall (255) is kept when the new map has no data there
    - saved wall demoted to floor (254) when the new map shows activity there
    - saved-unknown + new-wall -> wall propagates
    - saved-unknown + new-anything-else -> collapses to floor (254)
    - saved-unknown + no new data either -> stays 0
    """
    saved_pixel = np.full((4, 4), 50, dtype=np.uint8)
    saved_pixel[0, 0] = 255  # wall, outside new map's view (global (0,0))
    saved_pixel[2, 2] = 255  # wall, but new map also covers this cell (global (2,2))
    saved_pixel[3, 3] = 50  # generic saved value, overlaps new data (global (3,3))
    saved_pixel[1, 1] = 0  # unknown, outside new map's view (global (1,1))

    new_pixel = np.full((4, 4), 200, dtype=np.uint8)
    new_pixel[0, 0] = 200  # overlaps saved wall at global (2,2)
    new_pixel[1, 1] = 77  # overlaps saved value(50) at global (3,3): saved must still win
    new_pixel[2, 2] = 255  # global (4,4): saved has no data here -> wall propagates
    new_pixel[3, 3] = 200  # global (5,5): saved has no data here -> collapses to floor(254)

    saved_map_data = SimpleNamespace(
        pixel_type=saved_pixel,
        dimensions=SimpleNamespace(left=0, top=0, width=4, height=4, grid_size=1),
    )
    map_data = _make_map_data(
        pixel_type=new_pixel,
        optimized_pixel_type=None,
        dimensions=SimpleNamespace(left=2, top=2, width=4, height=4, grid_size=1),
    )

    result = optimizer._merge_saved_map_data(map_data, saved_map_data)

    assert result is None  # mutates map_data in place, returns nothing
    merged = map_data.optimized_pixel_type
    assert merged is not None
    assert merged.shape == (6, 6)
    assert merged.dtype == np.uint8

    assert int(merged[0, 0]) == 255  # saved wall preserved, new map has no view there
    assert int(merged[2, 2]) == 254  # saved wall demoted: new map shows non-wall activity
    assert int(merged[3, 3]) == 50  # saved generic value always wins over new
    assert int(merged[1, 1]) == 0  # saved unknown + no new coverage -> stays 0
    assert int(merged[4, 4]) == 255  # saved unknown + new wall -> wall propagates
    assert int(merged[5, 5]) == 254  # saved unknown + new generic value -> floor

    dims = map_data.optimized_dimensions
    assert isinstance(dims, MapImageDimensions)
    assert (dims.top, dims.left, dims.height, dims.width, dims.grid_size) == (0, 0, 6, 6, 1)


def test_merge_saved_map_data_extends_merged_bbox_when_saved_map_is_larger(
    optimizer: DreameVacuumMapOptimizer,
) -> None:
    """
    When the saved map's own bounding box extends further right/down than the new
    map's, the merged bbox (maxX/maxY) must grow to cover the saved map's full extent,
    not just the new map's.
    """
    saved_map_data = SimpleNamespace(
        pixel_type=np.zeros((5, 5), dtype=np.uint8),
        dimensions=SimpleNamespace(left=0, top=0, width=5, height=5, grid_size=1),
    )
    map_data = _make_map_data(
        pixel_type=np.zeros((2, 2), dtype=np.uint8),
        optimized_pixel_type=None,
        dimensions=SimpleNamespace(left=0, top=0, width=2, height=2, grid_size=1),
    )

    optimizer._merge_saved_map_data(map_data, saved_map_data)

    # Merged bbox must cover the saved map's larger extent (5x5), not just the new map's (2x2).
    assert map_data.optimized_pixel_type.shape == (5, 5)
    assert (map_data.optimized_dimensions.height, map_data.optimized_dimensions.width) == (5, 5)


def test_merge_saved_map_data_uses_optimized_pixel_type_when_present(
    optimizer: DreameVacuumMapOptimizer,
) -> None:
    """When map_data.optimized_pixel_type is already set, the merge reads from it, not from pixel_type."""
    saved_map_data = SimpleNamespace(
        pixel_type=np.zeros((2, 2), dtype=np.uint8),  # all unknown, so the new/optimized value always wins
        dimensions=SimpleNamespace(left=0, top=0, width=2, height=2, grid_size=1),
    )

    raw_pixel = np.full((2, 2), 200, dtype=np.uint8)  # would collapse to floor(254) if this were used
    optimized_pixel = np.full((2, 2), 255, dtype=np.uint8)  # collapses to wall(255) since this is used instead

    map_data = _make_map_data(
        pixel_type=raw_pixel,
        optimized_pixel_type=optimized_pixel,
        dimensions=SimpleNamespace(left=0, top=0, width=2, height=2, grid_size=1),
    )

    optimizer._merge_saved_map_data(map_data, saved_map_data)

    assert int(map_data.optimized_pixel_type[0, 0]) == 255


def test_merge_saved_map_data_original_data_marks_isolated_obstacle_as_hidden_wall(
    optimizer: DreameVacuumMapOptimizer,
) -> None:
    """
    original_data[i] == 2 at a merged non-zero cell with no WALL(255) pixel in its
    neighbourhood gets stamped as 251 (OBSTACLE_WALL marker).
    """
    new_pixel = np.full((3, 3), 200, dtype=np.uint8)  # all floors after merge (collapses to 254 everywhere)
    map_data = _make_map_data(
        pixel_type=new_pixel,
        optimized_pixel_type=None,
        dimensions=SimpleNamespace(left=0, top=0, width=3, height=3, grid_size=1),
    )
    # A saved_map_data is required to reach the merge loop at all (early-return guard),
    # but this one contributes nothing (all-zero, identical bbox) so pixel_type values
    # are driven purely by `new_pixel` above.
    saved_map_data = SimpleNamespace(
        pixel_type=np.zeros((3, 3), dtype=np.uint8),
        dimensions=SimpleNamespace(left=0, top=0, width=3, height=3, grid_size=1),
    )

    # Flat, row-major (width-major) original_data matching map_data's own bbox.
    original_data = [0] * 9
    original_data[(1 - 0) * 3 + (1 - 0)] = 2  # center cell (i=1, j=1) flagged as "2"

    optimizer._merge_saved_map_data(map_data, saved_map_data, original_data)

    merged = map_data.optimized_pixel_type
    assert int(merged[1, 1]) == 251  # no WALL(255) neighbour anywhere -> stamped as obstacle-wall
    assert int(merged[0, 0]) == 254  # untouched neighbour keeps its regular merged (floor) value


def test_merge_saved_map_data_original_data_skips_cell_near_existing_wall(
    optimizer: DreameVacuumMapOptimizer,
) -> None:
    """The 251 stamp is only applied when no WALL(255) pixel exists in the local neighbourhood."""
    new_pixel = np.full((3, 3), 200, dtype=np.uint8)
    new_pixel[0, 0] = 255  # a real wall pixel, within the `dis=3` search window of every cell in this 3x3 grid
    map_data = _make_map_data(
        pixel_type=new_pixel,
        optimized_pixel_type=None,
        dimensions=SimpleNamespace(left=0, top=0, width=3, height=3, grid_size=1),
    )
    saved_map_data = SimpleNamespace(
        pixel_type=np.zeros((3, 3), dtype=np.uint8),
        dimensions=SimpleNamespace(left=0, top=0, width=3, height=3, grid_size=1),
    )

    original_data = [0] * 9
    original_data[(1 - 0) * 3 + (1 - 0)] = 2  # center cell flagged as "2"

    optimizer._merge_saved_map_data(map_data, saved_map_data, original_data)

    merged = map_data.optimized_pixel_type
    # A WALL neighbour exists nearby -> the cell keeps its regular first-pass merged value
    # (254, from the floor collapse rule); it is NOT overwritten to 251.
    assert int(merged[1, 1]) == 254


# ---------------------------------------------------------------------------
# optimize(): JS success path building saved_map_data-aware left/top (lines
# skipped by the existing failure-path tests because both maps shared the same
# origin there)
# ---------------------------------------------------------------------------


def test_optimize_js_path_adjusts_origin_to_saved_map_bbox_before_falling_back(
    optimizer: DreameVacuumMapOptimizer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When saved_map_data's bounding box starts further left/up than map_data's own,
    optimize() computes charger_position using the saved map's left/top as the
    merge origin (the `if saved_map_data.dimensions.left < left` / `...top < top`
    branches). Forcing the JS call itself to fail afterwards proves those lines
    ran without raising, and that the fallback still receives both map objects.
    """
    monkeypatch.setattr(MiniRacer, "call", MagicMock(side_effect=RuntimeError("boom")))
    merge_spy = MagicMock()
    monkeypatch.setattr(optimizer, "_merge_saved_map_data", merge_spy)

    map_data = _make_map_data(dimensions=SimpleNamespace(left=10, top=10, width=40, height=30, grid_size=5))
    saved_map_data = _make_map_data(dimensions=SimpleNamespace(left=-5, top=-5, width=40, height=30, grid_size=5))

    result = optimizer.optimize(map_data, saved_map_data)

    assert result is map_data
    merge_spy.assert_called_once_with(map_data, saved_map_data)
