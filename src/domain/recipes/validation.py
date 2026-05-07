from __future__ import annotations

import attrs

from src.domain.images import dataclasses as image_dataclasses
from src.domain.recipes import constants as recipe_constants

_DRP_OFF = "Off"
_GRAIN_OFF = "Off"

_ALWAYS_REQUIRED_STR_FIELDS: tuple[str, ...] = (
    "film_simulation",
    "d_range_priority",
    "grain_roughness",
    "color_chrome_effect",
    "color_chrome_fx_blue",
    "white_balance",
    "sharpness",
    "high_iso_nr",
    "clarity",
)


@attrs.frozen
class InvalidFujifilmRecipeData(Exception):
    """Raised when FujifilmRecipeData fails cross-field consistency validation."""

    field: str
    value: object


def validate_recipe_data(data: image_dataclasses.FujifilmRecipeData) -> None:
    """Validate cross-field consistency of *data* before storing in the database.

    Checks that conditional optional fields are present or absent according to
    the values of the fields that control them (d_range_priority, grain_roughness,
    film_simulation).

    :raises InvalidFujifilmRecipeData: On the first field that fails validation,
        carrying the field name and the offending value.
    """
    for field in _ALWAYS_REQUIRED_STR_FIELDS:
        value: str = getattr(data, field)
        if not value:
            raise InvalidFujifilmRecipeData(field, value)

    _validate_drp_fields(data)
    _validate_grain_fields(data)
    _validate_film_sim_fields(data)


def _validate_drp_fields(data: image_dataclasses.FujifilmRecipeData) -> None:
    drp_active = data.d_range_priority != _DRP_OFF
    if drp_active:
        if data.dynamic_range is not None:
            raise InvalidFujifilmRecipeData("dynamic_range", data.dynamic_range)
        if data.highlight is not None:
            raise InvalidFujifilmRecipeData("highlight", data.highlight)
        if data.shadow is not None:
            raise InvalidFujifilmRecipeData("shadow", data.shadow)
    else:
        if data.dynamic_range is None:
            raise InvalidFujifilmRecipeData("dynamic_range", data.dynamic_range)
        if data.highlight is None:
            raise InvalidFujifilmRecipeData("highlight", data.highlight)
        if data.shadow is None:
            raise InvalidFujifilmRecipeData("shadow", data.shadow)


def _validate_grain_fields(data: image_dataclasses.FujifilmRecipeData) -> None:
    if data.grain_roughness == _GRAIN_OFF:
        if data.grain_size is not None:
            raise InvalidFujifilmRecipeData("grain_size", data.grain_size)
    else:
        if data.grain_size is None:
            raise InvalidFujifilmRecipeData("grain_size", data.grain_size)


def _validate_film_sim_fields(data: image_dataclasses.FujifilmRecipeData) -> None:
    is_mono = data.film_simulation in recipe_constants.MONOCHROMATIC_FILM_SIMULATIONS
    if is_mono:
        if data.color is not None:
            raise InvalidFujifilmRecipeData("color", data.color)
        if data.monochromatic_color_warm_cool is None:
            raise InvalidFujifilmRecipeData("monochromatic_color_warm_cool", data.monochromatic_color_warm_cool)
        if data.monochromatic_color_magenta_green is None:
            raise InvalidFujifilmRecipeData("monochromatic_color_magenta_green", data.monochromatic_color_magenta_green)
    else:
        if data.color is None:
            raise InvalidFujifilmRecipeData("color", data.color)
        if data.monochromatic_color_warm_cool is not None:
            raise InvalidFujifilmRecipeData("monochromatic_color_warm_cool", data.monochromatic_color_warm_cool)
        if data.monochromatic_color_magenta_green is not None:
            raise InvalidFujifilmRecipeData("monochromatic_color_magenta_green", data.monochromatic_color_magenta_green)
