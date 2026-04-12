import attrs
import os

from django import conf

from src.data import models
from src.domain.images import events, queries
from src.domain.images.queries import NoFilmSimulationError  # noqa: F401 — re-exported
from src.domain.recipes import operations as recipe_operations


@attrs.frozen
class InvalidImageRatingError(Exception):
    """Raised when a rating value is outside the allowed range [0, IMAGE_MAX_RATING]."""

    rating: int


@attrs.frozen
class UnableToRateImage(Exception):
    """Raised when an image cannot be rated for any reason."""

    image_path: str


def set_image_rating(*, image: models.Image, rating: int) -> None:
    """Set the rating of *image* to *rating*.

    Raises:
        InvalidImageRatingError: If *rating* is negative or exceeds
            settings.IMAGE_MAX_RATING.
    """
    if rating < 0 or rating > conf.settings.IMAGE_MAX_RATING:
        raise InvalidImageRatingError(rating)
    image.set_rating(rating)
    events.publish_event(
        event_type=events.IMAGE_RATING_SET,
        image_id=image.pk,
        rating=rating,
    )


def rate_image(*, image_path: str, rating: int) -> models.Image:
    """Find the Image for *image_path* and set its rating.

    Does not create a new DB record if the image is not found.

    Raises:
        UnableToRateImage: If the image cannot be found, the match is
            ambiguous, or the rating value is invalid.
    """
    try:
        image = queries.find_image_for_path(image_path=image_path)
    except (queries.ImageNotFound, queries.AmbiguousImageMatch) as exc:
        raise UnableToRateImage(image_path) from exc
    try:
        set_image_rating(image=image, rating=rating)
    except InvalidImageRatingError as exc:
        raise UnableToRateImage(image_path) from exc
    return image


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

    fujifilm_recipe = recipe_operations.get_or_create_recipe_from_metadata(metadata=metadata)

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
