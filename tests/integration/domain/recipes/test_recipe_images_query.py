import pytest
from datetime import datetime, timezone

from src.domain.images.queries import get_images_for_recipe
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestGetImagesForRecipeEmpty:
    def test_returns_empty_list_when_recipe_has_no_images(self):
        recipe = FujifilmRecipeFactory()

        result = get_images_for_recipe(recipe_id=recipe.pk)

        assert result == []

    def test_returns_empty_list_for_nonexistent_recipe(self):
        result = get_images_for_recipe(recipe_id=99999)

        assert result == []


@pytest.mark.django_db
class TestGetImagesForRecipeFiltering:
    def test_returns_ids_for_images_in_recipe(self):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        result = get_images_for_recipe(recipe_id=recipe.pk)

        assert image.pk in result

    def test_excludes_images_from_other_recipes(self):
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        image_a = ImageFactory(fujifilm_recipe=recipe_a)
        ImageFactory(fujifilm_recipe=recipe_b)

        result = get_images_for_recipe(recipe_id=recipe_a.pk)

        assert result == [image_a.pk]

    def test_excludes_images_without_recipe(self):
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=None)
        image_with_recipe = ImageFactory(fujifilm_recipe=recipe)

        result = get_images_for_recipe(recipe_id=recipe.pk)

        assert result == [image_with_recipe.pk]


@pytest.mark.django_db
class TestGetImagesForRecipeOrdering:
    def test_higher_rated_image_comes_first(self):
        recipe = FujifilmRecipeFactory()
        low = ImageFactory(fujifilm_recipe=recipe, rating=1)
        high = ImageFactory(fujifilm_recipe=recipe, rating=5)

        result = get_images_for_recipe(recipe_id=recipe.pk)

        assert result.index(high.pk) < result.index(low.pk)

    def test_same_rating_orders_by_taken_at_desc(self):
        recipe = FujifilmRecipeFactory()
        older = ImageFactory(
            fujifilm_recipe=recipe,
            rating=3,
            taken_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )
        newer = ImageFactory(
            fujifilm_recipe=recipe,
            rating=3,
            taken_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        result = get_images_for_recipe(recipe_id=recipe.pk)

        assert result.index(newer.pk) < result.index(older.pk)

    def test_rating_beats_taken_at(self):
        recipe = FujifilmRecipeFactory()
        older_high_rated = ImageFactory(
            fujifilm_recipe=recipe,
            rating=5,
            taken_at=datetime(2022, 1, 1, tzinfo=timezone.utc),
        )
        newer_low_rated = ImageFactory(
            fujifilm_recipe=recipe,
            rating=1,
            taken_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        result = get_images_for_recipe(recipe_id=recipe.pk)

        assert result.index(older_high_rated.pk) < result.index(newer_low_rated.pk)

    def test_returns_list_of_ints(self):
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)

        result = get_images_for_recipe(recipe_id=recipe.pk)

        assert all(isinstance(pk, int) for pk in result)
