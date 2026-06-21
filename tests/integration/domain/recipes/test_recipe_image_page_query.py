import pytest
from datetime import datetime, timezone

from src.data import models
from src.domain.images.queries import get_recipe_image_page
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestGetRecipeImagePageRaises:
    def test_raises_when_image_not_in_recipe(self):
        recipe = FujifilmRecipeFactory()
        other_recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=other_recipe)

        with pytest.raises(models.Image.DoesNotExist):
            get_recipe_image_page(recipe_id=recipe.pk, image_id=image.pk)

    def test_raises_when_recipe_has_no_images(self):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=None)

        with pytest.raises(models.Image.DoesNotExist):
            get_recipe_image_page(recipe_id=recipe.pk, image_id=image.pk)


@pytest.mark.django_db
class TestGetRecipeImagePageSingleImage:
    def test_returns_image_id(self):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        result = get_recipe_image_page(recipe_id=recipe.pk, image_id=image.pk)

        assert result.image_id == image.pk

    def test_prev_id_is_none_for_only_image(self):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        result = get_recipe_image_page(recipe_id=recipe.pk, image_id=image.pk)

        assert result.prev_id is None

    def test_next_id_is_none_for_only_image(self):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        result = get_recipe_image_page(recipe_id=recipe.pk, image_id=image.pk)

        assert result.next_id is None


@pytest.mark.django_db
class TestGetRecipeImagePageNavigation:
    def test_first_image_has_no_prev(self):
        recipe = FujifilmRecipeFactory()
        first = ImageFactory(
            fujifilm_recipe=recipe,
            rating=5,
            taken_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        ImageFactory(
            fujifilm_recipe=recipe,
            rating=1,
            taken_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )

        result = get_recipe_image_page(recipe_id=recipe.pk, image_id=first.pk)

        assert result.prev_id is None

    def test_first_image_has_correct_next(self):
        recipe = FujifilmRecipeFactory()
        first = ImageFactory(
            fujifilm_recipe=recipe,
            rating=5,
            taken_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        second = ImageFactory(
            fujifilm_recipe=recipe,
            rating=1,
            taken_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )

        result = get_recipe_image_page(recipe_id=recipe.pk, image_id=first.pk)

        assert result.next_id == second.pk

    def test_last_image_has_no_next(self):
        recipe = FujifilmRecipeFactory()
        ImageFactory(
            fujifilm_recipe=recipe,
            rating=5,
            taken_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        last = ImageFactory(
            fujifilm_recipe=recipe,
            rating=1,
            taken_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )

        result = get_recipe_image_page(recipe_id=recipe.pk, image_id=last.pk)

        assert result.next_id is None

    def test_last_image_has_correct_prev(self):
        recipe = FujifilmRecipeFactory()
        first = ImageFactory(
            fujifilm_recipe=recipe,
            rating=5,
            taken_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        last = ImageFactory(
            fujifilm_recipe=recipe,
            rating=1,
            taken_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )

        result = get_recipe_image_page(recipe_id=recipe.pk, image_id=last.pk)

        assert result.prev_id == first.pk

    def test_middle_image_has_both_prev_and_next(self):
        recipe = FujifilmRecipeFactory()
        first = ImageFactory(
            fujifilm_recipe=recipe,
            rating=5,
            taken_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        middle = ImageFactory(
            fujifilm_recipe=recipe,
            rating=3,
            taken_at=datetime(2023, 6, 1, tzinfo=timezone.utc),
        )
        last = ImageFactory(
            fujifilm_recipe=recipe,
            rating=1,
            taken_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )

        result = get_recipe_image_page(recipe_id=recipe.pk, image_id=middle.pk)

        assert result.prev_id == first.pk
        assert result.next_id == last.pk

    def test_ordering_respects_rating_then_taken_at(self):
        recipe = FujifilmRecipeFactory()
        high_rated_old = ImageFactory(
            fujifilm_recipe=recipe,
            rating=5,
            taken_at=datetime(2022, 1, 1, tzinfo=timezone.utc),
        )
        low_rated_new = ImageFactory(
            fujifilm_recipe=recipe,
            rating=1,
            taken_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

        result = get_recipe_image_page(recipe_id=recipe.pk, image_id=high_rated_old.pk)

        assert result.next_id == low_rated_new.pk
        assert result.prev_id is None
