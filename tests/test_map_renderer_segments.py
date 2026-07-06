"""Behavioural tests for the ``_SegmentsRenderMixin`` (``_segments_render.py``).

Exercises ``render_segment`` (badges/labels/order/custom-cleanset icons),
``render_floor_material`` and ``render_carpets`` directly against real
``MapImageDimensions``/``Segment``/``Carpet`` instances, in the same spirit as
``tests/test_map_renderer.py``. Renders produce PIL images; assertions target
verifiable structural properties (size, non-transparent pixel presence,
before/after differences) rather than exact pixel snapshots.
"""

from __future__ import annotations

import numpy as np
import pytest

from custom_components.dreame_vacuum.dreame.map_renderer._core import DreameVacuumMapRenderer
from custom_components.dreame_vacuum.dreame.vacuum_types import (
    Carpet,
    MapImageDimensions,
    Segment,
)


def _dims(width: int = 60, height: int = 60, grid_size: int = 10) -> MapImageDimensions:
    dims = MapImageDimensions(top=0, left=0, height=height, width=width, grid_size=grid_size)
    dims.scale = 2
    dims.padding = [0, 0, 0, 0]
    dims.crop = [0, 0, 0, 0]
    return dims


def _segment(**overrides: object) -> Segment:
    seg = Segment(1, x0=0, y0=0, x1=590, y1=590, x=300, y=300)
    seg.color_index = 0
    for key, value in overrides.items():
        setattr(seg, key, value)
    return seg


def _has_visible_pixels(layer) -> bool:
    return bool((np.array(layer)[:, :, 3] > 0).any())


LAYER_SIZE = (240, 240)


class TestRenderSegmentIconSets:
    @pytest.mark.parametrize("icon_set", [0, 1, 2, 3])
    def test_icon_lookup_per_icon_set(self, icon_set: int) -> None:
        names = {0: None, 1: "Dreame Old", 2: "Mijia", 3: "Material"}
        renderer = DreameVacuumMapRenderer(icon_set=names[icon_set] or "Dreame")
        segment = _segment(type=1)  # Living room -> present in every icon set.
        layer = renderer.render_segment(segment, False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)

    def test_invert_color_scheme_dims_the_segment_icon(self) -> None:
        renderer = DreameVacuumMapRenderer(color_scheme="Grayscale")  # invert=True
        assert renderer.color_scheme.invert is True
        segment = _segment(type=1)
        layer = renderer.render_segment(segment, False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)
        # Icon is cached after first render.
        assert segment.icon_type in renderer._segment_icons

    def test_unknown_icon_type_has_no_icon_but_still_renders_text(self) -> None:
        renderer = DreameVacuumMapRenderer()
        # A segment type of 999 has no dedicated icon in any icon set -> icon stays None,
        # falling back to the plain-text (no icon) layout branch.
        segment = _segment(type=999)
        layer = renderer.render_segment(segment, False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)
        assert renderer._segment_icons.get(segment.icon_type) is None


