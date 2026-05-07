from __future__ import annotations

import attrs

from src.domain.images import dataclasses as image_dataclasses
from src.domain.recipes import constants as recipe_constants


def normalize_recipe_data(
    data: image_dataclasses.FujifilmRecipeData,
) -> image_dataclasses.FujifilmRecipeData:
    """Return a copy of *data* with inapplicable fields set to None.

    Applies the applicability rules defined in ADR 007:
    - Mono sim  → color = None; mono color fields preserved.
    - Color sim → mono color fields = None; color preserved.
    - DRP active → dynamic_range, highlight, shadow = None.
    - DRP off   → those fields preserved.
    - grain_roughness Off → grain_size = None.
    - grain_roughness active → grain_size preserved.

    This function does NOT validate the recipe and does NOT fill in missing
    required fields. After normalizing, callers that write to the DB must
    also call validate_recipe_data() to guarantee full correctness.
    Idempotent: calling twice produces the same result.
    """
    is_mono = data.film_simulation in recipe_constants.MONOCHROMATIC_FILM_SIMULATIONS
    drp_active = data.d_range_priority != "Off"
    grain_off = data.grain_roughness == "Off"
    return attrs.evolve(
        data,
        color=None if is_mono else data.color,
        monochromatic_color_warm_cool=None if not is_mono else data.monochromatic_color_warm_cool,
        monochromatic_color_magenta_green=None if not is_mono else data.monochromatic_color_magenta_green,
        dynamic_range=None if drp_active else data.dynamic_range,
        highlight=None if drp_active else data.highlight,
        shadow=None if drp_active else data.shadow,
        grain_size=None if grain_off else data.grain_size,
    )
