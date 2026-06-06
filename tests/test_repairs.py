"""Tests for the Dreame Vacuum repairs platform."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.repairs import ConfirmRepairFlow

from custom_components.dreame_vacuum.repairs import async_create_fix_flow


async def test_create_fix_flow_returns_confirm_flow() -> None:
    """The fix flow for the segment-change issue is a simple confirmation."""
    flow = await async_create_fix_flow(MagicMock(), "segments_changed_AA:BB:CC:DD:EE:FF", None)
    assert isinstance(flow, ConfirmRepairFlow)


async def test_create_fix_flow_with_data() -> None:
    """A fix flow is returned regardless of issue_id / data payload."""
    flow = await async_create_fix_flow(MagicMock(), "segments_changed_x", {"foo": "bar"})
    assert isinstance(flow, ConfirmRepairFlow)
