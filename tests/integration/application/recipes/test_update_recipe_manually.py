from __future__ import annotations

import pytest

from src.application.usecases.recipes import update_recipe_manually as uc
from src.data import models
from src.domain.images import dataclasses as image_dataclasses
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
class TestUpdateRecipeManuallyPersistence:
    def test_updates_recipe_fields_in_db(self) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        uc.update_recipe_manually(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        recipe.refresh_from_db()
        assert recipe.film_simulation == "Velvia"

    def test_returns_updated_recipe(self) -> None:
        recipe = FujifilmRecipeFactory()
        result = uc.update_recipe_manually(recipe=recipe, data=_make_data())
        assert result.pk == recipe.pk

    def test_row_count_unchanged_after_update(self) -> None:
        recipe = FujifilmRecipeFactory()
        count_before = models.FujifilmRecipe.objects.count()
        uc.update_recipe_manually(recipe=recipe, data=_make_data())
        assert models.FujifilmRecipe.objects.count() == count_before


@pytest.mark.django_db
class TestUpdateRecipeManuallySettingsConflict:
    def test_raises_already_exists_when_settings_match_existing_recipe(self) -> None:
        from src.domain.recipes import operations as recipe_operations
        recipe_operations.get_or_create_recipe_from_data(data=_make_data(film_simulation="Velvia"))
        recipe = FujifilmRecipeFactory(white_balance_red=99)
        with pytest.raises(uc.RecipeAlreadyExistsError) as exc_info:
            uc.update_recipe_manually(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        assert exc_info.value.recipe_id == recipe.pk

    def test_recipe_not_changed_when_settings_conflict(self) -> None:
        from src.domain.recipes import operations as recipe_operations
        recipe_operations.get_or_create_recipe_from_data(data=_make_data(film_simulation="Velvia"))
        recipe = FujifilmRecipeFactory(film_simulation="Provia", white_balance_red=99)
        with pytest.raises(uc.RecipeAlreadyExistsError):
            uc.update_recipe_manually(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        recipe.refresh_from_db()
        assert recipe.film_simulation == "Provia"


@pytest.mark.django_db
class TestUpdateRecipeManuallyGuards:
    def test_raises_cannot_be_edited_when_settings_change_and_recipe_has_images(self) -> None:
        recipe = FujifilmRecipeFactory(name="Has Images")
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(uc.RecipeCannotBeEditedError) as exc_info:
            uc.update_recipe_manually(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        assert exc_info.value.recipe_id == recipe.pk
        assert exc_info.value.image_count == 1
        assert exc_info.value.name == "Has Images"

    def test_recipe_not_changed_when_settings_change_and_has_images(self) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(uc.RecipeCannotBeEditedError):
            uc.update_recipe_manually(recipe=recipe, data=_make_data(film_simulation="Velvia"))
        recipe.refresh_from_db()
        assert recipe.film_simulation == "Provia"

    def test_updates_name_when_only_name_changes_and_recipe_has_images(self) -> None:
        from src.domain.recipes import queries as recipe_queries
        import attrs
        recipe = FujifilmRecipeFactory(name="Old Name")
        ImageFactory(fujifilm_recipe=recipe)
        current = recipe_queries.recipe_from_db(recipe=recipe)
        data = attrs.evolve(current, name="New Name")
        uc.update_recipe_manually(recipe=recipe, data=data)
        recipe.refresh_from_db()
        assert recipe.name == "New Name"
