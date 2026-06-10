"""Shared member declarations for the renderer mixins (type-checking only).

``DreameVacuumMapRenderer`` is assembled from :class:`_ObjectsMixin`,
:class:`_ShapesMixin` and :class:`_StaticHelpersMixin` plus the state created in
``DreameVacuumMapRenderer.__init__``. Because mypy type-checks each mixin in
isolation, ``_ObjectsMixin`` / ``_ShapesMixin`` accessing renderer state
(``self.icon_set``, ``self._coords_on_line`` …) would raise ``attr-defined``.

:class:`_MapRendererState` declares that shared surface for the type checker
only. Its body is gated behind :data:`typing.TYPE_CHECKING`, so at runtime it is
an empty class with no behavioural effect. ``_StaticHelpersMixin`` does *not*
inherit it (it owns the real staticmethods); the renderer and the two consuming
mixins precede it in the MRO, so the real members always win.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL import Image

    from ..vacuum_types import MapRendererColorScheme, MapRendererConfig


class _MapRendererState:
    """Type-checking-only view of the renderer surface shared by its mixins."""

    if TYPE_CHECKING:
        # --- State (created in DreameVacuumMapRenderer.__init__) ---
        color_scheme: MapRendererColorScheme
        config: MapRendererConfig
        icon_set: int
        _robot_type: int
        _low_memory: bool
        _square: bool
        _obstacle_icons: dict[Any, Any]
        _obstacle_hidden_icons: dict[Any, Any]
        _furniture_icons: dict[Any, Any]
        _furniture_images: dict[Any, Any]

        # --- Lazily-loaded image/asset caches (created None in __init__) ---
        _charger_icon: Image.Image | None
        _robot_icon: Image.Image | None
        _robot_charging_icon: Image.Image | None
        _robot_cleaning_icon: Image.Image | None
        _robot_warning_icon: Image.Image | None
        _robot_sleeping_icon: list[Image.Image] | None
        _robot_washing_icon: Image.Image | None
        _robot_hot_washing_icon: Image.Image | None
        _robot_drying_icon: Image.Image | None
        _robot_hot_drying_icon: Image.Image | None
        _robot_emptying_icon: Image.Image | None
        _robot_cleaning_direction_icon: Image.Image | None
        _obstacle_background: Image.Image | None
        _obstacle_hidden_background: Image.Image | None
        _cruise_path_point_background: Image.Image | None
        _cruise_point_background: Image.Image | None
        _furniture_background: Image.Image | None
        _wifi_icon: Image.Image | None
        _map_problem_icon: Image.Image | None
        _font_file: bytes | None

        # --- Pure staticmethods (defined on _StaticHelpersMixin) ---
        @staticmethod
        def _set_icon_color(image: Image.Image, size: float, color: Any) -> Image.Image: ...

        @staticmethod
        def _close_image(img: Image.Image | None) -> None: ...

        @staticmethod
        def _coords_on_line(
            x0: float, y0: float, x1: float, y1: float, spacing: float, size: int | None = None
        ) -> list[tuple[float, float]]: ...
