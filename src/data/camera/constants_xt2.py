"""
Byte-level constants for the Fujifilm X-T2 settings-backup blob.

The X-T2 (and other pre-X-T3 bodies) have no per-slot PTP property interface:
recipes live inside a single fixed 5660-byte settings backup blob at fixed byte
offsets. These maps describe that layout for the backup codec in
src/domain/camera/xt2_backup/. They were derived by reverse-engineering the blob and
proven against real hardware captures.

Scope: the X-T2 at the firmware captured. NOT a general Fuji backup format; other
bodies differ in both layout and capability set.

Value maps are keyed to the app's canonical domain names (the keys of
src.data.camera.constants.FILM_SIMULATION_TO_PTP etc.), so the codec converts a
blob byte straight to a FujifilmRecipeData field and back.
"""
from __future__ import annotations

from collections.abc import Mapping

# ---------------------------------------------------------------------------
# Blob geometry and self-describing header
# ---------------------------------------------------------------------------

MAGIC: bytes = b"FUJIFILMX-BACKUP0100X-T2"
BLOB_SIZE: int = 5660

# Self-describing size fields (168 + 5492 = 5660) and a constant marker; hard
# anchors that a shifted/wrong blob fails.
HEADER_SIZE_OFFSET: int = 0x98
HEADER_SIZE_VALUE: int = 168
BODY_SIZE_OFFSET: int = 0xA0
BODY_SIZE_VALUE: int = 5492
MARKER_OFFSET: int = 0xAC
MARKER_VALUE: int = 1

# Seven custom-slot records, 256 bytes each, starting at 0xF00.
SLOT0_OFFSET: int = 0xF00
SLOT_SIZE: int = 0x100
SLOT_COUNT: int = 7
NAME_OFFSET: int = 0x7E       # within a slot record
NAME_FIELD_LEN: int = 0x20

# ---------------------------------------------------------------------------
# Per-slot field offsets (within a slot record)
# ---------------------------------------------------------------------------

OFF_WB_SELECTOR: int = 0x24
OFF_KELVIN_INDEX: int = 0x25
OFF_NOISE_REDUCTION: int = 0x3E
OFF_FILM_SIMULATION: int = 0x45
OFF_DYNAMIC_RANGE: int = 0x48
OFF_COLOR: int = 0x4C
OFF_SHARPNESS: int = 0x4E
OFF_HIGHLIGHT: int = 0x4F
OFF_SHADOW: int = 0x50
OFF_GRAIN: int = 0x51

# The camera manages these itself and will not reproduce a pushed value, so they
# are excluded from the post-restore read-back verify.
SLOT_WRITE_COUNTER_OFFSET: int = 0x16     # within a slot record
DRIFT_RANGE: tuple[int, int] = (0xED8, 0xEDD)   # inclusive, live/lens state

# ---------------------------------------------------------------------------
# Value maps: blob byte -> canonical domain value
# ---------------------------------------------------------------------------

# Film simulation (+0x45). 15 values, the X-T2 subset. Bytes 0x02/0x04/0x06 are
# unused (sims the X-T2 lacks). Keyed to FILM_SIMULATION_TO_PTP domain names.
FILM_SIMULATION_BY_BYTE: Mapping[int, str] = {
    0x00: "Provia",
    0x01: "Astia",
    0x03: "Velvia",
    0x05: "Sepia",
    0x07: "Monochrome STD",
    0x08: "Monochrome Red",
    0x09: "Monochrome Yellow",
    0x0A: "Monochrome Green",
    0x0B: "Pro Neg. Std",
    0x0C: "Pro Neg. Hi",
    0x0D: "Classic Chrome",
    0x0E: "Acros STD",
    0x0F: "Acros Red",
    0x10: "Acros Yellow",
    0x11: "Acros Green",
}

# Film-sim bytes that are black-and-white: Color is retained-but-ignored on these
# (no storage-level validation), so the codec does not range-check Color for them.
BW_FILM_SIMULATION_BYTES: frozenset[int] = frozenset(
    {0x05, 0x07, 0x08, 0x09, 0x0A, 0x0E, 0x0F, 0x10, 0x11}
)

# Grain Effect (+0x51). Single field (no size on the X-T2); counts down. Keyed to
# FujifilmRecipeData.grain_roughness values.
GRAIN_ROUGHNESS_BY_BYTE: Mapping[int, str] = {
    0x02: "Off",
    0x01: "Weak",
    0x00: "Strong",
}

# Dynamic Range (+0x48). Keyed to DRANGE_MODE_TO_PTP domain names.
DYNAMIC_RANGE_BY_BYTE: Mapping[int, str] = {
    0x00: "DR-Auto",
    0x01: "DR100",
    0x02: "DR200",
    0x03: "DR400",
}

# Color (+0x4C). Scrambled 9-value lookup (byte -> domain int -4..+4).
COLOR_VALUE_BY_BYTE: Mapping[int, int] = {
    0x00: 0,
    0x03: 4,
    0x04: 3,
    0x05: 2,
    0x06: 1,
    0x07: -2,
    0x08: -1,
    0x09: -3,
    0x0A: -4,
}

