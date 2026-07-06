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


# ===========================================================================
# dreame/__init__.py — lazy __getattr__ must not mask real import failures
# ===========================================================================


def test_getattr_propagates_import_error():
    """A broken const/vacuum_types lookup must raise its real exception, not
    a misleading AttributeError.

    We cannot force the `from . import const` statement in `__getattr__`
    itself to raise ImportError in-process: dreame/__init__.py's own eager
    top-level imports (`from .device import DreameVacuumDevice`, etc.)
    transitively import const.py/vacuum_types.py, so `const` and
    `vacuum_types` are already bound as attributes on the `dreame` package
    object by the time any test runs (verified: `'const' in dreame_pkg.__dict__`
    is True immediately after `import dreame`, before any lazy attribute is
    ever touched). Deleting that attribute to force a genuine re-import
    instead recurses infinitely: `hasattr(dreame_pkg, 'const')` (inside the
    import machinery) is not found in `__dict__`, so it invokes the package's
    own `__getattr__('const')` per PEP 562, which itself runs
    `from . import const` again, hitting the same `hasattr` check -> infinite
    recursion (verified empirically: RecursionError, not ImportError). This
    is a pre-existing, unrelated latent issue in the lazy-facade design
    (present identically before and after this fix) that is unreachable in
    real usage for the same reason it can't be simulated here.

    So this test exercises the actual guarantee this fix provides: an
    exception other than AttributeError raised while probing an already
    -imported backing module is propagated, not swallowed by
    `except AttributeError: pass`. A substitute object standing in for
    `const` that raises ImportError on attribute access reproduces that
    boundary precisely.
    """
    import custom_components.dreame_vacuum.dreame as dreame_pkg

    name = "THIS_NAME_IS_NOT_CACHED_AND_NOT_REAL_XYZ_012"
    assert name not in dreame_pkg._lazy_imports

    class _BoomOnAccess:
        def __getattr__(self, item):
            raise ImportError("boom: simulated broken const submodule")

    original_const = dreame_pkg.__dict__["const"]
    dreame_pkg.__dict__["const"] = _BoomOnAccess()
    try:
        with pytest.raises(ImportError, match="boom"):
            dreame_pkg.__getattr__(name)
    finally:
        dreame_pkg.__dict__["const"] = original_const

    # Sanity: normal lazy lookups still work after the substitute is removed.
    assert dreame_pkg.PROPERTY_TO_NAME is not None


def test_getattr_unknown_name_still_attribute_error():
    """An unknown symbol still raises AttributeError naming the module."""
    import custom_components.dreame_vacuum.dreame as dreame_pkg

    with pytest.raises(AttributeError, match=r"module '.*dreame' has no attribute 'DOES_NOT_EXIST_XYZ_012'"):
        dreame_pkg.__getattr__("DOES_NOT_EXIST_XYZ_012")
