import attrs
import os
from decimal import Decimal

from src.data import models
from src.domain.images import events, queries
from src.domain.images import dataclasses as image_dataclasses


def _parse_numeric(*, s: str | None) -> Decimal | None:
    """Convert a signed numeric string like '+4', '-1.5', '0' to Decimal, or None.

    Decimal is used (not float or int) so that half-step values like -1.5 and
    +0.5 are stored exactly in the DecimalField without rounding.
    """
    if s is None or s == "N/A":
        return None
    return Decimal(s)


class NoFilmSimulationError(Exception):
    """Raised when an image has no film simulation in its EXIF data."""

    def __init__(self, image_path: str) -> None:
        self.image_path = image_path
        super().__init__(f"No film simulation found in {image_path}")


class RecipeNameValidationError(Exception):
    """Raised when a recipe name fails validation (too long or non-ASCII)."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Invalid recipe name: {name!r}")


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



def toggle_image_favorite(*, image_id: int) -> bool:
    """Toggle the is_favorite flag for the image with the given *image_id*.

    Returns the new value of is_favorite after toggling.
    """
    image = models.Image.objects.get(pk=image_id)
    image.is_favorite = not image.is_favorite
    image.save(update_fields=["is_favorite"])
    return image.is_favorite


def process_image(*, image_path: str) -> models.Image:
    """Read EXIF data from *image_path* and persist it to the database.

    If a record for the same filepath already exists it is updated in-place.
    A FujifilmExif record is looked up or created for the image's EXIF field
    combination and linked via the recipe FK.

    Raises:
        NoFilmSimulationError: If the image has no film simulation EXIF data.
    """
    metadata = queries.read_image_exif(image_path=image_path)

    if metadata.camera_make.upper() != "FUJIFILM":
        raise NoFilmSimulationError(image_path)
    filename = os.path.basename(image_path)

    # Convert date string to timezone-aware datetime
    date_taken = queries.parse_exif_date(value=metadata.date_taken) if metadata.date_taken else None

    exif_fields = attrs.asdict(metadata)
    exif_fields.pop("date_taken")
    recipe_fields = {field: exif_fields.pop(field) for field in models.RECIPE_FIELDS}

    fujifilm_exif = models.FujifilmExif.get_or_create(**recipe_fields)

    try:
        recipe_data = queries.exif_to_recipe(exif=metadata)
    except KeyError:
        raise NoFilmSimulationError(image_path)
    fujifilm_recipe = models.FujifilmRecipe.get_or_create(
        film_simulation=recipe_data.film_simulation,
        dynamic_range=recipe_data.dynamic_range or "",
        d_range_priority=recipe_data.d_range_priority,
        grain_roughness=recipe_data.grain_roughness,
        grain_size=recipe_data.grain_size or "",
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

    image, created = models.Image.update_or_create(
        filepath=image_path,
        filename=filename,
        taken_at=date_taken,
        fujifilm_exif=fujifilm_exif,
        fujifilm_recipe=fujifilm_recipe,
        **exif_fields,
    )

    events.publish_event(
        event_type=events.RECIPE_IMAGE_CREATED if created else events.RECIPE_IMAGE_UPDATED,
        image_id=image.pk,
        filename=filename,
        film_simulation=fujifilm_exif.film_simulation,
        taken_at=image.taken_at.isoformat() if image.taken_at else "",
    )
    return image
