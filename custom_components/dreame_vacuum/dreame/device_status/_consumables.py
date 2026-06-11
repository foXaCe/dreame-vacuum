"""Consumables-lifecycle mixin for DreameVacuumDeviceStatus.

Reads the ``*_LEFT`` properties that track the remaining percentage of
each replaceable part (brush, filter, mop pad, etc.). Every accessor is
a thin wrapper around ``_get_property``; they live here so the main
``_core.py`` module stops being 3000+ lines of grab-bag properties.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from ..vacuum_types import DreameVacuumProperty


class _ConsumablesMixin:
    """Remaining-life accessors for user-serviceable parts."""

    if TYPE_CHECKING:
        # Provided by DreameVacuumDeviceStatus (_core), which combines the mixins.
        def _get_property(self, prop: DreameVacuumProperty) -> Any: ...

    def _life_property(self, prop: DreameVacuumProperty) -> int:
        """Typed wrapper: every consumable accessor returns an int percentage."""
        return cast(int, self._get_property(prop))

    @property
    def main_brush_life(self) -> int:
        """Returns main brush remaining life in percent."""
        return self._life_property(DreameVacuumProperty.MAIN_BRUSH_LEFT)

    @property
    def side_brush_life(self) -> int:
        """Returns side brush remaining life in percent."""
        return self._life_property(DreameVacuumProperty.SIDE_BRUSH_LEFT)

    @property
    def filter_life(self) -> int:
        """Returns filter remaining life in percent."""
        return self._life_property(DreameVacuumProperty.FILTER_LEFT)

    @property
    def sensor_dirty_life(self) -> int:
        """Returns sensor clean remaining time in percent."""
        return self._life_property(DreameVacuumProperty.SENSOR_DIRTY_LEFT)

    @property
    def tank_filter_life(self) -> int:
        """Returns tank filter remaining life in percent."""
        return self._life_property(DreameVacuumProperty.TANK_FILTER_LEFT)

    @property
    def mop_life(self) -> int:
        """Returns mop remaining life in percent."""
        return self._life_property(DreameVacuumProperty.MOP_PAD_LEFT)

    @property
    def silver_ion_life(self) -> int:
        """Returns silver-ion life in percent."""
        return self._life_property(DreameVacuumProperty.SILVER_ION_LEFT)

    @property
    def detergent_life(self) -> int:
        """Returns detergent life in percent."""
        return self._life_property(DreameVacuumProperty.DETERGENT_LEFT)

    @property
    def squeegee_life(self) -> int:
        """Returns squeegee life in percent."""
        return self._life_property(DreameVacuumProperty.SQUEEGEE_LEFT)

    @property
    def onboard_dirty_water_tank_life(self) -> int:
        """Returns onboard dirty water tank life in percent."""
        return self._life_property(DreameVacuumProperty.ONBOARD_DIRTY_WATER_TANK_LEFT)

    @property
    def dirty_water_tank_life(self) -> int:
        """Returns dirty water tank life in percent."""
        return self._life_property(DreameVacuumProperty.DIRTY_WATER_TANK_LEFT)

    @property
    def deodorizer_life(self) -> int:
        """Returns deodorizer life in percent."""
        return self._life_property(DreameVacuumProperty.DEODORIZER_LEFT)

    @property
    def wheel_dirty_life(self) -> int:
        """Returns wheel life in percent."""
        return self._life_property(DreameVacuumProperty.WHEEL_DIRTY_LEFT)

    @property
    def scale_inhibitor_life(self) -> int:
        """Returns scale inhibitor life in percent."""
        return self._life_property(DreameVacuumProperty.SCALE_INHIBITOR_LEFT)
