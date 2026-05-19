from __future__ import annotations

import enum
from collections.abc import Iterable
from pathlib import Path

import attrs

from src.application.usecases.recipes import create_recipe_card as create_recipe_card_uc
from src.data import models
from src.domain.recipes.cards import operations as card_operations
from src.domain.recipes.cards import templates as card_templates

# Every batch card uses long labels on a generated gradient (no background
# image), matching the agreed fixed template for bulk creation.
_BATCH_TEMPLATE = card_templates.LONG_LABEL


class CreateRecipeCardFailureReason(enum.StrEnum):
    NOT_FOUND = "not_found"


@attrs.frozen
class CreateRecipeCardFailure:
    recipe_id: int
    reason: CreateRecipeCardFailureReason

    @property
    def is_not_found(self) -> bool:
        return self.reason == CreateRecipeCardFailureReason.NOT_FOUND


@attrs.frozen
class CreateRecipeCardsBatchResult:
    created_count: int
    failures: tuple[CreateRecipeCardFailure, ...]
    zip_path: Path | None


def create_recipe_cards_batch(
    *,
    recipe_ids: Iterable[int],
) -> CreateRecipeCardsBatchResult:
    """
    Create a recipe card for each recipe in recipe_ids and zip the results.

    Calls create_recipe_card for every ID regardless of individual failures,
    collecting successes and failures. Recipes that do not exist are recorded
    as NOT_FOUND failures; any other exception propagates immediately. When at
    least one card is created the cards are bundled into a zip and its path is
    returned, otherwise zip_path is None.
    """
    created: list[models.RecipeCard] = []
    failures: list[CreateRecipeCardFailure] = []

    for recipe_id in recipe_ids:
        try:
            card = create_recipe_card_uc.create_recipe_card(
                recipe_id=recipe_id,
                image_id=None,
                template=_BATCH_TEMPLATE,
            )
            created.append(card)
        except models.FujifilmRecipe.DoesNotExist:
            failures.append(CreateRecipeCardFailure(
                recipe_id=recipe_id,
                reason=CreateRecipeCardFailureReason.NOT_FOUND,
            ))

    zip_path = (
        card_operations.create_recipe_cards_zip(cards=created) if created else None
    )

    return CreateRecipeCardsBatchResult(
        created_count=len(created),
        failures=tuple(failures),
        zip_path=zip_path,
    )
