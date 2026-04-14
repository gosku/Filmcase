import pytest

from src.domain.images import events
from src.domain.recipes import operations
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestSetCoverImagePersistence:
    def test_sets_cover_image_on_recipe(self):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        operations.set_cover_image_for_recipe(recipe_id=recipe.pk, image_id=image.pk)

        recipe.refresh_from_db()
        assert recipe.cover_image_id == image.pk

    def test_only_updates_cover_image_field(self):
        recipe = FujifilmRecipeFactory(name="Keep Me")
        image = ImageFactory(fujifilm_recipe=recipe)

        operations.set_cover_image_for_recipe(recipe_id=recipe.pk, image_id=image.pk)

        recipe.refresh_from_db()
        assert recipe.name == "Keep Me"

    def test_can_change_cover_image_to_another_image(self):
        recipe = FujifilmRecipeFactory()
        image_a = ImageFactory(fujifilm_recipe=recipe)
        image_b = ImageFactory(fujifilm_recipe=recipe)

        operations.set_cover_image_for_recipe(recipe_id=recipe.pk, image_id=image_a.pk)
        operations.set_cover_image_for_recipe(recipe_id=recipe.pk, image_id=image_b.pk)

        recipe.refresh_from_db()
        assert recipe.cover_image_id == image_b.pk

    def test_publishes_event_with_correct_ids(self, captured_logs):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        operations.set_cover_image_for_recipe(recipe_id=recipe.pk, image_id=image.pk)

        cover_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_COVER_IMAGE_SET]
        assert len(cover_events) == 1
        assert cover_events[0]["recipe_id"] == recipe.pk
        assert cover_events[0]["image_id"] == image.pk

    def test_raises_recipe_not_found_for_missing_recipe(self):
        with pytest.raises(operations.RecipeNotFoundError):
            operations.set_cover_image_for_recipe(recipe_id=99999, image_id=1)

    def test_raises_image_not_found_for_missing_image(self):
        recipe = FujifilmRecipeFactory()
        with pytest.raises(operations.ImageNotFoundError):
            operations.set_cover_image_for_recipe(recipe_id=recipe.pk, image_id=99999)

    def test_raises_image_not_associated_when_image_belongs_to_other_recipe(self):
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe_b)

        with pytest.raises(operations.ImageNotAssociatedToRecipeError):
            operations.set_cover_image_for_recipe(recipe_id=recipe_a.pk, image_id=image.pk)

    def test_raises_image_not_associated_when_image_has_no_recipe(self):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=None)

        with pytest.raises(operations.ImageNotAssociatedToRecipeError):
            operations.set_cover_image_for_recipe(recipe_id=recipe.pk, image_id=image.pk)

    def test_cover_image_not_changed_when_image_not_associated(self):
        recipe = FujifilmRecipeFactory()
        original_cover = ImageFactory(fujifilm_recipe=recipe)
        operations.set_cover_image_for_recipe(recipe_id=recipe.pk, image_id=original_cover.pk)

        other_image = ImageFactory(fujifilm_recipe=None)
        with pytest.raises(operations.ImageNotAssociatedToRecipeError):
            operations.set_cover_image_for_recipe(recipe_id=recipe.pk, image_id=other_image.pk)

        recipe.refresh_from_db()
        assert recipe.cover_image_id == original_cover.pk
