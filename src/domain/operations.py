import attrs
import os

from src.data.models import FujifilmExif, FujifilmRecipe, Image, RECIPE_FIELDS
from src.domain import events, queries


def _parse_numeric(s: str) -> int | None:
    """Convert a signed numeric string like '+4', '-1', '0' to int, or None for 'N/A'."""
    if s == "N/A":
        return None
    return round(float(s))


class NoFilmSimulationError(Exception):
    """Raised when an image has no film simulation in its EXIF data."""

    def __init__(self, image_path: str) -> None:
        self.image_path = image_path
        super().__init__(f"No film simulation found in {image_path}")



def process_image(image_path: str) -> Image:
    """Read EXIF data from *image_path* and persist it to the database.

    If a record for the same filepath already exists it is updated in-place.
    A FujifilmExif record is looked up or created for the image's EXIF field
    combination and linked via the recipe FK.

    Raises:
        NoFilmSimulationError: If the image has no film simulation EXIF data.
    """
    metadata = queries.read_image_exif(image_path)

    if metadata.camera_make.upper() != "FUJIFILM":
        raise NoFilmSimulationError(image_path)
    filename = os.path.basename(image_path)

    # Convert date string to timezone-aware datetime
    date_taken = queries.parse_exif_date(metadata.date_taken) if metadata.date_taken else None

    exif_fields = attrs.asdict(metadata)
    exif_fields.pop("date_taken")
    recipe_fields = {field: exif_fields.pop(field) for field in RECIPE_FIELDS}

    fujifilm_exif = FujifilmExif.get_or_create(**recipe_fields)

    try:
        recipe_data = queries.exif_to_recipe(metadata)
    except KeyError:
        raise NoFilmSimulationError(image_path)
    fujifilm_recipe = FujifilmRecipe.get_or_create(
        film_simulation=recipe_data.film_simulation,
        dynamic_range=recipe_data.dynamic_range,
        d_range_priority=recipe_data.d_range_priority,
        grain_roughness=recipe_data.grain_roughness,
        grain_size=recipe_data.grain_size,
        color_chrome_effect=recipe_data.color_chrome_effect,
        color_chrome_fx_blue=recipe_data.color_chrome_fx_blue,
        white_balance=recipe_data.white_balance,
        white_balance_red=recipe_data.white_balance_red,
        white_balance_blue=recipe_data.white_balance_blue,
        highlight=_parse_numeric(recipe_data.highlight),
        shadow=_parse_numeric(recipe_data.shadow),
        color=_parse_numeric(recipe_data.color),
        sharpness=_parse_numeric(recipe_data.sharpness),
        high_iso_nr=_parse_numeric(recipe_data.high_iso_nr),
        clarity=_parse_numeric(recipe_data.clarity),
        monochromatic_color_warm_cool=_parse_numeric(recipe_data.monochromatic_color_warm_cool),
        monochromatic_color_magenta_green=_parse_numeric(recipe_data.monochromatic_color_magenta_green),
    )

    image, created = Image.update_or_create(
        filepath=image_path,
        filename=filename,
        taken_at=date_taken,
        fujifilm_exif=fujifilm_exif,
        fujifilm_recipe=fujifilm_recipe,
        **exif_fields,
    )

    event_params = {
        "recipe_id": image.pk,
        "filename": filename,
        "film_simulation": fujifilm_exif.film_simulation,
        "taken_at": image.taken_at.isoformat() if image.taken_at else "",
    }
    events.publish_event(
        event_type=events.RECIPE_IMAGE_CREATED if created else events.RECIPE_IMAGE_UPDATED,
        params=event_params,
    )
    return image


def process_images_in_folder(folder: str) -> tuple[int, list[str]]:
    """Process all JPG images in *folder*, skipping those without Fujifilm metadata.

    Returns:
        A tuple of (total_found, skipped_paths).
    """
    paths = queries.collect_image_paths(folder)
    skipped = []
    for path in paths:
        try:
            process_image(path)
        except NoFilmSimulationError:
            skipped.append(path)
    return len(paths), skipped


def reprocess_kelvin_images() -> tuple[int, list[str]]:
    """Reprocess all images whose white balance EXIF value is Kelvin.

    Returns:
        A tuple of (total_found, skipped_paths).
    """
    images = Image.objects.with_kelvin_white_balance().select_related("fujifilm_exif")
    paths = [image.filepath for image in images]
    skipped = []
    for path in paths:
        try:
            process_image(path)
        except NoFilmSimulationError:
            skipped.append(path)
    return len(paths), skipped


def mark_image_as_favorite(image_path: str) -> Image:
    """Find or process the Image for *image_path* and mark it as a favourite.

    If the image is not yet in the database, or the match is ambiguous,
    it is first processed and stored via process_image().

    Raises:
        NoFilmSimulationError: If the image has no Fujifilm metadata.
    """
    try:
        image = queries.find_image_for_path(image_path)
    except (queries.ImageNotFound, queries.AmbiguousImageMatch):
        image = process_image(image_path)
    image.set_as_favorite()
    return image
