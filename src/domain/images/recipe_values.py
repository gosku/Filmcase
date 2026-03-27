"""
Typed values for FujifilmRecipe model fields.

Enum *values* are the exact strings stored in the database (as returned by
exiftool).  Distinct values were sourced directly from the data_fujifilmrecipe
table.

Recipe card ↔ DB translation:
  - .recipe_card_label  → recipe card display string
  - .from_recipe_card() → parse recipe card string into the enum
"""

from __future__ import annotations

import re
from enum import Enum

import attrs


# ---------------------------------------------------------------------------
# film_simulation  (EXIF tag: Film Mode)
# ---------------------------------------------------------------------------

class FilmSimulation(str, Enum):
    CLASSIC_CHROME = "Classic Chrome"
    CLASSIC_NEGATIVE = "Classic Negative"
    ETERNA = "Eterna"
    PROVIA = "F0/Standard (Provia)"
    PRO_NEG_STD = "Pro Neg. Std"
    VELVIA = "F2/Fujichrome (Velvia)"
    ASTIA = "F1b/Studio Portrait Smooth Skin Tone (Astia)"
    BLEACH_BYPASS = "Bleach Bypass"
    PRO_NEG_HI = "Pro Neg. Hi"
    REALA_ACE = "Reala Ace"
    # Values below come from the EXIF `color` field (film_simulation is empty for these)
    ACROS = "Acros"
    ACROS_YELLOW = "Acros Yellow Filter"
    ACROS_RED = "Acros Red Filter"
    ACROS_GREEN = "Acros Green Filter"
    MONOCHROME = "None (B&W)"
    SEPIA = "B&W Sepia"
    MONOCHROME_YELLOW = "B&W Yellow Filter"
    MONOCHROME_RED = "B&W Red Filter"
    MONOCHROME_GREEN = "B&W Green Filter"

    @property
    def display_name(self) -> str:
        return _FILM_SIMULATION_DISPLAY_NAMES[self]

    @property
    def recipe_card_label(self) -> str:
        return _FILM_SIMULATION_LABELS[self]

    @classmethod
    def from_recipe_card(cls, *, label: str) -> FilmSimulation:
        return _FILM_SIMULATION_FROM_LABEL[label]


_FILM_SIMULATION_DISPLAY_NAMES: dict[FilmSimulation, str] = {
    FilmSimulation.CLASSIC_CHROME: "Classic Chrome",
    FilmSimulation.CLASSIC_NEGATIVE: "Classic Negative",
    FilmSimulation.ETERNA: "Eterna",
    FilmSimulation.PROVIA: "Provia",
    FilmSimulation.PRO_NEG_STD: "Pro Neg. Std",
    FilmSimulation.VELVIA: "Velvia",
    FilmSimulation.ASTIA: "Astia",
    FilmSimulation.BLEACH_BYPASS: "Eterna Bleach Bypass",
    FilmSimulation.PRO_NEG_HI: "Pro Neg. Hi",
    FilmSimulation.REALA_ACE: "Reala Ace",
    FilmSimulation.ACROS: "Acros STD",
    FilmSimulation.ACROS_YELLOW: "Acros Yellow",
    FilmSimulation.ACROS_RED: "Acros Red",
    FilmSimulation.ACROS_GREEN: "Acros Green",
    FilmSimulation.MONOCHROME: "Monochrome STD",
    FilmSimulation.MONOCHROME_YELLOW: "Monochrome Yellow",
    FilmSimulation.MONOCHROME_RED: "Monochrome Red",
    FilmSimulation.MONOCHROME_GREEN: "Monochrome Green",
    FilmSimulation.SEPIA: "Sepia",
}

# Simulations sourced from EXIF `film_simulation` field
_FILM_SIMULATION_FROM_EXIF: dict[str, FilmSimulation] = {
    fs.value: fs for fs in [
        FilmSimulation.CLASSIC_CHROME,
        FilmSimulation.CLASSIC_NEGATIVE,
        FilmSimulation.ETERNA,
        FilmSimulation.PROVIA,
        FilmSimulation.PRO_NEG_STD,
        FilmSimulation.VELVIA,
        FilmSimulation.ASTIA,
        FilmSimulation.BLEACH_BYPASS,
        FilmSimulation.PRO_NEG_HI,
        FilmSimulation.REALA_ACE,
    ]
}

