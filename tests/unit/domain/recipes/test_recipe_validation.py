"""
Unit tests for src.domain.camera.validation.validate_recipe_for_camera.

Each parametrized test covers one allowed value for one field, ensuring
every camera-acceptable value passes without error.  Negative tests verify
that out-of-range or malformed values raise RecipeValidationError with the
correct field name.
"""
import pytest

from src.data.camera.constants import (
    CUSTOM_SLOT_CCE_PTP,
    CUSTOM_SLOT_CFX_PTP,
    CUSTOM_SLOT_DR_PRIORITY_DECODE,
    CUSTOM_SLOT_NR_DECODE,
    DRANGE_MODE_TO_PTP,
    FILM_SIMULATION_TO_PTP,
    WHITE_BALANCE_TO_PTP,
)
from src.domain.camera.validation import RecipeValidationError, validate_recipe_for_camera
from src.domain.images.dataclasses import FujifilmRecipeData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_recipe(**overrides: object) -> FujifilmRecipeData:
    defaults = dict(
        name="Test Recipe",
        film_simulation="Provia",
        d_range_priority="Off",
        grain_roughness="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Auto",
        white_balance_red=0,
        white_balance_blue=0,
        color="0",
        sharpness="0",
        high_iso_nr="0",
        clarity="0",
        dynamic_range="DR100",
        highlight="0",
        shadow="0",
    )
    defaults.update(overrides)
    return FujifilmRecipeData(**defaults)


# ---------------------------------------------------------------------------
# name — required, non-blank, ≤25 ASCII characters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["A", "My Recipe", "X" * 25])
def test_name_valid(name):
    validate_recipe_for_camera(_make_recipe(name=name))


def test_name_blank_raises():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(name=""))
    assert exc_info.value.field == "name"


def test_name_whitespace_only_raises():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(name="   "))
    assert exc_info.value.field == "name"


def test_name_too_long_raises():
    # The dataclass attrs validator catches this at construction — ValueError,
    # not RecipeValidationError, because the object can't be created at all.
    with pytest.raises(ValueError):
        _make_recipe(name="A" * 26)


def test_name_non_ascii_raises():
    # Same: caught by the dataclass attrs validator before the recipe exists.
    with pytest.raises(ValueError):
        _make_recipe(name="Café")


# ---------------------------------------------------------------------------
# film_simulation — 20 valid values
# ---------------------------------------------------------------------------

_FILM_SIM_IDS = list(FILM_SIMULATION_TO_PTP.keys())


@pytest.mark.parametrize("sim", _FILM_SIM_IDS, ids=_FILM_SIM_IDS)
def test_film_simulation_valid(sim):
    validate_recipe_for_camera(_make_recipe(film_simulation=sim))


def test_film_simulation_invalid():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(film_simulation="Unknown Film"))
    assert exc_info.value.field == "film_simulation"


# ---------------------------------------------------------------------------
# white_balance — 14 named modes + Kelvin format
# ---------------------------------------------------------------------------

_WB_MODE_IDS = list(WHITE_BALANCE_TO_PTP.keys())
_KELVIN_EXAMPLES = ["2500K", "6500K", "10000K"]


@pytest.mark.parametrize("wb", _WB_MODE_IDS, ids=_WB_MODE_IDS)
def test_white_balance_named_mode_valid(wb):
    validate_recipe_for_camera(_make_recipe(white_balance=wb))


@pytest.mark.parametrize("wb", _KELVIN_EXAMPLES, ids=_KELVIN_EXAMPLES)
def test_white_balance_kelvin_valid(wb):
    validate_recipe_for_camera(_make_recipe(white_balance=wb))


def test_white_balance_invalid_label():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(white_balance="Tungsten"))
    assert exc_info.value.field == "white_balance"


def test_white_balance_invalid_kelvin_format():
    # "K6500" is not a valid Kelvin string (digit must come before K)
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(white_balance="K6500"))
    assert exc_info.value.field == "white_balance"


