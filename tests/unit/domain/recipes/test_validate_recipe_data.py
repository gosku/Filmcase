"""Unit tests for src.domain.recipes.validation.validate_recipe_data."""
import pytest

from src.domain.images.dataclasses import FujifilmRecipeData
from src.domain.recipes.validation import InvalidFujifilmRecipeData, validate_recipe_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_A_MONO_SIM = "Acros STD"
_A_COLOR_SIM = "Provia"


def _make_color_data(**overrides: object) -> FujifilmRecipeData:
    """Minimal valid data for a colour (non-monochromatic) film simulation with DRP off."""
    base = dict(
        film_simulation=_A_COLOR_SIM,
        d_range_priority="Off",
        grain_roughness="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Auto",
        white_balance_red=0,
        white_balance_blue=0,
        sharpness="0",
        high_iso_nr="0",
        clarity="0",
        dynamic_range="DR100",
        grain_size=None,
        highlight="0",
        shadow="0",
        color="0",
        monochromatic_color_warm_cool=None,
        monochromatic_color_magenta_green=None,
    )
    base.update(overrides)
    return FujifilmRecipeData(**base)


def _make_mono_data(**overrides: object) -> FujifilmRecipeData:
    """Minimal valid data for a monochromatic film simulation with DRP off."""
    base = dict(
        film_simulation=_A_MONO_SIM,
        d_range_priority="Off",
        grain_roughness="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Auto",
        white_balance_red=0,
        white_balance_blue=0,
        sharpness="0",
        high_iso_nr="0",
        clarity="0",
        dynamic_range="DR100",
        grain_size=None,
        highlight="0",
        shadow="0",
        color=None,
        monochromatic_color_warm_cool="0",
        monochromatic_color_magenta_green="0",
    )
    base.update(overrides)
    return FujifilmRecipeData(**base)


def _make_drp_active_data(**overrides: object) -> FujifilmRecipeData:
    """Minimal valid data with D-Range Priority active (DR/highlight/shadow absent)."""
    base = dict(
        film_simulation=_A_COLOR_SIM,
        d_range_priority="Auto",
        grain_roughness="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Auto",
        white_balance_red=0,
        white_balance_blue=0,
        sharpness="0",
        high_iso_nr="0",
        clarity="0",
        dynamic_range=None,
        grain_size=None,
        highlight=None,
        shadow=None,
        color="0",
        monochromatic_color_warm_cool=None,
        monochromatic_color_magenta_green=None,
    )
    base.update(overrides)
    return FujifilmRecipeData(**base)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestValidateRecipeDataValid:
    def test_color_sim_drp_off_grain_off(self) -> None:
        validate_recipe_data(_make_color_data())

    def test_mono_sim_drp_off_grain_off(self) -> None:
        validate_recipe_data(_make_mono_data())

    def test_drp_active_dr_and_tones_absent(self) -> None:
        validate_recipe_data(_make_drp_active_data())

    def test_grain_active_size_provided(self) -> None:
        validate_recipe_data(_make_color_data(grain_roughness="Weak", grain_size="Small"))

    @pytest.mark.parametrize("drp", ["Auto", "Weak", "Strong"])
    def test_all_drp_active_values_accepted(self, drp: str) -> None:
        validate_recipe_data(_make_drp_active_data(d_range_priority=drp))

    @pytest.mark.parametrize("mono_sim", [
        "Acros STD", "Acros Yellow", "Acros Red", "Acros Green",
        "Monochrome STD", "Monochrome Yellow", "Monochrome Red", "Monochrome Green",
        "Sepia",
    ])
    def test_all_mono_sims_require_mono_fields(self, mono_sim: str) -> None:
        validate_recipe_data(_make_mono_data(film_simulation=mono_sim))

    def test_white_balance_red_blue_zero_is_valid(self) -> None:
        validate_recipe_data(_make_color_data(white_balance_red=0, white_balance_blue=0))


# ---------------------------------------------------------------------------
# Always-required string fields
# ---------------------------------------------------------------------------


