from unittest.mock import call, patch

import pytest

from src.application.usecases.recipes import remove_recipes as uc
from src.domain.recipes.operations import RecipeHasImagesError, RecipeNotFoundError

_OP = "src.application.usecases.recipes.remove_recipes.recipe_operations.remove_recipe"


class TestRemoveRecipesSuccessCount:
    def test_removed_count_is_zero_when_no_ids_given(self) -> None:
        result = uc.remove_recipes(recipe_ids=[], remove_recipe_card_file=False)
        assert result.removed_count == 0

    def test_removed_count_increments_for_each_success(self) -> None:
        with patch(_OP) as mock_op:
            mock_op.return_value = None
            result = uc.remove_recipes(recipe_ids=[1, 2, 3], remove_recipe_card_file=False)
        assert result.removed_count == 3

    def test_passes_remove_recipe_card_file_flag_to_operation(self) -> None:
        with patch(_OP) as mock_op:
            uc.remove_recipes(recipe_ids=[10], remove_recipe_card_file=True)
        mock_op.assert_called_once_with(recipe_id=10, remove_recipe_card_file=True)

    def test_calls_operation_for_every_id(self) -> None:
        with patch(_OP) as mock_op:
            uc.remove_recipes(recipe_ids=[1, 2, 3], remove_recipe_card_file=False)
        assert mock_op.call_count == 3
        mock_op.assert_has_calls([
            call(recipe_id=1, remove_recipe_card_file=False),
            call(recipe_id=2, remove_recipe_card_file=False),
            call(recipe_id=3, remove_recipe_card_file=False),
        ])


class TestRemoveRecipesFailureCapture:
    def test_captures_recipe_not_found_as_not_found_failure(self) -> None:
        with patch(_OP, side_effect=RecipeNotFoundError(recipe_id=42)):
            result = uc.remove_recipes(recipe_ids=[42], remove_recipe_card_file=False)
        assert len(result.failures) == 1
        assert result.failures[0].recipe_id == 42
        assert result.failures[0].reason == uc.RemoveRecipeFailureReason.NOT_FOUND
        assert result.failures[0].name is None

    def test_captures_recipe_has_images_as_has_images_failure(self) -> None:
        with patch(_OP, side_effect=RecipeHasImagesError(recipe_id=7, image_count=3, name="Velvia")):
            result = uc.remove_recipes(recipe_ids=[7], remove_recipe_card_file=False)
        assert len(result.failures) == 1
        assert result.failures[0].recipe_id == 7
        assert result.failures[0].reason == uc.RemoveRecipeFailureReason.HAS_IMAGES
        assert result.failures[0].name == "Velvia"

    def test_failure_does_not_stop_processing_remaining_ids(self) -> None:
        def _side_effect(*, recipe_id: int, remove_recipe_card_file: bool) -> None:
            if recipe_id == 2:
                raise RecipeNotFoundError(recipe_id=recipe_id)

        with patch(_OP, side_effect=_side_effect):
            result = uc.remove_recipes(recipe_ids=[1, 2, 3], remove_recipe_card_file=False)

        assert result.removed_count == 2
        assert len(result.failures) == 1
        assert result.failures[0].recipe_id == 2

    def test_collects_multiple_failures(self) -> None:
        def _side_effect(*, recipe_id: int, remove_recipe_card_file: bool) -> None:
            if recipe_id == 1:
                raise RecipeNotFoundError(recipe_id=recipe_id)
            if recipe_id == 2:
                raise RecipeHasImagesError(recipe_id=recipe_id, image_count=5, name="Provia")

        with patch(_OP, side_effect=_side_effect):
            result = uc.remove_recipes(recipe_ids=[1, 2], remove_recipe_card_file=False)

        assert result.removed_count == 0
        assert len(result.failures) == 2
        reasons = {f.recipe_id: f.reason for f in result.failures}
        assert reasons[1] == uc.RemoveRecipeFailureReason.NOT_FOUND
        assert reasons[2] == uc.RemoveRecipeFailureReason.HAS_IMAGES

    def test_unexpected_exception_propagates(self) -> None:
        with patch(_OP, side_effect=RuntimeError("unexpected")):
            with pytest.raises(RuntimeError, match="unexpected"):
                uc.remove_recipes(recipe_ids=[1], remove_recipe_card_file=False)

    def test_no_failures_when_all_succeed(self) -> None:
        with patch(_OP):
            result = uc.remove_recipes(recipe_ids=[1, 2], remove_recipe_card_file=False)
        assert result.failures == ()