# Simulations sourced from EXIF `color` field (when film_simulation is empty)
_FILM_SIMULATION_FROM_COLOR: dict[str, FilmSimulation] = {
    fs.value: fs for fs in [
        FilmSimulation.ACROS,
        FilmSimulation.ACROS_YELLOW,
        FilmSimulation.ACROS_RED,
        FilmSimulation.ACROS_GREEN,
        FilmSimulation.MONOCHROME,
        FilmSimulation.MONOCHROME_YELLOW,
        FilmSimulation.MONOCHROME_RED,
        FilmSimulation.MONOCHROME_GREEN,
        FilmSimulation.SEPIA,
    ]
}


def film_simulation_from_exif(*, film_simulation: str, color: str) -> FilmSimulation:
    """Resolve the FilmSimulation from the two relevant EXIF fields."""
    if film_simulation:
        return _FILM_SIMULATION_FROM_EXIF[film_simulation]
    return _FILM_SIMULATION_FROM_COLOR[color]


_FILM_SIMULATION_LABELS: dict[FilmSimulation, str] = {
    FilmSimulation.CLASSIC_CHROME: "CLASSIC CHROME",
    FilmSimulation.CLASSIC_NEGATIVE: "CLASSIC Neg.",
    FilmSimulation.ETERNA: "ETERNA/CINEMA",
    FilmSimulation.PROVIA: "PROVIA/STANDARD",
    FilmSimulation.PRO_NEG_STD: "PRO Neg. Std",
    FilmSimulation.VELVIA: "VELVIA/VIVID",
    FilmSimulation.ASTIA: "ASTIA/SOFT",
    FilmSimulation.BLEACH_BYPASS: "ETERNA BLEACH BYPASS",
    FilmSimulation.PRO_NEG_HI: "PRO Neg. Hi",
}
_FILM_SIMULATION_FROM_LABEL: dict[str, FilmSimulation] = {
    v: k for k, v in _FILM_SIMULATION_LABELS.items()
}


# ---------------------------------------------------------------------------
# dynamic_range  (EXIF tags: Dynamic Range Setting + Development Dynamic Range)
# d_range_priority (EXIF tags: D Range Priority + D Range Priority Auto)
#
# These two settings are mutually exclusive on the camera.
# When D-Range Priority is active (not Off), dynamic_range is left empty.
# HDR drive mode images (picture_mode == "HDR") are not recipe images.
# ---------------------------------------------------------------------------

class DRangePriority(str, Enum):
    OFF = "Off"
    AUTO = "Auto"
    WEAK = "Weak"
    STRONG = "Strong"


def dynamic_range_from_exif(*, dynamic_range_setting: str, development_dynamic_range: str) -> str:
    """Return recipe dynamic_range string from EXIF fields.

    Returns empty string when dynamic_range_setting is absent (i.e. D-Range Priority is active).
    """
    if dynamic_range_setting == "Auto":
        return "DR-Auto"
    return {
        "100": "DR100",
        "200": "DR200",
        "400": "DR400",
    }.get(development_dynamic_range, "")


def d_range_priority_from_exif(*, d_range_priority: str, d_range_priority_auto: str) -> DRangePriority:
    """Resolve D-Range Priority setting from the two relevant EXIF fields."""
    if d_range_priority == "Auto":
        return DRangePriority.AUTO
    if d_range_priority == "Fixed":
        if d_range_priority_auto == "Weak":
            return DRangePriority.WEAK
        if d_range_priority_auto == "Strong":
            return DRangePriority.STRONG
    return DRangePriority.OFF


# ---------------------------------------------------------------------------
# white_balance  (EXIF tag: White Balance)
# ---------------------------------------------------------------------------

class WhiteBalance(str, Enum):
    AUTO = "Auto"
    DAYLIGHT = "Daylight"
    KELVIN = "Kelvin"
    INCANDESCENT = "Incandescent"
    DAYLIGHT_FLUORESCENT = "Daylight Fluorescent"
    AUTO_WHITE_PRIORITY = "Auto (white priority)"

    @property
    def recipe_card_label(self) -> str:
        return _WHITE_BALANCE_LABELS[self]

    @classmethod
    def from_recipe_card(cls, *, label: str) -> WhiteBalance:
        """
        Parse a recipe card WB label such as 'AUTO', 'DAYLIGHT', '5200K'.
        Temperature labels (e.g. '5200K') return WhiteBalance.KELVIN;
        the numeric value goes into the separate color_temperature field.
        """
        if re.match(r"^\d+K$", label):
            return cls.KELVIN
        return _WHITE_BALANCE_FROM_LABEL[label]


