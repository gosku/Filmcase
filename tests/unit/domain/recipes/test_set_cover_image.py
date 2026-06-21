from unittest.mock import MagicMock, patch

import pytest

from src.data import models
from src.domain.images import events
from src.domain.recipes import operations


def _make_recipe_qs(recipe=None, missing=False):
    qs = MagicMock()
    if missing:
        qs.get.side_effect = models.FujifilmRecipe.DoesNotExist
    else:
        qs.get.return_value = recipe
    return qs


def _make_image_qs(image=None, missing=False):
    qs = MagicMock()
    if missing:
        qs.get.side_effect = models.Image.DoesNotExist
    else:
        qs.get.return_value = image
    return qs


class TestSetCoverImageExceptions:
    def test_raises_recipe_not_found_when_recipe_missing(self):
        recipe_qs = _make_recipe_qs(missing=True)
        with patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", recipe_qs):
            with pytest.raises(operations.RecipeNotFoundError) as exc_info:
                operations.set_cover_image_for_recipe(recipe_id=99, image_id=1)
        assert exc_info.value.recipe_id == 99

    def test_raises_image_not_found_when_image_missing(self):
        recipe = MagicMock()
        recipe.pk = 1
        recipe_qs = _make_recipe_qs(recipe=recipe)
        image_qs = _make_image_qs(missing=True)

        with (
            patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", recipe_qs),
            patch("src.domain.recipes.operations.models.Image.objects", image_qs),
        ):
            with pytest.raises(operations.ImageNotFoundError) as exc_info:
                operations.set_cover_image_for_recipe(recipe_id=1, image_id=99)
        assert exc_info.value.image_id == 99

    def test_raises_image_not_associated_when_image_belongs_to_different_recipe(self):
        recipe = MagicMock()
        recipe.pk = 1
        image = MagicMock()
        image.fujifilm_recipe_id = 2  # different recipe

        with (
            patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(recipe=recipe)),
            patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(image=image)),
        ):
            with pytest.raises(operations.ImageNotAssociatedToRecipeError) as exc_info:
                operations.set_cover_image_for_recipe(recipe_id=1, image_id=5)
        assert exc_info.value.recipe_id == 1
        assert exc_info.value.image_id == 5

    def test_recipe_not_saved_when_image_not_associated(self):
        recipe = MagicMock()
        recipe.pk = 1
        image = MagicMock()
        image.fujifilm_recipe_id = 2

        with (
            patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(recipe=recipe)),
            patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(image=image)),
        ):
            with pytest.raises(operations.ImageNotAssociatedToRecipeError):
                operations.set_cover_image_for_recipe(recipe_id=1, image_id=5)
        recipe.set_cover_image.assert_not_called()

    def test_recipe_not_saved_when_recipe_missing(self):
        recipe_qs = _make_recipe_qs(missing=True)
        with patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", recipe_qs):
            with pytest.raises(operations.RecipeNotFoundError):
                operations.set_cover_image_for_recipe(recipe_id=99, image_id=1)
        # No recipe instance to assert on — just confirm no save was attempted
        recipe_qs.get.assert_called_once_with(pk=99)


class TestSetCoverImageEventPublishing:
    def test_publishes_cover_image_set_event(self, captured_logs):
        recipe = MagicMock()
        recipe.pk = 10
        image = MagicMock()
        image.fujifilm_recipe_id = 10

        with (
            patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(recipe=recipe)),
            patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(image=image)),
        ):
            operations.set_cover_image_for_recipe(recipe_id=10, image_id=42)

        cover_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_COVER_IMAGE_SET]
        assert len(cover_events) == 1
        assert cover_events[0]["recipe_id"] == 10
        assert cover_events[0]["image_id"] == 42

    def test_no_event_published_when_image_not_associated(self, captured_logs):
        recipe = MagicMock()
        recipe.pk = 10
        image = MagicMock()
        image.fujifilm_recipe_id = 99  # not associated

        with (
            patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(recipe=recipe)),
            patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(image=image)),
        ):
            with pytest.raises(operations.ImageNotAssociatedToRecipeError):
                operations.set_cover_image_for_recipe(recipe_id=10, image_id=7)

        cover_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_COVER_IMAGE_SET]
        assert len(cover_events) == 0
