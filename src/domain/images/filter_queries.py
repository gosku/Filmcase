import attrs
from collections.abc import Mapping, Sequence

from django.core import paginator as django_paginator
from django.db import models as db_models

from src.data import models

_NOTABLE_RECIPE_MIN_IMAGES = 50

SENSOR_NONE_VALUE = "none"
SENSOR_NONE_LABEL = "Not assigned"


def decimal_filter_str(value: object) -> str:
    """Convert a DB Decimal value to a filter string, dropping redundant .0 suffixes."""
    try:
        n = float(value)  # type: ignore[arg-type]
        return str(int(n)) if n == int(n) else str(value)
    except (TypeError, ValueError):
        return str(value)


def filter_images_by_sensors(
    qs: db_models.QuerySet[models.Image],
    sensor_values: Sequence[str],
) -> db_models.QuerySet[models.Image]:
    named = [v for v in sensor_values if v != SENSOR_NONE_VALUE]
    include_none = SENSOR_NONE_VALUE in sensor_values
    if named and include_none:
        return qs.filter(
            db_models.Q(fujifilm_recipe__sensors__name__in=named)
            | db_models.Q(fujifilm_recipe__sensors__isnull=True)
        ).distinct()
    if named:
        return qs.filter(fujifilm_recipe__sensors__name__in=named).distinct()
    if include_none:
        return qs.filter(fujifilm_recipe__sensors__isnull=True)
    return qs


def filter_recipes_by_sensors(
    qs: db_models.QuerySet[models.FujifilmRecipe],
    sensor_values: Sequence[str],
) -> db_models.QuerySet[models.FujifilmRecipe]:
    named = [v for v in sensor_values if v != SENSOR_NONE_VALUE]
    include_none = SENSOR_NONE_VALUE in sensor_values
    if named and include_none:
        return qs.filter(
            db_models.Q(sensors__name__in=named) | db_models.Q(sensors__isnull=True)
        ).distinct()
    if named:
        return qs.filter(sensors__name__in=named).distinct()
    if include_none:
        return qs.filter(sensors__isnull=True)
    return qs


RECIPE_FILTER_FIELDS = [
    ("film_simulation", "Film Simulation"),
    ("dynamic_range", "Dynamic Range"),
    ("d_range_priority", "D-Range Priority"),
    ("grain_roughness", "Grain Roughness"),
    ("grain_size", "Grain Size"),
    ("color_chrome_effect", "Color Chrome Effect"),
    ("color_chrome_fx_blue", "Color Chrome FX Blue"),
    ("white_balance", "White Balance"),
    ("white_balance_red", "WB Red"),
    ("white_balance_blue", "WB Blue"),
    ("highlight", "Highlight"),
    ("shadow", "Shadow"),
    ("color", "Color"),
    ("sharpness", "Sharpness"),
    ("high_iso_nr", "High ISO NR"),
    ("clarity", "Clarity"),
]


def get_sidebar_filter_options(
    active_filters: Mapping[str, Sequence[str]],
) -> dict[str, dict[str, object]]:
    """
    Compute faceted sidebar options for all recipe filter fields.

    For each field, available values and their image counts are derived
    by applying all OTHER active filters — so selecting a value in one field
    narrows the choices shown in every other field.

    Values that are currently selected but no longer available (because other
    filters have excluded them) are still included in the result with
    available=False and count=0, so the UI can render them as greyed-out.

    Args:
        active_filters: mapping of field name → list of selected string values
                        (URL params, always strings even for IntegerFields).

    Returns:
        Dict keyed by field name, each entry:
            label    – human-readable field name
            options  – list of dicts: value, count, available, selected
            selected – list of currently selected string values for this field
    """
    sensor_selected: Sequence[str] = active_filters.get("sensors", [])
    sensor_base_qs = models.Image.objects.filter(fujifilm_recipe__isnull=False)
    recipe_ids = active_filters.get("recipe_id", [])
    if recipe_ids:
        sensor_base_qs = sensor_base_qs.filter(fujifilm_recipe_id__in=recipe_ids)
    for other_field, values in active_filters.items():
        if other_field in ("recipe_id", "sensors") or not values:
            continue
        sensor_base_qs = sensor_base_qs.filter(**{f"fujifilm_recipe__{other_field}__in": values})

    sensor_counts: dict[str, int] = {
        row["fujifilm_recipe__sensors__name"]: row["count"]
        for row in (
            sensor_base_qs
            .filter(fujifilm_recipe__sensors__isnull=False)
            .values("fujifilm_recipe__sensors__name")
            .annotate(count=db_models.Count("id", distinct=True))
        )
    }
    no_sensor_count = sensor_base_qs.filter(fujifilm_recipe__sensors__isnull=True).count()
    if no_sensor_count:
        sensor_counts[SENSOR_NONE_VALUE] = no_sensor_count

    all_sensor_values: set[str] = set(sensor_counts) | set(sensor_selected)
    sorted_sensor_values = sorted(
        all_sensor_values,
        key=lambda v: (0 if v in sensor_counts else 1, 1 if v == SENSOR_NONE_VALUE else 0, v),
    )
    _sensor_section: dict[str, object] = {
        "label": "Sensor",
        "options": [
            {
                "value": v,
                "label": SENSOR_NONE_LABEL if v == SENSOR_NONE_VALUE else v,
                "count": sensor_counts.get(v, 0),
                "available": v in sensor_counts,
                "selected": v in sensor_selected,
            }
            for v in sorted_sensor_values
        ],
        "selected": sensor_selected,
    }

    result: dict[str, dict[str, object]] = {}

    for field, label in RECIPE_FILTER_FIELDS:
        model_field = models.FujifilmRecipe._meta.get_field(field)
        is_numeric = isinstance(model_field, (db_models.IntegerField, db_models.DecimalField))

        # Base queryset: only images that have a recipe, filtered by all
        # OTHER active filters (faceted search — own field excluded).
        # recipe_id is a cross-cutting filter: it always applies regardless of
        # which field is being computed, since it narrows to specific recipes.
        base_qs: db_models.QuerySet[models.Image] = models.Image.objects.filter(fujifilm_recipe__isnull=False)
        recipe_ids = active_filters.get("recipe_id", [])
        if recipe_ids:
            base_qs = base_qs.filter(fujifilm_recipe_id__in=recipe_ids)
        for other_field, values in active_filters.items():
            if other_field in ("recipe_id", field) or not values:
                continue
            if other_field == "sensors":
                base_qs = filter_images_by_sensors(base_qs, values)
            else:
                base_qs = base_qs.filter(
                    **{f"fujifilm_recipe__{other_field}__in": values}
                )

        # Exclude null / empty values from the option set.
        if is_numeric:
            base_qs = base_qs.exclude(**{f"fujifilm_recipe__{field}__isnull": True})
        else:
            base_qs = base_qs.exclude(**{f"fujifilm_recipe__{field}": ""})

        # Aggregate counts; normalise DB values to strings so they match
        # URL param strings throughout the rest of the logic.
        available_counts: dict[str, int] = {
            decimal_filter_str(row[f"fujifilm_recipe__{field}"]): row["count"]
            for row in (
                base_qs
                .values(f"fujifilm_recipe__{field}")
                .annotate(count=db_models.Count("id"))
            )
        }

        selected_values: Sequence[str] = active_filters.get(field, [])

        # Union of available values and selected-but-unavailable values.
        all_values: set[str] = set(available_counts.keys()) | set(selected_values)

        # Sort: available values first, then unavailable; within each group
        # sort numerically for numeric fields, alphabetically for text fields.
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


