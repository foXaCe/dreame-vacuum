"""Shared member declarations for the renderer mixins (type-checking only).

``DreameVacuumMapRenderer`` is assembled from :class:`_ObjectsMixin`,
:class:`_ShapesMixin`, :class:`_StaticHelpersMixin`, :class:`_LayersMixin`,
:class:`_SegmentsRenderMixin` and :class:`_ResourcesMixin` plus the state
created in ``DreameVacuumMapRenderer.__init__``. Because mypy type-checks each
mixin in isolation, a mixin accessing renderer state or another mixin's
methods (``self.icon_set``, ``self._coords_on_line``, ``self.render_segment``
…) would raise ``attr-defined``.

:class:`_MapRendererState` declares that shared surface for the type checker
only. Its body is gated behind :data:`typing.TYPE_CHECKING`, so at runtime it is
an empty class with no behavioural effect. ``_StaticHelpersMixin`` does *not*
inherit it (it owns the real staticmethods); the renderer and the consuming
mixins precede it in the MRO, so the real members always win.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL import Image

    from ..vacuum_types import MapData, MapRendererColorScheme, MapRendererConfig


class _MapRendererState:
    """Type-checking-only view of the renderer surface shared by its mixins."""

    if TYPE_CHECKING:
        # --- State (created in DreameVacuumMapRenderer.__init__) ---
        color_scheme: MapRendererColorScheme
        config: MapRendererConfig
        icon_set: int
        _robot_type: int
        _low_memory: bool
        _low_resolution: bool
        _square: bool
        _cache: bool
        _language: str | None
        _map_data: MapData | None
        _robot_status: int | None
        _station_status: int | None
        _badge_positions: dict[Any, Any]
        _name_offsets: dict[Any, Any]
        _obstacle_icons: dict[Any, Any]
        _obstacle_hidden_icons: dict[Any, Any]
        _furniture_icons: dict[Any, Any]
        _furniture_images: dict[Any, Any]
        _segment_icons: dict[Any, Any]
        _cleaning_times_icon: Any
        _suction_level_icon: Any
        _water_volume_icon: Any
        _mop_pad_humidity_icon: Any
        _cleaning_mode_icon: Any
        _cleaning_route_icon: Any
        _custom_mopping_route_icon: Any
        _calibration_points: Any
        _default_calibration_points: Any

        # --- Lazily-loaded image/asset caches (created None in __init__) ---
        _charger_icon: Image.Image | None
        _robot_icon: Image.Image | None
        _robot_icon_data_uri: str | None
        _robot_icon_lit_data_uri: str | None
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
        _light_font_file: Any
        _image: Any
        _default_map_image: Any
        _default_map_image_data: bytes | None
        _disconnected_map_image_data: bytes | None
        _disconnected_map_image_src: Any

        # --- Pure staticmethods (defined on _StaticHelpersMixin) ---
        @staticmethod
        def _set_icon_color(image: Image.Image, size: float, color: Any) -> Image.Image: ...

        @staticmethod
        def _close_image(img: Image.Image | None) -> None: ...

        @staticmethod
        def _coords_on_line(
            x0: float, y0: float, x1: float, y1: float, spacing: float, size: int | None = None
        ) -> list[tuple[float, float]]: ...

        @staticmethod
        def _del_layer(cached_layers: dict[Any, Any], key: Any) -> None: ...

        @staticmethod
        def _replace_layer(cached_layers: dict[Any, Any], key: Any, new_image: Image.Image | None) -> None: ...

        @staticmethod
        def _combine_layers(
            cached_layers: dict[Any, Any], layer_size: tuple[int, int], parent: Any, sub: Any
        ) -> None: ...

        @staticmethod
        def _alpha_composite(source: Any, destination: Any) -> Any: ...

        @staticmethod
        def _to_buffer(image: Image.Image | None) -> bytes | None: ...

        # --- Pure staticmethods (defined directly on DreameVacuumMapRenderer, in _core.py) ---
        @staticmethod
        def _get_carpet_coords(carpet: Any, dimensions: Any) -> Any: ...

        @staticmethod
        def _optimize_carpet_pixels(carpet_pixels: Any, dimensions: Any, pixel_type: Any) -> Any: ...

        @staticmethod
        def _check_carpet(x: Any, y: Any, carpet: Any, dimensions: Any, pixel_type: Any = None) -> Any: ...

        # --- Methods defined on other mixins, called across mixin boundaries ---
        def _calculate_render_sizes(self, map_data: Any, map_image: Any, scale: Any) -> Any: ...

        # _ShapesMixin
        def render_areas(
            self,
            areas: list[Any],
            color: tuple[int, ...],
            fill: tuple[int, ...] | None,
            layer_size: tuple[int, int],
            dimensions: Any,
            width: int,
            scale: int,
        ) -> Image.Image: ...

        def render_points(
            self,
            points: list[Any],
            color: tuple[int, ...],
            fill: tuple[int, ...] | None,
            layer_size: tuple[int, int],
            dimensions: Any,
            width: int,
            scale: int,
        ) -> Image.Image: ...

        def render_walls(
            self,
            walls: list[Any],
            color: tuple[int, ...],
            layer_size: tuple[int, int],
            dimensions: Any,
            width: int,
            scale: int,
        ) -> Image.Image: ...

        def render_thresholds(
            self,
            thresholds: list[Any],
            color: tuple[int, ...],
            fill: tuple[int, ...] | None,
            layer_size: tuple[int, int],
            dimensions: Any,
            width: int,
            scale: int,
        ) -> Image.Image: ...

        def render_curtains(
            self,
            curtains: list[Any],
            color: tuple[int, ...],
            layer_size: tuple[int, int],
            dimensions: Any,
            width: int,
            scale: int,
        ) -> Image.Image: ...

        def render_ramps(
            self,
            ramps: list[Any],
            color: tuple[int, ...],
            fill: tuple[int, ...] | None,
            layer_size: tuple[int, int],
            dimensions: Any,
            width: int,
            scale: int,
            rotation: int,
        ) -> Image.Image: ...

        # _ObjectsMixin
        def render_vacuum(
            self,
            robot_position: Any,
            robot_status: int,
            layer_size: tuple[int, int],
            dimensions: Any,
            size: float,
            map_rotation: int,
            scale: int,
        ) -> Image.Image: ...

        def render_obstacle(
            self,
            obstacle: Any,
            layer_size: tuple[int, int],
            dimensions: Any,
            size: float,
            rotation: int,
            scale: int,
        ) -> Image.Image | None: ...

        def render_cruise_point(
            self,
            index: int,
            cruise_point: Any,
            layer_size: tuple[int, int],
            dimensions: Any,
            size: float,
            rotation: int,
            scale: int,
        ) -> Image.Image: ...

        def render_furniture(
            self,
            furniture: Any,
            furniture_version: int,
            layer_size: tuple[int, int],
            dimensions: Any,
            size: float,
            rotation: int,
            scale: int,
        ) -> Image.Image | None: ...

        def render_charger(
            self,
            charger_position: Any,
            station_status: int,
            layer_size: tuple[int, int],
            dimensions: Any,
            size: float,
            map_rotation: int,
            scale: int,
        ) -> Image.Image: ...

        def render_router(
            self,
            router_position: Any,
            layer_size: tuple[int, int],
            dimensions: Any,
            size: float,
            rotation: int,
            scale: int,
        ) -> Image.Image: ...

        def render_low_lying_areas(
            self,
            areas: Any,
            layer_size: tuple[int, int],
            dimensions: Any,
            width: int,
            scale: int,
        ) -> Image.Image: ...

        # _SegmentsRenderMixin
        def render_segment(
            self,
            segment: Any,
            cleanset: Any,
            sequence: Any,
            layer_size: Any,
            dimensions: Any,
            size: Any,
            rotation: Any,
            scale: Any,
            active: Any,
            neglected: Any,
            flip_badge: bool = False,
            name_offset: Any = (0, 0),
        ) -> Any: ...
