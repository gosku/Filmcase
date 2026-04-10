from __future__ import annotations

from collections.abc import Mapping, Sequence

import attrs
from django.core import paginator as django_paginator
from django.db.models import Case, Count, IntegerField, Max, Min, Value, When
from django.db.models.functions import TruncMonth

from src.data import models
from src.domain.images import dataclasses as image_dataclasses


# Recipe fields available for comparison and graph computation.
RECIPE_FIELDS: tuple[str, ...] = (
    "film_simulation",
    "dynamic_range",
    "d_range_priority",
    "grain_roughness",
    "grain_size",
    "color_chrome_effect",
    "color_chrome_fx_blue",
    "white_balance",
    "white_balance_red",
    "white_balance_blue",
    "highlight",
    "shadow",
    "color",
    "sharpness",
    "high_iso_nr",
    "clarity",
    "monochromatic_color_warm_cool",
    "monochromatic_color_magenta_green",
)


_DECIMAL_FIELDS: frozenset[str] = frozenset({
    "highlight",
    "shadow",
    "color",
    "sharpness",
    "high_iso_nr",
    "clarity",
    "monochromatic_color_warm_cool",
    "monochromatic_color_magenta_green",
})

_FIELD_LABELS: dict[str, str] = {
    "film_simulation": "Film Simulation",
    "dynamic_range": "Dynamic Range",
    "d_range_priority": "D-Range Priority",
    "grain_roughness": "Grain",
    "grain_size": "Grain Size",
    "color_chrome_effect": "Color Chrome",
    "color_chrome_fx_blue": "CC FX Blue",
    "white_balance": "White Balance",
    "white_balance_red": "WB Red",
    "white_balance_blue": "WB Blue",
    "highlight": "Highlight",
    "shadow": "Shadow",
    "color": "Color",
    "sharpness": "Sharpness",
    "high_iso_nr": "High ISO NR",
    "clarity": "Clarity",
    "monochromatic_color_warm_cool": "BW Warm/Cool",
    "monochromatic_color_magenta_green": "BW Mag/Green",
}


@attrs.frozen
class FieldValue:
    field: str
    value: str
    before: str | None = None  # set on diffs; None for root all-fields display


@attrs.frozen
class PathNodeDelta:
    recipe_id: int
    label: str
    changed_fields: tuple[FieldValue, ...]


@attrs.frozen
class PathDeltaResult:
    root_diffs: tuple[FieldValue, ...]
    path_nodes: tuple[PathNodeDelta, ...]
    missing_ids: tuple[int, ...]


def _decimal_str(value: object) -> str:
    """Convert a non-null Decimal DB value to a signed string (e.g. Decimal('1.5') → '+1.5')."""
    n = float(value)  # type: ignore[arg-type]
    v: int | float = int(n) if n == int(n) else n
    return f"+{v}" if v > 0 else str(v)


def _decimal_str_or_none(value: object) -> str | None:
    return None if value is None else _decimal_str(value)


def recipe_from_db(*, recipe: models.FujifilmRecipe) -> image_dataclasses.FujifilmRecipeData:
    """Convert a FujifilmRecipe DB model instance to a FujifilmRecipeData domain object."""
    return image_dataclasses.FujifilmRecipeData(
        name=recipe.name,
        film_simulation=recipe.film_simulation,
        d_range_priority=recipe.d_range_priority,
        grain_roughness=recipe.grain_roughness,
        color_chrome_effect=recipe.color_chrome_effect,
        color_chrome_fx_blue=recipe.color_chrome_fx_blue,
        white_balance=recipe.white_balance,
        white_balance_red=recipe.white_balance_red,
        white_balance_blue=recipe.white_balance_blue,
        sharpness=_decimal_str(recipe.sharpness),
        high_iso_nr=_decimal_str(recipe.high_iso_nr),
        clarity=_decimal_str(recipe.clarity),
        dynamic_range=recipe.dynamic_range or None,
        grain_size=None if recipe.grain_roughness == "Off" else recipe.grain_size,
        highlight=_decimal_str_or_none(recipe.highlight),
        shadow=_decimal_str_or_none(recipe.shadow),
        color=_decimal_str_or_none(recipe.color),
        monochromatic_color_warm_cool=_decimal_str_or_none(recipe.monochromatic_color_warm_cool),
        monochromatic_color_magenta_green=_decimal_str_or_none(recipe.monochromatic_color_magenta_green),
    )


