from decimal import Decimal

import pytest

from src.data import models
from src.domain.recipes.queries import recipe_from_db
from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestRecipeFromDbSensors:
    def test_recipe_with_no_sensors_returns_empty_tuple(self):
        recipe = FujifilmRecipeFactory()

        data = recipe_from_db(recipe=recipe)

        assert data.sensors == ()

    def test_recipe_with_single_sensor_returns_it(self):
        recipe = FujifilmRecipeFactory()
        recipe.set_sensors(sensors=models.Sensor.objects.filter(name="X-Trans IV"))

        data = recipe_from_db(recipe=recipe)

        assert data.sensors == ("X-Trans IV",)

    def test_recipe_with_multiple_sensors_returns_sorted_tuple(self):
        recipe = FujifilmRecipeFactory()
        recipe.set_sensors(
            sensors=models.Sensor.objects.filter(name__in=["X-Trans V", "GFX", "X-Trans IV"])
        )

        data = recipe_from_db(recipe=recipe)

        # Sorted alphabetically so the returned order is stable regardless of
        # the underlying queryset iteration order.
        assert data.sensors == ("GFX", "X-Trans IV", "X-Trans V")


@pytest.mark.django_db
class TestRecipeFromDbDescription:
    def test_recipe_with_no_description_returns_empty_string(self):
        recipe = FujifilmRecipeFactory()

        data = recipe_from_db(recipe=recipe)

        assert data.description == ""

    def test_recipe_description_round_trips_verbatim(self):
        recipe = FujifilmRecipeFactory()
        recipe.set_description(description="Some recipe notes here.")

        data = recipe_from_db(recipe=recipe)

        assert data.description == "Some recipe notes here."


@pytest.mark.django_db
class TestRecipeFromDbNormalization:
    """recipe_from_db() applies normalize_recipe_data() — inapplicable fields are None."""

    def test_nulls_color_for_mono_sim(self) -> None:
        db_recipe = FujifilmRecipeFactory(
            film_simulation="Acros STD",
            color=Decimal("2"),
            sharpness=Decimal("0"),
            high_iso_nr=Decimal("0"),
            clarity=Decimal("0"),
        )
        result = recipe_from_db(recipe=db_recipe)
        assert result.color is None

    def test_nulls_mono_fields_for_colour_sim(self) -> None:
        db_recipe = FujifilmRecipeFactory(
            film_simulation="Provia",
            monochromatic_color_warm_cool=Decimal("2"),
            monochromatic_color_magenta_green=Decimal("-1"),
            sharpness=Decimal("0"),
            high_iso_nr=Decimal("0"),
            clarity=Decimal("0"),
        )
        result = recipe_from_db(recipe=db_recipe)
        assert result.monochromatic_color_warm_cool is None
        assert result.monochromatic_color_magenta_green is None

    def test_nulls_drp_fields_when_drp_active(self) -> None:
        db_recipe = FujifilmRecipeFactory(
            d_range_priority="Auto",
            dynamic_range="DR100",
            highlight=Decimal("1"),
            shadow=Decimal("-1"),
            sharpness=Decimal("0"),
            high_iso_nr=Decimal("0"),
            clarity=Decimal("0"),
        )
        result = recipe_from_db(recipe=db_recipe)
        assert result.dynamic_range is None
        assert result.highlight is None
        assert result.shadow is None