# ---------------------------------------------------------------------------
# dynamic_range — 4 valid values + empty/N/A optional
# ---------------------------------------------------------------------------

_DR_MODE_IDS = list(DRANGE_MODE_TO_PTP.keys())


@pytest.mark.parametrize("dr", _DR_MODE_IDS, ids=_DR_MODE_IDS)
def test_dynamic_range_valid(dr):
    validate_recipe_for_camera(_make_recipe(dynamic_range=dr))


@pytest.mark.parametrize("dr", ["", None])
def test_dynamic_range_empty_or_none_valid(dr):
    validate_recipe_for_camera(_make_recipe(dynamic_range=dr))


def test_dynamic_range_invalid():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(dynamic_range="DR50"))
    assert exc_info.value.field == "dynamic_range"


# ---------------------------------------------------------------------------
# d_range_priority — 4 valid values + empty/N/A optional
# ---------------------------------------------------------------------------

_DR_PRI_IDS = sorted(set(CUSTOM_SLOT_DR_PRIORITY_DECODE.values()))


@pytest.mark.parametrize("pri", _DR_PRI_IDS, ids=_DR_PRI_IDS)
def test_d_range_priority_valid(pri):
    validate_recipe_for_camera(_make_recipe(d_range_priority=pri))


@pytest.mark.parametrize("pri", ["", "N/A"])
def test_d_range_priority_empty_or_na_valid(pri):
    validate_recipe_for_camera(_make_recipe(d_range_priority=pri))


def test_d_range_priority_invalid():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(d_range_priority="Medium"))
    assert exc_info.value.field == "d_range_priority"


# ---------------------------------------------------------------------------
# grain — 7 valid (roughness, size) combinations
#
# Roughness "Off" → camera writes 1 and normalises to 6 or 7, retaining the
# last remembered size.  All three sizes (Off, Small, Large) are valid when
# roughness is Off (X-S10 confirmed 2026-03-26).
# Roughness "Weak" / "Strong" → size must be "Small" or "Large".
# ---------------------------------------------------------------------------

_GRAIN_VALID_COMBOS = [
    ("Off",    None),
    ("Off",    "Off"),
    ("Off",    "Small"),
    ("Off",    "Large"),
    ("Weak",   "Small"),
    ("Weak",   "Large"),
    ("Strong", "Small"),
    ("Strong", "Large"),
]
_GRAIN_IDS = [f"{r}_{s}" for r, s in _GRAIN_VALID_COMBOS]


@pytest.mark.parametrize("roughness,size", _GRAIN_VALID_COMBOS, ids=_GRAIN_IDS)
def test_grain_valid_pair(roughness, size):
    validate_recipe_for_camera(_make_recipe(grain_roughness=roughness, grain_size=size))


def test_grain_invalid_size_for_active_roughness():
    # ("Weak", "Off") is not valid — size must be Small or Large when roughness is active
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(grain_roughness="Weak", grain_size="Off"))
    assert exc_info.value.field == "grain_roughness"


def test_grain_none_size_invalid_when_roughness_active():
    # None size is only valid when roughness is Off
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(grain_roughness="Weak", grain_size=None))
    assert exc_info.value.field == "grain_roughness"


def test_grain_invalid_roughness_value():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(grain_roughness="Medium", grain_size="Small"))
    assert exc_info.value.field == "grain_roughness"


# ---------------------------------------------------------------------------
# color_chrome_effect — 3 valid values + empty/N/A optional
# ---------------------------------------------------------------------------

_CCE_IDS = sorted(set(CUSTOM_SLOT_CCE_PTP.values()))


@pytest.mark.parametrize("cce", _CCE_IDS, ids=_CCE_IDS)
def test_color_chrome_effect_valid(cce):
    validate_recipe_for_camera(_make_recipe(color_chrome_effect=cce))


@pytest.mark.parametrize("cce", ["", "N/A"])
def test_color_chrome_effect_empty_or_na_valid(cce):
    validate_recipe_for_camera(_make_recipe(color_chrome_effect=cce))


