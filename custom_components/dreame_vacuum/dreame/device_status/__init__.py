"""Device status package.

Re-exports :class:`DreameVacuumDeviceStatus`. The original implementation
was a ~3000-line single module; it now lives in ``_core.py`` so the
next refactor pass can split it by domain (consumables, cleaning, map,
docking, water) as mixins without touching call sites.
"""

from __future__ import annotations

from ._core import _BOOLEAN_PROPERTIES, DreameVacuumDeviceStatus

__all__ = ["_BOOLEAN_PROPERTIES", "DreameVacuumDeviceStatus"]