@attrs.frozen
class RecipeUsageStats:
    recipe_id: int
    photo_count: int
    first_used: object  # datetime | None
    last_used: object  # datetime | None


@attrs.frozen
class RecipeComparisonResult:
    recipes: tuple[models.FujifilmRecipe, ...]
    missing_ids: tuple[int, ...]
    stats_by_id: dict[int, RecipeUsageStats]
    # month_key (YYYY-MM) → {recipe_id: count}
    monthly_counts: dict[str, dict[int, int]]


def get_default_recipe_for_film_simulation(
    *, film_simulation: str,
) -> models.FujifilmRecipe | None:
    """Return the most-used recipe for the given film simulation.

    "Most-used" is defined as the recipe linked to the greatest number of images.
    Ties are broken by ascending pk (earliest created recipe wins).
    Returns None when no recipes exist for the film simulation.
    """
    from django.db.models import Count
    return (
        models.FujifilmRecipe.objects
        .filter(film_simulation=film_simulation)
        .annotate(image_count=Count("images"))
        .order_by("-image_count", "pk")
        .first()
    )


def get_recipes_by_film_simulation(*, film_simulation: str) -> list[models.FujifilmRecipe]:
    """Return all recipes whose film_simulation matches exactly."""
    return list(models.FujifilmRecipe.objects.filter(film_simulation=film_simulation))


def get_distinct_film_simulations() -> list[str]:
    """Return all distinct film_simulation values present in the recipe table, sorted."""
    return list(
        models.FujifilmRecipe.objects
        .values_list("film_simulation", flat=True)
        .distinct()
        .order_by("film_simulation")
    )


def get_film_simulations_with_multiple_recipes() -> list[str]:
    """Return film simulations that have more than one recipe, sorted.

    Film simulations with only one recipe produce a trivial (single-node) graph
    and are excluded from graph filter controls.
    """
    from django.db.models import Count
    return list(
        models.FujifilmRecipe.objects
        .values("film_simulation")
        .annotate(count=Count("pk"))
        .filter(count__gt=1)
        .order_by("film_simulation")
        .values_list("film_simulation", flat=True)
    )


def get_image_counts_for_film_simulation(*, film_simulation: str) -> dict[int, int]:
    """Return a mapping of recipe_id → image count for all recipes with the given film sim."""
    from django.db.models import Count
    return {
        row["fujifilm_recipe_id"]: row["count"]
        for row in (
            models.Image.objects
            .filter(fujifilm_recipe__film_simulation=film_simulation)
            .values("fujifilm_recipe_id")
            .annotate(count=Count("id"))
        )
    }


def get_image_counts(*, recipe_pks: list[int]) -> dict[int, int]:
    """Return a mapping of recipe_id → image count for the given recipe PKs."""
    return {
        row["fujifilm_recipe_id"]: row["count"]
        for row in (
            models.Image.objects
            .filter(fujifilm_recipe_id__in=recipe_pks)
            .values("fujifilm_recipe_id")
            .annotate(count=Count("id"))
        )
    }


