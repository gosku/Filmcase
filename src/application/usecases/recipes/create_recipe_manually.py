from __future__ import annotations

import attrs

from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.recipes import operations as recipe_operations
from src.domain.recipes import validation as recipe_validation


@attrs.frozen
class RecipeAlreadyExistsError(Exception):
    """Raised when a recipe with the same settings already exists in the database."""

    name: str


@attrs.frozen
class InvalidRecipeDataError(Exception):
    """Raised when recipe data fails normalization or validation."""

    field: str
    value: object


def create_recipe_manually(*, data: image_dataclasses.FujifilmRecipeData) -> models.FujifilmRecipe:
    """Create a new recipe from manually entered data.

    :raises InvalidRecipeDataError: If the data fails normalization or validation.
    :raises RecipeAlreadyExistsError: If a recipe with the same settings already exists.
    """
    try:
        recipe, created = recipe_operations.get_or_create_recipe_from_data(data=data)
    except recipe_validation.InvalidFujifilmRecipeData as exc:
        raise InvalidRecipeDataError(field=exc.field, value=exc.value)

    if not created:
        raise RecipeAlreadyExistsError(name=recipe.name)

    return recipe
