from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

import attrs

from src.data import models
from src.domain.images import queries as image_queries
from src.domain.images.queries import Duration
from src.domain.recipes import queries as recipe_queries
from src.domain.recipes.queries import RecipeNotInVersionLineError as _QueryRecipeNotInVersionLineError


@attrs.frozen
class InvalidDurationError(Exception):
    duration: str


@attrs.frozen
class RecipeNotFoundError(Exception):
    recipe_id: int


@attrs.frozen
class RecipeNotInVersionLineError(Exception):
    recipe_id: int


_VERSION_COLORS: tuple[str, ...] = ("#6366F1", "#14B8A6", "#F59E0B")
_CURRENT_COLOR = "#EF4444"


@attrs.frozen
class VersionInfo:
    recipe_id: int
    label: str
    name: str
    color: str
    is_current: bool
    image_count: int


@attrs.frozen
class BucketData:
    label: str
    counts: dict[int, int]


@attrs.frozen
class RecipeDistributionContext:
    recipe_id: int
    versions: tuple[VersionInfo, ...]
    buckets: tuple[BucketData, ...]
    scale: Duration
    total_images: int
    total_time_periods: int


def _build_versions(
    *,
    version_recipes: Sequence[recipe_queries.VersionLineRecipe],
    distributions: Sequence[image_queries.RecipeImageDistribution],
) -> tuple[VersionInfo, ...]:
    """
    Assign a display colour and total image count to each version.

    The current recipe always uses the highlight colour; every other
    version takes the next colour from the palette (cycling), so colours
    stay stable regardless of which version is current.
    """
    dist_by_id = {d.recipe_id: d for d in distributions}
    non_current_idx = 0
    versions: list[VersionInfo] = []
    for vr in version_recipes:
        if vr.is_current:
            color = _CURRENT_COLOR
        else:
            color = _VERSION_COLORS[non_current_idx % len(_VERSION_COLORS)]
            non_current_idx += 1
        dist = dist_by_id.get(vr.recipe_id)
        image_count = sum(bc.count for bc in dist.buckets) if dist else 0
        versions.append(VersionInfo(
            recipe_id=vr.recipe_id,
            label=vr.label,
            name=vr.name,
            color=color,
            is_current=vr.is_current,
            image_count=image_count,
        ))
    return tuple(versions)


def _ordered_buckets(
    distributions: Iterable[image_queries.RecipeImageDistribution],
) -> tuple[tuple[datetime, str], ...]:
    """
    Return the union of all time buckets across versions, chronologically.

    Versions cover different periods, so the x-axis is the deduplicated
    set of (bucket_dt, label) pairs sorted by the real datetime.
    """
    seen_dts: dict[datetime, str] = {}
    for dist in distributions:
        for bc in dist.buckets:
            if bc.bucket_dt not in seen_dts:
                seen_dts[bc.bucket_dt] = bc.bucket
    return tuple(sorted(seen_dts.items()))


def _align_counts(
    *,
    ordered_buckets: Sequence[tuple[datetime, str]],
    distributions: Sequence[image_queries.RecipeImageDistribution],
    recipe_ids: Sequence[int],
) -> tuple[BucketData, ...]:
    """
    Densify ragged per-version counts into an aligned bucket matrix.

    Every bucket gets a count for every recipe in the line, defaulting
    to 0 when a recipe had no images in that period.
    """
    bc_by_recipe_and_dt: dict[int, dict[datetime, int]] = {
        dist.recipe_id: {bc.bucket_dt: bc.count for bc in dist.buckets}
        for dist in distributions
    }
    return tuple(
        BucketData(
            label=label,
            counts={
                rid: bc_by_recipe_and_dt.get(rid, {}).get(bucket_dt, 0)
                for rid in recipe_ids
            },
        )
        for bucket_dt, label in ordered_buckets
    )


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

    all_recipe_ids = [vr.recipe_id for vr in version_line.recipes]
    distributions = image_queries.get_number_images_aggregated_by(
        duration=_duration,
        recipe_ids=all_recipe_ids,
    )

    versions = _build_versions(
        version_recipes=version_line.recipes,
        distributions=distributions,
    )
    buckets = _align_counts(
        ordered_buckets=_ordered_buckets(distributions),
        distributions=distributions,
        recipe_ids=all_recipe_ids,
    )

    return RecipeDistributionContext(
        recipe_id=recipe_id,
        versions=versions,
        buckets=buckets,
        scale=_duration,
        total_images=sum(v.image_count for v in versions),
        total_time_periods=len(buckets),
    )
