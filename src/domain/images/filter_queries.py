import attrs

from django.core import paginator as django_paginator
from django.db import models as db_models

from src.data import models

_NOTABLE_RECIPE_MIN_IMAGES = 50

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
]


def get_sidebar_filter_options(
    active_filters: dict[str, list[str]],
) -> dict[str, dict]:
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
    result = {}

    for field, label in RECIPE_FILTER_FIELDS:
        model_field = models.FujifilmRecipe._meta.get_field(field)
        is_integer = isinstance(model_field, db_models.IntegerField)

        # Base queryset: only images that have a recipe, filtered by all
        # OTHER active filters (faceted search — own field excluded).
        # recipe_id is a cross-cutting filter: it always applies regardless of
        # which field is being computed, since it narrows to specific recipes.
        base_qs = models.Image.objects.filter(fujifilm_recipe__isnull=False)
        recipe_ids = active_filters.get("recipe_id", [])
        if recipe_ids:
            base_qs = base_qs.filter(fujifilm_recipe_id__in=recipe_ids)
        for other_field, values in active_filters.items():
            if other_field in ("recipe_id", field) or not values:
                continue
            base_qs = base_qs.filter(
                **{f"fujifilm_recipe__{other_field}__in": values}
            )

        # Exclude null / empty values from the option set.
        if is_integer:
            base_qs = base_qs.exclude(**{f"fujifilm_recipe__{field}__isnull": True})
        else:
            base_qs = base_qs.exclude(**{f"fujifilm_recipe__{field}": ""})

        # Aggregate counts; normalise DB values to strings so they match
        # URL param strings throughout the rest of the logic.
        available_counts: dict[str, int] = {
            str(row[f"fujifilm_recipe__{field}"]): row["count"]
            for row in (
                base_qs
                .values(f"fujifilm_recipe__{field}")
                .annotate(count=db_models.Count("id"))
            )
        }

        selected_values: list[str] = active_filters.get(field, [])

        # Union of available values and selected-but-unavailable values.
        all_values: set[str] = set(available_counts.keys()) | set(selected_values)

        # Sort: available values first, then unavailable; within each group
        # sort numerically for integer fields, alphabetically for text fields.
        if is_integer:
            def _sort_key(v: str) -> tuple:
                try:
                    return (0 if v in available_counts else 1, int(v))
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

    return result


def get_filtered_images(
    *,
    active_filters: dict[str, list[str]],
    favorites_first: bool,
) -> db_models.QuerySet:
    qs = models.Image.objects.select_related("fujifilm_recipe")
    recipe_ids = active_filters.get("recipe_id", [])
    if recipe_ids:
        qs = qs.filter(fujifilm_recipe_id__in=recipe_ids)
    for field, _ in RECIPE_FILTER_FIELDS:
        values = active_filters.get(field, [])
        if values:
            qs = qs.filter(**{f"fujifilm_recipe__{field}__in": values})
    if favorites_first:
        return qs.order_by("-is_favorite", "-taken_at", "id")
    return qs.order_by("-taken_at", "id")


def _recipe_options(
    *,
    active_filters: dict[str, list[str]],
    active_field_filters: dict[str, list[str]],
) -> dict:
    selected = active_filters.get("recipe_id", [])

    filtered_qs = models.Image.objects.filter(fujifilm_recipe__isnull=False)
    for field, values in active_field_filters.items():
        if values:
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
    sidebar_options: dict
    recipe_options: dict


def get_gallery_data(
    *,
    active_filters: dict[str, list[str]],
    favorites_first: bool,
    page_number: int | str,
    page_size: int,
) -> GalleryData:
    """Return all data needed to render the gallery page in a single query bundle."""
    active_field_filters = {k: v for k, v in active_filters.items() if k != "recipe_id"}
    qs = get_filtered_images(active_filters=active_filters, favorites_first=favorites_first)
    page_obj = django_paginator.Paginator(qs, page_size).get_page(page_number)
    return GalleryData(
        page_obj=page_obj,
        sidebar_options=get_sidebar_filter_options(active_filters),
        recipe_options=_recipe_options(
            active_filters=active_filters,
            active_field_filters=active_field_filters,
        ),
    )
