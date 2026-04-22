from src.domain.recipes.cards import dataclasses as card_dataclasses
from src.domain.recipes.cards import queries as card_queries


def _valid_qr(**overrides: object) -> card_dataclasses.QRFujifilmRecipe:
    """Build a QRFujifilmRecipe with minimal required fields, overridable via kwargs."""
    defaults: dict[str, object] = {
        "v": 1,
        "film_simulation": "Provia",
        "grain_roughness": "Off",
        "d_range_priority": "Off",
        "white_balance": "Auto",
        "white_balance_red": 0,
        "white_balance_blue": 0,
    }
    defaults.update(overrides)
    return card_dataclasses.QRFujifilmRecipe(**defaults)  # type: ignore[arg-type]


class TestGetRecipeDataFromQRRecipe:
    def test_passes_through_required_string_and_int_fields(self) -> None:
        qr = _valid_qr(
            film_simulation="Classic Chrome",
            grain_roughness="Weak",
            d_range_priority="Auto",
            white_balance="Daylight",
            white_balance_red=2,
            white_balance_blue=-1,
        )

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr)

        assert result.film_simulation == "Classic Chrome"
        assert result.grain_roughness == "Weak"
        assert result.d_range_priority == "Auto"
        assert result.white_balance == "Daylight"
        assert result.white_balance_red == 2
        assert result.white_balance_blue == -1

    def test_formats_decimal_zero_as_unsigned_string(self) -> None:
        qr = _valid_qr(highlight=0, shadow=0, color=0, sharpness=0, high_iso_nr=0, clarity=0)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr)

        assert result.highlight == "0"
        assert result.shadow == "0"
        assert result.color == "0"
        assert result.sharpness == "0"
        assert result.high_iso_nr == "0"
        assert result.clarity == "0"

    def test_formats_positive_decimal_with_plus_sign(self) -> None:
        qr = _valid_qr(highlight=2, sharpness=1)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr)

        assert result.highlight == "+2"
        assert result.sharpness == "+1"

    def test_formats_negative_decimal_without_extra_plus(self) -> None:
        qr = _valid_qr(shadow=-1, high_iso_nr=-4)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr)

        assert result.shadow == "-1"
        assert result.high_iso_nr == "-4"

    def test_formats_half_step_decimals_as_signed_floats(self) -> None:
        qr = _valid_qr(
            highlight=1.5,
            shadow=-1.5,
            monochromatic_color_warm_cool=-2.5,
            monochromatic_color_magenta_green=0.5,
        )

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr)

        assert result.highlight == "+1.5"
        assert result.shadow == "-1.5"
        assert result.monochromatic_color_warm_cool == "-2.5"
        assert result.monochromatic_color_magenta_green == "+0.5"

    def test_passes_through_none_for_omitted_optional_decimal(self) -> None:
        qr = _valid_qr()  # highlight, shadow, color, etc. default to None

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr)

        assert result.highlight is None
        assert result.shadow is None
        assert result.color is None
        assert result.monochromatic_color_warm_cool is None
        assert result.monochromatic_color_magenta_green is None

    def test_defaults_grain_size_to_off_when_absent_and_grain_roughness_is_off(self) -> None:
        qr = _valid_qr(grain_roughness="Off", grain_size=None)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr)

        assert result.grain_size == "Off"

    def test_preserves_grain_size_when_present(self) -> None:
        qr = _valid_qr(grain_roughness="Weak", grain_size="Small")

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr)

        assert result.grain_size == "Small"

    def test_defaults_colour_chrome_fields_to_empty_when_absent(self) -> None:
        # These are omitted for monochromatic film simulations.
        qr = _valid_qr(
            film_simulation="Acros STD",
            color_chrome_effect=None,
            color_chrome_fx_blue=None,
        )

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr)

        assert result.color_chrome_effect == ""
        assert result.color_chrome_fx_blue == ""

    def test_preserves_colour_chrome_fields_when_present(self) -> None:
        qr = _valid_qr(color_chrome_effect="Strong", color_chrome_fx_blue="Weak")

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr)

        assert result.color_chrome_effect == "Strong"
        assert result.color_chrome_fx_blue == "Weak"

    def test_defaults_name_to_empty_when_payload_omits_it(self) -> None:
        qr = _valid_qr()  # name defaults to None on QRFujifilmRecipe

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr)

        assert result.name == ""

    def test_passes_name_through_when_payload_includes_it(self) -> None:
        qr = _valid_qr(name="My Summer Recipe")

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr)

        assert result.name == "My Summer Recipe"
