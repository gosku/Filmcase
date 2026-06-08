from __future__ import annotations

import attrs

from src.domain.recipes import operations as recipe_operations
from src.domain.recipes import queries as recipe_queries


@attrs.frozen
class RecipeNotInVersionLineError(Exception):
    """
    Raised when the recipe has no VERSION_LINE group membership.
    """

    recipe_id: int


@attrs.frozen
class VersionLineGroupNotFoundError(Exception):
    """
    Raised when no VERSION_LINE group with the given ID exists.
    """

    group_id: int


@attrs.frozen
class CannotMoveToSameGroupError(Exception):
    """
    Raised when the source and destination version line groups are the same.
    """

    group_id: int


@attrs.frozen
class InvalidVersionLinePositionError(Exception):
    """
    Raised when the requested position falls outside the valid range for the destination group.
    """

    position: int
    max_position: int


def move_recipe_to_version_line(
    *,
    recipe_id: int,
    destination_group_id: int,
    position: int | None = None,
) -> None:
    """
    Move a recipe from its current version line to destination_group_id.

    :raises RecipeNotInVersionLineError: If recipe_id has no VERSION_LINE membership.
    :raises VersionLineGroupNotFoundError: If destination_group_id doesn't exist.
    :raises CannotMoveToSameGroupError: If source and destination are the same group.
    :raises InvalidVersionLinePositionError: If position is out of valid range.
    """
    try:
        recipe_operations.move_recipe_to_version_line(
            recipe_id=recipe_id,
            destination_group_id=destination_group_id,
            position=position,
        )
    except recipe_queries.RecipeNotInVersionLineError as exc:
        raise RecipeNotInVersionLineError(recipe_id=exc.recipe_id)
    except recipe_operations.VersionLineGroupNotFoundError as exc:
        raise VersionLineGroupNotFoundError(group_id=exc.group_id)
    except recipe_operations.CannotMoveToSameGroupError as exc:
        raise CannotMoveToSameGroupError(group_id=exc.group_id)
    except recipe_operations.InvalidVersionLinePositionError as exc:
        raise InvalidVersionLinePositionError(
            position=exc.position,
            max_position=exc.max_position,
        )