class TestRenderSegmentNeglectedOffsets:
    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_neglected_offset_direction_changes_with_rotation(self, rotation: int) -> None:
        renderer = DreameVacuumMapRenderer()
        segment = _segment(type=1)
        layer = renderer.render_segment(segment, False, False, LAYER_SIZE, _dims(), 10, rotation, 2, True, True)
        assert _has_visible_pixels(layer)

    def test_neglected_badge_differs_from_active_badge(self) -> None:
        renderer = DreameVacuumMapRenderer()
        segment_active = _segment(type=1)
        segment_neglected = _segment(type=1)
        active_layer = renderer.render_segment(segment_active, False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        neglected_layer = renderer.render_segment(
            segment_neglected, False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, True
        )
        assert (np.array(active_layer) != np.array(neglected_layer)).any()


class TestRenderSegmentNameBackgroundBranches:
    def test_no_name_background_light_scheme_uses_dark_text(self) -> None:
        renderer = DreameVacuumMapRenderer(hidden_map_objects=["icon", "name_background"])
        assert renderer.config.name_background is False
        segment = _segment(type=1)
        layer = renderer.render_segment(segment, False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)

    def test_no_name_background_dark_scheme_uses_light_text(self) -> None:
        renderer = DreameVacuumMapRenderer(color_scheme="Dreame Dark", hidden_map_objects=["icon", "name_background"])
        segment = _segment(type=1)
        layer = renderer.render_segment(segment, False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)

    def test_name_background_with_invert_scheme_and_non_mijia_icon_set(self) -> None:
        renderer = DreameVacuumMapRenderer(color_scheme="Grayscale")  # invert=True, icon_set default 0
        segment = _segment(type=1)
        layer = renderer.render_segment(segment, False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)

    def test_active_without_text_font_draws_plain_ellipse_badge(self) -> None:
        # name off + icon on + segment.type == 0 (custom-name room, no dedicated icon and
        # no rendered text since config.name is False and text_font stays falsy) hits the
        # "elif active:" ellipse-only badge branch.
        renderer = DreameVacuumMapRenderer(hidden_map_objects=["name"])
        segment = _segment(type=0, custom_name=None, index=0)
        layer = renderer.render_segment(segment, False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)


class TestRenderSegmentOrderBadge:
    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_order_badge_renders_for_each_rotation(self, rotation: int) -> None:
        renderer = DreameVacuumMapRenderer()
        segment = _segment(type=1, order=2)
        layer = renderer.render_segment(segment, False, True, LAYER_SIZE, _dims(), 10, rotation, 2, True, False)
        assert _has_visible_pixels(layer)

    def test_order_badge_flip_changes_arrow_position(self) -> None:
        renderer = DreameVacuumMapRenderer()
        segment_a = _segment(type=1, order=1)
        segment_b = _segment(type=1, order=1)
        normal = renderer.render_segment(
            segment_a, False, True, LAYER_SIZE, _dims(), 10, 0, 2, True, False, flip_badge=False
        )
        flipped = renderer.render_segment(
            segment_b, False, True, LAYER_SIZE, _dims(), 10, 0, 2, True, False, flip_badge=True
        )
        assert (np.array(normal) != np.array(flipped)).any()

    def test_order_badge_without_sequence_is_not_drawn(self) -> None:
        renderer = DreameVacuumMapRenderer()
        with_seq = renderer.render_segment(
            _segment(type=1, order=1), False, True, LAYER_SIZE, _dims(), 10, 0, 2, True, False
        )
        without_seq = renderer.render_segment(
            _segment(type=1, order=1), False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False
        )
        assert (np.array(with_seq) != np.array(without_seq)).any()

    def test_name_offset_shifts_badge_position(self) -> None:
        renderer = DreameVacuumMapRenderer()
        default_offset = renderer.render_segment(
            _segment(type=1), False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False
        )
        shifted = renderer.render_segment(
            _segment(type=1), False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False, name_offset=(20, 20)
        )
        assert (np.array(default_offset) != np.array(shifted)).any()


class TestRenderSegmentCustomCleanset:
    @staticmethod
    def _renderer() -> DreameVacuumMapRenderer:
        renderer = DreameVacuumMapRenderer()
        # render_segment() is normally only reached via render_map(), which
        # warms the icon sets first; called directly here, so warm them up.
        renderer._warm_up_icons()
        return renderer

    def test_all_custom_fields_with_cleaning_mode_sweep_and_mop(self) -> None:
        renderer = self._renderer()
        segment = _segment(
            type=1,
            suction_level=2,
            water_volume=2,
            cleaning_times=2,
            cleaning_mode=2,  # sweep-and-mop -> suction AND water icons both drawn
        )
        layer = renderer.render_segment(segment, True, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)

    def test_cleaning_mode_sweep_only_skips_water_icon(self) -> None:
        renderer = self._renderer()
        segment = _segment(type=1, suction_level=1, water_volume=2, cleaning_times=1, cleaning_mode=0)
        layer = renderer.render_segment(segment, True, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)

    def test_cleaning_mode_mop_only_skips_suction_icon_and_draws_route(self) -> None:
        renderer = self._renderer()
        segment = _segment(
            type=1,
            suction_level=1,
            water_volume=2,
            cleaning_times=1,
            cleaning_mode=1,
            cleaning_route=2,
            custom_mopping_route=None,
        )
        layer = renderer.render_segment(segment, True, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)

    def test_custom_mopping_route_icon_used_instead_of_mop_pad_humidity(self) -> None:
        renderer = self._renderer()
        segment = _segment(
            type=1,
            water_volume=2,
            cleaning_mode=2,
            cleaning_route=2,
            custom_mopping_route=3,
        )
        layer = renderer.render_segment(segment, True, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)

    def test_cleaning_route_without_custom_route_uses_mop_pad_humidity_icon(self) -> None:
        renderer = self._renderer()
        segment = _segment(
            type=1,
            water_volume=2,
            cleaning_mode=2,
            cleaning_route=None,
            custom_mopping_route=None,
        )
        layer = renderer.render_segment(segment, True, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)

    def test_out_of_range_cleaning_mode_is_treated_as_none(self) -> None:
        renderer = self._renderer()
        segment = _segment(type=1, suction_level=1, water_volume=1, cleaning_times=1, cleaning_mode=99)
        layer = renderer.render_segment(segment, True, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)

    def test_disabled_config_flags_shrink_icon_row(self) -> None:
        renderer = DreameVacuumMapRenderer(hidden_map_objects=["suction_level", "cleaning_mode"])
        renderer._warm_up_icons()
        segment = _segment(type=1, suction_level=1, water_volume=1, cleaning_times=1, cleaning_mode=2)
        full = self._renderer().render_segment(
            _segment(type=1, suction_level=1, water_volume=1, cleaning_times=1, cleaning_mode=2),
            True,
            False,
            LAYER_SIZE,
            _dims(),
            10,
            0,
            2,
            True,
            False,
        )
        reduced = renderer.render_segment(segment, True, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert (np.array(full) != np.array(reduced)).any()

    def test_neglected_segment_never_shows_custom_badges(self) -> None:
        renderer = self._renderer()
        active_seg = _segment(type=1, suction_level=1, water_volume=1, cleaning_times=1, cleaning_mode=2)
        neglected_seg = _segment(type=1, suction_level=1, water_volume=1, cleaning_times=1, cleaning_mode=2)
        active_layer = renderer.render_segment(active_seg, True, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        neglected_layer = renderer.render_segment(neglected_seg, True, False, LAYER_SIZE, _dims(), 10, 0, 2, True, True)
        assert (np.array(active_layer) != np.array(neglected_layer)).any()

    def test_inactive_segment_skips_custom_badges(self) -> None:
        renderer = self._renderer()
        active_seg = _segment(type=1, suction_level=1, water_volume=1, cleaning_times=1, cleaning_mode=2)
        inactive_seg = _segment(type=1, suction_level=1, water_volume=1, cleaning_times=1, cleaning_mode=2)
        active_layer = renderer.render_segment(active_seg, True, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        inactive_layer = renderer.render_segment(inactive_seg, True, False, LAYER_SIZE, _dims(), 10, 0, 2, False, False)
        assert (np.array(active_layer) != np.array(inactive_layer)).any()

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_custom_badge_renders_for_each_rotation(self, rotation: int) -> None:
        renderer = self._renderer()
        segment = _segment(type=1, suction_level=1, water_volume=1, cleaning_times=1, cleaning_mode=2)
        layer = renderer.render_segment(segment, True, False, LAYER_SIZE, _dims(), 10, rotation, 2, True, False)
        assert _has_visible_pixels(layer)

    def test_order_and_custom_together(self) -> None:
        renderer = self._renderer()
        segment = _segment(type=1, order=1, suction_level=1, water_volume=1, cleaning_times=1, cleaning_mode=2)
        layer = renderer.render_segment(segment, True, True, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert _has_visible_pixels(layer)


class TestRenderSegmentEmptyCoordinates:
    def test_missing_x_y_returns_empty_layer(self) -> None:
        renderer = DreameVacuumMapRenderer()
        segment = Segment(1, x0=0, y0=0, x1=100, y1=100)  # x/y left as None
        layer = renderer.render_segment(segment, False, False, LAYER_SIZE, _dims(), 10, 0, 2, True, False)
        assert not _has_visible_pixels(layer)


# ---------------------------------------------------------------------------
# render_floor_material
# ---------------------------------------------------------------------------


class TestRenderFloorMaterial:
    @staticmethod
    def _pixel_type_and_image(width: int = 30, height: int = 30, scale: int = 2) -> tuple[np.ndarray, np.ndarray]:
        pixel_type = np.zeros((width, height), dtype=np.uint8)
        pixel_type[2:28, 2:28] = 1  # a single segment covering most of the map
        image = np.zeros((height * scale, width * scale, 4), dtype=np.uint8)
        image[...] = (200, 200, 200, 255)  # neutral grey so the alpha-composited overlay is visible
        return pixel_type, image

    def test_default_tile_pattern_paints_pixels(self) -> None:
        renderer = DreameVacuumMapRenderer()
        pixel_type, image = self._pixel_type_and_image()
        dims = _dims(width=30, height=30, grid_size=10)
        before = image.copy()
        result = renderer.render_floor_material(image, {1: 3}, pixel_type, (0, 0, 0, 50), dims, 2)
        assert result is not None
        assert not np.array_equal(before, result)

    def test_herringbone_diagonal_pattern_paints_pixels(self) -> None:
        renderer = DreameVacuumMapRenderer()
        pixel_type, image = self._pixel_type_and_image()
        dims = _dims(width=30, height=30, grid_size=10)
        before = image.copy()
        result = renderer.render_floor_material(image, {1: 1}, pixel_type, (0, 0, 0, 50), dims, 2)
        assert result is not None
        assert not np.array_equal(before, result)

    def test_vertical_plank_pattern_paints_pixels(self) -> None:
        renderer = DreameVacuumMapRenderer()
        pixel_type, image = self._pixel_type_and_image()
        dims = _dims(width=30, height=30, grid_size=10)
        before = image.copy()
        result = renderer.render_floor_material(image, {1: 2}, pixel_type, (0, 0, 0, 50), dims, 2)
        assert result is not None
        assert not np.array_equal(before, result)

    def test_no_matching_floor_types_returns_none(self) -> None:
        renderer = DreameVacuumMapRenderer()
        pixel_type, image = self._pixel_type_and_image()
        dims = _dims(width=30, height=30, grid_size=10)
        # Floor type 0 and >=4 are filtered out by "v > 0 and v < 4".
        result = renderer.render_floor_material(image, {1: 0, 2: 5}, pixel_type, (0, 0, 0, 50), dims, 2)
        assert result is None

    def test_color_cache_reused_for_repeated_segment_value(self) -> None:
        renderer = DreameVacuumMapRenderer()
        pixel_type, image = self._pixel_type_and_image()
        dims = _dims(width=30, height=30, grid_size=10)
        # Calling twice on the same renderer/segment exercises the "already in color_map" cache-hit path.
        first = renderer.render_floor_material(image.copy(), {1: 3}, pixel_type, (0, 0, 0, 50), dims, 2)
        second = renderer.render_floor_material(image.copy(), {1: 3}, pixel_type, (0, 0, 0, 50), dims, 2)
        assert first is not None
        assert second is not None


# ---------------------------------------------------------------------------
# render_carpets
# ---------------------------------------------------------------------------


class TestRenderCarpets:
    @staticmethod
    def _pixel_type(width: int = 30, height: int = 30) -> np.ndarray:
        pixel_type = np.zeros((width, height), dtype=np.uint8)
        pixel_type[2:28, 2:28] = 1
        return pixel_type

    @staticmethod
    def _image(width: int = 30, height: int = 30, scale: int = 1) -> np.ndarray:
        image = np.zeros((height * scale, width * scale, 4), dtype=np.uint8)
        image[...] = (200, 200, 200, 255)  # neutral grey so the alpha-composited overlay is visible
        return image

    def test_carpet_pixels_direct_paints_area(self) -> None:
        renderer = DreameVacuumMapRenderer()
        dims = _dims(width=30, height=30, grid_size=10)
        pixel_type = self._pixel_type()
        image = self._image()
        before = image.copy()
        result = renderer.render_carpets(
            image, pixel_type, None, None, None, [(10, 10), (11, 11)], None, (0, 0, 0, 80), (0, 0, 0, 35), dims, 1
        )
        assert not np.array_equal(before, result)

    def test_detected_carpet_rectangle_paints_area(self) -> None:
        renderer = DreameVacuumMapRenderer()
        dims = _dims(width=30, height=30, grid_size=10)
        pixel_type = self._pixel_type()
        image = self._image()
        carpet = Carpet(1, x0=50, y0=50, x1=200, y1=50, x2=200, y2=200, x3=50, y3=200, ellipse=0)
        before = image.copy()
        result = renderer.render_carpets(
            image, pixel_type, None, None, [carpet], None, None, (0, 0, 0, 80), (0, 0, 0, 35), dims, 1
        )
        assert not np.array_equal(before, result)

    def test_detected_carpet_large_polygon_uses_optimized_pixels(self) -> None:
        renderer = DreameVacuumMapRenderer()
        dims = _dims(width=30, height=30, grid_size=10)
        pixel_type = self._pixel_type()
        image = self._image()
        # >100 polygon coordinates forces the _optimize_carpet_pixels() fast-path.
        polygon = []
        for i in range(60):
            polygon.extend([50 + i, 50])
        carpet = Carpet(1, x0=50, y0=50, x1=200, y1=50, x2=200, y2=200, x3=50, y3=200, ellipse=0, polygon=polygon)
        carpet_pixels = [(x, 24) for x in range(5, 25)]
        result = renderer.render_carpets(
            image, pixel_type, None, None, [carpet], carpet_pixels, None, (0, 0, 0, 80), (0, 0, 0, 35), dims, 1
        )
        assert result is not None

    def test_segment_floor_material_carpet_range_paints_area(self) -> None:
        renderer = DreameVacuumMapRenderer()
        dims = _dims(width=30, height=30, grid_size=10)
        pixel_type = self._pixel_type()
        image = self._image()
        segment = _segment(x0=20, y0=20, x1=270, y1=270)
        segment.floor_material = 6  # in (4, 8) exclusive range -> carpet-eligible
        before = image.copy()
        result = renderer.render_carpets(
            image, pixel_type, None, None, None, None, {1: segment}, (0, 0, 0, 80), (0, 0, 0, 35), dims, 1
        )
        assert not np.array_equal(before, result)

    def test_ignored_carpets_remove_previously_marked_pixels(self) -> None:
        # ignored_carpets is processed before carpets/detected_carpets in
        # render_carpets, so it only actually suppresses paint when the
        # coordinate isn't also re-marked by a later "carpets"/"detected_carpets"
        # entry: pair it with detected_carpets (which runs before it) instead.
        renderer = DreameVacuumMapRenderer()
        dims = _dims(width=30, height=30, grid_size=10)
        pixel_type = self._pixel_type()
        carpet = Carpet(1, x0=50, y0=50, x1=200, y1=50, x2=200, y2=200, x3=50, y3=200, ellipse=0)

        image_detected = self._image()
        detected_only = renderer.render_carpets(
            image_detected, pixel_type, None, None, [carpet], None, None, (0, 0, 0, 80), (0, 0, 0, 35), dims, 1
        )

        image_ignored = self._image()
        detected_and_ignored = renderer.render_carpets(
            image_ignored, pixel_type, None, [carpet], [carpet], None, None, (0, 0, 0, 80), (0, 0, 0, 35), dims, 1
        )
        assert not np.array_equal(detected_only, detected_and_ignored)

    def test_added_carpets_use_carpet_color(self) -> None:
        renderer = DreameVacuumMapRenderer()
        dims = _dims(width=30, height=30, grid_size=10)
        pixel_type = self._pixel_type()
        image = self._image()
        carpet = Carpet(1, x0=50, y0=50, x1=200, y1=50, x2=200, y2=200, x3=50, y3=200, ellipse=0)
        before = image.copy()
        result = renderer.render_carpets(
            image, pixel_type, [carpet], None, None, None, None, (0, 0, 0, 80), (0, 0, 0, 35), dims, 1
        )
        assert not np.array_equal(before, result)
