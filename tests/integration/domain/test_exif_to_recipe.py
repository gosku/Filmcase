"""Integration tests for exif_to_recipe() using real 1x1 pixel fixture images.

Each fixture is a real Fujifilm JPEG shrunk to 1x1 pixel with its original EXIF
preserved.  Tests call read_image_exif() (which runs exiftool) and then
exif_to_recipe() to verify the field mapping rules described in:
  docs/dynamic_range_exif_mapping.md
"""

from pathlib import Path

import pytest

from src.domain.images.queries import exif_to_recipe, read_image_exif

FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures" / "recipe"


def _recipe(filename: str):
    """Read EXIF from a fixture file and convert to a recipe."""
    return exif_to_recipe(exif=read_image_exif(image_path=str(FIXTURES / filename)))


# ---------------------------------------------------------------------------
# film_simulation — sourced from EXIF Film Mode field
# ---------------------------------------------------------------------------

class TestFilmSimulationFromFilmModeField:
    def test_provia(self):
        assert _recipe("film_simulation_provia.jpg").film_simulation == "Provia"

    def test_classic_chrome(self):
        assert _recipe("film_simulation_classic_chrome.jpg").film_simulation == "Classic Chrome"

    def test_classic_negative(self):
        assert _recipe("film_simulation_classic_negative.jpg").film_simulation == "Classic Negative"

    def test_eterna(self):
        assert _recipe("film_simulation_eterna.jpg").film_simulation == "Eterna"

    def test_astia(self):
        assert _recipe("film_simulation_astia.jpg").film_simulation == "Astia"

    def test_velvia(self):
        assert _recipe("film_simulation_velvia.jpg").film_simulation == "Velvia"

    def test_pro_neg_std(self):
        assert _recipe("film_simulation_pro_neg_std.jpg").film_simulation == "Pro Neg. Std"

    def test_pro_neg_hi(self):
        assert _recipe("film_simulation_pro_neg_hi.jpg").film_simulation == "Pro Neg. Hi"

    def test_bleach_bypass(self):
        assert _recipe("film_simulation_bleach_bypass.jpg").film_simulation == "Eterna Bleach Bypass"


# ---------------------------------------------------------------------------
# film_simulation — sourced from EXIF Saturation (color) field
# (Film Mode field is empty for these; the Saturation value identifies the sim)
# ---------------------------------------------------------------------------

class TestFilmSimulationFromColorField:
    def test_acros(self):
        assert _recipe("film_simulation_acros.jpg").film_simulation == "Acros STD"

    def test_acros_yellow(self):
        assert _recipe("film_simulation_acros_yellow.jpg").film_simulation == "Acros Yellow"

    def test_acros_red(self):
        assert _recipe("film_simulation_acros_red.jpg").film_simulation == "Acros Red"

    def test_acros_green(self):
        assert _recipe("film_simulation_acros_green.jpg").film_simulation == "Acros Green"

    def test_monochrome(self):
        assert _recipe("film_simulation_monochrome.jpg").film_simulation == "Monochrome STD"

    def test_monochrome_yellow(self):
        assert _recipe("film_simulation_monochrome_yellow.jpg").film_simulation == "Monochrome Yellow"

    def test_monochrome_red(self):
        assert _recipe("film_simulation_monochrome_red.jpg").film_simulation == "Monochrome Red"

    def test_monochrome_green(self):
        assert _recipe("film_simulation_monochrome_green.jpg").film_simulation == "Monochrome Green"

    def test_sepia(self):
        assert _recipe("film_simulation_sepia.jpg").film_simulation == "Sepia"


# ---------------------------------------------------------------------------
# dynamic_range — DR100 / DR-Auto / DR200 / DR400
# When dynamic_range is active, d_range_priority must be "Off".
# ---------------------------------------------------------------------------

class TestDynamicRange:
    def test_dr100(self):
        recipe = _recipe("dynamic_range_dr100.jpg")
        assert recipe.dynamic_range == "DR100"
        assert recipe.d_range_priority == "Off"

    def test_dr_auto(self):
        recipe = _recipe("dynamic_range_dr_auto.jpg")
        assert recipe.dynamic_range == "DR-Auto"
        assert recipe.d_range_priority == "Off"

    def test_dr200(self):
        recipe = _recipe("dynamic_range_dr200.jpg")
        assert recipe.dynamic_range == "DR200"
        assert recipe.d_range_priority == "Off"

    def test_dr400(self):
        recipe = _recipe("dynamic_range_dr400.jpg")
        assert recipe.dynamic_range == "DR400"
        assert recipe.d_range_priority == "Off"


# ---------------------------------------------------------------------------
# d_range_priority — Auto / Weak / Strong
# When D-Range Priority is active, dynamic_range must be empty.
# ---------------------------------------------------------------------------

