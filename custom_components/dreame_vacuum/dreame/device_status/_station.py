"""Station bay status enum accessors for DreameVacuumDeviceStatus.

Wraps the raw ``*_STATUS`` properties reported by the dock/station bays
(clean-water tank, dirty-water tank, dust bag, detergent reservoir,
hot-water module) into their typed enum counterparts, with a matching
``*_name`` accessor for translation lookups.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..const import (
    CLEAN_WATER_TANK_STATUS_TO_NAME,
    DETERGENT_STATUS_TO_NAME,
    DIRTY_WATER_TANK_STATUS_TO_NAME,
    DUST_BAG_STATUS_TO_NAME,
    HOT_WATER_STATUS_TO_NAME,
    STATE_UNKNOWN,
)
from ..vacuum_types import (
    DreameVacuumCleanWaterTankStatus,
    DreameVacuumDetergentStatus,
    DreameVacuumDirtyWaterTankStatus,
    DreameVacuumDustBagStatus,
    DreameVacuumHotWaterStatus,
    DreameVacuumProperty,
)


class _StationMixin:
    """Typed enum + name accessors for dock/station bay statuses."""

    if TYPE_CHECKING:
        # Provided by DreameVacuumDeviceStatus (_core), which combines the mixins.
        def _get_property(self, prop: DreameVacuumProperty) -> Any: ...

    @property
    def clean_water_tank_status(self) -> DreameVacuumCleanWaterTankStatus:
        """Return clean water tank status of the device."""
        value = self._get_property(DreameVacuumProperty.CLEAN_WATER_TANK_STATUS)
        if value is not None and value in DreameVacuumCleanWaterTankStatus._value2member_map_:
            if value == DreameVacuumCleanWaterTankStatus.ACTIVE.value:
                value = DreameVacuumCleanWaterTankStatus.INSTALLED.value
            return DreameVacuumCleanWaterTankStatus(value)
        return DreameVacuumCleanWaterTankStatus.UNKNOWN

    @property
    def clean_water_tank_status_name(self) -> str:
        """Return clean water tank status as string for translation."""
        return CLEAN_WATER_TANK_STATUS_TO_NAME.get(self.clean_water_tank_status, STATE_UNKNOWN)

    @property
    def dirty_water_tank_status(self) -> DreameVacuumDirtyWaterTankStatus:
        """Return dirty water tank status of the device."""
        value = self._get_property(DreameVacuumProperty.DIRTY_WATER_TANK_STATUS)
        if value is not None and value in DreameVacuumDirtyWaterTankStatus._value2member_map_:
            return DreameVacuumDirtyWaterTankStatus(value)
        return DreameVacuumDirtyWaterTankStatus.UNKNOWN

    @property
    def dirty_water_tank_status_name(self) -> str:
        """Return dirty water tank status as string for translation."""
        return DIRTY_WATER_TANK_STATUS_TO_NAME.get(self.dirty_water_tank_status, STATE_UNKNOWN)

    @property
    def dust_bag_status(self) -> DreameVacuumDustBagStatus:
        """Return dust bag status of the device."""
        value = self._get_property(DreameVacuumProperty.DUST_BAG_STATUS)
        if value is not None and value in DreameVacuumDustBagStatus._value2member_map_:
            return DreameVacuumDustBagStatus(value)
        return DreameVacuumDustBagStatus.UNKNOWN

    @property
    def dust_bag_status_name(self) -> str:
        """Return dust bag status as string for translation."""
        return DUST_BAG_STATUS_TO_NAME.get(self.dust_bag_status, STATE_UNKNOWN)

    @property
    def detergent_status(self) -> DreameVacuumDetergentStatus:
        """Return detergent status of the device."""
        value = self._get_property(DreameVacuumProperty.DETERGENT_STATUS)
        if value is not None and value in DreameVacuumDetergentStatus._value2member_map_:
            return DreameVacuumDetergentStatus(value)
        return DreameVacuumDetergentStatus.UNKNOWN

    @property
    def detergent_status_name(self) -> str:
        """Return detergent status as string for translation."""
        return DETERGENT_STATUS_TO_NAME.get(self.detergent_status, STATE_UNKNOWN)

    @property
    def hot_water_status(self) -> DreameVacuumHotWaterStatus:
        """Return hot water status of the device."""
        value = self._get_property(DreameVacuumProperty.HOT_WATER_STATUS)
        if value is not None and value in DreameVacuumHotWaterStatus._value2member_map_:
            return DreameVacuumHotWaterStatus(value)
        return DreameVacuumHotWaterStatus.UNKNOWN

    @property
    def hot_water_status_name(self) -> str:
        """Return hot water status as string for translation."""
        return HOT_WATER_STATUS_TO_NAME.get(self.hot_water_status, STATE_UNKNOWN)