def get_recipe_comparison(*, recipe_ids: list[int]) -> RecipeComparisonResult:
    """Fetch recipes, usage stats, and monthly breakdowns for the given IDs.

    Returns a structured result containing all data needed to render a comparison,
    so callers make a single query into the domain rather than issuing multiple
    separate ORM calls.
    """
    recipes_by_id = {
        r.id: r for r in models.FujifilmRecipe.objects.filter(id__in=recipe_ids)
    }
    missing = tuple(sorted(set(recipe_ids) - set(recipes_by_id)))
    ordered = tuple(recipes_by_id[i] for i in recipe_ids if i in recipes_by_id)

    raw_stats = (
        models.Image.objects
        .filter(fujifilm_recipe_id__in=recipe_ids, taken_at__isnull=False)
        .values("fujifilm_recipe_id")
        .annotate(
            first_used=Min("taken_at"),
            last_used=Max("taken_at"),
            photo_count=Count("id"),
        )
    )
    stats_by_id = {
        s["fujifilm_recipe_id"]: RecipeUsageStats(
            recipe_id=s["fujifilm_recipe_id"],
            photo_count=s["photo_count"],
            first_used=s["first_used"],
            last_used=s["last_used"],
        )
        for s in raw_stats
    }

    monthly_qs = (
        models.Image.objects
        .filter(fujifilm_recipe_id__in=recipe_ids, taken_at__isnull=False)
        .annotate(month=TruncMonth("taken_at"))
        .values("month", "fujifilm_recipe_id")
        .annotate(count=Count("id"))
        .order_by("month")
    )
    monthly_counts: dict[str, dict[int, int]] = {}
    for row in monthly_qs:
        key = row["month"].strftime("%Y-%m")
        monthly_counts.setdefault(key, {})[row["fujifilm_recipe_id"]] = row["count"]

    return RecipeComparisonResult(
        recipes=ordered,
        missing_ids=missing,
        stats_by_id=stats_by_id,
        monthly_counts=monthly_counts,
    )


def _field_display_value(field: str, raw: object) -> str | None:
    """Return a display-ready string for *field*'s value, or None to omit it."""
    if raw is None:
        return None
    if field in _DECIMAL_FIELDS:
        return _decimal_str(raw)
    return str(raw)


def _recipe_all_fields(recipe: models.FujifilmRecipe) -> tuple[FieldValue, ...]:
    result = []
    for field in RECIPE_FIELDS:
        value = _field_display_value(field, getattr(recipe, field))
        if value is not None:
            result.append(FieldValue(field=_FIELD_LABELS[field], value=value))
    return tuple(result)


def _recipe_diff_fields(
    a: models.FujifilmRecipe,
    b: models.FujifilmRecipe,
) -> tuple[FieldValue, ...]:
    """Return FieldValues for fields where *a* and *b* differ, with before and after values."""
    result = []
    for field in RECIPE_FIELDS:
        if getattr(a, field) != getattr(b, field):
            after = _field_display_value(field, getattr(b, field))
            before = _field_display_value(field, getattr(a, field))
            result.append(FieldValue(
                field=_FIELD_LABELS[field],
                value=after if after is not None else "—",
                before=before if before is not None else "—",
            ))
    return tuple(result)


def get_recipe_all_fields(*, recipe: models.FujifilmRecipe) -> tuple[FieldValue, ...]:
    """Return all non-None RECIPE_FIELDS of *recipe* as display-ready FieldValue tuples."""
    return _recipe_all_fields(recipe)


def get_path_deltas(*, path_ids: list[int]) -> PathDeltaResult:
    """Compute per-node field deltas for an ordered path through the recipe graph.

    *path_ids* must be ordered root → clicked node. For each recipe:
    - The root (index 0) gets all its non-None field values.
    - Each subsequent node gets only the fields that changed vs the immediately preceding node.

    *root_diffs* contains every field where the root differs from the clicked (last) node,
    using the clicked node's values — a direct comparison independent of path length.
    """
    recipes_by_id = {
        r.pk: r for r in models.FujifilmRecipe.objects.filter(pk__in=path_ids)
    }
    missing = tuple(sorted(set(path_ids) - set(recipes_by_id)))
    ordered = [recipes_by_id[i] for i in path_ids if i in recipes_by_id]

    if not ordered:
        return PathDeltaResult(root_diffs=(), path_nodes=(), missing_ids=missing)

    path_nodes: list[PathNodeDelta] = []
    for i, recipe in enumerate(ordered):
        if i == 0:
            changed = _recipe_all_fields(recipe)
        else:
            changed = _recipe_diff_fields(ordered[i - 1], recipe)
        path_nodes.append(PathNodeDelta(
            recipe_id=recipe.pk,
            label=recipe.name or f"#{recipe.pk}",
            changed_fields=changed,
        ))

    root = ordered[0]
    clicked = ordered[-1]
    root_diffs = _recipe_diff_fields(root, clicked) if len(ordered) > 1 else ()

    return PathDeltaResult(
        root_diffs=root_diffs,
        path_nodes=tuple(path_nodes),
        missing_ids=missing,
    )


