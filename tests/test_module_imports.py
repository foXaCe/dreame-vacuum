"""Tests for module split backward compatibility.

Verifies that all split modules can be imported and that re-exports
from the original hub modules (map.py, device.py) work correctly.

Note: map modules require py_mini_racer (HA dependency) and are skipped
if not available in the test environment.
"""

from __future__ import annotations

import pytest

# py_mini_racer is a HA runtime dependency not always available in test env
try:
    from custom_components.dreame_vacuum.dreame.map import (
        DreameMapVacuumMapEditor,
        DreameMapVacuumMapManager,
        DreameVacuumMapDataJsonRenderer,
        DreameVacuumMapDecoder,
        DreameVacuumMapOptimizer,
        DreameVacuumMapRenderer,
    )

    HAS_MAP_DEPS = True
except ImportError:
    HAS_MAP_DEPS = False


@pytest.mark.skipif(not HAS_MAP_DEPS, reason="py_mini_racer not installed")
def test_map_hub_reexports():
    """Test that map.py re-exports all split classes."""
    assert DreameMapVacuumMapManager is not None
    assert DreameMapVacuumMapEditor is not None
    assert DreameVacuumMapDecoder is not None
    assert DreameVacuumMapRenderer is not None
    assert DreameVacuumMapDataJsonRenderer is not None
    assert DreameVacuumMapOptimizer is not None


@pytest.mark.skipif(not HAS_MAP_DEPS, reason="py_mini_racer not installed")
def test_map_direct_imports():
    """Test that split map modules can be imported directly."""
    from custom_components.dreame_vacuum.dreame.map_data_json_renderer import DreameVacuumMapDataJsonRenderer
    from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
    from custom_components.dreame_vacuum.dreame.map_editor import DreameMapVacuumMapEditor
    from custom_components.dreame_vacuum.dreame.map_manager import DreameMapVacuumMapManager
    from custom_components.dreame_vacuum.dreame.map_optimizer import DreameVacuumMapOptimizer
    from custom_components.dreame_vacuum.dreame.map_renderer import DreameVacuumMapRenderer

    assert callable(DreameMapVacuumMapManager)
    assert callable(DreameMapVacuumMapEditor)
    assert callable(DreameVacuumMapDecoder)
    assert callable(DreameVacuumMapRenderer)
    assert callable(DreameVacuumMapDataJsonRenderer)
    assert callable(DreameVacuumMapOptimizer)


@pytest.mark.skipif(not HAS_MAP_DEPS, reason="py_mini_racer not installed")
def test_map_hub_matches_direct():
    """Test that hub re-exports point to the same classes as direct imports."""
    from custom_components.dreame_vacuum.dreame.map import DreameVacuumMapRenderer as HubRenderer
    from custom_components.dreame_vacuum.dreame.map_renderer import DreameVacuumMapRenderer as DirectRenderer

    assert HubRenderer is DirectRenderer


def test_device_hub_reexports():
    """Test that device.py re-exports split classes."""
    from custom_components.dreame_vacuum.dreame.device import (
        DreameVacuumDeviceInfo,
        DreameVacuumDeviceStatus,
    )

    assert DreameVacuumDeviceStatus is not None
    assert DreameVacuumDeviceInfo is not None


def test_device_direct_imports():
    """Test that split device modules can be imported directly."""
    from custom_components.dreame_vacuum.dreame.device_info import DreameVacuumDeviceInfo
    from custom_components.dreame_vacuum.dreame.device_status import DreameVacuumDeviceStatus

    assert callable(DreameVacuumDeviceStatus)
    assert callable(DreameVacuumDeviceInfo)


def test_device_hub_matches_direct():
    """Test that device hub re-exports point to the same classes as direct imports."""
    from custom_components.dreame_vacuum.dreame.device import DreameVacuumDeviceStatus as HubStatus
    from custom_components.dreame_vacuum.dreame.device_status import DreameVacuumDeviceStatus as DirectStatus

    assert HubStatus is DirectStatus
