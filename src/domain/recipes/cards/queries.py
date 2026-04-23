from __future__ import annotations

import json

import attrs

from src.data import models
from src.domain.recipes import constants as recipe_constants
from src.domain.recipes import queries as recipe_queries
from src.domain.recipes.cards import templates as card_templates


@attrs.frozen
class FieldLine:
    label: str
    value: str


_LONG_LABELS: dict[str, str] = {
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

_SHORT_LABELS: dict[str, str] = {
    "film_simulation": "Film Sim",
    "dynamic_range": "DR",
    "d_range_priority": "D-Range",
    "grain_roughness": "Grain",
    "grain_size": "Grain Size",
    "color_chrome_effect": "CC",
    "color_chrome_fx_blue": "CC Blue",
    "white_balance": "WB",
    "white_balance_red": "WB Red",
    "white_balance_blue": "WB Blue",
    "highlight": "HL",
    "shadow": "SH",
    "color": "Color",
    "sharpness": "Sharp",
    "high_iso_nr": "NR",
    "clarity": "Clarity",
    "monochromatic_color_warm_cool": "BW W/C",
    "monochromatic_color_magenta_green": "BW M/G",
}

# Fields that only apply to colour (non-monochromatic) film simulations.
_COLOR_ONLY_FIELDS: frozenset[str] = frozenset({
    "color",
    "color_chrome_effect",
    "color_chrome_fx_blue",
})

# Fields that only apply to monochromatic film simulations.
_MONOCHROME_ONLY_FIELDS: frozenset[str] = frozenset({
    "monochromatic_color_warm_cool",
    "monochromatic_color_magenta_green",
})

# Fields where string value "Off" signals the paired field should be hidden.
_GRAIN_ROUGHNESS_FIELD = "grain_roughness"
_GRAIN_SIZE_FIELD = "grain_size"

# Ordered list of fields to include in card display and JSON payload.
# Order matches the recipe detail view.
_DISPLAY_FIELDS: tuple[str, ...] = (
    "film_simulation",
    "monochromatic_color_warm_cool",
    "monochromatic_color_magenta_green",
    "grain_roughness",
    "grain_size",
    "color_chrome_effect",
    "color_chrome_fx_blue",
    "white_balance",
    "white_balance_red",
    "white_balance_blue",
    "dynamic_range",
    "d_range_priority",
    "highlight",
    "shadow",
    "color",
    "sharpness",
    "high_iso_nr",
    "clarity",
)


def _get_raw_value(recipe: models.FujifilmRecipe, field: str) -> object:
    return getattr(recipe, field)


def _format_value(field: str, raw: object) -> str:
    if field in recipe_queries.DECIMAL_FIELDS:
        return recipe_queries.decimal_str(raw)
    return str(raw)


def _is_applicable(recipe: models.FujifilmRecipe, field: str) -> bool:
    """Return False when a field is semantically inapplicable for this recipe."""
    is_monochromatic = recipe.film_simulation in recipe_constants.MONOCHROMATIC_FILM_SIMULATIONS
    if field in _COLOR_ONLY_FIELDS and is_monochromatic:
        return False
    if field in _MONOCHROME_ONLY_FIELDS and not is_monochromatic:
        return False
    if field == _GRAIN_SIZE_FIELD and recipe.grain_roughness == "Off":
        return False
    return True


def get_recipe_as_json(*, recipe: models.FujifilmRecipe) -> str:
    """Return a minified JSON string encoding the recipe (used as QR payload).

    Uses short snake_case keys. Fields that are None and semantically inapplicable
    for the current film simulation are omitted. Values of 0 or other defaults are
    always included. The recipe name is included only when non-empty, so nameless
    recipes produce byte-identical payloads to before this key existed.
    """
    payload: dict[str, object] = {"v": 1}
    if recipe.name:
        payload["name"] = recipe.name
    for field in _DISPLAY_FIELDS:
        if not _is_applicable(recipe, field):
            continue
        raw = _get_raw_value(recipe, field)
        if raw is None:
            continue
        if field in recipe_queries.DECIMAL_FIELDS:
            payload[field] = float(raw) if float(raw) != int(float(raw)) else int(float(raw))  # type: ignore[arg-type]
        else:
            payload[field] = raw
    return json.dumps(payload, separators=(",", ":"))


def get_recipe_cover_lines(
    *,
    recipe: models.FujifilmRecipe,
    template: card_templates.CardTemplate,
) -> tuple[FieldLine, ...]:
    """Return display lines for the recipe card formatted per template label style.

    Inapplicable fields (same rules as get_recipe_as_json) and null values are omitted.
    """
    labels = _LONG_LABELS if template.label_style == "long" else _SHORT_LABELS
    lines: list[FieldLine] = []
    for field in _DISPLAY_FIELDS:
        if not _is_applicable(recipe, field):
            continue
        raw = _get_raw_value(recipe, field)
        if raw is None:
            continue
        value = _format_value(field, raw)
        lines.append(FieldLine(label=labels[field], value=value))
    return tuple(lines)
