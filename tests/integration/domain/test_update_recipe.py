from __future__ import annotations

from decimal import Decimal

import pytest

from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.images import events
from src.domain.recipes import operations
from tests.factories import FujifilmRecipeFactory, ImageFactory


def _make_data(**overrides: object) -> image_dataclasses.FujifilmRecipeData:
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
        name="Updated",
    )
    base.update(overrides)
    return image_dataclasses.FujifilmRecipeData(**base)


@pytest.mark.django_db
class TestUpdateRecipePersistence:
    def test_updates_film_simulation_in_db(self) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        operations.update_recipe(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        recipe.refresh_from_db()
        assert recipe.film_simulation == "Velvia"

    def test_updates_numeric_fields_in_db(self) -> None:
        recipe = FujifilmRecipeFactory()
        operations.update_recipe(recipe=recipe, data=_make_data(sharpness="+2", high_iso_nr="-1", clarity="+3"))
        recipe.refresh_from_db()
        assert recipe.sharpness == Decimal("2")
        assert recipe.high_iso_nr == Decimal("-1")
        assert recipe.clarity == Decimal("3")

    def test_updates_name_when_data_name_is_non_empty(self) -> None:
        recipe = FujifilmRecipeFactory(name="Old Name")
        operations.update_recipe(recipe=recipe, data=_make_data(name="New Name"))
        recipe.refresh_from_db()
        assert recipe.name == "New Name"

    def test_does_not_overwrite_name_when_data_name_is_empty(self) -> None:
        recipe = FujifilmRecipeFactory(name="Kept Name")
        operations.update_recipe(recipe=recipe, data=_make_data(name=""))
        recipe.refresh_from_db()
        assert recipe.name == "Kept Name"

    def test_recipe_row_count_unchanged_after_update(self) -> None:
        recipe = FujifilmRecipeFactory()
        count_before = models.FujifilmRecipe.objects.count()
        operations.update_recipe(recipe=recipe, data=_make_data())
        assert models.FujifilmRecipe.objects.count() == count_before


@pytest.mark.django_db
class TestUpdateRecipeSettingsConflict:
    def test_raises_settings_conflict_when_new_settings_match_existing_recipe(self) -> None:
        existing, _ = operations.get_or_create_recipe_from_data(data=_make_data(film_simulation="Velvia"))
        recipe = FujifilmRecipeFactory(white_balance_red=99)
        with pytest.raises(operations.RecipeSettingsConflictError) as exc_info:
            operations.update_recipe(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        assert exc_info.value.recipe_id == recipe.pk

    def test_recipe_not_saved_when_settings_conflict(self) -> None:
        operations.get_or_create_recipe_from_data(data=_make_data(film_simulation="Velvia"))
        recipe = FujifilmRecipeFactory(film_simulation="Provia", white_balance_red=99)
        with pytest.raises(operations.RecipeSettingsConflictError):
            operations.update_recipe(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        recipe.refresh_from_db()
        assert recipe.film_simulation == "Provia"


@pytest.mark.django_db
class TestUpdateRecipeGuards:
    def test_raises_recipe_cannot_be_edited_when_recipe_has_images(self) -> None:
        recipe = FujifilmRecipeFactory(name="My Recipe")
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeCannotBeEditedError) as exc_info:
            operations.update_recipe(recipe=recipe, data=_make_data())
        assert exc_info.value.recipe_id == recipe.pk
        assert exc_info.value.image_count == 1
        assert exc_info.value.name == "My Recipe"

    def test_recipe_cannot_be_edited_error_reflects_actual_image_count(self) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeCannotBeEditedError) as exc_info:
            operations.update_recipe(recipe=recipe, data=_make_data())
        assert exc_info.value.image_count == 2

    def test_fields_not_updated_when_recipe_has_images(self) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeCannotBeEditedError):
            operations.update_recipe(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        recipe.refresh_from_db()
        assert recipe.film_simulation == "Provia"


@pytest.mark.django_db
class TestUpdateRecipeEventPublishing:
    def test_publishes_recipe_updated_event(self, captured_logs: list[dict]) -> None:
        recipe = FujifilmRecipeFactory()
        operations.update_recipe(recipe=recipe, data=_make_data())
        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_UPDATED]
        assert len(updated_events) == 1
        assert updated_events[0]["recipe_id"] == recipe.pk

    def test_no_event_when_recipe_has_images(self, captured_logs: list[dict]) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeCannotBeEditedError):
            operations.update_recipe(recipe=recipe, data=_make_data())
        updated_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_UPDATED]
        assert len(updated_events) == 0