class TestDRangePriority:
    def test_auto(self):
        recipe = _recipe("d_range_priority_auto.jpg")
        assert recipe.d_range_priority == "Auto"
        assert recipe.dynamic_range is None

    def test_weak(self):
        recipe = _recipe("d_range_priority_weak.jpg")
        assert recipe.d_range_priority == "Weak"
        assert recipe.dynamic_range is None

    def test_strong(self):
        recipe = _recipe("d_range_priority_strong.jpg")
        assert recipe.d_range_priority == "Strong"
        assert recipe.dynamic_range is None


# ---------------------------------------------------------------------------
# grain_roughness / grain_size
# grain_size is always "Off" when grain_roughness is "Off".
# ---------------------------------------------------------------------------

class TestGrain:
    def test_off(self):
        # The DR100 fixture has grain off — reuse it rather than a dedicated file
        recipe = _recipe("dynamic_range_dr100.jpg")
        assert recipe.grain_roughness == "Off"
        assert recipe.grain_size is None

    def test_weak_small(self):
        recipe = _recipe("grain_weak_small.jpg")
        assert recipe.grain_roughness == "Weak"
        assert recipe.grain_size == "Small"

    def test_weak_large(self):
        recipe = _recipe("grain_weak_large.jpg")
        assert recipe.grain_roughness == "Weak"
        assert recipe.grain_size == "Large"

    def test_strong_small(self):
        recipe = _recipe("grain_strong_small.jpg")
        assert recipe.grain_roughness == "Strong"
        assert recipe.grain_size == "Small"

    def test_strong_large(self):
        recipe = _recipe("grain_strong_large.jpg")
        assert recipe.grain_roughness == "Strong"
        assert recipe.grain_size == "Large"


# ---------------------------------------------------------------------------
# color_chrome_effect  (EXIF tag: Color Chrome Effect)
# ---------------------------------------------------------------------------

class TestColorChromeEffect:
    def test_off(self):
        # Reuse DR100 fixture which has Color Chrome Effect: Off
        assert _recipe("dynamic_range_dr100.jpg").color_chrome_effect == "Off"

    def test_weak(self):
        assert _recipe("color_chrome_effect_weak.jpg").color_chrome_effect == "Weak"

    def test_strong(self):
        assert _recipe("color_chrome_effect_strong.jpg").color_chrome_effect == "Strong"


# ---------------------------------------------------------------------------
# color_chrome_fx_blue  (EXIF tag: Color Chrome FX Blue)
# ---------------------------------------------------------------------------

class TestColorChromeFxBlue:
    def test_off(self):
        # Reuse DR100 fixture which has Color Chrome FX Blue: Off
        assert _recipe("dynamic_range_dr100.jpg").color_chrome_fx_blue == "Off"

    def test_weak(self):
        assert _recipe("color_chrome_fx_blue_weak.jpg").color_chrome_fx_blue == "Weak"

    def test_strong(self):
        assert _recipe("color_chrome_fx_blue_strong.jpg").color_chrome_fx_blue == "Strong"


# ---------------------------------------------------------------------------
# white_balance  (EXIF tag: White Balance)
# white_balance_red / white_balance_blue  (EXIF tag: White Balance Fine Tune, ÷20)
# ---------------------------------------------------------------------------

class TestWhiteBalance:
    def test_auto(self):
        assert _recipe("white_balance_auto.jpg").white_balance == "Auto"

    def test_daylight(self):
        assert _recipe("white_balance_daylight.jpg").white_balance == "Daylight"

    def test_incandescent(self):
        assert _recipe("white_balance_incandescent.jpg").white_balance == "Incandescent"

    def test_daylight_fluorescent(self):
        assert _recipe("white_balance_daylight_fluorescent.jpg").white_balance == "Daylight Fluorescent"

    def test_kelvin_includes_temperature(self):
        assert _recipe("white_balance_kelvin.jpg").white_balance == "5500K"

    def test_auto_white_priority(self):
        # dr100 fixture has White Balance: Auto (white priority)
        assert _recipe("dynamic_range_dr100.jpg").white_balance == "Auto (white priority)"


class TestWhiteBalanceFineTune:
    def test_zero_fine_tune(self):
        recipe = _recipe("white_balance_auto.jpg")
        assert recipe.white_balance_red == 0
        assert recipe.white_balance_blue == 0

    def test_nonzero_fine_tune(self):
        # fixture has Red +80, Blue -60 raw (÷20 → +4, -3)
        recipe = _recipe("white_balance_fine_tune.jpg")
        assert recipe.white_balance_red == 4
        assert recipe.white_balance_blue == -3


