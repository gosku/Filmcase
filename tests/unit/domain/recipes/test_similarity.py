"""Unit tests for the pure similarity helpers (no database)."""

from decimal import Decimal

import pytest

from src.data import models
from src.domain.recipes import similarity


def _recipe(**overrides: object) -> models.FujifilmRecipe:
    """Build an unsaved recipe with neutral defaults, for the pure metric."""
    defaults: dict[str, object] = {
        "film_simulation": "Provia",
        "dynamic_range": "DR100",
        "d_range_priority": "Off",
        "grain_roughness": "Off",
        "grain_size": "Off",
        "color_chrome_effect": "Off",
        "color_chrome_fx_blue": "Off",
        "white_balance": "Auto",
        "white_balance_red": 0,
        "white_balance_blue": 0,
        "highlight": None,
        "shadow": None,
        "color": None,
        "sharpness": None,
        "high_iso_nr": None,
        "clarity": None,
        "monochromatic_color_warm_cool": None,
        "monochromatic_color_magenta_green": None,
    }
    defaults.update(overrides)
    return models.FujifilmRecipe(**defaults)


# Field values of the recipes used in the ADR worked examples.
_PORTRA_V2 = dict(
    film_simulation="Classic Chrome", dynamic_range="DR400", d_range_priority="Off",
    grain_roughness="Off", grain_size="Off", color_chrome_effect="Strong",
    color_chrome_fx_blue="Weak", white_balance="5200K", white_balance_red=2,
    white_balance_blue=-4, highlight=Decimal("0.0"), shadow=Decimal("-2.0"),
    color=Decimal("2.0"), sharpness=Decimal("0.0"), high_iso_nr=Decimal("-4.0"),
    clarity=Decimal("0.0"),
)
_PORTRA_V3 = {**_PORTRA_V2, "dynamic_range": "DR200", "sharpness": Decimal("-1.0"), "high_iso_nr": Decimal("-2.0")}
_TRI_X = dict(
    film_simulation="Acros Yellow", dynamic_range="DR200", d_range_priority="Off",
    grain_roughness="Off", grain_size="Off", color_chrome_effect="Strong",
    color_chrome_fx_blue="Off", white_balance="Daylight", white_balance_red=9,
    white_balance_blue=-9, highlight=Decimal("0.0"), shadow=Decimal("3.0"),
    color=None, sharpness=Decimal("1.0"), high_iso_nr=Decimal("-2.0"),
    clarity=Decimal("0.0"), monochromatic_color_warm_cool=Decimal("0.0"),
    monochromatic_color_magenta_green=Decimal("0.0"),
)


class TestFilmSimulationDistance:
    def test_identical_simulations_are_zero(self) -> None:
        assert similarity.film_simulation_distance("Velvia", "Velvia") == 0.0

    def test_is_symmetric(self) -> None:
        forward = similarity.film_simulation_distance("Provia", "Velvia")
        backward = similarity.film_simulation_distance("Velvia", "Provia")
        assert forward == backward

    def test_neighbours_are_closer_than_opposites(self) -> None:
        # Astia is a soft Provia; Eterna (flat) is far from Velvia (vivid).
        assert similarity.film_simulation_distance("Provia", "Astia") < similarity.film_simulation_distance("Eterna", "Velvia")

    def test_colour_to_black_and_white_is_a_large_jump(self) -> None:
        colour_to_colour = similarity.film_simulation_distance("Provia", "Velvia")
        colour_to_bw = similarity.film_simulation_distance("Provia", "Acros STD")
        assert colour_to_bw > colour_to_colour

    def test_sepia_is_distinct_from_neutral_monochrome_but_close(self) -> None:
        distance = similarity.film_simulation_distance("Sepia", "Monochrome STD")
        assert 0.0 < distance < 0.2

    def test_every_pair_is_within_unit_range(self) -> None:
        sims = list(similarity._FILM_SIM_RAW)
        for a in sims:
            for b in sims:
                assert 0.0 <= similarity.film_simulation_distance(a, b) <= 1.0


