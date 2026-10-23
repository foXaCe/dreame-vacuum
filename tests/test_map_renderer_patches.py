"""Layer patches must render exactly like the full-size layers they replace.

The renderer keeps object layers as ``LayerPatch`` (their non-transparent
bounding box) and blends them in place instead of compositing full-size
layers. These tests pin that every helper gives the same visible pixels as
the plain ``Image.alpha_composite`` / ``thumbnail`` pipeline it replaced.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
import pytest

from custom_components.dreame_vacuum.dreame.map_renderer._core import DreameVacuumMapRenderer
from custom_components.dreame_vacuum.dreame.map_renderer._helpers import BLANK_PIXEL, LayerPatch

SIZE = (120, 96)


def _sparse_layer(seed: int, size: tuple[int, int] = SIZE) -> Image.Image:
    """Blank layer with a few antialiased, semi-transparent shapes on it."""
    rng = np.random.default_rng(seed)
    layer = Image.new("RGBA", size, BLANK_PIXEL)
    draw = ImageDraw.Draw(layer, "RGBA")
    for _ in range(3):
        x0, y0 = int(rng.integers(0, size[0] - 20)), int(rng.integers(0, size[1] - 20))
        color = tuple(int(c) for c in rng.integers(0, 256, 4))
        draw.ellipse([x0, y0, x0 + int(rng.integers(5, 20)), y0 + int(rng.integers(5, 20))], fill=color)
    return layer


def _background(size: tuple[int, int] = SIZE) -> Image.Image:
    rng = np.random.default_rng(42)
    return Image.fromarray(rng.integers(0, 256, (size[1], size[0], 4), dtype=np.uint8), "RGBA")


def _composited(background: Image.Image, layer: Image.Image | LayerPatch) -> np.ndarray:
    image = background.copy()
    DreameVacuumMapRenderer._composite_onto(image, layer)
    return np.asarray(image)


def test_from_layer_crops_to_the_visible_pixels() -> None:
    layer = Image.new("RGBA", SIZE, BLANK_PIXEL)
    layer.putpixel((10, 20), (1, 2, 3, 4))
    patch = LayerPatch.from_layer(layer)
    assert patch.offset == (10, 20)
    assert patch.image.size == (1, 1)
    assert patch.size == SIZE


def test_from_layer_of_a_blank_layer_has_no_image() -> None:
    patch = LayerPatch.from_layer(Image.new("RGBA", SIZE, BLANK_PIXEL))
    assert patch.image is None
    patch.close()


@pytest.mark.parametrize("seed", range(5))
def test_composite_onto_matches_alpha_composite(seed: int) -> None:
    layer = _sparse_layer(seed)
    expected = np.asarray(Image.alpha_composite(_background(), layer))
    assert (_composited(_background(), layer) == expected).all()
    assert (_composited(_background(), LayerPatch.from_layer(layer)) == expected).all()


@pytest.mark.parametrize("align", [1, 2])
def test_merge_layers_matches_compositing_full_layers(align: int) -> None:
    layers = [_sparse_layer(seed) for seed in range(4)]
    full = Image.new("RGBA", SIZE, BLANK_PIXEL)
    for layer in layers:
        full = Image.alpha_composite(full, layer)

    mixed = [layers[0], LayerPatch.from_layer(layers[1]), layers[2], LayerPatch.from_layer(layers[3])]
    merged = DreameVacuumMapRenderer._merge_layers(mixed, SIZE, align)
    assert merged.offset[0] % align == 0
    assert merged.offset[1] % align == 0
    assert (_composited(_background(), merged) == np.asarray(Image.alpha_composite(_background(), full))).all()


def test_merge_layers_of_nothing_visible_is_empty() -> None:
    merged = DreameVacuumMapRenderer._merge_layers(
        [Image.new("RGBA", SIZE, BLANK_PIXEL), LayerPatch(None, (0, 0), SIZE)], SIZE
    )
    assert merged.image is None


@pytest.mark.parametrize("factor", [2, 3, 4])
def test_downscale_patch_matches_thumbnail(factor: int) -> None:
    size = (SIZE[0] // factor, SIZE[1] // factor)
    layers = [_sparse_layer(seed) for seed in range(3)]
    full = Image.new("RGBA", SIZE, BLANK_PIXEL)
    for layer in layers:
        full = Image.alpha_composite(full, layer)
    full.thumbnail(size, Image.Resampling.BOX, reducing_gap=1.5)

    downscaled = DreameVacuumMapRenderer._downscale_patch(DreameVacuumMapRenderer._merge_layers(layers, SIZE, 2), size)
    assert downscaled.size == size
    expected = np.asarray(Image.alpha_composite(_background(size), full))
    assert (_composited(_background(size), downscaled) == expected).all()


def test_new_layer_recycles_the_kept_layer_blank() -> None:
    renderer = DreameVacuumMapRenderer()
    layer = renderer._new_layer(SIZE)
    layer.paste((9, 9, 9, 9), (0, 0, 10, 10))
    patch = renderer._keep_patch(layer)
    assert patch.image.size == (10, 10)

    again = renderer._new_layer(SIZE)
    assert again is layer
    assert np.asarray(again).tolist() == np.asarray(Image.new("RGBA", SIZE, BLANK_PIXEL)).tolist()
    # Handed out once only, and never for another size.
    assert renderer._new_layer(SIZE) is not layer
    assert renderer._keep_patch(None) is None
