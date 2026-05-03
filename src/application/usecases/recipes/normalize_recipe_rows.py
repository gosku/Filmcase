from __future__ import annotations

import attrs

from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.recipes import normalization as recipe_normalization
from src.domain.recipes import validation as recipe_validation


@attrs.frozen
class NormalizedRecipe:
    pk: int
    nulled_fields: tuple[str, ...]


@attrs.frozen
class MergedRecipe:
    pk: int
    merged_into_pk: int


@attrs.frozen
class SkippedRecipe:
    pk: int
    reason: str


@attrs.frozen
class NormalizeRecipesResult:
    normalized: tuple[NormalizedRecipe, ...]
    merged: tuple[MergedRecipe, ...]
    skipped: tuple[SkippedRecipe, ...]


def _decimal_str(value: object) -> str | None:
    if value is None:
        return None
    n = float(value)  # type: ignore[arg-type]
    v: int | float = int(n) if n == int(n) else n
    return f"+{v}" if v > 0 else str(v)


def _recipe_data_raw(recipe: models.FujifilmRecipe) -> image_dataclasses.FujifilmRecipeData:
    """
    Build FujifilmRecipeData from DB columns without applying normalization.
    """
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
        sharpness=_decimal_str(recipe.sharpness) or "0",
        high_iso_nr=_decimal_str(recipe.high_iso_nr) or "0",
        clarity=_decimal_str(recipe.clarity) or "0",
        dynamic_range=recipe.dynamic_range or None,
        grain_size=recipe.grain_size or None,
        highlight=_decimal_str(recipe.highlight),
        shadow=_decimal_str(recipe.shadow),
        color=_decimal_str(recipe.color),
        monochromatic_color_warm_cool=_decimal_str(recipe.monochromatic_color_warm_cool),
        monochromatic_color_magenta_green=_decimal_str(recipe.monochromatic_color_magenta_green),
    )


# DB column value that represents "inapplicable" for each field normalize can change.
# Nullable Decimal fields → None (NULL). Non-nullable CharFields → the canonical empty value.
_INAPPLICABLE_DB_VALUE: dict[str, object] = {
    "color": None,
    "monochromatic_color_warm_cool": None,
    "monochromatic_color_magenta_green": None,
    "highlight": None,
    "shadow": None,
    "dynamic_range": "",
    "grain_size": "Off",
}

_NORMALIZABLE_FIELDS: tuple[str, ...] = tuple(_INAPPLICABLE_DB_VALUE)


def normalize_recipe_rows() -> NormalizeRecipesResult:
    """
    Normalize FujifilmRecipe rows whose inapplicable fields are set to non-null/non-empty values.

    For each row:
    - Fields that are inapplicable for the row's film sim, DRP state, or grain state
      are set to their canonical "absent" DB value (NULL for decimal fields, '' or 'Off'
      for CharFields).
    - If the normalized shape already exists as another row, the dirty row's images are
      reassigned and the dirty row is deleted.
    - Rows that cannot be fully repaired (a required field is missing) are skipped.

    Returns a NormalizeRecipesResult summarising every action taken.
    """
    normalized: list[NormalizedRecipe] = []
    merged: list[MergedRecipe] = []
    skipped: list[SkippedRecipe] = []

    for recipe in models.FujifilmRecipe.objects.all():
        try:
            raw_data = _recipe_data_raw(recipe)
        except Exception:
            skipped.append(SkippedRecipe(pk=recipe.pk, reason="failed to read from DB"))
            continue

        normalized_data = recipe_normalization.normalize_recipe_data(raw_data)

        # A domain change only matters if the resulting DB write value differs
        # from the current DB value (e.g. grain_size="Off" → domain None → write
        # "Off" back is a no-op that should not trigger normalization).
        changed_fields = [
            f for f in _NORMALIZABLE_FIELDS
            if getattr(raw_data, f) != getattr(normalized_data, f)
            and getattr(recipe, f) != _INAPPLICABLE_DB_VALUE[f]
        ]
        if not changed_fields:
            continue

        try:
            recipe_validation.validate_recipe_data(normalized_data)
        except recipe_validation.InvalidFujifilmRecipeData as exc:
            skipped.append(SkippedRecipe(
                pk=recipe.pk,
                reason=f"{exc.field} = {exc.value!r} — cannot normalize",
            ))
            continue

        db_changes: dict[str, object] = {
            f: _INAPPLICABLE_DB_VALUE[f] for f in changed_fields
        }

        correct_kwargs: dict[str, object] = {
            "film_simulation": recipe.film_simulation,
            "dynamic_range": db_changes.get("dynamic_range", recipe.dynamic_range),
            "d_range_priority": recipe.d_range_priority,
            "grain_roughness": recipe.grain_roughness,
            "grain_size": db_changes.get("grain_size", recipe.grain_size),
            "color_chrome_effect": recipe.color_chrome_effect,
            "color_chrome_fx_blue": recipe.color_chrome_fx_blue,
            "white_balance": recipe.white_balance,
            "white_balance_red": recipe.white_balance_red,
            "white_balance_blue": recipe.white_balance_blue,
            "highlight": db_changes.get("highlight", recipe.highlight),
            "shadow": db_changes.get("shadow", recipe.shadow),
            "color": db_changes.get("color", recipe.color),
            "sharpness": recipe.sharpness,
            "high_iso_nr": recipe.high_iso_nr,
            "clarity": recipe.clarity,
            "monochromatic_color_warm_cool": db_changes.get(
                "monochromatic_color_warm_cool", recipe.monochromatic_color_warm_cool
            ),
            "monochromatic_color_magenta_green": db_changes.get(
                "monochromatic_color_magenta_green", recipe.monochromatic_color_magenta_green
            ),
        }

        try:
            correct = models.FujifilmRecipe.objects.get(**correct_kwargs)
        except models.FujifilmRecipe.DoesNotExist:
            for field, value in db_changes.items():
                setattr(recipe, field, value)
            recipe.save(update_fields=list(db_changes.keys()))
            normalized.append(NormalizedRecipe(pk=recipe.pk, nulled_fields=tuple(changed_fields)))
        else:
            if recipe.name and not correct.name:
                correct.name = recipe.name
                correct.save(update_fields=["name"])
            models.Image.objects.filter(fujifilm_recipe=recipe).update(fujifilm_recipe=correct)
            dirty_pk = recipe.pk
            recipe.delete()
            merged.append(MergedRecipe(pk=dirty_pk, merged_into_pk=correct.pk))

    return NormalizeRecipesResult(
        normalized=tuple(normalized),
        merged=tuple(merged),
        skipped=tuple(skipped),
    )
