"""Tests for the Dreame Vacuum button platform.

Covers the three entity classes (plain / shortcut / map button) including
``async_press`` success and failure (-> ``HomeAssistantError``), availability,
icon/name computation, the coordinator update callbacks, the dynamic
``async_update_buttons`` / ``async_remove_buttons`` machinery and
``async_setup_entry``.

Local fixtures only; ``tests/conftest.py`` is not modified.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.dreame_vacuum import button as button_mod
from custom_components.dreame_vacuum.button import (
    BUTTONS,
    DreameVacuumButtonEntity,
    DreameVacuumMapButtonEntity,
    DreameVacuumShortcutButtonEntity,
    async_remove_buttons,
    async_setup_entry,
    async_update_buttons,
)
from custom_components.dreame_vacuum.dreame import (
    DeviceException,
    DeviceUpdateFailedException,
    DreameVacuumAction,
    InvalidActionException,
)
from custom_components.dreame_vacuum.dreame.vacuum_types import Shortcut


@pytest.fixture
def hass() -> MagicMock:
    """Lightweight fake hass (real fixture unavailable under ``-p no:homeassistant``)."""
    fake = MagicMock()
    fake.states.async_available = MagicMock(return_value=True)

    async def _exec(func, *args, **kwargs):
        return func(*args, **kwargs)

    fake.async_add_executor_job = AsyncMock(side_effect=_exec)
    return fake


def _make_status() -> MagicMock:
    status = MagicMock()
    status.started = False
    status.draining = False
    status.self_repairing = False
    status.shortcut_task = False
    status.map_backup_status = False
    status.washing = False
    status.washing_paused = False
    status.washing_available = True
    status.returning_to_wash_paused = False
    status.drying = False
    status.drying_available = True
    status.dust_collection_available = True
    status.auto_emptying = False
    status.main_brush_life = 80
    status.side_brush_life = 80
    status.filter_life = 80
    status.mop_life = 80
    status.silver_ion_life = 80
    status.squeegee_life = 80
    status.onboard_dirty_water_tank_life = 80
    status.dirty_water_tank_life = 80
    status.shortcuts = None
    status.map_list = None
    return status


def _make_capability() -> MagicMock:
    capability = MagicMock()
    capability.disable_sensor_cleaning = False
    capability.detergent = True
    capability.scale_inhibitor = True
    capability.wheel = True
    capability.deodorizer = True
    capability.auto_empty_base = True
    capability.lidar_navigation = True
    capability.self_wash_base = True
    capability.drainage = True
    capability.empty_water_tank = True
    capability.station_cleaning = True
    capability.auto_recleaning = True
    capability.map = True
    capability.shortcuts = False
    capability.backup_map = False
    return capability


def make_coordinator(hass) -> tuple[MagicMock, MagicMock]:
    device = MagicMock()
    device.name = "Test Vacuum"
    device.mac = "AA:BB:CC:DD:EE:FF"
    device.available = True
    device.device_connected = True
    device.status = _make_status()
    device.capability = _make_capability()
    device.action_mapping = {a: {} for a in DreameVacuumAction}
    device.call_action = MagicMock()
    coordinator = MagicMock()
    coordinator.device = device
    coordinator.hass = hass
    return coordinator, device


def get_description(*, action_key=None, key=None):
    for desc in BUTTONS:
        if action_key is not None and getattr(desc, "action_key", None) == action_key:
            return desc
        if key is not None and desc.key == key:
            return desc
    raise AssertionError(f"description not found for {action_key or key}")


def build_entity(hass, *, action_key=None, key=None):
    coordinator, device = make_coordinator(hass)
    desc = get_description(action_key=action_key, key=key)
    entity = DreameVacuumButtonEntity(coordinator, desc)
    entity.hass = hass
    return entity, device, coordinator


# ---------------------------------------------------------------------------
# DreameVacuumButtonEntity: construction & async_press (action_key path)
# ---------------------------------------------------------------------------


async def test_construction_unique_id_and_entity_id(hass):
    entity, _device, _coord = build_entity(hass, action_key=DreameVacuumAction.RESET_MAIN_BRUSH)
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_reset_main_brush"
    assert entity.entity_id.startswith("button.")


async def test_press_calls_action_via_call_action(hass):
    entity, device, _coord = build_entity(hass, action_key=DreameVacuumAction.RESET_MAIN_BRUSH)
    await entity.async_press()
    device.call_action.assert_called_once_with(DreameVacuumAction.RESET_MAIN_BRUSH)


async def test_press_action_key_failure_raises(hass):
    entity, device, _coord = build_entity(hass, action_key=DreameVacuumAction.RESET_MAIN_BRUSH)
    device.call_action.side_effect = InvalidActionException("nope")
    with pytest.raises(HomeAssistantError):
        await entity.async_press()


async def test_press_raises_when_unavailable(hass):
    entity, device, _coord = build_entity(hass, action_key=DreameVacuumAction.RESET_MAIN_BRUSH)
    device.device_connected = False
    with pytest.raises(HomeAssistantError):
        await entity.async_press()


# ---------------------------------------------------------------------------
# DreameVacuumButtonEntity: async_press (action_fn path)
# ---------------------------------------------------------------------------


async def test_press_calls_action_fn(hass):
    # CLEAR_WARNING button -> action_fn=lambda device: device.clear_warning()
    entity, device, _coord = build_entity(hass, action_key=DreameVacuumAction.CLEAR_WARNING)
    await entity.async_press()
    device.clear_warning.assert_called_once_with()


async def test_press_action_fn_failure_raises(hass):
    entity, device, _coord = build_entity(hass, key="start_fast_mapping")
    device.start_fast_mapping.side_effect = InvalidActionException("nope")
    with pytest.raises(HomeAssistantError):
        await entity.async_press()


async def test_press_action_fn_self_clean_toggle(hass):
    entity, device, _coord = build_entity(hass, key="self_clean")
    await entity.async_press()
    device.toggle_washing.assert_called_once_with()


async def test_press_device_exception_swallowed_when_unavailable(hass):
    entity, device, _coord = build_entity(hass, action_key=DreameVacuumAction.CLEAR_WARNING)
    device.available = False
    device.clear_warning.side_effect = DeviceUpdateFailedException("offline")
    await entity.async_press()  # must not raise
    device.clear_warning.assert_called_once()


async def test_press_device_exception_raises_when_available(hass):
    entity, device, _coord = build_entity(hass, action_key=DreameVacuumAction.CLEAR_WARNING)
    device.available = True
    device.clear_warning.side_effect = DeviceException("boom")
    with pytest.raises(HomeAssistantError):
        await entity.async_press()


# ---------------------------------------------------------------------------
# availability of the dynamic-icon buttons
# ---------------------------------------------------------------------------


async def test_self_clean_available_fn_true(hass):
    entity, device, _coord = build_entity(hass, key="self_clean")
    device.status.washing_available = True
    device.status.draining = False
    device.status.self_repairing = False
    assert entity.available is True


async def test_self_clean_available_fn_false_when_draining(hass):
    entity, device, _coord = build_entity(hass, key="self_clean")
    device.status.washing_available = True
    device.status.draining = True
    assert entity.available is False


async def test_icon_fn_applied_at_construction(hass):
    # start_auto_empty has an icon_fn -> _attr_icon resolved from device.status.
    entity, device, _coord = build_entity(hass, action_key=DreameVacuumAction.START_AUTO_EMPTY)
    assert entity.icon in {"mdi:delete-off", "mdi:delete-restore", "mdi:delete-empty"}


# ---------------------------------------------------------------------------
# DreameVacuumShortcutButtonEntity
# ---------------------------------------------------------------------------


def _shortcut_coordinator(hass, shortcuts):
    coordinator, device = make_coordinator(hass)
    device.capability.shortcuts = True
    device.status.shortcuts = shortcuts
    device.start_shortcut = MagicMock()
    return coordinator, device


def _shortcut_description():
    return button_mod.DreameVacuumButtonEntityDescription(
        key="shortcut",
        icon="mdi:play-speed",
        available_fn=lambda device: (
            not device.status.started
            and not device.status.shortcut_task
            and not device.status.draining
            and not device.status.self_repairing
        ),
    )


async def test_shortcut_button_construction_and_name(hass):
    shortcuts = {1: Shortcut(id=1, name="Shortcut Kitchen", tasks=[])}
    coordinator, device = _shortcut_coordinator(hass, shortcuts)
    entity = DreameVacuumShortcutButtonEntity(coordinator, _shortcut_description(), 1)
    entity.hass = hass
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_shortcut_1"
    # name strips the leading "Shortcut" token.
    entity._set_id()
    assert entity._attr_translation_placeholders == {"name": "Kitchen"}
    assert entity.extra_state_attributes == shortcuts[1].as_dict()


async def test_shortcut_button_id_offset_above_32(hass):
    shortcuts = {33: Shortcut(id=33, name="Garage", tasks=[])}
    coordinator, device = _shortcut_coordinator(hass, shortcuts)
    entity = DreameVacuumShortcutButtonEntity(coordinator, _shortcut_description(), 33)
    entity.hass = hass
    # id >= 32 -> id - 31 == 2
    assert entity.id == 2
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_shortcut_2"


async def test_shortcut_button_press_calls_start_shortcut(hass):
    shortcuts = {1: Shortcut(id=1, name="Kitchen", tasks=[])}
    coordinator, device = _shortcut_coordinator(hass, shortcuts)
    entity = DreameVacuumShortcutButtonEntity(coordinator, _shortcut_description(), 1)
    entity.hass = hass
    await entity.async_press()
    device.start_shortcut.assert_called_once_with(1)


async def test_shortcut_button_press_failure_raises(hass):
    shortcuts = {1: Shortcut(id=1, name="Kitchen", tasks=[])}
    coordinator, device = _shortcut_coordinator(hass, shortcuts)
    device.start_shortcut.side_effect = InvalidActionException("nope")
    entity = DreameVacuumShortcutButtonEntity(coordinator, _shortcut_description(), 1)
    entity.hass = hass
    with pytest.raises(HomeAssistantError):
        await entity.async_press()


async def test_shortcut_button_press_raises_when_unavailable(hass):
    shortcuts = {1: Shortcut(id=1, name="Kitchen", tasks=[])}
    coordinator, device = _shortcut_coordinator(hass, shortcuts)
    device.status.started = True  # available_fn -> False
    entity = DreameVacuumShortcutButtonEntity(coordinator, _shortcut_description(), 1)
    entity.hass = hass
    with pytest.raises(HomeAssistantError):
        await entity.async_press()


async def test_shortcut_button_construction_without_matching_shortcut(hass):
    # When no shortcut matches ``shortcut_id``, ``_set_id`` falls back to
    # ``str(self.id)``. ``self.id`` is now assigned before ``super().__init__()``,
    # so construction succeeds instead of raising AttributeError.
    coordinator, _device = _shortcut_coordinator(hass, None)
    entity = DreameVacuumShortcutButtonEntity(coordinator, _shortcut_description(), 1)
    assert entity.shortcut is None
    assert entity.id == 1
    assert entity._attr_translation_placeholders == {"name": "1"}


async def test_shortcut_button_extra_attributes_none_without_shortcut(hass):
    # Cover the ``extra_state_attributes`` None branch without tripping the
    # construction bug above: build a bare instance and set ``shortcut`` to None.
    entity = object.__new__(DreameVacuumShortcutButtonEntity)
    entity.shortcut = None
    assert entity.extra_state_attributes is None


async def test_shortcut_button_update_refreshes_name(hass):
    shortcuts = {1: Shortcut(id=1, name="Kitchen", tasks=[])}
    coordinator, device = _shortcut_coordinator(hass, shortcuts)
    entity = DreameVacuumShortcutButtonEntity(coordinator, _shortcut_description(), 1)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    # change the shortcut name on the device
    device.status.shortcuts = {1: Shortcut(id=1, name="Bedroom", tasks=[])}
    entity._handle_coordinator_update()
    assert entity._attr_translation_placeholders == {"name": "Bedroom"}
    entity.async_write_ha_state.assert_called_once()


async def test_shortcut_button_update_clears_removed_shortcut(hass):
    shortcuts = {1: Shortcut(id=1, name="Kitchen", tasks=[])}
    coordinator, device = _shortcut_coordinator(hass, shortcuts)
    entity = DreameVacuumShortcutButtonEntity(coordinator, _shortcut_description(), 1)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    device.status.shortcuts = {}  # shortcut removed
    entity._handle_coordinator_update()
    assert entity.shortcut is None


async def test_shortcut_button_update_device_none(hass):
    shortcuts = {1: Shortcut(id=1, name="Kitchen", tasks=[])}
    coordinator, device = _shortcut_coordinator(hass, shortcuts)
    entity = DreameVacuumShortcutButtonEntity(coordinator, _shortcut_description(), 1)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    coordinator.device = None
    entity._handle_coordinator_update()
    entity.async_write_ha_state.assert_called_once()


# ---------------------------------------------------------------------------
# DreameVacuumMapButtonEntity
# ---------------------------------------------------------------------------


def _map_coordinator(hass, *, custom_name="kitchen-map", map_id=7):
    coordinator, device = make_coordinator(hass)
    device.capability.backup_map = True
    map_data = SimpleNamespace(custom_name=custom_name, map_id=map_id)
    device.get_map = MagicMock(return_value=map_data)
    device.backup_map = MagicMock()
    return coordinator, device, map_data


async def test_map_button_construction_and_name(hass):
    coordinator, device, _map_data = _map_coordinator(hass)
    entity = DreameVacuumMapButtonEntity(coordinator, _map_description(), 1)
    entity.hass = hass
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_backup_map_1"
    # "kitchen-map" -> "Kitchen map" (underscores/hyphens to spaces + capitalize)
    assert entity._attr_translation_placeholders == {"map_name": "Kitchen map"}


def _map_description():
    return button_mod.DreameVacuumButtonEntityDescription(
        key="backup",
        icon="mdi:content-save",
        available_fn=lambda device: not device.status.started and not device.status.map_backup_status,
    )


async def test_map_button_name_falls_back_to_index(hass):
    coordinator, device, _map_data = _map_coordinator(hass, custom_name=None)
    entity = DreameVacuumMapButtonEntity(coordinator, _map_description(), 3)
    entity.hass = hass
    assert entity._attr_translation_placeholders == {"map_name": "3"}


async def test_map_button_press_calls_backup_map(hass):
    coordinator, device, map_data = _map_coordinator(hass)
    entity = DreameVacuumMapButtonEntity(coordinator, _map_description(), 1)
    entity.hass = hass
    await entity.async_press()
    device.backup_map.assert_called_once_with(map_data.map_id)


async def test_map_button_press_raises_when_map_missing(hass):
    coordinator, device, _map_data = _map_coordinator(hass)
    entity = DreameVacuumMapButtonEntity(coordinator, _map_description(), 1)
    entity.hass = hass
    device.get_map.return_value = None
    with pytest.raises(HomeAssistantError):
        await entity.async_press()


async def test_map_button_press_raises_when_unavailable(hass):
    coordinator, device, _map_data = _map_coordinator(hass)
    device.status.started = True  # available_fn -> False
    entity = DreameVacuumMapButtonEntity(coordinator, _map_description(), 1)
    entity.hass = hass
    with pytest.raises(HomeAssistantError):
        await entity.async_press()


async def test_map_button_press_failure_raises(hass):
    coordinator, device, _map_data = _map_coordinator(hass)
    device.backup_map.side_effect = InvalidActionException("nope")
    entity = DreameVacuumMapButtonEntity(coordinator, _map_description(), 1)
    entity.hass = hass
    with pytest.raises(HomeAssistantError):
        await entity.async_press()


async def test_map_button_update_refreshes_name(hass):
    coordinator, device, _map_data = _map_coordinator(hass)
    entity = DreameVacuumMapButtonEntity(coordinator, _map_description(), 1)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    device.get_map.return_value = SimpleNamespace(custom_name="office", map_id=7)
    entity._handle_coordinator_update()
    assert entity._attr_translation_placeholders == {"map_name": "Office"}
    entity.async_write_ha_state.assert_called_once()


async def test_map_button_update_device_none(hass):
    coordinator, device, _map_data = _map_coordinator(hass)
    entity = DreameVacuumMapButtonEntity(coordinator, _map_description(), 1)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    coordinator.device = None
    entity._handle_coordinator_update()
    entity.async_write_ha_state.assert_called_once()


# ---------------------------------------------------------------------------
# async_update_buttons / async_remove_buttons
# ---------------------------------------------------------------------------


async def test_async_update_buttons_adds_shortcut_entities(hass):
    coordinator, device = make_coordinator(hass)
    device.capability.shortcuts = True
    device.capability.backup_map = False
    device.status.shortcuts = {1: Shortcut(id=1, name="Kitchen", tasks=[])}
    current_shortcut: dict = {}
    current_map: dict = {}
    added: list = []
    async_update_buttons(coordinator, current_shortcut, current_map, lambda ents: added.extend(ents))
    assert 1 in current_shortcut
    assert len(added) == 1
    assert isinstance(added[0], DreameVacuumShortcutButtonEntity)


async def test_async_update_buttons_adds_map_entities(hass):
    coordinator, device = make_coordinator(hass)
    device.capability.shortcuts = False
    device.capability.backup_map = True
    device.status.map_list = ["m1", "m2"]
    device.get_map = MagicMock(return_value=SimpleNamespace(custom_name="m", map_id=1))
    current_shortcut: dict = {}
    current_map: dict = {}
    added: list = []
    async_update_buttons(coordinator, current_shortcut, current_map, lambda ents: added.extend(ents))
    assert set(current_map) == {1, 2}
    assert len(added) == 2


async def test_async_update_buttons_removes_stale_shortcuts(hass):
    coordinator, device = make_coordinator(hass)
    device.capability.shortcuts = True
    device.capability.backup_map = False
    device.status.shortcuts = {}  # no shortcuts now
    stale = MagicMock()
    stale.entity_id = "button.shortcut_1"
    current_shortcut: dict = {1: [stale]}
    registry = MagicMock()
    registry.entities = {"button.shortcut_1": MagicMock()}
    with patch.object(button_mod.entity_registry, "async_get", return_value=registry):
        async_update_buttons(coordinator, current_shortcut, {}, lambda ents: None)
    registry.async_remove.assert_called_once_with("button.shortcut_1")
    assert 1 not in current_shortcut


async def test_async_update_buttons_removes_stale_maps(hass):
    coordinator, device = make_coordinator(hass)
    device.capability.shortcuts = False
    device.capability.backup_map = True
    device.status.map_list = []  # no maps now -> index 2 is stale
    device.get_map = MagicMock(return_value=SimpleNamespace(custom_name="m", map_id=1))
    stale = MagicMock()
    stale.entity_id = "button.backup_map_2"
    current_map: dict = {2: [stale]}
    registry = MagicMock()
    registry.entities = {"button.backup_map_2": MagicMock()}
    with patch.object(button_mod.entity_registry, "async_get", return_value=registry):
        async_update_buttons(coordinator, {}, current_map, lambda ents: None)
    registry.async_remove.assert_called_once_with("button.backup_map_2")
    assert 2 not in current_map


async def test_async_update_buttons_noop_when_device_none(hass):
    coordinator, _device = make_coordinator(hass)
    coordinator.device = None
    added: list = []
    async_update_buttons(coordinator, {}, {}, lambda ents: added.extend(ents))
    assert added == []


async def test_async_remove_buttons_skips_unregistered(hass):
    coordinator, _device = make_coordinator(hass)
    entity = MagicMock()
    entity.entity_id = "button.unknown"
    current: dict = {5: [entity]}
    registry = MagicMock()
    registry.entities = {}  # entity not registered
    with patch.object(button_mod.entity_registry, "async_get", return_value=registry):
        async_remove_buttons(5, coordinator, current)
    registry.async_remove.assert_not_called()
    assert 5 not in current


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------


async def test_async_setup_entry_adds_static_buttons(hass):
    coordinator, device = make_coordinator(hass)
    device.capability.shortcuts = False
    device.capability.backup_map = False
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    added: list = []
    await async_setup_entry(hass, entry, lambda gen: added.extend(list(gen)))
    assert len(added) > 0
    assert all(isinstance(e, DreameVacuumButtonEntity) for e in added)


async def test_async_setup_entry_registers_dynamic_listener(hass):
    coordinator, device = make_coordinator(hass)
    device.capability.shortcuts = True
    device.capability.backup_map = False
    device.status.shortcuts = {1: Shortcut(id=1, name="Kitchen", tasks=[])}
    coordinator.async_add_listener = MagicMock()
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    added: list = []
    await async_setup_entry(hass, entry, lambda gen: added.extend(list(gen)))
    # A listener for dynamic buttons must be registered and invoked once.
    coordinator.async_add_listener.assert_called_once()
    # The initial update added the shortcut entity.
    assert any(isinstance(e, DreameVacuumShortcutButtonEntity) for e in added)


async def test_async_setup_entry_respects_exists_fn(hass):
    coordinator, device = make_coordinator(hass)
    device.capability.shortcuts = False
    device.capability.backup_map = False
    device.capability.lidar_navigation = False  # removes start_fast_mapping/start_mapping
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    added: list = []
    await async_setup_entry(hass, entry, lambda gen: added.extend(list(gen)))
    keys = {e.entity_description.key for e in added}
    assert "start_fast_mapping" not in keys


def test_buttons_tuple_non_empty():
    assert len(BUTTONS) > 0
    assert button_mod.PARALLEL_UPDATES == 1
