"""Regression guard for Passe 9 (import decoupling).

entity.py used to import homeassistant.components.camera (-> turbojpeg), which made
EVERY platform module unimportable without that native dep. DreameVacuumCameraEntityDescription
was moved to camera.py, so non-camera platforms must now import on their own. If anyone
re-couples entity.py to the camera component, all of these imports fail again.
"""

from __future__ import annotations

import importlib

import pytest

PLATFORM_MODULES = [
    "custom_components.dreame_vacuum.entity",
    "custom_components.dreame_vacuum.switch",
    "custom_components.dreame_vacuum.number",
    "custom_components.dreame_vacuum.select",
    "custom_components.dreame_vacuum.time",
    "custom_components.dreame_vacuum.sensor",
    "custom_components.dreame_vacuum.button",
    "custom_components.dreame_vacuum.binary_sensor",
    "custom_components.dreame_vacuum.vacuum",
]


@pytest.mark.parametrize("module_path", PLATFORM_MODULES)
def test_p9_platform_imports_without_camera_dependency(module_path) -> None:
    """Non-camera platform modules must import without the HA camera/turbojpeg chain."""
    importlib.import_module(module_path)


def test_p9_camera_description_no_longer_lives_in_entity() -> None:
    """The camera-coupled description must not be defined in entity.py anymore."""
    entity = importlib.import_module("custom_components.dreame_vacuum.entity")
    assert not hasattr(entity, "DreameVacuumCameraEntityDescription")
