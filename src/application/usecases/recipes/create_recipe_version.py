from __future__ import annotations

import attrs

from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.recipes import operations as recipe_operations
from src.domain.recipes import validation as recipe_validation


@attrs.frozen
class InvalidRecipeDataError(Exception):
    """
    Raised when recipe data fails normalization or validation.
    """

    field: str
    value: object


@attrs.frozen
class RecipeAlreadyExistsError(Exception):
    """
    Raised when a recipe with the same settings already exists in the database.
    """

    name: str


@attrs.frozen
class VersionLineGroupNotFoundError(Exception):
    """
    Raised when no VERSION_LINE group with the given ID exists.
    """

    group_id: int


def create_recipe_version(
    *,
    data: image_dataclasses.FujifilmRecipeData,
    group_id: int,
) -> models.FujifilmRecipe:
    """
    Create a new recipe version in an existing version line group.

    :raises InvalidRecipeDataError: If the data fails normalization or validation.
    :raises RecipeAlreadyExistsError: If a recipe with the same settings already exists.
    :raises VersionLineGroupNotFoundError: If no VERSION_LINE group with *group_id* exists.
    """
    try:
        recipe, created = recipe_operations.get_or_create_recipe_from_data(
            data=data,
            group_id=group_id,
        )
    except recipe_validation.InvalidFujifilmRecipeData as exc:
        raise InvalidRecipeDataError(field=exc.field, value=exc.value)
    except recipe_operations.VersionLineGroupNotFoundError as exc:
        raise VersionLineGroupNotFoundError(group_id=exc.group_id)

    if not created:
        raise RecipeAlreadyExistsError(name=recipe.name)

    return recipe