_WHITE_BALANCE_LABELS: dict[WhiteBalance, str] = {
    WhiteBalance.AUTO: "AUTO",
    WhiteBalance.DAYLIGHT: "DAYLIGHT",
    WhiteBalance.KELVIN: "{temp}K",  # substitute actual temp, e.g. "5200K"
    WhiteBalance.INCANDESCENT: "INCANDESCENT",
    WhiteBalance.DAYLIGHT_FLUORESCENT: "DAYLIGHT FLUORESCENT",
    WhiteBalance.AUTO_WHITE_PRIORITY: "AUTO WHITE PRIORITY",
}
_WHITE_BALANCE_FROM_LABEL: dict[str, WhiteBalance] = {
    v: k for k, v in _WHITE_BALANCE_LABELS.items() if "{temp}" not in v
}


# ---------------------------------------------------------------------------
# white_balance_fine_tune  (EXIF tag: White Balance Fine Tune, normalised ÷20)
# ---------------------------------------------------------------------------

@attrs.define
class WhiteBalanceFineTune:
    """
    WB fine-tune stored as e.g. 'Red +2, Blue -4'.
    Values match recipe card display values directly (already ÷20 from raw EXIF).
    Observed range in DB: -9 to +9 for both channels.
    """
    red: int
    blue: int

    def __str__(self) -> str:
        return f"Red {self.red:+d}, Blue {self.blue:+d}"

    @classmethod
    def from_string(cls, *, s: str) -> WhiteBalanceFineTune:
        """Parse a normalised WB fine-tune string, e.g. 'Red +2, Blue -4'."""
        m_red = re.search(r"Red\s+([+-]?\d+)", s)
        m_blue = re.search(r"Blue\s+([+-]?\d+)", s)
        return cls(
            red=int(m_red.group(1)) if m_red else 0,
            blue=int(m_blue.group(1)) if m_blue else 0,
        )


def white_balance_from_exif(*, white_balance: str, color_temperature: str) -> str:
    """Return the WB display string for FujifilmRecipeData.

    Kelvin mode stores the temperature in a separate field; all other modes
    use their EXIF value directly (e.g. 'Auto', 'Daylight').
    """
    wb = WhiteBalance(white_balance)
    if wb == WhiteBalance.KELVIN:
        return f"{color_temperature}K"
    return wb.value


def white_balance_fine_tune_from_exif(*, white_balance_fine_tune: str) -> tuple[int, int]:
    """Return (red, blue) fine-tune integers from the normalised EXIF string."""
    if not white_balance_fine_tune:
        return 0, 0
    ft = WhiteBalanceFineTune.from_string(s=white_balance_fine_tune)
    return ft.red, ft.blue


# ---------------------------------------------------------------------------
# dynamic_range        (EXIF tag: Dynamic Range)         — always "Standard" in DB
# dynamic_range_setting (EXIF tag: Dynamic Range Setting) — "Auto" | "Manual"
# development_dynamic_range (EXIF tag: Development Dynamic Range) — the meaningful DR value
#
# Recipe cards show a single 'DR Range' field; use DevelopmentDynamicRange.
# ---------------------------------------------------------------------------

class DevelopmentDynamicRange(str, Enum):
    """
    Value = exiftool 'Development Dynamic Range' string.
    This is the field that actually encodes the DR setting from recipe cards.
    DR Auto results in an empty string (camera decides at shoot time).
    """
    AUTO = ""      # dynamic_range_setting = "Auto"
    DR100 = "100"
    DR200 = "200"
    DR400 = "400"
    DR800 = "800"  # requires ISO >= 1600

    @property
    def recipe_card_label(self) -> str:
        return _DDR_LABELS[self]

    @property
    def dynamic_range_setting(self) -> str:
        """Companion 'Dynamic Range Setting' EXIF field value."""
        return "Auto" if self == DevelopmentDynamicRange.AUTO else "Manual"

    @classmethod
    def from_recipe_card(cls, *, label: str) -> DevelopmentDynamicRange:
        return _DDR_FROM_LABEL[label]


