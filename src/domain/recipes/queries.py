from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

import attrs
from django.core import paginator as django_paginator
from django.db import models as db_models
from django.db.models import Case, Count, IntegerField, Max, Min, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Lower, TruncMonth

from src.data import models
from src.domain.images import filter_queries
from src.domain.recipes import normalization as recipe_normalization
from src.domain.recipes import sensors as recipe_sensors
from src.domain.recipes.constants import FILM_SIM_LOGO, MONOCHROMATIC_FILM_SIMULATIONS
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


DECIMAL_FIELDS: frozenset[str] = frozenset({
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


def decimal_str(value: object) -> str:
    """
    Convert a non-null Decimal DB value to a signed string (e.g. Decimal('1.5') → '+1.5').
    """
    n = float(value)  # type: ignore[arg-type]
    v: int | float = int(n) if n == int(n) else n
    return f"+{v}" if v > 0 else str(v)


def _decimal_str_or_none(value: object) -> str | None:
    return None if value is None else decimal_str(value)


def recipe_from_db(*, recipe: models.FujifilmRecipe) -> image_dataclasses.FujifilmRecipeData:
    """
    Convert a FujifilmRecipe DB model instance to a FujifilmRecipeData domain object.
    """
    sensors: tuple[str, ...] = tuple(
        sorted(recipe.sensors.values_list("name", flat=True))
    )
    return recipe_normalization.normalize_recipe_data(
        image_dataclasses.FujifilmRecipeData(
            name=recipe.name,
            film_simulation=recipe.film_simulation,
            d_range_priority=recipe.d_range_priority,
            grain_roughness=recipe.grain_roughness,
            color_chrome_effect=recipe.color_chrome_effect,
            color_chrome_fx_blue=recipe.color_chrome_fx_blue,
            white_balance=recipe.white_balance,
            white_balance_red=recipe.white_balance_red,
            white_balance_blue=recipe.white_balance_blue,
            sharpness=_decimal_str_or_none(recipe.sharpness) or "0",
            high_iso_nr=_decimal_str_or_none(recipe.high_iso_nr) or "0",
            clarity=_decimal_str_or_none(recipe.clarity) or "0",
            dynamic_range=recipe.dynamic_range or None,
            grain_size=recipe.grain_size or None,
            highlight=_decimal_str_or_none(recipe.highlight),
            shadow=_decimal_str_or_none(recipe.shadow),
            color=_decimal_str_or_none(recipe.color),
            monochromatic_color_warm_cool=_decimal_str_or_none(recipe.monochromatic_color_warm_cool),
            monochromatic_color_magenta_green=_decimal_str_or_none(recipe.monochromatic_color_magenta_green),
            sensors=sensors,
            description=recipe.description,
        )
    )


@attrs.frozen
class RecipeUsageStats:
    recipe_id: int
    photo_count: int
    first_used: datetime | None
    last_used: datetime | None


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
    """
    Return the most-used recipe for the given film simulation.

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
    """
    Return all recipes whose film_simulation matches exactly.
    """
    return list(models.FujifilmRecipe.objects.filter(film_simulation=film_simulation))


def get_distinct_film_simulations() -> list[str]:
    """
    Return all distinct film_simulation values present in the recipe table, sorted.
    """
    return list(
        models.FujifilmRecipe.objects
        .values_list("film_simulation", flat=True)
        .distinct()
        .order_by("film_simulation")
    )


def get_film_simulations_with_multiple_recipes() -> list[str]:
    """
    Return film simulations that have more than one recipe, sorted.

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
    """
    Return a mapping of recipe_id → image count for all recipes with the given film sim.
    """
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
    """
    Return a mapping of recipe_id → image count for the given recipe PKs.
    """
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
    """
    Fetch recipes, usage stats, and monthly breakdowns for the given IDs.

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


# Shown where a recipe has no value for a field the other recipe does have.
EMPTY_VALUE = "—"  # em dash


def _field_display_value(field: str, raw: object) -> str | None:
    """
    Return a display-ready string for *field*'s value, or None to omit it.
    """
    if raw is None:
        return None
    if field in DECIMAL_FIELDS:
        return decimal_str(raw)
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
    """
    Return FieldValues for fields where *a* and *b* differ, with before and after values.
    """
    result = []
    for field in RECIPE_FIELDS:
        if getattr(a, field) != getattr(b, field):
            after = _field_display_value(field, getattr(b, field))
            before = _field_display_value(field, getattr(a, field))
            result.append(FieldValue(
                field=_FIELD_LABELS[field],
                value=after if after is not None else EMPTY_VALUE,
                before=before if before is not None else EMPTY_VALUE,
            ))
    return tuple(result)


def get_recipe_all_fields(*, recipe: models.FujifilmRecipe) -> tuple[FieldValue, ...]:
    """
    Return all non-None RECIPE_FIELDS of *recipe* as display-ready FieldValue tuples.
    """
    return _recipe_all_fields(recipe)


# Recipe fields arranged into the categories the comparison panel renders.
# Every entry of RECIPE_FIELDS must appear exactly once; a test enforces it, so
# a newly added field cannot be silently dropped from the panel.
PROPERTY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Basic", ("film_simulation",)),
    ("Dynamic Range", ("dynamic_range", "d_range_priority")),
    ("Grain", ("grain_roughness", "grain_size")),
    ("Color Chrome", ("color_chrome_effect", "color_chrome_fx_blue")),
    ("White Balance", ("white_balance", "white_balance_red", "white_balance_blue")),
    ("Tone & Color", ("highlight", "shadow", "color")),
    ("Detail", ("sharpness", "high_iso_nr", "clarity")),
    ("Monochrome", ("monochromatic_color_warm_cool", "monochromatic_color_magenta_green")),
)


@attrs.frozen
class PropertyRow:
    key: str  # the model field name, so callers can map an icon to it
    label: str
    reference_value: str
    # None when only one recipe is being shown and there is nothing to compare.
    compared_value: str | None
    changed: bool


@attrs.frozen
class PropertyGroup:
    label: str
    rows: tuple[PropertyRow, ...]

    @property
    def changed_count(self) -> int:
        return sum(1 for row in self.rows if row.changed)


@attrs.frozen
class RecipePropertyView:
    groups: tuple[PropertyGroup, ...]
    changed_count: int


def _build_property_view(
    *,
    reference: models.FujifilmRecipe,
    compared: models.FujifilmRecipe | None,
) -> RecipePropertyView:
    """
    Group *reference*'s fields, optionally paired with *compared*'s values.

    A field is omitted when neither recipe has a value for it, and a group with
    no remaining rows is dropped. That is what keeps the Monochrome group out of
    a colour recipe's panel without special-casing it.
    """
    groups: list[PropertyGroup] = []
    changed_count = 0

    for label, fields in PROPERTY_GROUPS:
        rows: list[PropertyRow] = []
        for field in fields:
            reference_value = _field_display_value(field, getattr(reference, field))
            compared_value = (
                _field_display_value(field, getattr(compared, field))
                if compared is not None
                else None
            )
            if reference_value is None and compared_value is None:
                continue

            changed = compared is not None and getattr(reference, field) != getattr(compared, field)
            if changed:
                changed_count += 1

            rows.append(PropertyRow(
                key=field,
                label=_FIELD_LABELS[field],
                reference_value=reference_value if reference_value is not None else EMPTY_VALUE,
                compared_value=(
                    (compared_value if compared_value is not None else EMPTY_VALUE)
                    if compared is not None
                    else None
                ),
                changed=changed,
            ))

        if rows:
            groups.append(PropertyGroup(label=label, rows=tuple(rows)))

    return RecipePropertyView(groups=tuple(groups), changed_count=changed_count)


def get_recipe_properties(*, recipe: models.FujifilmRecipe) -> RecipePropertyView:
    """
    Return *recipe*'s fields grouped into display categories, one value per row.

    Used when a reference recipe is being inspected on its own, so nothing is
    marked as changed and `compared_value` is None throughout.
    """
    return _build_property_view(reference=recipe, compared=None)


def get_recipe_property_comparison(
    *,
    reference: models.FujifilmRecipe,
    compared: models.FujifilmRecipe,
) -> RecipePropertyView:
    """
    Return every field of both recipes, grouped, with the pair of values and a
    changed flag on each row.

    Unlike `get_path_deltas`, which reports only what differs, this keeps the
    unchanged rows so the panel can show the full recipe and filter down to the
    changes on demand.
    """
    return _build_property_view(reference=reference, compared=compared)


def get_path_deltas(*, path_ids: list[int]) -> PathDeltaResult:
    """
    Compute per-node field deltas for an ordered path through the recipe graph.

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
    highlight: object = None                       # Decimal | None
    shadow: object = None                          # Decimal | None
    color: object = None                           # Decimal | None
    sharpness: object = None                       # Decimal | None
    high_iso_nr: object = None                     # Decimal | None
    clarity: object = None                         # Decimal | None
    monochromatic_color_warm_cool: object = None   # Decimal | None
    monochromatic_color_magenta_green: object = None  # Decimal | None
    cover_image_id: int | None = None              # most popular image for card background
    film_sim_logo_filename: str | None = None      # from FILM_SIM_LOGO mapping
    # Populated only by ``get_recipe_detail`` (one DB hit for the M2M plus a
    # pure lookup for bodies). Other producers default these to empty tuples
    # so list-view callers don't pay the extra query per recipe.
    sensors: tuple[str, ...] = ()
    bodies: tuple[str, ...] = ()


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
        cover_image_id=recipe.cover_image_id or getattr(recipe, "fallback_cover_image_id", None),
        film_sim_logo_filename=FILM_SIM_LOGO.get(recipe.film_simulation),
    )


def recipe_is_editable(*, recipe_id: int) -> bool:
    """
    Return True if the recipe has no associated Images.

    When True, all fields (including camera settings) can be modified.
    When False, only metadata fields (name, description) remain writable;
    settings fields are protected.
    """
    return not models.Image.objects.filter(fujifilm_recipe_id=recipe_id).exists()


@attrs.frozen
class RecipeDetailContext:
    recipe: RecipeData
    is_monochromatic: bool
    settings_editable: bool


def get_recipe_detail(*, recipe_id: int) -> RecipeDetailContext:
    """
    Return the recipe with the given primary key as a RecipeDetailContext.

    The ``cover_image_id`` on the returned ``RecipeData`` is the recipe's explicit
    cover image if one has been set, otherwise the highest-rated image associated
    with the recipe (by rating desc, taken_at desc, id asc).

    :raises models.FujifilmRecipe.DoesNotExist: If no recipe with *recipe_id* exists.
    """
    cover_subquery = (
        models.Image.objects.filter(fujifilm_recipe=OuterRef("pk"))
        .order_by("-rating", "-taken_at", "id")
        .values("id")[:1]
    )
    recipe = (
        models.FujifilmRecipe.objects.annotate(
            image_count=Count("images"),
            fallback_cover_image_id=Subquery(cover_subquery),
        ).get(pk=recipe_id)
    )
    sensors = tuple(sorted(recipe.sensors.values_list("name", flat=True)))
    bodies = recipe_sensors.cameras_for_sensors(sensors)
    recipe_data = attrs.evolve(
        _to_recipe_data(recipe), sensors=sensors, bodies=bodies
    )
    return RecipeDetailContext(
        recipe=recipe_data,
        is_monochromatic=recipe_data.film_simulation in MONOCHROMATIC_FILM_SIMULATIONS,
        settings_editable=recipe_is_editable(recipe_id=recipe_id),
    )


def get_filtered_recipes(
    *,
    active_filters: Mapping[str, Sequence[str]],
    name_search: str = "",
) -> list[RecipeData]:
    """
    Return all recipes matching the given multi-valued field filters.

    *active_filters* maps recipe field names to lists of allowed values,
    e.g. ``{"film_simulation": ["Provia", "Classic Chrome"], "grain_roughness": ["Off"]}``.
    An empty list for a key is ignored (treated as no filter on that field).
    Pass an empty dict to return all recipes.

    *name_search* is an optional case-insensitive substring filter on the recipe name.

    Results are ordered by:
    1. Whether the recipe has a name — named recipes before unnamed.
    2. Image count descending (most-used recipes first).
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
    if name_search:
        qs = qs.filter(Q(name__icontains=name_search))
    qs = qs.order_by("-has_name", "-image_count", "pk")
    return [_to_recipe_data(r) for r in qs]


def get_recipe_sidebar_filter_options(
    *,
    active_filters: Mapping[str, Sequence[str]],
    name_search: str = "",
) -> dict[str, dict[str, object]]:
    """
    Return faceted filter options for the recipe explorer sidebar.

    For each field in RECIPE_FILTER_FIELDS, counts the number of recipes matching
    that field value while applying all OTHER active filters (faceted search).
    Counts represent recipes, not images.

    *name_search* is applied to all facet counts so they reflect the current search.
    """
    sensor_selected: Sequence[str] = active_filters.get("sensors", [])
    sensor_base_qs = models.FujifilmRecipe.objects.all()
    if name_search:
        sensor_base_qs = sensor_base_qs.filter(Q(name__icontains=name_search))
    for other_field, values in active_filters.items():
        if other_field == "sensors" or not values:
            continue
        sensor_base_qs = sensor_base_qs.filter(**{f"{other_field}__in": values})

    sensor_counts: dict[str, int] = {
        row["sensors__name"]: row["count"]
        for row in (
            sensor_base_qs
            .filter(sensors__isnull=False)
            .values("sensors__name")
            .annotate(count=Count("pk", distinct=True))
        )
    }
    no_sensor_count = sensor_base_qs.filter(sensors__isnull=True).count()
    if no_sensor_count:
        sensor_counts[filter_queries.SENSOR_NONE_VALUE] = no_sensor_count

    all_sensor_values: set[str] = set(sensor_counts) | set(sensor_selected)
    sorted_sensor_values = sorted(
        all_sensor_values,
        key=lambda v: (0 if v in sensor_counts else 1, 1 if v == filter_queries.SENSOR_NONE_VALUE else 0, v),
    )
    _sensor_section: dict[str, object] = {
        "label": "Sensor",
        "options": [
            {
                "value": v,
                "label": filter_queries.SENSOR_NONE_LABEL if v == filter_queries.SENSOR_NONE_VALUE else v,
                "count": sensor_counts.get(v, 0),
                "available": v in sensor_counts,
                "selected": v in sensor_selected,
            }
            for v in sorted_sensor_values
        ],
        "selected": sensor_selected,
    }

    result: dict[str, dict[str, object]] = {}
    for field, label in filter_queries.RECIPE_FILTER_FIELDS:
        model_field = models.FujifilmRecipe._meta.get_field(field)
        is_numeric = isinstance(model_field, (db_models.IntegerField, db_models.DecimalField))

        base_qs = models.FujifilmRecipe.objects.all()
        if name_search:
            base_qs = base_qs.filter(Q(name__icontains=name_search))
        for other_field, values in active_filters.items():
            if other_field == field or not values:
                continue
            if other_field == "sensors":
                base_qs = filter_queries.filter_recipes_by_sensors(base_qs, values)
            else:
                base_qs = base_qs.filter(**{f"{other_field}__in": values})
        if is_numeric:
            base_qs = base_qs.exclude(**{f"{field}__isnull": True})
        else:
            base_qs = base_qs.exclude(**{field: ""})

        available_counts: dict[str, int] = {
            filter_queries.decimal_filter_str(row[field]): row["count"]
            for row in base_qs.values(field).annotate(count=Count("pk"))
        }
        selected_values = active_filters.get(field, [])
        all_values: set[str] = set(available_counts) | set(selected_values)

        if is_numeric:
            def _sort_key(v: str) -> tuple[int, float]:
                try:
                    return (0 if v in available_counts else 1, float(v))
                except (ValueError, TypeError):
                    return (0 if v in available_counts else 1, 0)
            sorted_values = sorted(all_values, key=_sort_key)
        else:
            sorted_values = sorted(
                all_values,
                key=lambda v: (0 if v in available_counts else 1, v),
            )

        result[field] = {
            "label": label,
            "options": [
                {
                    "value": v,
                    "count": available_counts.get(v, 0),
                    "available": v in available_counts,
                    "selected": v in selected_values,
                }
                for v in sorted_values
            ],
            "selected": selected_values,
        }
        if field == "film_simulation":
            result["sensors"] = _sensor_section

    return result


@attrs.frozen
class RecipeGalleryPage:
    items: tuple[RecipeData, ...]
    has_next: bool
    next_page_number: int | None  # None when has_next is False
    has_previous: bool
    number: int


@attrs.frozen
class RecipeGalleryData:
    page_obj: RecipeGalleryPage
    sidebar_options: dict[str, dict[str, object]]


def get_recipe_gallery_data(
    *,
    active_filters: Mapping[str, Sequence[str]],
    name_search: str = "",
    page_number: int | str,
    page_size: int,
) -> RecipeGalleryData:
    """
    Return all data needed to render the recipe explorer page.

    Filters recipes by *active_filters* (multi-valued field lookups), annotates
    each with its image count and the ID of its most popular image (for the card
    background), paginates, and returns domain value objects — no ORM models escape.

    *name_search* is an optional case-insensitive substring filter on the recipe name.

    Results are ordered by:
    1. Whether the recipe has a name — named recipes before unnamed.
    2. Image count descending (most-used recipes first).
    3. Primary key ascending as a stable tiebreaker.
    """
    cover_subquery = (
        models.Image.objects
        .filter(fujifilm_recipe=OuterRef("pk"))
        .order_by("-rating", "-taken_at", "id")
        .values("id")[:1]
    )
    qs = models.FujifilmRecipe.objects.annotate(
        image_count=Count("images"),
        has_name=Case(
            When(name="", then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ),
        fallback_cover_image_id=Subquery(cover_subquery),
    )
    sensor_values = active_filters.get("sensors", [])
    for field, values in active_filters.items():
        if not values or field == "sensors":
            continue
        qs = qs.filter(**{f"{field}__in": values})
    if sensor_values:
        matching_pks = filter_queries.filter_recipes_by_sensors(
            models.FujifilmRecipe.objects.all(), sensor_values
        ).values("pk")
        qs = qs.filter(pk__in=matching_pks)
    if name_search:
        qs = qs.filter(Q(name__icontains=name_search))
    qs = qs.order_by("-has_name", "-image_count", "pk")

    raw_page = django_paginator.Paginator(qs, page_size).get_page(page_number)
    page = RecipeGalleryPage(
        items=tuple(_to_recipe_data(r) for r in raw_page.object_list),
        has_next=raw_page.has_next(),
        next_page_number=raw_page.next_page_number() if raw_page.has_next() else None,
        has_previous=raw_page.has_previous(),
        number=raw_page.number,
    )
    return RecipeGalleryData(
        page_obj=page,
        sidebar_options=get_recipe_sidebar_filter_options(active_filters=active_filters, name_search=name_search),
    )


@attrs.frozen
class RecipeNotInVersionLineError(Exception):
    recipe_id: int


@attrs.frozen
class VersionLineRecipe:
    recipe_id: int
    position: int
    label: str
    name: str
    is_current: bool


@attrs.frozen
class VersionLineResult:
    recipes: tuple[VersionLineRecipe, ...]


def get_recipes_in_version_line(*, recipe_id: int) -> VersionLineResult:
    """
    Return all recipes belonging to the same VERSION_LINE group as recipe_id.

    :raises RecipeNotInVersionLineError: If recipe_id has no VERSION_LINE group member.
    """
    try:
        member = models.RecipeGroupMember.objects.get(
            recipe_id=recipe_id,
            group_type=models.RecipeGroup.GROUP_TYPE_VERSION_LINE,
        )
    except models.RecipeGroupMember.DoesNotExist:
        raise RecipeNotInVersionLineError(recipe_id=recipe_id)

    members = (
        models.RecipeGroupMember.objects
        .filter(group_id=member.group_id)
        .select_related("recipe")
        .order_by("position")
    )
    version_recipes: list[VersionLineRecipe] = []
    for m in members:
        assert m.position is not None, "VERSION_LINE members always have a position"
        version_recipes.append(VersionLineRecipe(
            recipe_id=m.recipe_id,
            position=m.position,
            label=f"v{m.position}",
            name=m.recipe.name,
            is_current=(m.recipe_id == recipe_id),
        ))
    recipes = tuple(version_recipes)
    return VersionLineResult(recipes=recipes)


_MOVE_SEARCH_LIMIT = 30


@attrs.frozen
class RecipeMoveCandidate:
    recipe_id: int
    name: str
    version_label: str
    group_id: int
    group_member_count: int


def search_recipes_for_version_line_move(
    *,
    source_recipe_id: int,
    name_search: str,
) -> tuple[RecipeMoveCandidate, ...]:
    """
    Return up to 30 recipes from other VERSION_LINE groups whose name contains name_search.

    Excludes all recipes in the same group as source_recipe_id.
    Returns an empty tuple when name_search is blank.

    :raises RecipeNotInVersionLineError: If source_recipe_id has no VERSION_LINE membership.
    """
    if not name_search.strip():
        return ()

    try:
        source_member = models.RecipeGroupMember.objects.get(
            recipe_id=source_recipe_id,
            group_type=models.RecipeGroup.GROUP_TYPE_VERSION_LINE,
        )
    except models.RecipeGroupMember.DoesNotExist:
        raise RecipeNotInVersionLineError(recipe_id=source_recipe_id)

    source_group_id = source_member.group_id

    member_count_sq = (
        models.RecipeGroupMember.objects
        .filter(group_id=OuterRef("group_id"))
        .values("group_id")
        .annotate(cnt=Count("pk"))
        .values("cnt")
    )

    members = (
        models.RecipeGroupMember.objects
        .filter(
            group_type=models.RecipeGroup.GROUP_TYPE_VERSION_LINE,
            recipe__name__icontains=name_search,
        )
        .exclude(group_id=source_group_id)
        .select_related("recipe")
        .annotate(group_member_count=Subquery(member_count_sq))
        .order_by("recipe__name")
    )[:_MOVE_SEARCH_LIMIT]

    return tuple(
        RecipeMoveCandidate(
            recipe_id=m.recipe_id,
            name=m.recipe.name,
            version_label=f"v{m.position}",
            group_id=m.group_id,
            group_member_count=m.group_member_count,
        )
        for m in members
    )


@attrs.frozen
class VersionLineGroupNotFoundError(Exception):
    group_id: int


def get_simulated_version_line_members(
    *,
    source_recipe_id: int,
    destination_group_id: int,
    position: int | None = None,
) -> VersionLineResult:
    """
    Return a VersionLineResult showing the destination group after the move (read-only).

    The source recipe is inserted at position (default: last) and marked is_current=True.
    All destination members retain is_current=False.

    :raises VersionLineGroupNotFoundError: If destination_group_id has no members.
    """
    first_member = (
        models.RecipeGroupMember.objects
        .filter(group_id=destination_group_id)
        .order_by("position")
        .first()
    )
    if first_member is None:
        raise VersionLineGroupNotFoundError(group_id=destination_group_id)

    destination_result = get_recipes_in_version_line(recipe_id=first_member.recipe_id)
    destination_count = len(destination_result.recipes)
    target_position = destination_count + 1 if position is None else position

    source_name: str = (
        models.FujifilmRecipe.objects
        .values_list("name", flat=True)
        .get(pk=source_recipe_id)
    )
    source_recipe = VersionLineRecipe(
        recipe_id=source_recipe_id,
        position=target_position,
        label=f"v{target_position}",
        name=source_name,
        is_current=True,
    )

    updated: list[VersionLineRecipe] = []
    for vr in destination_result.recipes:
        new_pos = vr.position + 1 if vr.position >= target_position else vr.position
        updated.append(attrs.evolve(vr, position=new_pos, label=f"v{new_pos}", is_current=False))
    updated.append(source_recipe)
    updated.sort(key=lambda r: r.position)

    return VersionLineResult(recipes=tuple(updated))


@attrs.frozen
class RecipeListPage:
    page_obj: object  # Django Page; object_list contains FujifilmRecipe instances


def get_recipe_list(
    *,
    filters: Mapping[str, object],
    page_number: int | str,
    page_size: int,
) -> RecipeListPage:
    """
    Return a paginated list of recipes matching the given field filters.

    *filters* is a mapping of ORM field lookup kwargs (equality by default),
    e.g. ``{"film_simulation": "Provia"}``.  Pass an empty dict to list all recipes.

    Results are ordered by:
    1. Whether the recipe has a name — named recipes before unnamed.
    2. Image count descending (most-used recipes first).
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
        .order_by("-has_name", "-image_count", "pk")
    )
    page_obj = django_paginator.Paginator(qs, page_size).get_page(page_number)
    return RecipeListPage(page_obj=page_obj)


