"""Shared member declarations for the device mixins (type-checking only).

The runtime :class:`~.device.DreameVacuumDevice` is assembled from several
mixins (:mod:`.device_setters`, :mod:`.device_actions`, :mod:`.device_map_ops`)
together with the state created in ``DreameVacuumDevice.__init__``. Because mypy
type-checks each mixin in isolation, cross-mixin access to that shared surface
(``self.status``, ``self.set_property`` …) would otherwise raise hundreds of
``attr-defined`` errors.

:class:`DreameVacuumDeviceState` declares that shared surface for the type
checker only. Its whole body is gated behind :data:`typing.TYPE_CHECKING`, so at
runtime it is an empty class: inheriting from it merely adds an inert node to the
MRO (no attributes, no methods, no ``__init__``) and has zero behavioural
effect. The real attributes and methods are always resolved from
``DreameVacuumDevice`` or a sibling mixin, which precede this class in the MRO.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .device_info import DreameVacuumDeviceInfo
    from .device_status import DreameVacuumDeviceStatus
    from .map_manager import DreameMapVacuumMapManager
    from .protocol import DreameVacuumProtocol
    from .vacuum_types import (
        DirtyData,
        DreameVacuumAction,
        DreameVacuumAIProperty,
        DreameVacuumAutoSwitchProperty,
        DreameVacuumDeviceCapability,
        DreameVacuumProperty,
        DreameVacuumStatus,
        DreameVacuumStrAIProperty,
        DreameVacuumTaskStatus,
    )

    _PropertyKey = (
        DreameVacuumProperty | DreameVacuumAutoSwitchProperty | DreameVacuumStrAIProperty | DreameVacuumAIProperty
    )


class DreameVacuumDeviceState:
    """Type-checking-only view of the surface shared across device mixins.

    Empty at runtime (see module docstring); never instantiate or rely on it
    for behaviour.
    """

    if TYPE_CHECKING:
        # --- Shared state (created in DreameVacuumDevice.__init__) ---
        info: DreameVacuumDeviceInfo | None
        # ``data``/``_dirty_data`` are keyed by the raw numeric property id (``did``),
        # an ``int``; ``DreameVacuumProperty`` is an ``IntEnum`` so enum keys also work.
        data: dict[int, Any]
        # ``auto_switch_data``/``ai_data`` are keyed by the enum member *name* (``prop.name``),
        # a plain ``str`` (``*AutoSwitch*``/``*StrAI*`` are ``StrEnum`` but indexed by name).
        auto_switch_data: dict[str, Any] | None
        ai_data: dict[str, Any] | None
        status: DreameVacuumDeviceStatus
        capability: DreameVacuumDeviceCapability
        property_mapping: dict[DreameVacuumProperty, dict[str, int]]
        action_mapping: dict[DreameVacuumAction, dict[str, int]]
        _protocol: DreameVacuumProtocol
        _map_manager: DreameMapVacuumMapManager | None
        # Timing state shared with the mixins (they assign ``= 0`` / ``time.time()``);
        # declared here so the type is canonical across the whole MRO.
        _last_settings_request: float
        _last_map_list_request: float
        _last_map_request: float
        _last_map_change_time: float | None
        _map_select_time: float | None
        _dirty_data: dict[int, DirtyData]
        _dirty_auto_switch_data: dict[str, DirtyData]
        _dirty_ai_data: dict[str, DirtyData]
        _read_write_properties: list[DreameVacuumProperty]
        _discarded_properties: list[DreameVacuumProperty]

        # --- Shared methods (defined on DreameVacuumDevice or a sibling mixin) ---
        def set_property(self, prop: _PropertyKey, value: Any) -> bool: ...

        def get_property(self, prop: _PropertyKey) -> Any: ...

        def schedule_update(self, wait: float | None = None, force_request_properties: bool = False) -> None: ...

        def _update_property(self, prop: DreameVacuumProperty, value: Any, delay: bool = True) -> Any: ...

        def _property_changed(self, delay: bool = True) -> None: ...

        def _update_status(self, task_status: DreameVacuumTaskStatus, status: DreameVacuumStatus) -> None: ...

        def call_action(
            self, action: DreameVacuumAction, parameters: list[Any] | dict[str, Any] | None = None
        ) -> dict[str, Any] | None: ...

        def set_auto_switch_property(
            self, prop: DreameVacuumAutoSwitchProperty, value: int
        ) -> dict[str, Any] | None: ...

        # --- Read-only properties (defined on DreameVacuumDevice) ---
        @property
        def device_connected(self) -> bool: ...

        @property
        def _update_interval(self) -> float: ...

        @property
        def _map_update_interval(self) -> float: ...

        # --- Static helpers (defined on DreameVacuumDevice) ---
        @staticmethod
        def split_group_value(value: int, mop_pad_lifting: bool = False) -> list[int]: ...

        @staticmethod
        def combine_group_value(values: list[int]) -> int: ...

        # --- Defined on DreameVacuumDeviceSettersMixin (sibling) ---
        def _update_suction_level(self, suction_level: Any) -> bool: ...

        def _update_water_level(self, water_level: Any) -> bool: ...

        def _set_go_to_zone(self, x: Any, y: Any, size: Any) -> None: ...

        def _restore_go_to_zone(self, stop: bool = False) -> None: ...

        # --- Defined on sibling mixins (device_actions / device_map_ops) ---
        def call_stream_property_action(
            self, property: DreameVacuumProperty, parameters: Any = None
        ) -> dict[str, Any] | None: ...

        def update_map_data_async(self, parameters: dict[str, Any]) -> dict[str, Any] | None: ...

        def recovery_map_file(self, map_id: Any, index: Any) -> Any: ...

        def _request_properties(
            self,
            properties: list[DreameVacuumProperty] | None = None,
            force_all: bool = False,
        ) -> bool: ...
