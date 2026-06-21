"""Unit tests for the attrs-level validators on FujifilmRecipeData."""

import pytest

from src.domain.images.dataclasses import FujifilmRecipeData


def _minimal_fields(**overrides: object) -> dict[str, object]:
    """Return the minimal set of required fields for a valid recipe data instance."""
    base: dict[str, object] = dict(
        film_simulation="Provia",
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
        highlight="0",
        shadow="0",
        color="0",
    )
    base.update(overrides)
    return base


class TestFujifilmRecipeDataSensorsValidator:
    def test_empty_tuple_is_valid(self):
        data = FujifilmRecipeData(**_minimal_fields(), sensors=())

        assert data.sensors == ()

    def test_single_known_sensor_is_valid(self):
        data = FujifilmRecipeData(**_minimal_fields(), sensors=("X-Trans IV",))

        assert data.sensors == ("X-Trans IV",)

    def test_multiple_known_sensors_are_valid(self):
        data = FujifilmRecipeData(
            **_minimal_fields(), sensors=("X-Trans IV", "GFX", "X-Trans V")
        )

        assert data.sensors == ("X-Trans IV", "GFX", "X-Trans V")

    def test_unknown_sensor_name_raises(self):
        with pytest.raises(ValueError, match="Unknown sensor name 'Imaginary'"):
            FujifilmRecipeData(**_minimal_fields(), sensors=("Imaginary",))

    def test_mixed_known_and_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown sensor name 'Definitely Not'"):
            FujifilmRecipeData(
                **_minimal_fields(), sensors=("X-Trans IV", "Definitely Not")
            )

    def test_validator_is_case_sensitive(self):
        # SENSOR_NAMES values are the canonical display strings ("X-Trans IV",
        # etc.) and the dataclass refuses lower-cased variants. Signature
        # canonicalisation is the *signature*'s job, not the validator's.
        with pytest.raises(ValueError, match="Unknown sensor name 'x-trans iv'"):
            FujifilmRecipeData(**_minimal_fields(), sensors=("x-trans iv",))


class TestFujifilmRecipeDataDescription:
    def test_defaults_to_empty_string(self):
        data = FujifilmRecipeData(**_minimal_fields())

        assert data.description == ""

    def test_accepts_any_string(self):
        long_text = "x" * 5000

        data = FujifilmRecipeData(**_minimal_fields(), description=long_text)

        assert data.description == long_text


class TestFujifilmRecipeDataDefaults:
    def test_omitting_new_fields_does_not_break_existing_callers(self):
        # Callers that don't know about `sensors` or `description` get the
        # defaults, so existing construction paths (EXIF importer, QR card
        # importer, form handler) continue to work unchanged until they're
        # explicitly updated to populate the new fields.
        data = FujifilmRecipeData(**_minimal_fields(), name="Some Name")

        assert data.sensors == ()
        assert data.description == ""
        assert data.name == "Some Name"
