import pytest

from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.images import events
from src.domain.recipes.dataclasses import RecipeImportOutcome
from src.domain.recipes.operations import (
    get_or_create_recipe_and_backfill_name,
    get_or_create_recipe_from_data,
)


def _make_data(**overrides: object) -> image_dataclasses.FujifilmRecipeData:
    base = dict(
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
    return image_dataclasses.FujifilmRecipeData(**base)  # type: ignore[arg-type]  # test helper merges typed defaults with arbitrary overrides via dict


@pytest.mark.django_db
class TestGetOrCreateRecipeAndBackfillName:
    def test_creates_the_recipe_when_the_library_has_no_match(self) -> None:
        recipe, outcome = get_or_create_recipe_and_backfill_name(data=_make_data(name="Kodachrome"))

        assert recipe.name == "Kodachrome"
        assert outcome is RecipeImportOutcome.CREATED

    def test_backfills_the_name_of_a_matching_recipe_that_has_none(self) -> None:
        existing, _ = get_or_create_recipe_from_data(data=_make_data(name=""))

        recipe, outcome = get_or_create_recipe_and_backfill_name(data=_make_data(name="Kodachrome"))

        assert recipe.pk == existing.pk
        assert outcome is RecipeImportOutcome.NAME_BACKFILLED
        existing.refresh_from_db()
        assert existing.name == "Kodachrome"
        assert models.FujifilmRecipe.objects.count() == 1

    def test_keeps_a_name_already_chosen_locally(self) -> None:
        existing, _ = get_or_create_recipe_from_data(data=_make_data(name="My Chrome"))

        recipe, outcome = get_or_create_recipe_and_backfill_name(data=_make_data(name="Kodachrome"))

        assert recipe.pk == existing.pk
        assert outcome is RecipeImportOutcome.UNCHANGED
        existing.refresh_from_db()
        assert existing.name == "My Chrome"

    def test_leaves_an_unnamed_recipe_unnamed_when_the_incoming_data_has_no_name(self) -> None:
        existing, _ = get_or_create_recipe_from_data(data=_make_data(name=""))

        recipe, outcome = get_or_create_recipe_and_backfill_name(data=_make_data(name=""))

        assert recipe.pk == existing.pk
        assert outcome is RecipeImportOutcome.UNCHANGED
        assert recipe.name == ""

    def test_never_writes_the_description(self) -> None:
        existing, _ = get_or_create_recipe_from_data(data=_make_data(name="", description=""))

        get_or_create_recipe_and_backfill_name(
            data=_make_data(name="Kodachrome", description="Notes from the other library")
        )

        existing.refresh_from_db()
        assert existing.description == ""

    def test_publishes_the_name_updated_event_when_it_backfills(
        self, captured_logs: list[dict[str, object]]
    ) -> None:
        existing, _ = get_or_create_recipe_from_data(data=_make_data(name=""))
        captured_logs.clear()

        get_or_create_recipe_and_backfill_name(data=_make_data(name="Kodachrome"))

        name_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_NAME_UPDATED]
        assert len(name_events) == 1
        assert name_events[0]["recipe_id"] == existing.pk
        assert name_events[0]["name"] == "Kodachrome"

    def test_publishes_no_name_updated_event_when_nothing_is_backfilled(
        self, captured_logs: list[dict[str, object]]
    ) -> None:
        get_or_create_recipe_from_data(data=_make_data(name="My Chrome"))
        captured_logs.clear()

        get_or_create_recipe_and_backfill_name(data=_make_data(name="Kodachrome"))

        assert not [e for e in captured_logs if e.get("event_type") == events.RECIPE_NAME_UPDATED]


@pytest.mark.django_db
class TestGetOrCreateRecipeAndBackfillNameWithSensors:
    """
    The case this exists for: recipes shared from a newer library into an
    older one, where the local copies predate both sensor tracking and being
    named. Each card must find its local recipe and complete it, not duplicate it.
    """

    def test_backfills_name_and_sensors_of_a_sensorless_local_recipe(self) -> None:
        local, _ = get_or_create_recipe_from_data(
            data=_make_data(name="", sensors=(), white_balance_red=9001)
        )
        assert local.sensor_signature == ""

        recipe, outcome = get_or_create_recipe_and_backfill_name(
            data=_make_data(name="Kodachrome", sensors=("X-Trans V",), white_balance_red=9001)
        )

        assert recipe.pk == local.pk
        assert outcome is RecipeImportOutcome.NAME_BACKFILLED
        assert models.FujifilmRecipe.objects.count() == 1
        local.refresh_from_db()
        assert local.name == "Kodachrome"
        assert [s.name for s in local.sensors.all()] == ["X-Trans V"]
        assert local.sensor_signature == "x-trans v"

    def test_creates_a_separate_recipe_for_a_different_sensor_set(self) -> None:
        # Two cards with identical settings but different sensors are two
        # recipes. The first claims the sensorless local recipe; the second
        # can no longer match it and is created.
        get_or_create_recipe_from_data(data=_make_data(name="", sensors=(), white_balance_red=9002))

        first, first_outcome = get_or_create_recipe_and_backfill_name(
            data=_make_data(name="Chrome IV", sensors=("X-Trans IV",), white_balance_red=9002)
        )
        second, second_outcome = get_or_create_recipe_and_backfill_name(
            data=_make_data(name="Chrome V", sensors=("X-Trans V",), white_balance_red=9002)
        )

        assert first_outcome is RecipeImportOutcome.NAME_BACKFILLED
        assert second_outcome is RecipeImportOutcome.CREATED
        assert first.pk != second.pk
        assert models.FujifilmRecipe.objects.count() == 2