# ----------------------------------------------------------------------------
# Recipe collections
# ----------------------------------------------------------------------------

# Best-rated images shown in a collection card's mosaic before it falls back to
# the film-simulation logo legend.
_COLLECTION_MOSAIC_IMAGE_LIMIT = 4

# Cap on the recipe list offered in the collection editor's add panel.
_COLLECTION_EDITOR_SEARCH_LIMIT = 50


@attrs.frozen
class CollectionNotFound(Exception):
    collection_id: int


@attrs.frozen
class CollectionFilmSim:
    film_simulation: str
    logo_filename: str | None


@attrs.frozen
class CollectionSummaryData:
    id: int
    name: str
    recipe_count: int
    film_sims: tuple[CollectionFilmSim, ...]
    mosaic_image_ids: tuple[int, ...]


def get_collection_summaries(
    *,
    name_search: str = "",
    recipe_name_search: str = "",
    film_simulations: Sequence[str] = (),
) -> list[CollectionSummaryData]:
    """
    Return collection cards matching the given filters, ordered by name.

    A collection matches when its name contains *name_search*, it holds a recipe
    whose name contains *recipe_name_search*, and it holds a recipe of one of
    *film_simulations* — each filter is applied only when non-empty. Every card
    carries its recipe count, the distinct film simulations of its recipes (most
    frequent first, with logo filenames) for the legend, and up to four
    best-rated images across its recipes for the mosaic. A card with no images
    yet returns an empty ``mosaic_image_ids`` so the caller renders the
    logo-only fallback.
    """
    groups = models.RecipeGroup.objects.filter(
        group_type=models.RecipeGroup.GROUP_TYPE_COLLECTION,
    )
    if name_search:
        groups = groups.filter(name__icontains=name_search)
    if recipe_name_search:
        groups = groups.filter(members__recipe__name__icontains=recipe_name_search)
    if film_simulations:
        groups = groups.filter(members__recipe__film_simulation__in=list(film_simulations))
    group_rows = list(groups.distinct().order_by(Lower("name"), "pk").values("pk", "name"))
    if not group_rows:
        return []

    group_ids = [row["pk"] for row in group_rows]
    name_by_id = {row["pk"]: row["name"] for row in group_rows}

    members = (
        models.RecipeGroupMember.objects
        .filter(group_id__in=group_ids, group_type=models.RecipeGroup.GROUP_TYPE_COLLECTION)
        .select_related("recipe")
        .order_by("group_id", "position", "pk")
    )
    members_by_group: dict[int, list[models.RecipeGroupMember]] = {}
    for member in members:
        members_by_group.setdefault(member.group_id, []).append(member)

    top_image_by_recipe = _top_image_by_recipe(
        recipe_ids={member.recipe_id for member in members}
    )

    summaries: list[CollectionSummaryData] = []
    for group_id in group_ids:
        group_members = members_by_group.get(group_id, [])
        summaries.append(
            CollectionSummaryData(
                id=group_id,
                name=name_by_id[group_id],
                recipe_count=len(group_members),
                film_sims=_collection_film_sims(group_members),
                mosaic_image_ids=_collection_mosaic(group_members, top_image_by_recipe),
            )
        )
    return summaries


