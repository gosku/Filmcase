from django.db import models as db_models

from src.data import models

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
