"""Tests for platform entity setup and configuration.

These modules are imported directly: mini-racer/PIL/numpy are installed in
the dev venv, so a broken import here is a real regression and must fail the
test rather than being silently skipped. The single genuinely optional
runtime dependency (``turbojpeg``, native and not installed in every dev
environment) is skipped explicitly via ``pytest.importorskip``.
"""

from __future__ import annotations

import pytest


def test_vacuum_entity_description_imports():
    """Test that vacuum entity descriptions can be imported."""
    from custom_components.dreame_vacuum.vacuum import DreameVacuumEntity

    assert DreameVacuumEntity is not None


def test_sensor_entity_description_imports():
    """Test that sensor entity descriptions can be imported."""
    from custom_components.dreame_vacuum.sensor import SENSORS

    assert len(SENSORS) > 0


def test_camera_entity_imports():
    """Test that camera entity can be imported."""
    pytest.importorskip("turbojpeg", reason="camera platform requires turbojpeg")
    from custom_components.dreame_vacuum.camera import DreameVacuumCameraEntity

    assert DreameVacuumCameraEntity is not None


def test_switch_entity_imports():
    """Test that switch entities can be imported."""
    from custom_components.dreame_vacuum.switch import SWITCHES

    assert SWITCHES is not None


def test_button_entity_imports():
    """Test that button entities can be imported."""
    from custom_components.dreame_vacuum.button import BUTTONS

    assert BUTTONS is not None


def test_number_entity_imports():
    """Test that number entities can be imported."""
    from custom_components.dreame_vacuum.number import NUMBERS

    assert NUMBERS is not None


def test_select_entity_imports():
    """Test that select entities can be imported."""
    from custom_components.dreame_vacuum.select import SELECTS

    assert SELECTS is not None
