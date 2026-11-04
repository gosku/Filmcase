"""Unit tests for white-balance decoding in recipe_values.

white_balance_from_exif() is a pure function (no DB, no files), so the decode
rules are covered here directly rather than through the EXIF fixture pipeline,
which has no X-T5 ambience-priority or Custom fixtures.
"""

import pytest

from src.domain.images import dataclasses as image_dataclasses
from src.domain.images import queries, recipe_values
from src.domain.recipes import validation as recipe_validation


class TestWhiteBalanceFromExif:
    def test_known_mode_passes_through(self) -> None:
        result = recipe_values.white_balance_from_exif(
            white_balance="Daylight", color_temperature="5500"
        )

        assert result == "Daylight"

    def test_kelvin_mode_uses_colour_temperature(self) -> None:
        result = recipe_values.white_balance_from_exif(
            white_balance="Kelvin", color_temperature="5500"
        )

        assert result == "5500K"

    def test_ambience_priority_exiftool_spelling_normalises_to_sdk_spelling(self) -> None:
        # exiftool emits the "ambiance" spelling; it must be stored as the
        # codebase-canonical "ambience" so it matches the PTP push whitelist.
        result = recipe_values.white_balance_from_exif(
            white_balance="Auto (ambiance priority)", color_temperature="5500"
        )

        assert result == "Auto (ambience priority)"

    def test_auto_white_priority_passes_through(self) -> None:
        result = recipe_values.white_balance_from_exif(
            white_balance="Auto (white priority)", color_temperature="5500"
        )

        assert result == "Auto (white priority)"

    def test_measured_custom_mode_raises_invalid_white_balance(self) -> None:
        with pytest.raises(recipe_values.InvalidWhiteBalance):
            recipe_values.white_balance_from_exif(
                white_balance="Custom", color_temperature="5500"
            )

    def test_second_measured_custom_mode_raises_invalid_white_balance(self) -> None:
        with pytest.raises(recipe_values.InvalidWhiteBalance):
            recipe_values.white_balance_from_exif(
                white_balance="Custom2", color_temperature="5500"
            )

    def test_unknown_mode_raises_invalid_white_balance(self) -> None:
        with pytest.raises(recipe_values.InvalidWhiteBalance):
            recipe_values.white_balance_from_exif(
                white_balance="Some Future Mode", color_temperature="5500"
            )

    def test_raised_error_carries_field_and_offending_value(self) -> None:
        with pytest.raises(recipe_values.InvalidWhiteBalance) as exc_info:
            recipe_values.white_balance_from_exif(
                white_balance="Custom2", color_temperature="5500"
            )

        assert exc_info.value.field == "white_balance"
        assert exc_info.value.value == "Custom2"


class TestInvalidWhiteBalance:
    def test_is_a_sibling_not_a_subclass_of_invalid_recipe_data(self) -> None:
        # Deliberately NOT a subclass: like NoFilmSimulationError, it is handled
        # by an explicit except clause at each import entry point rather than
        # being swept up implicitly by the generic InvalidFujifilmRecipeData
        # handler. Keep it a sibling so that implicit handling cannot creep back.
        assert not issubclass(
            recipe_values.InvalidWhiteBalance,
            recipe_validation.InvalidFujifilmRecipeData,
        )

    def test_reports_the_white_balance_field(self) -> None:
        assert recipe_values.InvalidWhiteBalance("Custom").field == "white_balance"


class TestExifToRecipeWhiteBalance:
    def test_unmappable_white_balance_raises_through_the_decode_pipeline(self) -> None:
        # Prove the error propagates from the real call site in exif_to_recipe,
        # not just the isolated helper. Minimal valid EXIF: a known film
        # simulation so decoding reaches the white-balance field.
        exif = image_dataclasses.ImageExifData(
            camera_make="FUJIFILM",
            camera_model="X-T5",
            film_simulation="F0/Standard (Provia)",
            white_balance="Custom",
        )

        with pytest.raises(recipe_values.InvalidWhiteBalance):
            queries.exif_to_recipe(exif=exif)
