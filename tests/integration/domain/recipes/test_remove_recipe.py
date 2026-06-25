from pathlib import Path

import pytest

from src.data import models
from src.domain.images import events
from src.domain.recipes import operations
from tests.factories import FujifilmRecipeFactory, ImageFactory, RecipeCardFactory


# Tests that exercise the card-removal path call remove_recipe_card which uses
# atomic(durable=True), so they need transaction=True to avoid nesting inside
# pytest-django's implicit test transaction.
@pytest.mark.django_db(transaction=True)
class TestRemoveRecipeWithCards:
    def test_deletes_associated_recipe_cards(self) -> None:
        recipe = FujifilmRecipeFactory()
        card = RecipeCardFactory(recipe=recipe)
        operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=False)
        assert not models.RecipeCard.objects.filter(pk=card.pk).exists()

    def test_deletes_all_associated_recipe_cards(self) -> None:
        recipe = FujifilmRecipeFactory()
        card_a = RecipeCardFactory(recipe=recipe)
        card_b = RecipeCardFactory(recipe=recipe)
        operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=False)
        assert not models.RecipeCard.objects.filter(pk__in=[card_a.pk, card_b.pk]).exists()

    def test_removes_card_files_when_remove_recipe_card_file_is_true(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        filepath = tmp_path / "card.jpg"
        filepath.write_bytes(b"fake_jpeg")
        RecipeCardFactory(recipe=recipe, filepath=str(filepath))
        operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=True)
        assert not filepath.exists()

    def test_does_not_remove_card_files_when_flag_is_false(self, tmp_path: Path) -> None:
        recipe = FujifilmRecipeFactory()
        filepath = tmp_path / "card.jpg"
        filepath.write_bytes(b"fake_jpeg")
        RecipeCardFactory(recipe=recipe, filepath=str(filepath))
        operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=False)
        assert filepath.exists()

    def test_also_deletes_recipe_from_db(self) -> None:
        recipe = FujifilmRecipeFactory()
        RecipeCardFactory(recipe=recipe)
        operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=False)
        assert not models.FujifilmRecipe.objects.filter(pk=recipe.pk).exists()


# Tests that never reach the card-removal loop (no cards, or raise before it)
# can use the faster non-transactional wrapper.
@pytest.mark.django_db
class TestRemoveRecipePersistence:
    def test_deletes_recipe_from_db(self) -> None:
        recipe = FujifilmRecipeFactory()
        operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=False)
        assert not models.FujifilmRecipe.objects.filter(pk=recipe.pk).exists()

    def test_succeeds_when_recipe_has_no_cards(self) -> None:
        recipe = FujifilmRecipeFactory()
        operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=False)
        assert not models.FujifilmRecipe.objects.filter(pk=recipe.pk).exists()


@pytest.mark.django_db
class TestRemoveRecipeGuards:
    def test_raises_recipe_not_found_for_missing_recipe(self) -> None:
        with pytest.raises(operations.RecipeNotFoundError) as exc_info:
            operations.remove_recipe(recipe_id=99999, remove_recipe_card_file=False)
        assert exc_info.value.recipe_id == 99999

    def test_raises_recipe_has_images_when_recipe_has_images(self) -> None:
        recipe = FujifilmRecipeFactory(name="TestRecipe")
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeHasImagesError) as exc_info:
            operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=False)
        assert exc_info.value.recipe_id == recipe.pk
        assert exc_info.value.image_count == 1
        assert exc_info.value.name == "TestRecipe"

    def test_recipe_has_images_error_reflects_actual_count(self) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        ImageFactory(fujifilm_recipe=recipe)
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeHasImagesError) as exc_info:
            operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=False)
        assert exc_info.value.image_count == 3

    def test_does_not_delete_recipe_when_it_has_images(self) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeHasImagesError):
            operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=False)
        assert models.FujifilmRecipe.objects.filter(pk=recipe.pk).exists()

    def test_does_not_delete_cards_when_recipe_has_images(self) -> None:
        recipe = FujifilmRecipeFactory()
        card = RecipeCardFactory(recipe=recipe)
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeHasImagesError):
            operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=False)
        assert models.RecipeCard.objects.filter(pk=card.pk).exists()


@pytest.mark.django_db
class TestRemoveRecipeEventPublishing:
    def test_publishes_recipe_removed_event(self, captured_logs: list[dict]) -> None:
        recipe = FujifilmRecipeFactory(name="TestRecipe")
        operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=False)
        removed_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_REMOVED]
        assert len(removed_events) == 1
        assert removed_events[0]["recipe_id"] == recipe.pk
        assert removed_events[0]["recipe_name"] == "TestRecipe"

    def test_no_recipe_removed_event_when_recipe_has_images(self, captured_logs: list[dict]) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        with pytest.raises(operations.RecipeHasImagesError):
            operations.remove_recipe(recipe_id=recipe.pk, remove_recipe_card_file=False)
        removed_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_REMOVED]
        assert len(removed_events) == 0
