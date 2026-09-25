from collections.abc import Sequence

import attrs

from src.domain.recipes import operations as domain_operations
from src.domain.recipes.operations import CollectionNameTaken as DomainCollectionNameTaken
from src.domain.recipes.operations import RecipeNotFound as DomainRecipeNotFound
from src.domain.recipes.queries import CollectionNotFound as DomainCollectionNotFound
from . import dataclasses


@attrs.frozen
class CollectionNotFound(Exception):
    """
    Raised when no collection with the given id exists.
    """

    collection_id: int


@attrs.frozen
class CollectionNameTaken(Exception):
    """
    Raised when another collection already uses the given name (case-insensitively).
    """

    name: str


@attrs.frozen
class RecipeNotFound(Exception):
    """
    Raised when a supplied recipe id does not exist.
    """

    recipe_id: int


def update_collection(
    *, collection_id: int, name: str, recipe_ids: Sequence[int],
) -> dataclasses.CollectionData:
    """
    Rename the collection and replace its ordered membership with *recipe_ids*.

    :raises CollectionNotFound: If no collection with *collection_id* exists.
    :raises CollectionNameTaken: If the name is already taken by another collection.
    :raises RecipeNotFound: If any supplied recipe id does not exist.
    """
    try:
        group = domain_operations.update_collection(
            collection_id=collection_id, name=name, recipe_ids=recipe_ids
        )
    except DomainCollectionNotFound as exc:
        raise CollectionNotFound(collection_id=exc.collection_id)
    except DomainCollectionNameTaken as exc:
        raise CollectionNameTaken(name=exc.name)
    except DomainRecipeNotFound as exc:
        raise RecipeNotFound(recipe_id=exc.recipe_id)

    return dataclasses.CollectionData(collection_id=group.pk, name=group.name)
