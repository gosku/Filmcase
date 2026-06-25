"""Unit tests for src.domain.recipes.normalization.normalize_recipe_data."""
import pytest

from src.domain.images.dataclasses import FujifilmRecipeData
from src.domain.recipes.normalization import normalize_recipe_data


_A_MONO_SIM = "Acros STD"
_A_COLOR_SIM = "Provia"


def _make_color_data(**overrides: object) -> FujifilmRecipeData:
    """Minimal fully-populated data for a colour sim, DRP off, grain off."""
    base: dict[str, object] = dict(
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
    """Minimal fully-populated data for a mono sim, DRP off, grain off."""
    base: dict[str, object] = dict(
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


class TestNormalizeRecipeDataColorSim:
    def test_nulls_mono_fields_for_colour_sim(self) -> None:
        data = _make_color_data(monochromatic_color_warm_cool="+1", monochromatic_color_magenta_green="-2")
        result = normalize_recipe_data(data)
        assert result.monochromatic_color_warm_cool is None
        assert result.monochromatic_color_magenta_green is None

    def test_preserves_color_for_colour_sim(self) -> None:
        data = _make_color_data(color="+2")
        result = normalize_recipe_data(data)
        assert result.color == "+2"

    def test_already_clean_colour_sim_passes_through_unchanged(self) -> None:
        data = _make_color_data()
        result = normalize_recipe_data(data)
        assert result == data


class TestNormalizeRecipeDataMonoSim:
    def test_nulls_color_for_mono_sim(self) -> None:
        data = _make_mono_data(color="0")
        result = normalize_recipe_data(data)
        assert result.color is None

    def test_preserves_mono_fields_for_mono_sim(self) -> None:
        data = _make_mono_data(monochromatic_color_warm_cool="-2", monochromatic_color_magenta_green="+1")
        result = normalize_recipe_data(data)
        assert result.monochromatic_color_warm_cool == "-2"
        assert result.monochromatic_color_magenta_green == "+1"

    def test_already_clean_mono_sim_passes_through_unchanged(self) -> None:
        data = _make_mono_data()
        result = normalize_recipe_data(data)
        assert result == data

    @pytest.mark.parametrize("mono_sim", [
        "Acros STD", "Acros Yellow", "Acros Red", "Acros Green",
        "Monochrome STD", "Monochrome Yellow", "Monochrome Red", "Monochrome Green",
        "Sepia",
    ])
    def test_nulls_color_for_all_mono_sims(self, mono_sim: str) -> None:
        data = _make_mono_data(film_simulation=mono_sim, color="+1")
        result = normalize_recipe_data(data)
        assert result.color is None


class TestNormalizeRecipeDataDRP:
    def test_nulls_dr_hl_sh_when_drp_active(self) -> None:
        data = _make_color_data(d_range_priority="Auto", dynamic_range="DR100", highlight="+1", shadow="-1")
        result = normalize_recipe_data(data)
        assert result.dynamic_range is None
        assert result.highlight is None
        assert result.shadow is None

    def test_preserves_dr_hl_sh_when_drp_off(self) -> None:
        data = _make_color_data(d_range_priority="Off", dynamic_range="DR200", highlight="+2", shadow="-2")
        result = normalize_recipe_data(data)
        assert result.dynamic_range == "DR200"
        assert result.highlight == "+2"
        assert result.shadow == "-2"

    @pytest.mark.parametrize("drp", ["Auto", "Weak", "Strong"])
    def test_all_active_drp_values_null_out_dr_fields(self, drp: str) -> None:
        data = _make_color_data(d_range_priority=drp, dynamic_range="DR100", highlight="0", shadow="0")
        result = normalize_recipe_data(data)
        assert result.dynamic_range is None
        assert result.highlight is None
        assert result.shadow is None


class TestNormalizeRecipeDataGrain:
    def test_nulls_grain_size_when_roughness_off(self) -> None:
        data = _make_color_data(grain_roughness="Off", grain_size="Small")
        result = normalize_recipe_data(data)
        assert result.grain_size is None

    def test_preserves_grain_size_when_roughness_active(self) -> None:
        data = _make_color_data(grain_roughness="Weak", grain_size="Large")
        result = normalize_recipe_data(data)
        assert result.grain_size == "Large"

    @pytest.mark.parametrize("roughness,size", [("Weak", "Small"), ("Weak", "Large"), ("Strong", "Small"), ("Strong", "Large")])
    def test_grain_size_preserved_for_all_active_roughness_size_combinations(self, roughness: str, size: str) -> None:
        data = _make_color_data(grain_roughness=roughness, grain_size=size)
        result = normalize_recipe_data(data)
        assert result.grain_size == size


class TestNormalizeRecipeDataIdempotency:
    def test_normalizing_twice_produces_same_result_as_once(self) -> None:
        dirty = _make_color_data(
            d_range_priority="Auto",
            dynamic_range="DR100",
            highlight="+1",
            shadow="-1",
            monochromatic_color_warm_cool="+2",
        )
        once = normalize_recipe_data(dirty)
        twice = normalize_recipe_data(once)
        assert once == twice

    def test_idempotent_on_already_normalized_color_data(self) -> None:
        data = _make_color_data()
        assert normalize_recipe_data(normalize_recipe_data(data)) == normalize_recipe_data(data)

    def test_idempotent_on_already_normalized_mono_data(self) -> None:
        data = _make_mono_data()
        assert normalize_recipe_data(normalize_recipe_data(data)) == normalize_recipe_data(data)


class TestNormalizeRecipeDataPreservesOtherFields:
    def test_unrelated_fields_are_not_modified(self) -> None:
        data = _make_color_data(
            name="My Recipe",
            white_balance="Kelvin",
            white_balance_red=3,
            white_balance_blue=-2,
            sharpness="+1",
            high_iso_nr="-2",
            clarity="+3",
            color_chrome_effect="Strong",
            color_chrome_fx_blue="Weak",
        )
        result = normalize_recipe_data(data)
        assert result.name == "My Recipe"
        assert result.white_balance == "Kelvin"
        assert result.white_balance_red == 3
        assert result.white_balance_blue == -2
        assert result.sharpness == "+1"
        assert result.high_iso_nr == "-2"
        assert result.clarity == "+3"
        assert result.color_chrome_effect == "Strong"
        assert result.color_chrome_fx_blue == "Weak"

    def test_returns_new_object_not_same_reference(self) -> None:
        data = _make_color_data()
        result = normalize_recipe_data(data)
        assert result is not data
