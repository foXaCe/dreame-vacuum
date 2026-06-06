"""Non-regression tests for the P9-unblocked P6 deduplications.

- set-resolver: switch/number/time shared the same set_<key> resolver block; it now
  lives in DreameVacuumEntity._resolve_set_fn.
- segment navigation: the 6 index-navigation methods duplicated between the two select
  entities now live in DreameVacuumOptionNavigationMixin.

These modules became importable/testable only after P9 (entity.py <-> camera decoupling).
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.dreame_vacuum import select as select_mod
from custom_components.dreame_vacuum.entity import DreameVacuumEntity

_CC = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "dreame_vacuum"
_CC_PLATFORMS = ("switch.py", "number.py", "time.py")


# --- set-resolver helper -----------------------------------------------------


def _bare_entity(computed_key):
    entity: DreameVacuumEntity = object.__new__(DreameVacuumEntity)
    entity._computed_key = computed_key
    return entity


def test_p6_resolve_set_fn_wires_device_setter_from_key() -> None:
    entity = _bare_entity("foo")
    setter = MagicMock()
    coordinator = SimpleNamespace(device=SimpleNamespace(set_foo=setter))
    description = SimpleNamespace(set_fn=None, property_key=None)

    fn = entity._resolve_set_fn(coordinator, description)
    assert fn is not None
    fn(coordinator.device, 5)
    setter.assert_called_once_with(5)


def test_p6_resolve_set_fn_uses_property_key() -> None:
    entity = _bare_entity(None)
    setter = MagicMock()
    coordinator = SimpleNamespace(device=SimpleNamespace(set_suction_level=setter))
    description = SimpleNamespace(set_fn=None, property_key=SimpleNamespace(name="SUCTION_LEVEL"))

    fn = entity._resolve_set_fn(coordinator, description)
    assert fn is not None
    fn(coordinator.device, 2)
    setter.assert_called_once_with(2)


def test_p6_resolve_set_fn_falls_back_when_no_setter() -> None:
    entity = _bare_entity("bar")
    coordinator = SimpleNamespace(device=SimpleNamespace())  # no set_bar
    description = SimpleNamespace(set_fn=None, property_key=None)

    assert entity._resolve_set_fn(coordinator, description) is None


def test_p6_resolve_set_fn_keeps_explicit_set_fn() -> None:
    entity = _bare_entity("foo")
    sentinel = MagicMock()
    coordinator = SimpleNamespace(device=SimpleNamespace(set_foo=MagicMock()))
    description = SimpleNamespace(set_fn=sentinel, property_key=None)

    assert entity._resolve_set_fn(coordinator, description) is sentinel


def test_p6_platforms_use_shared_resolver() -> None:
    """The inline resolver block must be gone from the platforms, replaced by the helper."""
    for fname in _CC_PLATFORMS:
        src = (_CC / fname).read_text()
        assert "# Override _computed_set_fn if we can find a setter method" not in src
        assert "self._computed_set_fn = self._resolve_set_fn(coordinator, description)" in src


# --- segment navigation mixin ------------------------------------------------


class _FakeSelect(select_mod.DreameVacuumOptionNavigationMixin):
    def __init__(self, options, current):
        self._attr_options = options
        self._attr_current_option = current
        self.selected: list = []

    async def async_select_option(self, option: str) -> None:
        self.selected.append(option)
        self._attr_current_option = option


async def test_p6_nav_first_and_last() -> None:
    sel = _FakeSelect(["a", "b", "c"], "b")
    await sel.async_first()
    assert sel.selected[-1] == "a"
    await sel.async_last()
    assert sel.selected[-1] == "c"


async def test_p6_nav_next_previous_cycle() -> None:
    sel = _FakeSelect(["a", "b", "c"], "c")
    await sel.async_next(cycle=True)
    assert sel.selected[-1] == "a"  # wraps around

    sel2 = _FakeSelect(["a", "b", "c"], "a")
    await sel2.async_previous(cycle=True)
    assert sel2.selected[-1] == "c"  # wraps around


async def test_p6_nav_next_no_cycle_clamps() -> None:
    sel = _FakeSelect(["a", "b", "c"], "c")
    await sel.async_next(cycle=False)
    assert sel.selected == []  # already last, clamped -> no selection


async def test_p6_nav_offset_with_unknown_current() -> None:
    sel = _FakeSelect(["a", "b", "c"], "x")  # not in options -> current_index = 0
    await sel.async_offset_index(1, cycle=False)
    assert sel.selected[-1] == "b"


def test_p6_select_entities_inherit_navigation_mixin() -> None:
    """Both select entities resolve the nav methods to the shared mixin (not redefined)."""
    mixin = select_mod.DreameVacuumOptionNavigationMixin
    for cls in (select_mod.DreameVacuumSelectEntity, select_mod.DreameVacuumSegmentSelectEntity):
        assert issubclass(cls, mixin)
        assert cls.async_first is mixin.async_first
        assert cls.async_offset_index is mixin.async_offset_index
