from __future__ import annotations

import attrs

from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.recipes import operations as recipe_operations
from src.domain.recipes import validation as recipe_validation


@attrs.frozen
class RecipeCannotBeEditedError(Exception):
    """
    Raised when the recipe's settings cannot be changed because it has associated Images.
    """

    recipe_id: int
    image_count: int
    name: str


@attrs.frozen
class RecipeAlreadyExistsError(Exception):
    """
    Raised when the updated settings match an existing recipe.
    """

    recipe_id: int


@attrs.frozen
class InvalidRecipeDataError(Exception):
    """
    Raised when recipe data fails normalization or validation.
    """

    field: str
    value: object


def update_recipe_manually(
    *,
    recipe: models.FujifilmRecipe,
    data: image_dataclasses.FujifilmRecipeData,
) -> models.FujifilmRecipe:
    """
    Update an existing recipe with the given data.

    :raises RecipeCannotBeEditedError: If settings fields changed but the recipe has associated Images.
    :raises RecipeAlreadyExistsError: If the new settings match an existing recipe.
    :raises InvalidRecipeDataError: If the data fails normalization or validation.
    """
    try:
        recipe_operations.update_recipe(recipe=recipe, data=data)
    except recipe_operations.RecipeCannotBeEditedError as exc:
        raise RecipeCannotBeEditedError(
            recipe_id=exc.recipe_id,
            image_count=exc.image_count,
            name=exc.name,
        )
    except recipe_operations.RecipeSettingsConflictError as exc:
        raise RecipeAlreadyExistsError(recipe_id=exc.recipe_id)
    except recipe_validation.InvalidFujifilmRecipeData as exc:
        raise InvalidRecipeDataError(field=exc.field, value=exc.value)
    return recipe
