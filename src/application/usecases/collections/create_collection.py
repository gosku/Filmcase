from collections.abc import Sequence

import attrs

from src.domain.recipes import operations as domain_operations
from src.domain.recipes.operations import CollectionNameTaken as DomainCollectionNameTaken
from src.domain.recipes.operations import RecipeNotFound as DomainRecipeNotFound
from . import dataclasses


@attrs.frozen
class CollectionNameTaken(Exception):
    """
    Raised when a collection already uses the given name (case-insensitively).
    """

    name: str


@attrs.frozen
class RecipeNotFound(Exception):
    """
    Raised when a supplied recipe id does not exist.
    """

    recipe_id: int


def create_collection(*, name: str, recipe_ids: Sequence[int]) -> dataclasses.CollectionData:
    """
    Create a collection named *name* holding *recipe_ids* in order.

    :raises CollectionNameTaken: If the name is already taken.
    :raises RecipeNotFound: If any supplied recipe id does not exist.
    """
    try:
        group = domain_operations.create_collection(name=name, recipe_ids=recipe_ids)
    except DomainCollectionNameTaken as exc:
        raise CollectionNameTaken(name=exc.name)
    except DomainRecipeNotFound as exc:
        raise RecipeNotFound(recipe_id=exc.recipe_id)

    return dataclasses.CollectionData(collection_id=group.pk, name=group.name)
