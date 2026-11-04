"""Unit tests for white-balance decoding in recipe_values.

white_balance_from_exif() is a pure function (no DB, no files), so the decode
rules are covered here directly rather than through the EXIF fixture pipeline,
which has no X-T5 ambience-priority or Custom fixtures.
"""

import pytest

from src.domain.images import recipe_values


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
