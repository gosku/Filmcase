from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.application.usecases.recipes.update_recipe_manually import (
    InvalidRecipeDataError,
    RecipeAlreadyExistsError,
    RecipeCannotBeEditedError,
    update_recipe_manually,
)
from src.domain.images import dataclasses as image_dataclasses
from src.domain.recipes import operations as recipe_operations
from src.domain.recipes.validation import InvalidFujifilmRecipeData

_OP = "src.application.usecases.recipes.update_recipe_manually.recipe_operations.update_recipe"


def _make_data(**overrides: object) -> image_dataclasses.FujifilmRecipeData:
    base: dict[str, object] = dict(
        film_simulation="Provia",
        d_range_priority="Off",
        grain_roughness="Off",
        color_chrome_effect="Off",
        color_chrome_fx_blue="Off",
        white_balance="Auto",
        white_balance_red=0,
        white_balance_blue=0,
        sharpness="0",
        high_iso_nr="0",
        clarity="0",
        dynamic_range="DR100",
        highlight="0",
        shadow="0",
        color="0",
    )
    base.update(overrides)
    return image_dataclasses.FujifilmRecipeData(**base)


class TestUpdateRecipeManually:
    def test_returns_recipe_on_success(self) -> None:
        recipe = MagicMock()
        with patch(_OP):
            result = update_recipe_manually(recipe=recipe, data=_make_data())
        assert result is recipe

    def test_raises_cannot_be_edited_when_operation_raises_guard(self) -> None:
        recipe = MagicMock()
        with patch(
            _OP,
            side_effect=recipe_operations.RecipeCannotBeEditedError(recipe_id=1, image_count=3, name="My Recipe"),
        ):
            with pytest.raises(RecipeCannotBeEditedError) as exc_info:
                update_recipe_manually(recipe=recipe, data=_make_data())
        assert exc_info.value.recipe_id == 1
        assert exc_info.value.image_count == 3
        assert exc_info.value.name == "My Recipe"

    def test_raises_already_exists_when_operation_raises_settings_conflict(self) -> None:
        recipe = MagicMock()
        recipe.pk = 9
        with patch(
            _OP,
            side_effect=recipe_operations.RecipeSettingsConflictError(recipe_id=9),
        ):
            with pytest.raises(RecipeAlreadyExistsError) as exc_info:
                update_recipe_manually(recipe=recipe, data=_make_data())
        assert exc_info.value.recipe_id == 9

    def test_raises_invalid_recipe_data_when_operation_raises_validation_error(self) -> None:
        recipe = MagicMock()
        with patch(_OP, side_effect=InvalidFujifilmRecipeData(field="color", value=None)):
            with pytest.raises(InvalidRecipeDataError) as exc_info:
                update_recipe_manually(recipe=recipe, data=_make_data())
        assert exc_info.value.field == "color"
        assert exc_info.value.value is None
