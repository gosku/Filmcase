# PTP Encodings — Fujifilm Custom Slots

Reference for all PTP property codes and integer encodings used to read and write
Fujifilm custom program slots (C1–Cn).  Implementation lives in
`src/data/camera/constants.py` and `src/domain/camera/queries.py`.

---

## Slot cursor mechanism

Custom-slot properties do not target a slot by themselves.  Before reading or
writing any custom-slot property, write the 1-based slot index to the slot
cursor property:

| Property | Code | Type | Purpose |
|---|---|---|---|
| `PROP_SLOT_CURSOR` | `0xD18C` | uint16 | Selects which slot subsequent reads/writes target |
| `PROP_SLOT_NAME`   | `0xD18D` | PTP string | Display name of the currently selected slot |

Example: to read or write C2, write `2` to `0xD18C` first, then issue
`GetDevicePropValue` / `SetDevicePropValue` on the slot property codes below.

---

## Custom-slot property codes

All properties below use the codes in `CUSTOM_SLOT_CODES` (`constants.py`).

| Property name | Code | Domain field |
|---|---|---|
| `FilmSimulation` | `0xD192` | `film_simulation` |
| `WhiteBalance` | `0xD199` | `white_balance` |
| `WhiteBalanceColorTemperature` | `0xD19C` | `white_balance` (Kelvin value) |
| `WhiteBalanceRed` | `0xD19A` | `white_balance_red` |
| `WhiteBalanceBlue` | `0xD19B` | `white_balance_blue` |
| `DRangeMode` | `0xD190` | `dynamic_range` |
| `DRangePriority` | `0xD191` | `d_range_priority` |
| `GrainEffect` | `0xD195` | `grain_roughness` + `grain_size` |
| `ColorEffect` | `0xD196` | `color_chrome_effect` |
| `ColorFx` | `0xD197` | `color_chrome_fx_blue` |
| `ColorMode` | `0xD19F` | `color` (saturation) |
| `Sharpness` | `0xD1A0` | `sharpness` |
| `HighLightTone` | `0xD19D` | `highlight` |
| `ShadowTone` | `0xD19E` | `shadow` |
| `HighIsoNoiseReduction` | `0xD1A1` | `high_iso_nr` |
| `Definition` | `0xD1A2` | `clarity` |
| `MonochromaticColorWarmCool` | `0xD193` | `monochromatic_color_warm_cool` |
| `MonochromaticColorMagentaGreen` | `0xD194` | `monochromatic_color_magenta_green` |

---

## Write order constraint

`WhiteBalanceColorTemperature` **must be written before** `WhiteBalanceRed` and
`WhiteBalanceBlue`.  Writing the colour temperature resets the shift registers to
zero; any red/blue values written before it are lost.  See
`RecipePTPValues.items()` in `queries.py` for the enforced write order.

---

## Property encodings

### FilmSimulation — `0xD192`

Type: 32-bit int.  Read and write values are identical (`FILM_SIMULATION_TO_PTP`).

| Domain value | PTP value |
|---|---|
| Provia | 1 |
| Velvia | 2 |
| Astia | 3 |
| Pro Neg. Hi | 4 |
| Pro Neg. Std | 5 |
| Monochrome STD | 6 |
| Monochrome Yellow | 7 |
| Monochrome Red | 8 |
| Monochrome Green | 9 |
| Sepia | 10 |
| Classic Chrome | 11 |
| Acros STD | 12 |
| Acros Yellow | 13 |
| Acros Red | 14 |
| Acros Green | 15 |
| Eterna | 16 |
| Classic Negative | 17 |
| Eterna Bleach Bypass | 18 |
| Nostalgic Negative | 19 |
| Reala Ace | 20 |

> Values 19 and 20 are not available on all bodies (e.g. not on X-S10).
> The camera silently ignores writes for unsupported simulations.

---

### WhiteBalance — `0xD199`