def get_filtered_images(
    *,
    active_filters: Mapping[str, Sequence[str]],
    rating_first: bool,
) -> db_models.QuerySet[models.Image]:
    qs: db_models.QuerySet[models.Image] = models.Image.objects.select_related("fujifilm_recipe")
    recipe_ids = active_filters.get("recipe_id", [])
    if recipe_ids:
        qs = qs.filter(fujifilm_recipe_id__in=recipe_ids)
    for field, _ in RECIPE_FILTER_FIELDS:
        values = active_filters.get(field, [])
        if values:
            qs = qs.filter(**{f"fujifilm_recipe__{field}__in": values})
    sensor_values = active_filters.get("sensors", [])
    if sensor_values:
        qs = filter_images_by_sensors(qs, sensor_values)
    if rating_first:
        return qs.order_by("-rating", "-taken_at", "id")
    return qs.order_by("-taken_at", "id")


def _recipe_options(
    *,
    active_filters: Mapping[str, Sequence[str]],
    active_field_filters: Mapping[str, Sequence[str]],
) -> dict[str, object]:
    selected = active_filters.get("recipe_id", [])

    filtered_qs: db_models.QuerySet[models.Image] = models.Image.objects.filter(fujifilm_recipe__isnull=False)
    for field, values in active_field_filters.items():
        if not values:
            continue
        if field == "sensors":
            filtered_qs = filter_images_by_sensors(filtered_qs, values)
        else:
            filtered_qs = filtered_qs.filter(**{f"fujifilm_recipe__{field}__in": values})
    filtered_counts = {
        str(row["fujifilm_recipe_id"]): row["count"]
        for row in filtered_qs.values("fujifilm_recipe_id").annotate(count=db_models.Count("id"))
    }

    selected_ids = [int(r) for r in selected if r.isdigit()]
    recipes = (
        models.FujifilmRecipe.objects.annotate(total_images=db_models.Count("images"))
        .filter(
            db_models.Q(total_images__gt=_NOTABLE_RECIPE_MIN_IMAGES)
            | ~db_models.Q(name="")
            | db_models.Q(id__in=selected_ids)
        )
        .order_by("-total_images")
    )

    options = []
    for recipe in recipes:
        count = filtered_counts.get(str(recipe.id), 0)
        name = recipe.name if recipe.name else f"{recipe.id} - {recipe.film_simulation}"
        options.append({
            "value": str(recipe.id),
            "label": f"{name} ({count})",
            "available": count > 0,
            "selected": str(recipe.id) in selected,
        })
    options.sort(key=lambda o: 0 if o["available"] else 1)
    return {"label": "Recipe", "options": options, "selected": selected}


@attrs.frozen
class GalleryData:
    page_obj: object
    sidebar_options: dict[str, dict[str, object]]
    recipe_options: dict[str, object]


def get_gallery_data(
    *,
    active_filters: Mapping[str, Sequence[str]],
    rating_first: bool,
    page_number: int | str,
    page_size: int,
) -> GalleryData:
    """
    Return all data needed to render the gallery page in a single query bundle.
    """
    active_field_filters = {k: v for k, v in active_filters.items() if k != "recipe_id"}
    qs = get_filtered_images(active_filters=active_filters, rating_first=rating_first)
    page_obj = django_paginator.Paginator(qs, page_size).get_page(page_number)
    return GalleryData(
        page_obj=page_obj,
        sidebar_options=get_sidebar_filter_options(active_filters),
        recipe_options=_recipe_options(
            active_filters=active_filters,
            active_field_filters=active_field_filters,
        ),
    )
