from unittest.mock import MagicMock, patch

import pytest

from src.application.usecases.recipes.create_recipe_manually import (
    InvalidRecipeDataError,
    RecipeAlreadyExistsError,
    create_recipe_manually,
)
from src.domain.images import dataclasses as image_dataclasses
from src.domain.recipes.validation import InvalidFujifilmRecipeData

_OP = "src.application.usecases.recipes.create_recipe_manually.recipe_operations.get_or_create_recipe_from_data"


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


class TestCreateRecipeManually:
    def test_returns_recipe_when_successfully_created(self) -> None:
        recipe = MagicMock()
        with patch(_OP, return_value=(recipe, True)):
            result = create_recipe_manually(data=_make_data())
        assert result is recipe

    def test_raises_already_exists_when_recipe_was_not_created(self) -> None:
        recipe = MagicMock()
        recipe.name = "Existing Recipe"
        with patch(_OP, return_value=(recipe, False)):
            with pytest.raises(RecipeAlreadyExistsError) as exc_info:
                create_recipe_manually(data=_make_data())
        assert exc_info.value.name == "Existing Recipe"

    def test_already_exists_error_carries_empty_name_when_recipe_is_unnamed(self) -> None:
        recipe = MagicMock()
        recipe.name = ""
        with patch(_OP, return_value=(recipe, False)):
            with pytest.raises(RecipeAlreadyExistsError) as exc_info:
                create_recipe_manually(data=_make_data())
        assert exc_info.value.name == ""

    def test_raises_invalid_recipe_data_when_operation_raises_validation_error(self) -> None:
        with patch(_OP, side_effect=InvalidFujifilmRecipeData(field="color", value=None)):
            with pytest.raises(InvalidRecipeDataError) as exc_info:
                create_recipe_manually(data=_make_data())
        assert exc_info.value.field == "color"
        assert exc_info.value.value is None