@attrs.frozen
class RecipeData:
    id: int
    name: str
    film_simulation: str
    dynamic_range: str
    d_range_priority: str
    grain_roughness: str
    grain_size: str
    color_chrome_effect: str
    color_chrome_fx_blue: str
    white_balance: str
    white_balance_red: int
    white_balance_blue: int
    image_count: int
    highlight: object = None       # Decimal | None
    shadow: object = None          # Decimal | None
    color: object = None           # Decimal | None
    sharpness: object = None       # Decimal | None
    high_iso_nr: object = None     # Decimal | None
    clarity: object = None         # Decimal | None
    monochromatic_color_warm_cool: object = None    # Decimal | None
    monochromatic_color_magenta_green: object = None  # Decimal | None


def _to_recipe_data(recipe: models.FujifilmRecipe) -> RecipeData:
    return RecipeData(
        id=recipe.pk,
        name=recipe.name,
        film_simulation=recipe.film_simulation,
        dynamic_range=recipe.dynamic_range,
        d_range_priority=recipe.d_range_priority,
        grain_roughness=recipe.grain_roughness,
        grain_size=recipe.grain_size,
        color_chrome_effect=recipe.color_chrome_effect,
        color_chrome_fx_blue=recipe.color_chrome_fx_blue,
        white_balance=recipe.white_balance,
        white_balance_red=recipe.white_balance_red,
        white_balance_blue=recipe.white_balance_blue,
        image_count=getattr(recipe, "image_count", 0),
        highlight=recipe.highlight,
        shadow=recipe.shadow,
        color=recipe.color,
        sharpness=recipe.sharpness,
        high_iso_nr=recipe.high_iso_nr,
        clarity=recipe.clarity,
        monochromatic_color_warm_cool=recipe.monochromatic_color_warm_cool,
        monochromatic_color_magenta_green=recipe.monochromatic_color_magenta_green,
    )


def get_filtered_recipes(
    *,
    active_filters: Mapping[str, Sequence[str]],
) -> list[RecipeData]:
    """Return all recipes matching the given multi-valued field filters.

    *active_filters* maps recipe field names to lists of allowed values,
    e.g. ``{"film_simulation": ["Provia", "Classic Chrome"], "grain_roughness": ["Off"]}``.
    An empty list for a key is ignored (treated as no filter on that field).
    Pass an empty dict to return all recipes.

    Results are ordered by:
    1. Image count descending (most-used recipes first).
    2. Whether the recipe has a name — named recipes before unnamed.
    3. Primary key ascending as a stable tiebreaker.
    """
    qs = models.FujifilmRecipe.objects.annotate(
        image_count=Count("images"),
        has_name=Case(
            When(name="", then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ),
    )
    for field, values in active_filters.items():
        if values:
            qs = qs.filter(**{f"{field}__in": values})
    qs = qs.order_by("-image_count", "-has_name", "pk")
    return [_to_recipe_data(r) for r in qs]


@attrs.frozen
class RecipeListPage:
    page_obj: object  # Django Page; object_list contains FujifilmRecipe instances


def get_recipe_list(
    *,
    filters: Mapping[str, object],
    page_number: int | str,
    page_size: int,
) -> RecipeListPage:
    """Return a paginated list of recipes matching the given field filters.

    *filters* is a mapping of ORM field lookup kwargs (equality by default),
    e.g. ``{"film_simulation": "Provia"}``.  Pass an empty dict to list all recipes.

    Results are ordered by:
    1. Image count descending (most-used recipes first).
    2. Whether the recipe has a name — named recipes before unnamed.
    3. Primary key ascending as a stable tiebreaker.
    """
    qs = (
        models.FujifilmRecipe.objects
        .filter(**filters)
        .annotate(
            image_count=Count("images"),
            has_name=Case(
                When(name="", then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
        )
        .order_by("-image_count", "-has_name", "pk")
    )
    page_obj = django_paginator.Paginator(qs, page_size).get_page(page_number)
    return RecipeListPage(page_obj=page_obj)
