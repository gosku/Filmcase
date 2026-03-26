# PTP Encodings — Fujifilm Custom Slot

Audit of all PTP integer value mappings for custom-slot (C1–Cn) read operations.
All camera reads are from a Fujifilm X-S10 (2026-03-21) unless noted otherwise.

---

## READ (custom slot → domain value)

Used by `slot_recipe()` in `src/domain/camera/queries.py`.

| Property | Values | Confirmed by camera | Confirmed by source | Unconfirmed |
|---|---|---|---|---|
| FilmSimulation | Provia=1, Velvia=2, Astia=3, Pro Neg. Hi=4, Pro Neg. Std=5, Monochrome STD=6, Monochrome Yellow=7, Monochrome Red=8, Monochrome Green=9, Sepia=10, Classic Chrome=11, Acros STD=12, Acros Yellow=13, Acros Red=14, Acros Green=15, Eterna=16, Classic Negative=17, Eterna Bleach Bypass=18, Nostalgic Negative=19, Reala Ace=20 | 1–18 write+read confirmed (X-S10, 2026-03-26) | Second independent source confirms all values | 19 (Nostalgic Negative) and 20 (Reala Ace) not available on X-S10 — camera ignores writes; values correct but only verifiable on newer bodies |
| WhiteBalance | Auto=0x0002, Auto white priority=0x8020, Auto ambience priority=0x8021, Daylight=0x0004, Incandescent=0x0006, Fluorescent1=0x8001, Fluorescent2=0x8002, Fluorescent3=0x8003, Shade=0x8006, Kelvin=0x8007, Underwater=0x0008, Custom1=0x8008, Custom2=0x8009, Custom3=0x800A | All 14 values write+read confirmed (X-S10, 2026-03-26) | Fujifilm SDK XAPI.H XSDK_WB_* | |
| WB colour temperature | Raw uint16, unit scale (no ×10) | All (4 known slots matched expected Kelvin values); write 5200 → read 5200 confirmed (X-S10, 2026-03-26) | | |
| WB red fine-tune | int16, unit scale, range −9..+9 | All (4 known slots); all 19 values write+read confirmed (X-S10, 2026-03-26) | | |
| WB blue fine-tune | int16, unit scale, range −9..+9 | All (4 known slots); all 19 values write+read confirmed (X-S10, 2026-03-26) | | |
| DRangeMode | DR-Auto=0xFFFF (65535), DR100=100, DR200=200, DR400=400 | All 4 values write+read confirmed (X-S10, 2026-03-26) | Second independent source confirms all values | |
| DRangePriority | Off=0, Weak=1, Strong=2, Auto=0x8000 | All 4 values write+read confirmed (X-S10, 2026-03-26) | Second independent source confirms all values | |
| GrainEffect | Off=6 or 7, Weak+Small=2, Strong+Small=3, Weak+Large=4, Strong+Large=5 | All 5 values write+read confirmed (X-S10, 2026-03-26) | Second independent source confirms non-Off values | Values 6 and 7 both decode to Off; **write Off as 1** (camera normalises to 6 or 7, retaining last size) |

> **Grain Off write value — RESOLVED (2026-03-26, X-S10).**
> Write `1` for Off. The camera accepts it and normalises to `6` (Off+Small) or `7` (Off+Large) on read-back, retaining the last remembered size. Confirmed by writing `1` to C1 (which had Strong+Large = 5), reading back `7` (Off+Large), and visually confirming the camera body showed Roughness=Off, Size=Large.
| ColorEffect | Off=1, Weak=2, Strong=3 | All 3 values write+read confirmed (X-S10, 2026-03-26) | Fujifilm SDK XAPIOpt.H; second independent source confirms all values | |
| ColorFx | Off=1, Weak=2, Strong=3 | All 3 values write+read confirmed (X-S10, 2026-03-26) | Second independent source confirms all values | |
| MonochromaticColorWarmCool | int16 ÷ 10, range −18..+18 | Extremes and centre write+read confirmed (X-S10, 2026-03-26); encoding is deterministic ×10 formula | | |
| MonochromaticColorMagentaGreen | int16 ÷ 10, range −18..+18 | Extremes and centre write+read confirmed (X-S10, 2026-03-26); encoding is deterministic ×10 formula | | |
| ColorMode (saturation) | int16 ÷ 10, range −4..+4 | All 9 values write+read confirmed (X-S10, 2026-03-26) | Second independent source confirms encoding and range | Note: camera ignores writes when a monochromatic film sim is active |
| Sharpness | int16 ÷ 10, range −4..+4 | All 9 values write+read confirmed (X-S10, 2026-03-26) | Second independent source confirms encoding and range | |
| HighLightTone | int16 ÷ 10, range −2..+4 | All 7 values write+read confirmed (X-S10, 2026-03-26) | Second independent source confirms encoding and range | |
| ShadowTone | int16 ÷ 10, range −2..+4 | All 7 values write+read confirmed (X-S10, 2026-03-26) | Second independent source confirms encoding and range | |
| HighIsoNoiseReduction | 0x5000=+4, 0x6000=+3, 0x0000=+2, 0x1000=+1, 0x2000=0, 0x3000=−1, 0x4000=−2, 0x7000=−3, 0x8000=−4 | All 9 values write+read confirmed (X-S10, 2026-03-26) | Second independent source confirms all 9 values | |
| Definition (clarity) | int16 ÷ 10, range −5..+5 | All 11 values write+read confirmed (X-S10, 2026-03-26) | Second independent source confirms encoding and range | |
