"""
Validation query for FujifilmRecipeData before writing to a camera.

Validation is model-relative: each camera model accepts a different set of
values, so the allowed values come from a CameraProfile rather than from
hard-coded sets.  validate_recipe_for_camera() validates against the default
per-property profile (the X-S10 / X-T3+ interface); validate_recipe_for_profile()
takes an explicit profile for a specific model.

The profile holds write-side value sets, which differ from read-side constants
in some cases (e.g. Grain "Off" is stored as raw value 6 or 7 when read back,
but validated as the domain roughness "Off" for writing).
"""
from __future__ import annotations

import re

from src.domain.camera import profiles
from src.domain.images import dataclasses as image_dataclasses

_KELVIN_RE: re.Pattern[str] = re.compile(r"^\d+K$")

_EMPTY_OR_NA: frozenset[str] = frozenset(("", "N/A"))


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class RecipeValidationError(ValueError):
    """
    Raised when a FujifilmRecipeData field contains a value the camera cannot accept.
    """

    def __init__(self, field: str, value: object) -> None:
        self.field = field
        self.value = value
        super().__init__(f"Invalid value for field {field!r}: {value!r}")


# ---------------------------------------------------------------------------
# Public validation query
# ---------------------------------------------------------------------------


def validate_recipe_for_camera(recipe: image_dataclasses.FujifilmRecipeData) -> None:
    """
    Validate that every field in *recipe* is acceptable to a per-property camera.

    Convenience wrapper over :func:`validate_recipe_for_profile` using the
    default per-property profile (X-S10 / X-T3+).  Fields that are optional on
    the write path (dynamic_range, d_range_priority, colour chrome, etc.) may be
    empty strings or "N/A" without raising.

    Args:
        recipe: The recipe to validate.

    Raises:
        RecipeValidationError: On the first field that fails validation,
                               carrying the field name and the offending value.
    """
    validate_recipe_for_profile(recipe, profile=profiles.PER_PROPERTY_PROFILE)


def validate_recipe_for_profile(
    recipe: image_dataclasses.FujifilmRecipeData,
    *,
    profile: profiles.CameraProfile,
) -> None:
    """
    Validate that every field in *recipe* is acceptable to the given model.

    The allowed values for each field come from *profile*, so the same code
    validates any camera model: an unsupported value raises for the model that
    lacks it and passes for one that has it.

    Args:
        recipe:  The recipe to validate.
        profile: The capability profile of the target camera model.

    Raises:
        RecipeValidationError: On the first field that fails validation,
                               carrying the field name and the offending value.
    """
    # --- name: required for writing; must be non-blank ASCII ≤25 chars ---
    if not recipe.name or not recipe.name.strip():
        raise RecipeValidationError("name", recipe.name)
    if len(recipe.name) > image_dataclasses.RECIPE_NAME_MAX_LEN:
        raise RecipeValidationError("name", recipe.name)
    if not recipe.name.isascii():
        raise RecipeValidationError("name", recipe.name)

    # --- film_simulation ---
    if recipe.film_simulation not in profile.supported_film_simulations:
        raise RecipeValidationError("film_simulation", recipe.film_simulation)

    # --- white_balance: named mode or Kelvin string ("6500K" etc.) ---
    wb = recipe.white_balance
    if wb not in profile.supported_white_balance_modes and not _KELVIN_RE.match(wb):
        raise RecipeValidationError("white_balance", wb)

    # --- dynamic_range: None or "" means omitted; "N/A" is not a valid DR value ---
    if recipe.dynamic_range is not None and recipe.dynamic_range != "":
        if recipe.dynamic_range not in profile.supported_dynamic_ranges:
            raise RecipeValidationError("dynamic_range", recipe.dynamic_range)

    # --- d_range_priority ---
    if (
        recipe.d_range_priority not in _EMPTY_OR_NA
        and recipe.d_range_priority not in profile.supported_dr_priorities
    ):
        raise RecipeValidationError("d_range_priority", recipe.d_range_priority)

    # --- grain: roughness and size validated together ---
    roughness, size = recipe.grain_roughness, recipe.grain_size
    if roughness not in profile.supported_grain_roughnesses:
        raise RecipeValidationError("grain_roughness", (roughness, size))
    if size is None or size == "":
        # None/"" means omitted — only valid when roughness is Off (size not applicable)
        if roughness != "Off":
            raise RecipeValidationError("grain_roughness", (roughness, size))
    else:
        valid_sizes = (
            profile.grain_sizes_when_off if roughness == "Off" else profile.grain_sizes_when_on
        )
        if size not in valid_sizes:
            raise RecipeValidationError("grain_roughness", (roughness, size))

    # --- color_chrome_effect ---
    if (
        recipe.color_chrome_effect not in _EMPTY_OR_NA
        and recipe.color_chrome_effect not in profile.supported_color_chrome_effects
    ):
        raise RecipeValidationError("color_chrome_effect", recipe.color_chrome_effect)

    # --- color_chrome_fx_blue ---
    if (
        recipe.color_chrome_fx_blue not in _EMPTY_OR_NA
        and recipe.color_chrome_fx_blue not in profile.supported_color_chrome_fx_blues
    ):
        raise RecipeValidationError("color_chrome_fx_blue", recipe.color_chrome_fx_blue)

    # --- high_iso_nr: must be a parseable int in the NR lookup ---
    if recipe.high_iso_nr not in _EMPTY_OR_NA:
        try:
            nr_int = int(recipe.high_iso_nr)
        except (ValueError, TypeError):
            raise RecipeValidationError("high_iso_nr", recipe.high_iso_nr)
        if nr_int not in profile.supported_high_iso_nr_values:
            raise RecipeValidationError("high_iso_nr", recipe.high_iso_nr)

    # --- numeric string fields ---
    _validate_int_str(recipe, "color")
    _validate_int_str(recipe, "sharpness")
    _validate_int_str(recipe, "clarity")
    _validate_float_str(recipe, "highlight")
    _validate_float_str(recipe, "shadow")
    _validate_float_str(recipe, "monochromatic_color_warm_cool")
    _validate_float_str(recipe, "monochromatic_color_magenta_green")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_int_str(recipe: image_dataclasses.FujifilmRecipeData, field: str) -> None:
    value = getattr(recipe, field)
    if value is None or value in _EMPTY_OR_NA:
        return
    try:
        int(value)
    except (ValueError, TypeError):
        raise RecipeValidationError(field, value)


def _validate_float_str(recipe: image_dataclasses.FujifilmRecipeData, field: str) -> None:
    value = getattr(recipe, field)
    if value is None or value in _EMPTY_OR_NA:
        return
    try:
        float(value)
    except (ValueError, TypeError):
        raise RecipeValidationError(field, value)