def _top_image_by_recipe(*, recipe_ids: set[int]) -> dict[int, tuple[int, float]]:
    """
    Map each recipe id to its best image as ``(image_id, rating)``.

    The best image is the highest-rated, breaking ties by most recent then id —
    the same ordering the explorer uses for card backgrounds. Recipes with no
    image are absent from the mapping.
    """
    if not recipe_ids:
        return {}
    top_id_sq = (
        models.Image.objects.filter(fujifilm_recipe=OuterRef("pk"))
        .order_by("-rating", "-taken_at", "id").values("id")[:1]
    )
    top_rating_sq = (
        models.Image.objects.filter(fujifilm_recipe=OuterRef("pk"))
        .order_by("-rating", "-taken_at", "id").values("rating")[:1]
    )
    result: dict[int, tuple[int, float]] = {}
    for row in (
        models.FujifilmRecipe.objects.filter(pk__in=recipe_ids)
        .annotate(top_image_id=Subquery(top_id_sq), top_rating=Subquery(top_rating_sq))
        .values("pk", "top_image_id", "top_rating")
    ):
        if row["top_image_id"] is not None:
            result[row["pk"]] = (row["top_image_id"], float(row["top_rating"] or 0))
    return result


def _collection_film_sims(
    members: Sequence[models.RecipeGroupMember],
) -> tuple[CollectionFilmSim, ...]:
    counts: dict[str, int] = {}
    for member in members:
        film_sim = member.recipe.film_simulation
        counts[film_sim] = counts.get(film_sim, 0) + 1
    return tuple(
        CollectionFilmSim(film_simulation=film_sim, logo_filename=FILM_SIM_LOGO.get(film_sim))
        for film_sim in sorted(counts, key=lambda fs: (-counts[fs], fs))
    )