_DDR_LABELS: dict[DevelopmentDynamicRange, str] = {
    DevelopmentDynamicRange.AUTO: "Auto",
    DevelopmentDynamicRange.DR100: "DR100",
    DevelopmentDynamicRange.DR200: "DR200",
    DevelopmentDynamicRange.DR400: "DR400",
    DevelopmentDynamicRange.DR800: "DR800",
}
_DDR_FROM_LABEL: dict[str, DevelopmentDynamicRange] = {
    v: k for k, v in _DDR_LABELS.items()
}


# ---------------------------------------------------------------------------
# color_chrome_effect  (EXIF tag: Color Chrome Effect — recipe cards: CCE)
# ---------------------------------------------------------------------------

class ColorChromeEffect(str, Enum):
    OFF = "Off"
    WEAK = "Weak"
    STRONG = "Strong"

    @property
    def recipe_card_label(self) -> str:
        return self.value

    @classmethod
    def from_recipe_card(cls, *, label: str) -> ColorChromeEffect:
        return cls(label)


def color_chrome_effect_from_exif(*, value: str) -> ColorChromeEffect:
    """Return ColorChromeEffect from the EXIF 'Color Chrome Effect' field."""
    return ColorChromeEffect(value) if value else ColorChromeEffect.OFF


# ---------------------------------------------------------------------------
# color_chrome_fx_blue  (EXIF tag: Color Chrome FX Blue — recipe cards: CFXB)
# ---------------------------------------------------------------------------

class ColorChromeFxBlue(str, Enum):
    OFF = "Off"
    WEAK = "Weak"
    STRONG = "Strong"

    @property
    def recipe_card_label(self) -> str:
        return self.value

    @classmethod
    def from_recipe_card(cls, *, label: str) -> ColorChromeFxBlue:
        return cls(label)


def color_chrome_fx_blue_from_exif(*, value: str) -> ColorChromeFxBlue:
    """Return ColorChromeFxBlue from the EXIF 'Color Chrome FX Blue' field."""
    return ColorChromeFxBlue(value) if value else ColorChromeFxBlue.OFF


# ---------------------------------------------------------------------------
# grain_effect_roughness  (EXIF tag: Grain Effect Roughness)
# grain_effect_size       (EXIF tag: Grain Effect Size)
#
# Recipe cards show a combined label e.g. "Strong Large" or "Off".
# ---------------------------------------------------------------------------

class GrainEffectRoughness(str, Enum):
    OFF = "Off"
    WEAK = "Weak"
    STRONG = "Strong"

    @property
    def recipe_card_label(self) -> str:
        return self.value

    @classmethod
    def from_recipe_card(cls, *, label: str) -> GrainEffectRoughness:
        return cls(label)


class GrainEffectSize(str, Enum):
    OFF = "Off"
    SMALL = "Small"
    LARGE = "Large"

    @property
    def recipe_card_label(self) -> str:
        return self.value

    @classmethod
    def from_recipe_card(cls, *, label: str) -> GrainEffectSize:
        return cls(label)


@attrs.define
class GrainEffect:
    """Combined grain effect parsed from a recipe card label e.g. 'Strong Large' or 'Off'."""
    roughness: GrainEffectRoughness
    size: GrainEffectSize

    @classmethod
    def from_recipe_card(cls, *, label: str) -> GrainEffect:
        label = label.strip()
        if label.lower() == "off":
            return cls(roughness=GrainEffectRoughness.OFF, size=GrainEffectSize.OFF)
        parts = label.split()
        roughness = GrainEffectRoughness.from_recipe_card(label=parts[0])
        size = GrainEffectSize.from_recipe_card(label=parts[1]) if len(parts) > 1 else GrainEffectSize.SMALL
        return cls(roughness=roughness, size=size)

    @property
    def recipe_card_label(self) -> str:
        if self.roughness == GrainEffectRoughness.OFF:
            return "Off"
        return f"{self.roughness.value} {self.size.value}"


# ---------------------------------------------------------------------------
# Tonal / numeric fields
#
# These are stored as strings with a text label suffix by exiftool, e.g.
# "0 (normal)", "+1 (medium hard)", "-2 (soft)".  Half-step values are stored
# as bare floats ("0.5", "-0.5") without a label — this is an exiftool
# inconsistency across camera firmware versions.
#
# highlight_tone  (EXIF: Highlight Tone)
# shadow_tone     (EXIF: Shadow Tone)
# ---------------------------------------------------------------------------