# White balance selector (+0x24). Keyed to WHITE_BALANCE_TO_PTP domain names;
# the X-T2 "Color Temp" entry is the domain "Kelvin" mode.
WHITE_BALANCE_BY_SELECTOR: Mapping[int, str] = {
    0x00: "Auto",
    0x01: "Daylight",
    0x02: "Shade",
    0x03: "Fluorescent 1",
    0x04: "Fluorescent 2",
    0x05: "Fluorescent 3",
    0x06: "Incandescent",
    0x07: "Underwater",
    0x08: "Kelvin",
    0x09: "Custom 1",
    0x0A: "Custom 2",
    0x0B: "Custom 3",
}

# Custom WB entries are a live measurement, not a portable parameter, so a recipe
# cannot be pushed with one of these as its white balance.
MEASURED_CUSTOM_WB: frozenset[str] = frozenset({"Custom 1", "Custom 2", "Custom 3"})

# ---------------------------------------------------------------------------
# Global (shared across slots) white-balance R/B shift table
# ---------------------------------------------------------------------------

# Base of the 12-entry x 2-byte (R, B) table; byte = 9 - shift. The entry index
# is the WB's MENU-ORDER position, which is NOT the +0x24 selector order, so it
# has its own map (domain WB name -> table index).
WB_SHIFT_TABLE_BASE: int = 0x195
WB_SHIFT_ENTRIES: int = 12
WB_SHIFT_TABLE_INDEX: Mapping[str, int] = {
    "Auto": 0,
    "Custom 1": 1,
    "Custom 2": 2,
    "Custom 3": 3,
    "Kelvin": 4,
    "Daylight": 5,
    "Shade": 6,
    "Fluorescent 1": 7,
    "Fluorescent 2": 8,
    "Fluorescent 3": 9,
    "Incandescent": 10,
    "Underwater": 11,
}

# Color-temperature steps (+0x25 is a descending index into this list).
KELVIN_STEPS: tuple[int, ...] = (
    10000, 9100, 8300, 7700, 7100, 6700, 6300, 5900, 5600, 5300, 5000, 4800,
    4500, 4300, 4200, 4000, 3800, 3700, 3600, 3400, 3300, 3200, 3100, 3000,
    2950, 2850, 2800, 2700, 2650, 2550, 2500,
)

# ---------------------------------------------------------------------------
# Encoding limits for the strict validator
# ---------------------------------------------------------------------------

# byte = 4 - value: Highlight/Shadow (-2..+4 -> 0..6), Sharpness (-4..+4 -> 0..8);
# Noise Reduction byte = value + 4 (-4..+4 -> 0..8); WB shift byte = 9 - shift
# (-9..+9 -> 0..0x12). Name window is printable ASCII.
TONE_BYTE_MAX: int = 6       # Highlight / Shadow
SHARPNESS_BYTE_MAX: int = 8
NOISE_REDUCTION_BYTE_MAX: int = 8
WB_SHIFT_BYTE_MAX: int = 0x12
ASCII_MIN: int = 0x20
ASCII_MAX: int = 0x7E

# Non-zero bytes constant across all 7 slots and camera states, excluding mapped
# settings and the name window: structural scaffolding used as a soft fingerprint
# (a mismatch is a warning; a layout shift breaks many at once).
STRUCTURAL_ANCHORS: Mapping[int, int] = {
    0x23: 0x03, 0x26: 0x09, 0x27: 0x09, 0x28: 0x09, 0x29: 0x09, 0x2A: 0x09,
    0x2B: 0x09, 0x2C: 0x09, 0x2D: 0x09, 0x2E: 0x09, 0x2F: 0x09, 0x30: 0x09,
    0x31: 0x09, 0x32: 0x09, 0x33: 0x09, 0x34: 0x09, 0x35: 0x09, 0x36: 0x09,
    0x37: 0x09, 0x38: 0x09, 0x39: 0x09, 0x3A: 0x09, 0x3B: 0x09, 0x3C: 0x09,
    0x3D: 0x09, 0x40: 0x01, 0x42: 0x01, 0x43: 0x02, 0x44: 0x01, 0x52: 0x09,
    0x53: 0x09, 0x54: 0x02, 0x55: 0x01, 0x57: 0x02, 0x59: 0x01, 0x5E: 0x01,
    0x5F: 0x12, 0x60: 0x12, 0x61: 0x12, 0x62: 0x04, 0x63: 0x04, 0x64: 0x04,
    0x65: 0x0B, 0x66: 0x0B, 0x67: 0x0B, 0x6A: 0x2A, 0x6B: 0x2A, 0x6C: 0x0F,
    0x6E: 0x03, 0x70: 0x01, 0x73: 0x07, 0x74: 0x05, 0x75: 0x07, 0x76: 0x03,
    0x77: 0x07, 0x7C: 0x02, 0x7D: 0x02,
}