Type: 32-bit int.  Read and write values are identical (`WHITE_BALANCE_TO_PTP`).
Source: Fujifilm SDK `XAPI.H` (`XSDK_WB_*` defines).

| Domain value | PTP value (hex) | PTP value (dec) |
|---|---|---|
| Auto | `0x0002` | 2 |
| Auto (white priority) | `0x8020` | 32800 |
| Auto (ambience priority) | `0x8021` | 32801 |
| Daylight | `0x0004` | 4 |
| Incandescent | `0x0006` | 6 |
| Fluorescent 1 | `0x8001` | 32769 |
| Fluorescent 2 | `0x8002` | 32770 |
| Fluorescent 3 | `0x8003` | 32771 |
| Shade | `0x8006` | 32774 |
| Kelvin | `0x8007` | 32775 |
| Underwater | `0x0008` | 8 |
| Custom 1 | `0x8008` | 32776 |
| Custom 2 | `0x8009` | 32777 |
| Custom 3 | `0x800A` | 32778 |

---

### WhiteBalanceColorTemperature — `0xD19C`

Type: 32-bit int.  Raw Kelvin value (e.g. `5500`); no scaling.

Only written when `WhiteBalance` is `Kelvin`.  The property is always present
on read regardless of the active WB mode — when WB is not Kelvin the value is
the camera's last-used temperature and should be ignored.

---

### WhiteBalanceRed / WhiteBalanceBlue — `0xD19A` / `0xD19B`

Type: int16.  Unit scale — no multiplication.  Range: −9 to +9.

The recipe stores these directly; they are passed through to the camera as-is.
Negative values are stored as two's-complement uint16 on the wire
(e.g. `−1` → `0xFFFF`).

---

### DRangeMode — `0xD190`

Type: 32-bit int.  Read and write values are identical (`DRANGE_MODE_TO_PTP`).

| Domain value | PTP value (hex) | PTP value (dec) |
|---|---|---|
| DR-Auto | `0xFFFF` | 65535 |
| DR100 | `0x0064` | 100 |
| DR200 | `0x00C8` | 200 |
| DR400 | `0x0190` | 400 |

> Not written when `DRangePriority` is active (i.e. when `d_range_priority ≠ Off`).

---

### DRangePriority — `0xD191`

Type: 32-bit int.  Read and write values are identical
(`CUSTOM_SLOT_DR_PRIORITY_DECODE`).  Always written; `Off` (0) when D-Range
Priority is not active.

| Domain value | PTP value (hex) | PTP value (dec) |
|---|---|---|
| Off | `0x0000` | 0 |
| Weak | `0x0001` | 1 |
| Strong | `0x0002` | 2 |
| Auto | `0x8000` | 32768 |

---

### GrainEffect — `0xD195`

Type: 32-bit int.  Read and write encodings differ.

**Read** (`CUSTOM_SLOT_GRAIN_PTP`):

| Raw PTP value | Decoded (`grain_roughness`, `grain_size`) |
|---|---|
| 6 | `("Off", "Off")` |
| 7 | `("Off", "Off")` |
| 2 | `("Weak", "Small")` |
| 3 | `("Strong", "Small")` |
| 4 | `("Weak", "Large")` |
| 5 | `("Strong", "Large")` |

> The camera returns either `6` or `7` for Off, retaining the last-used size in
> its internal state.  Both are treated as `Off / Off`.

**Write**:

| (`grain_roughness`, `grain_size`) | Written PTP value |
|---|---|
| `("Off", any)` | `1` |
| `("Weak", "Small")` | `2` |
| `("Strong", "Small")` | `3` |
| `("Weak", "Large")` | `4` |
| `("Strong", "Large")` | `5` |

> Write `1` for Off.  The camera accepts it and normalises to `6` or `7` on
> read-back, retaining the last-remembered size.  Do not write `6` or `7`
> directly.

---

