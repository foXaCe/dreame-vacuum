"""Repairs platform for Dreame Vacuum.

Provides the fix flow for actionable repair issues. The map-segment change
issue (``segments_changed``) is acknowledged through a simple confirmation:
once the user has reviewed their segment-based automations they submit the
flow, which dismisses the issue. Consumable-depleted issues are informational
(``is_fixable=False``) and are not handled here.
"""

from __future__ import annotations

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow for a Dreame Vacuum repair issue."""
    return ConfirmRepairFlow()
