import pytest

from src.domain.images import dataclasses as image_dataclasses
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

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.film_simulation == "Classic Chrome"
        assert result.grain_roughness == "Weak"
        assert result.d_range_priority == "Auto"
        assert result.white_balance == "Daylight"
        assert result.white_balance_red == 2
        assert result.white_balance_blue == -1

    def test_formats_decimal_zero_as_unsigned_string(self) -> None:
        qr = _valid_qr(highlight=0, shadow=0, color=0, sharpness=0, high_iso_nr=0, clarity=0)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.highlight == "0"
        assert result.shadow == "0"
        assert result.color == "0"
        assert result.sharpness == "0"
        assert result.high_iso_nr == "0"
        assert result.clarity == "0"

    def test_formats_positive_decimal_with_plus_sign(self) -> None:
        qr = _valid_qr(highlight=2, sharpness=1)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.highlight == "+2"
        assert result.sharpness == "+1"

    def test_formats_negative_decimal_without_extra_plus(self) -> None:
        qr = _valid_qr(shadow=-1, high_iso_nr=-4)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.shadow == "-1"
        assert result.high_iso_nr == "-4"

    def test_formats_half_step_tone_decimals_as_signed_floats(self) -> None:
        qr = _valid_qr(highlight=1.5, shadow=-1.5)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.highlight == "+1.5"
        assert result.shadow == "-1.5"

    def test_formats_half_step_mono_color_decimals_as_signed_floats(self) -> None:
        qr = _valid_qr(
            film_simulation="Acros STD",
            monochromatic_color_warm_cool=-2.5,
            monochromatic_color_magenta_green=0.5,
        )

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.monochromatic_color_warm_cool == "-2.5"
        assert result.monochromatic_color_magenta_green == "+0.5"

    def test_defaults_absent_decimal_fields_to_zero_string(self) -> None:
        # For a non-mono sim with DRP off, absent decimal fields get "0" defaults.
        qr = _valid_qr()

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.highlight == "0"
        assert result.shadow == "0"
        assert result.color == "0"
        assert result.monochromatic_color_warm_cool is None
        assert result.monochromatic_color_magenta_green is None

    def test_defaults_grain_size_to_none_when_roughness_is_off(self) -> None:
        qr = _valid_qr(grain_roughness="Off", grain_size=None)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.grain_size is None

    def test_preserves_grain_size_when_present(self) -> None:
        qr = _valid_qr(grain_roughness="Weak", grain_size="Small")

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.grain_size == "Small"

    def test_defaults_colour_chrome_fields_to_off_when_absent(self) -> None:
        qr = _valid_qr(color_chrome_effect=None, color_chrome_fx_blue=None)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.color_chrome_effect == "Off"
        assert result.color_chrome_fx_blue == "Off"

    def test_preserves_colour_chrome_fields_when_present(self) -> None:
        qr = _valid_qr(color_chrome_effect="Strong", color_chrome_fx_blue="Weak")

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.color_chrome_effect == "Strong"
        assert result.color_chrome_fx_blue == "Weak"

    def test_defaults_name_to_empty_when_payload_omits_it(self) -> None:
        qr = _valid_qr()  # name defaults to None on QRFujifilmRecipe

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.name == ""

    def test_passes_name_through_when_payload_includes_it(self) -> None:
        qr = _valid_qr(name="My Summer Recipe")

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.name == "My Summer Recipe"

    def test_nulls_drp_fields_when_drp_is_active(self) -> None:
        qr = _valid_qr(d_range_priority="Auto", dynamic_range="DR100", highlight=1, shadow=-1)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.dynamic_range is None
        assert result.highlight is None
        assert result.shadow is None

    def test_nulls_mono_fields_for_colour_sim_when_present_in_qr(self) -> None:
        qr = _valid_qr(monochromatic_color_warm_cool=5.0, monochromatic_color_magenta_green=-3.0)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.monochromatic_color_warm_cool is None
        assert result.monochromatic_color_magenta_green is None


class TestGetRecipeDataFromQRRecipeSensors:
    """Sensor field round-trip through the v=2 schema."""

    def test_v1_payload_without_sensors_yields_empty_tuple(self) -> None:
        # The legacy v=1 schema didn't have a sensors field. Decoding it must
        # produce sensors=() (not None) so the FujifilmRecipeData validator
        # is satisfied.
        qr = _valid_qr(v=1)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.sensors == ()

    def test_v2_payload_with_sensors_round_trips(self) -> None:
        qr = _valid_qr(v=2, sensors=("X-Trans IV", "GFX"))

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.sensors == ("X-Trans IV", "GFX")

    def test_v2_payload_without_sensors_yields_empty_tuple(self) -> None:
        # sensors is optional even in v=2 (a nameless recipe with no sensors
        # produces a payload without the key); the converter normalises the
        # absent value to an empty tuple downstream.
        qr = _valid_qr(v=2)

        result = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert result.sensors == ()


class TestGetRecipeDataFromQRRecipeInvalidValues:
    """
    Values that are the right type but not legal.

    The payload type checks let these through, and the FujifilmRecipeData
    validators reject them with a plain ValueError. They must surface as
    InvalidQRRecipePayloadError so a caller importing a batch of cards can
    record the offending card as failed and carry on with the rest.
    """

    def test_raises_for_a_name_longer_than_the_maximum(self) -> None:
        qr = _valid_qr(name="x" * (image_dataclasses.RECIPE_NAME_MAX_LEN + 1))

        with pytest.raises(card_queries.InvalidQRRecipePayloadError) as exc_info:
            card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert exc_info.value.reason == "invalid_field_value"
        assert exc_info.value.image_path == "card.jpg"

    def test_raises_for_a_non_ascii_name(self) -> None:
        qr = _valid_qr(name="Velvia Añejo")

        with pytest.raises(card_queries.InvalidQRRecipePayloadError) as exc_info:
            card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert exc_info.value.reason == "invalid_field_value"

    def test_raises_for_an_unknown_sensor_name(self) -> None:
        # A card exported by a deployment that knows a sensor this one doesn't.
        qr = _valid_qr(v=2, sensors=("X-Trans VI",))

        with pytest.raises(card_queries.InvalidQRRecipePayloadError) as exc_info:
            card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr, image_path="card.jpg")

        assert exc_info.value.reason == "invalid_field_value"
