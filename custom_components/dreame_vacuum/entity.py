"""Base entity classes for Dreame Vacuum integration.

This module provides the base entity class and entity description dataclass
that all Dreame Vacuum entities inherit from. It handles common functionality
like device info, availability, and state attributes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.components.number import NumberEntityDescription
from homeassistant.components.select import SelectEntityDescription
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.components.time import TimeEntityDescription
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import EntityDescription, async_generate_entity_id
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LOGGER
from .coordinator import DreameVacuumDataUpdateCoordinator
from .dreame import (
    ACTION_AVAILABILITY,
    ACTION_TO_NAME,
    PROPERTY_AVAILABILITY,
    PROPERTY_TO_NAME,
    DeviceException,
    DeviceUpdateFailedException,
    DreameVacuumAction,
    DreameVacuumAIProperty,
    DreameVacuumAutoSwitchProperty,
    DreameVacuumDevice,
    DreameVacuumProperty,
    DreameVacuumStrAIProperty,
    InvalidActionException,
    InvalidValueException,
)
from .dreame.const import ATTR_VALUE


def default_exists_fn(description: Any, device: Any) -> bool:
    """Default exists function for entity descriptions."""
    return bool(
        (description.action_key is not None and description.action_key in device.action_mapping)
        or description.property_key is None
        or (
            isinstance(description.property_key, DreameVacuumProperty)
            and (
                description.property_key.value in device.data
                or description.property_key.value in device.pending_properties
            )
        )
        or (
            isinstance(description.property_key, DreameVacuumAutoSwitchProperty)
            and device.auto_switch_data
            and description.property_key.name in device.auto_switch_data
        )
        or (
            (isinstance(description.property_key, (DreameVacuumStrAIProperty, DreameVacuumAIProperty)))
            and device.ai_data
            and description.property_key.name in device.ai_data
        )
    )


# Mixin class for Dreame-specific fields (used with HA EntityDescription classes)
@dataclass(frozen=True, kw_only=True)
class DreameVacuumEntityDescriptionMixin:
    """Mixin for Dreame Vacuum entity descriptions."""

    property_key: DreameVacuumProperty | None = None
    action_key: DreameVacuumAction | None = None
    exists_fn: Callable[[Any, Any], bool] = field(default=default_exists_fn)
    value_fn: Callable[[Any, Any], Any] | None = None
    value_int_fn: Callable[[Any, Any], int | None] | None = None
    format_fn: Callable[[Any, Any], Any] | None = None
    available_fn: Callable[[Any], bool] | None = None
    icon_fn: Callable[[Any, Any], str] | None = None
    name_fn: Callable[[str, Any], str] | None = None
    attrs_fn: Callable[[Any], dict[str, Any] | None] | None = None


# Platform-specific entity descriptions that inherit from HA classes
@dataclass(frozen=True, kw_only=True)
class DreameVacuumEntityDescription(EntityDescription, DreameVacuumEntityDescriptionMixin):
    """Base description for Dreame Vacuum entities."""

    key: str = ""  # Override to provide default


@dataclass(frozen=True, kw_only=True)
class DreameVacuumSensorEntityDescription(SensorEntityDescription, DreameVacuumEntityDescription):
    """Describes Dreame Vacuum Sensor entity."""

    key: str = ""


@dataclass(frozen=True, kw_only=True)
class DreameVacuumBinarySensorEntityDescription(BinarySensorEntityDescription, DreameVacuumEntityDescription):
    """Describes Dreame Vacuum BinarySensor entity."""

    key: str = ""


@dataclass(frozen=True, kw_only=True)
class DreameVacuumSwitchEntityDescription(SwitchEntityDescription, DreameVacuumEntityDescription):
    """Describes Dreame Vacuum Switch entity."""

    key: str = ""
    set_fn: Callable[[Any, int], None] | None = None


@dataclass(frozen=True, kw_only=True)
class DreameVacuumButtonEntityDescription(ButtonEntityDescription, DreameVacuumEntityDescription):
    """Describes Dreame Vacuum Button entity."""

    key: str = ""
    action_fn: Callable[[Any], None] | None = None


@dataclass(frozen=True, kw_only=True)
class DreameVacuumSelectEntityDescription(SelectEntityDescription, DreameVacuumEntityDescription):
    """Describes Dreame Vacuum Select entity."""

    key: str = ""
    set_fn: Callable[[Any, int, int], None] | None = None
    options: Callable[[Any, Any], list[str]] | None = None  # type: ignore[assignment]
    segment_available_fn: Callable[[Any, Any], bool] | None = None
    segment_list_fn: Callable[[Any], Any] | None = None
    segment_icon_fn: Callable[[Any, Any, Any], str] | None = None


@dataclass(frozen=True, kw_only=True)
class DreameVacuumNumberEntityDescription(NumberEntityDescription, DreameVacuumEntityDescription):
    """Describes Dreame Vacuum Number entity."""

    key: str = ""
    set_fn: Callable[[Any, int], None] | None = None
    max_value_fn: Callable[[Any], int] | None = None
    min_value_fn: Callable[[Any], int] | None = None
    segment_available_fn: Callable[[Any, Any], bool] | None = None
    segment_list_fn: Callable[[Any], Any] | None = None
    segment_icon_fn: Callable[[Any, Any, Any], str] | None = None


@dataclass(frozen=True, kw_only=True)
class DreameVacuumTimeEntityDescription(TimeEntityDescription, DreameVacuumEntityDescription):
    """Describes Dreame Vacuum Time entity."""

    key: str = ""
    set_fn: Callable[[Any, int], None] | None = None


class DreameVacuumEntity(CoordinatorEntity[DreameVacuumDataUpdateCoordinator]):
    """Defines a base Dreame Vacuum entity."""

    __slots__ = (
        "_computed_available_fn",
        "_computed_key",
        "_computed_name",
        "_computed_value_fn",
        "entity_description",
    )

    _attr_has_entity_name = True
    entity_description: DreameVacuumEntityDescription

    def __init__(
        self,
        coordinator: DreameVacuumDataUpdateCoordinator,
        # Platform descriptions are ``<Platform>EntityDescription + Mixin`` (not a
        # subtype of DreameVacuumEntityDescription); typed Any so every platform can
        # pass its own description. Each platform narrows ``entity_description`` for
        # precise field access.
        description: Any = None,
    ) -> None:
        # Store computed values as instance attributes (descriptions are frozen)
        self._computed_key: str | None = None
        self._computed_name: str | None = None
        self._computed_value_fn: Callable[[Any, Any], Any] | None = None
        self._computed_available_fn: Callable[[Any], bool] | None = None

        if description is not None:
            # Compute key if not provided
            if description.key is None or description.key == "":
                if description.property_key is not None:
                    name = PROPERTY_TO_NAME.get(description.property_key.name)
                    if name:
                        self._computed_key = name[0]
                        self._computed_name = name[1]
                    else:
                        self._computed_key = description.property_key.name.lower()
                elif description.action_key is not None:
                    name = ACTION_TO_NAME.get(description.action_key)
                    if name:
                        self._computed_key = name[0]
                        self._computed_name = name[1]
                    else:
                        self._computed_key = description.action_key.name.lower()
            else:
                self._computed_key = description.key

            # Compute name if not provided (UNDEFINED means translation_key handles naming)
            if description.name is None or description.name is UNDEFINED:
                if self._computed_name is None and self._computed_key is not None:
                    name = self._computed_key.replace("_", " ")
                    self._computed_name = name[0].upper() + name[1:] if name else name
            else:
                self._computed_name = description.name

            # Compute key from name if still not set
            if self._computed_key is None and self._computed_name is not None:
                self._computed_key = self._computed_name.lower().replace(" ", "_").replace("-", "_")

            # Compute value_fn if not provided
            if description.value_fn is None and (
                description.property_key is not None or self._computed_key is not None
            ):
                if description.property_key is not None:
                    prop = description.property_key.name.lower()
                else:
                    prop = self._computed_key.lower() if self._computed_key else None
                if prop and hasattr(coordinator.device.status, prop):
                    self._computed_value_fn = lambda value, device, p=prop: getattr(device.status, p)
            else:
                self._computed_value_fn = description.value_fn

            # Compute available_fn if not provided
            if description.available_fn is None:
                if description.property_key is not None:
                    self._computed_available_fn = PROPERTY_AVAILABILITY.get(description.property_key.name)
                elif description.action_key is not None:
                    self._computed_available_fn = ACTION_AVAILABILITY.get(description.action_key.name)
                elif self._computed_key is not None:
                    if self._computed_key in PROPERTY_AVAILABILITY:
                        self._computed_available_fn = PROPERTY_AVAILABILITY[self._computed_key]
                    elif self._computed_key in ACTION_AVAILABILITY:
                        self._computed_available_fn = ACTION_AVAILABILITY[self._computed_key]
            else:
                self._computed_available_fn = description.available_fn

        super().__init__(coordinator=coordinator)
        if description:
            if self._computed_key is not None:
                self._attr_translation_key = self._computed_key
            self.entity_description = description
            self._set_id()
            self._attr_unique_id = f"{self.device.mac}_{self._computed_key}"

    def _resolve_set_fn(
        self,
        coordinator: DreameVacuumDataUpdateCoordinator,
        description: Any,
    ) -> Callable[[Any, int], None] | None:
        """Resolve the device setter for a writable entity.

        Returns ``description.set_fn`` unless it is None and a ``set_<key>`` method
        exists on the device, in which case a wrapper invoking it is returned.
        Shared by the switch / number / time platforms (identical resolution).
        """
        if description.set_fn is None and (description.property_key is not None or self._computed_key is not None):
            prop: str | None = None
            if description.property_key is not None:
                prop = f"set_{description.property_key.name.lower()}"
            elif self._computed_key:
                prop = f"set_{self._computed_key.lower()}"
            if prop is not None and hasattr(coordinator.device, prop):
                method_name = prop
                return lambda device, value: getattr(device, method_name)(value)
        return cast("Callable[[Any, int], None] | None", description.set_fn)

    def _resolve_value_fn(
        self,
        coordinator: DreameVacuumDataUpdateCoordinator,
        description: Any,
        suffix: str = "",
    ) -> Callable[[Any, Any], Any] | None:
        """Resolve the value getter for an entity.

        Returns ``description.value_fn`` unless it is None and a ``<key><suffix>``
        attribute exists on ``device.status`` (sensors pass ``suffix='_name'`` to
        target the display-name variant), in which case a getter wrapper is returned.
        """
        if description.value_fn is None and (description.property_key is not None or self._computed_key is not None):
            prop: str | None = None
            if description.property_key is not None:
                prop = f"{description.property_key.name.lower()}{suffix}"
            elif self._computed_key:
                prop = f"{self._computed_key.lower()}{suffix}"
            if prop is not None and hasattr(coordinator.device.status, prop):
                attr_name = prop
                return lambda value, device: getattr(device.status, attr_name)
        return cast("Callable[[Any, Any], Any] | None", description.value_fn)

    def _resolve_segment_set_fn(
        self,
        coordinator: DreameVacuumDataUpdateCoordinator,
        description: Any,
    ) -> Callable[..., None] | None:
        """Resolve the per-segment device setter (``set_segment_<key>(segment_id, value)``).

        Returns ``description.set_fn`` unless it is None and a ``set_segment_<key>``
        method exists on the device. Shared by the segment number/select entities.
        """
        if description.set_fn is None and (description.property_key is not None or self._computed_key is not None):
            prop: str | None = None
            if description.property_key is not None:
                prop = f"set_segment_{description.property_key.name.lower()}"
            elif self._computed_key:
                prop = f"set_segment_{self._computed_key.lower()}"
            if prop is not None and hasattr(coordinator.device, prop):
                method_name = prop
                return lambda device, segment_id, value: getattr(device, method_name)(segment_id, value)
        return cast("Callable[..., None] | None", description.set_fn)

    def _set_id(self) -> None:
        if self.entity_description:
            if self.entity_description.icon_fn is not None:
                self._attr_icon = self.entity_description.icon_fn(self.native_value, self.device)
            elif self.entity_description.icon is not None:
                self._attr_icon = self.entity_description.icon

            # Check for native_unit_of_measurement (not all descriptions have it)
            if (
                hasattr(self.entity_description, "native_unit_of_measurement")
                and self.entity_description.native_unit_of_measurement is not None
            ):
                self._attr_native_unit_of_measurement = self.entity_description.native_unit_of_measurement

            # Only set _attr_name when name_fn provides a dynamic name.
            # Otherwise, let _attr_translation_key resolve the name from translations.
            if self.entity_description.name_fn is not None:
                self._attr_name = self.entity_description.name_fn(self.native_value, self.device)

    def _generate_entity_id(self, format: str) -> None:
        if self._computed_key:
            self.entity_id = async_generate_entity_id(
                format, f"{self.device.name} {self._computed_key}", hass=self.coordinator.hass
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.device is None:
            self.async_write_ha_state()
            return
        self._set_id()
        self.async_write_ha_state()

    async def _try_command(self, mask_error: str, func: Callable[..., Any] | None, *args: Any, **kwargs: Any) -> bool:
        """Call a vacuum command handling error messages."""
        if func is None:
            return False
        if not self.device.device_connected:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="device_not_available",
            )

        try:
            await self.hass.async_add_executor_job(partial(func, *args, **kwargs))
            return True
        except (InvalidActionException, InvalidValueException) as exc:
            LOGGER.error(mask_error, exc)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_command",
                translation_placeholders={"error": str(exc)},
            ) from exc
        except (DeviceUpdateFailedException, DeviceException) as exc:
            if self.device.available:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="command_failed",
                    translation_placeholders={"error": str(exc)},
                ) from exc
            return False

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information about this Dreame Vacuum device."""
        if not self.device.mac:
            return None
        # Link the entity to the device as soon as the (stable) MAC is known, even
        # before `info` is populated, so entities are never added unlinked during
        # the transient window where the device is connected but info is pending.
        # identifiers/connections are unchanged -> no unique_id migration.
        info = DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, self.device.mac)},
            identifiers={(DOMAIN, self.device.mac)},
            name=self.device.name,
            serial_number=(
                str(self.device.status.serial_number)
                if self.device.status and self.device.status.serial_number is not None
                else None
            ),
        )
        if self.device.info:
            info["manufacturer"] = self.device.info.manufacturer
            info["model"] = self.device.info.model
            info["sw_version"] = self.device.info.firmware_version
            info["hw_version"] = self.device.info.hardware_version
        return info

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if self.device is None or not self.device.device_connected:
            return False

        prop = getattr(self.entity_description, "property_key", None)
        if isinstance(prop, DreameVacuumProperty) and prop.value in self.device.pending_properties:
            # Warm-boot: the entity exists (persisted inventory) but its first
            # value is still loading in the background.
            return False

        if self._computed_available_fn is not None:
            return self._computed_available_fn(self.device)
        return self._attr_available

    @property
    def native_value(self) -> Any:
        """Return the native value of the entity."""
        value = None
        if self.entity_description.property_key is not None:
            value = self.device.get_property(self.entity_description.property_key)
        if self._computed_value_fn is not None:
            return self._computed_value_fn(value, self.device)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return the extra state attributes of the entity."""
        attrs = None
        if self.entity_description.attrs_fn is not None:
            attrs = self.entity_description.attrs_fn(self.device)
        elif self.entity_description.value_fn is not None or self.entity_description.value_int_fn is not None:
            if self.entity_description.property_key is not None:
                attrs = {ATTR_VALUE: self.device.get_property(self.entity_description.property_key)}
            elif self.entity_description.value_int_fn is not None:
                # native_value can be STATE_UNKNOWN / None during the transient window
                # before the device reports a usable value; value_int_fn may then raise
                # (e.g. int("unknown")). A state-attribute read must never break the entity.
                try:
                    attrs = {ATTR_VALUE: self.entity_description.value_int_fn(self.native_value, self)}
                except (ValueError, KeyError, AttributeError, TypeError):
                    attrs = None
        return attrs

    @property
    def device(self) -> DreameVacuumDevice:
        """Return the underlying Dreame vacuum device."""
        return self.coordinator.device


@callback
def async_sync_segment_entities(
    coordinator: DreameVacuumDataUpdateCoordinator,
    current: dict[int, list[Any]],
    async_add_entities: AddEntitiesCallback,
    descriptions: Iterable[Any],
    entity_factory: Callable[[DreameVacuumDataUpdateCoordinator, Any, int], Any],
) -> None:
    """Add or remove per-segment entities to match the current map segments.

    Shared by the number and select platforms: both create one entity per
    (segment, description) pair and must drop the entities of rooms that no
    longer exist in any saved map.
    """
    new_ids: set[int] = set()
    if coordinator.device and coordinator.device.status.map_list:
        for map_data in (coordinator.device.status.map_data_list or {}).values():
            new_ids.update(map_data.segments or {})

    current_ids = set(current)

    for segment_id in current_ids - new_ids:
        async_remove_segment_entities(segment_id, coordinator, current)

    new_entities: list[Any] = []
    for segment_id in new_ids - current_ids:
        current[segment_id] = [
            entity_factory(coordinator, description, segment_id)
            for description in descriptions
            if description.exists_fn(description, coordinator.device)
        ]
        new_entities.extend(current[segment_id])

    if new_entities:
        async_add_entities(new_entities)


def async_remove_segment_entities(
    segment_id: int,
    coordinator: DreameVacuumDataUpdateCoordinator,
    current: dict[int, list[Any]],
) -> None:
    """Remove the entities of a segment that no longer exists."""
    registry = entity_registry.async_get(coordinator.hass)
    for entity in current[segment_id]:
        if entity.entity_id in registry.entities:
            registry.async_remove(entity.entity_id)
    del current[segment_id]