class HighlightTone(str, Enum):
    MINUS_2   = "-2 (soft)"
    MINUS_1_5 = "-1.5"
    MINUS_1   = "-1 (medium soft)"
    MINUS_0_5 = "-0.5"
    ZERO      = "0 (normal)"
    PLUS_0_5  = "0.5"
    PLUS_1    = "+1 (medium hard)"
    PLUS_1_5  = "1.5"
    PLUS_2    = "+2 (hard)"
    PLUS_2_5  = "2.5"
    PLUS_3    = "+3 (very hard)"
    PLUS_3_5  = "3.5"
    PLUS_4    = "+4 (hardest)"

    @property
    def numeric(self) -> float:
        return _TONE_NUMERIC[self]

    @classmethod
    def from_recipe_card(cls, *, value: str) -> HighlightTone:
        """Parse a recipe card numeric string e.g. '-1.0', '+2.0', '0'."""
        return _HIGHLIGHT_TONE_FROM_NUMERIC[float(value)]


_TONE_NUMERIC: dict[HighlightTone | ShadowTone, float] = {}  # populated below


class ShadowTone(str, Enum):
    MINUS_2   = "-2 (soft)"
    MINUS_1_5 = "-1.5"
    MINUS_1   = "-1 (medium soft)"
    MINUS_0_5 = "-0.5"
    ZERO      = "0 (normal)"
    PLUS_0_5  = "0.5"
    PLUS_1    = "+1 (medium hard)"
    PLUS_1_5  = "1.5"
    PLUS_2    = "+2 (hard)"
    PLUS_2_5  = "2.5"
    PLUS_3    = "+3 (very hard)"
    PLUS_3_5  = "3.5"
    PLUS_4    = "+4 (hardest)"

    @property
    def numeric(self) -> float:
        return _TONE_NUMERIC[self]

    @classmethod
    def from_recipe_card(cls, *, value: str) -> ShadowTone:
        """Parse a recipe card numeric string e.g. '+1.0', '-2.0', '0'."""
        return _SHADOW_TONE_FROM_NUMERIC[float(value)]


_HIGHLIGHT_TONE_MAP: dict[float, HighlightTone] = {
    -2.0: HighlightTone.MINUS_2,
    -1.5: HighlightTone.MINUS_1_5,
    -1.0: HighlightTone.MINUS_1,
    -0.5: HighlightTone.MINUS_0_5,
     0.0: HighlightTone.ZERO,
     0.5: HighlightTone.PLUS_0_5,
     1.0: HighlightTone.PLUS_1,
     1.5: HighlightTone.PLUS_1_5,
     2.0: HighlightTone.PLUS_2,
     2.5: HighlightTone.PLUS_2_5,
     3.0: HighlightTone.PLUS_3,
     3.5: HighlightTone.PLUS_3_5,
     4.0: HighlightTone.PLUS_4,
}
_SHADOW_TONE_MAP: dict[float, ShadowTone] = {
    -2.0: ShadowTone.MINUS_2,
    -1.5: ShadowTone.MINUS_1_5,
    -1.0: ShadowTone.MINUS_1,
    -0.5: ShadowTone.MINUS_0_5,
     0.0: ShadowTone.ZERO,
     0.5: ShadowTone.PLUS_0_5,
     1.0: ShadowTone.PLUS_1,
     1.5: ShadowTone.PLUS_1_5,
     2.0: ShadowTone.PLUS_2,
     2.5: ShadowTone.PLUS_2_5,
     3.0: ShadowTone.PLUS_3,
     3.5: ShadowTone.PLUS_3_5,
     4.0: ShadowTone.PLUS_4,
}
_HIGHLIGHT_TONE_FROM_NUMERIC = _HIGHLIGHT_TONE_MAP
_SHADOW_TONE_FROM_NUMERIC = _SHADOW_TONE_MAP
_TONE_NUMERIC.update({v: k for k, v in _HIGHLIGHT_TONE_MAP.items()})
_TONE_NUMERIC.update({v: k for k, v in _SHADOW_TONE_MAP.items()})


