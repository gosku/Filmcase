"""
PTP/USB constants for Fujifilm camera communication.

Normal-mode codes write to the currently active shooting mode.
Custom-slot codes write to a specific C1–Cn slot (selected via PROP_SLOT_CURSOR).
"""

# ---------------------------------------------------------------------------
# Misc PTP property codes
# ---------------------------------------------------------------------------

# Used as a liveness ping: GetDevicePropValue → 0 means camera is alive.
# Also the GrainEffect property in normal mode (dual use).
PROP_PING = 0xD023

# Battery info — returns a string like "75,..." via GetDevicePropValue.
PROP_BATTERY = 0xD36B

# Write the target slot index (1-based) here before any custom-slot reads/writes.
# Type: uint16.
PROP_SLOT_CURSOR = 0xD18C

# Read/write the display name of the currently selected custom slot.
# Type: PTP string.
PROP_SLOT_NAME = 0xD18D


# ---------------------------------------------------------------------------
# Custom-slot PTP property codes (0xD18C–0xD1A2)
# (write to a specific C1–Cn slot)
# This entire block is undocumented in libfuji.
# ---------------------------------------------------------------------------

CUSTOM_SLOT_CODES: dict[str, int] = {
    "FilmSimulation":              0xD192,
    "WhiteBalance":                0xD199,
    "WhiteBalanceColorTemperature": 0xD19C,
    "WhiteBalanceRed":             0xD19A,
    "WhiteBalanceBlue":            0xD19B,
    "DRangeMode":                  0xD190,
    "GrainEffect":                 0xD195,
    "ColorEffect":                 0xD196,
    "ColorFx":                     0xD197,
    "ColorMode":                   0xD19F,
    "Sharpness":                   0xD1A0,
    "HighLightTone":               0xD19D,
    "ShadowTone":                  0xD19E,
    "HighIsoNoiseReduction":       0xD1A1,
    "Definition":                  0xD1A2,
    "MonochromaticColorWarmCool":  0xD193,
    "MonochromaticColorMagentaGreen": 0xD194,
    "DRangePriority":              0xD191,
}


# ---------------------------------------------------------------------------
# Film simulation PTP integer values
# ---------------------------------------------------------------------------

# Maps domain FilmSimulation string → PTP integer value sent to the camera.
FILM_SIMULATION_TO_PTP: dict[str, int] = {
    "Provia":                                           1,   # STD
    "Velvia":                                           2,   # V
    "Astia":                                            3,   # S
    "Pro Neg. Hi":                                      4,   # NH
    "Pro Neg. Std":                                     5,   # NS
    "Monochrome STD":                                   6,   # B
    "Monochrome Yellow":                                7,   # BY
    "Monochrome Red":                                   8,   # BR
    "Monochrome Green":                                 9,   # BG
    "Sepia":                                           10,   # SEPIA
    "Classic Chrome":                                  11,   # CC
    "Acros STD":                                       12,   # A
    "Acros Yellow":                                    13,   # AY
    "Acros Red":                                       14,   # AR
    "Acros Green":                                     15,   # AG
    "Eterna":                                          16,   # E
    "Classic Negative":                                17,   # NC (Nostalgic Neg)
    "Eterna Bleach Bypass":                            18,   # EB
    "Nostalgic Negative":                              19,   # NN
    "Reala Ace":                                       20,   # RA
}

# Inverse map for reading back film simulation from camera.
PTP_TO_FILM_SIMULATION: dict[int, str] = {v: k for k, v in FILM_SIMULATION_TO_PTP.items()}


# ---------------------------------------------------------------------------
# Custom-slot read-back decode tables
#
# The custom-slot PTP codes (0xD190–0xD1A2) use different integer encodings
# from the normal-mode codes when READ back from the camera.  These tables
# are built from empirical slot reads on a Fujifilm X-S10 (2026-03-21).
#
# Normal-mode equivalents are COLOR_CHROME_EFFECT_TO_PTP etc. above; those
# are used for writing (recipe_to_ptp_values) and should NOT be changed.
# ---------------------------------------------------------------------------

# GrainEffect (0xD195) — custom slot read values.
# Maps raw PTP integer → (grain_roughness, grain_size) pair.
# All values empirically confirmed from X-S10 slot reads (2026-03-21).
CUSTOM_SLOT_GRAIN_PTP: dict[int, tuple[str, str]] = {
    6: ("Off",    "Off"),    # confirmed X-S10; camera remembers last size but we treat both Off variants as Off/Off
    7: ("Off",    "Off"),    # confirmed X-S10 (Cuban Negative); same as above
    2: ("Weak",   "Small"),
    3: ("Strong", "Small"),
    4: ("Weak",   "Large"),
    5: ("Strong", "Large"),
}

# ColorEffect / Color Chrome Effect (0xD196) — custom slot read values.
# 1=Off confirmed (C4), 3=Strong confirmed (C1,C2,C3); 2=Weak confirmed by SDK (XAPIOpt.H SDK_SHADOWING_P1).
CUSTOM_SLOT_CCE_PTP: dict[int, str] = {
    1: "Off",
    2: "Weak",
    3: "Strong",
}

# ColorFx / Color Chrome FX Blue (0xD197) — custom slot read values.
# All three values confirmed from camera reads (C1=Strong, C2=Weak, C3=Off).
CUSTOM_SLOT_CFX_PTP: dict[int, str] = {
    1: "Off",
    2: "Weak",
    3: "Strong",
}

