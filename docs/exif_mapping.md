# Fujifilm Recipe — EXIF Mapping Reference

## Index

- [Film Simulation](#film-simulation)
- [Color / Saturation](#color--saturation)
- [Color Chrome Effect](#color-chrome-effect)
- [Grain Effect](#grain-effect)
- [White Balance](#white-balance)
- [Tonal Adjustments](#tonal-adjustments)
- [Sharpness, Noise Reduction, and Clarity](#sharpness-noise-reduction-and-clarity)
- [Dynamic Range](#dynamic-range)
- [Monochromatic Color Tuning](#monochromatic-color-tuning)

---

## Film Simulation

### EXIF fields involved

| Field | Exiftool tag | Notes |
|---|---|---|
| `film_simulation` | `Film Mode` | Set for all color simulations; **empty** for Acros, Monochrome, and Sepia |
| `color` | `Saturation` | Used to encode the simulation for Acros, Monochrome, and Sepia variants |

### Decoding logic

```
if film_simulation is not empty:
    → look up in Film Mode table below

elif color is not empty:
    → look up in Saturation table below
```

### Film Mode field values (color simulations)

| Camera menu name | `film_simulation` EXIF value | Display name |
|---|---|---|
| PROVIA/STANDARD | `F0/Standard (Provia)` | Provia |
| VELVIA/VIVID | `F2/Fujichrome (Velvia)` | Velvia |
| ASTIA/SOFT | `F1b/Studio Portrait Smooth Skin Tone (Astia)` | Astia |
| CLASSIC CHROME | `Classic Chrome` | Classic Chrome |
| PRO Neg. Std | `Pro Neg. Std` | Pro Neg. Std |
| PRO Neg. Hi | `Pro Neg. Hi` | Pro Neg. Hi |
| CLASSIC Neg. | `Classic Negative` | Classic Negative |
| ETERNA/CINEMA | `Eterna` | Eterna |
| ETERNA BLEACH BYPASS | `Bleach Bypass` | Eterna Bleach Bypass |
| Reala Ace | `Reala Ace` | Reala Ace |

> **Note:** `Reala Ace` follows the same pattern as other colour simulations (present in the `Film Mode` field).

### Saturation field values (Acros, Monochrome, Sepia)

When the camera is set to a monochromatic or sepia simulation, the `Film Mode`
field is **absent** from the EXIF.  The simulation is encoded in the `Saturation`
field instead.

| Camera menu name | `color` (Saturation) EXIF value | Display name |
|---|---|---|
| ACROS | `Acros` | Acros STD |
| ACROS + Ye | `Acros Yellow Filter` | Acros Yellow |
| ACROS + R | `Acros Red Filter` | Acros Red |
| ACROS + G | `Acros Green Filter` | Acros Green |
| MONOCHROME | `None (B&W)` | Monochrome STD |
| MONOCHROME + Ye | `B&W Yellow Filter` | Monochrome Yellow |
| MONOCHROME + R | `B&W Red Filter` | Monochrome Red |
| MONOCHROME + G | `B&W Green Filter` | Monochrome Green |
| SEPIA | `B&W Sepia` | Sepia |

> **Notes:**
> - When Saturation is a numeric label (e.g. `0 (normal)`, `+2 (high)`) the `Film Mode`
>   field is present and this lookup is not used.

### Key observations

- The dual-source design means you must check `Film Mode` first and fall back to
  `Saturation` — never use `Saturation` alone to determine the simulation for
  color modes (it holds the Color adjustment value there).
- For color simulations, `Saturation` holds the Color recipe setting (e.g.
  `+2 (high)`), not the simulation name.
- For B&W/Acros/Sepia, `Saturation` holds the simulation name and there is no
  separate Color adjustment.

---

## Color / Saturation

### EXIF fields involved

| Field | Exiftool tag | Notes |
|---|---|---|
| `color` | `Saturation` | Dual-purpose: saturation adjustment for colour simulations; simulation name for B&W/Acros/Sepia |

### Dual-purpose behaviour

The `Saturation` EXIF tag is shared between two unrelated meanings depending on the active
film simulation.  See also the [Film Simulation](#film-simulation) section for the B&W/Acros/Sepia lookup.

```
if color is a numeric label (e.g. "0 (normal)", "+2 (high)"):
    → saturation adjustment; decode using table below

elif color is a non-numeric string (e.g. "Acros", "None (B&W)", "Film Simulation"):
    → film simulation name or special case; recipe returns "N/A" for the Color field
```

### Numeric saturation mapping table

| Camera display value | EXIF stored value | Recipe output |
|---|---|---|
| −4 | `-4 (lowest)` | `"-4"` |
| −3 | `-3 (very low)` | `"-3"` |
| −2 | `-2 (low)` | `"-2"` |
| −1 | `-1 (medium low)` | `"-1"` |
| 0 | `0 (normal)` | `"0"` |
| +1 | `+1 (medium high)` | `"+1"` |
| +2 | `+2 (high)` | `"+2"` |
| +3 | `+3 (very high)` | `"+3"` |
| +4 | `+4 (highest)` | `"+4"` |

### Non-numeric values that produce "N/A"

| `color` EXIF value | Reason |
|---|---|
| `None (B&W)` | Monochrome simulation — no saturation adjustment |
| `B&W Red Filter` | Monochrome + Red filter |
| `B&W Yellow Filter` | Monochrome + Yellow filter |
| `B&W Green Filter` | Monochrome + Green filter |
| `B&W Sepia` | Sepia simulation |
| `Acros` | Acros simulation |
| `Acros Red Filter` | Acros + Red filter |
| `Acros Yellow Filter` | Acros + Yellow filter |
| `Acros Green Filter` | Acros + Green filter |
| `Film Simulation` | Saturation controlled by film profile (not user-set) |

### Key observations

- `Film Simulation` appears for some film simulations (e.g. Eterna, Astia, Pro Neg. Std); it means the film profile controls saturation internally and the user cannot override it.
- For B&W/Acros/Sepia simulations the `Film Mode` EXIF field is absent; `Saturation` encodes the simulation name instead.  In those cases the Color recipe field is `"N/A"` — there is no separate saturation adjustment.
- Recipe output for numeric values is a signed integer string: `"-2"`, `"+3"`, `"0"`.

---

## Color Chrome Effect

### EXIF fields involved

| Field | Exiftool tag | Notes |
|---|---|---|
| `color_chrome_effect` | `Color Chrome Effect` | `"Off"`, `"Weak"`, or `"Strong"` |
| `color_chrome_fx_blue` | `Color Chrome FX Blue` | `"Off"`, `"Weak"`, or `"Strong"` |

### Full mapping table

| Camera menu setting | `color_chrome_effect` | `color_chrome_fx_blue` |
|---|---|---|
| CCE: Off / CCFXB: Off | `Off` | `Off` |
| CCE: Weak / CCFXB: Off | `Weak` | `Off` |
| CCE: Strong / CCFXB: Off | `Strong` | `Off` |
| CCE: Off / CCFXB: Weak | `Off` | `Weak` |
| CCE: Off / CCFXB: Strong | `Off` | `Strong` |
| CCE: Weak / CCFXB: Weak | `Weak` | `Weak` |
| CCE: Strong / CCFXB: Strong | `Strong` | `Strong` |

### Key observations

- Both EXIF values map directly to recipe card display values — no translation needed.
- The two fields are fully independent; any combination of `Off`, `Weak`, and `Strong` is valid.
- `color_chrome_effect` (CCE) enhances colour saturation and detail on vivid, highly saturated colours across the full spectrum.
- `color_chrome_fx_blue` (CCFXB) applies the same treatment specifically to blue tones; useful for deepening skies and water without affecting other hues.
- Both fields accept the values `Off`, `Weak`, and `Strong`.

---

## Grain Effect

### EXIF fields involved

| Field | Exiftool tag | Notes |
|---|---|---|
| `grain_effect_roughness` | `Grain Effect Roughness` | `"Off"`, `"Weak"`, or `"Strong"` |
| `grain_effect_size` | `Grain Effect Size` | `"Off"`, `"Small"`, or `"Large"` |

### Full mapping table

| Camera menu setting | `grain_effect_roughness` | `grain_effect_size` |
|---|---|---|
| Grain Effect: Off | `Off` | `Off` |
| Grain Effect: Weak, Small | `Weak` | `Small` |
| Grain Effect: Weak, Large | `Weak` | `Large` |
| Grain Effect: Strong, Small | `Strong` | `Small` |
| Grain Effect: Strong, Large | `Strong` | `Large` |

### Key observations

- The EXIF values map directly to recipe card display values — no translation needed.
- `grain_effect_size` is **always `"Off"`** when `grain_effect_roughness` is `"Off"`.
  The camera never stores a size value independently of roughness.
- When `grain_effect_roughness` is `"Weak"` or `"Strong"`, `grain_effect_size` is
  always either `"Small"` or `"Large"` — never `"Off"`.
- Recipe cards combine both fields into a single label: `"Off"`, `"Weak Small"`,
  `"Weak Large"`, `"Strong Small"`, or `"Strong Large"`.

---

## White Balance

### EXIF fields involved

| Field | Exiftool tag | Notes |
|---|---|---|
| `white_balance` | `White Balance` | The WB mode (e.g. `"Auto"`, `"Daylight"`, `"Kelvin"`) |
| `white_balance_fine_tune` | `White Balance Fine Tune` | Raw EXIF value is 20× the camera display value; normalised on read |
| `color_temperature` | `Color Temperature` | Only present when `white_balance` is `"Kelvin"` |

### WB mode mapping table

| Camera menu name | `white_balance` EXIF value | Recipe display value |
|---|---|---|
| Auto | `Auto` | `Auto` |
| Auto White Priority | `Auto (white priority)` | `Auto (white priority)` |
| Daylight | `Daylight` | `Daylight` |
| Fluorescent (Daylight) | `Daylight Fluorescent` | `Daylight Fluorescent` |
| Incandescent | `Incandescent` | `Incandescent` |
| Kelvin | `Kelvin` | `<value>K` (e.g. `5500K`) |

### Fine tune normalisation

Raw EXIF fine tune values are stored at 20× the camera display value.  `read_image_exif`
divides by 20 on read, producing values in the range −9 to +9 for both channels.

| Raw EXIF value (Red, Blue) | Normalised (÷20) | Recipe display |
|---|---|---|
| `(40, -60)` | `(+2, -3)` | `"Red +2, Blue -3"` |
| `(0, 0)` | `(0, 0)` | `"Red 0, Blue 0"` |
| `(-180, 180)` | `(-9, +9)` | `"Red -9, Blue +9"` |

- Both channels are always present in the output string, even when zero.
- Format is always `"Red <signed_int>, Blue <signed_int>"`.
- Fine tune range: −9 to +9 for both red and blue channels (after normalisation).

### Color temperature (Kelvin mode)

When `white_balance` is `"Kelvin"`, `color_temperature` holds the numeric temperature
value (e.g. `5500`).  The recipe field renders this as `"5500K"`.  For all other WB
modes, `color_temperature` is absent and the recipe field uses the `white_balance`
EXIF value directly.

### Key observations

- `white_balance_fine_tune` normalisation (÷20) is applied in `read_image_exif` at read time; the rest of the codebase always works with the normalised value.
- For Kelvin mode the numeric temperature is stored in a separate field (`color_temperature`), not in `white_balance` itself — the WB field only ever holds the string `"Kelvin"`.
- Fine tune is independent of WB mode; it is present for every mode including Kelvin.

---

## Tonal Adjustments

### EXIF fields involved

| Field | Exiftool tag | Notes |
|---|---|---|
| `highlight_tone` | `Highlight Tone` | Range −2 to +4, step 0.5; integer values carry a label suffix |
| `shadow_tone` | `Shadow Tone` | Range −2 to +4, step 0.5; integer values carry a label suffix |

### Full mapping table — integer values (with label suffix)

| Camera display value | EXIF stored value | Recipe output |
|---|---|---|
| −2 | `-2 (soft)` | `"-2"` |
| −1 | `-1 (medium soft)` | `"-1"` |
| 0 | `0 (normal)` | `"0"` |
| +1 | `+1 (medium hard)` | `"+1"` |
| +2 | `+2 (hard)` | `"+2"` |
| +3 | `+3 (very hard)` | `"+3"` |
| +4 | `+4 (hardest)` | `"+4"` |

### Full mapping table — half-step values (bare float, no label suffix)

| Camera display value | EXIF stored value | Recipe output |
|---|---|---|
| −1.5 | `-1.5` | `"-1.5"` |
| −0.5 | `-0.5` | `"-0.5"` |
| +0.5 | `0.5` | `"+0.5"` |
| +1.5 | `1.5` | `"+1.5"` |
| +2.5 | `2.5` | `"+2.5"` |
| +3.5 | `3.5` | `"+3.5"` |

### Key observations

- Integer values are stored with a descriptive label suffix (e.g. `"-2 (soft)"`, `"+4 (hardest)"`); half-step values are stored as bare floats with no suffix.
- Recipe output is always a signed string with no label: `"-2"`, `"+1.5"`, `"0"` etc.
- `highlight_tone` and `shadow_tone` use the same value set and the same decoding logic.
- When D-Range Priority is active the camera forces both fields to `0 (normal)`; there is no user-adjustable highlight or shadow setting in that mode.

### Database storage

`FujifilmRecipe.highlight` and `FujifilmRecipe.shadow` are `DecimalField(max_digits=4, decimal_places=1)` so that half-step values are preserved exactly.  Using `int` or `float` would silently round `-1.5` to `-2` and `+0.5` to `0` or `1`.

The conversion from the recipe string to the DB field uses `Decimal(s)` directly (see `_parse_numeric` in `src/domain/images/operations.py`).  Never use `round(float(s))` — that was the original bug.

---

## Sharpness, Noise Reduction, and Clarity

### EXIF fields involved

| Field | Exiftool tag | Notes |
|---|---|---|
| `sharpness` | `Sharpness` | Range −4 to +4, step 1; label suffix on every value |
| `noise_reduction` | `Noise Reduction` | Range −4 to +4, step 1; label suffix on every value; legacy `Normal` from older firmware |
| `clarity` | `Clarity` | Range −5 to +5, step 1; bare integer strings, no label suffix |

### Sharpness

#### Mapping table

| Camera display value | EXIF stored value | Recipe output |
|---|---|---|
| −4 | `-4 (softest)` | `"-4"` |
| −3 | `-3 (very soft)` | `"-3"` |
| −2 | `-2 (soft)` | `"-2"` |
| −1 | `-1 (medium soft)` | `"-1"` |
| 0 | `0 (normal)` | `"0"` |
| +1 | `+1 (medium hard)` | `"+1"` |
| +2 | `+2 (hard)` | `"+2"` |
| +3 | `+3 (very hard)` | `"+3"` |
| +4 | `+4 (hardest)` | `"+4"` |
| (film profile) | `Film Simulation` | `"N/A"` |

#### Key observations

- `-4 (softest)` is defined in the exiftool tag table and is included in the enum, though it is rare in practice.
- `Film Simulation` indicates sharpness is controlled by the film profile; recipe returns `"N/A"`.

### Noise Reduction (High ISO NR)

#### Mapping table

| Camera display value | EXIF stored value | Recipe output |
|---|---|---|
| −4 | `-4 (weakest)` | `"-4"` |
| −3 | `-3 (very weak)` | `"-3"` |
| −2 | `-2 (weak)` | `"-2"` |
| −1 | `-1 (medium weak)` | `"-1"` |
| 0 | `0 (normal)` | `"0"` |
| 0 (legacy) | `Normal` | `"0"` |
| +1 | `+1 (medium strong)` | `"+1"` |
| +2 | `+2 (strong)` | `"+2"` |
| +3 | `+3 (very strong)` | `"+3"` |
| +4 | `+4 (strongest)` | `"+4"` |

#### Key observations

- Positive values (`+1` through `+4`) are defined in the exiftool tag table and supported by newer firmware.
- Older firmware stored `"Normal"` instead of `"0 (normal)"` for the centre value; both are treated as `0` in the recipe output.

### Clarity

#### Mapping table

| Camera display value | EXIF stored value | Recipe output |
|---|---|---|
| −5 | `-5` | `"-5"` |
| −4 | `-4` | `"-4"` |
| −3 | `-3` | `"-3"` |
| −2 | `-2` | `"-2"` |
| −1 | `-1` | `"-1"` |
| 0 | `0` | `"0"` |
| +1 | `1` | `"+1"` |
| +2 | `2` | `"+2"` |
| +3 | `3` | `"+3"` |
| +4 | `4` | `"+4"` |
| +5 | `5` | `"+5"` |

#### Key observations

- Raw exiftool output for Clarity is 1000× the display value (e.g. raw `3000` → display `3`); exiftool applies the ÷1000 conversion automatically before the value reaches the codebase.
- Clarity values are stored as bare integer strings with no label suffix — unlike Sharpness and Noise Reduction.
- Recipe output adds a `+` sign for positive values: `"-4"`, `"0"`, `"+3"`.

---

## Dynamic Range

### EXIF fields involved

| Field | Exiftool tag | Notes |
|---|---|---|
| `dynamic_range` | `Dynamic Range` | Always `"Standard"` on modern X-series — not useful |
| `dynamic_range_setting` | `Dynamic Range Setting` | `"Manual"` or `"Auto"` |
| `development_dynamic_range` | `Development Dynamic Range` | The actual DR value: `"100"`, `"200"`, `"400"` |
| `auto_dynamic_range` | `Auto Dynamic Range` | Set when DR-Auto is active, e.g. `"200%"` |
| `d_range_priority` | `D Range Priority` | `"Auto"` or `"Fixed"` when D-Range Priority is active |
| `d_range_priority_auto` | `D Range Priority Auto` | `"Weak"` or `"Strong"` when `d_range_priority = "Fixed"` |
| `picture_mode` | `Picture Mode` | `"HDR"` when HDR drive mode is active |

### Full mapping table

| Camera setting | `dynamic_range_setting` | `development_dynamic_range` | `d_range_priority` | `d_range_priority_auto` | `picture_mode` |
|---|---|---|---|---|---|
| DR100 | `Manual` | `100` | — | — | (normal) |
| DR-Auto | `Auto` | — | — | — | (normal) |
| DR200 | `Manual` | `200` | — | — | (normal) |
| DR400 | `Manual` | `400` | — | — | (normal) |
| D-Range Priority Auto | — | — | `Auto` | — | (normal) |
| D-Range Priority Weak | — | — | `Fixed` | `Weak` | (normal) |
| D-Range Priority Strong | — | — | `Fixed` | `Strong` | (normal) |
| HDR drive mode (800%) | `Manual` | `800` | — | — | `HDR` |

### Key observations

- `dynamic_range` is always `"Standard"` on modern X-series cameras and carries no useful information.
- **DR-Auto** (`dynamic_range_setting = "Auto"`) and **manual DR** (`dynamic_range_setting = "Manual"`) are mutually exclusive with **D-Range Priority** — when `d_range_priority` is present, the `dynamic_range_setting` / `development_dynamic_range` fields are absent.
- **DR800** does not appear as a user-facing menu option on modern X-series cameras (max is DR400). A `development_dynamic_range = "800"` record indicates the image was shot in **HDR drive mode**, identifiable by `picture_mode = "HDR"`. HDR drive mode is not a recipe setting.
- When DR-Auto is active, `auto_dynamic_range` records the value the camera actually applied (e.g. `"200%"`), but this field is not always stored.

### Decoding logic for `dynamic_range` recipe field

```
if picture_mode == "HDR":
    → not a recipe image, skip

if d_range_priority == "Auto":
    → "D-Range Priority Auto"
elif d_range_priority == "Fixed" and d_range_priority_auto == "Weak":
    → "D-Range Priority Weak"
elif d_range_priority == "Fixed" and d_range_priority_auto == "Strong":
    → "D-Range Priority Strong"
elif dynamic_range_setting == "Auto":
    → "DR-Auto"
elif development_dynamic_range == "100":
    → "DR100"
elif development_dynamic_range == "200":
    → "DR200"
elif development_dynamic_range == "400":
    → "DR400"
```

---

## Monochromatic Color Tuning

### EXIF fields involved

| Field | Exiftool tag | Recipe field | Notes |
|---|---|---|---|
| `bw_adjustment` | `BW Adjustment` | `monochromatic_color_warm_cool` | Warm/cool (yellow/blue) axis; range −18 to +18 |
| `bw_magenta_green` | `BW Magenta Green` | `monochromatic_color_magenta_green` | Magenta/green axis; range −18 to +18 |

### Value format

Both fields store signed integer strings with no label suffix.  The EXIF value is a
direct pass-through to the recipe field — no conversion is needed.

| Camera display value | EXIF stored value | Recipe output |
|---|---|---|
| −18 | `"-18"` | `"-18"` |
| −5 | `"-5"` | `"-5"` |
| 0 | `"0"` | `"0"` |
| +3 | `"+3"` | `"+3"` |
| +10 | `"+10"` | `"+10"` |
| +18 | `"+18"` | `"+18"` |

### Availability

Monochromatic color tuning is only available when the active film simulation is
B&W (Monochrome), Acros, or Sepia.  For all colour simulations, both EXIF fields
are **empty** and the recipe returns `"N/A"`.

| Condition | `bw_adjustment` | `bw_magenta_green` | Recipe output |
|---|---|---|---|
| B&W / Acros / Sepia active | signed integer string | signed integer string | value as-is |
| Colour simulation active | `""` (empty) | `""` (empty) | `"N/A"` |

### Key observations

- Both fields are independent; each axis can be set to any value in the −18 to +18 range regardless of the other.
- `bw_adjustment` controls the warm/cool axis: positive values shift towards yellow (warm), negative values shift towards blue (cool).
- `bw_magenta_green` controls the magenta/green axis: positive values shift towards magenta, negative values shift towards green.
- EXIF values are already formatted as signed integer strings (`"+10"`, `"-5"`, `"0"`); no reformatting is required.
