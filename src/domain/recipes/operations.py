from __future__ import annotations

import attrs
from decimal import Decimal

from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.images import events
from src.domain.images import queries as image_queries


def _parse_numeric(*, s: str | None) -> Decimal | None:
    """Convert a signed numeric string like '+4', '-1.5', '0' to Decimal, or None.

    Decimal is used (not float or int) so that half-step values like -1.5 and
    +0.5 are stored exactly in the DecimalField without rounding.
    """
    if s is None or s == "N/A":
        return None
    return Decimal(s)


def get_or_create_recipe_from_metadata(*, metadata: image_dataclasses.ImageExifData) -> models.FujifilmRecipe:
    """Create or retrieve a FujifilmRecipe for the given parsed EXIF data.

    :raises NoFilmSimulationError: If the EXIF data contains no known film simulation.
    """
    try:
        recipe_data = image_queries.exif_to_recipe(exif=metadata)
    except KeyError:
        raise image_queries.NoFilmSimulationError()
    recipe, created = models.FujifilmRecipe.get_or_create(
        film_simulation=recipe_data.film_simulation,
        dynamic_range=recipe_data.dynamic_range or "",
        d_range_priority=recipe_data.d_range_priority,
        grain_roughness=recipe_data.grain_roughness,
        grain_size=recipe_data.grain_size if recipe_data.grain_size is not None else "Off",
        color_chrome_effect=recipe_data.color_chrome_effect,
        color_chrome_fx_blue=recipe_data.color_chrome_fx_blue,
        white_balance=recipe_data.white_balance,
        white_balance_red=recipe_data.white_balance_red,
        white_balance_blue=recipe_data.white_balance_blue,
        highlight=_parse_numeric(s=recipe_data.highlight),
        shadow=_parse_numeric(s=recipe_data.shadow),
        color=_parse_numeric(s=recipe_data.color),
        sharpness=_parse_numeric(s=recipe_data.sharpness),
        high_iso_nr=_parse_numeric(s=recipe_data.high_iso_nr),
        clarity=_parse_numeric(s=recipe_data.clarity),
        monochromatic_color_warm_cool=_parse_numeric(s=recipe_data.monochromatic_color_warm_cool),
        monochromatic_color_magenta_green=_parse_numeric(s=recipe_data.monochromatic_color_magenta_green),
    )
    if created:
        events.publish_event(
            event_type=events.RECIPE_CREATED,
            recipe_id=recipe.pk,
            film_simulation=recipe.film_simulation,
        )
    return recipe


def get_or_create_recipe_from_filepath(*, filepath: str) -> models.FujifilmRecipe:
    """Read EXIF from *filepath* and return the matching FujifilmRecipe, creating it if needed.

    :raises NoFilmSimulationError: If the file is not a Fujifilm image or has no film simulation.
    """
    metadata = image_queries.read_image_exif(image_path=filepath)
    if metadata.camera_make.upper() != "FUJIFILM":
        raise image_queries.NoFilmSimulationError(filepath)
    return get_or_create_recipe_from_metadata(metadata=metadata)


@attrs.frozen
class RecipeNotFoundError(Exception):
    """Raised when no recipe with the given ID exists."""

    recipe_id: int


@attrs.frozen
class ImageNotFoundError(Exception):
    """Raised when no image with the given ID exists."""

    image_id: int


@attrs.frozen
class ImageNotAssociatedToRecipeError(Exception):
    """Raised when the image is not linked to the recipe."""

    recipe_id: int
    image_id: int


def set_cover_image_for_recipe(*, recipe_id: int, image_id: int) -> None:
    """Set the cover image of a recipe to the given image.

    Raises:
        RecipeNotFoundError: If no recipe with *recipe_id* exists.
        ImageNotFoundError: If no image with *image_id* exists.
        ImageNotAssociatedToRecipeError: If the image is not linked to the recipe.
    """
    try:
        recipe = models.FujifilmRecipe.objects.get(pk=recipe_id)
    except models.FujifilmRecipe.DoesNotExist:
        raise RecipeNotFoundError(recipe_id)

    try:
        image = models.Image.objects.get(pk=image_id)
    except models.Image.DoesNotExist:
        raise ImageNotFoundError(image_id)

    if image.fujifilm_recipe_id != recipe_id:
        raise ImageNotAssociatedToRecipeError(recipe_id=recipe_id, image_id=image_id)

    recipe.set_cover_image(image_id=image_id)
    events.publish_event(
        event_type=events.RECIPE_COVER_IMAGE_SET,
        recipe_id=recipe_id,
        image_id=image_id,
    )


@attrs.frozen
class RecipeNameValidationError(Exception):
    """Raised when a recipe name fails validation (too long or non-ASCII)."""

    name: str


def set_recipe_name(*, recipe: models.FujifilmRecipe, name: str) -> None:
    """Set the name of *recipe* to *name* after validating it.

    Raises:
        RecipeNameValidationError: If the name is empty, longer than
            RECIPE_NAME_MAX_LEN, or contains non-ASCII characters.
    """
    if not name or len(name) > image_dataclasses.RECIPE_NAME_MAX_LEN or not name.isascii():
        raise RecipeNameValidationError(name)
    recipe.name = name
    recipe.save(update_fields=["name"])
    events.publish_event(
        event_type=events.RECIPE_IMAGE_UPDATED,
        name=name,
        recipe_id=recipe.pk,
    )