def _tone_str(*, n: float) -> str:
    """Format a tone numeric value as a signed string, e.g. '+1.5', '-0.5', '0'."""
    if n == 0.0:
        return "0"
    formatted = f"{n:+.1f}".rstrip("0").rstrip(".")
    return formatted if "." in f"{n}" or n % 1 != 0 else f"{int(n):+d}"


def highlight_from_exif(*, highlight_tone: str) -> str:
    """Return the highlight tone as a signed string, e.g. '+1.5', '-2', '0'."""
    return _tone_str(n=HighlightTone(highlight_tone).numeric)


def shadow_from_exif(*, shadow_tone: str) -> str:
    """Return the shadow tone as a signed string, e.g. '+3', '-0.5', '0'."""
    return _tone_str(n=ShadowTone(shadow_tone).numeric)


# ---------------------------------------------------------------------------
# color        (EXIF: Saturation — recipe cards: Color)
# sharpness    (EXIF: Sharpness)
# noise_reduction (EXIF: Noise Reduction — recipe cards: ISO Denoise)
# ---------------------------------------------------------------------------

class Color(str, Enum):
    MINUS_4 = "-4 (lowest)"
    MINUS_3 = "-3 (very low)"
    MINUS_2 = "-2 (low)"
    MINUS_1 = "-1 (medium low)"
    ZERO = "0 (normal)"
    PLUS_1 = "+1 (medium high)"
    PLUS_2 = "+2 (high)"
    PLUS_3 = "+3 (very high)"
    PLUS_4 = "+4 (highest)"

    @property
    def numeric(self) -> int:
        return _COLOR_NUMERIC[self]

    @classmethod
    def from_recipe_card(cls, *, value: str) -> Color:
        return _COLOR_FROM_NUMERIC[int(value)]


_COLOR_MAP: dict[int, Color] = {
    -4: Color.MINUS_4,
    -3: Color.MINUS_3,
    -2: Color.MINUS_2,
    -1: Color.MINUS_1,
     0: Color.ZERO,
     1: Color.PLUS_1,
     2: Color.PLUS_2,
     3: Color.PLUS_3,
     4: Color.PLUS_4,
}
_COLOR_FROM_NUMERIC = _COLOR_MAP
_COLOR_NUMERIC: dict[Color, int] = {v: k for k, v in _COLOR_MAP.items()}
_NUMERIC_COLOR_VALUES: frozenset[str] = frozenset(c.value for c in Color)


_NON_NUMERIC_COLOR_VALUES: frozenset[str] = frozenset({
    # B&W / Acros / Sepia — color field encodes the film simulation name
    "None (B&W)",
    "B&W Red Filter",
    "B&W Yellow Filter",
    "B&W Green Filter",
    "B&W Sepia",
    "Acros",
    "Acros Red Filter",
    "Acros Yellow Filter",
    "Acros Green Filter",
    # Film Simulation — saturation controlled by the film profile, not user-set
    "Film Simulation",
})


def color_from_exif(*, color: str) -> str | None:
    """Return the numeric color/saturation value as a signed string, or None.

    Positive values are prefixed with '+' (e.g. '+2'), negative with '-'
    (e.g. '-3'), zero is '0'.

    Returns None for non-numeric EXIF values: B&W/Acros/Sepia modes store the
    film simulation name in this field, and 'Film Simulation' indicates the
    saturation is controlled by the film profile rather than set by the user.
    """
    if color in _NON_NUMERIC_COLOR_VALUES or color not in _NUMERIC_COLOR_VALUES:
        return None
    n = Color(color).numeric
    return f"+{n}" if n > 0 else str(n)


class Sharpness(str, Enum):
    MINUS_4 = "-4 (softest)"
    MINUS_3 = "-3 (very soft)"
    MINUS_2 = "-2 (soft)"
    MINUS_1 = "-1 (medium soft)"
    ZERO    = "0 (normal)"
    PLUS_1  = "+1 (medium hard)"
    PLUS_2  = "+2 (hard)"
    PLUS_3  = "+3 (very hard)"
    PLUS_4  = "+4 (hardest)"

    @property
    def numeric(self) -> int:
        return _SHARPNESS_NUMERIC[self]

    @classmethod
    def from_recipe_card(cls, *, value: str) -> Sharpness:
        return _SHARPNESS_FROM_NUMERIC[int(value)]


