"""
Validation query for FujifilmRecipeData before writing to a camera.

Uses write-side constants, which differ from read-side constants in some
cases (e.g. Grain "Off" is stored as raw value 6 or 7 when read back, but
validated as the domain pair ("Off", "Off") for writing).
"""
from __future__ import annotations

import re

from src.data.camera import constants
from src.domain.images.dataclasses import RECIPE_NAME_MAX_LEN, FujifilmRecipeData

# ---------------------------------------------------------------------------
# Pre-computed allowed value sets (write-side constants)
# ---------------------------------------------------------------------------

_VALID_FILM_SIMS: frozenset[str] = frozenset(constants.FILM_SIMULATION_TO_PTP)

_VALID_WB_MODES: frozenset[str] = frozenset(constants.WHITE_BALANCE_TO_PTP)

_VALID_DR_MODES: frozenset[str] = frozenset(constants.DRANGE_MODE_TO_PTP)

_VALID_DR_PRIORITIES: frozenset[str] = frozenset(
    constants.CUSTOM_SLOT_DR_PRIORITY_DECODE.values()
)

# Grain valid roughness values and their allowed sizes.
# Write-side behaviour (confirmed X-S10, 2026-03-26):
#   - Roughness "Off"  → write 1; camera normalises to 6/7, retaining last size.
#     Size "Off", "Small", or "Large" are all valid — the size is remembered by
#     the camera, not encoded in the write value.
#   - Roughness "Weak" / "Strong" → size must be "Small" or "Large" (distinct PTP values).
_VALID_OFF_SIZES: frozenset[str] = frozenset(("Off", "Small", "Large"))
_VALID_ON_SIZES: frozenset[str] = frozenset(("Small", "Large"))
_VALID_ROUGHNESS: frozenset[str] = frozenset(("Off", "Weak", "Strong"))

_VALID_CCE: frozenset[str] = frozenset(constants.CUSTOM_SLOT_CCE_PTP.values())

_VALID_CFX: frozenset[str] = frozenset(constants.CUSTOM_SLOT_CFX_PTP.values())

# Valid high-ISO NR domain integers: values of the NR decode table.
_VALID_NR_INTS: frozenset[int] = frozenset(constants.CUSTOM_SLOT_NR_DECODE.values())

_KELVIN_RE: re.Pattern[str] = re.compile(r"^\d+K$")

_EMPTY_OR_NA: frozenset[str] = frozenset(("", "N/A"))


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class RecipeValidationError(ValueError):
    """Raised when a FujifilmRecipeData field contains a value the camera cannot accept."""

    def __init__(self, field: str, value: object) -> None:
        self.field = field
        self.value = value
        super().__init__(f"Invalid value for field {field!r}: {value!r}")


# ---------------------------------------------------------------------------
# Public validation query
# ---------------------------------------------------------------------------


def validate_recipe_for_camera(recipe: FujifilmRecipeData) -> None:
    """
    Validate that every field in *recipe* contains a camera-acceptable value.

    Validates against write-side constants.  Fields that are optional on the
    write path (dynamic_range, d_range_priority, colour chrome, etc.) may be
    empty strings or "N/A" without raising.

    Args:
        recipe: The recipe to validate.

    Raises:
        RecipeValidationError: On the first field that fails validation,
                               carrying the field name and the offending value.
    """
    # --- name: required for writing; must be non-blank ASCII ≤25 chars ---
    if not recipe.name or not recipe.name.strip():
        raise RecipeValidationError("name", recipe.name)
    if len(recipe.name) > RECIPE_NAME_MAX_LEN:
        raise RecipeValidationError("name", recipe.name)
    if not recipe.name.isascii():
        raise RecipeValidationError("name", recipe.name)

    # --- film_simulation ---
    if recipe.film_simulation not in _VALID_FILM_SIMS:
        raise RecipeValidationError("film_simulation", recipe.film_simulation)

    # --- white_balance: named mode or Kelvin string ("6500K" etc.) ---
    wb = recipe.white_balance
    if wb not in _VALID_WB_MODES and not _KELVIN_RE.match(wb):
        raise RecipeValidationError("white_balance", wb)

    # --- dynamic_range: None or "" means omitted; "N/A" is not a valid DR value ---
    if recipe.dynamic_range is not None and recipe.dynamic_range != "":
        if recipe.dynamic_range not in _VALID_DR_MODES:
            raise RecipeValidationError("dynamic_range", recipe.dynamic_range)

    # --- d_range_priority ---
    if (
        recipe.d_range_priority not in _EMPTY_OR_NA
        and recipe.d_range_priority not in _VALID_DR_PRIORITIES
    ):
        raise RecipeValidationError("d_range_priority", recipe.d_range_priority)

    # --- grain: roughness and size validated together ---
    roughness, size = recipe.grain_roughness, recipe.grain_size
    if roughness not in _VALID_ROUGHNESS:
        raise RecipeValidationError("grain_roughness", (roughness, size))
    if size is None or size == "":
        # None/"" means omitted — only valid when roughness is Off (size not applicable)
        if roughness != "Off":
            raise RecipeValidationError("grain_roughness", (roughness, size))
    else:
        valid_sizes = _VALID_OFF_SIZES if roughness == "Off" else _VALID_ON_SIZES
        if size not in valid_sizes:
            raise RecipeValidationError("grain_roughness", (roughness, size))

    # --- color_chrome_effect ---
    if recipe.color_chrome_effect not in _EMPTY_OR_NA and recipe.color_chrome_effect not in _VALID_CCE:
        raise RecipeValidationError("color_chrome_effect", recipe.color_chrome_effect)

    # --- color_chrome_fx_blue ---
    if (
        recipe.color_chrome_fx_blue not in _EMPTY_OR_NA
        and recipe.color_chrome_fx_blue not in _VALID_CFX
    ):
        raise RecipeValidationError("color_chrome_fx_blue", recipe.color_chrome_fx_blue)

    # --- high_iso_nr: must be a parseable int in the NR lookup ---
    if recipe.high_iso_nr not in _EMPTY_OR_NA:
        try:
            nr_int = int(recipe.high_iso_nr)
        except (ValueError, TypeError):
            raise RecipeValidationError("high_iso_nr", recipe.high_iso_nr)
        if nr_int not in _VALID_NR_INTS:
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


def _validate_int_str(recipe: FujifilmRecipeData, field: str) -> None:
    value = getattr(recipe, field)
    if value is None or value in _EMPTY_OR_NA:
        return
    try:
        int(value)
    except (ValueError, TypeError):
        raise RecipeValidationError(field, value)


def _validate_float_str(recipe: FujifilmRecipeData, field: str) -> None:
    value = getattr(recipe, field)
    if value is None or value in _EMPTY_OR_NA:
        return
    try:
        float(value)
    except (ValueError, TypeError):
        raise RecipeValidationError(field, value)
