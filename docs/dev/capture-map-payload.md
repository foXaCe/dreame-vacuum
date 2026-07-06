# Capturing a real map payload for the golden decoder fixture

This is a maintainer-only, temporary procedure for pulling one raw map
payload off a live device so it can become a committed golden fixture under
`tests/fixtures/maps/` (see `tests/test_map_decoder_golden.py`). It requires
a live/logged-in device and is not something a user should be asked to do
without the maintainer reviewing what comes out first (a payload contains
the home floor plan, room names and possibly Wi-Fi SSIDs — see
"Privacy / redaction" below).

## Why a temporary patch, not DEBUG logging

`DreameVacuumMapDecoder.decode_map_partial` already logs at DEBUG, but only
a 64-character prefix:

```python
# custom_components/dreame_vacuum/dreame/map_decoder.py:204
_LOGGER.debug("raw_map (%d chars): %.64s...", len(raw_data), raw_data)
```

That is enough to confirm a payload arrived, not enough to reconstruct one —
the payload is base64 of zlib-compressed (optionally AES-CBC-encrypted)
binary and cannot be resumed from a truncated prefix. No other call site in
`map_manager.py` logs the full payload at any level. So capturing a complete
payload requires a temporary, never-committed patch that dumps the full
string to a file. This is intentional: no sanctioned always-on flag exists
today (and this plan explicitly keeps it that way — see "Out of scope" in
the parent plan).

## Hook point

The payload arrives at `DreameVacuumMapDecoder.decode_map_partial` /
`decode_map` as a single plain-text base64 string argument (`raw_map` /
`raw_data`) — this is also exactly the text format the fixture files use
(`tests/fixtures/maps/<name>.b64`), so whatever you dump here can be copied
into a fixture file verbatim, no re-encoding needed.

The most convenient interception point is `map_manager.py`'s
`_decode_map_partial`, because it is the single choke point for every
*live* map update — both the cloud-object-download path and the direct
device-property (P-frame) path funnel through it before anything is
decoded:

```python
# custom_components/dreame_vacuum/dreame/map_manager.py:515-516
def _decode_map_partial(self, raw_map: Any, timestamp: Any = None, key: Any = None) -> MapDataPartial | None:
    partial_map = DreameVacuumMapDecoder.decode_map_partial(raw_map, self._aes_iv, key)
```

Temporary patch (do not commit):

```python
def _decode_map_partial(self, raw_map: Any, timestamp: Any = None, key: Any = None) -> MapDataPartial | None:
    with open("/tmp/dreame-map-capture.b64", "w") as f:  # TEMP - DO NOT COMMIT
        f.write(raw_map)
    partial_map = DreameVacuumMapDecoder.decode_map_partial(raw_map, self._aes_iv, key)
```

Restart Home Assistant (or reload the integration) with the target vacuum
actively cleaning (or freshly resumed) so at least one live map update
flows through, then pull `/tmp/dreame-map-capture.b64` off the HA host.
`raw_map` may include a `,<key>` suffix (comma-separated AES key, see
`decode_map_partial`'s `"," in raw_map` branch) — keep it if present, the
decoder splits it back out itself.

### Where `raw_map` comes from, for context

`_decode_map_partial` is called from three places, corresponding to the
three ways a map payload can arrive:

- **Live P-frame, direct device property** (no cloud file download at all):
  `map_manager.py:172`, inside the property-polling loop — `raw_map` is the
  `MAP_DATA` MIoT property value, already the plain base64 string.
- **New object name, cloud object file**: `map_manager.py:563`
  (`_add_cloud_map_data`), fed by `_get_object_file_data` →
  `_get_interim_file_data` → `cloud.get_file(url)`
  (`map_manager.py:451-488`, the actual HTTP GET is at line 482). The HTTP
  response body *is* the base64 string (no extra encoding needed):
  `response.body` in `protocol.py:648-661` (`DreameVacuumProtocol.get_file`).
- **Same cloud-object path, alternate caller**: `map_manager.py:586-587`
  (`_add_raw_map_data`), used e.g. by `map_editor.py::restore_map`.

For a **saved/history/recovery map** instead of a live one, two other
entry points bypass `_decode_map_partial` and call the decoder directly —
patch these instead if you specifically want that kind of payload:

- `get_history_map` — `map_manager.py:1019-1032`, the line to patch is
  right before `DreameVacuumMapDecoder.decode_map(response.decode(), ...)`
  at line 1030-1032.
- `get_recovery_map` — `map_manager.py:1050-1079`, `response.decode()` is
  assigned to `recovery_map_list[index].raw_map` around line 1063 before
  `decode_saved_map` is called at line 1069.

## Privacy / redaction

Before a captured payload is committed to `tests/fixtures/maps/`, it MUST be
reviewed and redacted:

1. The payload's JSON tail (after the header + pixel grid, once
   zlib-decompressed — `zlib.decompress(base64.decodebytes(raw_map...))`)
   contains `seg_inf.<id>.name` (base64-encoded custom room names) in
   plaintext. Replace any custom segment name with a generic placeholder
   (or drop the key entirely) so only built-in room `type` codes remain —
   this reproduces the same generic naming the synthetic seed fixture
   already uses (`SEGMENT_TYPE_CODE_TO_NAME` in `vacuum_types.py`), so no
   personal data ships in the repo.
2. If the payload is a Wi-Fi map (`frame_type == W`), it may contain SSIDs —
   confirm with the donor (realistically: the maintainer) before
   committing, or exclude wifi-map fixtures for now.
3. AES key/IV material (the `,<key>` suffix, or `self._aes_iv`) is
   device-specific secret material — never commit it. If the payload is
   encrypted, decrypt it locally first (or capture from a code path that
   doesn't use encryption) and commit only the plaintext-after-decrypt
   form re-compressed/re-encoded, or skip encrypted fixtures entirely.

## Fixture format (decision)

- Path: `tests/fixtures/maps/<model>-<kind>.b64` — e.g.
  `p2149-saved.b64`, `l10s-pro-live.b64`. One payload per file, **text**
  base64 (not binary) — text diffs review far better than binary blobs in
  git, and this is the exact string type the decoder already expects.
- Companion snapshot: `tests/fixtures/maps/<model>-<kind>.expected.json` —
  selected decoded fields only (frame type, map dimensions, segment
  count/ids/names/types/neighbors, robot/charger position) — never the
  pixel grid or raw JSON tail. See `extract_golden_fields()` in
  `tests/test_map_decoder_golden.py` for the exact field set.
- Generate/refresh a snapshot with:

  ```bash
  python3 -m tests.test_map_decoder_golden <name>
  ```

  Then **eyeball the diff** before committing — the snapshot must reflect a
  correct decode of the fixture, not just whatever the decoder currently
  emits (that would defeat the point of a golden test on the next refactor).

## Maintainer ask

See the executor report for Plan 016 (`NOTES` section) for the exact ask —
summary: run this procedure once against a real device, apply the redaction
rules above, and drop the resulting `.b64` file into
`tests/fixtures/maps/`. `tests/test_map_decoder_golden.py` picks it up with
zero code changes; only the `.expected.json` needs generating (command
above) and a sanity eyeball.
