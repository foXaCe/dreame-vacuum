"""Tests for the segment_id enrichment applied to the rooms attribute.

The camera entity exposes a ``segment_map`` PNG where the blue channel
encodes the room key (after remapping from the raw pixel_type values).
Lovelace cards need the reverse lookup — which raw pixel_type value
corresponds to which room — so we inject it onto each room dict under
``segment_id``. These tests pin that contract.

The camera module pulls in optional native deps (turbojpeg, py_mini_racer)
that aren't guaranteed to be installed in CI or dev. We load
``_find_segment_at`` from source with ``ast`` so the algorithm stays
covered without those heavyweight imports.
"""

from __future__ import annotations

import ast
import pathlib


def _load_find_segment_at():
    """Return the live ``_find_segment_at`` function parsed from camera.py."""
    source = pathlib.Path("custom_components/dreame_vacuum/camera.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_find_segment_at":
            func_src = ast.get_source_segment(source, node)
            namespace: dict = {}
            exec(func_src, namespace)  # nosec B102 -- loading our own source intentionally
            return namespace["_find_segment_at"]
    raise AssertionError("_find_segment_at not found in camera.py")


_find_segment_at = _load_find_segment_at()


def test_find_segment_at_hit() -> None:
    """Direct hit: the center pixel carries the raw pixel_type value."""

    class FakePixelType:
        def __getitem__(self, key):
            x, y = key
            return 7 if (x, y) == (5, 5) else 0

    assert _find_segment_at(FakePixelType(), 5, 5, 10, 10) == 7


def test_find_segment_at_spiral_walk() -> None:
    """The center is empty but a neighbour carries a raw value."""

    class FakePixelType:
        def __getitem__(self, key):
            x, y = key
            return 3 if (x, y) == (6, 5) else 0

    assert _find_segment_at(FakePixelType(), 5, 5, 10, 10) == 3


def test_find_segment_at_background() -> None:
    """Nothing within the search radius → the helper returns 0."""

    class FakePixelType:
        def __getitem__(self, key):
            return 0

    assert _find_segment_at(FakePixelType(), 5, 5, 10, 10) == 0


def test_find_segment_at_ignores_out_of_range_values() -> None:
    """Only raw values in the segment range (0 < v < 64) should match."""

    class FakePixelType:
        def __getitem__(self, key):
            # Floor marker (e.g. 200) must not be picked up.
            return 200

    assert _find_segment_at(FakePixelType(), 5, 5, 10, 10) == 0


def test_segment_id_contract_constants() -> None:
    """The camera imports the ATTR_SEGMENT_ID constant from const.py."""
    from custom_components.dreame_vacuum.dreame.const import ATTR_SEGMENT_ID

    assert ATTR_SEGMENT_ID == "segment_id"