# HighIsoNoiseReduction (0xD1A1) — custom slot read values.
# All 9 values empirically confirmed from X-S10 slot reads (2026-03-21).
# Upper nibble of uint16: 0,1,2,3,4 = NR +2..−2 (linear); 5,6 = NR +4,+3; 7,8 = NR −3,−4.
CUSTOM_SLOT_DR_PRIORITY_DECODE: dict[int, str] = {
    0:     "Off",    # confirmed (0x0000)
    1:     "Weak",   # confirmed (0x0001)
    2:     "Strong", # confirmed (0x0002)
    32768: "Auto",   # confirmed (0x8000)
}


CUSTOM_SLOT_NR_DECODE: dict[int, int] = {
    20480: 4,   # confirmed (0x5000)
    24576: 3,   # confirmed (0x6000)
    0:     2,   # confirmed (0x0000)
    4096:  1,   # confirmed (0x1000)
    8192:  0,   # confirmed (0x2000, C3)
    12288: -1,  # confirmed (0x3000)
    16384: -2,  # confirmed (0x4000, C2)
    28672: -3,  # confirmed (0x7000)
    32768: -4,  # confirmed (0x8000, C1, C4)
}


# ---------------------------------------------------------------------------
# White balance PTP integer values (custom slot property 0xD199)
#
# Source: Fujifilm SDK XAPI.H (XSDK_WB_* defines).
# XSDK_WB_COLORTEMP = 0x8007 = 32775 is confirmed from camera (C2 slot read);
# all other values are from the SDK and considered reliable.
# ---------------------------------------------------------------------------

WHITE_BALANCE_TO_PTP: dict[str, int] = {
    "Auto":                      0x0002,  # 2     — SDK XSDK_WB_AUTO
    "Auto (white priority)":     0x8020,  # 32800 — SDK XSDK_WB_AUTO_WHITE_PRIORITY
    "Auto (ambience priority)":  0x8021,  # 32801 — SDK XSDK_WB_AUTO_AMBIENCE_PRIORITY
    "Daylight":                  0x0004,  # 4     — SDK XSDK_WB_DAYLIGHT
    "Incandescent":              0x0006,  # 6     — SDK XSDK_WB_INCANDESCENT
    "Fluorescent 1":             0x8001,  # 32769 — SDK XSDK_WB_FLUORESCENT1
    "Fluorescent 2":             0x8002,  # 32770 — SDK XSDK_WB_FLUORESCENT2
    "Fluorescent 3":             0x8003,  # 32771 — SDK XSDK_WB_FLUORESCENT3
    "Shade":                     0x8006,  # 32774 — SDK XSDK_WB_SHADE
    "Kelvin":                    0x8007,  # 32775 — SDK XSDK_WB_COLORTEMP; confirmed from camera (C2 slot read)
    "Underwater":                0x0008,  # 8     — SDK XSDK_WB_UNDER_WATER
    "Custom 1":                  0x8008,  # 32776 — SDK XSDK_WB_CUSTOM1
    "Custom 2":                  0x8009,  # 32777 — SDK XSDK_WB_CUSTOM2
    "Custom 3":                  0x800A,  # 32778 — SDK XSDK_WB_CUSTOM3
}


# ---------------------------------------------------------------------------
# D-Range mode PTP integer values (custom slot property 0xD190)
#
# DR100/200/400 confirmed from recipe slot reads (Batches 1–4).
# DR-Auto = 0xFFFF (65535) confirmed by manual camera read (2026-03-25).
# ---------------------------------------------------------------------------

DRANGE_MODE_TO_PTP: dict[str, int] = {
    "DR-Auto": 65535,  # 0xFFFF — confirmed X-S10
    "DR100":   100,
    "DR200":   200,
    "DR400":   400,
}


# ---------------------------------------------------------------------------
# Camera model → custom slot count
# ---------------------------------------------------------------------------

CAMERA_CUSTOM_SLOT_COUNTS: dict[str, int] = {
    # 7-slot cameras
    "X-T3": 7, "X-T4": 7, "X-T5": 7,
    "X-T30": 7, "X-T30 II": 7, "X-T30 III": 7, "X-T50": 7,
    "X-H1": 7, "X-H2": 7, "X-H2S": 7,
    "X100T": 7, "X100V": 7, "X100VI": 7,
    "X-Pro1": 7, "X-Pro2": 7, "X-Pro3": 7,
    "X-E2": 7, "X-E2S": 7, "X-E3": 7, "X-E4": 7, "X-E5": 7,
    "X-T1": 7, "X-T2": 7, "X-T10": 7, "X-T20": 7,
    "GFX 50R": 7, "X70": 7,
    # 6-slot cameras
    "GFX100 II": 6, "GFX100S": 6, "GFX100SII": 6,
    "GFX50S II": 6, "GFX 50S": 6,
    # 4-slot cameras
    "X-S20": 4, "X-S10": 4,
    # 3-slot cameras
    "X100S": 3, "X100": 3, "X-E1": 3,
    # 0-slot cameras (no custom slot support)
    "X-T100": 0, "X-T200": 0, "X-M1": 0,
    "X10": 0, "X20": 0, "X30": 0,
    "XF1": 0, "XF10": 0, "XQ1": 0, "XQ2": 0,
}
