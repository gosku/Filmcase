# Fujifilm Tonal Adjustments — EXIF Mapping


## EXIF fields involved

| Field | Exiftool tag | Notes |
|---|---|---|
| `highlight_tone` | `Highlight Tone` | Range −2 to +4, step 0.5; integer values carry a label suffix |
| `shadow_tone` | `Shadow Tone` | Range −2 to +4, step 0.5; integer values carry a label suffix |

## Full mapping table — integer values (with label suffix)

| Camera display value | EXIF stored value | Recipe output |
|---|---|---|
| −2 | `-2 (soft)` | `"-2"` |
| −1 | `-1 (medium soft)` | `"-1"` |
| 0 | `0 (normal)` | `"0"` |
| +1 | `+1 (medium hard)` | `"+1"` |
| +2 | `+2 (hard)` | `"+2"` |
| +3 | `+3 (very hard)` | `"+3"` |
| +4 | `+4 (hardest)` | `"+4"` |

## Full mapping table — half-step values (bare float, no label suffix)

| Camera display value | EXIF stored value | Recipe output |
|---|---|---|
| −1.5 | `-1.5` | `"-1.5"` |
| −0.5 | `-0.5` | `"-0.5"` |
| +0.5 | `0.5` | `"+0.5"` |
| +1.5 | `1.5` | `"+1.5"` |
| +2.5 | `2.5` | `"+2.5"` |
| +3.5 | `3.5` | `"+3.5"` |

## Key observations

- Integer values are stored with a descriptive label suffix (e.g. `"-2 (soft)"`, `"+4 (hardest)"`); half-step values are stored as bare floats with no suffix.
- Recipe output is always a signed string with no label: `"-2"`, `"+1.5"`, `"0"` etc.
- `highlight_tone` and `shadow_tone` use the same value set and the same decoding logic.
- When D-Range Priority is active the camera forces both fields to `0 (normal)`; there is no user-adjustable highlight or shadow setting in that mode.

## Database storage

`FujifilmRecipe.highlight` and `FujifilmRecipe.shadow` are `DecimalField(max_digits=4, decimal_places=1)` so that half-step values are preserved exactly.  Using `int` or `float` would silently round `-1.5` to `-2` and `+0.5` to `0` or `1`.

The conversion from the recipe string to the DB field uses `Decimal(s)` directly (see `_parse_numeric` in `src/domain/images/operations.py`).  Never use `round(float(s))` — that was the original bug.
