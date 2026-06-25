import pytest

from src.data import models


def _settings(**overrides: object) -> dict[str, object]:
    """Return a minimal valid argument bundle for FujifilmRecipe.get_or_create."""
    base: dict[str, object] = dict(
        film_simulation="Provia",
        dynamic_range="DR100",
        d_range_priority="Off",
        grain_roughness="Off",
        grain_size="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Auto",
        white_balance_red=0,
        white_balance_blue=0,
        highlight=0,
        shadow=0,
        color=0,
        sharpness=0,
        high_iso_nr=0,
        clarity=0,
        monochromatic_color_warm_cool=None,
        monochromatic_color_magenta_green=None,
    )
    base.update(overrides)
    return base


@pytest.mark.django_db
class TestFujifilmRecipeGetOrCreateSensorSignature:
    def test_same_settings_same_signature_dedups(self):
        a, created_a = models.FujifilmRecipe.get_or_create(
            **_settings(white_balance_red=9101), sensor_signature="x-trans iv"
        )

        b, created_b = models.FujifilmRecipe.get_or_create(
            **_settings(white_balance_red=9101), sensor_signature="x-trans iv"
        )

        assert created_a and not created_b
        assert a.pk == b.pk

    def test_same_settings_different_signature_yields_two_rows(self):
        a, created_a = models.FujifilmRecipe.get_or_create(
            **_settings(white_balance_red=9102), sensor_signature="x-trans iv"
        )

        b, created_b = models.FujifilmRecipe.get_or_create(
            **_settings(white_balance_red=9102), sensor_signature="x-trans v"
        )

        assert created_a and created_b
        assert a.pk != b.pk

    def test_empty_signature_preserves_legacy_dedup(self):
        # Before sensor_signature existed, identical-settings rows collided.
        # Two calls that both leave sensor_signature unset must still dedup.
        a, created_a = models.FujifilmRecipe.get_or_create(
            **_settings(white_balance_red=9103)
        )

        b, created_b = models.FujifilmRecipe.get_or_create(
            **_settings(white_balance_red=9103)
        )

        assert created_a and not created_b
        assert a.pk == b.pk

    def test_signature_is_written_on_create(self):
        recipe, _ = models.FujifilmRecipe.get_or_create(
            **_settings(white_balance_red=9104), sensor_signature="gfx,x-trans iv"
        )

        recipe.refresh_from_db()
        assert recipe.sensor_signature == "gfx,x-trans iv"


@pytest.mark.django_db
class TestFujifilmRecipeGetOrCreateDescription:
    def test_description_written_on_create(self):
        recipe, _ = models.FujifilmRecipe.get_or_create(
            **_settings(white_balance_red=9105),
            description="Some notes about this recipe.",
        )

        recipe.refresh_from_db()
        assert recipe.description == "Some notes about this recipe."

    def test_description_not_overwritten_on_get(self):
        # description is in defaults={}, so a subsequent get_or_create with a
        # different description must not touch the stored value.
        original, _ = models.FujifilmRecipe.get_or_create(
            **_settings(white_balance_red=9106), description="Original notes"
        )

        same, created = models.FujifilmRecipe.get_or_create(
            **_settings(white_balance_red=9106), description="New notes"
        )

        assert not created and same.pk == original.pk
        original.refresh_from_db()
        assert original.description == "Original notes"

    def test_description_defaults_to_empty_string(self):
        recipe, _ = models.FujifilmRecipe.get_or_create(
            **_settings(white_balance_red=9107)
        )

        recipe.refresh_from_db()
        assert recipe.description == ""
