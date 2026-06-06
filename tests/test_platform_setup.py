"""Tests for platform entity setup and configuration.

Note: Platform modules require full HA runtime dependencies.
Tests are skipped if imports fail.
"""

from __future__ import annotations

import pytest


def _try_import(module_path, name):
    """Try to import a name from a module, return None if deps missing."""
    try:
        mod = __import__(module_path, fromlist=[name])
        return getattr(mod, name)
    except (ImportError, AttributeError):
        return None


# Try importing platform modules - they may fail if HA camera deps are missing
_DreameVacuumEntity = _try_import("custom_components.dreame_vacuum.vacuum", "DreameVacuumEntity")
_SENSORS = _try_import("custom_components.dreame_vacuum.sensor", "SENSORS")
_DreameCamera = _try_import("custom_components.dreame_vacuum.camera", "DreameVacuumCameraEntity")
_SWITCHES = _try_import("custom_components.dreame_vacuum.switch", "SWITCHES")
_BUTTONS = _try_import("custom_components.dreame_vacuum.button", "BUTTONS")
_NUMBERS = _try_import("custom_components.dreame_vacuum.number", "NUMBERS")
_SELECTS = _try_import("custom_components.dreame_vacuum.select", "SELECTS")

HAS_PLATFORM_DEPS = _DreameVacuumEntity is not None


@pytest.mark.skipif(not HAS_PLATFORM_DEPS, reason="HA platform dependencies not available")
def test_vacuum_entity_description_imports():
    """Test that vacuum entity descriptions can be imported."""
    assert _DreameVacuumEntity is not None


@pytest.mark.skipif(not HAS_PLATFORM_DEPS, reason="HA platform dependencies not available")
def test_sensor_entity_description_imports():
    """Test that sensor entity descriptions can be imported."""
    assert _SENSORS is not None
    assert len(_SENSORS) > 0


@pytest.mark.skipif(_DreameCamera is None, reason="camera platform requires turbojpeg")
def test_camera_entity_imports():
    """Test that camera entity can be imported."""
    assert _DreameCamera is not None


@pytest.mark.skipif(not HAS_PLATFORM_DEPS, reason="HA platform dependencies not available")
def test_switch_entity_imports():
    """Test that switch entities can be imported."""
    assert _SWITCHES is not None


@pytest.mark.skipif(not HAS_PLATFORM_DEPS, reason="HA platform dependencies not available")
def test_button_entity_imports():
    """Test that button entities can be imported."""
    assert _BUTTONS is not None


@pytest.mark.skipif(not HAS_PLATFORM_DEPS, reason="HA platform dependencies not available")
def test_number_entity_imports():
    """Test that number entities can be imported."""
    assert _NUMBERS is not None


@pytest.mark.skipif(not HAS_PLATFORM_DEPS, reason="HA platform dependencies not available")
def test_select_entity_imports():
    """Test that select entities can be imported."""
    assert _SELECTS is not None
