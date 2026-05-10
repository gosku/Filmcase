import pytest

from src.application.usecases.recipes import remove_recipes as uc
from src.data import models
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestRemoveRecipesPersistence:
    def test_deletes_recipe_from_db(self) -> None:
        recipe = FujifilmRecipeFactory()
        uc.remove_recipes(recipe_ids=[recipe.pk], remove_recipe_card_file=False)
        assert not models.FujifilmRecipe.objects.filter(pk=recipe.pk).exists()

    def test_removed_count_reflects_deletions(self) -> None:
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        result = uc.remove_recipes(
            recipe_ids=[recipe_a.pk, recipe_b.pk],
            remove_recipe_card_file=False,
        )
        assert result.removed_count == 2

    def test_does_not_delete_recipe_with_images(self) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        uc.remove_recipes(recipe_ids=[recipe.pk], remove_recipe_card_file=False)
        assert models.FujifilmRecipe.objects.filter(pk=recipe.pk).exists()

    def test_continues_after_failure_and_deletes_remaining(self) -> None:
        recipe_ok = FujifilmRecipeFactory()
        recipe_with_image = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe_with_image)

        uc.remove_recipes(
            recipe_ids=[recipe_with_image.pk, recipe_ok.pk],
            remove_recipe_card_file=False,
        )

        assert not models.FujifilmRecipe.objects.filter(pk=recipe_ok.pk).exists()
        assert models.FujifilmRecipe.objects.filter(pk=recipe_with_image.pk).exists()


@pytest.mark.django_db
class TestRemoveRecipesResult:
    def test_returns_zero_failures_on_full_success(self) -> None:
        recipe = FujifilmRecipeFactory()
        result = uc.remove_recipes(recipe_ids=[recipe.pk], remove_recipe_card_file=False)
        assert result.failures == ()

    def test_not_found_id_produces_not_found_failure(self) -> None:
        result = uc.remove_recipes(recipe_ids=[99999], remove_recipe_card_file=False)
        assert len(result.failures) == 1
        assert result.failures[0].recipe_id == 99999
        assert result.failures[0].reason == uc.RemoveRecipeFailureReason.NOT_FOUND
        assert result.failures[0].name is None

    def test_recipe_with_images_produces_has_images_failure(self) -> None:
        recipe = FujifilmRecipeFactory(name="Velvia Recipe")
        ImageFactory(fujifilm_recipe=recipe)
        result = uc.remove_recipes(recipe_ids=[recipe.pk], remove_recipe_card_file=False)
        assert len(result.failures) == 1
        assert result.failures[0].recipe_id == recipe.pk
        assert result.failures[0].reason == uc.RemoveRecipeFailureReason.HAS_IMAGES
        assert result.failures[0].name == "Velvia Recipe"

    def test_removed_count_excludes_failures(self) -> None:
        recipe_ok = FujifilmRecipeFactory()
        result = uc.remove_recipes(
            recipe_ids=[recipe_ok.pk, 99999],
            remove_recipe_card_file=False,
        )
        assert result.removed_count == 1
        assert len(result.failures) == 1

    def test_empty_ids_returns_zero_removed_and_no_failures(self) -> None:
        result = uc.remove_recipes(recipe_ids=[], remove_recipe_card_file=False)
        assert result.removed_count == 0
        assert result.failures == ()
