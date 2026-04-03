from __future__ import annotations

import attrs

from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.images import events


@attrs.frozen
class RecipeNameValidationError(Exception):
    """Raised when a recipe name fails validation (too long or non-ASCII)."""

    name: str


def set_recipe_name(*, recipe: models.FujifilmRecipe, name: str) -> None:
    """Set the name of *recipe* to *name* after validating it.

    Raises:
        RecipeNameValidationError: If the name is empty, longer than
            RECIPE_NAME_MAX_LEN, or contains non-ASCII characters.
    """
    if not name or len(name) > image_dataclasses.RECIPE_NAME_MAX_LEN or not name.isascii():
        raise RecipeNameValidationError(name)
    recipe.name = name
    recipe.save(update_fields=["name"])
    events.publish_event(
        event_type=events.RECIPE_IMAGE_UPDATED,
        name=name,
        recipe_id=recipe.pk,
    )