def _collection_mosaic(
    members: Sequence[models.RecipeGroupMember],
    top_image_by_recipe: Mapping[int, tuple[int, float]],
) -> tuple[int, ...]:
    rated: list[tuple[int, float]] = [
        top_image_by_recipe[member.recipe_id]
        for member in members
        if member.recipe_id in top_image_by_recipe
    ]
    rated.sort(key=lambda pair: pair[1], reverse=True)
    mosaic: list[int] = []
    seen: set[int] = set()
    for image_id, _rating in rated:
        if image_id in seen:
            continue
        seen.add(image_id)
        mosaic.append(image_id)
        if len(mosaic) >= _COLLECTION_MOSAIC_IMAGE_LIMIT:
            break
    return tuple(mosaic)


@attrs.frozen
class CollectionFilmSimFacet:
    value: str
    count: int
    available: bool
    selected: bool


@attrs.frozen
class CollectionFilterOptions:
    film_simulations: tuple[CollectionFilmSimFacet, ...]


def get_collection_filter_options(
    *, selected_film_simulations: Sequence[str] = (),
) -> CollectionFilterOptions:
    """
    Return the film-simulation facet for the collections sidebar.

    Each option's count is the number of distinct collections holding at least
    one recipe of that film simulation. A currently selected value with no
    matches is kept in the list, marked unavailable, so it can be unticked.
    """
    counts = {
        row["recipe__film_simulation"]: row["count"]
        for row in (
            models.RecipeGroupMember.objects
            .filter(group_type=models.RecipeGroup.GROUP_TYPE_COLLECTION)
            .values("recipe__film_simulation")
            .annotate(count=Count("group_id", distinct=True))
        )
    }
    selected = set(selected_film_simulations)
    values = sorted(set(counts) | selected, key=lambda v: (0 if v in counts else 1, v))
    return CollectionFilterOptions(
        film_simulations=tuple(
            CollectionFilmSimFacet(
                value=value,
                count=counts.get(value, 0),
                available=value in counts,
                selected=value in selected,
            )
            for value in values
        )
    )