### ColorEffect (Color Chrome Effect) — `0xD196`

Type: 32-bit int.  Read and write values are identical (`CUSTOM_SLOT_CCE_PTP`).
Source: Fujifilm SDK `XAPIOpt.H` (`SDK_SHADOWING_P1`).

| Domain value | PTP value |
|---|---|
| Off | 1 |
| Weak | 2 |
| Strong | 3 |

---

### ColorFx (Color Chrome FX Blue) — `0xD197`

Type: 32-bit int.  Read and write values are identical (`CUSTOM_SLOT_CFX_PTP`).

| Domain value | PTP value |
|---|---|
| Off | 1 |
| Weak | 2 |
| Strong | 3 |

---

### ColorMode (Saturation) — `0xD19F`

Type: int16.  Encoding: `raw = domain_value × 10`.  Range: −4 to +4
(raw: −40 to +40).

| Domain value | Raw PTP value |
|---|---|
| −4 | −40 (`0xFFD8`) |
| −2 | −20 (`0xFFEC`) |
| 0 | 0 (`0x0000`) |
| +2 | 20 (`0x0014`) |
| +4 | 40 (`0x0028`) |

> Not written for monochromatic film simulations (the camera ignores writes
> when a B&W/Acros/Sepia sim is active).

---

### Sharpness — `0xD1A0`

Type: int16.  Encoding: `raw = domain_value × 10`.  Range: −4 to +4
(raw: −40 to +40).  Always written; defaults to `0` when not set.

---

### HighLightTone / ShadowTone — `0xD19D` / `0xD19E`

Type: int16.  Encoding: `raw = round(domain_value × 10)`.  Range: −2 to +4,
half-steps allowed (e.g. `+1.5` → raw `15`).

| Domain value | Raw PTP value |
|---|---|
| −2 | −20 (`0xFFEC`) |
| −1.5 | −15 (`0xFFF1`) |
| 0 | 0 |
| +1.5 | 15 (`0x000F`) |
| +4 | 40 (`0x0028`) |

> Use `round(float × 10)` when encoding, not `int(float × 10)`, to preserve
> half-steps exactly.

---

### HighIsoNoiseReduction — `0xD1A1`

Type: 32-bit int.  Non-linear encoding (`CUSTOM_SLOT_NR_DECODE`).  The value
is determined by the upper nibble of the uint16 in a non-sequential pattern.

| Domain value | Raw PTP (hex) | Raw PTP (dec) |
|---|---|---|
| +4 | `0x5000` | 20480 |
| +3 | `0x6000` | 24576 |
| +2 | `0x0000` | 0 |
| +1 | `0x1000` | 4096 |
| 0 | `0x2000` | 8192 |
| −1 | `0x3000` | 12288 |
| −2 | `0x4000` | 16384 |
| −3 | `0x7000` | 28672 |
| −4 | `0x8000` | 32768 |

Always written; defaults to `0` (raw `0x2000`) when not set.

---

### Definition (Clarity) — `0xD1A2`

Type: int16.  Encoding: `raw = domain_value × 10`.  Range: −5 to +5
(raw: −50 to +50).  Always written; defaults to `0` when not set.

---

### MonochromaticColorWarmCool — `0xD193`

Type: int16.  Encoding: `raw = round(domain_value × 10)`.  Range: −18 to +18
(raw: −180 to +180).

| Domain value | Raw PTP (hex) | Raw PTP (dec) |
|---|---|---|
| −18 | `0xFF4C` | 65356 (int16: −180) |
| 0 | `0x0000` | 0 |
| +18 | `0x00B4` | 180 |

Only written when the film simulation is monochromatic (B&W, Acros, Sepia).

---

### MonochromaticColorMagentaGreen — `0xD194`

Type: int16.  Same encoding as `MonochromaticColorWarmCool` above.
Range: −18 to +18.  Only written for monochromatic simulations.
