from __future__ import annotations

import attrs
from django.db.models import Count, Max, Min
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
