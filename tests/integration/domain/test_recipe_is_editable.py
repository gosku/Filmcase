from __future__ import annotations

import pytest

from src.domain.recipes.queries import recipe_is_editable
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestRecipeIsEditable:
    def test_returns_true_when_recipe_has_no_images(self) -> None:
        recipe = FujifilmRecipeFactory()
        assert recipe_is_editable(recipe_id=recipe.pk) is True

    def test_returns_false_when_recipe_has_one_image(self) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        assert recipe_is_editable(recipe_id=recipe.pk) is False

    def test_returns_false_when_recipe_has_multiple_images(self) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory.create_batch(3, fujifilm_recipe=recipe)
        assert recipe_is_editable(recipe_id=recipe.pk) is False

    def test_images_on_other_recipes_do_not_affect_result(self) -> None:
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe_b)
        assert recipe_is_editable(recipe_id=recipe_a.pk) is True
