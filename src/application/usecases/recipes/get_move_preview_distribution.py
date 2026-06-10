from __future__ import annotations

import attrs

from src.domain.images.queries import Duration
from src.domain.recipes import queries as recipe_queries

from . import _distribution_context

RecipeDistributionContext = _distribution_context.RecipeDistributionContext


@attrs.frozen
class InvalidDurationError(Exception):
    duration: str


@attrs.frozen
class VersionLineGroupNotFoundError(Exception):
    group_id: int


def get_move_preview_distribution(
    *,
    source_recipe_id: int,
    destination_group_id: int,
    position: int | None = None,
    duration: str | None = None,
) -> RecipeDistributionContext:
    """
    Return the distribution chart data as it would appear after moving source_recipe_id
    to destination_group_id at position (default: last).

    Does not write to the database.

    :raises InvalidDurationError: If duration is not a valid Duration value.
    :raises VersionLineGroupNotFoundError: If destination_group_id has no members.
    """
    if duration is None:
        _duration = Duration.MONTH
    else:
        try:
            _duration = Duration(duration)
        except ValueError:
            raise InvalidDurationError(duration=duration)

    try:
        simulated = recipe_queries.get_simulated_version_line_members(
            source_recipe_id=source_recipe_id,
            destination_group_id=destination_group_id,
            position=position,
        )
    except recipe_queries.VersionLineGroupNotFoundError as exc:
        raise VersionLineGroupNotFoundError(group_id=exc.group_id)

    return _distribution_context.build_distribution_context(
        version_line=simulated,
        duration=_duration,
        current_recipe_id=source_recipe_id,
    )