class TestValidateRecipeDataRequiredFields:
    @pytest.mark.parametrize("field", [
        "film_simulation",
        "d_range_priority",
        "grain_roughness",
        "color_chrome_effect",
        "color_chrome_fx_blue",
        "white_balance",
        "sharpness",
        "high_iso_nr",
        "clarity",
    ])
    def test_empty_string_raises(self, field: str) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_color_data(**{field: ""}))
        assert exc_info.value.field == field

    @pytest.mark.parametrize("field", ["color_chrome_effect", "color_chrome_fx_blue"])
    def test_cce_cfx_empty_raises_for_mono_sim_too(self, field: str) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_mono_data(**{field: ""}))
        assert exc_info.value.field == field


# ---------------------------------------------------------------------------
# D-Range Priority rules
# ---------------------------------------------------------------------------


class TestValidateRecipeDataDRP:
    @pytest.mark.parametrize("drp", ["Auto", "Weak", "Strong"])
    def test_dynamic_range_must_be_none_when_drp_active(self, drp: str) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_drp_active_data(d_range_priority=drp, dynamic_range="DR100"))
        assert exc_info.value.field == "dynamic_range"

    @pytest.mark.parametrize("drp", ["Auto", "Weak", "Strong"])
    def test_highlight_must_be_none_when_drp_active(self, drp: str) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_drp_active_data(d_range_priority=drp, highlight="0"))
        assert exc_info.value.field == "highlight"

    @pytest.mark.parametrize("drp", ["Auto", "Weak", "Strong"])
    def test_shadow_must_be_none_when_drp_active(self, drp: str) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_drp_active_data(d_range_priority=drp, shadow="0"))
        assert exc_info.value.field == "shadow"

    def test_dynamic_range_required_when_drp_off(self) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_color_data(dynamic_range=None))
        assert exc_info.value.field == "dynamic_range"

    def test_highlight_required_when_drp_off(self) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_color_data(highlight=None))
        assert exc_info.value.field == "highlight"

    def test_shadow_required_when_drp_off(self) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_color_data(shadow=None))
        assert exc_info.value.field == "shadow"


# ---------------------------------------------------------------------------
# Grain rules
# ---------------------------------------------------------------------------


class TestValidateRecipeDataGrain:
    def test_grain_size_must_be_none_when_roughness_off(self) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_color_data(grain_roughness="Off", grain_size="Small"))
        assert exc_info.value.field == "grain_size"

    @pytest.mark.parametrize("roughness", ["Weak", "Strong"])
    def test_grain_size_required_when_roughness_active(self, roughness: str) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_color_data(grain_roughness=roughness, grain_size=None))
        assert exc_info.value.field == "grain_size"

    @pytest.mark.parametrize("roughness,size", [("Weak", "Small"), ("Weak", "Large"), ("Strong", "Small"), ("Strong", "Large")])
    def test_grain_active_with_valid_size_passes(self, roughness: str, size: str) -> None:
        validate_recipe_data(_make_color_data(grain_roughness=roughness, grain_size=size))


# ---------------------------------------------------------------------------
# Monochromatic film simulation rules
# ---------------------------------------------------------------------------


class TestValidateRecipeDataMonochromatic:
    def test_color_must_be_none_for_mono_sim(self) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_mono_data(color="0"))
        assert exc_info.value.field == "color"

    def test_mono_warm_cool_required_for_mono_sim(self) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_mono_data(monochromatic_color_warm_cool=None))
        assert exc_info.value.field == "monochromatic_color_warm_cool"

    def test_mono_magenta_green_required_for_mono_sim(self) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_mono_data(monochromatic_color_magenta_green=None))
        assert exc_info.value.field == "monochromatic_color_magenta_green"

    def test_color_required_for_non_mono_sim(self) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_color_data(color=None))
        assert exc_info.value.field == "color"

    def test_mono_warm_cool_must_be_none_for_non_mono_sim(self) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_color_data(monochromatic_color_warm_cool="0"))
        assert exc_info.value.field == "monochromatic_color_warm_cool"

    def test_mono_magenta_green_must_be_none_for_non_mono_sim(self) -> None:
        with pytest.raises(InvalidFujifilmRecipeData) as exc_info:
            validate_recipe_data(_make_color_data(monochromatic_color_magenta_green="0"))
        assert exc_info.value.field == "monochromatic_color_magenta_green"