@attrs.frozen
class CollectionMemberData:
    recipe_id: int
    name: str
    film_simulation: str
    film_sim_logo_filename: str | None
    image_count: int
    position: int


@attrs.frozen
class CollectionDetailData:
    id: int
    name: str
    members: tuple[CollectionMemberData, ...]


def get_collection_detail(*, collection_id: int) -> CollectionDetailData:
    """
    Return the collection with its recipes in stored order.

    :raises CollectionNotFound: If no collection with *collection_id* exists.
    """
    try:
        group = models.RecipeGroup.objects.get(
            pk=collection_id, group_type=models.RecipeGroup.GROUP_TYPE_COLLECTION,
        )
    except models.RecipeGroup.DoesNotExist:
        raise CollectionNotFound(collection_id=collection_id)

    members = (
        models.RecipeGroupMember.objects
        .filter(group_id=group.pk)
        .select_related("recipe")
        .annotate(recipe_image_count=Count("recipe__images"))
        .order_by("position", "pk")
    )
    member_data = tuple(
        CollectionMemberData(
            recipe_id=member.recipe_id,
            name=member.recipe.name,
            film_simulation=member.recipe.film_simulation,
            film_sim_logo_filename=FILM_SIM_LOGO.get(member.recipe.film_simulation),
            image_count=member.recipe_image_count,
            position=member.position if member.position is not None else 0,
        )
        for member in members
    )
    return CollectionDetailData(id=group.pk, name=group.name, members=member_data)


