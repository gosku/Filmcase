from __future__ import annotations

import attrs

from src.data import models
from src.domain.images.queries import Duration
from src.domain.recipes import queries as recipe_queries
from src.domain.recipes.queries import RecipeNotInVersionLineError as _QueryRecipeNotInVersionLineError

from . import _distribution_context

# Re-export shared types, constants, and helpers so existing importers still work.
BucketData = _distribution_context.BucketData
RecipeDistributionContext = _distribution_context.RecipeDistributionContext
VersionInfo = _distribution_context.VersionInfo
_CURRENT_COLOR = _distribution_context._CURRENT_COLOR
_VERSION_COLORS = _distribution_context._VERSION_COLORS
_align_counts = _distribution_context._align_counts
_build_versions = _distribution_context._build_versions
_ordered_buckets = _distribution_context._ordered_buckets


@attrs.frozen
class InvalidDurationError(Exception):
    duration: str


@attrs.frozen
class RecipeNotFoundError(Exception):
    recipe_id: int


@attrs.frozen
class RecipeNotInVersionLineError(Exception):
    recipe_id: int


def get_recipe_distribution(
    *,
    recipe_id: int,
    duration: str | None = None,
) -> RecipeDistributionContext:
    """
    Return all data needed to render the recipe distribution chart.

    If duration is None, defaults to Duration.MONTH.

    :raises InvalidDurationError: If duration is not a valid Duration value.
    :raises RecipeNotFoundError: If no recipe with recipe_id exists.
    :raises RecipeNotInVersionLineError: If recipe_id has no VERSION_LINE group.
    """
    if duration is None:
        _duration = Duration.MONTH
    else:
        try:
            _duration = Duration(duration)
        except ValueError:
            raise InvalidDurationError(duration=duration)

    try:
        recipe_queries.get_recipe_detail(recipe_id=recipe_id)
    except models.FujifilmRecipe.DoesNotExist:
        raise RecipeNotFoundError(recipe_id=recipe_id)

    try:
        version_line = recipe_queries.get_recipes_in_version_line(recipe_id=recipe_id)
    except _QueryRecipeNotInVersionLineError:
        raise RecipeNotInVersionLineError(recipe_id=recipe_id)

    return _distribution_context.build_distribution_context(
        version_line=version_line,
        duration=_duration,
        current_recipe_id=recipe_id,
    )
