"""Activity/state boolean accessors for DreameVacuumDeviceStatus.

Booleans that describe what the device is currently doing (sweeping,
mopping, returning, washing, ...), derived from the enum-valued
properties in ``_named_props``. Extracted from the monolithic
``_core.py`` module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..vacuum_types import (
    DreameVacuumAutoEmptyStatus,
    DreameVacuumChargingStatus,
    DreameVacuumCleaningMode,
    DreameVacuumDrainageStatus,
    DreameVacuumProperty,
    DreameVacuumRelocationStatus,
    DreameVacuumSelfWashBaseStatus,
    DreameVacuumState,
    DreameVacuumStatus,
    DreameVacuumTaskStatus,
)


class _ActivityMixin:
    """Boolean accessors describing the device's current activity/state."""

    if TYPE_CHECKING:
        # Provided by DreameVacuumDeviceStatus (_core) and its other mixins.
        def _get_property(self, prop: Any) -> Any: ...

        _capability: Any
        _device: Any
        _device_connected: bool
        go_to_zone: Any
        shortcuts: Any

        relocation_status: DreameVacuumRelocationStatus
        fast_mapping: bool
        cleaning_mode: DreameVacuumCleaningMode | None
        water_tank_or_mop_installed: bool
        task_status: DreameVacuumTaskStatus
        status: DreameVacuumStatus
        drainage_status: DreameVacuumDrainageStatus
        self_wash_base_status: DreameVacuumSelfWashBaseStatus
        charging_status: DreameVacuumChargingStatus
        battery_level: int
        auto_empty_status: DreameVacuumAutoEmptyStatus
        state: DreameVacuumState

    @property
    def located(self) -> bool:
        """Returns true when robot knows its position on current map."""
        relocation_status = self.relocation_status
        return bool(
            relocation_status is DreameVacuumRelocationStatus.LOCATED
            or relocation_status is DreameVacuumRelocationStatus.UNKNOWN
            or self.fast_mapping
        )

    @property
    def sweeping(self) -> bool:
        """Returns true when cleaning mode is sweeping therefore cannot set its water volume."""
        cleaning_mode = self.cleaning_mode
        if cleaning_mode is None:
            return not self.water_tank_or_mop_installed
        return bool(
            cleaning_mode is not DreameVacuumCleaningMode.MOPPING
            and cleaning_mode is not DreameVacuumCleaningMode.SWEEPING_AND_MOPPING
            and cleaning_mode is not DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING
        )

    @property
    def mopping(self) -> bool:
        """Returns true when cleaning mode is mopping therefore cannot set its suction level."""
        return bool(self.cleaning_mode is DreameVacuumCleaningMode.MOPPING)

    @property
    def mopping_after_sweeping(self) -> bool:
        """Returns true when cleaning mode is mopping after sweeping therefore cannot change the cleaning mode when active."""
        return bool(self.cleaning_mode is DreameVacuumCleaningMode.MOPPING_AFTER_SWEEPING)

    @property
    def zone_cleaning(self) -> bool:
        """Returns true when device is currently performing a zone cleaning task."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and self.started
            and (
                task_status is DreameVacuumTaskStatus.ZONE_CLEANING
                or task_status is DreameVacuumTaskStatus.ZONE_CLEANING_PAUSED
                or task_status is DreameVacuumTaskStatus.ZONE_MOPPING_PAUSED
                or task_status is DreameVacuumTaskStatus.ZONE_DOCKING_PAUSED
            )
        )

    @property
    def spot_cleaning(self) -> bool:
        """Returns true when device is currently performing a spot cleaning task."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and self.started
            and (
                task_status is DreameVacuumTaskStatus.SPOT_CLEANING
                or task_status is DreameVacuumTaskStatus.SPOT_CLEANING_PAUSED
                or self.status is DreameVacuumStatus.SPOT_CLEANING
            )
        )

    @property
    def segment_cleaning(self) -> bool:
        """Returns true when device is currently performing a custom segment cleaning task."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and self.started
            and (
                task_status is DreameVacuumTaskStatus.SEGMENT_CLEANING
                or task_status is DreameVacuumTaskStatus.SEGMENT_CLEANING_PAUSED
                or task_status is DreameVacuumTaskStatus.SEGMENT_MOPPING_PAUSED
                or task_status is DreameVacuumTaskStatus.SEGMENT_DOCKING_PAUSED
            )
        )

    @property
    def auto_cleaning(self) -> bool:
        """Returns true when device is currently performing a complete map cleaning task."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and self.started
            and (
                task_status is DreameVacuumTaskStatus.AUTO_CLEANING
                or task_status is DreameVacuumTaskStatus.AUTO_CLEANING_PAUSED
                or task_status is DreameVacuumTaskStatus.AUTO_MOPPING_PAUSED
                or task_status is DreameVacuumTaskStatus.AUTO_DOCKING_PAUSED
            )
        )

    @property
    def fast_mapping(self) -> bool:
        """Returns true when device is creating a new map."""
        return bool(
            self._device_connected
            and (
                self.task_status is DreameVacuumTaskStatus.FAST_MAPPING
                or self.status is DreameVacuumStatus.FAST_MAPPING
                or self.fast_mapping_paused
            )
        )

    @property
    def fast_mapping_paused(self) -> bool:
        """Returns true when creating a new map paused by user.
        Used for resuming fast cleaning on start because standard start action can not be used for resuming fast mapping.
        """

        state = self._get_property(DreameVacuumProperty.STATE)
        task_status = self.task_status
        return bool(
            (
                task_status is DreameVacuumTaskStatus.FAST_MAPPING
                or task_status is DreameVacuumTaskStatus.MAP_CLEANING_PAUSED
            )
            and (
                state == DreameVacuumState.PAUSED.value
                or state == DreameVacuumState.ERROR.value
                or state == DreameVacuumState.IDLE.value
            )
        )

    @property
    def draining(self) -> bool:
        """Returns true when device has a self-wash base and draining is performing."""
        return bool(self._capability.drainage and self.drainage_status is DreameVacuumDrainageStatus.DRAINING)

    @property
    def draining_complete(self) -> bool:
        """Returns true when device has a self-wash base and draining is performing."""
        return bool(
            self._capability.drainage
            and (
                self.drainage_status is DreameVacuumDrainageStatus.DRAINING_FAILED
                or self.drainage_status is DreameVacuumDrainageStatus.DRAINING_SUCCESS
            )
        )

    @property
    def self_repairing(self) -> bool:
        """Returns true when device is self repairing/testing or water checking."""
        status = self.status
        return bool(
            status is DreameVacuumStatus.SELF_REPAIR
            or status is DreameVacuumStatus.WATER_CHECK
            or self.state is DreameVacuumState.WATER_CHECK
        )

    @property
    def station_cleaning(self) -> bool:
        """Returns true when base station is cleaning."""
        task_status = self.task_status
        return bool(task_status is DreameVacuumTaskStatus.STATION_CLEANING)

    @property
    def cruising(self) -> bool:
        """Returns true when device is cruising."""
        if self._capability.cruising:
            task_status = self.task_status
            status = self.status
            return bool(
                task_status is DreameVacuumTaskStatus.CRUISING_PATH
                or task_status is DreameVacuumTaskStatus.CRUISING_POINT
                or task_status is DreameVacuumTaskStatus.CRUISING_PATH_PAUSED
                or task_status is DreameVacuumTaskStatus.CRUISING_POINT_PAUSED
                or status is DreameVacuumStatus.CRUISING_PATH
                or status is DreameVacuumStatus.CRUISING_POINT
            )
        return bool(self.go_to_zone)

    @property
    def cruising_paused(self) -> bool:
        """Returns true when cruising paused."""
        if self._capability.cruising:
            task_status = self.task_status
            return bool(
                task_status is DreameVacuumTaskStatus.CRUISING_PATH_PAUSED
                or task_status is DreameVacuumTaskStatus.CRUISING_POINT_PAUSED
            )
        if self.go_to_zone:
            status = self.status
            if self.started and (
                status is DreameVacuumStatus.PAUSED
                or status is DreameVacuumStatus.SLEEPING
                or status is DreameVacuumStatus.IDLE
                or status is DreameVacuumStatus.STANDBY
            ):
                return True
        return False

    @property
    def resume_cleaning(self) -> bool:
        """Returns true when resume_cleaning is enabled."""
        return bool(
            self._get_property(DreameVacuumProperty.RESUME_CLEANING) == (2 if self._capability.auto_charging else 1)
        )

    @property
    def mop_in_station(self) -> bool:
        """Returns true when the mop pad is in the station."""
        value = self._get_property(DreameVacuumProperty.MOP_IN_STATION)
        return bool(value == 1 or value == 4) and not self.docked

    @property
    def cleaning_paused(self) -> bool:
        """Returns true when device battery is too low for resuming its task and needs to be charged before continuing."""
        return bool(self._get_property(DreameVacuumProperty.CLEANING_PAUSED))

    @property
    def charging(self) -> bool:
        """Returns true when device is currently charging."""
        return bool(self.charging_status is DreameVacuumChargingStatus.CHARGING and self.battery_level < 100)

    @property
    def docked(self) -> bool:
        """Returns true when device is docked."""
        return bool(
            (
                self.charging
                or self.charging_status is DreameVacuumChargingStatus.CHARGING_COMPLETED
                or self.washing
                or self.drying
                or self.washing_paused
            )
            and not (self.running and not self.returning and not self.fast_mapping and not self.cruising)
        )

    @property
    def sleeping(self) -> bool:
        """Returns true when device is sleeping."""
        return bool(self.status is DreameVacuumStatus.SLEEPING)

    @property
    def returning_paused(self) -> bool:
        """Returns true when returning to dock is paused."""
        task_status = self.task_status
        return bool(
            self._device_connected
            and not self.docked
            and (
                task_status is DreameVacuumTaskStatus.DOCKING_PAUSED
                or task_status is DreameVacuumTaskStatus.AUTO_DOCKING_PAUSED
                or task_status is DreameVacuumTaskStatus.SEGMENT_DOCKING_PAUSED
                or task_status is DreameVacuumTaskStatus.ZONE_DOCKING_PAUSED
            )
        )

    @property
    def returning(self) -> bool:
        """Returns true when returning to dock for charging or washing."""
        return bool(
            self._device_connected
            and (self.status is DreameVacuumStatus.BACK_HOME or self.returning_to_wash)
            and not self.docked
        )

    @property
    def started(self) -> bool:
        """Returns true when device has an active task.
        Used for preventing updates on settings that relates to currently performing task.
        """
        status = self.status
        return bool(
            (
                self.task_status is not DreameVacuumTaskStatus.COMPLETED
                and self.task_status is not DreameVacuumTaskStatus.DOCKING_PAUSED
            )
            or self.cleaning_paused
            or status is DreameVacuumStatus.CLEANING
            or status is DreameVacuumStatus.SEGMENT_CLEANING
            or status is DreameVacuumStatus.ZONE_CLEANING
            or status is DreameVacuumStatus.SPOT_CLEANING
            or status is DreameVacuumStatus.PART_CLEANING
            or status is DreameVacuumStatus.FAST_MAPPING
            or status is DreameVacuumStatus.CRUISING_PATH
            or status is DreameVacuumStatus.CRUISING_POINT
            or status is DreameVacuumStatus.SHORTCUT
        )

    @property
    def paused(self) -> bool:
        """Returns true when device has an active paused task."""
        status = self.status
        return bool(
            self.cleaning_paused
            or self.cruising_paused
            or (
                self.started
                and (
                    status is DreameVacuumStatus.PAUSED
                    or status is DreameVacuumStatus.SLEEPING
                    or status is DreameVacuumStatus.IDLE
                    or status is DreameVacuumStatus.STANDBY
                )
            )
        )

    @property
    def active(self) -> bool:
        """Returns true when device is moving or not sleeping."""
        return self.status is DreameVacuumStatus.STANDBY or self.running

    @property
    def running(self) -> bool:
        """Returns true when device is moving."""
        status = self.status
        return bool(
            not (
                self.charging
                or self.charging_status is DreameVacuumChargingStatus.CHARGING_COMPLETED
                or self.washing
                or self.drying
                or self.washing_paused
            )
            and (
                status is DreameVacuumStatus.CLEANING
                or status is DreameVacuumStatus.BACK_HOME
                or status is DreameVacuumStatus.PART_CLEANING
                or status is DreameVacuumStatus.FOLLOW_WALL
                or status is DreameVacuumStatus.REMOTE_CONTROL
                or status is DreameVacuumStatus.SEGMENT_CLEANING
                or status is DreameVacuumStatus.ZONE_CLEANING
                or status is DreameVacuumStatus.SPOT_CLEANING
                or status is DreameVacuumStatus.FAST_MAPPING
                or status is DreameVacuumStatus.CRUISING_PATH
                or status is DreameVacuumStatus.CRUISING_POINT
                or status is DreameVacuumStatus.SUMMON_CLEAN
                or status is DreameVacuumStatus.SHORTCUT
                or status is DreameVacuumStatus.PERSON_FOLLOW
            )
        )

    @property
    def shortcut_task(self) -> bool:
        """Returns true when device has an active shortcut task."""
        if self.started and self.shortcuts:
            for _k, v in self.shortcuts.items():
                if v.running:
                    return True
        return False

    @property
    def auto_emptying(self) -> bool:
        """Returns true when device is auto emptying."""
        return bool(self.auto_empty_status is DreameVacuumAutoEmptyStatus.ACTIVE)

    @property
    def auto_emptying_not_performed(self) -> bool:
        """Returns true when auto emptying is not performed due to DND settings."""
        return bool(self.auto_empty_status is DreameVacuumAutoEmptyStatus.NOT_PERFORMED)

    @property
    def washing(self) -> bool:
        """Returns true the when device is currently performing mop washing."""
        return bool(
            self._capability.self_wash_base
            and (
                self.self_wash_base_status is DreameVacuumSelfWashBaseStatus.WASHING
                or self.self_wash_base_status is DreameVacuumSelfWashBaseStatus.CLEAN_ADD_WATER
            )
        )

    @property
    def drying(self) -> bool:
        """Returns true the when device is currently performing mop drying."""
        return bool(
            self._capability.self_wash_base and self.self_wash_base_status is DreameVacuumSelfWashBaseStatus.DRYING
        )

    @property
    def washing_paused(self) -> bool:
        """Returns true when mop washing paused."""
        return bool(
            self._capability.self_wash_base and self.self_wash_base_status is DreameVacuumSelfWashBaseStatus.PAUSED
        )

    @property
    def returning_to_wash(self) -> bool:
        """Returns true when the device returning to self-wash base to wash or dry its mop."""
        return bool(
            self._capability.self_wash_base
            and self.self_wash_base_status is DreameVacuumSelfWashBaseStatus.RETURNING
            and (self.state is DreameVacuumState.RETURNING or self.state is DreameVacuumState.RETURNING_TO_WASH)
        )

    @property
    def returning_to_wash_paused(self) -> bool:
        """Returns true when the device returning to self-wash base to wash or dry its mop."""
        return bool(
            self._capability.self_wash_base
            and self.self_wash_base_status is DreameVacuumSelfWashBaseStatus.RETURNING
            and self.state is DreameVacuumState.PAUSED
        )

    @property
    def washing_available(self) -> bool:
        """Returns true when device has a self-wash base and washing mop can be performed."""
        return bool(
            self._capability.self_wash_base
            and (self.water_tank_or_mop_installed or self.mop_in_station)
            and not (
                self.washing
                or self.washing_paused
                or self.returning_to_wash_paused
                or self.returning_to_wash
                or self.returning
                or self.returning_paused
                or self.cleaning_paused
                # or self.drying
            )
        )

    @property
    def drying_available(self) -> bool:
        """Returns true when device has a self-wash base and drying mop can be performed."""
        return bool(
            self._capability.self_wash_base
            and self.water_tank_or_mop_installed
            and self.docked
            and not (self.washing or self.washing_paused)
            and not self.started
        )
