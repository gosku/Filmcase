from __future__ import annotations

import enum
from collections.abc import Iterable

import attrs

from src.domain.recipes import operations as recipe_operations


class RemoveRecipeFailureReason(enum.StrEnum):
    NOT_FOUND = "not_found"
    HAS_IMAGES = "has_images"


@attrs.frozen
class RemoveRecipeFailure:
    recipe_id: int
    reason: RemoveRecipeFailureReason
    name: str | None


@attrs.frozen
class RemoveRecipesResult:
    removed_count: int
    failures: tuple[RemoveRecipeFailure, ...]


def remove_recipes(
    *,
    recipe_ids: Iterable[int],
    remove_recipe_card_file: bool,
) -> RemoveRecipesResult:
    """
    Remove each recipe in recipe_ids, collecting successes and failures.

    Calls remove_recipe for every ID regardless of individual failures.
    RecipeNotFoundError and RecipeHasImagesError are captured and returned
    as failures; any other exception propagates immediately.
    """
    removed_count = 0
    failures: list[RemoveRecipeFailure] = []

    for recipe_id in recipe_ids:
        try:
            recipe_operations.remove_recipe(
                recipe_id=recipe_id,
                remove_recipe_card_file=remove_recipe_card_file,
            )
            removed_count += 1
        except recipe_operations.RecipeNotFoundError:
            failures.append(RemoveRecipeFailure(
                recipe_id=recipe_id,
                reason=RemoveRecipeFailureReason.NOT_FOUND,
                name=None,
            ))
        except recipe_operations.RecipeHasImagesError as exc:
            failures.append(RemoveRecipeFailure(
                recipe_id=recipe_id,
                reason=RemoveRecipeFailureReason.HAS_IMAGES,
                name=exc.name,
            ))

    return RemoveRecipesResult(removed_count=removed_count, failures=tuple(failures))
