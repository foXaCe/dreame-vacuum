"""Tests for the lazy-loading resource wrapper module (dreame/resources.py).

resources.py never eagerly imports the two large backing modules
(_notification_images.py / _resources_data.py); it resolves attribute
access on demand via module __getattr__ and caches the result. These
tests exercise the real lazy-loading success path plus the "primary
relative import fails, fall back to a bare absolute import" branch,
which is otherwise only reachable in exotic packaging situations.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

import custom_components.dreame_vacuum.dreame.resources as resources


@pytest.fixture(autouse=True)
def _reset_resources_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure each test observes a fresh lazy-loading state.

    The module keeps process-wide caches (_notification_module,
    _resources_module, _loaded_attrs, ...); without resetting them a test
    could silently hit the fast-path cache populated by an earlier test
    (or by an unrelated test file that already touched a resource), and
    never actually exercise the loading branch it's meant to test.
    """
    monkeypatch.setattr(resources, "_notification_module", None)
    monkeypatch.setattr(resources, "_resources_module", None)
    monkeypatch.setattr(resources, "_loaded_attrs", {})
    monkeypatch.setattr(resources, "_notification_load_logged", False)
    monkeypatch.setattr(resources, "_resources_load_logged", False)


def test_getattr_loads_notification_attribute() -> None:
    """A name listed in _NOTIFICATION_ATTRS is served from _notification_images."""
    value = resources.CONSUMABLE_IMAGE
    assert value is not None
    # Second access must hit the in-memory cache and return the identical object.
    assert resources.CONSUMABLE_IMAGE is value


def test_getattr_loads_resources_data_attribute() -> None:
    """A name NOT in _NOTIFICATION_ATTRS is served from the larger _resources_data module."""
    value = resources.MAP_FONT
    assert value is not None
    assert "MAP_FONT" in resources._loaded_attrs


def test_getattr_unknown_attribute_raises_attribute_error() -> None:
    with pytest.raises(AttributeError, match="has no attribute 'DOES_NOT_EXIST'"):
        resources.DOES_NOT_EXIST  # noqa: B018


def test_dir_returns_declared_all() -> None:
    assert dir(resources) == resources.__all__


def test_getattr_notification_import_error_falls_back_to_absolute_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate the relative ``from . import _notification_images`` failing.

    Setting the fully-qualified module name to ``None`` in sys.modules is the
    standard trick to force the next `import`/`from ... import` statement
    referencing it to raise ImportError immediately (see PEP 328 / import
    system docs). The bare ``import _notification_images`` fallback then
    resolves via sys.modules too, so pre-seeding a fake module there lets us
    observe which branch actually supplied the value.
    """
    fake_module = MagicMock()
    fake_module.CONSUMABLE_IMAGE = "fallback-notification-value"

    # If an earlier test already imported the real submodule, the parent
    # package object caches it as an attribute; `from . import name` reads
    # that attribute directly and never re-consults sys.modules, so the
    # None-in-sys.modules trick alone would silently no-op. Remove the
    # cached attribute too (monkeypatch restores it after the test).
    parent_pkg = sys.modules["custom_components.dreame_vacuum.dreame"]
    monkeypatch.delattr(parent_pkg, "_notification_images", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "custom_components.dreame_vacuum.dreame._notification_images",
        None,
    )
    monkeypatch.setitem(sys.modules, "_notification_images", fake_module)

    value = resources.CONSUMABLE_IMAGE

    assert value == "fallback-notification-value"
    assert resources._notification_module is fake_module


def test_getattr_resources_import_error_falls_back_to_absolute_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same fallback behaviour for the larger _resources_data backing module."""
    fake_module = MagicMock()
    fake_module.MAP_FONT = "fallback-resources-value"

    parent_pkg = sys.modules["custom_components.dreame_vacuum.dreame"]
    monkeypatch.delattr(parent_pkg, "_resources_data", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "custom_components.dreame_vacuum.dreame._resources_data",
        None,
    )
    monkeypatch.setitem(sys.modules, "_resources_data", fake_module)

    value = resources.MAP_FONT

    assert value == "fallback-resources-value"
    assert resources._resources_module is fake_module
