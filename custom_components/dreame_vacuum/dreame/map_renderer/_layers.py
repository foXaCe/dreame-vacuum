"""Layer composition mixin for :class:`DreameVacuumMapRenderer`.

Orchestrates the per-object render methods (from :class:`_ObjectsMixin`,
:class:`_ShapesMixin` and :class:`_SegmentsRenderMixin`) into cached
layer dicts: charger/robot positioning, object layer composition, the
public ``render_objects``/``render_path`` entry points, and the badge/name
overlap resolution used when laying out segment labels. Extracted from
the monolithic ``_core.py`` module.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from PIL import Image, ImageDraw

from ..vacuum_types import MapRendererLayer, ObstacleType, PathType, Point, RobotType
from ._base import _MapRendererState

_LOGGER = logging.getLogger(__name__)


class _LayersMixin(_MapRendererState):
    """Builds and caches the charger/robot/object render layers."""

    def _render_charger_layer(
        self,
        cached_layers: Any,
        map_data: Any,
        station_status: Any,
        changes: Any,
        layers: Any,
        layer_size: Any,
        robot_icon_size: Any,
        scale: Any,
    ) -> None:
        """Render the charger position layer."""
        layer = MapRendererLayer.CHARGER
        if map_data.charger_position and self.config.charger:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.charger_position != map_data.charger_position
                or self._map_data.rotation != map_data.rotation
                or self._station_status != station_status
                or not cached_layers.get(layer)
            ):
                charger_position = map_data.charger_position
                offset = 0
                if self._robot_type != RobotType.VSLAM and self.icon_set == 2:
                    offset = int(robot_icon_size * 21.42)
                elif self._robot_type == RobotType.VSLAM and self.icon_set == 3:
                    offset = int(-robot_icon_size * 18)

                if offset:
                    charger_position = Point(
                        charger_position.x - offset * math.cos(charger_position.a * math.pi / 180),
                        charger_position.y - offset * math.sin(charger_position.a * math.pi / 180),
                        charger_position.a,
                    )

                changes.append(layer)
                cached_layers[layer] = self.render_charger(
                    charger_position,
                    station_status,
                    layer_size,
                    map_data.dimensions,
                    int((robot_icon_size * (map_data.dimensions.scale if map_data.dimensions.scale > 2 else 3)) * 1.2),
                    map_data.rotation,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

    def _render_robot_layer(
        self,
        cached_layers: Any,
        map_data: Any,
        robot_status: Any,
        station_status: Any,
        changes: Any,
        layers: Any,
        layer_size: Any,
        robot_icon_size: Any,
        scale: Any,
    ) -> None:
        """Render the robot position layer."""
        layer = MapRendererLayer.ROBOT
        if not map_data.saved_map and map_data.robot_position and self.config.robot:
            layers.append(layer)

            current_is_washing = False
            if station_status >= 10:
                test_status = station_status - 10
                current_is_washing = 1 < test_status < 4
            else:
                current_is_washing = 1 < station_status < 4

            if (
                not self._cache
                or self._map_data is None
                or self._map_data.robot_position != map_data.robot_position
                or self._map_data.charger_position != map_data.charger_position
                or self._map_data.rotation != map_data.rotation
                or self._robot_status != robot_status
                or self._station_status != station_status
                or self._map_data.docked != map_data.docked
                or not cached_layers.get(layer)
                or current_is_washing
            ):
                robot_position = map_data.robot_position

                if map_data.docked and map_data.charger_position:
                    charger_angle = map_data.charger_position.a
                    if self._robot_type != RobotType.VSLAM:
                        offset = int(
                            robot_icon_size * (15 if self._robot_type == RobotType.SWEEPING_AND_MOPPING else 21.42)
                        )

                        if self.icon_set != 2:
                            if (charger_angle > -45 and charger_angle < 45) or (
                                (charger_angle > -45 and charger_angle <= 45)
                                or (charger_angle > 315 and charger_angle <= 405)
                            ):
                                charger_angle = 0
                            elif (charger_angle > 45 and charger_angle <= 135) or (
                                charger_angle > -315 and charger_angle <= -225
                            ):
                                charger_angle = 90
                            elif (charger_angle > 135 and charger_angle <= 225) or (
                                charger_angle > -225 and charger_angle <= -135
                            ):
                                charger_angle = 180
                            elif (charger_angle > 225 and charger_angle <= 315) or (
                                charger_angle > -135 and charger_angle <= -45
                            ):
                                charger_angle = 270
                    else:
                        offset = int(robot_icon_size * 35.71)

                    robot_position = Point(
                        map_data.charger_position.x + offset * math.cos(charger_angle * math.pi / 180),
                        map_data.charger_position.y + offset * math.sin(charger_angle * math.pi / 180),
                        (
                            charger_angle + 180
                            if self._robot_type != RobotType.MOPPING
                            and self._robot_type != RobotType.SWEEPING_AND_MOPPING
                            else charger_angle
                        ),
                    )

                changes.append(layer)
                cached_layers[layer] = self.render_vacuum(
                    robot_position,
                    robot_status,
                    layer_size,
                    map_data.dimensions,
                    int(robot_icon_size * (map_data.dimensions.scale if map_data.dimensions.scale > 2 else 3)),
                    map_data.rotation,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

    def _compose_object_layers(
        self, cached_layers: Any, changes: Any, layers: Any, layer_size: Any, map_image: Any
    ) -> Any:
        """Compose all rendered layers into the final OBJECTS layer."""
        if changes or not self._cache:
            old_objects = cached_layers.get(MapRendererLayer.OBJECTS)
            cached_layers[MapRendererLayer.OBJECTS] = Image.new(
                "RGBA",
                [layer_size[0], layer_size[1]],
                (255, 255, 255, 0),
            )
            self._close_image(old_objects)
            for layer in layers:
                if cached_layers.get(layer):
                    if layer in changes:
                        _LOGGER.debug("Render %s", layer.name)
                    old = cached_layers[MapRendererLayer.OBJECTS]
                    cached_layers[MapRendererLayer.OBJECTS] = Image.alpha_composite(old, cached_layers[layer])
                    self._close_image(old)

            if layer_size != map_image.size:
                cached_layers[MapRendererLayer.OBJECTS].thumbnail(
                    map_image.size, Image.Resampling.BOX, reducing_gap=1.5
                )
        else:
            if not cached_layers.get(MapRendererLayer.OBJECTS):
                return map_image

        return Image.alpha_composite(
            map_image,
            cached_layers[MapRendererLayer.OBJECTS],
        )

    def render_objects(
        self, cached_layers: Any, map_data: Any, robot_status: Any, station_status: Any, map_image: Any, scale: Any
    ) -> Any:
        layer_size, line_width, border_width, robot_icon_size, icon_size, segment_icon_size = (
            self._calculate_render_sizes(map_data, map_image, scale)
        )
        changes = []
        layers = []

        layer = MapRendererLayer.NO_MOP
        if (
            (not map_data.saved_map or map_data.recovery_map)
            and map_data.no_mopping_areas
            and self.config.no_mop
            and (not robot_status or robot_status < 100)
        ):
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.no_mopping_areas != map_data.no_mopping_areas
                or (not robot_status or (self._robot_status or 0) < 100) != (not robot_status or robot_status < 100)
                or not cached_layers.get(layer)
            ):
                changes.append(layer)
                cached_layers[layer] = self.render_areas(
                    map_data.no_mopping_areas,
                    self.color_scheme.no_mop_outline,
                    self.color_scheme.no_mop,
                    layer_size,
                    map_data.dimensions,
                    border_width,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.NO_GO
        if (not map_data.saved_map or map_data.recovery_map) and map_data.no_go_areas and self.config.no_go:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.no_go_areas != map_data.no_go_areas
                or not cached_layers.get(layer)
            ):
                changes.append(layer)
                cached_layers[layer] = self.render_areas(
                    map_data.no_go_areas,
                    self.color_scheme.no_go_outline,
                    self.color_scheme.no_go,
                    layer_size,
                    map_data.dimensions,
                    border_width,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.WALL
        if (not map_data.saved_map or map_data.recovery_map) and map_data.virtual_walls and self.config.virtual_wall:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.virtual_walls != map_data.virtual_walls
                or not cached_layers.get(layer)
            ):
                changes.append(layer)
                cached_layers[layer] = self.render_walls(
                    map_data.virtual_walls,
                    self.color_scheme.virtual_wall,
                    layer_size,
                    map_data.dimensions,
                    line_width,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.VIRTUAL_THRESHOLD
        if map_data.virtual_thresholds and self.config.pathway:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.virtual_thresholds != map_data.virtual_thresholds
                or not cached_layers.get(layer)
            ):
                changes.append(layer)
                cached_layers[layer] = self.render_walls(
                    map_data.virtual_thresholds,
                    self.color_scheme.virtual_threshold,
                    layer_size,
                    map_data.dimensions,
                    line_width,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.PASSABLE_THRESHOLD
        if map_data.passable_thresholds and self.config.pathway:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.passable_thresholds != map_data.passable_thresholds
                or not cached_layers.get(layer)
            ):
                changes.append(layer)
                cached_layers[layer] = self.render_thresholds(
                    map_data.passable_thresholds,
                    self.color_scheme.passable_threshold_outline,
                    self.color_scheme.passable_threshold,
                    layer_size,
                    map_data.dimensions,
                    line_width,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.IMPASSABLE_THRESHOLD
        if map_data.impassable_thresholds and self.config.pathway:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.impassable_thresholds != map_data.impassable_thresholds
                or not cached_layers.get(layer)
            ):
                changes.append(layer)
                cached_layers[layer] = self.render_thresholds(
                    map_data.impassable_thresholds,
                    self.color_scheme.impassable_threshold_outline,
                    self.color_scheme.impassable_threshold,
                    layer_size,
                    map_data.dimensions,
                    line_width,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.RAMP
        if map_data.ramps and self.config.ramp:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.ramps != map_data.ramps
                or self._map_data.rotation != map_data.rotation
                or not cached_layers.get(layer)
            ):
                changes.append(layer)
                cached_layers[layer] = self.render_ramps(
                    map_data.ramps,
                    self.color_scheme.ramp_outline,
                    self.color_scheme.ramp,
                    layer_size,
                    map_data.dimensions,
                    line_width,
                    scale,
                    map_data.rotation,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.CURTAIN
        if map_data.curtains and self.config.curtain:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.curtains != map_data.curtains
                or not cached_layers.get(layer)
            ):
                changes.append(layer)
                cached_layers[layer] = self.render_curtains(
                    map_data.curtains,
                    self.color_scheme.curtain,
                    layer_size,
                    map_data.dimensions,
                    line_width,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.LOW_LYING_AREA
        if map_data.low_lying_areas and self.config.low_lying_area:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.low_lying_areas != map_data.low_lying_areas
                or not cached_layers.get(layer)
            ):
                changes.append(layer)
                cached_layers[layer] = self.render_low_lying_areas(
                    map_data.low_lying_areas,
                    layer_size,
                    map_data.dimensions,
                    line_width,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.FURNITURES
        if map_data.furnitures and self.config.furniture:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.furnitures != map_data.furnitures
                or self._map_data.rotation != map_data.rotation
                or not cached_layers.get(layer)
            ):
                if layer not in cached_layers:
                    cached_layers[MapRendererLayer.FURNITURE] = {}
                else:
                    for k in list(cached_layers[MapRendererLayer.FURNITURE].keys()).copy():
                        if k not in map_data.furnitures:
                            self._close_image(cached_layers[MapRendererLayer.FURNITURE].pop(k, None))

                changed = False
                for k, v in map_data.furnitures.items():
                    if (
                        not self._cache
                        or self._map_data is None
                        or k not in cached_layers[MapRendererLayer.FURNITURE]
                        or not self._map_data.furnitures
                        or k not in self._map_data.furnitures
                        or self._map_data.furnitures[k] != v
                        or self._map_data.rotation != map_data.rotation
                    ):
                        changed = True
                        cached_layers[MapRendererLayer.FURNITURE][k] = self.render_furniture(
                            v,
                            map_data.furniture_version,
                            layer_size,
                            map_data.dimensions,
                            int((icon_size * 1.2) * map_data.dimensions.scale),
                            map_data.rotation,
                            scale,
                        )

                if changed:
                    changes.append(layer)
                    self._combine_layers(cached_layers, layer_size, layer, MapRendererLayer.FURNITURE)
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.ACTIVE_AREA
        if not map_data.saved_map and map_data.active_areas and self.config.active_area:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.active_areas != map_data.active_areas
                or not cached_layers.get(layer)
            ):
                changes.append(layer)
                cached_layers[layer] = self.render_areas(
                    map_data.active_areas,
                    self.color_scheme.active_area_outline,
                    self.color_scheme.active_area,
                    layer_size,
                    map_data.dimensions,
                    border_width,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.ACTIVE_POINT
        if not map_data.saved_map and map_data.active_points and self.config.active_point:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.active_points != map_data.active_points
                or not cached_layers.get(layer)
            ):
                changes.append(layer)
                cached_layers[layer] = self.render_points(
                    map_data.active_points,
                    self.color_scheme.active_point_outline,
                    self.color_scheme.active_point,
                    layer_size,
                    map_data.dimensions,
                    border_width,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.SEGMENTS
        if (
            map_data.segments
            and not (map_data.history_map and map_data.task_cruise_points)
            and (
                self.config.icon
                or self.config.name
                or self.config.order
                or self.config.suction_level
                or self.config.water_volume
                or self.config.cleaning_times
                or self.config.cleaning_mode
                or self.config.mopping_mode
            )
        ):
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.segments != map_data.segments
                or self._map_data.rotation != map_data.rotation
                or (not self._map_data.cleaning_map and self._map_data.active_segments != map_data.active_segments)
                or (not self._map_data.cleaning_map and self._map_data.hidden_segments != map_data.hidden_segments)
                or (self._map_data.cleaning_map and self._map_data.neglected_segments != map_data.neglected_segments)
                or bool((not map_data.saved_map or map_data.recovery_map) and self._map_data.cleanset)
                != bool((not map_data.saved_map or map_data.recovery_map) and map_data.cleanset)
                or not cached_layers.get(layer)
            ):
                if MapRendererLayer.SEGMENT not in cached_layers:
                    cached_layers[MapRendererLayer.SEGMENT] = {}
                else:
                    for k in list(cached_layers[MapRendererLayer.SEGMENT].keys()).copy():
                        if k not in map_data.segments:
                            self._close_image(cached_layers[MapRendererLayer.SEGMENT].pop(k, None))

                badge_positions = self._resolve_badge_overlaps(
                    map_data.segments,
                    map_data.dimensions,
                    int(segment_icon_size * map_data.dimensions.scale),
                    map_data.rotation,
                )

                name_offsets = self._resolve_name_overlaps(
                    map_data.segments,
                    map_data.dimensions,
                    int(segment_icon_size * map_data.dimensions.scale),
                    map_data.rotation,
                )

                changed = False
                for k in sorted(map_data.segments.keys()):
                    v = map_data.segments[k]
                    if (
                        not self._cache
                        or self._map_data is None
                        or k not in cached_layers[MapRendererLayer.SEGMENT]
                        or not self._map_data.segments
                        or k not in self._map_data.segments
                        or self._map_data.segments[k] != v
                        or self._map_data.rotation != map_data.rotation
                        or bool((not map_data.saved_map or map_data.recovery_map) and self._map_data.cleanset)
                        != bool((not map_data.saved_map or map_data.recovery_map) and map_data.cleanset)
                        or bool(
                            (not map_data.active_segments or k in map_data.active_segments)
                            and (not map_data.hidden_segments or k not in map_data.hidden_segments)
                            and not map_data.cleaning_map
                        )
                        != bool(
                            (not self._map_data.active_segments or k in self._map_data.active_segments)
                            and (not self._map_data.hidden_segments or k not in self._map_data.hidden_segments)
                            and not self._map_data.cleaning_map
                        )
                        or bool(
                            map_data.cleaning_map and (map_data.neglected_segments and k in map_data.neglected_segments)
                        )
                        != bool(
                            self._map_data.cleaning_map
                            and self._map_data.neglected_segments
                            and k in self._map_data.neglected_segments
                        )
                        or badge_positions.get(k) != self._badge_positions.get(k)
                        or name_offsets.get(k) != self._name_offsets.get(k)
                    ):
                        changed = True
                        cached_layers[MapRendererLayer.SEGMENT][k] = self.render_segment(
                            v,
                            bool((not map_data.saved_map or map_data.recovery_map) and map_data.cleanset),
                            bool((not map_data.saved_map or map_data.recovery_map) and map_data.sequence),
                            layer_size,
                            map_data.dimensions,
                            int(segment_icon_size * map_data.dimensions.scale),
                            map_data.rotation,
                            scale,
                            (
                                (not map_data.active_segments or k in map_data.active_segments)
                                and (not map_data.hidden_segments or k not in map_data.hidden_segments)
                                and not map_data.cleaning_map
                            ),
                            (
                                map_data.cleaning_map
                                and map_data.neglected_segments
                                and k in map_data.neglected_segments
                            ),
                            flip_badge=badge_positions.get(k, False),
                            name_offset=name_offsets.get(k, (0, 0)),
                        )

                self._badge_positions = badge_positions
                self._name_offsets = name_offsets

                if changed:
                    changes.append(layer)
                    self._combine_layers(cached_layers, layer_size, layer, MapRendererLayer.SEGMENT)
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        self._render_charger_layer(
            cached_layers, map_data, station_status, changes, layers, layer_size, robot_icon_size, scale
        )
        self._render_robot_layer(
            cached_layers, map_data, robot_status, station_status, changes, layers, layer_size, robot_icon_size, scale
        )

        layer = MapRendererLayer.ROUTER
        if map_data.router_position and map_data.wifi_map:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.router_position != map_data.router_position
                or self._map_data.rotation != map_data.rotation
                or not cached_layers.get(layer)
            ):
                changes.append(layer)
                cached_layers[layer] = self.render_router(
                    map_data.router_position,
                    layer_size,
                    map_data.dimensions,
                    int((robot_icon_size * 1.25) * map_data.dimensions.scale),
                    map_data.rotation,
                    scale,
                )
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.OBSTACLES
        if not map_data.saved_map and map_data.obstacles and (self.config.obstacle or self.config.pet):
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.obstacles != map_data.obstacles
                or self._map_data.rotation != map_data.rotation
                or not cached_layers.get(layer)
            ):
                if MapRendererLayer.OBSTACLE not in cached_layers:
                    cached_layers[MapRendererLayer.OBSTACLE] = {}
                else:
                    for k in list(cached_layers[MapRendererLayer.OBSTACLE].keys()).copy():
                        if k not in map_data.obstacles:
                            self._close_image(cached_layers[MapRendererLayer.OBSTACLE].pop(k, None))

                changed = False
                for k, v in map_data.obstacles.items():
                    if (
                        not self.config.obstacle
                        and v.type != ObstacleType.PET
                        and v.type != ObstacleType.LIQUID_STAIN
                        and v.type != ObstacleType.DRIED_STAIN
                        and v.type != ObstacleType.MIXED_STAIN
                        and v.type != ObstacleType.DETECTED_STAIN
                    ):
                        continue
                    if (
                        not self.config.stain
                        and v.type != ObstacleType.LIQUID_STAIN
                        and v.type != ObstacleType.DRIED_STAIN
                        and v.type != ObstacleType.MIXED_STAIN
                        and v.type != ObstacleType.DETECTED_STAIN
                    ) or (not self.config.pet and v.type == ObstacleType.PET):
                        continue

                    if (
                        not self._cache
                        or self._map_data is None
                        or k not in cached_layers[MapRendererLayer.OBSTACLE]
                        or not self._map_data.obstacles
                        or k not in self._map_data.obstacles
                        or self._map_data.obstacles[k] != v
                        or self._map_data.rotation != map_data.rotation
                    ):
                        obstacle_image = self.render_obstacle(
                            v,
                            layer_size,
                            map_data.dimensions,
                            int((icon_size * 1.2) * map_data.dimensions.scale),
                            map_data.rotation,
                            scale,
                        )
                        if obstacle_image:
                            changed = True
                            cached_layers[MapRendererLayer.OBSTACLE][k] = obstacle_image
                        elif k in cached_layers[MapRendererLayer.OBSTACLE]:
                            self._close_image(cached_layers[MapRendererLayer.OBSTACLE].pop(k, None))

                if changed:
                    changes.append(layer)
                    self._combine_layers(cached_layers, layer_size, layer, MapRendererLayer.OBSTACLE)
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        layer = MapRendererLayer.CRUISE_POINTS
        if not map_data.saved_map and map_data.active_cruise_points:
            layers.append(layer)
            if (
                not self._cache
                or self._map_data is None
                or self._map_data.active_cruise_points != map_data.active_cruise_points
                or self._map_data.rotation != map_data.rotation
                or not cached_layers.get(layer)
            ):
                if MapRendererLayer.CRUISE_POINT not in cached_layers:
                    cached_layers[MapRendererLayer.CRUISE_POINT] = {}
                else:
                    for k in list(cached_layers[MapRendererLayer.CRUISE_POINT].keys()).copy():
                        if k not in map_data.active_cruise_points:
                            self._close_image(cached_layers[MapRendererLayer.CRUISE_POINT].pop(k, None))

                changed = False
                for k, v in map_data.active_cruise_points.items():
                    if (
                        self._map_data is None
                        or k not in cached_layers[MapRendererLayer.CRUISE_POINT]
                        or not self._map_data.active_cruise_points
                        or k not in self._map_data.active_cruise_points
                        or self._map_data.active_cruise_points[k] != v
                        or self._map_data.rotation != map_data.rotation
                    ):
                        changed = True
                        cached_layers[MapRendererLayer.CRUISE_POINT][k] = self.render_cruise_point(
                            k,
                            v,
                            layer_size,
                            map_data.dimensions,
                            int(round(icon_size * 1.25 * map_data.dimensions.scale)),
                            map_data.rotation,
                            scale,
                        )

                if changed:
                    changes.append(layer)
                    self._combine_layers(cached_layers, layer_size, layer, MapRendererLayer.CRUISE_POINT)
        elif self._cache and cached_layers.get(layer):
            changes.append(layer)
            self._del_layer(cached_layers, layer)

        return self._compose_object_layers(cached_layers, changes, layers, layer_size, map_image)

    # render_areas, render_points, render_walls, render_thresholds,
    # render_curtains, render_ramps: see _ShapesMixin

    def render_path(
        self, path: Any, color: Any, mop_color: Any, layer_size: Any, mask: Any, dimensions: Any, width: Any, scale: Any
    ) -> Any:
        new_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(new_layer, "RGBA")
        sweep = []
        mop = []
        sweep_path = []
        mop_path = []
        path_type = ""

        for point in path:
            p = point.to_img(dimensions)
            if point.path_type == PathType.LINE:
                coords = [p.x * scale, p.y * scale]
                if path_type == PathType.SWEEP_AND_MOP or (path_type == PathType.SWEEP or self._low_memory):
                    sweep_path.extend(coords)

                if not self._low_memory and (path_type == PathType.SWEEP_AND_MOP or path_type == PathType.MOP):
                    mop_path.extend(coords)
            else:
                if mop_path:
                    mop.append(mop_path)

                if sweep_path:
                    sweep.append(sweep_path)

                path_type = point.path_type
                if path_type == PathType.SWEEP_AND_MOP or (path_type == PathType.SWEEP or self._low_memory):
                    sweep_path = [p.x * scale, p.y * scale]
                else:
                    sweep_path = []

                if not self._low_memory and (path_type == PathType.SWEEP_AND_MOP or path_type == PathType.MOP):
                    mop_path = [p.x * scale, p.y * scale]
                else:
                    mop_path = []

        if sweep_path:
            sweep.append(sweep_path)

        if mop_path:
            mop.append(mop_path)

        if mop and mask:
            mop_layer = Image.new("RGBA", layer_size, (255, 255, 255, 0))
            mop_draw = ImageDraw.Draw(mop_layer, "RGBA")

        for path in mop:
            size = width * scale * 10.5
            (mop_draw if mask else draw).line(
                path,
                width=int(round(size)),
                fill=mop_color,
                joint="curve",
            )

        if mop and mask:
            new_layer.paste(mop_layer, (0, 0), mask=mask)

        for path in sweep:
            size = width * scale
            draw.line(
                path,
                width=int(round(size)),
                fill=color,
                joint="curve",
            )
            size = int(math.floor(size / 2))
            draw.ellipse(
                [
                    path[-2] - size,
                    path[-1] - size,
                    path[-2] + size,
                    path[-1] + size,
                ],
                fill=color,
            )
            draw.ellipse(
                [
                    path[0] - size,
                    path[1] - size,
                    path[0] + size,
                    path[1] + size,
                ],
                fill=color,
            )

        return new_layer

    def _resolve_badge_overlaps(self, segments: Any, dimensions: Any, size: Any, rotation: Any) -> Any:
        offset = size * 2.7
        default_offsets = {
            0: (0, -offset),
            90: (offset, 0),
            180: (0, offset),
            270: (-offset, 0),
        }
        dx, dy = default_offsets.get(rotation, (0, -offset))

        badge_centers = {}
        for seg_id, seg in segments.items():
            if seg.x is None or seg.y is None:
                continue
            p = Point(seg.x, seg.y).to_img(dimensions, False)
            badge_centers[seg_id] = (p.x + dx, p.y + dy)

        flipped = {}
        threshold = size * 5
        for _ in range(3):
            changed = False
            ids = sorted(badge_centers.keys())
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    a, b = ids[i], ids[j]
                    ax, ay = badge_centers[a]
                    bx, by = badge_centers[b]
                    dist = math.hypot(ax - bx, ay - by)
                    if dist < threshold:
                        flip_id = max(a, b)
                        if flip_id not in flipped:
                            flipped[flip_id] = True
                            seg = segments[flip_id]
                            p = Point(seg.x, seg.y).to_img(dimensions, False)
                            badge_centers[flip_id] = (p.x - dx, p.y - dy)
                            changed = True
            if not changed:
                break
        return flipped

    def _resolve_name_overlaps(self, segments: Any, dimensions: Any, size: Any, rotation: Any) -> Any:
        """Detect overlapping room name badges and compute offsets to push them apart."""
        centers = {}
        for seg_id, seg in segments.items():
            if seg.x is None or seg.y is None:
                continue
            p = Point(seg.x, seg.y).to_img(dimensions, False)
            centers[seg_id] = [p.x, p.y]

        offsets: dict[Any, Any] = {}
        threshold = size * 3.5

        for _ in range(3):
            changed = False
            ids = sorted(centers.keys())
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    a, b = ids[i], ids[j]
                    ax, ay = centers[a]
                    bx, by = centers[b]
                    dist = math.hypot(ax - bx, ay - by)
                    if dist < threshold:
                        if dist > 0:
                            dx = (ax - bx) / dist
                            dy = (ay - by) / dist
                        else:
                            dx, dy = 0, -1
                        shift = (threshold - dist) / 2 + size * 0.5

                        offsets.setdefault(a, [0, 0])
                        offsets[a][0] += dx * shift
                        offsets[a][1] += dy * shift
                        centers[a] = [ax + dx * shift, ay + dy * shift]

                        offsets.setdefault(b, [0, 0])
                        offsets[b][0] -= dx * shift
                        offsets[b][1] -= dy * shift
                        centers[b] = [bx - dx * shift, by - dy * shift]

                        changed = True
            if not changed:
                break

        return {k: tuple(v) for k, v in offsets.items()}
