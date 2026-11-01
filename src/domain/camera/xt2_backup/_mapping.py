"""
Map a FujifilmRecipeData onto the X-T2 capability subset.

Produces an Xt2Mapping of the values the X-T2 can store, and a list of the
recipe's fields the X-T2 lacks (dropped and reported, not rejected). Raises
RecipeNotRepresentable only when a value the X-T2 does support cannot be
represented at all (a film sim it lacks, a WB mode it lacks, a numeric value
outside its range). Colour on a black-and-white sim is kept but ignored by the
camera, so it is never a hard failure.
"""
from __future__ import annotations

import re

import attrs

from src.data.camera import constants_xt2 as xt2
from src.domain.images import dataclasses as image_dataclasses

_EMPTY_OR_NA: frozenset[str] = frozenset(("", "N/A"))
_KELVIN_RE: re.Pattern[str] = re.compile(r"^(\d+)K$")

_SUPPORTED_FILM_SIMS: frozenset[str] = frozenset(xt2.FILM_SIMULATION_BY_BYTE.values())
_SUPPORTED_GRAIN: frozenset[str] = frozenset(xt2.GRAIN_ROUGHNESS_BY_BYTE.values())
_SUPPORTED_DR: frozenset[str] = frozenset(xt2.DYNAMIC_RANGE_BY_BYTE.values())
_SUPPORTED_WB: frozenset[str] = frozenset(xt2.WHITE_BALANCE_BY_SELECTOR.values())

_WB_SHIFT_LIMIT = 9
_TONE_MIN, _TONE_MAX = -2, 4
_EFFECT_MIN, _EFFECT_MAX = -4, 4


class RecipeNotRepresentable(Exception):
    """
    Raised when a recipe holds a value the X-T2 cannot represent at all.

    Carries the offending field and value as attributes for the caller to report.
    """

    def __init__(self, field: str, value: object) -> None:
        self.field = field
        self.value = value
        super().__init__(f"The X-T2 cannot represent {field}={value!r}")


@attrs.frozen
class Xt2Mapping:
    """
    A recipe reduced to the fields the X-T2 can store.

    ``dropped`` names the recipe's fields the X-T2 lacks (reported to the user).
    ``white_balance`` is an X-T2 WB name; ``kelvin`` is set only when it is
    "Kelvin".
    """

    name: str
    film_simulation: str
    grain_roughness: str
    dynamic_range: str
    white_balance: str
    white_balance_red: int
    white_balance_blue: int
    kelvin: int | None
    highlight: int
    shadow: int
    color: int
    sharpness: int
    noise_reduction: int
    dropped: tuple[str, ...]


def _parse_signed(value: str | None, default: int = 0) -> int:
    if value is None or value in _EMPTY_OR_NA:
        return default
    return round(float(value))


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _snap_kelvin(kelvin: int) -> int:
    return min(xt2.KELVIN_STEPS, key=lambda step: abs(step - kelvin))


def _dropped_fields(recipe: image_dataclasses.FujifilmRecipeData) -> tuple[str, ...]:
    dropped: list[str] = []
    if recipe.clarity not in _EMPTY_OR_NA and recipe.clarity not in ("0", None):
        dropped.append("Clarity")
    if recipe.color_chrome_effect not in _EMPTY_OR_NA and recipe.color_chrome_effect not in (
        "Off",
        None,
    ):
        dropped.append("Color Chrome Effect")
    if recipe.color_chrome_fx_blue not in _EMPTY_OR_NA and recipe.color_chrome_fx_blue not in (
        "Off",
        None,
    ):
        dropped.append("Color Chrome FX Blue")
    if recipe.d_range_priority not in _EMPTY_OR_NA and recipe.d_range_priority not in ("Off", None):
        dropped.append("D-Range Priority")
    if recipe.grain_size not in (None, "", "Off", "N/A"):
        dropped.append("Grain Size")
    return tuple(dropped)


def _map_white_balance(recipe: image_dataclasses.FujifilmRecipeData) -> tuple[str, int | None]:
    wb = recipe.white_balance
    kelvin_match = _KELVIN_RE.match(wb)
    if kelvin_match:
        return "Kelvin", _snap_kelvin(int(kelvin_match.group(1)))
    if wb not in _SUPPORTED_WB:
        raise RecipeNotRepresentable("white_balance", wb)
    return wb, None


def map_recipe(recipe: image_dataclasses.FujifilmRecipeData) -> Xt2Mapping:
    """
    Map *recipe* to the X-T2 capability subset.

    :raises RecipeNotRepresentable: if a supported field holds a value the X-T2
        has no representation for.
    """
    if recipe.film_simulation not in _SUPPORTED_FILM_SIMS:
        raise RecipeNotRepresentable("film_simulation", recipe.film_simulation)
    if recipe.grain_roughness not in _SUPPORTED_GRAIN:
        raise RecipeNotRepresentable("grain_roughness", recipe.grain_roughness)

    dynamic_range = recipe.dynamic_range if recipe.dynamic_range not in (None, "") else "DR-Auto"
    if dynamic_range not in _SUPPORTED_DR:
        raise RecipeNotRepresentable("dynamic_range", recipe.dynamic_range)

    white_balance, kelvin = _map_white_balance(recipe)

    highlight = _parse_signed(recipe.highlight)
    shadow = _parse_signed(recipe.shadow)
    color = _parse_signed(recipe.color)
    sharpness = _parse_signed(recipe.sharpness)
    noise_reduction = _parse_signed(recipe.high_iso_nr)
    for field, value, lo, hi in (
        ("highlight", highlight, _TONE_MIN, _TONE_MAX),
        ("shadow", shadow, _TONE_MIN, _TONE_MAX),
        ("color", color, _EFFECT_MIN, _EFFECT_MAX),
        ("sharpness", sharpness, _EFFECT_MIN, _EFFECT_MAX),
        ("high_iso_nr", noise_reduction, _EFFECT_MIN, _EFFECT_MAX),
    ):
        if not (lo <= value <= hi):
            raise RecipeNotRepresentable(field, value)

    return Xt2Mapping(
        name=recipe.name,
        film_simulation=recipe.film_simulation,
        grain_roughness=recipe.grain_roughness,
        dynamic_range=dynamic_range,
        white_balance=white_balance,
        white_balance_red=_clamp(recipe.white_balance_red, -_WB_SHIFT_LIMIT, _WB_SHIFT_LIMIT),
        white_balance_blue=_clamp(recipe.white_balance_blue, -_WB_SHIFT_LIMIT, _WB_SHIFT_LIMIT),
        kelvin=kelvin,
        highlight=highlight,
        shadow=shadow,
        color=color,
        sharpness=sharpness,
        noise_reduction=noise_reduction,
        dropped=_dropped_fields(recipe),
    )