@attrs.frozen
class RecipeOptionData:
    recipe_id: int
    name: str
    film_simulation: str
    film_sim_logo_filename: str | None
    image_count: int
    in_collection: bool


def get_recipes_for_collection_editor(
    *, name_search: str = "", in_collection_id: int | None = None,
) -> list[RecipeOptionData]:
    """
    Return recipes for the collection editor's add panel, most-used first.

    When *in_collection_id* is given, recipes already in that collection are
    flagged with ``in_collection=True`` so the panel can mark them as added.
    """
    in_collection_ids: set[int] = set()
    if in_collection_id is not None:
        in_collection_ids = set(
            models.RecipeGroupMember.objects
            .filter(
                group_id=in_collection_id,
                group_type=models.RecipeGroup.GROUP_TYPE_COLLECTION,
            )
            .values_list("recipe_id", flat=True)
        )

    qs = models.FujifilmRecipe.objects.annotate(
        image_count=Count("images"),
        has_name=Case(
            When(name="", then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ),
    )
    if name_search:
        qs = qs.filter(Q(name__icontains=name_search))
    qs = qs.order_by("-has_name", "-image_count", "pk")[:_COLLECTION_EDITOR_SEARCH_LIMIT]

    return [
        RecipeOptionData(
            recipe_id=recipe.pk,
            name=recipe.name,
            film_simulation=recipe.film_simulation,
            film_sim_logo_filename=FILM_SIM_LOGO.get(recipe.film_simulation),
            image_count=recipe.image_count,
            in_collection=recipe.pk in in_collection_ids,
        )
        for recipe in qs
    ]


def get_recipe_editor_options(*, recipe_ids: Sequence[int]) -> list[RecipeOptionData]:
    """
    Return option rows for exactly *recipe_ids*, in that order (``in_collection``
    always True). Unknown or repeated ids are skipped. Used to rebuild the
    ordered selection in the collection editor, e.g. after a form error.
    """
    by_id = {
        recipe.pk: recipe
        for recipe in (
            models.FujifilmRecipe.objects
            .filter(pk__in=list(recipe_ids))
            .annotate(image_count=Count("images"))
        )
    }
    ordered: list[RecipeOptionData] = []
    seen: set[int] = set()
    for recipe_id in recipe_ids:
        if recipe_id in seen or recipe_id not in by_id:
            continue
        seen.add(recipe_id)
        recipe = by_id[recipe_id]
        ordered.append(
            RecipeOptionData(
                recipe_id=recipe.pk,
                name=recipe.name,
                film_simulation=recipe.film_simulation,
                film_sim_logo_filename=FILM_SIM_LOGO.get(recipe.film_simulation),
                image_count=recipe.image_count,
                in_collection=True,
            )
        )
    return ordered