def test_color_chrome_effect_invalid():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(color_chrome_effect="Medium"))
    assert exc_info.value.field == "color_chrome_effect"


# ---------------------------------------------------------------------------
# color_chrome_fx_blue — 3 valid values + empty/N/A optional
# ---------------------------------------------------------------------------

_CFX_IDS = sorted(set(CUSTOM_SLOT_CFX_PTP.values()))


@pytest.mark.parametrize("cfx", _CFX_IDS, ids=_CFX_IDS)
def test_color_chrome_fx_blue_valid(cfx):
    validate_recipe_for_camera(_make_recipe(color_chrome_fx_blue=cfx))


@pytest.mark.parametrize("cfx", ["", "N/A"])
def test_color_chrome_fx_blue_empty_or_na_valid(cfx):
    validate_recipe_for_camera(_make_recipe(color_chrome_fx_blue=cfx))


def test_color_chrome_fx_blue_invalid():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(color_chrome_fx_blue="Ultra"))
    assert exc_info.value.field == "color_chrome_fx_blue"


# ---------------------------------------------------------------------------
# high_iso_nr — 9 valid values (-4 to +4)
# ---------------------------------------------------------------------------

_NR_DOMAIN_VALUES = sorted(set(CUSTOM_SLOT_NR_DECODE.values()))  # [-4, -3, ..., 4]


@pytest.mark.parametrize("nr", _NR_DOMAIN_VALUES, ids=[str(v) for v in _NR_DOMAIN_VALUES])
def test_high_iso_nr_valid_int(nr):
    # Stored as signed string in the recipe (e.g. "+2", "-1", "0")
    nr_str = f"+{nr}" if nr > 0 else str(nr)
    validate_recipe_for_camera(_make_recipe(high_iso_nr=nr_str))


@pytest.mark.parametrize("nr", ["", "N/A"])
def test_high_iso_nr_empty_or_na_valid(nr):
    validate_recipe_for_camera(_make_recipe(high_iso_nr=nr))


def test_high_iso_nr_out_of_range():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(high_iso_nr="+5"))
    assert exc_info.value.field == "high_iso_nr"


def test_high_iso_nr_non_numeric():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(high_iso_nr="strong"))
    assert exc_info.value.field == "high_iso_nr"


# ---------------------------------------------------------------------------
# Numeric string fields (color, sharpness, clarity, highlight, shadow,
# monochromatic_color_warm_cool, monochromatic_color_magenta_green)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["-4", "-1", "0", "+1", "+4"])
def test_color_valid(value):
    validate_recipe_for_camera(_make_recipe(color=value))


@pytest.mark.parametrize("value", ["", "N/A"])
def test_color_empty_or_na_valid(value):
    validate_recipe_for_camera(_make_recipe(color=value))


def test_color_non_numeric():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(color="vivid"))
    assert exc_info.value.field == "color"


@pytest.mark.parametrize("value", ["-4", "0", "+4"])
def test_sharpness_valid(value):
    validate_recipe_for_camera(_make_recipe(sharpness=value))


def test_sharpness_non_numeric():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(sharpness="soft"))
    assert exc_info.value.field == "sharpness"


@pytest.mark.parametrize("value", ["-5", "0", "+5"])
def test_clarity_valid(value):
    validate_recipe_for_camera(_make_recipe(clarity=value))


def test_clarity_non_numeric():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(clarity="high"))
    assert exc_info.value.field == "clarity"


@pytest.mark.parametrize("value", ["-2", "-1.5", "-1", "-0.5", "0", "+0.5", "+1", "+1.5", "+2", "+2.5", "+3", "+3.5", "+4", None])
def test_highlight_valid(value):
    validate_recipe_for_camera(_make_recipe(highlight=value))


def test_highlight_non_numeric():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(highlight="hard"))
    assert exc_info.value.field == "highlight"


@pytest.mark.parametrize("value", ["-2", "-1.5", "0", "+1.5", "+4", None])
def test_shadow_valid(value):
    validate_recipe_for_camera(_make_recipe(shadow=value))