# ---------------------------------------------------------------------------
# highlight / shadow  (EXIF tags: Highlight Tone / Shadow Tone)
# Both are numeric floats; half-step values (±0.5, ±1.5) are valid.
# When D-Range Priority is active the camera forces these to 0.
# ---------------------------------------------------------------------------

class TestHighlight:
    def test_negative_integer(self):
        assert _recipe("dynamic_range_dr100.jpg").highlight == "-2"  # dr100 fixture has -2 (soft)

    def test_positive_integer(self):
        assert _recipe("highlight_plus2.jpg").highlight == "+2"

    def test_negative_half_step(self):
        assert _recipe("highlight_minus1_5.jpg").highlight == "-1.5"

    def test_none_when_d_range_priority_active(self):
        assert _recipe("d_range_priority_weak.jpg").highlight is None


class TestShadow:
    def test_zero(self):
        assert _recipe("dynamic_range_dr100.jpg").shadow == "0"

    def test_positive_integer(self):
        assert _recipe("shadow_plus3.jpg").shadow == "+3"

    def test_negative_half_step(self):
        assert _recipe("shadow_minus0_5.jpg").shadow == "-0.5"

    def test_none_when_d_range_priority_active(self):
        assert _recipe("d_range_priority_weak.jpg").shadow is None


# ---------------------------------------------------------------------------
# color  (EXIF tag: Saturation)
# Returns the numeric value as a string, or None for B&W/Acros/Sepia modes
# where the field encodes the film simulation name instead of a saturation level.
# ---------------------------------------------------------------------------

class TestColor:
    def test_zero(self):
        assert _recipe("dynamic_range_dr100.jpg").color == "0"

    def test_positive(self):
        assert _recipe("color_plus2.jpg").color == "+2"

    def test_none_for_acros(self):
        assert _recipe("film_simulation_acros.jpg").color is None

    def test_none_for_monochrome(self):
        assert _recipe("film_simulation_monochrome.jpg").color is None

    def test_none_for_sepia(self):
        assert _recipe("film_simulation_sepia.jpg").color is None

    def test_none_for_film_simulation(self):
        # Eterna fixture has color = 'Film Simulation' (saturation not user-set)
        assert _recipe("film_simulation_eterna.jpg").color is None


# ---------------------------------------------------------------------------
# sharpness  (EXIF tag: Sharpness) — -4 to +4
# 'Film Simulation' means sharpness is controlled by the film profile → N/A
# ---------------------------------------------------------------------------

class TestSharpness:
    def test_zero(self):
        assert _recipe("dynamic_range_dr100.jpg").sharpness == "0"

    def test_positive(self):
        assert _recipe("sharpness_plus3.jpg").sharpness == "+3"

    def test_negative(self):
        assert _recipe("sharpness_minus2.jpg").sharpness == "-2"


# ---------------------------------------------------------------------------
# high_iso_nr  (EXIF tag: Noise Reduction) — -4 to +4
# ---------------------------------------------------------------------------

class TestHighIsoNr:
    def test_zero(self):
        assert _recipe("dynamic_range_dr100.jpg").high_iso_nr == "0"

    def test_negative(self):
        assert _recipe("noise_reduction_minus3.jpg").high_iso_nr == "-3"


# ---------------------------------------------------------------------------
# clarity  (EXIF tag: Clarity) — -5 to +5, bare integer strings
# ---------------------------------------------------------------------------

class TestClarity:
    def test_zero(self):
        assert _recipe("dynamic_range_dr100.jpg").clarity == "0"

    def test_positive(self):
        assert _recipe("clarity_plus3.jpg").clarity == "+3"

    def test_negative(self):
        assert _recipe("clarity_minus4.jpg").clarity == "-4"


# ---------------------------------------------------------------------------
# monochromatic_color_warm_cool / monochromatic_color_magenta_green
# (EXIF: BW Adjustment / BW Magenta Green) — -18 to +18
# Empty on colour film simulations → None
# ---------------------------------------------------------------------------

class TestMonochromaticColor:
    def test_zero_on_bw(self):
        recipe = _recipe("film_simulation_acros.jpg")
        assert recipe.monochromatic_color_warm_cool == "0"
        assert recipe.monochromatic_color_magenta_green == "0"

    def test_none_on_colour_simulation(self):
        recipe = _recipe("film_simulation_provia.jpg")
        assert recipe.monochromatic_color_warm_cool is None
        assert recipe.monochromatic_color_magenta_green is None

    def test_warm_cool_positive(self):
        assert _recipe("monochromatic_warm_cool_plus10.jpg").monochromatic_color_warm_cool == "+10"

    def test_magenta_green_negative(self):
        assert _recipe("monochromatic_magenta_green_minus6.jpg").monochromatic_color_magenta_green == "-6"
