from unittest.mock import MagicMock, call, patch

import pytest

from src.data import models
from src.domain.images import events
from src.domain.recipes import operations


def _make_recipe_qs(recipe: object = None, missing: bool = False) -> MagicMock:
    qs = MagicMock()
    if missing:
        qs.get.side_effect = models.FujifilmRecipe.DoesNotExist
    else:
        qs.get.return_value = recipe
    return qs


def _make_image_qs(count: int = 0) -> MagicMock:
    qs = MagicMock()
    qs.filter.return_value.count.return_value = count
    return qs


def _make_card_qs(cards: list = None) -> MagicMock:
    qs = MagicMock()
    qs.filter.return_value = cards or []
    return qs


class TestRemoveRecipeNotFound:
    def test_raises_recipe_not_found_when_recipe_missing(self) -> None:
        with patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(missing=True)):
            with pytest.raises(operations.RecipeNotFoundError) as exc_info:
                operations.remove_recipe(recipe_id=42, remove_recipe_card_file=False)
        assert exc_info.value.recipe_id == 42


class TestRemoveRecipeHasImages:
    def test_raises_recipe_has_images_when_image_count_is_nonzero(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        recipe.name = "MyRecipe"
        with (
            patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(recipe=recipe)),
            patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=3)),
        ):
            with pytest.raises(operations.RecipeHasImagesError) as exc_info:
                operations.remove_recipe(recipe_id=1, remove_recipe_card_file=False)
        assert exc_info.value.recipe_id == 1
        assert exc_info.value.image_count == 3
        assert exc_info.value.name == "MyRecipe"

    def test_recipe_not_deleted_when_it_has_images(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        with (
            patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(recipe=recipe)),
            patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=1)),
        ):
            with pytest.raises(operations.RecipeHasImagesError):
                operations.remove_recipe(recipe_id=1, remove_recipe_card_file=False)
        recipe.delete.assert_not_called()

    def test_remove_recipe_card_not_called_when_recipe_has_images(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        with (
            patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(recipe=recipe)),
            patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=1)),
            patch("src.domain.recipes.operations.card_operations.remove_recipe_card") as mock_remove_card,
        ):
            with pytest.raises(operations.RecipeHasImagesError):
                operations.remove_recipe(recipe_id=1, remove_recipe_card_file=False)
        mock_remove_card.assert_not_called()


class TestRemoveRecipeCardDelegation:
    def test_calls_remove_recipe_card_for_each_card(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        recipe.name = "R"
        card_a = MagicMock()
        card_a.pk = 10
        card_b = MagicMock()
        card_b.pk = 20
        with (
            patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(recipe=recipe)),
            patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)),
            patch("src.domain.recipes.operations.models.RecipeCard.objects", _make_card_qs(cards=[card_a, card_b])),
            patch("src.domain.recipes.operations.card_operations.remove_recipe_card") as mock_remove_card,
        ):
            operations.remove_recipe(recipe_id=1, remove_recipe_card_file=True)
        assert mock_remove_card.call_count == 2
        mock_remove_card.assert_any_call(card_id=10, remove_file=True)
        mock_remove_card.assert_any_call(card_id=20, remove_file=True)

    def test_passes_remove_file_flag_to_remove_recipe_card(self) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        recipe.name = "R"
        card = MagicMock()
        card.pk = 10
        with (
            patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(recipe=recipe)),
            patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)),
            patch("src.domain.recipes.operations.models.RecipeCard.objects", _make_card_qs(cards=[card])),
            patch("src.domain.recipes.operations.card_operations.remove_recipe_card") as mock_remove_card,
        ):
            operations.remove_recipe(recipe_id=1, remove_recipe_card_file=False)
        mock_remove_card.assert_called_once_with(card_id=10, remove_file=False)


class TestRemoveRecipeEventPublishing:
    def test_publishes_recipe_removed_event(self, captured_logs: list[dict]) -> None:
        recipe = MagicMock()
        recipe.pk = 7
        recipe.name = "MyRecipe"
        with (
            patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(recipe=recipe)),
            patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=0)),
            patch("src.domain.recipes.operations.models.RecipeCard.objects", _make_card_qs()),
        ):
            operations.remove_recipe(recipe_id=7, remove_recipe_card_file=False)
        removed_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_REMOVED]
        assert len(removed_events) == 1
        assert removed_events[0]["recipe_id"] == 7
        assert removed_events[0]["recipe_name"] == "MyRecipe"

    def test_no_event_published_when_recipe_not_found(self, captured_logs: list[dict]) -> None:
        with patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(missing=True)):
            with pytest.raises(operations.RecipeNotFoundError):
                operations.remove_recipe(recipe_id=42, remove_recipe_card_file=False)
        removed_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_REMOVED]
        assert len(removed_events) == 0

    def test_no_event_published_when_recipe_has_images(self, captured_logs: list[dict]) -> None:
        recipe = MagicMock()
        recipe.pk = 1
        with (
            patch("src.domain.recipes.operations.models.FujifilmRecipe.objects", _make_recipe_qs(recipe=recipe)),
            patch("src.domain.recipes.operations.models.Image.objects", _make_image_qs(count=2)),
        ):
            with pytest.raises(operations.RecipeHasImagesError):
                operations.remove_recipe(recipe_id=1, remove_recipe_card_file=False)
        removed_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_REMOVED]
        assert len(removed_events) == 0