_SHARPNESS_MAP: dict[int, Sharpness] = {
    -4: Sharpness.MINUS_4,
    -3: Sharpness.MINUS_3,
    -2: Sharpness.MINUS_2,
    -1: Sharpness.MINUS_1,
     0: Sharpness.ZERO,
     1: Sharpness.PLUS_1,
     2: Sharpness.PLUS_2,
     3: Sharpness.PLUS_3,
     4: Sharpness.PLUS_4,
}
_SHARPNESS_FROM_NUMERIC = _SHARPNESS_MAP
_SHARPNESS_NUMERIC: dict[Sharpness, int] = {v: k for k, v in _SHARPNESS_MAP.items()}
_NUMERIC_SHARPNESS_VALUES: frozenset[str] = frozenset(s.value for s in Sharpness)


def sharpness_from_exif(*, sharpness: str) -> str:
    """Return the numeric sharpness value as a signed string, or 'N/A'.

    'Film Simulation' appears on some bodies where sharpness is controlled by
    the film simulation; there is no user-set numeric value in that case.
    """
    if sharpness not in _NUMERIC_SHARPNESS_VALUES:
        return "N/A"
    n = Sharpness(sharpness).numeric
    return f"+{n}" if n > 0 else str(n)


class NoiseReduction(str, Enum):
    """Recipe cards label this field 'ISO Denoise'."""
    MINUS_4 = "-4 (weakest)"
    MINUS_3 = "-3 (very weak)"
    MINUS_2 = "-2 (weak)"
    MINUS_1 = "-1 (medium weak)"
    ZERO    = "0 (normal)"
    PLUS_1  = "+1 (medium strong)"
    PLUS_2  = "+2 (strong)"
    PLUS_3  = "+3 (very strong)"
    PLUS_4  = "+4 (strongest)"

    @property
    def numeric(self) -> int:
        return _NOISE_REDUCTION_NUMERIC[self]

    @classmethod
    def from_recipe_card(cls, *, value: str) -> NoiseReduction:
        return _NOISE_REDUCTION_FROM_NUMERIC[int(value)]


_NOISE_REDUCTION_MAP: dict[int, NoiseReduction] = {
    -4: NoiseReduction.MINUS_4,
    -3: NoiseReduction.MINUS_3,
    -2: NoiseReduction.MINUS_2,
    -1: NoiseReduction.MINUS_1,
     0: NoiseReduction.ZERO,
     1: NoiseReduction.PLUS_1,
     2: NoiseReduction.PLUS_2,
     3: NoiseReduction.PLUS_3,
     4: NoiseReduction.PLUS_4,
}
_NOISE_REDUCTION_FROM_NUMERIC = _NOISE_REDUCTION_MAP
_NOISE_REDUCTION_NUMERIC: dict[NoiseReduction, int] = {v: k for k, v in _NOISE_REDUCTION_MAP.items()}
# 'Normal' is a legacy label used by older firmware; it maps to 0 (normal).
_NOISE_REDUCTION_LEGACY: dict[str, int] = {"Normal": 0}


def noise_reduction_from_exif(*, noise_reduction: str) -> str:
    """Return the numeric noise reduction value as a signed string.

    Handles the legacy 'Normal' label from older firmware as 0.
    """
    if noise_reduction in _NOISE_REDUCTION_LEGACY:
        n = _NOISE_REDUCTION_LEGACY[noise_reduction]
    else:
        n = NoiseReduction(noise_reduction).numeric
    return f"+{n}" if n > 0 else str(n)


# ---------------------------------------------------------------------------
# clarity  (EXIF: Clarity)
# Stored as a bare integer string ("-5" … "5"). Range: -5 to +5, step 1.
# ---------------------------------------------------------------------------

def clarity_from_exif(*, clarity: str) -> str:
    """Return the numeric clarity value as a signed string, e.g. '+3', '-4', '0'."""
    n = int(clarity)
    return f"+{n}" if n > 0 else str(n)


# ---------------------------------------------------------------------------
# monochromatic tuning  (EXIF: BW Adjustment / BW Magenta Green)
# Stored as signed integer strings (e.g. '+10', '-5', '0'). Range: -18 to +18.
# Empty on colour film simulations that don't support monochromatic tuning.
# ---------------------------------------------------------------------------

def monochromatic_color_from_exif(*, value: str) -> str | None:
    """Return the monochromatic tuning value as a signed string, or None.

    None indicates a colour film simulation where this setting is not available.
    """
    return value if value else None
