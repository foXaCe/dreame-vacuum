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