class TestWhiteBalanceDistance:
    def test_identical_modes_are_zero(self) -> None:
        assert similarity.white_balance_distance("5200K", "5200K") == 0.0

    def test_daylight_equals_5500_kelvin(self) -> None:
        assert similarity.white_balance_distance("Daylight", "5500K") == 0.0

    def test_warmer_gap_is_larger_in_mired_space(self) -> None:
        # A 300K gap near tungsten is more visible than the same gap near daylight.
        warm = similarity.white_balance_distance("3200K", "3500K")
        cool = similarity.white_balance_distance("7000K", "7300K")
        assert warm > cool

    def test_auto_versus_temperature_is_the_fixed_penalty(self) -> None:
        assert similarity.white_balance_distance("Auto", "5500K") == similarity.WB_AUTO_PENALTY

    def test_same_auto_mode_is_zero(self) -> None:
        assert similarity.white_balance_distance("Auto", "Auto") == 0.0

    def test_two_different_auto_modes_take_the_penalty(self) -> None:
        assert similarity.white_balance_distance("Auto", "Auto (white priority)") == similarity.WB_AUTO_PENALTY


class TestClosenessLabel:
    def test_very_close_at_the_top(self) -> None:
        assert similarity.closeness_label(0.97) == "Very close"
        assert similarity.closeness_label(0.90) == "Very close"

    def test_close_in_the_upper_band(self) -> None:
        assert similarity.closeness_label(0.89) == "Close"
        assert similarity.closeness_label(0.70) == "Close"

    def test_similar_in_the_middle(self) -> None:
        assert similarity.closeness_label(0.69) == "Similar"
        assert similarity.closeness_label(0.50) == "Similar"

    def test_loosely_related_at_the_bottom(self) -> None:
        assert similarity.closeness_label(0.49) == "Loosely related"
        assert similarity.closeness_label(0.10) == "Loosely related"


class TestComputeSimilarity:
    def test_identical_recipes_score_one(self) -> None:
        recipe = _recipe(**_PORTRA_V2)
        assert similarity.compute_similarity(a=recipe, b=recipe) == pytest.approx(1.0)

    def test_is_symmetric(self) -> None:
        a = _recipe(**_PORTRA_V2)
        b = _recipe(**_TRI_X)
        assert similarity.compute_similarity(a=a, b=b) == pytest.approx(similarity.compute_similarity(a=b, b=a))

    def test_close_portra_pair_matches_adr(self) -> None:
        a = _recipe(**_PORTRA_V2)
        b = _recipe(**_PORTRA_V3)
        assert similarity.compute_similarity(a=a, b=b) == pytest.approx(0.968, abs=1e-3)

    def test_distant_colour_versus_black_and_white_matches_adr(self) -> None:
        a = _recipe(**_PORTRA_V2)
        b = _recipe(**_TRI_X)
        assert similarity.compute_similarity(a=a, b=b) == pytest.approx(0.348, abs=1e-3)

    def test_close_pair_scores_higher_than_distant_pair(self) -> None:
        v2 = _recipe(**_PORTRA_V2)
        v3 = _recipe(**_PORTRA_V3)
        tri_x = _recipe(**_TRI_X)
        assert similarity.compute_similarity(a=v2, b=v3) > similarity.compute_similarity(a=v2, b=tri_x)

    def test_score_is_within_unit_range(self) -> None:
        a = _recipe(**_PORTRA_V2)
        b = _recipe(**_TRI_X)
        score = similarity.compute_similarity(a=a, b=b)
        assert 0.0 <= score <= 1.0

    def test_two_black_and_white_recipes_compare_toning_not_saturation(self) -> None:
        # Both B&W: differ only in warm/cool toning; should stay very similar.
        a = _recipe(film_simulation="Acros STD", monochromatic_color_warm_cool=Decimal("0.0"), monochromatic_color_magenta_green=Decimal("0.0"))
        b = _recipe(film_simulation="Acros STD", monochromatic_color_warm_cool=Decimal("2.0"), monochromatic_color_magenta_green=Decimal("0.0"))
        assert similarity.compute_similarity(a=a, b=b) > 0.98
