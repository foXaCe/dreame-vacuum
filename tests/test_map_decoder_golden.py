"""Golden-fixture tests for DreameVacuumMapDecoder.

Every hand-built payload elsewhere in this test suite
(``tests/test_map_decoder_paths.py``, ``tests/test_map_decoder_extra.py``) is
constructed with the same mental model as the decoder itself, so a format
quirk the model misses is untestable by construction. This module closes
that gap: it decodes committed wire-format payloads
(``tests/fixtures/maps/*.b64``) through the same public entry point
production code uses (``DreameVacuumMapDecoder.decode_map``) and compares a
privacy-safe subset of the result against a companion
``<name>.expected.json`` snapshot.

Fixture format (see ``docs/dev/capture-map-payload.md`` for the full
rationale and the capture procedure for a real device payload):

- ``tests/fixtures/maps/<name>.b64``: one payload per file, plain text,
  base64 — exactly the string ``DreameVacuumMapDecoder.decode_map_partial``
  / ``decode_map`` receive as ``raw_map`` in production. Text (not binary)
  so payload changes show up as readable diffs in code review.
- ``tests/fixtures/maps/<name>.expected.json``: selected decoded fields
  (frame type, dimensions, robot/charger position, segment count/ids/
  names/types/neighbors). Segment ``name``/``custom_name`` must be
  redacted to generic room names before a real-payload fixture is
  committed (the synthetic seed below is generic by construction: it only
  sets built-in room ``type`` codes, never ``custom_name``).

Today only one fixture is seeded: ``synthetic-baseline.b64``, built from the
same header+grid+JSON helpers as ``test_map_decoder_paths.py`` so the harness
is exercised (and kept green) before any real device payload exists. Once a
maintainer drops a real, redacted payload into ``tests/fixtures/maps/``, this
test picks it up automatically with zero code changes — only a new
``.expected.json`` needs generating (see ``main()`` below).

To (re)generate the ``.expected.json`` for a fixture (inspect the diff
before committing — the snapshot must reflect a *correct* decode, not just
*a* decode):

    python3 -m tests.test_map_decoder_golden synthetic-baseline
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import struct
import sys
from typing import Any
import zlib

import pytest

# py_mini_racer is a HA runtime dependency not always available in test env
try:
    from custom_components.dreame_vacuum.dreame.map_decoder import DreameVacuumMapDecoder
    from custom_components.dreame_vacuum.dreame.vacuum_types import MapFrameType

    HAS_MAP_DECODER = True
except ImportError:
    HAS_MAP_DECODER = False

pytestmark = pytest.mark.skipif(not HAS_MAP_DECODER, reason="py_mini_racer or map_decoder deps not available")

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "maps"
HEADER_FMT = "<HHb11h"


# ---------------------------------------------------------------------------
# Synthetic seed builder (reused/adapted from test_map_decoder_paths.py so the
# harness has something to run against before a real payload is captured)
# ---------------------------------------------------------------------------


def build_header(
    map_id: int = 1,
    frame_id: int = 1,
    frame_type: int = MapFrameType.I.value if HAS_MAP_DECODER else 0,
    robot: tuple[int, int, int] = (0, 0, 0),
    charger: tuple[int, int, int] = (0, 0, 0),
    grid_size: int = 50,
    width: int = 0,
    height: int = 0,
    left: int = 0,
    top: int = 0,
) -> bytes:
    """Pack the 27-byte binary map header (all fields little-endian int16, frame_type is 1 byte)."""
    return struct.pack(
        HEADER_FMT,
        map_id,
        frame_id,
        frame_type,
        robot[0],
        robot[1],
        robot[2],
        charger[0],
        charger[1],
        charger[2],
        grid_size,
        width,
        height,
        left,
        top,
    )


def build_raw_map_str(header: bytes, grid: bytes, meta: dict) -> str:
    """Build the base64(zlib(header+grid+json)) wire payload (unencrypted, cloud object files may add AES-CBC)."""
    payload = header + grid + json.dumps(meta).encode("utf8")
    compressed = zlib.compress(payload)
    return base64.b64encode(compressed).decode("ascii")


def build_synthetic_baseline() -> str:
    """Two-segment 5x5 I-frame: robot/charger positions, generic (non-custom) room names/types."""
    width, height = 5, 5
    grid = bytearray(width * height)
    for x in range(1, 4):
        grid[2 * width + x] = 1  # segment 1 ("Living Room" via type=1 below)
        grid[3 * width + x] = 2  # segment 2 ("Kitchen" via type=4 below)

    header = build_header(
        map_id=99,
        frame_id=1,
        frame_type=MapFrameType.I.value,
        robot=(100, 200, 0),
        charger=(50, 60, 0),
        grid_size=50,
        width=width,
        height=height,
    )
    meta = {
        "seg_inf": {
            "1": {"type": 1, "index": 0, "nei_id": [2]},
            "2": {"type": 4, "index": 0, "nei_id": [1]},
        },
        "timestamp_ms": 1700000000000,
    }
    return build_raw_map_str(header, grid, meta)


# ---------------------------------------------------------------------------
# Golden comparison helper
# ---------------------------------------------------------------------------


def _point_to_dict(point: Any) -> dict[str, Any] | None:
    if point is None:
        return None
    return {"x": point.x, "y": point.y, "a": point.a}


def extract_golden_fields(map_data: Any) -> dict[str, Any]:
    """Pull the privacy-safe, comparable subset of a decoded MapData for golden snapshotting.

    Deliberately excludes the pixel grid (``map_data.data``/``pixel_type``),
    raw JSON tail and anything else that could carry a real floor plan or
    Wi-Fi SSIDs verbatim - only structural/summary fields are compared.
    """
    dims = map_data.dimensions
    segments = map_data.segments or {}
    return {
        "frame_type": map_data.frame_type,
        "dimensions": (
            {
                "width": dims.width,
                "height": dims.height,
                "grid_size": dims.grid_size,
                "left": dims.left,
                "top": dims.top,
            }
            if dims is not None
            else None
        ),
        "robot_position": _point_to_dict(map_data.robot_position),
        "charger_position": _point_to_dict(map_data.charger_position),
        "saved_map": bool(map_data.saved_map),
        "empty_map": bool(map_data.empty_map),
        "segments": {
            str(seg_id): {
                "name": seg.name,
                "type": seg.type,
                "index": seg.index,
                "neighbors": sorted(seg.neighbors or []),
            }
            for seg_id, seg in sorted(segments.items())
        },
    }


def _expected_path(fixture_path: Path) -> Path:
    # "foo.b64" -> "foo.expected.json"
    return fixture_path.with_suffix("").with_suffix(".expected.json")


def _fixture_paths() -> list[Path]:
    if not FIXTURES_DIR.is_dir():
        return []
    return sorted(FIXTURES_DIR.glob("*.b64"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture_path", _fixture_paths(), ids=lambda p: p.stem)
def test_golden_fixture_matches_snapshot(fixture_path: Path) -> None:
    expected_path = _expected_path(fixture_path)
    assert expected_path.exists(), (
        f"Missing snapshot {expected_path.name} for fixture {fixture_path.name}. "
        f"Generate it with: python3 -m tests.test_map_decoder_golden {fixture_path.stem}"
    )

    raw_map = fixture_path.read_text(encoding="utf-8").strip()
    map_data, _saved_map_data = DreameVacuumMapDecoder.decode_map(raw_map, False)

    assert map_data is not None, f"Fixture {fixture_path.name} failed to decode at all"

    actual = extract_golden_fields(map_data)
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert actual == expected


def test_synthetic_baseline_fixture_is_reproducible() -> None:
    """The committed synthetic-baseline.b64 matches what build_synthetic_baseline() produces now.

    Guards against the fixture and its builder drifting apart silently.
    """
    fixture_path = FIXTURES_DIR / "synthetic-baseline.b64"
    if not fixture_path.exists():
        pytest.skip("synthetic-baseline fixture not present")

    assert fixture_path.read_text(encoding="utf-8").strip() == build_synthetic_baseline()


# ---------------------------------------------------------------------------
# Snapshot generator: `python3 -m tests.test_map_decoder_golden <name>`
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"Usage: python3 -m tests.test_map_decoder_golden <fixture-name>", file=sys.stderr)  # noqa: F541
        return 2

    name = argv[1]
    fixture_path = FIXTURES_DIR / f"{name}.b64"
    if not fixture_path.exists():
        print(f"No such fixture: {fixture_path}", file=sys.stderr)
        return 1

    raw_map = fixture_path.read_text(encoding="utf-8").strip()
    map_data, _saved_map_data = DreameVacuumMapDecoder.decode_map(raw_map, False)
    if map_data is None:
        print(f"Fixture {fixture_path.name} failed to decode", file=sys.stderr)
        return 1

    expected_path = _expected_path(fixture_path)
    expected_path.write_text(json.dumps(extract_golden_fields(map_data), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {expected_path} - EYEBALL IT before committing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
