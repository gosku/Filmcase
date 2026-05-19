from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.application.usecases.recipes import create_recipe_cards_batch as uc
from src.data import models

_CREATE = (
    "src.application.usecases.recipes.create_recipe_cards_batch"
    ".create_recipe_card_uc.create_recipe_card"
)
_ZIP = (
    "src.application.usecases.recipes.create_recipe_cards_batch"
    ".card_operations.create_recipe_cards_zip"
)


def _fake_card() -> MagicMock:
    return MagicMock(spec=models.RecipeCard)


class TestCreateRecipeCardsBatchSuccessCount:
    def test_created_count_is_zero_when_no_ids_given(self) -> None:
        with patch(_ZIP) as mock_zip:
            result = uc.create_recipe_cards_batch(recipe_ids=[])
        assert result.created_count == 0
        assert result.zip_path is None
        mock_zip.assert_not_called()

    def test_created_count_increments_for_each_success(self) -> None:
        with patch(_CREATE, return_value=_fake_card()), patch(_ZIP):
            result = uc.create_recipe_cards_batch(recipe_ids=[1, 2, 3])
        assert result.created_count == 3
        assert result.failures == ()

    def test_calls_create_recipe_card_for_every_id(self) -> None:
        with patch(_CREATE, return_value=_fake_card()) as mock_create, patch(_ZIP):
            uc.create_recipe_cards_batch(recipe_ids=[1, 2])
        assert mock_create.call_count == 2
        mock_create.assert_any_call(
            recipe_id=1, image_id=None, template=uc._BATCH_TEMPLATE
        )


class TestCreateRecipeCardsBatchZip:
    def test_zip_called_with_created_cards_when_successes(self) -> None:
        cards = [_fake_card(), _fake_card()]
        with patch(_CREATE, side_effect=cards), patch(_ZIP) as mock_zip:
            uc.create_recipe_cards_batch(recipe_ids=[1, 2])
        mock_zip.assert_called_once_with(cards=cards)

    def test_zip_not_called_when_no_successes(self) -> None:
        with (
            patch(_CREATE, side_effect=models.FujifilmRecipe.DoesNotExist),
            patch(_ZIP) as mock_zip,
        ):
            result = uc.create_recipe_cards_batch(recipe_ids=[1, 2])
        mock_zip.assert_not_called()
        assert result.zip_path is None

    def test_zip_path_is_returned_from_operation(self) -> None:
        zip_path = Path("/tmp/recipe_cards_abcd1234.zip")
        with patch(_CREATE, return_value=_fake_card()), patch(_ZIP, return_value=zip_path):
            result = uc.create_recipe_cards_batch(recipe_ids=[1])
        assert result.zip_path == zip_path


class TestCreateRecipeCardsBatchFailureCapture:
    def test_captures_missing_recipe_as_not_found_failure(self) -> None:
        with (
            patch(_CREATE, side_effect=models.FujifilmRecipe.DoesNotExist),
            patch(_ZIP),
        ):
            result = uc.create_recipe_cards_batch(recipe_ids=[42])
        assert len(result.failures) == 1
        assert result.failures[0].recipe_id == 42
        assert result.failures[0].reason == uc.CreateRecipeCardFailureReason.NOT_FOUND
        assert result.failures[0].is_not_found

    def test_failure_does_not_stop_processing_remaining_ids(self) -> None:
        def _side_effect(*, recipe_id: int, image_id: int | None, template: object) -> MagicMock:
            if recipe_id == 2:
                raise models.FujifilmRecipe.DoesNotExist
            return _fake_card()

        with patch(_CREATE, side_effect=_side_effect), patch(_ZIP):
            result = uc.create_recipe_cards_batch(recipe_ids=[1, 2, 3])

        assert result.created_count == 2
        assert len(result.failures) == 1
        assert result.failures[0].recipe_id == 2

    def test_unexpected_exception_propagates(self) -> None:
        with patch(_CREATE, side_effect=RuntimeError("unexpected")), patch(_ZIP):
            with pytest.raises(RuntimeError, match="unexpected"):
                uc.create_recipe_cards_batch(recipe_ids=[1])