def test_shadow_non_numeric():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(shadow="hard"))
    assert exc_info.value.field == "shadow"


@pytest.mark.parametrize("value", ["-9", "0", "+9", None, ""])
def test_monochromatic_color_warm_cool_valid(value):
    validate_recipe_for_camera(_make_recipe(monochromatic_color_warm_cool=value))


def test_monochromatic_color_warm_cool_non_numeric():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(monochromatic_color_warm_cool="warm"))
    assert exc_info.value.field == "monochromatic_color_warm_cool"


@pytest.mark.parametrize("value", ["-9", "0", "+9", None, ""])
def test_monochromatic_color_magenta_green_valid(value):
    validate_recipe_for_camera(_make_recipe(monochromatic_color_magenta_green=value))


def test_monochromatic_color_magenta_green_non_numeric():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(monochromatic_color_magenta_green="green"))
    assert exc_info.value.field == "monochromatic_color_magenta_green"


# ---------------------------------------------------------------------------
# dynamic_range: "N/A" is invalid; None/"" are allowed regardless of drp;
# None/"" are also explicitly valid when d_range_priority is active (not Off)
# ---------------------------------------------------------------------------

def test_dynamic_range_na_is_invalid():
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_recipe_for_camera(_make_recipe(dynamic_range="N/A"))
    assert exc_info.value.field == "dynamic_range"


_DRP_ACTIVE = ["Auto", "Weak", "Strong"]


@pytest.mark.parametrize("drp", _DRP_ACTIVE)
@pytest.mark.parametrize("dr", [None, ""])
def test_dynamic_range_omitted_when_drp_active(drp, dr):
    validate_recipe_for_camera(_make_recipe(d_range_priority=drp, dynamic_range=dr))


# ---------------------------------------------------------------------------
# shadow / highlight: None/"" allowed when d_range_priority is active (not Off)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("drp", _DRP_ACTIVE)
@pytest.mark.parametrize("value", [None, ""])
def test_shadow_omitted_when_drp_active(drp, value):
    validate_recipe_for_camera(_make_recipe(d_range_priority=drp, shadow=value))


@pytest.mark.parametrize("drp", _DRP_ACTIVE)
@pytest.mark.parametrize("value", [None, ""])
def test_highlight_omitted_when_drp_active(drp, value):
    validate_recipe_for_camera(_make_recipe(d_range_priority=drp, highlight=value))


# ---------------------------------------------------------------------------
# monochromatic color fields: None/"" when film sim is not monochromatic
# ---------------------------------------------------------------------------

_MONO_SIMS = [
    s for s in FILM_SIMULATION_TO_PTP
    if any(k in s for k in ("Monochrome", "Acros", "Sepia"))
]
_NON_MONO_SIMS = [s for s in FILM_SIMULATION_TO_PTP if s not in _MONO_SIMS]


@pytest.mark.parametrize("sim", _NON_MONO_SIMS)
@pytest.mark.parametrize("value", [None, ""])
def test_mono_warm_cool_omitted_for_non_mono_sim(sim, value):
    validate_recipe_for_camera(_make_recipe(film_simulation=sim, monochromatic_color_warm_cool=value))


@pytest.mark.parametrize("sim", _NON_MONO_SIMS)
@pytest.mark.parametrize("value", [None, ""])
def test_mono_magenta_green_omitted_for_non_mono_sim(sim, value):
    validate_recipe_for_camera(_make_recipe(film_simulation=sim, monochromatic_color_magenta_green=value))


# ---------------------------------------------------------------------------
# grain_size: None or "" are both valid when roughness is Off
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("size", [None, ""])
def test_grain_size_omitted_when_roughness_off(size):
    validate_recipe_for_camera(_make_recipe(grain_roughness="Off", grain_size=size))


# ---------------------------------------------------------------------------
# color: None/"" when film sim is monochromatic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sim", _MONO_SIMS)
@pytest.mark.parametrize("value", [None, ""])
def test_color_omitted_for_mono_sim(sim, value):
    validate_recipe_for_camera(_make_recipe(film_simulation=sim, color=value))
